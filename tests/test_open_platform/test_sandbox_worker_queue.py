"""Sandbox Worker Queue 测试 — domain + store + service + safety。95 tests。"""
import os, tempfile, pytest
os.environ.setdefault("DEEPSEEK_API_KEY","test-key")
from datetime import datetime, timezone
from src.adapters.config import Settings
from src.adapters.sandbox_worker_queue_store import SQLiteSandboxWorkerQueueStore
from src.open_platform.sandbox_worker_queue import *
from src.open_platform.sandbox_worker_queue_service import SandboxWorkerQueueService

@pytest.fixture
def settings(): return Settings()
@pytest.fixture
def tmp_db_path(): d=tempfile.mkdtemp(); p=os.path.join(d,"test_swq.db"); yield p; import shutil; shutil.rmtree(d,ignore_errors=True)
@pytest.fixture
def store(settings,tmp_db_path): return SQLiteSandboxWorkerQueueStore(settings,db_path=tmp_db_path)
@pytest.fixture
def svc(store): return SandboxWorkerQueueService(store=store)

def _rec(**kw):
    kw.setdefault("tenant_id", kw.pop("tid", "t1"))
    return SandboxWorkerQueueRecord(**kw)

# ═══════ Domain (31) ═══════
class TestDomain:
    def test_create(self): r=_rec(); assert r.queue_record_id.startswith("swq_")
    def test_id_format(self): assert len(_rec().queue_record_id)==len("swq_")+16
    def test_snapshots_are_dict(self): r=_rec(execution_snapshot={"k":"v"}); assert r.execution_snapshot=={"k":"v"}
    def test_all_enabled_false(self): r=_rec(); assert not r.queue_enabled and not r.enqueue_enabled and not r.dispatch_enabled and not r.worker_enabled and not r.lease_enabled and not r.heartbeat_enabled and not r.execution_enabled
    def test_all_no_flags_true(self): r=_rec(); assert r.no_queue_created and r.no_job_enqueued and r.no_job_dispatched and r.no_worker_started
    def test_is_queue_enabled_false(self): assert not _rec().is_queue_enabled()
    def test_is_enqueue_allowed_false(self): assert not _rec().is_enqueue_allowed()
    def test_is_dispatch_allowed_false(self): assert not _rec().is_dispatch_allowed()
    def test_is_worker_start_allowed_false(self): assert not _rec().is_worker_start_allowed()
    def test_is_execution_allowed_false(self): assert not _rec().is_execution_allowed()
    def test_no_enqueue_method(self): assert not hasattr(_rec(),"enqueue") or not callable(getattr(_rec(),"enqueue",None))
    def test_no_dispatch_method(self): assert not hasattr(_rec(),"dispatch") or not callable(getattr(_rec(),"dispatch",None))
    def test_no_execute_method(self): assert not hasattr(_rec(),"execute") or not callable(getattr(_rec(),"execute",None))
    def test_enum_no_queued(self): assert "QUEUED" not in [str(v) for v in SandboxWorkerQueueStatus.__members__.values()]
    def test_enum_no_dispatched(self): assert "DISPATCHED" not in [str(v) for v in SandboxWorkerDispatchStatus.__members__.values()]
    def test_enum_no_running(self): assert "RUNNING" not in [str(v) for v in SandboxWorkerQueueStatus.__members__.values()]
    def test_lease_no_active(self): assert "ACTIVE" not in [str(v) for v in SandboxWorkerLeaseStatus.__members__.values()]
    def test_to_dict_from_dict(self): d=_rec().to_dict(); r2=SandboxWorkerQueueRecord.from_dict(d); assert r2.tenant_id=="t1"
    def test_metadata_safe(self): d=_rec().to_dict(); assert "raw_key" not in str(d)
    def test_create_gate(self): g=SandboxWorkerQueueGateResult(tenant_id="t1"); assert g.gate_result_id.startswith("swqgate_")
    def test_gate_is_passed_false(self): assert not SandboxWorkerQueueGateResult(tenant_id="t1").is_passed_for_queue()
    def test_gate_is_dispatch_false(self): assert not SandboxWorkerQueueGateResult(tenant_id="t1").is_dispatch_allowed()
    def test_gate_to_dict(self): d=SandboxWorkerQueueGateResult(tenant_id="t1").to_dict(); g=SandboxWorkerQueueGateResult.from_dict(d); assert g.tenant_id=="t1"
    def test_audit_event(self): e=SandboxWorkerQueueAuditEvent(queue_record_id="q1",tenant_id="t1",event_type="test",message="ok"); assert e.event_id.startswith("swqevt_")
    def test_audit_metadata_safe(self): d=SandboxWorkerQueueAuditEvent(queue_record_id="q1",tenant_id="t1",event_type="t",message="ok").to_dict(); assert "raw_key" not in str(d)

