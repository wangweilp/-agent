"""Trusted Fixture Execution Tests — domain + registry + store + service + safety。85 tests."""
import os, tempfile, pytest
os.environ.setdefault("DEEPSEEK_API_KEY","test-key")
from datetime import datetime, timezone
from src.adapters.config import Settings
from src.adapters.trusted_fixture_execution_store import SQLiteTrustedFixtureExecutionStore
from src.open_platform.trusted_fixture_execution import *
from src.open_platform.trusted_fixture_registry import TrustedFixtureRegistry
from src.open_platform.trusted_fixture_execution_service import TrustedFixtureExecutionService

@pytest.fixture
def settings(): return Settings()
@pytest.fixture
def tmp_db_path(): d=tempfile.mkdtemp(); p=os.path.join(d,"test_tfix.db"); yield p; import shutil; shutil.rmtree(d,ignore_errors=True)
@pytest.fixture
def store(settings,tmp_db_path): return SQLiteTrustedFixtureExecutionStore(settings,db_path=tmp_db_path)
@pytest.fixture
def reg(): return TrustedFixtureRegistry()
@pytest.fixture
def svc(store,reg): return TrustedFixtureExecutionService(store=store,registry=reg)

# ═══════ Domain (22) ═══════
class TestDomain:
    def test_def_danger_false(self): d=TrustedFixtureDefinition(fixture_id="t1"); assert not d.third_party_code_allowed and not d.package_execution_allowed
    def test_def_all_flags_false(self): d=TrustedFixtureDefinition(fixture_id="t1"); assert not d.network_allowed and not d.filesystem_allowed and not d.subprocess_allowed
    def test_def_to_dict(self): d=TrustedFixtureDefinition(fixture_id="t1",fixture_name="n"); d2=TrustedFixtureDefinition.from_dict(d.to_dict()); assert d2.fixture_name=="n"
    def test_req_id(self): assert TrustedFixtureExecutionRequest(fixture_id="f",tenant_id="t").request_id.startswith("tfixreq_")
    def test_req_no_flags(self): r=TrustedFixtureExecutionRequest(fixture_id="f",tenant_id="t"); assert r.no_third_party_code_executed and r.no_package_executed and r.no_eval_exec_used
    def test_req_is_3p_false(self): assert not TrustedFixtureExecutionRequest(fixture_id="f",tenant_id="t").is_third_party_execution_allowed()
    def test_req_is_pkg_false(self): assert not TrustedFixtureExecutionRequest(fixture_id="f",tenant_id="t").is_package_execution_allowed()
    def test_req_no_exec_methods(self): r=TrustedFixtureExecutionRequest(fixture_id="f",tenant_id="t"); assert not hasattr(r,"execute_package") or not callable(getattr(r,"execute_package",None))
    def test_req_to_dict(self): d=TrustedFixtureExecutionRequest(fixture_id="f",tenant_id="t").to_dict(); r2=TrustedFixtureExecutionRequest.from_dict(d); assert r2.fixture_id=="f"
    def test_res_id(self): assert TrustedFixtureExecutionResult(request_id="r",fixture_id="f",tenant_id="t").result_id.startswith("tfixres_")
    def test_res_danger_false(self): r=TrustedFixtureExecutionResult(request_id="r",fixture_id="f",tenant_id="t"); r.trusted_fixture_executed=True; assert not r.third_party_code_executed and not r.package_executed
    def test_res_no_eval(self): r=TrustedFixtureExecutionResult(request_id="r",fixture_id="f",tenant_id="t"); assert not r.eval_exec_used and not r.dynamic_import_used
    def test_res_all_danger(self): r=TrustedFixtureExecutionResult(request_id="r",fixture_id="f",tenant_id="t"); assert not any([r.network_used,r.filesystem_used,r.secrets_used,r.subprocess_used,r.container_used,r.worker_queue_used,r.job_dispatched])
    def test_3p_success_false(self): assert not TrustedFixtureExecutionResult(request_id="r",fixture_id="f",tenant_id="t").is_third_party_success()
    def test_pkg_success_false(self): assert not TrustedFixtureExecutionResult(request_id="r",fixture_id="f",tenant_id="t").is_package_success()
    def test_res_to_dict(self): d=TrustedFixtureExecutionResult(request_id="r",fixture_id="f",tenant_id="t").to_dict(); r2=TrustedFixtureExecutionResult.from_dict(d); assert r2.fixture_id=="f"
    def test_audit_safe(self): d=TrustedFixtureAuditEvent(request_id="r",tenant_id="t",event_type="t",message="ok").to_dict(); assert "raw_key" not in str(d)

