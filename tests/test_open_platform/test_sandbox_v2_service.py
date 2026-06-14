"""Test Sandbox v2 Service — 服务层单元测试。

覆盖：
1. metadata_only job 可以生成 execution record
2. simulation job 可以生成 execution record
3. cancel job 不会假装杀进程
4. submit_job 策略检查
"""
import pytest
import tempfile
import os

from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.open_platform.sandbox_v2.service import SandboxV2Service
from src.open_platform.sandbox_v2.models import (
    SandboxV2JobStatus,
    SandboxV2Mode,
    SandboxV2Decision,
    SandboxJob,
)


@pytest.fixture
def service():
    """创建临时 SQLite store + service。"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    settings = Settings()
    store = SQLiteSandboxV2Store(settings, db_path=db_path)
    svc = SandboxV2Service(store=store)
    yield svc
    try:
        os.unlink(db_path)
    except Exception:
        pass


class TestSubmitJob:
    def test_submit_simulation_job_policy_blocked(self, service):
        """simulation job 默认策略 deny，应被 blocked。"""
        result = service.submit_job(
            mode=SandboxV2Mode.SIMULATION,
            requested_action="dry_run",
        )
        assert result["status"] == SandboxV2JobStatus.REJECTED
        assert result["decision"]["allowed"] is False

    def test_submit_invalid_mode_rejected(self, service):
        """非法 mode 直接被拒绝。"""
        result = service.submit_job(
            mode=SandboxV2Mode.FUTURE_CONTAINER,
        )
        assert result["status"] == SandboxV2JobStatus.REJECTED
        assert result["job_id"] is None

    def test_submit_disabled_mode(self, service):
        """disabled mode 返回被拒绝。"""
        result = service.submit_job(mode=SandboxV2Mode.DISABLED)
        assert result["status"] == SandboxV2JobStatus.REJECTED


class TestSimulation:
    def test_simulation_creates_execution_record(self, service):
        """simulation 模拟执行后生成 execution record。"""
        job_id = "sbxjob_sim_test"
        job = SandboxJob(
            job_id=job_id,
            mode=SandboxV2Mode.SIMULATION,
            status=SandboxV2JobStatus.POLICY_CHECKED,
            requested_action="dry_run",
        )
        service._store.create_job(job)

        result = service.run_simulation(job_id)
        assert result["status"] == SandboxV2JobStatus.COMPLETED
        assert result["execution_record"] is not None
        assert result["execution_record"]["no_real_execution"] is True

        # 验证有 execution record
        records = service.list_execution_records(job_id=job_id)
        assert len(records) >= 1
        assert records[0]["status"] == SandboxV2JobStatus.COMPLETED

    def test_metadata_only_creates_execution_record(self, service):
        """metadata_only job 可以生成 execution record。"""
        job_id = "sbxjob_meta_test"
        job = SandboxJob(
            job_id=job_id,
            mode=SandboxV2Mode.METADATA_ONLY,
            status=SandboxV2JobStatus.POLICY_CHECKED,
            requested_action="metadata_validate",
        )
        service._store.create_job(job)

        result = service.run_simulation(job_id)
        assert result["status"] == SandboxV2JobStatus.COMPLETED
        assert result["execution_record"]["no_real_execution"] is True

    def test_simulation_on_already_terminal_job(self, service):
        """已在终态的 job 不能再模拟执行。"""
        job_id = "sbxjob_terminal_test"
        job = SandboxJob(
            job_id=job_id,
            mode=SandboxV2Mode.SIMULATION,
            status=SandboxV2JobStatus.COMPLETED,
        )
        service._store.create_job(job)

        result = service.run_simulation(job_id)
        assert "error" not in result
        assert result["status"] == SandboxV2JobStatus.COMPLETED
        assert result["execution_record"] is None


class TestCancelJob:
    def test_cancel_does_not_pretend_kill(self, service):
        """cancel job 不会假装杀进程。"""
        job_id = "sbxjob_cancel_test"
        job = SandboxJob(
            job_id=job_id,
            mode=SandboxV2Mode.SIMULATION,
            status=SandboxV2JobStatus.POLICY_CHECKED,
        )
        service._store.create_job(job)

        result = service.cancel_job(job_id)
        assert result["canceled"] is True
        assert result["status"] == SandboxV2JobStatus.CANCELED
        assert "No real process was killed" in result["message"]

    def test_cancel_already_completed_job(self, service):
        """已完成 job 的 cancel 返回明确状态，不杀进程。"""
        job_id = "sbxjob_completed_test"
        job = SandboxJob(
            job_id=job_id,
            mode=SandboxV2Mode.SIMULATION,
            status=SandboxV2JobStatus.COMPLETED,
        )
        service._store.create_job(job)

        result = service.cancel_job(job_id)
        assert result["canceled"] is False
        assert "No process was killed" in result["message"]

    def test_cancel_nonexistent_job(self, service):
        """不存在的 job 返回错误。"""
        result = service.cancel_job("nonexistent")
        assert "error" in result


class TestGetJob:
    def test_get_job_status(self, service):
        """获取 job 状态。"""
        job_id = "sbxjob_get_test"
        job = SandboxJob(
            job_id=job_id,
            mode=SandboxV2Mode.SIMULATION,
        )
        service._store.create_job(job)

        status = service.get_job_status(job_id)
        assert status is not None
        assert status["job_id"] == job_id

    def test_get_nonexistent_job(self, service):
        assert service.get_job_status("nonexistent") is None
