"""Sandbox Execution Domain Model — audit-only execution record。

Step 25-B: 只做 execution record + audit event model。
is_executable()/is_queued() 始终 False。
NO RUNNING/COMPLETED/SUCCEEDED status。"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

# ═══════════ Enums ═══════════

class SandboxExecutionStatus(StrEnum):
    DRAFT="draft"; REQUESTED="requested"; GATE_BLOCKED="gate_blocked"
    REVIEW_REQUIRED="review_required"; AUDIT_ONLY="audit_only"
    QUEUE_DISABLED="queue_disabled"; RESERVED_FOR_QUEUE="reserved_for_queue"
    CANCELLED="cancelled"; EXPIRED="expired"

class SandboxExecutionDecision(StrEnum):
    BLOCKED="blocked"; REVIEW_REQUIRED="review_required"
    AUDIT_ONLY="audit_only"; RESERVED_ONLY="reserved_only"; FAIL_CLOSED="fail_closed"

class SandboxExecutionQueueStatus(StrEnum):
    NOT_QUEUED="not_queued"; QUEUE_DISABLED="queue_disabled"
    RESERVED_FOR_STEP25F="reserved_for_step25f"; BLOCKED="blocked"

class SandboxExecutionRiskLevel(StrEnum):
    LOW="low"; MEDIUM="medium"; HIGH="high"; CRITICAL="critical"; UNKNOWN="unknown"

class SandboxExecutionAuditEventType(StrEnum):
    CREATED="created"; GATE_EVALUATED="gate_evaluated"; STATUS_CHANGED="status_changed"
    DECISION_CHANGED="decision_changed"; QUEUE_STATUS_CHANGED="queue_status_changed"
    CANCELLED="cancelled"; EXPIRED="expired"; BLOCKED="blocked"; NOTE_ADDED="note_added"

class SandboxExecutionAuditSeverity(StrEnum):
    INFO="info"; WARNING="warning"; ERROR="error"; BLOCKER="blocker"

# ═══════════ SandboxExecutionRecord ═══════════

@dataclass
class SandboxExecutionRecord:
    execution_id: str = field(default_factory=lambda: f"sbxexec_{uuid4().hex[:16]}")
    plan_id: str = ""; gate_id: str | None = None
    marketplace_agent_id: str = ""; tenant_id: str = ""; user_id: str | None = None
    developer_id: str = ""; submission_id: str | None = None
    artifact_id: str | None = None; verification_id: str | None = None
    sandbox_policy_id: str | None = None; runtime_binding_id: str | None = None
    worker_type: str | None = None
    execution_status: str = SandboxExecutionStatus.DRAFT
    decision: str = SandboxExecutionDecision.BLOCKED
    queue_status: str = SandboxExecutionQueueStatus.QUEUE_DISABLED
    risk_level: str = SandboxExecutionRiskLevel.UNKNOWN
    input_payload_hash: str | None = None
    plan_snapshot: dict[str,Any] = field(default_factory=dict)
    gate_snapshot: dict[str,Any] = field(default_factory=dict)
    policy_config_snapshot: dict[str,Any] = field(default_factory=dict)
    artifact_snapshot: dict[str,Any] = field(default_factory=dict)
    verification_snapshot: dict[str,Any] = field(default_factory=dict)
    worker_request_snapshot: dict[str,Any] = field(default_factory=dict)
    no_execution_performed: bool = True; no_download_used: bool = True
    no_network_used: bool = True; no_subprocess_used: bool = True
    no_container_used: bool = True; no_queue_created: bool = True
    no_job_dispatched: bool = True; no_agent_runtime_used: bool = True
    no_agent_registry_used: bool = True
    created_by: str | None = None; cancelled_by: str | None = None; expired_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cancelled_at: datetime | None = None; expired_at: datetime | None = None
    expires_at: datetime | None = None
    metadata: dict[str,Any] = field(default_factory=dict)

    def __post_init__(self):
        for f in ["plan_snapshot","gate_snapshot","policy_config_snapshot","artifact_snapshot",
                  "verification_snapshot","worker_request_snapshot","metadata"]:
            if not isinstance(getattr(self,f), dict): raise ValueError(f"{f} must be dict")

    def is_executable(self) -> bool: return False  # Step 25-B: always false
    def is_queued(self) -> bool: return False
    def is_terminal(self) -> bool:
        return self.execution_status in (SandboxExecutionStatus.CANCELLED,
            SandboxExecutionStatus.EXPIRED, SandboxExecutionStatus.GATE_BLOCKED)

    def to_dict(self) -> dict[str,Any]:
        return {"execution_id":self.execution_id,"plan_id":self.plan_id,"gate_id":self.gate_id,
            "marketplace_agent_id":self.marketplace_agent_id,"tenant_id":self.tenant_id,
            "user_id":self.user_id,"developer_id":self.developer_id,"submission_id":self.submission_id,
            "artifact_id":self.artifact_id,"verification_id":self.verification_id,
            "sandbox_policy_id":self.sandbox_policy_id,"runtime_binding_id":self.runtime_binding_id,
            "worker_type":self.worker_type,"execution_status":self.execution_status,
            "decision":self.decision,"queue_status":self.queue_status,"risk_level":self.risk_level,
            "input_payload_hash":self.input_payload_hash,
            "plan_snapshot":dict(self.plan_snapshot),"gate_snapshot":dict(self.gate_snapshot),
            "policy_config_snapshot":dict(self.policy_config_snapshot),
            "artifact_snapshot":dict(self.artifact_snapshot),
            "verification_snapshot":dict(self.verification_snapshot),
            "worker_request_snapshot":dict(self.worker_request_snapshot),
            "no_execution_performed":self.no_execution_performed,"no_download_used":self.no_download_used,
            "no_network_used":self.no_network_used,"no_subprocess_used":self.no_subprocess_used,
            "no_container_used":self.no_container_used,"no_queue_created":self.no_queue_created,
            "no_job_dispatched":self.no_job_dispatched,"no_agent_runtime_used":self.no_agent_runtime_used,
            "no_agent_registry_used":self.no_agent_registry_used,
            "created_by":self.created_by,"cancelled_by":self.cancelled_by,"expired_by":self.expired_by,
            "created_at":self.created_at.isoformat() if self.created_at else None,
            "updated_at":self.updated_at.isoformat() if self.updated_at else None,
            "cancelled_at":self.cancelled_at.isoformat() if self.cancelled_at else None,
            "expired_at":self.expired_at.isoformat() if self.expired_at else None,
            "expires_at":self.expires_at.isoformat() if self.expires_at else None,
            "metadata":dict(self.metadata)}

    @classmethod
    def from_dict(cls,d:dict[str,Any]) -> "SandboxExecutionRecord":
        return cls(execution_id=str(d.get("execution_id","")),plan_id=str(d.get("plan_id","")),
            gate_id=d.get("gate_id"),marketplace_agent_id=str(d.get("marketplace_agent_id","")),
            tenant_id=str(d.get("tenant_id","")),user_id=d.get("user_id"),
            developer_id=str(d.get("developer_id","")),submission_id=d.get("submission_id"),
            artifact_id=d.get("artifact_id"),verification_id=d.get("verification_id"),
            sandbox_policy_id=d.get("sandbox_policy_id"),runtime_binding_id=d.get("runtime_binding_id"),
            worker_type=d.get("worker_type"),
            execution_status=str(d.get("execution_status","draft")),
            decision=str(d.get("decision","blocked")),
            queue_status=str(d.get("queue_status","queue_disabled")),
            risk_level=str(d.get("risk_level","unknown")),
            input_payload_hash=d.get("input_payload_hash"),
            plan_snapshot=dict(d.get("plan_snapshot",{})),gate_snapshot=dict(d.get("gate_snapshot",{})),
            policy_config_snapshot=dict(d.get("policy_config_snapshot",{})),
            artifact_snapshot=dict(d.get("artifact_snapshot",{})),
            verification_snapshot=dict(d.get("verification_snapshot",{})),
            worker_request_snapshot=dict(d.get("worker_request_snapshot",{})),
            no_execution_performed=bool(d.get("no_execution_performed",True)),
            no_download_used=bool(d.get("no_download_used",True)),
            no_network_used=bool(d.get("no_network_used",True)),
            no_subprocess_used=bool(d.get("no_subprocess_used",True)),
            no_container_used=bool(d.get("no_container_used",True)),
            no_queue_created=bool(d.get("no_queue_created",True)),
            no_job_dispatched=bool(d.get("no_job_dispatched",True)),
            no_agent_runtime_used=bool(d.get("no_agent_runtime_used",True)),
            no_agent_registry_used=bool(d.get("no_agent_registry_used",True)),
            created_by=d.get("created_by"),cancelled_by=d.get("cancelled_by"),expired_by=d.get("expired_by"),
            created_at=_safe_dt(d.get("created_at")),updated_at=_safe_dt(d.get("updated_at")),
            cancelled_at=_safe_dt(d.get("cancelled_at"),none_ok=True),
            expired_at=_safe_dt(d.get("expired_at"),none_ok=True),
            expires_at=_safe_dt(d.get("expires_at"),none_ok=True),
            metadata=dict(d.get("metadata",{})))

# ═══════════ SandboxExecutionAuditEvent ═══════════

@dataclass
class SandboxExecutionAuditEvent:
    event_id: str = field(default_factory=lambda: f"sbxevt_{uuid4().hex[:16]}")
    execution_id: str = ""; tenant_id: str = ""
    event_type: str = ""; severity: str = SandboxExecutionAuditSeverity.INFO
    actor_id: str | None = None; message: str = ""
    metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str,Any]:
        return {"event_id":self.event_id,"execution_id":self.execution_id,"tenant_id":self.tenant_id,
            "event_type":self.event_type,"severity":self.severity,"actor_id":self.actor_id,
            "message":self.message,"metadata":dict(self.metadata),
            "created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d:dict[str,Any]) -> "SandboxExecutionAuditEvent":
        return cls(event_id=str(d.get("event_id","")),execution_id=str(d.get("execution_id","")),
            tenant_id=str(d.get("tenant_id","")),event_type=str(d.get("event_type","")),
            severity=str(d.get("severity","info")),actor_id=d.get("actor_id"),
            message=str(d.get("message","")),metadata=dict(d.get("metadata",{})),
            created_at=_safe_dt(d.get("created_at")))

# ═══════════ Errors ═══════════

class SandboxExecutionError(Exception): pass
class SandboxExecutionNotFoundError(SandboxExecutionError): pass
class SandboxExecutionAlreadyExistsError(SandboxExecutionError): pass
class SandboxExecutionStateError(SandboxExecutionError): pass
class SandboxExecutionBlockedError(SandboxExecutionError): pass

# ═══════════ Protocol ═══════════

@runtime_checkable
class SandboxExecutionStore(Protocol):
    def create_execution(self, record: SandboxExecutionRecord) -> SandboxExecutionRecord: ...
    def get_execution(self, execution_id: str) -> SandboxExecutionRecord | None: ...
    def list_executions(self, *, tenant_id: str = "", marketplace_agent_id: str = "",
        developer_id: str = "", status: str = "", decision: str = "",
        queue_status: str = "") -> list[SandboxExecutionRecord]: ...
    def update_execution(self, record: SandboxExecutionRecord) -> SandboxExecutionRecord: ...
    def set_execution_status(self, execution_id: str, status: str, actor_id: str | None = None,
        reason: str | None = None) -> SandboxExecutionRecord: ...
    def set_decision(self, execution_id: str, decision: str, actor_id: str | None = None,
        reason: str | None = None) -> SandboxExecutionRecord: ...
    def set_queue_status(self, execution_id: str, queue_status: str, actor_id: str | None = None,
        reason: str | None = None) -> SandboxExecutionRecord: ...
    def cancel_execution(self, execution_id: str, actor_id: str | None = None,
        reason: str | None = None) -> SandboxExecutionRecord: ...
    def expire_execution(self, execution_id: str, actor_id: str | None = None,
        reason: str | None = None) -> SandboxExecutionRecord: ...
    def count_executions(self, *, tenant_id: str = "", status: str = "", decision: str = "",
        queue_status: str = "") -> int: ...
    def add_audit_event(self, event: SandboxExecutionAuditEvent) -> SandboxExecutionAuditEvent: ...
    def list_audit_events(self, execution_id: str) -> list[SandboxExecutionAuditEvent]: ...

def _safe_dt(raw,none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
