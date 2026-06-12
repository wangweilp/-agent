"""Runtime Execution Plan Domain Model — Developer Agent 执行计划。

Step 24-D MVP:
- RuntimeExecutionPlanCheck — 单个 preflight check
- RuntimeExecutionPlan — 执行计划（不做执行）
- RuntimeExecutionPlanAuditEvent — 审计事件
- RuntimeExecutionPlanStore Protocol — 存储层抽象

安全边界：
- is_dispatchable() 始终 False — no worker/dispatch in Step 24-D
- no_download_planned / no_network_planned / no_execution_performed 始终 True
- dispatch_status 不出现 DISPATCHED / RUNNING / COMPLETED
- SANDBOX_RESERVED mode 不执行
"""

from __future__ import annotations

import hashlib, json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


# ═══════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════

class RuntimeExecutionMode(StrEnum):
    SIMULATION = "simulation"
    SANDBOX_RESERVED = "sandbox_reserved"
    DISABLED = "disabled"

class RuntimeExecutionPlanStatus(StrEnum):
    DRAFT = "draft"
    PLANNED = "planned"
    BLOCKED = "blocked"
    REVIEW_REQUIRED = "review_required"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

class RuntimeDispatchStatus(StrEnum):
    NOT_DISPATCHABLE = "not_dispatchable"
    WORKER_UNAVAILABLE = "worker_unavailable"
    RESERVED_FOR_STEP24E = "reserved_for_step24e"
    DISABLED = "disabled"

class RuntimePlanDecision(StrEnum):
    ALLOW_PLAN = "allow_plan"
    BLOCK_PLAN = "block_plan"
    REVIEW_REQUIRED = "review_required"
    RESERVED_ONLY = "reserved_only"

class RuntimePlanCheckType(StrEnum):
    MARKETPLACE_AGENT_EXISTS = "marketplace_agent_exists"
    MARKETPLACE_AGENT_IS_DEVELOPER = "marketplace_agent_is_developer"
    TENANT_INSTALLATION_ACTIVE = "tenant_installation_active"
    REQUIRED_PERMISSIONS_GRANTED = "required_permissions_granted"
    RUNTIME_BINDING_EXISTS = "runtime_binding_exists"
    RUNTIME_BINDING_ENABLED = "runtime_binding_enabled"
    RUNTIME_ADAPTER_ALLOWED = "runtime_adapter_allowed"
    SANDBOX_POLICY_EXISTS = "sandbox_policy_exists"
    SANDBOX_POLICY_ACTIVE = "sandbox_policy_active"
    ARTIFACT_DECLARED = "artifact_declared"
    ARTIFACT_NOT_REJECTED = "artifact_not_rejected"
    ARTIFACT_QUARANTINE_ACCEPTABLE = "artifact_quarantine_acceptable"
    PACKAGE_VERIFICATION_EXISTS = "package_verification_exists"
    CHECKSUM_VERIFIED_OR_PENDING_POLICY = "checksum_verified_or_pending_policy"
    SIGNATURE_METADATA_ACCEPTABLE = "signature_metadata_acceptable"
    KILL_SWITCH_OFF_RESERVED = "kill_switch_off_reserved"
    WORKER_AVAILABLE_RESERVED = "worker_available_reserved"
    NO_DOWNLOAD_IN_PLAN = "no_download_in_plan"
    NO_EXECUTION_IN_PLAN = "no_execution_in_plan"
    NO_NETWORK_IN_PLAN = "no_network_in_plan"

class RuntimePlanCheckStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"

class RuntimePlanSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"

class RuntimeExecutionRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

class RuntimeExecutionPlanAuditEventType(StrEnum):
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    CHECK_ADDED = "check_added"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REVIEW_REQUIRED = "review_required"


# ═══════════════════════════════════════════
# RuntimeExecutionPlanCheck
# ═══════════════════════════════════════════

