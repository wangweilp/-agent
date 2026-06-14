"""Sandbox v2 Backend Factory — 根据配置创建 store / queue / storage。

设计原则:
1. 默认创建 SQLite/local 后端（不破坏现有模式）。
2. 显式选择 postgres/redis/minio 但缺依赖或缺配置 → fail closed（不回退）。
3. 所有创建方法返回 (instance, error) 元组。

Step 12 — Production Backend Adapters.
"""

from __future__ import annotations

import logging
from typing import Any

from src.open_platform.sandbox_v2.config import SandboxV2Settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Backend Creation
# ═══════════════════════════════════════════════════════════════════════════

def create_sandbox_v2_store(settings: SandboxV2Settings) -> tuple[Any | None, str]:
    """根据配置创建 SandboxV2Store 实例。

    返回 (store_instance, error_message)。
    error 为空字符串表示成功。
    """
    if settings.database_backend == "sqlite":
        try:
            from src.adapters.config import Settings as AppSettings
            from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
            app_config = AppSettings()
            store = SQLiteSandboxV2Store(config=app_config)
            return store, ""
        except Exception as e:
            return None, f"Failed to create SQLiteSandboxV2Store: {e}"

    if settings.database_backend == "postgres":
        if not settings.postgres_dsn:
            return None, (
                "SANDBOX_V2_DATABASE_BACKEND=postgres but SANDBOX_V2_POSTGRES_DSN is empty. "
                "Set SANDBOX_V2_POSTGRES_DSN or switch to SANDBOX_V2_DATABASE_BACKEND=sqlite."
            )
        # 检查 psycopg 是否可用
        try:
            import importlib
            importlib.import_module("psycopg2")
        except ImportError:
            try:
                importlib.import_module("psycopg")
            except ImportError:
                return None, (
                    "SANDBOX_V2_DATABASE_BACKEND=postgres but psycopg2/psycopg is not installed. "
                    "Install with: pip install psycopg2-binary"
                )
        try:
            from src.adapters.postgres_sandbox_v2_store import PostgresSandboxV2Store
            store = PostgresSandboxV2Store(dsn=settings.postgres_dsn, connect=False)
            return store, ""
        except Exception as e:
            return None, f"Failed to create PostgresSandboxV2Store: {e}"

    return None, f"Unknown database_backend: '{settings.database_backend}'. Valid: sqlite, postgres"


def create_sandbox_v2_queue(settings: SandboxV2Settings) -> tuple[Any | None, str]:
    """根据配置创建 SandboxQueue 实例。

    返回 (queue_instance, error_message)。
    """
    if settings.queue_backend == "sqlite":
        try:
            from src.adapters.config import Settings as AppSettings
            from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
            app_config = AppSettings()
            queue = SQLiteSandboxV2Queue(config=app_config)
            return queue, ""
        except Exception as e:
            return None, f"Failed to create SQLiteSandboxV2Queue: {e}"

    if settings.queue_backend == "redis":
        if not settings.redis_url:
            return None, (
                "SANDBOX_V2_QUEUE_BACKEND=redis but SANDBOX_V2_REDIS_URL is empty. "
                "Set SANDBOX_V2_REDIS_URL or switch to SANDBOX_V2_QUEUE_BACKEND=sqlite."
            )
        try:
            import importlib
            importlib.import_module("redis")
        except ImportError:
            return None, (
                "SANDBOX_V2_QUEUE_BACKEND=redis but redis-py is not installed. "
                "Install with: pip install redis"
            )
        try:
            from src.adapters.redis_sandbox_v2_queue import RedisSandboxV2Queue
            queue = RedisSandboxV2Queue(redis_url=settings.redis_url, connect=False)
            return queue, ""
        except Exception as e:
            return None, f"Failed to create RedisSandboxV2Queue: {e}"

    if settings.queue_backend == "celery":
        return None, (
            "SANDBOX_V2_QUEUE_BACKEND=celery is not yet implemented. "
            "Use sqlite or redis."
        )

    return None, f"Unknown queue_backend: '{settings.queue_backend}'. Valid: sqlite, redis"


def create_sandbox_v2_artifact_store(settings: SandboxV2Settings) -> tuple[Any | None, str]:
    """根据配置创建 artifact storage 实例。

    返回 (storage_instance, error_message)。
    """
    backend = settings.object_storage_backend

    if backend == "local":
        try:
            from src.open_platform.sandbox_v2.artifacts import LocalSandboxArtifactStore
            store = LocalSandboxArtifactStore(artifact_root=settings.artifact_root)
            return store, ""
        except Exception as e:
            return None, f"Failed to create LocalSandboxArtifactStore: {e}"

    if backend in ("minio", "s3"):
        endpoint = settings.minio_endpoint
        access_key = settings.minio_access_key or settings.s3_access_key
        secret_key = settings.minio_secret_key or settings.s3_secret_key
        bucket = settings.minio_bucket or settings.s3_bucket
        region = settings.s3_region

        if backend == "minio" and not endpoint:
            return None, "object_storage_backend=minio but SANDBOX_V2_MINIO_ENDPOINT is empty"
        if not access_key:
            return None, f"object_storage_backend={backend} but access key is empty"
        if not secret_key:
            return None, f"object_storage_backend={backend} but secret key is empty"
        if not bucket:
            return None, f"object_storage_backend={backend} but bucket is empty"

        try:
            import importlib
            importlib.import_module("boto3")
        except ImportError:
            return None, (
                f"object_storage_backend={backend} but boto3 is not installed. "
                "Install with: pip install boto3"
            )

        try:
            from src.adapters.object_sandbox_v2_storage import S3SandboxV2Storage
            if backend == "minio":
                store = S3SandboxV2Storage(
                    endpoint_url=endpoint,
                    access_key=access_key,
                    secret_key=secret_key,
                    bucket=bucket,
                    region=region,
                    prefix=settings.storage_prefix,
                    connect=False,
                )
            else:
                store = S3SandboxV2Storage(
                    endpoint_url="",
                    access_key=access_key,
                    secret_key=secret_key,
                    bucket=bucket,
                    region=region,
                    prefix=settings.storage_prefix,
                    connect=False,
                )
            return store, ""
        except Exception as e:
            return None, f"Failed to create S3SandboxV2Storage: {e}"

    return None, f"Unknown object_storage_backend: '{backend}'. Valid: local, minio, s3"


