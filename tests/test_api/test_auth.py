"""Multi-Tenant Auth 测试 — 注册/登录/JWT/Workspace隔离/权限。"""
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adapters.auth_store import SQLiteAuthStore, WorkspaceAwareStore, WorkspaceContext
from src.api.auth_router import create_auth_router
from src.api.middleware import JWTTokenService, init_auth, require_auth, require_write, require_manage
from src.core.auth import TokenPayload, User, WorkspaceRole
from src.core.types import Memory


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
def token_service(auth_store):
    return JWTTokenService(auth_store=auth_store)


@pytest.fixture
def client(auth_store, token_service):
    app = FastAPI()
    init_auth(token_service, auth_store)
    app.include_router(create_auth_router(token_service, auth_store))
    return TestClient(app)


# ── Test: Register ──


class TestRegister:
    def test_register_creates_user_and_workspace(self, client):
        res = client.post("/auth/register", json={
            "email": "test@example.com", "password": "test123456", "name": "Test",
        })
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == "test@example.com"
        assert data["workspace"] is not None
        assert data["workspace"]["role"] == "owner"

    def test_register_duplicate_email_rejected(self, client):
        client.post("/auth/register", json={
            "email": "dup@example.com", "password": "password123", "name": "Dup",
        })
        res = client.post("/auth/register", json={
            "email": "dup@example.com", "password": "another456", "name": "Dup2",
        })
        assert res.status_code == 409

    def test_register_validation(self, client):
        res = client.post("/auth/register", json={"email": "", "password": "123"})
        assert res.status_code == 422  # validation error
        res = client.post("/auth/register", json={"email": "a@b.com", "password": "12"})
        assert res.status_code == 422


# ── Test: Login ──


class TestLogin:
    def test_login_returns_tokens(self, client):
        client.post("/auth/register", json={
            "email": "login@test.com", "password": "securepass", "name": "Login",
        })
        res = client.post("/auth/login", json={
            "email": "login@test.com", "password": "securepass",
        })
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["user"]["email"] == "login@test.com"

    def test_login_wrong_password(self, client):
        client.post("/auth/register", json={
            "email": "wp@test.com", "password": "rightpass", "name": "WP",
        })
        res = client.post("/auth/login", json={
            "email": "wp@test.com", "password": "wrongpass",
        })
        assert res.status_code == 401

    def test_login_nonexistent_user(self, client):
        res = client.post("/auth/login", json={
            "email": "nobody@test.com", "password": "anything",
        })
        assert res.status_code == 401


# ── Test: Refresh ──


class TestRefresh:
    def test_refresh_works(self, client):
        reg = client.post("/auth/register", json={
            "email": "refresh@test.com", "password": "refpass123", "name": "RF",
        })
        refresh_token = reg.json()["refresh_token"]

        res = client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert res.status_code == 200
        assert "access_token" in res.json()

    def test_refresh_bad_token(self, client):
        res = client.post("/auth/refresh", json={"refresh_token": "bad"})
        assert res.status_code == 401

    def test_refresh_expired_token(self, client):
        res = client.post("/auth/refresh", json={"refresh_token": "eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjEwfQ.bad"})
        assert res.status_code == 401


# ── Test: Me ──


class TestMe:
    def test_me_returns_user(self, client):
        reg = client.post("/auth/register", json={
            "email": "me@test.com", "password": "mepass123", "name": "Me",
        })
        token = reg.json()["access_token"]

        res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["user"]["email"] == "me@test.com"
        assert len(res.json()["workspaces"]) >= 1

    def test_me_unauthorized(self, client):
        res = client.get("/auth/me")
        assert res.status_code == 401


# ── Test: Workspaces ──


