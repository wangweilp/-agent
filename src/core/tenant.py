"""Tenant Domain Models — Tenant / Organization / Workspace 扩展。

六边形架构核心层：纯数据类 + 协议。
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import uuid4


# ── Enums ──

class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"
    TRIAL = "trial"


class OrganizationSize(StrEnum):
    SOLO = "solo"           # 1人
    SMALL = "small"         # 2-10
    MEDIUM = "medium"       # 11-50
    LARGE = "large"         # 51-200
    ENTERPRISE = "enterprise"  # 200+


# ── Data Classes ──


@dataclass
class Tenant:
    """SaaS 租户（= Billing Account 持有者）。

    一个 Tenant 可包含多个 Workspace。
    """
    name: str
    email: str  # 管理员邮箱
    id: str = field(default_factory=lambda: f"tnt_{uuid4().hex[:12]}")
    slug: str = ""  # URL-friendly identifier
    status: TenantStatus = TenantStatus.TRIAL
    owner_user_id: str = ""  # User.id of the creator
    org_size: OrganizationSize = OrganizationSize.SOLO
    industry: str = ""
    website: str = ""
    logo_url: str = ""
    timezone: str = "Asia/Shanghai"
    locale: str = "zh-CN"
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_active(self) -> bool:
        return self.status in (TenantStatus.ACTIVE, TenantStatus.TRIAL)


@dataclass
class Organization:
    """组织架构（可选 — Enterprise 套餐用）。"""
    tenant_id: str
    name: str
    id: str = field(default_factory=lambda: f"org_{uuid4().hex[:12]}")
    parent_org_id: str | None = None  # 上级组织（层级结构）
    description: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TenantMember:
    """租户成员（关联 User → Tenant）。"""
    tenant_id: str
    user_id: str
    role: str = "member"  # owner | admin | member | viewer
    org_id: str | None = None  # 所属组织
    id: str = field(default_factory=lambda: f"tmem_{uuid4().hex[:12]}")
    joined_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    invited_by: str | None = None


@dataclass
class TenantContext:
    """请求级别租户上下文。"""
    tenant_id: str
    user_id: str
    role: str = "member"

    def is_owner(self) -> bool:
        return self.role == "owner"

    def is_admin(self) -> bool:
        return self.role in ("owner", "admin")


# ── Protocols ──


@runtime_checkable
class TenantStore(Protocol):
    """租户存储协议。"""

    def create_tenant(self, tenant: Tenant) -> Tenant: ...
    def get_tenant(self, tenant_id: str) -> Tenant | None: ...
    def get_tenant_by_slug(self, slug: str) -> Tenant | None: ...
    def update_tenant(self, tenant: Tenant) -> None: ...
    def delete_tenant(self, tenant_id: str) -> None: ...
    def list_tenants(self, status: str | None = None) -> list[Tenant]: ...
    def add_member(self, member: TenantMember) -> TenantMember: ...
    def remove_member(self, tenant_id: str, user_id: str) -> None: ...
    def list_members(self, tenant_id: str) -> list[TenantMember]: ...
    def get_member(self, tenant_id: str, user_id: str) -> TenantMember | None: ...

    def create_organization(self, org: Organization) -> Organization: ...
    def get_organization(self, org_id: str) -> Organization | None: ...
    def list_organizations(self, tenant_id: str) -> list[Organization]: ...
    def update_organization(self, org: Organization) -> None: ...
    def delete_organization(self, org_id: str) -> None: ...
