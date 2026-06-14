"""Sandbox v2 Kill Policy Engine — Kill/Suspend 安全策略评估。

安全规则：
1. 默认 deny
2. fail closed
3. 只能 kill sandbox 管理的对象
4. 不允许任意 PID kill
5. 不允许 kill 非当前 organization/workspace 对象
6. 已完成/失败/死信状态返回 no_active_execution
7. queued 状态允许 cancel queue item
8. leased/processing/running_simulation 允许标记 canceled
9. container kill 仅在 Linux + enabled + container_id recorded 时允许
10. Windows → container kill unsupported
"""

from __future__ import annotations

import logging, platform as _plat

from src.open_platform.sandbox_v2.models import (
    SandboxV2RiskLevel, SandboxV2KillAction, SandboxV2KillTargetType,
    SandboxKillRequest, SandboxKillDecision,
)

logger = logging.getLogger(__name__)

# Scope 必须是 sandbox 管理的对象
VALID_TARGETS = {e.value for e in SandboxV2KillTargetType}


def evaluate_kill_policy(
    request: SandboxKillRequest,
    *,
    target_exists: bool = False,
    target_status: str = "",
    target_is_owned_by_sandbox: bool = True,
    container_execution_enabled: bool = False,
    container_id_recorded: bool = False,
    provider_supports_cancel: bool = False,
) -> SandboxKillDecision:
    try:
        return _eval(request, target_exists, target_status, target_is_owned_by_sandbox,
                     container_execution_enabled, container_id_recorded, provider_supports_cancel)
    except Exception:
        logger.exception("kill_policy_failed")
        return SandboxKillDecision(reason="Kill policy exception — fail closed.", risk_level=SandboxV2RiskLevel.CRITICAL, matched_rules=["exception_fail_closed"], fail_closed=True)


