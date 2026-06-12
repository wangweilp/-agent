"""Workflow Registry Domain Model — 将 Package 组合为 Workflow。

Workflow Sandbox 约束：
- Workflow 只包含 Package 引用（package_ids），不包含代码
- metadata_only=True — 只存储元数据
- 审核流水线: draft → review → approved → published
- Workflow 在 published 后才能用于未来 Runtime
- 不可执行、不可启动 runtime/container/microVM

禁止：
- subprocess / docker / container / microVM
- execution / runtime / network / filesystem write
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


class WorkflowStatus(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


_VALID_TRANSITIONS: dict[str, set[str]] = {
    WorkflowStatus.DRAFT: {WorkflowStatus.REVIEW},
    WorkflowStatus.REVIEW: {WorkflowStatus.APPROVED, WorkflowStatus.REJECTED},
    WorkflowStatus.REJECTED: {WorkflowStatus.DRAFT},
    WorkflowStatus.APPROVED: {WorkflowStatus.PUBLISHED},
    WorkflowStatus.PUBLISHED: set(),
}

_IMMUTABLE_STATUSES: frozenset[str] = frozenset({
    WorkflowStatus.REVIEW,
    WorkflowStatus.APPROVED,
    WorkflowStatus.PUBLISHED,
})


def is_valid_transition(from_status: str, to_status: str) -> bool:
    allowed = _VALID_TRANSITIONS.get(from_status, set())
    return to_status in allowed


def is_immutable(status: str) -> bool:
    return status in _IMMUTABLE_STATUSES


# ═══════════════════════════════════════════
# Workflow Domain
# ═══════════════════════════════════════════


@dataclass
class Workflow:
    """Package 组合 — 将多个 Package 编排为 Workflow。

    安全约束：
    - 只引用 package_ids，不内嵌可执行代码
    - metadata_only 永远为 True
    - Workflow 定义的是元数据层面的编排关系
    """

    id: str = field(default_factory=lambda: f"wf_{uuid4().hex[:12]}")
    workspace_id: str = ""
    name: str = ""
    description: str = ""
    package_ids: list[str] = field(default_factory=list)
    version: str = "0.1.0"
    status: str = WorkflowStatus.DRAFT

    # 安全约束
    metadata_only: bool = True

    # 审核信息
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_comment: str | None = None

    # 发布信息
    published_by: str | None = None
    published_at: datetime | None = None

    # 元数据
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def can_transition_to(self, target: str) -> bool:
        return is_valid_transition(self.status, target)

    def is_editable(self) -> bool:
        return not is_immutable(self.status)

    def is_terminal(self) -> bool:
        return self.status in (WorkflowStatus.PUBLISHED, WorkflowStatus.REJECTED)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.workspace_id or not self.workspace_id.strip():
            errors.append("workspace_id 必填")
        if not self.name or not self.name.strip():
            errors.append("name 必填")
        if self.status not in [v.value for v in WorkflowStatus]:
            errors.append(f"status 无效: {self.status}")
        if self.metadata_only is not True:
            errors.append("metadata_only 必须为 True — Workflow 只存元数据")
        if not isinstance(self.package_ids, list):
            errors.append("package_ids 必须是 list")
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
            "package_ids": list(self.package_ids),
            "version": self.version,
            "status": self.status,
            "metadata_only": self.metadata_only,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "review_comment": self.review_comment,
            "published_by": self.published_by,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Workflow":
        return cls(
            id=str(d.get("id", "")),
            workspace_id=str(d.get("workspace_id", "")),
            name=str(d.get("name", "")),
            description=str(d.get("description", "")),
            package_ids=list(d.get("package_ids", [])),
            version=str(d.get("version", "0.1.0")),
            status=str(d.get("status", WorkflowStatus.DRAFT)),
            metadata_only=True,
            reviewed_by=d.get("reviewed_by"),
            reviewed_at=_safe_parse_dt(d.get("reviewed_at")),
            review_comment=d.get("review_comment"),
            published_by=d.get("published_by"),
            published_at=_safe_parse_dt(d.get("published_at")),
            tags=list(d.get("tags", [])),
            metadata=dict(d.get("metadata", {})),
            created_at=_safe_parse_dt(d.get("created_at")),
            updated_at=_safe_parse_dt(d.get("updated_at")),
        )


# ═══════════════════════════════════════════
# WorkflowStore Protocol
# ═══════════════════════════════════════════


@runtime_checkable
class WorkflowStore(Protocol):
    """Workflow 存储协议。metadata-only，不执行。"""

    def create(self, workflow: Workflow) -> Workflow: ...
    def get(self, workflow_id: str) -> Workflow | None: ...
    def list(self, *, workspace_id: str = "", status: str = "",
             limit: int = 50, offset: int = 0) -> list[Workflow]: ...
    def update(self, workflow: Workflow) -> None: ...
    def update_status(self, workflow_id: str, status: str,
                      reviewed_by: str | None = None,
                      review_comment: str | None = None,
                      published_by: str | None = None) -> None: ...
    def delete(self, workflow_id: str) -> None: ...


# ═══════════════════════════════════════════
# Error Classes
# ═══════════════════════════════════════════


class WorkflowNotFoundError(Exception):
    def __init__(self, message: str = "Workflow 不存在"):
        super().__init__(message)


class WorkflowValidationError(Exception):
    def __init__(self, message: str = "Workflow 校验失败", errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


class WorkflowStateError(Exception):
    def __init__(self, message: str = "Workflow 状态不允许此操作"):
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
