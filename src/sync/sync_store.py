"""SyncStore — SQLite persistence for sync jobs, rules, executions, and changes.

Follows the same pattern as src/adapters/sqlite_store.py and the
ImportHistory class in src/core/import_worker.py.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.adapters.config import Settings
from src.adapters.auth_store import WorkspaceContext
from src.sync.models import (
    EXECUTION_STATUS_ACTIVE,
    JOB_STATUS_ACTIVE,
    SyncConnectorConfig,
    SyncRule,
    SyncJob,
    SyncExecution,
    ChangeRecord,
)

logger = logging.getLogger(__name__)

_DB_FILENAME = "sync_store.db"


class SyncStore:
    """Thread-safe SQLite store for all sync entities."""

    def __init__(self, settings: Settings) -> None:
        configured_path = str(getattr(settings, "sqlite_db_path", "./data"))
        if configured_path == ":memory:":
            self._db_path = configured_path
            self._lock = threading.Lock()
            self._conn: sqlite3.Connection | None = None
            self._init_db()
            return

        base_path = Path(configured_path)
        db_dir = base_path.parent if base_path.suffix or base_path.is_file() else base_path
        db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = db_dir / _DB_FILENAME
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    # ── Internal ──

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS sync_connectors (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            connector_type TEXT NOT NULL,
            credentials_json TEXT NOT NULL DEFAULT '{}',
            enabled INTEGER NOT NULL DEFAULT 1,
            last_sync_time TEXT,
            last_sync_status TEXT DEFAULT 'never',
            etag_map_json TEXT DEFAULT '{}',
            hash_map_json TEXT DEFAULT '{}',
            version_map_json TEXT DEFAULT '{}',
            workspace_id TEXT NOT NULL DEFAULT 'default',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sync_rules (
            id TEXT PRIMARY KEY,
            rule_type TEXT NOT NULL DEFAULT 'manual',
            cron_expression TEXT DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            webhook_url TEXT DEFAULT '',
            webhook_secret TEXT DEFAULT '',
            workspace_id TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE IF NOT EXISTS sync_jobs (
            id TEXT PRIMARY KEY,
            connector_config_id TEXT NOT NULL REFERENCES sync_connectors(id) ON DELETE CASCADE,
            rule_id TEXT NOT NULL REFERENCES sync_rules(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            enabled INTEGER NOT NULL DEFAULT 1,
            workspace_id TEXT NOT NULL DEFAULT 'default',
            created_at TEXT NOT NULL,
            started_at TEXT,
            heartbeat_at TEXT,
            worker_id TEXT DEFAULT '',
            attempt_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sync_executions (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES sync_jobs(id) ON DELETE CASCADE,
            status TEXT DEFAULT 'pending',
            started_at TEXT,
            completed_at TEXT,
            items_fetched INTEGER DEFAULT 0,
            items_new INTEGER DEFAULT 0,
            items_updated INTEGER DEFAULT 0,
            items_deleted INTEGER DEFAULT 0,
            items_renamed INTEGER DEFAULT 0,
            memories_created INTEGER DEFAULT 0,
            errors_count INTEGER DEFAULT 0,
            error TEXT,
            elapsed_ms INTEGER DEFAULT 0,
            workspace_id TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE IF NOT EXISTS sync_changes (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL REFERENCES sync_executions(id) ON DELETE CASCADE,
            connector_type TEXT NOT NULL,
            resource_id TEXT NOT NULL,
            change_type TEXT NOT NULL,
            content_hash TEXT DEFAULT '',
            previous_hash TEXT DEFAULT '',
            content_preview TEXT DEFAULT '',
            content_type TEXT DEFAULT '',
            metadata_json TEXT DEFAULT '{}',
            processed INTEGER NOT NULL DEFAULT 0,
            process_error TEXT,
            detected_at TEXT NOT NULL,
            workspace_id TEXT NOT NULL DEFAULT 'default'
        );
        CREATE INDEX IF NOT EXISTS idx_changes_exec ON sync_changes(execution_id);
        CREATE INDEX IF NOT EXISTS idx_changes_resource ON sync_changes(connector_type, resource_id);
        CREATE INDEX IF NOT EXISTS idx_executions_job ON sync_executions(job_id);
        """)
        conn.commit()
        self._run_migrations()

    def _run_migrations(self) -> None:
        """Idempotent migration: add workspace_id columns to pre-existing tables."""
        conn = self._get_conn()
        for table, col in (
            ("sync_connectors", "workspace_id"),
            ("sync_rules", "workspace_id"),
            ("sync_jobs", "workspace_id"),
            ("sync_executions", "workspace_id"),
            ("sync_changes", "workspace_id"),
        ):
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if col not in cols:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {col} TEXT NOT NULL DEFAULT 'default'"
                )
                logger.info("migration: added %s.%s", table, col)
        for table, idx in (
            ("sync_connectors", "idx_connectors_ws"),
            ("sync_rules", "idx_rules_ws"),
            ("sync_jobs", "idx_jobs_ws"),
            ("sync_executions", "idx_executions_ws"),
            ("sync_changes", "idx_changes_ws"),
        ):
            conn.execute(f"CREATE INDEX IF NOT EXISTS {idx} ON {table}(workspace_id)")

        # P1: sync_jobs 生命周期字段迁移
        job_cols = {r["name"] for r in conn.execute("PRAGMA table_info(sync_jobs)").fetchall()}
        for col, ddl in (
            ("started_at", "TEXT"),
            ("heartbeat_at", "TEXT"),
            ("worker_id", "TEXT DEFAULT ''"),
            ("attempt_count", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if col not in job_cols:
                conn.execute(f"ALTER TABLE sync_jobs ADD COLUMN {col} {ddl}")
                logger.info("migration: added sync_jobs.%s", col)
        conn.commit()

    @staticmethod
    def _resolve_workspace(workspace_id: str | None) -> str:
        """Resolve the effective workspace, defaulting to the request context."""
        return workspace_id or WorkspaceContext.workspace_id()

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    # ── Connectors ──

    def save_connector(
        self, config: SyncConnectorConfig, workspace_id: str | None = None
    ) -> SyncConnectorConfig:
        ws = self._resolve_workspace(workspace_id or config.workspace_id)
        config.workspace_id = ws
        with self._lock:
            conn = self._get_conn()
            # ON CONFLICT(id) DO UPDATE 而非 REPLACE：避免 REPLACE 先 DELETE 旧行，
            # 触发 sync_jobs.connector_config_id 的 ON DELETE CASCADE 清空其 Job。
            conn.execute(
                """INSERT INTO sync_connectors
                   (id, name, connector_type, credentials_json, enabled,
                    last_sync_time, last_sync_status, etag_map_json, hash_map_json,
                    version_map_json, workspace_id, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                   name=excluded.name,
                   connector_type=excluded.connector_type,
                   credentials_json=excluded.credentials_json,
                   enabled=excluded.enabled,
                   last_sync_time=excluded.last_sync_time,
                   last_sync_status=excluded.last_sync_status,
                   etag_map_json=excluded.etag_map_json,
                   hash_map_json=excluded.hash_map_json,
                   version_map_json=excluded.version_map_json,
                   workspace_id=excluded.workspace_id,
                   updated_at=excluded.updated_at""",
                (
                    config.id, config.name, config.connector_type,
                    json.dumps(config.credentials, ensure_ascii=False),
                    1 if config.enabled else 0,
                    config.last_sync_time.isoformat() if config.last_sync_time else None,
                    config.last_sync_status,
                    json.dumps(config.etag_map, ensure_ascii=False),
                    json.dumps(config.hash_map, ensure_ascii=False),
                    json.dumps(config.version_map, ensure_ascii=False),
                    ws,
                    config.created_at.isoformat(),
                    config.updated_at.isoformat(),
                ),
            )
            conn.commit()
        return config

    def get_connector(
        self, connector_id: str, workspace_id: str | None = None
    ) -> SyncConnectorConfig | None:
        ws = self._resolve_workspace(workspace_id)
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM sync_connectors WHERE id = ? AND workspace_id = ?",
            (connector_id, ws),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_connector(row)

    def list_connectors(self, workspace_id: str | None = None) -> list[SyncConnectorConfig]:
        ws = self._resolve_workspace(workspace_id)
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM sync_connectors WHERE workspace_id = ? ORDER BY updated_at DESC",
            (ws,),
        ).fetchall()
        return [self._row_to_connector(r) for r in rows]

    def update_connector(
        self, config: SyncConnectorConfig, workspace_id: str | None = None
    ) -> SyncConnectorConfig:
        return self.save_connector(config, workspace_id=workspace_id)

    def delete_connector(self, connector_id: str, workspace_id: str | None = None) -> bool:
        ws = self._resolve_workspace(workspace_id)
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "DELETE FROM sync_connectors WHERE id = ? AND workspace_id = ?",
                (connector_id, ws),
            )
            conn.commit()
            return cur.rowcount > 0

    def _row_to_connector(self, row: sqlite3.Row) -> SyncConnectorConfig:
        from datetime import datetime, timezone

        def _parse_dt(val: str | None) -> datetime | None:
            if not val:
                return None
            try:
                return datetime.fromisoformat(val)
            except (ValueError, TypeError):
                return None

        return SyncConnectorConfig(
            id=row["id"],
            name=row["name"],
            connector_type=row["connector_type"],
            credentials=json.loads(row["credentials_json"] or "{}"),
            enabled=bool(row["enabled"]),
            last_sync_time=_parse_dt(row["last_sync_time"]),
            last_sync_status=row["last_sync_status"] or "never",
            etag_map=json.loads(row["etag_map_json"] or "{}"),
            hash_map=json.loads(row["hash_map_json"] or "{}"),
            version_map=json.loads(row["version_map_json"] or "{}"),
            created_at=_parse_dt(row["created_at"]) or datetime.now(timezone.utc),
            updated_at=_parse_dt(row["updated_at"]) or datetime.now(timezone.utc),
            workspace_id=row["workspace_id"] or "default",
        )

    # ── Rules ──

    def save_rule(
        self, rule: SyncRule, workspace_id: str | None = None
    ) -> SyncRule:
        ws = self._resolve_workspace(workspace_id or rule.workspace_id)
        rule.workspace_id = ws
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """INSERT INTO sync_rules
                   (id, rule_type, cron_expression, enabled, webhook_url, webhook_secret, workspace_id)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                   rule_type=excluded.rule_type,
                   cron_expression=excluded.cron_expression,
                   enabled=excluded.enabled,
                   webhook_url=excluded.webhook_url,
                   webhook_secret=excluded.webhook_secret,
                   workspace_id=excluded.workspace_id""",
                (
                    rule.id, rule.rule_type, rule.cron_expression,
                    1 if rule.enabled else 0, rule.webhook_url, rule.webhook_secret,
                    ws,
                ),
            )
            conn.commit()
        return rule

    def get_rule(
        self, rule_id: str, workspace_id: str | None = None
    ) -> SyncRule | None:
        ws = self._resolve_workspace(workspace_id)
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM sync_rules WHERE id = ? AND workspace_id = ?", (rule_id, ws)
        ).fetchone()
        if row is None:
            return None
        return SyncRule(
            id=row["id"], rule_type=row["rule_type"],
            cron_expression=row["cron_expression"] or "",
            enabled=bool(row["enabled"]),
            webhook_url=row["webhook_url"] or "",
            webhook_secret=row["webhook_secret"] or "",
            workspace_id=row["workspace_id"] or "default",
        )

    def get_rule_for_job(
        self, job_id: str, workspace_id: str | None = None
    ) -> SyncRule | None:
        ws = self._resolve_workspace(workspace_id)
        conn = self._get_conn()
        row = conn.execute(
            """SELECT r.* FROM sync_rules r
               JOIN sync_jobs j ON j.rule_id = r.id
               WHERE j.id = ? AND j.workspace_id = ?""",
            (job_id, ws),
        ).fetchone()
        if row is None:
            return None
        return SyncRule(
            id=row["id"], rule_type=row["rule_type"],
            cron_expression=row["cron_expression"] or "",
            enabled=bool(row["enabled"]),
            webhook_url=row["webhook_url"] or "",
            webhook_secret=row["webhook_secret"] or "",
            workspace_id=row["workspace_id"] or "default",
        )

    def delete_rule(
        self, rule_id: str, workspace_id: str | None = None
    ) -> bool:
        ws = self._resolve_workspace(workspace_id)
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "DELETE FROM sync_rules WHERE id = ? AND workspace_id = ?",
                (rule_id, ws),
            )
            conn.commit()
            return cur.rowcount > 0

    # ── Jobs ──

    def save_job(
        self, job: SyncJob, workspace_id: str | None = None
    ) -> SyncJob:
        ws = self._resolve_workspace(workspace_id or job.workspace_id)
        job.workspace_id = ws
        with self._lock:
            conn = self._get_conn()
            # 用 ON CONFLICT(id) DO UPDATE 而非 INSERT OR REPLACE：
            # REPLACE 会先 DELETE 旧行，触发 sync_executions.job_id 的
            # ON DELETE CASCADE，把该 Job 的 execution 全部清空（P1 数据完整性 bug）。
            conn.execute(
                """INSERT INTO sync_jobs
                   (id, connector_config_id, rule_id, name, status, enabled, workspace_id, created_at,
                    started_at, heartbeat_at, worker_id, attempt_count)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                   connector_config_id=excluded.connector_config_id,
                   rule_id=excluded.rule_id,
                   name=excluded.name,
                   status=excluded.status,
                   enabled=excluded.enabled,
                   workspace_id=excluded.workspace_id,
                   started_at=excluded.started_at,
                   heartbeat_at=excluded.heartbeat_at,
                   worker_id=excluded.worker_id,
                   attempt_count=excluded.attempt_count""",
                (
                    job.id, job.connector_config_id, job.rule_id, job.name,
                    job.status, 1 if job.enabled else 0, ws, job.created_at.isoformat(),
                    job.started_at.isoformat() if job.started_at else None,
                    job.heartbeat_at.isoformat() if job.heartbeat_at else None,
                    job.worker_id or "",
                    job.attempt_count,
                ),
            )
            conn.commit()
        return job

    def get_job(
        self, job_id: str, workspace_id: str | None = None
    ) -> SyncJob | None:
        ws = self._resolve_workspace(workspace_id)
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM sync_jobs WHERE id = ? AND workspace_id = ?", (job_id, ws)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    def list_jobs(
        self, enabled_only: bool = False, workspace_id: str | None = None
    ) -> list[SyncJob]:
        ws = self._resolve_workspace(workspace_id)
        conn = self._get_conn()
        if enabled_only:
            rows = conn.execute(
                "SELECT * FROM sync_jobs WHERE workspace_id = ? AND enabled = 1 AND status != 'cancelled' ORDER BY created_at DESC",
                (ws,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sync_jobs WHERE workspace_id = ? ORDER BY created_at DESC",
                (ws,),
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def list_all_jobs(self, enabled_only: bool = False) -> list[SyncJob]:
        """List jobs across ALL workspaces.

        INTERNAL — intended only for the trusted background scheduler, which
        runs outside any request context. Do NOT call from request handlers;
        normal callers must use `list_jobs` (workspace-scoped).
        """
        conn = self._get_conn()
        if enabled_only:
            rows = conn.execute(
                "SELECT * FROM sync_jobs WHERE enabled = 1 AND status != 'cancelled' ORDER BY created_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sync_jobs ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def update_job(
        self, job: SyncJob, workspace_id: str | None = None
    ) -> SyncJob:
        return self.save_job(job, workspace_id=workspace_id)

    def delete_job(self, job_id: str, workspace_id: str | None = None) -> bool:
        ws = self._resolve_workspace(workspace_id)
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "DELETE FROM sync_jobs WHERE id = ? AND workspace_id = ?",
                (job_id, ws),
            )
            conn.commit()
            return cur.rowcount > 0

    def _row_to_job(self, row: sqlite3.Row) -> SyncJob:
        from datetime import datetime, timezone

        def _parse_dt(val: str | None) -> datetime:
            if not val:
                return datetime.now(timezone.utc)
            try:
                return datetime.fromisoformat(val)
            except (ValueError, TypeError):
                return datetime.now(timezone.utc)

        return SyncJob(
            id=row["id"], connector_config_id=row["connector_config_id"],
            rule_id=row["rule_id"], name=row["name"],
            status=row["status"] or "pending",
            enabled=bool(row["enabled"]),
            created_at=_parse_dt(row["created_at"]),
            workspace_id=row["workspace_id"] or "default",
            started_at=_parse_dt(row["started_at"]) if row["started_at"] else None,
            heartbeat_at=_parse_dt(row["heartbeat_at"]) if row["heartbeat_at"] else None,
            worker_id=row["worker_id"] or "",
            attempt_count=row["attempt_count"] or 0,
        )

    # ── Executions ──

    def save_execution(
        self, execution: SyncExecution, workspace_id: str | None = None
    ) -> SyncExecution:
        ws = self._resolve_workspace(workspace_id or execution.workspace_id)
        execution.workspace_id = ws
        with self._lock:
            conn = self._get_conn()
            # 用 ON CONFLICT(id) DO UPDATE 而非 INSERT OR REPLACE：
            # REPLACE 在存在 active 唯一约束时会先删兄弟行，破坏幂等保护。
            conn.execute(
                """INSERT INTO sync_executions
                   (id, job_id, status, started_at, completed_at,
                    items_fetched, items_new, items_updated, items_deleted,
                    items_renamed, memories_created, errors_count, error, elapsed_ms, workspace_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                   status=excluded.status,
                   started_at=excluded.started_at,
                   completed_at=excluded.completed_at,
                   items_fetched=excluded.items_fetched,
                   items_new=excluded.items_new,
                   items_updated=excluded.items_updated,
                   items_deleted=excluded.items_deleted,
                   items_renamed=excluded.items_renamed,
                   memories_created=excluded.memories_created,
                   errors_count=excluded.errors_count,
                   error=excluded.error,
                   elapsed_ms=excluded.elapsed_ms,
                   workspace_id=excluded.workspace_id""",
                (
                    execution.id, execution.job_id, execution.status,
                    execution.started_at.isoformat() if execution.started_at else None,
                    execution.completed_at.isoformat() if execution.completed_at else None,
                    execution.items_fetched, execution.items_new,
                    execution.items_updated, execution.items_deleted,
                    execution.items_renamed, execution.memories_created,
                    execution.errors_count, execution.error, execution.elapsed_ms,
                    ws,
                ),
            )
            conn.commit()
        return execution

    def get_active_execution(
        self, job_id: str, workspace_id: str | None = None
    ) -> SyncExecution | None:
        """返回某 Job 当前 active（pending/running）的 execution，无则 None。"""
        ws = self._resolve_workspace(workspace_id)
        placeholders = ",".join("?" for _ in EXECUTION_STATUS_ACTIVE)
        conn = self._get_conn()
        row = conn.execute(
            f"SELECT * FROM sync_executions WHERE job_id = ? AND workspace_id = ? "
            f"AND status IN ({placeholders}) ORDER BY started_at DESC LIMIT 1",
            (job_id, ws, *sorted(EXECUTION_STATUS_ACTIVE)),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_execution(row)

    def create_execution_if_idle(
        self, execution: SyncExecution, workspace_id: str | None = None
    ) -> SyncExecution | None:
        """原子地为 Job 创建 execution —— 仅当该 Job 无 active execution 时成功。

        在 Store 写锁 / SQLite 事务内执行 INSERT...WHERE NOT EXISTS，
        并发 RUN 请求（含多线程）最终只会有一个 active execution。
        若已有 active execution，返回 None（调用方应返回 409）。
        """
        ws = self._resolve_workspace(workspace_id or execution.workspace_id)
        execution.workspace_id = ws
        active_in = ",".join("?" for _ in EXECUTION_STATUS_ACTIVE)
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                f"""INSERT INTO sync_executions
                    (id, job_id, status, started_at, completed_at,
                     items_fetched, items_new, items_updated, items_deleted,
                     items_renamed, memories_created, errors_count, error, elapsed_ms, workspace_id)
                    SELECT ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM sync_executions
                        WHERE job_id = ? AND status IN ({active_in})
                    )""",
                (
                    execution.id, execution.job_id, execution.status,
                    execution.started_at.isoformat() if execution.started_at else None,
                    execution.completed_at.isoformat() if execution.completed_at else None,
                    execution.items_fetched, execution.items_new,
                    execution.items_updated, execution.items_deleted,
                    execution.items_renamed, execution.memories_created,
                    execution.errors_count, execution.error, execution.elapsed_ms,
                    ws,
                    execution.job_id, *sorted(EXECUTION_STATUS_ACTIVE),
                ),
            )
            conn.commit()
            if cur.rowcount == 1:
                return execution
            return None

    def update_job_heartbeat(
        self, job_id: str, workspace_id: str | None, heartbeat_at: datetime
    ) -> None:
        """更新 Job 心跳（Worker 后台心跳线程调用，workspace 隔离）。"""
        ws = self._resolve_workspace(workspace_id)
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "UPDATE sync_jobs SET heartbeat_at = ? WHERE id = ? AND workspace_id = ?",
                (heartbeat_at.isoformat(), job_id, ws),
            )
            conn.commit()

    def recover_stale_jobs(self, stale_timeout_seconds: float = 300.0) -> list[dict]:
        """扫描所有 workspace 的 active Job，将 stale（心跳/开始时间过期）的收敛为 failed。

        INTERNAL — 仅供后台 Scheduler 启动时与 tick 周期调用，跨 workspace 扫描。
        恢复策略：标记 failed，不自动重试（避免重复写 Memory）。
        同时把该 Job 的 active execution 标记为 failed/cancelled，避免留下 orphan execution。
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=stale_timeout_seconds)
        recovered: list[dict] = []
        conn = self._get_conn()

        with self._lock:
            rows = conn.execute(
                "SELECT * FROM sync_jobs WHERE status IN ('running','queued')"
            ).fetchall()
            for r in rows:
                job = self._row_to_job(r)
                # stale 判定：有心跳看心跳，否则看 started_at，再否则看 created_at
                ref = job.heartbeat_at or job.started_at or job.created_at
                if ref is None or ref > cutoff:
                    continue  # 仍新鲜，跳过

                active_in = ",".join("?" for _ in EXECUTION_STATUS_ACTIVE)
                # 收敛 execution → failed
                conn.execute(
                    f"UPDATE sync_executions SET status='failed', "
                    f"error='recovered: worker crashed or stale', completed_at=? "
                    f"WHERE job_id=? AND status IN ({active_in})",
                    (now.isoformat(), job.id, *sorted(EXECUTION_STATUS_ACTIVE)),
                )
                # 收敛 job → failed
                conn.execute(
                    "UPDATE sync_jobs SET status='failed', heartbeat_at=? WHERE id=?",
                    (now.isoformat(), job.id),
                )
                recovered.append({
                    "job_id": job.id,
                    "workspace_id": job.workspace_id,
                    "status": "running" if job.status == "running" else "queued",
                    "recovered_to": "failed",
                    "stale_ref": ref.isoformat(),
                })
            conn.commit()
        return recovered

    def get_execution(
        self, execution_id: str, workspace_id: str | None = None
    ) -> SyncExecution | None:
        ws = self._resolve_workspace(workspace_id)
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM sync_executions WHERE id = ? AND workspace_id = ?",
            (execution_id, ws),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_execution(row)

    def list_executions(
        self,
        job_id: str = "",
        connector_id: str = "",
        limit: int = 50,
        workspace_id: str | None = None,
    ) -> list[SyncExecution]:
        ws = self._resolve_workspace(workspace_id)
        conn = self._get_conn()
        if job_id:
            rows = conn.execute(
                "SELECT * FROM sync_executions WHERE job_id = ? AND workspace_id = ? ORDER BY started_at DESC LIMIT ?",
                (job_id, ws, limit),
            ).fetchall()
        elif connector_id:
            rows = conn.execute(
                """SELECT e.* FROM sync_executions e
                   JOIN sync_jobs j ON j.id = e.job_id
                   WHERE j.connector_config_id = ? AND e.workspace_id = ?
                   ORDER BY e.started_at DESC LIMIT ?""",
                (connector_id, ws, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sync_executions WHERE workspace_id = ? ORDER BY started_at DESC LIMIT ?",
                (ws, limit),
            ).fetchall()
        return [self._row_to_execution(r) for r in rows]

    def _row_to_execution(self, row: sqlite3.Row) -> SyncExecution:
        from datetime import datetime, timezone

        def _parse_dt(val: str | None) -> datetime | None:
            if not val:
                return None
            try:
                return datetime.fromisoformat(val)
            except (ValueError, TypeError):
                return None

        return SyncExecution(
            id=row["id"], job_id=row["job_id"],
            status=row["status"] or "pending",
            started_at=_parse_dt(row["started_at"]),
            completed_at=_parse_dt(row["completed_at"]),
            items_fetched=row["items_fetched"] or 0,
            items_new=row["items_new"] or 0,
            items_updated=row["items_updated"] or 0,
            items_deleted=row["items_deleted"] or 0,
            items_renamed=row["items_renamed"] or 0,
            memories_created=row["memories_created"] or 0,
            errors_count=row["errors_count"] or 0,
            error=row["error"],
            elapsed_ms=row["elapsed_ms"] or 0,
            workspace_id=row["workspace_id"] or "default",
        )

    # ── Changes ──

    def save_change(
        self, change: ChangeRecord, workspace_id: str | None = None
    ) -> ChangeRecord:
        with self._lock:
            conn = self._get_conn()
            content_preview = change.content[:500] if change.content else ""
            ws = self._resolve_workspace(workspace_id or change.workspace_id)
            change.workspace_id = ws
            conn.execute(
                """INSERT OR REPLACE INTO sync_changes
                   (id, execution_id, connector_type, resource_id, change_type,
                    content_hash, previous_hash, content_preview, content_type,
                    metadata_json, processed, process_error, detected_at, workspace_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    change.id, change.execution_id, change.connector_type,
                    change.resource_id, change.change_type,
                    change.content_hash, change.previous_hash,
                    content_preview, change.content_type,
                    json.dumps(change.metadata, ensure_ascii=False),
                    1 if change.processed else 0,
                    change.process_error,
                    change.detected_at.isoformat(),
                    ws,
                ),
            )
            conn.commit()
        return change

    def list_changes(
        self, execution_id: str, workspace_id: str | None = None
    ) -> list[ChangeRecord]:
        ws = self._resolve_workspace(workspace_id)
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM sync_changes WHERE execution_id = ? AND workspace_id = ? ORDER BY detected_at",
            (execution_id, ws),
        ).fetchall()
        return [self._row_to_change(r) for r in rows]

    def _row_to_change(self, row: sqlite3.Row) -> ChangeRecord:
        from datetime import datetime, timezone

        def _parse_dt(val: str) -> datetime:
            try:
                return datetime.fromisoformat(val)
            except (ValueError, TypeError):
                return datetime.now(timezone.utc)

        return ChangeRecord(
            id=row["id"], execution_id=row["execution_id"],
            connector_type=row["connector_type"],
            resource_id=row["resource_id"],
            change_type=row["change_type"],
            content_hash=row["content_hash"] or "",
            previous_hash=row["previous_hash"] or "",
            content=row["content_preview"] or "",
            content_type=row["content_type"] or "",
            metadata=json.loads(row["metadata_json"] or "{}"),
            processed=bool(row["processed"]),
            process_error=row["process_error"],
            detected_at=_parse_dt(row["detected_at"]),
            workspace_id=row["workspace_id"] or "default",
        )
