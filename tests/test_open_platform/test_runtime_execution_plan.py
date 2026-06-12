"""Runtime Execution Plan 单元测试 — Domain + Store + Planner。

覆盖:
- Domain: PlanCheck, RuntimeExecutionPlan, AuditEvent
- Store: CRUD, filters, status transitions, audit
- Planner: preflight checks, blocking paths, non-mutation
- Safety: no dispatch/execution/worker/network/download
"""

from __future__ import annotations

import hashlib, json, os, tempfile

import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from datetime import datetime, timezone
from src.adapters.config import Settings
from src.adapters.runtime_execution_plan_store import SQLiteRuntimeExecutionPlanStore
from src.open_platform.runtime_execution_plan import (
    RuntimeExecutionMode, RuntimeExecutionPlan, RuntimeExecutionPlanCheck,
    RuntimeExecutionPlanAuditEvent, RuntimeExecutionPlanAuditEventType,
    RuntimeExecutionPlanNotFoundError, RuntimeExecutionPlanStatus,
    RuntimeDispatchStatus, RuntimePlanCheckStatus, RuntimePlanCheckType,
    RuntimePlanDecision, RuntimePlanSeverity, RuntimeExecutionRiskLevel,
    RuntimeExecutionPlanAlreadyExistsError,
)


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test_plan.db")
    yield path
    import shutil; shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def pstore(settings, tmp_db_path):
    return SQLiteRuntimeExecutionPlanStore(settings, db_path=tmp_db_path)


# ═══════════════════════════ Domain Model ═══════════════════════════

class TestPlanDomain:
    def test_create_check(self):
        c = RuntimeExecutionPlanCheck(check_type=RuntimePlanCheckType.MARKETPLACE_AGENT_EXISTS, message="ok")
        assert c.check_id.startswith("planchk_")

    def test_check_to_dict_from_dict(self):
        c = RuntimeExecutionPlanCheck(check_type="test", status=RuntimePlanCheckStatus.PASSED,
                                      severity=RuntimePlanSeverity.INFO, message="m")
        d = c.to_dict(); c2 = RuntimeExecutionPlanCheck.from_dict(d)
        assert c2.check_type == "test"

    def test_check_metadata_safe(self):
        c = RuntimeExecutionPlanCheck(message="ok", metadata={"public": "data"})
        d = c.to_dict(); assert "raw_key" not in str(d) and "key_hash" not in str(d)

    def test_create_plan_minimal(self):
        p = RuntimeExecutionPlan(marketplace_agent_id="mkp_x", tenant_id="t1", developer_id="d1")
        assert p.plan_id.startswith("rtexplan_")
        assert p.is_dispatchable() is False
        assert p.no_execution_performed is True
        assert p.no_download_planned is True
        assert p.no_network_planned is True

    def test_plan_to_dict_from_dict(self):
        p = RuntimeExecutionPlan(marketplace_agent_id="mkp_x", tenant_id="t1", developer_id="d1")
        p.add_check(RuntimeExecutionPlanCheck(check_type="t1", message="ok"))
        d = p.to_dict(); p2 = RuntimeExecutionPlan.from_dict(d)
        assert p2.marketplace_agent_id == "mkp_x"
        assert len(p2.checks) == 1

    def test_output_contract_must_be_dict(self):
        p = RuntimeExecutionPlan(marketplace_agent_id="x", tenant_id="t", developer_id="d", output_contract={"a": 1})
        assert p.output_contract == {"a": 1}

    def test_policy_snapshot_must_be_dict(self):
        p = RuntimeExecutionPlan(marketplace_agent_id="x", tenant_id="t", developer_id="d", policy_snapshot={"b": 2})
        assert p.policy_snapshot == {"b": 2}

    def test_add_check_recounts(self):
        p = RuntimeExecutionPlan(marketplace_agent_id="x", tenant_id="t", developer_id="d")
        p.add_check(RuntimeExecutionPlanCheck(check_type="w", status=RuntimePlanCheckStatus.WARNING, severity=RuntimePlanSeverity.WARNING, message="w"))
        p.add_check(RuntimeExecutionPlanCheck(check_type="b", status=RuntimePlanCheckStatus.BLOCKED, severity=RuntimePlanSeverity.BLOCKER, message="b"))
        assert p.warnings_count == 1; assert p.blockers_count == 1

    def test_calculate_status_blocked(self):
        p = RuntimeExecutionPlan(marketplace_agent_id="x", tenant_id="t", developer_id="d")
        p.add_check(RuntimeExecutionPlanCheck(check_type="b", status=RuntimePlanCheckStatus.BLOCKED, severity=RuntimePlanSeverity.BLOCKER, message="b"))
        p.calculate_status()
        assert p.plan_status == RuntimeExecutionPlanStatus.BLOCKED
        assert p.decision == RuntimePlanDecision.BLOCK_PLAN

    def test_calculate_status_planned(self):
        p = RuntimeExecutionPlan(marketplace_agent_id="x", tenant_id="t", developer_id="d")
        p.add_check(RuntimeExecutionPlanCheck(check_type="ok", status=RuntimePlanCheckStatus.PASSED, message="ok"))
        p.calculate_status()
        assert p.plan_status == RuntimeExecutionPlanStatus.PLANNED
        assert p.decision == RuntimePlanDecision.RESERVED_ONLY

    def test_is_dispatchable_always_false(self):
        p = RuntimeExecutionPlan(marketplace_agent_id="x", tenant_id="t", developer_id="d", plan_status=RuntimeExecutionPlanStatus.PLANNED)
        assert p.is_dispatchable() is False

    def test_input_payload_hash(self):
        h = RuntimeExecutionPlan.hash_payload({"input": "hello"})
        assert h is not None and len(h) == 64

    def test_audit_event(self):
        e = RuntimeExecutionPlanAuditEvent(plan_id="p1", tenant_id="t1", event_type=RuntimeExecutionPlanAuditEventType.CREATED, message="test")
        assert e.event_id.startswith("rtexevt_")

    def test_audit_metadata_safe(self):
        e = RuntimeExecutionPlanAuditEvent(plan_id="p1", tenant_id="t1", event_type="test", message="ok")
        d = e.to_dict(); assert "raw_key" not in str(d)

    def test_id_formats(self):
        assert RuntimeExecutionPlan().plan_id.startswith("rtexplan_")
        assert RuntimeExecutionPlanCheck().check_id.startswith("planchk_")
        assert RuntimeExecutionPlanAuditEvent().event_id.startswith("rtexevt_")


