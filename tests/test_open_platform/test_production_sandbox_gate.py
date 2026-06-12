"""Production Sandbox Gate Tests — domain + store + service + safety。68 tests."""
import os, tempfile, pytest
os.environ.setdefault("DEEPSEEK_API_KEY","test-key")
from datetime import datetime, timezone
from src.adapters.config import Settings
from src.adapters.production_sandbox_gate_store import SQLiteProductionSandboxGateStore
from src.open_platform.production_sandbox_gate import *
from src.open_platform.production_sandbox_gate_service import ProductionSandboxGateService

@pytest.fixture
def settings(): return Settings()
@pytest.fixture
def tmp_db_path():
    d=tempfile.mkdtemp(); p=os.path.join(d,"test_psg.db"); yield p
    import shutil; shutil.rmtree(d,ignore_errors=True)
@pytest.fixture
def store(settings,tmp_db_path): return SQLiteProductionSandboxGateStore(settings,db_path=tmp_db_path)
@pytest.fixture
def svc(store): return ProductionSandboxGateService(store=store)

# ═══════ Domain (20) ═══════
class TestDomain:
    def test_req_id(self): r=ProductionSandboxRequirement(name="t"); assert r.requirement_id.startswith("psreq_")
    def test_req_hard_gate(self): r=ProductionSandboxRequirement(is_hard_gate=True,is_required_before_execution=True); assert r.is_hard_gate
    def test_req_to_dict(self): r=ProductionSandboxRequirement(name="t"); d=r.to_dict(); r2=ProductionSandboxRequirement.from_dict(d); assert r2.name=="t"
    def test_req_metadata_safe(self): d=ProductionSandboxRequirement().to_dict(); assert "raw_key" not in str(d)
    def test_gate_req_id(self): r=ProductionSandboxGateRequest(tenant_id="t"); assert r.gate_request_id.startswith("psgate_")
    def test_gate_req_no_flags(self): r=ProductionSandboxGateRequest(tenant_id="t"); assert r.no_third_party_execution_enabled and r.no_package_execution_enabled and r.no_container_enabled
    def test_gate_req_no_3p(self): assert not ProductionSandboxGateRequest(tenant_id="t").is_third_party_execution_allowed()
    def test_gate_req_no_pkg(self): assert not ProductionSandboxGateRequest(tenant_id="t").is_package_execution_allowed()
    def test_gate_req_no_runtime(self): assert not ProductionSandboxGateRequest(tenant_id="t").is_runtime_enabled()
    def test_gate_req_no_exec(self): r=ProductionSandboxGateRequest(tenant_id="t"); assert not hasattr(r,"enable_execution") or not callable(getattr(r,"enable_execution",None))
    def test_gate_req_to_dict(self): d=ProductionSandboxGateRequest(tenant_id="t").to_dict(); r2=ProductionSandboxGateRequest.from_dict(d); assert r2.tenant_id=="t"
    def test_check_id(self): assert ProductionSandboxGateCheck().check_id.startswith("pscheck_")
    def test_check_safe(self): d=ProductionSandboxGateCheck().to_dict(); assert "raw_key" not in str(d)
    def test_result_id(self): r=ProductionSandboxGateResult(); assert r.gate_result_id.startswith("psres_")
    def test_result_3p_false(self): assert not ProductionSandboxGateResult().is_third_party_execution_allowed()
    def test_result_pkg_false(self): assert not ProductionSandboxGateResult().is_package_execution_allowed()
    def test_result_runtime_false(self): assert not ProductionSandboxGateResult().is_runtime_enabled()
    def test_result_metadata_only(self): assert ProductionSandboxGateResult().metadata_only
    def test_result_add_check(self): r=ProductionSandboxGateResult(); r.add_check(ProductionSandboxGateCheck(check_type="b",status=ProductionSandboxCheckStatus.BLOCKED,severity=ProductionSandboxSeverity.BLOCKER,message="b")); assert r.blockers_count>=1
    def test_audit_safe(self): d=ProductionSandboxGateAuditEvent(gate_request_id="g",tenant_id="t",event_type="t",message="ok").to_dict(); assert "raw_key" not in str(d)

