"""Runtime Kill Switch + Incident Store Tests — 80 tests。"""
import os, tempfile, pytest
os.environ.setdefault("DEEPSEEK_API_KEY","test-key")
from datetime import datetime, timezone
from src.adapters.config import Settings
from src.adapters.runtime_safety_store import SQLiteRuntimeSafetyStore
from src.open_platform.runtime_kill_switch import *
from src.open_platform.runtime_safety_service import RuntimeSafetyService

@pytest.fixture
def settings(): return Settings()
@pytest.fixture
def tmp_db_path(): d=tempfile.mkdtemp(); p=os.path.join(d,"test_rts.db"); yield p; import shutil; shutil.rmtree(d,ignore_errors=True)
@pytest.fixture
def store(settings,tmp_db_path): return SQLiteRuntimeSafetyStore(settings,db_path=tmp_db_path)
@pytest.fixture
def svc(store): return RuntimeSafetyService(store=store)

# ═══════ Domain (20) ═══════
class TestDomain:
    def test_policy_id(self): p=RuntimeKillSwitchPolicy(); assert p.policy_id.startswith("rks_")
    def test_policy_metadata_only(self): p=RuntimeKillSwitchPolicy(); assert p.enabled_metadata_only
    def test_policy_blocks_future(self): p=RuntimeKillSwitchPolicy(); assert p.blocks_future_runtime_admission and p.blocks_future_third_party_execution
    def test_policy_no_kill_impl(self): p=RuntimeKillSwitchPolicy(); assert not p.runtime_kill_implemented and not p.process_kill_implemented and not p.worker_kill_implemented
    def test_policy_to_dict(self): p=RuntimeKillSwitchPolicy(policy_name="t"); d=p.to_dict(); p2=RuntimeKillSwitchPolicy.from_dict(d); assert p2.policy_name=="t"
    def test_policy_metadata_safe(self): d=RuntimeKillSwitchPolicy().to_dict(); assert "raw_key" not in str(d)
    def test_trigger_id(self): t=RuntimeKillSwitchTrigger(policy_id="p"); assert t.trigger_id.startswith("rkstrg_")
    def test_trigger_no_kill_flags(self): t=RuntimeKillSwitchTrigger(policy_id="p"); assert t.no_process_killed and t.no_runtime_terminated and t.no_worker_stopped
    def test_trigger_is_kill_active_false(self): assert not RuntimeKillSwitchTrigger(policy_id="p").is_runtime_kill_active()
    def test_trigger_is_execution_allowed_false(self): assert not RuntimeKillSwitchTrigger(policy_id="p").is_execution_allowed()
    def test_trigger_to_dict(self): t=RuntimeKillSwitchTrigger(policy_id="p",reason="r"); d=t.to_dict(); t2=RuntimeKillSwitchTrigger.from_dict(d); assert t2.reason=="r"
    def test_incident_id(self): i=RuntimeIncidentRecord(incident_type="test"); assert i.incident_id.startswith("rinc_")
    def test_incident_no_kill_flags(self): i=RuntimeIncidentRecord(incident_type="test"); assert i.no_runtime_killed and i.no_process_killed and i.no_worker_stopped
    def test_incident_is_stopped_false(self): assert not RuntimeIncidentRecord(incident_type="test").is_runtime_stopped()
    def test_incident_is_exec_allowed_false(self): assert not RuntimeIncidentRecord(incident_type="test").is_execution_allowed()
    def test_incident_to_dict(self): i=RuntimeIncidentRecord(incident_type="test",title="t"); d=i.to_dict(); i2=RuntimeIncidentRecord.from_dict(d); assert i2.title=="t"
    def test_audit_event_id(self): e=RuntimeSafetyAuditEvent(event_type="test",message="ok"); assert e.event_id.startswith("rsaevt_")
    def test_audit_metadata_safe(self): d=RuntimeSafetyAuditEvent(event_type="t",message="ok").to_dict(); assert "raw_key" not in str(d)
    def test_trig_status_no_process_killed_absent(self):
        vs = [v.value for v in RuntimeKillSwitchStatus.__members__.values()]
        for bad in ["process_killed","runtime_terminated","worker_terminated","container_stopped","microvm_stopped"]: assert bad not in vs
    def test_trig_decision_no_kill_absent(self):
        vs = [v.value for v in RuntimeKillSwitchDecision.__members__.values()]
        for bad in ["process_killed","runtime_terminated","worker_terminated","container_stopped","microvm_stopped"]: assert bad not in vs
    def test_policy_container_microvm_no_kill_impl(self):
        p=RuntimeKillSwitchPolicy(); assert not p.container_stop_implemented and not p.microvm_stop_implemented
    def test_trigger_no_container_microvm_stop_flags(self):
        t=RuntimeKillSwitchTrigger(policy_id="p"); assert t.no_container_stopped and t.no_microvm_stopped and t.no_execution_performed and t.no_dispatch_performed and t.no_queue_modified
    def test_incident_no_execution_flag(self):
        i=RuntimeIncidentRecord(incident_type="t"); assert i.no_execution_performed

