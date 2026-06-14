"""Test Sandbox v2 Policy Engine — 策略引擎单元测试。

覆盖：
1. 默认策略是 deny
2. 未知动作 fail closed
3. package download 默认拒绝
4. network access 默认拒绝
5. write filesystem 默认拒绝
"""
import pytest

from src.open_platform.sandbox_v2.models import (
    SandboxJob,
    SandboxPolicyV2,
    SandboxV2Decision,
    SandboxV2Mode,
    SandboxV2JobStatus,
)
from src.open_platform.sandbox_v2.policy_engine import evaluate_policy


def test_default_policy_deny():
    """默认策略是 deny。"""
    job = SandboxJob(mode=SandboxV2Mode.SIMULATION)
    policy = SandboxPolicyV2()  # default_action="deny"
    decision = evaluate_policy(job, policy, requested_action="dry_run")
    assert decision.allowed is False
    assert decision.action == SandboxV2Decision.DENY
    assert "default_action_deny" in decision.matched_rules


def test_unknown_action_fail_closed():
    """未识别动作 fail closed。"""
    job = SandboxJob(mode=SandboxV2Mode.SIMULATION)
    # 创建一个 allow 策略，但 action 不在识别列表中
    policy = SandboxPolicyV2(default_action=SandboxV2Decision.ALLOW)
    decision = evaluate_policy(job, policy, requested_action="unknown_malicious_action")
    assert decision.allowed is False
    assert "unrecognized_action_denied" in decision.matched_rules


def test_package_download_default_deny():
    """package download 默认拒绝。"""
    job = SandboxJob(mode=SandboxV2Mode.SIMULATION)
    policy = SandboxPolicyV2(default_action=SandboxV2Decision.ALLOW)
    decision = evaluate_policy(
        job, policy, requested_action="dry_run",
        requested_package_download=True,
    )
    assert decision.allowed is False
    assert "package_download_denied" in decision.matched_rules


def test_network_access_default_deny():
    """network access 默认拒绝。"""
    job = SandboxJob(mode=SandboxV2Mode.SIMULATION)
    policy = SandboxPolicyV2(default_action=SandboxV2Decision.ALLOW)
    decision = evaluate_policy(
        job, policy, requested_action="dry_run",
        requested_network=True,
    )
    assert decision.allowed is False
    assert "network_denied" in decision.matched_rules


def test_filesystem_write_default_deny():
    """write filesystem 默认拒绝。"""
    job = SandboxJob(mode=SandboxV2Mode.SIMULATION)
    policy = SandboxPolicyV2(default_action=SandboxV2Decision.ALLOW)
    decision = evaluate_policy(
        job, policy, requested_action="dry_run",
        requested_filesystem_write=True,
    )
    assert decision.allowed is False
    assert "filesystem_write_denied" in decision.matched_rules


def test_artifact_materialization_default_deny():
    """artifact materialization 默认拒绝。"""
    job = SandboxJob(mode=SandboxV2Mode.SIMULATION)
    policy = SandboxPolicyV2(default_action=SandboxV2Decision.ALLOW)
    decision = evaluate_policy(
        job, policy, requested_action="dry_run",
        requested_artifact_materialization=True,
    )
    assert decision.allowed is False
    assert "artifact_materialization_denied" in decision.matched_rules


def test_future_container_mode_blocked():
    """future_container 模式被阻止。"""
    job = SandboxJob(mode=SandboxV2Mode.FUTURE_CONTAINER)
    policy = SandboxPolicyV2(default_action=SandboxV2Decision.ALLOW)
    decision = evaluate_policy(job, policy)
    assert decision.allowed is False
    assert "mode_not_allowed" in decision.matched_rules


def test_future_microvm_mode_blocked():
    """future_microvm 模式被阻止。"""
    job = SandboxJob(mode=SandboxV2Mode.FUTURE_MICROVM)
    decision = evaluate_policy(job)
    assert decision.allowed is False


def test_disabled_mode_graceful_deny():
    """disabled 模式返回合理的 deny。"""
    job = SandboxJob(mode=SandboxV2Mode.DISABLED)
    policy = SandboxPolicyV2(default_action=SandboxV2Decision.ALLOW)
    decision = evaluate_policy(job, policy)
    assert decision.allowed is False
    assert "mode_disabled" in decision.matched_rules


def test_missing_mode_fail_closed():
    """mode 缺失 → fail closed。"""
    job = SandboxJob(mode="")  # empty mode
    decision = evaluate_policy(job)
    assert decision.allowed is False
    assert decision.fail_closed is True


def test_none_policy_uses_default_deny():
    """policy 为 None 时使用默认 deny-all 策略。"""
    job = SandboxJob(mode=SandboxV2Mode.SIMULATION)
    decision = evaluate_policy(job, policy=None)
    assert decision.allowed is False
    assert decision.action == SandboxV2Decision.DENY
    assert "default_action_deny" in decision.matched_rules


def test_high_risk_action_denied():
    """高风险动作（如 execute_code）默认拒绝。"""
    job = SandboxJob(mode=SandboxV2Mode.SIMULATION)
    policy = SandboxPolicyV2(default_action=SandboxV2Decision.ALLOW)
    decision = evaluate_policy(job, policy, requested_action="execute_code")
    assert decision.allowed is False
    assert "high_risk_action_denied" in decision.matched_rules
    assert decision.fail_closed is True


def test_shell_exec_high_risk_action_denied():
    """shell_exec 高风险动作拒绝。"""
    job = SandboxJob(mode=SandboxV2Mode.SIMULATION)
    policy = SandboxPolicyV2(default_action=SandboxV2Decision.ALLOW)
    decision = evaluate_policy(job, policy, requested_action="shell_exec")
    assert decision.allowed is False
    assert "high_risk_action_denied" in decision.matched_rules


def test_safe_action_with_allow_policy_passes():
    """安全动作 + allow 策略 → 通过。"""
    job = SandboxJob(mode=SandboxV2Mode.SIMULATION)
    policy = SandboxPolicyV2(default_action=SandboxV2Decision.ALLOW)
    decision = evaluate_policy(job, policy, requested_action="dry_run")
    assert decision.allowed is True
    assert decision.action == SandboxV2Decision.ALLOW
    assert "all_checks_passed" in decision.matched_rules


def test_policy_exception_fail_closed():
    """策略评估异常时 fail closed。"""
    # 传入一个故意导致异常的参数（如 policy 为 broken object）
    decision = evaluate_policy(
        job=None,  # type: ignore — 故意触发异常
        policy=None,
    )
    assert decision.allowed is False
    assert decision.action == SandboxV2Decision.FAIL_CLOSED
    assert decision.fail_closed is True
