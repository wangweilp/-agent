"""API Middleware — JWT 认证 + Workspace 上下文注入。

依赖链:
    Request → JWTMiddleware (解析 token)
           → get_current_user (注入 User)
           → get_current_workspace (注入 workspace_id + role)
           → WorkspaceContext (adapter 层自动读取)
"""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import cast

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from src.adapters.auth_store import SQLiteAuthStore, WorkspaceContext
from src.core.auth import AuthTokens, TokenPayload, User, WorkspaceRole

logger = logging.getLogger(__name__)
_GENERATED_DEV_SECRET: str | None = None

# ── Config ──

_DEFAULT_MSG = (
    "JWT_SECRET_KEY environment variable is required in production. "
    "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
)


def _is_production(environment: str) -> bool:
    return environment.lower() in ("production", "prod")


def resolve_jwt_secret_key(
    secret_key: str | None = None,
    environment: str | None = None,
) -> str:
    global _GENERATED_DEV_SECRET
    configured_secret = (secret_key or os.getenv("JWT_SECRET_KEY", "")).strip()
    if configured_secret:
        return configured_secret
    if _is_production(environment or os.getenv("ENVIRONMENT", "")):
        raise RuntimeError(_DEFAULT_MSG)
    if _GENERATED_DEV_SECRET is None:
        _GENERATED_DEV_SECRET = secrets.token_hex(32)
        logger.warning(
            "JWT_SECRET_KEY not set; generated temporary development key "
            "(set ENVIRONMENT=production to require explicit configuration)"
        )
    return _GENERATED_DEV_SECRET

SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE = 3600       # 1 hour
REFRESH_TOKEN_EXPIRE = 2592000   # 30 days

bearer_scheme = HTTPBearer(auto_error=False)

# ── JWT Token Service ──