def create_sandbox_v2_package_store(settings: SandboxV2Settings) -> tuple[Any | None, str]:
    """根据配置创建 package quarantine storage 实例。"""
    if settings.object_storage_backend == "local":
        try:
            from src.open_platform.sandbox_v2.packages import LocalSandboxPackageQuarantineStore
            store = LocalSandboxPackageQuarantineStore(quarantine_root=settings.package_quarantine_root)
            return store, ""
        except Exception as e:
            return None, f"Failed to create LocalSandboxPackageQuarantineStore: {e}"

    # 非 local 也返回 object storage adapter
    return create_sandbox_v2_artifact_store(settings)


# ═══════════════════════════════════════════════════════════════════════════
# Backend Readiness
# ═══════════════════════════════════════════════════════════════════════════

def get_backend_readiness(settings: SandboxV2Settings) -> dict[str, Any]:
    """返回完整后端 readiness 状态字典。"""
    result: dict[str, Any] = {
        "database_backend": settings.database_backend,
        "database_backend_ready": True,
        "postgres_adapter_available": False,
        "postgres_dsn_configured": bool(settings.postgres_dsn),

        "queue_backend": settings.queue_backend,
        "queue_backend_ready": True,
        "redis_queue_adapter_available": False,
        "redis_url_configured": bool(settings.redis_url),

        "object_storage_backend": settings.object_storage_backend,
        "object_storage_ready": True,
        "minio_adapter_available": False,
        "minio_endpoint_configured": bool(settings.minio_endpoint),

        "local_fallback_enabled": (
            settings.database_backend == "sqlite"
            and settings.queue_backend == "sqlite"
            and settings.object_storage_backend == "local"
        ),
        "production_backend_configured": False,
        "backend_warnings": [],
        "backend_blockers": [],
    }

    # Check database
    if settings.database_backend == "sqlite":
        result["database_backend_ready"] = True
    elif settings.database_backend == "postgres":
        result["database_backend_ready"] = False
        if not settings.postgres_dsn:
            result["backend_blockers"].append("PostgreSQL selected but POSTGRES_DSN is empty")
        else:
            # 尝试导入
            pg_ok = False
            try:
                import importlib
                importlib.import_module("psycopg2")
                pg_ok = True
            except ImportError:
                try:
                    importlib.import_module("psycopg")
                    pg_ok = True
                except ImportError:
                    pass
            if pg_ok:
                result["postgres_adapter_available"] = True
                result["database_backend_ready"] = True
            else:
                result["backend_blockers"].append("PostgreSQL selected but psycopg2/psycopg not installed")

    # Check queue
    if settings.queue_backend == "sqlite":
        result["queue_backend_ready"] = True
    elif settings.queue_backend == "redis":
        if not settings.redis_url:
            result["backend_blockers"].append("Redis selected but REDIS_URL is empty")
            result["queue_backend_ready"] = False
        else:
            redis_ok = False
            try:
                import importlib
                importlib.import_module("redis")
                redis_ok = True
            except ImportError:
                pass
            if redis_ok:
                result["redis_queue_adapter_available"] = True
                result["queue_backend_ready"] = True
            else:
                result["backend_blockers"].append("Redis selected but redis-py not installed")

    # Check object storage
    if settings.object_storage_backend == "local":
        result["object_storage_ready"] = True
    elif settings.object_storage_backend in ("minio", "s3"):
        minio_ok = False
        try:
            import importlib
            importlib.import_module("boto3")
            minio_ok = True
        except ImportError:
            pass

        if settings.object_storage_backend == "minio" and not settings.minio_endpoint:
            result["backend_blockers"].append("MinIO selected but MINIO_ENDPOINT is empty")
        access_key = settings.minio_access_key or settings.s3_access_key
        secret_key = settings.minio_secret_key or settings.s3_secret_key
        bucket = settings.minio_bucket or settings.s3_bucket
        if not access_key:
            result["backend_blockers"].append("Object storage selected but access key is empty")
        if not secret_key:
            result["backend_blockers"].append("Object storage selected but secret key is empty")
        if not bucket:
            result["backend_blockers"].append("Object storage selected but bucket is empty")

        if minio_ok and access_key and secret_key and bucket:
            result["minio_adapter_available"] = True
            result["object_storage_ready"] = True
        else:
            result["object_storage_ready"] = False
            if not minio_ok:
                result["backend_blockers"].append("Object storage selected but boto3 not installed")

    # Production backend configured
    result["production_backend_configured"] = (
        settings.database_backend == "postgres"
        or settings.queue_backend == "redis"
        or settings.object_storage_backend in ("minio", "s3")
    )

    # Warnings
    result["backend_warnings"] = settings.backend_warnings()

    return result