@dataclass
class RuntimeExecutionPlanCheck:
    check_id: str = field(default_factory=lambda: f"planchk_{uuid4().hex[:16]}")
    check_type: str = ""
    status: str = RuntimePlanCheckStatus.PASSED
    severity: str = RuntimePlanSeverity.INFO
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id, "check_type": self.check_type,
            "status": self.status, "severity": self.severity,
            "message": self.message, "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RuntimeExecutionPlanCheck":
        return cls(
            check_id=str(d.get("check_id", "")), check_type=str(d.get("check_type", "")),
            status=str(d.get("status", RuntimePlanCheckStatus.PASSED)),
            severity=str(d.get("severity", RuntimePlanSeverity.INFO)),
            message=str(d.get("message", "")), metadata=dict(d.get("metadata", {})),
            created_at=_safe_dt(d.get("created_at")),
        )


# ═══════════════════════════════════════════
# RuntimeExecutionPlan
# ═══════════════════════════════════════════

@dataclass
class RuntimeExecutionPlan:
    plan_id: str = field(default_factory=lambda: f"rtexplan_{uuid4().hex[:16]}")
    marketplace_agent_id: str = ""
    tenant_id: str = ""
    user_id: str | None = None
    developer_id: str = ""
    submission_id: str | None = None
    runtime_binding_id: str | None = None
    adapter_id: str | None = None
    adapter_type: str | None = None
    sandbox_policy_id: str | None = None
    artifact_id: str | None = None
    verification_id: str | None = None
    execution_mode: str = RuntimeExecutionMode.SANDBOX_RESERVED
    plan_status: str = RuntimeExecutionPlanStatus.DRAFT
    dispatch_status: str = RuntimeDispatchStatus.RESERVED_FOR_STEP24E
    decision: str = RuntimePlanDecision.RESERVED_ONLY
    risk_level: str = RuntimeExecutionRiskLevel.UNKNOWN
    checks: list[RuntimeExecutionPlanCheck] = field(default_factory=list)
    warnings_count: int = 0
    errors_count: int = 0
    blockers_count: int = 0
    input_payload_hash: str | None = None
    output_contract: dict[str, Any] = field(default_factory=dict)
    policy_snapshot: dict[str, Any] = field(default_factory=dict)
    artifact_snapshot: dict[str, Any] = field(default_factory=dict)
    verification_snapshot: dict[str, Any] = field(default_factory=dict)
    no_download_planned: bool = True
    no_network_planned: bool = True
    no_execution_performed: bool = True
    worker_required: bool = False
    worker_available: bool = False
    expires_at: datetime | None = None
    created_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        for fld in ["output_contract", "policy_snapshot", "artifact_snapshot", "verification_snapshot", "metadata"]:
            v = getattr(self, fld)
            if not isinstance(v, dict):
                raise ValueError(f"{fld} must be dict")

    def add_check(self, check: RuntimeExecutionPlanCheck) -> None:
        self.checks.append(check)
        self._recount()

    def _recount(self) -> None:
        self.warnings_count = sum(1 for c in self.checks if c.status == RuntimePlanCheckStatus.WARNING)
        self.errors_count = sum(1 for c in self.checks if c.status == RuntimePlanCheckStatus.FAILED and c.severity != RuntimePlanSeverity.BLOCKER)
        self.blockers_count = sum(1 for c in self.checks if c.status == RuntimePlanCheckStatus.BLOCKED or (c.status == RuntimePlanCheckStatus.FAILED and c.severity == RuntimePlanSeverity.BLOCKER))

    def calculate_status(self) -> None:
        self._recount()
        if self.blockers_count > 0:
            self.plan_status = RuntimeExecutionPlanStatus.BLOCKED
            self.decision = RuntimePlanDecision.BLOCK_PLAN
        elif self.errors_count > 0:
            self.plan_status = RuntimeExecutionPlanStatus.REVIEW_REQUIRED
            self.decision = RuntimePlanDecision.REVIEW_REQUIRED
        elif self.warnings_count > 0:
            self.plan_status = RuntimeExecutionPlanStatus.PLANNED
            self.decision = RuntimePlanDecision.RESERVED_ONLY
        else:
            self.plan_status = RuntimeExecutionPlanStatus.PLANNED
            self.decision = RuntimePlanDecision.RESERVED_ONLY

    def is_dispatchable(self) -> bool:
        """Step 24-D: 始终返回 False。no worker / no queue / no dispatch。"""
        return False

    def is_blocked(self) -> bool:
        return self.plan_status == RuntimeExecutionPlanStatus.BLOCKED

    def is_expired(self) -> bool:
        return (self.plan_status == RuntimeExecutionPlanStatus.EXPIRED or
                (self.expires_at is not None and self.expires_at < datetime.now(timezone.utc)))

    @staticmethod
    def hash_payload(payload: dict | None) -> str | None:
        if payload is None: return None
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id, "marketplace_agent_id": self.marketplace_agent_id,
            "tenant_id": self.tenant_id, "user_id": self.user_id,
            "developer_id": self.developer_id, "submission_id": self.submission_id,
            "runtime_binding_id": self.runtime_binding_id, "adapter_id": self.adapter_id,
            "adapter_type": self.adapter_type, "sandbox_policy_id": self.sandbox_policy_id,
            "artifact_id": self.artifact_id, "verification_id": self.verification_id,
            "execution_mode": self.execution_mode, "plan_status": self.plan_status,
            "dispatch_status": self.dispatch_status, "decision": self.decision,
            "risk_level": self.risk_level,
            "checks": [c.to_dict() for c in self.checks],
            "warnings_count": self.warnings_count, "errors_count": self.errors_count,
            "blockers_count": self.blockers_count, "input_payload_hash": self.input_payload_hash,
            "output_contract": dict(self.output_contract),
            "policy_snapshot": dict(self.policy_snapshot),
            "artifact_snapshot": dict(self.artifact_snapshot),
            "verification_snapshot": dict(self.verification_snapshot),
            "no_download_planned": self.no_download_planned,
            "no_network_planned": self.no_network_planned,
            "no_execution_performed": self.no_execution_performed,
            "worker_required": self.worker_required, "worker_available": self.worker_available,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RuntimeExecutionPlan":
        checks = [RuntimeExecutionPlanCheck.from_dict(c) for c in d.get("checks", [])]
        return cls(
            plan_id=str(d.get("plan_id", "")), marketplace_agent_id=str(d.get("marketplace_agent_id", "")),
            tenant_id=str(d.get("tenant_id", "")), user_id=d.get("user_id"),
            developer_id=str(d.get("developer_id", "")), submission_id=d.get("submission_id"),
            runtime_binding_id=d.get("runtime_binding_id"), adapter_id=d.get("adapter_id"),
            adapter_type=d.get("adapter_type"), sandbox_policy_id=d.get("sandbox_policy_id"),
            artifact_id=d.get("artifact_id"), verification_id=d.get("verification_id"),
            execution_mode=str(d.get("execution_mode", RuntimeExecutionMode.SANDBOX_RESERVED)),
            plan_status=str(d.get("plan_status", RuntimeExecutionPlanStatus.DRAFT)),
            dispatch_status=str(d.get("dispatch_status", RuntimeDispatchStatus.RESERVED_FOR_STEP24E)),
            decision=str(d.get("decision", RuntimePlanDecision.RESERVED_ONLY)),
            risk_level=str(d.get("risk_level", RuntimeExecutionRiskLevel.UNKNOWN)),
            checks=checks, warnings_count=int(d.get("warnings_count", 0)),
            errors_count=int(d.get("errors_count", 0)), blockers_count=int(d.get("blockers_count", 0)),
            input_payload_hash=d.get("input_payload_hash"),
            output_contract=dict(d.get("output_contract", {})),
            policy_snapshot=dict(d.get("policy_snapshot", {})),
            artifact_snapshot=dict(d.get("artifact_snapshot", {})),
            verification_snapshot=dict(d.get("verification_snapshot", {})),
            no_download_planned=bool(d.get("no_download_planned", True)),
            no_network_planned=bool(d.get("no_network_planned", True)),
            no_execution_performed=bool(d.get("no_execution_performed", True)),
            worker_required=bool(d.get("worker_required", False)),
            worker_available=bool(d.get("worker_available", False)),
            expires_at=_safe_dt(d.get("expires_at"), none_ok=True),
            created_by=d.get("created_by"), created_at=_safe_dt(d.get("created_at")),
            updated_at=_safe_dt(d.get("updated_at")), metadata=dict(d.get("metadata", {})),
        )


