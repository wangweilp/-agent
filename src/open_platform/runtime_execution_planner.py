"""Runtime Execution Planner Service — 创建执行计划（不执行）。

Step 24-D:
- 20 preflight checks
- snapshots (policy/artifact/verification)
- input_payload_hash (no raw input)
- is_dispatchable() always False
- 不执行 / 不派发 / 不 worker / 不联网
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.open_platform.runtime_execution_plan import (
    RuntimeExecutionMode, RuntimeExecutionPlan, RuntimeExecutionPlanCheck,
    RuntimeDispatchStatus, RuntimePlanCheckStatus, RuntimePlanCheckType,
    RuntimePlanDecision, RuntimePlanSeverity, RuntimeExecutionRiskLevel,
    RuntimeExecutionPlanStatus,
)
from src.open_platform.runtime import (
    RuntimeBindingStatus, RuntimeAdapterStatus, is_mvp_allowed_adapter_type,
)

logger = logging.getLogger(__name__)

_PUBLISHER_TYPE_DEVELOPER = "developer"


class RuntimeExecutionPlannerService:
    """创建 runtime execution plan — 只做 preflight checks，不做执行。"""

    def __init__(
        self, *,
        plan_store=None, marketplace_store=None, runtime_store=None,
        sandbox_policy_store=None, artifact_store=None, verification_store=None,
        usage_store=None,
    ):
        self._plan_store = plan_store
        self._marketplace_store = marketplace_store
        self._runtime_store = runtime_store
        self._sandbox_policy_store = sandbox_policy_store
        self._artifact_store = artifact_store
        self._verification_store = verification_store
        self._usage_store = usage_store

    def create_plan(
        self, marketplace_agent_id: str, tenant_id: str, requested_by: str,
        *, user_id: str | None = None, input_payload: dict | None = None,
        execution_mode: str = RuntimeExecutionMode.SANDBOX_RESERVED,
    ) -> RuntimeExecutionPlan:
        if self._plan_store is None:
            raise ValueError("plan_store not available")

        plan = RuntimeExecutionPlan(
            marketplace_agent_id=marketplace_agent_id, tenant_id=tenant_id,
            user_id=user_id, created_by=requested_by,
            execution_mode=execution_mode,
            dispatch_status=RuntimeDispatchStatus.RESERVED_FOR_STEP24E,
            plan_status=RuntimeExecutionPlanStatus.DRAFT,
            no_download_planned=True, no_network_planned=True, no_execution_performed=True,
            worker_available=False,
            worker_required=(execution_mode == RuntimeExecutionMode.SANDBOX_RESERVED),
            input_payload_hash=RuntimeExecutionPlan.hash_payload(input_payload),
        )

        # ── Phase 0: Safety checks (always) ──
        plan.add_check(_chk(RuntimePlanCheckType.NO_DOWNLOAD_IN_PLAN, RuntimePlanCheckStatus.PASSED,
                            RuntimePlanSeverity.INFO, "No package download in this plan."))
        plan.add_check(_chk(RuntimePlanCheckType.NO_NETWORK_IN_PLAN, RuntimePlanCheckStatus.PASSED,
                            RuntimePlanSeverity.INFO, "No network calls in this plan."))
        plan.add_check(_chk(RuntimePlanCheckType.NO_EXECUTION_IN_PLAN, RuntimePlanCheckStatus.PASSED,
                            RuntimePlanSeverity.INFO, "No code execution in this plan."))

        # ── Phase 1: Marketplace ──
        agent = self._get_agent(marketplace_agent_id)
        if agent is None:
            plan.add_check(_chk(RuntimePlanCheckType.MARKETPLACE_AGENT_EXISTS, RuntimePlanCheckStatus.BLOCKED,
                                RuntimePlanSeverity.BLOCKER, f"Marketplace agent '{marketplace_agent_id}' not found."))
            return self._finalize(plan, requested_by)
        plan.add_check(_chk(RuntimePlanCheckType.MARKETPLACE_AGENT_EXISTS, RuntimePlanCheckStatus.PASSED,
                            RuntimePlanSeverity.INFO, f"Marketplace agent found: {getattr(agent, 'display_name', '')}"))

        pub_type = getattr(agent, "publisher_type", "")
        if pub_type != _PUBLISHER_TYPE_DEVELOPER:
            plan.add_check(_chk(RuntimePlanCheckType.MARKETPLACE_AGENT_IS_DEVELOPER, RuntimePlanCheckStatus.BLOCKED,
                                RuntimePlanSeverity.BLOCKER, f"Agent publisher_type='{pub_type}', not 'developer'."))
            return self._finalize(plan, requested_by)
        plan.add_check(_chk(RuntimePlanCheckType.MARKETPLACE_AGENT_IS_DEVELOPER, RuntimePlanCheckStatus.PASSED,
                            RuntimePlanSeverity.INFO, "Agent is a developer agent."))

        # ── Phase 2: Installation ──
        inst = self._get_installation(marketplace_agent_id, tenant_id)
        if inst is None:
            plan.add_check(_chk(RuntimePlanCheckType.TENANT_INSTALLATION_ACTIVE, RuntimePlanCheckStatus.BLOCKED,
                                RuntimePlanSeverity.BLOCKER, "No active installation found."))
            return self._finalize(plan, requested_by)
        if not getattr(inst, "enabled", False) or getattr(inst, "status", "") not in ("active",):
            plan.add_check(_chk(RuntimePlanCheckType.TENANT_INSTALLATION_ACTIVE, RuntimePlanCheckStatus.BLOCKED,
                                RuntimePlanSeverity.BLOCKER, f"Installation not active: enabled={getattr(inst, 'enabled', False)}, status={getattr(inst, 'status', '')}"))
            return self._finalize(plan, requested_by)
        plan.add_check(_chk(RuntimePlanCheckType.TENANT_INSTALLATION_ACTIVE, RuntimePlanCheckStatus.PASSED,
                            RuntimePlanSeverity.INFO, "Installation is active and enabled."))

        # Permissions
        granted = list(getattr(inst, "permissions_granted", []))
        required = list(getattr(agent, "required_permissions", []))
        missing = [p for p in required if p not in granted]
        if missing:
            plan.add_check(_chk(RuntimePlanCheckType.REQUIRED_PERMISSIONS_GRANTED, RuntimePlanCheckStatus.BLOCKED,
                                RuntimePlanSeverity.BLOCKER, f"Permissions missing: {missing}"))
            return self._finalize(plan, requested_by)
        plan.add_check(_chk(RuntimePlanCheckType.REQUIRED_PERMISSIONS_GRANTED, RuntimePlanCheckStatus.PASSED,
                            RuntimePlanSeverity.INFO, "All required permissions granted."))

        plan.developer_id = agent.metadata.get("developer_id", "") if hasattr(agent, "metadata") else ""

        # ── Phase 3: Runtime Binding ──
        binding = None
        if self._runtime_store:
            try:
                binding = self._runtime_store.get_binding_by_marketplace_agent(marketplace_agent_id, tenant_id)
            except Exception:
                pass
        if binding is None:
            plan.add_check(_chk(RuntimePlanCheckType.RUNTIME_BINDING_EXISTS, RuntimePlanCheckStatus.BLOCKED,
                                RuntimePlanSeverity.BLOCKER, "No runtime binding found."))
            return self._finalize(plan, requested_by)
        plan.runtime_binding_id = getattr(binding, "binding_id", None)
        plan.add_check(_chk(RuntimePlanCheckType.RUNTIME_BINDING_EXISTS, RuntimePlanCheckStatus.PASSED,
                            RuntimePlanSeverity.INFO, f"Runtime binding found: {plan.runtime_binding_id}"))

        if not getattr(binding, "is_enabled", None) or (
            hasattr(binding, "is_enabled") and callable(binding.is_enabled) and not binding.is_enabled()):
            plan.add_check(_chk(RuntimePlanCheckType.RUNTIME_BINDING_ENABLED, RuntimePlanCheckStatus.BLOCKED,
                                RuntimePlanSeverity.BLOCKER, f"Binding status={getattr(binding, 'runtime_status', '')}"))
            return self._finalize(plan, requested_by)
        plan.add_check(_chk(RuntimePlanCheckType.RUNTIME_BINDING_ENABLED, RuntimePlanCheckStatus.PASSED,
                            RuntimePlanSeverity.INFO, "Runtime binding is enabled."))

        # Adapter
        adapter_id = getattr(binding, "adapter_id", None)
        adapter = None
        if adapter_id and self._runtime_store:
            try: adapter = self._runtime_store.get_adapter(adapter_id)
            except Exception: pass
        if adapter is None:
            plan.add_check(_chk(RuntimePlanCheckType.RUNTIME_ADAPTER_ALLOWED, RuntimePlanCheckStatus.BLOCKED,
                                RuntimePlanSeverity.BLOCKER, f"Adapter not found: {adapter_id}"))
            return self._finalize(plan, requested_by)
        plan.adapter_id = getattr(adapter, "adapter_id", None)
        plan.adapter_type = getattr(adapter, "adapter_type", None)

        adapter_type = plan.adapter_type or ""
        if execution_mode == RuntimeExecutionMode.SANDBOX_RESERVED:
            # SANDBOX_RESERVED: allow all adapter types for future planning
            plan.add_check(_chk(RuntimePlanCheckType.RUNTIME_ADAPTER_ALLOWED, RuntimePlanCheckStatus.PASSED,
                                RuntimePlanSeverity.INFO,
                                f"Adapter '{adapter_type}' accepted for sandbox_reserved plan."))
        elif not is_mvp_allowed_adapter_type(adapter_type):
            plan.add_check(_chk(RuntimePlanCheckType.RUNTIME_ADAPTER_ALLOWED, RuntimePlanCheckStatus.BLOCKED,
                                RuntimePlanSeverity.BLOCKER, f"Adapter type '{adapter_type}' not allowed for this mode."))
            return self._finalize(plan, requested_by)
        else:
            plan.add_check(_chk(RuntimePlanCheckType.RUNTIME_ADAPTER_ALLOWED, RuntimePlanCheckStatus.PASSED,
                                RuntimePlanSeverity.INFO, f"Adapter '{adapter_type}' is allowed."))

        # ── Phase 4: Sandbox Policy ──
        policy_id = getattr(binding, "sandbox_policy_id", None)
        policy = None
        if policy_id and self._sandbox_policy_store:
            try: policy = self._sandbox_policy_store.get_policy(policy_id)
            except Exception: pass
        if policy is None:
            plan.add_check(_chk(RuntimePlanCheckType.SANDBOX_POLICY_EXISTS, RuntimePlanCheckStatus.BLOCKED,
                                RuntimePlanSeverity.BLOCKER, f"Sandbox policy not found: {policy_id}"))
            return self._finalize(plan, requested_by)
        plan.sandbox_policy_id = policy_id
        plan.add_check(_chk(RuntimePlanCheckType.SANDBOX_POLICY_EXISTS, RuntimePlanCheckStatus.PASSED,
                            RuntimePlanSeverity.INFO, f"Sandbox policy found: {policy_id}"))

        if not getattr(policy, "is_active", None) or (callable(getattr(policy, "is_active", None)) and not policy.is_active()):
            plan.add_check(_chk(RuntimePlanCheckType.SANDBOX_POLICY_ACTIVE, RuntimePlanCheckStatus.BLOCKED,
                                RuntimePlanSeverity.BLOCKER, f"Policy status={getattr(policy, 'status', '')}"))
            return self._finalize(plan, requested_by)
        plan.add_check(_chk(RuntimePlanCheckType.SANDBOX_POLICY_ACTIVE, RuntimePlanCheckStatus.PASSED,
                            RuntimePlanSeverity.INFO, "Sandbox policy is active."))
        plan.policy_snapshot = self._safe_dict(getattr(policy, "to_dict", lambda: {})())

        # ── Phase 5: Artifact ──
        submission_id = agent.metadata.get("submission_id", "") if hasattr(agent, "metadata") else ""
        plan.submission_id = submission_id
        artifact = None
        if submission_id and self._artifact_store:
            try: artifact = self._artifact_store.get_artifact_by_submission(submission_id)
            except Exception: pass
        if artifact is None:
            plan.add_check(_chk(RuntimePlanCheckType.ARTIFACT_DECLARED, RuntimePlanCheckStatus.BLOCKED,
                                RuntimePlanSeverity.BLOCKER, f"No artifact for submission {submission_id}"))
            return self._finalize(plan, requested_by)
        plan.artifact_id = getattr(artifact, "artifact_id", None)
        plan.add_check(_chk(RuntimePlanCheckType.ARTIFACT_DECLARED, RuntimePlanCheckStatus.PASSED,
                            RuntimePlanSeverity.INFO, f"Artifact found: {plan.artifact_id}"))

        art_status = getattr(artifact, "artifact_status", "")
        if art_status in ("rejected", "disabled"):
            plan.add_check(_chk(RuntimePlanCheckType.ARTIFACT_NOT_REJECTED, RuntimePlanCheckStatus.BLOCKED,
                                RuntimePlanSeverity.BLOCKER, f"Artifact status='{art_status}'"))
            return self._finalize(plan, requested_by)
        plan.add_check(_chk(RuntimePlanCheckType.ARTIFACT_NOT_REJECTED, RuntimePlanCheckStatus.PASSED,
                            RuntimePlanSeverity.INFO, f"Artifact status='{art_status}' acceptable."))

        q_status = getattr(artifact, "quarantine_status", "")
        if q_status in ("rejected", "expired"):
            plan.add_check(_chk(RuntimePlanCheckType.ARTIFACT_QUARANTINE_ACCEPTABLE, RuntimePlanCheckStatus.BLOCKED,
                                RuntimePlanSeverity.BLOCKER, f"Quarantine status='{q_status}'"))
            return self._finalize(plan, requested_by)
        plan.add_check(_chk(RuntimePlanCheckType.ARTIFACT_QUARANTINE_ACCEPTABLE, RuntimePlanCheckStatus.PASSED,
                            RuntimePlanSeverity.INFO, f"Quarantine status='{q_status}' acceptable."))
        plan.artifact_snapshot = self._safe_dict(getattr(artifact, "to_dict", lambda: {})())

        # ── Phase 6: Verification ──
        run = None
        if plan.artifact_id and self._verification_store:
            try: run = self._verification_store.get_latest_run_for_artifact(plan.artifact_id)
            except Exception: pass
        if run is None:
            plan.add_check(_chk(RuntimePlanCheckType.PACKAGE_VERIFICATION_EXISTS, RuntimePlanCheckStatus.BLOCKED,
                                RuntimePlanSeverity.BLOCKER, "No verification run found."))
            return self._finalize(plan, requested_by)
        plan.verification_id = getattr(run, "verification_id", None)
        plan.add_check(_chk(RuntimePlanCheckType.PACKAGE_VERIFICATION_EXISTS, RuntimePlanCheckStatus.PASSED,
                            RuntimePlanSeverity.INFO, f"Verification run: {plan.verification_id}"))

        run_status = getattr(run, "run_status", "")
        has_cs_match = any(getattr(c, "check_type", "") == "checksum_match" and
                          getattr(c, "status", "") == "passed" for c in getattr(run, "checks", []))
        if has_cs_match:
            plan.add_check(_chk(RuntimePlanCheckType.CHECKSUM_VERIFIED_OR_PENDING_POLICY, RuntimePlanCheckStatus.PASSED,
                                RuntimePlanSeverity.INFO, "Checksum verified."))
        elif run_status in ("passed", "passed_with_warnings"):
            plan.add_check(_chk(RuntimePlanCheckType.CHECKSUM_VERIFIED_OR_PENDING_POLICY, RuntimePlanCheckStatus.WARNING,
                                RuntimePlanSeverity.WARNING, "Checksum not verified; pending review."))
        elif run_status in ("blocked", "failed"):
            plan.add_check(_chk(RuntimePlanCheckType.CHECKSUM_VERIFIED_OR_PENDING_POLICY, RuntimePlanCheckStatus.BLOCKED,
                                RuntimePlanSeverity.BLOCKER, f"Verification status='{run_status}'"))
            return self._finalize(plan, requested_by)
        else:
            plan.add_check(_chk(RuntimePlanCheckType.CHECKSUM_VERIFIED_OR_PENDING_POLICY, RuntimePlanCheckStatus.WARNING,
                                RuntimePlanSeverity.WARNING, f"Checksum status unclear: run={run_status}"))

        sig_present = getattr(run, "signature_value_present", False)
        if sig_present:
            plan.add_check(_chk(RuntimePlanCheckType.SIGNATURE_METADATA_ACCEPTABLE, RuntimePlanCheckStatus.PASSED,
                                RuntimePlanSeverity.INFO, "Signature metadata present."))
        else:
            plan.add_check(_chk(RuntimePlanCheckType.SIGNATURE_METADATA_ACCEPTABLE, RuntimePlanCheckStatus.WARNING,
                                RuntimePlanSeverity.WARNING, "No signature metadata."))
        plan.verification_snapshot = self._safe_dict(getattr(run, "to_dict", lambda: {})())

        # ── Phase 7: Reserved checks ──
        plan.add_check(_chk(RuntimePlanCheckType.KILL_SWITCH_OFF_RESERVED, RuntimePlanCheckStatus.SKIPPED,
                            RuntimePlanSeverity.INFO, "Kill switch check reserved; not implemented."))
        plan.add_check(_chk(RuntimePlanCheckType.WORKER_AVAILABLE_RESERVED, RuntimePlanCheckStatus.WARNING,
                            RuntimePlanSeverity.WARNING, "Worker not available. Reserved for Step 24-E+."))

        return self._finalize(plan, requested_by)

    # ── Helpers ──

    def _get_agent(self, mkp_id: str) -> Any | None:
        if self._marketplace_store is None: return None
        try: return self._marketplace_store.get_agent(mkp_id)
        except Exception: return None

    def _get_installation(self, mkp_id: str, tid: str) -> Any | None:
        if self._marketplace_store is None: return None
        try: return self._marketplace_store.get_installation_by_agent(mkp_id, tid, tid)
        except Exception: return None

    def _finalize(self, plan: RuntimeExecutionPlan, actor_id: str) -> RuntimeExecutionPlan:
        plan.calculate_status()
        plan.updated_at = datetime.now(timezone.utc)
        if self._plan_store:
            self._plan_store.create_plan(plan)
        self._try_usage(plan, actor_id)
        return plan

    def _try_usage(self, plan: RuntimeExecutionPlan, actor_id: str) -> None:
        if self._usage_store is None: return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            self._usage_store.record_event(UsageEvent(
                tenant_id=plan.tenant_id, user_id=actor_id, workspace_id=plan.tenant_id,
                resource=UsageResource.RUNTIME_EXECUTION_PLAN_CREATE, quantity=1, unit=UsageUnit.COUNT,
                metadata={
                    "plan_id": plan.plan_id, "marketplace_agent_id": plan.marketplace_agent_id,
                    "tenant_id": plan.tenant_id, "developer_id": plan.developer_id,
                    "artifact_id": plan.artifact_id, "verification_id": plan.verification_id,
                    "execution_mode": plan.execution_mode, "plan_status": plan.plan_status,
                    "decision": plan.decision, "dispatch_status": plan.dispatch_status,
                    "risk_level": plan.risk_level,
                    "warnings_count": plan.warnings_count, "errors_count": plan.errors_count,
                    "blockers_count": plan.blockers_count,
                    "no_download_planned": True, "no_network_planned": True,
                    "no_execution_performed": True, "worker_available": False,
                },
            ))
        except Exception:
            logger.warning("plan_usage_failed", exc_info=True, extra={"plan_id": plan.plan_id})

    @staticmethod
    def _safe_dict(d: Any) -> dict:
        if isinstance(d, dict): return d
        if hasattr(d, "to_dict") and callable(d.to_dict): return d.to_dict()
        return {}


def _chk(ct, status=RuntimePlanCheckStatus.PASSED, severity=RuntimePlanSeverity.INFO, message="", **kw) -> RuntimeExecutionPlanCheck:
    return RuntimeExecutionPlanCheck(check_type=ct, status=status, severity=severity, message=message, metadata=kw)
