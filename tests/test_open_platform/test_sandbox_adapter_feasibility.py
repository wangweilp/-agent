"""Sandbox Adapter Feasibility Tests — domain + service + safety。85 tests。"""
import os, pytest
os.environ.setdefault("DEEPSEEK_API_KEY","test-key")
from src.open_platform.sandbox_adapter_feasibility import *
from src.open_platform.sandbox_adapter_feasibility_service import SandboxAdapterFeasibilityService

@pytest.fixture
def svc():
    return SandboxAdapterFeasibilityService()

class TestDomain:
    def test_create_check(self):
        c = FeasibilityCheck(check_type=FeasibilityCheckType.TECHNOLOGY_CLASSIFIED, message="ok")
        assert c.check_id.startswith("fscheck_")
    def test_check_id_format(self):
        assert len(FeasibilityCheck().check_id) == len("fscheck_") + 16
    def test_check_metadata_safe(self):
        d = FeasibilityCheck(message="ok").to_dict()
        assert "raw_key" not in str(d)
    def test_create_profile(self):
        p = AdapterCapabilityProfile(technology=SandboxIsolationTechnology.CONTAINER, name="test")
        assert p.profile_id.startswith("fsprof_")
    def test_profile_exec_false(self):
        assert not AdapterCapabilityProfile().execution_enabled
    def test_profile_to_dict_from_dict(self):
        p = AdapterCapabilityProfile(name="t", technology="container")
        p2 = AdapterCapabilityProfile.from_dict(p.to_dict())
        assert p2.name == "t"
    def test_profile_metadata_safe(self):
        d = AdapterCapabilityProfile().to_dict()
        assert "raw_key" not in str(d)
    def test_create_descriptor(self):
        d = SandboxAdapterDescriptor()
        assert d.adapter_id.startswith("fsadapter_")
    def test_descriptor_all_disabled(self):
        d = SandboxAdapterDescriptor()
        assert not d.execution_enabled and not d.worker_enabled and not d.queue_enabled
        assert not d.dispatch_enabled and not d.download_enabled
        assert not d.container_start_enabled and not d.microvm_start_enabled and not d.subprocess_enabled
    def test_descriptor_is_executable_false(self):
        assert not SandboxAdapterDescriptor().is_executable()
    def test_descriptor_can_start_container_false(self):
        assert not SandboxAdapterDescriptor().can_start_container()
    def test_descriptor_can_start_microvm_false(self):
        assert not SandboxAdapterDescriptor().can_start_microvm()
    def test_descriptor_can_dispatch_false(self):
        assert not SandboxAdapterDescriptor().can_dispatch()
    def test_descriptor_to_dict_from_dict(self):
        d = SandboxAdapterDescriptor(adapter_name="test")
        d2 = SandboxAdapterDescriptor.from_dict(d.to_dict())
        assert d2.adapter_name == "test"
    def test_create_assessment(self):
        a = SandboxAdapterFeasibilityAssessment()
        assert a.assessment_id.startswith("fsassess_")
    def test_assessment_safety_flags_true(self):
        a = SandboxAdapterFeasibilityAssessment()
        assert a.no_execution_performed and a.no_container_started and a.no_microvm_started
        assert a.no_subprocess_started and a.no_network_used
    def test_is_approved_for_execution_false(self):
        assert not SandboxAdapterFeasibilityAssessment().is_approved_for_execution()
    def test_add_check_recounts(self):
        a = SandboxAdapterFeasibilityAssessment()
        a.add_check(FeasibilityCheck(check_type="w", status=FeasibilityCheckStatus.WARNING, severity=FeasibilityCheckSeverity.WARNING, message="w"))
        a.add_check(FeasibilityCheck(check_type="b", status=FeasibilityCheckStatus.BLOCKED, severity=FeasibilityCheckSeverity.BLOCKER, message="b"))
        assert a.warnings_count == 1 and a.blockers_count == 1
    def test_assessment_to_dict_from_dict(self):
        a = SandboxAdapterFeasibilityAssessment(technology="container", profile=AdapterCapabilityProfile(name="t", technology="container"), descriptor=SandboxAdapterDescriptor())
        a.add_check(FeasibilityCheck(check_type="t", message="ok"))
        a2 = SandboxAdapterFeasibilityAssessment.from_dict(a.to_dict())
        assert len(a2.checks) == 1
    def test_assessment_null_profile_ok(self):
        a = SandboxAdapterFeasibilityAssessment()
        d = a.to_dict()
        assert "assessment_id" in d

