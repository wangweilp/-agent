"""Sandbox Adapter Feasibility Service — paper-tier assessment of 10 isolation technologies.

Step 25-C: No runtime started. No Docker. No container. No microVM. No WASM.
is_approved_for_execution() = always False. All adapter enabled flags = False."""

from __future__ import annotations
from .sandbox_adapter_feasibility import *

_NOEXEC_CHECKS = [(FeasibilityCheckType.NO_EXECUTION_PERFORMED,"No code execution performed."),(FeasibilityCheckType.NO_DOCKER_STARTED,"No Docker daemon started."),(FeasibilityCheckType.NO_CONTAINER_STARTED,"No container started."),(FeasibilityCheckType.NO_MICROVM_STARTED,"No microVM started."),(FeasibilityCheckType.NO_WASM_RUNTIME_STARTED,"No WASM runtime started."),(FeasibilityCheckType.NO_SUBPROCESS_STARTED,"No subprocess started."),(FeasibilityCheckType.NO_NETWORK_USED,"No network calls made."),(FeasibilityCheckType.NO_PACKAGE_DOWNLOADED,"No package downloaded."),(FeasibilityCheckType.NO_QUEUE_CREATED,"No queue created."),(FeasibilityCheckType.NO_JOB_DISPATCHED,"No job dispatched.")]
def _c(ct,st="passed",sv="info",msg="",**kw): return FeasibilityCheck(check_type=ct,status=st,severity=sv,message=msg,metadata=kw)

def _make(tech,profile,checks=(),force_decision=None,force_status=None):
    a=SandboxAdapterFeasibilityAssessment(technology=tech,profile=profile,descriptor=SandboxAdapterDescriptor(technology=tech,adapter_name=tech,adapter_status=FeasibilityStatus.BLOCKED))
    for ct,msg in _NOEXEC_CHECKS: a.add_check(_c(ct,"passed","info",msg))
    for ct,st,sv,msg in checks: a.add_check(_c(ct,st,sv,msg))
    a.calculate_status()
    if force_decision: a.decision = force_decision
    if force_status: a.status = force_status
    return a

