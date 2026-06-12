"""Trusted Fixture Execution — built-in fixtures only, NO third-party/package/entrypoint code.

Step 25-H: is_third_party_success()/is_package_success() = always False. No eval/exec/subprocess/network."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

class TrustedFixtureStatus(StrEnum): AVAILABLE="available"; DISABLED="disabled"; BLOCKED="blocked"; DEPRECATED="deprecated"
class TrustedFixtureKind(StrEnum): NOOP="noop"; ECHO_METADATA="echo_metadata"; POLICY_PROOF_SUMMARY="policy_proof_summary"; QUEUE_GATE_SUMMARY="queue_gate_summary"; STATIC_HEALTH_CHECK="static_health_check"
class TrustedFixtureExecutionStatus(StrEnum): DRAFT="draft"; REQUESTED="requested"; FIXTURE_VALIDATED="fixture_validated"; EXECUTED_TRUSTED_FIXTURE="executed_trusted_fixture"; BLOCKED="blocked"; CANCELLED="cancelled"; EXPIRED="expired"; FAIL_CLOSED="fail_closed"
class TrustedFixtureExecutionDecision(StrEnum): ALLOW_TRUSTED_FIXTURE_ONLY="allow_trusted_fixture_only"; BLOCK_THIRD_PARTY_CODE="block_third_party_code"; REVIEW_REQUIRED="review_required"; FAIL_CLOSED="fail_closed"
class TrustedFixtureSafetyLevel(StrEnum): SAFE_NO_SIDE_EFFECTS="safe_no_side_effects"; METADATA_ONLY="metadata_only"; BLOCKED_UNSAFE="blocked_unsafe"; UNKNOWN="unknown"
class TrustedFixtureResultStatus(StrEnum): TRUSTED_FIXTURE_COMPLETED="trusted_fixture_completed"; BLOCKED="blocked"; FAIL_CLOSED="fail_closed"
class TrustedFixtureAuditEventType(StrEnum): FIXTURE_REQUEST_CREATED="fixture_request_created"; FIXTURE_VALIDATED="fixture_validated"; TRUSTED_FIXTURE_EXECUTED="trusted_fixture_executed"; THIRD_PARTY_CODE_BLOCKED="third_party_code_blocked"; STATUS_CHANGED="status_changed"; DECISION_CHANGED="decision_changed"; CANCELLED="cancelled"; EXPIRED="expired"; BLOCKED="blocked"; NOTE_ADDED="note_added"
class TrustedFixtureAuditSeverity(StrEnum): INFO="info"; WARNING="warning"; ERROR="error"; BLOCKER="blocker"

@dataclass
class TrustedFixtureDefinition:
    fixture_id: str = ""; fixture_name: str = ""; fixture_kind: str = TrustedFixtureKind.NOOP
    fixture_status: str = TrustedFixtureStatus.AVAILABLE; safety_level: str = TrustedFixtureSafetyLevel.SAFE_NO_SIDE_EFFECTS
    description: str = ""; allowed_input_keys: list[str] = field(default_factory=list); max_input_size_bytes: int = 4096
    produces_output: bool = True; output_schema_version: str = "1.0.0"
    third_party_code_allowed: bool = False; package_execution_allowed: bool = False
    network_allowed: bool = False; filesystem_allowed: bool = False; secrets_allowed: bool = False
    subprocess_allowed: bool = False; container_allowed: bool = False; worker_queue_allowed: bool = False
    dynamic_import_allowed: bool = False; eval_exec_allowed: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str,Any] = field(default_factory=dict)
    def to_dict(self): return {"fixture_id":self.fixture_id,"fixture_name":self.fixture_name,"fixture_kind":self.fixture_kind,"fixture_status":self.fixture_status,"safety_level":self.safety_level,"description":self.description,"allowed_input_keys":list(self.allowed_input_keys),"max_input_size_bytes":self.max_input_size_bytes,"produces_output":self.produces_output,"output_schema_version":self.output_schema_version,"third_party_code_allowed":self.third_party_code_allowed,"package_execution_allowed":self.package_execution_allowed,"network_allowed":self.network_allowed,"filesystem_allowed":self.filesystem_allowed,"secrets_allowed":self.secrets_allowed,"subprocess_allowed":self.subprocess_allowed,"container_allowed":self.container_allowed,"worker_queue_allowed":self.worker_queue_allowed,"dynamic_import_allowed":self.dynamic_import_allowed,"eval_exec_allowed":self.eval_exec_allowed,"created_at":self.created_at.isoformat() if self.created_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): return cls(fixture_id=str(d.get("fixture_id","")),fixture_name=str(d.get("fixture_name","")),fixture_kind=str(d.get("fixture_kind","noop")),fixture_status=str(d.get("fixture_status","available")),safety_level=str(d.get("safety_level","safe_no_side_effects")),description=str(d.get("description","")),allowed_input_keys=list(d.get("allowed_input_keys",[])),max_input_size_bytes=int(d.get("max_input_size_bytes",4096)),produces_output=bool(d.get("produces_output",True)),output_schema_version=str(d.get("output_schema_version","1.0.0")),third_party_code_allowed=bool(d.get("third_party_code_allowed",False)),package_execution_allowed=bool(d.get("package_execution_allowed",False)),network_allowed=bool(d.get("network_allowed",False)),filesystem_allowed=bool(d.get("filesystem_allowed",False)),secrets_allowed=bool(d.get("secrets_allowed",False)),subprocess_allowed=bool(d.get("subprocess_allowed",False)),container_allowed=bool(d.get("container_allowed",False)),worker_queue_allowed=bool(d.get("worker_queue_allowed",False)),dynamic_import_allowed=bool(d.get("dynamic_import_allowed",False)),eval_exec_allowed=bool(d.get("eval_exec_allowed",False)),created_at=_safe_dt(d.get("created_at")),metadata=dict(d.get("metadata",{})))

@dataclass
class TrustedFixtureExecutionRequest:
    request_id: str = field(default_factory=lambda: f"tfixreq_{uuid4().hex[:16]}")
    fixture_id: str = ""; tenant_id: str = ""
    execution_id: str|None=None; queue_record_id: str|None=None; enforcement_proof_request_id: str|None=None
    requested_by: str|None=None; input_payload_hash: str|None=None
    input_metadata: dict[str,Any] = field(default_factory=dict)
    fixture_snapshot: dict[str,Any] = field(default_factory=dict)
    execution_snapshot: dict[str,Any] = field(default_factory=dict)
    queue_snapshot: dict[str,Any] = field(default_factory=dict)
    enforcement_snapshot: dict[str,Any] = field(default_factory=dict)
    request_status: str = TrustedFixtureExecutionStatus.DRAFT
    decision: str = TrustedFixtureExecutionDecision.FAIL_CLOSED
    safety_level: str = TrustedFixtureSafetyLevel.UNKNOWN
    no_third_party_code_executed: bool = True; no_package_executed: bool = True
    no_entrypoint_executed: bool = True; no_dynamic_import_used: bool = True
    no_eval_exec_used: bool = True; no_network_used: bool = True
    no_filesystem_used: bool = True; no_secret_read: bool = True
    no_subprocess_used: bool = True; no_container_used: bool = True
    no_worker_queue_used: bool = True; no_job_dispatched: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cancelled_at: datetime|None=None; expired_at: datetime|None=None; expires_at: datetime|None=None
    metadata: dict[str,Any] = field(default_factory=dict)
    def is_third_party_execution_allowed(self) -> bool: return False
    def is_package_execution_allowed(self) -> bool: return False
    def is_worker_queue_allowed(self) -> bool: return False
    def to_dict(self): return {"request_id":self.request_id,"fixture_id":self.fixture_id,"tenant_id":self.tenant_id,"execution_id":self.execution_id,"queue_record_id":self.queue_record_id,"enforcement_proof_request_id":self.enforcement_proof_request_id,"requested_by":self.requested_by,"input_payload_hash":self.input_payload_hash,"input_metadata":dict(self.input_metadata),"fixture_snapshot":dict(self.fixture_snapshot),"execution_snapshot":dict(self.execution_snapshot),"queue_snapshot":dict(self.queue_snapshot),"enforcement_snapshot":dict(self.enforcement_snapshot),"request_status":self.request_status,"decision":self.decision,"safety_level":self.safety_level,"no_third_party_code_executed":self.no_third_party_code_executed,"no_package_executed":self.no_package_executed,"no_entrypoint_executed":self.no_entrypoint_executed,"no_dynamic_import_used":self.no_dynamic_import_used,"no_eval_exec_used":self.no_eval_exec_used,"no_network_used":self.no_network_used,"no_filesystem_used":self.no_filesystem_used,"no_secret_read":self.no_secret_read,"no_subprocess_used":self.no_subprocess_used,"no_container_used":self.no_container_used,"no_worker_queue_used":self.no_worker_queue_used,"no_job_dispatched":self.no_job_dispatched,"created_at":self.created_at.isoformat() if self.created_at else None,"updated_at":self.updated_at.isoformat() if self.updated_at else None,"cancelled_at":self.cancelled_at.isoformat() if self.cancelled_at else None,"expired_at":self.expired_at.isoformat() if self.expired_at else None,"expires_at":self.expires_at.isoformat() if self.expires_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): return cls(request_id=str(d.get("request_id","")),fixture_id=str(d.get("fixture_id","")),tenant_id=str(d.get("tenant_id","")),execution_id=d.get("execution_id"),queue_record_id=d.get("queue_record_id"),enforcement_proof_request_id=d.get("enforcement_proof_request_id"),requested_by=d.get("requested_by"),input_payload_hash=d.get("input_payload_hash"),input_metadata=dict(d.get("input_metadata",{})),fixture_snapshot=dict(d.get("fixture_snapshot",{})),execution_snapshot=dict(d.get("execution_snapshot",{})),queue_snapshot=dict(d.get("queue_snapshot",{})),enforcement_snapshot=dict(d.get("enforcement_snapshot",{})),request_status=str(d.get("request_status","draft")),decision=str(d.get("decision","fail_closed")),safety_level=str(d.get("safety_level","unknown")),no_third_party_code_executed=bool(d.get("no_third_party_code_executed",True)),no_package_executed=bool(d.get("no_package_executed",True)),no_entrypoint_executed=bool(d.get("no_entrypoint_executed",True)),no_dynamic_import_used=bool(d.get("no_dynamic_import_used",True)),no_eval_exec_used=bool(d.get("no_eval_exec_used",True)),no_network_used=bool(d.get("no_network_used",True)),no_filesystem_used=bool(d.get("no_filesystem_used",True)),no_secret_read=bool(d.get("no_secret_read",True)),no_subprocess_used=bool(d.get("no_subprocess_used",True)),no_container_used=bool(d.get("no_container_used",True)),no_worker_queue_used=bool(d.get("no_worker_queue_used",True)),no_job_dispatched=bool(d.get("no_job_dispatched",True)),created_at=_safe_dt(d.get("created_at")),updated_at=_safe_dt(d.get("updated_at")),cancelled_at=_safe_dt(d.get("cancelled_at"),True),expired_at=_safe_dt(d.get("expired_at"),True),expires_at=_safe_dt(d.get("expires_at"),True),metadata=dict(d.get("metadata",{})))

@dataclass
class TrustedFixtureExecutionResult:
    result_id: str = field(default_factory=lambda: f"tfixres_{uuid4().hex[:16]}")
    request_id: str = ""; fixture_id: str = ""; tenant_id: str = ""
    result_status: str = TrustedFixtureResultStatus.BLOCKED
    output_metadata: dict[str,Any] = field(default_factory=dict)
    output_payload_hash: str|None=None; duration_ms: int|None=None
    trusted_fixture_executed: bool = False; third_party_code_executed: bool = False
    package_executed: bool = False; entrypoint_executed: bool = False
    dynamic_import_used: bool = False; eval_exec_used: bool = False
    network_used: bool = False; filesystem_used: bool = False; secrets_used: bool = False
    subprocess_used: bool = False; container_used: bool = False
    worker_queue_used: bool = False; job_dispatched: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str,Any] = field(default_factory=dict)
    def is_third_party_success(self) -> bool: return False
    def is_package_success(self) -> bool: return False
    def to_dict(self): return {"result_id":self.result_id,"request_id":self.request_id,"fixture_id":self.fixture_id,"tenant_id":self.tenant_id,"result_status":self.result_status,"output_metadata":dict(self.output_metadata),"output_payload_hash":self.output_payload_hash,"duration_ms":self.duration_ms,"trusted_fixture_executed":self.trusted_fixture_executed,"third_party_code_executed":self.third_party_code_executed,"package_executed":self.package_executed,"entrypoint_executed":self.entrypoint_executed,"dynamic_import_used":self.dynamic_import_used,"eval_exec_used":self.eval_exec_used,"network_used":self.network_used,"filesystem_used":self.filesystem_used,"secrets_used":self.secrets_used,"subprocess_used":self.subprocess_used,"container_used":self.container_used,"worker_queue_used":self.worker_queue_used,"job_dispatched":self.job_dispatched,"created_at":self.created_at.isoformat() if self.created_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): return cls(result_id=str(d.get("result_id","")),request_id=str(d.get("request_id","")),fixture_id=str(d.get("fixture_id","")),tenant_id=str(d.get("tenant_id","")),result_status=str(d.get("result_status","blocked")),output_metadata=dict(d.get("output_metadata",{})),output_payload_hash=d.get("output_payload_hash"),duration_ms=d.get("duration_ms"),trusted_fixture_executed=bool(d.get("trusted_fixture_executed",False)),third_party_code_executed=bool(d.get("third_party_code_executed",False)),package_executed=bool(d.get("package_executed",False)),entrypoint_executed=bool(d.get("entrypoint_executed",False)),dynamic_import_used=bool(d.get("dynamic_import_used",False)),eval_exec_used=bool(d.get("eval_exec_used",False)),network_used=bool(d.get("network_used",False)),filesystem_used=bool(d.get("filesystem_used",False)),secrets_used=bool(d.get("secrets_used",False)),subprocess_used=bool(d.get("subprocess_used",False)),container_used=bool(d.get("container_used",False)),worker_queue_used=bool(d.get("worker_queue_used",False)),job_dispatched=bool(d.get("job_dispatched",False)),created_at=_safe_dt(d.get("created_at")),metadata=dict(d.get("metadata",{})))

@dataclass
class TrustedFixtureAuditEvent:
    event_id: str = field(default_factory=lambda: f"tfixevt_{uuid4().hex[:16]}")
    request_id: str = ""; tenant_id: str = ""; event_type: str = ""; severity: str = TrustedFixtureAuditSeverity.INFO
    actor_id: str|None=None; message: str = ""; metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"event_id":self.event_id,"request_id":self.request_id,"tenant_id":self.tenant_id,"event_type":self.event_type,"severity":self.severity,"actor_id":self.actor_id,"message":self.message,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(event_id=str(d.get("event_id","")),request_id=str(d.get("request_id","")),tenant_id=str(d.get("tenant_id","")),event_type=str(d.get("event_type","")),severity=str(d.get("severity","info")),actor_id=d.get("actor_id"),message=str(d.get("message","")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

class TrustedFixtureExecutionError(Exception): pass
class TrustedFixtureNotFoundError(TrustedFixtureExecutionError): pass
class TrustedFixtureBlockedError(TrustedFixtureExecutionError): pass
class TrustedFixtureStateError(TrustedFixtureExecutionError): pass

@runtime_checkable
class TrustedFixtureExecutionStore(Protocol):
    def create_request(self, request: TrustedFixtureExecutionRequest) -> TrustedFixtureExecutionRequest: ...
    def get_request(self, request_id: str) -> TrustedFixtureExecutionRequest | None: ...
    def list_requests(self, *, tenant_id: str = "", fixture_id: str = "", status: str = "", decision: str = "") -> list[TrustedFixtureExecutionRequest]: ...
    def update_request(self, request: TrustedFixtureExecutionRequest) -> TrustedFixtureExecutionRequest: ...
    def set_request_status(self, request_id: str, status: str, actor_id: str | None = None, reason: str | None = None) -> TrustedFixtureExecutionRequest: ...
    def set_decision(self, request_id: str, decision: str, actor_id: str | None = None, reason: str | None = None) -> TrustedFixtureExecutionRequest: ...
    def create_result(self, result: TrustedFixtureExecutionResult) -> TrustedFixtureExecutionResult: ...
    def get_result(self, result_id: str) -> TrustedFixtureExecutionResult | None: ...
    def get_result_by_request(self, request_id: str) -> TrustedFixtureExecutionResult | None: ...
    def cancel_request(self, request_id: str, actor_id: str | None = None, reason: str | None = None) -> TrustedFixtureExecutionRequest: ...
    def expire_request(self, request_id: str, actor_id: str | None = None, reason: str | None = None) -> TrustedFixtureExecutionRequest: ...
    def add_audit_event(self, event: TrustedFixtureAuditEvent) -> TrustedFixtureAuditEvent: ...
    def list_audit_events(self, request_id: str) -> list[TrustedFixtureAuditEvent]: ...
    def count_requests(self, *, tenant_id: str = "", fixture_id: str = "", status: str = "", decision: str = "") -> int: ...

def _safe_dt(raw, none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
