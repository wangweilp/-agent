"""Sandbox Worker Queue Domain Model — disabled-by-default, metadata-only, no real queue.

Step 25-F: NO QUEUED/ENQUEUED/DISPATCHED/RUNNING/COMPLETED.
is_queue_enabled/is_enqueue_allowed/is_dispatch_allowed/is_execution_allowed = always False."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

class SandboxWorkerQueueStatus(StrEnum):
    DRAFT="draft"; QUEUE_DISABLED="queue_disabled"; REQUESTED="requested"
    ADMIN_REVIEW_REQUIRED="admin_review_required"; RESERVED_METADATA_ONLY="reserved_metadata_only"
    BLOCKED="blocked"; CANCELLED="cancelled"; EXPIRED="expired"; FAIL_CLOSED="fail_closed"
class SandboxWorkerQueueDecision(StrEnum):
    BLOCKED_DISABLED="blocked_disabled"; REVIEW_REQUIRED="review_required"
    RESERVED_ONLY="reserved_only"; REJECTED="rejected"; FAIL_CLOSED="fail_closed"
class SandboxWorkerQueueMode(StrEnum):
    DISABLED="disabled"; METADATA_ONLY="metadata_only"; RESERVED_FOR_STEP25H="reserved_for_step25h"
class SandboxWorkerLeaseStatus(StrEnum):
    NOT_REQUESTED="not_requested"; LEASE_DISABLED="lease_disabled"; RESERVED_FOR_FUTURE="reserved_for_future"; BLOCKED="blocked"
class SandboxWorkerDispatchStatus(StrEnum):
    NOT_DISPATCHED="not_dispatched"; DISPATCH_DISABLED="dispatch_disabled"; RESERVED_FOR_FUTURE="reserved_for_future"; BLOCKED="blocked"
class SandboxWorkerQueueRiskLevel(StrEnum):
    LOW="low"; MEDIUM="medium"; HIGH="high"; CRITICAL="critical"; UNKNOWN="unknown"
class SandboxWorkerQueueAuditEventType(StrEnum):
    QUEUE_RECORD_CREATED="queue_record_created"; QUEUE_GATE_EVALUATED="queue_gate_evaluated"
    QUEUE_STATUS_CHANGED="queue_status_changed"; DECISION_CHANGED="decision_changed"
    LEASE_STATUS_CHANGED="lease_status_changed"; DISPATCH_STATUS_CHANGED="dispatch_status_changed"
    RESERVED_METADATA_ONLY="reserved_metadata_only"; CANCELLED="cancelled"; EXPIRED="expired"
    BLOCKED="blocked"; NOTE_ADDED="note_added"
class SandboxWorkerQueueAuditSeverity(StrEnum):
    INFO="info"; WARNING="warning"; ERROR="error"; BLOCKER="blocker"

@dataclass
class SandboxWorkerQueueRecord:
    queue_record_id: str = field(default_factory=lambda: f"swq_{uuid4().hex[:16]}")
    execution_id: str | None = None; plan_id: str | None = None; gate_id: str | None = None
    artifact_id: str | None = None; package_download_request_id: str | None = None
    package_quarantine_id: str | None = None; extraction_guard_request_id: str | None = None
    extraction_plan_id: str | None = None; marketplace_agent_id: str | None = None
    tenant_id: str = ""; developer_id: str | None = None; requested_by: str | None = None
    worker_type: str | None = None
    queue_mode: str = SandboxWorkerQueueMode.DISABLED
    queue_status: str = SandboxWorkerQueueStatus.QUEUE_DISABLED
    decision: str = SandboxWorkerQueueDecision.BLOCKED_DISABLED
    lease_status: str = SandboxWorkerLeaseStatus.LEASE_DISABLED
    dispatch_status: str = SandboxWorkerDispatchStatus.DISPATCH_DISABLED
    risk_level: str = SandboxWorkerQueueRiskLevel.UNKNOWN; priority: int = 0
    execution_snapshot: dict[str,Any] = field(default_factory=dict)
    plan_snapshot: dict[str,Any] = field(default_factory=dict)
    gate_snapshot: dict[str,Any] = field(default_factory=dict)
    package_download_snapshot: dict[str,Any] = field(default_factory=dict)
    quarantine_snapshot: dict[str,Any] = field(default_factory=dict)
    extraction_plan_snapshot: dict[str,Any] = field(default_factory=dict)
    adapter_descriptor_snapshot: dict[str,Any] = field(default_factory=dict)
    policy_config_snapshot: dict[str,Any] = field(default_factory=dict)
    worker_request_snapshot: dict[str,Any] = field(default_factory=dict)
    queue_enabled: bool = False; enqueue_enabled: bool = False; dispatch_enabled: bool = False
    worker_enabled: bool = False; lease_enabled: bool = False; heartbeat_enabled: bool = False
    execution_enabled: bool = False
    no_queue_created: bool = True; no_job_enqueued: bool = True; no_job_dispatched: bool = True
    no_worker_started: bool = True; no_worker_process_created: bool = True
    no_execution_performed: bool = True; no_download_performed: bool = True
    no_extraction_performed: bool = True; no_network_used: bool = True
    no_subprocess_used: bool = True; no_container_used: bool = True
    no_agent_runtime_used: bool = True; no_agent_registry_used: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cancelled_at: datetime | None = None; expired_at: datetime | None = None
    expires_at: datetime | None = None; metadata: dict[str,Any] = field(default_factory=dict)

    def is_queue_enabled(self) -> bool: return False
    def is_enqueue_allowed(self) -> bool: return False
    def is_dispatch_allowed(self) -> bool: return False
    def is_worker_start_allowed(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False

    def to_dict(self): return {"queue_record_id":self.queue_record_id,"execution_id":self.execution_id,"plan_id":self.plan_id,"gate_id":self.gate_id,"artifact_id":self.artifact_id,"package_download_request_id":self.package_download_request_id,"package_quarantine_id":self.package_quarantine_id,"extraction_guard_request_id":self.extraction_guard_request_id,"extraction_plan_id":self.extraction_plan_id,"marketplace_agent_id":self.marketplace_agent_id,"tenant_id":self.tenant_id,"developer_id":self.developer_id,"requested_by":self.requested_by,"worker_type":self.worker_type,"queue_mode":self.queue_mode,"queue_status":self.queue_status,"decision":self.decision,"lease_status":self.lease_status,"dispatch_status":self.dispatch_status,"risk_level":self.risk_level,"priority":self.priority,"execution_snapshot":dict(self.execution_snapshot),"plan_snapshot":dict(self.plan_snapshot),"gate_snapshot":dict(self.gate_snapshot),"package_download_snapshot":dict(self.package_download_snapshot),"quarantine_snapshot":dict(self.quarantine_snapshot),"extraction_plan_snapshot":dict(self.extraction_plan_snapshot),"adapter_descriptor_snapshot":dict(self.adapter_descriptor_snapshot),"policy_config_snapshot":dict(self.policy_config_snapshot),"worker_request_snapshot":dict(self.worker_request_snapshot),"queue_enabled":self.queue_enabled,"enqueue_enabled":self.enqueue_enabled,"dispatch_enabled":self.dispatch_enabled,"worker_enabled":self.worker_enabled,"lease_enabled":self.lease_enabled,"heartbeat_enabled":self.heartbeat_enabled,"execution_enabled":self.execution_enabled,"no_queue_created":self.no_queue_created,"no_job_enqueued":self.no_job_enqueued,"no_job_dispatched":self.no_job_dispatched,"no_worker_started":self.no_worker_started,"no_worker_process_created":self.no_worker_process_created,"no_execution_performed":self.no_execution_performed,"no_download_performed":self.no_download_performed,"no_extraction_performed":self.no_extraction_performed,"no_network_used":self.no_network_used,"no_subprocess_used":self.no_subprocess_used,"no_container_used":self.no_container_used,"no_agent_runtime_used":self.no_agent_runtime_used,"no_agent_registry_used":self.no_agent_registry_used,"created_at":self.created_at.isoformat() if self.created_at else None,"updated_at":self.updated_at.isoformat() if self.updated_at else None,"cancelled_at":self.cancelled_at.isoformat() if self.cancelled_at else None,"expired_at":self.expired_at.isoformat() if self.expired_at else None,"expires_at":self.expires_at.isoformat() if self.expires_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): return cls(queue_record_id=str(d.get("queue_record_id","")),execution_id=d.get("execution_id"),plan_id=d.get("plan_id"),gate_id=d.get("gate_id"),artifact_id=d.get("artifact_id"),package_download_request_id=d.get("package_download_request_id"),package_quarantine_id=d.get("package_quarantine_id"),extraction_guard_request_id=d.get("extraction_guard_request_id"),extraction_plan_id=d.get("extraction_plan_id"),marketplace_agent_id=d.get("marketplace_agent_id"),tenant_id=str(d.get("tenant_id","")),developer_id=d.get("developer_id"),requested_by=d.get("requested_by"),worker_type=d.get("worker_type"),queue_mode=str(d.get("queue_mode","disabled")),queue_status=str(d.get("queue_status","queue_disabled")),decision=str(d.get("decision","blocked_disabled")),lease_status=str(d.get("lease_status","lease_disabled")),dispatch_status=str(d.get("dispatch_status","dispatch_disabled")),risk_level=str(d.get("risk_level","unknown")),priority=int(d.get("priority",0)),execution_snapshot=dict(d.get("execution_snapshot",{})),plan_snapshot=dict(d.get("plan_snapshot",{})),gate_snapshot=dict(d.get("gate_snapshot",{})),package_download_snapshot=dict(d.get("package_download_snapshot",{})),quarantine_snapshot=dict(d.get("quarantine_snapshot",{})),extraction_plan_snapshot=dict(d.get("extraction_plan_snapshot",{})),adapter_descriptor_snapshot=dict(d.get("adapter_descriptor_snapshot",{})),policy_config_snapshot=dict(d.get("policy_config_snapshot",{})),worker_request_snapshot=dict(d.get("worker_request_snapshot",{})),queue_enabled=bool(d.get("queue_enabled",False)),enqueue_enabled=bool(d.get("enqueue_enabled",False)),dispatch_enabled=bool(d.get("dispatch_enabled",False)),worker_enabled=bool(d.get("worker_enabled",False)),lease_enabled=bool(d.get("lease_enabled",False)),heartbeat_enabled=bool(d.get("heartbeat_enabled",False)),execution_enabled=bool(d.get("execution_enabled",False)),no_queue_created=bool(d.get("no_queue_created",True)),no_job_enqueued=bool(d.get("no_job_enqueued",True)),no_job_dispatched=bool(d.get("no_job_dispatched",True)),no_worker_started=bool(d.get("no_worker_started",True)),no_worker_process_created=bool(d.get("no_worker_process_created",True)),no_execution_performed=bool(d.get("no_execution_performed",True)),no_download_performed=bool(d.get("no_download_performed",True)),no_extraction_performed=bool(d.get("no_extraction_performed",True)),no_network_used=bool(d.get("no_network_used",True)),no_subprocess_used=bool(d.get("no_subprocess_used",True)),no_container_used=bool(d.get("no_container_used",True)),no_agent_runtime_used=bool(d.get("no_agent_runtime_used",True)),no_agent_registry_used=bool(d.get("no_agent_registry_used",True)),created_at=_safe_dt(d.get("created_at")),updated_at=_safe_dt(d.get("updated_at")),cancelled_at=_safe_dt(d.get("cancelled_at"),True),expired_at=_safe_dt(d.get("expired_at"),True),expires_at=_safe_dt(d.get("expires_at"),True),metadata=dict(d.get("metadata",{})))

@dataclass
class SandboxWorkerQueueGateResult:
    gate_result_id: str = field(default_factory=lambda: f"swqgate_{uuid4().hex[:16]}")
    queue_record_id: str | None = None; tenant_id: str = ""
    decision: str = SandboxWorkerQueueDecision.BLOCKED_DISABLED
    queue_status: str = SandboxWorkerQueueStatus.QUEUE_DISABLED
    lease_status: str = SandboxWorkerLeaseStatus.LEASE_DISABLED
    dispatch_status: str = SandboxWorkerDispatchStatus.DISPATCH_DISABLED
    checks: list[dict[str,Any]] = field(default_factory=list)
    blockers_count: int = 0; warnings_count: int = 0; errors_count: int = 0
    queue_enabled: bool = False; enqueue_enabled: bool = False
    dispatch_enabled: bool = False; worker_enabled: bool = False
    no_queue_created: bool = True; no_job_enqueued: bool = True; no_job_dispatched: bool = True
    no_worker_started: bool = True; no_execution_performed: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str,Any] = field(default_factory=dict)

    def is_passed_for_queue(self) -> bool: return False
    def is_dispatch_allowed(self) -> bool: return False
    def to_dict(self): return {"gate_result_id":self.gate_result_id,"queue_record_id":self.queue_record_id,"tenant_id":self.tenant_id,"decision":self.decision,"queue_status":self.queue_status,"lease_status":self.lease_status,"dispatch_status":self.dispatch_status,"checks":list(self.checks),"blockers_count":self.blockers_count,"warnings_count":self.warnings_count,"errors_count":self.errors_count,"queue_enabled":self.queue_enabled,"enqueue_enabled":self.enqueue_enabled,"dispatch_enabled":self.dispatch_enabled,"worker_enabled":self.worker_enabled,"no_queue_created":self.no_queue_created,"no_job_enqueued":self.no_job_enqueued,"no_job_dispatched":self.no_job_dispatched,"no_worker_started":self.no_worker_started,"no_execution_performed":self.no_execution_performed,"created_at":self.created_at.isoformat() if self.created_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): return cls(gate_result_id=str(d.get("gate_result_id","")),queue_record_id=d.get("queue_record_id"),tenant_id=str(d.get("tenant_id","")),decision=str(d.get("decision","blocked_disabled")),queue_status=str(d.get("queue_status","queue_disabled")),lease_status=str(d.get("lease_status","lease_disabled")),dispatch_status=str(d.get("dispatch_status","dispatch_disabled")),checks=list(d.get("checks",[])),blockers_count=int(d.get("blockers_count",0)),warnings_count=int(d.get("warnings_count",0)),errors_count=int(d.get("errors_count",0)),queue_enabled=bool(d.get("queue_enabled",False)),enqueue_enabled=bool(d.get("enqueue_enabled",False)),dispatch_enabled=bool(d.get("dispatch_enabled",False)),worker_enabled=bool(d.get("worker_enabled",False)),no_queue_created=bool(d.get("no_queue_created",True)),no_job_enqueued=bool(d.get("no_job_enqueued",True)),no_job_dispatched=bool(d.get("no_job_dispatched",True)),no_worker_started=bool(d.get("no_worker_started",True)),no_execution_performed=bool(d.get("no_execution_performed",True)),created_at=_safe_dt(d.get("created_at")),metadata=dict(d.get("metadata",{})))

@dataclass
class SandboxWorkerQueueAuditEvent:
    event_id: str = field(default_factory=lambda: f"swqevt_{uuid4().hex[:16]}")
    queue_record_id: str = ""; tenant_id: str = ""
    event_type: str = ""; severity: str = SandboxWorkerQueueAuditSeverity.INFO
    actor_id: str | None = None; message: str = ""
    metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"event_id":self.event_id,"queue_record_id":self.queue_record_id,"tenant_id":self.tenant_id,"event_type":self.event_type,"severity":self.severity,"actor_id":self.actor_id,"message":self.message,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(event_id=str(d.get("event_id","")),queue_record_id=str(d.get("queue_record_id","")),tenant_id=str(d.get("tenant_id","")),event_type=str(d.get("event_type","")),severity=str(d.get("severity","info")),actor_id=d.get("actor_id"),message=str(d.get("message","")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

class SandboxWorkerQueueError(Exception): pass
class SandboxWorkerQueueRecordNotFoundError(SandboxWorkerQueueError): pass
class SandboxWorkerQueueStateError(SandboxWorkerQueueError): pass
class SandboxWorkerQueueBlockedError(SandboxWorkerQueueError): pass

@runtime_checkable
class SandboxWorkerQueueStore(Protocol):
    def create_queue_record(self, record: SandboxWorkerQueueRecord) -> SandboxWorkerQueueRecord: ...
    def get_queue_record(self, queue_record_id: str) -> SandboxWorkerQueueRecord | None: ...
    def list_queue_records(self, *, tenant_id: str = "", execution_id: str = "", plan_id: str = "",
        status: str = "", decision: str = "", lease_status: str = "", dispatch_status: str = "") -> list[SandboxWorkerQueueRecord]: ...
    def update_queue_record(self, record: SandboxWorkerQueueRecord) -> SandboxWorkerQueueRecord: ...
    def set_queue_status(self, queue_record_id: str, status: str, actor_id: str | None = None, reason: str | None = None) -> SandboxWorkerQueueRecord: ...
    def set_decision(self, queue_record_id: str, decision: str, actor_id: str | None = None, reason: str | None = None) -> SandboxWorkerQueueRecord: ...
    def set_lease_status(self, queue_record_id: str, lease_status: str, actor_id: str | None = None, reason: str | None = None) -> SandboxWorkerQueueRecord: ...
    def set_dispatch_status(self, queue_record_id: str, dispatch_status: str, actor_id: str | None = None, reason: str | None = None) -> SandboxWorkerQueueRecord: ...
    def cancel_queue_record(self, queue_record_id: str, actor_id: str | None = None, reason: str | None = None) -> SandboxWorkerQueueRecord: ...
    def expire_queue_record(self, queue_record_id: str, actor_id: str | None = None, reason: str | None = None) -> SandboxWorkerQueueRecord: ...
    def create_gate_result(self, result: SandboxWorkerQueueGateResult) -> SandboxWorkerQueueGateResult: ...
    def get_gate_result(self, gate_result_id: str) -> SandboxWorkerQueueGateResult | None: ...
    def get_gate_result_by_queue_record(self, queue_record_id: str) -> SandboxWorkerQueueGateResult | None: ...
    def add_audit_event(self, event: SandboxWorkerQueueAuditEvent) -> SandboxWorkerQueueAuditEvent: ...
    def list_audit_events(self, queue_record_id: str) -> list[SandboxWorkerQueueAuditEvent]: ...
    def count_queue_records(self, *, tenant_id: str = "", status: str = "", decision: str = "", dispatch_status: str = "") -> int: ...

def _safe_dt(raw,none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