# ═══════ Store (30) ═══════
class TestStore:
    def _p(self, **kw): kw.setdefault("policy_name","test"); return RuntimeKillSwitchPolicy(**kw)
    def _t(self, **kw): return RuntimeKillSwitchTrigger(policy_id=kw.pop("policy_id","p1"),**kw)
    def _i(self, **kw): kw.setdefault("incident_type","test"); return RuntimeIncidentRecord(**kw)
    def test_create_policy(self,store): p=store.create_policy(self._p()); assert store.get_policy(p.policy_id) is not None
    def test_get_policy(self,store): p=store.create_policy(self._p(policy_name="get")); assert store.get_policy(p.policy_id).policy_name=="get"
    def test_list_policies_tenant(self,store): store.create_policy(self._p(tenant_id="tA")); store.create_policy(self._p(tenant_id="tB")); assert len(store.list_policies(tenant_id="tA"))==1
    def test_list_policies_scope(self,store): store.create_policy(self._p(scope=RuntimeKillSwitchScope.GLOBAL_RUNTIME)); assert len(store.list_policies(scope=RuntimeKillSwitchScope.GLOBAL_RUNTIME))>=1
    def test_update_policy(self,store): p=store.create_policy(self._p()); p.policy_name="updated"; store.update_policy(p); assert store.get_policy(p.policy_id).policy_name=="updated"
    def test_create_trigger(self,store): t=store.create_trigger(self._t()); assert store.get_trigger(t.trigger_id) is not None
    def test_get_trigger(self,store): t=store.create_trigger(self._t(policy_id="pget")); assert store.get_trigger(t.trigger_id).policy_id=="pget"
    def test_get_latest_trigger(self,store): store.create_trigger(self._t(policy_id="plat")); store.create_trigger(self._t(policy_id="plat")); assert store.get_latest_trigger("plat") is not None
    def test_release_trigger(self,store): p=store.create_policy(self._p(policy_id="prel")); t=store.create_trigger(self._t()); tr=store.release_trigger(t.trigger_id,"admin","ok"); assert tr.status==RuntimeKillSwitchStatus.RELEASED_METADATA_ONLY
    def test_create_incident(self,store): i=store.create_incident(self._i()); assert store.get_incident(i.incident_id) is not None
    def test_get_incident(self,store): i=store.create_incident(self._i(incident_type="get")); assert store.get_incident(i.incident_id).incident_type=="get"
    def test_list_incidents_tenant(self,store): store.create_incident(self._i(tenant_id="tA")); store.create_incident(self._i(tenant_id="tB")); assert len(store.list_incidents(tenant_id="tA"))==1
    def test_list_by_type(self,store): store.create_incident(self._i(incident_type="t1")); assert len(store.list_incidents(incident_type="t1"))>=1
    def test_list_by_severity(self,store): store.create_incident(self._i(severity=RuntimeIncidentSeverity.CRITICAL)); assert len(store.list_incidents(severity=RuntimeIncidentSeverity.CRITICAL))>=1
    def test_list_by_status(self,store): store.create_incident(self._i(status=RuntimeIncidentStatus.OPEN)); assert len(store.list_incidents(status=RuntimeIncidentStatus.OPEN))>=1
    def test_update_incident(self,store): i=store.create_incident(self._i()); i.severity=RuntimeIncidentSeverity.HIGH; store.update_incident(i); assert store.get_incident(i.incident_id).severity==RuntimeIncidentSeverity.HIGH
    def test_set_incident_status(self,store): i=store.create_incident(self._i()); store.set_incident_status(i.incident_id,RuntimeIncidentStatus.TRIAGED,"a"); assert store.get_incident(i.incident_id).status==RuntimeIncidentStatus.TRIAGED
    def test_set_incident_decision(self,store): i=store.create_incident(self._i()); store.set_incident_decision(i.incident_id,RuntimeIncidentDecision.RECORD_ONLY,"a"); assert store.get_incident(i.incident_id).decision==RuntimeIncidentDecision.RECORD_ONLY
    def test_triage(self,store): i=store.create_incident(self._i()); store.triage_incident(i.incident_id,"admin","triage note"); f=store.get_incident(i.incident_id); assert f.status==RuntimeIncidentStatus.TRIAGED and len(f.remediation_notes)>=1
    def test_close_metadata_only(self,store): i=store.create_incident(self._i()); store.close_incident_metadata_only(i.incident_id,"admin","closed"); f=store.get_incident(i.incident_id); assert f.status==RuntimeIncidentStatus.CLOSED_METADATA_ONLY
    def test_count_incidents(self,store): store.create_incident(self._i(tenant_id="tc")); store.create_incident(self._i(tenant_id="tc")); assert store.count_incidents(tenant_id="tc")==2
    def test_audit_policy_create(self,store): p=store.create_policy(self._p()); assert any(e.event_type==RuntimeSafetyAuditEventType.KILL_SWITCH_POLICY_CREATED for e in store.list_audit_events(policy_id=p.policy_id))
    def test_audit_trigger(self,store): t=store.create_trigger(self._t()); assert any(e.event_type==RuntimeSafetyAuditEventType.KILL_SWITCH_TRIGGERED_METADATA_ONLY for e in store.list_audit_events(trigger_id=t.trigger_id))
    def test_audit_sorted(self,store): i=store.create_incident(self._i()); store.triage_incident(i.incident_id,"a"); evts=store.list_audit_events(incident_id=i.incident_id); assert evts[0].created_at<=evts[-1].created_at
    def test_json_rt(self,store): p=store.create_policy(self._p(metadata={"k":"v"})); assert store.get_policy(p.policy_id).metadata=={"k":"v"}
    def test_bool_rt(self,store): p=store.create_policy(self._p()); f=store.get_policy(p.policy_id); assert f.enabled_metadata_only and not f.runtime_kill_implemented
    def test_no_delete(self,store):
            for m  in ["delete_policy","delete_incident","delete_trigger"]: assert not hasattr(store,m) or not callable(getattr(store,m,None))
    def test_repeated_init(self,store,settings,tmp_db_path): store.create_policy(self._p()); store.flush(); assert SQLiteRuntimeSafetyStore(settings,db_path=tmp_db_path).count_incidents()==0
    _DANGEROUS_METHODS = ["kill_process","terminate_runtime","stop_worker","stop_container","stop_microvm","execute_package","dispatch_job","enqueue_job","start_worker","register_agent","download_package","extract_archive","run_entrypoint","ensure_worker_running","ensure_container_running","ensure_microvm_running"]
    def test_store_no_kill_process(self,store): assert not hasattr(store,"kill_process")
    def test_store_no_terminate_runtime(self,store): assert not hasattr(store,"terminate_runtime")
    def test_store_no_stop_worker(self,store): assert not hasattr(store,"stop_worker")
    def test_store_no_stop_container(self,store): assert not hasattr(store,"stop_container")
    def test_store_no_stop_microvm(self,store): assert not hasattr(store,"stop_microvm")
    def test_store_no_execute_package(self,store): assert not hasattr(store,"execute_package")
    def test_store_no_dispatch_job(self,store): assert not hasattr(store,"dispatch_job")
    def test_store_no_enqueue_job(self,store): assert not hasattr(store,"enqueue_job")
    def test_store_no_start_worker(self,store): assert not hasattr(store,"start_worker")
    def test_store_no_register_agent(self,store): assert not hasattr(store,"register_agent")
    def test_store_no_dangerous_methods(self,store):
        names = [n for n in dir(store) if not n.startswith("_")]
        for bad in self._DANGEROUS_METHODS: assert bad not in names
    def test_store_trigger_has_no_kill_flags(self,store):
        t=store.create_trigger(self._t()); assert t.no_process_killed and t.no_runtime_terminated and t.no_worker_stopped and t.no_container_stopped and t.no_microvm_stopped and t.no_execution_performed and t.no_dispatch_performed and t.no_queue_modified
    def test_store_incident_has_no_kill_flags(self,store):
        i=store.create_incident(self._i()); assert i.no_runtime_killed and i.no_process_killed and i.no_worker_stopped and i.no_execution_performed
    def test_store_released_trigger_remains_metadata_only(self,store):
        t=store.create_trigger(self._t()); tr=store.release_trigger(t.trigger_id,"admin","ok"); assert tr.status==RuntimeKillSwitchStatus.RELEASED_METADATA_ONLY and tr.no_process_killed
    def test_store_closed_incident_not_runtime_fixed(self,store):
        i=store.create_incident(self._i()); ci=store.close_incident_metadata_only(i.incident_id,"a","done"); assert ci.status==RuntimeIncidentStatus.CLOSED_METADATA_ONLY and ci.no_runtime_killed and not ci.is_runtime_stopped()