class JWTTokenService:
    """JWT Token 服务的实际实现。

    Refresh token 撤销状态持久存储在 SQLiteAuthStore.revoked_tokens 表中，
    跨进程重启后依然有效。
    """

    def __init__(
        self,
        secret_key: str | None = None,
        algorithm: str = ALGORITHM,
        auth_store: "SQLiteAuthStore | None" = None,
    ) -> None:
        self._secret = resolve_jwt_secret_key(secret_key)
        self._algorithm = algorithm
        self._auth_store = auth_store

    def create_tokens(self, user: User, workspace_id: str, role: WorkspaceRole) -> AuthTokens:
        now = datetime.now(timezone.utc)
        access_payload = {
            "sub": user.id,
            "email": user.email,
            "workspace_id": workspace_id,
            "role": role.value,
            "is_super_admin": user.is_super_admin,
            "exp": now + timedelta(seconds=ACCESS_TOKEN_EXPIRE),
            "iat": now,
            "type": "access",
        }
        refresh_payload = {
            "sub": user.id,
            "workspace_id": workspace_id,
            "role": role.value,
            "is_super_admin": user.is_super_admin,
            "exp": now + timedelta(seconds=REFRESH_TOKEN_EXPIRE),
            "iat": now,
            "type": "refresh",
            "jti": secrets.token_hex(8),
        }

        access_token = jwt.encode(access_payload, self._secret, algorithm=self._algorithm)
        refresh_token = jwt.encode(refresh_payload, self._secret, algorithm=self._algorithm)

        return AuthTokens(
            access_token=cast(str, access_token),
            refresh_token=cast(str, refresh_token),
            expires_in=ACCESS_TOKEN_EXPIRE,
        )

    def decode_token(self, token: str) -> TokenPayload | None:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
            if payload.get("type") != "access":
                return None
            return TokenPayload(
                user_id=payload["sub"],
                workspace_id=payload.get("workspace_id", "default"),
                role=WorkspaceRole(payload.get("role", "member")),
                email=payload.get("email", ""),
                is_super_admin=payload.get("is_super_admin", False),
            )
        except JWTError:
            return None

    def refresh_access_token(self, refresh_token: str) -> AuthTokens | None:
        try:
            payload = jwt.decode(refresh_token, self._secret, algorithms=[self._algorithm])
            if payload.get("type") != "refresh":
                return None
            jti = payload.get("jti", "")
            # Check DB for revocation
            if self._auth_store is not None and self._auth_store.is_token_revoked(jti):
                logger.warning("refresh_token_revoked", extra={"jti": jti[:8]})
                return None
            # Check expiry
            exp = payload.get("exp", 0)
            if datetime.now(timezone.utc).timestamp() > exp:
                return None

            # Issue new tokens (keep same workspace/role/super_admin)
            now = datetime.now(timezone.utc)
            new_jti = secrets.token_hex(8)
            access_payload = {
                "sub": payload["sub"],
                "email": payload.get("email", ""),
                "workspace_id": payload.get("workspace_id", "default"),
                "role": payload.get("role", "member"),
                "is_super_admin": payload.get("is_super_admin", False),
                "exp": now + timedelta(seconds=ACCESS_TOKEN_EXPIRE),
                "iat": now,
                "type": "access",
            }
            refresh_payload = {
                "sub": payload["sub"],
                "workspace_id": payload.get("workspace_id", "default"),
                "role": payload.get("role", "member"),
                "is_super_admin": payload.get("is_super_admin", False),
                "exp": now + timedelta(seconds=REFRESH_TOKEN_EXPIRE),
                "iat": now,
                "type": "refresh",
                "jti": new_jti,
            }

            access_token = jwt.encode(access_payload, self._secret, algorithm=self._algorithm)
            new_refresh = jwt.encode(refresh_payload, self._secret, algorithm=self._algorithm)
            # Revoke old refresh token — persist to DB
            self.revoke_refresh_token(refresh_token)
            return AuthTokens(
                access_token=cast(str, access_token),
                refresh_token=cast(str, new_refresh),
                expires_in=ACCESS_TOKEN_EXPIRE,
            )
        except JWTError:
            return None

    def revoke_refresh_token(self, refresh_token: str) -> None:
        """撤销一个 refresh token — 持久存储到 revoked_tokens 表。

        如果 auth_store 不可用（测试模式），静默忽略。
        """
        try:
            payload = jwt.decode(refresh_token, self._secret, algorithms=[self._algorithm])
            jti = payload.get("jti", "")
            user_id = payload.get("sub", "")
            exp = payload.get("exp", 0)
            if jti and self._auth_store is not None:
                expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
                self._auth_store.revoke_token(jti, user_id, expires_at)
                # 顺便清理过期记录
                self._auth_store.prune_expired_tokens()
        except JWTError:
            pass


# ── FastAPI Dependencies ──

# Global instances (set by main.py bootstrap)
_token_service: JWTTokenService | None = None
_auth_store: SQLiteAuthStore | None = None


def init_auth(token_service: JWTTokenService, auth_store: SQLiteAuthStore) -> None:
    """由 main.py 在启动时调用，注册全局认证实例。"""
    global _token_service, _auth_store
    _token_service = token_service
    _auth_store = auth_store


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User | None:
    """从 JWT 中解析当前用户。如果无 token 则返回 None（兼容本地开发模式）。"""
    if credentials is None or _token_service is None or _auth_store is None:
        return None
    payload = _token_service.decode_token(credentials.credentials)
    if payload is None:
        return None
    return _auth_store.get_user_by_id(payload.user_id)


async def get_token_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> TokenPayload | None:
    """从 JWT 中解析 TokenPayload（含 workspace_id + role）。"""
    if credentials is None or _token_service is None:
        return None
    return _token_service.decode_token(credentials.credentials)


async def require_auth(
    payload: TokenPayload | None = Depends(get_token_payload),
) -> TokenPayload:
    """强制要求认证 — 无有效 token 则 401。"""
    if payload is None:
        raise HTTPException(status_code=401, detail="需要登录")
    # 设置 workspace 上下文供 adapter 层使用
    WorkspaceContext.set(payload)
    return payload


async def require_write(
    payload: TokenPayload = Depends(require_auth),
) -> TokenPayload:
    """要求 write 权限（member+）。超级管理员直接通过。"""
    if payload.is_super_admin:
        return payload
    if not payload.has_write_access():
        raise HTTPException(status_code=403, detail="权限不足: 需要 member 或以上角色")
    return payload


