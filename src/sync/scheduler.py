"""SyncScheduler — cron-based sync job scheduler.

Design:
  - Own daemon thread, polls every 30 seconds
  - Uses croniter for cron expression parsing
  - Manual syncs are triggered directly via API, not through the scheduler
  - Maintains in-memory next_fire_time map for each cron job

Mirrors the thread pattern from ImportWorker.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from src.sync.models import SyncExecution
from src.sync.sync_store import SyncStore

logger = logging.getLogger(__name__)


class SyncScheduler(threading.Thread):
    """Background thread that triggers cron-scheduled sync jobs.

    Manual and realtime jobs are triggered externally (API/webhook);
    this scheduler only handles jobs bound to cron rules.
    """

    def __init__(
        self,
        sync_store: SyncStore,
        sync_worker: object,  # SyncWorker, avoid circular import
        tick_interval: int = 30,
        stale_timeout_seconds: float = 300.0,
    ) -> None:
        super().__init__(daemon=True, name="sync-scheduler")
        self._store = sync_store
        self._worker = sync_worker  # has .enqueue(job, execution)
        self._tick_interval = tick_interval
        self._stale_timeout_seconds = stale_timeout_seconds
        self._running = False
        # job_id → next fire datetime
        self._cron_timers: dict[str, datetime] = {}
        # job_id → workspace_id (populated with the timer map for context-free threads)
        self._job_workspaces: dict[str, str] = {}
        self._lock = threading.Lock()

    # ── Thread main loop ──

    def run(self) -> None:
        self._running = True
        self._recover_stale_jobs()
        self._reload_cron_timers()
        logger.info("sync_scheduler_started", extra={"cron_jobs": len(self._cron_timers)})

        while self._running:
            now = datetime.now(timezone.utc)
            triggered: list[str] = []

            with self._lock:
                for job_id, next_fire in list(self._cron_timers.items()):
                    if now >= next_fire:
                        triggered.append(job_id)
                        # Recompute next fire time
                        ws = self._job_workspaces.get(job_id)
                        rule = self._store.get_rule_for_job(job_id, workspace_id=ws)
                        if rule and rule.cron_expression and rule.enabled:
                            try:
                                new_next = _cron_next(rule.cron_expression, now)
                                self._cron_timers[job_id] = new_next
                            except Exception:
                                logger.warning(
                                    "sync_cron_recompute_failed",
                                    extra={"job_id": job_id, "expr": rule.cron_expression},
                                )
                                # Remove broken timer to avoid tight loop
                                del self._cron_timers[job_id]
                                self._job_workspaces.pop(job_id, None)
                        else:
                            # Rule no longer valid
                            del self._cron_timers[job_id]
                            self._job_workspaces.pop(job_id, None)

            for job_id in triggered:
                self._trigger_job(job_id)

            # P1-1: 周期性收敛 stale running/queued Job（Worker 崩溃恢复）
            self._recover_stale_jobs()

            time.sleep(self._tick_interval)

    # ── Internal ──

    def _recover_stale_jobs(self) -> None:
        """调用 Store 收敛 Worker 崩溃遗留的 stale Job（标记 failed，不自动重试）。"""
        try:
            recovered = self._store.recover_stale_jobs(
                stale_timeout_seconds=self._stale_timeout_seconds
            )
            if recovered:
                logger.warning(
                    "sync_recovered_stale_jobs",
                    extra={"recovered": recovered},
                )
        except Exception:
            logger.warning("sync_recover_stale_jobs_failed", exc_info=True)

    def _trigger_job(self, job_id: str) -> None:
        """Enqueue a sync job to SyncWorker."""
        ws = self._job_workspaces.get(job_id)
        job = self._store.get_job(job_id, workspace_id=ws)
        if job is None or not job.enabled:
            return
        if job.status == "cancelled":
            return

        rule = self._store.get_rule_for_job(job_id, workspace_id=ws)
        if rule is None or not rule.enabled:
            return

        # 认领为 queued（非终止），供删除/取消语义区分
        job.status = "queued"
        self._store.update_job(job, workspace_id=job.workspace_id)

        execution = SyncExecution(job_id=job_id, workspace_id=job.workspace_id)
        self._store.save_execution(execution, workspace_id=job.workspace_id)

        if hasattr(self._worker, "enqueue"):
            self._worker.enqueue(job, execution)

        logger.info(
            "sync_scheduler_triggered",
            extra={"job_id": job_id, "execution_id": execution.id, "job_name": job.name},
        )

    def _reload_cron_timers(self) -> None:
        """Rebuild cron timer map from stored rules at startup."""
        now = datetime.now(timezone.utc)
        jobs = self._store.list_all_jobs(enabled_only=True)

        with self._lock:
            self._cron_timers.clear()
            self._job_workspaces.clear()
            for job in jobs:
                rule = self._store.get_rule_for_job(job.id, workspace_id=job.workspace_id)
                if rule and rule.rule_type == "cron" and rule.cron_expression:
                    try:
                        next_fire = _cron_next(rule.cron_expression, now)
                        self._cron_timers[job.id] = next_fire
                        self._job_workspaces[job.id] = job.workspace_id
                        logger.debug(
                            "sync_cron_loaded",
                            extra={"job_id": job.id, "expr": rule.cron_expression, "next": next_fire.isoformat()},
                        )
                    except Exception:
                        logger.warning(
                            "sync_invalid_cron",
                            extra={"job_id": job.id, "expr": rule.cron_expression},
                        )

    def refresh_timers(self) -> None:
        """Public API: reload cron timers after job/rule changes."""
        self._reload_cron_timers()

    def shutdown(self, timeout: float = 5.0) -> None:
        self._running = False
        if self._started.is_set():
            self.join(timeout=timeout)
        logger.info("sync_scheduler_shutdown")


# ── Cron helper ──


def _cron_next(expression: str, from_time: datetime) -> datetime:
    """Compute the next fire time for a cron expression.

    Uses croniter if available, falls back to a simple parser for common patterns.
    """
    try:
        from croniter import croniter

        return croniter(expression, from_time).get_next(datetime)
    except ImportError:
        return _simple_cron_next(expression, from_time)


def _simple_cron_next(expression: str, from_time: datetime) -> datetime:
    """Fallback cron parser for common patterns when croniter is unavailable.

    Supports: hourly, daily, weekly, and simple "every N hours" patterns.
    """
    from datetime import timedelta

    parts = expression.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Unsupported cron expression: {expression}")

    minute, hour, dom, month, dow = parts

    # Simple exact patterns
    if minute == "0" and hour == "*" and dom == "*" and month == "*" and dow == "*":
        # Every hour at minute 0
        next_dt = from_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return next_dt

    if minute == "0" and hour == "0" and dom == "*" and month == "*" and dow == "*":
        # Every day at midnight
        next_dt = from_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return next_dt

    if minute == "0" and hour == "0" and dom == "*" and month == "*" and dow == "0":
        # Every Sunday at midnight
        days_ahead = 6 - from_time.weekday()  # Sunday = 6
        if days_ahead <= 0:
            days_ahead += 7
        next_dt = from_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
        return next_dt

    # Fallback: hourly
    next_dt = from_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return next_dt
