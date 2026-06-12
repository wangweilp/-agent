"""Sandbox Worker Domain Model — 安全沙箱 Worker 接口。

Step 24-E:
- SandboxWorker Protocol — evaluate_request 不 execute
- SandboxWorkerRequest / Result — fail-closed safety flags
- build_worker_request_from_plan — plan → worker request helper

安全边界：
- 不 execute / dispatch / run
- 不 subprocess / container / network
- is_successful_execution() 始终 False
- DISABLED_STUB 是唯一实现的 worker type
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4


# ═══════════════ Enums ═══════════════

class SandboxWorkerType(StrEnum):
    DISABLED_STUB = "disabled_stub"
    LOCAL_DEV_DRY_RUN = "local_dev_dry_run"
    LOCAL_PROCESS_RESERVED = "local_process_reserved"
    CONTAINER_RESERVED = "container_reserved"
    WASM_RESERVED = "wasm_reserved"
    MICROVM_RESERVED = "microvm_reserved"

class SandboxWorkerAvailability(StrEnum):
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    AVAILABLE_RESERVED = "available_reserved"
    DEGRADED = "degraded"

class SandboxWorkerDecision(StrEnum):
    BLOCKED_DISABLED = "blocked_disabled"
    BLOCKED_PLAN_NOT_DISPATCHABLE = "blocked_plan_not_dispatchable"
    BLOCKED_POLICY_NOT_ENFORCEABLE = "blocked_policy_not_enforceable"
    BLOCKED_ARTIFACT_NOT_READY = "blocked_artifact_not_ready"
    RESERVED_ONLY = "reserved_only"
    FAIL_CLOSED = "fail_closed"

class SandboxWorkerResultStatus(StrEnum):
    BLOCKED = "blocked"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    RESERVED = "reserved"

class SandboxWorkerCheckType(StrEnum):
    WORKER_DISABLED = "worker_disabled"
    PLAN_NOT_DISPATCHABLE = "plan_not_dispatchable"
    PLAN_STATUS_NOT_PLANNED = "plan_status_not_planned"
    DISPATCH_STATUS_NOT_ALLOWED = "dispatch_status_not_allowed"
    EXECUTION_MODE_RESERVED = "execution_mode_reserved"
    POLICY_SNAPSHOT_PRESENT = "policy_snapshot_present"
    ARTIFACT_SNAPSHOT_PRESENT = "artifact_snapshot_present"
    VERIFICATION_SNAPSHOT_PRESENT = "verification_snapshot_present"
    NO_PACKAGE_DOWNLOAD = "no_package_download"
    NO_NETWORK_USED = "no_network_used"
    NO_EXECUTION_PERFORMED = "no_execution_performed"
    NO_SUBPROCESS_USED = "no_subprocess_used"
    NO_CONTAINER_USED = "no_container_used"
    NO_AGENT_RUNTIME_USED = "no_agent_runtime_used"
    NO_AGENT_REGISTRY_USED = "no_agent_registry_used"
    FAIL_CLOSED = "fail_closed"

class SandboxWorkerCheckStatus(StrEnum):
    PASSED = "passed"; WARNING = "warning"; BLOCKED = "blocked"; FAILED = "failed"; SKIPPED = "skipped"

class SandboxWorkerSeverity(StrEnum):
    INFO = "info"; WARNING = "warning"; ERROR = "error"; BLOCKER = "blocker"


# ═══════════════ SandboxWorkerCheck ═══════════════

@dataclass
class SandboxWorkerCheck:
    check_id: str = field(default_factory=lambda: f"sbxchk_{uuid4().hex[:16]}")
    check_type: str = ""
    status: str = SandboxWorkerCheckStatus.PASSED
    severity: str = SandboxWorkerSeverity.INFO
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {"check_id": self.check_id, "check_type": self.check_type,
                "status": self.status, "severity": self.severity,
                "message": self.message, "metadata": dict(self.metadata),
                "created_at": self.created_at.isoformat() if self.created_at else None}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxWorkerCheck":
        return cls(check_id=str(d.get("check_id", "")), check_type=str(d.get("check_type", "")),
                   status=str(d.get("status", SandboxWorkerCheckStatus.PASSED)),
                   severity=str(d.get("severity", SandboxWorkerSeverity.INFO)),
                   message=str(d.get("message", "")), metadata=dict(d.get("metadata", {})),
                   created_at=_safe_dt(d.get("created_at")))


# ═══════════════ SandboxWorkerRequest ═══════════════

@dataclass
class SandboxWorkerRequest:
    request_id: str = field(default_factory=lambda: f"sbxreq_{uuid4().hex[:16]}")
    plan_id: str = ""
    marketplace_agent_id: str = ""
    tenant_id: str = ""
    user_id: str | None = None
    developer_id: str = ""
    execution_mode: str = ""
    plan_status: str = ""
    dispatch_status: str = ""
    risk_level: str = ""
    input_payload_hash: str | None = None
    policy_snapshot: dict[str, Any] = field(default_factory=dict)
    artifact_snapshot: dict[str, Any] = field(default_factory=dict)
    verification_snapshot: dict[str, Any] = field(default_factory=dict)
    policy_config_snapshot: dict[str, Any] = field(default_factory=dict)
    worker_type: str = SandboxWorkerType.DISABLED_STUB
    requested_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        for f in ["policy_snapshot", "artifact_snapshot", "verification_snapshot", "policy_config_snapshot", "metadata"]:
            if not isinstance(getattr(self, f), dict): raise ValueError(f"{f} must be dict")

    @classmethod
    def from_plan(cls, plan: Any, requested_by: str | None = None,
                  worker_type: str = SandboxWorkerType.DISABLED_STUB) -> "SandboxWorkerRequest":
        return cls(
            plan_id=getattr(plan, "plan_id", ""),
            marketplace_agent_id=getattr(plan, "marketplace_agent_id", ""),
            tenant_id=getattr(plan, "tenant_id", ""),
            user_id=getattr(plan, "user_id", None),
            developer_id=getattr(plan, "developer_id", ""),
            execution_mode=getattr(plan, "execution_mode", ""),
            plan_status=getattr(plan, "plan_status", ""),
            dispatch_status=getattr(plan, "dispatch_status", ""),
            risk_level=getattr(plan, "risk_level", ""),
            input_payload_hash=getattr(plan, "input_payload_hash", None),
            policy_snapshot=dict(getattr(plan, "policy_snapshot", {}) or {}),
            artifact_snapshot=dict(getattr(plan, "artifact_snapshot", {}) or {}),
            verification_snapshot=dict(getattr(plan, "verification_snapshot", {}) or {}),
            policy_config_snapshot=dict(getattr(plan, "policy_config_snapshot", {}) or {}),
            worker_type=worker_type, requested_by=requested_by, metadata={},
        )

    def to_dict(self) -> dict[str, Any]:
        return {"request_id": self.request_id, "plan_id": self.plan_id,
                "marketplace_agent_id": self.marketplace_agent_id, "tenant_id": self.tenant_id,
                "user_id": self.user_id, "developer_id": self.developer_id,
                "execution_mode": self.execution_mode, "plan_status": self.plan_status,
                "dispatch_status": self.dispatch_status, "risk_level": self.risk_level,
                "input_payload_hash": self.input_payload_hash,
                "policy_snapshot": dict(self.policy_snapshot),
                "artifact_snapshot": dict(self.artifact_snapshot),
                "verification_snapshot": dict(self.verification_snapshot),
                "policy_config_snapshot": dict(self.policy_config_snapshot),
                "worker_type": self.worker_type, "requested_by": self.requested_by,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxWorkerRequest":
        return cls(request_id=str(d.get("request_id", "")), plan_id=str(d.get("plan_id", "")),
                   marketplace_agent_id=str(d.get("marketplace_agent_id", "")),
                   tenant_id=str(d.get("tenant_id", "")), user_id=d.get("user_id"),
                   developer_id=str(d.get("developer_id", "")),
                   execution_mode=str(d.get("execution_mode", "")),
                   plan_status=str(d.get("plan_status", "")),
                   dispatch_status=str(d.get("dispatch_status", "")),
                   risk_level=str(d.get("risk_level", "")),
                   input_payload_hash=d.get("input_payload_hash"),
                   policy_snapshot=dict(d.get("policy_snapshot", {})),
                   artifact_snapshot=dict(d.get("artifact_snapshot", {})),
                   verification_snapshot=dict(d.get("verification_snapshot", {})),
                   policy_config_snapshot=dict(d.get("policy_config_snapshot", {})),
                   worker_type=str(d.get("worker_type", SandboxWorkerType.DISABLED_STUB)),
                   requested_by=d.get("requested_by"), created_at=_safe_dt(d.get("created_at")),
                   metadata=dict(d.get("metadata", {})))


# ═══════════════ SandboxWorkerResult ═══════════════

@dataclass
class SandboxWorkerResult:
    result_id: str = field(default_factory=lambda: f"sbxres_{uuid4().hex[:16]}")
    request_id: str = ""
    plan_id: str = ""
    tenant_id: str = ""
    worker_type: str = SandboxWorkerType.DISABLED_STUB
    availability: str = SandboxWorkerAvailability.DISABLED
    status: str = SandboxWorkerResultStatus.BLOCKED
    decision: str = SandboxWorkerDecision.BLOCKED_DISABLED
    checks: list[SandboxWorkerCheck] = field(default_factory=list)
    warnings_count: int = 0; errors_count: int = 0; blockers_count: int = 0
    output_json: dict[str, Any] = field(default_factory=dict)
    output_truncated: bool = False
    stdout_text: str | None = None; stderr_text: str | None = None; exit_code: int | None = None
    duration_ms: int = 0; memory_peak_mb: int | None = None
    no_download_used: bool = True; no_network_used: bool = True
    no_execution_performed: bool = True; no_subprocess_used: bool = True
    no_container_used: bool = True; no_agent_runtime_used: bool = True
    no_agent_registry_used: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_check(self, c: SandboxWorkerCheck) -> None: self.checks.append(c); self._recount()
    def _recount(self):
        self.warnings_count = sum(1 for c in self.checks if c.status == SandboxWorkerCheckStatus.WARNING)
        self.errors_count = sum(1 for c in self.checks if c.status == SandboxWorkerCheckStatus.FAILED)
        self.blockers_count = sum(1 for c in self.checks if c.status == SandboxWorkerCheckStatus.BLOCKED)

    def calculate_status(self):
        self._recount()
        if self.blockers_count > 0: self.status = SandboxWorkerResultStatus.BLOCKED; self.decision = SandboxWorkerDecision.BLOCKED_DISABLED
        elif self.errors_count > 0: self.status = SandboxWorkerResultStatus.REJECTED
        elif self.warnings_count > 0: self.status = SandboxWorkerResultStatus.RESERVED
        else: self.status = SandboxWorkerResultStatus.SKIPPED

    def is_successful_execution(self) -> bool:
        """Step 24-E: 始终返回 False。no real execution。"""
        return False

    def to_dict(self) -> dict[str, Any]:
        return {"result_id": self.result_id, "request_id": self.request_id, "plan_id": self.plan_id,
                "tenant_id": self.tenant_id, "worker_type": self.worker_type,
                "availability": self.availability, "status": self.status, "decision": self.decision,
                "checks": [c.to_dict() for c in self.checks],
                "warnings_count": self.warnings_count, "errors_count": self.errors_count,
                "blockers_count": self.blockers_count,
                "output_json": dict(self.output_json), "output_truncated": self.output_truncated,
                "stdout_text": self.stdout_text, "stderr_text": self.stderr_text,
                "exit_code": self.exit_code, "duration_ms": self.duration_ms,
                "memory_peak_mb": self.memory_peak_mb,
                "no_download_used": self.no_download_used, "no_network_used": self.no_network_used,
                "no_execution_performed": self.no_execution_performed,
                "no_subprocess_used": self.no_subprocess_used, "no_container_used": self.no_container_used,
                "no_agent_runtime_used": self.no_agent_runtime_used,
                "no_agent_registry_used": self.no_agent_registry_used,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "completed_at": self.completed_at.isoformat() if self.completed_at else None,
                "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxWorkerResult":
        checks = [SandboxWorkerCheck.from_dict(c) for c in d.get("checks", [])]
        return cls(result_id=str(d.get("result_id", "")), request_id=str(d.get("request_id", "")),
                   plan_id=str(d.get("plan_id", "")), tenant_id=str(d.get("tenant_id", "")),
                   worker_type=str(d.get("worker_type", SandboxWorkerType.DISABLED_STUB)),
                   availability=str(d.get("availability", SandboxWorkerAvailability.DISABLED)),
                   status=str(d.get("status", SandboxWorkerResultStatus.BLOCKED)),
                   decision=str(d.get("decision", SandboxWorkerDecision.BLOCKED_DISABLED)),
                   checks=checks, warnings_count=int(d.get("warnings_count", 0)),
                   errors_count=int(d.get("errors_count", 0)), blockers_count=int(d.get("blockers_count", 0)),
                   output_json=dict(d.get("output_json", {})),
                   output_truncated=bool(d.get("output_truncated", False)),
                   stdout_text=d.get("stdout_text"), stderr_text=d.get("stderr_text"),
                   exit_code=d.get("exit_code"), duration_ms=int(d.get("duration_ms", 0)),
                   memory_peak_mb=d.get("memory_peak_mb"),
                   no_download_used=bool(d.get("no_download_used", True)),
                   no_network_used=bool(d.get("no_network_used", True)),
                   no_execution_performed=bool(d.get("no_execution_performed", True)),
                   no_subprocess_used=bool(d.get("no_subprocess_used", True)),
                   no_container_used=bool(d.get("no_container_used", True)),
                   no_agent_runtime_used=bool(d.get("no_agent_runtime_used", True)),
                   no_agent_registry_used=bool(d.get("no_agent_registry_used", True)),
                   created_at=_safe_dt(d.get("created_at")),
                   completed_at=_safe_dt(d.get("completed_at"), none_ok=True),
                   metadata=dict(d.get("metadata", {})))


# ═══════════════ Errors ═══════════════

class SandboxWorkerError(Exception): pass
class SandboxWorkerDisabledError(SandboxWorkerError): pass
class SandboxWorkerRequestError(SandboxWorkerError): pass
class SandboxWorkerPolicyError(SandboxWorkerError): pass
class SandboxWorkerUnavailableError(SandboxWorkerError): pass


# ═══════════════ Protocol ═══════════════

class SandboxWorker(Protocol):
    """Sandbox Worker 协议。方法名 evaluate_request，不是 execute/run/dispatch。"""
    def get_worker_type(self) -> str: ...
    def get_availability(self) -> str: ...
    def evaluate_request(self, request: SandboxWorkerRequest) -> SandboxWorkerResult: ...


# ═══════════════ Plan → WorkerRequest Helper ═══════════════

def build_worker_request_from_plan(
    plan: Any,
    requested_by: str | None = None,
    worker_type: str = SandboxWorkerType.DISABLED_STUB,
) -> SandboxWorkerRequest:
    """从 RuntimeExecutionPlan 构建 SandboxWorkerRequest。不 dispatch, 不修改 plan。"""
    return SandboxWorkerRequest.from_plan(plan, requested_by=requested_by, worker_type=worker_type)


# ═══════════════ Helpers ═══════════════

def _safe_dt(raw, none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
