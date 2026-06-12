"""Enterprise RBAC / ABAC Domain Models — Permission / Role / Policy.

六边形架构核心层：只定义数据类和协议，不引用任何外部库。

核心约束：
- 禁止跨组织访问 — 所有权限检查必须验证 organization_id
- RBAC: 基于角色的访问控制
- ABAC: 基于属性的访问控制（扩展）
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


# ── Permission Resources & Actions ──


class ResourceType(StrEnum):
    """可被权限控制的资源类型。"""
    WORKSPACE = "workspace"
    MEMORY = "memory"
    IMPORT = "import"
    SYNC = "sync"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    COACH = "coach"
    ADMIN = "admin"
    ORGANIZATION = "organization"
    AUDIT = "audit"
    COMPLIANCE = "compliance"
    AGENT_MARKETPLACE = "agent_marketplace"  # Agent Marketplace 安装/配置
    AGENT = "agent"             # Enterprise AI Agent
    WORKFLOW = "workflow"       # Agent Workflow
    OPEN_PLATFORM = "open_platform"  # Open Platform 开发者管理
    DEVELOPER = "developer"     # Developer 身份与 API Key


class ActionType(StrEnum):
    """操作类型。"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    MANAGE = "manage"          # 管理操作（修改权限、配置）


# ── Predefined Roles ──


class EnterpriseRole(StrEnum):
    """企业级角色 — 层级递进，越往下权限越大。"""
    SUPER_ADMIN = "super_admin"      # 系统最高权限
    ORG_ADMIN = "org_admin"          # 组织管理员
    DEPT_ADMIN = "dept_admin"        # 部门管理员
    MANAGER = "manager"              # 管理者
    EMPLOYEE = "employee"            # 普通员工
    GUEST = "guest"                  # 访客（只读限制资源）

    @classmethod
    def hierarchy(cls) -> dict[str, int]:
        return {
            "guest": 0,
            "employee": 1,
            "manager": 2,
            "dept_admin": 3,
            "org_admin": 4,
            "super_admin": 5,
        }

    def rank(self) -> int:
        return self.hierarchy().get(self.value, 0)

    def can_manage_users(self) -> bool:
        return self.rank() >= self.hierarchy()["org_admin"]

    def can_access_admin(self) -> bool:
        return self.rank() >= self.hierarchy()["dept_admin"]


# ── Permission ──


@dataclass
class Permission:
    """细粒度权限 — 针对特定资源的特定操作。"""
    resource: ResourceType
    action: ActionType
    organization_id: str = ""           # 空 = 全局权限（仅 SuperAdmin）
    id: str = field(default_factory=lambda: str(uuid4()))
    description: str = ""

    @property
    def key(self) -> str:
        """权限唯一键：resource:action:org_id"""
        return f"{self.resource.value}:{self.action.value}:{self.organization_id or '*'}"


# ── Role ──


@dataclass
class Role:
    """角色 — 一组权限的集合。"""
    name: str                           # EnterpriseRole 值或自定义角色名
    organization_id: str                # 角色所属组织
    permissions: list[str] = field(default_factory=list)  # Permission.key 列表
    id: str = field(default_factory=lambda: str(uuid4()))
    description: str = ""
    is_system: bool = False             # 系统预定义角色不可删除
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Policy (ABAC) ──


@dataclass
class Policy:
    """ABAC 策略 — 基于属性的访问规则。

    示例：
      Policy(
        name="deny-cross-org",
        effect="deny",
        conditions={"resource.org_id": {"neq": "subject.org_id"}}
      )
    """
    name: str
    effect: str                         # "allow" | "deny"
    organization_id: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))
    description: str = ""
    priority: int = 100                 # 越小越优先
    conditions: dict[str, Any] = field(default_factory=dict)
    # conditions 支持的操作符：eq, neq, in, not_in, contains, regex
    enabled: bool = True
    is_system: bool = False             # 系统预定义策略不可删除
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── RBAC Assignment ──


@dataclass
class RoleAssignment:
    """用户-角色绑定。"""
    user_id: str
    role_id: str
    organization_id: str
    scope_type: str = "organization"     # "organization" | "business_unit" | "department"
    scope_id: str = ""                   # BU/Department ID
    id: str = field(default_factory=lambda: str(uuid4()))
    assigned_by: str = ""               # 分配者 user_id
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Access Request & Decision ──


@dataclass
class AccessRequest:
    """权限检查请求。"""
    user_id: str
    organization_id: str
    resource: ResourceType
    action: ActionType
    resource_id: str = ""               # 具体资源 ID
    is_super_admin: bool = False        # 超级管理员 — 绕过所有检查
    context: dict[str, Any] = field(default_factory=dict)  # 额外上下文（IP、时间等）


@dataclass
class AccessDecision:
    """权限检查结果。"""
    allowed: bool
    reason: str = ""
    matched_role: str = ""
    matched_policy: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Role-Permission Mapping (built-in) ──


