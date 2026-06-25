"""AnalyticsStore — Dashboard V2 Analytics Pipeline 统一写入入口。

设计原则：
- async first：所有写入方法为 async，内部用 asyncio.to_thread 包装 sqlite3 同步调用
- tenant aware / workspace aware：所有记录都带 tenant_id + workspace_id
- 失败不影响主业务流程：内部异常自动降级日志记录，不抛出
- 幂等 schema：_init_schema() 使用 CREATE TABLE IF NOT EXISTS

写入方法：
- record_agent_run(status, duration_ms, prompt_tokens, completion_tokens, cost_usd)
- record_memory_event(event_type, memory_type, hit)
- record_user_activity(user_id, event_date, sessions, messages, active_minutes)
- record_token_usage(event_date, prompt_tokens, completion_tokens, cost_usd)

依赖：sqlite3（标准库）+ asyncio（标准库），不引入 sqlalchemy/aiosqlite，与项目现有架构一致。
"""
import asyncio
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from uuid import uuid4

from src.adapters.config import Settings

logger = logging.getLogger(__name__)


# ── Schema（与 docs/sql/analytics_pipeline_schema.sql 一致）──

_ANALYTICS_SCHEMA = """
CREATE TABLE IF NOT EXISTS analytics_user_activity_daily (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    workspace_id    TEXT NOT NULL DEFAULT '',
    user_id         TEXT NOT NULL,
    event_date      TEXT NOT NULL,
    sessions        INTEGER NOT NULL DEFAULT 0,
    messages        INTEGER NOT NULL DEFAULT 0,
    active_minutes  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_auad_tenant_date ON analytics_user_activity_daily(tenant_id, event_date);
CREATE INDEX IF NOT EXISTS idx_auad_user_date ON analytics_user_activity_daily(user_id, event_date);
CREATE INDEX IF NOT EXISTS idx_auad_date ON analytics_user_activity_daily(event_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_auad_unique ON analytics_user_activity_daily(tenant_id, user_id, event_date);

CREATE TABLE IF NOT EXISTS analytics_agent_runs (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    workspace_id        TEXT NOT NULL DEFAULT '',
    agent_name          TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL,
    duration_ms         REAL NOT NULL DEFAULT 0,
    prompt_tokens       INTEGER NOT NULL DEFAULT 0,
    completion_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd            REAL NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_aar_tenant_created ON analytics_agent_runs(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_aar_status ON analytics_agent_runs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_aar_agent ON analytics_agent_runs(agent_name, created_at);

CREATE TABLE IF NOT EXISTS analytics_memory_events (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    workspace_id    TEXT NOT NULL DEFAULT '',
    memory_type     TEXT NOT NULL DEFAULT '',
    event_type      TEXT NOT NULL,
    hit             INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ame_tenant_type ON analytics_memory_events(tenant_id, event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_ame_created ON analytics_memory_events(created_at);

CREATE TABLE IF NOT EXISTS analytics_token_usage_daily (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    workspace_id        TEXT NOT NULL DEFAULT '',
    event_date          TEXT NOT NULL,
    prompt_tokens       INTEGER NOT NULL DEFAULT 0,
    completion_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd            REAL NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_atud_tenant_date ON analytics_token_usage_daily(tenant_id, event_date);
CREATE INDEX IF NOT EXISTS idx_atud_date ON analytics_token_usage_daily(event_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_atud_unique ON analytics_token_usage_daily(tenant_id, workspace_id, event_date);
"""


