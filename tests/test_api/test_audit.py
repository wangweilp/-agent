"""审计和通知增强测试 — 审计摘要 / 日志修剪 / 用户活动 / 通知偏好。"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adapters.auth_store import SQLiteAuthStore
from src.adapters.collab_store import CollabStore, CollaborationService
from src.api.middleware import JWTTokenService, init_auth
from src.api.workspace_router import create_workspace_router
from src.core.auth import TokenPayload, User, WorkspaceRole
from src.core.collaboration import AuditAction, AuditLog, Notification


def _seed_access(auth_store, user_id: str, ws_id: str, role: str = "admin") -> None:
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
def client(auth_store, collab_service, token_service):
    _seed_access(auth_store, "u1", "ws1", "admin")
    _seed_access(auth_store, "u2", "ws1", "member")
    _seed_access(auth_store, "anon", "ws1", "member")
    app = FastAPI()
    init_auth(token_service, auth_store)
    app.include_router(create_workspace_router(collab_service, auth_store))
    return TestClient(app)


def _make_headers(token_service, user_id="u1", workspace_id="ws1", role=WorkspaceRole.ADMIN):
    """创建带 JWT 的认证请求头。"""
    user = User(email=f"{user_id}@test.com", name=user_id)
    user.id = user_id
    tokens = token_service.create_tokens(user, workspace_id, role)
    return {"Authorization": f"Bearer {tokens.access_token}"}


def _make_headers_member(token_service, user_id="u2", workspace_id="ws1"):
    """创建 member 角色的认证请求头。"""
    return _make_headers(token_service, user_id, workspace_id, WorkspaceRole.MEMBER)


# ── Test: CollabStore Audit Summary ──


class TestAuditSummary:
    def test_audit_summary_empty_workspace(self, collab_store):
        summary = collab_store.get_audit_summary("ws-empty")
        assert summary.workspace_id == "ws-empty"
        assert summary.last_24h == {}
        assert summary.last_7d == {}
        assert summary.last_30d == {}
        assert summary.total == 0

    def test_audit_summary_mixed_actions(self, collab_store):
        now = datetime.now(timezone.utc)
        # Recent — within 24h
        collab_store.log_audit(AuditLog(
            workspace_id="ws1", user_id="u1",
            action=AuditAction.MEMORY_CREATE, resource_type="memory", resource_id="m1",
            timestamp=now,
        ))
        collab_store.log_audit(AuditLog(
            workspace_id="ws1", user_id="u1",
            action=AuditAction.MEMORY_UPDATE, resource_type="memory", resource_id="m2",
            timestamp=now - timedelta(hours=2),
        ))
        # Within 7d but outside 24h
        collab_store.log_audit(AuditLog(
            workspace_id="ws1", user_id="u2",
            action=AuditAction.MEMBER_ADD, resource_type="member", resource_id="u2",
            timestamp=now - timedelta(days=3),
        ))
        # Within 30d but outside 7d
        collab_store.log_audit(AuditLog(
            workspace_id="ws1", user_id="u3",
            action=AuditAction.WORKSPACE_CREATE, resource_type="workspace", resource_id="ws1",
            timestamp=now - timedelta(days=14),
        ))

        summary = collab_store.get_audit_summary("ws1")
        assert summary.total == 4

        # 24h: 2 actions
        assert summary.last_24h.get("memory_create", 0) == 1
        assert summary.last_24h.get("memory_update", 0) == 1

        # 7d: 24h actions + 3d action = 3
        assert summary.last_7d.get("memory_create", 0) == 1
        assert summary.last_7d.get("memory_update", 0) == 1
        assert summary.last_7d.get("member_add", 0) == 1

        # 30d: all 4
        assert summary.last_30d.get("workspace_create", 0) == 1
        # total count
        window_total = (
            sum(summary.last_30d.values())
        )
        assert window_total == 4

    def test_audit_summary_correctness(self, collab_store):
        now = datetime.now(timezone.utc)
        # 3 memory_create in the last 3 hours (all in 24h window)
        for i in range(3):
            collab_store.log_audit(AuditLog(
                workspace_id="ws2", user_id="u1",
                action=AuditAction.MEMORY_CREATE, resource_type="memory",
                resource_id=f"m{i}",
                timestamp=now - timedelta(hours=i),
            ))
        # 2 action_plan_create in last 2 days (outside 24h but inside 7d)
        for i in range(2):
            collab_store.log_audit(AuditLog(
                workspace_id="ws2", user_id="u1",
                action=AuditAction.ACTION_PLAN_CREATE, resource_type="action_plan",
                resource_id=f"ap{i}",
                timestamp=now - timedelta(days=2, hours=i),
            ))

        summary = collab_store.get_audit_summary("ws2")
        assert summary.total == 5
        assert summary.last_24h.get("memory_create", 0) == 3
        assert summary.last_24h.get("action_plan_create", 0) == 0
        assert summary.last_7d.get("memory_create", 0) == 3
        assert summary.last_7d.get("action_plan_create", 0) == 2


# ── Test: Prune Old Logs ──


class TestPruneOldLogs:
    def test_prune_removes_old_logs(self, collab_store):
        now = datetime.now(timezone.utc)
        # Old: 100 days ago
        collab_store.log_audit(AuditLog(
            workspace_id="ws1", user_id="u1",
            action=AuditAction.MEMORY_CREATE, resource_type="memory", resource_id="old1",
            timestamp=now - timedelta(days=100),
        ))
        collab_store.log_audit(AuditLog(
            workspace_id="ws1", user_id="u1",
            action=AuditAction.MEMORY_DELETE, resource_type="memory", resource_id="old2",
            timestamp=now - timedelta(days=120),
        ))
        # Recent: 1 day ago
        collab_store.log_audit(AuditLog(
            workspace_id="ws1", user_id="u2",
            action=AuditAction.MEMORY_UPDATE, resource_type="memory", resource_id="new1",
            timestamp=now - timedelta(days=1),
        ))

        # Prune logs older than 30 days
        deleted = collab_store.prune_old_logs("ws1", 30)
        assert deleted == 2

        remaining = collab_store.list_audit_logs("ws1", limit=10)
        assert len(remaining) == 1
        assert remaining[0].action == AuditAction.MEMORY_UPDATE

    def test_prune_nothing_when_all_recent(self, collab_store):
        now = datetime.now(timezone.utc)
        collab_store.log_audit(AuditLog(
            workspace_id="ws2", user_id="u1",
            action=AuditAction.MEMORY_CREATE, resource_type="memory", resource_id="m1",
            timestamp=now,
        ))

        deleted = collab_store.prune_old_logs("ws2", 30)
        assert deleted == 0
        logs = collab_store.list_audit_logs("ws2")
        assert len(logs) == 1

    def test_prune_respects_workspace(self, collab_store):
        now = datetime.now(timezone.utc)
        # ws1: old logs
        collab_store.log_audit(AuditLog(
            workspace_id="ws1", user_id="u1",
            action=AuditAction.MEMORY_CREATE, resource_type="memory", resource_id="m1",
            timestamp=now - timedelta(days=60),
        ))
        # ws2: old logs
        collab_store.log_audit(AuditLog(
            workspace_id="ws2", user_id="u2",
            action=AuditAction.MEMBER_ADD, resource_type="member", resource_id="u2",
            timestamp=now - timedelta(days=60),
        ))

        # Only prune ws1
        deleted = collab_store.prune_old_logs("ws1", 30)
        assert deleted == 1

        ws1_logs = collab_store.list_audit_logs("ws1")
        ws2_logs = collab_store.list_audit_logs("ws2")
        assert len(ws1_logs) == 0
        assert len(ws2_logs) == 1


# ── Test: User Activity Timeline ──


class TestUserActivityTimeline:
    def test_user_activity_timeline(self, collab_store):
        now = datetime.now(timezone.utc)
        # Activity across 5 days
        for d in range(5):
            for i in range(d + 1):
                collab_store.log_audit(AuditLog(
                    workspace_id="ws1", user_id="u1",
                    action=AuditAction.MEMORY_CREATE if i % 2 == 0 else AuditAction.MEMORY_UPDATE,
                    resource_type="memory", resource_id=f"m{d}-{i}",
                    timestamp=now - timedelta(days=d, hours=i),
                ))

        activity = collab_store.get_user_activity_timeline("u1", "ws1", days=7)
        assert activity.user_id == "u1"
        assert activity.workspace_id == "ws1"
        assert activity.total_actions == 15  # sum(1..5) = 15
        assert len(activity.daily_actions) == 5  # 5 distinct days
        assert len(activity.top_actions) >= 1

    def test_user_activity_empty(self, collab_store):
        activity = collab_store.get_user_activity_timeline("nobody", "ws1", days=7)
        assert activity.user_id == "nobody"
        assert activity.total_actions == 0
        assert activity.daily_actions == []
        assert activity.top_actions == []

    def test_user_activity_days_limit(self, collab_store):
        now = datetime.now(timezone.utc)
        # Activity 10 days ago
        collab_store.log_audit(AuditLog(
            workspace_id="ws1", user_id="u1",
            action=AuditAction.MEMORY_CREATE, resource_type="memory", resource_id="m-old",
            timestamp=now - timedelta(days=10),
        ))
        # Activity today
        collab_store.log_audit(AuditLog(
            workspace_id="ws1", user_id="u1",
            action=AuditAction.MEMORY_UPDATE, resource_type="memory", resource_id="m-new",
            timestamp=now,
        ))

        # Only 7 day window — should exclude the 10-day-old entry
        activity = collab_store.get_user_activity_timeline("u1", "ws1", days=7)
        assert activity.total_actions == 1


# ── Test: Notification Preferences ──


class TestNotificationPreferences:
    def test_get_default_preferences(self, collab_store):
        prefs = collab_store.get_notification_preferences("u1", "ws1")
        assert prefs.user_id == "u1"
        assert prefs.workspace_id == "ws1"
        assert prefs.email_enabled is True
        assert prefs.push_enabled is True
        assert prefs.digest_frequency == "daily"

    def test_update_and_read_preferences(self, collab_store):
        from src.core.audit import NotificationPreferences

        prefs = NotificationPreferences(
            user_id="u1", workspace_id="ws1",
            email_enabled=False, push_enabled=True, digest_frequency="weekly",
        )
        collab_store.update_notification_preferences(prefs)

        fetched = collab_store.get_notification_preferences("u1", "ws1")
        assert fetched.email_enabled is False
        assert fetched.push_enabled is True
        assert fetched.digest_frequency == "weekly"

    def test_update_is_idempotent(self, collab_store):
        from src.core.audit import NotificationPreferences

        prefs = NotificationPreferences(
            user_id="u2", workspace_id="ws2",
            email_enabled=False, push_enabled=False, digest_frequency="none",
        )
        collab_store.update_notification_preferences(prefs)
        # Update again with different values
        prefs.email_enabled = True
        collab_store.update_notification_preferences(prefs)

        fetched = collab_store.get_notification_preferences("u2", "ws2")
        assert fetched.email_enabled is True
        assert fetched.push_enabled is False
        assert fetched.digest_frequency == "none"


# ── Test: API Endpoints ──


class TestAuditEndpoints:
    def test_audit_summary_endpoint_require_manage(self, collab_store, client, token_service):
        # Member should get 403
        headers_member = _make_headers_member(token_service)
        res = client.get("/workspace/ws1/audit-summary", headers=headers_member)
        assert res.status_code == 403

    def test_audit_summary_endpoint_admin(self, collab_store, client, token_service):
        now = datetime.now(timezone.utc)
        collab_store.log_audit(AuditLog(
            workspace_id="ws1", user_id="u1",
            action=AuditAction.MEMORY_CREATE, resource_type="memory", resource_id="m1",
            timestamp=now,
        ))
        headers = _make_headers(token_service)
        res = client.get("/workspace/ws1/audit-summary", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["workspace_id"] == "ws1"
        assert data["total"] == 1

    def test_user_activity_endpoint(self, collab_store, client, token_service):
        now = datetime.now(timezone.utc)
        collab_store.log_audit(AuditLog(
            workspace_id="ws1", user_id="u1",
            action=AuditAction.MEMORY_CREATE, resource_type="memory", resource_id="m1",
            timestamp=now,
        ))
        headers = _make_headers(token_service, user_id="u1")
        res = client.get("/workspace/ws1/user-activity?days=7", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["user_id"] == "u1"
        assert data["total_actions"] == 1

    def test_user_activity_endpoint_days_param(self, collab_store, client, token_service):
        headers = _make_headers(token_service, user_id="u1")
        # Invalid: days < 1
        res = client.get("/workspace/ws1/user-activity?days=0", headers=headers)
        assert res.status_code == 422

        # Invalid: days > 90
        res = client.get("/workspace/ws1/user-activity?days=100", headers=headers)
        assert res.status_code == 422

    def test_notification_preferences_api(self, collab_store, client, token_service):
        headers = _make_headers(token_service, user_id="u1")

        # GET defaults
        res = client.get("/notifications/preferences", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["email_enabled"] is True
        assert data["digest_frequency"] == "daily"

        # PATCH update
        res = client.patch("/notifications/preferences", json={
            "email_enabled": False, "digest_frequency": "weekly",
        }, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["email_enabled"] is False
        assert data["digest_frequency"] == "weekly"

        # Verify persistence
        res = client.get("/notifications/preferences", headers=headers)
        data = res.json()
        assert data["email_enabled"] is False

    def test_notification_preferences_invalid_digest(self, collab_store, client, token_service):
        headers = _make_headers(token_service)
        res = client.patch("/notifications/preferences", json={
            "digest_frequency": "hourly",
        }, headers=headers)
        assert res.status_code == 400

    def test_notification_preferences_partial_update(self, collab_store, client, token_service):
        headers = _make_headers(token_service, user_id="u1")

        # Set initial
        client.patch("/notifications/preferences", json={
            "email_enabled": False, "push_enabled": False, "digest_frequency": "none",
        }, headers=headers)

        # Partial: only update push
        res = client.patch("/notifications/preferences", json={
            "push_enabled": True,
        }, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["email_enabled"] is False  # unchanged
        assert data["push_enabled"] is True    # updated
        assert data["digest_frequency"] == "none"  # unchanged


# ── Test: Domain Data Classes ──


class TestAuditDomain:
    def test_audit_summary_defaults(self):
        from src.core.audit import AuditSummary
        s = AuditSummary(workspace_id="ws1")
        assert s.total == 0
        assert s.last_24h == {}

    def test_user_activity_defaults(self):
        from src.core.audit import UserActivity
        a = UserActivity(user_id="u1", workspace_id="ws1")
        assert a.daily_actions == []
        assert a.top_actions == []
        assert a.total_actions == 0

    def test_notification_preferences_defaults(self):
        from src.core.audit import NotificationPreferences
        p = NotificationPreferences(user_id="u1", workspace_id="ws1")
        assert p.email_enabled is True
        assert p.push_enabled is True
        assert p.digest_frequency == "daily"

    def test_audit_store_protocol(self):
        from src.core.audit import AuditStore
        from src.core.collaboration import AuditLogStore, NotificationStore

        # CollabStore should satisfy the simpler protocols
        assert hasattr(AuditLogStore, "log")
        assert hasattr(AuditLogStore, "list_for_workspace")
        assert hasattr(AuditLogStore, "list_for_user")
        assert hasattr(NotificationStore, "unread_count")