def get_default_role_permissions() -> dict[EnterpriseRole, list[str]]:
    """系统预定义角色 → 权限列表。

    权限粒度：Workspace / Memory / Import / Sync / KnowledgeGraph / Coach / Admin
    """
    R = ResourceType
    A = ActionType

    def _perms(resource: ResourceType, actions: list[ActionType]) -> list[str]:
        return [f"{resource.value}:{a.value}:*" for a in actions]

    read_write = [A.CREATE, A.READ, A.UPDATE, A.DELETE]
    read_only = [A.READ]
    full = read_write + [A.EXPORT, A.MANAGE]

    return {
        EnterpriseRole.SUPER_ADMIN: (
            _perms(R.WORKSPACE, full) +
            _perms(R.MEMORY, full) +
            _perms(R.IMPORT, full) +
            _perms(R.SYNC, full) +
            _perms(R.KNOWLEDGE_GRAPH, full) +
            _perms(R.COACH, full) +
            _perms(R.ADMIN, full) +
            _perms(R.ORGANIZATION, full) +
            _perms(R.AUDIT, full) +
            _perms(R.COMPLIANCE, full)
        ),
        EnterpriseRole.ORG_ADMIN: (
            _perms(R.WORKSPACE, full) +
            _perms(R.MEMORY, full) +
            _perms(R.IMPORT, full) +
            _perms(R.SYNC, full) +
            _perms(R.KNOWLEDGE_GRAPH, full) +
            _perms(R.COACH, full) +
            _perms(R.ADMIN, read_write) +
            _perms(R.ORGANIZATION, read_write) +
            _perms(R.AUDIT, read_only) +
            _perms(R.COMPLIANCE, read_only)
        ),
        EnterpriseRole.DEPT_ADMIN: (
            _perms(R.WORKSPACE, read_write) +
            _perms(R.MEMORY, read_write) +
            _perms(R.IMPORT, read_write) +
            _perms(R.SYNC, read_only) +
            _perms(R.KNOWLEDGE_GRAPH, read_only) +
            _perms(R.COACH, read_only) +
            _perms(R.ADMIN, read_only) +
            _perms(R.ORGANIZATION, read_only)
        ),
        EnterpriseRole.MANAGER: (
            _perms(R.WORKSPACE, [A.CREATE, A.READ, A.UPDATE]) +
            _perms(R.MEMORY, read_write) +
            _perms(R.IMPORT, read_write) +
            _perms(R.SYNC, [A.CREATE, A.READ]) +
            _perms(R.KNOWLEDGE_GRAPH, read_only) +
            _perms(R.COACH, read_only)
        ),
        EnterpriseRole.EMPLOYEE: (
            _perms(R.WORKSPACE, [A.READ]) +
            _perms(R.MEMORY, [A.CREATE, A.READ, A.UPDATE]) +
            _perms(R.IMPORT, [A.CREATE, A.READ]) +
            _perms(R.KNOWLEDGE_GRAPH, read_only) +
            _perms(R.COACH, read_only)
        ),
        EnterpriseRole.GUEST: (
            _perms(R.WORKSPACE, [A.READ]) +
            _perms(R.MEMORY, [A.READ]) +
            _perms(R.KNOWLEDGE_GRAPH, read_only)
        ),
    }


# ── Cross-Org Isolation (ABAC Default Policy) ──


def get_default_abac_policies(organization_id: str) -> list[Policy]:
    """为组织生成默认 ABAC 策略 — 核心：禁止跨组织访问。"""
    return [
        Policy(
            name="deny-cross-org-access",
            effect="deny",
            organization_id=organization_id,
            priority=1,  # 最高优先级
            description="禁止跨组织访问 — 用户只能访问所属组织的数据",
            conditions={
                "subject.org_id": {"neq": "resource.org_id"},
            },
            is_system=True,
        ),
        Policy(
            name="allow-same-org-access",
            effect="allow",
            organization_id=organization_id,
            priority=100,
            description="允许同组织内访问",
            conditions={
                "subject.org_id": {"eq": "resource.org_id"},
            },
            is_system=True,
        ),
    ]


# ── Protocols ──


@runtime_checkable
class RBACStore(Protocol):
    """RBAC 存储协议。"""

    # Permission
    def create_permission(self, p: Permission) -> Permission: ...
    def get_permission(self, perm_id: str) -> Permission | None: ...
    def list_permissions(self, organization_id: str) -> list[Permission]: ...
    def delete_permission(self, perm_id: str) -> None: ...

    # Role
    def create_role(self, role: Role) -> Role: ...
    def get_role(self, role_id: str) -> Role | None: ...
    def get_role_by_name(self, name: str, organization_id: str) -> Role | None: ...
    def list_roles(self, organization_id: str) -> list[Role]: ...
    def update_role(self, role: Role) -> None: ...
    def delete_role(self, role_id: str) -> None: ...
    def add_permission_to_role(self, role_id: str, permission_key: str) -> None: ...
    def remove_permission_from_role(self, role_id: str, permission_key: str) -> None: ...

    # Policy
    def create_policy(self, policy: Policy) -> Policy: ...
    def get_policy(self, policy_id: str) -> Policy | None: ...
    def list_policies(self, organization_id: str) -> list[Policy]: ...
    def update_policy(self, policy: Policy) -> None: ...
    def delete_policy(self, policy_id: str) -> None: ...

    # Role Assignment
    def assign_role(self, assignment: RoleAssignment) -> RoleAssignment: ...
    def get_user_assignments(self, user_id: str,
                             organization_id: str) -> list[RoleAssignment]: ...
    def remove_assignment(self, assignment_id: str) -> None: ...
    def get_user_roles(self, user_id: str, organization_id: str) -> list[Role]: ...

    # Access Check
    def check_access(self, request: AccessRequest) -> AccessDecision: ...


@runtime_checkable
class ABACEngine(Protocol):
    """ABAC 策略评估引擎协议。"""

    def evaluate(self, request: AccessRequest,
                 policies: list[Policy],
                 subject_attrs: dict[str, Any],
                 resource_attrs: dict[str, Any]) -> AccessDecision: ...