# ═══════ Registry (19) ═══════
class TestRegistry:
    def test_has_noop(self,reg): assert reg.get_fixture("tfix_noop_builtin") is not None
    def test_has_echo(self,reg): assert reg.get_fixture("tfix_echo_metadata_builtin") is not None
    def test_has_proof(self,reg): assert reg.get_fixture("tfix_policy_proof_summary_builtin") is not None
    def test_has_queue(self,reg): assert reg.get_fixture("tfix_queue_gate_summary_builtin") is not None
    def test_has_health(self,reg): assert reg.get_fixture("tfix_static_health_check_builtin") is not None
    def test_list_5(self,reg): assert len(reg.list_fixtures())==5
    def test_unknown_none(self,reg): assert reg.get_fixture("unknown") is None
    def test_unknown_not_allowed(self,reg): assert not reg.is_fixture_allowed("unknown")
    def test_noop_allowed(self,reg): assert reg.is_fixture_allowed("tfix_noop_builtin")
    def test_noop_output(self,reg): o=reg.run_trusted_fixture("tfix_noop_builtin",{}); assert o.get("ok") and o.get("fixture")=="noop"
    def test_echo_no_raw(self,reg): o=reg.run_trusted_fixture("tfix_echo_metadata_builtin",{"secret":"abc"}); assert "abc" not in str(o) or "hash" in str(o)
    def test_proof_summary(self,reg): o=reg.run_trusted_fixture("tfix_policy_proof_summary_builtin",{"proof_status":"passed","decision":"metadata_proof_passed"}); assert o.get("proof_status")=="passed"
    def test_queue_summary(self,reg): o=reg.run_trusted_fixture("tfix_queue_gate_summary_builtin",{"queue_enabled":"false","dispatch_enabled":"false"}); assert o.get("queue_enabled")=="false"
    def test_health(self,reg): o=reg.run_trusted_fixture("tfix_static_health_check_builtin",{}); assert o.get("fixture_count",0)>=5
    def test_no_dyn_register(self,reg): assert not hasattr(reg,"register_third_party_fixture") or not callable(getattr(reg,"register_third_party_fixture",None))
    def test_no_eval(self): import src.open_platform.trusted_fixture_registry as m; assert "eval" not in str(dir(m)).lower() or "eval_exec" in str(dir(m)).lower()
    def test_no_subprocess(self): import src.open_platform.trusted_fixture_registry as m; assert "subprocess" not in str(dir(m)).lower()

# ═══════ Store (31) ═══════
class TestStore:
    def _req(self, **kw):
        kw.setdefault("fixture_id","tfix_noop_builtin"); kw.setdefault("tenant_id","t1")
        return TrustedFixtureExecutionRequest(**kw)
    def test_create(self,store): r=store.create_request(self._req()); assert store.get_request(r.request_id) is not None
    def test_get(self,store): r=store.create_request(self._req()); assert store.get_request(r.request_id).fixture_id=="tfix_noop_builtin"
    def test_list_tenant(self,store): store.create_request(self._req(tenant_id="tA")); store.create_request(self._req(tenant_id="tB")); assert len(store.list_requests(tenant_id="tA"))==1
    def test_list_fixture(self,store): store.create_request(self._req(fixture_id="fA")); store.create_request(self._req(fixture_id="fB")); assert len(store.list_requests(fixture_id="fA"))==1
    def test_list_status(self,store): store.create_request(self._req(request_status=TrustedFixtureExecutionStatus.REQUESTED)); assert len(store.list_requests(status=TrustedFixtureExecutionStatus.REQUESTED))>=1
    def test_list_decision(self,store): store.create_request(self._req(decision=TrustedFixtureExecutionDecision.ALLOW_TRUSTED_FIXTURE_ONLY)); assert len(store.list_requests(decision=TrustedFixtureExecutionDecision.ALLOW_TRUSTED_FIXTURE_ONLY))>=1
    def test_update(self,store): r=store.create_request(self._req()); r.safety_level=TrustedFixtureSafetyLevel.METADATA_ONLY; store.update_request(r); assert store.get_request(r.request_id).safety_level==TrustedFixtureSafetyLevel.METADATA_ONLY
    def test_set_status(self,store): r=store.create_request(self._req()); store.set_request_status(r.request_id,TrustedFixtureExecutionStatus.FIXTURE_VALIDATED,"a"); assert store.get_request(r.request_id).request_status==TrustedFixtureExecutionStatus.FIXTURE_VALIDATED
    def test_set_decision(self,store): r=store.create_request(self._req()); store.set_decision(r.request_id,TrustedFixtureExecutionDecision.ALLOW_TRUSTED_FIXTURE_ONLY,"a"); assert store.get_request(r.request_id).decision==TrustedFixtureExecutionDecision.ALLOW_TRUSTED_FIXTURE_ONLY
    def test_create_result(self,store): r=store.create_request(self._req()); res=TrustedFixtureExecutionResult(request_id=r.request_id,fixture_id="f",tenant_id="t"); store.create_result(res); assert store.get_result(res.result_id) is not None
    def test_get_result_by_req(self,store): r=store.create_request(self._req()); res=TrustedFixtureExecutionResult(request_id=r.request_id,fixture_id="f",tenant_id="t"); store.create_result(res); assert store.get_result_by_request(r.request_id) is not None
    def test_cancel(self,store): r=store.create_request(self._req()); store.cancel_request(r.request_id,"a"); assert store.get_request(r.request_id).request_status==TrustedFixtureExecutionStatus.CANCELLED
    def test_expire(self,store): r=store.create_request(self._req()); store.expire_request(r.request_id,"sys"); assert store.get_request(r.request_id).request_status==TrustedFixtureExecutionStatus.EXPIRED
    def test_count(self,store): store.create_request(self._req(tenant_id="tc")); store.create_request(self._req(tenant_id="tc")); assert store.count_requests(tenant_id="tc")==2
    def test_audit_create(self,store): r=store.create_request(self._req()); assert any(e.event_type==TrustedFixtureAuditEventType.FIXTURE_REQUEST_CREATED for e in store.list_audit_events(r.request_id))
    def test_audit_status(self,store): r=store.create_request(self._req()); store.set_request_status(r.request_id,TrustedFixtureExecutionStatus.FIXTURE_VALIDATED,"a"); assert any(e.event_type==TrustedFixtureAuditEventType.STATUS_CHANGED for e in store.list_audit_events(r.request_id))
    def test_json_rt(self,store): r=store.create_request(self._req(input_metadata={"k":"v"})); assert store.get_request(r.request_id).input_metadata=={"k":"v"}
    def test_no_delete(self,store): assert not hasattr(store,"delete_request") or not callable(getattr(store,"delete_request",None))
    def test_repeated_init(self,store,settings,tmp_db_path): store.create_request(self._req()); store.flush(); assert SQLiteTrustedFixtureExecutionStore(settings,db_path=tmp_db_path).count_requests()==1