class TestWorkspaces:
    def test_list_workspaces(self, client):
        reg = client.post("/auth/register", json={
            "email": "ws@test.com", "password": "wspass123", "name": "WS",
        })
        token = reg.json()["access_token"]

        res = client.get("/auth/workspaces", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert len(res.json()) >= 1

    def test_create_workspace(self, client):
        reg = client.post("/auth/register", json={
            "email": "ws2@test.com", "password": "ws2pass123", "name": "WS2",
        })
        token = reg.json()["access_token"]

        res = client.post("/auth/workspaces", json={"name": "项目A"},
                          headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["name"] == "项目A"

    def test_create_workspace_unauthorized(self, client):
        res = client.post("/auth/workspaces", json={"name": "hack"})
        assert res.status_code == 401


# ── Test: JWT Token Service ──


class TestJWTTokenService:
    def test_create_and_decode(self, token_service):
        user = User(email="jwt@test.com", name="JWT")
        tokens = token_service.create_tokens(user, "ws1", WorkspaceRole.OWNER)
        payload = token_service.decode_token(tokens.access_token)
        assert payload is not None
        assert payload.user_id == user.id
        assert payload.workspace_id == "ws1"
        assert payload.role == WorkspaceRole.OWNER

    def test_bad_token_returns_none(self, token_service):
        assert token_service.decode_token("bad.token.here") is None

    def test_refresh_and_revoke(self, token_service):
        user = User(email="jwt2@test.com", name="JWT2")
        tokens = token_service.create_tokens(user, "ws1", WorkspaceRole.MEMBER)
        new_tokens = token_service.refresh_access_token(tokens.refresh_token)
        assert new_tokens is not None
        assert new_tokens.access_token != tokens.access_token

        # Revoke old refresh
        token_service.revoke_refresh_token(tokens.refresh_token)
        assert token_service.refresh_access_token(tokens.refresh_token) is None


# ── Test: JWT_SECRET_KEY Production Enforcement ──


class TestSecretKeyEnforcement:
    def test_development_auto_generates_key(self, monkeypatch):
        """非 production 模式自动生成 key，不抛异常。"""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

        from src.api import middleware
        key = middleware.resolve_jwt_secret_key(environment="development")

        assert key, "auto-generated key should exist"
        assert len(key) == 64  # 32 bytes hex = 64 chars

    def test_explicit_key_is_used(self, monkeypatch):
        """显式设置的 JWT_SECRET_KEY 被采用。"""
        monkeypatch.setenv("JWT_SECRET_KEY", "my-production-key-32bytes!!")

        from src.api import middleware

        assert middleware.resolve_jwt_secret_key() == "my-production-key-32bytes!!"
        assert middleware.JWTTokenService()._secret == "my-production-key-32bytes!!"

    def test_production_requires_explicit_key(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

        from src.api import middleware

        with pytest.raises(RuntimeError):
            middleware.resolve_jwt_secret_key(environment="production")


# ── Test: Workspace Role Permissions ──


# ── Test: Workspace Role Permissions ──


class TestRolePermissions:
    def test_owner_can_write(self):
        assert WorkspaceRole.OWNER.can_write()
        assert WorkspaceRole.OWNER.can_manage()
        assert WorkspaceRole.OWNER.can_admin()

    def test_admin_can_manage(self):
        assert WorkspaceRole.ADMIN.can_write()
        assert WorkspaceRole.ADMIN.can_manage()
        assert not WorkspaceRole.ADMIN.can_admin()

    def test_member_can_write_only(self):
        assert WorkspaceRole.MEMBER.can_write()
        assert not WorkspaceRole.MEMBER.can_manage()

    def test_viewer_read_only(self):
        assert not WorkspaceRole.VIEWER.can_write()
        assert not WorkspaceRole.VIEWER.can_manage()

    def test_hierarchy(self):
        h = WorkspaceRole.hierarchy()
        assert h["owner"] > h["admin"]
        assert h["admin"] > h["member"]
        assert h["member"] > h["viewer"]


# ── Test: WorkspaceContext ──


class TestWorkspaceContext:
    def test_set_and_get(self):
        payload = TokenPayload(
            user_id="u1", workspace_id="ws-abc", role=WorkspaceRole.ADMIN,
            email="admin@test.com",
        )
        WorkspaceContext.set(payload)
        assert WorkspaceContext.workspace_id() == "ws-abc"
        retrieved = WorkspaceContext.get()
        assert retrieved is not None
        assert retrieved.role == WorkspaceRole.ADMIN

    def test_default_workspace(self):
        WorkspaceContext.set(None)
        assert WorkspaceContext.workspace_id() == "default"


# ── Test: Auth Store ──


class TestAuthStore:
    def test_create_and_get_user(self, auth_store):
        user = auth_store.create_user("store@test.com", "Store", "hashed_xxx")
        assert user.email == "store@test.com"

        u = auth_store.get_user_by_id(user.id)
        assert u is not None
        assert u.email == "store@test.com"

        by_email = auth_store.get_by_email("store@test.com")
        assert by_email is not None
        assert by_email.id == user.id

    def test_create_workspace_and_membership(self, auth_store):
        user = auth_store.create_user("owner@test.com", "Owner", "pass")
        ws = auth_store.create_workspace("Test WS", user.id)

        m = auth_store.get_membership(ws.id, user.id)
        assert m is not None
        assert m.role == WorkspaceRole.OWNER

    def test_list_user_workspaces(self, auth_store):
        user = auth_store.create_user("wslist@test.com", "Lister", "pass")
        auth_store.create_workspace("WS A", user.id)
        auth_store.create_workspace("WS B", user.id)

        ws_list = auth_store.list_for_user(user.id)
        assert len(ws_list) == 2

    def test_member_management(self, auth_store):
        owner = auth_store.create_user("boss@test.com", "Boss", "pass")
        member = auth_store.create_user("worker@test.com", "Worker", "pass")
        ws = auth_store.create_workspace("Team", owner.id)

        auth_store.add_member(ws.id, member.id, WorkspaceRole.MEMBER)
        members = auth_store.list_members(ws.id)
        assert len(members) == 2

        auth_store.update_role(ws.id, member.id, WorkspaceRole.ADMIN)
        m = auth_store.get_membership(ws.id, member.id)
        assert m is not None
        assert m.role == WorkspaceRole.ADMIN

        auth_store.remove_member(ws.id, member.id)
        assert len(auth_store.list_members(ws.id)) == 1