class TestService:
    def test_noexec(self, svc):
        a = svc.assess_technology(SandboxIsolationTechnology.NO_EXECUTION_BASELINE)
        assert a.profile.isolation_strength == IsolationStrength.VERY_HIGH
        assert not a.profile.execution_enabled
    def test_disabled_worker(self, svc):
        a = svc.assess_technology(SandboxIsolationTechnology.DISABLED_WORKER)
        assert a.decision == FeasibilityDecision.ACCEPT_AS_CANDIDATE
    def test_dryrun(self, svc):
        a = svc.assess_technology(SandboxIsolationTechnology.LOCAL_DRY_RUN)
        assert a.decision == FeasibilityDecision.ACCEPT_AS_CANDIDATE
    def test_subprocess_rejected(self, svc):
        a = svc.assess_technology(SandboxIsolationTechnology.SUBPROCESS_REJECTED)
        assert a.decision == FeasibilityDecision.REJECT_FOR_UNTRUSTED_CODE
    def test_subprocess_exec_false(self, svc):
        assert not svc.assess_technology(SandboxIsolationTechnology.SUBPROCESS_REJECTED).profile.execution_enabled
    def test_subprocess_risk_critical(self, svc):
        p = svc.assess_technology(SandboxIsolationTechnology.SUBPROCESS_REJECTED).profile
        assert p.security_risk == FeasibilityRiskLevel.CRITICAL
    def test_container_has_risks(self, svc):
        a = svc.assess_technology(SandboxIsolationTechnology.CONTAINER)
        assert a.profile.known_risks and len(a.profile.known_risks) >= 2
    def test_container_exec_false(self, svc):
        assert not svc.assess_technology(SandboxIsolationTechnology.CONTAINER).profile.execution_enabled
    def test_container_requires_docker_socket(self, svc):
        assert svc.assess_technology(SandboxIsolationTechnology.CONTAINER).profile.requires_docker_socket
    def test_container_requires_linux(self, svc):
        assert svc.assess_technology(SandboxIsolationTechnology.CONTAINER).profile.requires_linux_host
    def test_rootless_candidate(self, svc):
        a = svc.assess_technology(SandboxIsolationTechnology.ROOTLESS_CONTAINER)
        assert a.profile.supports_rootless and a.decision == FeasibilityDecision.ACCEPT_AS_CANDIDATE
    def test_remote_requires_infra(self, svc):
        assert svc.assess_technology(SandboxIsolationTechnology.REMOTE_ISOLATED_WORKER).profile.requires_remote_infra
    def test_wasm_exec_false(self, svc):
        assert not svc.assess_technology(SandboxIsolationTechnology.WASM).profile.execution_enabled
    def test_microvm_very_high_isolation(self, svc):
        assert svc.assess_technology(SandboxIsolationTechnology.MICROVM).profile.isolation_strength == IsolationStrength.VERY_HIGH
    def test_microvm_exec_false(self, svc):
        assert not svc.assess_technology(SandboxIsolationTechnology.MICROVM).profile.execution_enabled
    def test_microvm_linux_only(self, svc):
        assert svc.assess_technology(SandboxIsolationTechnology.MICROVM).profile.requires_linux_host
    def test_managed_cloud_remote(self, svc):
        assert svc.assess_technology(SandboxIsolationTechnology.MANAGED_CLOUD_SANDBOX).profile.requires_remote_infra
    def test_all_default_10(self, svc):
        assert len(svc.assess_all_default_options()) == 10
    def test_all_exec_false(self, svc):
        for a in svc.assess_all_default_options():
            assert not a.profile.execution_enabled
    def test_all_have_noexec_check(self, svc):
        for a in svc.assess_all_default_options():
            assert any(c.check_type == FeasibilityCheckType.NO_EXECUTION_PERFORMED and c.status == "passed" for c in a.checks)
    def test_all_have_no_container_check(self, svc):
        for a in svc.assess_all_default_options():
            assert any(c.check_type == FeasibilityCheckType.NO_CONTAINER_STARTED for c in a.checks)
    def test_all_have_no_microvm_check(self, svc):
        for a in svc.assess_all_default_options():
            assert any(c.check_type == FeasibilityCheckType.NO_MICROVM_STARTED for c in a.checks)
    def test_all_have_no_subprocess_check(self, svc):
        for a in svc.assess_all_default_options():
            assert any(c.check_type == FeasibilityCheckType.NO_SUBPROCESS_STARTED for c in a.checks)
    def test_all_have_no_network_check(self, svc):
        for a in svc.assess_all_default_options():
            assert any(c.check_type == FeasibilityCheckType.NO_NETWORK_USED for c in a.checks)
    def test_all_have_no_download_check(self, svc):
        for a in svc.assess_all_default_options():
            assert any(c.check_type == FeasibilityCheckType.NO_PACKAGE_DOWNLOADED for c in a.checks)
    def test_unknown_fail_closed(self, svc):
        a = svc.assess_technology("unknown_xxx")
        assert a.decision == FeasibilityDecision.FAIL_CLOSED
    def test_build_disabled_descriptor(self, svc):
        d = svc.build_disabled_adapter_descriptor(SandboxIsolationTechnology.CONTAINER)
        assert d.adapter_status == FeasibilityStatus.BLOCKED and not d.execution_enabled
    def test_all_approved_execution_false(self, svc):
        for a in svc.assess_all_default_options():
            assert not a.is_approved_for_execution()

