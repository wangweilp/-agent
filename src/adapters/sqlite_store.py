"""SQLite 记忆存储适配器 — 实现 MemoryStore 协议。

管理 notes / entities / memory_entities / relations 四张表。
语义搜索职责由上层 Retriever 编排，不在此层实现。
"""
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from sqlite_utils import Database

from src.adapters.config import Settings
from src.core.types import Memory

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys = ON;

-- ── Memory Tables (workspace_id + multi-tenant added by migration) ──

CREATE TABLE IF NOT EXISTS notes (
    id             TEXT PRIMARY KEY,
    content        TEXT NOT NULL,
    summary        TEXT,
    source         TEXT,
    timestamp      TEXT NOT NULL,
    importance     INTEGER NOT NULL DEFAULT 5,
    entities_json  TEXT NOT NULL DEFAULT '[]',
    relations_json TEXT NOT NULL DEFAULT '[]',
    memory_type    TEXT DEFAULT 'episodic',
    access_count   INTEGER NOT NULL DEFAULT 0,
    last_accessed  TEXT,
    status         TEXT NOT NULL DEFAULT 'active',
    archived_at    TEXT
);

CREATE TABLE IF NOT EXISTS entities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    entity_type   TEXT DEFAULT '',
    first_seen    TEXT NOT NULL DEFAULT (datetime('now')),
    mention_count INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);

