"""Enterprise Organization Domain Models — Organization / BusinessUnit / Department / Position.

六边形架构核心层：只定义数据类和协议，不引用任何外部库。
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable
from uuid import uuid4


# ── Data Classes ──


@dataclass
class Organization:
    """企业组织 — 顶层实体，隔离不同企业的数据。

    一个 Organization 可包含多个 Workspace，但 RBAC 策略禁止跨组织访问。
    """
    name: str
    industry: str = ""
    owner_id: str = ""                     # User.id — 组织创建者
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class BusinessUnit:
    """业务单元 — 组织下的第二层级，如「研发中心」「产品中心」。"""
    organization_id: str
    name: str
    id: str = field(default_factory=lambda: str(uuid4()))
    parent_id: str | None = None           # 上级 BU，null = 顶层
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Department:
    """部门 — BU 下的第三层级，如「后端组」「前端组」。"""
    organization_id: str
    business_unit_id: str
    name: str
    id: str = field(default_factory=lambda: str(uuid4()))
    parent_id: str | None = None           # 上级部门，支持部门嵌套
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Position:
    """职位 — 用户在组织中的岗位，关联到部门。

    position 决定了用户的默认角色和权限基础。
    """
    organization_id: str
    department_id: str
    user_id: str
    title: str                             # "后端工程师" / "产品经理" / "部门主管"
    id: str = field(default_factory=lambda: str(uuid4()))
    is_manager: bool = False               # 是否为部门管理者
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Organizational Tree Node (for API responses) ──


@dataclass
class OrgTreeNode:
    """组织树节点 — 用于前端渲染组织架构图。"""
    id: str
    name: str
    node_type: str                         # "organization" | "business_unit" | "department"
    children: list["OrgTreeNode"] = field(default_factory=list)
    member_count: int = 0
    metadata: dict = field(default_factory=dict)


# ── Protocols ──


@runtime_checkable
class OrganizationStore(Protocol):
    """组织存储协议。"""

    # Organization
    def create_organization(self, name: str, owner_id: str, industry: str = "") -> Organization: ...
    def get_organization(self, org_id: str) -> Organization | None: ...
    def list_organizations(self, user_id: str) -> list[Organization]: ...
    def update_organization(self, org: Organization) -> None: ...
    def delete_organization(self, org_id: str) -> None: ...

    # BusinessUnit
    def create_business_unit(self, organization_id: str, name: str,
                             parent_id: str | None = None,
                             description: str = "") -> BusinessUnit: ...
    def get_business_unit(self, bu_id: str) -> BusinessUnit | None: ...
    def list_business_units(self, organization_id: str) -> list[BusinessUnit]: ...
    def update_business_unit(self, bu: BusinessUnit) -> None: ...
    def delete_business_unit(self, bu_id: str) -> None: ...

    # Department
    def create_department(self, organization_id: str, business_unit_id: str, name: str,
                          parent_id: str | None = None,
                          description: str = "") -> Department: ...
    def get_department(self, dept_id: str) -> Department | None: ...
    def list_departments(self, organization_id: str,
                         business_unit_id: str = "") -> list[Department]: ...
    def update_department(self, dept: Department) -> None: ...
    def delete_department(self, dept_id: str) -> None: ...

    # Position
    def create_position(self, organization_id: str, department_id: str,
                        user_id: str, title: str,
                        is_manager: bool = False) -> Position: ...
    def get_position(self, position_id: str) -> Position | None: ...
    def get_position_by_user(self, user_id: str,
                             organization_id: str) -> Position | None: ...
    def list_positions(self, organization_id: str,
                       department_id: str = "") -> list[Position]: ...
    def list_positions_by_user(self, user_id: str) -> list[Position]: ...
    def update_position(self, position: Position) -> None: ...
    def delete_position(self, position_id: str) -> None: ...

    # Org Tree
    def get_org_tree(self, organization_id: str) -> OrgTreeNode | None: ...
    def get_member_count(self, organization_id: str) -> int: ...
