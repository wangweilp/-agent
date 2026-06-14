"""Sandbox v2 Policy Engine — 默认 deny / fail closed 策略评估。

安全约束：
- 不执行用户代码
- 不调用 subprocess
- 不调用 Docker
- 不写真实系统文件
- 不发起外网请求

策略逻辑：
1. 默认 deny
2. fail closed（任何异常 → deny）
3. 高风险动作默认拒绝
4. 未识别动作默认拒绝
5. 包下载、文件写入、外网访问、artifact materialization 默认拒绝
6. 只允许 metadata_only 或 simulation 类型的 job 通过
7. 如果策略字段缺失，必须 fail closed
8. 输出 SandboxV2PolicyDecision
"""

from __future__ import annotations

import logging
from typing import Any

from src.open_platform.sandbox_v2.models import (
    SandboxV2Decision,
    SandboxV2JobStatus,
    SandboxV2Mode,
    SandboxV2PolicyDecision,
    SandboxV2RiskLevel,
    SandboxPolicyV2,
    SandboxJob,
    MVP_ALLOWED_MODES,
)

logger = logging.getLogger(__name__)

# 高风险动作关键词
_HIGH_RISK_ACTIONS: frozenset[str] = frozenset({
    "execute_code", "run_script", "eval", "exec",
    "subprocess", "os_system", "shell_exec",
    "file_delete", "file_overwrite", "rm_rf",
    "download_executable", "install_package",
    "network_bind", "open_port", "reverse_shell",
    "container_escape", "privilege_escalation",
})


def evaluate_policy(
    job: SandboxJob,
    policy: SandboxPolicyV2 | None = None,
    *,
    requested_network: bool = False,
    requested_filesystem_write: bool = False,
    requested_package_download: bool = False,
    requested_artifact_materialization: bool = False,
    requested_action: str = "",
) -> SandboxV2PolicyDecision:
    """评估 Sandbox v2 策略，返回决策。

    如果 policy 为 None，使用最严格的默认 deny-all 策略。
    如果任何步骤出现异常，返回 fail_closed deny 决策。
    """
    try:
        return _evaluate_policy_impl(
            job=job,
            policy=policy,
            requested_network=requested_network,
            requested_filesystem_write=requested_filesystem_write,
            requested_package_download=requested_package_download,
            requested_artifact_materialization=requested_artifact_materialization,
            requested_action=requested_action,
        )
    except Exception:
        logger.exception("sandbox_v2_policy_evaluation_failed")
        return SandboxV2PolicyDecision(
            allowed=False,
            action=SandboxV2Decision.FAIL_CLOSED,
            reason="Policy evaluation raised an exception — fail closed.",
            risk_level=SandboxV2RiskLevel.CRITICAL,
            required_approvals=["security_admin"],
            matched_rules=["exception_fail_closed"],
            fail_closed=True,
            policy_snapshot=_safe_snapshot(policy),
        )


def _safe_snapshot(policy: SandboxPolicyV2 | None) -> dict[str, Any]:
    if policy is None:
        return {"policy": "default_deny_all"}
    try:
        return policy.to_dict()
    except Exception:
        return {"policy_id": getattr(policy, "policy_id", "unknown"), "error": "snapshot_failed"}


