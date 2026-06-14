"""Test Step 7 — Kill Switch API 测试。"""
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
from src.open_platform.sandbox_v2.kill_switch import SandboxKillSwitchService
from src.open_platform.sandbox_v2.models import SandboxJob, SandboxV2JobStatus, SandboxV2Mode
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
    ks = SandboxKillSwitchService(store=store, queue=queue, execution_providers=providers)
    svc = SandboxV2Service(store=store, queue=queue, artifact_store=art, package_store=pkg, network_service=ns, execution_providers=providers, kill_switch=ks)
    w = SandboxV2Worker(queue=queue, service=svc, worker_id="api-kill-wkr")
    app = FastAPI(); app.include_router(create_sandbox_v2_router(svc, worker=w))
    yield TestClient(app)
    try: os.unlink(db_path)
    except: pass
    for d in [art_root, pkg_root]:
        try: shutil.rmtree(d)
        except: pass


class TestKillJob:
    def test_kill_job_200(self, client):
        # Create a job first
        job = SandboxJob(job_id="sbxjob_kapi", status=SandboxV2JobStatus.QUEUED, mode=SandboxV2Mode.SIMULATION)
        # Use the raw store to create it
        res = client.post("/api/runtime/sandbox-v2/kill/job/sbxjob_kapi")
        assert res.status_code == 200

    def test_kill_job_returns_response(self, client):
        res = client.post("/api/runtime/sandbox-v2/kill/job/test-job-kr")
        data = res.json()
        assert "kill_request" in data or "canceled" in data


class TestKillRequestsList:
    def test_list_200(self, client):
        res = client.get("/api/runtime/sandbox-v2/kill/requests")
        assert res.status_code == 200


class TestKillRecords:
    def test_list_200(self, client):
        res = client.get("/api/runtime/sandbox-v2/kill/records")
        assert res.status_code == 200


class TestActiveHandles:
    def test_list_200(self, client):
        res = client.get("/api/runtime/sandbox-v2/kill/active-handles")
        assert res.status_code == 200


class TestKillReadiness:
    def test_readiness_200(self, client):
        res = client.get("/api/runtime/sandbox-v2/kill/readiness")
        assert res.status_code == 200
        data = res.json()
        assert data["kill_switch"] is True
        assert data["process_kill_implemented"] is False
        assert data["arbitrary_pid_kill"] is False


class TestCancelJobCompatibility:
    def test_cancel_job_api_still_works(self, client):
        res = client.post("/api/runtime/sandbox-v2/jobs/nonexistent-cancel-test/cancel")
        assert res.status_code != 500


class TestGlobalReadinessKillFields:
    def test_readiness_has_kill_fields(self, client):
        res = client.get("/api/runtime/sandbox-v2/readiness")
        data = res.json()
        assert data["kill_switch"] is True
        assert data["kill_policy"] is True
        assert data["active_execution_handles"] is True
        assert data["process_kill_implemented"] is False
        assert data["arbitrary_pid_kill"] is False


class TestBackwardCompat:
    def test_jobs(self, client):
        assert client.post("/api/runtime/sandbox-v2/jobs", json={"mode": "simulation"}).status_code == 200
    def test_queue(self, client):
        assert client.get("/api/runtime/sandbox-v2/queue").status_code == 200
    def test_isolation(self, client):
        assert client.get("/api/runtime/sandbox-v2/isolation/capabilities").status_code == 200


class TestNo500:
    def test_all_kill_endpoints_no_500(self, client):
        paths = [
            "/api/runtime/sandbox-v2/kill/requests",
            "/api/runtime/sandbox-v2/kill/records",
            "/api/runtime/sandbox-v2/kill/active-handles",
            "/api/runtime/sandbox-v2/kill/readiness",
        ]
        for p in paths:
            res = client.get(p)
            assert res.status_code != 500, f"{p} returned 500"
