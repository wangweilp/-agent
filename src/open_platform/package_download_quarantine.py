"""Package Download Quarantine Domain Model — admin-gated download request, metadata-only quarantine.

Step 25-D: No real download. No network. No file write. No extraction. No execution.
is_downloadable()/is_network_allowed()/is_execution_allowed()/is_materialized()/is_executable() = always False.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse
from uuid import uuid4

# ═══════════ Enums ═══════════

class PackageDownloadRequestStatus(StrEnum):
    DRAFT="draft"; REQUESTED="requested"; ADMIN_REVIEW_REQUIRED="admin_review_required"
    ADMIN_APPROVED_FOR_FUTURE_DOWNLOAD="admin_approved_for_future_download"
    ADMIN_REJECTED="admin_rejected"; DOWNLOAD_DISABLED="download_disabled"
    QUARANTINE_RESERVED="quarantine_reserved"; CANCELLED="cancelled"
    EXPIRED="expired"; FAIL_CLOSED="fail_closed"

class PackageDownloadDecision(StrEnum):
    BLOCKED="blocked"; REVIEW_REQUIRED="review_required"
    APPROVED_FOR_FUTURE_DOWNLOAD="approved_for_future_download"
    REJECTED="rejected"; RESERVED_ONLY="reserved_only"; FAIL_CLOSED="fail_closed"

class PackageDownloadGateStatus(StrEnum):
    CLOSED="closed"; ADMIN_REQUIRED="admin_required"
    ADMIN_APPROVED_RESERVED="admin_approved_reserved"; ADMIN_REJECTED="admin_rejected"
    FAIL_CLOSED="fail_closed"

class PackageDownloadQuarantineStatus(StrEnum):
    NOT_CREATED="not_created"; RESERVED_METADATA_ONLY="reserved_metadata_only"
    QUARANTINE_PENDING="quarantine_pending"; BLOCKED="blocked"
    CANCELLED="cancelled"; EXPIRED="expired"

class PackageSourceScheme(StrEnum):
    HTTPS="https"; HTTP_BLOCKED="http_blocked"; GIT_BLOCKED="git_blocked"
    FILE_BLOCKED="file_blocked"; UNKNOWN_BLOCKED="unknown_blocked"

class PackageSourceRiskLevel(StrEnum):
    LOW="low"; MEDIUM="medium"; HIGH="high"; CRITICAL="critical"; UNKNOWN="unknown"

class PackageDownloadAuditEventType(StrEnum):
    REQUEST_CREATED="request_created"; SOURCE_VALIDATED="source_validated"
    ADMIN_GATE_EVALUATED="admin_gate_evaluated"; ADMIN_APPROVED_RESERVED="admin_approved_reserved"
    ADMIN_REJECTED="admin_rejected"; QUARANTINE_RESERVED="quarantine_reserved"
    STATUS_CHANGED="status_changed"; DECISION_CHANGED="decision_changed"
    CANCELLED="cancelled"; EXPIRED="expired"; BLOCKED="blocked"; NOTE_ADDED="note_added"

class PackageDownloadAuditSeverity(StrEnum): INFO="info"; WARNING="warning"; ERROR="error"; BLOCKER="blocker"

_PRIVATE_NETS = ["10.0.0.0/8","172.16.0.0/12","192.168.0.0/16"]
_BLOCKED_HOSTS = {"localhost","127.0.0.1","::1","0.0.0.0","169.254.169.254","metadata.google.internal"}

# ═══════════ PackageSourceMetadata ═══════════

def build_package_source_metadata(raw_url: str | None) -> PackageSourceMetadata:
    if not raw_url or not raw_url.strip():
        return PackageSourceMetadata(source_scheme=PackageSourceScheme.UNKNOWN_BLOCKED,
            is_blocked_source=True, risk_level=PackageSourceRiskLevel.CRITICAL,
            metadata={"reason":"empty_or_none_url","no_network_used":True})

    url = raw_url.strip()
    url_hash = sha256(url.encode()).hexdigest()
    try: parsed = urlparse(url)
    except Exception:
        return PackageSourceMetadata(source_url_hash=url_hash, source_url_redacted="<invalid>",
            source_scheme=PackageSourceScheme.UNKNOWN_BLOCKED, is_blocked_source=True,
            risk_level=PackageSourceRiskLevel.CRITICAL, metadata={"reason":"parse_failed","no_network_used":True})

    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    path_part = (parsed.path or "")[:20] + ("..." if len(parsed.path or "") > 20 else "")
    redacted = f"{scheme}://{host}/{path_part}" if host else "<no host>"

    is_private = _is_private_ip(host)
    is_localhost = host in ("localhost","127.0.0.1","::1","0.0.0.0")
    is_metadata = host in ("169.254.169.254","metadata.google.internal")
    is_file = scheme == "file"
    is_git = scheme in ("git","ssh")
    is_https = scheme == "https"
    is_blocked = not is_https or is_private or is_localhost or is_metadata or is_file or is_git

    src_scheme = PackageSourceScheme.HTTPS
    if is_file: src_scheme = PackageSourceScheme.FILE_BLOCKED
    elif is_git: src_scheme = PackageSourceScheme.GIT_BLOCKED
    elif scheme == "http": src_scheme = PackageSourceScheme.HTTP_BLOCKED
    elif not is_https: src_scheme = PackageSourceScheme.UNKNOWN_BLOCKED

    risk = PackageSourceRiskLevel.UNKNOWN
    if is_metadata: risk = PackageSourceRiskLevel.CRITICAL
    elif is_private or is_localhost: risk = PackageSourceRiskLevel.HIGH
    elif is_blocked: risk = PackageSourceRiskLevel.HIGH
    elif is_https: risk = PackageSourceRiskLevel.LOW

    return PackageSourceMetadata(source_scheme=src_scheme, source_host=host,
        source_port=parsed.port, source_path_hash=sha256((parsed.path or "").encode()).hexdigest()[:16],
        source_url_hash=url_hash, source_url_redacted=redacted, is_https=is_https,
        is_private_ip_literal=is_private, is_localhost=is_localhost, is_metadata_ip=is_metadata,
        is_file_scheme=is_file, is_git_scheme=is_git, is_blocked_source=is_blocked,
        risk_level=risk, metadata={"no_network_used":True,"no_dns_lookup":True})

def _is_private_ip(host: str) -> bool:
    try:
        import ipaddress; addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_unspecified
    except ValueError: return False

# ═══════════ Dataclasses ═══════════

@dataclass
class PackageSourceMetadata:
    source_id: str = field(default_factory=lambda: f"pkgsrc_{uuid4().hex[:16]}")
    source_scheme: str = PackageSourceScheme.UNKNOWN_BLOCKED
    source_host: str | None = None; source_port: int | None = None
    source_path_hash: str | None = None; source_url_hash: str | None = None
    source_url_redacted: str | None = None
    is_https: bool = False; is_private_ip_literal: bool = False; is_localhost: bool = False
    is_metadata_ip: bool = False; is_file_scheme: bool = False; is_git_scheme: bool = False
    is_blocked_source: bool = True; risk_level: str = PackageSourceRiskLevel.CRITICAL
    metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"source_id":self.source_id,"source_scheme":self.source_scheme,"source_host":self.source_host,"source_port":self.source_port,"source_path_hash":self.source_path_hash,"source_url_hash":self.source_url_hash,"source_url_redacted":self.source_url_redacted,"is_https":self.is_https,"is_private_ip_literal":self.is_private_ip_literal,"is_localhost":self.is_localhost,"is_metadata_ip":self.is_metadata_ip,"is_file_scheme":self.is_file_scheme,"is_git_scheme":self.is_git_scheme,"is_blocked_source":self.is_blocked_source,"risk_level":self.risk_level,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(source_id=str(d.get("source_id","")),source_scheme=str(d.get("source_scheme","unknown_blocked")),source_host=d.get("source_host"),source_port=d.get("source_port"),source_path_hash=d.get("source_path_hash"),source_url_hash=d.get("source_url_hash"),source_url_redacted=d.get("source_url_redacted"),is_https=bool(d.get("is_https",False)),is_private_ip_literal=bool(d.get("is_private_ip_literal",False)),is_localhost=bool(d.get("is_localhost",False)),is_metadata_ip=bool(d.get("is_metadata_ip",False)),is_file_scheme=bool(d.get("is_file_scheme",False)),is_git_scheme=bool(d.get("is_git_scheme",False)),is_blocked_source=bool(d.get("is_blocked_source",True)),risk_level=str(d.get("risk_level","critical")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

@dataclass
class PackageDownloadRequest:
    request_id: str = field(default_factory=lambda: f"pkgdl_{uuid4().hex[:16]}")
    artifact_id: str = ""; marketplace_agent_id: str | None = None
    tenant_id: str = ""; developer_id: str | None = None; submission_id: str | None = None
    requested_by: str | None = None
    source_metadata: PackageSourceMetadata = field(default_factory=PackageSourceMetadata)
    request_status: str = PackageDownloadRequestStatus.DRAFT
    decision: str = PackageDownloadDecision.BLOCKED
    gate_status: str = PackageDownloadGateStatus.CLOSED
    quarantine_status: str = PackageDownloadQuarantineStatus.NOT_CREATED
    risk_level: str = PackageSourceRiskLevel.UNKNOWN
    admin_approved_by: str | None = None; admin_rejected_by: str | None = None
    cancelled_by: str | None = None; expired_by: str | None = None
    approval_reason: str | None = None; rejection_reason: str | None = None
    input_payload_hash: str | None = None
    artifact_snapshot: dict[str,Any] = field(default_factory=dict)
    verification_snapshot: dict[str,Any] = field(default_factory=dict)
    execution_snapshot: dict[str,Any] = field(default_factory=dict)
    no_download_performed: bool = True; no_network_used: bool = True
    no_file_written: bool = True; no_package_extracted: bool = True
    no_execution_performed: bool = True; no_subprocess_used: bool = True
    no_container_used: bool = True; no_queue_created: bool = True
    no_job_dispatched: bool = True; no_agent_runtime_used: bool = True
    no_agent_registry_used: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    approved_at: datetime | None = None; rejected_at: datetime | None = None
    cancelled_at: datetime | None = None; expired_at: datetime | None = None
    expires_at: datetime | None = None
    metadata: dict[str,Any] = field(default_factory=dict)

    def __post_init__(self):
        for f in ["artifact_snapshot","verification_snapshot","execution_snapshot","metadata"]:
            if not isinstance(getattr(self,f),dict): raise ValueError(f"{f} must be dict")

    def is_downloadable(self) -> bool: return False
    def is_network_allowed(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False

    def to_dict(self): return {"request_id":self.request_id,"artifact_id":self.artifact_id,"marketplace_agent_id":self.marketplace_agent_id,"tenant_id":self.tenant_id,"developer_id":self.developer_id,"submission_id":self.submission_id,"requested_by":self.requested_by,"source_metadata":self.source_metadata.to_dict(),"request_status":self.request_status,"decision":self.decision,"gate_status":self.gate_status,"quarantine_status":self.quarantine_status,"risk_level":self.risk_level,"admin_approved_by":self.admin_approved_by,"admin_rejected_by":self.admin_rejected_by,"cancelled_by":self.cancelled_by,"expired_by":self.expired_by,"approval_reason":self.approval_reason,"rejection_reason":self.rejection_reason,"input_payload_hash":self.input_payload_hash,"artifact_snapshot":dict(self.artifact_snapshot),"verification_snapshot":dict(self.verification_snapshot),"execution_snapshot":dict(self.execution_snapshot),"no_download_performed":self.no_download_performed,"no_network_used":self.no_network_used,"no_file_written":self.no_file_written,"no_package_extracted":self.no_package_extracted,"no_execution_performed":self.no_execution_performed,"no_subprocess_used":self.no_subprocess_used,"no_container_used":self.no_container_used,"no_queue_created":self.no_queue_created,"no_job_dispatched":self.no_job_dispatched,"no_agent_runtime_used":self.no_agent_runtime_used,"no_agent_registry_used":self.no_agent_registry_used,"created_at":self.created_at.isoformat() if self.created_at else None,"updated_at":self.updated_at.isoformat() if self.updated_at else None,"approved_at":self.approved_at.isoformat() if self.approved_at else None,"rejected_at":self.rejected_at.isoformat() if self.rejected_at else None,"cancelled_at":self.cancelled_at.isoformat() if self.cancelled_at else None,"expired_at":self.expired_at.isoformat() if self.expired_at else None,"expires_at":self.expires_at.isoformat() if self.expires_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): return cls(request_id=str(d.get("request_id","")),artifact_id=str(d.get("artifact_id","")),marketplace_agent_id=d.get("marketplace_agent_id"),tenant_id=str(d.get("tenant_id","")),developer_id=d.get("developer_id"),submission_id=d.get("submission_id"),requested_by=d.get("requested_by"),source_metadata=PackageSourceMetadata.from_dict(d["source_metadata"]) if isinstance(d.get("source_metadata"),dict) else PackageSourceMetadata(),request_status=str(d.get("request_status","draft")),decision=str(d.get("decision","blocked")),gate_status=str(d.get("gate_status","closed")),quarantine_status=str(d.get("quarantine_status","not_created")),risk_level=str(d.get("risk_level","unknown")),admin_approved_by=d.get("admin_approved_by"),admin_rejected_by=d.get("admin_rejected_by"),cancelled_by=d.get("cancelled_by"),expired_by=d.get("expired_by"),approval_reason=d.get("approval_reason"),rejection_reason=d.get("rejection_reason"),input_payload_hash=d.get("input_payload_hash"),artifact_snapshot=dict(d.get("artifact_snapshot",{})),verification_snapshot=dict(d.get("verification_snapshot",{})),execution_snapshot=dict(d.get("execution_snapshot",{})),no_download_performed=bool(d.get("no_download_performed",True)),no_network_used=bool(d.get("no_network_used",True)),no_file_written=bool(d.get("no_file_written",True)),no_package_extracted=bool(d.get("no_package_extracted",True)),no_execution_performed=bool(d.get("no_execution_performed",True)),no_subprocess_used=bool(d.get("no_subprocess_used",True)),no_container_used=bool(d.get("no_container_used",True)),no_queue_created=bool(d.get("no_queue_created",True)),no_job_dispatched=bool(d.get("no_job_dispatched",True)),no_agent_runtime_used=bool(d.get("no_agent_runtime_used",True)),no_agent_registry_used=bool(d.get("no_agent_registry_used",True)),created_at=_safe_dt(d.get("created_at")),updated_at=_safe_dt(d.get("updated_at")),approved_at=_safe_dt(d.get("approved_at"),none_ok=True),rejected_at=_safe_dt(d.get("rejected_at"),none_ok=True),cancelled_at=_safe_dt(d.get("cancelled_at"),none_ok=True),expired_at=_safe_dt(d.get("expired_at"),none_ok=True),expires_at=_safe_dt(d.get("expires_at"),none_ok=True),metadata=dict(d.get("metadata",{})))

@dataclass
class PackageDownloadQuarantineRecord:
    quarantine_id: str = field(default_factory=lambda: f"pkgq_{uuid4().hex[:16]}")
    request_id: str = ""; artifact_id: str = ""; tenant_id: str = ""
    quarantine_status: str = PackageDownloadQuarantineStatus.NOT_CREATED
    logical_quarantine_ref: str | None = None
    file_materialized: bool = False; file_size_bytes: int | None = None
    content_sha256: str | None = None
    extraction_allowed: bool = False; execution_allowed: bool = False
    created_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str,Any] = field(default_factory=dict)
    def is_materialized(self) -> bool: return False
    def is_executable(self) -> bool: return False
    def to_dict(self): return {"quarantine_id":self.quarantine_id,"request_id":self.request_id,"artifact_id":self.artifact_id,"tenant_id":self.tenant_id,"quarantine_status":self.quarantine_status,"logical_quarantine_ref":self.logical_quarantine_ref,"file_materialized":self.file_materialized,"file_size_bytes":self.file_size_bytes,"content_sha256":self.content_sha256,"extraction_allowed":self.extraction_allowed,"execution_allowed":self.execution_allowed,"created_by":self.created_by,"created_at":self.created_at.isoformat() if self.created_at else None,"updated_at":self.updated_at.isoformat() if self.updated_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): return cls(quarantine_id=str(d.get("quarantine_id","")),request_id=str(d.get("request_id","")),artifact_id=str(d.get("artifact_id","")),tenant_id=str(d.get("tenant_id","")),quarantine_status=str(d.get("quarantine_status","not_created")),logical_quarantine_ref=d.get("logical_quarantine_ref"),file_materialized=bool(d.get("file_materialized",False)),file_size_bytes=d.get("file_size_bytes"),content_sha256=d.get("content_sha256"),extraction_allowed=bool(d.get("extraction_allowed",False)),execution_allowed=bool(d.get("execution_allowed",False)),created_by=d.get("created_by"),created_at=_safe_dt(d.get("created_at")),updated_at=_safe_dt(d.get("updated_at")),metadata=dict(d.get("metadata",{})))

@dataclass
class PackageDownloadAuditEvent:
    event_id: str = field(default_factory=lambda: f"pkgdlevt_{uuid4().hex[:16]}")
    request_id: str = ""; tenant_id: str = ""
    event_type: str = ""; severity: str = PackageDownloadAuditSeverity.INFO
    actor_id: str | None = None; message: str = ""
    metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"event_id":self.event_id,"request_id":self.request_id,"tenant_id":self.tenant_id,"event_type":self.event_type,"severity":self.severity,"actor_id":self.actor_id,"message":self.message,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(event_id=str(d.get("event_id","")),request_id=str(d.get("request_id","")),tenant_id=str(d.get("tenant_id","")),event_type=str(d.get("event_type","")),severity=str(d.get("severity","info")),actor_id=d.get("actor_id"),message=str(d.get("message","")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

# ═══════════ Errors ═══════════
class PackageDownloadQuarantineError(Exception): pass
class PackageDownloadRequestNotFoundError(PackageDownloadQuarantineError): pass
class PackageDownloadRequestAlreadyExistsError(PackageDownloadQuarantineError): pass
class PackageDownloadStateError(PackageDownloadQuarantineError): pass
class PackageDownloadBlockedError(PackageDownloadQuarantineError): pass

# ═══════════ Protocol ═══════════
@runtime_checkable
class PackageDownloadQuarantineStore(Protocol):
    def create_request(self, request: PackageDownloadRequest) -> PackageDownloadRequest: ...
    def get_request(self, request_id: str) -> PackageDownloadRequest | None: ...
    def list_requests(self, *, tenant_id: str = "", artifact_id: str = "", marketplace_agent_id: str = "",
        status: str = "", decision: str = "", gate_status: str = "", quarantine_status: str = "") -> list[PackageDownloadRequest]: ...
    def update_request(self, request: PackageDownloadRequest) -> PackageDownloadRequest: ...
    def set_request_status(self, request_id: str, status: str, actor_id: str | None = None, reason: str | None = None) -> PackageDownloadRequest: ...
    def set_decision(self, request_id: str, decision: str, actor_id: str | None = None, reason: str | None = None) -> PackageDownloadRequest: ...
    def set_gate_status(self, request_id: str, gate_status: str, actor_id: str | None = None, reason: str | None = None) -> PackageDownloadRequest: ...
    def approve_for_future_download(self, request_id: str, actor_id: str | None = None, reason: str | None = None) -> PackageDownloadRequest: ...
    def reject_request(self, request_id: str, actor_id: str | None = None, reason: str | None = None) -> PackageDownloadRequest: ...
    def cancel_request(self, request_id: str, actor_id: str | None = None, reason: str | None = None) -> PackageDownloadRequest: ...
    def expire_request(self, request_id: str, actor_id: str | None = None, reason: str | None = None) -> PackageDownloadRequest: ...
    def reserve_quarantine_record(self, record: PackageDownloadQuarantineRecord) -> PackageDownloadQuarantineRecord: ...
    def get_quarantine_record(self, quarantine_id: str) -> PackageDownloadQuarantineRecord | None: ...
    def get_quarantine_by_request(self, request_id: str) -> PackageDownloadQuarantineRecord | None: ...
    def add_audit_event(self, event: PackageDownloadAuditEvent) -> PackageDownloadAuditEvent: ...
    def list_audit_events(self, request_id: str) -> list[PackageDownloadAuditEvent]: ...
    def count_requests(self, *, tenant_id: str = "", status: str = "", decision: str = "", gate_status: str = "") -> int: ...

def _safe_dt(raw,none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
