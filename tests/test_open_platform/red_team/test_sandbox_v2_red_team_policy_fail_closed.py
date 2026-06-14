"""Red-Team Policy Fail-Closed Tests — 所有策略引擎在异常/缺失时必须 fail closed。

验证：异常时 allowed=false, fail_closed=true，状态不误判为 completed/released/materialized。
"""

import pytest
from src.open_platform.sandbox_v2.models import (
    SandboxJob, SandboxExecutionPlan, SandboxV2IsolationProvider, SandboxV2Mode,
    SandboxNetworkEgressRequest,
    SandboxArtifactMaterializationRequest,
    SandboxPackageRequest, SandboxV2PackageManager, SandboxV2PackageSourceType,
)
from src.open_platform.sandbox_v2.policy_engine import evaluate_policy
from src.open_platform.sandbox_v2.isolation_policy import evaluate_isolation_policy
from src.open_platform.sandbox_v2.network_policy import evaluate_egress_policy
from src.open_platform.sandbox_v2.artifact_policy import evaluate_artifact_policy
from src.open_platform.sandbox_v2.package_policy import evaluate_package_policy
from src.open_platform.sandbox_v2.kill_policy import evaluate_kill_policy


class TestFailClosedAllEngines:
    """所有策略引擎在异常输入时 fail closed。"""
    def test_sandbox_policy_none(self):
        d = evaluate_policy(None)  # type: ignore
        assert not d.allowed and d.fail_closed

    def test_network_policy_none(self):
        d = evaluate_egress_policy(None)  # type: ignore
        assert not d.allowed and d.fail_closed

    def test_artifact_policy_none(self):
        d = evaluate_artifact_policy(None)  # type: ignore
        assert not d.allowed and d.fail_closed

    def test_package_policy_none(self):
        d = evaluate_package_policy(None)  # type: ignore
        assert not d.allowed and d.fail_closed

    def test_isolation_policy_none(self):
        d = evaluate_isolation_policy(None)  # type: ignore
        assert not d.allowed and d.fail_closed

    def test_kill_policy_none(self):
        d = evaluate_kill_policy(None)  # type: ignore
        assert not d.allowed and d.fail_closed


class TestMissingFields:
    """缺失关键字段时 fail closed。"""
    def test_missing_mode(self):
        job = SandboxJob(mode="")
        d = evaluate_policy(job)
        assert not d.allowed and d.fail_closed

    def test_missing_provider(self):
        d = evaluate_isolation_policy(SandboxExecutionPlan(provider=""))
        assert not d.allowed and d.fail_closed

    def test_unknown_mode(self):
        job = SandboxJob(mode="quantum_executor")
        d = evaluate_policy(job)
        assert not d.allowed and d.fail_closed

    def test_unknown_action(self):
        job = SandboxJob(mode=SandboxV2Mode.SIMULATION, requested_action="exploit_kernel")
        d = evaluate_policy(job, requested_action="exploit_kernel")
        assert not d.allowed

    def test_no_resource_limits_isolation(self):
        d = evaluate_isolation_policy(
            SandboxExecutionPlan(provider=SandboxV2IsolationProvider.TRUSTED_FIXTURE, mode=SandboxV2Mode.SIMULATION),
            resource_limits_provided=False)
        assert not d.allowed


class TestHighRiskActionBlocked:
    """高风险动作关键字被拦截。"""
    def _chk(self, action):
        job = SandboxJob(mode=SandboxV2Mode.SIMULATION, requested_action=action)
        from src.open_platform.sandbox_v2.models import SandboxPolicyV2, SandboxV2Decision
        d = evaluate_policy(job, SandboxPolicyV2(default_action=SandboxV2Decision.ALLOW), requested_action=action)
        return d

    def test_execute_code(self): assert not self._chk("execute_code").allowed
    def test_shell_exec(self): assert not self._chk("shell_exec").allowed
    def test_subprocess(self): assert not self._chk("subprocess").allowed
    def test_container_escape(self): assert not self._chk("container_escape").allowed
    def test_privilege_escalation(self): assert not self._chk("privilege_escalation").allowed
    def test_reverse_shell(self): assert not self._chk("reverse_shell").allowed