# ═══════ Requirements (10) ═══════
class TestRequirements:
    def test_default_count(self): reqs=build_step26a_default_requirements(); assert len(reqs)>=24
    def test_has_step25_final(self): reqs=build_step26a_default_requirements(); assert any(r.area==ProductionSandboxImplementationArea.FINAL_REGRESSION for r in reqs)
    def test_has_kill_switch(self): reqs=build_step26a_default_requirements(); assert any(r.area==ProductionSandboxImplementationArea.KILL_SWITCH and r.requirement_status==ProductionSandboxRequirementStatus.MISSING for r in reqs)
    def test_has_incident(self): reqs=build_step26a_default_requirements(); assert any(r.area==ProductionSandboxImplementationArea.INCIDENT_STORE for r in reqs)
    def test_has_tenant_iso(self): reqs=build_step26a_default_requirements(); assert any(r.area==ProductionSandboxImplementationArea.TENANT_ISOLATION for r in reqs)
    def test_has_network(self): reqs=build_step26a_default_requirements(); assert any(r.area==ProductionSandboxImplementationArea.NETWORK_ENFORCEMENT and r.name=="Real Network Enforcement" for r in reqs)
    def test_has_secrets(self): reqs=build_step26a_default_requirements(); assert any(r.area==ProductionSandboxImplementationArea.SECRETS_ENFORCEMENT for r in reqs)
    def test_has_container(self): reqs=build_step26a_default_requirements(); assert any(r.area==ProductionSandboxImplementationArea.CONTAINER_ISOLATION for r in reqs)
    def test_has_microvm(self): reqs=build_step26a_default_requirements(); assert any(r.area==ProductionSandboxImplementationArea.MICROVM_ISOLATION for r in reqs)
    def test_missing_block_3p(self):
        reqs = build_step26a_default_requirements()
        missing_hard = [r for r in reqs if r.is_hard_gate and r.is_required_before_execution and r.requirement_status==ProductionSandboxRequirementStatus.MISSING]
        assert len(missing_hard) >= 10

# ═══════ Store (21) ═══════
class TestStore:
    def _r(self, **kw):
        kw.setdefault("tenant_id","t1"); return ProductionSandboxGateRequest(**kw)
    def test_create(self,store): r=store.create_gate_request(self._r()); assert store.get_gate_request(r.gate_request_id) is not None
    def test_get(self,store): r=store.create_gate_request(self._r()); assert store.get_gate_request(r.gate_request_id).tenant_id=="t1"
    def test_list_tenant(self,store): store.create_gate_request(self._r(tenant_id="tA")); store.create_gate_request(self._r(tenant_id="tB")); assert len(store.list_gate_requests(tenant_id="tA"))==1
    def test_list_status(self,store): store.create_gate_request(self._r(gate_status=ProductionSandboxGateStatus.REQUESTED)); assert len(store.list_gate_requests(status=ProductionSandboxGateStatus.REQUESTED))>=1
    def test_list_decision(self,store): store.create_gate_request(self._r(decision=ProductionSandboxGateDecision.REVIEW_REQUIRED)); assert len(store.list_gate_requests(decision=ProductionSandboxGateDecision.REVIEW_REQUIRED))>=1
    def test_update(self,store): r=store.create_gate_request(self._r()); r.risk_level=ProductionSandboxRiskLevel.HIGH; store.update_gate_request(r); assert store.get_gate_request(r.gate_request_id).risk_level==ProductionSandboxRiskLevel.HIGH
    def test_set_status(self,store): r=store.create_gate_request(self._r()); store.set_gate_status(r.gate_request_id,ProductionSandboxGateStatus.EVALUATED,"a"); assert store.get_gate_request(r.gate_request_id).gate_status==ProductionSandboxGateStatus.EVALUATED
    def test_set_decision(self,store): r=store.create_gate_request(self._r()); store.set_decision(r.gate_request_id,ProductionSandboxGateDecision.READY_FOR_CONTROLLED_SPIKE_ONLY,"a"); assert store.get_gate_request(r.gate_request_id).decision==ProductionSandboxGateDecision.READY_FOR_CONTROLLED_SPIKE_ONLY
    def test_create_result(self,store): r=store.create_gate_request(self._r()); res=ProductionSandboxGateResult(gate_request_id=r.gate_request_id,tenant_id="t1"); store.create_gate_result(res); assert store.get_gate_result(res.gate_result_id) is not None
    def test_get_result_by_req(self,store): r=store.create_gate_request(self._r()); res=ProductionSandboxGateResult(gate_request_id=r.gate_request_id,tenant_id="t1"); store.create_gate_result(res); assert store.get_gate_result_by_request(r.gate_request_id) is not None
    def test_cancel(self,store): r=store.create_gate_request(self._r()); store.cancel_gate_request(r.gate_request_id,"a"); assert store.get_gate_request(r.gate_request_id).gate_status in (ProductionSandboxGateStatus.FAIL_CLOSED,ProductionSandboxGateStatus.BLOCKED)
    def test_expire(self,store): r=store.create_gate_request(self._r()); store.expire_gate_request(r.gate_request_id,"sys"); assert store.get_gate_request(r.gate_request_id).gate_status in (ProductionSandboxGateStatus.FAIL_CLOSED,ProductionSandboxGateStatus.BLOCKED)
    def test_count(self,store): store.create_gate_request(self._r(tenant_id="tc")); store.create_gate_request(self._r(tenant_id="tc")); assert store.count_gate_requests(tenant_id="tc")==2
    def test_audit_create(self,store): r=store.create_gate_request(self._r()); assert any(e.event_type==ProductionSandboxGateAuditEventType.GATE_REQUEST_CREATED for e in store.list_audit_events(r.gate_request_id))
    def test_audit_status(self,store): r=store.create_gate_request(self._r()); store.set_gate_status(r.gate_request_id,ProductionSandboxGateStatus.EVALUATED,"a"); assert any(e.event_type==ProductionSandboxGateAuditEventType.STATUS_CHANGED for e in store.list_audit_events(r.gate_request_id))
    def test_audit_sorted(self,store): r=store.create_gate_request(self._r()); store.set_gate_status(r.gate_request_id,ProductionSandboxGateStatus.EVALUATED,"a"); evts=store.list_audit_events(r.gate_request_id); assert evts[0].created_at<=evts[-1].created_at
    def test_json_rt(self,store): r=store.create_gate_request(self._r(step25_final_gate_snapshot={"k":"v"})); assert store.get_gate_request(r.gate_request_id).step25_final_gate_snapshot=={"k":"v"}
    def test_bool_rt(self,store): r=store.create_gate_request(self._r()); f=store.get_gate_request(r.gate_request_id); assert f.no_third_party_execution_enabled and f.no_container_enabled
    def test_no_delete(self,store): assert not hasattr(store,"delete_gate_request") or not callable(getattr(store,"delete_gate_request",None))
    def test_repeated_init(self,store,settings,tmp_db_path): store.create_gate_request(self._r()); store.flush(); assert SQLiteProductionSandboxGateStore(settings,db_path=tmp_db_path).count_gate_requests()==1
    def test_no_danger_methods(self,store):
        for b in ["enable_execution","start_runtime","execute_package","dispatch","enqueue","start_worker","start_container","start_microvm"]:
            assert not hasattr(store,b) or not callable(getattr(store,b,None)), f"store has {b}"

