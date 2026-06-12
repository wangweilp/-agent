"""Runtime Safety Service — metadata-only kill switch + incident management."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from .runtime_kill_switch import *

logger = logging.getLogger(__name__)

class RuntimeSafetyService:
    def __init__(self, store=None, usage_store=None):
        self._store = store; self._usage_store = usage_store

    def create_default_kill_switch_policy(self, tenant_id=None, scope=RuntimeKillSwitchScope.GLOBAL_RUNTIME,
                                           created_by=None) -> RuntimeKillSwitchPolicy:
        if self._store is None: raise ValueError("store not available")
        p = RuntimeKillSwitchPolicy(tenant_id=tenant_id, scope=scope, policy_name="Default Runtime Safety Policy",
            enabled_metadata_only=True, auto_trigger_on_critical_incident=True, auto_trigger_on_test_regression=True,
            auto_trigger_on_startup_violation=True, auto_trigger_on_claim_violation=True, requires_admin_release=True,
            blocks_future_runtime_admission=True, blocks_future_worker_dispatch=True,
            blocks_future_package_execution=True, blocks_future_third_party_execution=True,
            runtime_kill_implemented=False, process_kill_implemented=False, worker_kill_implemented=False,
            container_stop_implemented=False, microvm_stop_implemented=False, created_by=created_by)
        created = self._store.create_policy(p)
        self._try_usage(created, created_by, "policy_create"); return created

    def trigger_kill_switch_metadata_only(self, policy_id, reason, actor_id=None, incident_id=None) -> RuntimeKillSwitchTrigger:
        if self._store is None: raise ValueError("store not available")
        pol = self._store.get_policy(policy_id)
        if pol is None: raise RuntimeKillSwitchPolicyNotFoundError(f"Policy not found: {policy_id}")
        tr = RuntimeKillSwitchTrigger(policy_id=policy_id, tenant_id=pol.tenant_id, scope=pol.scope,
            status=RuntimeKillSwitchStatus.TRIGGERED_METADATA_ONLY, decision=RuntimeKillSwitchDecision.METADATA_TRIGGER_ALLOWED,
            reason=reason, incident_id=incident_id, triggered_by=actor_id, triggered_at=datetime.now(timezone.utc),
            no_process_killed=True, no_runtime_terminated=True, no_worker_stopped=True, no_container_stopped=True,
            no_microvm_stopped=True, no_execution_performed=True, no_dispatch_performed=True, no_queue_modified=True)
        created = self._store.create_trigger(tr)
        self._try_usage(None, actor_id, "trigger", trigger_id=created.trigger_id, policy_id=policy_id, tenant_id=pol.tenant_id, scope=pol.scope)
        return created

    def release_kill_switch_metadata_only(self, trigger_id, actor_id=None, reason=None) -> RuntimeKillSwitchTrigger:
        if self._store is None: raise ValueError("store not available")
        return self._store.release_trigger(trigger_id, actor_id, reason)

    def create_incident(self, incident_type, severity, title, description, *, tenant_id=None,
                         source_component=None, detected_by=None, related_execution_id=None, related_queue_record_id=None,
                         related_gate_request_id=None, related_package_request_id=None, related_fixture_request_id=None,
                         evidence_refs=None, metadata=None) -> RuntimeIncidentRecord:
        if self._store is None: raise ValueError("store not available")
        decision = RuntimeIncidentDecision.TRIAGE_REQUIRED if severity in (RuntimeIncidentSeverity.CRITICAL,RuntimeIncidentSeverity.HIGH) else RuntimeIncidentDecision.RECORD_ONLY
        inc = RuntimeIncidentRecord(tenant_id=tenant_id, incident_type=incident_type, severity=severity,
            status=RuntimeIncidentStatus.OPEN, decision=decision, title=title, description=description,
            source_component=source_component, detected_by=detected_by, related_execution_id=related_execution_id,
            related_queue_record_id=related_queue_record_id, related_gate_request_id=related_gate_request_id,
            related_package_request_id=related_package_request_id, related_fixture_request_id=related_fixture_request_id,
            evidence_refs=evidence_refs or [], no_runtime_killed=True, no_process_killed=True,
            no_worker_stopped=True, no_execution_performed=True, metadata=metadata or {})
        created = self._store.create_incident(inc)
        self._try_usage(None, detected_by, "incident_create", incident_id=created.incident_id, incident_type=incident_type, severity=severity)
        return created

    def auto_trigger_for_critical_incident(self, incident_id, policy_id, actor_id=None) -> RuntimeKillSwitchTrigger | None:
        if self._store is None: raise ValueError("store not available")
        inc = self._store.get_incident(incident_id)
        if inc is None: raise RuntimeIncidentNotFoundError(f"Not found: {incident_id}")
        pol = self._store.get_policy(policy_id)
        if pol is None: return None
        if inc.severity == RuntimeIncidentSeverity.CRITICAL and pol.auto_trigger_on_critical_incident:
            return self.trigger_kill_switch_metadata_only(policy_id, f"Auto-triggered by critical incident {incident_id}", actor_id, incident_id)
        return None

    def triage_incident(self, incident_id, actor_id=None, notes=None):
        if self._store is None: raise ValueError("store not available")
        return self._store.triage_incident(incident_id, actor_id, notes)

    def close_incident_metadata_only(self, incident_id, actor_id=None, notes=None):
        if self._store is None: raise ValueError("store not available")
        return self._store.close_incident_metadata_only(incident_id, actor_id, notes)

    def _try_usage(self, rec, actor_id, action, **extra):
        if self._usage_store is None: return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            resource_map = {"policy_create":UsageResource.RUNTIME_KILL_SWITCH_POLICY_CREATE,"trigger":UsageResource.RUNTIME_KILL_SWITCH_TRIGGER_METADATA_ONLY,"incident_create":UsageResource.RUNTIME_INCIDENT_CREATE}
            resource = resource_map.get(action, UsageResource.RUNTIME_SAFETY_AUDIT_EVENT)
            tid = extra.get("tenant_id") or (rec.tenant_id if rec else None)
            self._usage_store.record_event(UsageEvent(tenant_id=tid or "", user_id=actor_id or "", workspace_id=tid or "",
                resource=resource, quantity=1, unit=UsageUnit.COUNT,
                metadata={"no_process_killed":True,"no_runtime_terminated":True,"no_worker_stopped":True,"no_execution_performed":True,**{k:v for k,v in extra.items() if v}}))
        except Exception: logger.warning("rtsafety_usage_failed", exc_info=True)