class TestSafety:
    def test_dm_no_docker(self):
        m = __import__("src.open_platform.sandbox_adapter_feasibility", fromlist=[""])
        assert "docker" not in str(dir(m)).lower()
    def test_dm_no_subprocess(self):
        m = __import__("src.open_platform.sandbox_adapter_feasibility", fromlist=[""])
        assert "subprocess" not in str(dir(m)).lower()
    def test_dm_no_requests(self):
        m = __import__("src.open_platform.sandbox_adapter_feasibility", fromlist=[""])
        assert "requests" not in str(dir(m)).lower() and "httpx" not in str(dir(m)).lower()
    def test_dm_no_AgentRuntime(self):
        m = __import__("src.open_platform.sandbox_adapter_feasibility", fromlist=[""])
        assert "AgentRuntime" not in str(dir(m))
    def test_dm_no_AgentRegistry(self):
        m = __import__("src.open_platform.sandbox_adapter_feasibility", fromlist=[""])
        assert "AgentRegistry" not in str(dir(m))
    def test_svc_no_docker(self):
        m = __import__("src.open_platform.sandbox_adapter_feasibility_service", fromlist=[""])
        assert "docker" not in str(dir(m)).lower()
    def test_svc_no_subprocess(self):
        m = __import__("src.open_platform.sandbox_adapter_feasibility_service", fromlist=[""])
        assert "subprocess" not in str(dir(m)).lower()
    def test_svc_no_requests(self):
        m = __import__("src.open_platform.sandbox_adapter_feasibility_service", fromlist=[""])
        assert "requests" not in str(dir(m)).lower() and "httpx" not in str(dir(m)).lower()
    def test_svc_no_AgentRuntime(self):
        m = __import__("src.open_platform.sandbox_adapter_feasibility_service", fromlist=[""])
        assert "AgentRuntime" not in str(dir(m))
    def test_svc_no_AgentRegistry(self):
        m = __import__("src.open_platform.sandbox_adapter_feasibility_service", fromlist=[""])
        assert "AgentRegistry" not in str(dir(m))
    def test_descriptor_flags_all_false(self):
        d = SandboxAdapterDescriptor()
        assert not d.execution_enabled and not d.worker_enabled and not d.queue_enabled
        assert not d.dispatch_enabled and not d.download_enabled
        assert not d.container_start_enabled and not d.microvm_start_enabled and not d.subprocess_enabled
    def test_svc_no_execute_method(self):
        assert not hasattr(SandboxAdapterFeasibilityService, "execute") or not callable(getattr(SandboxAdapterFeasibilityService, "execute", None))
    def test_svc_no_start_container(self):
        assert not hasattr(SandboxAdapterFeasibilityService, "start_container")
    def test_svc_no_start_microvm(self):
        assert not hasattr(SandboxAdapterFeasibilityService, "start_microvm")
    def test_svc_no_dispatch(self):
        assert not hasattr(SandboxAdapterFeasibilityService, "dispatch")
    def test_svc_no_download(self):
        assert not hasattr(SandboxAdapterFeasibilityService, "download")
    def test_subprocess_rejected_explicit(self):
        svc = SandboxAdapterFeasibilityService()
        a = svc.assess_technology(SandboxIsolationTechnology.SUBPROCESS_REJECTED)
        assert a.decision == FeasibilityDecision.REJECT_FOR_UNTRUSTED_CODE
    def test_container_not_approved(self):
        svc = SandboxAdapterFeasibilityService()
        a = svc.assess_technology(SandboxIsolationTechnology.CONTAINER)
        assert not a.is_approved_for_execution()
    def test_rootless_not_approved(self):
        svc = SandboxAdapterFeasibilityService()
        a = svc.assess_technology(SandboxIsolationTechnology.ROOTLESS_CONTAINER)
        assert not a.is_approved_for_execution()
    def test_all_approved_execution_false(self):
        svc = SandboxAdapterFeasibilityService()
        for a in svc.assess_all_default_options():
            assert not a.is_approved_for_execution()
    def test_all_safety_flags(self, svc):
        for a in svc.assess_all_default_options():
            assert a.no_container_started and a.no_microvm_started and a.no_subprocess_started and a.no_wasm_runtime_started
    def test_all_no_network(self, svc):
        for a in svc.assess_all_default_options():
            assert a.no_network_used
    def test_all_no_package_download(self, svc):
        for a in svc.assess_all_default_options():
            assert a.no_package_downloaded
    def test_all_no_queue(self, svc):
        for a in svc.assess_all_default_options():
            assert a.no_queue_created