# ═══════ Service + Safety (10) ═══════
class TestService:
    def test_create(self,svc,store): r=svc.create_gate_request("t1"); assert r.gate_status==ProductionSandboxGateStatus.REQUESTED
    def test_evaluate(self,svc,store):
        r=svc.create_gate_request("t1"); res=svc.evaluate_gate(r.gate_request_id)
        assert len(res.requirements)>=24 and res.metadata_only
    def test_evaluate_3p_false(self,svc,store): r=svc.create_gate_request("t1"); res=svc.evaluate_gate(r.gate_request_id); assert not res.is_third_party_execution_allowed() and not res.is_package_execution_allowed()
    def test_evaluate_runtime_false(self,svc,store): r=svc.create_gate_request("t1"); res=svc.evaluate_gate(r.gate_request_id); assert not res.is_runtime_enabled()
    def test_svc_no_danger(self,svc):
        for b in ["enable_execution","start_runtime","execute_package","execute_third_party_code","dispatch_job","enqueue_job","start_worker","start_container","start_microvm"]:
            assert not hasattr(svc,b) or not callable(getattr(svc,b,None)), f"svc has {b}"
    def test_exec_not_executable(self):
        from src.open_platform.sandbox_execution import SandboxExecutionRecord
        assert not SandboxExecutionRecord(plan_id="p",marketplace_agent_id="m",tenant_id="t",developer_id="d").is_executable()
    def test_dm_no_subprocess(self):
        import src.open_platform.production_sandbox_gate as m; assert "subprocess" not in str(dir(m)).lower()
    def test_dm_no_AgentRuntime(self):
        import src.open_platform.production_sandbox_gate as m; assert "AgentRuntime" not in str(dir(m))
    def test_fixture_not_3p(self):
        from src.open_platform.trusted_fixture_execution import TrustedFixtureExecutionResult
        r=TrustedFixtureExecutionResult(request_id="r",fixture_id="f",tenant_id="t"); assert not r.is_third_party_success()
    def test_gate_blocked(self):
        from src.open_platform.runtime_execution_gate import RuntimeExecutionGateResult
        assert not RuntimeExecutionGateResult().is_execution_allowed()