# ═══════ Service (17) ═══════
class TestService:
    def test_create_default_policy(self,svc,store):
        p=svc.create_default_kill_switch_policy(tenant_id="t1",created_by="admin")
        assert p.blocks_future_third_party_execution and p.blocks_future_runtime_admission and not p.runtime_kill_implemented
    def test_default_policy_no_kill_impl(self,svc): p=svc.create_default_kill_switch_policy(); assert not p.runtime_kill_implemented and not p.process_kill_implemented and not p.worker_kill_implemented
    def test_trigger_metadata_only(self,svc,store):
        p=svc.create_default_kill_switch_policy(tenant_id="t1"); t=svc.trigger_kill_switch_metadata_only(p.policy_id,"test reason","actor1")
        assert t.status==RuntimeKillSwitchStatus.TRIGGERED_METADATA_ONLY and t.no_process_killed
    def test_trigger_no_kill(self,svc,store):
        p=svc.create_default_kill_switch_policy(tenant_id="t1"); t=svc.trigger_kill_switch_metadata_only(p.policy_id,"reason","a")
        assert t.no_process_killed and t.no_runtime_terminated and t.no_worker_stopped and t.no_container_stopped and t.no_microvm_stopped
    def test_release(self,svc,store):
        p=svc.create_default_kill_switch_policy(tenant_id="t1"); t=svc.trigger_kill_switch_metadata_only(p.policy_id,"r","a"); tr=svc.release_kill_switch_metadata_only(t.trigger_id,"admin","ok")
        assert tr.status==RuntimeKillSwitchStatus.RELEASED_METADATA_ONLY
    def test_create_incident(self,svc,store):
        i=svc.create_incident("test","high","T","D",tenant_id="t1")
        assert i.status==RuntimeIncidentStatus.OPEN and i.no_runtime_killed
    def test_critical_incident_triage(self,svc,store):
        i=svc.create_incident("test","critical","T","D",tenant_id="t1"); assert i.decision==RuntimeIncidentDecision.TRIAGE_REQUIRED
    def test_auto_trigger(self,svc,store):
        p=svc.create_default_kill_switch_policy(tenant_id="t1"); i=svc.create_incident("test","critical","T","D",tenant_id="t1")
        t=svc.auto_trigger_for_critical_incident(i.incident_id,p.policy_id,"admin"); assert t is not None and t.no_process_killed
    def test_auto_trigger_no_kill(self,svc,store):
        p=svc.create_default_kill_switch_policy(tenant_id="t1"); i=svc.create_incident("test","critical","T","D",tenant_id="t1")
        t=svc.auto_trigger_for_critical_incident(i.incident_id,p.policy_id,"admin"); assert t.no_process_killed and t.no_execution_performed
    def test_triage(self,svc,store): i=svc.create_incident("test","high","T","D"); tri=svc.triage_incident(i.incident_id,"a","note"); assert tri.status==RuntimeIncidentStatus.TRIAGED
    def test_close(self,svc,store): i=svc.create_incident("test","low","T","D"); ci=svc.close_incident_metadata_only(i.incident_id,"a","done"); assert ci.status==RuntimeIncidentStatus.CLOSED_METADATA_ONLY
    def test_exec_not_executable(self):
        from src.open_platform.sandbox_execution import SandboxExecutionRecord
        assert not SandboxExecutionRecord(plan_id="p",marketplace_agent_id="m",tenant_id="t",developer_id="d").is_executable()
    def test_kill_switch_not_active(self,svc,store):
        p=svc.create_default_kill_switch_policy(); t=svc.trigger_kill_switch_metadata_only(p.policy_id,"r","a"); assert not t.is_runtime_kill_active()
    def test_incident_not_runtime_stopped(self,svc,store):
        i=svc.create_incident("test","low","T","D"); assert not i.is_runtime_stopped()
    _DANGEROUS_METHODS = ["kill_process","terminate_runtime","stop_worker","stop_container","stop_microvm","execute_package","dispatch_job","enqueue_job","start_worker","register_agent","download_package","extract_archive","run_entrypoint"]
    def test_service_no_kill_process(self,svc): assert not hasattr(svc,"kill_process")
    def test_service_no_terminate_runtime(self,svc): assert not hasattr(svc,"terminate_runtime")
    def test_service_no_stop_worker(self,svc): assert not hasattr(svc,"stop_worker")
    def test_service_no_stop_container(self,svc): assert not hasattr(svc,"stop_container")
    def test_service_no_stop_microvm(self,svc): assert not hasattr(svc,"stop_microvm")
    def test_service_no_execute_package(self,svc): assert not hasattr(svc,"execute_package")
    def test_service_no_dispatch_job(self,svc): assert not hasattr(svc,"dispatch_job")
    def test_service_no_enqueue_job(self,svc): assert not hasattr(svc,"enqueue_job")
    def test_service_no_start_worker(self,svc): assert not hasattr(svc,"start_worker")
    def test_service_no_register_agent(self,svc): assert not hasattr(svc,"register_agent")
    def test_service_no_dangerous_methods(self,svc):
        names = [n for n in dir(svc) if not n.startswith("_")]
        for bad in self._DANGEROUS_METHODS: assert bad not in names
    def test_trigger_does_not_kill_process(self,svc,store):
        p=svc.create_default_kill_switch_policy(); t=svc.trigger_kill_switch_metadata_only(p.policy_id,"reason","a"); assert t.no_process_killed
    def test_trigger_does_not_terminate_runtime(self,svc,store):
        p=svc.create_default_kill_switch_policy(); t=svc.trigger_kill_switch_metadata_only(p.policy_id,"reason","a"); assert t.no_runtime_terminated
    def test_trigger_does_not_stop_worker_or_container(self,svc,store):
        p=svc.create_default_kill_switch_policy(); t=svc.trigger_kill_switch_metadata_only(p.policy_id,"reason","a"); assert t.no_worker_stopped and t.no_container_stopped and t.no_microvm_stopped
    def test_trigger_does_not_create_queue(self,svc,store):
        p=svc.create_default_kill_switch_policy(); t=svc.trigger_kill_switch_metadata_only(p.policy_id,"reason","a"); assert t.no_queue_modified
    def test_release_does_not_enable_runtime(self,svc,store):
        p=svc.create_default_kill_switch_policy(tenant_id="t1"); t=svc.trigger_kill_switch_metadata_only(p.policy_id,"r","a"); tr=svc.release_kill_switch_metadata_only(t.trigger_id,"admin","ok"); assert not tr.is_runtime_kill_active() and not tr.is_execution_allowed()
    def test_auto_trigger_returns_metadata_only(self,svc,store):
        p=svc.create_default_kill_switch_policy(tenant_id="t1"); i=svc.create_incident("test","critical","T","D",tenant_id="t1"); t=svc.auto_trigger_for_critical_incident(i.incident_id,p.policy_id,"admin"); assert t is not None and t.status==RuntimeKillSwitchStatus.TRIGGERED_METADATA_ONLY
    def test_close_incident_not_runtime_fixed(self,svc,store):
        i=svc.create_incident("test","low","T","D"); ci=svc.close_incident_metadata_only(i.incident_id,"a","done"); assert ci.status==RuntimeIncidentStatus.CLOSED_METADATA_ONLY; assert ci.no_runtime_killed; assert not ci.is_runtime_stopped()
    def test_close_incident_does_not_enable_execution(self,svc,store):
        i=svc.create_incident("test","low","T","D"); ci=svc.close_incident_metadata_only(i.incident_id,"a","done"); assert not ci.is_execution_allowed()
    def test_service_default_policy_all_no_kill_impl(self,svc):
        p=svc.create_default_kill_switch_policy(); assert not p.runtime_kill_implemented and not p.process_kill_implemented and not p.worker_kill_implemented and not p.container_stop_implemented and not p.microvm_stop_implemented