CREATE TABLE IF NOT EXISTS memory_entities (
    memory_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    PRIMARY KEY (memory_id, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_me_memory ON memory_entities(memory_id);
CREATE INDEX IF NOT EXISTS idx_me_entity ON memory_entities(entity_id);

CREATE TABLE IF NOT EXISTS relations (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    subject   TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rel_memory ON relations(memory_id);
CREATE INDEX IF NOT EXISTS idx_rel_subject ON relations(subject);
CREATE INDEX IF NOT EXISTS idx_rel_object ON relations(object);
"""


class MemoryStoreError(Exception):
    """记忆存储错误。"""


class SQLiteStoreAdapter:
    """MemoryStore 的 SQLite 实现。"""

    def __init__(
        self,
        config: Settings,
        db_path: str | None = None,
    ) -> None:
        self._write_lock = threading.Lock()

        path = db_path or config.sqlite_db_path
        if path == ":memory:":
            self._db = Database(memory=True)
        else:
            conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=30)
            self._db = Database(conn)

        self._init_schema()

    def _init_schema(self) -> None:
        self._db.conn.row_factory = sqlite3.Row
        for statement in _SCHEMA_SQL.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                self._db.execute(stmt)
        self._run_migrations()
        # autocommit 模式下 commit 是 no-op；非 autocommit 模式下确保 DDL 提交
        try:
            self._db.conn.commit()
        except Exception:
            pass

    def _run_migrations(self) -> None:
        """幂等 migration：为存量数据库增加 lifecycle + 多租户字段。"""
        existing = {r["name"] for r in self._db.execute("PRAGMA table_info(notes)").fetchall()}
        if "status" not in existing:
            self._db.execute("ALTER TABLE notes ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            logger.info("migration: added notes.status")
        if "archived_at" not in existing:
            self._db.execute("ALTER TABLE notes ADD COLUMN archived_at TEXT")
            logger.info("migration: added notes.archived_at")
        if "last_accessed" not in existing:
            self._db.execute("ALTER TABLE notes ADD COLUMN last_accessed TEXT")
            logger.info("migration: added notes.last_accessed")
        if "workspace_id" not in existing:
            self._db.execute("ALTER TABLE notes ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
            self._db.execute("CREATE INDEX IF NOT EXISTS idx_notes_workspace ON notes(workspace_id)")
            logger.info("migration: added notes.workspace_id")

        # entities table workspace_id
        ent_cols = {r["name"] for r in self._db.execute("PRAGMA table_info(entities)").fetchall()}
        if "workspace_id" not in ent_cols:
            self._db.execute("ALTER TABLE entities ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
            self._db.execute("CREATE INDEX IF NOT EXISTS idx_entities_workspace ON entities(workspace_id)")
            logger.info("migration: added entities.workspace_id")

        # relations table workspace_id
        rel_cols = {r["name"] for r in self._db.execute("PRAGMA table_info(relations)").fetchall()}
        if "workspace_id" not in rel_cols:
            self._db.execute("ALTER TABLE relations ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
            self._db.execute("CREATE INDEX IF NOT EXISTS idx_rel_workspace ON relations(workspace_id)")
            logger.info("migration: added relations.workspace_id")

        # New multi-tenant tables
        all_tables = {r["name"] for r in self._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "users" not in all_tables:
            self._db.execute("""
                CREATE TABLE users (
                    id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL DEFAULT '',
                    avatar_url TEXT, hashed_password TEXT,
                    auth_provider TEXT NOT NULL DEFAULT 'email', auth_provider_id TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            self._db.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
            logger.info("migration: created users table")

        if "workspaces" not in all_tables:
            self._db.execute("""
                CREATE TABLE workspaces (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT 'My Workspace',
                    owner_id TEXT NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            self._db.execute("CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_id)")
            logger.info("migration: created workspaces table")

        if "memberships" not in all_tables:
            self._db.execute("""
                CREATE TABLE memberships (
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    role TEXT NOT NULL DEFAULT 'member',
                    joined_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (user_id, workspace_id)
                )
            """)
            self._db.execute("CREATE INDEX IF NOT EXISTS idx_memberships_workspace ON memberships(workspace_id)")
            self._db.execute("CREATE INDEX IF NOT EXISTS idx_memberships_user ON memberships(user_id)")
            logger.info("migration: created memberships table")

    # ── 连接管理 ──────────────────────────────────────────────────────

    def flush(self) -> None:
        """显式提交底层连接事务，释放写锁。autocommit 模式下为安全 no-op。"""
        try:
            if hasattr(self._db, "conn") and self._db.conn:
                self._db.conn.commit()
        except Exception:
            pass

    # ── MemoryStore 协议 ──────────────────────────────────────────────

    def store(self, memory: Memory) -> str:
        archived_at = memory.archived_at.isoformat() if memory.archived_at else None
        with self._write_lock:
            with self._db.conn:
                self._db.execute(
                    """INSERT INTO notes (id, content, summary, source, timestamp,
                       importance, entities_json, relations_json, memory_type,
                       status, archived_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                       content=excluded.content, summary=excluded.summary,
                       source=excluded.source, timestamp=excluded.timestamp,
                       importance=excluded.importance,
                       entities_json=excluded.entities_json,
                       relations_json=excluded.relations_json,
                       memory_type=excluded.memory_type,
                       status=excluded.status,
                       archived_at=excluded.archived_at""",
                    (
                        memory.id, memory.content, memory.summary, memory.source,
                        memory.timestamp.isoformat(), memory.importance,
                        json.dumps(memory.entities, ensure_ascii=False),
                        json.dumps(memory.relations, ensure_ascii=False),
                        memory.memory_type,
                        memory.status,
                        archived_at,
                    ),
                )

                self._db.execute(
                    "DELETE FROM memory_entities WHERE memory_id = ?", (memory.id,)
                )
                self._db.execute(
                    "DELETE FROM relations WHERE memory_id = ?", (memory.id,)
                )

                for entity_name in memory.entities:
                    entity_id = self._ensure_entity(entity_name)
                    self._db.execute(
                        "INSERT INTO memory_entities (memory_id, entity_id) VALUES (?, ?)",
                        (memory.id, entity_id),
                    )

                for rel in memory.relations:
                    self._db.execute(
                        "INSERT INTO relations (memory_id, subject, predicate, object) "
                        "VALUES (?, ?, ?, ?)",
                        (memory.id, rel["s"], rel["p"], rel["o"]),
                    )

        return memory.id

    def delete(self, memory_id: str) -> None:
        """删除一条记忆及其关联的实体/关系记录。"""
        with self._write_lock:
            with self._db.conn:
                self._db.execute(
                    "DELETE FROM memory_entities WHERE memory_id = ?", (memory_id,)
                )
                self._db.execute(
                    "DELETE FROM relations WHERE memory_id = ?", (memory_id,)
                )
                self._db.execute(
                    "DELETE FROM notes WHERE id = ?", (memory_id,)
                )

    def search_by_entity(self, entity_name: str) -> list[Memory]:
        rows = self._db.execute(
            """SELECT n.* FROM notes n
               JOIN memory_entities me ON n.id = me.memory_id
               JOIN entities e ON me.entity_id = e.id
               WHERE e.name = ?
               ORDER BY n.timestamp DESC""",
            (entity_name,),
        ).fetchall()

        return [self._row_to_memory(dict(r)) for r in rows]

    def get_by_id(self, memory_id: str) -> Memory | None:
        """获取单条记忆，同时原子地更新 access_count。

        使用 BEGIN IMMEDIATE 防止 read-modify-write 竞态。
        """
        with self._write_lock:
            with self._db.conn:
                self._db.execute("BEGIN IMMEDIATE")
                row = self._db.execute(
                    "SELECT * FROM notes WHERE id = ?", (memory_id,)
                ).fetchone()
                if row is None:
                    return None

                now = datetime.now(timezone.utc).isoformat()
                self._db.execute(
                    "UPDATE notes SET access_count = access_count + 1,"
                    " last_accessed = ? WHERE id = ?",
                    (now, memory_id),
                )
                row = self._db.execute(
                    "SELECT * FROM notes WHERE id = ?", (memory_id,)
                ).fetchone()
        return self._row_to_memory(dict(row))

    def get_recent(self, limit: int) -> list[Memory]:
        rows = self._db.execute(
            "SELECT * FROM notes ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_memory(dict(r)) for r in rows]

    def list_all(self) -> list[Memory]:
        """列出所有记忆（用于 lifecycle 批量操作）。"""
        rows = self._db.execute(
            "SELECT * FROM notes ORDER BY timestamp DESC"
        ).fetchall()
        return [self._row_to_memory(dict(r)) for r in rows]

    def list_by_status(self, status: str) -> list[Memory]:
        """按状态列出记忆。"""
        rows = self._db.execute(
            "SELECT * FROM notes WHERE status = ? ORDER BY timestamp DESC", (status,)
        ).fetchall()
        return [self._row_to_memory(dict(r)) for r in rows]

    def update_status(self, memory_id: str, status: str) -> None:
        """原子更新单条记忆状态。"""
        with self._write_lock:
            with self._db.conn:
                self._db.execute(
                    "UPDATE notes SET status = ? WHERE id = ?", (status, memory_id)
                )

    # ── 内部方法 ──────────────────────────────────────────────────────

    def _ensure_entity(self, name: str) -> int:
        self._db.execute(
            """INSERT INTO entities (name) VALUES (?)
               ON CONFLICT(name) DO UPDATE SET mention_count = mention_count + 1""",
            (name,),
        )
        row = self._db.execute(
            "SELECT id FROM entities WHERE name = ?", (name,)
        ).fetchone()
        return row["id"]

    @staticmethod
    def _row_to_memory(row: dict) -> Memory:
        entities = json.loads(row.get("entities_json") or "[]")
        relations = json.loads(row.get("relations_json") or "[]")
        timestamp = datetime.fromisoformat(row["timestamp"])
        last_accessed = (
            datetime.fromisoformat(row["last_accessed"])
            if row.get("last_accessed")
            else None
        )
        archived_at = (
            datetime.fromisoformat(row["archived_at"])
            if row.get("archived_at")
            else None
        )
        return Memory(
            id=row["id"],
            content=row["content"],
            summary=row.get("summary"),
            source=row["source"] or "",
            timestamp=timestamp,
            importance=row.get("importance", 5),
            entities=entities,
            relations=relations,
            memory_type=row.get("memory_type", "episodic"),
            access_count=row.get("access_count", 0),
            last_accessed=last_accessed,
            status=row.get("status", "active"),
            archived_at=archived_at,
        )

    def close(self) -> None:
        if hasattr(self._db, "conn") and self._db.conn:
            self._db.conn.close()

    def __enter__(self) -> "SQLiteStoreAdapter":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
