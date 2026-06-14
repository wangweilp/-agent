"""SQLite Agent Module Store — 实现 AgentModuleStore 协议。

约束: metadata_only=True，不执行，不联网，不写文件。
"""

from __future__ import annotations

import json, logging
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.agent_module import (
    AgentModule, AgentModuleNotFoundError, AgentModuleStateError,
    AgentModuleStatus, AgentModuleValidationError, Subscription,
    SubscriptionAlreadyExistsError, SubscriptionNotFoundError,
    is_valid_transition, _safe_parse_dt,
)

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_modules (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    workflow_ids_json TEXT NOT NULL DEFAULT '[]',
    version TEXT NOT NULL DEFAULT '0.1.0',
    status TEXT NOT NULL DEFAULT 'draft',
    metadata_only INTEGER NOT NULL DEFAULT 1,
    author TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    icon_url TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    reviewed_by TEXT,
    reviewed_at TEXT,
    review_comment TEXT,
    published_by TEXT,
    published_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_am_workspace ON agent_modules(workspace_id);
CREATE INDEX IF NOT EXISTS idx_am_status ON agent_modules(status);
CREATE INDEX IF NOT EXISTS idx_am_category ON agent_modules(category);
CREATE INDEX IF NOT EXISTS idx_am_name ON agent_modules(name);

CREATE TABLE IF NOT EXISTS marketplace_subscriptions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    agent_module_id TEXT NOT NULL,
    subscribed_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(workspace_id, agent_module_id)
);
CREATE INDEX IF NOT EXISTS idx_mksub_workspace ON marketplace_subscriptions(workspace_id);
CREATE INDEX IF NOT EXISTS idx_mksub_module ON marketplace_subscriptions(agent_module_id);
"""


class SQLiteAgentModuleStore:
    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="am_init_schema")

    def _init_schema(self) -> None:
        for stmt in _SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)
        try: self._db.conn.commit()
        except Exception: pass

    def flush(self) -> None:
        try:
            if hasattr(self._db, "conn") and self._db.conn:
                self._db.conn.commit()
        except Exception: pass

    def _exec(self, sql: str, params: list[Any] | None = None) -> Any:
        return self._db.execute(sql, params or [])

    # ── AgentModule CRUD ──

    def create(self, m: AgentModule) -> AgentModule:
        m.metadata_only = True
        errors = m.validate()
        if errors:
            raise AgentModuleValidationError(f"AgentModule 校验失败: {'; '.join(errors)}", errors)
        if m.status != AgentModuleStatus.DRAFT:
            raise AgentModuleStateError(f"新建状态必须为 draft，当前: {m.status}")
        self._exec("""INSERT INTO agent_modules (
            id, workspace_id, name, description, workflow_ids_json, version,
            status, metadata_only,
            author, category, icon_url, tags_json,
            reviewed_by, reviewed_at, review_comment, published_by, published_at,
            metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            m.id, m.workspace_id, m.name, m.description,
            json.dumps(m.workflow_ids, ensure_ascii=False), m.version,
            m.status, 1,
            m.author, m.category, m.icon_url, json.dumps(m.tags, ensure_ascii=False),
            m.reviewed_by, m.reviewed_at.isoformat() if m.reviewed_at else None,
            m.review_comment, m.published_by,
            m.published_at.isoformat() if m.published_at else None,
            json.dumps(m.metadata, ensure_ascii=False),
        ])
        return m

    def get(self, agent_module_id: str) -> AgentModule | None:
        row = next(self._exec("SELECT * FROM agent_modules WHERE id=?", [agent_module_id]), None)
        return self._row_to_module(dict(row)) if row else None

    def list(self, *, workspace_id: str = "", status: str = "",
             category: str = "", limit: int = 50, offset: int = 0) -> list[AgentModule]:
        sql = "SELECT * FROM agent_modules WHERE 1=1"
        params: list[Any] = []
        if workspace_id:
            sql += " AND workspace_id=?"
            params.append(workspace_id)
        if status:
            sql += " AND status=?"
            params.append(status)
        if category:
            sql += " AND category=?"
            params.append(category)
        sql += " ORDER BY created_at DESC"
        sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        return [self._row_to_module(dict(r)) for r in self._exec(sql, params)]

    def search(self, q: str, *, category: str = "", limit: int = 50) -> list[AgentModule]:
        """关键词搜索 — 在 name/description/tags 中模糊匹配。"""
        sql = "SELECT * FROM agent_modules WHERE status='published'"
        params: list[Any] = []
        if q:
            sql += " AND (name LIKE ? OR description LIKE ? OR tags_json LIKE ?)"
            like = f"%{q}%"
            params.extend([like, like, like])
        if category:
            sql += " AND category=?"
            params.append(category)
        sql += f" ORDER BY created_at DESC LIMIT {int(limit)}"
        return [self._row_to_module(dict(r)) for r in self._exec(sql, params)]

    def update(self, m: AgentModule) -> None:
        existing = self.get(m.id)
        if existing is None:
            raise AgentModuleNotFoundError(f"AgentModule 不存在: {m.id}")
        if not existing.is_editable():
            raise AgentModuleStateError(f"状态 '{existing.status}' 不允许编辑")
        m.metadata_only = True
        m.status = existing.status
        errors = m.validate()
        if errors:
            raise AgentModuleValidationError(f"校验失败: {'; '.join(errors)}", errors)
        self._exec("""UPDATE agent_modules SET
            workspace_id=?, name=?, description=?, workflow_ids_json=?, version=?,
            metadata_only=1, author=?, category=?, icon_url=?, tags_json=?,
            metadata_json=?, updated_at=?
            WHERE id=?""", [
            m.workspace_id, m.name, m.description,
            json.dumps(m.workflow_ids, ensure_ascii=False), m.version,
            m.author, m.category, m.icon_url, json.dumps(m.tags, ensure_ascii=False),
            json.dumps(m.metadata, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(), m.id,
        ])

    def update_status(self, agent_module_id: str, status: str,
                      reviewed_by: str | None = None, review_comment: str | None = None,
                      published_by: str | None = None) -> None:
        existing = self.get(agent_module_id)
        if existing is None:
            raise AgentModuleNotFoundError(f"AgentModule 不存在: {agent_module_id}")
        if not is_valid_transition(existing.status, status):
            raise AgentModuleStateError(f"状态迁移非法: {existing.status} → {status}")
        now = datetime.now(timezone.utc).isoformat()
        if status in (AgentModuleStatus.APPROVED, AgentModuleStatus.REJECTED):
            self._exec("UPDATE agent_modules SET status=?, reviewed_by=?, reviewed_at=?, review_comment=?, updated_at=? WHERE id=?",
                       [status, reviewed_by, now, review_comment, now, agent_module_id])
        elif status == AgentModuleStatus.PUBLISHED:
            self._exec("UPDATE agent_modules SET status=?, published_by=?, published_at=?, updated_at=? WHERE id=?",
                       [status, published_by, now, now, agent_module_id])
        elif status == AgentModuleStatus.DRAFT:
            self._exec("UPDATE agent_modules SET status=?, review_comment=NULL, updated_at=? WHERE id=?",
                       [status, now, agent_module_id])
        else:
            self._exec("UPDATE agent_modules SET status=?, updated_at=? WHERE id=?",
                       [status, now, agent_module_id])

    def delete(self, agent_module_id: str) -> None:
        existing = self.get(agent_module_id)
        if existing is None:
            raise AgentModuleNotFoundError(f"AgentModule 不存在: {agent_module_id}")
        if existing.status not in (AgentModuleStatus.DRAFT, AgentModuleStatus.REJECTED):
            raise AgentModuleStateError(f"状态 '{existing.status}' 不允许删除")
        self._exec("DELETE FROM agent_modules WHERE id=?", [agent_module_id])

    # ── Subscription ──

    def subscribe(self, sub: Subscription) -> Subscription:
        existing = self._exec(
            "SELECT * FROM marketplace_subscriptions WHERE workspace_id=? AND agent_module_id=?",
            [sub.workspace_id, sub.agent_module_id])
        if next(existing, None):
            raise SubscriptionAlreadyExistsError(f"已订阅 {sub.agent_module_id}")
        self._exec("INSERT INTO marketplace_subscriptions (id, workspace_id, agent_module_id, active) VALUES (?,?,?,?)",
                   [sub.id, sub.workspace_id, sub.agent_module_id, 1])
        return sub

    def unsubscribe(self, workspace_id: str, agent_module_id: str) -> None:
        row = next(self._exec(
            "SELECT * FROM marketplace_subscriptions WHERE workspace_id=? AND agent_module_id=? AND active=1",
            [workspace_id, agent_module_id]), None)
        if not row:
            raise SubscriptionNotFoundError(f"订阅不存在: {workspace_id}/{agent_module_id}")
        self._exec("UPDATE marketplace_subscriptions SET active=0 WHERE workspace_id=? AND agent_module_id=?",
                   [workspace_id, agent_module_id])

    def list_subscriptions(self, workspace_id: str) -> list[Subscription]:
        rows = self._exec(
            "SELECT * FROM marketplace_subscriptions WHERE workspace_id=? AND active=1 ORDER BY subscribed_at DESC",
            [workspace_id])
        return [self._row_to_subscription(dict(r)) for r in rows]

    def get_subscription(self, workspace_id: str, agent_module_id: str) -> Subscription | None:
        row = next(self._exec(
            "SELECT * FROM marketplace_subscriptions WHERE workspace_id=? AND agent_module_id=? AND active=1",
            [workspace_id, agent_module_id]), None)
        return self._row_to_subscription(dict(row)) if row else None

    # ── Row → Domain ──

    @staticmethod
    def _row_to_module(row: dict) -> AgentModule:
        return AgentModule(
            id=row["id"], workspace_id=row.get("workspace_id", ""),
            name=row.get("name", ""), description=row.get("description", ""),
            workflow_ids=json.loads(row.get("workflow_ids_json", "[]")),
            version=row.get("version", "0.1.0"),
            status=row.get("status", "draft"), metadata_only=True,
            author=row.get("author", ""), category=row.get("category", ""),
            icon_url=row.get("icon_url", ""),
            tags=json.loads(row.get("tags_json", "[]")),
            reviewed_by=row.get("reviewed_by"),
            reviewed_at=_safe_parse_dt(row.get("reviewed_at")),
            review_comment=row.get("review_comment"),
            published_by=row.get("published_by"),
            published_at=_safe_parse_dt(row.get("published_at")),
            metadata=json.loads(row.get("metadata_json", "{}")),
            created_at=_safe_parse_dt(row.get("created_at")),
            updated_at=_safe_parse_dt(row.get("updated_at")),
        )

    @staticmethod
    def _row_to_subscription(row: dict) -> Subscription:
        return Subscription(
            id=row["id"], workspace_id=row.get("workspace_id", ""),
            agent_module_id=row.get("agent_module_id", ""),
            subscribed_at=_safe_parse_dt(row.get("subscribed_at")),
            active=bool(row.get("active", 1)),
        )
