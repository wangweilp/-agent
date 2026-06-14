"""Tests for Sandbox v2 Backend Factory (Step 12).

验证:
1. 默认 database_backend=sqlite → store 创建成功
2. 默认 queue_backend=sqlite → queue 创建成功
3. 默认 object_storage_backend=local → artifact store 创建成功
4. 显式 postgres 但缺 DSN → 返回 error
5. 显式 redis 但缺 REDIS_URL → 返回 error
6. 显式 minio 但缺配置 → 返回 error
7. 未知 backend → 返回 error
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.open_platform.sandbox_v2.config import SandboxV2Settings
from src.open_platform.sandbox_v2.backend_factory import (
    create_sandbox_v2_store,
    create_sandbox_v2_queue,
    create_sandbox_v2_artifact_store,
    create_sandbox_v2_package_store,
    get_backend_readiness,
)


class TestDefaultBackendCreation:
    """默认 SQLite/local 后端创建成功。"""

    def test_default_store_is_sqlite(self):
        settings = SandboxV2Settings(database_backend="sqlite")
        store, err = create_sandbox_v2_store(settings)
        assert store is not None, f"Store creation failed: {err}"
        assert err == ""
        assert "SQLite" in type(store).__name__

    def test_default_queue_is_sqlite(self):
        settings = SandboxV2Settings(queue_backend="sqlite")
        queue, err = create_sandbox_v2_queue(settings)
        assert queue is not None, f"Queue creation failed: {err}"
        assert err == ""
        assert "SQLite" in type(queue).__name__

    def test_default_artifact_store_is_local(self):
        settings = SandboxV2Settings(object_storage_backend="local")
        store, err = create_sandbox_v2_artifact_store(settings)
        assert store is not None, f"Artifact store creation failed: {err}"
        assert err == ""
        assert "Local" in type(store).__name__

    def test_default_package_store_is_local(self):
        settings = SandboxV2Settings(object_storage_backend="local")
        store, err = create_sandbox_v2_package_store(settings)
        assert store is not None, f"Package store creation failed: {err}"
        assert err == ""


class TestExplicitBackendFailClosed:
    """显式选择生产后端但缺配置 → fail closed。"""

    def test_postgres_without_dsn_fails(self):
        settings = SandboxV2Settings(database_backend="postgres", postgres_dsn="")
        store, err = create_sandbox_v2_store(settings)
        assert store is None
        assert "POSTGRES_DSN" in err or "postgres" in err.lower()

    def test_redis_without_url_fails(self):
        settings = SandboxV2Settings(queue_backend="redis", redis_url="")
        queue, err = create_sandbox_v2_queue(settings)
        assert queue is None
        assert "REDIS_URL" in err or "redis" in err.lower()

    def test_minio_without_endpoint_fails(self):
        settings = SandboxV2Settings(
            object_storage_backend="minio",
            minio_endpoint="",
            minio_access_key="fake-key",
            minio_secret_key="fake-secret",
            minio_bucket="test",
        )
        store, err = create_sandbox_v2_artifact_store(settings)
        assert store is None or "minio" in err.lower()
        # 即使用 boto3 已安装，缺 endpoint 也应 fail
        assert "MINIO_ENDPOINT" in err or "minio" in err.lower() or err != ""

    def test_minio_without_access_key_fails(self):
        settings = SandboxV2Settings(
            object_storage_backend="minio",
            minio_endpoint="http://localhost:9000",
            minio_access_key="",
            minio_secret_key="",
            minio_bucket="test",
        )
        store, err = create_sandbox_v2_artifact_store(settings)
        assert store is None or "access key" in err.lower() or "Access key" in err

    def test_unknown_database_backend_fails(self):
        settings = SandboxV2Settings(database_backend="mongodb")
        store, err = create_sandbox_v2_store(settings)
        assert store is None
        assert "Unknown" in err or "mongodb" in err.lower()

    def test_unknown_queue_backend_fails(self):
        settings = SandboxV2Settings(queue_backend="kafka")
        queue, err = create_sandbox_v2_queue(settings)
        assert queue is None
        assert "Unknown" in err or "kafka" in err.lower()

    def test_celery_queue_is_unsupported(self):
        settings = SandboxV2Settings(queue_backend="celery", redis_url="redis://localhost:6379/0")
        queue, err = create_sandbox_v2_queue(settings)
        assert queue is None
        assert "celery" in err.lower() or "not yet implemented" in err.lower()


class TestBackendReadiness:
    """get_backend_readiness() 返回正确状态。"""

    def test_default_readiness_all_ready(self):
        settings = SandboxV2Settings()
        status = get_backend_readiness(settings)
        assert status["database_backend"] == "sqlite"
        assert status["database_backend_ready"] is True
        assert status["queue_backend"] == "sqlite"
        assert status["queue_backend_ready"] is True
        assert status["object_storage_backend"] == "local"
        assert status["object_storage_ready"] is True
        assert status["local_fallback_enabled"] is True
        assert status["production_backend_configured"] is False

    def test_readiness_production_configured(self):
        settings = SandboxV2Settings(database_backend="postgres", postgres_dsn="postgresql://localhost/test")
        status = get_backend_readiness(settings)
        assert status["production_backend_configured"] is True
        assert status["postgres_dsn_configured"] is True

    def test_readiness_has_backend_warnings(self):
        settings = SandboxV2Settings()
        status = get_backend_readiness(settings)
        assert isinstance(status["backend_warnings"], list)
        # SQLite default should produce some warnings
        assert len(status["backend_warnings"]) >= 1

    def test_postgres_without_dsn_has_blocker(self):
        settings = SandboxV2Settings(database_backend="postgres", postgres_dsn="")
        status = get_backend_readiness(settings)
        assert len(status["backend_blockers"]) >= 1
        assert any("POSTGRES" in b.upper() or "postgres" in b.lower() for b in status["backend_blockers"])

    def test_redis_without_url_has_blocker(self):
        settings = SandboxV2Settings(queue_backend="redis", redis_url="")
        status = get_backend_readiness(settings)
        assert len(status["backend_blockers"]) >= 1
        assert any("REDIS" in b.upper() or "redis" in b.lower() for b in status["backend_blockers"])

    def test_minio_without_config_has_blocker(self):
        settings = SandboxV2Settings(
            object_storage_backend="minio",
            minio_endpoint="",
            minio_access_key="",
            minio_secret_key="",
            minio_bucket="",
        )
        status = get_backend_readiness(settings)
        assert len(status["backend_blockers"]) >= 1

    def test_no_backend_blockers_when_default(self):
        settings = SandboxV2Settings()
        status = get_backend_readiness(settings)
        assert status["backend_blockers"] == []
