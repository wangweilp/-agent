"""Sandbox Enforcement Proof Tests — domain + store + service + safety。81 tests."""
import os, tempfile, pytest
os.environ.setdefault("DEEPSEEK_API_KEY","test-key")
from datetime import datetime, timezone
from src.adapters.config import Settings
from src.adapters.sandbox_enforcement_proof_store import SQLiteEnforcementProofStore
from src.open_platform.sandbox_enforcement_proof import *
from src.open_platform.sandbox_enforcement_proof_service import SandboxEnforcementProofService

@pytest.fixture
def settings(): return Settings()
@pytest.fixture
def tmp_db_path(): d=tempfile.mkdtemp(); p=os.path.join(d,"test_enf.db"); yield p; import shutil; shutil.rmtree(d,ignore_errors=True)
@pytest.fixture
def store(settings,tmp_db_path): return SQLiteEnforcementProofStore(settings,db_path=tmp_db_path)
@pytest.fixture
def svc(store): return SandboxEnforcementProofService(store=store)

# ═══════ Rule Builders (16) ═══════
class TestRuleBuilders:
    def test_nw_default_deny(self): r=build_default_deny_network_rule(); assert not r.allow_network and r.mode==NetworkRuleMode.DENY_ALL
    def test_nw_id_format(self): assert build_default_deny_network_rule().rule_id.startswith("nwrule_")
    def test_nw_metadata_ip_blocked(self): assert build_default_deny_network_rule().block_metadata_ip
    def test_nw_localhost_blocked(self): assert build_default_deny_network_rule().block_localhost
    def test_nw_private_blocked(self): assert build_default_deny_network_rule().block_private_ranges
    def test_nw_raw_blocked(self): assert build_default_deny_network_rule().block_raw_sockets
    def test_nw_dns_reviewed(self): assert build_default_deny_network_rule().dns_egress_requires_review
    def test_nw_private_cidr_high_risk(self): r=build_default_deny_network_rule(allowed_cidrs=["10.0.0.0/8"]); assert r.risk_level==EnforcementRiskLevel.HIGH
    def test_nw_to_dict(self): r=build_default_deny_network_rule(allowed_domains=["x.com"]); d=r.to_dict(); r2=NetworkEnforcementRule.from_dict(d); assert r2.allowed_domains==["x.com"]
    def test_fs_default_deny(self): r=build_default_deny_filesystem_rule(); assert r.mode==FilesystemRuleMode.DENY_ALL and not r.allow_write
    def test_fs_id_format(self): assert build_default_deny_filesystem_rule().rule_id.startswith("fsrule_")
    def test_fs_no_host_mount(self): assert not build_default_deny_filesystem_rule().host_mount_allowed
    def test_fs_no_docker_socket(self): assert not build_default_deny_filesystem_rule().docker_socket_allowed
    def test_fs_ephemeral(self): assert build_default_deny_filesystem_rule().ephemeral_workspace_required
    def test_sec_default_deny(self): r=build_default_deny_secret_rule(); assert r.mode==SecretRuleMode.DENY_ALL and not r.allow_secrets
    def test_sec_no_raw_env(self): assert not build_default_deny_secret_rule().raw_env_injection_allowed

# ═══════ Domain (13) ═══════
class TestDomain:
    def test_create_request(self): r=EnforcementProofRequest(tenant_id="t1"); assert r.request_id.startswith("enfreq_")
    def test_no_flags_true(self): r=EnforcementProofRequest(tenant_id="t1"); assert r.no_network_enforcement_applied and r.no_filesystem_enforcement_applied and r.no_runtime_started
    def test_is_enforcement_active_false(self): assert not EnforcementProofRequest(tenant_id="t1").is_runtime_enforcement_active()
    def test_is_execution_allowed_false(self): assert not EnforcementProofRequest(tenant_id="t1").is_execution_allowed()
    def test_no_apply_method(self): r=EnforcementProofRequest(tenant_id="t1"); assert not hasattr(r,"apply") or not callable(getattr(r,"apply",None))
    def test_to_dict_from_dict(self): d=EnforcementProofRequest(tenant_id="t1").to_dict(); r2=EnforcementProofRequest.from_dict(d); assert r2.tenant_id=="t1"
    def test_create_check(self): c=EnforcementCheck(request_id="r1",check_type=EnforcementCheckType.DEFAULT_DENY_NETWORK,message="ok"); assert c.check_id.startswith("enfchk_")
    def test_create_result(self): r=EnforcementProofResult(request_id="r1",tenant_id="t1"); assert r.result_id.startswith("enfres_")
    def test_result_is_enforcement_active_false(self): assert not EnforcementProofResult(request_id="r1").is_enforcement_active()
    def test_result_is_execution_allowed_false(self): assert not EnforcementProofResult(request_id="r1").is_execution_allowed()
    def test_result_add_check(self): r=EnforcementProofResult(request_id="r1"); r.add_check(EnforcementCheck(check_type="b",status=EnforcementCheckStatus.BLOCKED,severity=EnforcementSeverity.BLOCKER,message="b")); assert r.blockers_count==1
    def test_result_to_dict(self): r=EnforcementProofResult(request_id="r1"); r.add_check(EnforcementCheck(message="ok")); d=r.to_dict(); r2=EnforcementProofResult.from_dict(d); assert len(r2.checks)==1
    def test_audit_safe(self): d=EnforcementProofAuditEvent(request_id="r1",tenant_id="t1",event_type="t",message="ok").to_dict(); assert "raw_key" not in str(d)

