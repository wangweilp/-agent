"""Multi-Tenant Auth Domain Models — User / Workspace / Membership / Role.

六边形架构核心层：只定义数据类和协议，不引用任何外部库。
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import uuid4


# ── Roles ──

class WorkspaceRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"

    @classmethod
    def hierarchy(cls) -> dict[str, int]:
        """权限层级：数字越大权限越高。"""
        return {"viewer": 0, "member": 1, "admin": 2, "owner": 3}

    def can_write(self) -> bool:
        return self in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER)

    def can_manage(self) -> bool:
        return self in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN)

    def can_admin(self) -> bool:
        return self == WorkspaceRole.OWNER


# ── Data Classes ──

@dataclass
class User:
    email: str
    name: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))
    avatar_url: str | None = None
    hashed_password: str | None = None
    auth_provider: str = "email"    # email | google | github
    auth_provider_id: str | None = None
    is_super_admin: bool = False    # 超级管理员 — 绕过所有 RBAC 检查
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_oauth_user(self) -> bool:
        return self.auth_provider != "email"


@dataclass
class Workspace:
    name: str
    owner_id: str  # User.id
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Membership:
    user_id: str
    workspace_id: str
    role: WorkspaceRole = WorkspaceRole.MEMBER
    joined_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def composite_key(self) -> str:
        return f"{self.user_id}:{self.workspace_id}"


# ── Auth Tokens ──

@dataclass
class AuthTokens:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600  # 1 hour


@dataclass
class TokenPayload:
    """JWT payload 中携带的认证上下文。"""
    user_id: str
    workspace_id: str
    role: WorkspaceRole
    email: str = ""
    is_super_admin: bool = False  # 超级管理员 — 绕过所有权限检查

    def has_write_access(self) -> bool:
        return WorkspaceRole(self.role).can_write()

    def has_manage_access(self) -> bool:
        return WorkspaceRole(self.role).can_manage()


# ── Protocols ──

@runtime_checkable
class UserStore(Protocol):
    """用户存储协议。"""

    def create_user(self, email: str, name: str, hashed_password: str | None = None,
                    auth_provider: str = "email", auth_provider_id: str | None = None) -> User: ...

    def get_by_id(self, user_id: str) -> User | None: ...

    def get_by_email(self, email: str) -> User | None: ...

    def update_user(self, user: User) -> None: ...


@runtime_checkable
class WorkspaceStore(Protocol):
    """Workspace 存储协议。"""

    def create_workspace(self, name: str, owner_id: str) -> Workspace: ...

    def get_by_id(self, workspace_id: str) -> Workspace | None: ...

    def list_for_user(self, user_id: str) -> list[Workspace]: ...

    def add_member(self, workspace_id: str, user_id: str, role: WorkspaceRole) -> Membership: ...

    def get_membership(self, workspace_id: str, user_id: str) -> Membership | None: ...

    def list_members(self, workspace_id: str) -> list[Membership]: ...

    def update_role(self, workspace_id: str, user_id: str, role: WorkspaceRole) -> None: ...

    def remove_member(self, workspace_id: str, user_id: str) -> None: ...


@runtime_checkable
class TokenService(Protocol):
    """JWT Token 服务协议。"""

    def create_tokens(self, user: User, workspace_id: str, role: WorkspaceRole) -> AuthTokens: ...

    def decode_token(self, token: str) -> TokenPayload | None: ...

    def refresh_access_token(self, refresh_token: str) -> AuthTokens | None: ...

    def revoke_refresh_token(self, refresh_token: str) -> None: ...
