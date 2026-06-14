"""Test Sandbox v2 Network Service — 网络出站服务测试。"""
import pytest, tempfile, os, shutil
from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
from src.open_platform.sandbox_v2.service import SandboxV2Service
from src.open_platform.sandbox_v2.worker import SandboxV2Worker
from src.open_platform.sandbox_v2.artifacts import LocalSandboxArtifactStore
from src.open_platform.sandbox_v2.packages import LocalSandboxPackageQuarantineStore
from src.open_platform.sandbox_v2.network import SandboxNetworkEgressService
from src.open_platform.sandbox_v2.models import (
    SandboxNetworkPolicyConfig, SandboxJob, SandboxV2Mode, SandboxV2JobStatus,
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
    svc = SandboxV2Service(store=store, queue=queue, artifact_store=art, package_store=pkg, network_service=ns)
    yield svc
    try: os.unlink(db_path)
    except: pass
    for d in [art_root, pkg_root]:
        try: shutil.rmtree(d)
        except: pass


class TestEgressRequest:
    def test_create_returns_result(self, service):
        result = service.request_network_egress(url="https://example.com", hostname="example.com")
        # Default SandboxNetworkPolicyConfig has allow_network=False → rejected
        assert "egress_request" in result
        assert "decision" in result

    def test_list_after_create(self, service):
        service.request_network_egress(url="https://example.com", hostname="example.com")
        items = service.list_network_egress_requests()
        assert len(items) >= 1

    def test_evaluate_preflight(self, service):
        result = service.evaluate_network_egress(url="https://example.com")
        assert "allowed" in result
        assert result["preflight_only"] is True

    def test_readiness(self, service):
        r = service.get_network_egress_readiness()
        assert r["network_egress_policy"] is True
        assert r["external_network_access"] is False
        assert r["no_real_network"] is True
        assert r["private_network_blocking"] is True


class TestWorkerNetworkPreflight:
    def test_worker_network_preflight_no_error(self, service):
        worker = SandboxV2Worker(queue=service.queue, service=service, worker_id="net-wkr")
        job = SandboxJob(job_id="sbxjob_net", mode=SandboxV2Mode.SIMULATION,
                         status=SandboxV2JobStatus.QUEUED, requested_action="network_test")
        service._store.create_job(job)
        service._queue.enqueue(job_id="sbxjob_net")
        result = worker.run_once()
        assert result is not None
