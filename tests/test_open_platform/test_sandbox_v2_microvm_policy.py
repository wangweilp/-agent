"""Tests for MicroVM Policy Engine (Step 11).

验证:
1. 默认 microvm_execution_enabled=false → disabled
2. Windows → unavailable
3. 缺 KVM → unavailable
4. 缺 firecracker binary → unavailable
5. 缺 kernel/rootfs → unavailable
6. network_enabled=true → rejected
7. user_kernel/rootfs → rejected
8. host_mounts → rejected
9. unknown fixture → rejected
10. trusted fixture + all conditions → preflight_passed
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionPlan
from src.open_platform.sandbox_v2.microvm_policy import evaluate_microvm_policy


def _make_plan(**kw) -> SandboxMicroVMExecutionPlan:
    return SandboxMicroVMExecutionPlan(
        fixture_id=kw.get("fixture_id", "hello-microvm-fixture"),
        network_enabled=kw.get("network_enabled", False),
    )


def _all_conditions_met():
    """返回满足所有前置条件的 kw."""
    return {
        "microvm_execution_enabled": True,
        "run_microvm_integration": True,
        "is_linux": True,
        "has_kvm": True,
        "firecracker_binary_present": True,
        "kernel_present": True,
        "rootfs_present": True,
        "network_enabled": False,
        "allow_user_kernel": False,
        "allow_user_rootfs": False,
        "allow_host_mounts": False,
    }


class TestMicroVMPolicyDefaultDeny:
    """默认所有危险操作 deny。"""

    def test_default_disabled(self):
        r = evaluate_microvm_policy(_make_plan())
        assert not r["allowed"]
        assert r["status"] == "disabled"

    def test_enabled_but_integration_disabled(self):
        r = evaluate_microvm_policy(_make_plan(), microvm_execution_enabled=True)
        assert not r["allowed"]
        assert r["status"] == "disabled"

    def test_windows_unavailable(self):
        r = evaluate_microvm_policy(_make_plan(),
            microvm_execution_enabled=True, run_microvm_integration=True,
            is_linux=False)
        assert not r["allowed"]
        assert r["status"] == "unavailable"

    def test_no_kvm_unavailable(self):
        r = evaluate_microvm_policy(_make_plan(),
            microvm_execution_enabled=True, run_microvm_integration=True,
            is_linux=True, has_kvm=False)
        assert not r["allowed"]
        assert r["status"] == "unavailable"

    def test_no_firecracker_binary_unavailable(self):
        kw = _all_conditions_met()
        kw["firecracker_binary_present"] = False
        r = evaluate_microvm_policy(_make_plan(), **kw)
        assert not r["allowed"]
        assert r["status"] == "unavailable"

    def test_no_kernel_unavailable(self):
        kw = _all_conditions_met()
        kw["kernel_present"] = False
        r = evaluate_microvm_policy(_make_plan(), **kw)
        assert not r["allowed"]
        assert r["status"] == "unavailable"

    def test_no_rootfs_unavailable(self):
        kw = _all_conditions_met()
        kw["rootfs_present"] = False
        r = evaluate_microvm_policy(_make_plan(), **kw)
        assert not r["allowed"]
        assert r["status"] == "unavailable"


class TestMicroVMPolicyRejections:
    """危险配置被拒绝。"""

    def test_network_enabled_rejected(self):
        kw = _all_conditions_met()
        kw["network_enabled"] = True
        r = evaluate_microvm_policy(_make_plan(network_enabled=True), **kw)
        assert not r["allowed"]
        assert r["status"] == "rejected"

    def test_user_kernel_rejected(self):
        kw = _all_conditions_met()
        kw["allow_user_kernel"] = True
        r = evaluate_microvm_policy(_make_plan(), **kw)
        assert not r["allowed"]
        assert r["status"] == "rejected"

    def test_user_rootfs_rejected(self):
        kw = _all_conditions_met()
        kw["allow_user_rootfs"] = True
        r = evaluate_microvm_policy(_make_plan(), **kw)
        assert not r["allowed"]
        assert r["status"] == "rejected"

    def test_host_mounts_rejected(self):
        kw = _all_conditions_met()
        kw["allow_host_mounts"] = True
        r = evaluate_microvm_policy(_make_plan(), **kw)
        assert not r["allowed"]
        assert r["status"] == "rejected"

    def test_unknown_fixture_rejected(self):
        r = evaluate_microvm_policy(_make_plan(fixture_id="evil-rootkit"),
            **_all_conditions_met())
        assert not r["allowed"]
        assert r["status"] == "rejected"

    def test_missing_fixture_id_rejected(self):
        r = evaluate_microvm_policy(_make_plan(fixture_id=""),
            **_all_conditions_met())
        assert not r["allowed"]
        assert r["status"] == "rejected"

    def test_exception_fail_closed(self):
        """Exception inside policy → fail closed."""
        r = evaluate_microvm_policy(
            SandboxMicroVMExecutionPlan(fixture_id=None, network_enabled=None),
        )
        assert not r["allowed"]


class TestMicroVMPolicySuccess:
    """所有条件满足时 preflight_passed。"""

    def test_trusted_fixture_preflight_passed(self):
        r = evaluate_microvm_policy(_make_plan(fixture_id="hello-microvm-fixture"),
            **_all_conditions_met())
        assert r["allowed"]
        assert r["status"] == "preflight_passed"

    def test_has_matched_rules(self):
        r = evaluate_microvm_policy(_make_plan(fixture_id="hello-microvm-fixture"),
            **_all_conditions_met())
        assert len(r["matched_rules"]) > 5
        assert "trusted_fixture_valid" in r["matched_rules"]