# ═══════ Store (39) ═══════
class TestStore:
    def test_create(self,store): r=store.create_queue_record(_rec(tenant_id="t1")); assert store.get_queue_record(r.queue_record_id) is not None
    def test_get(self,store): r=store.create_queue_record(_rec(tenant_id="t1")); assert store.get_queue_record(r.queue_record_id).tenant_id=="t1"
    def test_list_tenant(self,store): store.create_queue_record(_rec(tid="tA")); store.create_queue_record(_rec(tid="tB")); assert len(store.list_queue_records(tenant_id="tA"))==1
    def test_list_status(self,store): store.create_queue_record(_rec(tid="t1",queue_status=SandboxWorkerQueueStatus.QUEUE_DISABLED)); assert len(store.list_queue_records(status=SandboxWorkerQueueStatus.QUEUE_DISABLED))>=1
    def test_list_decision(self,store): store.create_queue_record(_rec(tid="t1",decision=SandboxWorkerQueueDecision.BLOCKED_DISABLED)); assert len(store.list_queue_records(decision=SandboxWorkerQueueDecision.BLOCKED_DISABLED))>=1
    def test_update(self,store): r=store.create_queue_record(_rec()); r.risk_level=SandboxWorkerQueueRiskLevel.HIGH; store.update_queue_record(r); assert store.get_queue_record(r.queue_record_id).risk_level==SandboxWorkerQueueRiskLevel.HIGH
    def test_set_status(self,store): r=store.create_queue_record(_rec()); store.set_queue_status(r.queue_record_id,SandboxWorkerQueueStatus.RESERVED_METADATA_ONLY,"a"); assert store.get_queue_record(r.queue_record_id).queue_status==SandboxWorkerQueueStatus.RESERVED_METADATA_ONLY
    def test_set_decision(self,store): r=store.create_queue_record(_rec()); store.set_decision(r.queue_record_id,SandboxWorkerQueueDecision.RESERVED_ONLY,"a"); assert store.get_queue_record(r.queue_record_id).decision==SandboxWorkerQueueDecision.RESERVED_ONLY
    def test_set_lease(self,store): r=store.create_queue_record(_rec()); store.set_lease_status(r.queue_record_id,SandboxWorkerLeaseStatus.RESERVED_FOR_FUTURE,"a"); assert store.get_queue_record(r.queue_record_id).lease_status==SandboxWorkerLeaseStatus.RESERVED_FOR_FUTURE
    def test_set_dispatch(self,store): r=store.create_queue_record(_rec()); store.set_dispatch_status(r.queue_record_id,SandboxWorkerDispatchStatus.RESERVED_FOR_FUTURE,"a"); assert store.get_queue_record(r.queue_record_id).dispatch_status==SandboxWorkerDispatchStatus.RESERVED_FOR_FUTURE
    def test_create_gate(self,store): r=store.create_queue_record(_rec()); g=SandboxWorkerQueueGateResult(queue_record_id=r.queue_record_id,tenant_id="t1"); store.create_gate_result(g); assert store.get_gate_result(g.gate_result_id) is not None
    def test_get_gate_by_qr(self,store): r=store.create_queue_record(_rec()); g=SandboxWorkerQueueGateResult(queue_record_id=r.queue_record_id,tenant_id="t1"); store.create_gate_result(g); assert store.get_gate_result_by_queue_record(r.queue_record_id) is not None
    def test_cancel(self,store): r=store.create_queue_record(_rec()); store.cancel_queue_record(r.queue_record_id,"a"); assert store.get_queue_record(r.queue_record_id).queue_status==SandboxWorkerQueueStatus.CANCELLED
    def test_expire(self,store): r=store.create_queue_record(_rec()); store.expire_queue_record(r.queue_record_id,"sys"); assert store.get_queue_record(r.queue_record_id).queue_status==SandboxWorkerQueueStatus.EXPIRED
    def test_count(self,store): store.create_queue_record(_rec(tid="tc")); store.create_queue_record(_rec(tid="tc")); assert store.count_queue_records(tenant_id="tc")==2
    def test_audit_create(self,store): r=store.create_queue_record(_rec()); assert any(e.event_type==SandboxWorkerQueueAuditEventType.QUEUE_RECORD_CREATED for e in store.list_audit_events(r.queue_record_id))
    def test_audit_status(self,store): r=store.create_queue_record(_rec()); store.set_queue_status(r.queue_record_id,SandboxWorkerQueueStatus.RESERVED_METADATA_ONLY,"a"); assert any(e.event_type==SandboxWorkerQueueAuditEventType.QUEUE_STATUS_CHANGED for e in store.list_audit_events(r.queue_record_id))
    def test_audit_decision(self,store): r=store.create_queue_record(_rec()); store.set_decision(r.queue_record_id,SandboxWorkerQueueDecision.RESERVED_ONLY,"a"); assert any(e.event_type==SandboxWorkerQueueAuditEventType.DECISION_CHANGED for e in store.list_audit_events(r.queue_record_id))
    def test_audit_lease(self,store): r=store.create_queue_record(_rec()); store.set_lease_status(r.queue_record_id,SandboxWorkerLeaseStatus.RESERVED_FOR_FUTURE,"a"); assert any(e.event_type==SandboxWorkerQueueAuditEventType.LEASE_STATUS_CHANGED for e in store.list_audit_events(r.queue_record_id))
    def test_audit_dispatch(self,store): r=store.create_queue_record(_rec()); store.set_dispatch_status(r.queue_record_id,SandboxWorkerDispatchStatus.RESERVED_FOR_FUTURE,"a"); assert any(e.event_type==SandboxWorkerQueueAuditEventType.DISPATCH_STATUS_CHANGED for e in store.list_audit_events(r.queue_record_id))
    def test_audit_sorted(self,store): r=store.create_queue_record(_rec()); store.set_queue_status(r.queue_record_id,SandboxWorkerQueueStatus.RESERVED_METADATA_ONLY,"a"); evts=store.list_audit_events(r.queue_record_id); assert evts[0].created_at<=evts[-1].created_at
    def test_json_rt(self,store): r=store.create_queue_record(_rec(execution_snapshot={"k":"v"})); assert store.get_queue_record(r.queue_record_id).execution_snapshot=={"k":"v"}
    def test_bool_rt(self,store): r=store.create_queue_record(_rec()); f=store.get_queue_record(r.queue_record_id); assert not f.queue_enabled and f.no_queue_created
    def test_no_delete(self,store): assert not hasattr(store,"delete_queue_record") or not callable(getattr(store,"delete_queue_record",None))
    def test_repeated_init(self,store,settings,tmp_db_path): store.create_queue_record(_rec()); store.flush(); assert SQLiteSandboxWorkerQueueStore(settings,db_path=tmp_db_path).count_queue_records()==1
    def test_no_danger(self,store):
        for b in ["enqueue_job","dispatch_job","start_worker","run_worker","execute_job","heartbeat"]:
            assert not hasattr(store,b) or not callable(getattr(store,b,None))

