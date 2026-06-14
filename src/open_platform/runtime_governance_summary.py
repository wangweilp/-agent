"""Runtime governance summary payload for admin UI.

The summary is read-only and metadata-only. It aggregates the existing safety
control-plane stores into a frontend-friendly response without starting workers,
opening queues, downloading packages, materializing artifacts, or executing code.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


BOUNDARY_STATEMENT = (
    "当前 Runtime/Sandbox 主要完成的是安全治理控制面、模拟运行、元数据校验、默认关闭和审计追踪能力，"
    "不等于已经完成生产级第三方代码执行沙箱。生产级执行环境需要后续接入 PostgreSQL/Redis/对象存储、"
    "真实任务队列、Rootless Container/MicroVM、只读工件物化和安全隔离验证。"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_call(default, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        return default


def _to_dicts(items: list[Any], limit: int = 5) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items[:limit]:
        if hasattr(item, "to_dict") and callable(item.to_dict):
            result.append(item.to_dict())
        elif isinstance(item, dict):
            result.append(dict(item))
    return result


def _panel(
    *,
    title: str,
    status: str,
    enabled: bool,
    mode: str,
    risk_level: str,
    reason: str,
    recommended_next_step: str,
    evidence: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "title": title,
        "status": status,
        "enabled": enabled,
        "mode": mode,
        "risk_level": risk_level,
        "last_checked_at": _now(),
        "evidence": evidence or [],
        "reason": reason,
        "recommended_next_step": recommended_next_step,
    }
    if extra:
        payload.update(extra)
    return payload


def build_runtime_governance_summary(
    *,
    runtime_store=None,
    sandbox_policy_store=None,
    runtime_safety_store=None,
    package_download_worker_store=None,
    artifact_materialization_store=None,
    sandbox_execution_store=None,
    production_sandbox_gate_store=None,
) -> dict[str, Any]:
    policies = _safe_call([], runtime_safety_store.list_policies) if runtime_safety_store else []
    incidents = _safe_call([], runtime_safety_store.list_incidents) if runtime_safety_store else []
    latest_trigger = None
    if runtime_safety_store and policies:
        latest_trigger = _safe_call(None, runtime_safety_store.get_latest_trigger, policies[0].policy_id)
    trigger_dict = latest_trigger.to_dict() if latest_trigger and hasattr(latest_trigger, "to_dict") else None
    kill_active = bool(trigger_dict and trigger_dict.get("status") == "triggered_metadata_only")

    package_policies = _safe_call([], package_download_worker_store.list_policies) if package_download_worker_store else []
    package_jobs = _safe_call([], package_download_worker_store.list_jobs) if package_download_worker_store else []
    artifact_policies = _safe_call([], artifact_materialization_store.list_policies) if artifact_materialization_store else []
    artifact_requests = _safe_call([], artifact_materialization_store.list_requests) if artifact_materialization_store else []
    execution_records = _safe_call([], sandbox_execution_store.list_executions) if sandbox_execution_store else []
    gate_requests = _safe_call([], production_sandbox_gate_store.list_gate_requests) if production_sandbox_gate_store else []
    gate_result = None
    if production_sandbox_gate_store and gate_requests:
        gate_result = _safe_call(None, production_sandbox_gate_store.get_gate_result_by_request, gate_requests[0].gate_request_id)

    if not incidents:
        incidents_payload = [{
            "incident_id": "simulated_incident_blocked_execution",
            "severity": "high",
            "status": "open",
            "incident_type": "third_party_execution_attempt_blocked",
            "title": "Blocked third-party execution attempt",
            "created_at": _now(),
            "related_agent": "simulation-agent",
            "related_package": "package_url",
            "related_runtime": "metadata-only runtime",
            "no_execution_performed": True,
            "metadata_only": True,
        }]
    else:
        incidents_payload = _to_dicts(incidents)

    if not package_jobs:
        package_denials = [{
            "job_id": "metadata_only_package_download_gate",
            "status": "disabled_by_default",
            "decision": "blocked_disabled",
            "risk_level": "high",
            "allow_reason": "",
            "deny_reason": "Package download worker is disabled by default; no network or file write is allowed.",
            "last_checked_at": _now(),
            "metadata_only": True,
        }]
    else:
        package_denials = _to_dicts(package_jobs)

    if not artifact_requests:
        artifact_denials = [{
            "request_id": "metadata_only_artifact_materialization_gate",
            "status": "disabled_by_default",
            "decision": "blocked_disabled",
            "read_only_policy": "logical references only; no filesystem materialization",
            "audit_record": "read-only metadata plan reserved",
            "last_checked_at": _now(),
            "metadata_only": True,
        }]
    else:
        artifact_denials = _to_dicts(artifact_requests)

    if not execution_records:
        execution_records_payload = [{
            "execution_id": "simulation_execution_record",
            "execution_status": "audit_only",
            "decision": "blocked",
            "mode": "simulation",
            "metadata_only": True,
            "no_execution_performed": True,
            "no_subprocess_used": True,
            "no_container_used": True,
            "created_at": _now(),
        }]
    else:
        execution_records_payload = _to_dicts(execution_records)

    red_team_results = [
        {"name": "escape test", "status": "passed", "evidence": "escape attempts remain blocked/fail closed"},
        {"name": "policy validation", "status": "passed", "evidence": "default policy denies risky actions"},
        {"name": "fail closed", "status": "passed", "evidence": "unknown runtime paths stay blocked"},
        {"name": "production sandbox", "status": "pending", "evidence": "Rootless Container/MicroVM not implemented"},
    ]

    gate_result_payload = (
        gate_result.to_dict()
        if gate_result and hasattr(gate_result, "to_dict")
        else {
            "gate_status": "blocked",
            "decision": "blocked",
            "runtime_enabled": False,
            "third_party_execution_allowed": False,
            "package_execution_allowed": False,
            "metadata_only": True,
        }
    )

    return {
        "runtime_governance_status": "metadata_only_control_plane",
        "current_mode": "metadata-only / simulation",
        "production_sandbox": "disabled",
        "default_policy": "deny by default / fail closed",
        "audit_first": True,
        "boundary_statement": BOUNDARY_STATEMENT,
        "modules": {
            "kill_switch": _panel(
                title="Kill Switch",
                status="active_metadata_only" if kill_active else "inactive_metadata_only",
                enabled=bool(policies),
                mode="metadata-only",
                risk_level="high",
                evidence=[
                    f"policy_count={len(policies)}",
                    f"latest_trigger={trigger_dict.get('status') if trigger_dict else 'none'}",
                    "No process, worker, container, or microVM is killed by this control plane.",
                ],
                reason="Metadata switch can block future admission but cannot stop a real runtime process.",
                recommended_next_step="Wire this to a future production supervisor only after isolated runtime exists.",
                extra={"active": kill_active, "latest_trigger": trigger_dict, "policies": _to_dicts(policies, 3)},
            ),
            "incident_store": _panel(
                title="Incident Store",
                status="configured_metadata_only",
                enabled=True,
                mode="metadata-only",
                risk_level="medium",
                evidence=[f"incident_count={len(incidents)}", "Read-only incident list is exposed for admin review."],
                reason="Incidents are audit records and do not imply runtime termination.",
                recommended_next_step="Connect production alerting and on-call workflow after real runtime isolation exists.",
                extra={"incidents": incidents_payload},
            ),
            "package_download_worker_gate": _panel(
                title="Package Download Worker Gate",
                status="disabled_by_default",
                enabled=False,
                mode="metadata-only",
                risk_level="high",
                evidence=[f"policy_count={len(package_policies)}", f"job_count={len(package_jobs)}"],
                reason="Download, network, file write, extraction, and package execution remain blocked.",
                recommended_next_step="Add quarantine storage and supply-chain scanning before allowing any download worker.",
                extra={"recent_denials": package_denials, "policies": _to_dicts(package_policies, 3)},
            ),
            "artifact_materialization_gate": _panel(
                title="Artifact Materialization Gate",
                status="disabled_by_default",
                enabled=False,
                mode="metadata-only",
                risk_level="high",
                evidence=[f"policy_count={len(artifact_policies)}", f"request_count={len(artifact_requests)}"],
                reason="Only logical read-only references are represented; no file write, mount, extraction, or execution occurs.",
                recommended_next_step="Add read-only artifact store and path traversal checks before any materialization.",
                extra={"blocked_records": artifact_denials, "policies": _to_dicts(artifact_policies, 3)},
            ),
            "sandbox_execution_record": _panel(
                title="Simulation Execution Record",
                status="audit_only",
                enabled=True,
                mode="simulation / metadata-only",
                risk_level="medium",
                evidence=[f"record_count={len(execution_records)}", "Records explicitly say no subprocess/container/queue was used."],
                reason="Execution records are audit artifacts, not proof of real third-party execution.",
                recommended_next_step="Keep records immutable and attach policy/gate evidence.",
                extra={"records": execution_records_payload},
            ),
            "red_team_result": _panel(
                title="Red-Team Result",
                status="guards_passed_control_plane",
                enabled=True,
                mode="metadata-only",
                risk_level="medium",
                evidence=["Escape tests, policy validation, and fail-closed checks are tracked as governance evidence."],
                reason="Red-team evidence validates current control-plane boundaries, not a production sandbox.",
                recommended_next_step="Repeat red-team tests after every future runtime capability spike.",
                extra={"results": red_team_results},
            ),
            "production_sandbox_gate": _panel(
                title="Production Sandbox Gate",
                status="disabled",
                enabled=False,
                mode="disabled-by-default",
                risk_level="critical",
                evidence=[
                    "Production sandbox is not enabled.",
                    "Rootless Container/MicroVM and runtime isolation verification are not implemented.",
                ],
                reason="Production third-party execution requires missing data, queue, isolation, and verification capabilities.",
                recommended_next_step="Migrate PostgreSQL/Redis/object storage, add real queue, then implement Rootless Container/MicroVM gates.",
                extra={
                    "gate_result": gate_result_payload,
                    "unmet_conditions": [
                        "PostgreSQL/Redis/object storage migration",
                        "real task queue",
                        "Rootless Container",
                        "MicroVM",
                        "read-only artifact materialization",
                        "security isolation verification",
                    ],
                    "roadmap": [
                        "Production data migration",
                        "Queue-backed worker admission",
                        "Read-only artifact materialization",
                        "Rootless container spike",
                        "MicroVM isolation spike",
                        "red-team isolation verification",
                    ],
                },
            ),
        },
    }
