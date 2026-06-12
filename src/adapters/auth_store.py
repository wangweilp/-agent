"""Auth Adapter — SQLite 实现的多租户存储 + Workspace 隔离包装器。

两层职责：
  1. SQLiteAuthStore: 用户/Workspace/Membership CRUD
  2. WorkspaceAwareStore: 包装现有 MemoryStore，透明注入 workspace_id
"""
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.core.auth import (
    Membership,
    TokenPayload,
    User,
    Workspace,
    WorkspaceRole,
    WorkspaceStore,
)
from src.core.types import Memory

logger = logging.getLogger(__name__)

# 默认workspace (存量数据归属)
DEFAULT_WORKSPACE_ID = "default"


class SQLiteAuthStore:
    """多租户认证存储的 SQLite 实现。"""

    _AUTH_SCHEMA = """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL DEFAULT '',
            avatar_url TEXT, hashed_password TEXT,
            auth_provider TEXT NOT NULL DEFAULT 'email', auth_provider_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT 'My Workspace',
            owner_id TEXT NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_id);

        CREATE TABLE IF NOT EXISTS memberships (
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'member',
            joined_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, workspace_id)
        );
        CREATE INDEX IF NOT EXISTS idx_memberships_workspace ON memberships(workspace_id);
        CREATE INDEX IF NOT EXISTS idx_memberships_user ON memberships(user_id);

        CREATE TABLE IF NOT EXISTS revoked_tokens (
            jti        TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL,
            revoked_at TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expiry ON revoked_tokens(expires_at);
    """

    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        from sqlite_utils import Database as SqliteDB
        path = db_path or config.sqlite_db_path
        conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=30)
        self._db = SqliteDB(conn)
        self._db.conn.row_factory = sqlite3.Row
        self._write_lock = threading.Lock()
        self._init_schema()
        if path == ":memory:":
            # Store reference to prevent GC
            self._conn = conn

    def _init_schema(self) -> None:
        for stmt in self._AUTH_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)
        # 迁移：为已有 users 表添加 is_super_admin 列（SQLite 不支持 IF NOT EXISTS for ALTER）
        try:
            self._db.execute(
                "ALTER TABLE users ADD COLUMN is_super_admin INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass  # 列已存在
        # autocommit 模式下 commit 是 no-op；非 autocommit 模式下确保 DDL 提交
        try:
            self._db.conn.commit()
        except Exception:
            pass

    # ── 连接管理 ──

    def flush(self) -> None:
        """显式提交底层连接事务，释放写锁。autocommit 模式下为安全 no-op。"""
        try:
            if hasattr(self._db, "conn") and self._db.conn:
                self._db.conn.commit()
        except Exception:
            pass

    # ── User CRUD ──

    def create_user(self, email: str, name: str = "",
                    hashed_password: str | None = None,
                    auth_provider: str = "email",
                    auth_provider_id: str | None = None,
                    is_super_admin: bool = False) -> User:
        user = User(email=email, name=name, hashed_password=hashed_password,
                     auth_provider=auth_provider, auth_provider_id=auth_provider_id,
                     is_super_admin=is_super_admin)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO users (id, email, name, hashed_password,
                   auth_provider, auth_provider_id, is_super_admin, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user.id, user.email, user.name, hashed_password,
                 auth_provider, auth_provider_id,
                 int(user.is_super_admin),
                 user.created_at.isoformat(), user.updated_at.isoformat()),
            )
        logger.info("auth:user_created", extra={"user_id": user.id, "email": email,
                                                "is_super_admin": is_super_admin})
        return user

    def get_user_by_id(self, user_id: str) -> User | None:
        row = self._db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_user(dict(row))

    def get_by_email(self, email: str) -> User | None:
        row = self._db.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower(),)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_user(dict(row))

    def update_user(self, user: User) -> None:
        user.updated_at = datetime.now(timezone.utc)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE users SET name=?, avatar_url=?, hashed_password=?,
                   auth_provider=?, auth_provider_id=?, updated_at=?
                   WHERE id=?""",
                (user.name, user.avatar_url, user.hashed_password,
                 user.auth_provider, user.auth_provider_id,
                 user.updated_at.isoformat(), user.id),
            )

    # ── Workspace CRUD ──

    def create_workspace(self, name: str, owner_id: str) -> Workspace:
        ws = Workspace(name=name, owner_id=owner_id)
        with self._write_lock, self._db.conn:
            self._db.execute(
                "INSERT INTO workspaces (id, name, owner_id, created_at) VALUES (?, ?, ?, ?)",
                (ws.id, ws.name, ws.owner_id, ws.created_at.isoformat()),
            )
            # 自动创建 owner membership
            self._db.execute(
                """INSERT INTO memberships (user_id, workspace_id, role, joined_at)
                   VALUES (?, ?, ?, ?)""",
                (owner_id, ws.id, WorkspaceRole.OWNER.value, ws.created_at.isoformat()),
            )
        logger.info("auth:workspace_created", extra={"ws_id": ws.id, "workspace_name": name})
        return ws

    def get_workspace_by_id(self, workspace_id: str) -> Workspace | None:
        row = self._db.execute(
            "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
        ).fetchone()
        if row is None:
            return None
        r = dict(row)
        return Workspace(id=r["id"], name=r["name"], owner_id=r["owner_id"],
                         created_at=datetime.fromisoformat(r["created_at"]))

    def list_for_user(self, user_id: str) -> list[Workspace]:
        rows = self._db.execute(
            """SELECT w.* FROM workspaces w
               JOIN memberships m ON w.id = m.workspace_id
               WHERE m.user_id = ?
               ORDER BY w.created_at DESC""",
            (user_id,),
        ).fetchall()
        return [
            Workspace(id=r["id"], name=r["name"], owner_id=r["owner_id"],
                      created_at=datetime.fromisoformat(r["created_at"]))
            for r in rows
        ]

    # ── Membership CRUD ──

    def add_member(self, workspace_id: str, user_id: str,
                   role: WorkspaceRole = WorkspaceRole.MEMBER) -> Membership:
        m = Membership(user_id=user_id, workspace_id=workspace_id, role=role)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT OR REPLACE INTO memberships (user_id, workspace_id, role, joined_at)
                   VALUES (?, ?, ?, ?)""",
                (user_id, workspace_id, role.value, m.joined_at.isoformat()),
            )
        return m

    def get_membership(self, workspace_id: str, user_id: str) -> Membership | None:
        row = self._db.execute(
            "SELECT * FROM memberships WHERE workspace_id = ? AND user_id = ?",
            (workspace_id, user_id),
        ).fetchone()
        if row is None:
            return None
        r = dict(row)
        return Membership(user_id=r["user_id"], workspace_id=r["workspace_id"],
                          role=WorkspaceRole(r["role"]))

    def list_members(self, workspace_id: str) -> list[Membership]:
        rows = self._db.execute(
            "SELECT * FROM memberships WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchall()
        return [
            Membership(user_id=r["user_id"], workspace_id=r["workspace_id"],
                       role=WorkspaceRole(r["role"]),
                       joined_at=datetime.fromisoformat(r["joined_at"]))
            for r in rows
        ]

    def update_role(self, workspace_id: str, user_id: str,
                    role: WorkspaceRole) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                "UPDATE memberships SET role = ? WHERE workspace_id = ? AND user_id = ?",
                (role.value, workspace_id, user_id),
            )

    def remove_member(self, workspace_id: str, user_id: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                "DELETE FROM memberships WHERE workspace_id = ? AND user_id = ?",
                (workspace_id, user_id),
            )

    # ── Token Revocation ──

    def revoke_token(self, jti: str, user_id: str, expires_at: datetime) -> None:
        """持久撤销一个 refresh token（存储 jti + 过期时间）。"""
        with self._write_lock, self._db.conn:
            self._db.execute(
                "INSERT OR REPLACE INTO revoked_tokens (jti, user_id, revoked_at, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (jti, user_id, datetime.now(timezone.utc).isoformat(), expires_at.isoformat()),
            )

    def is_token_revoked(self, jti: str) -> bool:
        """检查 token 是否已被撤销。"""
        row = self._db.execute(
            "SELECT 1 FROM revoked_tokens WHERE jti = ?", (jti,)
        ).fetchone()
        return row is not None

    def prune_expired_tokens(self) -> int:
        """清理已过期的撤销记录，返回删除数量。"""
        now = datetime.now(timezone.utc).isoformat()
        with self._write_lock, self._db.conn:
            cur = self._db.execute(
                "DELETE FROM revoked_tokens WHERE expires_at < ?", (now,)
            )
        deleted = cur.rowcount
        if deleted:
            logger.info("auth:pruned_expired_tokens", extra={"count": deleted})
        return deleted

    # ── Super Admin Bootstrap ──

    def ensure_super_admin(self, email: str, password: str, name: str = "Super Admin") -> User | None:
        """确保存在一个超级管理员账号。

        如果 email 对应的用户已存在但非超级管理员，将其提升为超级管理员。
        如果 email 对应的用户不存在，创建新的超级管理员账号。
        密码通过 bcrypt 哈希存储（与 auth_router 一致）。

        Returns:
            创建/更新后的 User，如果无 email/password 则返回 None。
        """
        if not email or not password:
            logger.debug("auth:super_admin_skipped", extra={"reason": "no env credentials"})
            return None

        import bcrypt
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        existing = self.get_by_email(email.lower())
        if existing is not None:
            if existing.is_super_admin:
                logger.info("auth:super_admin_exists", extra={"user_id": existing.id, "email": email})
                return existing
            # 提升已有用户为超级管理员
            existing.is_super_admin = True
            existing.hashed_password = hashed  # 同步更新密码
            existing.updated_at = datetime.now(timezone.utc)
            with self._write_lock, self._db.conn:
                self._db.execute(
                    """UPDATE users SET is_super_admin=1, hashed_password=?, updated_at=?
                       WHERE id=?""",
                    (existing.hashed_password, existing.updated_at.isoformat(), existing.id),
                )
            logger.info("auth:user_promoted_to_super_admin",
                        extra={"user_id": existing.id, "email": email})
            return existing

        # 创建新的超级管理员
        user = self.create_user(
            email=email.lower(),
            name=name,
            hashed_password=hashed,
            is_super_admin=True,
        )
        logger.info("auth:super_admin_created",
                    extra={"user_id": user.id, "email": email})
        return user

    # ── Internal ──

    @staticmethod
    def _row_to_user(row: dict) -> User:
        return User(
            id=row["id"],
            email=row["email"],
            name=row.get("name", ""),
            avatar_url=row.get("avatar_url"),
            hashed_password=row.get("hashed_password"),
            auth_provider=row.get("auth_provider", "email"),
            auth_provider_id=row.get("auth_provider_id"),
            is_super_admin=bool(row.get("is_super_admin", 0)),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def close(self) -> None:
        if hasattr(self._db, "conn") and self._db.conn:
            self._db.conn.close()

    def __enter__(self) -> "SQLiteAuthStore":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ── Workspace Filter Wrapper ──


class WorkspaceContext:
    """请求级别的 workspace 上下文（thread-local）。"""
    _ctx = threading.local()

    @classmethod
    def set(cls, payload: TokenPayload | None) -> None:
        cls._ctx.payload = payload

    @classmethod
    def get(cls) -> TokenPayload | None:
        return getattr(cls._ctx, "payload", None)

    @classmethod
    def workspace_id(cls) -> str:
        p = cls.get()
        return p.workspace_id if p else DEFAULT_WORKSPACE_ID


class WorkspaceAwareStore:
    """包装 MemoryStore，自动在查询中注入 workspace_id 过滤。

    核心原则：不修改 core 层 MemoryStore 协议，在 adapter 层做隔离。
    写入默认走 inner store（workspace_id 由 schema default 或 context 注入）。
    读取时追加 WHERE workspace_id = ?。
    """

    def __init__(self, inner_store):
        self._inner = inner_store

    @property
    def _ws(self) -> str:
        return WorkspaceContext.workspace_id()

    # ── 写入委托给 inner ──

    def store(self, memory: Memory) -> str:
        return self._inner.store(memory)

    def delete(self, memory_id: str) -> None:
        self._inner.delete(memory_id)

    def get_by_id(self, memory_id: str) -> Memory | None:
        return self._inner.get_by_id(memory_id)

    def update_status(self, memory_id: str, status: str) -> None:
        self._inner.update_status(memory_id, status)

    def search_by_entity(self, entity_name: str) -> list[Memory]:
        return self._inner.search_by_entity(entity_name)

    # ── 读取追加 workspace 过滤 ──

    def get_recent(self, limit: int) -> list[Memory]:
        rows = self._inner._db.execute(
            "SELECT * FROM notes WHERE workspace_id = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (self._ws, limit),
        ).fetchall()
        return [self._inner._row_to_memory(dict(r)) for r in rows]

    def list_all(self) -> list[Memory]:
        rows = self._inner._db.execute(
            "SELECT * FROM notes WHERE workspace_id = ? ORDER BY timestamp DESC",
            (self._ws,),
        ).fetchall()
        return [self._inner._row_to_memory(dict(r)) for r in rows]

    def list_by_status(self, status: str) -> list[Memory]:
        rows = self._inner._db.execute(
            "SELECT * FROM notes WHERE status = ? AND workspace_id = ? "
            "ORDER BY timestamp DESC",
            (status, self._ws),
        ).fetchall()
        return [self._inner._row_to_memory(dict(r)) for r in rows]

    def __getattr__(self, name: str):
        return getattr(self._inner, name)
