"""Red-Team Worker/Queue Abuse Tests — Worker 和 Queue 滥用攻击测试。

验证：不允许重复 lease、expired lease 安全回收、超过 max_attempts 进 dead_letter、
canceled job 不继续 processing、future mode 不被 auto-execute、worker 不访问网络。
"""

import pytest, tempfile, os, shutil
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
from src.open_platform.sandbox_v2.models import (
    SandboxJob, SandboxV2JobStatus, SandboxV2Mode, SandboxV2QueueStatus,
)


@pytest.fixture
def worker():
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
    w = SandboxV2Worker(queue=queue, service=svc, worker_id="rt-wkr")
    yield w
    try: os.unlink(db_path)
    except: pass
    for d in [art_root, pkg_root]:
        try: shutil.rmtree(d)
        except: pass


class TestQueueSafety:
    def test_no_double_lease(self, worker):
        worker._queue.enqueue(job_id="sbxjob_rt_q1")
        item1 = worker._queue.lease_next("worker-A")
        item2 = worker._queue.lease_next("worker-B")
        # After first lease, second should get None or a different item
        assert item2 is None or item2.job_id != "sbxjob_rt_q1"

    def test_expired_lease_requeue(self, worker):
        worker._queue.enqueue(job_id="sbxjob_rt_q2")
        item = worker._queue.lease_next("worker-A", lease_seconds=1)
        assert item is not None
        from datetime import datetime, timedelta, timezone
        future = datetime.now(timezone.utc) + timedelta(seconds=120)
        count = worker._queue.requeue_expired_leases(now=future)
        assert count >= 1

    def test_max_attempts_dead_letter(self, worker):
        worker._queue.enqueue(job_id="sbxjob_rt_q3", max_attempts=1)
        item = worker._queue.lease_next("worker-A")
        result = worker._queue.fail(item.queue_id, reason="test", retry=True)
        assert result.status == SandboxV2QueueStatus.DEAD_LETTER

    def test_canceled_job_not_processing(self, worker):
        job = SandboxJob(job_id="sbxjob_rt_q4", status=SandboxV2JobStatus.QUEUED, mode=SandboxV2Mode.SIMULATION, requested_action="dry_run")
        worker._service._store.create_job(job)
        worker._queue.enqueue(job_id="sbxjob_rt_q4")
        worker._queue.cancel("sbxjob_rt_q4", "test cancel")
        result = worker.run_once()
        # Should skip canceled item (returns None since no un-canceled queued items)
        assert result is None or result.status == SandboxV2JobStatus.CANCELED

    def test_dead_letter_not_re_executed(self, worker):
        worker._queue.enqueue(job_id="sbxjob_rt_q5", max_attempts=1)
        item = worker._queue.lease_next("worker-A")
        worker._queue.fail(item.queue_id, reason="fatal", retry=True)
        result = worker.run_once()
        assert result is None  # dead_letter items not re-processed


class TestFutureModeRejection:
    def test_future_container_not_auto_executed(self, worker):
        job = SandboxJob(job_id="sbxjob_rt_fc", status=SandboxV2JobStatus.QUEUED, mode=SandboxV2Mode.FUTURE_CONTAINER)
        worker._service._store.create_job(job)
        worker._queue.enqueue(job_id="sbxjob_rt_fc")
        result = worker.run_once()
        assert result is not None
        assert result.status == SandboxV2JobStatus.FAILED

    def test_future_microvm_not_auto_executed(self, worker):
        job = SandboxJob(job_id="sbxjob_rt_fmv", status=SandboxV2JobStatus.QUEUED, mode=SandboxV2Mode.FUTURE_MICROVM)
        worker._service._store.create_job(job)
        worker._queue.enqueue(job_id="sbxjob_rt_fmv")
        result = worker.run_once()
        assert result.status == SandboxV2JobStatus.FAILED


class TestWorkerSafety:
    def test_worker_no_subprocess(self):
        import src.open_platform.sandbox_v2.worker as wm
        assert "subprocess" not in wm.__dict__

    def test_worker_no_network(self):
        import src.open_platform.sandbox_v2.worker as wm
        for bad in ("urllib", "requests", "socket"):
            assert bad not in wm.__dict__

    def test_worker_run_once_no_user_code(self, worker):
        job = SandboxJob(job_id="sbxjob_rt_nouser", status=SandboxV2JobStatus.QUEUED,
                         mode=SandboxV2Mode.SIMULATION, requested_action="dry_run")
        worker._service._store.create_job(job)
        worker._queue.enqueue(job_id="sbxjob_rt_nouser")
        result = worker.run_once()
        assert result is not None