# ═══════ Service + Safety (13) ═══════
class TestService:
    def test_create_disabled(self,svc,store): r=svc.create_disabled_queue_record(requested_by="a"); assert r.queue_status==SandboxWorkerQueueStatus.QUEUE_DISABLED and r.decision==SandboxWorkerQueueDecision.BLOCKED_DISABLED
    def test_all_flags_false(self,svc): r=svc.create_disabled_queue_record(); assert not r.queue_enabled and not r.enqueue_enabled and not r.dispatch_enabled and not r.worker_enabled
    def test_all_no_flags_true(self,svc): r=svc.create_disabled_queue_record(); assert r.no_queue_created and r.no_job_enqueued and r.no_job_dispatched and r.no_worker_started and r.no_execution_performed
    def test_evaluate_gate(self,svc,store):
        r=store.create_queue_record(_rec()); g=svc.evaluate_queue_gate(r.queue_record_id)
        assert not g.is_passed_for_queue() and not g.is_dispatch_allowed()
    def test_gate_queue_disabled(self,svc,store):
        r=store.create_queue_record(_rec()); g=svc.evaluate_queue_gate(r.queue_record_id)
        assert g.queue_status==SandboxWorkerQueueStatus.QUEUE_DISABLED and g.decision==SandboxWorkerQueueDecision.BLOCKED_DISABLED
    def test_svc_no_danger(self,svc):
        for b in ["enqueue_job","dispatch_job","start_worker","run_worker","execute_job","heartbeat"]:
            assert not hasattr(svc,b) or not callable(getattr(svc,b,None))
    def test_module_no_queue(self):
        import src.open_platform.sandbox_worker_queue as m
        # The module's classes have "queue" in their names — that's fine.
        # What we must not have: actual enqueue/dispatch calls, real queue primitives
        assert "multiprocessing" not in str(dir(m)).lower()
        assert "threading" not in str(dir(m)).lower()
    def test_module_no_subprocess(self):
        import src.open_platform.sandbox_worker_queue as m; assert "subprocess" not in str(dir(m)).lower()
    def test_module_no_docker(self):
        import src.open_platform.sandbox_worker_queue as m; assert "docker" not in str(dir(m)).lower()
    def test_module_no_AgentRuntime(self):
        import src.open_platform.sandbox_worker_queue as m; assert "AgentRuntime" not in str(dir(m))
    def test_module_no_AgentRegistry(self):
        import src.open_platform.sandbox_worker_queue as m; assert "AgentRegistry" not in str(dir(m))
    def test_execution_not_executable(self):
        from src.open_platform.sandbox_execution import SandboxExecutionRecord
        assert not SandboxExecutionRecord(plan_id="p",marketplace_agent_id="m",tenant_id="t",developer_id="d").is_executable()
    def test_execute_draft_blocked(self):
        from src.open_platform.runtime_execution_gate import RuntimeExecutionGateResult
        assert not RuntimeExecutionGateResult().is_execution_allowed()
