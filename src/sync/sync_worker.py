"""SyncWorker — independent thread for serial sync job execution.

Architecture mirrors ImportWorker (src/core/import_worker.py):
  - Own thread with daemon=True
  - Queue-based job submission
  - Serial execution (no concurrency issues)
  - Stats tracking + DLQ
  - Status machine: pending → running → completed | failed
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import (
    EXECUTION_STATUS_ACTIVE,
    JOB_STATUS_TERMINAL,
    SyncConnectorConfig,
    SyncExecution,
    SyncJob,
)
from src.sync.sync_pipeline import SyncPipeline, SyncPipelineResult
from src.sync.sync_store import SyncStore

logger = logging.getLogger(__name__)

_DEAD_LETTER_DIR = "./data/dead_letter"


class SyncWorker(threading.Thread):
    """Independent thread that processes SyncJob executions serially.

    Single-threaded = no locks needed for ChromaDB/SQLite.
    Follows the exact pattern of ImportWorker.
    """

    def __init__(
        self,
        sync_store: SyncStore,
        sync_pipeline: SyncPipeline,
        connector_factory: Any = None,
        dead_letter_dir: str = _DEAD_LETTER_DIR,
        heartbeat_interval: float = 15.0,
    ) -> None:
        super().__init__(daemon=True, name="sync-worker")
        self._queue: queue.Queue[tuple[SyncJob, SyncExecution] | None] = queue.Queue()
        self._store = sync_store
        self._pipeline = sync_pipeline
        self._connector_factory = connector_factory  # callable(connector_type, config) -> BaseSyncConnector
        self._dead_letter_dir = Path(dead_letter_dir)
        self._running = False
        self._worker_id = f"worker-{threading.get_ident()}-{int(time.time())}"

        # Heartbeat（仅当 worker 线程真正运行 / run() 时启用）
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._active_heartbeat: tuple[str, str] | None = None  # (job_id, workspace_id)

        # Stats
        self._started_at: str = ""
        self._lock = threading.Lock()
        self._completed_count: int = 0
        self._failed_count: int = 0
        self._in_progress_count: int = 0
        self._history: list[dict[str, Any]] = []
        self._max_history = 50

    # ── Public API ──

    def enqueue(self, job: SyncJob, execution: SyncExecution) -> None:
        """Submit a sync job for execution."""
        self._queue.put((job, execution))

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def shutdown(self, timeout: float = 5.0) -> None:
        self._queue.put(None)
        if self._started.is_set():
            self.join(timeout=timeout)
        logger.info("sync_worker_shutdown", extra={"pending": self.pending})

    # ── Thread main loop ──

    def run(self) -> None:
        self._running = True
        self._dead_letter_dir.mkdir(parents=True, exist_ok=True)
        self._started_at = datetime.now(timezone.utc).isoformat()
        logger.info("sync_worker_started")

        while self._running:
            try:
                item = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if item is None:  # shutdown sentinel
                break

            job, execution = item
            self._process(job, execution)

    # ── Job processing ──

    def _process(self, job: SyncJob, execution: SyncExecution) -> None:
        t0 = time.monotonic()

        with self._lock:
            self._in_progress_count += 1

        try:
            self._process_inner(job, execution, t0)
        finally:
            # 确保任何路径都不残留进行中的计数
            with self._lock:
                self._in_progress_count = max(0, self._in_progress_count - 1)

    def _process_inner(self, job: SyncJob, execution: SyncExecution, t0: float) -> None:
        """执行一次 Job（含生命周期守卫、取消感知、崩溃安全）。"""
        ws = job.workspace_id

        # ── 守卫 1：Job 是否仍存在 / 已终止（防止删除后继续写）──
        fresh = self._retrieve_job(job.id, ws)
        if fresh is None or fresh.status in JOB_STATUS_TERMINAL:
            # Job 已被删除或已收敛：不执行，不 resurrect Job 行，
            # best-effort 标记 execution cancelled（若 Job 已删，FK 会静默失败）。
            self._finalize_cancelled(
                job, execution, ws,
                f"job no longer active ({getattr(fresh, 'status', 'deleted')})",
                persist_job=False,
            )
            return

        # ── 认领：pending/queued → running ──
        now = datetime.now(timezone.utc)
        job.status = "running"
        job.started_at = job.started_at or now
        job.heartbeat_at = now
        job.worker_id = self._worker_id
        job.attempt_count += 1
        self._safe_save_job(job, ws)

        execution.status = "running"
        execution.started_at = execution.started_at or now
        self._safe_save_execution(execution, ws)

        # 心跳（仅当 worker 线程真正运行）
        self._start_heartbeat(job.id, ws)

        try:
            # Resolve connector
            config = self._store.get_connector(job.connector_config_id, workspace_id=ws)
            if config is None:
                raise ValueError(f"Connector config {job.connector_config_id} not found")

            connector = self._build_connector(config)
            if connector is None:
                raise ValueError(
                    f"No connector for type '{config.connector_type}'. "
                    f"Is it registered in SYNC_CONNECTOR_REGISTRY?"
                )

            # Execute pipeline
            result: SyncPipelineResult = self._pipeline.run(connector, config, execution)

            # ── 守卫 2：运行期间是否被请求取消 / 删除 ──
            cancel_state = self._cancel_state(job.id, ws)
            if cancel_state is not None:
                should_cancel, job_exists = cancel_state
                self._finalize_cancelled(
                    job, execution, ws,
                    "cancelled: job delete/cancel requested during run",
                    persist_job=job_exists,
                )
                return

            # Persist results
            execution.items_fetched = result.items_fetched
            execution.items_new = result.items_new
            execution.items_updated = result.items_updated
            execution.items_deleted = result.items_deleted
            execution.items_renamed = result.items_renamed
            execution.memories_created = result.memories_created
            execution.errors_count = result.errors_count
            execution.error = result.error
            execution.status = result.status
            execution.elapsed_ms = result.processing_time_ms

            self._safe_save_execution(execution, ws)
            self._safe_update_connector(config, ws)

            # Update job status
            job.status = "completed" if result.status == "completed" else result.status
            job.heartbeat_at = datetime.now(timezone.utc)
            self._safe_save_job(job, ws)

            elapsed_ms = int((time.monotonic() - t0) * 1000)

            with self._lock:
                self._completed_count += 1

            logger.info(
                "sync_execution_completed",
                extra={
                    "job_id": job.id,
                    "execution_id": execution.id,
                    "job_name": job.name,
                    "status": result.status,
                    "items_new": result.items_new,
                    "items_updated": result.items_updated,
                    "memories_created": result.memories_created,
                    "elapsed_ms": elapsed_ms,
                },
            )
            self._record_history(job, execution, result, elapsed_ms)

        except Exception:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            execution.status = "failed"
            execution.error = f"Sync execution crashed: {_truncate_error()}"
            execution.elapsed_ms = elapsed_ms
            self._safe_save_execution(execution, ws)

            job.status = "failed"
            job.heartbeat_at = datetime.now(timezone.utc)
            self._safe_save_job(job, ws)

            with self._lock:
                self._failed_count += 1

            logger.exception(
                "sync_execution_failed",
                extra={"job_id": job.id, "execution_id": execution.id, "job_name": job.name},
            )
            self._write_dead_letter(execution)
            self._record_history(job, execution, None, elapsed_ms)
        finally:
            self._stop_heartbeat()

    # ── 生命周期守卫辅助 ──

    def _retrieve_job(self, job_id: str, ws: str) -> SyncJob | None:
        """重新读取 Job（workspace 隔离）。"""
        try:
            return self._store.get_job(job_id, workspace_id=ws)
        except Exception:
            logger.warning("sync_worker_job_read_failed", exc_info=True)
            return None

    def _is_cancel_requested(self, job_id: str, ws: str) -> bool:
        """检查 Job 是否被请求取消/删除。"""
        state = self._cancel_state(job_id, ws)
        return state is not None

    def _cancel_state(self, job_id: str, ws: str) -> tuple[bool, bool] | None:
        """返回 (should_cancel, job_exists)；若无需取消返回 None。"""
        fresh = self._retrieve_job(job_id, ws)
        if fresh is None:
            return (True, False)  # 已被删除 → 取消，但不得 resurrect Job
        if fresh.status in ("cancel_requested", "cancelled"):
            return (True, True)
        return None

    def _finalize_cancelled(
        self, job: SyncJob, execution: SyncExecution, ws: str, reason: str,
        persist_job: bool = True,
    ) -> None:
        """取消/删除路径：execution → cancelled，job → cancelled（best-effort）。

        persist_job=False 用于守卫 1（Job 已被删除）：不写 Job 行，避免
        INSERT OR REPLACE 把已删除的 Job 重新创建（复活）。
        """
        execution.status = "cancelled"
        execution.error = reason
        execution.completed_at = datetime.now(timezone.utc)
        self._safe_save_execution(execution, ws)

        if persist_job:
            job.status = "cancelled"
            job.heartbeat_at = datetime.now(timezone.utc)
            self._safe_save_job(job, ws)

        logger.info(
            "sync_execution_cancelled",
            extra={"job_id": job.id, "execution_id": execution.id, "reason": reason},
        )

    # 对删除的 Job 写数据会触发 FK 错误 —— 用 try/except 兜底，绝不崩溃 worker 线程
    def _safe_save_job(self, job: SyncJob, ws: str) -> None:
        try:
            self._store.update_job(job, workspace_id=ws)
        except Exception:
            logger.warning("sync_worker_job_save_failed", exc_info=True,
                           extra={"job_id": job.id})

    def _safe_save_execution(self, execution: SyncExecution, ws: str) -> None:
        try:
            self._store.save_execution(execution, workspace_id=ws)
        except Exception:
            logger.warning("sync_worker_execution_save_failed", exc_info=True,
                           extra={"execution_id": execution.id, "job_id": execution.job_id})

    def _safe_update_connector(self, config: SyncConnectorConfig, ws: str) -> None:
        try:
            self._store.update_connector(config, workspace_id=ws)
        except Exception:
            logger.warning("sync_worker_connector_update_failed", exc_info=True,
                           extra={"connector_id": config.id})

    # ── Heartbeat ──

    def _start_heartbeat(self, job_id: str, ws: str) -> None:
        """仅当 worker run() 循环真正运行时启用心跳线程。"""
        if not self._running:
            return
        self._active_heartbeat = (job_id, ws)
        self._heartbeat_stop.clear()
        t = threading.Thread(
            target=self._heartbeat_loop,
            args=(job_id, ws),
            daemon=True,
            name=f"sync-heartbeat-{job_id[:8]}",
        )
        self._heartbeat_thread = t
        t.start()

    def _heartbeat_loop(self, job_id: str, ws: str) -> None:
        while not self._heartbeat_stop.wait(self._heartbeat_interval):
            try:
                self._store.update_job_heartbeat(
                    job_id, ws, datetime.now(timezone.utc)
                )
            except Exception:
                logger.debug("sync_worker_heartbeat_failed", exc_info=True)

    def _stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        self._active_heartbeat = None
        t = self._heartbeat_thread
        self._heartbeat_thread = None
        if t is not None and t.is_alive():
            t.join(timeout=1.0)

    # ── Connector resolution ──

    def _build_connector(self, config: SyncConnectorConfig) -> BaseSyncConnector | None:
        """Resolve a connector instance from the registry."""
        if self._connector_factory is not None:
            return self._connector_factory(config.connector_type, config.credentials)

        # Fall back to import-time registry
        from src.sync import SYNC_CONNECTOR_REGISTRY

        cls = SYNC_CONNECTOR_REGISTRY.get(config.connector_type)
        if cls is None:
            return None
        return cls(config.credentials)

    # ── History / Stats / DLQ ──

    def _record_history(
        self,
        job: SyncJob,
        execution: SyncExecution,
        result: SyncPipelineResult | None,
        elapsed_ms: int,
    ) -> None:
        entry = {
            "job_id": job.id,
            "execution_id": execution.id,
            "name": job.name,
            "status": execution.status,
            "items_new": execution.items_new,
            "items_updated": execution.items_updated,
            "items_deleted": execution.items_deleted,
            "memories_created": execution.memories_created,
            "elapsed_ms": elapsed_ms,
            "started_at": execution.started_at.isoformat() if execution.started_at else "",
        }
        with self._lock:
            self._history.append(entry)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

    def _write_dead_letter(self, execution: SyncExecution) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = f"sync_{ts}_{execution.id[:8]}.json"
        self._dead_letter_dir.mkdir(parents=True, exist_ok=True)
        path = self._dead_letter_dir / filename
        try:
            path.write_text(
                json.dumps(
                    {
                        "execution_id": execution.id,
                        "job_id": execution.job_id,
                        "status": execution.status,
                        "error": execution.error,
                        "started_at": execution.started_at.isoformat() if execution.started_at else "",
                        "failed_at": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            logger.info("sync_dead_letter_written", extra={"path": str(path)})
        except Exception:
            logger.exception("sync_dead_letter_write_failed")

    # ── Runtime Stats ──

    @property
    def stats(self) -> dict[str, Any]:
        dlq_count = 0
        try:
            if self._dead_letter_dir.exists():
                dlq_count = len(list(self._dead_letter_dir.glob("sync_*.json")))
        except Exception:
            pass

        with self._lock:
            return {
                "worker": {
                    "alive": self.is_alive(),
                    "started_at": self._started_at,
                },
                "jobs": {
                    "completed": self._completed_count,
                    "failed": self._failed_count,
                    "in_progress": self._in_progress_count,
                    "pending": int(self._queue.qsize()),
                },
                "queue": {
                    "pending": int(self._queue.qsize()),
                },
                "dead_letter": {
                    "count": dlq_count,
                    "dir": str(self._dead_letter_dir),
                },
                "recent_executions": list(self._history[-20:]),
            }

    @property
    def alerts(self) -> list[dict[str, Any]]:
        dlq_count = 0
        try:
            if self._dead_letter_dir.exists():
                dlq_count = len(list(self._dead_letter_dir.glob("sync_*.json")))
        except Exception:
            pass

        result: list[dict[str, Any]] = []

        if dlq_count >= 5:
            result.append({
                "level": "warning",
                "type": "dlq_accumulation",
                "message": f"Sync Dead Letter Queue 积压 {dlq_count} 条",
                "threshold": 5,
                "current": dlq_count,
            })

        if self._queue.qsize() >= 10:
            result.append({
                "level": "warning",
                "type": "queue_congestion",
                "message": f"同步队列积压 {self._queue.qsize()} 条",
                "threshold": 10,
                "current": self._queue.qsize(),
            })

        with self._lock:
            recent = list(self._history[-10:])
        if recent:
            failed_in_window = sum(1 for e in recent if e.get("status") == "failed")
            fail_rate = failed_in_window / len(recent)
            if fail_rate >= 0.3:
                result.append({
                    "level": "critical",
                    "type": "high_failure_rate",
                    "message": f"最近 {len(recent)} 条同步失败率 {fail_rate:.0%}",
                    "threshold": 0.3,
                    "current": round(fail_rate, 2),
                })

        return result


def _truncate_error(max_len: int = 500) -> str:
    import traceback

    tb = traceback.format_exc()
    return tb[:max_len] if len(tb) > max_len else tb
