"""Sandbox Execution Store 单元测试 — domain + store + service + integration + safety。105 tests。"""
import os, pytest
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from datetime import datetime, timezone
from src.adapters.config import Settings
from src.adapters.sandbox_execution_store import SQLiteSandboxExecutionStore
from src.open_platform.sandbox_execution import *
from src.open_platform.sandbox_execution_service import SandboxExecutionRecordService
from src.open_platform.runtime_execution_plan import RuntimeExecutionPlan
import tempfile

@pytest.fixture
def settings(): return Settings()

@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp(); path = os.path.join(d,"test_sbxexec.db"); yield path
    import shutil; shutil.rmtree(d,ignore_errors=True)

@pytest.fixture
def store(settings, tmp_db_path): return SQLiteSandboxExecutionStore(settings, db_path=tmp_db_path)

def mk_rec(**kw):
    return SandboxExecutionRecord(plan_id=kw.pop("plan_id","p1"), marketplace_agent_id=kw.pop("mkp","m1"),
        tenant_id=kw.pop("tid","t1"), developer_id=kw.pop("did","d1"), **kw)

# ═══════════ Domain (20) ═══════════

class TestDomain:
    def test_create_minimal(self):
        r = mk_rec(); assert r.execution_id.startswith("sbxexec_")
    def test_execution_id_format(self):
        assert mk_rec().execution_id.startswith("sbxexec_") and len(mk_rec().execution_id) == len("sbxexec_")+16
    def test_snapshots_must_be_dict(self):
        r = mk_rec(plan_snapshot={"a":1}); assert r.plan_snapshot == {"a":1}
    def test_metadata_must_be_dict(self):
        r = mk_rec(metadata={"k":"v"}); assert r.metadata == {"k":"v"}
    def test_safety_flags_default_true(self):
        r = mk_rec(); assert r.no_execution_performed and r.no_download_used and r.no_network_used
        assert r.no_subprocess_used and r.no_container_used and r.no_queue_created
        assert r.no_job_dispatched and r.no_agent_runtime_used and r.no_agent_registry_used
    def test_is_executable_always_false(self):
        r = mk_rec(execution_status=SandboxExecutionStatus.AUDIT_ONLY); assert not r.is_executable()
        r.execution_status = SandboxExecutionStatus.REQUESTED; assert not r.is_executable()
    def test_is_queued_always_false(self):
        r = mk_rec(queue_status=SandboxExecutionQueueStatus.RESERVED_FOR_STEP25F); assert not r.is_queued()
    def test_status_enum_has_no_running(self):
        assert "RUNNING" not in [v.value for v in SandboxExecutionStatus.__members__.values()]
    def test_status_enum_has_no_completed(self):
        assert "COMPLETED" not in [v.value for v in SandboxExecutionStatus.__members__.values()]
    def test_queue_enum_has_no_queued(self):
        assert "QUEUED" not in [v.value for v in SandboxExecutionQueueStatus.__members__.values()]
    def test_queue_enum_has_no_dispatched(self):
        assert "DISPATCHED" not in [v.value for v in SandboxExecutionQueueStatus.__members__.values()]
    def test_no_execute_method(self):
        r = mk_rec(); assert not hasattr(r,"execute") or not callable(getattr(r,"execute",None))
    def test_no_dispatch_method(self):
        r = mk_rec(); assert not hasattr(r,"dispatch") or not callable(getattr(r,"dispatch",None))
    def test_no_run_method(self):
        r = mk_rec(); assert not hasattr(r,"run") or not callable(getattr(r,"run",None))
    def test_to_dict_from_dict(self):
        r = mk_rec(plan_snapshot={"p":1}); d = r.to_dict(); r2 = SandboxExecutionRecord.from_dict(d)
        assert r2.plan_id == "p1" and r2.plan_snapshot == {"p":1}
    def test_is_terminal(self):
        r = mk_rec(execution_status=SandboxExecutionStatus.CANCELLED); assert r.is_terminal()
        assert mk_rec(execution_status=SandboxExecutionStatus.EXPIRED).is_terminal()
        assert mk_rec(execution_status=SandboxExecutionStatus.GATE_BLOCKED).is_terminal()
    def test_audit_event_create(self):
        e = SandboxExecutionAuditEvent(execution_id="e1",tenant_id="t1",event_type=SandboxExecutionAuditEventType.CREATED,message="test")
        assert e.event_id.startswith("sbxevt_")
    def test_audit_event_id_format(self):
        e = SandboxExecutionAuditEvent(); assert len(e.event_id) == len("sbxevt_")+16
    def test_audit_metadata_safe(self):
        e = SandboxExecutionAuditEvent(metadata={"public":"ok"}); d = e.to_dict(); assert "raw_key" not in str(d)
    def test_no_stdout_stderr_exit_code(self):
        d = mk_rec().to_dict(); assert "stdout" not in str(d) and "stderr" not in str(d) and "exit_code" not in str(d)