class AnalyticsStore:
    """Dashboard V2 Analytics Pipeline 统一写入入口。

    所有写入方法为 async，内部用 asyncio.to_thread 包装 sqlite3 同步调用。
    失败时仅记录日志，不抛出异常，不影响主业务流程。
    """

    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        path = db_path or config.sqlite_db_path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._write_lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        """幂等初始化 4 张 analytics 表。"""
        with self._write_lock:
            for stmt in _ANALYTICS_SCHEMA.strip().split(";"):
                s = stmt.strip()
                if s:
                    try:
                        self._conn.execute(s)
                    except sqlite3.Error:
                        logger.warning("analytics_schema_init_failed", exc_info=True)
            self._conn.commit()

    def close(self) -> None:
        """关闭数据库连接。"""
        try:
            self._conn.close()
        except Exception:
            logger.warning("analytics_store_close_failed", exc_info=True)

    # ── 私有：同步写入辅助 ────────────────────────────────

    def _exec_sync(self, sql: str, params: tuple) -> None:
        """同步执行写入（线程安全）。异常仅记录日志。"""
        with self._write_lock:
            try:
                self._conn.execute(sql, params)
                self._conn.commit()
            except sqlite3.Error:
                logger.warning("analytics_write_failed", exc_info=True, extra={"sql": sql[:80]})

    # ── 公开：async 写入方法 ──────────────────────────────

    async def record_agent_run(
        self,
        tenant_id: str,
        workspace_id: str,
        agent_name: str,
        status: str,
        duration_ms: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> str:
        """记录一次 Agent 运行。

        Args:
            status: "success" | "failed"
            duration_ms: 执行耗时（毫秒）
            cost_usd: 本次运行成本（美元）
        Returns:
            记录 ID
        """
        run_id = f"ar_{uuid4().hex[:16]}"
        now = datetime.now(timezone.utc).isoformat()
        await asyncio.to_thread(
            self._exec_sync,
            """INSERT INTO analytics_agent_runs
               (id, tenant_id, workspace_id, agent_name, status, duration_ms,
                prompt_tokens, completion_tokens, cost_usd, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, tenant_id, workspace_id, agent_name, status, duration_ms,
             prompt_tokens, completion_tokens, cost_usd, now),
        )
        return run_id

    async def record_memory_event(
        self,
        tenant_id: str,
        workspace_id: str,
        memory_type: str,
        event_type: str,
        hit: bool = False,
    ) -> str:
        """记录一次 Memory 事件。

        Args:
            event_type: "INSERT" | "UPDATE" | "DELETE" | "HIT"
            memory_type: episodic | semantic | reflect
            hit: 是否命中检索（仅 HIT 事件为 True）
        Returns:
            记录 ID
        """
        event_id = f"me_{uuid4().hex[:16]}"
        now = datetime.now(timezone.utc).isoformat()
        await asyncio.to_thread(
            self._exec_sync,
            """INSERT INTO analytics_memory_events
               (id, tenant_id, workspace_id, memory_type, event_type, hit, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_id, tenant_id, workspace_id, memory_type, event_type,
             1 if hit else 0, now),
        )
        return event_id

    async def record_user_activity(
        self,
        tenant_id: str,
        workspace_id: str,
        user_id: str,
        event_date: str,
        sessions: int = 1,
        messages: int = 0,
        active_minutes: int = 0,
    ) -> str:
        """记录用户日活（按 tenant+user+date 聚合，UPSERT）。

        Args:
            event_date: YYYY-MM-DD
            sessions: 本次会话数（累加）
            messages: 本次消息数（累加）
        Returns:
            记录 ID
        """
        record_id = f"ua_{uuid4().hex[:16]}"
        now = datetime.now(timezone.utc).isoformat()
        await asyncio.to_thread(
            self._exec_sync,
            """INSERT INTO analytics_user_activity_daily
               (id, tenant_id, workspace_id, user_id, event_date,
                sessions, messages, active_minutes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(tenant_id, user_id, event_date) DO UPDATE SET
                 sessions = sessions + excluded.sessions,
                 messages = messages + excluded.messages,
                 active_minutes = active_minutes + excluded.active_minutes""",
            (record_id, tenant_id, workspace_id, user_id, event_date,
             sessions, messages, active_minutes, now),
        )
        return record_id

    async def record_token_usage(
        self,
        tenant_id: str,
        workspace_id: str,
        event_date: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> str:
        """记录 Token 日用量（按 tenant+workspace+date 聚合，UPSERT）。

        Args:
            event_date: YYYY-MM-DD
            cost_usd: 本次成本（美元）
        Returns:
            记录 ID
        """
        record_id = f"tu_{uuid4().hex[:16]}"
        now = datetime.now(timezone.utc).isoformat()
        await asyncio.to_thread(
            self._exec_sync,
            """INSERT INTO analytics_token_usage_daily
               (id, tenant_id, workspace_id, event_date,
                prompt_tokens, completion_tokens, cost_usd, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(tenant_id, workspace_id, event_date) DO UPDATE SET
                 prompt_tokens = prompt_tokens + excluded.prompt_tokens,
                 completion_tokens = completion_tokens + excluded.completion_tokens,
                 cost_usd = cost_usd + excluded.cost_usd""",
            (record_id, tenant_id, workspace_id, event_date,
             prompt_tokens, completion_tokens, cost_usd, now),
        )
        return record_id

    # ── 同步查询辅助（供 AnalyticsRepository 使用）──

    @property
    def conn(self) -> sqlite3.Connection:
        """暴露底层连接，供 AnalyticsRepository 同步查询。"""
        return self._conn
