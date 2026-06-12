"""Artifact Sandbox API — /api/artifacts 端点。

Artifact Sandbox 约束：
- 所有 artifact execution_allowed=False
- 所有 artifact runtime_enabled=False
- 所有 artifact metadata_only=True
- 无 subprocess/docker/container/microVM

端点:
- POST   /api/artifacts                     — 创建 artifact（Agent 生成）
- GET    /api/artifacts                     — 列出 artifacts
- GET    /api/artifacts/{id}                — Artifact 详情
- PATCH  /api/artifacts/{id}                — 更新 artifact（仅 draft/rejected）
- DELETE /api/artifacts/{id}                — 删除 artifact（仅 draft/rejected）
- POST   /api/artifacts/{id}/review         — 提交审核 (draft → review)
- POST   /api/artifacts/{id}/approve        — 审核通过 (review → approved)
- POST   /api/artifacts/{id}/reject         — 审核拒绝 (review → rejected)
- POST   /api/artifacts/{id}/publish        — 发布 (approved → published)

权限: require_auth
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.middleware import require_auth, TokenPayload

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# Request Models
# ═══════════════════════════════════════════


class CreateArtifactRequest(BaseModel):
    workspace_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    artifact_type: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = ""
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateArtifactRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    content: str | None = None
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


# ═══════════════════════════════════════════
# Router Factory
# ═══════════════════════════════════════════


def create_artifact_router(
    artifact_service,
    usage_store=None,
) -> APIRouter:
    router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])

    # ── Create ──

    @router.post("", status_code=201)
    async def create_artifact(
        body: CreateArtifactRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """Agent 创建 artifact — 永远进入 draft 状态。

        安全约束：
        - execution_allowed 强制 False
        - runtime_enabled 强制 False
        - metadata_only 强制 True
        """
        from src.open_platform.artifact_service import ArtifactValidationError

        try:
            artifact = artifact_service.create_artifact(
                workspace_id=body.workspace_id,
                agent_id=body.agent_id,
                artifact_type=body.artifact_type,
                title=body.title,
                description=body.description,
                content=body.content,
                tags=body.tags,
                metadata=body.metadata,
            )
        except ArtifactValidationError as e:
            raise HTTPException(status_code=422, detail={"message": str(e), "errors": e.errors})

        logger.info("artifact_api_created", extra={"artifact_id": artifact.id})
        return {"artifact": artifact.to_dict()}

    # ── List ──

    @router.get("")
    async def list_artifacts(
        workspace_id: str = Query(default=""),
        agent_id: str = Query(default=""),
        artifact_type: str = Query(default=""),
        status: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """列出 artifacts，支持多条件过滤。"""
        artifacts = artifact_service.list(
            workspace_id=workspace_id,
            agent_id=agent_id,
            artifact_type=artifact_type,
            status=status,
            limit=limit,
            offset=offset,
        )
        return {
            "artifacts": [a.to_dict() for a in artifacts],
            "total": len(artifacts),
        }

    # ── Get ──

    @router.get("/{artifact_id}")
    async def get_artifact(
        artifact_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """获取单个 artifact 详情。"""
        artifact = artifact_service.get(artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="Artifact 不存在")
        return {"artifact": artifact.to_dict()}

    # ── Update ──

    @router.patch("/{artifact_id}")
    async def update_artifact(
        artifact_id: str,
        body: UpdateArtifactRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """更新 artifact（仅 draft/rejected）。

        不允许通过此端点改 status——状态迁移走专用端点。
        """
        from src.open_platform.artifact import (
            ArtifactNotFoundError, ArtifactStateError, ArtifactValidationError,
        )

        artifact = artifact_service.get(artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="Artifact 不存在")

        if body.title is not None:
            artifact.title = body.title
        if body.description is not None:
            artifact.description = body.description
        if body.content is not None:
            artifact.content = body.content
        if body.tags is not None:
            artifact.tags = body.tags
        if body.metadata is not None:
            artifact.metadata = {**artifact.metadata, **body.metadata}

        try:
            artifact_service._store.update(artifact)
        except ArtifactNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ArtifactStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except ArtifactValidationError as e:
            raise HTTPException(status_code=422, detail={"message": str(e), "errors": e.errors})

        updated = artifact_service.get(artifact_id)
        return {"artifact": updated.to_dict() if updated else None}

    # ── Delete ──

    @router.delete("/{artifact_id}")
    async def delete_artifact(
        artifact_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """删除 artifact（仅 draft/rejected）。"""
        from src.open_platform.artifact import (
            ArtifactNotFoundError, ArtifactStateError,
        )

        try:
            artifact_service.delete(artifact_id)
        except ArtifactNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ArtifactStateError as e:
            raise HTTPException(status_code=409, detail=str(e))

        return {"success": True, "artifact_id": artifact_id}

    # ── Status Update (通用) ──

    @router.patch("/{artifact_id}/status")
    async def update_artifact_status(
        artifact_id: str,
        body: StatusUpdateRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """通用状态更新端点。"""
        from src.open_platform.artifact import (
            ArtifactNotFoundError, ArtifactStateError,
        )

        try:
            artifact_service._store.update_status(
                artifact_id,
                body.status,
                reviewed_by=body.reviewer_id or None,
                review_comment=body.review_comment or None,
                published_by=body.publisher_id or None,
            )
        except ArtifactNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ArtifactStateError as e:
            raise HTTPException(status_code=409, detail=str(e))

        updated = artifact_service.get(artifact_id)
        return {"artifact": updated.to_dict() if updated else None}

    # ── Review Pipeline ──

    @router.post("/{artifact_id}/review")
    async def submit_review(
        artifact_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """提交审核 — draft → review。"""
        from src.open_platform.artifact import (
            ArtifactNotFoundError, ArtifactStateError,
        )

        try:
            artifact = artifact_service.submit_review(artifact_id)
        except ArtifactNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ArtifactStateError as e:
            raise HTTPException(status_code=409, detail=str(e))

        return {"artifact": artifact.to_dict()}

    @router.post("/{artifact_id}/approve")
    async def approve_artifact(
        artifact_id: str,
        body: ReviewActionRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """审核通过 — review → approved。"""
        from src.open_platform.artifact import (
            ArtifactNotFoundError, ArtifactStateError,
        )

        try:
            artifact = artifact_service.approve(
                artifact_id,
                reviewer_id=body.reviewer_id,
                comment=body.comment,
            )
        except ArtifactNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ArtifactStateError as e:
            raise HTTPException(status_code=409, detail=str(e))

        return {"artifact": artifact.to_dict()}

    @router.post("/{artifact_id}/reject")
    async def reject_artifact(
        artifact_id: str,
        body: ReviewActionRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """审核拒绝 — review → rejected。"""
        from src.open_platform.artifact import (
            ArtifactNotFoundError, ArtifactStateError,
        )

        try:
            artifact = artifact_service.reject(
                artifact_id,
                reviewer_id=body.reviewer_id,
                comment=body.comment,
            )
        except ArtifactNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ArtifactStateError as e:
            raise HTTPException(status_code=409, detail=str(e))

        return {"artifact": artifact.to_dict()}

    @router.post("/{artifact_id}/publish")
    async def publish_artifact(
        artifact_id: str,
        publisher_id: str = Query(..., min_length=1),
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """发布 — approved → published。

        published 是终态。execution_allowed 仍然为 False。
        """
        from src.open_platform.artifact import (
            ArtifactNotFoundError, ArtifactStateError,
        )

        try:
            artifact = artifact_service.publish(artifact_id, publisher_id)
        except ArtifactNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ArtifactStateError as e:
            raise HTTPException(status_code=409, detail=str(e))

        return {"artifact": artifact.to_dict()}

    return router