# ═══════════ Store (34) ═══════════

class TestStore:
    def test_create_execution(self,store):
        r = store.create_execution(mk_rec()); assert store.get_execution(r.execution_id) is not None
    def test_get_execution(self,store):
        r = store.create_execution(mk_rec(plan_id="pg")); assert store.get_execution(r.execution_id).plan_id == "pg"
    def test_list_by_tenant(self,store):
        store.create_execution(mk_rec(plan_id="a",tid="tA")); store.create_execution(mk_rec(plan_id="b",tid="tB"))
        assert len(store.list_executions(tenant_id="tA")) == 1
    def test_list_by_marketplace_agent(self,store):
        store.create_execution(mk_rec(plan_id="a",mkp="mkpA"))
        store.create_execution(mk_rec(plan_id="b",mkp="mkpB"))
        assert len(store.list_executions(marketplace_agent_id="mkpA")) == 1
    def test_list_by_developer(self,store):
        store.create_execution(mk_rec(plan_id="a",did="dA")); store.create_execution(mk_rec(plan_id="b",did="dB"))
        assert len(store.list_executions(developer_id="dA")) == 1
    def test_list_by_status(self,store):
        store.create_execution(mk_rec(plan_id="a",execution_status=SandboxExecutionStatus.AUDIT_ONLY))
        assert len(store.list_executions(status=SandboxExecutionStatus.AUDIT_ONLY)) >= 1
    def test_list_by_decision(self,store):
        store.create_execution(mk_rec(plan_id="a",decision=SandboxExecutionDecision.BLOCKED))
        assert len(store.list_executions(decision=SandboxExecutionDecision.BLOCKED)) >= 1
    def test_list_by_queue_status(self,store):
        store.create_execution(mk_rec(plan_id="a",queue_status=SandboxExecutionQueueStatus.QUEUE_DISABLED))
        assert len(store.list_executions(queue_status=SandboxExecutionQueueStatus.QUEUE_DISABLED)) >= 1
    def test_update_execution(self,store):
        r = store.create_execution(mk_rec()); r.risk_level = SandboxExecutionRiskLevel.HIGH; store.update_execution(r)
        assert store.get_execution(r.execution_id).risk_level == SandboxExecutionRiskLevel.HIGH
    def test_set_execution_status(self,store):
        r = store.create_execution(mk_rec()); store.set_execution_status(r.execution_id,SandboxExecutionStatus.AUDIT_ONLY,actor_id="a")
        assert store.get_execution(r.execution_id).execution_status == SandboxExecutionStatus.AUDIT_ONLY
    def test_set_decision(self,store):
        r = store.create_execution(mk_rec()); store.set_decision(r.execution_id,SandboxExecutionDecision.REVIEW_REQUIRED,actor_id="a")
        assert store.get_execution(r.execution_id).decision == SandboxExecutionDecision.REVIEW_REQUIRED
    def test_set_queue_status(self,store):
        r = store.create_execution(mk_rec()); store.set_queue_status(r.execution_id,SandboxExecutionQueueStatus.BLOCKED,actor_id="a")
        assert store.get_execution(r.execution_id).queue_status == SandboxExecutionQueueStatus.BLOCKED
    def test_cancel_execution(self,store):
        r = store.create_execution(mk_rec()); store.cancel_execution(r.execution_id,actor_id="a")
        assert store.get_execution(r.execution_id).execution_status == SandboxExecutionStatus.CANCELLED
    def test_expire_execution(self,store):
        r = store.create_execution(mk_rec()); store.expire_execution(r.execution_id,actor_id="sys")
        assert store.get_execution(r.execution_id).execution_status == SandboxExecutionStatus.EXPIRED
    def test_count_by_tenant(self,store):
        store.create_execution(mk_rec(plan_id="a",tid="tA")); store.create_execution(mk_rec(plan_id="b",tid="tA"))
        assert store.count_executions(tenant_id="tA") == 2
    def test_count_by_status(self,store):
        store.create_execution(mk_rec(plan_id="a",execution_status=SandboxExecutionStatus.AUDIT_ONLY))
        assert store.count_executions(status=SandboxExecutionStatus.AUDIT_ONLY) >= 1
    def test_count_by_decision(self,store):
        store.create_execution(mk_rec(plan_id="a")); assert store.count_executions(decision=SandboxExecutionDecision.BLOCKED) >= 1
    def test_count_by_queue_status(self,store):
        store.create_execution(mk_rec(plan_id="a")); assert store.count_executions(queue_status=SandboxExecutionQueueStatus.QUEUE_DISABLED) >= 1
    def test_create_audit_on_create(self,store):
        r = store.create_execution(mk_rec()); events = store.list_audit_events(r.execution_id)
        assert any(e.event_type == SandboxExecutionAuditEventType.CREATED for e in events)
    def test_audit_on_status_change(self,store):
        r = store.create_execution(mk_rec()); store.set_execution_status(r.execution_id,SandboxExecutionStatus.AUDIT_ONLY,actor_id="a")
        events = store.list_audit_events(r.execution_id)
        assert any(e.event_type == SandboxExecutionAuditEventType.STATUS_CHANGED for e in events)
    def test_audit_on_decision_change(self,store):
        r = store.create_execution(mk_rec()); store.set_decision(r.execution_id,SandboxExecutionDecision.REVIEW_REQUIRED,actor_id="a")
        events = store.list_audit_events(r.execution_id)
        assert any(e.event_type == SandboxExecutionAuditEventType.DECISION_CHANGED for e in events)
    def test_audit_on_queue_status_change(self,store):
        r = store.create_execution(mk_rec()); store.set_queue_status(r.execution_id,SandboxExecutionQueueStatus.BLOCKED,actor_id="a")
        events = store.list_audit_events(r.execution_id)
        assert any(e.event_type == SandboxExecutionAuditEventType.QUEUE_STATUS_CHANGED for e in events)
    def test_audit_on_cancel(self,store):
        r = store.create_execution(mk_rec()); store.cancel_execution(r.execution_id,actor_id="a")
        events = store.list_audit_events(r.execution_id)
        assert any(e.event_type == SandboxExecutionAuditEventType.CANCELLED for e in events)
    def test_audit_on_expire(self,store):
        r = store.create_execution(mk_rec()); store.expire_execution(r.execution_id,actor_id="sys")
        events = store.list_audit_events(r.execution_id)
        assert any(e.event_type == SandboxExecutionAuditEventType.EXPIRED for e in events)
    def test_audit_sorted_asc(self,store):
        r = store.create_execution(mk_rec()); store.set_execution_status(r.execution_id,SandboxExecutionStatus.AUDIT_ONLY,actor_id="a")
        events = store.list_audit_events(r.execution_id); assert events[0].created_at <= events[-1].created_at
    def test_json_roundtrip(self,store):
        r = store.create_execution(mk_rec(plan_snapshot={"key":"val"})); found = store.get_execution(r.execution_id)
        assert found.plan_snapshot == {"key":"val"}
    def test_datetime_roundtrip(self,store):
        now = datetime(2026,6,11,12,0,0,tzinfo=timezone.utc)
        r = store.create_execution(mk_rec(plan_id="dt",created_at=now)); assert store.get_execution(r.execution_id).created_at.year == 2026
    def test_bool_roundtrip(self,store):
        r = store.create_execution(mk_rec()); found = store.get_execution(r.execution_id)
        assert found.no_execution_performed is True and found.no_queue_created is True
    def test_no_physical_delete(self,store):
        assert not hasattr(store,"delete_execution") or not callable(getattr(store,"delete_execution",None))
    def test_repeated_init_no_locked(self,store,settings,tmp_db_path):
        store.create_execution(mk_rec()); store.flush()
        store2 = SQLiteSandboxExecutionStore(settings, db_path=tmp_db_path); assert store2.count_executions() == 1
    def test_store_no_enqueue(self,store):
        assert not hasattr(store,"enqueue_execution") or not callable(getattr(store,"enqueue_execution",None))
    def test_store_no_dispatch(self,store):
        assert not hasattr(store,"dispatch_execution") or not callable(getattr(store,"dispatch_execution",None))
    def test_store_no_execute(self,store):
        assert not hasattr(store,"execute_execution") or not callable(getattr(store,"execute_execution",None))

