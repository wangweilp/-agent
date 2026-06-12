"""Read-only Artifact Materialization Spike — metadata-only, no file write, no mount, no extraction, no execution.

Step 26-D: NO real materialization. NO file write. NO directory creation. NO mount. NO archive read.
NO extraction. NO execution. is_materialization_allowed()/is_materialized()/is_filesystem_ref_active() = always False.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


# ═══════════ Enums ═══════════

class ArtifactMaterializationStatus(StrEnum):
    DRAFT = "draft"
    DISABLED_BY_DEFAULT = "disabled_by_default"
    REQUESTED_METADATA_ONLY = "requested_metadata_only"
    PLAN_RESERVED_METADATA_ONLY = "plan_reserved_metadata_only"
    READ_ONLY_REFERENCE_RESERVED = "read_only_reference_reserved"
    GATE_EVALUATED = "gate_evaluated"
    BLOCKED_DISABLED = "blocked_disabled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAIL_CLOSED = "fail_closed"


class ArtifactMaterializationDecision(StrEnum):
    BLOCKED_DISABLED = "blocked_disabled"
    REVIEW_REQUIRED = "review_required"
    METADATA_PLAN_RESERVED = "metadata_plan_reserved"
    READ_ONLY_REF_RESERVED = "read_only_ref_reserved"
    FAIL_CLOSED = "fail_closed"


class ArtifactMaterializationScope(StrEnum):
    GLOBAL = "global"
    TENANT = "tenant"
    PACKAGE_REQUEST = "package_request"
    QUARANTINE_RECORD = "quarantine_record"
    DOWNLOAD_WORKER_JOB = "download_worker_job"
    EXTRACTION_PLAN = "extraction_plan"
    FUTURE_RUNTIME = "future_runtime"


class ArtifactMaterializationAuditEventType(StrEnum):
    MATERIALIZATION_POLICY_CREATED = "materialization_policy_created"
    MATERIALIZATION_REQUEST_CREATED = "materialization_request_created"
    MATERIALIZATION_PLAN_RESERVED = "materialization_plan_reserved"
    READ_ONLY_REFERENCE_RESERVED = "read_only_reference_reserved"
    GATE_EVALUATED = "gate_evaluated"
    STATUS_CHANGED = "status_changed"
    DECISION_CHANGED = "decision_changed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    NOTE_ADDED = "note_added"


class ArtifactMaterializationAuditSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


# ═══════════ Dataclasses ═══════════

@dataclass
class ArtifactMaterializationPolicy:
    policy_id: str = field(default_factory=lambda: f"artmatpol_{uuid4().hex[:16]}")
    tenant_id: str | None = None
    scope: str = ArtifactMaterializationScope.GLOBAL
    enabled_metadata_only: bool = True
    materialization_enabled: bool = False
    file_write_enabled: bool = False
    directory_create_enabled: bool = False
    mount_enabled: bool = False
    extraction_enabled: bool = False
    package_execution_enabled: bool = False
    requires_download_worker_gate: bool = True
    requires_extraction_guard_gate: bool = True
    requires_kill_switch_clear: bool = True
    requires_incident_clear: bool = True
    read_only_refs_only: bool = True
    blocks_absolute_paths: bool = True
    blocks_traversal: bool = True
    blocks_symlink_escape: bool = True
    created_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_materialization_allowed(self) -> bool: return False
    def is_file_write_allowed(self) -> bool: return False
    def is_mount_allowed(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False

    def to_dict(self):
        return {
            "policy_id": self.policy_id, "tenant_id": self.tenant_id, "scope": self.scope,
            "enabled_metadata_only": self.enabled_metadata_only,
            "materialization_enabled": self.materialization_enabled,
            "file_write_enabled": self.file_write_enabled,
            "directory_create_enabled": self.directory_create_enabled,
            "mount_enabled": self.mount_enabled,
            "extraction_enabled": self.extraction_enabled,
            "package_execution_enabled": self.package_execution_enabled,
            "requires_download_worker_gate": self.requires_download_worker_gate,
            "requires_extraction_guard_gate": self.requires_extraction_guard_gate,
            "requires_kill_switch_clear": self.requires_kill_switch_clear,
            "requires_incident_clear": self.requires_incident_clear,
            "read_only_refs_only": self.read_only_refs_only,
            "blocks_absolute_paths": self.blocks_absolute_paths,
            "blocks_traversal": self.blocks_traversal,
            "blocks_symlink_escape": self.blocks_symlink_escape,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": dict(self.metadata)
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            policy_id=str(d.get("policy_id", "")), tenant_id=d.get("tenant_id"),
            scope=str(d.get("scope", "global")),
            enabled_metadata_only=bool(d.get("enabled_metadata_only", True)),
            materialization_enabled=bool(d.get("materialization_enabled", False)),
            file_write_enabled=bool(d.get("file_write_enabled", False)),
            directory_create_enabled=bool(d.get("directory_create_enabled", False)),
            mount_enabled=bool(d.get("mount_enabled", False)),
            extraction_enabled=bool(d.get("extraction_enabled", False)),
            package_execution_enabled=bool(d.get("package_execution_enabled", False)),
            requires_download_worker_gate=bool(d.get("requires_download_worker_gate", True)),
            requires_extraction_guard_gate=bool(d.get("requires_extraction_guard_gate", True)),
            requires_kill_switch_clear=bool(d.get("requires_kill_switch_clear", True)),
            requires_incident_clear=bool(d.get("requires_incident_clear", True)),
            read_only_refs_only=bool(d.get("read_only_refs_only", True)),
            blocks_absolute_paths=bool(d.get("blocks_absolute_paths", True)),
            blocks_traversal=bool(d.get("blocks_traversal", True)),
            blocks_symlink_escape=bool(d.get("blocks_symlink_escape", True)),
            created_by=d.get("created_by"),
            created_at=_safe_dt(d.get("created_at")),
            updated_at=_safe_dt(d.get("updated_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class ArtifactMaterializationRequest:
    request_id: str = field(default_factory=lambda: f"artmatreq_{uuid4().hex[:16]}")
    tenant_id: str | None = None
    policy_id: str | None = None
    package_download_request_id: str | None = None
    quarantine_record_id: str | None = None
    download_worker_job_id: str | None = None
    extraction_guard_request_id: str | None = None
    extraction_plan_id: str | None = None
    source_snapshot: dict[str, Any] = field(default_factory=dict)
    quarantine_snapshot: dict[str, Any] = field(default_factory=dict)
    download_worker_snapshot: dict[str, Any] = field(default_factory=dict)
    extraction_guard_snapshot: dict[str, Any] = field(default_factory=dict)
    kill_switch_snapshot: dict[str, Any] = field(default_factory=dict)
    status: str = ArtifactMaterializationStatus.DISABLED_BY_DEFAULT
    decision: str = ArtifactMaterializationDecision.BLOCKED_DISABLED
    materialization_performed: bool = False
    file_written: bool = False
    directory_created: bool = False
    mount_created: bool = False
    archive_read: bool = False
    archive_extracted: bool = False
    package_executed: bool = False
    entrypoint_executed: bool = False
    no_file_written: bool = True
    no_directory_created: bool = True
    no_mount_created: bool = True
    no_archive_read: bool = True
    no_extraction_performed: bool = True
    no_execution_performed: bool = True
    no_worker_started: bool = True
    no_dispatch_performed: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_materialization_allowed(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False

    def to_dict(self):
        return {
            "request_id": self.request_id, "tenant_id": self.tenant_id,
            "policy_id": self.policy_id,
            "package_download_request_id": self.package_download_request_id,
            "quarantine_record_id": self.quarantine_record_id,
            "download_worker_job_id": self.download_worker_job_id,
            "extraction_guard_request_id": self.extraction_guard_request_id,
            "extraction_plan_id": self.extraction_plan_id,
            "source_snapshot": dict(self.source_snapshot),
            "quarantine_snapshot": dict(self.quarantine_snapshot),
            "download_worker_snapshot": dict(self.download_worker_snapshot),
            "extraction_guard_snapshot": dict(self.extraction_guard_snapshot),
            "kill_switch_snapshot": dict(self.kill_switch_snapshot),
            "status": self.status, "decision": self.decision,
            "materialization_performed": self.materialization_performed,
            "file_written": self.file_written,
            "directory_created": self.directory_created,
            "mount_created": self.mount_created,
            "archive_read": self.archive_read,
            "archive_extracted": self.archive_extracted,
            "package_executed": self.package_executed,
            "entrypoint_executed": self.entrypoint_executed,
            "no_file_written": self.no_file_written,
            "no_directory_created": self.no_directory_created,
            "no_mount_created": self.no_mount_created,
            "no_archive_read": self.no_archive_read,
            "no_extraction_performed": self.no_extraction_performed,
            "no_execution_performed": self.no_execution_performed,
            "no_worker_started": self.no_worker_started,
            "no_dispatch_performed": self.no_dispatch_performed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": dict(self.metadata)
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            request_id=str(d.get("request_id", "")), tenant_id=d.get("tenant_id"),
            policy_id=d.get("policy_id"),
            package_download_request_id=d.get("package_download_request_id"),
            quarantine_record_id=d.get("quarantine_record_id"),
            download_worker_job_id=d.get("download_worker_job_id"),
            extraction_guard_request_id=d.get("extraction_guard_request_id"),
            extraction_plan_id=d.get("extraction_plan_id"),
            source_snapshot=dict(d.get("source_snapshot", {})),
            quarantine_snapshot=dict(d.get("quarantine_snapshot", {})),
            download_worker_snapshot=dict(d.get("download_worker_snapshot", {})),
            extraction_guard_snapshot=dict(d.get("extraction_guard_snapshot", {})),
            kill_switch_snapshot=dict(d.get("kill_switch_snapshot", {})),
            status=str(d.get("status", "disabled_by_default")),
            decision=str(d.get("decision", "blocked_disabled")),
            materialization_performed=bool(d.get("materialization_performed", False)),
            file_written=bool(d.get("file_written", False)),
            directory_created=bool(d.get("directory_created", False)),
            mount_created=bool(d.get("mount_created", False)),
            archive_read=bool(d.get("archive_read", False)),
            archive_extracted=bool(d.get("archive_extracted", False)),
            package_executed=bool(d.get("package_executed", False)),
            entrypoint_executed=bool(d.get("entrypoint_executed", False)),
            no_file_written=bool(d.get("no_file_written", True)),
            no_directory_created=bool(d.get("no_directory_created", True)),
            no_mount_created=bool(d.get("no_mount_created", True)),
            no_archive_read=bool(d.get("no_archive_read", True)),
            no_extraction_performed=bool(d.get("no_extraction_performed", True)),
            no_execution_performed=bool(d.get("no_execution_performed", True)),
            no_worker_started=bool(d.get("no_worker_started", True)),
            no_dispatch_performed=bool(d.get("no_dispatch_performed", True)),
            created_at=_safe_dt(d.get("created_at")),
            updated_at=_safe_dt(d.get("updated_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class ReadOnlyArtifactMaterializationPlan:
    plan_id: str = field(default_factory=lambda: f"artmatplan_{uuid4().hex[:16]}")
    request_id: str = ""
    tenant_id: str | None = None
    policy_id: str | None = None
    logical_artifact_ref: str | None = None
    allowed_logical_paths: list[str] = field(default_factory=list)
    blocked_logical_paths: list[str] = field(default_factory=list)
    source_hashes: list[str] = field(default_factory=list)
    metadata_manifest: dict[str, Any] = field(default_factory=dict)
    plan_status: str = ArtifactMaterializationStatus.PLAN_RESERVED_METADATA_ONLY
    decision: str = ArtifactMaterializationDecision.METADATA_PLAN_RESERVED
    materialization_allowed: bool = False
    file_write_allowed: bool = False
    directory_create_allowed: bool = False
    mount_allowed: bool = False
    extraction_allowed: bool = False
    execution_allowed: bool = False
    metadata_only: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_materialized(self) -> bool: return False
    def is_mount_active(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False

    def to_dict(self):
        return {
            "plan_id": self.plan_id, "request_id": self.request_id,
            "tenant_id": self.tenant_id, "policy_id": self.policy_id,
            "logical_artifact_ref": self.logical_artifact_ref,
            "allowed_logical_paths": list(self.allowed_logical_paths),
            "blocked_logical_paths": list(self.blocked_logical_paths),
            "source_hashes": list(self.source_hashes),
            "metadata_manifest": dict(self.metadata_manifest),
            "plan_status": self.plan_status, "decision": self.decision,
            "materialization_allowed": self.materialization_allowed,
            "file_write_allowed": self.file_write_allowed,
            "directory_create_allowed": self.directory_create_allowed,
            "mount_allowed": self.mount_allowed,
            "extraction_allowed": self.extraction_allowed,
            "execution_allowed": self.execution_allowed,
            "metadata_only": self.metadata_only,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": dict(self.metadata)
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            plan_id=str(d.get("plan_id", "")),
            request_id=str(d.get("request_id", "")),
            tenant_id=d.get("tenant_id"), policy_id=d.get("policy_id"),
            logical_artifact_ref=d.get("logical_artifact_ref"),
            allowed_logical_paths=list(d.get("allowed_logical_paths", [])),
            blocked_logical_paths=list(d.get("blocked_logical_paths", [])),
            source_hashes=list(d.get("source_hashes", [])),
            metadata_manifest=dict(d.get("metadata_manifest", {})),
            plan_status=str(d.get("plan_status", "plan_reserved_metadata_only")),
            decision=str(d.get("decision", "metadata_plan_reserved")),
            materialization_allowed=bool(d.get("materialization_allowed", False)),
            file_write_allowed=bool(d.get("file_write_allowed", False)),
            directory_create_allowed=bool(d.get("directory_create_allowed", False)),
            mount_allowed=bool(d.get("mount_allowed", False)),
            extraction_allowed=bool(d.get("extraction_allowed", False)),
            execution_allowed=bool(d.get("execution_allowed", False)),
            metadata_only=bool(d.get("metadata_only", True)),
            created_at=_safe_dt(d.get("created_at")),
            updated_at=_safe_dt(d.get("updated_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class ReadOnlyArtifactReference:
    ref_id: str = field(default_factory=lambda: f"artmatref_{uuid4().hex[:16]}")
    plan_id: str = ""
    tenant_id: str | None = None
    logical_ref: str | None = None
    ref_type: str = "logical_only"
    ref_status: str = ArtifactMaterializationStatus.READ_ONLY_REFERENCE_RESERVED
    content_hash: str | None = None
    manifest_hash: str | None = None
    filesystem_path: str | None = None
    filesystem_ref_active: bool = False
    file_exists_checked: bool = False
    file_opened: bool = False
    file_written: bool = False
    mount_active: bool = False
    execution_allowed: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_filesystem_ref_active(self) -> bool: return False
    def is_file_opened(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False

    def to_dict(self):
        return {
            "ref_id": self.ref_id, "plan_id": self.plan_id, "tenant_id": self.tenant_id,
            "logical_ref": self.logical_ref, "ref_type": self.ref_type,
            "ref_status": self.ref_status,
            "content_hash": self.content_hash, "manifest_hash": self.manifest_hash,
            "filesystem_path": self.filesystem_path,
            "filesystem_ref_active": self.filesystem_ref_active,
            "file_exists_checked": self.file_exists_checked,
            "file_opened": self.file_opened, "file_written": self.file_written,
            "mount_active": self.mount_active,
            "execution_allowed": self.execution_allowed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": dict(self.metadata)
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            ref_id=str(d.get("ref_id", "")), plan_id=str(d.get("plan_id", "")),
            tenant_id=d.get("tenant_id"), logical_ref=d.get("logical_ref"),
            ref_type=str(d.get("ref_type", "logical_only")),
            ref_status=str(d.get("ref_status", "read_only_reference_reserved")),
            content_hash=d.get("content_hash"), manifest_hash=d.get("manifest_hash"),
            filesystem_path=d.get("filesystem_path"),
            filesystem_ref_active=bool(d.get("filesystem_ref_active", False)),
            file_exists_checked=bool(d.get("file_exists_checked", False)),
            file_opened=bool(d.get("file_opened", False)),
            file_written=bool(d.get("file_written", False)),
            mount_active=bool(d.get("mount_active", False)),
            execution_allowed=bool(d.get("execution_allowed", False)),
            created_at=_safe_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class ArtifactMaterializationGateResult:
    gate_result_id: str = field(default_factory=lambda: f"artmatgate_{uuid4().hex[:16]}")
    request_id: str = ""
    tenant_id: str | None = None
    status: str = ArtifactMaterializationStatus.DISABLED_BY_DEFAULT
    decision: str = ArtifactMaterializationDecision.BLOCKED_DISABLED
    checks: list[dict[str, Any]] = field(default_factory=list)
    blockers_count: int = 0
    warnings_count: int = 0
    materialization_allowed: bool = False
    file_write_allowed: bool = False
    directory_create_allowed: bool = False
    mount_allowed: bool = False
    archive_read_allowed: bool = False
    extraction_allowed: bool = False
    execution_allowed: bool = False
    metadata_only: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "gate_result_id": self.gate_result_id, "request_id": self.request_id,
            "tenant_id": self.tenant_id, "status": self.status, "decision": self.decision,
            "checks": [dict(c) for c in self.checks],
            "blockers_count": self.blockers_count, "warnings_count": self.warnings_count,
            "materialization_allowed": self.materialization_allowed,
            "file_write_allowed": self.file_write_allowed,
            "directory_create_allowed": self.directory_create_allowed,
            "mount_allowed": self.mount_allowed,
            "archive_read_allowed": self.archive_read_allowed,
            "extraction_allowed": self.extraction_allowed,
            "execution_allowed": self.execution_allowed,
            "metadata_only": self.metadata_only,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": dict(self.metadata)
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            gate_result_id=str(d.get("gate_result_id", "")),
            request_id=str(d.get("request_id", "")), tenant_id=d.get("tenant_id"),
            status=str(d.get("status", "disabled_by_default")),
            decision=str(d.get("decision", "blocked_disabled")),
            checks=[dict(c) for c in d.get("checks", [])],
            blockers_count=int(d.get("blockers_count", 0)),
            warnings_count=int(d.get("warnings_count", 0)),
            materialization_allowed=bool(d.get("materialization_allowed", False)),
            file_write_allowed=bool(d.get("file_write_allowed", False)),
            directory_create_allowed=bool(d.get("directory_create_allowed", False)),
            mount_allowed=bool(d.get("mount_allowed", False)),
            archive_read_allowed=bool(d.get("archive_read_allowed", False)),
            extraction_allowed=bool(d.get("extraction_allowed", False)),
            execution_allowed=bool(d.get("execution_allowed", False)),
            metadata_only=bool(d.get("metadata_only", True)),
            created_at=_safe_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class ArtifactMaterializationAuditEvent:
    event_id: str = field(default_factory=lambda: f"artmatevt_{uuid4().hex[:16]}")
    tenant_id: str | None = None
    request_id: str | None = None
    plan_id: str | None = None
    ref_id: str | None = None
    policy_id: str | None = None
    event_type: str = ""
    severity: str = ArtifactMaterializationAuditSeverity.INFO
    actor_id: str | None = None
    message: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "event_id": self.event_id, "tenant_id": self.tenant_id,
            "request_id": self.request_id, "plan_id": self.plan_id,
            "ref_id": self.ref_id, "policy_id": self.policy_id,
            "event_type": self.event_type, "severity": self.severity,
            "actor_id": self.actor_id, "message": self.message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": dict(self.metadata)
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            event_id=str(d.get("event_id", "")), tenant_id=d.get("tenant_id"),
            request_id=d.get("request_id"), plan_id=d.get("plan_id"),
            ref_id=d.get("ref_id"), policy_id=d.get("policy_id"),
            event_type=str(d.get("event_type", "")),
            severity=str(d.get("severity", "info")),
            actor_id=d.get("actor_id"), message=str(d.get("message", "")),
            created_at=_safe_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}))
        )


# ═══════════ Errors ═══════════

class ArtifactMaterializationError(Exception): pass
class ArtifactMaterializationPolicyNotFoundError(ArtifactMaterializationError): pass
class ArtifactMaterializationRequestNotFoundError(ArtifactMaterializationError): pass
class ArtifactMaterializationPlanNotFoundError(ArtifactMaterializationError): pass
class ArtifactMaterializationReferenceNotFoundError(ArtifactMaterializationError): pass
class ArtifactMaterializationBlockedError(ArtifactMaterializationError): pass


# ═══════════ Protocol ═══════════

@runtime_checkable
class ArtifactMaterializationStore(Protocol):
    def create_policy(self, policy: ArtifactMaterializationPolicy) -> ArtifactMaterializationPolicy: ...
    def get_policy(self, policy_id: str) -> ArtifactMaterializationPolicy | None: ...
    def list_policies(self, *, tenant_id: str = "", scope: str = "") -> list[ArtifactMaterializationPolicy]: ...
    def update_policy(self, policy: ArtifactMaterializationPolicy) -> ArtifactMaterializationPolicy: ...
    def create_request(self, request: ArtifactMaterializationRequest) -> ArtifactMaterializationRequest: ...
    def get_request(self, request_id: str) -> ArtifactMaterializationRequest | None: ...
    def list_requests(self, *, tenant_id: str = "", status: str = "", policy_id: str = "") -> list[ArtifactMaterializationRequest]: ...
    def update_request(self, request: ArtifactMaterializationRequest) -> ArtifactMaterializationRequest: ...
    def set_request_status(self, request_id: str, status: str, actor_id: str | None = None, reason: str | None = None) -> ArtifactMaterializationRequest: ...
    def set_request_decision(self, request_id: str, decision: str, actor_id: str | None = None, reason: str | None = None) -> ArtifactMaterializationRequest: ...
    def reserve_plan_metadata_only(self, plan: ReadOnlyArtifactMaterializationPlan) -> ReadOnlyArtifactMaterializationPlan: ...
    def get_plan(self, plan_id: str) -> ReadOnlyArtifactMaterializationPlan | None: ...
    def get_plan_by_request(self, request_id: str) -> ReadOnlyArtifactMaterializationPlan | None: ...
    def reserve_read_only_reference(self, ref: ReadOnlyArtifactReference) -> ReadOnlyArtifactReference: ...
    def get_reference(self, ref_id: str) -> ReadOnlyArtifactReference | None: ...
    def list_references(self, *, plan_id: str = "") -> list[ReadOnlyArtifactReference]: ...
    def create_gate_result(self, gate: ArtifactMaterializationGateResult) -> ArtifactMaterializationGateResult: ...
    def get_gate_result(self, gate_result_id: str) -> ArtifactMaterializationGateResult | None: ...
    def get_gate_result_by_request(self, request_id: str) -> ArtifactMaterializationGateResult | None: ...
    def add_audit_event(self, event: ArtifactMaterializationAuditEvent) -> ArtifactMaterializationAuditEvent: ...
    def list_audit_events(self, *, request_id: str = "", policy_id: str = "") -> list[ArtifactMaterializationAuditEvent]: ...
    def count_requests(self, *, tenant_id: str = "", status: str = "") -> int: ...


def _safe_dt(raw, none_ok=False):
    if not raw:
        return None if none_ok else datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None if none_ok else datetime.now(timezone.utc)