# ═══════════════════════════════════════════
# RuntimeExecutionPlanAuditEvent
# ═══════════════════════════════════════════

@dataclass
class RuntimeExecutionPlanAuditEvent:
    event_id: str = field(default_factory=lambda: f"rtexevt_{uuid4().hex[:16]}")
    plan_id: str = ""
    tenant_id: str = ""
    event_type: str = ""
    actor_id: str | None = None
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id, "plan_id": self.plan_id, "tenant_id": self.tenant_id,
            "event_type": self.event_type, "actor_id": self.actor_id, "message": self.message,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RuntimeExecutionPlanAuditEvent":
        return cls(event_id=str(d.get("event_id", "")), plan_id=str(d.get("plan_id", "")),
                   tenant_id=str(d.get("tenant_id", "")), event_type=str(d.get("event_type", "")),
                   actor_id=d.get("actor_id"), message=str(d.get("message", "")),
                   metadata=dict(d.get("metadata", {})), created_at=_safe_dt(d.get("created_at")))


# ═══════════════════════════════════════════
# Error Classes
# ═══════════════════════════════════════════

class RuntimeExecutionPlanError(Exception): pass
class RuntimeExecutionPlanNotFoundError(RuntimeExecutionPlanError): pass
class RuntimeExecutionPlanAlreadyExistsError(RuntimeExecutionPlanError): pass
class RuntimeExecutionPlanStateError(RuntimeExecutionPlanError): pass
class RuntimeExecutionPlanBlockedError(RuntimeExecutionPlanError): pass


