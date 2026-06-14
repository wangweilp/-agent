"""SQLite Sandbox v2 Queue — SandboxQueue 协议的默认实现。

使用 SQLite 作为队列后端，支持：
- lease 防重复消费
- attempts / max_attempts 重试
- dead letter 队列
- lease 过期回收
- worker 心跳

遵循现有 store 模式。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.sandbox_v2.models import (
    SandboxQueueItem,
    SandboxWorkerHeartbeat,
    SandboxV2QueueStatus,
    SandboxV2WorkerStatus,
)

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sandbox_v2_queue_items (
    queue_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE,
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 100,
    status TEXT NOT NULL DEFAULT 'queued',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    available_at TEXT NOT NULL DEFAULT (datetime('now')),
    leased_by TEXT NOT NULL DEFAULT '',
    leased_until TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_error TEXT NOT NULL DEFAULT '',
    dead_letter_reason TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_queue_status ON sandbox_v2_queue_items(status);
CREATE INDEX IF NOT EXISTS idx_sbxv2_queue_job ON sandbox_v2_queue_items(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_queue_leased_until ON sandbox_v2_queue_items(leased_until);
CREATE INDEX IF NOT EXISTS idx_sbxv2_queue_priority ON sandbox_v2_queue_items(priority, available_at);

CREATE TABLE IF NOT EXISTS sandbox_v2_worker_heartbeats (
    worker_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'idle',
    current_job_id TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_heartbeat_at TEXT NOT NULL DEFAULT (datetime('now')),
    processed_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    canceled_count INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_wkr_status ON sandbox_v2_worker_heartbeats(status);
CREATE INDEX IF NOT EXISTS idx_sbxv2_wkr_heartbeat ON sandbox_v2_worker_heartbeats(last_heartbeat_at);
"""


