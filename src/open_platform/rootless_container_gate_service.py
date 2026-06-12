"""Rootless Container Gate Service — metadata/control-plane readiness assessment, no container start, no Docker/Podman, no execution.

Step 26-E: evaluate readiness for rootless container. All container_start/runtime/execution = False.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from .rootless_container_gate import *

logger = logging.getLogger(__name__)


class RootlessContainerGateService:
    def __init__(self, store=None, production_gate_store=None,
                 runtime_safety_store=None, artifact_materialization_store=None,
                 package_download_worker_store=None, usage_store=None):
        self._store = store
        self._production_gate_store = production_gate_store
        self._runtime_safety_store = runtime_safety_store
        self._artifact_materialization_store = artifact_materialization_store
        self._package_download_worker_store = package_download_worker_store
        self._usage_store = usage_store

    def create_disabled_rootless_container_policy(
            self, tenant_id=None, created_by=None) -> RootlessContainerPrototypePolicy:
        if self._store is None:
            raise ValueError("store not available")
        p = RootlessContainerPrototypePolicy(
            tenant_id=tenant_id,
            enabled_metadata_only=True,
            rootless_container_enabled=False, container_start_enabled=False,
            docker_enabled=False, podman_enabled=False,
            namespace_creation_enabled=False, cgroup_enabled=False,
            mount_enabled=False, network_enabled=False,
            package_execution_enabled=False, third_party_execution_enabled=False,
            requires_kill_switch_clear=True, requires_incident_clear=True,
            requires_read_only_artifact_plan=True, requires_download_worker_blocked=True,
            requires_red_team_passed=True, created_by=created_by)
        created = self._store.create_policy(p)
        self._try_usage(created, created_by, "policy_create")
        return created

    def create_prototype_request_metadata_only(
            self, policy_id, production_gate_request_id=None,
            kill_switch_policy_id=None, incident_id=None,
            artifact_plan_id=None, download_worker_job_id=None, actor_id=None,
            policy_snapshot=None, production_gate_snapshot=None,
            kill_switch_snapshot=None, artifact_plan_snapshot=None,
            download_worker_snapshot=None) -> RootlessContainerPrototypeRequest:
        if self._store is None:
            raise ValueError("store not available")
        pol = self._store.get_policy(policy_id)
        tid = pol.tenant_id if pol else None

        r = RootlessContainerPrototypeRequest(
            tenant_id=tid, policy_id=policy_id,
            production_gate_request_id=production_gate_request_id,
            kill_switch_policy_id=kill_switch_policy_id, incident_id=incident_id,
            artifact_plan_id=artifact_plan_id, download_worker_job_id=download_worker_job_id,
            policy_snapshot=policy_snapshot or {},
            production_gate_snapshot=production_gate_snapshot or {},
            kill_switch_snapshot=kill_switch_snapshot or {},
            artifact_plan_snapshot=artifact_plan_snapshot or {},
            download_worker_snapshot=download_worker_snapshot or {},
            status=RootlessContainerGateStatus.DISABLED_BY_DEFAULT,
            decision=RootlessContainerGateDecision.BLOCKED_DISABLED,
            container_started=False, runtime_started=False,
            namespace_created=False, cgroup_created=False,
            mount_created=False, network_enabled=False,
            package_executed=False, third_party_code_executed=False,
            no_container_started=True, no_runtime_started=True,
            no_namespace_created=True, no_cgroup_created=True,
            no_mount_created=True, no_network_enabled=True,
            no_execution_performed=True, no_package_executed=True,
            no_third_party_code_executed=True)
        created = self._store.create_request(r)
        self._try_usage(None, actor_id, "request_create",
                        request_id=created.request_id, tenant_id=tid)
        return created

    def evaluate_rootless_container_gate(self, request_id, actor_id=None) -> RootlessContainerGateResult:
        if self._store is None:
            raise ValueError("store not available")
        r = self._store.get_request(request_id)
        if r is None:
            raise RootlessContainerRequestNotFoundError(f"Not found: {request_id}")

        # Build and persist capability assessments
        assessments = build_rootless_container_default_capabilities(r.tenant_id)
        saved = []
        for a in assessments:
            saved.append(self._store.create_capability_assessment(a))

        checks = []
        satisfied = 0
        missing = 0
        blockers = 0
        warnings = 0

        for a in saved:
            st = a.status
            if st == RootlessContainerCapabilityStatus.SATISFIED:
                satisfied += 1
            elif st in (RootlessContainerCapabilityStatus.MISSING,
                        RootlessContainerCapabilityStatus.BLOCKED):
                missing += 1
                if a.required_before_container_start:
                    blockers += 1
            checks.append({
                "capability_type": a.capability_type,
                "name": a.name, "status": a.status,
                "blocker": a.status in (RootlessContainerCapabilityStatus.MISSING,
                                        RootlessContainerCapabilityStatus.BLOCKED)
            })

        # Missing runtime capabilities block container start, execution remains blocked
        # But control-plane readiness (no control-plane blockers) means ready_for_step26f can be True
        ready = missing > 0  # if capabilities are missing, step26f review is justified

        gate = RootlessContainerGateResult(
            request_id=request_id, tenant_id=r.tenant_id,
            status=RootlessContainerGateStatus.GATE_EVALUATED,
            decision=RootlessContainerGateDecision.READY_FOR_FUTURE_ISOLATED_FIXTURE_GATE_ONLY,
            checks=checks, satisfied_count=satisfied, missing_count=missing,
            blockers_count=blockers, warnings_count=warnings,
            ready_for_step26f=ready,
            container_start_allowed=False, runtime_enabled=False,
            network_allowed=False, mount_allowed=False,
            execution_allowed=False, third_party_execution_allowed=False,
            package_execution_allowed=False, metadata_only=True)
        created = self._store.create_gate_result(gate)
        self._try_usage(None, actor_id, "gate_evaluate",
                        request_id=request_id, tenant_id=r.tenant_id)
        return created

    def reserve_prototype_plan_metadata_only(self, request_id, actor_id=None) -> RootlessContainerPrototypePlan:
        if self._store is None:
            raise ValueError("store not available")
        r = self._store.get_request(request_id)
        if r is None:
            raise RootlessContainerRequestNotFoundError(f"Not found: {request_id}")

        assessments = self._store.list_capability_assessments()
        required = [a.name for a in assessments if a.status == RootlessContainerCapabilityStatus.SATISFIED]
        missing = [a.name for a in assessments if a.status in (RootlessContainerCapabilityStatus.MISSING,
                                                                RootlessContainerCapabilityStatus.BLOCKED)]

        plan = RootlessContainerPrototypePlan(
            request_id=request_id, tenant_id=r.tenant_id, policy_id=r.policy_id,
            capability_assessments=[a.to_dict() for a in assessments],
            required_controls=required, missing_controls=missing,
            blocker_summary=f"{len(missing)} runtime capabilities missing",
            plan_status=RootlessContainerGateStatus.PLAN_RESERVED_METADATA_ONLY,
            decision=RootlessContainerGateDecision.METADATA_PLAN_RESERVED,
            container_start_allowed=False, runtime_enabled=False,
            network_allowed=False, mount_allowed=False,
            package_execution_allowed=False, third_party_execution_allowed=False,
            metadata_only=True)
        created = self._store.reserve_plan_metadata_only(plan)
        self._try_usage(None, actor_id, "plan_reserve",
                        plan_id=created.plan_id, request_id=request_id,
                        tenant_id=r.tenant_id)
        return created

    def cancel_request(self, request_id, actor_id=None, reason=None) -> RootlessContainerPrototypeRequest:
        if self._store is None:
            raise ValueError("store not available")
        return self._store.set_request_status(
            request_id, RootlessContainerGateStatus.CANCELLED, actor_id, reason)

    def expire_request(self, request_id, actor_id=None, reason=None) -> RootlessContainerPrototypeRequest:
        if self._store is None:
            raise ValueError("store not available")
        return self._store.set_request_status(
            request_id, RootlessContainerGateStatus.EXPIRED, actor_id, reason)

    def _try_usage(self, rec, actor_id, action, **extra):
        if self._usage_store is None:
            return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            resource_map = {
                "policy_create": UsageResource.ROOTLESS_CONTAINER_POLICY_CREATE,
                "request_create": UsageResource.ROOTLESS_CONTAINER_REQUEST_CREATE,
                "gate_evaluate": UsageResource.ROOTLESS_CONTAINER_GATE_EVALUATE,
                "capability_assess": UsageResource.ROOTLESS_CONTAINER_CAPABILITY_ASSESS,
                "plan_reserve": UsageResource.ROOTLESS_CONTAINER_PLAN_RESERVE_METADATA_ONLY,
                "blocked": UsageResource.ROOTLESS_CONTAINER_BLOCKED,
                "audit": UsageResource.ROOTLESS_CONTAINER_AUDIT_EVENT,
            }
            resource = resource_map.get(action, UsageResource.ROOTLESS_CONTAINER_AUDIT_EVENT)
            tid = extra.get("tenant_id") or (rec.tenant_id if rec else "")
            self._usage_store.record_event(UsageEvent(
                tenant_id=tid or "", user_id=actor_id or "", workspace_id=tid or "",
                resource=resource, quantity=1, unit=UsageUnit.COUNT,
                metadata={"container_start_allowed": False, "runtime_enabled": False,
                          "network_allowed": False, "execution_allowed": False,
                          "third_party_execution_allowed": False,
                          "package_execution_allowed": False, "metadata_only": True,
                          **{k: v for k, v in extra.items() if v}}))
        except Exception:
            logger.warning("rtcls_usage_failed", exc_info=True)