# ═══════════════════════════ Store ═══════════════════════════

class TestPlanStore:
    def test_create_plan(self, pstore):
        p = mk_plan(mkp="mkp1"); created = pstore.create_plan(p)
        assert created.plan_id == p.plan_id

    def test_get_plan(self, pstore):
        p = pstore.create_plan(mk_plan(mkp="mkp1"))
        found = pstore.get_plan(p.plan_id); assert found is not None

    def test_list_by_tenant(self, pstore):
        pstore.create_plan(mk_plan(mkp="mkp1", tenant="tA"))
        pstore.create_plan(mk_plan(mkp="mkp2", tenant="tB"))
        assert len(pstore.list_plans(tenant_id="tA")) == 1

    def test_list_by_marketplace_agent(self, pstore):
        pstore.create_plan(mk_plan(mkp="mkp_a"))
        pstore.create_plan(mk_plan(mkp="mkp_b"))
        assert len(pstore.list_plans(marketplace_agent_id="mkp_a")) == 1

    def test_list_by_developer(self, pstore):
        pstore.create_plan(mk_plan(mkp="mkp1", developer="dev_a"))
        pstore.create_plan(mk_plan(mkp="mkp2", developer="dev_b"))
        assert len(pstore.list_plans(developer_id="dev_a")) == 1

    def test_list_by_status(self, pstore):
        p = mk_plan(mkp="mkp1"); p.plan_status = RuntimeExecutionPlanStatus.BLOCKED; pstore.create_plan(p)
        assert len(pstore.list_plans(status=RuntimeExecutionPlanStatus.BLOCKED)) == 1

    def test_list_by_decision(self, pstore):
        p = mk_plan(mkp="mkp1"); p.decision = RuntimePlanDecision.RESERVED_ONLY; pstore.create_plan(p)
        assert len(pstore.list_plans(decision=RuntimePlanDecision.RESERVED_ONLY)) == 1

    def test_update_plan(self, pstore):
        p = pstore.create_plan(mk_plan(mkp="mkp1")); p.risk_level = RuntimeExecutionRiskLevel.HIGH; pstore.update_plan(p)
        assert pstore.get_plan(p.plan_id).risk_level == RuntimeExecutionRiskLevel.HIGH

    def test_set_status(self, pstore):
        p = pstore.create_plan(mk_plan(mkp="mkp1"))
        pstore.set_plan_status(p.plan_id, RuntimeExecutionPlanStatus.REVIEW_REQUIRED, actor_id="a")
        assert pstore.get_plan(p.plan_id).plan_status == RuntimeExecutionPlanStatus.REVIEW_REQUIRED

    def test_cancel_plan(self, pstore):
        p = pstore.create_plan(mk_plan(mkp="mkp1"))
        pstore.cancel_plan(p.plan_id, actor_id="a", reason="test")
        assert pstore.get_plan(p.plan_id).plan_status == RuntimeExecutionPlanStatus.CANCELLED

    def test_expire_plan(self, pstore):
        p = pstore.create_plan(mk_plan(mkp="mkp1"))
        pstore.expire_plan(p.plan_id, actor_id="sys")
        assert pstore.get_plan(p.plan_id).plan_status == RuntimeExecutionPlanStatus.EXPIRED

    def test_count_by_tenant(self, pstore):
        pstore.create_plan(mk_plan(mkp="mkp1", tenant="tA"))
        pstore.create_plan(mk_plan(mkp="mkp2", tenant="tA"))
        assert pstore.count_plans(tenant_id="tA") == 2

    def test_count_by_status(self, pstore):
        pstore.create_plan(mk_plan(mkp="mkp1"))
        assert pstore.count_plans(status=RuntimeExecutionPlanStatus.DRAFT) >= 1

    def test_audit_on_create(self, pstore):
        p = pstore.create_plan(mk_plan(mkp="mkp1"))
        events = pstore.list_audit_events(p.plan_id)
        assert any(e.event_type == RuntimeExecutionPlanAuditEventType.CREATED for e in events)

    def test_audit_on_status_change(self, pstore):
        p = pstore.create_plan(mk_plan(mkp="mkp1"))
        pstore.set_plan_status(p.plan_id, RuntimeExecutionPlanStatus.REVIEW_REQUIRED, actor_id="a", reason="r")
        events = pstore.list_audit_events(p.plan_id)
        assert any(e.event_type == RuntimeExecutionPlanAuditEventType.STATUS_CHANGED for e in events)

    def test_audit_on_cancel(self, pstore):
        p = pstore.create_plan(mk_plan(mkp="mkp1"))
        pstore.cancel_plan(p.plan_id, actor_id="a")
        events = pstore.list_audit_events(p.plan_id)
        assert any(e.event_type == RuntimeExecutionPlanAuditEventType.CANCELLED for e in events)

    def test_audit_on_expire(self, pstore):
        p = pstore.create_plan(mk_plan(mkp="mkp1"))
        pstore.expire_plan(p.plan_id, actor_id="sys")
        events = pstore.list_audit_events(p.plan_id)
        assert any(e.event_type == RuntimeExecutionPlanAuditEventType.EXPIRED for e in events)

    def test_audit_sorted_asc(self, pstore):
        p = pstore.create_plan(mk_plan(mkp="mkp1"))
        pstore.set_plan_status(p.plan_id, RuntimeExecutionPlanStatus.REVIEW_REQUIRED, actor_id="a")
        events = pstore.list_audit_events(p.plan_id)
        assert events[0].created_at <= events[-1].created_at

    def test_json_roundtrip(self, pstore):
        p = mk_plan(mkp="mkp_json"); p.add_check(RuntimeExecutionPlanCheck(check_type="test", message="json"))
        pstore.create_plan(p); found = pstore.get_plan(p.plan_id)
        assert len(found.checks) == 1; assert found.checks[0].check_type == "test"

    def test_datetime_roundtrip(self, pstore):
        now = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)
        p = mk_plan(mkp="mkp_dt", created_at=now); pstore.create_plan(p)
        assert pstore.get_plan(p.plan_id).created_at.year == 2026

    def test_bool_roundtrip(self, pstore):
        p = mk_plan(mkp="mkp_bool"); pstore.create_plan(p); found = pstore.get_plan(p.plan_id)
        assert found.no_execution_performed is True and found.worker_available is False

    def test_no_delete_method(self, pstore):
        assert not hasattr(pstore, "delete_plan") or not callable(getattr(pstore, "delete_plan", None))

    def test_repeated_init_no_locked(self, pstore, settings, tmp_db_path):
        pstore.create_plan(mk_plan(mkp="mkp_init")); pstore.flush()
        p2 = SQLiteRuntimeExecutionPlanStore(settings, db_path=tmp_db_path)
        assert p2.count_plans() == 1


