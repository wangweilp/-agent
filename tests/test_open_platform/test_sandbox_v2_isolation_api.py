"""Test Step 6A — Isolation API 集成测试。"""
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
    svc = SandboxV2Service(store=store, queue=queue, artifact_store=art, package_store=pkg, network_service=ns, execution_providers=providers)
    w = SandboxV2Worker(queue=queue, service=svc, worker_id="api-iso-wkr")
    app = FastAPI(); app.include_router(create_sandbox_v2_router(svc, worker=w))
    yield TestClient(app)
    try: os.unlink(db_path)
    except: pass
    for d in [art_root, pkg_root]:
        try: shutil.rmtree(d)
        except: pass


class TestCapabilities:
    def test_capabilities_200(self, client):
        res = client.get("/api/runtime/sandbox-v2/isolation/capabilities")
        assert res.status_code == 200
        data = res.json()
        assert data["untrusted_code_execution"] is False

    def test_readiness_200(self, client):
        res = client.get("/api/runtime/sandbox-v2/isolation/readiness")
        assert res.status_code == 200


class TestExecutionPlan:
    def test_create_plan_200(self, client):
        res = client.post("/api/runtime/sandbox-v2/isolation/execution-plans", json={
            "provider": "trusted_fixture", "command_ref": "echo_hello",
            "resource_limits": {"max_mb": 256},
        })
        assert res.status_code == 200

    def test_list_plans_200(self, client):
        res = client.get("/api/runtime/sandbox-v2/isolation/execution-plans")
        assert res.status_code == 200

    def test_get_nonexistent_404(self, client):
        res = client.get("/api/runtime/sandbox-v2/isolation/execution-plans/nonexistent")
        assert res.status_code == 404

    def test_run_fixture_200(self, client):
        create_res = client.post("/api/runtime/sandbox-v2/isolation/execution-plans", json={
            "provider": "trusted_fixture", "command_ref": "echo_hello",
            "resource_limits": {"max_mb": 256},
        })
        plan_id = create_res.json()["execution_plan"]["execution_plan_id"]
        res = client.post(f"/api/runtime/sandbox-v2/isolation/execution-plans/{plan_id}/run-trusted-fixture")
        assert res.status_code == 200
        data = res.json()
        assert data["executed"] is True

    def test_cancel_plan_200(self, client):
        create_res = client.post("/api/runtime/sandbox-v2/isolation/execution-plans", json={
            "provider": "trusted_fixture", "command_ref": "echo_hello",
            "resource_limits": {"max_mb": 256},
        })
        plan_id = create_res.json()["execution_plan"]["execution_plan_id"]
        res = client.post(f"/api/runtime/sandbox-v2/isolation/execution-plans/{plan_id}/cancel")
        assert res.status_code == 200


class TestReadiness:
    def test_readiness_isolation_fields(self, client):
        res = client.get("/api/runtime/sandbox-v2/readiness")
        data = res.json()
        assert data["isolation_capability_probe"] is True
        assert data["execution_provider_abstraction"] is True
        assert data["trusted_fixture_provider"] is True
        assert data["untrusted_code_execution"] is False
        assert data["docker_execution"] is False
        assert data["podman_execution"] is False
        assert data["microvm_execution"] is False


class TestBackwardCompat:
    def test_jobs(self, client):
        assert client.post("/api/runtime/sandbox-v2/jobs", json={"mode": "simulation"}).status_code == 200
    def test_queue(self, client):
        assert client.get("/api/runtime/sandbox-v2/queue").status_code == 200
    def test_artifacts(self, client):
        assert client.get("/api/runtime/sandbox-v2/artifacts").status_code == 200
    def test_packages(self, client):
        assert client.get("/api/runtime/sandbox-v2/packages/requests").status_code == 200
    def test_network(self, client):
        assert client.get("/api/runtime/sandbox-v2/network/readiness").status_code == 200


class TestNo500:
    def test_all_isolation_endpoints_no_500(self, client):
        paths = [
            "/api/runtime/sandbox-v2/isolation/capabilities",
            "/api/runtime/sandbox-v2/isolation/readiness",
            "/api/runtime/sandbox-v2/isolation/execution-plans",
        ]
        for p in paths:
            res = client.get(p)
            assert res.status_code != 500, f"{p} returned 500"
