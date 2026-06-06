"""工作区越权测试 — 验证跨 workspace 访问被拒绝。

核心安全属性：
- 用户只能访问自己有 membership 的 workspace
- 只读端点（assert_workspace_access）: viewer+ 可访问
- 管理端点（assert_workspace_manage）: 仅 admin/owner
- 无 membership 时一律 403
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adapters.auth_store import SQLiteAuthStore
from src.adapters.collab_store import CollabStore, CollaborationService
from src.api.middleware import JWTTokenService, init_auth
from src.api.workspace_router import create_workspace_router
from src.api.analytics_router import create_analytics_router
from src.core.auth import User, WorkspaceRole


# ═══════════════════════════════════════════
# 辅助 — 插种子数据 + 生成 JWT
# ═══════════════════════════════════════════


def _seed(auth_store: SQLiteAuthStore, user_id: str, ws_id: str, role: str = "admin") -> None:
    """用已知 ID 直接插入 user + workspace + membership。"""
    auth_store._db.execute(
        "INSERT OR IGNORE INTO users (id, email, name, auth_provider) VALUES (?, ?, ?, ?)",
        (user_id, f"{user_id}@ws-test.local", f"User_{user_id}", "email"),
    )
    auth_store._db.execute(
        "INSERT OR IGNORE INTO workspaces (id, name, owner_id) VALUES (?, ?, ?)",
        (ws_id, f"WS_{ws_id}", user_id),
    )
    auth_store._db.execute(
        "INSERT OR REPLACE INTO memberships (user_id, workspace_id, role) VALUES (?, ?, ?)",
        (user_id, ws_id, role),
    )


def _auth(token_service: JWTTokenService, user_id: str, ws_id: str,
          role: WorkspaceRole = WorkspaceRole.ADMIN) -> dict:
    """生成 Bearer token header。"""
    user = User(id=user_id, email=f"{user_id}@ws-test.local", name=user_id)
    tokens = token_service.create_tokens(user, ws_id, role)
    return {"Authorization": f"Bearer {tokens.access_token}"}


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════


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
    """FastAPI TestClient — 注册 workspace_router 和 analytics_router。"""
    # 用户 u1 是 ws-a 的 admin，ws-b 无 membership
    _seed(auth_store, "u1", "ws-a", "admin")
    _seed(auth_store, "u1", "ws-b-nope", "admin")  # u1 not in ws-b
    # u2 是 ws-b 的 admin
    _seed(auth_store, "u2", "ws-a", "member")
    _seed(auth_store, "u2", "ws-b", "admin")
    # u3 是 ws-a 的 viewer
    _seed(auth_store, "u3", "ws-a", "viewer")
    # u4 只在 ws-b
    _seed(auth_store, "u4", "ws-b", "member")

    app = FastAPI()
    init_auth(token_service, auth_store)
    app.include_router(create_workspace_router(collab_service, auth_store))
    app.include_router(create_analytics_router(collab_service))

    return TestClient(app)


# ═══════════════════════════════════════════
# 基础：有 membership → 200
# ═══════════════════════════════════════════


class TestAccessGranted:
    """用户在有 membership 的 workspace 中访问应成功。"""

    def test_admin_can_list_members(self, client, token_service):
        """ws-a admin 可以列出 ws-a 成员。"""
        h = _auth(token_service, "u1", "ws-a")
        r = client.get("/workspace/ws-a/members", headers=h)
        assert r.status_code == 200

    def test_admin_can_see_dashboard(self, client, token_service):
        """ws-a admin 对 ws-a dashboard 不会被鉴权拦截（无需 agent 也可通过 membership 检查）。"""
        h = _auth(token_service, "u1", "ws-a")
        r = client.get("/workspace/ws-a/dashboard", headers=h)
        # 500 是因为测试环境没有 agent 实例，但不会 401/403
        assert r.status_code not in (401, 403), (
            f"期望通过 membership 校验，实际 {r.status_code}: {r.text[:200]}"
        )

    def test_admin_can_see_activity_log(self, client, token_service):
        """ws-a admin 可以看 ws-a 活动日志。"""
        h = _auth(token_service, "u1", "ws-a")
        r = client.get("/workspace/ws-a/activity-log", headers=h)
        assert r.status_code == 200

    def test_admin_can_see_audit_log(self, client, token_service):
        """ws-a admin 可以看 ws-a 审计日志。"""
        h = _auth(token_service, "u1", "ws-a")
        r = client.get("/workspace/ws-a/audit-log", headers=h)
        assert r.status_code == 200

    def test_admin_can_see_analytics(self, client, token_service):
        """ws-a admin 可以看 ws-a 分析。"""
        h = _auth(token_service, "u1", "ws-a")
        r = client.get("/workspace/ws-a/analytics", headers=h)
        assert r.status_code == 200

    def test_member_can_list_members(self, client, token_service):
        """ws-a member 可以列出成员。"""
        h = _auth(token_service, "u2", "ws-a", WorkspaceRole.MEMBER)
        r = client.get("/workspace/ws-a/members", headers=h)
        assert r.status_code == 200

    def test_viewer_can_list_members(self, client, token_service):
        """ws-a viewer 可以列出成员。"""
        h = _auth(token_service, "u3", "ws-a", WorkspaceRole.VIEWER)
        r = client.get("/workspace/ws-a/members", headers=h)
        assert r.status_code == 200

    def test_member_can_see_user_activity(self, client, token_service):
        """ws-a member 可以看自己的用户活动。"""
        h = _auth(token_service, "u2", "ws-a", WorkspaceRole.MEMBER)
        r = client.get("/workspace/ws-a/user-activity?days=7", headers=h)
        assert r.status_code == 200


# ═══════════════════════════════════════════
# 越权：无 membership → 403
# ═══════════════════════════════════════════


class TestCrossWorkspaceDenied:
    """用户在没有 membership 的 workspace 中访问应被拒绝（403）。"""

    READ_ENDPOINTS = [
        ("GET", "/workspace/ws-b/members"),
        ("GET", "/workspace/ws-b/dashboard"),
        ("GET", "/workspace/ws-b/activity-log"),
        ("GET", "/workspace/ws-b/action-plans"),
        ("GET", "/workspace/ws-b/user-activity?days=7"),
        ("GET", "/workspace/ws-b/analytics"),
        ("GET", "/workspace/ws-b/analytics/growth?days=30"),
    ]

    WRITE_ENDPOINTS = [
        ("POST", "/workspace/ws-b/members", {"email": "new@test.com", "role": "member"}),
        ("PATCH", "/workspace/ws-b/members/u2", {"role": "admin"}),
        ("POST", "/workspace/ws-b/memory/merge", {"primary_id": "m1", "secondary_ids": ["m2"]}),
        ("POST", "/workspace/ws-b/action-plan", {"title": "Test plan"}),
    ]

    @pytest.mark.parametrize("method,path", READ_ENDPOINTS)
    def test_no_membership_read_denied(self, client, token_service, method, path):
        """u1（只在 ws-a 中）访问 ws-b 的读端点应 403。"""
        h = _auth(token_service, "u1", "ws-a")  # token 中是 ws-a，但 path 是 ws-b
        r = client.request(method, path, headers=h)
        assert r.status_code == 403, (
            f"{method} {path}: expected 403, got {r.status_code}: {r.text[:200]}"
        )

    @pytest.mark.parametrize("method,path,body", WRITE_ENDPOINTS)
    def test_no_membership_write_denied(self, client, token_service, method, path, body):
        """u1（只在 ws-a 中）访问 ws-b 的写端点应 403。"""
        h = _auth(token_service, "u1", "ws-a")
        r = client.request(method, path, headers=h, json=body)
        assert r.status_code == 403, (
            f"{method} {path}: expected 403, got {r.status_code}: {r.text[:200]}"
        )

    def test_no_membership_delete_member_denied(self, client, token_service):
        """u1 不能删除 ws-b 的成员。"""
        h = _auth(token_service, "u1", "ws-a")
        r = client.delete("/workspace/ws-b/members/u2", headers=h)
        assert r.status_code == 403

    def test_user_in_ws_a_accesses_ws_b_audit(self, client, token_service):
        """u1 不能看 ws-b 的审计日志。"""
        h = _auth(token_service, "u1", "ws-a")
        r = client.get("/workspace/ws-b/audit-log", headers=h)
        assert r.status_code == 403

    def test_user_in_ws_a_accesses_ws_b_audit_summary(self, client, token_service):
        """u1 不能看 ws-b 的审计摘要。"""
        h = _auth(token_service, "u1", "ws-a")
        r = client.get("/workspace/ws-b/audit-summary", headers=h)
        assert r.status_code == 403

    def test_cross_ws_analytics_media_denied(self, client, token_service):
        """u1 不能看 ws-b 的媒体分析。"""
        h = _auth(token_service, "u1", "ws-a")
        r = client.get("/workspace/ws-b/analytics/media", headers=h)
        assert r.status_code == 403

    def test_cross_ws_analytics_contributors_denied(self, client, token_service):
        """u1 不能看 ws-b 的贡献排行。"""
        h = _auth(token_service, "u1", "ws-a")
        r = client.get("/workspace/ws-b/analytics/contributors", headers=h)
        assert r.status_code == 403


# ═══════════════════════════════════════════
# 权限不足：有 membership 但 role 不够 → 403
# ═══════════════════════════════════════════


class TestInsufficientRole:
    """用户在 workspace 中有 membership 但 role 不足以执行管理操作。"""

    def test_viewer_cannot_add_member(self, client, token_service):
        """viewer 不能添加成员（需要 admin）。"""
        h = _auth(token_service, "u3", "ws-a", WorkspaceRole.VIEWER)
        r = client.post("/workspace/ws-a/members", json={
            "email": "someone@test.com", "role": "member",
        }, headers=h)
        assert r.status_code == 403

    def test_member_cannot_add_member(self, client, token_service):
        """普通 member 不能添加成员。"""
        h = _auth(token_service, "u2", "ws-a", WorkspaceRole.MEMBER)
        r = client.post("/workspace/ws-a/members", json={
            "email": "someone@test.com", "role": "member",
        }, headers=h)
        assert r.status_code == 403

    def test_member_cannot_update_role(self, client, token_service):
        """普通 member 不能修改成员角色。"""
        h = _auth(token_service, "u2", "ws-a", WorkspaceRole.MEMBER)
        r = client.patch("/workspace/ws-a/members/u3", json={"role": "admin"}, headers=h)
        assert r.status_code == 403

    def test_member_cannot_delete_member(self, client, token_service):
        """普通 member 不能删除成员。"""
        h = _auth(token_service, "u2", "ws-a", WorkspaceRole.MEMBER)
        r = client.delete("/workspace/ws-a/members/u3", headers=h)
        assert r.status_code == 403

    def test_member_cannot_see_audit_log(self, client, token_service):
        """普通 member 不能看审计日志。"""
        h = _auth(token_service, "u2", "ws-a", WorkspaceRole.MEMBER)
        r = client.get("/workspace/ws-a/audit-log", headers=h)
        assert r.status_code == 403

    def test_member_cannot_see_audit_summary(self, client, token_service):
        """普通 member 不能看审计摘要。"""
        h = _auth(token_service, "u2", "ws-a", WorkspaceRole.MEMBER)
        r = client.get("/workspace/ws-a/audit-summary", headers=h)
        assert r.status_code == 403

    def test_member_cannot_create_action_plan(self, client, token_service):
        """普通 member 不能创建行动计划（需要 write/manage）。"""
        h = _auth(token_service, "u2", "ws-a", WorkspaceRole.MEMBER)
        r = client.post("/workspace/ws-a/action-plan", json={"title": "test"}, headers=h)
        assert r.status_code == 403

    def test_viewer_cannot_see_analytics(self, client, token_service):
        """viewer 仍可以看分析（read access）。"""
        h = _auth(token_service, "u3", "ws-a", WorkspaceRole.VIEWER)
        r = client.get("/workspace/ws-a/analytics", headers=h)
        assert r.status_code == 200

    def test_owner_can_see_audit_summary(self, client, token_service):
        """ws-a admin 可以看 ws-a 审计摘要（admin+ 权限）。"""
        h = _auth(token_service, "u1", "ws-a", WorkspaceRole.ADMIN)
        r = client.get("/workspace/ws-a/audit-summary", headers=h)
        assert r.status_code == 200


# ═══════════════════════════════════════════
# 不存在的工作区 → 403
# ═══════════════════════════════════════════


class TestNonexistentWorkspace:
    """访问不存在的工作区 — 因为 get_membership 返回 None，应 403。"""

    def test_access_nonexistent_workspace(self, client, token_service):
        h = _auth(token_service, "u1", "ws-a")
        r = client.get("/workspace/ws-nonexistent/members", headers=h)
        assert r.status_code == 403


# ═══════════════════════════════════════════
# Token 中的 workspace_id 与 URL 路径不同 → 均校验
# ═══════════════════════════════════════════


class TestMismatchedTokenAndPath:
    """Token ws_id 与 URL path ws_id 不同：应校验路径中的 ws_id 的 membership。"""

    def test_token_ws_a_access_ws_a(self, client, token_service):
        """token ws-a + path ws-a → 应通过。"""
        h = _auth(token_service, "u1", "ws-a")
        r = client.get("/workspace/ws-a/members", headers=h)
        assert r.status_code == 200

    def test_token_ws_b_access_ws_b(self, client, token_service):
        """u4 token ws-b + path ws-b → 应通过。"""
        h = _auth(token_service, "u4", "ws-b", WorkspaceRole.MEMBER)
        r = client.get("/workspace/ws-b/members", headers=h)
        assert r.status_code == 200

    def test_token_ws_a_access_ws_b_denied(self, client, token_service):
        """u1 token ws-a + path ws-b → 应拒绝（u1 不在 ws-b）。"""
        h = _auth(token_service, "u1", "ws-a")
        r = client.get("/workspace/ws-b/analytics", headers=h)
        assert r.status_code == 403

    def test_token_ws_b_access_ws_a_denied_for_members(self, client, token_service):
        """u4 token ws-b + path ws-a → 应拒绝（u4 不在 ws-a）。"""
        h = _auth(token_service, "u4", "ws-b", WorkspaceRole.MEMBER)
        r = client.get("/workspace/ws-a/members", headers=h)
        assert r.status_code == 403