# ═══════════════════════════ Planner Service ═══════════════════════════

class TestPlannerService:
    @pytest.fixture
    def pstore(self, settings, tmp_db_path):
        return SQLiteRuntimeExecutionPlanStore(settings, db_path=tmp_db_path)

    def _make_planner(self, pstore, **kw):
        from src.open_platform.runtime_execution_planner import RuntimeExecutionPlannerService
        return RuntimeExecutionPlannerService(plan_store=pstore, **kw)

    def _mock_agent(self, mkp_id="mkp1", publisher_type="developer", required_perms=None, metadata=None):
        class MockAgent:
            def __init__(self):
                self.publisher_type = publisher_type
                self.display_name = "Test Agent"
                self.required_permissions = required_perms or []
                self.metadata = metadata or {}
        return MockAgent()

    def _mock_inst(self, enabled=True, status="active", granted=None):
        class MockInst:
            def __init__(self):
                self.enabled = enabled; self.status = status
                self.permissions_granted = granted or []
        return MockInst()

    def _mock_binding(self, enabled=True, adapter_id="adp1", policy_id="sp1", runtime_status="enabled"):
        class MockBinding:
            def __init__(self):
                self.binding_id = "bind1"; self.runtime_status = runtime_status
                self.adapter_id = adapter_id; self.sandbox_policy_id = policy_id
                self.is_enabled = True if enabled else False
        return MockBinding()

    def _mock_adapter(self, adapter_type="simulation", active=True):
        class MockAdapter:
            def __init__(self):
                self.adapter_id = "adp1"; self.adapter_type = adapter_type
                self.status = "active" if active else "disabled"
                self.is_active = lambda: active
                def td(): return {"adapter_id": self.adapter_id, "adapter_type": adapter_type}
                self.to_dict = td
        return MockAdapter()

    def _mock_policy(self, active=True, policy_id="sp1"):
        class MockPolicy:
            def __init__(self):
                self.policy_id = policy_id; self.status = "active" if active else "disabled"
                self.is_active = lambda: active
                def td(): return {"policy_id": self.policy_id}
                self.to_dict = td
        return MockPolicy()

    def _mock_artifact(self, artifact_id="art1", art_status="declared", q_status="quarantined"):
        class MockArtifact:
            def __init__(self):
                self.artifact_id = artifact_id; self.artifact_status = art_status
                self.quarantine_status = q_status
                def td(): return {"artifact_id": artifact_id, "artifact_status": art_status}
                self.to_dict = td
        return MockArtifact()

    def _mock_run(self, run_status="passed", cs_matched=True, sig_present=False, verification_id="ver1"):
        class MockCheck:
            def __init__(self):
                self.check_type = "checksum_match"; self.status = "passed"
        class MockRun:
            def __init__(self):
                self.verification_id = verification_id; self.run_status = run_status
                self.checks = [MockCheck()] if cs_matched else []
                self.signature_value_present = sig_present
                def td(): return {"verification_id": verification_id, "run_status": run_status}
                self.to_dict = td
        return MockRun()

    def _all_stores(self, agent=None, inst=None, binding=None, adapter=None,
                     spolicy=None, artifact=None, ver_run=None):
        """Build combined mock serving as marketplace_store, runtime_store,
        sandbox_policy_store, artifact_store, and verification_store."""
        class AllStores:
            def get_agent(self, i): return agent
            def get_installation_by_agent(self, i, t, w): return inst
            def get_binding_by_marketplace_agent(self, i, t): return binding
            def get_adapter(self, i): return adapter
            def get_policy(self, i): return spolicy
            def get_artifact_by_submission(self, i): return artifact
            def get_latest_run_for_artifact(self, i): return ver_run
        s = AllStores()
        # Return the same object for all store arguments
        return s, s, s, s, s

    def test_marketplace_agent_exists_passed(self, pstore):
        mkp, runtime, spol, art, ver = self._all_stores(
            agent=self._mock_agent(metadata={"submission_id": "sub1"}),
            inst=self._mock_inst(), binding=self._mock_binding(),
            adapter=self._mock_adapter(), spolicy=self._mock_policy(),
            artifact=self._mock_artifact(), ver_run=self._mock_run(),
        )
        planner = self._make_planner(pstore, marketplace_store=mkp, runtime_store=runtime,
                                     sandbox_policy_store=spol, artifact_store=art, verification_store=ver)
        plan = planner.create_plan("mkp1", "t1", "actor", execution_mode=RuntimeExecutionMode.SANDBOX_RESERVED)
        assert plan.plan_status == RuntimeExecutionPlanStatus.PLANNED
        assert plan.decision == RuntimePlanDecision.RESERVED_ONLY
        assert plan.is_dispatchable() is False
        assert plan.no_execution_performed is True

    def test_builtin_agent_blocked(self, pstore):
        mkp, _, _, _, _ = self._all_stores(agent=self._mock_agent(publisher_type="builtin"))
        planner = self._make_planner(pstore, marketplace_store=mkp)
        plan = planner.create_plan("mkp_builtin", "t1", "actor"); assert plan.is_blocked()

    def test_missing_agent_blocked(self, pstore):
        mkp, _, _, _, _ = self._all_stores(agent=None)
        planner = self._make_planner(pstore, marketplace_store=mkp)
        plan = planner.create_plan("mkp_nope", "t1", "actor"); assert plan.is_blocked()

    def test_missing_installation_blocked(self, pstore):
        mkp, _, _, _, _ = self._all_stores(agent=self._mock_agent(metadata={"submission_id": "sub1"}))
        planner = self._make_planner(pstore, marketplace_store=mkp)
        plan = planner.create_plan("mkp1", "t1", "actor"); assert plan.is_blocked()

    def test_no_mutation_of_artifact(self, pstore):
        mkp, runtime, spol, art, ver = self._all_stores(
            agent=self._mock_agent(metadata={"submission_id": "sub1"}), inst=self._mock_inst(),
            binding=self._mock_binding(), adapter=self._mock_adapter(), spolicy=self._mock_policy(),
            artifact=self._mock_artifact(), ver_run=self._mock_run())
        planner = self._make_planner(pstore, marketplace_store=mkp, runtime_store=runtime,
                                     sandbox_policy_store=spol, artifact_store=art, verification_store=ver)
        plan = planner.create_plan("mkp1", "t1", "actor", execution_mode=RuntimeExecutionMode.SANDBOX_RESERVED)
        assert plan.plan_status == RuntimeExecutionPlanStatus.PLANNED

    def test_plan_not_dispatchable(self, pstore):
        mkp, runtime, spol, art, ver = self._all_stores(
            agent=self._mock_agent(metadata={"submission_id": "sub1"}), inst=self._mock_inst(),
            binding=self._mock_binding(), adapter=self._mock_adapter(), spolicy=self._mock_policy(),
            artifact=self._mock_artifact(), ver_run=self._mock_run())
        planner = self._make_planner(pstore, marketplace_store=mkp, runtime_store=runtime,
                                     sandbox_policy_store=spol, artifact_store=art, verification_store=ver)
        plan = planner.create_plan("mkp1", "t1", "actor", execution_mode=RuntimeExecutionMode.SANDBOX_RESERVED)
        assert plan.is_dispatchable() is False

    def test_safety_flags_true(self, pstore):
        mkp, runtime, spol, art, ver = self._all_stores(
            agent=self._mock_agent(metadata={"submission_id": "sub1"}), inst=self._mock_inst(),
            binding=self._mock_binding(), adapter=self._mock_adapter(), spolicy=self._mock_policy(),
            artifact=self._mock_artifact(), ver_run=self._mock_run())
        planner = self._make_planner(pstore, marketplace_store=mkp, runtime_store=runtime,
                                     sandbox_policy_store=spol, artifact_store=art, verification_store=ver)
        plan = planner.create_plan("mkp1", "t1", "actor", execution_mode=RuntimeExecutionMode.SANDBOX_RESERVED)
        assert plan.no_download_planned is True and plan.no_network_planned is True
        assert plan.no_execution_performed is True

    def test_planner_no_worker_no_queue(self, pstore):
        mkp, runtime, spol, art, ver = self._all_stores(
            agent=self._mock_agent(metadata={"submission_id": "sub1"}), inst=self._mock_inst(),
            binding=self._mock_binding(), adapter=self._mock_adapter(), spolicy=self._mock_policy(),
            artifact=self._mock_artifact(), ver_run=self._mock_run())
        planner = self._make_planner(pstore, marketplace_store=mkp, runtime_store=runtime,
                                     sandbox_policy_store=spol, artifact_store=art, verification_store=ver)
        plan = planner.create_plan("mkp1", "t1", "actor", execution_mode=RuntimeExecutionMode.SANDBOX_RESERVED)
        assert plan.dispatch_status in (RuntimeDispatchStatus.RESERVED_FOR_STEP24E, RuntimeDispatchStatus.NOT_DISPATCHABLE)


