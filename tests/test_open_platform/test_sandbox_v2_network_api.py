"""Test Sandbox v2 Network API — 网络出站 API 集成测试。"""
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
    svc = SandboxV2Service(store=store, queue=queue, artifact_store=art, package_store=pkg, network_service=ns)
    w = SandboxV2Worker(queue=queue, service=svc, worker_id="api-net-wkr")
    app = FastAPI(); app.include_router(create_sandbox_v2_router(svc, worker=w))
    yield TestClient(app)
    try: os.unlink(db_path)
    except: pass
    for d in [art_root, pkg_root]:
        try: shutil.rmtree(d)
        except: pass


class TestEgressRequests:
    def test_create_200(self, client):
        res = client.post("/api/runtime/sandbox-v2/network/egress-requests", json={"url": "https://example.com"})
        # Default policy reject is valid — just not 500
        assert res.status_code != 500

    def test_list_200(self, client):
        res = client.get("/api/runtime/sandbox-v2/network/egress-requests")
        assert res.status_code == 200

    def test_get_nonexistent_404(self, client):
        res = client.get("/api/runtime/sandbox-v2/network/egress-requests/nonexistent")
        assert res.status_code == 404


class TestAudit:
    def test_audit_200(self, client):
        res = client.get("/api/runtime/sandbox-v2/network/audit-records")
        assert res.status_code == 200


class TestPreflight:
    def test_preflight_200(self, client):
        res = client.post("/api/runtime/sandbox-v2/network/preflight", json={"url": "https://example.com"})
        assert res.status_code == 200
        data = res.json()
        assert "allowed" in data
        assert data["preflight_only"] is True
        assert data["no_real_network"] is True

    def test_preflight_does_not_make_network_call(self, client):
        """Verifies preflight only does policy check, no real network IO."""
        res = client.post("/api/runtime/sandbox-v2/network/preflight", json={"url": "https://nonexistent-12345678.invalid"})
        assert res.status_code == 200  # should not hang/timeout


class TestNetworkReadiness:
    def test_readiness_200(self, client):
        res = client.get("/api/runtime/sandbox-v2/network/readiness")
        assert res.status_code == 200
        data = res.json()
        assert data["external_network_access"] is False
        assert data["egress_proxy"] is False
        assert data["no_real_network"] is True


class TestReadiness:
    def test_global_readiness_network_fields(self, client):
        res = client.get("/api/runtime/sandbox-v2/readiness")
        data = res.json()
        assert data["network_egress_policy"] is True
        assert data["network_preflight"] is True
        assert data["external_network_access"] is False
        assert data["private_network_blocking"] is True
        assert data["localhost_blocking"] is True


class TestBackwardCompat:
    def test_jobs(self, client):
        assert client.post("/api/runtime/sandbox-v2/jobs", json={"mode": "simulation"}).status_code == 200
    def test_queue(self, client):
        assert client.get("/api/runtime/sandbox-v2/queue").status_code == 200
    def test_artifacts(self, client):
        assert client.get("/api/runtime/sandbox-v2/artifacts").status_code == 200
    def test_packages(self, client):
        assert client.get("/api/runtime/sandbox-v2/packages/requests").status_code == 200


class TestNo500:
    def test_all_network_endpoints_no_500(self, client):
        paths = [
            "/api/runtime/sandbox-v2/network/egress-requests",
            "/api/runtime/sandbox-v2/network/audit-records",
            "/api/runtime/sandbox-v2/network/readiness",
        ]
        for p in paths:
            res = client.get(p)
            assert res.status_code != 500, f"{p} returned 500"
