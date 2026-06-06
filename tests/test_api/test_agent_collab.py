"""Multi-Agent Collaboration 测试 — SharedContext / Delegation / Reasoning。

测试覆盖：
    SharedContext: 构建、空 workspace、成员分组、查询过滤、summary
    Delegation: recall/remember/reflect 委托、无效 agent_type、审计日志
    Reasoning: 单参与者/多参与者、空参与者、记忆不足、冲突检测
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adapters.auth_store import SQLiteAuthStore, WorkspaceContext
from src.adapters.collab_store import CollabStore, CollaborationService
from src.api.agent_collab_router import create_agent_collab_router
from src.api.middleware import JWTTokenService, init_auth
from src.adapters.collab_adapter import DefaultMultiAgentCoordinator
from src.core.agent_collab import (
    AgentDelegation,
    ParticipantInsight,
    SharedContext,
    TeamReasoning,
)
from src.core.auth import Membership, TokenPayload, Workspace, WorkspaceRole
from src.core.retrieval import MemoryRetrievalService
from src.core.types import Memory, ToolResult


# ── Helpers ──


def _make_memory(
    mid: str = "m1",
    content: str = "测试记忆",
    source: str = "user",
    importance: int = 5,
    entities: list | None = None,
    status: str = "active",
) -> Memory:
    return Memory(
        id=mid,
        content=content,
        summary=None,
        source=source,
        timestamp=datetime.now(timezone.utc),
        importance=importance,
        entities=entities or [],
        memory_type="episodic",
        status=status,
    )


def _make_token(user_id: str = "u1", workspace_id: str = "ws1",
                role: WorkspaceRole = WorkspaceRole.ADMIN) -> TokenPayload:
    return TokenPayload(
        user_id=user_id, workspace_id=workspace_id,
        role=role, email="test@test.com",
    )


def _make_auth_headers(user_id: str = "u1", workspace_id: str = "ws1") -> dict:
    token_svc = JWTTokenService()
    from src.core.auth import User
    user = User(id=user_id, email=f"{user_id}@seed.test", name="Test")
    tokens = token_svc.create_tokens(user, workspace_id, WorkspaceRole.ADMIN)
    return {"Authorization": f"Bearer {tokens.access_token}"}


def _seed_access(auth_store: SQLiteAuthStore, user_id: str, ws_id: str, role: str = "admin") -> None:
    """直接插入 user + workspace + membership，用已知 ID 匹配 JWT。"""
    try:
        auth_store._db.execute(
            "INSERT OR IGNORE INTO users (id, email, name, auth_provider) VALUES (?, ?, ?, ?)",
            (user_id, f"{user_id}@seed.test", f"User_{user_id}", "email"),
        )
    except Exception:
        pass
    try:
        auth_store._db.execute(
            "INSERT OR IGNORE INTO workspaces (id, name, owner_id) VALUES (?, ?, ?)",
            (ws_id, f"WS_{ws_id}", user_id),
        )
    except Exception:
        pass
    try:
        auth_store._db.execute(
            "INSERT OR REPLACE INTO memberships (user_id, workspace_id, role) VALUES (?, ?, ?)",
            (user_id, ws_id, role),
        )
    except Exception:
        pass


# ── Fixtures ──


@pytest.fixture
def settings():
    from src.adapters.config import Settings
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def auth_store(settings):
    store = SQLiteAuthStore(settings, db_path=":memory:")
    yield store
    store.close()


@pytest.fixture
def collab_store(settings):
    store = CollabStore(settings, db_path=":memory:")
    yield store
    store.close()


@pytest.fixture
def collab_service(collab_store, auth_store):
    return CollaborationService(collab_store, auth_store)


@pytest.fixture
def token_service():
    return JWTTokenService()


@pytest.fixture
def mock_retrieval():
    """模拟 MemoryRetrievalService。"""
    service = MagicMock(spec=MemoryRetrievalService)
    service.retrieve.return_value = []
    service.format_results.return_value = ""
    return service


@pytest.fixture
def mock_tool_registry():
    """模拟 ToolRegistry。"""
    reg = MagicMock()
    reg.execute.return_value = ToolResult(
        tool_name="recall",
        success=True,
        content="模拟检索结果",
        metadata={"count": 3},
    )
    return reg


@pytest.fixture
def coordinator(collab_service, auth_store, mock_retrieval, mock_tool_registry):
    coord = DefaultMultiAgentCoordinator(
        collab_service=collab_service,
        auth_store=auth_store,
        retrieval_service=mock_retrieval,
        tool_registry=mock_tool_registry,
    )
    # Patch _retrieve_for_user to use mock_retrieval
    coord._retrieve_for_user = lambda user_id, query, top_k: mock_retrieval.retrieve(
        query, top_k=top_k
    )
    return coord


@pytest.fixture
def client(auth_store, collab_service, token_service, coordinator):
    # 预建 membership，使 _make_auth_headers 的 JWT 能通过 assert_workspace_access
    _seed_access(auth_store, "u1", "ws1", "admin")
    _seed_access(auth_store, "u2", "ws1", "member")
    app = FastAPI()
    init_auth(token_service, auth_store)
    app.include_router(create_agent_collab_router(coordinator))
    return TestClient(app)


# ── Helper: seed workspace with members ──


def _seed_workspace(auth_store: SQLiteAuthStore, ws_id: str, user_emails: list[str]):
    """创建 workspace 并添加成员。"""
    owner = auth_store.create_user("owner@test.com", "Owner")
    auth_store.create_workspace("Test WS", owner.id)
    # Override workspace id -- tricky since create_workspace generates its own
    # We'll use the default approach: manually insert
    for email in user_emails:
        try:
            user = auth_store.get_by_email(email)
            if user is None:
                user = auth_store.create_user(email, email.split("@")[0])
            auth_store.add_member(ws_id, user.id, WorkspaceRole.MEMBER)
        except Exception:
            pass


# ═══════════════════════════════════════════
# SharedContext Tests
# ═══════════════════════════════════════════


class TestSharedContext:
    def test_empty_workspace(self, coordinator):
        """空的 workspace 返回 member_count=0 的 SharedContext。"""
        ctx = coordinator.get_shared_context("nonexistent", query="test")
        assert isinstance(ctx, SharedContext)
        assert ctx.workspace_id == "nonexistent"
        assert ctx.member_count == 0
        assert ctx.total_memories == 0
        assert ctx.team_memories == []

    def test_shared_context_has_correct_fields(self, coordinator):
        """SharedContext 包含所有必填字段。"""
        ctx = coordinator.get_shared_context("ws1", query="AI learning")
        assert ctx.workspace_id == "ws1"
        assert ctx.query == "AI learning"
        assert isinstance(ctx.member_count, int)
        assert isinstance(ctx.team_memories, list)
        assert isinstance(ctx.member_memories, dict)
        assert isinstance(ctx.recent_activity, list)

    def test_shared_context_summary(self, coordinator):
        """SharedContext.summary() 返回可读摘要。"""
        ctx = coordinator.get_shared_context("ws1")
        s = ctx.summary()
        assert "ws1" in s
        assert isinstance(s, str)

    def test_shared_context_with_top_k(self, auth_store, collab_service, mock_retrieval):
        """top_k 参数控制返回记忆数 -- 有成员的 workspace 触发检索。"""
        memories = [_make_memory(f"m{i}", f"记忆{i}") for i in range(3)]
        mock_retrieval.retrieve.return_value = memories

        # seed a workspace with members so get_shared_context won't return early
        u1 = auth_store.create_user("u1@test.com", "User1")
        u2 = auth_store.create_user("u2@test.com", "User2")
        ws = auth_store.create_workspace("Team WS", u1.id)
        auth_store.add_member(ws.id, u2.id, WorkspaceRole.MEMBER)

        coordinator2 = DefaultMultiAgentCoordinator(
            collab_service=collab_service,
            auth_store=auth_store,
            retrieval_service=mock_retrieval,
            tool_registry=MagicMock(),
        )

        ctx = coordinator2.get_shared_context(ws.id, query="test", top_k=3)
        assert ctx.member_count >= 2
        # retrieve was called
        mock_retrieval.retrieve.assert_called()

    def test_shared_context_member_memories_grouping(self, auth_store, collab_service, mock_retrieval):
        """成员记忆按 user_id 分组。"""
        # Create workspace with members
        u1 = auth_store.create_user("u1@test.com", "User1")
        u2 = auth_store.create_user("u2@test.com", "User2")
        ws = auth_store.create_workspace("Team WS", u1.id)
        auth_store.add_member(ws.id, u2.id, WorkspaceRole.MEMBER)

        coordinator2 = DefaultMultiAgentCoordinator(
            collab_service=collab_service,
            auth_store=auth_store,
            retrieval_service=mock_retrieval,
            tool_registry=MagicMock(),
        )

        ctx = coordinator2.get_shared_context(ws.id, query="project")
        assert ctx.member_count >= 2
        # member_memories keys should be user_ids
        assert isinstance(ctx.member_memories, dict)


# ═══════════════════════════════════════════
# AgentDelegation Tests
# ═══════════════════════════════════════════


class TestAgentDelegation:
    def test_delegate_recall(self, coordinator, mock_retrieval):
        """委托 recall 返回成功结果。"""
        memories = [_make_memory("m1", "测试记忆内容")]
        mock_retrieval.retrieve.return_value = memories

        delegation = coordinator.delegate(
            "ws1", "测试查询", "recall", executor_user_id="u1",
        )
        assert isinstance(delegation, AgentDelegation)
        assert delegation.agent_type == "recall"
        assert delegation.executor_user_id == "u1"
        assert delegation.result is not None
        assert delegation.success

    def test_delegate_remember(self, coordinator, mock_tool_registry):
        """委托 remember 返回成功结果。"""
        mock_tool_registry.execute.return_value = ToolResult(
            tool_name="remember",
            success=True,
            content="已存储记忆",
            metadata={"memory_id": "m_new"},
        )

        delegation = coordinator.delegate(
            "ws1", "重要信息需要记住", "remember", executor_user_id="u1",
        )
        assert delegation.agent_type == "remember"
        assert delegation.success
        mock_tool_registry.execute.assert_called()

    def test_delegate_reflect(self, coordinator, mock_tool_registry):
        """委托 reflect 返回成功结果。"""
        mock_tool_registry.execute.return_value = ToolResult(
            tool_name="reflect",
            success=True,
            content="反思完成，发现2条洞察",
            metadata={"checked": 10},
        )

        delegation = coordinator.delegate(
            "ws1", "项目进度", "reflect", executor_user_id="u1",
        )
        assert delegation.agent_type == "reflect"
        assert delegation.success

    def test_delegate_invalid_type(self, coordinator):
        """无效的 agent_type 返回失败结果。"""
        delegation = coordinator.delegate(
            "ws1", "test", "unknown_type", executor_user_id="u1",
        )
        assert not delegation.success
        assert delegation.result is not None
        assert delegation.result.error is not None
        assert "unknown_type" in delegation.result.error

    def test_delegate_with_context(self, coordinator, mock_tool_registry):
        """带 context 的委托正确合并到参数。"""
        delegation = coordinator.delegate(
            "ws1", "核心查询", "recall",
            context="前置背景信息",
            executor_user_id="u1",
        )
        assert delegation.context == "前置背景信息"
        assert delegation.agent_type == "recall"

    def test_delegate_metadata_timestamp(self, coordinator):
        """委托结果包含时间戳 metadata。"""
        delegation = coordinator.delegate("ws1", "q", "recall", executor_user_id="u1")
        assert "timestamp" in delegation.metadata

    def test_delegation_domain_defaults(self):
        """AgentDelegation 数据类默认值。"""
        d = AgentDelegation(workspace_id="ws1", query="test", agent_type="recall")
        assert d.query == "test"
        assert d.context == ""
        assert d.result is None
        assert not d.success


# ═══════════════════════════════════════════
# TeamReasoning Tests
# ═══════════════════════════════════════════


class TestTeamReasoning:
    def test_reason_empty_participants(self, coordinator):
        """空参与者返回无推理共识。"""
        reasoning = coordinator.reason("ws1", "test question", [])
        assert isinstance(reasoning, TeamReasoning)
        assert reasoning.participants == []
        assert "没有指定参与者" in reasoning.consensus

    def test_reason_single_participant(self, coordinator, mock_retrieval):
        """单参与者推理返回其见解。"""
        memories = [_make_memory("m1", "记忆1"), _make_memory("m2", "记忆2")]
        mock_retrieval.retrieve.return_value = memories

        reasoning = coordinator.reason("ws1", "项目进展如何？", ["u1"])
        assert reasoning.participant_count == 1
        assert len(reasoning.individual_insights) == 1
        assert reasoning.individual_insights[0].user_id == "u1"
        assert len(reasoning.individual_insights[0].relevant_memories) == 2

    def test_reason_multiple_participants(self, coordinator, mock_retrieval):
        """多参与者推理返回综合共识。"""
        mock_retrieval.retrieve.side_effect = [
            [_make_memory("m1", "用户1的记忆")],
            [_make_memory("m2", "用户2的记忆")],
            [_make_memory("m3", "用户3的记忆")],
        ]

        reasoning = coordinator.reason(
            "ws1", "团队目标是什么？", ["u1", "u2", "u3"],
        )
        assert reasoning.participant_count == 3
        assert len(reasoning.individual_insights) == 3
        assert reasoning.consensus != ""
        # synthesis should contain all insights
        assert reasoning.synthesis != ""

    def test_reason_no_memories(self, coordinator, mock_retrieval):
        """参与者无相关记忆时 insights 标记为空。"""
        mock_retrieval.retrieve.return_value = []

        reasoning = coordinator.reason("ws1", "未知主题", ["u1"])
        assert len(reasoning.individual_insights) == 1
        ins = reasoning.individual_insights[0]
        assert "未找到相关记忆" in ins.insight

    def test_reasoning_domain_defaults(self):
        """TeamReasoning 数据类默认值。"""
        tr = TeamReasoning(workspace_id="ws1", question="q")
        assert tr.participants == []
        assert tr.consensus == ""
        assert tr.individual_insights == []

    def test_participant_insight_defaults(self):
        """ParticipantInsight 数据类默认值。"""
        pi = ParticipantInsight(user_id="u1", insight="test")
        assert pi.user_id == "u1"
        assert pi.insight == "test"
        assert pi.relevant_memories == []


# ═══════════════════════════════════════════
# API Endpoint Tests
# ═══════════════════════════════════════════


class TestAgentCollabAPI:
    def test_delegate_endpoint_success(self, client, auth_store, collab_store, coordinator, token_service):
        """POST /workspace/{id}/agent/delegate 返回成功。"""
        headers = _make_auth_headers("u1", "ws1")

        res = client.post("/workspace/ws1/agent/delegate", json={
            "query": "测试查询", "agent_type": "recall",
        }, headers=headers)

        assert res.status_code == 200
        data = res.json()
        assert data["agent_type"] == "recall"
        assert "success" in data
        assert "result" in data

    def test_delegate_endpoint_invalid_type(self, client, auth_store, token_service):
        """无效 agent_type 返回 422 验证错误。"""
        headers = _make_auth_headers("u1", "ws1")
        res = client.post("/workspace/ws1/agent/delegate", json={
            "query": "test", "agent_type": "invalid",
        }, headers=headers)
        assert res.status_code == 422

    def test_context_endpoint(self, client, auth_store, token_service):
        """GET /workspace/{id}/agent/context 返回共享上下文。"""
        headers = _make_auth_headers("u1", "ws1")
        res = client.get("/workspace/ws1/agent/context", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["workspace_id"] == "ws1"
        assert "member_count" in data
        assert "total_memories" in data
        assert "team_memories" in data
        assert "summary" in data

    def test_context_endpoint_with_query(self, client, auth_store, token_service):
        """GET /workspace/{id}/agent/context?query=xxx 传递查询参数。"""
        headers = _make_auth_headers("u1", "ws1")
        res = client.get(
            "/workspace/ws1/agent/context?query=AI&top_k=5",
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["query"] == "AI"

    def test_reason_endpoint(self, client, auth_store, token_service):
        """POST /workspace/{id}/agent/reason 返回推理结果。"""
        headers = _make_auth_headers("u1", "ws1")
        res = client.post("/workspace/ws1/agent/reason", json={
            "question": "团队下一步行动是什么？",
            "participants": ["u1", "u2"],
        }, headers=headers)

        assert res.status_code == 200
        data = res.json()
        assert data["question"] == "团队下一步行动是什么？"
        assert data["participants"] == ["u1", "u2"]
        assert "consensus" in data
        assert "synthesis" in data
        assert "individual_insights" in data

    def test_reason_endpoint_single_participant(self, client, auth_store, token_service):
        """单参与者推理返回结构正确。"""
        headers = _make_auth_headers("u1", "ws1")
        res = client.post("/workspace/ws1/agent/reason", json={
            "question": "我的待办事项？",
            "participants": ["u1"],
        }, headers=headers)

        assert res.status_code == 200
        data = res.json()
        assert len(data["individual_insights"]) == 1

    def test_delegate_remember_endpoint(self, client, auth_store, coordinator, token_service):
        """POST delegate with remember 类型。"""
        headers = _make_auth_headers("u1", "ws1")
        res = client.post("/workspace/ws1/agent/delegate", json={
            "query": "需要记住的重要内容",
            "agent_type": "remember",
            "context": "项目上下文",
        }, headers=headers)

        assert res.status_code == 200
        data = res.json()
        assert data["agent_type"] == "remember"

    def test_delegate_reflect_endpoint(self, client, auth_store, coordinator, token_service):
        """POST delegate with reflect 类型。"""
        headers = _make_auth_headers("u1", "ws1")
        res = client.post("/workspace/ws1/agent/delegate", json={
            "query": "项目回顾",
            "agent_type": "reflect",
        }, headers=headers)

        assert res.status_code == 200
        data = res.json()
        assert data["agent_type"] == "reflect"
