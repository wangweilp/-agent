"""Agent API 集成测试（使用 FastAPI TestClient）。"""

import pytest
from fastapi.testclient import TestClient

from src.agents.registry import AgentRegistry
from src.agents.workflow import (
    WorkflowEngine,
    create_meeting_to_training_workflow,
)
from src.agents.builtin.knowledge_agent import KnowledgeAgent
from src.agents.builtin.meeting_agent import MeetingAgent
from src.agents.builtin.training_agent import TrainingAgent
from src.api.agent_router import create_agent_router
from src.api.middleware import require_auth, TokenPayload
from src.core.auth import WorkspaceRole
from tests.test_agents.test_runtime import FakeMemoryProvider, FakeKGProvider

from fastapi import FastAPI


# 测试用 TokenPayload
_TEST_PAYLOAD = TokenPayload(
    user_id="test-user-001",
    workspace_id="test-ws-001",
    role=WorkspaceRole.ADMIN,
)


async def _test_require_auth_override() -> TokenPayload:
    """测试用认证替代 — 返回固定测试 payload，跳过 JWT 验证。"""
    return _TEST_PAYLOAD


@pytest.fixture
def client():
    mem = FakeMemoryProvider()
    kg = FakeKGProvider()

    registry = AgentRegistry()
    registry.set_providers(memory=mem, kg=kg)

    for cls in [KnowledgeAgent, MeetingAgent, TrainingAgent]:
        registry.register(cls(memory=mem, knowledge_graph=kg))

    engine = WorkflowEngine(registry)

    # 注册预置工作流
    wf = create_meeting_to_training_workflow()
    engine.register_workflow(wf)

    app = FastAPI()
    # 覆盖认证依赖 — 测试环境跳过 JWT
    app.dependency_overrides[require_auth] = _test_require_auth_override
    app.include_router(create_agent_router(registry, engine))
    return TestClient(app)


# ═══════════════════════════════════════════
# GET /agents
# ═══════════════════════════════════════════


class TestListAgents:
    def test_list_all(self, client):
        resp = client.get("/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 3
        assert data["enabled"] >= 3

    def test_list_by_tag(self, client):
        resp = client.get("/agents?tag=nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    def test_list_enabled_only(self, client):
        resp = client.get("/agents?enabled_only=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == data["enabled"]


# ═══════════════════════════════════════════
# GET /agents/{id}
# ═══════════════════════════════════════════


class TestGetAgent:
    def test_get_existing(self, client):
        resp = client.get("/agents/builtin-knowledge")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Knowledge Agent"
        assert "metrics" in data

    def test_get_nonexistent(self, client):
        resp = client.get("/agents/nonexistent")
        assert resp.status_code == 404


# ═══════════════════════════════════════════
# POST /agents/run
# ═══════════════════════════════════════════


class TestRunAgent:
    def test_run_success(self, client):
        resp = client.post("/agents/run", json={
            "agent_id": "builtin-knowledge",
            "title": "测试",
            "description": "搜索AI",
            "priority": "medium",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["output"] != ""
        assert data["duration_ms"] >= 0

    def test_run_nonexistent_agent(self, client):
        resp = client.post("/agents/run", json={
            "agent_id": "nope",
            "title": "test",
        })
        assert resp.status_code == 404

    def test_run_with_custom_priority(self, client):
        resp = client.post("/agents/run", json={
            "agent_id": "builtin-knowledge",
            "title": "high prio",
            "priority": "high",
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# ═══════════════════════════════════════════
# POST /agents/{id}/enable & /disable
# ═══════════════════════════════════════════


class TestToggleAgent:
    def test_disable_and_enable(self, client):
        resp = client.post("/agents/builtin-knowledge/disable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

        resp = client.post("/agents/builtin-knowledge/enable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_disable_nonexistent(self, client):
        resp = client.post("/agents/nope/disable")
        assert resp.status_code == 404


# ═══════════════════════════════════════════
# PUT /agents/{id}/config
# ═══════════════════════════════════════════


class TestUpdateConfig:
    def test_update_config(self, client):
        resp = client.put("/agents/builtin-knowledge/config", json={
            "config": {"max_results": 50},
        })
        assert resp.status_code == 200
        assert resp.json()["config"]["max_results"] == 50

    def test_update_nonexistent(self, client):
        resp = client.put("/agents/nope/config", json={"config": {}})
        assert resp.status_code == 404


# ═══════════════════════════════════════════
# GET /agents/stats/overview
# ═══════════════════════════════════════════


class TestStats:
    def test_get_stats(self, client):
        resp = client.get("/agents/stats/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_agents" in data
        assert "enabled_agents" in data


# ═══════════════════════════════════════════
# Workflow API
# ═══════════════════════════════════════════


class TestWorkflowAPI:
    def test_list_workflows(self, client):
        resp = client.get("/agents/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_get_workflow(self, client):
        # 先获取列表拿到一个 workflow_id
        list_resp = client.get("/agents/workflows")
        wf_id = list_resp.json()[0]["workflow_id"]
        resp = client.get(f"/agents/workflows/{wf_id}")
        assert resp.status_code == 200

    def test_get_nonexistent_workflow(self, client):
        resp = client.get("/agents/workflows/nonexistent")
        assert resp.status_code == 404

    def test_execute_workflow(self, client):
        list_resp = client.get("/agents/workflows")
        wf_id = list_resp.json()[0]["workflow_id"]
        resp = client.post(
            f"/agents/workflows/{wf_id}/execute",
            json={"input_data": {"transcript": "讨论产品发布"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"

    def test_execute_nonexistent_workflow(self, client):
        resp = client.post("/agents/workflows/nonexistent/execute", json={})
        assert resp.status_code == 404

    def test_create_workflow(self, client):
        resp = client.post("/agents/workflows", json={
            "name": "API Test WF",
            "description": "Test from API",
            "nodes": [
                {"name": "开始", "node_type": "start", "is_start": True},
                {
                    "name": "知识搜索",
                    "node_type": "agent",
                    "agent_id": "builtin-knowledge",
                },
                {"name": "结束", "node_type": "end"},
            ],
            "tags": ["api-test"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "API Test WF"

    def test_create_invalid_workflow(self, client):
        resp = client.post("/agents/workflows", json={
            "name": "Invalid",
            "nodes": [
                {"name": "No Start", "node_type": "agent"},
            ],
        })
        assert resp.status_code == 400


# ═══════════════════════════════════════════
# Execution API
# ═══════════════════════════════════════════


class TestExecutionAPI:
    def test_list_executions(self, client):
        # 先执行一个工作流
        list_resp = client.get("/agents/workflows")
        wf_id = list_resp.json()[0]["workflow_id"]
        client.post(f"/agents/workflows/{wf_id}/execute", json={})

        resp = client.get("/agents/executions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_get_execution(self, client):
        # 先执行一个工作流
        list_resp = client.get("/agents/workflows")
        wf_id = list_resp.json()[0]["workflow_id"]
        client.post(f"/agents/workflows/{wf_id}/execute", json={})

        exec_resp = client.get("/agents/executions")
        ex_id = exec_resp.json()[0]["execution_id"]

        resp = client.get(f"/agents/executions/{ex_id}")
        assert resp.status_code == 200

    def test_get_nonexistent_execution(self, client):
        resp = client.get("/agents/executions/nope")
        assert resp.status_code == 404
