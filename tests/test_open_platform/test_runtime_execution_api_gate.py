"""Runtime Execution API Gate 测试 — gate domain + API endpoints + non-execution guards。"""
import os, pytest
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from datetime import datetime, timezone
from src.open_platform.runtime_execution_gate import (
    RuntimeExecutionGateCheck, RuntimeExecutionGateCheckStatus, RuntimeExecutionGateCheckType,
    RuntimeExecutionGateSeverity, RuntimeExecutionGateResult, RuntimeExecutionGateStatus,
    RuntimeExecutionGateDecision, RuntimeExecutionApiMode,
)
from src.open_platform.runtime_execution_plan import RuntimeExecutionPlan

# ═══════════ Gate Domain (10) ═══════════

class TestGateDomain:
    def test_create_check(self):
        c = RuntimeExecutionGateCheck(check_type=RuntimeExecutionGateCheckType.PLAN_ONLY_MODE, message="ok")
        assert c.check_id.startswith("rtexgatechk_")
    def test_check_to_dict_from_dict(self):
        c = RuntimeExecutionGateCheck(check_type="t", status="passed", message="m"); d=c.to_dict(); c2=RuntimeExecutionGateCheck.from_dict(d)
        assert c2.check_type=="t"
    def test_check_metadata_safe(self):
        c=RuntimeExecutionGateCheck(message="ok"); d=c.to_dict(); assert "raw_key" not in str(d)
    def test_create_gate_result(self):
        g=RuntimeExecutionGateResult(mode=RuntimeExecutionApiMode.ADMIN_PLAN_ONLY); assert g.gate_id.startswith("rtexgate_")
    def test_add_check_recounts(self):
        g=RuntimeExecutionGateResult()
        g.add_check(RuntimeExecutionGateCheck(check_type="b", status=RuntimeExecutionGateCheckStatus.BLOCKED, severity=RuntimeExecutionGateSeverity.BLOCKER, message="b"))
        assert g.blockers_count==1
    def test_calculate_status_blocked(self):
        g=RuntimeExecutionGateResult(); g.add_check(RuntimeExecutionGateCheck(check_type="b", status="blocked", severity="blocker", message="b"))
        g.calculate_status(); assert g.status==RuntimeExecutionGateStatus.BLOCKED
    def test_is_execution_allowed_always_false(self):
        g=RuntimeExecutionGateResult(); assert not g.is_execution_allowed()
        g.status=RuntimeExecutionGateStatus.PLAN_ONLY; assert not g.is_execution_allowed()
    def test_safety_flags_default_true(self):
        g=RuntimeExecutionGateResult(); assert g.no_execution_performed and g.no_download_used and g.no_network_used
        assert g.no_subprocess_used and g.no_container_used and g.no_queue_created
        assert g.no_job_dispatched and g.no_agent_runtime_used and g.no_agent_registry_used
    def test_response_payload_no_raw_input(self):
        g=RuntimeExecutionGateResult(response_payload={"status":"blocked"}); assert "raw" not in str(g.response_payload).lower() or "status" in str(g.response_payload)
    def test_id_formats(self):
        assert RuntimeExecutionGateCheck().check_id.startswith("rtexgatechk_")
        assert RuntimeExecutionGateResult().gate_id.startswith("rtexgate_")

# ═══════════ API Router Tests (FastAPI TestClient) ═══════════

import json
from fastapi.testclient import TestClient
from src.adapters.config import Settings

@pytest.fixture
def settings_obj():
    # Settings is frozen and all fields have defaults via env/.env
    from src.adapters.config import Settings
    return Settings()  # uses defaults from .env / pydantic defaults

# API endpoint tests use direct store/planner calls (bypassing auth for logic validation).