class SandboxAdapterFeasibilityService:
    def assess_technology(self, technology: str) -> SandboxAdapterFeasibilityAssessment:
        t=technology
        if t==SandboxIsolationTechnology.NO_EXECUTION_BASELINE:
            return _make(t,AdapterCapabilityProfile(technology=t,name="No Execution Baseline",isolation_strength=IsolationStrength.VERY_HIGH,production_fit=ProductionFit.LIMITED,windows_dev_fit=ProductionFit.STRONG,operational_complexity=FeasibilityRiskLevel.LOW,security_risk=FeasibilityRiskLevel.LOW,recommendation=FeasibilityDecision.ACCEPT_AS_CANDIDATE,prototype_allowed=True,known_risks=["No execution capability"],required_hard_gates=["current baseline"]))
        if t==SandboxIsolationTechnology.DISABLED_WORKER:
            return _make(t,AdapterCapabilityProfile(technology=t,name="Disabled Worker",isolation_strength=IsolationStrength.VERY_HIGH,production_fit=ProductionFit.LIMITED,windows_dev_fit=ProductionFit.STRONG,operational_complexity=FeasibilityRiskLevel.LOW,security_risk=FeasibilityRiskLevel.LOW,recommendation=FeasibilityDecision.ACCEPT_AS_CANDIDATE,prototype_allowed=True))
        if t==SandboxIsolationTechnology.LOCAL_DRY_RUN:
            return _make(t,AdapterCapabilityProfile(technology=t,name="Local Dry-Run",isolation_strength=IsolationStrength.VERY_HIGH,production_fit=ProductionFit.LIMITED,windows_dev_fit=ProductionFit.STRONG,operational_complexity=FeasibilityRiskLevel.LOW,security_risk=FeasibilityRiskLevel.LOW,recommendation=FeasibilityDecision.ACCEPT_AS_CANDIDATE,prototype_allowed=True,known_risks=["Dry-run only — no real execution"]))
        if t==SandboxIsolationTechnology.SUBPROCESS_REJECTED:
            return _make(t,AdapterCapabilityProfile(technology=t,name="Sandboxed Subprocess (REJECTED)",isolation_strength=IsolationStrength.LOW,production_fit=ProductionFit.NOT_FIT,windows_dev_fit=ProductionFit.LIMITED,operational_complexity=FeasibilityRiskLevel.MEDIUM,security_risk=FeasibilityRiskLevel.CRITICAL,execution_enabled=False,recommendation=FeasibilityDecision.REJECT_FOR_UNTRUSTED_CODE,known_risks=["No syscall filter on Windows","os.system() escape","ctypes/mmap escape","Python process isolation insufficient"],required_hard_gates=["REJECT permanently for untrusted third-party code"]),((FeasibilityCheckType.SUBPROCESS_REJECTED_FOR_UNTRUSTED_CODE,"passed","info","Subprocess is rejected for untrusted code."),(FeasibilityCheckType.ISOLATION_STRENGTH_ASSESSED,"failed","error","Isolation strength: LOW."),(FeasibilityCheckType.SECURITY_RISK_ASSESSED,"failed","blocker","Security risk: CRITICAL.")),force_decision=FeasibilityDecision.REJECT_FOR_UNTRUSTED_CODE)
        if t==SandboxIsolationTechnology.CONTAINER:
            return _make(t,AdapterCapabilityProfile(technology=t,name="Container (Docker)",isolation_strength=IsolationStrength.HIGH,production_fit=ProductionFit.GOOD,windows_dev_fit=ProductionFit.LIMITED,operational_complexity=FeasibilityRiskLevel.MEDIUM,security_risk=FeasibilityRiskLevel.HIGH,execution_enabled=False,supports_network_policy=True,supports_filesystem_policy=True,supports_resource_limits=True,supports_kill_switch=True,supports_audit=True,supports_tenant_isolation=True,requires_linux_host=True,requires_docker_socket=True,recommendation=FeasibilityDecision.BLOCK_UNTIL_HARD_GATES,known_risks=["Container escape if misconfigured","Privileged flag bypass","Docker socket = host access","Host path mount = data exfiltration"],required_hard_gates=["No privileged","No docker socket","No host mount","Seccomp+AppArmor","Read-only rootfs","Cap drop ALL","NoNewPrivileges"]))
        if t==SandboxIsolationTechnology.ROOTLESS_CONTAINER:
            return _make(t,AdapterCapabilityProfile(technology=t,name="Rootless Container",isolation_strength=IsolationStrength.VERY_HIGH,production_fit=ProductionFit.GOOD,windows_dev_fit=ProductionFit.LIMITED,operational_complexity=FeasibilityRiskLevel.MEDIUM,security_risk=FeasibilityRiskLevel.MEDIUM,execution_enabled=False,supports_network_policy=True,supports_filesystem_policy=True,supports_resource_limits=True,supports_kill_switch=True,supports_rootless=True,requires_linux_host=True,recommendation=FeasibilityDecision.ACCEPT_AS_CANDIDATE,known_risks=["Rootless ≠ no risk","Needs seccomp/AppArmor"],required_hard_gates=["No privileged","Read-only rootfs","Cap drop ALL","NoNewPrivileges"]),((FeasibilityCheckType.ROOTLESS_CONTAINER_CANDIDATE,"passed","info","Rootless container is a CANDIDATE for production."),))
        if t==SandboxIsolationTechnology.REMOTE_ISOLATED_WORKER:
            return _make(t,AdapterCapabilityProfile(technology=t,name="Remote Isolated Worker",isolation_strength=IsolationStrength.MEDIUM,production_fit=ProductionFit.LIMITED,windows_dev_fit=ProductionFit.GOOD,operational_complexity=FeasibilityRiskLevel.HIGH,security_risk=FeasibilityRiskLevel.MEDIUM,execution_enabled=False,requires_remote_infra=True,recommendation=FeasibilityDecision.RESERVE_FOR_FUTURE_SPIKE,known_risks=["App-level not kernel-level","Network dependency"]))
        if t==SandboxIsolationTechnology.WASM:
            return _make(t,AdapterCapabilityProfile(technology=t,name="WASM Runtime",isolation_strength=IsolationStrength.HIGH,production_fit=ProductionFit.LIMITED,windows_dev_fit=ProductionFit.GOOD,operational_complexity=FeasibilityRiskLevel.HIGH,security_risk=FeasibilityRiskLevel.MEDIUM,execution_enabled=False,supports_resource_limits=True,recommendation=FeasibilityDecision.RESERVE_FOR_FUTURE_SPIKE,known_risks=["Python not fully WASM-compatible","Limited library support","Pyodide ≠ all Python"]))
        if t==SandboxIsolationTechnology.MICROVM:
            return _make(t,AdapterCapabilityProfile(technology=t,name="MicroVM (Firecracker)",isolation_strength=IsolationStrength.VERY_HIGH,production_fit=ProductionFit.STRONG,windows_dev_fit=ProductionFit.NOT_FIT,operational_complexity=FeasibilityRiskLevel.HIGH,security_risk=FeasibilityRiskLevel.LOW,execution_enabled=False,supports_network_policy=True,supports_filesystem_policy=True,supports_resource_limits=True,supports_kill_switch=True,supports_tenant_isolation=True,requires_linux_host=True,recommendation=FeasibilityDecision.RESERVE_FOR_FUTURE_SPIKE,known_risks=["Linux only","Higher startup overhead"],required_hard_gates=["Linux production server only","KVM/VMX availability"]),((FeasibilityCheckType.MICROVM_RESERVED_FOR_PRODUCTION,"passed","info","MicroVM reserved for production Linux."),))
        if t==SandboxIsolationTechnology.MANAGED_CLOUD_SANDBOX:
            return _make(t,AdapterCapabilityProfile(technology=t,name="Managed Cloud Sandbox",isolation_strength=IsolationStrength.HIGH,production_fit=ProductionFit.GOOD,windows_dev_fit=ProductionFit.LIMITED,operational_complexity=FeasibilityRiskLevel.LOW,security_risk=FeasibilityRiskLevel.LOW,execution_enabled=False,requires_remote_infra=True,recommendation=FeasibilityDecision.RESERVE_FOR_FUTURE_SPIKE,known_risks=["Vendor dependency","Cost","Data residency"]))
        return _make(t,AdapterCapabilityProfile(technology=t,name=f"Unknown: {t}",recommendation=FeasibilityDecision.FAIL_CLOSED,security_risk=FeasibilityRiskLevel.CRITICAL),((FeasibilityCheckType.FAIL_CLOSED_ON_UNKNOWN,"blocked","blocker",f"Unknown technology '{t}' → FAIL_CLOSED."),))

    def assess_all_default_options(self) -> list[SandboxAdapterFeasibilityAssessment]:
        return [self.assess_technology(t) for t in SandboxIsolationTechnology.__members__.values()]

    def build_disabled_adapter_descriptor(self, technology: str, profile: Any = None) -> SandboxAdapterDescriptor:
        return SandboxAdapterDescriptor(technology=technology, adapter_name=technology,
            adapter_status=FeasibilityStatus.BLOCKED,
            capability_profile=profile.to_dict() if profile and hasattr(profile,"to_dict") else {})
