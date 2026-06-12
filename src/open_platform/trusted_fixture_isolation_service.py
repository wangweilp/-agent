"""Trusted Fixture Isolation Service — metadata/control-plane gating, no runtime, no container, no execution."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from .trusted_fixture_isolation import *

logger = logging.getLogger(__name__)


class TrustedFixtureIsolationService:
    def __init__(self, store=None, trusted_fixture_store=None,
                 rootless_container_gate_store=None, runtime_safety_store=None, usage_store=None):
        self._store = store
        self._trusted_fixture_store = trusted_fixture_store
        self._rootless_container_gate_store = rootless_container_gate_store
        self._runtime_safety_store = runtime_safety_store
        self._usage_store = usage_store

    def create_disabled_isolation_policy(self, tenant_id=None, created_by=None) -> TrustedFixtureIsolationPolicy:
        if self._store is None: raise ValueError("store not available")
        p = TrustedFixtureIsolationPolicy(
            tenant_id=tenant_id, enabled_metadata_only=True,
            isolated_runtime_enabled=False, container_start_enabled=False,
            microvm_start_enabled=False, trusted_fixture_execution_enabled=False,
            third_party_execution_enabled=False, package_execution_enabled=False,
            entrypoint_execution_enabled=False, network_enabled=False,
            filesystem_write_enabled=False, secrets_enabled=False,
            subprocess_enabled=False, dynamic_import_enabled=False, eval_exec_enabled=False,
            requires_rootless_container_gate=True, requires_kill_switch_clear=True,
            requires_incident_clear=True, requires_red_team_passed=True, created_by=created_by)
        created = self._store.create_policy(p)
        self._try_usage(created, created_by, "policy_create")
        return created

    def create_isolation_request_metadata_only(
            self, policy_id, trusted_fixture_request_id=None, trusted_fixture_id=None,
            rootless_container_gate_request_id=None, rootless_container_plan_id=None,
            actor_id=None,
            policy_snapshot=None, trusted_fixture_snapshot=None,
            rootless_container_snapshot=None, kill_switch_snapshot=None,
            incident_snapshot=None) -> TrustedFixtureIsolationRequest:
        if self._store is None: raise ValueError("store not available")
        pol = self._store.get_policy(policy_id)
        tid = pol.tenant_id if pol else None
        r = TrustedFixtureIsolationRequest(
            tenant_id=tid, policy_id=policy_id,
            trusted_fixture_request_id=trusted_fixture_request_id,
            trusted_fixture_id=trusted_fixture_id,
            rootless_container_gate_request_id=rootless_container_gate_request_id,
            rootless_container_plan_id=rootless_container_plan_id,
            policy_snapshot=policy_snapshot or {},
            trusted_fixture_snapshot=trusted_fixture_snapshot or {},
            rootless_container_snapshot=rootless_container_snapshot or {},
            kill_switch_snapshot=kill_switch_snapshot or {},
            incident_snapshot=incident_snapshot or {},
            status=TrustedFixtureIsolationStatus.DISABLED_BY_DEFAULT,
            decision=TrustedFixtureIsolationDecision.BLOCKED_DISABLED,
            isolated_runtime_started=False, container_started=False, microvm_started=False,
            fixture_executed_in_isolated_runtime=False, fixture_executed_in_container=False,
            fixture_executed_in_microvm=False, third_party_code_executed=False,
            package_executed=False, entrypoint_executed=False,
            network_used=False, filesystem_written=False, secrets_read=False,
            subprocess_used=False,
            no_isolated_runtime_started=True, no_container_started=True,
            no_microvm_started=True, no_third_party_code_executed=True,
            no_package_executed=True, no_entrypoint_executed=True,
            no_network_used=True, no_filesystem_written=True,
            no_secrets_read=True, no_subprocess_used=True)
        created = self._store.create_request(r)
        self._try_usage(None, actor_id, "request_create", request_id=created.request_id, tenant_id=tid)
        return created

    def evaluate_trusted_fixture_isolation_gate(self, request_id, actor_id=None) -> TrustedFixtureIsolationGateResult:
        if self._store is None: raise ValueError("store not available")
        r = self._store.get_request(request_id)
        if r is None: raise TrustedFixtureIsolationRequestNotFoundError(f"Not found: {request_id}")
        reqs = build_trusted_fixture_isolation_default_requirements(r.tenant_id)
        saved = [self._store.create_requirement(req) for req in reqs]
        checks = []; satisfied = 0; missing = 0; blockers = 0
        for s in saved:
            st = s.status
            if st == TrustedFixtureIsolationRequirementStatus.SATISFIED: satisfied += 1
            elif st in (TrustedFixtureIsolationRequirementStatus.MISSING,
                        TrustedFixtureIsolationRequirementStatus.BLOCKED):
                missing += 1
                if s.required_before_third_party_execution: blockers += 1
            checks.append({"requirement_type": s.requirement_type, "name": s.name,
                           "status": s.status,
                           "blocker": s.status in (TrustedFixtureIsolationRequirementStatus.MISSING,
                                                    TrustedFixtureIsolationRequirementStatus.BLOCKED)})
        ready = missing > 0
        gate = TrustedFixtureIsolationGateResult(
            request_id=request_id, tenant_id=r.tenant_id,
            status=TrustedFixtureIsolationStatus.GATE_EVALUATED,
            decision=TrustedFixtureIsolationDecision.READY_FOR_RUNTIME_ENFORCEMENT_SPIKE_ONLY,
            checks=checks, satisfied_count=satisfied, missing_count=missing,
            blockers_count=blockers, warnings_count=0,
            ready_for_step26g=ready,
            isolated_runtime_enabled=False, container_start_allowed=False,
            microvm_start_allowed=False, fixture_execution_allowed=False,
            third_party_execution_allowed=False, package_execution_allowed=False,
            execution_allowed=False, metadata_only=True)
        created = self._store.create_gate_result(gate)
        self._try_usage(None, actor_id, "gate_evaluate", request_id=request_id, tenant_id=r.tenant_id)
        return created

    def reserve_isolation_plan_metadata_only(self, request_id, actor_id=None) -> TrustedFixtureIsolationPlan:
        if self._store is None: raise ValueError("store not available")
        r = self._store.get_request(request_id)
        if r is None: raise TrustedFixtureIsolationRequestNotFoundError(f"Not found: {request_id}")
        reqs = self._store.list_requirements()
        satisfied_names = [q.name for q in reqs if q.status == TrustedFixtureIsolationRequirementStatus.SATISFIED]
        missing_names = [q.name for q in reqs if q.status in (TrustedFixtureIsolationRequirementStatus.MISSING,
                                                               TrustedFixtureIsolationRequirementStatus.BLOCKED)]
        plan = TrustedFixtureIsolationPlan(
            request_id=request_id, tenant_id=r.tenant_id, policy_id=r.policy_id,
            fixture_id=r.trusted_fixture_id,
            isolation_requirements=[q.to_dict() for q in reqs],
            satisfied_requirements=satisfied_names, missing_requirements=missing_names,
            blocker_summary=f"{len(missing_names)} runtime capabilities missing",
            plan_status=TrustedFixtureIsolationStatus.PLAN_RESERVED_METADATA_ONLY,
            decision=TrustedFixtureIsolationDecision.METADATA_PLAN_RESERVED,
            ready_for_step26g=True,
            isolated_runtime_enabled=False, container_start_allowed=False,
            microvm_start_allowed=False, fixture_execution_allowed=False,
            third_party_execution_allowed=False, package_execution_allowed=False,
            entrypoint_execution_allowed=False, network_allowed=False,
            filesystem_write_allowed=False, secrets_allowed=False,
            subprocess_allowed=False, metadata_only=True)
        created = self._store.reserve_plan_metadata_only(plan)
        self._try_usage(None, actor_id, "plan_reserve", plan_id=created.plan_id,
                        request_id=request_id, tenant_id=r.tenant_id)
        return created

    def cancel_request(self, request_id, actor_id=None, reason=None):
        if self._store is None: raise ValueError("store not available")
        return self._store.set_request_status(request_id, TrustedFixtureIsolationStatus.CANCELLED, actor_id, reason)

    def expire_request(self, request_id, actor_id=None, reason=None):
        if self._store is None: raise ValueError("store not available")
        return self._store.set_request_status(request_id, TrustedFixtureIsolationStatus.EXPIRED, actor_id, reason)

    def _try_usage(self, rec, actor_id, action, **extra):
        if self._usage_store is None: return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            resource_map = {
                "policy_create": UsageResource.TRUSTED_FIXTURE_ISOLATION_POLICY_CREATE,
                "request_create": UsageResource.TRUSTED_FIXTURE_ISOLATION_REQUEST_CREATE,
                "requirement_assess": UsageResource.TRUSTED_FIXTURE_ISOLATION_REQUIREMENT_ASSESS,
                "gate_evaluate": UsageResource.TRUSTED_FIXTURE_ISOLATION_GATE_EVALUATE,
                "plan_reserve": UsageResource.TRUSTED_FIXTURE_ISOLATION_PLAN_RESERVE_METADATA_ONLY,
                "blocked": UsageResource.TRUSTED_FIXTURE_ISOLATION_BLOCKED,
                "audit": UsageResource.TRUSTED_FIXTURE_ISOLATION_AUDIT_EVENT,
            }
            resource = resource_map.get(action, UsageResource.TRUSTED_FIXTURE_ISOLATION_AUDIT_EVENT)
            tid = extra.get("tenant_id") or (rec.tenant_id if rec else "")
            self._usage_store.record_event(UsageEvent(
                tenant_id=tid or "", user_id=actor_id or "", workspace_id=tid or "",
                resource=resource, quantity=1, unit=UsageUnit.COUNT,
                metadata={"isolated_runtime_enabled": False, "fixture_execution_allowed": False,
                          "third_party_execution_allowed": False, "package_execution_allowed": False,
                          "execution_allowed": False, "metadata_only": True,
                          **{k: v for k, v in extra.items() if v}}))
        except Exception: logger.warning("tfix_usage_failed", exc_info=True)