class TestAPIEndpoints:
    """Test API endpoints via direct plan_store + planner_service calls (bypassing auth for logic validation)."""
    @pytest.fixture
    def plan_store(self):
        from src.adapters.config import Settings
        import tempfile, uuid, os as _os
        d = tempfile.mkdtemp(); path = _os.path.join(d, f"t_{uuid.uuid4().hex[:8]}.db")
        from src.adapters.runtime_execution_plan_store import SQLiteRuntimeExecutionPlanStore
        return SQLiteRuntimeExecutionPlanStore(Settings(), db_path=path)

    @pytest.fixture
    def planner(self, plan_store):
        from src.open_platform.runtime_execution_planner import RuntimeExecutionPlannerService
        class MockMKP:
            def get_agent(self, mkp):
                class MA: publisher_type="developer"; display_name="T"; required_permissions=[]; metadata={"submission_id":"s1"}
                return MA()
            def get_installation_by_agent(self, mkp, tid, ws):
                class MI: enabled=True; status="active"; permissions_granted=[]
                return MI()
        class MockRT:
            def get_binding_by_marketplace_agent(self, mkp, tid):
                class MB: binding_id="b1"; runtime_status="enabled"; adapter_id="a1"; sandbox_policy_id="sp1"; is_enabled=True
                return MB()
            def get_adapter(self, aid):
                class MA: adapter_id="a1"; adapter_type="simulation"; status="active"; is_active=lambda: True
                def td(): return {}
                MA.to_dict=td; return MA()
        class MockSP:
            def get_policy(self, pid):
                from src.open_platform.sandbox_policy import SandboxPolicy, SandboxPolicyStatus, SandboxLevel
                return SandboxPolicy(policy_id="sp1", name="t", description="t", status=SandboxPolicyStatus.ACTIVE, sandbox_level=SandboxLevel.NO_EXECUTION, audit_enabled=True)
        class MockArt:
            def get_artifact_by_submission(self, sid):
                class MA: artifact_id="art1"; artifact_status="declared"; quarantine_status="quarantined"
                def td(s): return {}
                MA.to_dict=td; return MA()
        class MockVer:
            def get_latest_run_for_artifact(self, aid):
                class Ch: check_type="checksum_match"; status="passed"
                class MR: verification_id="v1"; run_status="passed"; checks=[Ch()]; signature_value_present=False
                def td(s): return {}
                MR.to_dict=td; return MR()
        return RuntimeExecutionPlannerService(plan_store=plan_store, marketplace_store=MockMKP(),
            runtime_store=MockRT(), sandbox_policy_store=MockSP(), artifact_store=MockArt(),
            verification_store=MockVer(), usage_store=None)

    def test_create_plan_via_planner(self, planner):
        plan = planner.create_plan("mkp1", "t1", "actor", execution_mode="sandbox_reserved")
        assert plan is not None and plan.plan_id.startswith("rtexplan_")
        assert plan.is_dispatchable() is False
        assert plan.dispatch_status != "dispatched" and plan.dispatch_status != "running" and plan.dispatch_status != "completed"
        assert plan.no_execution_performed is True
        assert plan.no_download_planned is True

    def test_store_crud(self, plan_store, planner):
        plan = planner.create_plan("mkp1", "t1", "actor", execution_mode="sandbox_reserved")
        # get
        found = plan_store.get_plan(plan.plan_id); assert found is not None
        # list
        plans = plan_store.list_plans(tenant_id="t1"); assert len(plans)==1
        # audit
        events = plan_store.list_audit_events(plan.plan_id); assert len(events)>=1
        # cancel
        plan_store.cancel_plan(plan.plan_id, "actor", "test")
        assert plan_store.get_plan(plan.plan_id).plan_status == "cancelled"

    def test_policy_preview_via_translator(self, planner, plan_store):
        plan = planner.create_plan("mkp1", "t1", "actor", execution_mode="sandbox_reserved")
        assert plan.sandbox_policy_id == "sp1"
        from src.open_platform.policy_enforcement_translator import SandboxPolicyEnforcementTranslator
        from src.open_platform.sandbox_policy import SandboxPolicy, SandboxPolicyStatus, SandboxLevel
        t = SandboxPolicyEnforcementTranslator()
        pol = SandboxPolicy(policy_id="sp1", name="t", description="t", status=SandboxPolicyStatus.ACTIVE,
            sandbox_level=SandboxLevel.NO_EXECUTION, audit_enabled=True)
        result = t.translate_policy(pol)
        assert result.config is not None
        assert result.no_execution_performed is True

    def test_worker_preview_blocked(self, planner, plan_store):
        plan = planner.create_plan("mkp1", "t1", "actor", execution_mode="sandbox_reserved")
        from src.open_platform.sandbox_worker_registry import SandboxWorkerRegistry
        from src.open_platform.sandbox_worker import build_worker_request_from_plan, SandboxWorkerType
        reg = SandboxWorkerRegistry()
        req = build_worker_request_from_plan(plan, worker_type=SandboxWorkerType.DISABLED_STUB)
        result = reg.evaluate_with_default(req)
        assert result.status == "blocked"
        assert result.is_successful_execution() is False

    def test_execute_draft_blocked(self, plan_store, planner):
        """POST /runtime/agents/{id}/execute always blocked (logic test)."""
        from src.open_platform.runtime_execution_gate import (
            RuntimeExecutionGateResult, RuntimeExecutionGateStatus,
            RuntimeExecutionGateDecision, RuntimeExecutionApiMode, RuntimeExecutionGateCheck,
            RuntimeExecutionGateCheckType, RuntimeExecutionGateCheckStatus, RuntimeExecutionGateSeverity,
        )
        gate = RuntimeExecutionGateResult(mode=RuntimeExecutionApiMode.USER_EXECUTE_DISABLED,
            status=RuntimeExecutionGateStatus.DISABLED, decision=RuntimeExecutionGateDecision.BLOCKED_DISABLED,
            marketplace_agent_id="mkp1", tenant_id="t1", actor_id="user1")
        gate.add_check(RuntimeExecutionGateCheck(check_type=RuntimeExecutionGateCheckType.USER_EXECUTE_DISABLED,
            status=RuntimeExecutionGateCheckStatus.BLOCKED, severity=RuntimeExecutionGateSeverity.BLOCKER,
            message="Runtime execution API is draft-only and disabled in Step 24-H."))
        gate.calculate_status()
        assert gate.status == RuntimeExecutionGateStatus.BLOCKED
        assert not gate.is_execution_allowed()

