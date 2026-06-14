"""Tests for MicroVM API (Step 11).

验证:
1. Preflight API 不返回 500
2. Readiness API 包含 MicroVM 字段
3. MicroVM plan CRUD API
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestMicroVMPreflightAPI:
    """Preflight API。"""

    def test_check_microvm_preconditions_no_error(self):
        from src.open_platform.sandbox_v2.isolation_capabilities import SandboxIsolationCapabilityProbe
        probe = SandboxIsolationCapabilityProbe()
        pc = probe.check_microvm_preconditions()
        assert "runnable" in pc
        assert "error" not in pc


class TestMicroVMReadinessFields:
    """Readiness API 含 MicroVM 字段。"""

    def test_readiness_has_microvm_fields(self):
        from src.api.sandbox_v2 import ReadinessResponse
        resp = ReadinessResponse()
        data = resp.model_dump()
        microvm_fields = [
            "microvm_provider_abstraction",
            "firecracker_provider_abstraction",
            "microvm_execution_enabled",
            "microvm_integration_enabled",
            "microvm_runnable",
            "kvm_available",
            "firecracker_binary_present",
            "microvm_kernel_present",
            "microvm_rootfs_present",
            "microvm_network_enabled",
            "user_kernel_allowed",
            "user_rootfs_allowed",
            "host_mounts_allowed",
            "real_microvm_execution",
        ]
        for field in microvm_fields:
            assert field in data, f"Field '{field}' missing from ReadinessResponse"

    def test_microvm_fields_default_safe(self):
        from src.api.sandbox_v2 import ReadinessResponse
        resp = ReadinessResponse()
        assert resp.microvm_execution_enabled is False
        assert resp.microvm_runnable is False
        assert resp.kvm_available is False
        assert resp.firecracker_binary_present is False
        assert resp.real_microvm_execution is False
        assert resp.user_kernel_allowed is False
        assert resp.user_rootfs_allowed is False
        assert resp.host_mounts_allowed is False
        assert resp.microvm_network_enabled is False


class TestMicroVMModels:
    """MicroVM 数据模型。"""

    def test_microvm_plan_defaults(self):
        from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionPlan
        plan = SandboxMicroVMExecutionPlan()
        assert plan.microvm_plan_id.startswith("sbxmv_")
        assert plan.runtime == "unavailable"
        assert plan.status == "created"
        assert plan.network_enabled is False
        assert plan.memory_mb == 128

    def test_microvm_result_defaults(self):
        from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionResult
        result = SandboxMicroVMExecutionResult()
        assert result.microvm_result_id.startswith("sbxmvres_")
        assert result.status == "unavailable"
        assert result.timeout is False

    def test_config_masks_paths(self):
        from src.open_platform.sandbox_v2.models import SandboxMicroVMRuntimeConfig
        config = SandboxMicroVMRuntimeConfig(
            firecracker_bin_path="/secret/path/firecracker",
            kernel_path="/secret/path/vmlinux",
            rootfs_path="/secret/path/rootfs.ext4",
        )
        d = config.to_dict()
        # Paths should be masked — only boolean presence
        assert d["firecracker_binary_present"] is True
        assert d["kernel_present"] is True
        assert d["rootfs_present"] is True
        # Should NOT leak actual paths
        assert "/secret/" not in str(d.get("firecracker_bin_path", ""))

    def test_preflight_result_fields(self):
        from src.open_platform.sandbox_v2.models import SandboxMicroVMPreflightResult
        pf = SandboxMicroVMPreflightResult(
            platform="Linux", is_linux=True, has_kvm=True,
            firecracker_binary_present=True, kernel_present=True, rootfs_present=True,
            execution_env_enabled=True, integration_env_enabled=True,
            runnable=True, reason="all good",
        )
        d = pf.to_dict()
        assert d["runnable"] is True
        assert d["blockers"] == []

    def test_preflight_blockers(self):
        from src.open_platform.sandbox_v2.models import SandboxMicroVMPreflightResult
        pf = SandboxMicroVMPreflightResult(
            blockers=["No KVM", "No kernel"], runnable=False,
        )
        assert pf.runnable is False
        assert len(pf.blockers) == 2


class TestMicroVMPlanCRUD:
    """MicroVM plan CRUD（通过 SQLite store 测试）。"""

    @pytest.fixture
    def store(self):
        from src.adapters.config import Settings as AppSettings
        from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        return SQLiteSandboxV2Store(config=AppSettings())

    def test_full_crud_flow(self, store):
        from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionPlan, SandboxMicroVMExecutionResult
        # Create
        plan = SandboxMicroVMExecutionPlan(job_id="crud-test", fixture_id="hello-microvm-fixture")
        created = store.create_microvm_execution_plan(plan)
        assert created is not None

        # Read
        fetched = store.get_microvm_execution_plan(plan.microvm_plan_id)
        assert fetched.job_id == "crud-test"

        # Update
        updated = store.update_microvm_execution_plan_status(plan.microvm_plan_id, "preflight_passed", "tests passed")
        assert updated.status == "preflight_passed"

        # List
        items = store.list_microvm_execution_plans(job_id="crud-test")
        assert len(items) >= 1

        # Result
        result = SandboxMicroVMExecutionResult(microvm_plan_id=plan.microvm_plan_id, job_id="crud-test")
        store.create_microvm_execution_result(result)
        results = store.list_microvm_execution_results(job_id="crud-test")
        assert len(results) >= 1
