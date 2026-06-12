"""Runtime Kill Switch + Incident Store — metadata-only safety control plane.

Step 26-B: NO process/runtime/worker/container/microVM kill.
is_runtime_kill_active()/is_runtime_stopped() = always False.
All runtime_kill_implemented/process_kill_implemented = False."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

class RuntimeKillSwitchStatus(StrEnum):
    DRAFT="draft"; CONFIGURED_METADATA_ONLY="configured_metadata_only"
    TRIGGER_REQUESTED="trigger_requested"; TRIGGERED_METADATA_ONLY="triggered_metadata_only"
    RELEASE_REQUESTED="release_requested"; RELEASED_METADATA_ONLY="released_metadata_only"
    BLOCKED="blocked"; EXPIRED="expired"; FAIL_CLOSED="fail_closed"

class RuntimeKillSwitchDecision(StrEnum):
    BLOCKED="blocked"; REVIEW_REQUIRED="review_required"
    METADATA_TRIGGER_ALLOWED="metadata_trigger_allowed"
    METADATA_RELEASE_ALLOWED="metadata_release_allowed"; FAIL_CLOSED="fail_closed"

class RuntimeKillSwitchScope(StrEnum):
    GLOBAL_RUNTIME="global_runtime"; TENANT_RUNTIME="tenant_runtime"
    EXECUTION_RECORD="execution_record"; WORKER_QUEUE="worker_queue"
    PACKAGE_PIPELINE="package_pipeline"; TRUSTED_FIXTURE="trusted_fixture"

class RuntimeIncidentType(StrEnum):
    THIRD_PARTY_EXECUTION_ATTEMPT_BLOCKED="third_party_execution_attempt_blocked"
    PACKAGE_EXECUTION_ATTEMPT_BLOCKED="package_execution_attempt_blocked"
    PACKAGE_DOWNLOAD_ATTEMPT_BLOCKED="package_download_attempt_blocked"
    ARCHIVE_EXTRACTION_ATTEMPT_BLOCKED="archive_extraction_attempt_blocked"
    QUEUE_DISPATCH_ATTEMPT_BLOCKED="queue_dispatch_attempt_blocked"
    WORKER_START_ATTEMPT_BLOCKED="worker_start_attempt_blocked"
    CONTAINER_START_ATTEMPT_BLOCKED="container_start_attempt_blocked"
    MICROVM_START_ATTEMPT_BLOCKED="microvm_start_attempt_blocked"
    NETWORK_EGRESS_ATTEMPT_BLOCKED="network_egress_attempt_blocked"
    FILESYSTEM_WRITE_ATTEMPT_BLOCKED="filesystem_write_attempt_blocked"
    SECRET_ACCESS_ATTEMPT_BLOCKED="secret_access_attempt_blocked"
    METADATA_LEAKAGE_ATTEMPT_BLOCKED="metadata_leakage_attempt_blocked"
    CLAIM_BOUNDARY_VIOLATION="claim_boundary_violation"
    STARTUP_GUARD_VIOLATION="startup_guard_violation"
    TEST_REGRESSION_FAILURE="test_regression_failure"
    UNKNOWN_SECURITY_EVENT="unknown_security_event"

class RuntimeIncidentStatus(StrEnum):
    OPEN="open"; TRIAGED="triaged"; MITIGATED_METADATA_ONLY="mitigated_metadata_only"
    CLOSED_METADATA_ONLY="closed_metadata_only"; BLOCKED="blocked"; FAIL_CLOSED="fail_closed"

class RuntimeIncidentSeverity(StrEnum):
    INFO="info"; LOW="low"; MEDIUM="medium"; HIGH="high"; CRITICAL="critical"

class RuntimeIncidentDecision(StrEnum):
    RECORD_ONLY="record_only"; TRIAGE_REQUIRED="triage_required"
    KILL_SWITCH_METADATA_TRIGGERED="kill_switch_metadata_triggered"
    BLOCKED="blocked"; FAIL_CLOSED="fail_closed"

class RuntimeSafetyAuditEventType(StrEnum):
    KILL_SWITCH_POLICY_CREATED="kill_switch_policy_created"
    KILL_SWITCH_TRIGGER_REQUESTED="kill_switch_trigger_requested"
    KILL_SWITCH_TRIGGERED_METADATA_ONLY="kill_switch_triggered_metadata_only"
    KILL_SWITCH_RELEASE_REQUESTED="kill_switch_release_requested"
    KILL_SWITCH_RELEASED_METADATA_ONLY="kill_switch_released_metadata_only"
    INCIDENT_CREATED="incident_created"; INCIDENT_TRIAGED="incident_triaged"
    INCIDENT_STATUS_CHANGED="incident_status_changed"; INCIDENT_DECISION_CHANGED="incident_decision_changed"
    INCIDENT_CLOSED_METADATA_ONLY="incident_closed_metadata_only"
    BLOCKED="blocked"; NOTE_ADDED="note_added"

class RuntimeSafetyAuditSeverity(StrEnum):
    INFO="info"; WARNING="warning"; ERROR="error"; BLOCKER="blocker"

# ═══════ Dataclasses ═══════

@dataclass
class RuntimeKillSwitchPolicy:
    policy_id: str = field(default_factory=lambda: f"rks_{uuid4().hex[:16]}")
    tenant_id: str|None=None; scope: str = RuntimeKillSwitchScope.GLOBAL_RUNTIME
    policy_name: str = ""; enabled_metadata_only: bool = True
    auto_trigger_on_critical_incident: bool = True
    auto_trigger_on_test_regression: bool = True
    auto_trigger_on_startup_violation: bool = True
    auto_trigger_on_claim_violation: bool = True
    requires_admin_release: bool = True
    blocks_future_runtime_admission: bool = True
    blocks_future_worker_dispatch: bool = True
    blocks_future_package_execution: bool = True
    blocks_future_third_party_execution: bool = True
    runtime_kill_implemented: bool = False; process_kill_implemented: bool = False
    worker_kill_implemented: bool = False; container_stop_implemented: bool = False
    microvm_stop_implemented: bool = False
    created_by: str|None=None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str,Any] = field(default_factory=dict)

    def to_dict(self): return {"policy_id":self.policy_id,"tenant_id":self.tenant_id,"scope":self.scope,"policy_name":self.policy_name,"enabled_metadata_only":self.enabled_metadata_only,"auto_trigger_on_critical_incident":self.auto_trigger_on_critical_incident,"auto_trigger_on_test_regression":self.auto_trigger_on_test_regression,"auto_trigger_on_startup_violation":self.auto_trigger_on_startup_violation,"auto_trigger_on_claim_violation":self.auto_trigger_on_claim_violation,"requires_admin_release":self.requires_admin_release,"blocks_future_runtime_admission":self.blocks_future_runtime_admission,"blocks_future_worker_dispatch":self.blocks_future_worker_dispatch,"blocks_future_package_execution":self.blocks_future_package_execution,"blocks_future_third_party_execution":self.blocks_future_third_party_execution,"runtime_kill_implemented":self.runtime_kill_implemented,"process_kill_implemented":self.process_kill_implemented,"worker_kill_implemented":self.worker_kill_implemented,"container_stop_implemented":self.container_stop_implemented,"microvm_stop_implemented":self.microvm_stop_implemented,"created_by":self.created_by,"created_at":self.created_at.isoformat() if self.created_at else None,"updated_at":self.updated_at.isoformat() if self.updated_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): return cls(policy_id=str(d.get("policy_id","")),tenant_id=d.get("tenant_id"),scope=str(d.get("scope","global_runtime")),policy_name=str(d.get("policy_name","")),enabled_metadata_only=bool(d.get("enabled_metadata_only",True)),auto_trigger_on_critical_incident=bool(d.get("auto_trigger_on_critical_incident",True)),auto_trigger_on_test_regression=bool(d.get("auto_trigger_on_test_regression",True)),auto_trigger_on_startup_violation=bool(d.get("auto_trigger_on_startup_violation",True)),auto_trigger_on_claim_violation=bool(d.get("auto_trigger_on_claim_violation",True)),requires_admin_release=bool(d.get("requires_admin_release",True)),blocks_future_runtime_admission=bool(d.get("blocks_future_runtime_admission",True)),blocks_future_worker_dispatch=bool(d.get("blocks_future_worker_dispatch",True)),blocks_future_package_execution=bool(d.get("blocks_future_package_execution",True)),blocks_future_third_party_execution=bool(d.get("blocks_future_third_party_execution",True)),runtime_kill_implemented=bool(d.get("runtime_kill_implemented",False)),process_kill_implemented=bool(d.get("process_kill_implemented",False)),worker_kill_implemented=bool(d.get("worker_kill_implemented",False)),container_stop_implemented=bool(d.get("container_stop_implemented",False)),microvm_stop_implemented=bool(d.get("microvm_stop_implemented",False)),created_by=d.get("created_by"),created_at=_safe_dt(d.get("created_at")),updated_at=_safe_dt(d.get("updated_at")),metadata=dict(d.get("metadata",{})))

@dataclass
class RuntimeKillSwitchTrigger:
    trigger_id: str = field(default_factory=lambda: f"rkstrg_{uuid4().hex[:16]}")
    policy_id: str = ""; tenant_id: str|None=None; scope: str = RuntimeKillSwitchScope.GLOBAL_RUNTIME
    status: str = RuntimeKillSwitchStatus.DRAFT; decision: str = RuntimeKillSwitchDecision.BLOCKED
    reason: str = ""; incident_id: str|None=None
    triggered_by: str|None=None; released_by: str|None=None
    triggered_at: datetime|None=None; released_at: datetime|None=None
    no_process_killed: bool = True; no_runtime_terminated: bool = True
    no_worker_stopped: bool = True; no_container_stopped: bool = True
    no_microvm_stopped: bool = True; no_execution_performed: bool = True
    no_dispatch_performed: bool = True; no_queue_modified: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str,Any] = field(default_factory=dict)

    def is_runtime_kill_active(self) -> bool: return False
    def is_metadata_triggered(self) -> bool: return self.status==RuntimeKillSwitchStatus.TRIGGERED_METADATA_ONLY
    def is_execution_allowed(self) -> bool: return False

    def to_dict(self): return {"trigger_id":self.trigger_id,"policy_id":self.policy_id,"tenant_id":self.tenant_id,"scope":self.scope,"status":self.status,"decision":self.decision,"reason":self.reason,"incident_id":self.incident_id,"triggered_by":self.triggered_by,"released_by":self.released_by,"triggered_at":self.triggered_at.isoformat() if self.triggered_at else None,"released_at":self.released_at.isoformat() if self.released_at else None,"no_process_killed":self.no_process_killed,"no_runtime_terminated":self.no_runtime_terminated,"no_worker_stopped":self.no_worker_stopped,"no_container_stopped":self.no_container_stopped,"no_microvm_stopped":self.no_microvm_stopped,"no_execution_performed":self.no_execution_performed,"no_dispatch_performed":self.no_dispatch_performed,"no_queue_modified":self.no_queue_modified,"created_at":self.created_at.isoformat() if self.created_at else None,"updated_at":self.updated_at.isoformat() if self.updated_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): return cls(trigger_id=str(d.get("trigger_id","")),policy_id=str(d.get("policy_id","")),tenant_id=d.get("tenant_id"),scope=str(d.get("scope","global_runtime")),status=str(d.get("status","draft")),decision=str(d.get("decision","blocked")),reason=str(d.get("reason","")),incident_id=d.get("incident_id"),triggered_by=d.get("triggered_by"),released_by=d.get("released_by"),triggered_at=_safe_dt(d.get("triggered_at"),True),released_at=_safe_dt(d.get("released_at"),True),no_process_killed=bool(d.get("no_process_killed",True)),no_runtime_terminated=bool(d.get("no_runtime_terminated",True)),no_worker_stopped=bool(d.get("no_worker_stopped",True)),no_container_stopped=bool(d.get("no_container_stopped",True)),no_microvm_stopped=bool(d.get("no_microvm_stopped",True)),no_execution_performed=bool(d.get("no_execution_performed",True)),no_dispatch_performed=bool(d.get("no_dispatch_performed",True)),no_queue_modified=bool(d.get("no_queue_modified",True)),created_at=_safe_dt(d.get("created_at")),updated_at=_safe_dt(d.get("updated_at")),metadata=dict(d.get("metadata",{})))

@dataclass
class RuntimeIncidentRecord:
    incident_id: str = field(default_factory=lambda: f"rinc_{uuid4().hex[:16]}")
    tenant_id: str|None=None; incident_type: str = ""; severity: str = RuntimeIncidentSeverity.MEDIUM
    status: str = RuntimeIncidentStatus.OPEN; decision: str = RuntimeIncidentDecision.TRIAGE_REQUIRED
    title: str = ""; description: str = ""
    source_component: str|None=None; related_execution_id: str|None=None
    related_queue_record_id: str|None=None; related_gate_request_id: str|None=None
    related_package_request_id: str|None=None; related_fixture_request_id: str|None=None
    detected_by: str|None=None; triaged_by: str|None=None; closed_by: str|None=None
    kill_switch_trigger_id: str|None=None
    evidence_refs: list[str] = field(default_factory=list); blockers: list[str] = field(default_factory=list)
    remediation_notes: list[str] = field(default_factory=list)
    no_runtime_killed: bool = True; no_process_killed: bool = True
    no_worker_stopped: bool = True; no_execution_performed: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    triaged_at: datetime|None=None; closed_at: datetime|None=None
    metadata: dict[str,Any] = field(default_factory=dict)

    def is_runtime_stopped(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False

    def to_dict(self): return {"incident_id":self.incident_id,"tenant_id":self.tenant_id,"incident_type":self.incident_type,"severity":self.severity,"status":self.status,"decision":self.decision,"title":self.title,"description":self.description,"source_component":self.source_component,"related_execution_id":self.related_execution_id,"related_queue_record_id":self.related_queue_record_id,"related_gate_request_id":self.related_gate_request_id,"related_package_request_id":self.related_package_request_id,"related_fixture_request_id":self.related_fixture_request_id,"detected_by":self.detected_by,"triaged_by":self.triaged_by,"closed_by":self.closed_by,"kill_switch_trigger_id":self.kill_switch_trigger_id,"evidence_refs":list(self.evidence_refs),"blockers":list(self.blockers),"remediation_notes":list(self.remediation_notes),"no_runtime_killed":self.no_runtime_killed,"no_process_killed":self.no_process_killed,"no_worker_stopped":self.no_worker_stopped,"no_execution_performed":self.no_execution_performed,"created_at":self.created_at.isoformat() if self.created_at else None,"updated_at":self.updated_at.isoformat() if self.updated_at else None,"triaged_at":self.triaged_at.isoformat() if self.triaged_at else None,"closed_at":self.closed_at.isoformat() if self.closed_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): return cls(incident_id=str(d.get("incident_id","")),tenant_id=d.get("tenant_id"),incident_type=str(d.get("incident_type","")),severity=str(d.get("severity","medium")),status=str(d.get("status","open")),decision=str(d.get("decision","triage_required")),title=str(d.get("title","")),description=str(d.get("description","")),source_component=d.get("source_component"),related_execution_id=d.get("related_execution_id"),related_queue_record_id=d.get("related_queue_record_id"),related_gate_request_id=d.get("related_gate_request_id"),related_package_request_id=d.get("related_package_request_id"),related_fixture_request_id=d.get("related_fixture_request_id"),detected_by=d.get("detected_by"),triaged_by=d.get("triaged_by"),closed_by=d.get("closed_by"),kill_switch_trigger_id=d.get("kill_switch_trigger_id"),evidence_refs=list(d.get("evidence_refs",[])),blockers=list(d.get("blockers",[])),remediation_notes=list(d.get("remediation_notes",[])),no_runtime_killed=bool(d.get("no_runtime_killed",True)),no_process_killed=bool(d.get("no_process_killed",True)),no_worker_stopped=bool(d.get("no_worker_stopped",True)),no_execution_performed=bool(d.get("no_execution_performed",True)),created_at=_safe_dt(d.get("created_at")),updated_at=_safe_dt(d.get("updated_at")),triaged_at=_safe_dt(d.get("triaged_at"),True),closed_at=_safe_dt(d.get("closed_at"),True),metadata=dict(d.get("metadata",{})))

@dataclass
class RuntimeSafetyAuditEvent:
    event_id: str = field(default_factory=lambda: f"rsaevt_{uuid4().hex[:16]}")
    tenant_id: str|None=None; incident_id: str|None=None; trigger_id: str|None=None; policy_id: str|None=None
    event_type: str = ""; severity: str = RuntimeSafetyAuditSeverity.INFO
    actor_id: str|None=None; message: str = ""; metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"event_id":self.event_id,"tenant_id":self.tenant_id,"incident_id":self.incident_id,"trigger_id":self.trigger_id,"policy_id":self.policy_id,"event_type":self.event_type,"severity":self.severity,"actor_id":self.actor_id,"message":self.message,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(event_id=str(d.get("event_id","")),tenant_id=d.get("tenant_id"),incident_id=d.get("incident_id"),trigger_id=d.get("trigger_id"),policy_id=d.get("policy_id"),event_type=str(d.get("event_type","")),severity=str(d.get("severity","info")),actor_id=d.get("actor_id"),message=str(d.get("message","")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

class RuntimeKillSwitchError(Exception): pass
class RuntimeKillSwitchPolicyNotFoundError(RuntimeKillSwitchError): pass
class RuntimeIncidentNotFoundError(RuntimeKillSwitchError): pass
class RuntimeSafetyStateError(RuntimeKillSwitchError): pass
class RuntimeSafetyBlockedError(RuntimeKillSwitchError): pass

@runtime_checkable
class RuntimeSafetyStore(Protocol):
    def create_policy(self, policy: RuntimeKillSwitchPolicy) -> RuntimeKillSwitchPolicy: ...
    def get_policy(self, policy_id: str) -> RuntimeKillSwitchPolicy | None: ...
    def list_policies(self, *, tenant_id: str = "", scope: str = "") -> list[RuntimeKillSwitchPolicy]: ...
    def update_policy(self, policy: RuntimeKillSwitchPolicy) -> RuntimeKillSwitchPolicy: ...
    def create_trigger(self, trigger: RuntimeKillSwitchTrigger) -> RuntimeKillSwitchTrigger: ...
    def get_trigger(self, trigger_id: str) -> RuntimeKillSwitchTrigger | None: ...
    def get_latest_trigger(self, policy_id: str) -> RuntimeKillSwitchTrigger | None: ...
    def release_trigger(self, trigger_id: str, actor_id: str | None = None, reason: str | None = None) -> RuntimeKillSwitchTrigger: ...
    def create_incident(self, incident: RuntimeIncidentRecord) -> RuntimeIncidentRecord: ...
    def get_incident(self, incident_id: str) -> RuntimeIncidentRecord | None: ...
    def list_incidents(self, *, tenant_id: str = "", incident_type: str = "", severity: str = "",
        status: str = "", decision: str = "") -> list[RuntimeIncidentRecord]: ...
    def update_incident(self, incident: RuntimeIncidentRecord) -> RuntimeIncidentRecord: ...
    def set_incident_status(self, incident_id: str, status: str, actor_id: str | None = None, reason: str | None = None) -> RuntimeIncidentRecord: ...
    def set_incident_decision(self, incident_id: str, decision: str, actor_id: str | None = None, reason: str | None = None) -> RuntimeIncidentRecord: ...
    def triage_incident(self, incident_id: str, actor_id: str | None = None, notes: str | None = None) -> RuntimeIncidentRecord: ...
    def close_incident_metadata_only(self, incident_id: str, actor_id: str | None = None, notes: str | None = None) -> RuntimeIncidentRecord: ...
    def add_audit_event(self, event: RuntimeSafetyAuditEvent) -> RuntimeSafetyAuditEvent: ...
    def list_audit_events(self, *, incident_id: str = "", trigger_id: str = "", policy_id: str = "") -> list[RuntimeSafetyAuditEvent]: ...
    def count_incidents(self, *, tenant_id: str = "", severity: str = "", status: str = "", decision: str = "") -> int: ...

def _safe_dt(raw, none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
