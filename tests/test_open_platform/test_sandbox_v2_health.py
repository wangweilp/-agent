"""Health Check Service tests (Step 15)."""
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest, platform
from src.open_platform.sandbox_v2.health import SandboxV2HealthService

class TestHealthChecks:
    def test_run_all_returns_results(self):
        from src.adapters.config import Settings; from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        store = SQLiteSandboxV2Store(config=Settings()); hs = SandboxV2HealthService(store=store)
        results = hs.run_all()
        assert len(results) > 0
    def test_core_component_present(self):
        hs = SandboxV2HealthService(); hs.check_core()
        assert len(hs._results) >= 1; assert hs._results[0].component == "core"
    def test_no_container_started(self):
        hs = SandboxV2HealthService(); hs.run_all()
        for r in hs._results:
            assert "started" not in r.reason.lower() or "container" not in r.reason.lower()
    def test_no_microvm_started(self):
        hs = SandboxV2HealthService(); hs.run_all()
        for r in hs._results:
            assert "started" not in r.reason.lower() or "microvm" not in r.reason.lower() or "firecracker" not in r.reason.lower()
    def test_windows_microvm_not_core_failure(self):
        hs = SandboxV2HealthService(); hs.check_microvm_provider()
        r = hs._results[-1]
        if platform.system() == "Windows":
            assert r.ready  # Not a core failure
    def test_safe_disabled_container_healthy(self):
        hs = SandboxV2HealthService(); hs.check_container_provider()
        r = hs._results[-1]; assert r.ready  # safe-disabled is healthy
    def test_health_results_persisted(self):
        from src.adapters.config import Settings; from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        store = SQLiteSandboxV2Store(config=Settings()); hs = SandboxV2HealthService(store=store)
        hs.check_core(); results = store.list_health_check_results(limit=10)
        assert len(results) >= 1
