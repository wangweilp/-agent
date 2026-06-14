"""Sandbox v2 Isolation Policy Engine — 执行隔离策略评估 (Step 6A + 6B)。

安全规则：
1. 默认 deny
2. fail closed
3. simulation / trusted_fixture 允许
4. docker_rootless_future / podman_rootless_future 在严格条件下允许
5. gvisor/kata/firecracker/microvm future 继续拒绝
6. local_process_disabled 拒绝
7. future_container / future_microvm mode 拒绝
8. 缺少 resource limits 拒绝
9. allow_network=true 时拒绝（container 也不例外）
10. filesystem 允许任意写时拒绝
11. package install 允许时拒绝
"""

from __future__ import annotations

import logging

from src.open_platform.sandbox_v2.models import (
    SandboxV2RiskLevel,
    SandboxV2IsolationProvider,
    SandboxV2Mode,
    SandboxV2Decision,
    SandboxExecutionPlan,
    SandboxIsolationDecision,
    STEP6A_ALLOWED_PROVIDERS,
)

# 容器类 provider — 需要严格条件
_CONTAINER_PROVIDERS = {
    SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE,
    SandboxV2IsolationProvider.PODMAN_ROOTLESS_FUTURE,
}

logger = logging.getLogger(__name__)


def evaluate_isolation_policy(
    plan: SandboxExecutionPlan,
    *,
    resource_limits_provided: bool = True,
    allow_network: bool = False,
    allow_filesystem_write: bool = False,
    allow_package_install: bool = False,
    allow_artifact_materialization_not_readonly: bool = False,
) -> SandboxIsolationDecision:
    """评估隔离执行计划策略。"""
    try:
        return _eval_impl(
            plan, resource_limits_provided=resource_limits_provided,
            allow_network=allow_network,
            allow_filesystem_write=allow_filesystem_write,
            allow_package_install=allow_package_install,
            allow_artifact_writable=allow_artifact_materialization_not_readonly,
        )
    except Exception:
        logger.exception("isolation_policy_failed")
        return SandboxIsolationDecision(
            reason="Isolation policy evaluation exception — fail closed.",
            risk_level=SandboxV2RiskLevel.CRITICAL,
            matched_rules=["exception_fail_closed"], fail_closed=True,
        )


def _eval_impl(plan, **kw) -> SandboxIsolationDecision:
    matched: list[str] = []

    # Rule 1: Provider must not be None / empty
    if not plan.provider:
        return SandboxIsolationDecision(
            reason="Execution plan has no provider — fail closed.",
            risk_level=SandboxV2RiskLevel.HIGH,
            matched_rules=["provider_missing"], fail_closed=True,
        )
    matched.append("provider_present")

    # Rule 2: Only STEP6A allowed providers; container providers need strict checks
    if plan.provider not in STEP6A_ALLOWED_PROVIDERS:
        return SandboxIsolationDecision(
            reason=f"Provider '{plan.provider}' is reserved for future step. Contact admin to enable.",
            risk_level=SandboxV2RiskLevel.HIGH,
            matched_rules=[*matched, "provider_future_reserved"],
            fail_closed=True,
        )

    # Rule 2b: Container providers need extra validation
    if plan.provider in _CONTAINER_PROVIDERS:
        if kw.get("allow_network", False):
            return SandboxIsolationDecision(provider=plan.provider,
                reason="Container execution requires network disabled.",
                risk_level=SandboxV2RiskLevel.HIGH, matched_rules=[*matched, "container_network_required"], fail_closed=True)
        if kw.get("allow_filesystem_write", False):
            return SandboxIsolationDecision(provider=plan.provider,
                reason="Container execution requires filesystem write disabled.",
                risk_level=SandboxV2RiskLevel.HIGH, matched_rules=[*matched, "container_fs_write_denied"], fail_closed=True)
        matched.append("container_poc_allowed")

    # Rule 3: Disabled provider always denies
    if plan.provider == SandboxV2IsolationProvider.DISABLED:
        return SandboxIsolationDecision(
            provider=SandboxV2IsolationProvider.DISABLED,
            reason="Execution provider is disabled.",
            risk_level=SandboxV2RiskLevel.LOW,
            matched_rules=[*matched, "provider_disabled"],
        )
    matched.append("provider_step6a_allowed")

    # Rule 4: Mode check — reject future_container/future_microvm
    bad_modes = {SandboxV2Mode.FUTURE_CONTAINER, SandboxV2Mode.FUTURE_MICROVM}
    if plan.mode in bad_modes:
        return SandboxIsolationDecision(
            provider=plan.provider,
            reason=f"Mode '{plan.mode}' is reserved for future and cannot be executed.",
            risk_level=SandboxV2RiskLevel.HIGH,
            matched_rules=[*matched, "future_mode_rejected"],
            fail_closed=True,
        )
    matched.append("mode_valid")

    # Rule 5: Resource limits must be provided
    if not kw.get("resource_limits_provided", True):
        return SandboxIsolationDecision(
            provider=plan.provider,
            reason="Resource limits are not provided — reject.",
            risk_level=SandboxV2RiskLevel.HIGH,
            matched_rules=[*matched, "missing_resource_limits"],
            fail_closed=True,
        )
    matched.append("resource_limits_provided")

    # Rule 6: Network must be denied in sandbox policy
    if kw.get("allow_network", False):
        return SandboxIsolationDecision(
            provider=plan.provider,
            reason="SandboxPolicy allow_network=true — real network not yet allowed for isolation execution.",
            risk_level=SandboxV2RiskLevel.HIGH,
            matched_rules=[*matched, "network_not_allowed"],
            fail_closed=True,
        )
    matched.append("network_denied_correctly")

    # Rule 7: Filesystem write must not be allowed
    if kw.get("allow_filesystem_write", False):
        return SandboxIsolationDecision(
            provider=plan.provider,
            reason="Filesystem write is not allowed for isolation execution at this step.",
            risk_level=SandboxV2RiskLevel.HIGH,
            matched_rules=[*matched, "filesystem_write_not_allowed"],
            fail_closed=True,
        )
    matched.append("filesystem_write_correctly_denied")

    # Rule 8: Package install must not be allowed
    if kw.get("allow_package_install", False):
        return SandboxIsolationDecision(
            provider=plan.provider,
            reason="Package install is not allowed for isolation execution.",
            risk_level=SandboxV2RiskLevel.CRITICAL,
            matched_rules=[*matched, "package_install_not_allowed"],
            fail_closed=True,
        )
    matched.append("package_install_correctly_denied")

    # Rule 9: Artifact must be read-only
    if kw.get("allow_artifact_writable", False):
        return SandboxIsolationDecision(
            provider=plan.provider,
            reason="Artifact materialization must be read-only.",
            risk_level=SandboxV2RiskLevel.HIGH,
            matched_rules=[*matched, "artifact_readonly_required"],
            fail_closed=True,
        )
    matched.append("artifact_readonly")

    # All passed
    action = "execute_trusted_fixture" if plan.provider == SandboxV2IsolationProvider.TRUSTED_FIXTURE else "simulate"
    return SandboxIsolationDecision(
        allowed=True,
        provider=plan.provider,
        action=action,
        reason=f"Isolation policy passed for provider={plan.provider}, mode={plan.mode}. No real code execution.",
        risk_level=SandboxV2RiskLevel.LOW,
        execution_allowed=(plan.provider == SandboxV2IsolationProvider.TRUSTED_FIXTURE),
        network_allowed=False,
        filesystem_write_allowed=False,
        package_install_allowed=False,
        matched_rules=matched,
        fail_closed=False,
    )
