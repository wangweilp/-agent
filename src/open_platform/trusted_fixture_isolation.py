"""Trusted Fixture in Isolated Runtime Gate — metadata/control-plane gating only.

Step 26-F: NO isolated runtime. NO container/microVM start. NO fixture execution in container.
NO third-party code. NO package execution. All is_*_enabled/allowed() = always False.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


# ═══════════ Enums ═══════════

class TrustedFixtureIsolationStatus(StrEnum):
    DRAFT = "draft"
    DISABLED_BY_DEFAULT = "disabled_by_default"
    REQUESTED_METADATA_ONLY = "requested_metadata_only"
    ISOLATION_REQUIREMENTS_ASSESSED = "isolation_requirements_assessed"
    PLAN_RESERVED_METADATA_ONLY = "plan_reserved_metadata_only"
    GATE_EVALUATED = "gate_evaluated"
    BLOCKED_DISABLED = "blocked_disabled"
    REVIEW_REQUIRED = "review_required"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAIL_CLOSED = "fail_closed"


class TrustedFixtureIsolationDecision(StrEnum):
    BLOCKED_DISABLED = "blocked_disabled"
    REVIEW_REQUIRED = "review_required"
    METADATA_PLAN_RESERVED = "metadata_plan_reserved"
    READY_FOR_RUNTIME_ENFORCEMENT_SPIKE_ONLY = "ready_for_runtime_enforcement_spike_only"
    FAIL_CLOSED = "fail_closed"


class TrustedFixtureIsolationRequirementStatus(StrEnum):
    SATISFIED = "satisfied"
    MISSING = "missing"
    PARTIALLY_SATISFIED = "partially_satisfied"
    BLOCKED = "blocked"
    NOT_CHECKED_RUNTIME_DISABLED = "not_checked_runtime_disabled"
    FAIL_CLOSED = "fail_closed"


class TrustedFixtureIsolationRequirementType(StrEnum):
    TRUSTED_FIXTURE_REGISTRY_REQUIRED = "trusted_fixture_registry_required"
    BUILTIN_FIXTURE_ONLY_REQUIRED = "builtin_fixture_only_required"
    THIRD_PARTY_EXECUTION_DISABLED_REQUIRED = "third_party_execution_disabled_required"
    PACKAGE_EXECUTION_DISABLED_REQUIRED = "package_execution_disabled_required"
    ENTRYPOINT_EXECUTION_DISABLED_REQUIRED = "entrypoint_execution_disabled_required"
    ROOTLESS_CONTAINER_GATE_REQUIRED = "rootless_container_gate_required"
    CONTAINER_START_DISABLED_REQUIRED = "container_start_disabled_required"
    RUNTIME_DISABLED_REQUIRED = "runtime_disabled_required"
    NETWORK_DISABLED_REQUIRED = "network_disabled_required"
    FILESYSTEM_WRITE_DISABLED_REQUIRED = "filesystem_write_disabled_required"
    SECRETS_DISABLED_REQUIRED = "secrets_disabled_required"
    SUBPROCESS_DISABLED_REQUIRED = "subprocess_disabled_required"
    DYNAMIC_IMPORT_DISABLED_REQUIRED = "dynamic_import_disabled_required"
    EVAL_EXEC_DISABLED_REQUIRED = "eval_exec_disabled_required"
    KILL_SWITCH_REQUIRED = "kill_switch_required"
    INCIDENT_STORE_REQUIRED = "incident_store_required"
    AUDIT_TRAIL_REQUIRED = "audit_trail_required"
    RED_TEAM_GUARDS_REQUIRED = "red_team_guards_required"
    ISOLATED_RUNTIME_IMPLEMENTATION_MISSING = "isolated_runtime_implementation_missing"
    OS_LEVEL_ISOLATION_MISSING = "os_level_isolation_missing"
    RESOURCE_LIMITS_MISSING = "resource_limits_missing"
    RUNTIME_ENFORCEMENT_MISSING = "runtime_enforcement_missing"


class TrustedFixtureIsolationAuditEventType(StrEnum):
    POLICY_CREATED = "policy_created"
    REQUEST_CREATED = "request_created"
    REQUIREMENT_ASSESSED = "requirement_assessed"
    PLAN_RESERVED_METADATA_ONLY = "plan_reserved_metadata_only"
    GATE_EVALUATED = "gate_evaluated"
    STATUS_CHANGED = "status_changed"
    DECISION_CHANGED = "decision_changed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    NOTE_ADDED = "note_added"


class TrustedFixtureIsolationAuditSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


# ═══════════ Dataclasses ═══════════

@dataclass
class TrustedFixtureIsolationPolicy:
    policy_id: str = field(default_factory=lambda: f"tfixpol_{uuid4().hex[:16]}")
    tenant_id: str | None = None
    enabled_metadata_only: bool = True
    isolated_runtime_enabled: bool = False
    container_start_enabled: bool = False
    microvm_start_enabled: bool = False
    trusted_fixture_execution_enabled: bool = False
    third_party_execution_enabled: bool = False
    package_execution_enabled: bool = False
    entrypoint_execution_enabled: bool = False
    network_enabled: bool = False
    filesystem_write_enabled: bool = False
    secrets_enabled: bool = False
    subprocess_enabled: bool = False
    dynamic_import_enabled: bool = False
    eval_exec_enabled: bool = False
    requires_rootless_container_gate: bool = True
    requires_kill_switch_clear: bool = True
    requires_incident_clear: bool = True
    requires_red_team_passed: bool = True
    created_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_isolated_runtime_enabled(self) -> bool: return False
    def is_fixture_execution_allowed(self) -> bool: return False
    def is_third_party_execution_allowed(self) -> bool: return False
    def is_package_execution_allowed(self) -> bool: return False

    def to_dict(self):
        return {
            "policy_id": self.policy_id, "tenant_id": self.tenant_id,
            "enabled_metadata_only": self.enabled_metadata_only,
            "isolated_runtime_enabled": self.isolated_runtime_enabled,
            "container_start_enabled": self.container_start_enabled,
            "microvm_start_enabled": self.microvm_start_enabled,
            "trusted_fixture_execution_enabled": self.trusted_fixture_execution_enabled,
            "third_party_execution_enabled": self.third_party_execution_enabled,
            "package_execution_enabled": self.package_execution_enabled,
            "entrypoint_execution_enabled": self.entrypoint_execution_enabled,
            "network_enabled": self.network_enabled,
            "filesystem_write_enabled": self.filesystem_write_enabled,
            "secrets_enabled": self.secrets_enabled,
            "subprocess_enabled": self.subprocess_enabled,
            "dynamic_import_enabled": self.dynamic_import_enabled,
            "eval_exec_enabled": self.eval_exec_enabled,
            "requires_rootless_container_gate": self.requires_rootless_container_gate,
            "requires_kill_switch_clear": self.requires_kill_switch_clear,
            "requires_incident_clear": self.requires_incident_clear,
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
            isolated_runtime_enabled=bool(d.get("isolated_runtime_enabled", False)),
            container_start_enabled=bool(d.get("container_start_enabled", False)),
            microvm_start_enabled=bool(d.get("microvm_start_enabled", False)),
            trusted_fixture_execution_enabled=bool(d.get("trusted_fixture_execution_enabled", False)),
            third_party_execution_enabled=bool(d.get("third_party_execution_enabled", False)),
            package_execution_enabled=bool(d.get("package_execution_enabled", False)),
            entrypoint_execution_enabled=bool(d.get("entrypoint_execution_enabled", False)),
            network_enabled=bool(d.get("network_enabled", False)),
            filesystem_write_enabled=bool(d.get("filesystem_write_enabled", False)),
            secrets_enabled=bool(d.get("secrets_enabled", False)),
            subprocess_enabled=bool(d.get("subprocess_enabled", False)),
            dynamic_import_enabled=bool(d.get("dynamic_import_enabled", False)),
            eval_exec_enabled=bool(d.get("eval_exec_enabled", False)),
            requires_rootless_container_gate=bool(d.get("requires_rootless_container_gate", True)),
            requires_kill_switch_clear=bool(d.get("requires_kill_switch_clear", True)),
            requires_incident_clear=bool(d.get("requires_incident_clear", True)),
            requires_red_team_passed=bool(d.get("requires_red_team_passed", True)),
            created_by=d.get("created_by"),
            created_at=_safe_dt(d.get("created_at")),
            updated_at=_safe_dt(d.get("updated_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class TrustedFixtureIsolationRequirement:
    requirement_id: str = field(default_factory=lambda: f"tfixreq_{uuid4().hex[:16]}")
    tenant_id: str | None = None
    requirement_type: str = ""
    status: str = TrustedFixtureIsolationRequirementStatus.NOT_CHECKED_RUNTIME_DISABLED
    name: str = ""
    description: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    required_before_isolated_fixture: bool = True
    required_before_third_party_execution: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "requirement_id": self.requirement_id, "tenant_id": self.tenant_id,
            "requirement_type": self.requirement_type, "status": self.status,
            "name": self.name, "description": self.description,
            "evidence_refs": list(self.evidence_refs),
            "blockers": list(self.blockers), "warnings": list(self.warnings),
            "required_before_isolated_fixture": self.required_before_isolated_fixture,
            "required_before_third_party_execution": self.required_before_third_party_execution,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": dict(self.metadata)
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            requirement_id=str(d.get("requirement_id", "")), tenant_id=d.get("tenant_id"),
            requirement_type=str(d.get("requirement_type", "")),
            status=str(d.get("status", "not_checked_runtime_disabled")),
            name=str(d.get("name", "")), description=str(d.get("description", "")),
            evidence_refs=list(d.get("evidence_refs", [])),
            blockers=list(d.get("blockers", [])), warnings=list(d.get("warnings", [])),
            required_before_isolated_fixture=bool(d.get("required_before_isolated_fixture", True)),
            required_before_third_party_execution=bool(d.get("required_before_third_party_execution", True)),
            created_at=_safe_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class TrustedFixtureIsolationRequest:
    request_id: str = field(default_factory=lambda: f"tfixreq_{uuid4().hex[:16]}")
    tenant_id: str | None = None
    policy_id: str | None = None
    trusted_fixture_request_id: str | None = None
    trusted_fixture_id: str | None = None
    rootless_container_gate_request_id: str | None = None
    rootless_container_plan_id: str | None = None
    policy_snapshot: dict[str, Any] = field(default_factory=dict)
    trusted_fixture_snapshot: dict[str, Any] = field(default_factory=dict)
    rootless_container_snapshot: dict[str, Any] = field(default_factory=dict)
    kill_switch_snapshot: dict[str, Any] = field(default_factory=dict)
    incident_snapshot: dict[str, Any] = field(default_factory=dict)
    status: str = TrustedFixtureIsolationStatus.DISABLED_BY_DEFAULT
    decision: str = TrustedFixtureIsolationDecision.BLOCKED_DISABLED
    isolated_runtime_started: bool = False
    container_started: bool = False
    microvm_started: bool = False
    fixture_executed_in_isolated_runtime: bool = False
    fixture_executed_in_container: bool = False
    fixture_executed_in_microvm: bool = False
    third_party_code_executed: bool = False
    package_executed: bool = False
    entrypoint_executed: bool = False
    network_used: bool = False
    filesystem_written: bool = False
    secrets_read: bool = False
    subprocess_used: bool = False
    no_isolated_runtime_started: bool = True
    no_container_started: bool = True
    no_microvm_started: bool = True
    no_third_party_code_executed: bool = True
    no_package_executed: bool = True
    no_entrypoint_executed: bool = True
    no_network_used: bool = True
    no_filesystem_written: bool = True
    no_secrets_read: bool = True
    no_subprocess_used: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_fixture_execution_allowed(self) -> bool: return False
    def is_isolated_runtime_enabled(self) -> bool: return False
    def is_third_party_execution_allowed(self) -> bool: return False
    def is_package_execution_allowed(self) -> bool: return False

    def to_dict(self):
        return {
            "request_id": self.request_id, "tenant_id": self.tenant_id,
            "policy_id": self.policy_id,
            "trusted_fixture_request_id": self.trusted_fixture_request_id,
            "trusted_fixture_id": self.trusted_fixture_id,
            "rootless_container_gate_request_id": self.rootless_container_gate_request_id,
            "rootless_container_plan_id": self.rootless_container_plan_id,
            "policy_snapshot": dict(self.policy_snapshot),
            "trusted_fixture_snapshot": dict(self.trusted_fixture_snapshot),
            "rootless_container_snapshot": dict(self.rootless_container_snapshot),
            "kill_switch_snapshot": dict(self.kill_switch_snapshot),
            "incident_snapshot": dict(self.incident_snapshot),
            "status": self.status, "decision": self.decision,
            "isolated_runtime_started": self.isolated_runtime_started,
            "container_started": self.container_started,
            "microvm_started": self.microvm_started,
            "fixture_executed_in_isolated_runtime": self.fixture_executed_in_isolated_runtime,
            "fixture_executed_in_container": self.fixture_executed_in_container,
            "fixture_executed_in_microvm": self.fixture_executed_in_microvm,
            "third_party_code_executed": self.third_party_code_executed,
            "package_executed": self.package_executed,
            "entrypoint_executed": self.entrypoint_executed,
            "network_used": self.network_used,
            "filesystem_written": self.filesystem_written,
            "secrets_read": self.secrets_read,
            "subprocess_used": self.subprocess_used,
            "no_isolated_runtime_started": self.no_isolated_runtime_started,
            "no_container_started": self.no_container_started,
            "no_microvm_started": self.no_microvm_started,
            "no_third_party_code_executed": self.no_third_party_code_executed,
            "no_package_executed": self.no_package_executed,
            "no_entrypoint_executed": self.no_entrypoint_executed,
            "no_network_used": self.no_network_used,
            "no_filesystem_written": self.no_filesystem_written,
            "no_secrets_read": self.no_secrets_read,
            "no_subprocess_used": self.no_subprocess_used,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": dict(self.metadata)
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            request_id=str(d.get("request_id", "")), tenant_id=d.get("tenant_id"),
            policy_id=d.get("policy_id"),
            trusted_fixture_request_id=d.get("trusted_fixture_request_id"),
            trusted_fixture_id=d.get("trusted_fixture_id"),
            rootless_container_gate_request_id=d.get("rootless_container_gate_request_id"),
            rootless_container_plan_id=d.get("rootless_container_plan_id"),
            policy_snapshot=dict(d.get("policy_snapshot", {})),
            trusted_fixture_snapshot=dict(d.get("trusted_fixture_snapshot", {})),
            rootless_container_snapshot=dict(d.get("rootless_container_snapshot", {})),
            kill_switch_snapshot=dict(d.get("kill_switch_snapshot", {})),
            incident_snapshot=dict(d.get("incident_snapshot", {})),
            status=str(d.get("status", "disabled_by_default")),
            decision=str(d.get("decision", "blocked_disabled")),
            isolated_runtime_started=bool(d.get("isolated_runtime_started", False)),
            container_started=bool(d.get("container_started", False)),
            microvm_started=bool(d.get("microvm_started", False)),
            fixture_executed_in_isolated_runtime=bool(d.get("fixture_executed_in_isolated_runtime", False)),
            fixture_executed_in_container=bool(d.get("fixture_executed_in_container", False)),
            fixture_executed_in_microvm=bool(d.get("fixture_executed_in_microvm", False)),
            third_party_code_executed=bool(d.get("third_party_code_executed", False)),
            package_executed=bool(d.get("package_executed", False)),
            entrypoint_executed=bool(d.get("entrypoint_executed", False)),
            network_used=bool(d.get("network_used", False)),
            filesystem_written=bool(d.get("filesystem_written", False)),
            secrets_read=bool(d.get("secrets_read", False)),
            subprocess_used=bool(d.get("subprocess_used", False)),
            no_isolated_runtime_started=bool(d.get("no_isolated_runtime_started", True)),
            no_container_started=bool(d.get("no_container_started", True)),
            no_microvm_started=bool(d.get("no_microvm_started", True)),
            no_third_party_code_executed=bool(d.get("no_third_party_code_executed", True)),
            no_package_executed=bool(d.get("no_package_executed", True)),
            no_entrypoint_executed=bool(d.get("no_entrypoint_executed", True)),
            no_network_used=bool(d.get("no_network_used", True)),
            no_filesystem_written=bool(d.get("no_filesystem_written", True)),
            no_secrets_read=bool(d.get("no_secrets_read", True)),
            no_subprocess_used=bool(d.get("no_subprocess_used", True)),
            created_at=_safe_dt(d.get("created_at")),
            updated_at=_safe_dt(d.get("updated_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class TrustedFixtureIsolationPlan:
    plan_id: str = field(default_factory=lambda: f"tfixplan_{uuid4().hex[:16]}")
    request_id: str = ""
    tenant_id: str | None = None
    policy_id: str | None = None
    fixture_id: str | None = None
    isolation_requirements: list[dict[str, Any]] = field(default_factory=list)
    satisfied_requirements: list[str] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)
    blocker_summary: str = ""
    plan_status: str = TrustedFixtureIsolationStatus.PLAN_RESERVED_METADATA_ONLY
    decision: str = TrustedFixtureIsolationDecision.METADATA_PLAN_RESERVED
    ready_for_step26g: bool = False
    isolated_runtime_enabled: bool = False
    container_start_allowed: bool = False
    microvm_start_allowed: bool = False
    fixture_execution_allowed: bool = False
    third_party_execution_allowed: bool = False
    package_execution_allowed: bool = False
    entrypoint_execution_allowed: bool = False
    network_allowed: bool = False
    filesystem_write_allowed: bool = False
    secrets_allowed: bool = False
    subprocess_allowed: bool = False
    metadata_only: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_fixture_execution_allowed(self) -> bool: return False
    def is_runtime_enabled(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False

    def to_dict(self):
        return {
            "plan_id": self.plan_id, "request_id": self.request_id,
            "tenant_id": self.tenant_id, "policy_id": self.policy_id,
            "fixture_id": self.fixture_id,
            "isolation_requirements": [dict(r) for r in self.isolation_requirements],
            "satisfied_requirements": list(self.satisfied_requirements),
            "missing_requirements": list(self.missing_requirements),
            "blocker_summary": self.blocker_summary,
            "plan_status": self.plan_status, "decision": self.decision,
            "ready_for_step26g": self.ready_for_step26g,
            "isolated_runtime_enabled": self.isolated_runtime_enabled,
            "container_start_allowed": self.container_start_allowed,
            "microvm_start_allowed": self.microvm_start_allowed,
            "fixture_execution_allowed": self.fixture_execution_allowed,
            "third_party_execution_allowed": self.third_party_execution_allowed,
            "package_execution_allowed": self.package_execution_allowed,
            "entrypoint_execution_allowed": self.entrypoint_execution_allowed,
            "network_allowed": self.network_allowed,
            "filesystem_write_allowed": self.filesystem_write_allowed,
            "secrets_allowed": self.secrets_allowed,
            "subprocess_allowed": self.subprocess_allowed,
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
            fixture_id=d.get("fixture_id"),
            isolation_requirements=[dict(r) for r in d.get("isolation_requirements", [])],
            satisfied_requirements=list(d.get("satisfied_requirements", [])),
            missing_requirements=list(d.get("missing_requirements", [])),
            blocker_summary=str(d.get("blocker_summary", "")),
            plan_status=str(d.get("plan_status", "plan_reserved_metadata_only")),
            decision=str(d.get("decision", "metadata_plan_reserved")),
            ready_for_step26g=bool(d.get("ready_for_step26g", False)),
            isolated_runtime_enabled=bool(d.get("isolated_runtime_enabled", False)),
            container_start_allowed=bool(d.get("container_start_allowed", False)),
            microvm_start_allowed=bool(d.get("microvm_start_allowed", False)),
            fixture_execution_allowed=bool(d.get("fixture_execution_allowed", False)),
            third_party_execution_allowed=bool(d.get("third_party_execution_allowed", False)),
            package_execution_allowed=bool(d.get("package_execution_allowed", False)),
            entrypoint_execution_allowed=bool(d.get("entrypoint_execution_allowed", False)),
            network_allowed=bool(d.get("network_allowed", False)),
            filesystem_write_allowed=bool(d.get("filesystem_write_allowed", False)),
            secrets_allowed=bool(d.get("secrets_allowed", False)),
            subprocess_allowed=bool(d.get("subprocess_allowed", False)),
            metadata_only=bool(d.get("metadata_only", True)),
            created_at=_safe_dt(d.get("created_at")),
            updated_at=_safe_dt(d.get("updated_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class TrustedFixtureIsolationGateResult:
    gate_result_id: str = field(default_factory=lambda: f"tfixgate_{uuid4().hex[:16]}")
    request_id: str = ""
    tenant_id: str | None = None
    status: str = TrustedFixtureIsolationStatus.DISABLED_BY_DEFAULT
    decision: str = TrustedFixtureIsolationDecision.BLOCKED_DISABLED
    checks: list[dict[str, Any]] = field(default_factory=list)
    satisfied_count: int = 0
    missing_count: int = 0
    blockers_count: int = 0
    warnings_count: int = 0
    ready_for_step26g: bool = False
    isolated_runtime_enabled: bool = False
    container_start_allowed: bool = False
    microvm_start_allowed: bool = False
    fixture_execution_allowed: bool = False
    third_party_execution_allowed: bool = False
    package_execution_allowed: bool = False
    execution_allowed: bool = False
    metadata_only: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "gate_result_id": self.gate_result_id, "request_id": self.request_id,
            "tenant_id": self.tenant_id, "status": self.status, "decision": self.decision,
            "checks": [dict(c) for c in self.checks],
            "satisfied_count": self.satisfied_count, "missing_count": self.missing_count,
            "blockers_count": self.blockers_count, "warnings_count": self.warnings_count,
            "ready_for_step26g": self.ready_for_step26g,
            "isolated_runtime_enabled": self.isolated_runtime_enabled,
            "container_start_allowed": self.container_start_allowed,
            "microvm_start_allowed": self.microvm_start_allowed,
            "fixture_execution_allowed": self.fixture_execution_allowed,
            "third_party_execution_allowed": self.third_party_execution_allowed,
            "package_execution_allowed": self.package_execution_allowed,
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
            satisfied_count=int(d.get("satisfied_count", 0)),
            missing_count=int(d.get("missing_count", 0)),
            blockers_count=int(d.get("blockers_count", 0)),
            warnings_count=int(d.get("warnings_count", 0)),
            ready_for_step26g=bool(d.get("ready_for_step26g", False)),
            isolated_runtime_enabled=bool(d.get("isolated_runtime_enabled", False)),
            container_start_allowed=bool(d.get("container_start_allowed", False)),
            microvm_start_allowed=bool(d.get("microvm_start_allowed", False)),
            fixture_execution_allowed=bool(d.get("fixture_execution_allowed", False)),
            third_party_execution_allowed=bool(d.get("third_party_execution_allowed", False)),
            package_execution_allowed=bool(d.get("package_execution_allowed", False)),
            execution_allowed=bool(d.get("execution_allowed", False)),
            metadata_only=bool(d.get("metadata_only", True)),
            created_at=_safe_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}))
        )


@dataclass
class TrustedFixtureIsolationAuditEvent:
    event_id: str = field(default_factory=lambda: f"tfixevt_{uuid4().hex[:16]}")
    tenant_id: str | None = None
    request_id: str | None = None
    plan_id: str | None = None
    policy_id: str | None = None
    requirement_id: str | None = None
    event_type: str = ""
    severity: str = TrustedFixtureIsolationAuditSeverity.INFO
    actor_id: str | None = None
    message: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "event_id": self.event_id, "tenant_id": self.tenant_id,
            "request_id": self.request_id, "plan_id": self.plan_id,
            "policy_id": self.policy_id, "requirement_id": self.requirement_id,
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
            policy_id=d.get("policy_id"), requirement_id=d.get("requirement_id"),
            event_type=str(d.get("event_type", "")),
            severity=str(d.get("severity", "info")),
            actor_id=d.get("actor_id"), message=str(d.get("message", "")),
            created_at=_safe_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}))
        )


# ═══════════ Errors ═══════════

class TrustedFixtureIsolationError(Exception): pass
class TrustedFixtureIsolationPolicyNotFoundError(TrustedFixtureIsolationError): pass
class TrustedFixtureIsolationRequestNotFoundError(TrustedFixtureIsolationError): pass
class TrustedFixtureIsolationPlanNotFoundError(TrustedFixtureIsolationError): pass
class TrustedFixtureIsolationBlockedError(TrustedFixtureIsolationError): pass


# ═══════════ Protocol ═══════════

@runtime_checkable
class TrustedFixtureIsolationStore(Protocol):
    def create_policy(self, policy: TrustedFixtureIsolationPolicy) -> TrustedFixtureIsolationPolicy: ...
    def get_policy(self, policy_id: str) -> TrustedFixtureIsolationPolicy | None: ...
    def list_policies(self, *, tenant_id: str = "") -> list[TrustedFixtureIsolationPolicy]: ...
    def update_policy(self, policy: TrustedFixtureIsolationPolicy) -> TrustedFixtureIsolationPolicy: ...
    def create_request(self, request: TrustedFixtureIsolationRequest) -> TrustedFixtureIsolationRequest: ...
    def get_request(self, request_id: str) -> TrustedFixtureIsolationRequest | None: ...
    def list_requests(self, *, tenant_id: str = "", status: str = "", policy_id: str = "") -> list[TrustedFixtureIsolationRequest]: ...
    def update_request(self, request: TrustedFixtureIsolationRequest) -> TrustedFixtureIsolationRequest: ...
    def set_request_status(self, request_id: str, status: str, actor_id: str | None = None, reason: str | None = None) -> TrustedFixtureIsolationRequest: ...
    def set_request_decision(self, request_id: str, decision: str, actor_id: str | None = None, reason: str | None = None) -> TrustedFixtureIsolationRequest: ...
    def create_requirement(self, req: TrustedFixtureIsolationRequirement) -> TrustedFixtureIsolationRequirement: ...
    def list_requirements(self, *, tenant_id: str = "", requirement_type: str = "") -> list[TrustedFixtureIsolationRequirement]: ...
    def reserve_plan_metadata_only(self, plan: TrustedFixtureIsolationPlan) -> TrustedFixtureIsolationPlan: ...
    def get_plan(self, plan_id: str) -> TrustedFixtureIsolationPlan | None: ...
    def get_plan_by_request(self, request_id: str) -> TrustedFixtureIsolationPlan | None: ...
    def create_gate_result(self, gate: TrustedFixtureIsolationGateResult) -> TrustedFixtureIsolationGateResult: ...
    def get_gate_result(self, gate_result_id: str) -> TrustedFixtureIsolationGateResult | None: ...
    def get_gate_result_by_request(self, request_id: str) -> TrustedFixtureIsolationGateResult | None: ...
    def add_audit_event(self, event: TrustedFixtureIsolationAuditEvent) -> TrustedFixtureIsolationAuditEvent: ...
    def list_audit_events(self, *, request_id: str = "", policy_id: str = "") -> list[TrustedFixtureIsolationAuditEvent]: ...
    def count_requests(self, *, tenant_id: str = "", status: str = "") -> int: ...


# ═══════════ Requirement Builder ═══════════

def build_trusted_fixture_isolation_default_requirements(tenant_id: str | None = None) -> list[TrustedFixtureIsolationRequirement]:
    """Build 22 default requirements for trusted fixture in isolated runtime gate."""
    return [
        # ── Satisfied (18) ──
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.TRUSTED_FIXTURE_REGISTRY_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Trusted Fixture Registry Required",
            description="Built-in trusted fixtures available via Step 25-H",
            required_before_isolated_fixture=True, required_before_third_party_execution=True),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.BUILTIN_FIXTURE_ONLY_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Built-in Fixture Only Required",
            description="Only built-in fixtures allowed, no third-party submission as fixture",
            required_before_isolated_fixture=True, required_before_third_party_execution=True),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.THIRD_PARTY_EXECUTION_DISABLED_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Third-Party Execution Disabled Required",
            description="All execution entrypoints block third-party code (Step 24-H, 25-K, 26-A)",
            required_before_third_party_execution=True),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.PACKAGE_EXECUTION_DISABLED_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Package Execution Disabled Required",
            description="Package execution disabled by default (Step 26-C/D/E)",
            required_before_third_party_execution=True),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.ENTRYPOINT_EXECUTION_DISABLED_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Entrypoint Execution Disabled Required",
            description="Entrypoint execution blocked by default"),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.ROOTLESS_CONTAINER_GATE_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Rootless Container Gate Required",
            description="Rootless container gate passed (Step 26-E, ready_for_step26f=True)"),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.CONTAINER_START_DISABLED_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Container Start Disabled Required",
            description="No container started (Step 26-E, container_start_allowed=False)"),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.RUNTIME_DISABLED_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Runtime Disabled Required",
            description="Runtime disabled by default (all steps)"),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.NETWORK_DISABLED_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Network Disabled Required",
            description="No network access (control-plane blocks)"),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.FILESYSTEM_WRITE_DISABLED_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Filesystem Write Disabled Required",
            description="No file write (Step 26-D, no_file_written=True)"),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.SECRETS_DISABLED_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Secrets Disabled Required",
            description="No secrets broker, no env injection"),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.SUBPROCESS_DISABLED_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Subprocess Disabled Required",
            description="No subprocess calls in production code"),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.DYNAMIC_IMPORT_DISABLED_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Dynamic Import Disabled Required",
            description="No dynamic import in production code"),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.EVAL_EXEC_DISABLED_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Eval/Exec Disabled Required",
            description="No eval/exec in production code"),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.KILL_SWITCH_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Kill Switch Required",
            description="Kill switch policy and incident store available (Step 26-B)"),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.INCIDENT_STORE_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Incident Store Required",
            description="Runtime incident store with audit trail (Step 26-B)"),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.AUDIT_TRAIL_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Audit Trail Required",
            description="Comprehensive audit event trail for all control-plane actions"),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.RED_TEAM_GUARDS_REQUIRED,
            status=TrustedFixtureIsolationRequirementStatus.SATISFIED,
            name="Red Team Guards Required",
            description="Red-team escape guard tests pass (163 tests, Step 25-I)"),
        # ── Missing (4) ──
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.ISOLATED_RUNTIME_IMPLEMENTATION_MISSING,
            status=TrustedFixtureIsolationRequirementStatus.MISSING,
            name="Isolated Runtime Implementation Missing",
            description="No real isolated runtime sandbox exists. Container/microVM not started.",
            blockers=["No rootless container runtime", "No microVM runtime", "No sandbox process isolation"],
            required_before_isolated_fixture=True, required_before_third_party_execution=True),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.OS_LEVEL_ISOLATION_MISSING,
            status=TrustedFixtureIsolationRequirementStatus.MISSING,
            name="OS-Level Isolation Missing",
            description="No namespace/cgroup/seccomp/AppArmor at runtime",
            blockers=["No user namespace", "No seccomp profile", "No AppArmor/SELinux applied"],
            required_before_isolated_fixture=True, required_before_third_party_execution=True),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.RESOURCE_LIMITS_MISSING,
            status=TrustedFixtureIsolationRequirementStatus.MISSING,
            name="Resource Limits Missing",
            description="No CPU/memory/PID/timeout limits at runtime",
            blockers=["No cgroup CPU/memory/PID controllers"],
            required_before_isolated_fixture=True, required_before_third_party_execution=True),
        TrustedFixtureIsolationRequirement(
            tenant_id=tenant_id,
            requirement_type=TrustedFixtureIsolationRequirementType.RUNTIME_ENFORCEMENT_MISSING,
            status=TrustedFixtureIsolationRequirementStatus.MISSING,
            name="Runtime Enforcement Missing",
            description="No runtime-level network/filesystem/secrets enforcement",
            blockers=["No network namespace isolation", "No read-only rootfs", "No secrets firewall"],
            required_before_isolated_fixture=True, required_before_third_party_execution=True),
    ]


def _safe_dt(raw, none_ok=False):
    if not raw:
        return None if none_ok else datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None if none_ok else datetime.now(timezone.utc)
