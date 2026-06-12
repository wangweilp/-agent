"""Rootless Container Prototype Gate — metadata/control-plane readiness assessment only.

Step 26-E: NO container start. NO Docker/Podman/containerd/runc/crun. NO namespace/cgroup creation.
NO mount. NO execution. is_container_start_allowed()/is_runtime_enabled()/is_execution_allowed() = always False.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


# ═══════════ Enums ═══════════

class RootlessContainerGateStatus(StrEnum):
    DRAFT = "draft"
    DISABLED_BY_DEFAULT = "disabled_by_default"
    REQUESTED_METADATA_ONLY = "requested_metadata_only"
    CAPABILITY_ASSESSED = "capability_assessed"
    PLAN_RESERVED_METADATA_ONLY = "plan_reserved_metadata_only"
    GATE_EVALUATED = "gate_evaluated"
    BLOCKED_DISABLED = "blocked_disabled"
    REVIEW_REQUIRED = "review_required"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAIL_CLOSED = "fail_closed"


class RootlessContainerGateDecision(StrEnum):
    BLOCKED_DISABLED = "blocked_disabled"
    REVIEW_REQUIRED = "review_required"
    METADATA_PLAN_RESERVED = "metadata_plan_reserved"
    READY_FOR_FUTURE_ISOLATED_FIXTURE_GATE_ONLY = "ready_for_future_isolated_fixture_gate_only"
    FAIL_CLOSED = "fail_closed"


class RootlessContainerCapabilityStatus(StrEnum):
    SATISFIED = "satisfied"
    MISSING = "missing"
    PARTIALLY_SATISFIED = "partially_satisfied"
    BLOCKED = "blocked"
    NOT_CHECKED_RUNTIME_DISABLED = "not_checked_runtime_disabled"
    FAIL_CLOSED = "fail_closed"


class RootlessContainerCapabilityType(StrEnum):
    ROOTLESS_USER_NAMESPACE_REQUIRED = "rootless_user_namespace_required"
    NO_ROOT_REQUIRED = "no_root_required"
    SECCOMP_PROFILE_REQUIRED = "seccomp_profile_required"
    APPARMOR_OR_SELINUX_REQUIRED = "apparmor_or_selinux_required"
    NETWORK_DISABLED_BY_DEFAULT_REQUIRED = "network_disabled_by_default_required"
    FILESYSTEM_READ_ONLY_REQUIRED = "filesystem_read_only_required"
    NO_HOST_MOUNT_REQUIRED = "no_host_mount_required"
    NO_DOCKER_SOCKET_REQUIRED = "no_docker_socket_required"
    NO_PRIVILEGED_MODE_REQUIRED = "no_privileged_mode_required"
    CPU_LIMIT_REQUIRED = "cpu_limit_required"
    MEMORY_LIMIT_REQUIRED = "memory_limit_required"
    PID_LIMIT_REQUIRED = "pid_limit_required"
    TIMEOUT_REQUIRED = "timeout_required"
    LOG_CAPTURE_POLICY_REQUIRED = "log_capture_policy_required"
    SECRET_INJECTION_DISABLED_REQUIRED = "secret_injection_disabled_required"
    PACKAGE_EXECUTION_DISABLED_REQUIRED = "package_execution_disabled_required"
    ENTRYPOINT_EXECUTION_DISABLED_REQUIRED = "entrypoint_execution_disabled_required"
    KILL_SWITCH_REQUIRED = "kill_switch_required"
    INCIDENT_STORE_REQUIRED = "incident_store_required"
    AUDIT_TRAIL_REQUIRED = "audit_trail_required"
    RED_TEAM_REQUIRED = "red_team_required"
    ROLLBACK_REQUIRED = "rollback_required"


class RootlessContainerAuditEventType(StrEnum):
    POLICY_CREATED = "policy_created"
    REQUEST_CREATED = "request_created"
    CAPABILITY_ASSESSED = "capability_assessed"
    PLAN_RESERVED_METADATA_ONLY = "plan_reserved_metadata_only"
    GATE_EVALUATED = "gate_evaluated"
    STATUS_CHANGED = "status_changed"
    DECISION_CHANGED = "decision_changed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    NOTE_ADDED = "note_added"


class RootlessContainerAuditSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


# ═══════════ Dataclasses ═══════════

@dataclass
class RootlessContainerPrototypePolicy:
    policy_id: str = field(default_factory=lambda: f"rtclspl_{uuid4().hex[:16]}")
    tenant_id: str | None = None
    enabled_metadata_only: bool = True
    rootless_container_enabled: bool = False
    container_start_enabled: bool = False
    docker_enabled: bool = False
    podman_enabled: bool = False
    namespace_creation_enabled: bool = False
    cgroup_enabled: bool = False
    mount_enabled: bool = False
    network_enabled: bool = False
    package_execution_enabled: bool = False
    third_party_execution_enabled: bool = False
    requires_kill_switch_clear: bool = True
    requires_incident_clear: bool = True
    requires_read_only_artifact_plan: bool = True
    requires_download_worker_blocked: bool = True
    requires_red_team_passed: bool = True
    created_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_container_start_allowed(self) -> bool: return False
    def is_runtime_enabled(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False

    def to_dict(self):
        return {
            "policy_id": self.policy_id, "tenant_id": self.tenant_id,
            "enabled_metadata_only": self.enabled_metadata_only,
            "rootless_container_enabled": self.rootless_container_enabled,
            "container_start_enabled": self.container_start_enabled,
            "docker_enabled": self.docker_enabled, "podman_enabled": self.podman_enabled,
            "namespace_creation_enabled": self.namespace_creation_enabled,
            "cgroup_enabled": self.cgroup_enabled,
            "mount_enabled": self.mount_enabled, "network_enabled": self.network_enabled,
            "package_execution_enabled": self.package_execution_enabled,
            "third_party_execution_enabled": self.third_party_execution_enabled,
            "requires_kill_switch_clear": self.requires_kill_switch_clear,
            "requires_incident_clear": self.requires_incident_clear,
            "requires_read_only_artifact_plan": self.requires_read_only_artifact_plan,
            "requires_download_worker_blocked": self.requires_download_worker_blocked,
            "requires_red_team_passed": self.requires_red_team_passed,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": dict(self.metadata)
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            policy_id=str(d.get("policy_id", "")), tenant_id=d.get("tenant_id"),
            enabled_metadata_only=bool(d.get("enabled_metadata_only", True)),
            rootless_container_enabled=bool(d.get("rootless_container_enabled", False)),
            container_start_enabled=bool(d.get("container_start_enabled", False)),
            docker_enabled=bool(d.get("docker_enabled", False)),
            podman_enabled=bool(d.get("podman_enabled", False)),
            namespace_creation_enabled=bool(d.get("namespace_creation_enabled", False)),
            cgroup_enabled=bool(d.get("cgroup_enabled", False)),
            mount_enabled=bool(d.get("mount_enabled", False)),
            network_enabled=bool(d.get("network_enabled", False)),
            package_execution_enabled=bool(d.get("package_execution_enabled", False)),
            third_party_execution_enabled=bool(d.get("third_party_execution_enabled", False)),
            requires_kill_switch_clear=bool(d.get("requires_kill_switch_clear", True)),
            requires_incident_clear=bool(d.get("requires_incident_clear", True)),
            requires_read_only_artifact_plan=bool(d.get("requires_read_only_artifact_plan", True)),
            requires_download_worker_blocked=bool(d.get("requires_download_worker_blocked", True)),
            requires_red_team_passed=bool(d.get("requires_red_team_passed", True)),
            created_by=d.get("created_by"),
            created_at=_safe_dt(d.get("created_at")),
            updated_at=_safe_dt(d.get("updated_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class RootlessContainerCapabilityAssessment:
    assessment_id: str = field(default_factory=lambda: f"rtclscap_{uuid4().hex[:16]}")
    tenant_id: str | None = None
    capability_type: str = ""
    status: str = RootlessContainerCapabilityStatus.NOT_CHECKED_RUNTIME_DISABLED
    risk_level: str = "unknown"
    name: str = ""
    description: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    required_before_container_start: bool = True
    required_before_execution: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "assessment_id": self.assessment_id, "tenant_id": self.tenant_id,
            "capability_type": self.capability_type, "status": self.status,
            "risk_level": self.risk_level, "name": self.name, "description": self.description,
            "evidence_refs": list(self.evidence_refs),
            "blockers": list(self.blockers), "warnings": list(self.warnings),
            "required_before_container_start": self.required_before_container_start,
            "required_before_execution": self.required_before_execution,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": dict(self.metadata)
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            assessment_id=str(d.get("assessment_id", "")), tenant_id=d.get("tenant_id"),
            capability_type=str(d.get("capability_type", "")),
            status=str(d.get("status", "not_checked_runtime_disabled")),
            risk_level=str(d.get("risk_level", "unknown")),
            name=str(d.get("name", "")), description=str(d.get("description", "")),
            evidence_refs=list(d.get("evidence_refs", [])),
            blockers=list(d.get("blockers", [])), warnings=list(d.get("warnings", [])),
            required_before_container_start=bool(d.get("required_before_container_start", True)),
            required_before_execution=bool(d.get("required_before_execution", True)),
            created_at=_safe_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class RootlessContainerPrototypeRequest:
    request_id: str = field(default_factory=lambda: f"rtclsreq_{uuid4().hex[:16]}")
    tenant_id: str | None = None
    policy_id: str | None = None
    production_gate_request_id: str | None = None
    kill_switch_policy_id: str | None = None
    incident_id: str | None = None
    artifact_plan_id: str | None = None
    download_worker_job_id: str | None = None
    policy_snapshot: dict[str, Any] = field(default_factory=dict)
    production_gate_snapshot: dict[str, Any] = field(default_factory=dict)
    kill_switch_snapshot: dict[str, Any] = field(default_factory=dict)
    artifact_plan_snapshot: dict[str, Any] = field(default_factory=dict)
    download_worker_snapshot: dict[str, Any] = field(default_factory=dict)
    status: str = RootlessContainerGateStatus.DISABLED_BY_DEFAULT
    decision: str = RootlessContainerGateDecision.BLOCKED_DISABLED
    container_started: bool = False
    runtime_started: bool = False
    namespace_created: bool = False
    cgroup_created: bool = False
    mount_created: bool = False
    network_enabled: bool = False
    package_executed: bool = False
    third_party_code_executed: bool = False
    no_container_started: bool = True
    no_runtime_started: bool = True
    no_namespace_created: bool = True
    no_cgroup_created: bool = True
    no_mount_created: bool = True
    no_network_enabled: bool = True
    no_execution_performed: bool = True
    no_package_executed: bool = True
    no_third_party_code_executed: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_container_start_allowed(self) -> bool: return False
    def is_runtime_enabled(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False

    def to_dict(self):
        return {
            "request_id": self.request_id, "tenant_id": self.tenant_id,
            "policy_id": self.policy_id,
            "production_gate_request_id": self.production_gate_request_id,
            "kill_switch_policy_id": self.kill_switch_policy_id,
            "incident_id": self.incident_id,
            "artifact_plan_id": self.artifact_plan_id,
            "download_worker_job_id": self.download_worker_job_id,
            "policy_snapshot": dict(self.policy_snapshot),
            "production_gate_snapshot": dict(self.production_gate_snapshot),
            "kill_switch_snapshot": dict(self.kill_switch_snapshot),
            "artifact_plan_snapshot": dict(self.artifact_plan_snapshot),
            "download_worker_snapshot": dict(self.download_worker_snapshot),
            "status": self.status, "decision": self.decision,
            "container_started": self.container_started,
            "runtime_started": self.runtime_started,
            "namespace_created": self.namespace_created,
            "cgroup_created": self.cgroup_created,
            "mount_created": self.mount_created,
            "network_enabled": self.network_enabled,
            "package_executed": self.package_executed,
            "third_party_code_executed": self.third_party_code_executed,
            "no_container_started": self.no_container_started,
            "no_runtime_started": self.no_runtime_started,
            "no_namespace_created": self.no_namespace_created,
            "no_cgroup_created": self.no_cgroup_created,
            "no_mount_created": self.no_mount_created,
            "no_network_enabled": self.no_network_enabled,
            "no_execution_performed": self.no_execution_performed,
            "no_package_executed": self.no_package_executed,
            "no_third_party_code_executed": self.no_third_party_code_executed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": dict(self.metadata)
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            request_id=str(d.get("request_id", "")), tenant_id=d.get("tenant_id"),
            policy_id=d.get("policy_id"),
            production_gate_request_id=d.get("production_gate_request_id"),
            kill_switch_policy_id=d.get("kill_switch_policy_id"),
            incident_id=d.get("incident_id"),
            artifact_plan_id=d.get("artifact_plan_id"),
            download_worker_job_id=d.get("download_worker_job_id"),
            policy_snapshot=dict(d.get("policy_snapshot", {})),
            production_gate_snapshot=dict(d.get("production_gate_snapshot", {})),
            kill_switch_snapshot=dict(d.get("kill_switch_snapshot", {})),
            artifact_plan_snapshot=dict(d.get("artifact_plan_snapshot", {})),
            download_worker_snapshot=dict(d.get("download_worker_snapshot", {})),
            status=str(d.get("status", "disabled_by_default")),
            decision=str(d.get("decision", "blocked_disabled")),
            container_started=bool(d.get("container_started", False)),
            runtime_started=bool(d.get("runtime_started", False)),
            namespace_created=bool(d.get("namespace_created", False)),
            cgroup_created=bool(d.get("cgroup_created", False)),
            mount_created=bool(d.get("mount_created", False)),
            network_enabled=bool(d.get("network_enabled", False)),
            package_executed=bool(d.get("package_executed", False)),
            third_party_code_executed=bool(d.get("third_party_code_executed", False)),
            no_container_started=bool(d.get("no_container_started", True)),
            no_runtime_started=bool(d.get("no_runtime_started", True)),
            no_namespace_created=bool(d.get("no_namespace_created", True)),
            no_cgroup_created=bool(d.get("no_cgroup_created", True)),
            no_mount_created=bool(d.get("no_mount_created", True)),
            no_network_enabled=bool(d.get("no_network_enabled", True)),
            no_execution_performed=bool(d.get("no_execution_performed", True)),
            no_package_executed=bool(d.get("no_package_executed", True)),
            no_third_party_code_executed=bool(d.get("no_third_party_code_executed", True)),
            created_at=_safe_dt(d.get("created_at")),
            updated_at=_safe_dt(d.get("updated_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class RootlessContainerPrototypePlan:
    plan_id: str = field(default_factory=lambda: f"rtclsplan_{uuid4().hex[:16]}")
    request_id: str = ""
    tenant_id: str | None = None
    policy_id: str | None = None
    capability_assessments: list[dict[str, Any]] = field(default_factory=list)
    required_controls: list[str] = field(default_factory=list)
    missing_controls: list[str] = field(default_factory=list)
    blocker_summary: str = ""
    plan_status: str = RootlessContainerGateStatus.PLAN_RESERVED_METADATA_ONLY
    decision: str = RootlessContainerGateDecision.METADATA_PLAN_RESERVED
    container_start_allowed: bool = False
    runtime_enabled: bool = False
    network_allowed: bool = False
    mount_allowed: bool = False
    package_execution_allowed: bool = False
    third_party_execution_allowed: bool = False
    metadata_only: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_container_start_allowed(self) -> bool: return False
    def is_runtime_enabled(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False

    def to_dict(self):
        return {
            "plan_id": self.plan_id, "request_id": self.request_id,
            "tenant_id": self.tenant_id, "policy_id": self.policy_id,
            "capability_assessments": [dict(a) for a in self.capability_assessments],
            "required_controls": list(self.required_controls),
            "missing_controls": list(self.missing_controls),
            "blocker_summary": self.blocker_summary,
            "plan_status": self.plan_status, "decision": self.decision,
            "container_start_allowed": self.container_start_allowed,
            "runtime_enabled": self.runtime_enabled,
            "network_allowed": self.network_allowed,
            "mount_allowed": self.mount_allowed,
            "package_execution_allowed": self.package_execution_allowed,
            "third_party_execution_allowed": self.third_party_execution_allowed,
            "metadata_only": self.metadata_only,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": dict(self.metadata)
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            plan_id=str(d.get("plan_id", "")), request_id=str(d.get("request_id", "")),
            tenant_id=d.get("tenant_id"), policy_id=d.get("policy_id"),
            capability_assessments=[dict(a) for a in d.get("capability_assessments", [])],
            required_controls=list(d.get("required_controls", [])),
            missing_controls=list(d.get("missing_controls", [])),
            blocker_summary=str(d.get("blocker_summary", "")),
            plan_status=str(d.get("plan_status", "plan_reserved_metadata_only")),
            decision=str(d.get("decision", "metadata_plan_reserved")),
            container_start_allowed=bool(d.get("container_start_allowed", False)),
            runtime_enabled=bool(d.get("runtime_enabled", False)),
            network_allowed=bool(d.get("network_allowed", False)),
            mount_allowed=bool(d.get("mount_allowed", False)),
            package_execution_allowed=bool(d.get("package_execution_allowed", False)),
            third_party_execution_allowed=bool(d.get("third_party_execution_allowed", False)),
            metadata_only=bool(d.get("metadata_only", True)),
            created_at=_safe_dt(d.get("created_at")),
            updated_at=_safe_dt(d.get("updated_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class RootlessContainerGateResult:
    gate_result_id: str = field(default_factory=lambda: f"rtclsgate_{uuid4().hex[:16]}")
    request_id: str = ""
    tenant_id: str | None = None
    status: str = RootlessContainerGateStatus.DISABLED_BY_DEFAULT
    decision: str = RootlessContainerGateDecision.BLOCKED_DISABLED
    checks: list[dict[str, Any]] = field(default_factory=list)
    satisfied_count: int = 0
    missing_count: int = 0
    blockers_count: int = 0
    warnings_count: int = 0
    ready_for_step26f: bool = False
    container_start_allowed: bool = False
    runtime_enabled: bool = False
    network_allowed: bool = False
    mount_allowed: bool = False
    execution_allowed: bool = False
    third_party_execution_allowed: bool = False
    package_execution_allowed: bool = False
    metadata_only: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "gate_result_id": self.gate_result_id, "request_id": self.request_id,
            "tenant_id": self.tenant_id, "status": self.status, "decision": self.decision,
            "checks": [dict(c) for c in self.checks],
            "satisfied_count": self.satisfied_count,
            "missing_count": self.missing_count,
            "blockers_count": self.blockers_count, "warnings_count": self.warnings_count,
            "ready_for_step26f": self.ready_for_step26f,
            "container_start_allowed": self.container_start_allowed,
            "runtime_enabled": self.runtime_enabled,
            "network_allowed": self.network_allowed,
            "mount_allowed": self.mount_allowed,
            "execution_allowed": self.execution_allowed,
            "third_party_execution_allowed": self.third_party_execution_allowed,
            "package_execution_allowed": self.package_execution_allowed,
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
            satisfied_count=int(d.get("satisfied_count", 0)),
            missing_count=int(d.get("missing_count", 0)),
            blockers_count=int(d.get("blockers_count", 0)),
            warnings_count=int(d.get("warnings_count", 0)),
            ready_for_step26f=bool(d.get("ready_for_step26f", False)),
            container_start_allowed=bool(d.get("container_start_allowed", False)),
            runtime_enabled=bool(d.get("runtime_enabled", False)),
            network_allowed=bool(d.get("network_allowed", False)),
            mount_allowed=bool(d.get("mount_allowed", False)),
            execution_allowed=bool(d.get("execution_allowed", False)),
            third_party_execution_allowed=bool(d.get("third_party_execution_allowed", False)),
            package_execution_allowed=bool(d.get("package_execution_allowed", False)),
            metadata_only=bool(d.get("metadata_only", True)),
            created_at=_safe_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class RootlessContainerAuditEvent:
    event_id: str = field(default_factory=lambda: f"rtclsevt_{uuid4().hex[:16]}")
    tenant_id: str | None = None
    request_id: str | None = None
    plan_id: str | None = None
    policy_id: str | None = None
    assessment_id: str | None = None
    event_type: str = ""
    severity: str = RootlessContainerAuditSeverity.INFO
    actor_id: str | None = None
    message: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "event_id": self.event_id, "tenant_id": self.tenant_id,
            "request_id": self.request_id, "plan_id": self.plan_id,
            "policy_id": self.policy_id, "assessment_id": self.assessment_id,
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
            policy_id=d.get("policy_id"), assessment_id=d.get("assessment_id"),
            event_type=str(d.get("event_type", "")),
            severity=str(d.get("severity", "info")),
            actor_id=d.get("actor_id"), message=str(d.get("message", "")),
            created_at=_safe_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}))
        )


# ═══════════ Errors ═══════════

class RootlessContainerGateError(Exception): pass
class RootlessContainerPolicyNotFoundError(RootlessContainerGateError): pass
class RootlessContainerRequestNotFoundError(RootlessContainerGateError): pass
class RootlessContainerPlanNotFoundError(RootlessContainerGateError): pass
class RootlessContainerBlockedError(RootlessContainerGateError): pass


# ═══════════ Protocol ═══════════

@runtime_checkable
class RootlessContainerGateStore(Protocol):
    def create_policy(self, policy: RootlessContainerPrototypePolicy) -> RootlessContainerPrototypePolicy: ...
    def get_policy(self, policy_id: str) -> RootlessContainerPrototypePolicy | None: ...
    def list_policies(self, *, tenant_id: str = "") -> list[RootlessContainerPrototypePolicy]: ...
    def update_policy(self, policy: RootlessContainerPrototypePolicy) -> RootlessContainerPrototypePolicy: ...
    def create_request(self, request: RootlessContainerPrototypeRequest) -> RootlessContainerPrototypeRequest: ...
    def get_request(self, request_id: str) -> RootlessContainerPrototypeRequest | None: ...
    def list_requests(self, *, tenant_id: str = "", status: str = "", policy_id: str = "") -> list[RootlessContainerPrototypeRequest]: ...
    def update_request(self, request: RootlessContainerPrototypeRequest) -> RootlessContainerPrototypeRequest: ...
    def set_request_status(self, request_id: str, status: str, actor_id: str | None = None, reason: str | None = None) -> RootlessContainerPrototypeRequest: ...
    def set_request_decision(self, request_id: str, decision: str, actor_id: str | None = None, reason: str | None = None) -> RootlessContainerPrototypeRequest: ...
    def create_capability_assessment(self, assessment: RootlessContainerCapabilityAssessment) -> RootlessContainerCapabilityAssessment: ...
    def list_capability_assessments(self, *, tenant_id: str = "", capability_type: str = "") -> list[RootlessContainerCapabilityAssessment]: ...
    def reserve_plan_metadata_only(self, plan: RootlessContainerPrototypePlan) -> RootlessContainerPrototypePlan: ...
    def get_plan(self, plan_id: str) -> RootlessContainerPrototypePlan | None: ...
    def get_plan_by_request(self, request_id: str) -> RootlessContainerPrototypePlan | None: ...
    def create_gate_result(self, gate: RootlessContainerGateResult) -> RootlessContainerGateResult: ...
    def get_gate_result(self, gate_result_id: str) -> RootlessContainerGateResult | None: ...
    def get_gate_result_by_request(self, request_id: str) -> RootlessContainerGateResult | None: ...
    def add_audit_event(self, event: RootlessContainerAuditEvent) -> RootlessContainerAuditEvent: ...
    def list_audit_events(self, *, request_id: str = "", policy_id: str = "") -> list[RootlessContainerAuditEvent]: ...
    def count_requests(self, *, tenant_id: str = "", status: str = "") -> int: ...


# ═══════════ Capability Builder ═══════════

def build_rootless_container_default_capabilities(tenant_id: str | None = None) -> list[RootlessContainerCapabilityAssessment]:
    """Build 22 default capability assessments for rootless container prototype gate."""
    return [
        # ── Control-plane capabilities (SATISFIED) ──
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.KILL_SWITCH_REQUIRED,
            status=RootlessContainerCapabilityStatus.SATISFIED,
            name="Kill Switch Required",
            description="Kill switch policy and incident store available (Step 26-B)",
            required_before_container_start=True, required_before_execution=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.INCIDENT_STORE_REQUIRED,
            status=RootlessContainerCapabilityStatus.SATISFIED,
            name="Incident Store Required",
            description="Runtime incident store with audit trail available (Step 26-B)",
            required_before_container_start=True, required_before_execution=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.AUDIT_TRAIL_REQUIRED,
            status=RootlessContainerCapabilityStatus.SATISFIED,
            name="Audit Trail Required",
            description="Safety audit event store available (Step 26-B)",
            required_before_container_start=True, required_before_execution=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.RED_TEAM_REQUIRED,
            status=RootlessContainerCapabilityStatus.SATISFIED,
            name="Red Team Required",
            description="163 red-team escape guard tests pass (Step 25-I)",
            required_before_container_start=True, required_before_execution=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.PACKAGE_EXECUTION_DISABLED_REQUIRED,
            status=RootlessContainerCapabilityStatus.SATISFIED,
            name="Package Execution Disabled Required",
            description="Package execution disabled by default (Step 25-D/E, 26-C/D)",
            required_before_execution=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.ENTRYPOINT_EXECUTION_DISABLED_REQUIRED,
            status=RootlessContainerCapabilityStatus.SATISFIED,
            name="Entrypoint Execution Disabled Required",
            description="Entrypoint execution disabled by default, gate always blocked",
            required_before_execution=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.SECRET_INJECTION_DISABLED_REQUIRED,
            status=RootlessContainerCapabilityStatus.SATISFIED,
            name="Secret Injection Disabled Required",
            description="No secrets broker, no env injection available",
            required_before_container_start=True, required_before_execution=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.NO_DOCKER_SOCKET_REQUIRED,
            status=RootlessContainerCapabilityStatus.SATISFIED,
            name="No Docker Socket Required",
            description="Docker socket access blocked by design, no docker invocation",
            required_before_container_start=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.NO_PRIVILEGED_MODE_REQUIRED,
            status=RootlessContainerCapabilityStatus.SATISFIED,
            name="No Privileged Mode Required",
            description="Privileged mode blocked by design",
            required_before_container_start=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.NO_HOST_MOUNT_REQUIRED,
            status=RootlessContainerCapabilityStatus.SATISFIED,
            name="No Host Mount Required",
            description="Host filesystem mounts blocked by design, no mount_enabled",
            required_before_container_start=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.LOG_CAPTURE_POLICY_REQUIRED,
            status=RootlessContainerCapabilityStatus.SATISFIED,
            name="Log Capture Policy Required",
            description="Audit event trail captures all control-plane actions",
            required_before_container_start=True, required_before_execution=True),
        # ── Runtime runtime capabilities (MISSING/BLOCKED) ──
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.ROOTLESS_USER_NAMESPACE_REQUIRED,
            status=RootlessContainerCapabilityStatus.MISSING,
            name="Rootless User Namespace Required",
            description="User namespace for rootless container — not implemented",
            blockers=["No user namespace creation code", "No unshare/clone calls"],
            required_before_container_start=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.NO_ROOT_REQUIRED,
            status=RootlessContainerCapabilityStatus.SATISFIED,
            name="No Root Required",
            description="Root privilege blocked by design",
            required_before_container_start=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.SECCOMP_PROFILE_REQUIRED,
            status=RootlessContainerCapabilityStatus.MISSING,
            name="Seccomp Profile Required",
            description="Seccomp profile for system call filtering — not implemented or written to disk",
            blockers=["No seccomp profile defined", "No seccomp() call executed"],
            required_before_container_start=True, required_before_execution=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.APPARMOR_OR_SELINUX_REQUIRED,
            status=RootlessContainerCapabilityStatus.MISSING,
            name="AppArmor or SELinux Required",
            description="Mandatory access control profile — not implemented or written to disk",
            blockers=["No AppArmor/SELinux profile defined", "No profile applied"],
            required_before_container_start=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.NETWORK_DISABLED_BY_DEFAULT_REQUIRED,
            status=RootlessContainerCapabilityStatus.MISSING,
            name="Network Disabled by Default Required",
            description="Container network stack disabled — runtime enforcement not implemented",
            blockers=["No network namespace isolation at runtime"],
            required_before_container_start=True,
            warnings=["Control-plane blocks network, but runtime enforcement not verified"]),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.FILESYSTEM_READ_ONLY_REQUIRED,
            status=RootlessContainerCapabilityStatus.MISSING,
            name="Filesystem Read-Only Required",
            description="Read-only rootfs — runtime enforcement not implemented",
            blockers=["No read-only mount applied at runtime"],
            required_before_container_start=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.CPU_LIMIT_REQUIRED,
            status=RootlessContainerCapabilityStatus.MISSING,
            name="CPU Limit Required",
            description="Cgroup CPU limit — not implemented",
            blockers=["No cgroup CPU controller configured"],
            required_before_container_start=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.MEMORY_LIMIT_REQUIRED,
            status=RootlessContainerCapabilityStatus.MISSING,
            name="Memory Limit Required",
            description="Cgroup memory limit — not implemented",
            blockers=["No cgroup memory controller configured"],
            required_before_container_start=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.PID_LIMIT_REQUIRED,
            status=RootlessContainerCapabilityStatus.MISSING,
            name="PID Limit Required",
            description="Cgroup PID limit — not implemented",
            blockers=["No cgroup PID controller configured"],
            required_before_container_start=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.TIMEOUT_REQUIRED,
            status=RootlessContainerCapabilityStatus.MISSING,
            name="Timeout Required",
            description="Container timeout enforcement — not implemented",
            blockers=["No timeout mechanism at runtime"],
            required_before_container_start=True, required_before_execution=True),
        RootlessContainerCapabilityAssessment(
            tenant_id=tenant_id,
            capability_type=RootlessContainerCapabilityType.ROLLBACK_REQUIRED,
            status=RootlessContainerCapabilityStatus.MISSING,
            name="Rollback Required",
            description="Container rollback/snapshot — not implemented",
            blockers=["No rollback mechanism implemented"],
            required_before_container_start=True),
    ]


def _safe_dt(raw, none_ok=False):
    if not raw:
        return None if none_ok else datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None if none_ok else datetime.now(timezone.utc)
