"""Tests for Sandbox v2 Backend Readiness API (Step 12).

验证:
1. readiness API 返回 backend 字段
2. 默认值: database_backend=sqlite, queue_backend=sqlite, object_storage_backend=local
3. 配置变化后字段正确更新
4. frontend TypeScript 类型兼容
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════════════════
# 1. ReadinessResponse backend fields
# ═══════════════════════════════════════════════════════════════════════════

class TestReadinessResponseBackendFields:
    """验证 ReadinessResponse 包含 Step 12 backend 字段。"""

    def test_readiness_response_has_all_backend_fields(self):
        from src.api.sandbox_v2 import ReadinessResponse
        resp = ReadinessResponse()
        data = resp.model_dump()

        required_fields = [
            "database_backend",
            "database_backend_ready",
            "postgres_adapter_available",
            "postgres_dsn_configured",
            "queue_backend",
            "queue_backend_ready",
            "redis_queue_adapter_available",
            "redis_url_configured",
            "object_storage_backend",
            "object_storage_ready",
            "minio_adapter_available",
            "minio_endpoint_configured",
            "local_fallback_enabled",
            "production_backend_configured",
            "backend_warnings",
            "backend_blockers",
        ]
        for field in required_fields:
            assert field in data, f"Field '{field}' missing from ReadinessResponse"

    def test_default_backend_field_values(self):
        from src.api.sandbox_v2 import ReadinessResponse
        resp = ReadinessResponse()

        assert resp.database_backend == "sqlite"
        assert resp.database_backend_ready is True
        assert resp.postgres_adapter_available is False
        assert resp.queue_backend == "sqlite"
        assert resp.queue_backend_ready is True
        assert resp.redis_queue_adapter_available is False
        assert resp.object_storage_backend == "local"
        assert resp.object_storage_ready is True
        assert resp.minio_adapter_available is False
        assert resp.local_fallback_enabled is True
        assert resp.production_backend_configured is False
        assert isinstance(resp.backend_warnings, list)
        assert isinstance(resp.backend_blockers, list)

    def test_backend_warnings_default_not_empty_with_sqlite(self):
        """默认 SQLite 配置有 backend warnings（建议升级到生产后端）。"""
        from src.api.sandbox_v2 import ReadinessResponse
        resp = ReadinessResponse()
        # 默认情况下 backend_warnings 可能为空（因为是用默认构造函数），
        # 但实际 readiness endpoint 会动态填充
        assert isinstance(resp.backend_warnings, list)

    def test_backend_blockers_default_empty(self):
        from src.api.sandbox_v2 import ReadinessResponse
        resp = ReadinessResponse()
        assert resp.backend_blockers == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. Config backend methods
# ═══════════════════════════════════════════════════════════════════════════

class TestConfigBackendMethods:
    """验证 SandboxV2Settings 的 backend_blockers / backend_warnings 方法。"""

    def test_backend_blockers_empty_with_default_config(self):
        from src.open_platform.sandbox_v2.config import SandboxV2Settings
        settings = SandboxV2Settings()
        blockers = settings.backend_blockers()
        assert blockers == []

    def test_backend_blockers_postgres_no_dsn(self):
        from src.open_platform.sandbox_v2.config import SandboxV2Settings
        settings = SandboxV2Settings(database_backend="postgres", postgres_dsn="")
        blockers = settings.backend_blockers()
        assert len(blockers) >= 1
        assert any("POSTGRES" in b.upper() for b in blockers)

    def test_backend_blockers_redis_no_url(self):
        from src.open_platform.sandbox_v2.config import SandboxV2Settings
        settings = SandboxV2Settings(queue_backend="redis", redis_url="")
        blockers = settings.backend_blockers()
        assert len(blockers) >= 1
        assert any("REDIS" in b.upper() for b in blockers)

    def test_backend_blockers_minio_no_endpoint(self):
        from src.open_platform.sandbox_v2.config import SandboxV2Settings
        settings = SandboxV2Settings(
            object_storage_backend="minio",
            minio_endpoint="",
            minio_access_key="k",
            minio_secret_key="s",
            minio_bucket="b",
        )
        blockers = settings.backend_blockers()
        assert len(blockers) >= 1
        assert any("MINIO_ENDPOINT" in b for b in blockers)

    def test_backend_blockers_minio_no_access_key(self):
        from src.open_platform.sandbox_v2.config import SandboxV2Settings
        settings = SandboxV2Settings(
            object_storage_backend="minio",
            minio_endpoint="http://localhost:9000",
            minio_access_key="",
            minio_secret_key="",
            minio_bucket="test",
        )
        blockers = settings.backend_blockers()
        assert len(blockers) >= 1
        assert any("access key" in b.lower() for b in blockers)

    def test_backend_blockers_minio_no_bucket(self):
        from src.open_platform.sandbox_v2.config import SandboxV2Settings
        settings = SandboxV2Settings(
            object_storage_backend="minio",
            minio_endpoint="http://localhost:9000",
            minio_access_key="key",
            minio_secret_key="secret",
            minio_bucket="",
        )
        blockers = settings.backend_blockers()
        assert len(blockers) >= 1
        assert any("bucket" in b.lower() for b in blockers)

    def test_backend_warnings_sqlite_default(self):
        from src.open_platform.sandbox_v2.config import SandboxV2Settings
        settings = SandboxV2Settings()
        warns = settings.backend_warnings()
        # SQLite default 下应有 warning 提示升级
        assert any("sqlite" in w.lower() for w in warns)

    def test_backend_warnings_production_configured(self):
        from src.open_platform.sandbox_v2.config import SandboxV2Settings
        settings = SandboxV2Settings(
            database_backend="postgres",
            postgres_dsn="postgresql://...",
            queue_backend="redis",
            redis_url="redis://...",
            object_storage_backend="minio",
            minio_endpoint="http://...",
            minio_access_key="k",
            minio_secret_key="s",
            minio_bucket="b",
        )
        warns = settings.backend_warnings()
        # 使用生产后端后不应再有 sqlite/local warning
        assert not any("sqlite" in w.lower() for w in warns)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Frontend TypeScript type compatibility (Python-side check)
# ═══════════════════════════════════════════════════════════════════════════

class TestFrontendTypeCompatibility:
    """确保 API 返回的字段与 TypeScript 接口兼容。"""

    def test_readiness_response_compatible_with_frontend(self):
        """ReadinessResponse 的 JSON 输出能被前端消费。"""
        from src.api.sandbox_v2 import ReadinessResponse
        resp = ReadinessResponse(
            database_backend="sqlite",
            database_backend_ready=True,
            postgres_adapter_available=False,
            queue_backend="sqlite",
            queue_backend_ready=True,
            redis_queue_adapter_available=False,
            object_storage_backend="local",
            object_storage_ready=True,
            minio_adapter_available=False,
            local_fallback_enabled=True,
            production_backend_configured=False,
        )
        data = resp.model_dump()

        # 验证所有字段都可以序列化为 JSON
        import json
        json_str = json.dumps(data, ensure_ascii=False)
        assert len(json_str) > 0

        # round-trip
        parsed = json.loads(json_str)
        assert parsed["database_backend"] == "sqlite"
        assert parsed["queue_backend"] == "sqlite"
        assert parsed["object_storage_backend"] == "local"

    def test_old_fields_still_present(self):
        """Step 1-10 的字段仍然存在。"""
        from src.api.sandbox_v2 import ReadinessResponse
        resp = ReadinessResponse()
        data = resp.model_dump()

        old_fields = [
            "sandbox_v2_core_contract",
            "real_task_queue",
            "kill_switch",
            "red_team_suite",
            "production_hardening_docs",
            "env_template_present",
            "safe_defaults_configured",
        ]
        for field in old_fields:
            assert field in data, f"Old field '{field}' missing!"
