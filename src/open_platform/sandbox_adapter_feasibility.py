"""Sandbox Adapter Feasibility Domain Model — container/microVM/WASM/subprocess viability assessment.

Step 25-C: 只做 feasibility spike。不启动任何 runtime。不调用 docker。不 import docker SDK。
is_approved_for_execution() = can_start_container() = can_start_microvm() = can_dispatch() = False。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

# ═══════════ Enums ═══════════

class SandboxIsolationTechnology(StrEnum):
    NO_EXECUTION_BASELINE="no_execution_baseline"; DISABLED_WORKER="disabled_worker"
    LOCAL_DRY_RUN="local_dry_run"; SUBPROCESS_REJECTED="subprocess_rejected"
    CONTAINER="container"; ROOTLESS_CONTAINER="rootless_container"
    REMOTE_ISOLATED_WORKER="remote_isolated_worker"; WASM="wasm"
    MICROVM="microvm"; MANAGED_CLOUD_SANDBOX="managed_cloud_sandbox"

class FeasibilityStatus(StrEnum):
    NOT_ASSESSED="not_assessed"; ASSESSED="assessed"; CANDIDATE="candidate"
    REJECTED="rejected"; RESERVED_FOR_PROTOTYPE="reserved_for_prototype"
    BLOCKED="blocked"; FAIL_CLOSED="fail_closed"

class FeasibilityDecision(StrEnum):
    ACCEPT_AS_CANDIDATE="accept_as_candidate"; REJECT_FOR_UNTRUSTED_CODE="reject_for_untrusted_code"
    RESERVE_FOR_FUTURE_SPIKE="reserve_for_future_spike"
    BLOCK_UNTIL_HARD_GATES="block_until_hard_gates"; FAIL_CLOSED="fail_closed"

class IsolationStrength(StrEnum):
    NONE="none"; LOW="low"; MEDIUM="medium"; HIGH="high"; VERY_HIGH="very_high"; UNKNOWN="unknown"

class ProductionFit(StrEnum):
    NOT_FIT="not_fit"; LIMITED="limited"; GOOD="good"; STRONG="strong"; UNKNOWN="unknown"

class FeasibilityRiskLevel(StrEnum):
    LOW="low"; MEDIUM="medium"; HIGH="high"; CRITICAL="critical"; UNKNOWN="unknown"

class FeasibilityCheckType(StrEnum):
    NO_EXECUTION_PERFORMED="no_execution_performed"; NO_DOCKER_STARTED="no_docker_started"
    NO_CONTAINER_STARTED="no_container_started"; NO_MICROVM_STARTED="no_microvm_started"
    NO_WASM_RUNTIME_STARTED="no_wasm_runtime_started"; NO_SUBPROCESS_STARTED="no_subprocess_started"
    NO_NETWORK_USED="no_network_used"; NO_PACKAGE_DOWNLOADED="no_package_downloaded"
    NO_QUEUE_CREATED="no_queue_created"; NO_JOB_DISPATCHED="no_job_dispatched"
    TECHNOLOGY_CLASSIFIED="technology_classified"; ISOLATION_STRENGTH_ASSESSED="isolation_strength_assessed"
    PRODUCTION_FIT_ASSESSED="production_fit_assessed"; WINDOWS_DEV_FIT_ASSESSED="windows_dev_fit_assessed"
    OPERATIONAL_COMPLEXITY_ASSESSED="operational_complexity_assessed"
    SECURITY_RISK_ASSESSED="security_risk_assessed"; HARD_GATES_IDENTIFIED="hard_gates_identified"
    SUBPROCESS_REJECTED_FOR_UNTRUSTED_CODE="subprocess_rejected_for_untrusted_code"
    ROOTLESS_CONTAINER_CANDIDATE="rootless_container_candidate"
    MICROVM_RESERVED_FOR_PRODUCTION="microvm_reserved_for_production"
    FAIL_CLOSED_ON_UNKNOWN="fail_closed_on_unknown"

class FeasibilityCheckStatus(StrEnum):
    PASSED="passed"; WARNING="warning"; BLOCKED="blocked"; FAILED="failed"; SKIPPED="skipped"

class FeasibilityCheckSeverity(StrEnum):
    INFO="info"; WARNING="warning"; ERROR="error"; BLOCKER="blocker"

# ═══════════ FeasibilityCheck ═══════════

@dataclass
class FeasibilityCheck:
    check_id: str = field(default_factory=lambda: f"fscheck_{uuid4().hex[:16]}")
    check_type: str = ""; status: str = FeasibilityCheckStatus.PASSED
    severity: str = FeasibilityCheckSeverity.INFO; message: str = ""
    metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"check_id":self.check_id,"check_type":self.check_type,"status":self.status,"severity":self.severity,"message":self.message,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(check_id=str(d.get("check_id","")),check_type=str(d.get("check_type","")),status=str(d.get("status","passed")),severity=str(d.get("severity","info")),message=str(d.get("message","")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

# ═══════════ AdapterCapabilityProfile ═══════════

@dataclass
class AdapterCapabilityProfile:
    profile_id: str = field(default_factory=lambda: f"fsprof_{uuid4().hex[:16]}")
    technology: str = SandboxIsolationTechnology.NO_EXECUTION_BASELINE
    name: str = ""; isolation_strength: str = IsolationStrength.UNKNOWN
    production_fit: str = ProductionFit.UNKNOWN; windows_dev_fit: str = ProductionFit.UNKNOWN
    operational_complexity: str = FeasibilityRiskLevel.UNKNOWN
    security_risk: str = FeasibilityRiskLevel.UNKNOWN
    supports_network_policy: bool = False; supports_filesystem_policy: bool = False
    supports_secret_isolation: bool = False; supports_resource_limits: bool = False
    supports_kill_switch: bool = False; supports_audit: bool = False
    supports_tenant_isolation: bool = False; supports_rootless: bool = False
    requires_linux_host: bool = False; requires_privileged_host_access: bool = False
    requires_docker_socket: bool = False; requires_remote_infra: bool = False
    execution_enabled: bool = False; prototype_allowed: bool = False
    recommendation: str = FeasibilityDecision.FAIL_CLOSED
    known_risks: list[str] = field(default_factory=list)
    required_hard_gates: list[str] = field(default_factory=list)
    metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"profile_id":self.profile_id,"technology":self.technology,"name":self.name,"isolation_strength":self.isolation_strength,"production_fit":self.production_fit,"windows_dev_fit":self.windows_dev_fit,"operational_complexity":self.operational_complexity,"security_risk":self.security_risk,"supports_network_policy":self.supports_network_policy,"supports_filesystem_policy":self.supports_filesystem_policy,"supports_secret_isolation":self.supports_secret_isolation,"supports_resource_limits":self.supports_resource_limits,"supports_kill_switch":self.supports_kill_switch,"supports_audit":self.supports_audit,"supports_tenant_isolation":self.supports_tenant_isolation,"supports_rootless":self.supports_rootless,"requires_linux_host":self.requires_linux_host,"requires_privileged_host_access":self.requires_privileged_host_access,"requires_docker_socket":self.requires_docker_socket,"requires_remote_infra":self.requires_remote_infra,"execution_enabled":self.execution_enabled,"prototype_allowed":self.prototype_allowed,"recommendation":self.recommendation,"known_risks":list(self.known_risks),"required_hard_gates":list(self.required_hard_gates),"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(profile_id=str(d.get("profile_id","")),technology=str(d.get("technology","no_execution_baseline")),name=str(d.get("name","")),isolation_strength=str(d.get("isolation_strength","unknown")),production_fit=str(d.get("production_fit","unknown")),windows_dev_fit=str(d.get("windows_dev_fit","unknown")),operational_complexity=str(d.get("operational_complexity","unknown")),security_risk=str(d.get("security_risk","unknown")),supports_network_policy=bool(d.get("supports_network_policy",False)),supports_filesystem_policy=bool(d.get("supports_filesystem_policy",False)),supports_secret_isolation=bool(d.get("supports_secret_isolation",False)),supports_resource_limits=bool(d.get("supports_resource_limits",False)),supports_kill_switch=bool(d.get("supports_kill_switch",False)),supports_audit=bool(d.get("supports_audit",False)),supports_tenant_isolation=bool(d.get("supports_tenant_isolation",False)),supports_rootless=bool(d.get("supports_rootless",False)),requires_linux_host=bool(d.get("requires_linux_host",False)),requires_privileged_host_access=bool(d.get("requires_privileged_host_access",False)),requires_docker_socket=bool(d.get("requires_docker_socket",False)),requires_remote_infra=bool(d.get("requires_remote_infra",False)),execution_enabled=bool(d.get("execution_enabled",False)),prototype_allowed=bool(d.get("prototype_allowed",False)),recommendation=str(d.get("recommendation","fail_closed")),known_risks=list(d.get("known_risks",[])),required_hard_gates=list(d.get("required_hard_gates",[])),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

# ═══════════ SandboxAdapterDescriptor ═══════════

@dataclass
class SandboxAdapterDescriptor:
    adapter_id: str = field(default_factory=lambda: f"fsadapter_{uuid4().hex[:16]}")
    technology: str = SandboxIsolationTechnology.NO_EXECUTION_BASELINE
    adapter_name: str = ""; adapter_status: str = FeasibilityStatus.BLOCKED
    execution_enabled: bool = False; worker_enabled: bool = False
    queue_enabled: bool = False; dispatch_enabled: bool = False
    download_enabled: bool = False; network_enabled: bool = False
    container_start_enabled: bool = False; microvm_start_enabled: bool = False
    subprocess_enabled: bool = False
    capability_profile: dict[str,Any] = field(default_factory=dict)
    safety_notes: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str,Any] = field(default_factory=dict)

    def is_executable(self) -> bool: return False
    def can_start_container(self) -> bool: return False
    def can_start_microvm(self) -> bool: return False
    def can_dispatch(self) -> bool: return False

    def to_dict(self): return {"adapter_id":self.adapter_id,"technology":self.technology,"adapter_name":self.adapter_name,"adapter_status":self.adapter_status,"execution_enabled":self.execution_enabled,"worker_enabled":self.worker_enabled,"queue_enabled":self.queue_enabled,"dispatch_enabled":self.dispatch_enabled,"download_enabled":self.download_enabled,"network_enabled":self.network_enabled,"container_start_enabled":self.container_start_enabled,"microvm_start_enabled":self.microvm_start_enabled,"subprocess_enabled":self.subprocess_enabled,"capability_profile":dict(self.capability_profile),"safety_notes":list(self.safety_notes),"created_at":self.created_at.isoformat() if self.created_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): return cls(adapter_id=str(d.get("adapter_id","")),technology=str(d.get("technology","no_execution_baseline")),adapter_name=str(d.get("adapter_name","")),adapter_status=str(d.get("adapter_status","blocked")),execution_enabled=bool(d.get("execution_enabled",False)),worker_enabled=bool(d.get("worker_enabled",False)),queue_enabled=bool(d.get("queue_enabled",False)),dispatch_enabled=bool(d.get("dispatch_enabled",False)),download_enabled=bool(d.get("download_enabled",False)),network_enabled=bool(d.get("network_enabled",False)),container_start_enabled=bool(d.get("container_start_enabled",False)),microvm_start_enabled=bool(d.get("microvm_start_enabled",False)),subprocess_enabled=bool(d.get("subprocess_enabled",False)),capability_profile=dict(d.get("capability_profile",{})),safety_notes=list(d.get("safety_notes",[])),created_at=_safe_dt(d.get("created_at")),metadata=dict(d.get("metadata",{})))

# ═══════════ SandboxAdapterFeasibilityAssessment ═══════════

@dataclass
class SandboxAdapterFeasibilityAssessment:
    assessment_id: str = field(default_factory=lambda: f"fsassess_{uuid4().hex[:16]}")
    technology: str = SandboxIsolationTechnology.NO_EXECUTION_BASELINE
    status: str = FeasibilityStatus.NOT_ASSESSED; decision: str = FeasibilityDecision.FAIL_CLOSED
    profile: AdapterCapabilityProfile | None = None
    descriptor: SandboxAdapterDescriptor | None = None
    checks: list[FeasibilityCheck] = field(default_factory=list)
    warnings_count: int = 0; errors_count: int = 0; blockers_count: int = 0
    no_execution_performed: bool = True; no_container_started: bool = True
    no_microvm_started: bool = True; no_wasm_runtime_started: bool = True
    no_subprocess_started: bool = True; no_network_used: bool = True
    no_package_downloaded: bool = True; no_queue_created: bool = True
    no_job_dispatched: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str,Any] = field(default_factory=dict)

    def add_check(self,c): self.checks.append(c); self._recount()
    def _recount(self):
        self.warnings_count=sum(1 for c in self.checks if c.status==FeasibilityCheckStatus.WARNING)
        self.errors_count=sum(1 for c in self.checks if c.status==FeasibilityCheckStatus.FAILED)
        self.blockers_count=sum(1 for c in self.checks if c.status==FeasibilityCheckStatus.BLOCKED)
    def calculate_status(self):
        self._recount()
        if self.blockers_count>0: self.status=FeasibilityStatus.BLOCKED; self.decision=FeasibilityDecision.FAIL_CLOSED
        elif self.errors_count>0: self.status=FeasibilityStatus.REJECTED
        elif self.warnings_count>0: self.status=FeasibilityStatus.ASSESSED; self.decision=FeasibilityDecision.RESERVE_FOR_FUTURE_SPIKE
        else: self.status=FeasibilityStatus.ASSESSED; self.decision=FeasibilityDecision.ACCEPT_AS_CANDIDATE
    def is_approved_for_execution(self) -> bool: return False

    def to_dict(self): return {"assessment_id":self.assessment_id,"technology":self.technology,"status":self.status,"decision":self.decision,"profile":self.profile.to_dict() if self.profile else None,"descriptor":self.descriptor.to_dict() if self.descriptor else None,"checks":[c.to_dict() for c in self.checks],"warnings_count":self.warnings_count,"errors_count":self.errors_count,"blockers_count":self.blockers_count,"no_execution_performed":self.no_execution_performed,"no_container_started":self.no_container_started,"no_microvm_started":self.no_microvm_started,"no_wasm_runtime_started":self.no_wasm_runtime_started,"no_subprocess_started":self.no_subprocess_started,"no_network_used":self.no_network_used,"no_package_downloaded":self.no_package_downloaded,"no_queue_created":self.no_queue_created,"no_job_dispatched":self.no_job_dispatched,"created_at":self.created_at.isoformat() if self.created_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): checks=[FeasibilityCheck.from_dict(c) for c in d.get("checks",[])]; return cls(assessment_id=str(d.get("assessment_id","")),technology=str(d.get("technology","no_execution_baseline")),status=str(d.get("status","not_assessed")),decision=str(d.get("decision","fail_closed")),profile=AdapterCapabilityProfile.from_dict(d["profile"]) if isinstance(d.get("profile"),dict) else None,descriptor=SandboxAdapterDescriptor.from_dict(d["descriptor"]) if isinstance(d.get("descriptor"),dict) else None,checks=checks,warnings_count=int(d.get("warnings_count",0)),errors_count=int(d.get("errors_count",0)),blockers_count=int(d.get("blockers_count",0)),no_execution_performed=bool(d.get("no_execution_performed",True)),no_container_started=bool(d.get("no_container_started",True)),no_microvm_started=bool(d.get("no_microvm_started",True)),no_wasm_runtime_started=bool(d.get("no_wasm_runtime_started",True)),no_subprocess_started=bool(d.get("no_subprocess_started",True)),no_network_used=bool(d.get("no_network_used",True)),no_package_downloaded=bool(d.get("no_package_downloaded",True)),no_queue_created=bool(d.get("no_queue_created",True)),no_job_dispatched=bool(d.get("no_job_dispatched",True)),created_at=_safe_dt(d.get("created_at")),metadata=dict(d.get("metadata",{})))

# ═══════════ Errors ═══════════

class SandboxAdapterFeasibilityError(Exception): pass
class SandboxAdapterUnsupportedError(SandboxAdapterFeasibilityError): pass
class SandboxAdapterFailClosedError(SandboxAdapterFeasibilityError): pass

def _safe_dt(raw,none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
