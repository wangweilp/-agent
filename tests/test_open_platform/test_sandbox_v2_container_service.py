"""Test Step 6B — Container Service 测试。"""
import pytest, tempfile, os, shutil
from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
from src.open_platform.sandbox_v2.service import SandboxV2Service
from src.open_platform.sandbox_v2.artifacts import LocalSandboxArtifactStore
from src.open_platform.sandbox_v2.packages import LocalSandboxPackageQuarantineStore
from src.open_platform.sandbox_v2.network import SandboxNetworkEgressService
from src.open_platform.sandbox_v2.execution_provider import create_default_provider_registry
from src.open_platform.sandbox_v2.container_provider import RootlessContainerExecutionProvider
from src.open_platform.sandbox_v2.models import (
    SandboxV2IsolationProvider, SandboxV2ContainerRuntime,
    SandboxContainerRuntimeConfig,
)


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
    # Add container provider (disabled)
    providers[SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE] = RootlessContainerExecutionProvider(
        SandboxContainerRuntimeConfig(provider=SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE, runtime=SandboxV2ContainerRuntime.UNAVAILABLE, enabled=False))
    svc = SandboxV2Service(store=store, queue=queue, artifact_store=art, package_store=pkg, network_service=ns, execution_providers=providers)
    yield svc
    try: os.unlink(db_path)
    except: pass
    for d in [art_root, pkg_root]:
        try: shutil.rmtree(d)
        except: pass


class TestContainerPlan:
    def test_create_plan(self, service):
        r = service.create_container_execution_plan(
            provider=SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE,
            runtime=SandboxV2ContainerRuntime.UNAVAILABLE,
            fixture_id="hello-container-fixture",
        )
        assert r["container_plan"]["status"] == "created"

    def test_list_plans(self, service):
        service.create_container_execution_plan(provider=SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE, fixture_id="hello-container-fixture")
        items = service.list_container_execution_plans()
        assert len(items) >= 1

    def test_run_disabled_returns_not_executed(self, service):
        r = service.create_container_execution_plan(provider=SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE, fixture_id="hello-container-fixture")
        cpid = r["container_plan"]["container_plan_id"]
        result = service.run_container_trusted_fixture(cpid)
        # Should not 500; either rejected or unavailable
        assert result["executed"] is False or "decision" in result


class TestContainerResult:
    def test_list_results_empty(self, service):
        items = service.list_container_execution_results()
        assert isinstance(items, list)
