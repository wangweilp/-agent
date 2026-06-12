"""Artifact Service — 制品生命周期管理。

Artifact Sandbox 安全约束：
- Agent 不执行，Agent 只能生成 Artifact
- Artifact 进入 Sandbox（draft 状态）
- 用户审核
- 审核通过后 → published
- 永远不可执行，永远不可启用运行时

禁止：
- subprocess / docker / container / microVM
- execution / runtime
- network / filesystem write
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.open_platform.artifact import (
    Artifact,
    ArtifactNotFoundError,
    ArtifactStateError,
    ArtifactStatus,
    ArtifactType,
    ArtifactValidationError,
    is_valid_transition,
)

logger = logging.getLogger(__name__)


class ArtifactService:
    """Artifact 生命周期管理服务。

    职责：
    - create_artifact: Agent 生成制品，进入 draft
    - submit_review: 提交审核，draft → review
    - approve: 审核通过，review → approved
    - reject: 审核拒绝，review → rejected
    - publish: 发布，approved → published
    """

    def __init__(self, artifact_store) -> None:
        self._store = artifact_store

    # ── create_artifact ──

    def create_artifact(
        self,
        workspace_id: str,
        agent_id: str,
        artifact_type: str,
        title: str,
        description: str = "",
        content: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Artifact:
        """Agent 创建制品 — 永远进入 draft 状态，不可执行。"""
        artifact = Artifact(
            workspace_id=workspace_id,
            agent_id=agent_id,
            artifact_type=artifact_type,
            title=title,
            description=description,
            content=content,
            status=ArtifactStatus.DRAFT,
            execution_allowed=False,
            runtime_enabled=False,
            metadata_only=True,
            tags=tags or [],
            metadata=metadata or {},
        )

        errors = artifact.validate()
        if errors:
            raise ArtifactValidationError(
                f"Artifact 校验失败: {'; '.join(errors)}", errors)

        created = self._store.create(artifact)
        logger.info("artifact_created", extra={
            "artifact_id": created.id,
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "artifact_type": artifact_type,
        })
        return created

    # ── submit_review ──

    def submit_review(self, artifact_id: str) -> Artifact:
        """提交审核 — draft → review。"""
        artifact = self._store.get(artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError(f"Artifact 不存在: {artifact_id}")

        if artifact.status != ArtifactStatus.DRAFT:
            raise ArtifactStateError(
                f"只有 draft 状态的 artifact 可以提交审核，当前: {artifact.status}")

        self._store.update_status(artifact_id, ArtifactStatus.REVIEW)
        logger.info("artifact_submitted_for_review", extra={
            "artifact_id": artifact_id,
        })
        return self._store.get(artifact_id)  # type: ignore[return-value]

    # ── approve ──

    def approve(
        self,
        artifact_id: str,
        reviewer_id: str,
        comment: str = "",
    ) -> Artifact:
        """审核通过 — review → approved。"""
        artifact = self._store.get(artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError(f"Artifact 不存在: {artifact_id}")

        if artifact.status != ArtifactStatus.REVIEW:
            raise ArtifactStateError(
                f"只有 review 状态的 artifact 可以 approve，当前: {artifact.status}")

        self._store.update_status(
            artifact_id,
            ArtifactStatus.APPROVED,
            reviewed_by=reviewer_id,
            review_comment=comment,
        )
        logger.info("artifact_approved", extra={
            "artifact_id": artifact_id,
            "reviewer_id": reviewer_id,
        })
        return self._store.get(artifact_id)  # type: ignore[return-value]

    # ── reject ──

    def reject(
        self,
        artifact_id: str,
        reviewer_id: str,
        comment: str = "",
    ) -> Artifact:
        """审核拒绝 — review → rejected。"""
        artifact = self._store.get(artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError(f"Artifact 不存在: {artifact_id}")

        if artifact.status != ArtifactStatus.REVIEW:
            raise ArtifactStateError(
                f"只有 review 状态的 artifact 可以 reject，当前: {artifact.status}")

        self._store.update_status(
            artifact_id,
            ArtifactStatus.REJECTED,
            reviewed_by=reviewer_id,
            review_comment=comment,
        )
        logger.info("artifact_rejected", extra={
            "artifact_id": artifact_id,
            "reviewer_id": reviewer_id,
        })
        return self._store.get(artifact_id)  # type: ignore[return-value]

    # ── publish ──

    def publish(
        self,
        artifact_id: str,
        publisher_id: str,
    ) -> Artifact:
        """发布 — approved → published。

        published 是终态，进入后不可编辑、不可回退。
        execution_allowed 仍然为 False — 这是 Artifact Sandbox。
        """
        artifact = self._store.get(artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError(f"Artifact 不存在: {artifact_id}")

        if artifact.status != ArtifactStatus.APPROVED:
            raise ArtifactStateError(
                f"只有 approved 状态的 artifact 可以 publish，当前: {artifact.status}")

        self._store.update_status(
            artifact_id,
            ArtifactStatus.PUBLISHED,
            published_by=publisher_id,
        )
        logger.info("artifact_published", extra={
            "artifact_id": artifact_id,
            "publisher_id": publisher_id,
        })
        return self._store.get(artifact_id)  # type: ignore[return-value]

    # ── get / list ──

    def get(self, artifact_id: str) -> Artifact | None:
        """获取单个 artifact。"""
        return self._store.get(artifact_id)

    def list(
        self,
        *,
        workspace_id: str = "",
        agent_id: str = "",
        artifact_type: str = "",
        status: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Artifact]:
        """列出 artifacts。"""
        return self._store.list(
            workspace_id=workspace_id,
            agent_id=agent_id,
            artifact_type=artifact_type,
            status=status,
            limit=limit,
            offset=offset,
        )

    def delete(self, artifact_id: str) -> None:
        """删除 artifact（仅 draft/rejected）。"""
        return self._store.delete(artifact_id)
