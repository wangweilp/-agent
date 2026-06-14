"""Tests for MicroVM Service integration (Step 11).

验证:
1. MicroVM plan 可写入 SQLite
2. MicroVM plan 可查询
3. MicroVM result 可写入 SQLite
4. Kill Switch target_type 包含 microvm
5. Preflight API 不返回 500
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════════════════
# 1. Store integration
# ═══════════════════════════════════════════════════════════════════════════

class TestMicroVMStoreIntegration:
    """MicroVM store 方法集成测试（使用 SQLite）。"""

    @pytest.fixture
    def store(self):
        from src.adapters.config import Settings as AppSettings
        from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        config = AppSettings()
        return SQLiteSandboxV2Store(config=config)

    def test_create_microvm_plan(self, store):
        from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionPlan
        plan = SandboxMicroVMExecutionPlan(
            job_id="test-job", fixture_id="hello-microvm-fixture",
            memory_mb=128, vcpu_count=1,
        )
        created = store.create_microvm_execution_plan(plan)
        assert created.microvm_plan_id == plan.microvm_plan_id
        assert created.job_id == "test-job"

    def test_get_microvm_plan(self, store):
        from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionPlan
        plan = SandboxMicroVMExecutionPlan(job_id="test-job-2", fixture_id="hello-microvm-fixture")
        store.create_microvm_execution_plan(plan)
        fetched = store.get_microvm_execution_plan(plan.microvm_plan_id)
        assert fetched is not None
        assert fetched.job_id == "test-job-2"

    def test_list_microvm_plans(self, store):
        from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionPlan
        store.create_microvm_execution_plan(SandboxMicroVMExecutionPlan(job_id="j1"))
        store.create_microvm_execution_plan(SandboxMicroVMExecutionPlan(job_id="j1"))
        items = store.list_microvm_execution_plans(job_id="j1")
        assert len(items) >= 2

    def test_update_microvm_plan_status(self, store):
        from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionPlan
        plan = SandboxMicroVMExecutionPlan(job_id="j-status")
        store.create_microvm_execution_plan(plan)
        updated = store.update_microvm_execution_plan_status(plan.microvm_plan_id, "preflight_passed", "ok")
        assert updated is not None
        assert updated.status == "preflight_passed"

    def test_create_microvm_result(self, store):
        from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionResult
        result = SandboxMicroVMExecutionResult(
            job_id="j1", status="preflight_passed", reason="ok",
        )
        created = store.create_microvm_execution_result(result)
        assert created.microvm_result_id == result.microvm_result_id

    def test_get_microvm_result(self, store):
        from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionResult
        result = SandboxMicroVMExecutionResult(job_id="j-get", status="completed")
        store.create_microvm_execution_result(result)
        fetched = store.get_microvm_execution_result(result.microvm_result_id)
        assert fetched is not None
        assert fetched.job_id == "j-get"

    def test_list_microvm_results(self, store):
        from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionResult
        store.create_microvm_execution_result(SandboxMicroVMExecutionResult(job_id="jr"))
        items = store.list_microvm_execution_results(job_id="jr")
        assert len(items) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# 2. Kill Switch integration
# ═══════════════════════════════════════════════════════════════════════════

class TestMicroVMKillSwitch:
    """MicroVM target type in kill switch。"""

    def test_kill_target_type_includes_microvm(self):
        from src.open_platform.sandbox_v2.models import SandboxV2KillTargetType
        assert SandboxV2KillTargetType.MICROVM_PLAN == "microvm_plan"
        assert SandboxV2KillTargetType.MICROVM == "microvm"

    def test_microvm_kill_not_allowed_default(self):
        """默认 MicroVM kill 不可用。"""
        from src.open_platform.sandbox_v2.kill_policy import evaluate_kill_policy
        from src.open_platform.sandbox_v2.models import SandboxKillRequest
        result = evaluate_kill_policy(
            SandboxKillRequest(target_type="microvm_plan", target_id="mv-test-1"),
        )
        assert not result.allowed


# ═══════════════════════════════════════════════════════════════════════════
# 3. Preflight check
# ═══════════════════════════════════════════════════════════════════════════

class TestMicroVMPreflight:
    """MicroVM preflight 功能。"""

    def test_preflight_returns_dict(self):
        from src.open_platform.sandbox_v2.microvm_provider import FirecrackerMicroVMExecutionProvider
        provider = FirecrackerMicroVMExecutionProvider()
        pf = provider.get_preflight()
        assert pf is not None

    def test_preflight_has_all_fields(self):
        from src.open_platform.sandbox_v2.microvm_provider import FirecrackerMicroVMExecutionProvider
        provider = FirecrackerMicroVMExecutionProvider()
        pf = provider.get_preflight()
        d = pf.to_dict()
        assert "has_kvm" in d
        assert "firecracker_binary_present" in d
        assert "kernel_present" in d
        assert "rootfs_present" in d
        assert "runnable" in d

    def test_preflight_not_runnable_on_windows(self):
        import platform
        from src.open_platform.sandbox_v2.microvm_provider import FirecrackerMicroVMExecutionProvider
        provider = FirecrackerMicroVMExecutionProvider()
        pf = provider.get_preflight()
        if platform.system() == "Windows":
            assert not pf.runnable

    def test_capability_probe_microvm_methods(self):
        from src.open_platform.sandbox_v2.isolation_capabilities import SandboxIsolationCapabilityProbe
        probe = SandboxIsolationCapabilityProbe()
        pc = probe.check_microvm_preconditions()
        import platform
        if platform.system() == "Windows":
            assert not pc["runnable"]
        assert "has_kvm" in pc

    def test_microvm_readiness_summary(self):
        from src.open_platform.sandbox_v2.isolation_capabilities import SandboxIsolationCapabilityProbe
        probe = SandboxIsolationCapabilityProbe()
        summary = probe.get_microvm_readiness_summary()
        assert summary["microvm_provider_abstraction"] is True
        assert summary["firecracker_provider_abstraction"] is True
        assert summary["microvm_execution_enabled"] is False
        assert summary["real_microvm_execution"] is False
