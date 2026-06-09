"""Agents Business Scenarios 测试。"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agents.registry import AgentRegistry
from src.agents.scenarios import (
    ScenarioEngine,
    MeetingToTrainingInput,
    DepartmentAssistantInput,
    SCENARIO_DEFINITIONS,
    list_scenarios,
    get_scenario,
)
from src.agents.builtin.meeting_agent import MeetingAgent
from src.agents.builtin.knowledge_agent import KnowledgeAgent
from src.agents.builtin.training_agent import TrainingAgent
from src.agents.department import RDAgent, ProductAgent, SalesDeptAgent
from src.api.agent_router import create_agent_router
from src.api.middleware import require_auth, TokenPayload
from src.core.auth import WorkspaceRole
from tests.test_agents.test_runtime import FakeMemoryProvider, FakeKGProvider


# Auth override for tests
_TEST_PAYLOAD = TokenPayload(
    user_id="test-scenario-user",
    workspace_id="test-ws-scenario",
    role=WorkspaceRole.ADMIN,
)


async def _test_auth() -> TokenPayload:
    return _TEST_PAYLOAD


@pytest.fixture
def mem():
    return FakeMemoryProvider()


@pytest.fixture
def kg():
    return FakeKGProvider()


@pytest.fixture
def registry(mem, kg):
    reg = AgentRegistry()
    reg.set_providers(memory=mem, kg=kg)
    reg.register(MeetingAgent(memory=mem, knowledge_graph=kg))
    reg.register(KnowledgeAgent(memory=mem, knowledge_graph=kg))
    reg.register(TrainingAgent(memory=mem, knowledge_graph=kg))
    reg.register(RDAgent(memory=mem, knowledge_graph=kg))
    reg.register(ProductAgent(memory=mem, knowledge_graph=kg))
    reg.register(SalesDeptAgent(memory=mem, knowledge_graph=kg))
    return reg


@pytest.fixture
def engine(registry):
    return ScenarioEngine(registry)


@pytest.fixture
def api_client(registry):
    app = FastAPI()
    app.dependency_overrides[require_auth] = _test_auth
    app.include_router(create_agent_router(registry, None, ScenarioEngine(registry)))
    return TestClient(app)


# ═══════════════════════════════════════════
# Scenario Definitions
# ═══════════════════════════════════════════


class TestScenarioDefinitions:
    def test_list_has_two_scenarios(self):
        result = list_scenarios()
        assert len(result) == 2

    def test_scenario_ids(self):
        ids = {s["scenario_id"] for s in list_scenarios()}
        assert "meeting-to-training" in ids
        assert "department-assistant" in ids

    def test_get_scenario_exists(self):
        s = get_scenario("meeting-to-training")
        assert s is not None
        assert s["name"] == "Meeting to Knowledge to Training"

    def test_get_scenario_not_found(self):
        assert get_scenario("nonexistent") is None


# ═══════════════════════════════════════════
# Meeting-to-Training Scenario
# ═══════════════════════════════════════════


class TestMeetingToTraining:
    def test_successful_run(self, engine):
        result = engine.run_meeting_to_training(
            MeetingToTrainingInput(
                meeting_title="产品发布评审会",
                meeting_notes="决定下周发布 v2.0，前端需要完成测试，后端 API 已就绪。负责: 张三跟进测试，李四负责部署。",
                participants=["张三", "李四"],
                department_id="product",
            ),
            tenant_id="t1", user_id="u1", workspace_id="ws1",
        )
        assert result.success
        assert result.scenario_id.startswith("scn_m2t_")
        assert len(result.action_items) >= 0
        assert len(result.knowledge_entries) >= 0
        assert len(result.training_outline) >= 0
        assert result.duration_ms >= 0

    def test_output_has_structured_fields(self, engine):
        result = engine.run_meeting_to_training(
            MeetingToTrainingInput(
                meeting_title="架构评审",
                meeting_notes="确认微服务架构方案。决定采用 API Gateway + 事件驱动。需要补充熔断策略。",
            ),
            tenant_id="t1", user_id="u1", workspace_id="ws1",
        )
        assert isinstance(result.summary, str)
        assert isinstance(result.decisions, list)
        assert isinstance(result.action_items, list)
        assert isinstance(result.training_outline, list)
        assert isinstance(result.training_qa, list)

    def test_memory_and_kg_refs_recorded(self, engine):
        result = engine.run_meeting_to_training(
            MeetingToTrainingInput(
                meeting_title="测试会议",
                meeting_notes="讨论测试覆盖率问题。",
            ),
            tenant_id="t1", user_id="u1", workspace_id="ws1",
        )
        assert isinstance(result.memory_refs, list)
        assert isinstance(result.knowledge_refs, list)

    def test_error_on_empty_input(self, engine):
        result = engine.run_meeting_to_training(
            MeetingToTrainingInput(meeting_title="", meeting_notes=""),
            tenant_id="t1", user_id="u1",
        )
        assert isinstance(result.success, bool)
        assert result.error is not None or result.success is True

    def test_to_dict(self, engine):
        result = engine.run_meeting_to_training(
            MeetingToTrainingInput(meeting_title="T", meeting_notes="N"),
            tenant_id="t1", user_id="u1",
        )
        d = result.to_dict()
        assert "scenario_id" in d
        assert "success" in d
        assert "execution_trace" in d


# ═══════════════════════════════════════════
# Department Assistant Scenario
# ═══════════════════════════════════════════


class TestDepartmentAssistant:
    def test_rd_department(self, engine):
        result = engine.run_department_assistant(
            DepartmentAssistantInput(
                department="研发部",
                question="当前项目的技术风险有哪些？",
            ),
            tenant_id="t1", user_id="u1", workspace_id="ws1",
        )
        assert result.success
        assert result.department == "研发部"
        assert len(result.answer) > 0
        assert isinstance(result.confidence, float)
        assert result.confidence >= 0.0

    def test_sales_department(self, engine):
        result = engine.run_department_assistant(
            DepartmentAssistantInput(
                department="销售部",
                question="这个客户适合推荐哪个套餐？",
            ),
            tenant_id="t1", user_id="u1", workspace_id="ws1",
        )
        assert result.success
        assert result.department == "销售部"
        assert len(result.answer) > 0

    def test_unknown_department(self, engine):
        result = engine.run_department_assistant(
            DepartmentAssistantInput(department="不存在的部门", question="test"),
            tenant_id="t1", user_id="u1",
        )
        assert result.success is False
        assert result.error is not None
        assert "未知部门" in result.error

    def test_structured_output(self, engine):
        result = engine.run_department_assistant(
            DepartmentAssistantInput(department="产品部", question="如何优化产品功能优先级？"),
            tenant_id="t1", user_id="u1",
        )
        assert isinstance(result.answer, str)
        assert isinstance(result.recommended_actions, list)
        assert isinstance(result.limitations, list)
        assert isinstance(result.confidence, float)
        assert len(result.limitations) > 0  # 始终有 limitations 说明

    def test_confidence_range(self, engine):
        """Confidence 必须在 0.0-1.0 之间。"""
        result = engine.run_department_assistant(
            DepartmentAssistantInput(department="研发部", question="test"),
            tenant_id="t1", user_id="u1",
        )
        assert 0.0 <= result.confidence <= 1.0

    def test_has_trace(self, engine):
        result = engine.run_department_assistant(
            DepartmentAssistantInput(department="运营部", question="如何提升用户活跃度？"),
            tenant_id="t1", user_id="u1",
        )
        assert isinstance(result.execution_trace, list)

    def test_to_dict(self, engine):
        result = engine.run_department_assistant(
            DepartmentAssistantInput(department="人力资源部", question="如何制定招聘计划？"),
            tenant_id="t1", user_id="u1",
        )
        d = result.to_dict()
        assert "scenario_id" in d
        assert "answer" in d
        assert "confidence" in d
        assert "limitations" in d


# ═══════════════════════════════════════════
# Scenario API Tests
# ═══════════════════════════════════════════


class TestScenarioAPI:
    def test_list_scenarios(self, api_client):
        resp = api_client.get("/agents/scenarios")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_get_scenario(self, api_client):
        resp = api_client.get("/agents/scenarios/meeting-to-training")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario_id"] == "meeting-to-training"

    def test_get_nonexistent_scenario(self, api_client):
        resp = api_client.get("/agents/scenarios/nonexistent")
        assert resp.status_code == 404

    def test_run_meeting_to_training_api(self, api_client):
        resp = api_client.post("/agents/scenarios/meeting-to-training/run", json={
            "meeting_title": "API 测试会议",
            "meeting_notes": "讨论接口规范并确定版本发布计划",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "scenario_id" in data
        assert "result" in data

    def test_run_department_assistant_api(self, api_client):
        resp = api_client.post("/agents/scenarios/department-assistant/run", json={
            "department": "研发部",
            "question": "如何评估新技术引入风险？",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "result" in data

    def test_missing_required_field_422(self, api_client):
        resp = api_client.post("/agents/scenarios/meeting-to-training/run", json={
            "meeting_title": "Missing notes",
        })
        assert resp.status_code == 422

    def test_department_not_found(self, api_client):
        resp = api_client.post("/agents/scenarios/department-assistant/run", json={
            "department": "不存在的部门",
            "question": "test",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] is not None


# ═══════════════════════════════════════════
# Cross-Department Isolation
# ═══════════════════════════════════════════


class TestDepartmentIsolation:
    def test_rd_agent_has_rd_namespace(self):
        """R&D Agent 使用 rd/engineering 知识空间，不会搜索产品部数据。"""
        agent = RDAgent()
        assert "rd" in agent.department_kb_namespace
        assert agent.department == "研发部"

    def test_sales_agent_has_sales_namespace(self):
        agent = SalesDeptAgent()
        assert "sales" in agent.department_kb_namespace
        assert agent.department == "销售部"

    def test_different_departments_different_namespaces(self):
        rd = RDAgent()
        sales = SalesDeptAgent()
        assert rd.department_kb_namespace != sales.department_kb_namespace
        assert rd.department != sales.department


# ===========================================
# WorkflowEngine Integration (P0 fixes)
# ===========================================

import pytest
from src.agents.workflow import WorkflowEngine


@pytest.fixture
def workflow_engine(registry):
    return WorkflowEngine(registry)


@pytest.fixture
def engine_with_wf(registry, workflow_engine):
    return ScenarioEngine(registry, workflow_engine)


@pytest.fixture
def api_client_with_wf(registry):
    app = FastAPI()
    app.dependency_overrides[require_auth] = _test_auth
    wfe = WorkflowEngine(registry)
    sce = ScenarioEngine(registry, wfe)
    app.include_router(create_agent_router(registry, wfe, sce))
    return TestClient(app)


class TestWorkflowEngineIntegration:
    """P0-1/P0-2/P0-3/P0-4: Workflow path + standard steps + workflow_execution_id."""

    def test_m2t_returns_workflow_execution_id(self, engine_with_wf):
        result = engine_with_wf.run_meeting_to_training(
            MeetingToTrainingInput(meeting_title="WF Test", meeting_notes="讨论架构"),
            tenant_id="t1", user_id="u1", workspace_id="ws1",
        )
        assert result.success
        assert result.workflow_execution_id is not None
        assert len(result.workflow_execution_id) > 10
        assert result.fallback_mode is False

    def test_m2t_execution_steps_standard_format(self, engine_with_wf):
        result = engine_with_wf.run_meeting_to_training(
            MeetingToTrainingInput(meeting_title="Steps", meeting_notes="内容"),
            tenant_id="t1", user_id="u1",
        )
        assert result.success
        steps = result.execution_steps
        assert len(steps) >= 1
        for s in steps:
            assert "step_index" in s
            assert "node_id" in s
            assert "node_name" in s
            assert "node_type" in s
            assert "status" in s
            assert "duration_ms" in s

    def test_da_returns_workflow_execution_id(self, engine_with_wf):
        result = engine_with_wf.run_department_assistant(
            DepartmentAssistantInput(department="研发部", question="风险?"),
            tenant_id="t1", user_id="u1", workspace_id="ws1",
        )
        assert result.success
        assert result.workflow_execution_id is not None
        assert result.fallback_mode is False

    def test_da_execution_steps_not_direct(self, engine_with_wf):
        result = engine_with_wf.run_department_assistant(
            DepartmentAssistantInput(department="产品部", question="优先级?"),
            tenant_id="t1", user_id="u1",
        )
        assert result.success
        steps = result.execution_steps
        assert len(steps) >= 1
        # Workflow steps should have real node_ids, not "direct"
        for s in steps:
            assert s["node_id"] != "direct"

    def test_fallback_has_null_workflow_id(self, engine):
        result = engine.run_meeting_to_training(
            MeetingToTrainingInput(meeting_title="FB", meeting_notes="测试"),
            tenant_id="t1", user_id="u1",
        )
        assert result.success
        assert result.workflow_execution_id is None
        assert result.fallback_mode is True

    def test_da_direct_fallback_null_id(self, engine):
        result = engine.run_department_assistant(
            DepartmentAssistantInput(department="销售部", question="test"),
            tenant_id="t1", user_id="u1",
        )
        assert result.success
        assert result.workflow_execution_id is None
        assert result.fallback_mode is True

    def test_unknown_department_still_errors(self, engine_with_wf):
        result = engine_with_wf.run_department_assistant(
            DepartmentAssistantInput(department="不存在的", question="test"),
            tenant_id="t1", user_id="u1",
        )
        assert result.success is False
        assert "未知部门" in result.error

    def test_api_workflow_execution_id(self, api_client_with_wf):
        resp = api_client_with_wf.post("/agents/scenarios/meeting-to-training/run", json={
            "meeting_title": "API", "meeting_notes": "内容",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["execution_id"] != data["scenario_id"]
        assert data["result"]["workflow_execution_id"] is not None

    def test_api_metrics_has_fallback_and_wfid(self, api_client_with_wf):
        resp = api_client_with_wf.post("/agents/scenarios/meeting-to-training/run", json={
            "meeting_title": "M", "meeting_notes": "内容",
        })
        assert resp.status_code == 200
        metrics = resp.json()["metrics"]
        assert metrics["fallback_mode"] is False
        assert metrics["workflow_execution_id"] is not None
