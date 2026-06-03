"""Team Collaboration 测试 — 成员管理 / 任务 / 审计 / 通知 / Dashboard。"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adapters.auth_store import SQLiteAuthStore, WorkspaceContext
from src.adapters.collab_store import CollabStore, CollaborationService
from src.api.middleware import JWTTokenService, init_auth
from src.api.workspace_router import create_workspace_router
from src.core.auth import TokenPayload, WorkspaceRole
from src.core.collaboration import (
    ActionPlan, ActionPriority, ActionStatus, AuditAction, AuditLog, Notification,
)


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
def mock_agent():
    agent = MagicMock()
    agent._memory_store = MagicMock()
    agent._memory_store.list_all.return_value = []
    agent._memory_store.get_by_id.return_value = None
    return agent


@pytest.fixture
def client(auth_store, collab_service, token_service, mock_agent):
    app = FastAPI()
    init_auth(token_service, auth_store)
    app.include_router(create_workspace_router(collab_service, auth_store, mock_agent))
    return TestClient(app)


def _register_and_get_token(client, email="test@team.com") -> tuple[str, str, str]:
    """注册用户并返回 (token, user_id, workspace_id)。"""
    from src.core.auth import User
    from src.adapters.auth_store import SQLiteAuthStore

    res = client.post("/workspace/../auth/register", json={
        "email": email, "password": "team123456", "name": email.split("@")[0],
    })
    if res.status_code == 404:  # register endpoint not on this router
        # Manually create user + workspace via auth_store
        # Need access to the auth_store used by client
        return "", "", ""

    if res.status_code != 200:
        return "", "", ""

    data = res.json()
    return data["access_token"], data["user"]["id"], data["workspace"]["id"]


def _make_auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Test: Collab Store ──


class TestCollabStore:
    def test_create_action_plan(self, collab_store):
        plan = ActionPlan(workspace_id="ws1", title="学习 AI", description="学习RAG",
                          assigned_to="u1", priority=ActionPriority.HIGH)
        result = collab_store.create_action_plan(plan)
        assert result.id == plan.id
        assert result.title == "学习 AI"

    def test_list_action_plans(self, collab_store):
        collab_store.create_action_plan(ActionPlan(workspace_id="ws1", title="任务A", assigned_to="u1"))
        collab_store.create_action_plan(ActionPlan(workspace_id="ws1", title="任务B", assigned_to="u2"))

        plans = collab_store.list_action_plans("ws1")
        assert len(plans) == 2

    def test_filter_by_assignee(self, collab_store):
        collab_store.create_action_plan(ActionPlan(workspace_id="ws1", title="A", assigned_to="u1"))
        collab_store.create_action_plan(ActionPlan(workspace_id="ws2", title="B", assigned_to="u1"))

        plans = collab_store.list_action_plans("ws1", assignee="u1")
        assert len(plans) == 1
        assert plans[0].title == "A"

    def test_update_action_plan(self, collab_store):
        plan = collab_store.create_action_plan(ActionPlan(workspace_id="ws1", title="原始"))
        plan.title = "已更新"
        plan.status = ActionStatus.IN_PROGRESS
        collab_store.update_action_plan(plan)

        fetched = collab_store.get_action_plan("ws1", plan.id)
        assert fetched is not None
        assert fetched.title == "已更新"
        assert fetched.status == ActionStatus.IN_PROGRESS

    def test_delete_action_plan(self, collab_store):
        plan = collab_store.create_action_plan(ActionPlan(workspace_id="ws1", title="待删除"))
        collab_store.delete_action_plan("ws1", plan.id)
        assert collab_store.get_action_plan("ws1", plan.id) is None

    def test_audit_log_write_and_read(self, collab_store):
        collab_store.log_audit(AuditLog(workspace_id="ws1", user_id="u1",
            action=AuditAction.MEMORY_CREATE, resource_type="memory", resource_id="m1",
            detail="创建记忆"))
        collab_store.log_audit(AuditLog(workspace_id="ws1", user_id="u2",
            action=AuditAction.MEMBER_ADD, resource_type="member", resource_id="u2",
            detail="添加成员"))

        logs = collab_store.list_audit_logs("ws1", limit=10)
        assert len(logs) == 2
        assert logs[0].action == AuditAction.MEMBER_ADD  # newest first

    def test_audit_filter_by_action(self, collab_store):
        collab_store.log_audit(AuditLog(workspace_id="ws1", user_id="u1",
            action=AuditAction.MEMORY_DELETE, resource_type="memory", resource_id="m1"))
        collab_store.log_audit(AuditLog(workspace_id="ws1", user_id="u2",
            action=AuditAction.MEMORY_CREATE, resource_type="memory", resource_id="m2"))

        logs = collab_store.list_audit_logs("ws1", action="memory_delete")
        assert len(logs) == 1
        assert logs[0].action == AuditAction.MEMORY_DELETE

    def test_notification_send_and_read(self, collab_store):
        collab_store.send_notification(Notification(
            user_id="u1", workspace_id="ws1", title="测试通知", body="内容",
        ))
        notifs = collab_store.list_notifications("u1", "ws1")
        assert len(notifs) == 1
        assert not notifs[0].read

        collab_store.mark_notification_read(notifs[0].id, "u1")
        notifs2 = collab_store.list_notifications("u1", "ws1")
        assert notifs2[0].read

    def test_unread_count(self, collab_store):
        collab_store.send_notification(Notification(user_id="u1", workspace_id="ws1", title="N1", body=""))
        collab_store.send_notification(Notification(user_id="u1", workspace_id="ws1", title="N2", body=""))

        assert collab_store.unread_count("u1", "ws1") == 2
        collab_store.mark_all_read("u1", "ws1")
        assert collab_store.unread_count("u1", "ws1") == 0

    def test_activity_events(self, collab_store):
        from src.core.collaboration import ActivityEvent
        collab_store.log_activity(ActivityEvent(
            workspace_id="ws1", user_id="u1", user_name="Alice",
            event_type="memory_created", message="创建了新记忆",
        ))
        collab_store.log_activity(ActivityEvent(
            workspace_id="ws1", user_id="u2", user_name="Bob",
            event_type="action_completed", message="完成了任务",
        ))

        events = collab_store.recent_activity("ws1", limit=10)
        assert len(events) == 2


# ── Test: CollaborationService ──


class TestCollaborationService:
    def test_create_action_with_audit(self, collab_store, auth_store):
        svc = CollaborationService(collab_store, auth_store)
        plan = ActionPlan(workspace_id="ws1", title="协作任务", assigned_to="u2")
        result = svc.create_action(plan, "u1", "Alice")

        assert result.title == "协作任务"
        # 应有审计日志
        logs = collab_store.list_audit_logs("ws1")
        assert any(l.action == AuditAction.ACTION_PLAN_CREATE for l in logs)
        # 应有通知
        notifs = collab_store.list_notifications("u2", "ws1")
        assert len(notifs) == 1
        # 通知标题是硬编码的"新任务分配"
        assert "分配" in notifs[0].title

    def test_complete_action(self, collab_store):
        svc = CollaborationService(collab_store)
        plan = collab_store.create_action_plan(ActionPlan(workspace_id="ws1", title="待完成"))
        result = svc.complete_action(plan.id, "ws1", "u1", "Alice")

        assert result is not None
        assert result.status == ActionStatus.COMPLETED
        assert result.completed_at is not None

    def test_merge_workspace_memories(self, collab_service, mock_agent):
        from src.core.types import Memory
        mem2 = Memory(
            id="m2", content="重复记忆2", summary=None, source="user",
            timestamp=datetime.now(timezone.utc), importance=5,
            memory_type="episodic", status="active",
        )
        mock_agent._memory_store.get_by_id.return_value = mem2

        count = collab_service.merge_workspace_memories(
            "ws1", "m1", ["m2"], "u1", "Alice", mock_agent._memory_store,
        )
        assert count == 1
        assert mem2.status == "merged"


# ── Test: Team Dashboard ──


class TestTeamDashboard:
    def test_dashboard_returns_stats(self, collab_service, mock_agent):
        stats = collab_service.get_dashboard("ws1", mock_agent._memory_store)
        assert stats.total_memories >= 0
        assert isinstance(stats.total_actions, int)

    def test_activity_log_returns_list(self, collab_service):
        log = collab_service.get_activity_log("ws1", limit=10)
        assert isinstance(log, list)


# ── Test: ActionPlan Domain ──


class TestActionPlanDomain:
    def test_status_enum(self):
        assert ActionStatus.PENDING.value == "pending"
        assert ActionStatus.COMPLETED.value == "completed"

    def test_priority_enum(self):
        assert ActionPriority.URGENT.value == "urgent"
        assert ActionPriority.LOW.value == "low"

    def test_plan_defaults(self):
        plan = ActionPlan(workspace_id="ws1", title="默认")
        assert plan.status == ActionStatus.PENDING
        assert plan.priority == ActionPriority.MEDIUM


# ── Test: AuditLog Domain ──


class TestAuditLogDomain:
    def test_all_actions_defined(self):
        actions = list(AuditAction)
        assert AuditAction.MEMORY_CREATE in actions
        assert AuditAction.MEMBER_ADD in actions
        assert AuditAction.ACTION_PLAN_COMPLETE in actions
        assert len(actions) >= 10  # 至少 10 种操作类型

    def test_log_defaults(self):
        log = AuditLog(workspace_id="ws1", user_id="u1",
                       action=AuditAction.MEMORY_CREATE,
                       resource_type="memory", resource_id="m1")
        assert log.id != ""
        assert log.timestamp is not None
