"""Test Step 6B — Container API 集成测试。"""
import os, pytest, tempfile, shutil
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
from src.open_platform.sandbox_v2.service import SandboxV2Service
from src.open_platform.sandbox_v2.worker import SandboxV2Worker
from src.open_platform.sandbox_v2.artifacts import LocalSandboxArtifactStore
from src.open_platform.sandbox_v2.packages import LocalSandboxPackageQuarantineStore
from src.open_platform.sandbox_v2.network import SandboxNetworkEgressService
from src.open_platform.sandbox_v2.execution_provider import create_default_provider_registry
from src.open_platform.sandbox_v2.container_provider import RootlessContainerExecutionProvider
from src.open_platform.sandbox_v2.models import (
    SandboxV2IsolationProvider, SandboxV2ContainerRuntime,
    SandboxContainerRuntimeConfig,
)
from src.api.sandbox_v2 import create_sandbox_v2_router


@pytest.fixture
def client():
    db_fd, db_path = tempfile.mkstemp(suffix=".db"); art_root = tempfile.mkdtemp(); pkg_root = tempfile.mkdtemp()
    os.close(db_fd)
    settings = Settings()
    store = SQLiteSandboxV2Store(settings, db_path=db_path)
    queue = SQLiteSandboxV2Queue(settings, db_path=db_path)
    art = LocalSandboxArtifactStore(artifact_root=art_root)
    pkg = LocalSandboxPackageQuarantineStore(quarantine_root=pkg_root)
    ns = SandboxNetworkEgressService(store=store)
    providers = create_default_provider_registry()
    providers[SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE] = RootlessContainerExecutionProvider(
        SandboxContainerRuntimeConfig(provider=SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE, runtime=SandboxV2ContainerRuntime.UNAVAILABLE, enabled=False))
    svc = SandboxV2Service(store=store, queue=queue, artifact_store=art, package_store=pkg, network_service=ns, execution_providers=providers)
    w = SandboxV2Worker(queue=queue, service=svc, worker_id="api-cnt-wkr")
    app = FastAPI(); app.include_router(create_sandbox_v2_router(svc, worker=w))
    yield TestClient(app)
    try: os.unlink(db_path)
    except: pass
    for d in [art_root, pkg_root]:
        try: shutil.rmtree(d)
        except: pass


class TestContainerPlans:
    def test_create_plan_200(self, client):
        res = client.post("/api/runtime/sandbox-v2/isolation/container-plans", json={
            "provider": "docker_rootless_future", "fixture_id": "hello-container-fixture",
        })
        assert res.status_code == 200

    def test_list_plans_200(self, client):
        res = client.get("/api/runtime/sandbox-v2/isolation/container-plans")
        assert res.status_code == 200

    def test_get_nonexistent_404(self, client):
        res = client.get("/api/runtime/sandbox-v2/isolation/container-plans/nonexistent")
        assert res.status_code == 404


class TestContainerRun:
    def test_run_disabled_no_500(self, client):
        r = client.post("/api/runtime/sandbox-v2/isolation/container-plans", json={
            "provider": "docker_rootless_future", "fixture_id": "hello-container-fixture",
        })
        cpid = r.json()["container_plan"]["container_plan_id"]
        res = client.post(f"/api/runtime/sandbox-v2/isolation/container-plans/{cpid}/run-trusted-fixture")
        assert res.status_code == 200  # Should not 500 even if disabled


class TestContainerResults:
    def test_list_results_200(self, client):
        res = client.get("/api/runtime/sandbox-v2/isolation/container-results")
        assert res.status_code == 200


class TestReadinessContainerFields:
    def test_readiness_has_container_fields(self, client):
        res = client.get("/api/runtime/sandbox-v2/readiness")
        data = res.json()
        assert "container_provider_abstraction" in data
        assert "rootless_container_poc" in data
        assert "container_execution_enabled" in data
        assert data["trusted_container_fixture_only"] is True
        assert data["arbitrary_container_command"] is False
        assert data["arbitrary_container_image"] is False
        assert data["container_network_disabled"] is True
        assert data["container_readonly_rootfs_required"] is True
        assert data["container_cap_drop_all_required"] is True
        assert data["container_no_new_privileges_required"] is True


class TestBackwardCompat:
    def test_jobs(self, client):
        assert client.post("/api/runtime/sandbox-v2/jobs", json={"mode": "simulation"}).status_code == 200
    def test_queue(self, client):
        assert client.get("/api/runtime/sandbox-v2/queue").status_code == 200
    def test_isolation_caps(self, client):
        assert client.get("/api/runtime/sandbox-v2/isolation/capabilities").status_code == 200
    def test_network(self, client):
        assert client.get("/api/runtime/sandbox-v2/network/readiness").status_code == 200


class TestNo500:
    def test_all_container_endpoints_no_500(self, client):
        paths = [
            "/api/runtime/sandbox-v2/isolation/container-plans",
            "/api/runtime/sandbox-v2/isolation/container-results",
            "/api/runtime/sandbox-v2/readiness",
        ]
        for p in paths:
            res = client.get(p)
            assert res.status_code != 500, f"{p} returned 500"
