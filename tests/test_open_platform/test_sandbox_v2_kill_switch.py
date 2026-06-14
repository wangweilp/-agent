"""Test Step 7 — Kill Switch Service 测试。"""
import pytest, tempfile, os, shutil
from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
from src.open_platform.sandbox_v2.kill_switch import SandboxKillSwitchService
from src.open_platform.sandbox_v2.execution_provider import create_default_provider_registry
from src.open_platform.sandbox_v2.models import (
    SandboxJob, SandboxV2JobStatus, SandboxV2Mode,
    SandboxV2KillTargetType, SandboxV2KillRequestStatus,
    SandboxV2ActiveExecutionStatus,
)


@pytest.fixture
def ks():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    settings = Settings()
    store = SQLiteSandboxV2Store(settings, db_path=db_path)
    queue = SQLiteSandboxV2Queue(settings, db_path=db_path)
    providers = create_default_provider_registry()
    k = SandboxKillSwitchService(store=store, queue=queue, execution_providers=providers)
    yield k
    try: os.unlink(db_path)
    except: pass


class TestKillJob:
    def test_kill_queued_job(self, ks):
        # Create job and enqueue
        job = SandboxJob(job_id="sbxjob_kq", status=SandboxV2JobStatus.QUEUED, mode=SandboxV2Mode.SIMULATION)
        ks._store.create_job(job)
        ks._queue.enqueue(job_id="sbxjob_kq")
        result = ks.request_kill(job_id="sbxjob_kq", target_type=SandboxV2KillTargetType.JOB)
        assert "kill_request" in result
        assert result["decision"]["allowed"] is True

    def test_kill_completed_job_no_active(self, ks):
        job = SandboxJob(job_id="sbxjob_kc", status=SandboxV2JobStatus.COMPLETED, mode=SandboxV2Mode.SIMULATION)
        ks._store.create_job(job)
        result = ks.request_kill(job_id="sbxjob_kc", target_type=SandboxV2KillTargetType.JOB)
        assert result["decision"]["action"] == "no_active_execution"

    def test_kill_record_created(self, ks):
        job = SandboxJob(job_id="sbxjob_kr", status=SandboxV2JobStatus.QUEUED, mode=SandboxV2Mode.SIMULATION)
        ks._store.create_job(job)
        ks._queue.enqueue(job_id="sbxjob_kr")
        result = ks.request_kill(job_id="sbxjob_kr", target_type=SandboxV2KillTargetType.JOB)
        records = ks.list_kill_records(job_id="sbxjob_kr")
        assert len(records) >= 1


class TestActiveExecutionHandle:
    def test_register_handle(self, ks):
        r = ks.register_active_execution_handle(job_id="sbxjob_h1", provider="trusted_fixture")
        assert r["handle"]["handle_id"].startswith("sbxhandle_")

    def test_get_handle_for_job(self, ks):
        ks.register_active_execution_handle(job_id="sbxjob_h2", provider="simulation")
        h = ks.get_active_execution_handle_for_job("sbxjob_h2")
        assert h is not None
        assert h.status == SandboxV2ActiveExecutionStatus.ACTIVE

    def test_mark_completed(self, ks):
        r = ks.register_active_execution_handle(job_id="sbxjob_h3")
        hid = r["handle"]["handle_id"]
        ks.mark_active_execution_completed(hid, "done")
        h = ks.get_active_execution_handle(hid)
        assert h.status == SandboxV2ActiveExecutionStatus.COMPLETED

    def test_expire_stale(self, ks):
        from datetime import datetime, timedelta, timezone
        r = ks.register_active_execution_handle(job_id="sbxjob_h4", timeout_at=datetime.now(timezone.utc) - timedelta(hours=1))
        count = ks.expire_stale_handles()
        assert count >= 1


class TestKillReadiness:
    def test_readiness(self, ks):
        r = ks.get_kill_readiness()
        assert r["kill_switch"] is True
        assert r["kill_policy"] is True
        assert r["arbitrary_pid_kill"] is False
        assert r["process_kill_implemented"] is False
