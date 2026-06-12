"""Runtime Execution Gate — admin-gated API boundary domain model。

Step 24-H: DISABLED/PLAN_ONLY/DRY_RUN_ONLY modes, is_execution_allowed()=False。
不下载/不执行/不联网/不 worker/不 queue。"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

class RuntimeExecutionGateStatus(StrEnum):
    DISABLED="disabled"; PLAN_ONLY="plan_only"; DRY_RUN_ONLY="dry_run_only"
    RESERVED_FOR_SANDBOX="reserved_for_sandbox"; BLOCKED="blocked"

class RuntimeExecutionGateDecision(StrEnum):
    BLOCKED_DISABLED="blocked_disabled"; BLOCKED_ADMIN_REQUIRED="blocked_admin_required"
    BLOCKED_NOT_DISPATCHABLE="blocked_not_dispatchable"; BLOCKED_WORKER_UNAVAILABLE="blocked_worker_unavailable"
    PLAN_CREATED="plan_created"; PREVIEW_ONLY="preview_only"
    DRY_RUN_PREVIEW_RESERVED="dry_run_preview_reserved"; FAIL_CLOSED="fail_closed"

class RuntimeExecutionApiMode(StrEnum):
    ADMIN_PLAN_ONLY="admin_plan_only"; ADMIN_PREVIEW_ONLY="admin_preview_only"
    USER_EXECUTE_DISABLED="user_execute_disabled"; API_KEY_EXECUTE_DISABLED="api_key_execute_disabled"

class RuntimeExecutionGateCheckType(StrEnum):
    ADMIN_AUTH_REQUIRED="admin_auth_required"; API_KEY_FORBIDDEN_FOR_ADMIN_GATE="api_key_forbidden_for_admin_gate"
    USER_EXECUTE_DISABLED="user_execute_disabled"; PLAN_ONLY_MODE="plan_only_mode"
    PLAN_CREATED_ONLY="plan_created_only"; PLAN_NOT_DISPATCHABLE="plan_not_dispatchable"
    WORKER_DISABLED="worker_disabled"; DRY_RUN_ONLY_IF_EXPLICIT="dry_run_only_if_explicit"
    NO_PACKAGE_DOWNLOAD="no_package_download"; NO_PACKAGE_EXECUTION="no_package_execution"
    NO_ENTRYPOINT_EXECUTION="no_entrypoint_execution"; NO_NETWORK_USED="no_network_used"
    NO_SUBPROCESS_USED="no_subprocess_used"; NO_CONTAINER_USED="no_container_used"
    NO_QUEUE_CREATED="no_queue_created"; NO_JOB_DISPATCHED="no_job_dispatched"
    NO_AGENT_RUNTIME_USED="no_agent_runtime_used"; NO_AGENT_REGISTRY_USED="no_agent_registry_used"
    FAIL_CLOSED="fail_closed"

class RuntimeExecutionGateCheckStatus(StrEnum):
    PASSED="passed"; WARNING="warning"; BLOCKED="blocked"; FAILED="failed"; SKIPPED="skipped"

class RuntimeExecutionGateSeverity(StrEnum):
    INFO="info"; WARNING="warning"; ERROR="error"; BLOCKER="blocker"

@dataclass
class RuntimeExecutionGateCheck:
    check_id: str = field(default_factory=lambda: f"rtexgatechk_{uuid4().hex[:16]}")
    check_type: str = ""; status: str = RuntimeExecutionGateCheckStatus.PASSED
    severity: str = RuntimeExecutionGateSeverity.INFO; message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"check_id":self.check_id,"check_type":self.check_type,"status":self.status,"severity":self.severity,"message":self.message,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(check_id=str(d.get("check_id","")),check_type=str(d.get("check_type","")),status=str(d.get("status","passed")),severity=str(d.get("severity","info")),message=str(d.get("message","")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

@dataclass
class RuntimeExecutionGateResult:
    gate_id: str = field(default_factory=lambda: f"rtexgate_{uuid4().hex[:16]}")
    mode: str = RuntimeExecutionApiMode.ADMIN_PLAN_ONLY
    status: str = RuntimeExecutionGateStatus.DISABLED
    decision: str = RuntimeExecutionGateDecision.BLOCKED_DISABLED
    plan_id: str | None = None; marketplace_agent_id: str | None = None
    tenant_id: str | None = None; actor_id: str | None = None
    checks: list[RuntimeExecutionGateCheck] = field(default_factory=list)
    warnings_count: int = 0; errors_count: int = 0; blockers_count: int = 0
    response_payload: dict[str, Any] = field(default_factory=dict)
    no_execution_performed: bool = True; no_download_used: bool = True
    no_network_used: bool = True; no_subprocess_used: bool = True; no_container_used: bool = True
    no_queue_created: bool = True; no_job_dispatched: bool = True
    no_agent_runtime_used: bool = True; no_agent_registry_used: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_check(self,c): self.checks.append(c); self._recount()
    def _recount(self):
        self.warnings_count=sum(1 for c in self.checks if c.status==RuntimeExecutionGateCheckStatus.WARNING)
        self.errors_count=sum(1 for c in self.checks if c.status==RuntimeExecutionGateCheckStatus.FAILED)
        self.blockers_count=sum(1 for c in self.checks if c.status==RuntimeExecutionGateCheckStatus.BLOCKED)
    def calculate_status(self):
        self._recount()
        if self.blockers_count>0: self.status=RuntimeExecutionGateStatus.BLOCKED; self.decision=RuntimeExecutionGateDecision.BLOCKED_DISABLED
        elif self.errors_count>0: self.status=RuntimeExecutionGateStatus.BLOCKED
        elif self.warnings_count>0: self.status=RuntimeExecutionGateStatus.PLAN_ONLY; self.decision=RuntimeExecutionGateDecision.PLAN_CREATED
        else: self.status=RuntimeExecutionGateStatus.PLAN_ONLY; self.decision=RuntimeExecutionGateDecision.PLAN_CREATED
    def is_execution_allowed(self) -> bool:
        """Step 24-H: always False。no real execution。"""
        return False

    def to_dict(self): return {"gate_id":self.gate_id,"mode":self.mode,"status":self.status,"decision":self.decision,"plan_id":self.plan_id,"marketplace_agent_id":self.marketplace_agent_id,"tenant_id":self.tenant_id,"actor_id":self.actor_id,"checks":[c.to_dict() for c in self.checks],"warnings_count":self.warnings_count,"errors_count":self.errors_count,"blockers_count":self.blockers_count,"response_payload":dict(self.response_payload),"no_execution_performed":self.no_execution_performed,"no_download_used":self.no_download_used,"no_network_used":self.no_network_used,"no_subprocess_used":self.no_subprocess_used,"no_container_used":self.no_container_used,"no_queue_created":self.no_queue_created,"no_job_dispatched":self.no_job_dispatched,"no_agent_runtime_used":self.no_agent_runtime_used,"no_agent_registry_used":self.no_agent_registry_used,"created_at":self.created_at.isoformat() if self.created_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d):
        checks=[RuntimeExecutionGateCheck.from_dict(c) for c in d.get("checks",[])]
        return cls(gate_id=str(d.get("gate_id","")),mode=str(d.get("mode","admin_plan_only")),status=str(d.get("status","disabled")),decision=str(d.get("decision","blocked_disabled")),plan_id=d.get("plan_id"),marketplace_agent_id=d.get("marketplace_agent_id"),tenant_id=d.get("tenant_id"),actor_id=d.get("actor_id"),checks=checks,warnings_count=int(d.get("warnings_count",0)),errors_count=int(d.get("errors_count",0)),blockers_count=int(d.get("blockers_count",0)),response_payload=dict(d.get("response_payload",{})),no_execution_performed=bool(d.get("no_execution_performed",True)),no_download_used=bool(d.get("no_download_used",True)),no_network_used=bool(d.get("no_network_used",True)),no_subprocess_used=bool(d.get("no_subprocess_used",True)),no_container_used=bool(d.get("no_container_used",True)),no_queue_created=bool(d.get("no_queue_created",True)),no_job_dispatched=bool(d.get("no_job_dispatched",True)),no_agent_runtime_used=bool(d.get("no_agent_runtime_used",True)),no_agent_registry_used=bool(d.get("no_agent_registry_used",True)),created_at=_safe_dt(d.get("created_at")),metadata=dict(d.get("metadata",{})))

class RuntimeExecutionGateError(Exception): pass
class RuntimeExecutionGateBlockedError(RuntimeExecutionGateError): pass
class RuntimeExecutionGateForbiddenError(RuntimeExecutionGateError): pass

def _safe_dt(raw,none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