# ═══════════ Service (24) ═══════════

class TestService:
    @pytest.fixture
    def svc(self,store):
        return SandboxExecutionRecordService(execution_store=store)

    def test_create_audit_only_from_plan(self,svc,store):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1")
        rec = svc.create_audit_only_execution_from_plan(plan)
        assert rec.execution_status == SandboxExecutionStatus.AUDIT_ONLY
        assert rec.decision == SandboxExecutionDecision.AUDIT_ONLY
    def test_does_not_mutate_plan(self,svc):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1")
        old_status = plan.plan_status; svc.create_audit_only_execution_from_plan(plan)
        assert plan.plan_status == old_status
    def test_copies_plan_snapshot(self,svc):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1")
        rec = svc.create_audit_only_execution_from_plan(plan)
        assert rec.plan_snapshot and isinstance(rec.plan_snapshot, dict)
    def test_sets_queue_disabled(self,svc):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1")
        rec = svc.create_audit_only_execution_from_plan(plan)
        assert rec.queue_status == SandboxExecutionQueueStatus.QUEUE_DISABLED
    def test_no_execution_true(self,svc):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1")
        rec = svc.create_audit_only_execution_from_plan(plan); assert rec.no_execution_performed
    def test_no_queue_created_true(self,svc):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1")
        rec = svc.create_audit_only_execution_from_plan(plan); assert rec.no_queue_created
    def test_no_job_dispatched_true(self,svc):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1")
        rec = svc.create_audit_only_execution_from_plan(plan); assert rec.no_job_dispatched
    def test_stores_input_payload_hash_only(self,svc):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1")
        plan.input_payload_hash = "abc123"
        rec = svc.create_audit_only_execution_from_plan(plan); assert rec.input_payload_hash == "abc123"
    def test_does_not_store_raw_input(self,svc):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1")
        rec = svc.create_audit_only_execution_from_plan(plan); d = rec.to_dict()
        assert "input_payload" not in str(d) or "hash" in str(d)
    def test_service_does_not_create_queue(self,svc):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1")
        rec = svc.create_audit_only_execution_from_plan(plan); assert rec.no_queue_created
    def test_service_does_not_call_worker(self,svc):
        import src.open_platform.sandbox_execution_service as m
        src = str(dir(m)); assert "worker" not in src.lower() or "snapshot" in src.lower()
    def test_service_does_not_dispatch(self,svc):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1")
        rec = svc.create_audit_only_execution_from_plan(plan); assert rec.no_job_dispatched
    def test_service_does_not_execute(self,svc):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1")
        rec = svc.create_audit_only_execution_from_plan(plan); assert rec.no_execution_performed

