"""Team Collaboration Domain Models — ActionPlan / AuditLog / ActivityEvent.

六边形架构核心层：只定义数据类和协议。
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import uuid4


# ── Action Plan ──


class ActionStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ActionPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class ActionPlan:
    """协作行动计划 — 可在成员间分配。"""
    workspace_id: str
    title: str
    description: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))
    assigned_to: str | None = None       # user_id
    assigned_by: str | None = None       # user_id
    priority: ActionPriority = ActionPriority.MEDIUM
    status: ActionStatus = ActionStatus.PENDING
    due_date: datetime | None = None
    related_memory_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


# ── Audit Log ──


class AuditAction(StrEnum):
    MEMORY_CREATE = "memory_create"
    MEMORY_UPDATE = "memory_update"
    MEMORY_DELETE = "memory_delete"
    MEMORY_ARCHIVE = "memory_archive"
    MEMORY_MERGE = "memory_merge"
    WORKSPACE_CREATE = "workspace_create"
    WORKSPACE_DELETE = "workspace_delete"
    MEMBER_ADD = "member_add"
    MEMBER_REMOVE = "member_remove"
    MEMBER_ROLE_CHANGE = "member_role_change"
    ACTION_PLAN_CREATE = "action_plan_create"
    ACTION_PLAN_UPDATE = "action_plan_update"
    ACTION_PLAN_COMPLETE = "action_plan_complete"
    MEMORY_SHARE = "memory_share"


@dataclass
class AuditLog:
    """审计日志 — 所有操作的可追溯记录。"""
    workspace_id: str
    user_id: str
    action: AuditAction
    resource_type: str     # memory | workspace | member | action_plan
    resource_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    detail: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Activity Event (实时通知流) ──


@dataclass
class ActivityEvent:
    """轻量活动事件 — 用于通知和实时 feed。"""
    workspace_id: str
    user_id: str
    user_name: str
    event_type: str         # 任意字符串标签
    message: str
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)


@dataclass
class Notification:
    """用户通知。"""
    user_id: str
    workspace_id: str
    title: str
    body: str
    id: str = field(default_factory=lambda: str(uuid4()))
    read: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    link: str = ""          # 前端跳转链接


# ── Team Dashboard Stats ──


@dataclass
class TeamStats:
    """Workspace 团队概览。"""
    total_members: int = 0
    total_memories: int = 0
    total_actions: int = 0
    completed_actions: int = 0
    member_contributions: list[dict] = field(default_factory=list)
    memory_growth: list[dict] = field(default_factory=list)
    recent_activity: list[dict] = field(default_factory=list)


# ── Protocols ──


@runtime_checkable
class ActionPlanStore(Protocol):
    """行动计划存储协议。"""

    def create(self, plan: ActionPlan) -> ActionPlan: ...
    def get_by_id(self, workspace_id: str, plan_id: str) -> ActionPlan | None: ...
    def list_for_workspace(self, workspace_id: str, assignee_id: str = "") -> list[ActionPlan]: ...
    def list_for_user(self, user_id: str, workspace_id: str = "") -> list[ActionPlan]: ...
    def update(self, plan: ActionPlan) -> None: ...
    def delete(self, workspace_id: str, plan_id: str) -> None: ...


@runtime_checkable
class AuditLogStore(Protocol):
    """审计日志存储协议。"""

    def log(self, entry: AuditLog) -> None: ...
    def list_for_workspace(self, workspace_id: str, limit: int = 50, action: str = "") -> list[AuditLog]: ...
    def list_for_user(self, user_id: str, workspace_id: str, limit: int = 30) -> list[AuditLog]: ...


@runtime_checkable
class NotificationStore(Protocol):
    """通知存储协议。"""

    def send(self, notification: Notification) -> None: ...
    def list_for_user(self, user_id: str, workspace_id: str, unread_only: bool = False, limit: int = 30) -> list[Notification]: ...
    def mark_read(self, notification_id: str, user_id: str) -> None: ...
    def mark_all_read(self, user_id: str, workspace_id: str) -> None: ...
    def unread_count(self, user_id: str, workspace_id: str) -> int: ...
