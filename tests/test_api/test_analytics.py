"""Team Analytics 测试 — memory_by_type / growth_trend / contributors / media / 聚合 / 降级。"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adapters.collab_store import CollabStore, CollaborationService
from src.adapters.sqlite_store import SQLiteStoreAdapter
from src.api.middleware import JWTTokenService, init_auth
from src.adapters.auth_store import SQLiteAuthStore
from src.api.analytics_router import create_analytics_router
from src.core.analytics import WorkspaceAnalytics
from src.core.collaboration import AuditAction, AuditLog


# ── Fixtures ──


@pytest.fixture
def analytics_db(settings, tmp_path):
    """创建共享数据库 — 同时有 SQLiteStoreAdapter 的 notes/entities 表和
    CollabStore 的协作表。"""
    db_path = str(tmp_path / "analytics_test.db")
    mem_store = SQLiteStoreAdapter(settings, db_path=db_path)
    collab_store = CollabStore(settings, db_path=db_path)
    yield collab_store, mem_store
    mem_store.close()
    collab_store.close()


@pytest.fixture
def collab_service(analytics_db):
    collab_store, _mem_store = analytics_db
    return CollaborationService(collab_store)


@pytest.fixture
def token_service():
    return JWTTokenService()


@pytest.fixture
def mock_agent(analytics_db):
    _collab_store, mem_store = analytics_db
    agent = MagicMock()
    agent._memory_store = mem_store
    return agent


@pytest.fixture
def client(analytics_db, settings, token_service, mock_agent):
    collab_store, _mem_store = analytics_db
    auth_store = SQLiteAuthStore(settings, db_path=":memory:")
    collab_svc = CollaborationService(collab_store, auth_store)

    app = FastAPI()
    init_auth(token_service, auth_store)
    app.include_router(create_analytics_router(collab_svc, mock_agent))
    return TestClient(app)


# ── Helpers for direct notes table insertion ──


def _insert_note(collab_store, mem_id, content, timestamp, memory_type="episodic",
                 workspace_id="ws1", status="active"):
    """直接向 notes 表插入测试数据（绕过 mem_store 的 workspace_id 限制）。"""
    collab_store._db.execute(
        """INSERT INTO notes (id, content, summary, source, timestamp, importance,
           entities_json, relations_json, memory_type, status, workspace_id)
           VALUES (?, ?, '', 'user', ?, 5, '[]', '[]', ?, ?, ?)""",
        [mem_id, content, timestamp.isoformat(), memory_type, status, workspace_id],
    )


def _insert_entity(collab_store, name, mention_count, workspace_id="ws1"):
    """直接向 entities 表插入测试数据。"""
    collab_store._db.execute(
        """INSERT INTO entities (name, entity_type, first_seen, mention_count, workspace_id)
           VALUES (?, '', datetime('now'), ?, ?)""",
        [name, mention_count, workspace_id],
    )


# ── Tests: Store Methods ──


class TestMemoryByType:
    """测试 get_memory_by_type — 按类型分组统计。"""

    def test_groups_by_memory_type(self, analytics_db):
        collab_store, mem_store = analytics_db
        now = datetime.now(timezone.utc)

        _insert_note(collab_store, "m1", "episodic mem", now, "episodic")
        _insert_note(collab_store, "m2", "semantic mem", now, "semantic")
        _insert_note(collab_store, "m3", "another episodic", now, "episodic")

        result = collab_store.get_memory_by_type("ws1", mem_store)
        assert result["episodic"] == 2
        assert result["semantic"] == 1

    def test_empty_workspace_returns_empty_dict(self, analytics_db):
        collab_store, mem_store = analytics_db
        result = collab_store.get_memory_by_type("nonexistent", mem_store)
        assert result == {}


class TestGrowthTrend:
    """测试 get_growth_trend — 按天聚合新增记忆。"""

    def test_daily_aggregation(self, analytics_db):
        collab_store, mem_store = analytics_db
        now = datetime.now(timezone.utc)
        d2 = now - timedelta(days=2)

        # 2 days ago: 2 memories
        _insert_note(collab_store, "m1", "day2-a", d2, "episodic")
        _insert_note(collab_store, "m2", "day2-b", d2, "semantic")

        # today: 3 memories
        _insert_note(collab_store, "m3", "today-a", now, "episodic")
        _insert_note(collab_store, "m4", "today-b", now, "semantic")
        _insert_note(collab_store, "m5", "today-c", now, "reflect")

        result = collab_store.get_growth_trend("ws1", mem_store, days=30)
        assert len(result) >= 2  # at least 2 distinct days

        # The day-2 entry should have count=2
        day2_str = d2.strftime("%Y-%m-%d")
        day2_entry = next((r for r in result if r["date"] == day2_str), None)
        assert day2_entry is not None
        assert day2_entry["count"] == 2

    def test_respects_days_param(self, analytics_db):
        collab_store, mem_store = analytics_db
        now = datetime.now(timezone.utc)
        d60 = now - timedelta(days=60)

        _insert_note(collab_store, "m_old", "old mem", d60, "episodic")
        _insert_note(collab_store, "m_new", "new mem", now, "episodic")

        # With days=90, should include both days
        result90 = collab_store.get_growth_trend("ws1", mem_store, days=90)
        d60_str = d60.strftime("%Y-%m-%d")
        assert any(r["date"] == d60_str for r in result90)

        # With days=7, should exclude the old day
        result7 = collab_store.get_growth_trend("ws1", mem_store, days=7)
        assert not any(r["date"] == d60_str for r in result7)

    def test_empty_workspace_returns_empty_list(self, analytics_db):
        collab_store, mem_store = analytics_db
        result = collab_store.get_growth_trend("nonexistent", mem_store)
        assert result == []


class TestTopContributors:
    """测试 get_top_contributors — 成员贡献排序。"""

    def test_orders_by_contribution_count(self, analytics_db):
        collab_store, _mem_store = analytics_db
        workspace_id = "ws1"
        now = datetime.now(timezone.utc)

        # u1: 5 memory operations
        for i in range(5):
            collab_store.log_audit(AuditLog(
                workspace_id=workspace_id, user_id="u1",
                action=AuditAction.MEMORY_CREATE,
                resource_type="memory", resource_id=f"m{i}",
                timestamp=now,
            ))
        # u2: 2 memory operations
        for i in range(2):
            collab_store.log_audit(AuditLog(
                workspace_id=workspace_id, user_id="u2",
                action=AuditAction.MEMORY_UPDATE,
                resource_type="memory", resource_id=f"m{i+10}",
                timestamp=now,
            ))
        # u3: 1 non-memory operation (should not count)
        collab_store.log_audit(AuditLog(
            workspace_id=workspace_id, user_id="u3",
            action=AuditAction.MEMBER_ADD,
            resource_type="member", resource_id="u3",
            timestamp=now,
        ))

        result = collab_store.get_top_contributors(workspace_id, days=30)
        assert len(result) == 2  # only u1 and u2 (memory_* actions)
        assert result[0]["user_id"] == "u1"
        assert result[0]["count"] == 5
        assert result[1]["user_id"] == "u2"
        assert result[1]["count"] == 2

    def test_empty_when_no_contributions(self, analytics_db):
        collab_store, _mem_store = analytics_db
        result = collab_store.get_top_contributors("empty_ws", days=30)
        assert result == []


class TestMediaBreakdown:
    """测试 get_media_breakdown — 媒体类型分布。"""

    def test_classifies_by_content_prefix(self, analytics_db):
        collab_store, mem_store = analytics_db
        now = datetime.now(timezone.utc)

        _insert_note(collab_store, "m_img", "[图片记忆·情景] photo analysis", now, "episodic")
        _insert_note(collab_store, "m_audio", "[音频记忆·语义] meeting recording", now, "semantic")
        _insert_note(collab_store, "m_video", "[视频记忆·工作区] tutorial", now, "working")
        _insert_note(collab_store, "m_text", "plain text memory", now, "episodic")
        _insert_note(collab_store, "m_text2", "another text note", now, "semantic")

        result = collab_store.get_media_breakdown("ws1", mem_store)
        assert result["image"] == 1
        assert result["audio"] == 1
        assert result["video"] == 1
        assert result["text"] == 2

    def test_all_text_when_no_media_prefixes(self, analytics_db):
        collab_store, mem_store = analytics_db
        now = datetime.now(timezone.utc)

        for i in range(3):
            _insert_note(collab_store, f"m{i}", f"text memory {i}", now, "episodic")

        result = collab_store.get_media_breakdown("ws1", mem_store)
        assert result["text"] == 3
        assert result["image"] == 0
        assert result["audio"] == 0
        assert result["video"] == 0

    def test_empty_workspace_returns_zeros(self, analytics_db):
        collab_store, mem_store = analytics_db
        result = collab_store.get_media_breakdown("nonexistent", mem_store)
        assert result == {"text": 0, "image": 0, "audio": 0, "video": 0}


class TestWorkspaceAnalytics:
    """测试 get_workspace_analytics — 聚合返回。"""

    def test_returns_workspace_analytics_instance(self, analytics_db):
        collab_store, mem_store = analytics_db
        result = collab_store.get_workspace_analytics("ws1", mem_store)
        assert isinstance(result, WorkspaceAnalytics)
        assert hasattr(result, "member_count")
        assert hasattr(result, "memory_by_type")
        assert hasattr(result, "media_breakdown")

    def test_empty_workspace_returns_defaults(self, analytics_db):
        collab_store, mem_store = analytics_db
        result = collab_store.get_workspace_analytics("nonexistent", mem_store)
        assert result.member_count == 0
        assert result.memory_by_type == {}
        assert result.memory_growth == []
        assert result.top_entities == []
        assert result.top_contributors == []
        assert result.action_completion_rate == 0.0
        assert result.media_breakdown == {"text": 0, "image": 0, "audio": 0, "video": 0}
        assert result.weekly_active_users == 0

    def test_aggregates_all_metrics(self, analytics_db):
        """全面聚合测试 — 同时有记忆、实体、贡献者的场景。"""
        collab_store, mem_store = analytics_db
        workspace_id = "ws1"
        now = datetime.now(timezone.utc)

        # 记忆
        _insert_note(collab_store, "ma", "episodic A", now, "episodic", workspace_id)
        _insert_note(collab_store, "mb", "semantic B", now, "semantic", workspace_id)
        _insert_note(collab_store, "mc", "[图片记忆] photo", now, "episodic", workspace_id)

        # 实体
        _insert_entity(collab_store, "AI", 10, workspace_id)
        _insert_entity(collab_store, "ML", 5, workspace_id)

        # 贡献者
        collab_store.log_audit(AuditLog(
            workspace_id=workspace_id, user_id="u1",
            action=AuditAction.MEMORY_CREATE,
            resource_type="memory", resource_id="m1",
            timestamp=now,
        ))

        # 行动计划
        from src.core.collaboration import ActionPlan, ActionStatus
        collab_store.create_action_plan(ActionPlan(
            workspace_id=workspace_id, title="Done", status=ActionStatus.COMPLETED,
        ))
        collab_store.create_action_plan(ActionPlan(
            workspace_id=workspace_id, title="Pending", status=ActionStatus.PENDING,
        ))

        result = collab_store.get_workspace_analytics(workspace_id, mem_store)
        assert result.memory_by_type["episodic"] == 2
        assert result.memory_by_type["semantic"] == 1
        assert len(result.memory_growth) >= 1
        assert len(result.top_entities) == 2
        assert result.top_entities[0]["name"] == "AI"
        assert len(result.top_contributors) == 1
        assert result.action_completion_rate == pytest.approx(0.50, abs=0.01)
        assert result.media_breakdown["image"] == 1
        assert result.media_breakdown["text"] == 2


class TestActionCompletionRate:
    """测试 action_completion_rate 计算。"""

    def test_calculates_completion_rate(self, analytics_db):
        collab_store, mem_store = analytics_db
        workspace_id = "ws1"
        from src.core.collaboration import ActionPlan, ActionStatus

        collab_store.create_action_plan(ActionPlan(
            workspace_id=workspace_id, title="Task A", status=ActionStatus.COMPLETED,
        ))
        collab_store.create_action_plan(ActionPlan(
            workspace_id=workspace_id, title="Task B", status=ActionStatus.PENDING,
        ))
        collab_store.create_action_plan(ActionPlan(
            workspace_id=workspace_id, title="Task C", status=ActionStatus.IN_PROGRESS,
        ))
        collab_store.create_action_plan(ActionPlan(
            workspace_id=workspace_id, title="Task D", status=ActionStatus.CANCELLED,
        ))

        result = collab_store.get_workspace_analytics(workspace_id, mem_store)
        assert result.action_completion_rate == pytest.approx(0.25, abs=0.01)

    def test_zero_when_no_actions(self, analytics_db):
        collab_store, mem_store = analytics_db
        result = collab_store.get_workspace_analytics("ws_empty", mem_store)
        assert result.action_completion_rate == 0.0


# ── Tests: API Endpoints ──


class TestAnalyticsAPI:
    """测试 REST API 端点结构（未经认证返回 401 而非 404）。"""

    def test_analytics_endpoint_registered(self, client):
        res = client.get("/workspace/ws1/analytics")
        assert res.status_code != 404

    def test_growth_endpoint_registered(self, client):
        res = client.get("/workspace/ws1/analytics/growth")
        assert res.status_code != 404

    def test_contributors_endpoint_registered(self, client):
        res = client.get("/workspace/ws1/analytics/contributors")
        assert res.status_code != 404

    def test_media_endpoint_registered(self, client):
        res = client.get("/workspace/ws1/analytics/media")
        assert res.status_code != 404