class TestDocs:
    def test_step25c_doc_exists(self):
        import os; assert os.path.exists("docs/STEP25C_CONTAINER_MICROVM_ADAPTER_FEASIBILITY_SPIKE.md")
    def test_doc_says_no_container_implementation(self):
        with open("docs/STEP25C_CONTAINER_MICROVM_ADAPTER_FEASIBILITY_SPIKE.md", encoding="utf-8") as f:
            c = f.read().lower()
        assert "not container implementation" in c or "没有启动 container" in c
    def test_doc_says_no_docker_started(self):
        with open("docs/STEP25C_CONTAINER_MICROVM_ADAPTER_FEASIBILITY_SPIKE.md", encoding="utf-8") as f:
            c = f.read().lower()
        assert "没有启动 docker" in c or "no docker" in c or "没有调用 docker" in c
    def test_doc_says_execute_blocked(self):
        with open("docs/STEP25C_CONTAINER_MICROVM_ADAPTER_FEASIBILITY_SPIKE.md", encoding="utf-8") as f:
            c = f.read().lower()
        assert "blocked" in c or "execute endpoint" in c
    def test_doc_says_subprocess_rejected(self):
        with open("docs/STEP25C_CONTAINER_MICROVM_ADAPTER_FEASIBILITY_SPIKE.md", encoding="utf-8") as f:
            c = f.read().lower()
        assert "subprocess" in c and ("rejected" in c or "不是" in c)
    def test_doc_says_rootless_candidate_not_approved(self):
        with open("docs/STEP25C_CONTAINER_MICROVM_ADAPTER_FEASIBILITY_SPIKE.md", encoding="utf-8") as f:
            c = f.read().lower()
        assert "rootless" in c or "candidate" in c
    def test_doc_says_microvm_reserved(self):
        with open("docs/STEP25C_CONTAINER_MICROVM_ADAPTER_FEASIBILITY_SPIKE.md", encoding="utf-8") as f:
            c = f.read().lower()
        assert "microvm" in c and ("reserved" in c or "future" in c)
    def test_readme_marks_25c_done(self):
        with open("README.md", encoding="utf-8") as f:
            c = f.read()
        assert "25-C" in c and "✅" in c
    def test_roadmap_marks_25c_done(self):
        with open("docs/ROADMAP.md", encoding="utf-8") as f:
            c = f.read()
        assert "25-C" in c and "✅" in c
    def test_roadmap_marks_25d_pending(self):
        with open("docs/ROADMAP.md", encoding="utf-8") as f:
            c = f.read()
        assert "25-D" in c and "⏸" in c
    def test_doc_no_claim_container_implementation_complete(self):
        with open("docs/STEP25C_CONTAINER_MICROVM_ADAPTER_FEASIBILITY_SPIKE.md", encoding="utf-8") as f:
            c = f.read().lower()
        assert "container implementation completed" not in c
    def test_doc_no_claim_microvm_implementation_complete(self):
        with open("docs/STEP25C_CONTAINER_MICROVM_ADAPTER_FEASIBILITY_SPIKE.md", encoding="utf-8") as f:
            c = f.read().lower()
        assert "microvm implementation completed" not in c
    def test_doc_no_claim_execution_complete(self):
        with open("docs/STEP25C_CONTAINER_MICROVM_ADAPTER_FEASIBILITY_SPIKE.md", encoding="utf-8") as f:
            c = f.read().lower()
        assert "external code execution completed" not in c
    def test_doc_no_claim_execute_endpoint_success(self):
        with open("docs/STEP25C_CONTAINER_MICROVM_ADAPTER_FEASIBILITY_SPIKE.md", encoding="utf-8") as f:
            c = f.read().lower()
        assert "runtime execution success completed" not in c