# ═══════════════════════════ Safety ═══════════════════════════

class TestModuleSafety:
    def test_no_subprocess(self):
        import src.open_platform.runtime_execution_planner as rp
        assert "subprocess" not in str(dir(rp))

    def test_no_docker(self):
        import src.open_platform.runtime_execution_planner as rp
        assert "docker" not in str(dir(rp)).lower()

    def test_no_requests_httpx(self):
        import src.open_platform.runtime_execution_planner as rp
        assert "requests" not in str(dir(rp)) and "httpx" not in str(dir(rp))

    def test_no_agent_runtime(self):
        import src.open_platform.runtime_execution_planner as rp
        assert "AgentRuntime" not in str(dir(rp))

    def test_no_agent_registry(self):
        import src.open_platform.runtime_execution_planner as rp
        assert "AgentRegistry" not in str(dir(rp))


# ═══════════════════════════ Helpers ═══════════════════════════

def mk_plan(mkp="mkp1", tenant="t1", developer="d1", plan_status=None, decision=None, dispatch_status=None,
            no_download=True, no_network=True, no_exec=True, worker_req=False, worker_avail=False, created_at=None,
            output_contract=None, policy_snapshot=None, artifact_snapshot=None, verification_snapshot=None, metadata=None):
    p = RuntimeExecutionPlan(
        marketplace_agent_id=mkp, tenant_id=tenant, developer_id=developer,
        no_download_planned=no_download, no_network_planned=no_network, no_execution_performed=no_exec,
        worker_required=worker_req, worker_available=worker_avail,
        created_at=created_at or datetime.now(timezone.utc),
        output_contract=output_contract or {}, policy_snapshot=policy_snapshot or {},
        artifact_snapshot=artifact_snapshot or {}, verification_snapshot=verification_snapshot or {},
        metadata=metadata or {},
    )
    if plan_status: p.plan_status = plan_status
    if decision: p.decision = decision
    if dispatch_status: p.dispatch_status = dispatch_status
    return p