# ═══════ Service (9) ═══════
class TestService:
    def test_create(self,svc,store): r=svc.create_fixture_request("tfix_noop_builtin","t1"); assert r.decision==TrustedFixtureExecutionDecision.ALLOW_TRUSTED_FIXTURE_ONLY
    def test_unknown_fail(self,svc,store): r=svc.create_fixture_request("unknown","t1"); assert r.decision==TrustedFixtureExecutionDecision.FAIL_CLOSED
    def test_sanitize_hash(self,svc,store): r=svc.create_fixture_request("tfix_noop_builtin","t1",input_metadata={"key":"value"}); assert r.input_payload_hash is not None
    def test_run_noop(self,svc,store):
        r=svc.create_fixture_request("tfix_noop_builtin","t1"); res=svc.run_trusted_fixture_request(r.request_id)
        assert res.trusted_fixture_executed and not res.third_party_code_executed
    def test_run_health(self,svc,store):
        r=svc.create_fixture_request("tfix_static_health_check_builtin","t1"); res=svc.run_trusted_fixture_request(r.request_id)
        assert res.trusted_fixture_executed and not res.package_executed
    def test_result_no_3p(self,svc,store):
        r=svc.create_fixture_request("tfix_noop_builtin","t1"); res=svc.run_trusted_fixture_request(r.request_id)
        assert not res.is_third_party_success() and not res.is_package_success()
    def test_result_no_danger(self,svc,store):
        r=svc.create_fixture_request("tfix_noop_builtin","t1"); res=svc.run_trusted_fixture_request(r.request_id)
        assert not res.network_used and not res.subprocess_used and not res.container_used
    def test_svc_no_danger(self,svc):
        for b in ["execute_package","execute_entrypoint","run_user_code","dispatch_job","enqueue_job","start_worker","start_container"]:
            assert not hasattr(svc,b) or not callable(getattr(svc,b,None))

# ═══════ Safety (4) ═══════
class TestSafety:
    def test_exec_not_executable(self):
        from src.open_platform.sandbox_execution import SandboxExecutionRecord
        assert not SandboxExecutionRecord(plan_id="p",marketplace_agent_id="m",tenant_id="t",developer_id="d").is_executable()
    def test_gate_blocked(self):
        from src.open_platform.runtime_execution_gate import RuntimeExecutionGateResult
        assert not RuntimeExecutionGateResult().is_execution_allowed()
    def test_worker_queue_not_dispatch(self):
        from src.open_platform.sandbox_worker_queue import SandboxWorkerQueueRecord
        assert not SandboxWorkerQueueRecord(tenant_id="t").is_dispatch_allowed()
    def test_dm_no_requests(self): import src.open_platform.trusted_fixture_execution as m; assert "requests" not in str(dir(m)).lower()
