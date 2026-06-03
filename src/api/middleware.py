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

# ── Config ──

SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE = 3600       # 1 hour
REFRESH_TOKEN_EXPIRE = 2592000   # 30 days

bearer_scheme = HTTPBearer(auto_error=False)

# ── JWT Token Service ──


class JWTTokenService:
    """JWT Token 服务的实际实现。"""

    def __init__(self, secret_key: str = SECRET_KEY, algorithm: str = ALGORITHM) -> None:
        self._secret = secret_key
        self._algorithm = algorithm
        # Simple in-memory refresh token blacklist (production: use Redis/DB)
        self._revoked_refresh: set[str] = set()

    def create_tokens(self, user: User, workspace_id: str, role: WorkspaceRole) -> AuthTokens:
        now = datetime.now(timezone.utc)
        access_payload = {
            "sub": user.id,
            "email": user.email,
            "workspace_id": workspace_id,
            "role": role.value,
            "exp": now + timedelta(seconds=ACCESS_TOKEN_EXPIRE),
            "iat": now,
            "type": "access",
        }
        refresh_payload = {
            "sub": user.id,
            "workspace_id": workspace_id,
            "role": role.value,
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
            )
        except JWTError:
            return None

    def refresh_access_token(self, refresh_token: str) -> AuthTokens | None:
        try:
            payload = jwt.decode(refresh_token, self._secret, algorithms=[self._algorithm])
            if payload.get("type") != "refresh":
                return None
            jti = payload.get("jti", "")
            if jti in self._revoked_refresh:
                return None
            # Check expiry
            exp = payload.get("exp", 0)
            if datetime.now(timezone.utc).timestamp() > exp:
                return None

            # Issue new tokens (keep same workspace/role)
            now = datetime.now(timezone.utc)
            access_payload = {
                "sub": payload["sub"],
                "email": payload.get("email", ""),
                "workspace_id": payload.get("workspace_id", "default"),
                "role": payload.get("role", "member"),
                "exp": now + timedelta(seconds=ACCESS_TOKEN_EXPIRE),
                "iat": now,
                "type": "access",
            }
            refresh_payload = {
                "sub": payload["sub"],
                "workspace_id": payload.get("workspace_id", "default"),
                "role": payload.get("role", "member"),
                "exp": now + timedelta(seconds=REFRESH_TOKEN_EXPIRE),
                "iat": now,
                "type": "refresh",
                "jti": secrets.token_hex(8),
            }

            access_token = jwt.encode(access_payload, self._secret, algorithm=self._algorithm)
            new_refresh = jwt.encode(refresh_payload, self._secret, algorithm=self._algorithm)
            # Revoke old refresh token
            self._revoked_refresh.add(jti)
            return AuthTokens(
                access_token=cast(str, access_token),
                refresh_token=cast(str, new_refresh),
                expires_in=ACCESS_TOKEN_EXPIRE,
            )
        except JWTError:
            return None

    def revoke_refresh_token(self, refresh_token: str) -> None:
        try:
            payload = jwt.decode(refresh_token, self._secret, algorithms=[self._algorithm])
            jti = payload.get("jti", "")
            if jti:
                self._revoked_refresh.add(jti)
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
    """要求 write 权限（member+）。"""
    if not payload.has_write_access():
        raise HTTPException(status_code=403, detail="权限不足: 需要 member 或以上角色")
    return payload


async def require_manage(
    payload: TokenPayload = Depends(require_auth),
) -> TokenPayload:
    """要求 manage 权限（admin+）。"""
    if not payload.has_manage_access():
        raise HTTPException(status_code=403, detail="权限不足: 需要 admin 或以上角色")
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