# ═══════════════════════════════════════════
# Store Protocol
# ═══════════════════════════════════════════

@runtime_checkable
class RuntimeExecutionPlanStore(Protocol):
    def create_plan(self, plan: RuntimeExecutionPlan) -> RuntimeExecutionPlan: ...
    def get_plan(self, plan_id: str) -> RuntimeExecutionPlan | None: ...
    def list_plans(self, *, tenant_id: str = "", marketplace_agent_id: str = "", developer_id: str = "",
                   status: str = "", decision: str = "") -> list[RuntimeExecutionPlan]: ...
    def update_plan(self, plan: RuntimeExecutionPlan) -> RuntimeExecutionPlan: ...
    def set_plan_status(self, plan_id: str, status: str, actor_id: str | None = None, reason: str | None = None) -> RuntimeExecutionPlan: ...
    def cancel_plan(self, plan_id: str, actor_id: str | None = None, reason: str | None = None) -> RuntimeExecutionPlan: ...
    def expire_plan(self, plan_id: str, actor_id: str | None = None, reason: str | None = None) -> RuntimeExecutionPlan: ...
    def count_plans(self, *, tenant_id: str = "", status: str = "", decision: str = "") -> int: ...
    def add_audit_event(self, event: RuntimeExecutionPlanAuditEvent) -> RuntimeExecutionPlanAuditEvent: ...
    def list_audit_events(self, plan_id: str) -> list[RuntimeExecutionPlanAuditEvent]: ...


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════

def _safe_dt(raw: str | None, none_ok: bool = False) -> datetime | None:
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError): return None if none_ok else datetime.now(timezone.utc)
