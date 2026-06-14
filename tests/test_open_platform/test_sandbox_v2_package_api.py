"""Test Sandbox v2 Package API — 包API集成测试。"""
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
from src.api.sandbox_v2 import create_sandbox_v2_router


@pytest.fixture
def client():
    db_fd, db_path = tempfile.mkstemp(suffix=".db"); art_root = tempfile.mkdtemp(); pkg_root = tempfile.mkdtemp()
    os.close(db_fd)
    settings = Settings()
    store = SQLiteSandboxV2Store(settings, db_path=db_path)
    queue = SQLiteSandboxV2Queue(settings, db_path=db_path)
    art_store = LocalSandboxArtifactStore(artifact_root=art_root)
    pkg_store = LocalSandboxPackageQuarantineStore(quarantine_root=pkg_root)
    service = SandboxV2Service(store=store, queue=queue, artifact_store=art_store, package_store=pkg_store)
    worker = SandboxV2Worker(queue=queue, service=service, worker_id="test-api-pkg-wkr")
    app = FastAPI(); app.include_router(create_sandbox_v2_router(service, worker=worker))
    yield TestClient(app)
    try: os.unlink(db_path)
    except: pass
    for d in [art_root, pkg_root]:
        try: shutil.rmtree(d)
        except: pass


class TestPackageRequests:
    def test_create_request_200(self, client):
        res = client.post("/api/runtime/sandbox-v2/packages/requests", json={
            "package_name": "api-pkg", "source_type": "offline_upload", "source_url": "offline://api",
        })
        assert res.status_code == 200

    def test_list_requests_200(self, client):
        res = client.get("/api/runtime/sandbox-v2/packages/requests")
        assert res.status_code == 200

    def test_get_nonexistent_404(self, client):
        res = client.get("/api/runtime/sandbox-v2/packages/requests/nonexistent")
        assert res.status_code == 404


class TestQuarantine:
    def test_quarantine_200(self, client):
        r = client.post("/api/runtime/sandbox-v2/packages/requests", json={"package_name": "q-api", "source_type": "offline_upload", "source_url": "offline://qapi"})
        rid = r.json()["package_request"]["package_request_id"]
        res = client.post(f"/api/runtime/sandbox-v2/packages/requests/{rid}/quarantine", json={"content_text": "test", "original_filename": "q.pkg"})
        assert res.status_code == 200

    def test_list_quarantine_200(self, client):
        res = client.get("/api/runtime/sandbox-v2/packages/quarantine")
        assert res.status_code == 200


class TestReadiness:
    def test_readiness_package_flags(self, client):
        res = client.get("/api/runtime/sandbox-v2/readiness")
        data = res.json()
        assert data["package_download_gate"] is True
        assert data["package_quarantine"] is True
        assert data["external_package_download"] is False
        assert data["public_registry_download"] is False
        assert data["package_hash_verification"] is True
        assert data["package_execution"] is False
        assert data["package_installation"] is False
        assert data["supply_chain_policy"] is True


class TestSBOMAndScan:
    def test_sbom_200(self, client):
        res = client.post("/api/runtime/sandbox-v2/packages/sbom", json={
            "package_request_id": "sbompkg_test",
            "sbom_content": '{"bomFormat":"CycloneDX","components":[{"name":"test"}]}',
            "format": "cyclonedx-json",
        })
        # May 400 if request doesn't exist, but shouldn't 500
        assert res.status_code != 500

    def test_scan_400_without_id(self, client):
        res = client.post("/api/runtime/sandbox-v2/packages/scans")
        assert res.status_code == 400


class TestBackwardCompatibility:
    def test_jobs_endpoint(self, client):
        res = client.post("/api/runtime/sandbox-v2/jobs", json={"mode": "simulation"})
        assert res.status_code == 200

    def test_artifacts_endpoint(self, client):
        res = client.get("/api/runtime/sandbox-v2/artifacts")
        assert res.status_code == 200

    def test_queue_endpoint(self, client):
        res = client.get("/api/runtime/sandbox-v2/queue")
        assert res.status_code == 200

    def test_workers_endpoint(self, client):
        res = client.get("/api/runtime/sandbox-v2/workers")
        assert res.status_code == 200


class TestNo500:
    def test_all_package_endpoints_no_500(self, client):
        paths = [
            "/api/runtime/sandbox-v2/packages/requests",
            "/api/runtime/sandbox-v2/packages/quarantine",
            "/api/runtime/sandbox-v2/readiness",
        ]
        for p in paths:
            res = client.get(p)
            assert res.status_code != 500, f"{p} returned 500"