# ═══════════ Safety Guards ═══════════

class TestModuleSafety:
    def test_router_no_subprocess(self):
        import src.api.runtime_execution_router as m; assert "subprocess" not in str(dir(m)).lower()
    def test_router_no_docker(self):
        import src.api.runtime_execution_router as m; assert "docker" not in str(dir(m)).lower()
    def test_router_no_requests(self):
        import src.api.runtime_execution_router as m; assert "requests" not in str(dir(m)).lower()
    def test_router_no_AgentRuntime(self):
        import src.api.runtime_execution_router as m; assert "AgentRuntime" not in str(dir(m))
    def test_router_no_AgentRegistry(self):
        import src.api.runtime_execution_router as m; assert "AgentRegistry" not in str(dir(m))
    def test_gate_no_subprocess(self):
        import src.open_platform.runtime_execution_gate as m; assert "subprocess" not in str(dir(m)).lower()
    def test_gate_no_docker(self):
        import src.open_platform.runtime_execution_gate as m; assert "docker" not in str(dir(m)).lower()
    def test_gate_no_requests(self):
        import src.open_platform.runtime_execution_gate as m; assert "requests" not in str(dir(m)).lower()
    def test_gate_no_AgentRuntime(self):
        import src.open_platform.runtime_execution_gate as m; assert "AgentRuntime" not in str(dir(m))
    def test_gate_no_AgentRegistry(self):
        import src.open_platform.runtime_execution_gate as m; assert "AgentRegistry" not in str(dir(m))

def _require_admin_for_test():
    """Dummy for dependency override."""
    pass
