"""Production backend readiness helpers.

This module is intentionally an adapter/readiness layer. It does not replace the
default SQLite/ChromaDB local demo path and it does not open PostgreSQL, Redis,
S3/MinIO, or queue connections. The goal is to make the production migration
boundary explicit and health-checkable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.object_storage_adapter import ObjectStorageAdapter
from src.adapters.postgres_adapter import PostgresAdapter
from src.adapters.redis_cache import RedisCacheAdapter
from src.adapters.task_queue_adapter import TaskQueueAdapter


@dataclass(frozen=True)
class BackendHealth:
    name: str
    configured_backend: str
    selected: bool
    status: str
    enabled: bool
    mode: str
    risk_level: str
    last_checked_at: str
    evidence: list[str] = field(default_factory=list)
    reason: str = ""
    recommended_next_step: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "configured_backend": self.configured_backend,
            "selected": self.selected,
            "status": self.status,
            "enabled": self.enabled,
            "mode": self.mode,
            "risk_level": self.risk_level,
            "last_checked_at": self.last_checked_at,
            "evidence": list(self.evidence),
            "reason": self.reason,
            "recommended_next_step": self.recommended_next_step,
            "metadata": dict(self.metadata),
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _configured_url(value: str) -> bool:
    return bool(value and value.strip())


def assess_production_backend_readiness(settings: Settings) -> dict[str, Any]:
    """Return a stable health payload for local and production backend adapters."""
    checked_at = _now()
    pg = PostgresAdapter(settings).assess_readiness().to_dict()
    redis = RedisCacheAdapter(settings).assess_readiness().to_dict()
    obj = ObjectStorageAdapter(settings).assess_readiness().to_dict()
    queue = TaskQueueAdapter(settings).assess_readiness().to_dict()

    database = BackendHealth(
        name="database",
        configured_backend=settings.database_backend,
        selected=True,
        status="local_active" if settings.database_backend == "sqlite" else "configured_metadata_only",
        enabled=settings.database_backend == "sqlite",
        mode="local_demo" if settings.database_backend == "sqlite" else "metadata_only",
        risk_level="low" if settings.database_backend == "sqlite" else "high",
        last_checked_at=checked_at,
        evidence=[
            f"sqlite_db_path={settings.sqlite_db_path}",
            f"postgres_dsn_configured={_configured_url(settings.postgres_dsn)}",
            "PostgreSQL adapter exposes schema/readiness only; no connection is opened.",
        ],
        reason=(
            "SQLite remains the default local demo database."
            if settings.database_backend == "sqlite"
            else "PostgreSQL is selected but only the adapter skeleton/readiness layer is present."
        ),
        recommended_next_step="Generate Alembic migrations, run SQLite to PostgreSQL data migration, then enable DB integration tests.",
        metadata={"postgres_report": pg},
    )

    cache = BackendHealth(
        name="cache",
        configured_backend=settings.cache_backend,
        selected=True,
        status="local_memory_active" if settings.cache_backend == "memory" else "configured_metadata_only",
        enabled=settings.cache_backend == "memory",
        mode="local_demo" if settings.cache_backend == "memory" else "metadata_only",
        risk_level="low" if settings.cache_backend == "memory" else "medium",
        last_checked_at=checked_at,
        evidence=[
            f"redis_url_configured={_configured_url(settings.redis_url)}",
            "Redis adapter defines key patterns and TTLs but does not connect to Redis.",
        ],
        reason=(
            "In-memory cache path is active for local demo."
            if settings.cache_backend == "memory"
            else "Redis is selected but live redis-py integration is not enabled."
        ),
        recommended_next_step="Add redis-py client, connection pooling, cache invalidation tests, and fallback behavior.",
        metadata={"redis_report": redis},
    )

    object_storage = BackendHealth(
        name="object_storage",
        configured_backend=settings.object_storage_backend,
        selected=True,
        status="local_filesystem_active" if settings.object_storage_backend == "local" else "configured_metadata_only",
        enabled=settings.object_storage_backend == "local",
        mode="local_demo" if settings.object_storage_backend == "local" else "metadata_only",
        risk_level="low" if settings.object_storage_backend == "local" else "medium",
        last_checked_at=checked_at,
        evidence=[
            f"upload_dir={settings.upload_dir}",
            f"object_storage_endpoint_configured={_configured_url(settings.object_storage_endpoint)}",
            f"object_storage_bucket={settings.object_storage_bucket}",
            "S3/MinIO adapter is readiness-only; no bucket or network call is made.",
        ],
        reason=(
            "Local filesystem uploads remain active for local demo."
            if settings.object_storage_backend == "local"
            else "Object storage is selected but the live S3/MinIO client is not connected."
        ),
        recommended_next_step="Add signed upload/download flows, bucket lifecycle policy, and object metadata integrity checks.",
        metadata={"object_storage_report": obj},
    )

    task_queue = BackendHealth(
        name="task_queue",
        configured_backend=settings.queue_backend,
        selected=True,
        status="inline_active" if settings.queue_backend == "inline" else "configured_metadata_only",
        enabled=settings.queue_backend == "inline",
        mode="local_demo" if settings.queue_backend == "inline" else "metadata_only",
        risk_level="low" if settings.queue_backend == "inline" else "high",
        last_checked_at=checked_at,
        evidence=[
            f"queue_url_configured={_configured_url(settings.queue_url)}",
            "Queue adapter defines task contracts only; no dispatch worker is started.",
        ],
        reason=(
            "Inline worker path remains active for local demo."
            if settings.queue_backend == "inline"
            else "External queue backend is selected but enqueue/dispatch is still blocked."
        ),
        recommended_next_step="Choose Celery/RQ/Redis queue, add idempotency keys, dead-letter handling, and worker health probes.",
        metadata={"task_queue_report": queue},
    )

    components = {
        "database": database.to_dict(),
        "cache": cache.to_dict(),
        "object_storage": object_storage.to_dict(),
        "task_queue": task_queue.to_dict(),
    }
    production_ready = all(
        components[key]["configured_backend"] in {"postgres", "redis", "s3", "minio", "celery", "rq"}
        and components[key]["enabled"]
        for key in components
    )

    return {
        "status": "local_demo_default" if not production_ready else "production_backends_active",
        "production_ready": production_ready,
        "last_checked_at": checked_at,
        "default_local_mode": "SQLite + ChromaDB + local filesystem + inline worker",
        "claim_boundary": (
            "Current production backend work is adapter skeleton, configuration, and health visibility; "
            "it is not a complete production cluster deployment."
        ),
        "components": components,
    }
