"""Sync router — Multi-Source Sync Hub API endpoints.

Endpoints:
    POST   /sync/connectors                  — Create connector config
    GET    /sync/connectors                  — List all connectors
    DELETE /sync/connectors/{connector_id}   — Delete connector
    POST   /sync/connectors/{id}/test        — Test connection to a connector
    POST   /sync/jobs                        — Create sync job with rule
    GET    /sync/jobs                        — List all jobs with rules
    GET    /sync/jobs/{job_id}               — Get job detail + recent executions
    POST   /sync/jobs/{id}/run               — Manually trigger sync
    POST   /sync/jobs/{id}/retry             — Retry failed execution
    DELETE /sync/jobs/{job_id}               — Delete job and its rule
    GET    /sync/history                     — Execution history
    GET    /sync/stats                       — Aggregate sync stats

Pattern follows src/api/import_router.py: factory function, consistent status
field, structured error responses via HTTPException, and response helpers.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.middleware import require_auth, require_manage
from src.core.auth import TokenPayload
from src.sync.models import (
    SyncConnectionResult,
    SyncConnectorConfig,
    SyncExecution,
    SyncJob,
    SyncRule,
)
from src.sync.scheduler import SyncScheduler
from src.sync.sync_store import SyncStore
from src.sync.sync_worker import SyncWorker

# ── Credential redaction ──
# These field names (case-insensitive) are stripped from API responses.
_CREDENTIAL_REDACT_KEYS: frozenset[str] = frozenset({
    "password", "secret", "token", "api_key", "apikey", "access_key",
    "access_token", "refresh_token", "private_key", "client_secret",
    "app_secret", "webhook_secret", "signing_secret", "auth_token",
    "bearer_token", "personal_access_token", "connection_string",
})

_REDACTED_VALUE = "********"


def _redact_credentials(credentials: dict) -> dict:
    """Return a copy of credentials with sensitive values masked.

    Only top-level keys matching known secret patterns are redacted.
    Nested dicts are walked one level deep.
    """
    if not credentials:
        return {}
    redacted: dict = {}
    for key, value in credentials.items():
        key_lower = key.lower().replace("-", "_")
        if key_lower in _CREDENTIAL_REDACT_KEYS or any(
            pattern in key_lower for pattern in ("_secret", "_token", "_key", "_password")
        ):
            redacted[key] = _REDACTED_VALUE
        elif isinstance(value, dict):
            redacted[key] = _redact_credentials(value)
        else:
            redacted[key] = value
    return redacted

logger = logging.getLogger(__name__)


# ── Request models ──


class CreateConnectorRequest(BaseModel):
    name: str
    connector_type: str
    credentials: dict = {}


class CreateJobRequest(BaseModel):
    connector_config_id: str
    name: str
    rule_type: str = "manual"
    cron_expression: str | None = None


# ── Factory ──


def create_sync_router(
    sync_store: SyncStore,
    sync_worker: SyncWorker,
    sync_scheduler: SyncScheduler,
) -> APIRouter:
    router = APIRouter(prefix="/sync", tags=["sync"])

    # ═════════════════════════════════════════════════════════════
    # Connectors  (admin-only: require_manage)
    # ═════════════════════════════════════════════════════════════

    @router.post("/connectors")
    async def create_connector(
        body: CreateConnectorRequest,
        _payload: TokenPayload = Depends(require_manage),
    ):
        """Create a new connector configuration."""
        if not body.name.strip():
            raise HTTPException(400, "name is required")
        if not body.connector_type.strip():
            raise HTTPException(400, "connector_type is required")

        config = SyncConnectorConfig(
            name=body.name.strip(),
            connector_type=body.connector_type.strip(),
            credentials=body.credentials,
        )
        sync_store.save_connector(config)

        logger.info(
            "sync_connector_created",
            extra={"connector_id": config.id, "type": config.connector_type},
        )

        return {
            "status": "created",
            "connector": _connector_to_response(config),
        }

    @router.get("/connectors")
    async def list_connectors(
        _payload: TokenPayload = Depends(require_auth),
    ):
        """List all connector configurations (credentials redacted)."""
        connectors = sync_store.list_connectors()
        return {
            "status": "ok",
            "connectors": [_connector_to_response(c) for c in connectors],
            "total": len(connectors),
        }

    @router.delete("/connectors/{connector_id}")
    async def delete_connector(
        connector_id: str,
        _payload: TokenPayload = Depends(require_manage),
    ):
        """Delete a connector and cascade-delete its jobs and rules."""
        config = sync_store.get_connector(connector_id)
        if config is None:
            raise HTTPException(404, f"Connector {connector_id} not found")

        deleted = sync_store.delete_connector(connector_id)

        logger.info(
            "sync_connector_deleted",
            extra={"connector_id": connector_id, "deleted": deleted},
        )

        return {
            "status": "deleted",
            "connector_id": connector_id,
            "deleted": deleted,
        }

    @router.post("/connectors/{connector_id}/test")
    async def test_connector(
        connector_id: str,
        _payload: TokenPayload = Depends(require_manage),
    ):
        """Test connectivity by instantiating the connector and calling test_connection()."""
        config = sync_store.get_connector(connector_id)
        if config is None:
            raise HTTPException(404, f"Connector {connector_id} not found")

        from src.sync import SYNC_CONNECTOR_REGISTRY

        cls = SYNC_CONNECTOR_REGISTRY.get(config.connector_type)
        if cls is None:
            raise HTTPException(
                400,
                f"No connector registered for type '{config.connector_type}'",
            )

        try:
            connector = cls(config.credentials)
            result: SyncConnectionResult = connector.test_connection()
        except Exception as exc:
            logger.exception(
                "sync_test_connection_crashed",
                extra={"connector_id": connector_id},
            )
            result = SyncConnectionResult(
                success=False,
                message=f"Connection test crashed: {str(exc)}",
            )

        return {
            "status": "ok",
            "connector_id": connector_id,
            "connector_type": config.connector_type,
            "test": {
                "success": result.success,
                "message": result.message,
                "resources_count": result.resources_count,
            },
        }

    # ═════════════════════════════════════════════════════════════
    # Jobs  (admin-only: require_manage for write, require_auth for read)
    # ═════════════════════════════════════════════════════════════

    @router.post("/jobs")
    async def create_job(
        body: CreateJobRequest,
        _payload: TokenPayload = Depends(require_manage),
    ):
        """Create a sync job with a scheduling rule.

        Validates the connector exists, creates a SyncRule, then binds the SyncJob
        to it. Cron jobs trigger a scheduler refresh so the new timer is picked up.
        """
        config = sync_store.get_connector(body.connector_config_id)
        if config is None:
            raise HTTPException(404, f"Connector config {body.connector_config_id} not found")

        if not body.name.strip():
            raise HTTPException(400, "name is required")

        rule_type = body.rule_type.strip() or "manual"
        if rule_type not in ("manual", "cron", "realtime"):
            raise HTTPException(
                400,
                f"Invalid rule_type: '{rule_type}'. Must be manual, cron, or realtime.",
            )

        if rule_type == "cron" and not body.cron_expression:
            raise HTTPException(400, "cron_expression is required when rule_type is 'cron'")

        rule = SyncRule(
            rule_type=rule_type,
            cron_expression=body.cron_expression or "",
        )
        sync_store.save_rule(rule)

        job = SyncJob(
            connector_config_id=body.connector_config_id,
            rule_id=rule.id,
            name=body.name.strip(),
        )
        sync_store.save_job(job)

        if rule_type == "cron":
            sync_scheduler.refresh_timers()

        logger.info(
            "sync_job_created",
            extra={
                "job_id": job.id,
                "name": job.name,
                "rule_type": rule_type,
                "connector_id": body.connector_config_id,
            },
        )

        return {
            "status": "created",
            "job": _job_to_response(job, rule),
        }

    @router.get("/jobs")
    async def list_jobs(
        _payload: TokenPayload = Depends(require_auth),
    ):
        """List all sync jobs with their scheduling rules."""
        jobs = sync_store.list_jobs()
        result: list[dict[str, Any]] = []
        for job in jobs:
            rule = sync_store.get_rule_for_job(job.id)
            result.append(_job_to_response(job, rule))

        return {
            "status": "ok",
            "jobs": result,
            "total": len(result),
            "worker": {
                "alive": sync_worker.is_alive(),
                "completed": sync_worker.stats["jobs"]["completed"],
                "failed": sync_worker.stats["jobs"]["failed"],
                "in_progress": sync_worker.stats["jobs"]["in_progress"],
                "pending": sync_worker.pending,
            },
        }

    @router.get("/jobs/{job_id}")
    async def get_job(job_id: str, _payload: TokenPayload = Depends(require_auth)):
        """Get a single job with its rule and most recent executions."""
        job = sync_store.get_job(job_id)
        if job is None:
            raise HTTPException(404, f"Job {job_id} not found")

        rule = sync_store.get_rule_for_job(job_id)
        executions = sync_store.list_executions(job_id=job_id, limit=20)

        return {
            "status": "ok",
            "job": _job_to_response(job, rule),
            "recent_executions": [_execution_to_response(e) for e in executions],
        }

    @router.post("/jobs/{job_id}/run")
    async def trigger_job(job_id: str, _payload: TokenPayload = Depends(require_manage)):
        """Manually trigger a sync job. Creates a pending execution and enqueues it."""
        job = sync_store.get_job(job_id)
        if job is None:
            raise HTTPException(404, f"Job {job_id} not found")

        if not job.enabled:
            raise HTTPException(409, f"Job {job_id} is disabled")

        if job.status == "running":
            raise HTTPException(409, f"Job {job_id} is already running")

        t0 = time.monotonic()

        execution = SyncExecution(job_id=job_id)
        sync_store.save_execution(execution)
        sync_worker.enqueue(job, execution)

        t_ms = int((time.monotonic() - t0) * 1000)

        return {
            "status": "accepted",
            "job_id": job_id,
            "execution_id": execution.id,
            "trigger_time_ms": t_ms,
            "queue_depth": sync_worker.pending,
            "alerts": sync_worker.alerts,
        }

    @router.post("/jobs/{job_id}/retry")
    async def retry_job(
        job_id: str,
        execution_id: str | None = Body(None, embed=True),
        _payload: TokenPayload = Depends(require_manage),
    ):
        """Retry a failed execution.

        If execution_id is given, retry that specific execution.
        Otherwise retry the most recently failed execution for this job.
        """
        job = sync_store.get_job(job_id)
        if job is None:
            raise HTTPException(404, f"Job {job_id} not found")

        if execution_id:
            prev_exec = sync_store.get_execution(execution_id)
            if prev_exec is None:
                raise HTTPException(404, f"Execution {execution_id} not found")
            if prev_exec.job_id != job_id:
                raise HTTPException(
                    400,
                    f"Execution {execution_id} does not belong to job {job_id}",
                )
        else:
            executions = sync_store.list_executions(job_id=job_id, limit=50)
            failed_execs = [e for e in executions if e.status == "failed"]
            if not failed_execs:
                raise HTTPException(404, f"No failed execution found for job {job_id}")
            prev_exec = failed_execs[0]

        t0 = time.monotonic()

        execution = SyncExecution(job_id=job_id)
        sync_store.save_execution(execution)
        sync_worker.enqueue(job, execution)

        t_ms = int((time.monotonic() - t0) * 1000)

        return {
            "status": "retrying",
            "job_id": job_id,
            "execution_id": execution.id,
            "previous_execution_id": prev_exec.id,
            "previous_status": prev_exec.status,
            "trigger_time_ms": t_ms,
            "queue_depth": sync_worker.pending,
        }

    @router.delete("/jobs/{job_id}")
    async def delete_job(job_id: str, _payload: TokenPayload = Depends(require_manage)):
        """Delete a job and its associated scheduling rule."""
        job = sync_store.get_job(job_id)
        if job is None:
            raise HTTPException(404, f"Job {job_id} not found")

        rule_id = job.rule_id
        job_deleted = sync_store.delete_job(job_id)
        rule_deleted = sync_store.delete_rule(rule_id) if rule_id else False

        sync_scheduler.refresh_timers()

        logger.info(
            "sync_job_deleted",
            extra={
                "job_id": job_id,
                "job_deleted": job_deleted,
                "rule_deleted": rule_deleted,
            },
        )

        return {
            "status": "deleted",
            "job_id": job_id,
            "job_deleted": job_deleted,
            "rule_deleted": rule_deleted,
        }

    # ═════════════════════════════════════════════════════════════
    # History & Stats
    # ═════════════════════════════════════════════════════════════

    @router.get("/history")
    async def list_history(
        connector_id: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=500),
        _payload: TokenPayload = Depends(require_auth),
    ):
        """List execution history, optionally filtered by connector."""
        executions = sync_store.list_executions(
            connector_id=connector_id,
            limit=limit,
        )

        return {
            "status": "ok",
            "executions": [_execution_to_response(e) for e in executions],
            "total": len(executions),
        }

    @router.get("/stats")
    async def get_stats(
        _payload: TokenPayload = Depends(require_auth),
    ):
        """Aggregate sync stats: connectors, jobs, queue, recent activity."""
        connectors = sync_store.list_connectors()
        jobs = sync_store.list_jobs()

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=1)

        all_executions = sync_store.list_executions(limit=500)
        last_hour_executions = 0
        last_hour_failures = 0
        for e in all_executions:
            if e.started_at and e.started_at >= cutoff:
                last_hour_executions += 1
                if e.status == "failed":
                    last_hour_failures += 1

        per_connector: list[dict[str, Any]] = []
        for c in connectors:
            c_jobs = [j for j in jobs if j.connector_config_id == c.id]
            per_connector.append({
                "connector_id": c.id,
                "name": c.name,
                "type": c.connector_type,
                "enabled": c.enabled,
                "last_sync_status": c.last_sync_status,
                "last_sync_time": c.last_sync_time.isoformat() if c.last_sync_time else None,
                "job_count": len(c_jobs),
            })

        worker_stats = sync_worker.stats

        return {
            "status": "ok",
            "total_connectors": len(connectors),
            "enabled_connectors": sum(1 for c in connectors if c.enabled),
            "total_jobs": len(jobs),
            "active_jobs": sum(
                1 for j in jobs if j.status in ("running", "pending")
            ),
            "pending_jobs": sync_worker.pending,
            "queue_depth": sync_worker.pending,
            "last_hour_executions": last_hour_executions,
            "last_hour_failures": last_hour_failures,
            "summary": {
                "total_connectors": len(connectors),
                "enabled_connectors": sum(1 for c in connectors if c.enabled),
                "total_jobs": len(jobs),
                "active_jobs": sum(
                    1 for j in jobs if j.status in ("running", "pending")
                ),
                "pending_jobs": sync_worker.pending,
                "queue_depth": sync_worker.pending,
                "last_hour_executions": last_hour_executions,
                "last_hour_failures": last_hour_failures,
            },
            "per_connector": per_connector,
            "connectors": per_connector,
            "worker": {
                "alive": worker_stats["worker"]["alive"],
                "completed": worker_stats["jobs"]["completed"],
                "failed": worker_stats["jobs"]["failed"],
                "in_progress": worker_stats["jobs"]["in_progress"],
            },
            "alerts": sync_worker.alerts,
        }

    return router


# ── Response helpers ──


def _connector_to_response(config: SyncConnectorConfig) -> dict[str, Any]:
    return {
        "id": config.id,
        "name": config.name,
        "connector_type": config.connector_type,
        "enabled": config.enabled,
        "last_sync_time": config.last_sync_time.isoformat() if config.last_sync_time else None,
        "last_sync_status": config.last_sync_status,
        "created_at": config.created_at.isoformat(),
        "updated_at": config.updated_at.isoformat(),
    }


def _job_to_response(job: SyncJob, rule: SyncRule | None) -> dict[str, Any]:
    rule_data: dict[str, Any] | None = None
    rule_type = rule.rule_type if rule else "manual"
    cron_expression = rule.cron_expression if rule else ""
    if rule is not None:
        rule_data = {
            "id": rule.id,
            "rule_type": rule.rule_type,
            "cron_expression": rule.cron_expression,
            "enabled": rule.enabled,
        }

    return {
        "id": job.id,
        "name": job.name,
        "connector_config_id": job.connector_config_id,
        "status": job.status,
        "enabled": job.enabled,
        "rule_type": rule_type,
        "cron_expression": cron_expression,
        "created_at": job.created_at.isoformat(),
        "rule": rule_data,
    }


def _execution_to_response(e: SyncExecution) -> dict[str, Any]:
    return {
        "id": e.id,
        "job_id": e.job_id,
        "status": e.status,
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        "items_fetched": e.items_fetched,
        "items_new": e.items_new,
        "items_updated": e.items_updated,
        "items_deleted": e.items_deleted,
        "items_renamed": e.items_renamed,
        "memories_created": e.memories_created,
        "errors_count": e.errors_count,
        "error": e.error,
        "elapsed_ms": e.elapsed_ms,
    }
