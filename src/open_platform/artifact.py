"""Artifact Domain Model — Agent 生成的制品。

Artifact Sandbox 核心约束：
- Agent 不执行，Agent 只能生成 Artifact
- Artifact 进入 Sandbox，用户审核
- 审核通过后进入 published 状态，等待未来 Runtime
- execution_allowed=False — 永远不可执行
- runtime_enabled=False — 永远不启用运行时
- metadata_only=True — 只存储元数据，不实例化执行环境

禁止：
- subprocess / docker / container / microVM
- execution / runtime
- network / filesystem write
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


class ArtifactType(StrEnum):
    CODE = "code"
    WORKFLOW = "workflow"
    PROMPT = "prompt"
    KNOWLEDGE_PACK = "knowledge_pack"
    TOOL_BUNDLE = "tool_bundle"


class ArtifactStatus(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


# ── 状态转换图 ─────────────────────────────
# Draft → Review → Approved → Published
#               ↘ Rejected → Draft（重新提交）
#
# 状态迁移白名单：
_VALID_TRANSITIONS: dict[str, set[str]] = {
    ArtifactStatus.DRAFT: {ArtifactStatus.REVIEW, ArtifactStatus.REJECTED},
    ArtifactStatus.REVIEW: {ArtifactStatus.APPROVED, ArtifactStatus.REJECTED},
    ArtifactStatus.REJECTED: {ArtifactStatus.DRAFT},
    ArtifactStatus.APPROVED: {ArtifactStatus.PUBLISHED},
    ArtifactStatus.PUBLISHED: set(),  # 终态
}

# 这些状态下 artifact 不可编辑
_IMMUTABLE_STATUSES: frozenset[str] = frozenset({
    ArtifactStatus.REVIEW,
    ArtifactStatus.APPROVED,
    ArtifactStatus.PUBLISHED,
})


def is_valid_transition(from_status: str, to_status: str) -> bool:
    """检查状态迁移是否合法。"""
    allowed = _VALID_TRANSITIONS.get(from_status, set())
    return to_status in allowed


def is_immutable(status: str) -> bool:
    """检查状态下 artifact 是否不可编辑。"""
    return status in _IMMUTABLE_STATUSES


# ═══════════════════════════════════════════
# Artifact
# ═══════════════════════════════════════════


@dataclass
class Artifact:
    """Agent 生成的制品 — 不执行，只存储元数据。

    安全约束：
    - execution_allowed 永远为 False
    - runtime_enabled 永远为 False
    - metadata_only 永远为 True
    - 不包含任何执行相关方法
    """

    id: str = field(default_factory=lambda: f"art_{uuid4().hex[:12]}")
    workspace_id: str = ""
    agent_id: str = ""

    artifact_type: str = ArtifactType.CODE
    title: str = ""
    description: str = ""
    content: str = ""

    status: str = ArtifactStatus.DRAFT

    # 安全元数据
    execution_allowed: bool = False  # 永远 False
    runtime_enabled: bool = False    # 永远 False
    metadata_only: bool = True       # 永远 True

    # 审核信息
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_comment: str | None = None

    # 发布信息
    published_by: str | None = None
    published_at: datetime | None = None

    # 额外元数据
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ── 状态方法 ──

    def can_transition_to(self, target: str) -> bool:
        """检查是否能迁移到目标状态。"""
        return is_valid_transition(self.status, target)

    def is_editable(self) -> bool:
        """检查是否可编辑。review/approved/published 不可编辑。"""
        return not is_immutable(self.status)

    def is_terminal(self) -> bool:
        """终态检查。"""
        return self.status in (ArtifactStatus.PUBLISHED, ArtifactStatus.REJECTED)

    # ── 校验 ──

    def validate(self) -> list[str]:
        """校验 artifact 合法性，返回 errors 列表。"""
        errors: list[str] = []

        if not self.workspace_id or not self.workspace_id.strip():
            errors.append("workspace_id 必填")
        if not self.agent_id or not self.agent_id.strip():
            errors.append("agent_id 必填")
        if not self.title or not self.title.strip():
            errors.append("title 必填")
        if self.artifact_type not in [v.value for v in ArtifactType]:
            errors.append(f"artifact_type 无效: {self.artifact_type}")
        if self.status not in [v.value for v in ArtifactStatus]:
            errors.append(f"status 无效: {self.status}")

        # 安全硬约束：永远不可执行
        if self.execution_allowed is not False:
            errors.append("execution_allowed 必须为 False — Artifact Sandbox 禁止执行")
        if self.runtime_enabled is not False:
            errors.append("runtime_enabled 必须为 False — Artifact Sandbox 禁止运行时")
        if self.metadata_only is not True:
            errors.append("metadata_only 必须为 True — Artifact Sandbox 只存元数据")

        if not isinstance(self.tags, list):
            errors.append("tags 必须是 list")
        if not isinstance(self.metadata, dict):
            errors.append("metadata 必须是 dict")

        return errors

    def is_valid(self) -> bool:
        return len(self.validate()) == 0

    # ── 序列化 ──

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "agent_id": self.agent_id,
            "artifact_type": self.artifact_type,
            "title": self.title,
            "description": self.description,
            "content": self.content,
            "status": self.status,
            "execution_allowed": self.execution_allowed,
            "runtime_enabled": self.runtime_enabled,
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
    def from_dict(cls, d: dict[str, Any]) -> "Artifact":
        return cls(
            id=str(d.get("id", "")),
            workspace_id=str(d.get("workspace_id", "")),
            agent_id=str(d.get("agent_id", "")),
            artifact_type=str(d.get("artifact_type", ArtifactType.CODE)),
            title=str(d.get("title", "")),
            description=str(d.get("description", "")),
            content=str(d.get("content", "")),
            status=str(d.get("status", ArtifactStatus.DRAFT)),
            execution_allowed=False,
            runtime_enabled=False,
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
# ArtifactStore Protocol
# ═══════════════════════════════════════════


@runtime_checkable
class ArtifactStore(Protocol):
    """Artifact 存储协议。

    禁止：
    - 执行代码
    - 联网
    - 文件系统写
    - 读取 secrets
    - container / microVM / runtime
    """

    def create(self, artifact: Artifact) -> Artifact: ...
    def get(self, artifact_id: str) -> Artifact | None: ...
    def list(
        self,
        *,
        workspace_id: str = "",
        agent_id: str = "",
        artifact_type: str = "",
        status: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Artifact]: ...
    def update(self, artifact: Artifact) -> None: ...
    def update_status(
        self,
        artifact_id: str,
        status: str,
        reviewed_by: str | None = None,
        review_comment: str | None = None,
        published_by: str | None = None,
    ) -> None: ...
    def delete(self, artifact_id: str) -> None: ...


# ═══════════════════════════════════════════
# Error Classes
# ═══════════════════════════════════════════


class ArtifactNotFoundError(Exception):
    def __init__(self, message: str = "Artifact 不存在"):
        super().__init__(message)


class ArtifactValidationError(Exception):
    def __init__(self, message: str = "Artifact 校验失败", errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


class ArtifactStateError(Exception):
    def __init__(self, message: str = "Artifact 状态不允许此操作"):
        super().__init__(message)


class ArtifactPermissionError(Exception):
    def __init__(self, message: str = "无权操作此 Artifact"):
        super().__init__(message)


class ArtifactAlreadyExistsError(Exception):
    def __init__(self, message: str = "Artifact 已存在"):
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
