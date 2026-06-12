"""Workflow Registry API — /api/workflows 端点。

端点:
- POST   /api/workflows                  — 创建 Workflow
- GET    /api/workflows                  — 列出 Workflows
- GET    /api/workflows/{id}             — Workflow 详情
- PATCH  /api/workflows/{id}             — 更新（仅 draft/rejected）
- DELETE /api/workflows/{id}             — 删除（仅 draft/rejected）
- PATCH  /api/workflows/{id}/status      — 状态迁移
- POST   /api/workflows/{id}/review      — 提交审核
- POST   /api/workflows/{id}/approve     — 审核通过
- POST   /api/workflows/{id}/reject      — 审核拒绝
- POST   /api/workflows/{id}/publish     — 发布

约束: metadata_only=True，不执行
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.middleware import require_auth, TokenPayload

logger = logging.getLogger(__name__)


class CreateWorkflowRequest(BaseModel):
    workspace_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = ""
    package_ids: list[str] = Field(default_factory=list)
    version: str = "0.1.0"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateWorkflowRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    package_ids: list[str] | None = None
    version: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class ReviewActionRequest(BaseModel):
    reviewer_id: str = Field(..., min_length=1)
    comment: str = ""


class StatusUpdateRequest(BaseModel):
    status: str = Field(..., min_length=1)
    reviewer_id: str = ""
    review_comment: str = ""
    publisher_id: str = ""


def create_workflow_router(workflow_service, usage_store=None) -> APIRouter:
    router = APIRouter(prefix="/api/workflows", tags=["workflows"])

    @router.post("", status_code=201)
    async def create_workflow(
        body: CreateWorkflowRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        from src.open_platform.workflow_registry import WorkflowValidationError
        try:
            wf = workflow_service.create_workflow(
                workspace_id=body.workspace_id,
                name=body.name,
                description=body.description,
                package_ids=body.package_ids,
                version=body.version,
                tags=body.tags,
                metadata=body.metadata,
            )
        except WorkflowValidationError as e:
            raise HTTPException(status_code=422, detail={"message": str(e), "errors": e.errors})
        return {"workflow": wf.to_dict()}

    @router.get("")
    async def list_workflows(
        workspace_id: str = Query(default=""),
        status: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        wfs = workflow_service.list(
            workspace_id=workspace_id, status=status,
            limit=limit, offset=offset)
        return {"workflows": [w.to_dict() for w in wfs], "total": len(wfs)}

    @router.get("/{workflow_id}")
    async def get_workflow(
        workflow_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        wf = workflow_service.get(workflow_id)
        if wf is None:
            raise HTTPException(status_code=404, detail="Workflow 不存在")
        return {"workflow": wf.to_dict()}

    @router.patch("/{workflow_id}")
    async def update_workflow(
        workflow_id: str,
        body: UpdateWorkflowRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        from src.open_platform.workflow_registry import (
            WorkflowNotFoundError, WorkflowStateError, WorkflowValidationError)
        wf = workflow_service.get(workflow_id)
        if wf is None:
            raise HTTPException(status_code=404, detail="Workflow 不存在")
        if body.name is not None: wf.name = body.name
        if body.description is not None: wf.description = body.description
        if body.package_ids is not None: wf.package_ids = body.package_ids
        if body.version is not None: wf.version = body.version
        if body.tags is not None: wf.tags = body.tags
        if body.metadata is not None: wf.metadata = {**wf.metadata, **body.metadata}
        try:
            workflow_service._store.update(wf)
        except WorkflowNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except WorkflowStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except WorkflowValidationError as e:
            raise HTTPException(status_code=422, detail={"message": str(e), "errors": e.errors})
        updated = workflow_service.get(workflow_id)
        return {"workflow": updated.to_dict() if updated else None}

    @router.delete("/{workflow_id}")
    async def delete_workflow(
        workflow_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        from src.open_platform.workflow_registry import (
            WorkflowNotFoundError, WorkflowStateError)
        try:
            workflow_service.delete(workflow_id)
        except WorkflowNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except WorkflowStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"success": True, "workflow_id": workflow_id}

    @router.patch("/{workflow_id}/status")
    async def update_status(
        workflow_id: str,
        body: StatusUpdateRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        from src.open_platform.workflow_registry import (
            WorkflowNotFoundError, WorkflowStateError)
        try:
            workflow_service._store.update_status(
                workflow_id, body.status,
                reviewed_by=body.reviewer_id or None,
                review_comment=body.review_comment or None,
                published_by=body.publisher_id or None)
        except WorkflowNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except WorkflowStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
        updated = workflow_service.get(workflow_id)
        return {"workflow": updated.to_dict() if updated else None}

    @router.post("/{workflow_id}/review")
    async def submit_review(
        workflow_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        from src.open_platform.workflow_registry import (
            WorkflowNotFoundError, WorkflowStateError)
        try:
            wf = workflow_service.submit_review(workflow_id)
        except WorkflowNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except WorkflowStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"workflow": wf.to_dict()}

    @router.post("/{workflow_id}/approve")
    async def approve(
        workflow_id: str,
        body: ReviewActionRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        from src.open_platform.workflow_registry import (
            WorkflowNotFoundError, WorkflowStateError)
        try:
            wf = workflow_service.approve(workflow_id, body.reviewer_id, body.comment)
        except WorkflowNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except WorkflowStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"workflow": wf.to_dict()}

    @router.post("/{workflow_id}/reject")
    async def reject(
        workflow_id: str,
        body: ReviewActionRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        from src.open_platform.workflow_registry import (
            WorkflowNotFoundError, WorkflowStateError)
        try:
            wf = workflow_service.reject(workflow_id, body.reviewer_id, body.comment)
        except WorkflowNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except WorkflowStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"workflow": wf.to_dict()}

    @router.post("/{workflow_id}/publish")
    async def publish(
        workflow_id: str,
        publisher_id: str = Query(..., min_length=1),
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        from src.open_platform.workflow_registry import (
            WorkflowNotFoundError, WorkflowStateError)
        try:
            wf = workflow_service.publish(workflow_id, publisher_id)
        except WorkflowNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except WorkflowStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"workflow": wf.to_dict()}

    return router
