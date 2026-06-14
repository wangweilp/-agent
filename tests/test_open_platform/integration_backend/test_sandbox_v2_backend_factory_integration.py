"""Backend factory integration tests (Step 13). Default SKIP.

Only run when SANDBOX_V2_RUN_BACKEND_INTEGRATION=true.
"""

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_RUNNING = os.environ.get("SANDBOX_V2_RUN_BACKEND_INTEGRATION", "").lower() in ("true", "1", "yes")

pytestmark = pytest.mark.skipif(
    not _RUNNING,
    reason="Requires SANDBOX_V2_RUN_BACKEND_INTEGRATION=true",
)


class TestBackendFactoryIntegration:
    """通过 backend_factory 创建 adapter 并验证 readiness。"""

    def test_factory_readiness_default(self):
        """默认 SQLite/local 始终就绪。"""
        from src.open_platform.sandbox_v2.config import SandboxV2Settings
        from src.open_platform.sandbox_v2.backend_factory import get_backend_readiness
        settings = SandboxV2Settings()
        status = get_backend_readiness(settings)
        assert status["database_backend"] == "sqlite"
        assert status["queue_backend"] == "sqlite"
        assert status["object_storage_backend"] == "local"
        assert status["local_fallback_enabled"] is True

    def test_postgres_store_creation(self):
        """PostgreSQL DSN 配置时 factory 返回 adapter。"""
        dsn = os.environ.get("SANDBOX_V2_POSTGRES_DSN", "")
        if not dsn:
            pytest.skip("No PostgreSQL DSN configured")
        from src.open_platform.sandbox_v2.config import SandboxV2Settings
        from src.open_platform.sandbox_v2.backend_factory import create_sandbox_v2_store
        settings = SandboxV2Settings(database_backend="postgres", postgres_dsn=dsn)
        store, err = create_sandbox_v2_store(settings)
        assert store is not None, f"Store creation failed: {err}"

    def test_redis_queue_creation(self):
        """Redis URL 配置时 factory 返回 adapter。"""
        redis_url = os.environ.get("SANDBOX_V2_REDIS_URL", "")
        if not redis_url:
            pytest.skip("No Redis URL configured")
        from src.open_platform.sandbox_v2.config import SandboxV2Settings
        from src.open_platform.sandbox_v2.backend_factory import create_sandbox_v2_queue
        settings = SandboxV2Settings(queue_backend="redis", redis_url=redis_url)
        queue, err = create_sandbox_v2_queue(settings)
        assert queue is not None, f"Queue creation failed: {err}"

    def test_standalone_readiness_has_no_blockers_when_default(self):
        """默认配置无 backend blockers。"""
        from src.open_platform.sandbox_v2.config import SandboxV2Settings
        from src.open_platform.sandbox_v2.backend_factory import get_backend_readiness
        settings = SandboxV2Settings()
        status = get_backend_readiness(settings)
        assert status["backend_blockers"] == []
