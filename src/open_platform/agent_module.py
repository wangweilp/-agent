"""Agent Module Domain — 将 Artifact/Package/Workflow 组合为可发布的 Agent 模块。

Agent Publishing 约束：
- AgentModule 只引用 workflow_ids，不内嵌可执行代码
- metadata_only=True
- 审核流水线: draft → review → approved → published
- published 后进入 Marketplace，用户可订阅/使用
- 不可执行、不可启动 runtime/container/microVM

禁止: subprocess/docker/container/microVM/execution/runtime/network/filesystem write
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


# ═══════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════


class AgentModuleStatus(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


_VALID_TRANSITIONS: dict[str, set[str]] = {
    AgentModuleStatus.DRAFT: {AgentModuleStatus.REVIEW},
    AgentModuleStatus.REVIEW: {AgentModuleStatus.APPROVED, AgentModuleStatus.REJECTED},
    AgentModuleStatus.REJECTED: {AgentModuleStatus.DRAFT},
    AgentModuleStatus.APPROVED: {AgentModuleStatus.PUBLISHED},
    AgentModuleStatus.PUBLISHED: set(),
}

_IMMUTABLE_STATUSES: frozenset[str] = frozenset({
    AgentModuleStatus.REVIEW,
    AgentModuleStatus.APPROVED,
    AgentModuleStatus.PUBLISHED,
})


def is_valid_transition(from_status: str, to_status: str) -> bool:
    return to_status in _VALID_TRANSITIONS.get(from_status, set())


def is_immutable(status: str) -> bool:
    return status in _IMMUTABLE_STATUSES


# ═══════════════════════════════════════════
# Subscription Record
# ═══════════════════════════════════════════


@dataclass
class Subscription:
    """用户订阅 Agent 模块的记录。"""
    id: str = field(default_factory=lambda: f"sub_{uuid4().hex[:12]}")
    workspace_id: str = ""
    agent_module_id: str = ""
    subscribed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "agent_module_id": self.agent_module_id,
            "subscribed_at": self.subscribed_at.isoformat(),
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Subscription":
        return cls(
            id=str(d.get("id", "")),
            workspace_id=str(d.get("workspace_id", "")),
            agent_module_id=str(d.get("agent_module_id", "")),
            subscribed_at=_safe_parse_dt(d.get("subscribed_at")),
            active=bool(d.get("active", True)),
        )


# ═══════════════════════════════════════════
# AgentModule Domain
# ═══════════════════════════════════════════


@dataclass
class AgentModule:
    """Agent 发布模块 — 封装 workflow_ids 为可共享的 Agent 模块。

    安全约束：
    - 只引用 workflow_ids（间接引用 package_ids → artifact_ids）
    - metadata_only 永远为 True
    - published 后进入 Marketplace
    """

    id: str = field(default_factory=lambda: f"agent_{uuid4().hex[:12]}")
    workspace_id: str = ""
    name: str = ""
    description: str = ""
    workflow_ids: list[str] = field(default_factory=list)
    version: str = "0.1.0"
    status: str = AgentModuleStatus.DRAFT

    # 安全约束
    metadata_only: bool = True

    # Marketplace 元数据
    author: str = ""
    category: str = ""
    icon_url: str = ""
    tags: list[str] = field(default_factory=list)

    # 审核信息
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_comment: str | None = None

    # 发布信息
    published_by: str | None = None
    published_at: datetime | None = None

    # 扩展元数据
    metadata: dict[str, Any] = field(default_factory=dict)

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def can_transition_to(self, target: str) -> bool:
        return is_valid_transition(self.status, target)

    def is_editable(self) -> bool:
        return not is_immutable(self.status)

    def is_terminal(self) -> bool:
        return self.status in (AgentModuleStatus.PUBLISHED, AgentModuleStatus.REJECTED)

    def is_published(self) -> bool:
        return self.status == AgentModuleStatus.PUBLISHED

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.workspace_id or not self.workspace_id.strip():
            errors.append("workspace_id 必填")
        if not self.name or not self.name.strip():
            errors.append("name 必填")
        if self.status not in [v.value for v in AgentModuleStatus]:
            errors.append(f"status 无效: {self.status}")
        if self.metadata_only is not True:
            errors.append("metadata_only 必须为 True — AgentModule 只存元数据")
        if not isinstance(self.workflow_ids, list):
            errors.append("workflow_ids 必须是 list")
        if not isinstance(self.tags, list):
            errors.append("tags 必须是 list")
        if not isinstance(self.metadata, dict):
            errors.append("metadata 必须是 dict")
        return errors

    def is_valid(self) -> bool:
        return len(self.validate()) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "name": self.name,
            "description": self.description,
            "workflow_ids": list(self.workflow_ids),
            "version": self.version,
            "status": self.status,
            "metadata_only": self.metadata_only,
            "author": self.author,
            "category": self.category,
            "icon_url": self.icon_url,
            "tags": list(self.tags),
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "review_comment": self.review_comment,
            "published_by": self.published_by,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentModule":
        return cls(
            id=str(d.get("id", "")),
            workspace_id=str(d.get("workspace_id", "")),
            name=str(d.get("name", "")),
            description=str(d.get("description", "")),
            workflow_ids=list(d.get("workflow_ids", [])),
            version=str(d.get("version", "0.1.0")),
            status=str(d.get("status", AgentModuleStatus.DRAFT)),
            metadata_only=True,
            author=str(d.get("author", "")),
            category=str(d.get("category", "")),
            icon_url=str(d.get("icon_url", "")),
            tags=list(d.get("tags", [])),
            reviewed_by=d.get("reviewed_by"),
            reviewed_at=_safe_parse_dt(d.get("reviewed_at")),
            review_comment=d.get("review_comment"),
            published_by=d.get("published_by"),
            published_at=_safe_parse_dt(d.get("published_at")),
            metadata=dict(d.get("metadata", {})),
            created_at=_safe_parse_dt(d.get("created_at")),
            updated_at=_safe_parse_dt(d.get("updated_at")),
        )


# ═══════════════════════════════════════════
# Store Protocol
# ═══════════════════════════════════════════


@runtime_checkable
class AgentModuleStore(Protocol):
    def create(self, m: AgentModule) -> AgentModule: ...
    def get(self, agent_module_id: str) -> AgentModule | None: ...
    def list(self, *, workspace_id: str = "", status: str = "",
             category: str = "", limit: int = 50, offset: int = 0) -> list[AgentModule]: ...
    def search(self, q: str, *, category: str = "", limit: int = 50) -> list[AgentModule]: ...
    def update(self, m: AgentModule) -> None: ...
    def update_status(self, agent_module_id: str, status: str,
                      reviewed_by: str | None = None,
                      review_comment: str | None = None,
                      published_by: str | None = None) -> None: ...
    def delete(self, agent_module_id: str) -> None: ...
    def subscribe(self, sub: Subscription) -> Subscription: ...
    def unsubscribe(self, workspace_id: str, agent_module_id: str) -> None: ...
    def list_subscriptions(self, workspace_id: str) -> list[Subscription]: ...
    def get_subscription(self, workspace_id: str, agent_module_id: str) -> Subscription | None: ...


# ═══════════════════════════════════════════
# Error Classes
# ═══════════════════════════════════════════


class AgentModuleNotFoundError(Exception):
    def __init__(self, message: str = "AgentModule 不存在"):
        super().__init__(message)


class AgentModuleValidationError(Exception):
    def __init__(self, message: str = "AgentModule 校验失败", errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


class AgentModuleStateError(Exception):
    def __init__(self, message: str = "AgentModule 状态不允许此操作"):
        super().__init__(message)


class SubscriptionNotFoundError(Exception):
    def __init__(self, message: str = "订阅不存在"):
        super().__init__(message)


class SubscriptionAlreadyExistsError(Exception):
    def __init__(self, message: str = "已订阅此模块"):
        super().__init__(message)


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════


def _safe_parse_dt(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)