# ═══════ Safety (8) ═══════
class TestSafety:
    def test_dm_no_subprocess(self): import src.open_platform.runtime_kill_switch as m; assert "subprocess" not in str(dir(m)).lower()
    def test_dm_no_os_kill(self):
        import src.open_platform.runtime_kill_switch as m
        # kill_switch is our domain name; os.kill/signal must not be imported
        assert "'os.kill'" not in str(dir(m)).lower() and "'signal'" not in str(dir(m)).lower()
    def test_dm_no_signal(self): import src.open_platform.runtime_kill_switch as m; assert "signal" not in str(dir(m)).lower()
    def test_dm_no_requests(self): import src.open_platform.runtime_kill_switch as m; assert "requests" not in str(dir(m)).lower()
    def test_dm_no_AgentRuntime(self): import src.open_platform.runtime_kill_switch as m; assert "AgentRuntime" not in str(dir(m))
    def test_gate_blocked(self):
        from src.open_platform.runtime_execution_gate import RuntimeExecutionGateResult
        assert not RuntimeExecutionGateResult().is_execution_allowed()
    def test_trigger_kill_always_false(self):
        t=RuntimeKillSwitchTrigger(policy_id="p",status=RuntimeKillSwitchStatus.TRIGGERED_METADATA_ONLY); assert not t.is_runtime_kill_active()
    def test_incident_stopped_always_false(self):
        i=RuntimeIncidentRecord(incident_type="t",status=RuntimeIncidentStatus.CLOSED_METADATA_ONLY); assert not i.is_runtime_stopped()
    def test_dm_no_multiprocessing(self): import src.open_platform.runtime_kill_switch as m; assert "multiprocessing" not in str(dir(m)).lower()
    def test_dm_no_threading(self): import src.open_platform.runtime_kill_switch as m; assert "threading" not in str(dir(m)).lower()
    def test_dm_no_docker(self): import src.open_platform.runtime_kill_switch as m; assert "docker" not in str(dir(m)).lower()
    def test_dm_no_httpx(self): import src.open_platform.runtime_kill_switch as m; assert "httpx" not in str(dir(m)).lower()
    def test_service_module_no_subprocess(self): import src.open_platform.runtime_safety_service as s; assert "subprocess" not in str(dir(s)).lower()
    def test_service_module_no_os_kill(self): import src.open_platform.runtime_safety_service as s; assert "os.kill" not in str(dir(s)).lower() and "signal" not in str(dir(s)).lower()
    def test_store_module_no_subprocess(self): import src.adapters.runtime_safety_store as st; assert "subprocess" not in str(dir(st)).lower()
    def test_store_module_no_os_kill(self): import src.adapters.runtime_safety_store as st; assert "os.kill" not in str(dir(st)).lower() and "signal" not in str(dir(st)).lower()
    def test_store_module_no_AgentRuntime(self): import src.adapters.runtime_safety_store as st; assert "AgentRuntime" not in str(dir(st))
    def test_store_module_no_requests(self): import src.adapters.runtime_safety_store as st; assert "requests" not in str(dir(st)).lower()