class SQLiteSandboxV2Queue:
    """SandboxQueue 的 SQLite 实现。"""

    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="sbx_v2_queue_init_schema")

    def _init_schema(self):
        for stmt in _SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)
        try:
            self._db.conn.commit()
        except Exception:
            pass

    def flush(self) -> None:
        try:
            if hasattr(self._db, "conn") and self._db.conn:
                self._db.conn.commit()
        except Exception:
            pass

    def _exec(self, sql: str, params: list[Any] | None = None) -> Any:
        return self._db.execute(sql, params or [])

    # ═══════════════════════════════════════════
    # Enqueue / Dequeue
    # ═══════════════════════════════════════════

    def enqueue(
        self,
        job_id: str,
        organization_id: str = "",
        workspace_id: str = "",
        priority: int = 100,
        max_attempts: int = 3,
    ) -> SandboxQueueItem:
        existing = self.get_queue_item_by_job_id(job_id)
        if existing:
            return existing

        now = datetime.now(timezone.utc)
        item = SandboxQueueItem(
            job_id=job_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            priority=priority,
            max_attempts=max_attempts,
            status=SandboxV2QueueStatus.QUEUED,
            available_at=now,
            created_at=now,
            updated_at=now,
        )
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_queue_items (
            queue_id, job_id, organization_id, workspace_id, priority, status,
            attempts, max_attempts, available_at, leased_by, leased_until,
            created_at, updated_at, last_error, dead_letter_reason, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            item.queue_id, item.job_id, item.organization_id, item.workspace_id,
            item.priority, item.status, item.attempts, item.max_attempts,
            item.available_at.isoformat(), item.leased_by,
            item.leased_until.isoformat() if item.leased_until else None,
            item.created_at.isoformat(), item.updated_at.isoformat(),
            item.last_error, item.dead_letter_reason,
            json.dumps(item.metadata, ensure_ascii=False),
        ])
        return item

    def lease_next(self, worker_id: str, lease_seconds: int = 60) -> SandboxQueueItem | None:
        """租约下一个 queued 的队列项。按 priority ASC, available_at ASC 排序。

        使用 SELECT + UPDATE 模式，在一条语句中完成租约分配。
        """
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        lease_until = now + timedelta(seconds=lease_seconds)
        lease_until_str = lease_until.isoformat()

        # 找到最早可用的 queued 项
        row = next(self._exec(
            """SELECT queue_id FROM sandbox_v2_queue_items
               WHERE status = ? AND available_at <= ?
               ORDER BY priority ASC, available_at ASC
               LIMIT 1""",
            [SandboxV2QueueStatus.QUEUED, now_str],
        ), None)

        if row is None:
            return None

        queue_id = row["queue_id"]
        self._exec("""UPDATE sandbox_v2_queue_items
            SET status=?, leased_by=?, leased_until=?, updated_at=?
            WHERE queue_id=? AND status=? AND available_at<=?""",
            [SandboxV2QueueStatus.LEASED, worker_id, lease_until_str, now_str,
             queue_id, SandboxV2QueueStatus.QUEUED, now_str])
        self._db.conn.commit()

        return self.get_queue_item(queue_id)

    def acknowledge(self, queue_id: str) -> None:
        self._exec("""UPDATE sandbox_v2_queue_items
            SET status=?, updated_at=? WHERE queue_id=?""",
            [SandboxV2QueueStatus.COMPLETED, datetime.now(timezone.utc).isoformat(), queue_id])

    def fail(
        self,
        queue_id: str,
        reason: str = "",
        retry: bool = True,
    ) -> SandboxQueueItem | None:
        item = self.get_queue_item(queue_id)
        if item is None:
            return None

        now = datetime.now(timezone.utc)
        new_attempts = item.attempts + 1

        if retry and new_attempts < item.max_attempts:
            # 重新入队
            self._exec("""UPDATE sandbox_v2_queue_items SET
                status=?, attempts=?, last_error=?, leased_by=?, leased_until=NULL,
                available_at=?, updated_at=?
                WHERE queue_id=?""",
                [SandboxV2QueueStatus.QUEUED, new_attempts, reason, "", now.isoformat(), now.isoformat(), queue_id])
        else:
            # 进入 dead letter
            self._exec("""UPDATE sandbox_v2_queue_items SET
                status=?, attempts=?, last_error=?, dead_letter_reason=?,
                leased_by=?, updated_at=?
                WHERE queue_id=?""",
                [SandboxV2QueueStatus.DEAD_LETTER, new_attempts, reason, reason, "", now.isoformat(), queue_id])

        self._db.conn.commit()
        return self.get_queue_item(queue_id)

    def cancel(self, job_id: str, reason: str = "") -> SandboxQueueItem | None:
        item = self.get_queue_item_by_job_id(job_id)
        if item is None:
            return None
        if not item.is_cancellable():
            return item
        now = datetime.now(timezone.utc)
        self._exec("""UPDATE sandbox_v2_queue_items SET
            status=?, last_error=?, updated_at=?
            WHERE job_id=? AND status IN (?,?,?)""",
            [SandboxV2QueueStatus.CANCELED, reason, now.isoformat(),
             job_id, SandboxV2QueueStatus.QUEUED, SandboxV2QueueStatus.LEASED, SandboxV2QueueStatus.PROCESSING])
        self._db.conn.commit()
        return self.get_queue_item_by_job_id(job_id)

    def heartbeat(
        self,
        worker_id: str,
        current_job_id: str = "",
    ) -> SandboxWorkerHeartbeat:
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        existing = next(self._exec(
            "SELECT * FROM sandbox_v2_worker_heartbeats WHERE worker_id=?", [worker_id]), None)

        if existing:
            row = dict(existing)
            hb = SandboxWorkerHeartbeat.from_dict(row)
            hb.current_job_id = current_job_id or row.get("current_job_id", "")
            hb.last_heartbeat_at = now
            self._exec("""UPDATE sandbox_v2_worker_heartbeats SET
                status=?, current_job_id=?, last_heartbeat_at=?
                WHERE worker_id=?""",
                [hb.status, hb.current_job_id, now_str, worker_id])
        else:
            hb = SandboxWorkerHeartbeat(
                worker_id=worker_id,
                status=SandboxV2WorkerStatus.IDLE if not current_job_id else SandboxV2WorkerStatus.PROCESSING,
                current_job_id=current_job_id,
                started_at=now,
                last_heartbeat_at=now,
            )
            self._exec("""INSERT OR REPLACE INTO sandbox_v2_worker_heartbeats (
                worker_id, status, current_job_id, started_at, last_heartbeat_at,
                processed_count, failed_count, canceled_count, metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?)""", [
                hb.worker_id, hb.status, hb.current_job_id,
                hb.started_at.isoformat(), hb.last_heartbeat_at.isoformat(),
                hb.processed_count, hb.failed_count, hb.canceled_count,
                json.dumps(hb.metadata, ensure_ascii=False),
            ])
        self._db.conn.commit()
        return hb

    def list_queue(self, status: str | None = None, limit: int = 50) -> list[SandboxQueueItem]:
        sql = "SELECT * FROM sandbox_v2_queue_items WHERE 1=1"
        params: list[Any] = []
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY priority ASC, available_at ASC LIMIT ?"
        params.append(limit)
        return [self._row_to_item(dict(r)) for r in self._exec(sql, params)]

    def get_queue_item(self, queue_id: str) -> SandboxQueueItem | None:
        row = next(self._exec(
            "SELECT * FROM sandbox_v2_queue_items WHERE queue_id=?", [queue_id]), None)
        return self._row_to_item(dict(row)) if row else None

    def get_queue_item_by_job_id(self, job_id: str) -> SandboxQueueItem | None:
        row = next(self._exec(
            "SELECT * FROM sandbox_v2_queue_items WHERE job_id=?", [job_id]), None)
        return self._row_to_item(dict(row)) if row else None

    def requeue_expired_leases(self, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        now_str = now.isoformat()
        rows = list(self._exec(
            """SELECT * FROM sandbox_v2_queue_items
               WHERE status IN (?,?) AND leased_until IS NOT NULL AND leased_until < ?""",
            [SandboxV2QueueStatus.LEASED, SandboxV2QueueStatus.PROCESSING, now_str]))
        count = 0
        for row in rows:
            r = dict(row)
            queue_id = r["queue_id"]
            attempts = int(r.get("attempts", 0)) + 1
            max_attempts = int(r.get("max_attempts", 3))
            if attempts >= max_attempts:
                self._exec("""UPDATE sandbox_v2_queue_items SET
                    status=?, attempts=?, dead_letter_reason=?, leased_by=?,
                    leased_until=NULL, updated_at=?
                    WHERE queue_id=?""",
                    [SandboxV2QueueStatus.DEAD_LETTER, attempts,
                     "Lease expired and max_attempts exceeded.", "", now_str, queue_id])
            else:
                self._exec("""UPDATE sandbox_v2_queue_items SET
                    status=?, attempts=?, leased_by=?, leased_until=NULL,
                    available_at=?, updated_at=?
                    WHERE queue_id=?""",
                    [SandboxV2QueueStatus.QUEUED, attempts, "", now_str, now_str, queue_id])
            count += 1
        if count:
            self._db.conn.commit()
        return count

    def move_to_dead_letter(self, queue_id: str, reason: str) -> SandboxQueueItem | None:
        item = self.get_queue_item(queue_id)
        if item is None:
            return None
        self._exec("""UPDATE sandbox_v2_queue_items SET
            status=?, dead_letter_reason=?, updated_at=?
            WHERE queue_id=?""",
            [SandboxV2QueueStatus.DEAD_LETTER, reason, datetime.now(timezone.utc).isoformat(), queue_id])
        self._db.conn.commit()
        return self.get_queue_item(queue_id)

    def list_dead_letter(self, limit: int = 50) -> list[SandboxQueueItem]:
        return self.list_queue(status=SandboxV2QueueStatus.DEAD_LETTER, limit=limit)

    def list_workers(self, limit: int = 50) -> list[SandboxWorkerHeartbeat]:
        rows = self._exec(
            "SELECT * FROM sandbox_v2_worker_heartbeats ORDER BY last_heartbeat_at DESC LIMIT ?",
            [limit])
        return [SandboxWorkerHeartbeat.from_dict(dict(r)) for r in rows]

    def update_queue_status(self, queue_id: str, status: str) -> SandboxQueueItem | None:
        item = self.get_queue_item(queue_id)
        if item is None:
            return None
        self._exec("""UPDATE sandbox_v2_queue_items SET
            status=?, updated_at=? WHERE queue_id=?""",
            [status, datetime.now(timezone.utc).isoformat(), queue_id])
        self._db.conn.commit()
        return self.get_queue_item(queue_id)

    def increment_worker_count(self, worker_id: str, field: str) -> None:
        """递增 worker 计数字段（processed_count / failed_count / canceled_count）。"""
        valid = {"processed_count", "failed_count", "canceled_count"}
        if field not in valid:
            return
        self._exec(f"UPDATE sandbox_v2_worker_heartbeats SET {field}={field}+1 WHERE worker_id=?",
                   [worker_id])
        self._db.conn.commit()

    def update_worker_status(self, worker_id: str, status: str, current_job_id: str = "") -> None:
        self._exec("""UPDATE sandbox_v2_worker_heartbeats SET
            status=?, current_job_id=?, last_heartbeat_at=?
            WHERE worker_id=?""",
            [status, current_job_id, datetime.now(timezone.utc).isoformat(), worker_id])
        self._db.conn.commit()

    # ═══════════════════════════════════════════
    # Row mapping
    # ═══════════════════════════════════════════

    @staticmethod
    def _row_to_item(row: dict[str, Any]) -> SandboxQueueItem:
        def _parse_dt(v):
            if isinstance(v, datetime):
                return v
            if isinstance(v, str) and v:
                try:
                    return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    return None
            return None

        return SandboxQueueItem(
            queue_id=row.get("queue_id", ""),
            job_id=row.get("job_id", ""),
            organization_id=row.get("organization_id", ""),
            workspace_id=row.get("workspace_id", ""),
            priority=row.get("priority", 100),
            status=row.get("status", SandboxV2QueueStatus.QUEUED),
            attempts=row.get("attempts", 0),
            max_attempts=row.get("max_attempts", 3),
            available_at=_parse_dt(row.get("available_at")) or datetime.now(timezone.utc),
            leased_by=row.get("leased_by", ""),
            leased_until=_parse_dt(row.get("leased_until")),
            created_at=_parse_dt(row.get("created_at")) or datetime.now(timezone.utc),
            updated_at=_parse_dt(row.get("updated_at")) or datetime.now(timezone.utc),
            last_error=row.get("last_error", ""),
            dead_letter_reason=row.get("dead_letter_reason", ""),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )
