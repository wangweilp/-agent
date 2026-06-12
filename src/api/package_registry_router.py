"""Package Registry API — /api/packages 端点。

端点:
- POST   /api/packages                  — 创建 Package
- GET    /api/packages                  — 列出 Packages
- GET    /api/packages/{id}             — Package 详情
- PATCH  /api/packages/{id}             — 更新（仅 draft/rejected）
- DELETE /api/packages/{id}             — 删除（仅 draft/rejected）
- PATCH  /api/packages/{id}/status      — 状态迁移
- POST   /api/packages/{id}/review      — 提交审核
- POST   /api/packages/{id}/approve     — 审核通过
- POST   /api/packages/{id}/reject      — 审核拒绝
- POST   /api/packages/{id}/publish     — 发布

约束: metadata_only=True，不执行
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.middleware import require_auth, TokenPayload

logger = logging.getLogger(__name__)


class CreatePackageRequest(BaseModel):
    workspace_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = ""
    artifact_ids: list[str] = Field(default_factory=list)
    version: str = "0.1.0"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdatePackageRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    artifact_ids: list[str] | None = None
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


def create_package_router(package_service, usage_store=None) -> APIRouter:
    router = APIRouter(prefix="/api/packages", tags=["packages"])

    @router.post("", status_code=201)
    async def create_package(
        body: CreatePackageRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        from src.open_platform.package_registry import PackageValidationError
        try:
            pkg = package_service.create_package(
                workspace_id=body.workspace_id,
                name=body.name,
                description=body.description,
                artifact_ids=body.artifact_ids,
                version=body.version,
                tags=body.tags,
                metadata=body.metadata,
            )
        except PackageValidationError as e:
            raise HTTPException(status_code=422, detail={"message": str(e), "errors": e.errors})
        return {"package": pkg.to_dict()}

    @router.get("")
    async def list_packages(
        workspace_id: str = Query(default=""),
        status: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        pkgs = package_service.list(
            workspace_id=workspace_id, status=status,
            limit=limit, offset=offset)
        return {"packages": [p.to_dict() for p in pkgs], "total": len(pkgs)}

    @router.get("/{package_id}")
    async def get_package(
        package_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        pkg = package_service.get(package_id)
        if pkg is None:
            raise HTTPException(status_code=404, detail="Package 不存在")
        return {"package": pkg.to_dict()}

    @router.patch("/{package_id}")
    async def update_package(
        package_id: str,
        body: UpdatePackageRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        from src.open_platform.package_registry import (
            PackageNotFoundError, PackageStateError, PackageValidationError)
        pkg = package_service.get(package_id)
        if pkg is None:
            raise HTTPException(status_code=404, detail="Package 不存在")
        if body.name is not None: pkg.name = body.name
        if body.description is not None: pkg.description = body.description
        if body.artifact_ids is not None: pkg.artifact_ids = body.artifact_ids
        if body.version is not None: pkg.version = body.version
        if body.tags is not None: pkg.tags = body.tags
        if body.metadata is not None: pkg.metadata = {**pkg.metadata, **body.metadata}
        try:
            package_service._store.update(pkg)
        except PackageNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except PackageStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except PackageValidationError as e:
            raise HTTPException(status_code=422, detail={"message": str(e), "errors": e.errors})
        updated = package_service.get(package_id)
        return {"package": updated.to_dict() if updated else None}

    @router.delete("/{package_id}")
    async def delete_package(
        package_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        from src.open_platform.package_registry import (
            PackageNotFoundError, PackageStateError)
        try:
            package_service.delete(package_id)
        except PackageNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except PackageStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"success": True, "package_id": package_id}

    @router.patch("/{package_id}/status")
    async def update_status(
        package_id: str,
        body: StatusUpdateRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        from src.open_platform.package_registry import (
            PackageNotFoundError, PackageStateError)
        try:
            package_service._store.update_status(
                package_id, body.status,
                reviewed_by=body.reviewer_id or None,
                review_comment=body.review_comment or None,
                published_by=body.publisher_id or None)
        except PackageNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except PackageStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
        updated = package_service.get(package_id)
        return {"package": updated.to_dict() if updated else None}

    @router.post("/{package_id}/review")
    async def submit_review(
        package_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        from src.open_platform.package_registry import (
            PackageNotFoundError, PackageStateError)
        try:
            pkg = package_service.submit_review(package_id)
        except PackageNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except PackageStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"package": pkg.to_dict()}

    @router.post("/{package_id}/approve")
    async def approve(
        package_id: str,
        body: ReviewActionRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        from src.open_platform.package_registry import (
            PackageNotFoundError, PackageStateError)
        try:
            pkg = package_service.approve(package_id, body.reviewer_id, body.comment)
        except PackageNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except PackageStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"package": pkg.to_dict()}

    @router.post("/{package_id}/reject")
    async def reject(
        package_id: str,
        body: ReviewActionRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        from src.open_platform.package_registry import (
            PackageNotFoundError, PackageStateError)
        try:
            pkg = package_service.reject(package_id, body.reviewer_id, body.comment)
        except PackageNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except PackageStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"package": pkg.to_dict()}

    @router.post("/{package_id}/publish")
    async def publish(
        package_id: str,
        publisher_id: str = Query(..., min_length=1),
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        from src.open_platform.package_registry import (
            PackageNotFoundError, PackageStateError)
        try:
            pkg = package_service.publish(package_id, publisher_id)
        except PackageNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except PackageStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"package": pkg.to_dict()}

    return router
