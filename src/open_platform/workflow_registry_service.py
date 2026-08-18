"""Workflow Registry Service — Workflow 生命周期管理。

约束：
- metadata-only
- 审核流水线: draft → review → approved → published
- 不执行、不联网、不写文件
"""

from __future__ import annotations

import logging
from typing import Any

from src.open_platform.workflow_registry import (
    Workflow,
    WorkflowNotFoundError,
    WorkflowStateError,
    WorkflowStatus,
    WorkflowValidationError,
)

logger = logging.getLogger(__name__)


class WorkflowService:
    """Workflow 生命周期管理服务。"""

    def __init__(self, workflow_store) -> None:
        self._store = workflow_store

    def create_workflow(
        self,
        workspace_id: str,
        name: str,
        description: str = "",
        package_ids: list[str] | None = None,
        version: str = "0.1.0",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Workflow:
        workflow = Workflow(
            workspace_id=workspace_id,
            name=name,
            description=description,
            package_ids=package_ids or [],
            version=version,
            status=WorkflowStatus.DRAFT,
            metadata_only=True,
            tags=tags or [],
            metadata=metadata or {},
        )
        errors = workflow.validate()
        if errors:
            raise WorkflowValidationError(
                f"Workflow 校验失败: {'; '.join(errors)}", errors)
        created = self._store.create(workflow)
        logger.info("workflow_created", extra={"workflow_id": created.id, "workflow_name": name})
        return created

    def submit_review(self, workflow_id: str) -> Workflow:
        wf = self._store.get(workflow_id)
        if wf is None:
            raise WorkflowNotFoundError(f"Workflow 不存在: {workflow_id}")
        if wf.status != WorkflowStatus.DRAFT:
            raise WorkflowStateError(
                f"只有 draft 状态可提交审核，当前: {wf.status}")
        self._store.update_status(workflow_id, WorkflowStatus.REVIEW)
        logger.info("workflow_review_submitted", extra={"workflow_id": workflow_id})
        return self._store.get(workflow_id)  # type: ignore[return-value]

    def approve(self, workflow_id: str, reviewer_id: str,
                comment: str = "") -> Workflow:
        wf = self._store.get(workflow_id)
        if wf is None:
            raise WorkflowNotFoundError(f"Workflow 不存在: {workflow_id}")
        if wf.status != WorkflowStatus.REVIEW:
            raise WorkflowStateError(
                f"只有 review 状态可 approve，当前: {wf.status}")
        self._store.update_status(
            workflow_id, WorkflowStatus.APPROVED,
            reviewed_by=reviewer_id, review_comment=comment)
        logger.info("workflow_approved", extra={"workflow_id": workflow_id})
        return self._store.get(workflow_id)  # type: ignore[return-value]

    def reject(self, workflow_id: str, reviewer_id: str,
               comment: str = "") -> Workflow:
        wf = self._store.get(workflow_id)
        if wf is None:
            raise WorkflowNotFoundError(f"Workflow 不存在: {workflow_id}")
        if wf.status != WorkflowStatus.REVIEW:
            raise WorkflowStateError(
                f"只有 review 状态可 reject，当前: {wf.status}")
        self._store.update_status(
            workflow_id, WorkflowStatus.REJECTED,
            reviewed_by=reviewer_id, review_comment=comment)
        logger.info("workflow_rejected", extra={"workflow_id": workflow_id})
        return self._store.get(workflow_id)  # type: ignore[return-value]

    def publish(self, workflow_id: str, publisher_id: str) -> Workflow:
        wf = self._store.get(workflow_id)
        if wf is None:
            raise WorkflowNotFoundError(f"Workflow 不存在: {workflow_id}")
        if wf.status != WorkflowStatus.APPROVED:
            raise WorkflowStateError(
                f"只有 approved 状态可 publish，当前: {wf.status}")
        self._store.update_status(
            workflow_id, WorkflowStatus.PUBLISHED, published_by=publisher_id)
        logger.info("workflow_published", extra={"workflow_id": workflow_id})
        return self._store.get(workflow_id)  # type: ignore[return-value]

    def get(self, workflow_id: str) -> Workflow | None:
        return self._store.get(workflow_id)

    def list(self, *, workspace_id: str = "", status: str = "",
             limit: int = 50, offset: int = 0) -> list[Workflow]:
        return self._store.list(
            workspace_id=workspace_id, status=status,
            limit=limit, offset=offset)

    def delete(self, workflow_id: str) -> None:
        return self._store.delete(workflow_id)