def _evaluate_policy_impl(
    job: SandboxJob,
    policy: SandboxPolicyV2 | None,
    requested_network: bool,
    requested_filesystem_write: bool,
    requested_package_download: bool,
    requested_artifact_materialization: bool,
    requested_action: str,
) -> SandboxV2PolicyDecision:
    matched_rules: list[str] = []
    required_approvals: list[str] = []

    # ── Rule 1: Mode validation ──
    if not job.mode:
        return SandboxV2PolicyDecision(
            allowed=False,
            action=SandboxV2Decision.FAIL_CLOSED,
            reason="Job mode is missing — fail closed.",
            risk_level=SandboxV2RiskLevel.CRITICAL,
            required_approvals=["security_admin"],
            matched_rules=["mode_missing_fail_closed"],
            fail_closed=True,
            policy_snapshot=_safe_snapshot(policy),
        )

    if job.mode not in MVP_ALLOWED_MODES:
        return SandboxV2PolicyDecision(
            allowed=False,
            action=SandboxV2Decision.DENY,
            reason=f"Mode '{job.mode}' is not allowed. Only metadata_only, simulation, disabled are permitted.",
            risk_level=SandboxV2RiskLevel.HIGH,
            required_approvals=["security_admin"],
            matched_rules=["mode_not_allowed"],
            fail_closed=True,
            policy_snapshot=_safe_snapshot(policy),
        )

    matched_rules.append("mode_allowed")

    # ── Rule 2: Disabled mode ──
    if job.mode == SandboxV2Mode.DISABLED:
        return SandboxV2PolicyDecision(
            allowed=False,
            action=SandboxV2Decision.DENY,
            reason="Sandbox execution is disabled.",
            risk_level=SandboxV2RiskLevel.LOW,
            required_approvals=[],
            matched_rules=["mode_disabled"],
            fail_closed=False,
            policy_snapshot=_safe_snapshot(policy),
        )

    # ── Rule 3: Future modes are blocked ──
    if job.mode in (SandboxV2Mode.FUTURE_CONTAINER, SandboxV2Mode.FUTURE_MICROVM):
        return SandboxV2PolicyDecision(
            allowed=False,
            action=SandboxV2Decision.DENY,
            reason=f"Mode '{job.mode}' is reserved for future use and not yet implemented.",
            risk_level=SandboxV2RiskLevel.HIGH,
            required_approvals=["security_admin", "platform_admin"],
            matched_rules=["future_mode_blocked"],
            fail_closed=True,
            policy_snapshot=_safe_snapshot(policy),
        )

    # ── Rule 4: Default policy if none provided ──
    if policy is None:
        policy = SandboxPolicyV2()  # uses default deny-all

    # ── Rule 5: Validate policy has required fields ──
    policy_valid, policy_reason = _validate_policy_fields(policy)
    if not policy_valid:
        return SandboxV2PolicyDecision(
            allowed=False,
            action=SandboxV2Decision.FAIL_CLOSED,
            reason=policy_reason,
            risk_level=SandboxV2RiskLevel.CRITICAL,
            required_approvals=["security_admin"],
            matched_rules=["policy_fields_missing_fail_closed"],
            fail_closed=True,
            policy_snapshot=_safe_snapshot(policy),
        )

    matched_rules.append("policy_fields_valid")

    # ── Rule 6: Default action check ──
    if policy.default_action != SandboxV2Decision.ALLOW:
        return SandboxV2PolicyDecision(
            allowed=False,
            action=SandboxV2Decision.DENY,
            reason=f"Policy default action is '{policy.default_action}'. Explicit allow required.",
            risk_level=SandboxV2RiskLevel.LOW,
            required_approvals=[],
            matched_rules=[*matched_rules, "default_action_deny"],
            fail_closed=False,
            policy_snapshot=policy.to_dict(),
        )

    # ── Rule 7: Network check ──
    if requested_network and not policy.allow_network:
        return SandboxV2PolicyDecision(
            allowed=False,
            action=SandboxV2Decision.DENY,
            reason="Network access is requested but policy does not allow it.",
            risk_level=SandboxV2RiskLevel.MEDIUM,
            required_approvals=["security_admin"],
            matched_rules=[*matched_rules, "network_denied"],
            fail_closed=False,
            policy_snapshot=policy.to_dict(),
        )

    # ── Rule 8: Filesystem write check ──
    if requested_filesystem_write and not policy.allow_write_filesystem:
        return SandboxV2PolicyDecision(
            allowed=False,
            action=SandboxV2Decision.DENY,
            reason="Filesystem write is requested but policy does not allow it.",
            risk_level=SandboxV2RiskLevel.MEDIUM,
            required_approvals=["security_admin"],
            matched_rules=[*matched_rules, "filesystem_write_denied"],
            fail_closed=False,
            policy_snapshot=policy.to_dict(),
        )

    # ── Rule 9: Package download check ──
    if requested_package_download and not policy.allow_package_download:
        return SandboxV2PolicyDecision(
            allowed=False,
            action=SandboxV2Decision.DENY,
            reason="Package download is requested but policy does not allow it.",
            risk_level=SandboxV2RiskLevel.MEDIUM,
            required_approvals=["security_admin"],
            matched_rules=[*matched_rules, "package_download_denied"],
            fail_closed=False,
            policy_snapshot=policy.to_dict(),
        )

    # ── Rule 10: Artifact materialization check ──
    if requested_artifact_materialization and not policy.allow_artifact_materialization:
        return SandboxV2PolicyDecision(
            allowed=False,
            action=SandboxV2Decision.DENY,
            reason="Artifact materialization is requested but policy does not allow it.",
            risk_level=SandboxV2RiskLevel.MEDIUM,
            required_approvals=["security_admin"],
            matched_rules=[*matched_rules, "artifact_materialization_denied"],
            fail_closed=False,
            policy_snapshot=policy.to_dict(),
        )

    # ── Rule 11: High-risk action detection ──
    action_lower = requested_action.lower().replace("-", "_").replace(" ", "_")
    for high_risk in _HIGH_RISK_ACTIONS:
        if high_risk in action_lower:
            return SandboxV2PolicyDecision(
                allowed=False,
                action=SandboxV2Decision.DENY,
                reason=f"Requested action '{requested_action}' matches high-risk pattern '{high_risk}'.",
                risk_level=SandboxV2RiskLevel.HIGH,
                required_approvals=["security_admin"],
                matched_rules=[*matched_rules, "high_risk_action_denied"],
                fail_closed=True,
                policy_snapshot=policy.to_dict(),
            )

    # ── Rule 12: Unrecognized action (default deny) ──
    if requested_action and not _is_recognized_action(requested_action):
        return SandboxV2PolicyDecision(
            allowed=False,
            action=SandboxV2Decision.DENY,
            reason=f"Requested action '{requested_action}' is not recognized — default deny.",
            risk_level=SandboxV2RiskLevel.MEDIUM,
            required_approvals=["security_admin"],
            matched_rules=[*matched_rules, "unrecognized_action_denied"],
            fail_closed=True,
            policy_snapshot=policy.to_dict(),
        )

    # ── Rule 13: Human approval check ──
    if policy.require_human_approval:
        required_approvals.append("human_approval")

    # ── All checks passed ──
    matched_rules.append("all_checks_passed")
    return SandboxV2PolicyDecision(
        allowed=True,
        action=SandboxV2Decision.ALLOW,
        reason=f"All policy checks passed for mode '{job.mode}'.",
        risk_level=SandboxV2RiskLevel.LOW,
        required_approvals=required_approvals,
        matched_rules=matched_rules,
        fail_closed=False,
        policy_snapshot=policy.to_dict(),
    )