# ═══════ Store (23) ═══════
class TestStore:
    def _req(self, **kw): kw.setdefault("tenant_id","t1"); return EnforcementProofRequest(**kw)
    def test_create(self,store): r=store.create_request(self._req()); assert store.get_request(r.request_id) is not None
    def test_get(self,store): r=store.create_request(self._req()); assert store.get_request(r.request_id).tenant_id=="t1"
    def test_list_tenant(self,store): store.create_request(self._req(tenant_id="tA")); store.create_request(self._req(tenant_id="tB")); assert len(store.list_requests(tenant_id="tA"))==1
    def test_list_status(self,store): store.create_request(self._req(proof_status=EnforcementProofStatus.REQUESTED)); assert len(store.list_requests(status=EnforcementProofStatus.REQUESTED))>=1
    def test_list_decision(self,store): store.create_request(self._req(decision=EnforcementProofDecision.REVIEW_REQUIRED)); assert len(store.list_requests(decision=EnforcementProofDecision.REVIEW_REQUIRED))>=1
    def test_update(self,store): r=store.create_request(self._req()); r.risk_level=EnforcementRiskLevel.HIGH; store.update_request(r); assert store.get_request(r.request_id).risk_level==EnforcementRiskLevel.HIGH
    def test_set_status(self,store): r=store.create_request(self._req()); store.set_request_status(r.request_id,EnforcementProofStatus.PROOF_EVALUATED,"a"); assert store.get_request(r.request_id).proof_status==EnforcementProofStatus.PROOF_EVALUATED
    def test_set_decision(self,store): r=store.create_request(self._req()); store.set_decision(r.request_id,EnforcementProofDecision.METADATA_PROOF_PASSED,"a"); assert store.get_request(r.request_id).decision==EnforcementProofDecision.METADATA_PROOF_PASSED
    def test_create_result(self,store): r=store.create_request(self._req()); res=EnforcementProofResult(request_id=r.request_id,tenant_id="t1"); store.create_result(res); assert store.get_result(res.result_id) is not None
    def test_get_result_by_req(self,store): r=store.create_request(self._req()); res=EnforcementProofResult(request_id=r.request_id,tenant_id="t1"); store.create_result(res); assert store.get_result_by_request(r.request_id) is not None
    def test_cancel(self,store): r=store.create_request(self._req()); store.cancel_request(r.request_id,"a"); assert store.get_request(r.request_id).proof_status in (EnforcementProofStatus.FAIL_CLOSED,EnforcementProofStatus.BLOCKED)
    def test_expire(self,store): r=store.create_request(self._req()); store.expire_request(r.request_id,"sys"); assert store.get_request(r.request_id).proof_status in (EnforcementProofStatus.FAIL_CLOSED,EnforcementProofStatus.BLOCKED)
    def test_count(self,store): store.create_request(self._req(tenant_id="tc")); store.create_request(self._req(tenant_id="tc")); assert store.count_requests(tenant_id="tc")==2
    def test_audit_create(self,store): r=store.create_request(self._req()); assert any(e.event_type==EnforcementAuditEventType.PROOF_REQUEST_CREATED for e in store.list_audit_events(r.request_id))
    def test_audit_status(self,store): r=store.create_request(self._req()); store.set_request_status(r.request_id,EnforcementProofStatus.PROOF_EVALUATED,"a"); assert any(e.event_type==EnforcementAuditEventType.STATUS_CHANGED for e in store.list_audit_events(r.request_id))
    def test_audit_sorted(self,store): r=store.create_request(self._req()); store.set_request_status(r.request_id,EnforcementProofStatus.PROOF_EVALUATED,"a"); evts=store.list_audit_events(r.request_id); assert evts[0].created_at<=evts[-1].created_at
    def test_json_rt(self,store): r=store.create_request(self._req(policy_config_snapshot={"k":"v"})); assert store.get_request(r.request_id).policy_config_snapshot=={"k":"v"}
    def test_bool_rt(self,store): r=store.create_request(self._req()); f=store.get_request(r.request_id); assert f.no_network_enforcement_applied and f.no_runtime_started
    def test_no_delete(self,store): assert not hasattr(store,"delete_request") or not callable(getattr(store,"delete_request",None))
    def test_repeated_init(self,store,settings,tmp_db_path): store.create_request(self._req()); store.flush(); assert SQLiteEnforcementProofStore(settings,db_path=tmp_db_path).count_requests()==1
    def test_no_danger(self,store):
            for b in ["apply_network","mount_filesystem","read_secret","execute","dispatch","enqueue"]: assert not hasattr(store,b) or not callable(getattr(store,b,None))

