"""SyncStore — SQLite persistence for sync jobs, rules, executions, and changes.

Follows the same pattern as src/adapters/sqlite_store.py and the
ImportHistory class in src/core/import_worker.py.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from src.adapters.config import Settings
from src.sync.models import (
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
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sync_rules (
            id TEXT PRIMARY KEY,
            rule_type TEXT NOT NULL DEFAULT 'manual',
            cron_expression TEXT DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            webhook_url TEXT DEFAULT '',
            webhook_secret TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS sync_jobs (
            id TEXT PRIMARY KEY,
            connector_config_id TEXT NOT NULL REFERENCES sync_connectors(id) ON DELETE CASCADE,
            rule_id TEXT NOT NULL REFERENCES sync_rules(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
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
            elapsed_ms INTEGER DEFAULT 0
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
            detected_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_changes_exec ON sync_changes(execution_id);
        CREATE INDEX IF NOT EXISTS idx_changes_resource ON sync_changes(connector_type, resource_id);
        CREATE INDEX IF NOT EXISTS idx_executions_job ON sync_executions(job_id);
        """)
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    # ── Connectors ──

    def save_connector(self, config: SyncConnectorConfig) -> SyncConnectorConfig:
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """INSERT OR REPLACE INTO sync_connectors
                   (id, name, connector_type, credentials_json, enabled,
                    last_sync_time, last_sync_status, etag_map_json, hash_map_json,
                    version_map_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    config.id, config.name, config.connector_type,
                    json.dumps(config.credentials, ensure_ascii=False),
                    1 if config.enabled else 0,
                    config.last_sync_time.isoformat() if config.last_sync_time else None,
                    config.last_sync_status,
                    json.dumps(config.etag_map, ensure_ascii=False),
                    json.dumps(config.hash_map, ensure_ascii=False),
                    json.dumps(config.version_map, ensure_ascii=False),
                    config.created_at.isoformat(),
                    config.updated_at.isoformat(),
                ),
            )
            conn.commit()
        return config

    def get_connector(self, connector_id: str) -> SyncConnectorConfig | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM sync_connectors WHERE id = ?", (connector_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_connector(row)

    def list_connectors(self) -> list[SyncConnectorConfig]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM sync_connectors ORDER BY updated_at DESC"
        ).fetchall()
        return [self._row_to_connector(r) for r in rows]

    def update_connector(self, config: SyncConnectorConfig) -> SyncConnectorConfig:
        return self.save_connector(config)

    def delete_connector(self, connector_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute("DELETE FROM sync_connectors WHERE id = ?", (connector_id,))
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
        )

    # ── Rules ──

    def save_rule(self, rule: SyncRule) -> SyncRule:
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """INSERT OR REPLACE INTO sync_rules
                   (id, rule_type, cron_expression, enabled, webhook_url, webhook_secret)
                   VALUES (?,?,?,?,?,?)""",
                (
                    rule.id, rule.rule_type, rule.cron_expression,
                    1 if rule.enabled else 0, rule.webhook_url, rule.webhook_secret,
                ),
            )
            conn.commit()
        return rule

    def get_rule(self, rule_id: str) -> SyncRule | None:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM sync_rules WHERE id = ?", (rule_id,)).fetchone()
        if row is None:
            return None
        return SyncRule(
            id=row["id"], rule_type=row["rule_type"],
            cron_expression=row["cron_expression"] or "",
            enabled=bool(row["enabled"]),
            webhook_url=row["webhook_url"] or "",
            webhook_secret=row["webhook_secret"] or "",
        )

    def get_rule_for_job(self, job_id: str) -> SyncRule | None:
        conn = self._get_conn()
        row = conn.execute(
            """SELECT r.* FROM sync_rules r
               JOIN sync_jobs j ON j.rule_id = r.id
               WHERE j.id = ?""",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return SyncRule(
            id=row["id"], rule_type=row["rule_type"],
            cron_expression=row["cron_expression"] or "",
            enabled=bool(row["enabled"]),
            webhook_url=row["webhook_url"] or "",
            webhook_secret=row["webhook_secret"] or "",
        )

    def delete_rule(self, rule_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute("DELETE FROM sync_rules WHERE id = ?", (rule_id,))
            conn.commit()
            return cur.rowcount > 0

    # ── Jobs ──

    def save_job(self, job: SyncJob) -> SyncJob:
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """INSERT OR REPLACE INTO sync_jobs
                   (id, connector_config_id, rule_id, name, status, enabled, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    job.id, job.connector_config_id, job.rule_id, job.name,
                    job.status, 1 if job.enabled else 0, job.created_at.isoformat(),
                ),
            )
            conn.commit()
        return job

    def get_job(self, job_id: str) -> SyncJob | None:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM sync_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    def list_jobs(self, enabled_only: bool = False) -> list[SyncJob]:
        conn = self._get_conn()
        if enabled_only:
            rows = conn.execute(
                "SELECT * FROM sync_jobs WHERE enabled = 1 AND status != 'cancelled' ORDER BY created_at DESC"
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM sync_jobs ORDER BY created_at DESC").fetchall()
        return [self._row_to_job(r) for r in rows]

    def update_job(self, job: SyncJob) -> SyncJob:
        return self.save_job(job)

    def delete_job(self, job_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute("DELETE FROM sync_jobs WHERE id = ?", (job_id,))
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
        )

    # ── Executions ──

    def save_execution(self, execution: SyncExecution) -> SyncExecution:
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """INSERT OR REPLACE INTO sync_executions
                   (id, job_id, status, started_at, completed_at,
                    items_fetched, items_new, items_updated, items_deleted,
                    items_renamed, memories_created, errors_count, error, elapsed_ms)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    execution.id, execution.job_id, execution.status,
                    execution.started_at.isoformat() if execution.started_at else None,
                    execution.completed_at.isoformat() if execution.completed_at else None,
                    execution.items_fetched, execution.items_new,
                    execution.items_updated, execution.items_deleted,
                    execution.items_renamed, execution.memories_created,
                    execution.errors_count, execution.error, execution.elapsed_ms,
                ),
            )
            conn.commit()
        return execution

    def get_execution(self, execution_id: str) -> SyncExecution | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM sync_executions WHERE id = ?", (execution_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_execution(row)

    def list_executions(
        self, job_id: str = "", connector_id: str = "", limit: int = 50
    ) -> list[SyncExecution]:
        conn = self._get_conn()
        if job_id:
            rows = conn.execute(
                "SELECT * FROM sync_executions WHERE job_id = ? ORDER BY started_at DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()
        elif connector_id:
            rows = conn.execute(
                """SELECT e.* FROM sync_executions e
                   JOIN sync_jobs j ON j.id = e.job_id
                   WHERE j.connector_config_id = ?
                   ORDER BY e.started_at DESC LIMIT ?""",
                (connector_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sync_executions ORDER BY started_at DESC LIMIT ?",
                (limit,),
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
        )

    # ── Changes ──

    def save_change(self, change: ChangeRecord) -> ChangeRecord:
        with self._lock:
            conn = self._get_conn()
            content_preview = change.content[:500] if change.content else ""
            conn.execute(
                """INSERT OR REPLACE INTO sync_changes
                   (id, execution_id, connector_type, resource_id, change_type,
                    content_hash, previous_hash, content_preview, content_type,
                    metadata_json, processed, process_error, detected_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    change.id, change.execution_id, change.connector_type,
                    change.resource_id, change.change_type,
                    change.content_hash, change.previous_hash,
                    content_preview, change.content_type,
                    json.dumps(change.metadata, ensure_ascii=False),
                    1 if change.processed else 0,
                    change.process_error,
                    change.detected_at.isoformat(),
                ),
            )
            conn.commit()
        return change

    def list_changes(self, execution_id: str) -> list[ChangeRecord]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM sync_changes WHERE execution_id = ? ORDER BY detected_at",
            (execution_id,),
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
        )
