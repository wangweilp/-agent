"""Test Step 6A — Isolation Service 测试。"""
import pytest, tempfile, os, shutil
from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
from src.open_platform.sandbox_v2.service import SandboxV2Service
from src.open_platform.sandbox_v2.artifacts import LocalSandboxArtifactStore
from src.open_platform.sandbox_v2.packages import LocalSandboxPackageQuarantineStore
from src.open_platform.sandbox_v2.network import SandboxNetworkEgressService
from src.open_platform.sandbox_v2.execution_provider import create_default_provider_registry


@pytest.fixture
def service():
    db_fd, db_path = tempfile.mkstemp(suffix=".db"); art_root = tempfile.mkdtemp(); pkg_root = tempfile.mkdtemp()
    os.close(db_fd)
    settings = Settings()
    store = SQLiteSandboxV2Store(settings, db_path=db_path)
    queue = SQLiteSandboxV2Queue(settings, db_path=db_path)
    art = LocalSandboxArtifactStore(artifact_root=art_root)
    pkg = LocalSandboxPackageQuarantineStore(quarantine_root=pkg_root)
    ns = SandboxNetworkEgressService(store=store)
    providers = create_default_provider_registry()
    svc = SandboxV2Service(store=store, queue=queue, artifact_store=art, package_store=pkg, network_service=ns, execution_providers=providers)
    yield svc
    try: os.unlink(db_path)
    except: pass
    for d in [art_root, pkg_root]:
        try: shutil.rmtree(d)
        except: pass


class TestIsolationCapabilities:
    def test_collect_capabilities(self, service):
        result = service.collect_isolation_capabilities()
        assert result["isolation_capability_probe"] is True

    def test_isolation_readiness(self, service):
        r = service.get_isolation_readiness()
        assert r["execution_provider_abstraction"] is True
        assert r["untrusted_code_execution"] is False


class TestExecutionPlan:
    def test_create_plan_trusted_fixture(self, service):
        result = service.create_execution_plan(
            provider="trusted_fixture", mode="simulation",
            command_ref="echo_hello", resource_limits={"max_mb": 256},
        )
        assert result["decision"]["allowed"] is True
        assert result["execution_plan"]["status"] != "rejected"

    def test_create_plan_docker_rootless_allowed(self, service):
        """Step 6B: docker_rootless_future 在严格条件下允许。"""
        result = service.create_execution_plan(
            provider="docker_rootless_future", resource_limits={"max_mb": 256},
        )
        assert result["decision"]["allowed"] is True

    def test_list_plans(self, service):
        service.create_execution_plan(provider="trusted_fixture", command_ref="echo_hello", resource_limits={"max_mb": 256})
        items = service.list_execution_plans()
        assert len(items) >= 1

    def test_run_trusted_fixture(self, service):
        result = service.create_execution_plan(
            provider="trusted_fixture", command_ref="echo_hello", resource_limits={"max_mb": 256},
        )
        plan_id = result["execution_plan"]["execution_plan_id"]
        fr = service.run_trusted_fixture_execution(plan_id)
        assert fr["executed"] is True
        assert "fixture_result" in fr
        assert fr["fixture_result"]["stdout_text"] != ""

    def test_cancel_plan(self, service):
        result = service.create_execution_plan(
            provider="trusted_fixture", command_ref="echo_hello", resource_limits={"max_mb": 256},
        )
        plan_id = result["execution_plan"]["execution_plan_id"]
        cancel = service.cancel_execution_plan(plan_id)
        assert cancel["canceled"] is True
        assert "no real process" in cancel["message"].lower()