async def require_manage(
    payload: TokenPayload = Depends(require_auth),
) -> TokenPayload:
    """要求 manage 权限（admin+）。超级管理员直接通过。"""
    if payload.is_super_admin:
        return payload
    if not payload.has_manage_access():
        raise HTTPException(status_code=403, detail="权限不足: 需要 admin 或以上角色")
    return payload


# ═══════════════════════════════════════════
# Workspace Membership Guards
# ═══════════════════════════════════════════


async def assert_workspace_access(
    request: Request,
    payload: TokenPayload = Depends(require_auth),
) -> TokenPayload:
    """验证当前用户是目标 workspace 的成员（viewer+）。超级管理员直接通过。"""
    if payload.is_super_admin:
        # 超级管理员：将 workspace_id 更新为请求中的目标
        ws_id: str = request.path_params.get("id", "")
        if ws_id:
            payload.workspace_id = ws_id
            WorkspaceContext.set(payload)
        return payload

    ws_id: str = request.path_params.get("id", "")
    if not ws_id:
        raise HTTPException(status_code=400, detail="请求路径缺少工作区 ID")

    if _auth_store is None:
        # 边缘：auth store 未就绪，放行（兼容本地开发及部分测试）
        logger.warning("assert_workspace_access: auth_store not initialized")
        return payload

    membership = _auth_store.get_membership(ws_id, payload.user_id)
    if membership is None:
        raise HTTPException(status_code=403,
                            detail=f"无权访问工作区 {ws_id}: 你不是该工作区成员")

    # 更新 payload 中的 workspace_id 和 role 为当前工作区的真实值
    # 这确保下游 adapter 层使用正确的工作区上下文
    payload.workspace_id = ws_id
    payload.role = membership.role
    WorkspaceContext.set(payload)

    logger.info("workspace_access_granted",
                extra={"user_id": payload.user_id,
                       "workspace_id": ws_id,
                       "role": membership.role.value})
    return payload


async def assert_workspace_manage(
    request: Request,
    payload: TokenPayload = Depends(assert_workspace_access),
) -> TokenPayload:
    """验证当前用户对目标 workspace 有管理权限（admin/owner）。超级管理员直接通过。"""
    if payload.is_super_admin:
        return payload
    if not payload.has_manage_access():
        raise HTTPException(status_code=403,
                            detail="权限不足: 需要该工作区的 admin 或以上角色")
    return payload


async def optional_auth(
    payload: TokenPayload | None = Depends(get_token_payload),
) -> TokenPayload | None:
    """可选的认证 — 有 token 则设置上下文，无则用默认 workspace。"""
    if payload:
        WorkspaceContext.set(payload)
    else:
        # 无认证模式：使用默认 workspace（兼容本地开发）
        WorkspaceContext.set(TokenPayload(
            user_id="anonymous", workspace_id="default",
            role=WorkspaceRole.ADMIN, email="",
        ))
    return payload


# ═══════════════════════════════════════════
# AuthMiddleware — 全局 ASGI 鉴权边界
# ═══════════════════════════════════════════


# ── Dev mode auto-auth token cache ──
_dev_token_cache: dict = {}  # {token_str: expiry_timestamp}


def _is_dev_mode() -> bool:
    """判断当前是否为开发模式（非生产环境）。

    DISABLE_DEV_AUTH=true 可强制关闭开发模式自动注入，用于安全测试环境。
    """
    if os.getenv("DISABLE_DEV_AUTH", "").lower() == "true":
        return False
    env = os.getenv("ENVIRONMENT", "development").lower()
    return env not in ("production", "prod")


