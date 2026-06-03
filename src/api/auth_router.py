"""Auth API — 注册/登录/JWT/工作区管理。

端点:
    POST /auth/register
    POST /auth/login
    POST /auth/refresh
    GET  /auth/me
    GET  /auth/workspaces
    POST /auth/workspaces
"""
import hashlib
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.adapters.auth_store import SQLiteAuthStore, WorkspaceContext
from src.api.middleware import (
    JWTTokenService,
    get_current_user,
    get_token_payload,
    require_auth,
)
from src.core.auth import User, WorkspaceRole

logger = logging.getLogger(__name__)


# ── Request/Response Schemas ──


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)
    name: str = Field(default="", max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: dict
    workspace: dict | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


class WorkspaceSwitchRequest(BaseModel):
    workspace_id: str


# ── Helpers ──


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    return salt + ":" + hashlib.sha256((salt + password).encode()).hexdigest()


def _verify_password(password: str, hashed: str) -> bool:
    if ":" not in hashed:
        return False
    salt, h = hashed.split(":", 1)
    return hashlib.sha256((salt + password).encode()).hexdigest() == h


def _user_to_dict(u: User) -> dict:
    return {
        "id": u.id, "email": u.email, "name": u.name,
        "avatar_url": u.avatar_url, "auth_provider": u.auth_provider,
        "created_at": u.created_at.isoformat(),
    }


# ── Router Factory ──


def create_auth_router(
    token_service: JWTTokenService,
    auth_store: SQLiteAuthStore,
) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/register")
    async def register(body: RegisterRequest):
        """邮箱 + 密码注册。自动创建默认 Workspace。"""
        # Check duplicate
        existing = auth_store.get_by_email(body.email.lower())
        if existing is not None:
            raise HTTPException(409, "该邮箱已注册")

        hashed = _hash_password(body.password)
        user = auth_store.create_user(
            email=body.email.lower(),
            name=body.name or body.email.split("@")[0],
            hashed_password=hashed,
        )

        # Auto-create workspace
        ws = auth_store.create_workspace(
            name=f"{user.name} 的工作区",
            owner_id=user.id,
        )

        tokens = token_service.create_tokens(user, ws.id, WorkspaceRole.OWNER)
        return {
            **tokens.__dict__,
            "user": _user_to_dict(user),
            "workspace": {"id": ws.id, "name": ws.name, "role": "owner"},
        }

    @router.post("/login")
    async def login(body: LoginRequest):
        """邮箱 + 密码登录。返回默认 workspace 的 token。"""
        user = auth_store.get_by_email(body.email.lower())
        if user is None or not user.hashed_password:
            raise HTTPException(401, "邮箱或密码错误")

        if not _verify_password(body.password, user.hashed_password):
            raise HTTPException(401, "邮箱或密码错误")

        # Get first workspace
        workspaces = auth_store.list_for_user(user.id)
        if not workspaces:
            # Create default workspace
            ws = auth_store.create_workspace(
                name=f"{user.name} 的工作区", owner_id=user.id)
            workspaces = [ws]

        ws = workspaces[0]
        membership = auth_store.get_membership(ws.id, user.id)
        role = membership.role if membership else WorkspaceRole.MEMBER

        tokens = token_service.create_tokens(user, ws.id, role)
        return {
            **tokens.__dict__,
            "user": _user_to_dict(user),
            "workspace": {"id": ws.id, "name": ws.name, "role": role.value},
        }

    @router.post("/refresh")
    async def refresh(body: RefreshRequest):
        """使用 refresh token 换取新 access token。"""
        tokens = token_service.refresh_access_token(body.refresh_token)
        if tokens is None:
            raise HTTPException(401, "Refresh token 无效或已过期")
        return tokens.__dict__

    @router.get("/me")
    async def me(user: User | None = Depends(get_current_user)):
        """当前登录用户信息 + workspace 列表。"""
        if user is None:
            raise HTTPException(401, "需要登录")

        workspaces = auth_store.list_for_user(user.id)
        ws_list = []
        for ws in workspaces:
            m = auth_store.get_membership(ws.id, user.id)
            ws_list.append({
                "id": ws.id, "name": ws.name,
                "role": m.role.value if m else "member",
            })

        return {
            "user": _user_to_dict(user),
            "workspaces": ws_list,
        }

    @router.get("/workspaces")
    async def list_workspaces(payload=Depends(require_auth)):
        """当前用户的 workspace 列表。"""
        user = auth_store.get_user_by_id(payload.user_id)
        if user is None:
            raise HTTPException(401)
        workspaces = auth_store.list_for_user(user.id)
        return [
            {
                "id": ws.id, "name": ws.name,
                "members": len(auth_store.list_members(ws.id)),
            }
            for ws in workspaces
        ]

    @router.post("/workspaces")
    async def create_workspace(body: WorkspaceCreateRequest,
                                payload=Depends(require_auth)):
        """创建新 Workspace。"""
        ws = auth_store.create_workspace(name=body.name, owner_id=payload.user_id)
        return {"id": ws.id, "name": ws.name}

    return router