def _validate_policy_fields(policy: SandboxPolicyV2) -> tuple[bool, str]:
    """验证策略对象是否有必需的字段。缺失字段 → fail closed。"""
    required_fields = [
        "policy_id", "default_action", "allow_network",
        "allow_write_filesystem", "allow_package_download",
        "allow_artifact_materialization", "require_human_approval",
    ]
    for field_name in required_fields:
        try:
            val = getattr(policy, field_name, None)
            if val is None:
                return False, f"Policy field '{field_name}' is None — fail closed."
        except Exception:
            return False, f"Policy field '{field_name}' is inaccessible — fail closed."

    # 验证嵌套对象存在
    for nested in ["resource_limits", "network_policy", "filesystem_policy", "artifact_policy", "package_policy"]:
        try:
            if getattr(policy, nested, None) is None:
                return False, f"Policy nested object '{nested}' is None — fail closed."
        except Exception:
            return False, f"Policy nested object '{nested}' is inaccessible — fail closed."

    return True, ""


# 可识别的安全动作
_SAFE_ACTIONS: frozenset[str] = frozenset({
    "metadata_validate", "simulate", "dry_run",
    "policy_check", "audit_query", "status_check",
    "readiness_check", "list_jobs", "cancel_job",
    "get_job_status", "get_execution_record",
    "metadata_only", "simulation",
    "",  # 允许空 action（metadata_only/simulation 场景）
})


def _is_recognized_action(action: str) -> bool:
    """判断 action 是否在可识别的安全动作列表中。"""
    if not action:
        return True
    normalized = action.lower().replace("-", "_").replace(" ", "_")
    return normalized in _SAFE_ACTIONS
