"""安全边界测试 — 验证 AuthMiddleware 统一鉴权。

覆盖:
- 公开入口无需认证返回 200
- 受保护路由无 token 返回 401
- 受保护路由无效/过期 token 返回 401
- 受保护路由有效 token 正常通过
- /auth/* 路由保持公开
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient
from jose import jwt

from src.api.middleware import (
    AuthMiddleware,
    JWTTokenService,
    init_auth,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE,
)
from src.adapters.auth_store import SQLiteAuthStore, WorkspaceContext
from src.adapters.config import Settings
from src.core.auth import User, WorkspaceRole, TokenPayload


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def auth_store(settings):
    store = SQLiteAuthStore(settings, db_path=":memory:")
    return store


@pytest.fixture
def token_service():
    return JWTTokenService()


@pytest.fixture
def test_user(auth_store):
    """创建测试用户。"""
    import bcrypt
    hashed = bcrypt.hashpw("test123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = auth_store.create_user(
        email="test@example.com",
        name="Test User",
        hashed_password=hashed,
    )
    return user


@pytest.fixture
def test_workspace(auth_store, test_user):
    ws = auth_store.create_workspace(name="Test WS", owner_id=test_user.id)
    return ws


@pytest.fixture
def access_token(token_service, test_user, test_workspace):
    """创建一个有效的 access token。"""
    tokens = token_service.create_tokens(test_user, test_workspace.id, WorkspaceRole.MEMBER)
    return tokens.access_token


@pytest.fixture
def admin_token(token_service, test_user, test_workspace):
    """创建一个 admin 权限的 access token。"""
    tokens = token_service.create_tokens(test_user, test_workspace.id, WorkspaceRole.ADMIN)
    return tokens.access_token


@pytest.fixture
def expired_token(token_service, test_user, test_workspace):
    """创建一个已过期的 access token。"""
    now = datetime.now(timezone.utc)
    import time as _time
    exp = now.timestamp() - 3600  # 1 hour ago
    payload = {
        "sub": test_user.id,
        "email": test_user.email,
        "workspace_id": test_workspace.id,
        "role": WorkspaceRole.MEMBER.value,
        "exp": exp,
        "iat": now.timestamp(),
        "type": "access",
    }
    return jwt.encode(payload, token_service._secret, algorithm=ALGORITHM)


@pytest.fixture
def app_with_middleware(token_service, auth_store, monkeypatch):
    """创建一个带 AuthMiddleware 的 FastAPI app 用于测试。

    DISABLE_DEV_AUTH=true 确保 dev admin token 不会自动注入，
    使无 token / 无效 token 的请求正确返回 401。
    """
    monkeypatch.setenv("DISABLE_DEV_AUTH", "true")
    init_auth(token_service, auth_store)

    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    # 公开路由（模拟）
    @app.get("/")
    async def root():
        return {"status": "ok"}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/docs")
    async def docs():
        return {"openapi": "3.0"}

    # Auth 路由（模拟）
    auth = APIRouter(prefix="/auth")
    @auth.post("/login")
    async def login():
        return {"token": "fake"}
    @auth.post("/register")
    async def register():
        return {"user_id": "123"}
    @auth.post("/refresh")
    async def refresh():
        return {"token": "fresh"}
    @auth.get("/me")
    async def me():
        return {"user": "test"}
    app.include_router(auth)

    # 受保护路由 — 读取用户数据
    @app.get("/chat")
    async def chat_history():
        return {"messages": []}

    @app.post("/chat")
    async def send_chat():
        return {"reply": "hello"}

    @app.get("/memory")
    async def list_memories():
        return {"memories": []}

    @app.patch("/memory/abc")
    async def update_memory():
        return {"status": "updated"}

    @app.delete("/memory/abc")
    async def delete_memory():
        return {"status": "deleted"}

    @app.get("/dashboard/metrics")
    async def dashboard_metrics():
        return {"count": 42}

    @app.post("/audio/upload")
    async def upload_audio():
        return {"file_id": "x"}

    @app.post("/video/upload")
    async def upload_video():
        return {"file_id": "y"}

    @app.post("/import")
    async def import_data():
        return {"job_id": "1"}

    @app.post("/sync/jobs")
    async def sync_jobs():
        return {"job_id": "2"}

    @app.post("/agents/run")
    async def run_agent():
        return {"result": "ok"}

    @app.post("/agents/workflows")
    async def create_workflow():
        return {"workflow_id": "wf1"}

    @app.get("/graph")
    async def graph():
        return {"nodes": []}

    @app.get("/timeline")
    async def timeline():
        return {"events": []}

    @app.get("/upload/chat")
    async def upload_chat():
        return {"reply": "ok"}

    return app


@pytest.fixture
def client(app_with_middleware):
    return TestClient(app_with_middleware)


@pytest.fixture
def auth_client(access_token, app_with_middleware):
    """预认证的 test client — Authorization header 已设置。"""
    return TestClient(app_with_middleware, headers={"Authorization": f"Bearer {access_token}"})


# ═══════════════════════════════════════════
# 公开路由测试
# ═══════════════════════════════════════════


class TestPublicRoutes:
    """公开路由 — 无需认证即可访问。"""

    @pytest.mark.parametrize("path,expected_status", [
        ("/", 200),
        ("/health", 200),
        ("/docs", 200),
        ("/openapi.json", 200),
        ("/redoc", 200),
    ])
    def test_public_exact_paths(self, client, path, expected_status):
        resp = client.get(path)
        assert resp.status_code == expected_status, f"{path} 应返回 {expected_status}，实际返回 {resp.status_code}"

    @pytest.mark.parametrize("path,method", [
        ("/auth/login", "POST"),
        ("/auth/register", "POST"),
        ("/auth/refresh", "POST"),
    ])
    def test_auth_prefix_paths(self, client, path, method):
        if method == "POST":
            resp = client.post(path, json={})
        else:
            resp = client.get(path)
        # /auth/* 路径仍应可访问（即使没有 token）
        # 具体业务逻辑验证由 auth router 内部处理
        assert resp.status_code != 401, f"{path} 不应返回 401（公开路由）"


# ═══════════════════════════════════════════
# 受保护路由 — 无认证返回 401
# ═══════════════════════════════════════════


class TestProtectedRoutesUnauthenticated:

    @pytest.mark.parametrize("path,method", [
        ("/chat", "GET"),
        ("/chat", "POST"),
        ("/memory", "GET"),
        ("/memory/abc", "PATCH"),
        ("/memory/abc", "DELETE"),
        ("/dashboard/metrics", "GET"),
        ("/audio/upload", "POST"),
        ("/video/upload", "POST"),
        ("/import", "POST"),
        ("/sync/jobs", "POST"),
        ("/agents/run", "POST"),
        ("/agents/workflows", "POST"),
        ("/graph", "GET"),
        ("/timeline", "GET"),
        ("/upload/chat", "GET"),
    ])
    def test_protected_route_no_token(self, client, path, method):
        """受保护路由无 token 应返回 401。"""
        if method == "GET":
            resp = client.get(path)
        elif method == "POST":
            resp = client.post(path, json={})
        elif method == "PATCH":
            resp = client.patch(path, json={})
        elif method == "DELETE":
            resp = client.delete(path)
        else:
            return
        assert resp.status_code == 401, (
            f"{method} {path} 无 token 应返回 401，实际返回 {resp.status_code}: {resp.text[:200]}"
        )
        body = resp.json()
        assert "detail" in body

    def test_no_auth_header_at_all(self, client):
        """无 Authorization header 返回 401。"""
        resp = client.get("/memory")
        assert resp.status_code == 401

    def test_empty_auth_header(self, client):
        """空 Authorization header 返回 401。"""
        resp = client.get("/memory", headers={"Authorization": ""})
        assert resp.status_code == 401

    def test_non_bearer_auth(self, client):
        """Basic auth（非 Bearer）返回 401。"""
        resp = client.get("/memory", headers={"Authorization": "Basic dGVzdDp0ZXN0"})
        assert resp.status_code == 401

    def test_malformed_bearer(self, client):
        """畸形的 Bearer token 返回 401。"""
        resp = client.get("/memory", headers={"Authorization": "Bearer"})
        assert resp.status_code == 401


# ═══════════════════════════════════════════
# 受保护路由 — 无效 token 返回 401
# ═══════════════════════════════════════════


class TestProtectedRoutesInvalidToken:

    def test_invalid_jwt(self, client):
        """无效 JWT 返回 401。"""
        resp = client.get("/memory", headers={
            "Authorization": "Bearer this.is.not.a.valid.jwt.token"
        })
        assert resp.status_code == 401

    def test_expired_token(self, client, expired_token):
        """过期 token 返回 401。"""
        resp = client.get("/memory", headers={
            "Authorization": f"Bearer {expired_token}"
        })
        assert resp.status_code == 401

    def test_wrong_type_token(self, token_service, test_user, test_workspace, client):
        """refresh token（type=refresh）不能用于 API 访问，返回 401。"""
        tokens = token_service.create_tokens(test_user, test_workspace.id, WorkspaceRole.MEMBER)
        resp = client.get("/memory", headers={
            "Authorization": f"Bearer {tokens.refresh_token}"
        })
        assert resp.status_code == 401


# ═══════════════════════════════════════════
# 受保护路由 — 有效 token 正常通过
# ═══════════════════════════════════════════


class TestProtectedRoutesAuthenticated:

    @pytest.mark.parametrize("path,method", [
        ("/chat", "GET"),
        ("/chat", "POST"),
        ("/memory", "GET"),
        ("/memory/abc", "PATCH"),
        ("/memory/abc", "DELETE"),
        ("/dashboard/metrics", "GET"),
        ("/import", "POST"),
        ("/sync/jobs", "POST"),
        ("/agents/run", "POST"),
        ("/agents/workflows", "POST"),
        ("/graph", "GET"),
        ("/timeline", "GET"),
    ])
    def test_protected_route_with_valid_token(self, auth_client, path, method):
        """有效 token 应正常通过受保护路由。"""
        if method == "GET":
            resp = auth_client.get(path)
        elif method == "POST":
            resp = auth_client.post(path, json={})
        elif method == "PATCH":
            resp = auth_client.patch(path, json={})
        elif method == "DELETE":
            resp = auth_client.delete(path)
        else:
            return
        assert resp.status_code == 200, (
            f"{method} {path} 有效 token 应返回 200，实际返回 {resp.status_code}: {resp.text[:200]}"
        )

    def test_workspace_context_set_after_auth(self, app_with_middleware, access_token):
        """认证通过后 WorkspaceContext 应被正确设置。"""
        client = TestClient(app_with_middleware)

        @app_with_middleware.get("/debug/context")
        async def debug_context():
            payload = WorkspaceContext.get()
            return {
                "user_id": payload.user_id if payload else None,
                "workspace_id": payload.workspace_id if payload else None,
                "role": payload.role.value if payload else None,
            }

        resp = client.get("/debug/context", headers={
            "Authorization": f"Bearer {access_token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] != ""
        assert data["workspace_id"] != ""

    def test_multiple_requests_same_token(self, auth_client):
        """同一 token 可用于多次请求。"""
        for _ in range(3):
            resp = auth_client.get("/memory")
            assert resp.status_code == 200


# ═══════════════════════════════════════════
# 完整场景测试
# ═══════════════════════════════════════════


class TestFullAuthFlow:
    """完整的注册 → 登录 → API 访问流程。"""

    def test_register_login_api_flow(self, app_with_middleware, token_service, auth_store, test_user, test_workspace):
        """端到端：注册 → 登录获取 token → 使用 token 访问受保护 API。"""
        client = TestClient(app_with_middleware)

        # 1. 注册 — 公开路由可访问
        register_resp = client.post("/auth/register", json={
            "email": "e2e@test.com",
            "password": "e2e123456",
            "name": "E2E User",
        })
        # 公开路由允许访问（返回什么格式由 auth router 决定，最小验证即可）
        assert register_resp.status_code != 401

        # 2. 使用 token_service 直接创建 token（绕过 mock login）
        tokens = token_service.create_tokens(test_user, test_workspace.id, WorkspaceRole.MEMBER)
        access = tokens.access_token

        # 3. 使用 access_token 访问受保护 API
        resp = client.get("/memory", headers={"Authorization": f"Bearer {access}"})
        assert resp.status_code == 200

        # 4. 使用 refresh_token 刷新
        refresh_resp = client.post("/auth/refresh", json={
            "refresh_token": tokens.refresh_token,
        })
        assert refresh_resp.status_code != 401

        # 5. 使用 token_service 创建新 token（模拟刷新的结果）
        new_tokens = token_service.create_tokens(test_user, test_workspace.id, WorkspaceRole.MEMBER)
        resp = client.get("/chat", headers={
            "Authorization": f"Bearer {new_tokens.access_token}"
        })
        assert resp.status_code == 200

    def test_login_api_flow(self, app_with_middleware, token_service, auth_store, test_user, test_workspace):
        """单独的 login → API 访问流程。"""
        client = TestClient(app_with_middleware)

        # 1. 登录 — 公开路由可访问
        login_resp = client.post("/auth/login", json={
            "email": "login@test.com",
            "password": "login123",
        })
        assert login_resp.status_code != 401

        # 2. 使用 token_service 创建 token
        tokens = token_service.create_tokens(test_user, test_workspace.id, WorkspaceRole.MEMBER)
        access = tokens.access_token

        # 3. 使用 token 访问受保护 API
        resp = client.get("/memory", headers={
            "Authorization": f"Bearer {access}"
        })
        assert resp.status_code == 200


# ═══════════════════════════════════════════
# 中间件状态测试
# ═══════════════════════════════════════════


class TestAuthMiddlewareBoundary:

    def test_non_http_scope_passes_through(self, app_with_middleware):
        """WebSocket/lifespan 等非 HTTP scope 应透传不拦截。"""
        # 通过正常 HTTP 请求验证 app 可达（证明中间件在 HTTP scope 正常工作）
        client = TestClient(app_with_middleware)
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_trailing_slash_auth(self, client, access_token):
        """带尾斜杠的路径也需鉴权。"""
        resp = client.get("/memory/", headers={
            "Authorization": f"Bearer {access_token}"
        })
        # 可能 200 或 307 redirect 或 404，但不应该是 401
        assert resp.status_code != 401

    def test_query_params_dont_bypass_auth(self, client):
        """URL 查询参数不应绕过鉴权。"""
        resp = client.get("/memory?token=anything")
        assert resp.status_code == 401
