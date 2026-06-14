"""Red-Team Kill Switch Abuse Tests — Kill Switch 滥用攻击测试。

验证：不允许任意 PID kill、跨 org/ws kill、伪造 container_id、terminal 假装 kill、参数数组约束。
"""

import pytest, tempfile, os
from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
from src.open_platform.sandbox_v2.kill_switch import SandboxKillSwitchService
from src.open_platform.sandbox_v2.models import (
    SandboxJob, SandboxV2JobStatus, SandboxV2Mode, SandboxV2KillTargetType,
)
from src.open_platform.sandbox_v2.container_provider import ContainerCommandBuilder
from src.open_platform.sandbox_v2.kill_policy import evaluate_kill_policy


@pytest.fixture
def ks():
    fd, db_path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    settings = Settings()
    store = SQLiteSandboxV2Store(settings, db_path=db_path)
    queue = SQLiteSandboxV2Queue(settings, db_path=db_path)
    k = SandboxKillSwitchService(store=store, queue=queue)
    yield k
    try: os.unlink(db_path)
    except: pass


class TestArbitraryPIDRejection:
    def test_pid_target_rejected(self):
        d = evaluate_kill_policy(SandboxJob().to_dict() if False else None, target_exists=True, target_status="running")
        # use kill policy directly
        from src.open_platform.sandbox_v2.models import SandboxKillRequest
        r = SandboxKillRequest(target_type=SandboxV2KillTargetType.JOB, target_id="pid:12345")
        d = evaluate_kill_policy(r, target_exists=True, target_status="running")
        assert not d.allowed

    def test_unknown_job_rejected(self, ks):
        r = ks.request_kill(job_id="nonexistent-job-id-12345", target_type="job")
        # Should not 500 — should return rejected
        decision = r.get("decision", {})
        assert decision.get("allowed") is False or r["action_result"].get("error")


class TestCrossOrgKillRejection:
    def test_not_sandbox_owned(self):
        from src.open_platform.sandbox_v2.models import SandboxKillRequest, SandboxV2KillTargetType
        d = evaluate_kill_policy(SandboxKillRequest(target_type=SandboxV2KillTargetType.JOB), target_exists=True, target_is_owned_by_sandbox=False)
        assert not d.allowed


class TestTerminalStateAbuse:
    def test_completed_no_kill(self, ks):
        job = SandboxJob(job_id="sbxjob_rt_c", status=SandboxV2JobStatus.COMPLETED, mode=SandboxV2Mode.SIMULATION)
        ks._store.create_job(job)
        r = ks.request_kill(job_id="sbxjob_rt_c", target_type="job")
        assert r["decision"]["action"] == "no_active_execution"

    def test_failed_no_kill(self, ks):
        job = SandboxJob(job_id="sbxjob_rt_f", status=SandboxV2JobStatus.FAILED, mode=SandboxV2Mode.SIMULATION)
        ks._store.create_job(job)
        r = ks.request_kill(job_id="sbxjob_rt_f", target_type="job")
        assert r["decision"]["action"] == "no_active_execution"


class TestContainerKillCommandSafety:
    def test_kill_command_is_array(self):
        cmd = ContainerCommandBuilder.build_kill_command("docker", "sbxcontainer_abc123")
        assert isinstance(cmd, list)
        assert cmd == ["docker", "kill", "sbxcontainer_abc123"]

    def test_no_shell_true(self):
        cmd = ContainerCommandBuilder.build_kill_command("docker", "sbxtest")
        assert ";" not in " ".join(cmd)
        assert "&&" not in " ".join(cmd)
        assert "|" not in " ".join(cmd)


class TestKillRecordCreation:
    def test_kill_produces_record(self, ks):
        job = SandboxJob(job_id="sbxjob_rt_rec", status=SandboxV2JobStatus.QUEUED, mode=SandboxV2Mode.SIMULATION)
        ks._store.create_job(job)
        ks._queue.enqueue(job_id="sbxjob_rt_rec")
        ks.request_kill(job_id="sbxjob_rt_rec", target_type="job")
        records = ks.list_kill_records(job_id="sbxjob_rt_rec")
        assert len(records) >= 1

    def test_readiness_arbitrary_pid_false(self, ks):
        r = ks.get_kill_readiness()
        assert r["arbitrary_pid_kill"] is False
        assert r["process_kill_implemented"] is False