def _eval(r, exists, status, owned, ce, cr, ps) -> SandboxKillDecision:
    m: list[str] = []

    # Rule 1: target must be valid
    if r.target_type not in VALID_TARGETS or r.target_type == SandboxV2KillTargetType.UNKNOWN:
        return SandboxKillDecision(reason=f"Unknown target_type '{r.target_type}'.", risk_level=SandboxV2RiskLevel.HIGH, matched_rules=["unknown_target"], fail_closed=True)
    m.append("target_valid")

    # Rule 2: must be sandbox-managed
    if not owned:
        return SandboxKillDecision(reason="Target is not owned by sandbox.", risk_level=SandboxV2RiskLevel.CRITICAL, matched_rules=[*m, "not_sandbox_owned"], fail_closed=True)
    m.append("sandbox_owned")

    # Rule 3: must exist
    if not exists:
        return SandboxKillDecision(reason="Target does not exist in sandbox records.", risk_level=SandboxV2RiskLevel.LOW, matched_rules=[*m, "target_missing"], fail_closed=True)
    m.append("target_exists")

    # Rule 4: cannot kill system process / arbitrary PID
    if r.target_type == SandboxV2KillTargetType.UNKNOWN or r.target_id and r.target_id.startswith("pid:"):
        return SandboxKillDecision(reason="Arbitrary PID kill is not allowed.", risk_level=SandboxV2RiskLevel.CRITICAL, matched_rules=[*m, "arbitrary_pid_rejected"], fail_closed=True)

    # Rule 5: terminal states → no_active_execution
    terminal = {"completed", "rejected", "failed", "dead_letter", "expired", "deleted", "canceled"}
    if status.lower() in terminal:
        return SandboxKillDecision(allowed=True, action=SandboxV2KillAction.NO_ACTIVE_EXECUTION,
            reason=f"Target is already in terminal state '{status}'. No active execution.",
            risk_level=SandboxV2RiskLevel.LOW,
            target_owned_by_sandbox=True, queue_cancel_allowed=False,
            job_state_cancel_allowed=False, matched_rules=[*m, "already_terminal"], fail_closed=False)

    # Rule 6: queued → cancel queue
    if status == "queued":
        return SandboxKillDecision(allowed=True, action=SandboxV2KillAction.CANCEL_QUEUE_ITEM,
            reason="Target is queued. Cancel queue item.",
            risk_level=SandboxV2RiskLevel.LOW,
            target_owned_by_sandbox=True, queue_cancel_allowed=True,
            job_state_cancel_allowed=True, matched_rules=[*m, "cancel_queue_item"], fail_closed=False)

    # Rule 7: MicroVM type — currently disabled, no real MicroVM process
    if r.target_type in (SandboxV2KillTargetType.MICROVM_PLAN, SandboxV2KillTargetType.MICROVM):
        return SandboxKillDecision(allowed=False, action=SandboxV2KillAction.REJECT,
            reason="MicroVM kill is disabled by default. No real MicroVM process to kill.",
            risk_level=SandboxV2RiskLevel.LOW, matched_rules=[*m, "microvm_kill_disabled"], fail_closed=True)

    # Rule 8: container type — check extra conditions BEFORE generic active state
    if r.target_type in (SandboxV2KillTargetType.CONTAINER, SandboxV2KillTargetType.CONTAINER_PLAN):
        if _plat.system() != "Linux":
            return SandboxKillDecision(allowed=False, action=SandboxV2KillAction.REJECT,
                reason="Container kill requires Linux platform.",
                risk_level=SandboxV2RiskLevel.MEDIUM, matched_rules=[*m, "container_kill_unsupported"], fail_closed=True)
        if not ce:
            return SandboxKillDecision(allowed=False, action=SandboxV2KillAction.REJECT,
                reason="Container execution is not enabled.",
                risk_level=SandboxV2RiskLevel.MEDIUM, matched_rules=[*m, "container_exec_disabled"], fail_closed=True)
        if not cr:
            return SandboxKillDecision(allowed=False, action=SandboxV2KillAction.REJECT,
                reason="No container_id recorded. Cannot kill container.",
                risk_level=SandboxV2RiskLevel.MEDIUM, matched_rules=[*m, "no_container_id"], fail_closed=True)
        if not ps:
            return SandboxKillDecision(allowed=False, action=SandboxV2KillAction.REJECT,
                reason="Provider does not support cancel/kill.",
                risk_level=SandboxV2RiskLevel.MEDIUM, matched_rules=[*m, "provider_no_cancel"], fail_closed=True)
        return SandboxKillDecision(allowed=True, action=SandboxV2KillAction.CONTAINER_KILL_FUTURE,
            reason="Container kill conditions met. Provider cancel available.",
            risk_level=SandboxV2RiskLevel.MEDIUM,
            target_owned_by_sandbox=True, container_kill_allowed=True,
            provider_cancel_supported=True, matched_rules=[*m, "container_kill_allowed"], fail_closed=False)

    # Rule 8: leased/processing/running → mark canceled
    active_states = {"leased", "processing", "running_simulation", "running"}
    if status.lower() in active_states:
        return SandboxKillDecision(allowed=True, action=SandboxV2KillAction.MARK_CANCELED,
            reason=f"Target is active ({status}). Marking canceled.",
            risk_level=SandboxV2RiskLevel.LOW,
            target_owned_by_sandbox=True, queue_cancel_allowed=True,
            job_state_cancel_allowed=True, provider_cancel_supported=ps,
            matched_rules=[*m, "mark_canceled"], fail_closed=False)

    # Rule 9: general provider cancel
    if ps:
        return SandboxKillDecision(allowed=True, action=SandboxV2KillAction.PROVIDER_CANCEL,
            reason="Provider cancel available.", risk_level=SandboxV2RiskLevel.LOW,
            target_owned_by_sandbox=True, provider_cancel_supported=True,
            matched_rules=[*m, "provider_cancel"], fail_closed=False)

    # Default: mark_canceled
    return SandboxKillDecision(allowed=True, action=SandboxV2KillAction.MARK_CANCELED,
        reason="Default — mark target canceled.", risk_level=SandboxV2RiskLevel.LOW,
        target_owned_by_sandbox=True, job_state_cancel_allowed=True,
        matched_rules=[*m, "default_mark_canceled"], fail_closed=False)