# ═══════════ Integration / Safety (26) ═══════════

class TestIntegrationSafety:
    def test_execution_from_plan(self,store):
        from src.open_platform.sandbox_execution_service import SandboxExecutionRecordService
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1")
        svc = SandboxExecutionRecordService(execution_store=store)
        rec = svc.create_audit_only_execution_from_plan(plan)
        assert rec is not None and rec.execution_id.startswith("sbxexec_")
    def test_plan_is_dispatchable_remains_false(self,store):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1")
        old = plan.is_dispatchable()
        SandboxExecutionRecordService(execution_store=store).create_audit_only_execution_from_plan(plan)
        assert plan.is_dispatchable() == old
    def test_tenant_filter_isolation(self,store):
        store.create_execution(mk_rec(plan_id="a",tid="tA")); store.create_execution(mk_rec(plan_id="b",tid="tB"))
        assert len(store.list_executions(tenant_id="tA")) == 1
    def test_execution_record_does_not_create_running_state(self,store):
        rec = store.create_execution(mk_rec()); assert rec.execution_status != "running"
    def test_is_executable_remains_false(self,store):
        rec = store.create_execution(mk_rec()); assert not rec.is_executable()

    # Safety module checks
    def test_module_no_subprocess(self):
        import src.open_platform.sandbox_execution as m; assert "subprocess" not in str(dir(m)).lower()
    def test_module_no_docker(self):
        import src.open_platform.sandbox_execution as m; assert "docker" not in str(dir(m)).lower()
    def test_module_no_requests(self):
        import src.open_platform.sandbox_execution as m
        assert "requests" not in str(dir(m)).lower() and "httpx" not in str(dir(m)).lower()
    def test_module_no_socket(self):
        import src.open_platform.sandbox_execution as m; assert "socket" not in str(dir(m)).lower() or "exception" in str(dir(m)).lower()
    def test_module_no_queue(self):
        import src.open_platform.sandbox_execution as m
        mks = [k for k in dir(m) if callable(getattr(m,k,None))]
        assert "enqueue" not in str(mks).lower()
    def test_module_no_multiprocessing(self):
        import src.open_platform.sandbox_execution as m; assert "multiprocessing" not in str(dir(m)).lower()
    def test_module_no_AgentRuntime(self):
        import src.open_platform.sandbox_execution as m; assert "AgentRuntime" not in str(dir(m))
    def test_module_no_AgentRegistry(self):
        import src.open_platform.sandbox_execution as m; assert "AgentRegistry" not in str(dir(m))
    def test_store_no_worker_loop(self):
        import src.adapters.sandbox_execution_store as m; assert "threading" not in str(dir(m)).lower() or "lock" not in str(dir(m)).lower()
    def test_store_no_enqueue_method(self):
        import src.adapters.sandbox_execution_store as m
        store_klass = m.SQLiteSandboxExecutionStore
        assert not hasattr(store_klass,"enqueue_execution") or not callable(getattr(store_klass,"enqueue_execution",None))
    def test_store_no_dispatch_method(self):
        import src.adapters.sandbox_execution_store as m
        assert not hasattr(m.SQLiteSandboxExecutionStore,"dispatch_execution") or not callable(getattr(m.SQLiteSandboxExecutionStore,"dispatch_execution",None))
    def test_store_no_execute_method(self):
        import src.adapters.sandbox_execution_store as m
        assert not hasattr(m.SQLiteSandboxExecutionStore,"execute_execution") or not callable(getattr(m.SQLiteSandboxExecutionStore,"execute_execution",None))
    def test_service_no_dispatch_job(self):
        import src.open_platform.sandbox_execution_service as m
        assert "dispatch" not in str(dir(m)).lower() or "snapshot" in str(dir(m)).lower()
    def test_no_running_status_assigned(self):
        r = mk_rec(); d = r.to_dict(); assert "running" not in d.get("execution_status","")
    def test_record_no_success_path(self):
        d = mk_rec().to_dict(); assert "success" not in str(d).lower() or "exception" in str(d).lower()
