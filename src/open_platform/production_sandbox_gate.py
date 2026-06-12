"""Production Sandbox Implementation Gate — readiness assessment, never enables execution.

Step 26-A: assess readiness for controlled implementation spikes.
third_party_execution_allowed/package_execution_allowed/runtime_enabled = always False."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

class ProductionSandboxGateStatus(StrEnum):
    DRAFT="draft"; REQUESTED="requested"; EVALUATED="evaluated"
    PASS_READY_FOR_DESIGN_ONLY="pass_ready_for_design_only"
    PASS_READY_FOR_CONTROLLED_SPIKE="pass_ready_for_controlled_spike"
    BLOCKED="blocked"; REVIEW_REQUIRED="review_required"; FAIL_CLOSED="fail_closed"

class ProductionSandboxGateDecision(StrEnum):
    BLOCKED="blocked"; REVIEW_REQUIRED="review_required"
    READY_FOR_IMPLEMENTATION_GATE_ONLY="ready_for_implementation_gate_only"
    READY_FOR_CONTROLLED_SPIKE_ONLY="ready_for_controlled_spike_only"; FAIL_CLOSED="fail_closed"

class ProductionSandboxImplementationArea(StrEnum):
    FINAL_REGRESSION="final_regression"; CLAIM_BOUNDARY="claim_boundary"; EXECUTION_ENDPOINT="execution_endpoint"
    SANDBOX_EXECUTION_RECORD="sandbox_execution_record"; PACKAGE_DOWNLOAD="package_download"
    ARTIFACT_EXTRACTION="artifact_extraction"; WORKER_QUEUE="worker_queue"
    NETWORK_ENFORCEMENT="network_enforcement"; FILESYSTEM_ENFORCEMENT="filesystem_enforcement"
    SECRETS_ENFORCEMENT="secrets_enforcement"; TRUSTED_FIXTURE="trusted_fixture"; RED_TEAM="red_team"
    KILL_SWITCH="kill_switch"; INCIDENT_STORE="incident_store"; AUDIT_TRAIL="audit_trail"
    ROLLBACK="rollback"; OBSERVABILITY="observability"; TENANT_ISOLATION="tenant_isolation"
    RESOURCE_LIMITS="resource_limits"; CONTAINER_ISOLATION="container_isolation"
    MICROVM_ISOLATION="microvm_isolation"; SUPPLY_CHAIN_SCAN="supply_chain_scan"
    SIGNATURE_VERIFICATION="signature_verification"; STEP26_PLANNING="step26_planning"

class ProductionSandboxRequirementStatus(StrEnum):
    SATISFIED="satisfied"; PARTIALLY_SATISFIED="partially_satisfied"; MISSING="missing"
    BLOCKED="blocked"; NOT_APPLICABLE="not_applicable"; FAIL_CLOSED="fail_closed"

class ProductionSandboxRiskLevel(StrEnum):
    LOW="low"; MEDIUM="medium"; HIGH="high"; CRITICAL="critical"; UNKNOWN="unknown"

class ProductionSandboxCheckType(StrEnum):
    STEP25_FINAL_GATE_PASSED="step25_final_gate_passed"; STEP26_ADMISSION_PASSED="step26_admission_passed"
    EXECUTE_ENDPOINT_BLOCKED="execute_endpoint_blocked"; THIRD_PARTY_EXECUTION_DISABLED="third_party_execution_disabled"
    PACKAGE_EXECUTION_DISABLED="package_execution_disabled"; PACKAGE_DOWNLOAD_DISABLED="package_download_disabled"
    ARCHIVE_EXTRACTION_DISABLED="archive_extraction_disabled"; REAL_QUEUE_DISABLED="real_queue_disabled"
    DISPATCH_DISABLED="dispatch_disabled"; WORKER_DISABLED="worker_disabled"
    CONTAINER_RUNTIME_DISABLED="container_runtime_disabled"; MICROVM_RUNTIME_DISABLED="microvm_runtime_disabled"
    AGENT_RUNTIME_DISABLED="agent_runtime_disabled"; AGENT_REGISTRY_PROTECTED="agent_registry_protected"
    TRUSTED_FIXTURE_SEPARATE="trusted_fixture_separate"; RED_TEAM_GUARDS_PASSED="red_team_guards_passed"
    DOCS_HONESTY_PASSED="docs_honesty_passed"; STARTUP_GATE_PASSED="startup_gate_passed"
    KILL_SWITCH_MISSING="kill_switch_missing"; INCIDENT_STORE_MISSING="incident_store_missing"
    ROLLBACK_PLAN_REQUIRED="rollback_plan_required"; RESOURCE_LIMITS_REQUIRED="resource_limits_required"
    TENANT_ISOLATION_REQUIRED="tenant_isolation_required"; SUPPLY_CHAIN_SCAN_REQUIRED="supply_chain_scan_required"
    REAL_SIGNATURE_VERIFICATION_REQUIRED="real_signature_verification_required"
    NETWORK_ENFORCEMENT_REQUIRED="network_enforcement_required"; FILESYSTEM_ENFORCEMENT_REQUIRED="filesystem_enforcement_required"
    SECRETS_BROKER_REQUIRED="secrets_broker_required"; FAIL_CLOSED_ON_UNKNOWN="fail_closed_on_unknown"

class ProductionSandboxCheckStatus(StrEnum):
    PASSED="passed"; WARNING="warning"; BLOCKED="blocked"; FAILED="failed"; SKIPPED="skipped"

class ProductionSandboxSeverity(StrEnum):
    INFO="info"; WARNING="warning"; ERROR="error"; BLOCKER="blocker"

class ProductionSandboxGateAuditEventType(StrEnum):
    GATE_REQUEST_CREATED="gate_request_created"; REQUIREMENT_EVALUATED="requirement_evaluated"
    GATE_EVALUATED="gate_evaluated"; STATUS_CHANGED="status_changed"; DECISION_CHANGED="decision_changed"
    BLOCKED="blocked"; CANCELLED="cancelled"; EXPIRED="expired"; NOTE_ADDED="note_added"

class ProductionSandboxGateAuditSeverity(StrEnum):
    INFO="info"; WARNING="warning"; ERROR="error"; BLOCKER="blocker"

# ═══════ Requirement Builder ═══════
def build_step26a_default_requirements() -> list[ProductionSandboxRequirement]:
    return [
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.FINAL_REGRESSION, name="Step25 Final Gate", description="Step 25-K final regression passed", requirement_status=ProductionSandboxRequirementStatus.SATISFIED, is_hard_gate=True, is_required_before_execution=True, evidence_refs=["docs/STEP25K_FINAL_REGRESSION_GATE.md","2832 regression tests"]),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.RED_TEAM, name="Red-Team Guards", description="163 red-team escape guard tests passed", requirement_status=ProductionSandboxRequirementStatus.SATISFIED, is_hard_gate=True, is_required_before_execution=True, evidence_refs=["tests/test_open_platform/test_step25_red_team_escape_guards.py"]),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.CLAIM_BOUNDARY, name="Docs Honesty", description="No false claims in all STEP25 docs", requirement_status=ProductionSandboxRequirementStatus.SATISFIED, is_hard_gate=True, is_required_before_execution=True, evidence_refs=["docs/STEP25_CLAIM_BOUNDARY.md"]),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.EXECUTION_ENDPOINT, name="Execute Endpoint Blocked", description="/runtime/agents/{id}/execute remains blocked for third-party/package execution", requirement_status=ProductionSandboxRequirementStatus.SATISFIED, is_hard_gate=True, is_required_before_execution=True),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.SANDBOX_EXECUTION_RECORD, name="SandboxExecution Record audit-only", description="is_executable() always False", requirement_status=ProductionSandboxRequirementStatus.SATISFIED, is_hard_gate=True, is_required_before_execution=True),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.PACKAGE_DOWNLOAD, name="Package Download Disabled", description="is_downloadable() always False", requirement_status=ProductionSandboxRequirementStatus.SATISFIED, is_hard_gate=True, is_required_before_execution=True),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.ARTIFACT_EXTRACTION, name="Artifact Extraction Disabled", description="is_extraction_allowed() always False, is_materialized() always False", requirement_status=ProductionSandboxRequirementStatus.SATISFIED, is_hard_gate=True, is_required_before_execution=True),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.WORKER_QUEUE, name="Worker Queue Disabled", description="is_enqueue_allowed()/is_dispatch_allowed() always False", requirement_status=ProductionSandboxRequirementStatus.SATISFIED, is_hard_gate=True, is_required_before_execution=True),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.NETWORK_ENFORCEMENT, name="Network Enforcement Disabled", description="is_enforcement_active() always False", requirement_status=ProductionSandboxRequirementStatus.SATISFIED, is_hard_gate=True, is_required_before_execution=True),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.TRUSTED_FIXTURE, name="Trusted Fixture Separate", description="third_party_code_executed always False", requirement_status=ProductionSandboxRequirementStatus.SATISFIED, is_hard_gate=True, is_required_before_execution=True),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.KILL_SWITCH, name="Kill Switch", description="Runtime kill switch implementation missing", requirement_status=ProductionSandboxRequirementStatus.MISSING, risk_level=ProductionSandboxRiskLevel.CRITICAL, is_hard_gate=True, is_required_before_execution=True, blockers=["No kill switch runtime", "No agent/tenant/global kill switch store"]),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.INCIDENT_STORE, name="Incident Store", description="Runtime incident tracking store missing", requirement_status=ProductionSandboxRequirementStatus.MISSING, risk_level=ProductionSandboxRiskLevel.HIGH, is_hard_gate=True, is_required_before_execution=True, blockers=["No incident store"]),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.ROLLBACK, name="Rollback Plan", description="Execution rollback/undo plan required", requirement_status=ProductionSandboxRequirementStatus.MISSING, risk_level=ProductionSandboxRiskLevel.HIGH, is_hard_gate=False, is_required_before_execution=True),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.OBSERVABILITY, name="Observability", description="Runtime execution metrics/logs/traces required", requirement_status=ProductionSandboxRequirementStatus.MISSING, risk_level=ProductionSandboxRiskLevel.HIGH, is_hard_gate=False, is_required_before_execution=True),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.RESOURCE_LIMITS, name="Resource Limits", description="OS-level resource limits (CPU/memory/disk) required", requirement_status=ProductionSandboxRequirementStatus.MISSING, risk_level=ProductionSandboxRiskLevel.CRITICAL, is_hard_gate=True, is_required_before_execution=True, blockers=["No cgroup/container resource limits enforced"]),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.TENANT_ISOLATION, name="Tenant Isolation Runtime", description="Runtime tenant isolation (namespace, cgroup, or VM boundary) required", requirement_status=ProductionSandboxRequirementStatus.MISSING, risk_level=ProductionSandboxRiskLevel.CRITICAL, is_hard_gate=True, is_required_before_execution=True, blockers=["No runtime tenant isolation"]),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.SUPPLY_CHAIN_SCAN, name="Supply Chain Scan", description="Dependency/CVE scan required before package execution", requirement_status=ProductionSandboxRequirementStatus.MISSING, risk_level=ProductionSandboxRiskLevel.HIGH, is_hard_gate=True, is_required_before_execution=True, blockers=["No dependency scan"]),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.SIGNATURE_VERIFICATION, name="Real Signature Verification", description="Cryptographic signature verification (minisign/cosign/GPG) required", requirement_status=ProductionSandboxRequirementStatus.MISSING, risk_level=ProductionSandboxRiskLevel.HIGH, is_hard_gate=True, is_required_before_execution=True, blockers=["No real crypto verification"]),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.NETWORK_ENFORCEMENT, name="Real Network Enforcement", description="Container-level network enforcement required", requirement_status=ProductionSandboxRequirementStatus.MISSING, risk_level=ProductionSandboxRiskLevel.CRITICAL, is_hard_gate=True, is_required_before_execution=True, blockers=["No iptables/DNS/namespace enforcement"]),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.FILESYSTEM_ENFORCEMENT, name="Real Filesystem Enforcement", description="Container-level filesystem enforcement required", requirement_status=ProductionSandboxRequirementStatus.MISSING, risk_level=ProductionSandboxRiskLevel.CRITICAL, is_hard_gate=True, is_required_before_execution=True, blockers=["No mount/namespace enforcement"]),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.SECRETS_ENFORCEMENT, name="Secrets Broker", description="Runtime secrets broker required", requirement_status=ProductionSandboxRequirementStatus.MISSING, risk_level=ProductionSandboxRiskLevel.CRITICAL, is_hard_gate=True, is_required_before_execution=True, blockers=["No secrets broker"]),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.CONTAINER_ISOLATION, name="Container/Rootless Runtime", description="Rootless container adapter implementation required", requirement_status=ProductionSandboxRequirementStatus.MISSING, risk_level=ProductionSandboxRiskLevel.CRITICAL, is_hard_gate=True, is_required_before_execution=True, blockers=["No container adapter"]),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.MICROVM_ISOLATION, name="MicroVM Runtime", description="MicroVM adapter for Linux production (reserved)", requirement_status=ProductionSandboxRequirementStatus.NOT_APPLICABLE, risk_level=ProductionSandboxRiskLevel.HIGH, is_hard_gate=False, is_required_before_execution=False),
        ProductionSandboxRequirement(area=ProductionSandboxImplementationArea.STEP26_PLANNING, name="Operational Runbook", description="Emergency disable switch + rollback procedure + runbook required", requirement_status=ProductionSandboxRequirementStatus.MISSING, risk_level=ProductionSandboxRiskLevel.HIGH, is_hard_gate=True, is_required_before_execution=True, blockers=["No operational runbook"]),
    ]

# ═══════ Dataclasses ═══════
@dataclass
class ProductionSandboxRequirement:
    requirement_id: str = field(default_factory=lambda: f"psreq_{uuid4().hex[:16]}")
    area: str = ProductionSandboxImplementationArea.STEP26_PLANNING; name: str = ""; description: str = ""
    requirement_status: str = ProductionSandboxRequirementStatus.MISSING
    risk_level: str = ProductionSandboxRiskLevel.UNKNOWN; is_hard_gate: bool = False
    is_required_before_execution: bool = False; evidence_refs: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list); warnings: list[str] = field(default_factory=list)
    metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"requirement_id":self.requirement_id,"area":self.area,"name":self.name,"description":self.description,"requirement_status":self.requirement_status,"risk_level":self.risk_level,"is_hard_gate":self.is_hard_gate,"is_required_before_execution":self.is_required_before_execution,"evidence_refs":list(self.evidence_refs),"blockers":list(self.blockers),"warnings":list(self.warnings),"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(requirement_id=str(d.get("requirement_id","")),area=str(d.get("area","step26_planning")),name=str(d.get("name","")),description=str(d.get("description","")),requirement_status=str(d.get("requirement_status","missing")),risk_level=str(d.get("risk_level","unknown")),is_hard_gate=bool(d.get("is_hard_gate",False)),is_required_before_execution=bool(d.get("is_required_before_execution",False)),evidence_refs=list(d.get("evidence_refs",[])),blockers=list(d.get("blockers",[])),warnings=list(d.get("warnings",[])),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

@dataclass
class ProductionSandboxGateRequest:
    gate_request_id: str = field(default_factory=lambda: f"psgate_{uuid4().hex[:16]}"); tenant_id: str = ""
    requested_by: str|None=None
    step25_final_gate_snapshot: dict[str,Any] = field(default_factory=dict)
    red_team_snapshot: dict[str,Any] = field(default_factory=dict)
    docs_snapshot: dict[str,Any] = field(default_factory=dict)
    startup_snapshot: dict[str,Any] = field(default_factory=dict)
    runtime_endpoint_snapshot: dict[str,Any] = field(default_factory=dict)
    execution_snapshot: dict[str,Any] = field(default_factory=dict); queue_snapshot: dict[str,Any] = field(default_factory=dict)
    download_snapshot: dict[str,Any] = field(default_factory=dict); extraction_snapshot: dict[str,Any] = field(default_factory=dict)
    enforcement_snapshot: dict[str,Any] = field(default_factory=dict); trusted_fixture_snapshot: dict[str,Any] = field(default_factory=dict)
    gate_status: str = ProductionSandboxGateStatus.DRAFT; decision: str = ProductionSandboxGateDecision.BLOCKED
    risk_level: str = ProductionSandboxRiskLevel.UNKNOWN
    no_third_party_execution_enabled: bool = True; no_package_execution_enabled: bool = True
    no_download_enabled: bool = True; no_extraction_enabled: bool = True
    no_real_queue_enabled: bool = True; no_dispatch_enabled: bool = True; no_worker_enabled: bool = True
    no_container_enabled: bool = True; no_microvm_enabled: bool = True
    no_agent_runtime_enabled: bool = True; no_agent_registry_execution_enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cancelled_at: datetime|None=None; expired_at: datetime|None=None; expires_at: datetime|None=None
    metadata: dict[str,Any] = field(default_factory=dict)

    def is_third_party_execution_allowed(self) -> bool: return False
    def is_package_execution_allowed(self) -> bool: return False
    def is_runtime_enabled(self) -> bool: return False

    def to_dict(self): return {"gate_request_id":self.gate_request_id,"tenant_id":self.tenant_id,"requested_by":self.requested_by,"step25_final_gate_snapshot":dict(self.step25_final_gate_snapshot),"red_team_snapshot":dict(self.red_team_snapshot),"docs_snapshot":dict(self.docs_snapshot),"startup_snapshot":dict(self.startup_snapshot),"runtime_endpoint_snapshot":dict(self.runtime_endpoint_snapshot),"execution_snapshot":dict(self.execution_snapshot),"queue_snapshot":dict(self.queue_snapshot),"download_snapshot":dict(self.download_snapshot),"extraction_snapshot":dict(self.extraction_snapshot),"enforcement_snapshot":dict(self.enforcement_snapshot),"trusted_fixture_snapshot":dict(self.trusted_fixture_snapshot),"gate_status":self.gate_status,"decision":self.decision,"risk_level":self.risk_level,"no_third_party_execution_enabled":self.no_third_party_execution_enabled,"no_package_execution_enabled":self.no_package_execution_enabled,"no_download_enabled":self.no_download_enabled,"no_extraction_enabled":self.no_extraction_enabled,"no_real_queue_enabled":self.no_real_queue_enabled,"no_dispatch_enabled":self.no_dispatch_enabled,"no_worker_enabled":self.no_worker_enabled,"no_container_enabled":self.no_container_enabled,"no_microvm_enabled":self.no_microvm_enabled,"no_agent_runtime_enabled":self.no_agent_runtime_enabled,"no_agent_registry_execution_enabled":self.no_agent_registry_execution_enabled,"created_at":self.created_at.isoformat() if self.created_at else None,"updated_at":self.updated_at.isoformat() if self.updated_at else None,"cancelled_at":self.cancelled_at.isoformat() if self.cancelled_at else None,"expired_at":self.expired_at.isoformat() if self.expired_at else None,"expires_at":self.expires_at.isoformat() if self.expires_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): return cls(gate_request_id=str(d.get("gate_request_id","")),tenant_id=str(d.get("tenant_id","")),requested_by=d.get("requested_by"),step25_final_gate_snapshot=dict(d.get("step25_final_gate_snapshot",{})),red_team_snapshot=dict(d.get("red_team_snapshot",{})),docs_snapshot=dict(d.get("docs_snapshot",{})),startup_snapshot=dict(d.get("startup_snapshot",{})),runtime_endpoint_snapshot=dict(d.get("runtime_endpoint_snapshot",{})),execution_snapshot=dict(d.get("execution_snapshot",{})),queue_snapshot=dict(d.get("queue_snapshot",{})),download_snapshot=dict(d.get("download_snapshot",{})),extraction_snapshot=dict(d.get("extraction_snapshot",{})),enforcement_snapshot=dict(d.get("enforcement_snapshot",{})),trusted_fixture_snapshot=dict(d.get("trusted_fixture_snapshot",{})),gate_status=str(d.get("gate_status","draft")),decision=str(d.get("decision","blocked")),risk_level=str(d.get("risk_level","unknown")),no_third_party_execution_enabled=bool(d.get("no_third_party_execution_enabled",True)),no_package_execution_enabled=bool(d.get("no_package_execution_enabled",True)),no_download_enabled=bool(d.get("no_download_enabled",True)),no_extraction_enabled=bool(d.get("no_extraction_enabled",True)),no_real_queue_enabled=bool(d.get("no_real_queue_enabled",True)),no_dispatch_enabled=bool(d.get("no_dispatch_enabled",True)),no_worker_enabled=bool(d.get("no_worker_enabled",True)),no_container_enabled=bool(d.get("no_container_enabled",True)),no_microvm_enabled=bool(d.get("no_microvm_enabled",True)),no_agent_runtime_enabled=bool(d.get("no_agent_runtime_enabled",True)),no_agent_registry_execution_enabled=bool(d.get("no_agent_registry_execution_enabled",True)),created_at=_safe_dt(d.get("created_at")),updated_at=_safe_dt(d.get("updated_at")),cancelled_at=_safe_dt(d.get("cancelled_at"),True),expired_at=_safe_dt(d.get("expired_at"),True),expires_at=_safe_dt(d.get("expires_at"),True),metadata=dict(d.get("metadata",{})))

@dataclass
class ProductionSandboxGateCheck:
    check_id: str = field(default_factory=lambda: f"pscheck_{uuid4().hex[:16]}"); gate_request_id: str = ""
    check_type: str = ""; status: str = ProductionSandboxCheckStatus.PASSED; severity: str = ProductionSandboxSeverity.INFO
    message: str = ""; metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"check_id":self.check_id,"gate_request_id":self.gate_request_id,"check_type":self.check_type,"status":self.status,"severity":self.severity,"message":self.message,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(check_id=str(d.get("check_id","")),gate_request_id=str(d.get("gate_request_id","")),check_type=str(d.get("check_type","")),status=str(d.get("status","passed")),severity=str(d.get("severity","info")),message=str(d.get("message","")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

@dataclass
class ProductionSandboxGateResult:
    gate_result_id: str = field(default_factory=lambda: f"psres_{uuid4().hex[:16]}"); gate_request_id: str = ""
    tenant_id: str = ""; gate_status: str = ProductionSandboxGateStatus.BLOCKED
    decision: str = ProductionSandboxGateDecision.BLOCKED
    requirements: list[ProductionSandboxRequirement] = field(default_factory=list)
    checks: list[ProductionSandboxGateCheck] = field(default_factory=list)
    satisfied_count: int = 0; missing_count: int = 0; blocked_count: int = 0
    warnings_count: int = 0; blockers_count: int = 0
    ready_for_step26b: bool = False; ready_for_controlled_runtime_spike: bool = False
    third_party_execution_allowed: bool = False; package_execution_allowed: bool = False
    runtime_enabled: bool = False; metadata_only: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc)); metadata: dict[str,Any] = field(default_factory=dict)

    def add_check(self,c): self.checks.append(c); self._recount()
    def add_requirement(self,r): self.requirements.append(r); self._recount()
    def _recount(self):
        self.satisfied_count=sum(1 for r in self.requirements if r.requirement_status==ProductionSandboxRequirementStatus.SATISFIED)
        self.missing_count=sum(1 for r in self.requirements if r.requirement_status==ProductionSandboxRequirementStatus.MISSING)
        self.blocked_count=sum(1 for r in self.requirements if r.requirement_status in (ProductionSandboxRequirementStatus.BLOCKED,ProductionSandboxRequirementStatus.FAIL_CLOSED))
        self.warnings_count=sum(1 for c in self.checks if c.status==ProductionSandboxCheckStatus.WARNING)
        self.blockers_count=sum(1 for c in self.checks if c.status==ProductionSandboxCheckStatus.BLOCKED)+sum(1 for r in self.requirements if r.is_required_before_execution and r.requirement_status in (ProductionSandboxRequirementStatus.MISSING,ProductionSandboxRequirementStatus.BLOCKED,ProductionSandboxRequirementStatus.FAIL_CLOSED))

    def calculate_status(self):
        self._recount()
        critical_missing = [r for r in self.requirements if r.is_hard_gate and r.is_required_before_execution and r.requirement_status==ProductionSandboxRequirementStatus.MISSING]
        all_sat = [r for r in self.requirements if r.is_required_before_execution and r.requirement_status==ProductionSandboxRequirementStatus.SATISFIED]
        if self.blockers_count>0: self.gate_status=ProductionSandboxGateStatus.BLOCKED; self.decision=ProductionSandboxGateDecision.BLOCKED
        elif len(critical_missing)>0: self.gate_status=ProductionSandboxGateStatus.PASS_READY_FOR_CONTROLLED_SPIKE; self.decision=ProductionSandboxGateDecision.READY_FOR_CONTROLLED_SPIKE_ONLY; self.ready_for_step26b=True
        else: self.gate_status=ProductionSandboxGateStatus.PASS_READY_FOR_CONTROLLED_SPIKE; self.decision=ProductionSandboxGateDecision.READY_FOR_CONTROLLED_SPIKE_ONLY; self.ready_for_step26b=True
        # Always keep execution disabled
        self.third_party_execution_allowed=False; self.package_execution_allowed=False; self.runtime_enabled=False

    def is_third_party_execution_allowed(self) -> bool: return False
    def is_package_execution_allowed(self) -> bool: return False
    def is_runtime_enabled(self) -> bool: return False

    def to_dict(self): return {"gate_result_id":self.gate_result_id,"gate_request_id":self.gate_request_id,"tenant_id":self.tenant_id,"gate_status":self.gate_status,"decision":self.decision,"requirements":[r.to_dict() for r in self.requirements],"checks":[c.to_dict() for c in self.checks],"satisfied_count":self.satisfied_count,"missing_count":self.missing_count,"blocked_count":self.blocked_count,"warnings_count":self.warnings_count,"blockers_count":self.blockers_count,"ready_for_step26b":self.ready_for_step26b,"ready_for_controlled_runtime_spike":self.ready_for_controlled_runtime_spike,"third_party_execution_allowed":self.third_party_execution_allowed,"package_execution_allowed":self.package_execution_allowed,"runtime_enabled":self.runtime_enabled,"metadata_only":self.metadata_only,"created_at":self.created_at.isoformat() if self.created_at else None,"metadata":dict(self.metadata)}
    @classmethod
    def from_dict(cls,d): reqs=[ProductionSandboxRequirement.from_dict(r) for r in d.get("requirements",[])]; chks=[ProductionSandboxGateCheck.from_dict(c) for c in d.get("checks",[])]; return cls(gate_result_id=str(d.get("gate_result_id","")),gate_request_id=str(d.get("gate_request_id","")),tenant_id=str(d.get("tenant_id","")),gate_status=str(d.get("gate_status","blocked")),decision=str(d.get("decision","blocked")),requirements=reqs,checks=chks,satisfied_count=int(d.get("satisfied_count",0)),missing_count=int(d.get("missing_count",0)),blocked_count=int(d.get("blocked_count",0)),warnings_count=int(d.get("warnings_count",0)),blockers_count=int(d.get("blockers_count",0)),ready_for_step26b=bool(d.get("ready_for_step26b",False)),ready_for_controlled_runtime_spike=bool(d.get("ready_for_controlled_runtime_spike",False)),third_party_execution_allowed=bool(d.get("third_party_execution_allowed",False)),package_execution_allowed=bool(d.get("package_execution_allowed",False)),runtime_enabled=bool(d.get("runtime_enabled",False)),metadata_only=bool(d.get("metadata_only",True)),created_at=_safe_dt(d.get("created_at")),metadata=dict(d.get("metadata",{})))

@dataclass
class ProductionSandboxGateAuditEvent:
    event_id: str = field(default_factory=lambda: f"psevt_{uuid4().hex[:16]}"); gate_request_id: str = ""
    tenant_id: str = ""; event_type: str = ""; severity: str = ProductionSandboxGateAuditSeverity.INFO
    actor_id: str|None=None; message: str = ""; metadata: dict[str,Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def to_dict(self): return {"event_id":self.event_id,"gate_request_id":self.gate_request_id,"tenant_id":self.tenant_id,"event_type":self.event_type,"severity":self.severity,"actor_id":self.actor_id,"message":self.message,"metadata":dict(self.metadata),"created_at":self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls,d): return cls(event_id=str(d.get("event_id","")),gate_request_id=str(d.get("gate_request_id","")),tenant_id=str(d.get("tenant_id","")),event_type=str(d.get("event_type","")),severity=str(d.get("severity","info")),actor_id=d.get("actor_id"),message=str(d.get("message","")),metadata=dict(d.get("metadata",{})),created_at=_safe_dt(d.get("created_at")))

class ProductionSandboxGateError(Exception): pass
class ProductionSandboxGateRequestNotFoundError(ProductionSandboxGateError): pass
class ProductionSandboxGateStateError(ProductionSandboxGateError): pass
class ProductionSandboxGateBlockedError(ProductionSandboxGateError): pass

@runtime_checkable
class ProductionSandboxGateStore(Protocol):
    def create_gate_request(self, request: ProductionSandboxGateRequest) -> ProductionSandboxGateRequest: ...
    def get_gate_request(self, gate_request_id: str) -> ProductionSandboxGateRequest | None: ...
    def list_gate_requests(self, *, tenant_id: str = "", status: str = "", decision: str = "") -> list[ProductionSandboxGateRequest]: ...
    def update_gate_request(self, request: ProductionSandboxGateRequest) -> ProductionSandboxGateRequest: ...
    def set_gate_status(self, gate_request_id: str, status: str, actor_id: str | None = None, reason: str | None = None) -> ProductionSandboxGateRequest: ...
    def set_decision(self, gate_request_id: str, decision: str, actor_id: str | None = None, reason: str | None = None) -> ProductionSandboxGateRequest: ...
    def create_gate_result(self, result: ProductionSandboxGateResult) -> ProductionSandboxGateResult: ...
    def get_gate_result(self, gate_result_id: str) -> ProductionSandboxGateResult | None: ...
    def get_gate_result_by_request(self, gate_request_id: str) -> ProductionSandboxGateResult | None: ...
    def cancel_gate_request(self, gate_request_id: str, actor_id: str | None = None, reason: str | None = None) -> ProductionSandboxGateRequest: ...
    def expire_gate_request(self, gate_request_id: str, actor_id: str | None = None, reason: str | None = None) -> ProductionSandboxGateRequest: ...
    def add_audit_event(self, event: ProductionSandboxGateAuditEvent) -> ProductionSandboxGateAuditEvent: ...
    def list_audit_events(self, gate_request_id: str) -> list[ProductionSandboxGateAuditEvent]: ...
    def count_gate_requests(self, *, tenant_id: str = "", status: str = "", decision: str = "") -> int: ...

def _safe_dt(raw, none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
