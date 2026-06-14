"""Test Sandbox v2 Models — 数据模型单元测试。"""
import pytest
from datetime import datetime, timezone

from src.open_platform.sandbox_v2.models import (
    SandboxV2JobStatus,
    SandboxV2Mode,
    SandboxV2Decision,
    SandboxV2RiskLevel,
    SandboxResourceLimits,
    SandboxNetworkPolicy,
    SandboxFilesystemPolicy,
    SandboxArtifactPolicy,
    SandboxPackagePolicy,
    SandboxPolicyV2,
    SandboxV2PolicyDecision,
    SandboxJob,
    SandboxV2ExecutionRecord,
    MVP_ALLOWED_MODES,
)


class TestSandboxV2Enums:
    def test_status_enum_values(self):
        assert SandboxV2JobStatus.CREATED == "created"
        assert SandboxV2JobStatus.POLICY_CHECKED == "policy_checked"
        assert SandboxV2JobStatus.REJECTED == "rejected"
        assert SandboxV2JobStatus.COMPLETED == "completed"
        assert SandboxV2JobStatus.CANCELED == "canceled"

    def test_mode_enum_values(self):
        assert SandboxV2Mode.METADATA_ONLY == "metadata_only"
        assert SandboxV2Mode.SIMULATION == "simulation"
        assert SandboxV2Mode.FUTURE_CONTAINER == "future_container"
        assert SandboxV2Mode.FUTURE_MICROVM == "future_microvm"

    def test_mvp_allowed_modes(self):
        assert SandboxV2Mode.METADATA_ONLY in MVP_ALLOWED_MODES
        assert SandboxV2Mode.SIMULATION in MVP_ALLOWED_MODES
        assert SandboxV2Mode.DISABLED in MVP_ALLOWED_MODES
        assert SandboxV2Mode.FUTURE_CONTAINER not in MVP_ALLOWED_MODES
        assert SandboxV2Mode.FUTURE_MICROVM not in MVP_ALLOWED_MODES


class TestSandboxResourceLimits:
    def test_default_values(self):
        limits = SandboxResourceLimits()
        assert limits.max_runtime_seconds == 30
        assert limits.max_memory_mb == 256
        assert limits.max_cpu_percent == 50
        assert limits.max_output_bytes == 1_048_576

    def test_to_dict_and_from_dict(self):
        limits = SandboxResourceLimits(max_runtime_seconds=60, max_memory_mb=512)
        d = limits.to_dict()
        restored = SandboxResourceLimits.from_dict(d)
        assert restored.max_runtime_seconds == 60
        assert restored.max_memory_mb == 512


class TestSandboxNetworkPolicy:
    def test_default_deny(self):
        policy = SandboxNetworkPolicy()
        assert policy.allow_network is False

    def test_to_dict(self):
        policy = SandboxNetworkPolicy(allow_network=True, allowed_domains=["example.com"])
        d = policy.to_dict()
        assert d["allow_network"] is True
        assert "example.com" in d["allowed_domains"]


class TestSandboxFilesystemPolicy:
    def test_default_deny(self):
        policy = SandboxFilesystemPolicy()
        assert policy.allow_write_filesystem is False
        assert policy.read_only_rootfs is True


class TestSandboxArtifactPolicy:
    def test_default_deny(self):
        policy = SandboxArtifactPolicy()
        assert policy.allow_artifact_materialization is False


class TestSandboxPackagePolicy:
    def test_default_deny(self):
        policy = SandboxPackagePolicy()
        assert policy.allow_package_download is False
        assert policy.require_hash_verification is True
        assert policy.quarantine_downloads is True


class TestSandboxPolicyV2:
    def test_default_policy_is_deny(self):
        policy = SandboxPolicyV2()
        assert policy.default_action == SandboxV2Decision.DENY
        assert policy.allow_network is False
        assert policy.allow_write_filesystem is False
        assert policy.allow_package_download is False
        assert policy.allow_artifact_materialization is False
        assert policy.require_human_approval is True

    def test_roundtrip(self):
        policy = SandboxPolicyV2(name="test-policy", default_action=SandboxV2Decision.ALLOW)
        d = policy.to_dict()
        restored = SandboxPolicyV2.from_dict(d)
        assert restored.name == "test-policy"
        assert restored.default_action == SandboxV2Decision.ALLOW


class TestSandboxJob:
    def test_default_job(self):
        job = SandboxJob()
        assert job.job_id.startswith("sbxjob_")
        assert job.mode == SandboxV2Mode.SIMULATION
        assert job.status == SandboxV2JobStatus.CREATED

    def test_is_valid_mode(self):
        job = SandboxJob(mode=SandboxV2Mode.SIMULATION)
        assert job.is_valid_mode() is True
        job.mode = SandboxV2Mode.FUTURE_CONTAINER
        assert job.is_valid_mode() is False

    def test_is_terminal(self):
        job = SandboxJob(status=SandboxV2JobStatus.CREATED)
        assert job.is_terminal() is False
        job.status = SandboxV2JobStatus.COMPLETED
        assert job.is_terminal() is True
        job.status = SandboxV2JobStatus.REJECTED
        assert job.is_terminal() is True

    def test_is_cancellable(self):
        job = SandboxJob(status=SandboxV2JobStatus.CREATED)
        assert job.is_cancellable() is True
        job.status = SandboxV2JobStatus.COMPLETED
        assert job.is_cancellable() is False

    def test_roundtrip(self):
        job = SandboxJob(
            organization_id="org-1",
            workspace_id="ws-1",
            requested_action="metadata_validate",
        )
        d = job.to_dict()
        restored = SandboxJob.from_dict(d)
        assert restored.organization_id == "org-1"
        assert restored.workspace_id == "ws-1"


class TestSandboxV2ExecutionRecord:
    def test_default_no_real_execution(self):
        record = SandboxV2ExecutionRecord()
        assert record.no_real_execution is True

    def test_roundtrip(self):
        now = datetime.now(timezone.utc)
        record = SandboxV2ExecutionRecord(
            job_id="sbxjob_test",
            status=SandboxV2JobStatus.COMPLETED,
            mode=SandboxV2Mode.SIMULATION,
            started_at=now,
            finished_at=now,
            duration_ms=42,
            reason="test",
        )
        d = record.to_dict()
        restored = SandboxV2ExecutionRecord.from_dict(d)
        assert restored.job_id == "sbxjob_test"
        assert restored.duration_ms == 42
        assert restored.no_real_execution is True
