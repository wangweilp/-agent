"""Controlled Package Download Worker Domain Model — disabled-by-default, metadata-only.

Step 26-C: NO real download. NO network. NO file write. NO extraction. NO execution.
All is_worker_enabled()/is_download_allowed()/is_network_allowed()/is_execution_allowed() = always False.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


# ═══════════ Enums ═══════════

class PackageDownloadWorkerStatus(StrEnum):
    DRAFT = "draft"
    DISABLED_BY_DEFAULT = "disabled_by_default"
    POLICY_CONFIGURED_METADATA_ONLY = "policy_configured_metadata_only"
    JOB_REQUESTED = "job_requested"
    JOB_BLOCKED = "job_blocked"
    LEASE_RESERVED_METADATA_ONLY = "lease_reserved_metadata_only"
    RELEASED_METADATA_ONLY = "released_metadata_only"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAIL_CLOSED = "fail_closed"


class PackageDownloadWorkerDecision(StrEnum):
    BLOCKED_DISABLED = "blocked_disabled"
    REVIEW_REQUIRED = "review_required"
    METADATA_JOB_RESERVED = "metadata_job_reserved"
    METADATA_LEASE_RESERVED = "metadata_lease_reserved"
    FAIL_CLOSED = "fail_closed"


class PackageDownloadWorkerScope(StrEnum):
    GLOBAL = "global"
    TENANT = "tenant"
    PACKAGE_REQUEST = "package_request"
    QUARANTINE_RECORD = "quarantine_record"
    FUTURE_RUNTIME = "future_runtime"


class PackageDownloadWorkerAuditEventType(StrEnum):
    WORKER_POLICY_CREATED = "worker_policy_created"
    DOWNLOAD_JOB_CREATED = "download_job_created"
    DOWNLOAD_JOB_BLOCKED = "download_job_blocked"
    LEASE_RESERVED_METADATA_ONLY = "lease_reserved_metadata_only"
    GATE_EVALUATED = "gate_evaluated"
    STATUS_CHANGED = "status_changed"
    DECISION_CHANGED = "decision_changed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    NOTE_ADDED = "note_added"


class PackageDownloadWorkerAuditSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


# ═══════════ Dataclasses ═══════════

@dataclass
class PackageDownloadWorkerPolicy:
    policy_id: str = field(default_factory=lambda: f"pkgwkpol_{uuid4().hex[:16]}")
    tenant_id: str | None = None
    scope: str = PackageDownloadWorkerScope.GLOBAL
    enabled_metadata_only: bool = True
    worker_enabled: bool = False
    network_enabled: bool = False
    download_enabled: bool = False
    file_write_enabled: bool = False
    extraction_enabled: bool = False
    package_execution_enabled: bool = False
    requires_admin_approval: bool = True
    requires_kill_switch_clear: bool = True
    requires_incident_clear: bool = True
    blocks_private_network_sources: bool = True
    blocks_metadata_ip: bool = True
    blocks_localhost: bool = True
    created_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_worker_enabled(self) -> bool: return False
    def is_download_allowed(self) -> bool: return False
    def is_network_allowed(self) -> bool: return False

    def to_dict(self):
        return {
            "policy_id": self.policy_id, "tenant_id": self.tenant_id, "scope": self.scope,
            "enabled_metadata_only": self.enabled_metadata_only, "worker_enabled": self.worker_enabled,
            "network_enabled": self.network_enabled, "download_enabled": self.download_enabled,
            "file_write_enabled": self.file_write_enabled, "extraction_enabled": self.extraction_enabled,
            "package_execution_enabled": self.package_execution_enabled,
            "requires_admin_approval": self.requires_admin_approval,
            "requires_kill_switch_clear": self.requires_kill_switch_clear,
            "requires_incident_clear": self.requires_incident_clear,
            "blocks_private_network_sources": self.blocks_private_network_sources,
            "blocks_metadata_ip": self.blocks_metadata_ip, "blocks_localhost": self.blocks_localhost,
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
            worker_enabled=bool(d.get("worker_enabled", False)),
            network_enabled=bool(d.get("network_enabled", False)),
            download_enabled=bool(d.get("download_enabled", False)),
            file_write_enabled=bool(d.get("file_write_enabled", False)),
            extraction_enabled=bool(d.get("extraction_enabled", False)),
            package_execution_enabled=bool(d.get("package_execution_enabled", False)),
            requires_admin_approval=bool(d.get("requires_admin_approval", True)),
            requires_kill_switch_clear=bool(d.get("requires_kill_switch_clear", True)),
            requires_incident_clear=bool(d.get("requires_incident_clear", True)),
            blocks_private_network_sources=bool(d.get("blocks_private_network_sources", True)),
            blocks_metadata_ip=bool(d.get("blocks_metadata_ip", True)),
            blocks_localhost=bool(d.get("blocks_localhost", True)),
            created_by=d.get("created_by"),
            created_at=_safe_dt(d.get("created_at")),
            updated_at=_safe_dt(d.get("updated_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class PackageDownloadWorkerJob:
    job_id: str = field(default_factory=lambda: f"pkgwkjob_{uuid4().hex[:16]}")
    tenant_id: str | None = None
    package_download_request_id: str | None = None
    quarantine_record_id: str | None = None
    worker_policy_id: str | None = None
    kill_switch_policy_id: str | None = None
    incident_id: str | None = None
    source_snapshot: dict[str, Any] = field(default_factory=dict)
    package_request_snapshot: dict[str, Any] = field(default_factory=dict)
    quarantine_snapshot: dict[str, Any] = field(default_factory=dict)
    kill_switch_snapshot: dict[str, Any] = field(default_factory=dict)
    status: str = PackageDownloadWorkerStatus.DISABLED_BY_DEFAULT
    decision: str = PackageDownloadWorkerDecision.BLOCKED_DISABLED
    download_performed: bool = False
    network_used: bool = False
    file_written: bool = False
    package_materialized: bool = False
    package_executed: bool = False
    entrypoint_executed: bool = False
    worker_started: bool = False
    job_dispatched: bool = False
    no_network_used: bool = True
    no_download_performed: bool = True
    no_file_written: bool = True
    no_extraction_performed: bool = True
    no_execution_performed: bool = True
    no_worker_started: bool = True
    no_dispatch_performed: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_download_allowed(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False
    def is_worker_start_allowed(self) -> bool: return False

    def to_dict(self):
        return {
            "job_id": self.job_id, "tenant_id": self.tenant_id,
            "package_download_request_id": self.package_download_request_id,
            "quarantine_record_id": self.quarantine_record_id,
            "worker_policy_id": self.worker_policy_id,
            "kill_switch_policy_id": self.kill_switch_policy_id,
            "incident_id": self.incident_id,
            "source_snapshot": dict(self.source_snapshot),
            "package_request_snapshot": dict(self.package_request_snapshot),
            "quarantine_snapshot": dict(self.quarantine_snapshot),
            "kill_switch_snapshot": dict(self.kill_switch_snapshot),
            "status": self.status, "decision": self.decision,
            "download_performed": self.download_performed,
            "network_used": self.network_used, "file_written": self.file_written,
            "package_materialized": self.package_materialized,
            "package_executed": self.package_executed,
            "entrypoint_executed": self.entrypoint_executed,
            "worker_started": self.worker_started,
            "job_dispatched": self.job_dispatched,
            "no_network_used": self.no_network_used,
            "no_download_performed": self.no_download_performed,
            "no_file_written": self.no_file_written,
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
            job_id=str(d.get("job_id", "")), tenant_id=d.get("tenant_id"),
            package_download_request_id=d.get("package_download_request_id"),
            quarantine_record_id=d.get("quarantine_record_id"),
            worker_policy_id=d.get("worker_policy_id"),
            kill_switch_policy_id=d.get("kill_switch_policy_id"),
            incident_id=d.get("incident_id"),
            source_snapshot=dict(d.get("source_snapshot", {})),
            package_request_snapshot=dict(d.get("package_request_snapshot", {})),
            quarantine_snapshot=dict(d.get("quarantine_snapshot", {})),
            kill_switch_snapshot=dict(d.get("kill_switch_snapshot", {})),
            status=str(d.get("status", "disabled_by_default")),
            decision=str(d.get("decision", "blocked_disabled")),
            download_performed=bool(d.get("download_performed", False)),
            network_used=bool(d.get("network_used", False)),
            file_written=bool(d.get("file_written", False)),
            package_materialized=bool(d.get("package_materialized", False)),
            package_executed=bool(d.get("package_executed", False)),
            entrypoint_executed=bool(d.get("entrypoint_executed", False)),
            worker_started=bool(d.get("worker_started", False)),
            job_dispatched=bool(d.get("job_dispatched", False)),
            no_network_used=bool(d.get("no_network_used", True)),
            no_download_performed=bool(d.get("no_download_performed", True)),
            no_file_written=bool(d.get("no_file_written", True)),
            no_extraction_performed=bool(d.get("no_extraction_performed", True)),
            no_execution_performed=bool(d.get("no_execution_performed", True)),
            no_worker_started=bool(d.get("no_worker_started", True)),
            no_dispatch_performed=bool(d.get("no_dispatch_performed", True)),
            created_at=_safe_dt(d.get("created_at")),
            updated_at=_safe_dt(d.get("updated_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class PackageDownloadWorkerLease:
    lease_id: str = field(default_factory=lambda: f"pkgwklease_{uuid4().hex[:16]}")
    job_id: str = ""
    policy_id: str | None = None
    tenant_id: str | None = None
    status: str = PackageDownloadWorkerStatus.DISABLED_BY_DEFAULT
    decision: str = PackageDownloadWorkerDecision.BLOCKED_DISABLED
    lease_active: bool = False
    worker_started: bool = False
    heartbeat_enabled: bool = False
    download_allowed: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    released_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool: return False
    def is_download_allowed(self) -> bool: return False

    def to_dict(self):
        return {
            "lease_id": self.lease_id, "job_id": self.job_id, "policy_id": self.policy_id,
            "tenant_id": self.tenant_id, "status": self.status, "decision": self.decision,
            "lease_active": self.lease_active, "worker_started": self.worker_started,
            "heartbeat_enabled": self.heartbeat_enabled, "download_allowed": self.download_allowed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "released_at": self.released_at.isoformat() if self.released_at else None,
            "metadata": dict(self.metadata)
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            lease_id=str(d.get("lease_id", "")), job_id=str(d.get("job_id", "")),
            policy_id=d.get("policy_id"), tenant_id=d.get("tenant_id"),
            status=str(d.get("status", "disabled_by_default")),
            decision=str(d.get("decision", "blocked_disabled")),
            lease_active=bool(d.get("lease_active", False)),
            worker_started=bool(d.get("worker_started", False)),
            heartbeat_enabled=bool(d.get("heartbeat_enabled", False)),
            download_allowed=bool(d.get("download_allowed", False)),
            created_at=_safe_dt(d.get("created_at")),
            released_at=_safe_dt(d.get("released_at"), none_ok=True),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class PackageDownloadWorkerGateResult:
    gate_result_id: str = field(default_factory=lambda: f"pkgwkgate_{uuid4().hex[:16]}")
    job_id: str = ""
    tenant_id: str | None = None
    status: str = PackageDownloadWorkerStatus.DISABLED_BY_DEFAULT
    decision: str = PackageDownloadWorkerDecision.BLOCKED_DISABLED
    checks: list[dict[str, Any]] = field(default_factory=list)
    blockers_count: int = 0
    warnings_count: int = 0
    worker_start_allowed: bool = False
    network_allowed: bool = False
    download_allowed: bool = False
    file_write_allowed: bool = False
    execution_allowed: bool = False
    metadata_only: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "gate_result_id": self.gate_result_id, "job_id": self.job_id,
            "tenant_id": self.tenant_id, "status": self.status, "decision": self.decision,
            "checks": [dict(c) for c in self.checks],
            "blockers_count": self.blockers_count, "warnings_count": self.warnings_count,
            "worker_start_allowed": self.worker_start_allowed,
            "network_allowed": self.network_allowed,
            "download_allowed": self.download_allowed,
            "file_write_allowed": self.file_write_allowed,
            "execution_allowed": self.execution_allowed,
            "metadata_only": self.metadata_only,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": dict(self.metadata)
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            gate_result_id=str(d.get("gate_result_id", "")),
            job_id=str(d.get("job_id", "")), tenant_id=d.get("tenant_id"),
            status=str(d.get("status", "disabled_by_default")),
            decision=str(d.get("decision", "blocked_disabled")),
            checks=[dict(c) for c in d.get("checks", [])],
            blockers_count=int(d.get("blockers_count", 0)),
            warnings_count=int(d.get("warnings_count", 0)),
            worker_start_allowed=bool(d.get("worker_start_allowed", False)),
            network_allowed=bool(d.get("network_allowed", False)),
            download_allowed=bool(d.get("download_allowed", False)),
            file_write_allowed=bool(d.get("file_write_allowed", False)),
            execution_allowed=bool(d.get("execution_allowed", False)),
            metadata_only=bool(d.get("metadata_only", True)),
            created_at=_safe_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class PackageDownloadWorkerAuditEvent:
    event_id: str = field(default_factory=lambda: f"pkgwkevt_{uuid4().hex[:16]}")
    tenant_id: str | None = None
    incident_id: str | None = None
    job_id: str | None = None
    policy_id: str | None = None
    request_id: str | None = None
    event_type: str = ""
    severity: str = PackageDownloadWorkerAuditSeverity.INFO
    actor_id: str | None = None
    message: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "event_id": self.event_id, "tenant_id": self.tenant_id,
            "incident_id": self.incident_id, "job_id": self.job_id,
            "policy_id": self.policy_id, "request_id": self.request_id,
            "event_type": self.event_type, "severity": self.severity,
            "actor_id": self.actor_id, "message": self.message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": dict(self.metadata)
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            event_id=str(d.get("event_id", "")), tenant_id=d.get("tenant_id"),
            incident_id=d.get("incident_id"), job_id=d.get("job_id"),
            policy_id=d.get("policy_id"), request_id=d.get("request_id"),
            event_type=str(d.get("event_type", "")),
            severity=str(d.get("severity", "info")),
            actor_id=d.get("actor_id"), message=str(d.get("message", "")),
            created_at=_safe_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}))
        )


# ═══════════ Errors ═══════════

class PackageDownloadWorkerError(Exception): pass
class PackageDownloadWorkerPolicyNotFoundError(PackageDownloadWorkerError): pass
class PackageDownloadWorkerJobNotFoundError(PackageDownloadWorkerError): pass
class PackageDownloadWorkerLeaseNotFoundError(PackageDownloadWorkerError): pass
class PackageDownloadWorkerBlockedError(PackageDownloadWorkerError): pass


# ═══════════ Protocol ═══════════

@runtime_checkable
class PackageDownloadWorkerStore(Protocol):
    def create_policy(self, policy: PackageDownloadWorkerPolicy) -> PackageDownloadWorkerPolicy: ...
    def get_policy(self, policy_id: str) -> PackageDownloadWorkerPolicy | None: ...
    def list_policies(self, *, tenant_id: str = "", scope: str = "") -> list[PackageDownloadWorkerPolicy]: ...
    def update_policy(self, policy: PackageDownloadWorkerPolicy) -> PackageDownloadWorkerPolicy: ...
    def create_job(self, job: PackageDownloadWorkerJob) -> PackageDownloadWorkerJob: ...
    def get_job(self, job_id: str) -> PackageDownloadWorkerJob | None: ...
    def list_jobs(self, *, tenant_id: str = "", status: str = "", policy_id: str = "") -> list[PackageDownloadWorkerJob]: ...
    def update_job(self, job: PackageDownloadWorkerJob) -> PackageDownloadWorkerJob: ...
    def set_job_status(self, job_id: str, status: str, actor_id: str | None = None, reason: str | None = None) -> PackageDownloadWorkerJob: ...
    def set_job_decision(self, job_id: str, decision: str, actor_id: str | None = None, reason: str | None = None) -> PackageDownloadWorkerJob: ...
    def reserve_lease_metadata_only(self, lease: PackageDownloadWorkerLease) -> PackageDownloadWorkerLease: ...
    def get_lease(self, lease_id: str) -> PackageDownloadWorkerLease | None: ...
    def get_lease_by_job(self, job_id: str) -> PackageDownloadWorkerLease | None: ...
    def release_lease_metadata_only(self, lease_id: str, actor_id: str | None = None, reason: str | None = None) -> PackageDownloadWorkerLease: ...
    def create_gate_result(self, gate: PackageDownloadWorkerGateResult) -> PackageDownloadWorkerGateResult: ...
    def get_gate_result(self, gate_result_id: str) -> PackageDownloadWorkerGateResult | None: ...
    def get_gate_result_by_job(self, job_id: str) -> PackageDownloadWorkerGateResult | None: ...
    def add_audit_event(self, event: PackageDownloadWorkerAuditEvent) -> PackageDownloadWorkerAuditEvent: ...
    def list_audit_events(self, *, job_id: str = "", policy_id: str = "") -> list[PackageDownloadWorkerAuditEvent]: ...
    def count_jobs(self, *, tenant_id: str = "", status: str = "") -> int: ...


def _safe_dt(raw, none_ok=False):
    if not raw:
        return None if none_ok else datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None if none_ok else datetime.now(timezone.utc)
