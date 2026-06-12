"""Artifact Extraction Guard — read-only entry metadata validation, no archive file read, no extraction, no file write.
Step 25-E: string-only path validation. No zipfile/tarfile/shutil/open. is_extraction_allowed()/is_execution_allowed()=False."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

class ArchiveFormat(StrEnum):
    ZIP_RESERVED="zip_reserved"; TAR_RESERVED="tar_reserved"; TAR_GZ_RESERVED="tar_gz_reserved"
    WHEEL_RESERVED="wheel_reserved"; SOURCE_DIST_RESERVED="source_dist_reserved"; UNKNOWN_BLOCKED="unknown_blocked"
class ArchiveEntryType(StrEnum):
    FILE="file"; DIRECTORY="directory"; SYMLINK_BLOCKED="symlink_blocked"; HARDLINK_BLOCKED="hardlink_blocked"
    DEVICE_BLOCKED="device_blocked"; FIFO_BLOCKED="fifo_blocked"; SOCKET_BLOCKED="socket_blocked"; UNKNOWN_BLOCKED="unknown_blocked"
class ExtractionGuardRequestStatus(StrEnum):
    DRAFT="draft"; REQUESTED="requested"; GUARD_REVIEW_REQUIRED="guard_review_required"
    VALIDATED_METADATA_ONLY="validated_metadata_only"; BLOCKED="blocked"; EXTRACTION_DISABLED="extraction_disabled"
    PLAN_RESERVED_METADATA_ONLY="plan_reserved_metadata_only"; CANCELLED="cancelled"; EXPIRED="expired"; FAIL_CLOSED="fail_closed"
class ExtractionGuardDecision(StrEnum):
    BLOCKED="blocked"; REVIEW_REQUIRED="review_required"; METADATA_VALIDATED="metadata_validated"
    RESERVED_ONLY="reserved_only"; FAIL_CLOSED="fail_closed"
class ExtractionGuardStatus(StrEnum):
    NOT_EVALUATED="not_evaluated"; PASSED_METADATA_ONLY="passed_metadata_only"
    BLOCKED="blocked"; REVIEW_REQUIRED="review_required"; FAIL_CLOSED="fail_closed"
class ExtractionPlanStatus(StrEnum):
    NOT_CREATED="not_created"; RESERVED_METADATA_ONLY="reserved_metadata_only"
    EXTRACTION_DISABLED="extraction_disabled"; BLOCKED="blocked"; CANCELLED="cancelled"; EXPIRED="expired"
class ArchiveEntryRiskLevel(StrEnum):
    LOW="low"; MEDIUM="medium"; HIGH="high"; CRITICAL="critical"; UNKNOWN="unknown"
class ExtractionGuardCheckType(StrEnum):
    NO_ARCHIVE_FILE_READ="no_archive_file_read"; NO_EXTRACTION_PERFORMED="no_extraction_performed"
    NO_FILE_WRITTEN="no_file_written"; NO_EXECUTION_PERFORMED="no_execution_performed"
    ENTRY_NAME_PRESENT="entry_name_present"; ENTRY_PATH_NORMALIZED="entry_path_normalized"
    PATH_TRAVERSAL_BLOCKED="path_traversal_blocked"; ZIP_SLIP_BLOCKED="zip_slip_blocked"
    ABSOLUTE_PATH_BLOCKED="absolute_path_blocked"; WINDOWS_DRIVE_BLOCKED="windows_drive_blocked"
    UNC_PATH_BLOCKED="unc_path_blocked"; NUL_BYTE_BLOCKED="nul_byte_blocked"
    SYMLINK_BLOCKED="symlink_blocked"; HARDLINK_BLOCKED="hardlink_blocked"
    DEVICE_ENTRY_BLOCKED="device_entry_blocked"; FIFO_ENTRY_BLOCKED="fifo_entry_blocked"
    SOCKET_ENTRY_BLOCKED="socket_entry_blocked"; DUPLICATE_PATH_BLOCKED="duplicate_path_blocked"
    MAX_ENTRY_COUNT_CHECKED="max_entry_count_checked"; MAX_ENTRY_SIZE_CHECKED="max_entry_size_checked"
    MAX_TOTAL_SIZE_CHECKED="max_total_size_checked"; EXECUTABLE_PERMISSION_REVIEWED="executable_permission_reviewed"
    SCRIPT_EXTENSION_REVIEWED="script_extension_reviewed"; MANIFEST_METADATA_ONLY="manifest_metadata_only"
    FAIL_CLOSED_ON_UNKNOWN="fail_closed_on_unknown"
class ExtractionGuardCheckStatus(StrEnum):
    PASSED="passed"; WARNING="warning"; BLOCKED="blocked"; FAILED="failed"; SKIPPED="skipped"
class ExtractionGuardSeverity(StrEnum):
    INFO="info"; WARNING="warning"; ERROR="error"; BLOCKER="blocker"
class ArtifactExtractionAuditEventType(StrEnum):
    REQUEST_CREATED="request_created"; ENTRY_VALIDATED="entry_validated"; GUARD_EVALUATED="guard_evaluated"
    PLAN_RESERVED="plan_reserved"; STATUS_CHANGED="status_changed"; DECISION_CHANGED="decision_changed"
    BLOCKED="blocked"; CANCELLED="cancelled"; EXPIRED="expired"; NOTE_ADDED="note_added"
class ArtifactExtractionAuditSeverity(StrEnum):
    INFO="info"; WARNING="warning"; ERROR="error"; BLOCKER="blocker"

_SCRIPT_EXTENSIONS = {".py",".sh",".bash",".exe",".bat",".ps1",".cmd",".vbs",".js"}
_EXEC_MODES = {"755","775","777","555","700","744","644"}  # 644 is just writable, but let's be conservative

def _hash(s: str) -> str: return sha256((s or "").encode()).hexdigest()
def _redact(s: str) -> str:
    if not s: return "<empty>"
    parts = s.replace("\\","/").split("/")
    if len(parts) <= 2: return ".../" + parts[-1] if parts else s
    return ".../" + "/".join(parts[-2:])

def build_archive_entry_metadata(
    entry_name: str | None, entry_type: str = ArchiveEntryType.FILE,
    size_bytes: int | None = None, compressed_size_bytes: int | None = None,
    mode: str | None = None, link_target: str | None = None,
) -> ArchiveEntryMetadata:
    name = (entry_name or "").strip()
    entry_type = str(entry_type)
    has_traversal = False; has_win_drive = False; has_unc = False
    has_nul = "\x00" in name; has_abs_path = False; normalized = ""
    is_blocked = False; ent = ArchiveEntryType.FILE
    name_hash = _hash(name); name_redacted = _redact(name)

    if not name:
        return ArchiveEntryMetadata(raw_entry_name_hash=name_hash, entry_name_redacted="<empty>",
            entry_type=ArchiveEntryType.UNKNOWN_BLOCKED, is_blocked=True,
            risk_level=ArchiveEntryRiskLevel.CRITICAL, metadata={"reason":"empty_entry_name"})

    if entry_type in (ArchiveEntryType.SYMLINK_BLOCKED, ArchiveEntryType.HARDLINK_BLOCKED,
        ArchiveEntryType.DEVICE_BLOCKED, ArchiveEntryType.FIFO_BLOCKED, ArchiveEntryType.SOCKET_BLOCKED,
        ArchiveEntryType.UNKNOWN_BLOCKED):
        is_blocked = True; ent = ArchiveEntryType(entry_type)

    # Normalize
    try:
        p = PurePosixPath(name)
        has_abs_path = p.is_absolute()
        parts = p.parts
        has_traversal = any(x == ".." for x in parts)
        normalized = str(p)
    except Exception:
        is_blocked = True

    # Path checks
    if has_nul: is_blocked = True
    if has_abs_path: is_blocked = True
    if has_traversal: is_blocked = True
    if "\\\\" in name.replace("/","\\") or name.startswith("\\\\"): has_unc = True; is_blocked = True
    if any(name.lstrip("/").lower().startswith(f"{d}:") for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ".lower()): has_win_drive = True; is_blocked = True
    if "__MACOSX" in name or name.startswith(".") and "/." not in name and name.count("/") < 2:
        pass  # dotfiles are fine, __MACOSX is suspicious but not blocked

    # Type
    if not entry_type.startswith(("symlink_","hardlink_","device_","fifo_","socket_","unknown_")):
        if entry_type == "directory" or entry_type == "dir":
            ent = ArchiveEntryType.DIRECTORY
        else:
            ent = ArchiveEntryType.FILE

    # Executable/script flags
    has_exec_perm = str(mode or "") in _EXEC_MODES
    has_script = any(name.lower().rstrip("/").endswith(ext) for ext in _SCRIPT_EXTENSIONS)

    if size_bytes is not None and size_bytes < 0: is_blocked = True

    risk = ArchiveEntryRiskLevel.LOW
    if is_blocked: risk = ArchiveEntryRiskLevel.CRITICAL
    elif has_exec_perm or has_script: risk = ArchiveEntryRiskLevel.MEDIUM

    return ArchiveEntryMetadata(
        raw_entry_name_hash=name_hash, entry_name_redacted=name_redacted,
        normalized_path=normalized, entry_type=ent, size_bytes=size_bytes,
        compressed_size_bytes=compressed_size_bytes, mode=mode,
        link_target_hash=_hash(link_target) if link_target else None,
        link_target_redacted=_redact(link_target) if link_target else None,
        is_directory=(ent == ArchiveEntryType.DIRECTORY),
        is_symlink=(ent == ArchiveEntryType.SYMLINK_BLOCKED),
        is_hardlink=(ent == ArchiveEntryType.HARDLINK_BLOCKED),
        is_device=(ent == ArchiveEntryType.DEVICE_BLOCKED),
        is_fifo=(ent == ArchiveEntryType.FIFO_BLOCKED),
        is_socket=(ent == ArchiveEntryType.SOCKET_BLOCKED),
        is_absolute_path=has_abs_path, has_parent_traversal=has_traversal,
        has_windows_drive=has_win_drive, has_unc_path=has_unc, has_nul_byte=has_nul,
        has_duplicate_normalized_path=False, has_executable_permission=has_exec_perm,
        has_script_extension=has_script, is_blocked=is_blocked, risk_level=risk,
        metadata={"no_file_read":True,"no_extraction":True})

# ═══════════ Dataclasses ═══════════

@dataclass
class ArchiveEntryMetadata:
    entry_id: str = field(default_factory=lambda: f"arcent_{uuid4().hex[:16]}")
    raw_entry_name_hash: str | None = None; entry_name_redacted: str | None = None
    normalized_path: str | None = None; entry_type: str = ArchiveEntryType.FILE
    size_bytes: int | None = None; compressed_size_bytes: int | None = None
    mode: str | None = None; link_target_hash: str | None = None
    link_target_redacted: str | None = None
    is_directory: bool = False; is_symlink: bool = False; is_hardlink: bool = False
    is_device: bool = False; is_fifo: bool = False; is_socket: bool = False
    is_absolute_path: bool = False; has_parent_traversal: bool = False
    has_windows_drive: bool = False; has_unc_path: bool = False; has_nul_byte: bool = False
    has_duplicate_normalized_path: bool = False; has_executable_permission: bool = False
    has_script_extension: bool = False; is_blocked: bool = False
    risk_level: str = ArchiveEntryRiskLevel.UNKNOWN
    metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"entry_id":self.entry_id,"raw_entry_name_hash":self.raw_entry_name_hash,"entry_name_redacted":self.entry_name_redacted,"normalized_path":self.normalized_path,"entry_type":self.entry_type,"size_bytes":self.size_bytes,"compressed_size_bytes":self.compressed_size_bytes,"mode":self.mode,"link_target_hash":self.link_target_hash,"link_target_redacted":self.link_target_redacted,"is_directory":self.is_directory,"is_symlink":self.is_symlink,"is_hardlink":self.is_hardlink,"is_device":self.is_device,"is_fifo":self.is_fifo,"is_socket":self.is_socket,"is_absolute_path":self.is_absolute_path,"has_parent_traversal":self.has_parent_traversal,"has_windows_drive":self.has_windows_drive,"has_unc_path":self.has_unc_path,"has_nul_byte":self.has_nul_byte,"has_duplicate_normalized_path":self.has_duplicate_normalized_path,"has_executable_permission":self.has_executable_permission,"has_script_extension":self.has_script_extension,"is_blocked":self.is_blocked,"risk_level":self.risk_level,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(entry_id=str(d.get("entry_id","")),raw_entry_name_hash=d.get("raw_entry_name_hash"),entry_name_redacted=d.get("entry_name_redacted"),normalized_path=d.get("normalized_path"),entry_type=str(d.get("entry_type","file")),size_bytes=d.get("size_bytes"),compressed_size_bytes=d.get("compressed_size_bytes"),mode=d.get("mode"),link_target_hash=d.get("link_target_hash"),link_target_redacted=d.get("link_target_redacted"),is_directory=bool(d.get("is_directory",False)),is_symlink=bool(d.get("is_symlink",False)),is_hardlink=bool(d.get("is_hardlink",False)),is_device=bool(d.get("is_device",False)),is_fifo=bool(d.get("is_fifo",False)),is_socket=bool(d.get("is_socket",False)),is_absolute_path=bool(d.get("is_absolute_path",False)),has_parent_traversal=bool(d.get("has_parent_traversal",False)),has_windows_drive=bool(d.get("has_windows_drive",False)),has_unc_path=bool(d.get("has_unc_path",False)),has_nul_byte=bool(d.get("has_nul_byte",False)),has_duplicate_normalized_path=bool(d.get("has_duplicate_normalized_path",False)),has_executable_permission=bool(d.get("has_executable_permission",False)),has_script_extension=bool(d.get("has_script_extension",False)),is_blocked=bool(d.get("is_blocked",False)),risk_level=str(d.get("risk_level","unknown")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

@dataclass
class ArtifactExtractionGuardRequest:
    request_id: str = field(default_factory=lambda: f"extreq_{uuid4().hex[:16]}")
    package_download_request_id: str | None = None; package_quarantine_id: str | None = None
    artifact_id: str = ""; tenant_id: str = ""; developer_id: str | None = None
    submission_id: str | None = None; requested_by: str | None = None
    archive_format: str = ArchiveFormat.UNKNOWN_BLOCKED
    guard_request_status: str = ExtractionGuardRequestStatus.DRAFT
    decision: str = ExtractionGuardDecision.BLOCKED; guard_status: str = ExtractionGuardStatus.NOT_EVALUATED
    plan_status: str = ExtractionPlanStatus.NOT_CREATED; risk_level: str = ArchiveEntryRiskLevel.UNKNOWN
    entry_count: int = 0; total_declared_size_bytes: int | None = None
    max_entry_count: int = 1000; max_entry_size_bytes: int = 50000000; max_total_size_bytes: int = 200000000
    source_snapshot: dict[str,Any] = field(default_factory=dict)
    download_request_snapshot: dict[str,Any] = field(default_factory=dict)
    quarantine_record_snapshot: dict[str,Any] = field(default_factory=dict)
    artifact_snapshot: dict[str,Any] = field(default_factory=dict)
    entries: list[ArchiveEntryMetadata] = field(default_factory=list)
    no_archive_file_read: bool = True; no_extraction_performed: bool = True
    no_file_written: bool = True; no_execution_performed: bool = True
    no_subprocess_used: bool = True; no_container_used: bool = True; no_network_used: bool = True
    no_queue_created: bool = True; no_job_dispatched: bool = True
    no_agent_runtime_used: bool = True; no_agent_registry_used: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cancelled_at: datetime | None = None; expired_at: datetime | None = None
    expires_at: datetime | None = None; metadata: dict[str,Any] = field(default_factory=dict)
    def __post_init__(self):
        for f in ["source_snapshot","download_request_snapshot","quarantine_record_snapshot","artifact_snapshot","metadata"]:
            if not isinstance(getattr(self,f),dict): raise ValueError(f"{f} must be dict")
    def is_extraction_allowed(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False
    def to_dict(self):
        entries = [e.to_dict() for e in self.entries]
        return {"request_id":self.request_id,"package_download_request_id":self.package_download_request_id,"package_quarantine_id":self.package_quarantine_id,"artifact_id":self.artifact_id,"tenant_id":self.tenant_id,"developer_id":self.developer_id,"submission_id":self.submission_id,"requested_by":self.requested_by,"archive_format":self.archive_format,"guard_request_status":self.guard_request_status,"decision":self.decision,"guard_status":self.guard_status,"plan_status":self.plan_status,"risk_level":self.risk_level,"entry_count":self.entry_count,"total_declared_size_bytes":self.total_declared_size_bytes,"max_entry_count":self.max_entry_count,"max_entry_size_bytes":self.max_entry_size_bytes,"max_total_size_bytes":self.max_total_size_bytes,"source_snapshot":dict(self.source_snapshot),"download_request_snapshot":dict(self.download_request_snapshot),"quarantine_record_snapshot":dict(self.quarantine_record_snapshot),"artifact_snapshot":dict(self.artifact_snapshot),"entries":entries,"no_archive_file_read":self.no_archive_file_read,"no_extraction_performed":self.no_extraction_performed,"no_file_written":self.no_file_written,"no_execution_performed":self.no_execution_performed,"no_subprocess_used":self.no_subprocess_used,"no_container_used":self.no_container_used,"no_network_used":self.no_network_used,"no_queue_created":self.no_queue_created,"no_job_dispatched":self.no_job_dispatched,"no_agent_runtime_used":self.no_agent_runtime_used,"no_agent_registry_used":self.no_agent_registry_used,"created_at":self.created_at.isoformat() if self.created_at else None,"updated_at":self.updated_at.isoformat() if self.updated_at else None,"cancelled_at":self.cancelled_at.isoformat() if self.cancelled_at else None,"expired_at":self.expired_at.isoformat() if self.expired_at else None,"expires_at":self.expires_at.isoformat() if self.expires_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d):
        entries = [ArchiveEntryMetadata.from_dict(e) for e in d.get("entries",[])]
        return cls(request_id=str(d.get("request_id","")),package_download_request_id=d.get("package_download_request_id"),package_quarantine_id=d.get("package_quarantine_id"),artifact_id=str(d.get("artifact_id","")),tenant_id=str(d.get("tenant_id","")),developer_id=d.get("developer_id"),submission_id=d.get("submission_id"),requested_by=d.get("requested_by"),archive_format=str(d.get("archive_format","unknown_blocked")),guard_request_status=str(d.get("guard_request_status","draft")),decision=str(d.get("decision","blocked")),guard_status=str(d.get("guard_status","not_evaluated")),plan_status=str(d.get("plan_status","not_created")),risk_level=str(d.get("risk_level","unknown")),entry_count=int(d.get("entry_count",0)),total_declared_size_bytes=d.get("total_declared_size_bytes"),max_entry_count=int(d.get("max_entry_count",1000)),max_entry_size_bytes=int(d.get("max_entry_size_bytes",50000000)),max_total_size_bytes=int(d.get("max_total_size_bytes",200000000)),source_snapshot=dict(d.get("source_snapshot",{})),download_request_snapshot=dict(d.get("download_request_snapshot",{})),quarantine_record_snapshot=dict(d.get("quarantine_record_snapshot",{})),artifact_snapshot=dict(d.get("artifact_snapshot",{})),entries=entries,no_archive_file_read=bool(d.get("no_archive_file_read",True)),no_extraction_performed=bool(d.get("no_extraction_performed",True)),no_file_written=bool(d.get("no_file_written",True)),no_execution_performed=bool(d.get("no_execution_performed",True)),no_subprocess_used=bool(d.get("no_subprocess_used",True)),no_container_used=bool(d.get("no_container_used",True)),no_network_used=bool(d.get("no_network_used",True)),no_queue_created=bool(d.get("no_queue_created",True)),no_job_dispatched=bool(d.get("no_job_dispatched",True)),no_agent_runtime_used=bool(d.get("no_agent_runtime_used",True)),no_agent_registry_used=bool(d.get("no_agent_registry_used",True)),created_at=_safe_dt(d.get("created_at")),updated_at=_safe_dt(d.get("updated_at")),cancelled_at=_safe_dt(d.get("cancelled_at"),True),expired_at=_safe_dt(d.get("expired_at"),True),expires_at=_safe_dt(d.get("expires_at"),True),metadata=dict(d.get("metadata",{})))

@dataclass
class ExtractionGuardCheck:
    check_id: str = field(default_factory=lambda: f"extchk_{uuid4().hex[:16]}")
    request_id: str = ""; check_type: str = ""; status: str = ExtractionGuardCheckStatus.PASSED
    severity: str = ExtractionGuardSeverity.INFO; message: str = ""
    metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"check_id":self.check_id,"request_id":self.request_id,"check_type":self.check_type,"status":self.status,"severity":self.severity,"message":self.message,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(check_id=str(d.get("check_id","")),request_id=str(d.get("request_id","")),check_type=str(d.get("check_type","")),status=str(d.get("status","passed")),severity=str(d.get("severity","info")),message=str(d.get("message","")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

@dataclass
class ArtifactExtractionGuardResult:
    result_id: str = field(default_factory=lambda: f"extres_{uuid4().hex[:16]}")
    request_id: str = ""; tenant_id: str = ""
    guard_status: str = ExtractionGuardStatus.NOT_EVALUATED; decision: str = ExtractionGuardDecision.BLOCKED
    checks: list[ExtractionGuardCheck] = field(default_factory=list)
    total_entries: int = 0; accepted_entries: int = 0; blocked_entries: int = 0
    warnings_count: int = 0; errors_count: int = 0; blockers_count: int = 0
    normalized_paths: list[str] = field(default_factory=list); blocked_entry_ids: list[str] = field(default_factory=list)
    metadata_only: bool = True; no_archive_file_read: bool = True; no_extraction_performed: bool = True
    no_file_written: bool = True; no_execution_performed: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str,Any] = field(default_factory=dict)
    def add_check(self,c): self.checks.append(c); self._recount()
    def _recount(self):
        self.warnings_count=sum(1 for c in self.checks if c.status==ExtractionGuardCheckStatus.WARNING)
        self.errors_count=sum(1 for c in self.checks if c.status==ExtractionGuardCheckStatus.FAILED)
        self.blockers_count=sum(1 for c in self.checks if c.status==ExtractionGuardCheckStatus.BLOCKED)
    def calculate_status(self):
        self._recount()
        if self.blockers_count>0: self.guard_status=ExtractionGuardStatus.BLOCKED; self.decision=ExtractionGuardDecision.BLOCKED
        elif self.errors_count>0: self.guard_status=ExtractionGuardStatus.BLOCKED
        elif self.warnings_count>0: self.guard_status=ExtractionGuardStatus.PASSED_METADATA_ONLY; self.decision=ExtractionGuardDecision.METADATA_VALIDATED
        else: self.guard_status=ExtractionGuardStatus.PASSED_METADATA_ONLY; self.decision=ExtractionGuardDecision.METADATA_VALIDATED
    def is_extraction_allowed(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False
    def to_dict(self): return {"result_id":self.result_id,"request_id":self.request_id,"tenant_id":self.tenant_id,"guard_status":self.guard_status,"decision":self.decision,"checks":[c.to_dict() for c in self.checks],"total_entries":self.total_entries,"accepted_entries":self.accepted_entries,"blocked_entries":self.blocked_entries,"warnings_count":self.warnings_count,"errors_count":self.errors_count,"blockers_count":self.blockers_count,"normalized_paths":list(self.normalized_paths),"blocked_entry_ids":list(self.blocked_entry_ids),"metadata_only":self.metadata_only,"no_archive_file_read":self.no_archive_file_read,"no_extraction_performed":self.no_extraction_performed,"no_file_written":self.no_file_written,"no_execution_performed":self.no_execution_performed,"created_at":self.created_at.isoformat() if self.created_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): checks=[ExtractionGuardCheck.from_dict(c) for c in d.get("checks",[])]; return cls(result_id=str(d.get("result_id","")),request_id=str(d.get("request_id","")),tenant_id=str(d.get("tenant_id","")),guard_status=str(d.get("guard_status","not_evaluated")),decision=str(d.get("decision","blocked")),checks=checks,total_entries=int(d.get("total_entries",0)),accepted_entries=int(d.get("accepted_entries",0)),blocked_entries=int(d.get("blocked_entries",0)),warnings_count=int(d.get("warnings_count",0)),errors_count=int(d.get("errors_count",0)),blockers_count=int(d.get("blockers_count",0)),normalized_paths=list(d.get("normalized_paths",[])),blocked_entry_ids=list(d.get("blocked_entry_ids",[])),metadata_only=bool(d.get("metadata_only",True)),no_archive_file_read=bool(d.get("no_archive_file_read",True)),no_extraction_performed=bool(d.get("no_extraction_performed",True)),no_file_written=bool(d.get("no_file_written",True)),no_execution_performed=bool(d.get("no_execution_performed",True)),created_at=_safe_dt(d.get("created_at")),metadata=dict(d.get("metadata",{})))

@dataclass
class ReadOnlyExtractionPlan:
    plan_id: str = field(default_factory=lambda: f"extplan_{uuid4().hex[:16]}")
    request_id: str = ""; artifact_id: str = ""; tenant_id: str = ""
    plan_status: str = ExtractionPlanStatus.NOT_CREATED
    logical_extraction_ref: str | None = None
    allowed_normalized_paths: list[str] = field(default_factory=list)
    blocked_entry_ids: list[str] = field(default_factory=list)
    extraction_allowed: bool = False; file_write_allowed: bool = False
    execution_allowed: bool = False; metadata_only: bool = True
    created_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str,Any] = field(default_factory=dict)
    def is_materialized(self) -> bool: return False
    def is_executable(self) -> bool: return False
    def to_dict(self): return {"plan_id":self.plan_id,"request_id":self.request_id,"artifact_id":self.artifact_id,"tenant_id":self.tenant_id,"plan_status":self.plan_status,"logical_extraction_ref":self.logical_extraction_ref,"allowed_normalized_paths":list(self.allowed_normalized_paths),"blocked_entry_ids":list(self.blocked_entry_ids),"extraction_allowed":self.extraction_allowed,"file_write_allowed":self.file_write_allowed,"execution_allowed":self.execution_allowed,"metadata_only":self.metadata_only,"created_by":self.created_by,"created_at":self.created_at.isoformat() if self.created_at else None,"updated_at":self.updated_at.isoformat() if self.updated_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): return cls(plan_id=str(d.get("plan_id","")),request_id=str(d.get("request_id","")),artifact_id=str(d.get("artifact_id","")),tenant_id=str(d.get("tenant_id","")),plan_status=str(d.get("plan_status","not_created")),logical_extraction_ref=d.get("logical_extraction_ref"),allowed_normalized_paths=list(d.get("allowed_normalized_paths",[])),blocked_entry_ids=list(d.get("blocked_entry_ids",[])),extraction_allowed=bool(d.get("extraction_allowed",False)),file_write_allowed=bool(d.get("file_write_allowed",False)),execution_allowed=bool(d.get("execution_allowed",False)),metadata_only=bool(d.get("metadata_only",True)),created_by=d.get("created_by"),created_at=_safe_dt(d.get("created_at")),updated_at=_safe_dt(d.get("updated_at")),metadata=dict(d.get("metadata",{})))

@dataclass
class ArtifactExtractionAuditEvent:
    event_id: str = field(default_factory=lambda: f"extevt_{uuid4().hex[:16]}")
    request_id: str = ""; tenant_id: str = ""
    event_type: str = ""; severity: str = ArtifactExtractionAuditSeverity.INFO
    actor_id: str | None = None; message: str = ""
    metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"event_id":self.event_id,"request_id":self.request_id,"tenant_id":self.tenant_id,"event_type":self.event_type,"severity":self.severity,"actor_id":self.actor_id,"message":self.message,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(event_id=str(d.get("event_id","")),request_id=str(d.get("request_id","")),tenant_id=str(d.get("tenant_id","")),event_type=str(d.get("event_type","")),severity=str(d.get("severity","info")),actor_id=d.get("actor_id"),message=str(d.get("message","")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

class ArtifactExtractionGuardError(Exception): pass
class ArtifactExtractionRequestNotFoundError(ArtifactExtractionGuardError): pass
class ArtifactExtractionStateError(ArtifactExtractionGuardError): pass
class ArtifactExtractionBlockedError(ArtifactExtractionGuardError): pass

@runtime_checkable
class ArtifactExtractionGuardStore(Protocol):
    def create_request(self, request: ArtifactExtractionGuardRequest) -> ArtifactExtractionGuardRequest: ...
    def get_request(self, request_id: str) -> ArtifactExtractionGuardRequest | None: ...
    def list_requests(self, *, tenant_id: str = "", artifact_id: str = "", status: str = "", decision: str = "",
        guard_status: str = "", plan_status: str = "") -> list[ArtifactExtractionGuardRequest]: ...
    def update_request(self, request: ArtifactExtractionGuardRequest) -> ArtifactExtractionGuardRequest: ...
    def set_request_status(self, request_id: str, status: str, actor_id: str | None = None, reason: str | None = None) -> ArtifactExtractionGuardRequest: ...
    def set_decision(self, request_id: str, decision: str, actor_id: str | None = None, reason: str | None = None) -> ArtifactExtractionGuardRequest: ...
    def create_result(self, result: ArtifactExtractionGuardResult) -> ArtifactExtractionGuardResult: ...
    def get_result(self, result_id: str) -> ArtifactExtractionGuardResult | None: ...
    def get_result_by_request(self, request_id: str) -> ArtifactExtractionGuardResult | None: ...
    def reserve_plan(self, plan: ReadOnlyExtractionPlan) -> ReadOnlyExtractionPlan: ...
    def get_plan(self, plan_id: str) -> ReadOnlyExtractionPlan | None: ...
    def get_plan_by_request(self, request_id: str) -> ReadOnlyExtractionPlan | None: ...
    def cancel_request(self, request_id: str, actor_id: str | None = None, reason: str | None = None) -> ArtifactExtractionGuardRequest: ...
    def expire_request(self, request_id: str, actor_id: str | None = None, reason: str | None = None) -> ArtifactExtractionGuardRequest: ...
    def add_audit_event(self, event: ArtifactExtractionAuditEvent) -> ArtifactExtractionAuditEvent: ...
    def list_audit_events(self, request_id: str) -> list[ArtifactExtractionAuditEvent]: ...
    def count_requests(self, *, tenant_id: str = "", status: str = "", decision: str = "", guard_status: str = "") -> int: ...

def _safe_dt(raw,none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