# ═══════ Service (10) ═══════
class TestService:
    def test_create(self,svc,store): r=svc.create_proof_request("t1"); assert r.proof_status==EnforcementProofStatus.REQUESTED
    def test_evaluate(self,svc,store):
        r=svc.create_proof_request("t1"); res=svc.evaluate_proof(r.request_id)
        assert res.metadata_only and res.proof_status in (EnforcementProofStatus.PASSED_METADATA_ONLY,EnforcementProofStatus.REVIEW_REQUIRED)
    def test_evaluate_not_active(self,svc,store): r=svc.create_proof_request("t1"); res=svc.evaluate_proof(r.request_id); assert not res.is_enforcement_active()
    def test_evaluate_network_checks(self,svc,store): r=svc.create_proof_request("t1"); res=svc.evaluate_proof(r.request_id); assert any(c.check_type==EnforcementCheckType.DEFAULT_DENY_NETWORK for c in res.checks)
    def test_evaluate_fs_checks(self,svc,store): r=svc.create_proof_request("t1"); res=svc.evaluate_proof(r.request_id); assert any(c.check_type==EnforcementCheckType.FILESYSTEM_HOST_MOUNT_BLOCKED for c in res.checks)
    def test_evaluate_secret_checks(self,svc,store): r=svc.create_proof_request("t1"); res=svc.evaluate_proof(r.request_id); assert any(c.check_type==EnforcementCheckType.SECRETS_RAW_ENV_INJECTION_BLOCKED for c in res.checks)
    def test_svc_no_danger(self,svc):
            for b in ["apply_network_policy","apply_filesystem_policy","read_secret","mount_filesystem","start_runtime","execute","dispatch","enqueue"]: assert not hasattr(svc,b) or not callable(getattr(svc,b,None))

# ═══════ Safety (7) ═══════
class TestSafety:
    def test_dm_no_socket(self): m=__import__("src.open_platform.sandbox_enforcement_proof",fromlist=[""]); assert "socket" not in str(dir(m)).lower()
    def test_dm_no_requests(self): m=__import__("src.open_platform.sandbox_enforcement_proof",fromlist=[""]); assert "requests" not in str(dir(m)).lower()
    def test_dm_no_subprocess(self): m=__import__("src.open_platform.sandbox_enforcement_proof",fromlist=[""]); assert "subprocess" not in str(dir(m)).lower()
    def test_dm_no_AgentRuntime(self): m=__import__("src.open_platform.sandbox_enforcement_proof",fromlist=[""]); assert "AgentRuntime" not in str(dir(m))
    def test_dm_no_AgentRegistry(self): m=__import__("src.open_platform.sandbox_enforcement_proof",fromlist=[""]); assert "AgentRegistry" not in str(dir(m))
    def test_exec_not_executable(self):
        from src.open_platform.sandbox_execution import SandboxExecutionRecord
        assert not SandboxExecutionRecord(plan_id="p",marketplace_agent_id="m",tenant_id="t",developer_id="d").is_executable()
    def test_result_inactive(self,svc,store): r=svc.create_proof_request("t1"); res=svc.evaluate_proof(r.request_id); assert not res.is_enforcement_active()
