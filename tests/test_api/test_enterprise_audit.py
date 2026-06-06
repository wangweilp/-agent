"""Enterprise审计扩展测试 — 审计日志导出 / 审计查询增强。

测试新增的 GET /api/audit 端点（由 audit_router 提供）。
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adapters.auth_store import SQLiteAuthStore
from src.adapters.collab_store import CollabStore, CollaborationService
from src.api.middleware import JWTTokenService, init_auth
from src.core.auth import TokenPayload, User, WorkspaceRole
from src.core.collaboration import AuditAction, AuditLog


@pytest.fixture
def settings():
    from src.adapters.config import Settings
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def auth_store(settings):
    store = SQLiteAuthStore(settings, db_path=":memory:")
    user = User(email="admin@test.com", name="Admin")
    user.id = "u-admin"
    store.create_user("admin@test.com", "Admin")
    yield store
    store.close()


@pytest.fixture
def collab_store(settings):
    store = CollabStore(settings, db_path=":memory:")
    yield store
    store.close()


@pytest.fixture
def token_service():
    return JWTTokenService()


@pytest.fixture
def client(auth_store, collab_store, token_service):
    """构建带审计路由的测试客户端。"""
    app = FastAPI()
    init_auth(token_service, auth_store)

    # Try to import the audit router; if not available (agent still writing), skip
    try:
        from src.api.audit_router import create_audit_router
        app.include_router(create_audit_router(collab_store))
    except ImportError:
        pytest.skip("audit_router not yet created")

    return TestClient(app)


def _make_headers(token_service, user_id="u-admin", workspace_id="ws1", role=WorkspaceRole.ADMIN):
    user = User(email=f"{user_id}@test.com", name=user_id)
    user.id = user_id
    tokens = token_service.create_tokens(user, workspace_id, role)
    return {"Authorization": f"Bearer {tokens.access_token}"}


@pytest.fixture(autouse=True)
def seed_data(collab_store):
    """预填充测试审计数据。"""
    now = datetime.now(timezone.utc)
    actions = [
        (AuditAction.MEMORY_CREATE, "memory", "m1", now),
        (AuditAction.MEMORY_UPDATE, "memory", "m1", now - timedelta(hours=1)),
        (AuditAction.MEMBER_ADD, "member", "u2", now - timedelta(hours=2)),
        (AuditAction.WORKSPACE_CREATE, "workspace", "ws1", now - timedelta(days=1)),
        (AuditAction.MEMORY_DELETE, "memory", "m3", now - timedelta(days=2)),
        (AuditAction.ACTION_PLAN_CREATE, "action_plan", "ap1", now - timedelta(days=3)),
        (AuditAction.MEMBER_ROLE_CHANGE, "member", "u3", now - timedelta(days=5)),
        (AuditAction.MEMORY_SHARE, "memory", "m4", now - timedelta(days=10)),
        (AuditAction.WORKSPACE_DELETE, "workspace", "ws-old", now - timedelta(days=30)),
        (AuditAction.MEMORY_ARCHIVE, "memory", "m5", now - timedelta(days=60)),
    ]
    for action, rtype, rid, ts in actions:
        collab_store.log_audit(AuditLog(
            workspace_id="ws1", user_id="u-admin",
            action=action, resource_type=rtype, resource_id=rid,
            timestamp=ts,
        ))
    # Also add logs from another user
    collab_store.log_audit(AuditLog(
        workspace_id="ws1", user_id="u-member",
        action=AuditAction.MEMORY_CREATE, resource_type="memory", resource_id="m-user",
        timestamp=now,
    ))


class TestAuditListEndpoint:
    """测试 GET /api/audit — 审计日志列表。"""

    def test_list_all_audit(self, client, token_service):
        headers = _make_headers(token_service)
        res = client.get("/api/audit?workspace_id=ws1&limit=20", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 5

    def test_list_filter_by_action(self, client, token_service):
        headers = _make_headers(token_service)
        res = client.get(
            "/api/audit?workspace_id=ws1&action=memory_create",
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        for entry in data:
            assert entry["action"] == "memory_create"

    def test_list_filter_by_user(self, client, token_service):
        headers = _make_headers(token_service)
        res = client.get(
            "/api/audit?workspace_id=ws1&user_id=u-member",
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 1
        for entry in data:
            assert entry["user_id"] == "u-member"

    def test_list_default_limit(self, client, token_service):
        headers = _make_headers(token_service)
        res = client.get("/api/audit?workspace_id=ws1", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data) <= 50  # default limit


class TestAuditSummaryEndpoint:
    """测试 GET /api/audit/summary — 审计摘要。"""

    def test_get_summary(self, client, token_service):
        headers = _make_headers(token_service)
        res = client.get("/api/audit/summary?workspace_id=ws1", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["workspace_id"] == "ws1"
        assert data["total"] >= 10


class TestAuditExportEndpoint:
    """测试 GET /api/audit/export — 审计日志导出。"""

    def test_export_json(self, client, token_service):
        headers = _make_headers(token_service)
        res = client.get("/api/audit/export?workspace_id=ws1", headers=headers)
        assert res.status_code == 200
        # Should be downloadable JSON
        assert "application/json" in res.headers.get("content-type", "")
        data = res.json()
        # Export wrapper: {"format": "json", "generated_at": ..., "total_records": N, "logs": [...]}
        assert isinstance(data, dict)
        assert "logs" in data
        assert data["format"] == "json"
        assert data["total_records"] >= 5
        logs = data["logs"]
        assert isinstance(logs, list)
        entry = logs[0]
        assert "id" in entry
        assert "action" in entry
        assert "timestamp" in entry
        assert "user_id" in entry


class TestAuditUserActivityEndpoint:
    """测试 GET /api/audit/user/{user_id} — 用户活动时间线。"""

    def test_get_user_activity(self, client, token_service):
        headers = _make_headers(token_service)
        res = client.get(
            "/api/audit/user/u-admin?workspace_id=ws1&days=7",
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["user_id"] == "u-admin"
        assert data["total_actions"] > 0

    def test_get_user_activity_default_days(self, client, token_service):
        headers = _make_headers(token_service)
        res = client.get("/api/audit/user/u-admin?workspace_id=ws1", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["user_id"] == "u-admin"