def _get_dev_token() -> str | None:
    """获取或创建开发模式管理员 token。

    仅在非生产环境下生效。使用缓存避免每次请求都查询数据库。
    """
    global _dev_token_cache
    now_ts = datetime.now(timezone.utc).timestamp()
    # 检查缓存是否有效（提前 60 秒过期以留出缓冲）
    for token, expiry in list(_dev_token_cache.items()):
        if expiry > now_ts + 60:
            return token
        else:
            del _dev_token_cache[token]

    # 创建或获取 dev admin 用户
    if _auth_store is None or _token_service is None:
        return None

    try:
        dev_email = os.getenv("ADMIN_EMAIL", "dev-admin@agent-os.local")
        dev_password = os.getenv("ADMIN_PASSWORD", "dev-admin-agent-os-2024")
        dev_user = _auth_store.ensure_super_admin(
            email=dev_email,
            password=dev_password,
            name="Dev Admin",
        )
        if dev_user is None:
            return None

        # 创建 token
        from src.core.auth import WorkspaceRole
        tokens = _token_service.create_tokens(
            user=dev_user,
            workspace_id="default",
            role=WorkspaceRole.ADMIN,
        )
        _dev_token_cache[tokens.access_token] = now_ts + 3300  # 55 min cache
        logger.info("dev_auth_token_created",
                    extra={"user_id": dev_user.id, "dev_mode": True})
        return tokens.access_token
    except Exception:
        logger.warning("dev_auth_token_failed", exc_info=True)
        return None


class AuthMiddleware:
    """全局鉴权中间件。

    所有 HTTP 请求必须通过 JWT 验证，除非路径在公开白名单中
    或当前为开发模式（ENVIRONMENT != production）。

    公开入口：/, /health, /docs, /openapi.json, /redoc, /auth/*
    开发模式：无 token 时自动注入 dev admin 身份
    """

    _PUBLIC_EXACT: frozenset[str] = frozenset({
        "/", "/health", "/docs", "/openapi.json", "/redoc",
    })
    _PUBLIC_PREFIXES: tuple[str, ...] = ("/auth/",)

    def __init__(self, app):
        self._app = app

    @classmethod
    def is_public(cls, path: str) -> bool:
        """判断路径是否无需鉴权。"""
        if path in cls._PUBLIC_EXACT:
            return True
        for prefix in cls._PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return True
        return False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        path: str = scope.get("path", "/")

        # 公开路径放行
        if self.is_public(path):
            await self._app(scope, receive, send)
            return

        # OPTIONS (CORS preflight) — 无条件放行，CORS 中间件会处理
        if scope.get("method") == "OPTIONS":
            await self._app(scope, receive, send)
            return

        # 提取 Authorization header
        headers: dict[bytes, bytes] = dict(scope.get("headers", []))
        auth_value = headers.get(b"authorization", b"").decode("latin-1")

        token_str: str | None = None
        if auth_value.startswith("Bearer "):
            token_str = auth_value[7:].strip()

        # 无 token
        if not token_str:
            # 开发模式：自动注入 dev admin token
            if _is_dev_mode():
                dev_token = _get_dev_token()
                if dev_token:
                    token_str = dev_token
                    # 注入到 scope headers 中，下游 FastAPI dependencies 可正常解析
                    new_headers = [(k, v) for k, v in scope.get("headers", [])
                                   if k != b"authorization"]
                    new_headers.append(
                        (b"authorization", f"Bearer {dev_token}".encode("latin-1"))
                    )
                    scope["headers"] = new_headers
                    logger.debug("dev_auth_injected", extra={"path": path})
                else:
                    logger.warning("dev_auth_unavailable",
                                   extra={"path": path,
                                          "hint": "检查 ADMIN_EMAIL/ADMIN_PASSWORD 环境变量或 .env 配置"})
                    await self._send_401(send, "开发模式认证不可用，请检查 .env 配置")
                    return
            else:
                await self._send_401(send, "缺少认证信息，请先登录")
                return

        # 验证 JWT
        if _token_service is None:
            # 边缘情况：token service 尚未初始化 → 放行（开发模式）
            logger.warning("auth_middleware_token_service_not_ready")
            await self._app(scope, receive, send)
            return

        payload = _token_service.decode_token(token_str)
        if payload is None:
            await self._send_401(send, "登录已过期，请重新登录")
            return

        # 注入 workspace 上下文，供 adapter 层使用
        WorkspaceContext.set(payload)

        # 放行
        await self._app(scope, receive, send)

    async def _send_401(self, send, detail: str) -> None:
        body = _json_bytes({"detail": detail})
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })


def _json_bytes(obj: object) -> bytes:
    import json as _json
    return _json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
