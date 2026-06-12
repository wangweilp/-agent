"""Agent Module + Marketplace API。

端点:
  Agent Publishing:
    POST   /api/agents                    — 创建 AgentModule
    GET    /api/agents                    — 列出
    GET    /api/agents/{id}               — 详情
    PATCH  /api/agents/{id}               — 更新 (draft/rejected)
    DELETE /api/agents/{id}               — 删除 (draft/rejected)
    PATCH  /api/agents/{id}/status        — 状态迁移
    POST   /api/agents/{id}/review        — 提交审核
    POST   /api/agents/{id}/approve       — 审核通过
    POST   /api/agents/{id}/reject        — 审核拒绝
    POST   /api/agents/{id}/publish       — 发布

  Marketplace:
    GET    /api/marketplace               — 搜索/浏览已发布模块
    GET    /api/marketplace/{id}          — 模块详情
    POST   /api/marketplace/subscribe     — 订阅
    DELETE /api/marketplace/subscribe     — 取消订阅
    GET    /api/marketplace/subscriptions — 我的订阅

约束: metadata_only=True，不可执行
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.middleware import require_auth, TokenPayload

logger = logging.getLogger(__name__)


# ── Request Models ──

class CreateAgentModuleRequest(BaseModel):
    workspace_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = ""
    workflow_ids: list[str] = Field(default_factory=list)
    version: str = "0.1.0"
    author: str = ""
    category: str = ""
    icon_url: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateAgentModuleRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    workflow_ids: list[str] | None = None
    version: str | None = None
    author: str | None = None
    category: str | None = None
    icon_url: str | None = None
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


class SubscribeRequest(BaseModel):
    workspace_id: str = Field(..., min_length=1)
    agent_module_id: str = Field(..., min_length=1)


class UnsubscribeRequest(BaseModel):
    workspace_id: str = Field(..., min_length=1)
    agent_module_id: str = Field(..., min_length=1)


# ── Agent Publishing Router ──

def create_agent_publishing_router(module_service, marketplace_service=None, usage_store=None) -> APIRouter:
    router = APIRouter(prefix="/api/agents", tags=["agents"])

    @router.post("", status_code=201)
    async def create(body: CreateAgentModuleRequest, payload: TokenPayload = Depends(require_auth)):
        from src.open_platform.agent_module import AgentModuleValidationError
        try:
            m = module_service.create_module(
                workspace_id=body.workspace_id, name=body.name,
                description=body.description, workflow_ids=body.workflow_ids,
                version=body.version, author=body.author, category=body.category,
                icon_url=body.icon_url, tags=body.tags, metadata=body.metadata,
            )
        except AgentModuleValidationError as e:
            raise HTTPException(status_code=422, detail={"message": str(e), "errors": e.errors})
        return {"agent_module": m.to_dict()}

    @router.get("")
    async def list_modules(
        workspace_id: str = Query(default=""), status: str = Query(default=""),
        category: str = Query(default=""), limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0), payload: TokenPayload = Depends(require_auth),
    ):
        ms = module_service.list(workspace_id=workspace_id, status=status,
                                  category=category, limit=limit, offset=offset)
        return {"agent_modules": [m.to_dict() for m in ms], "total": len(ms)}

    @router.get("/{module_id}")
    async def get(module_id: str, payload: TokenPayload = Depends(require_auth)):
        m = module_service.get(module_id)
        if m is None: raise HTTPException(status_code=404, detail="AgentModule 不存在")
        return {"agent_module": m.to_dict()}

    @router.patch("/{module_id}")
    async def update(module_id: str, body: UpdateAgentModuleRequest,
                      payload: TokenPayload = Depends(require_auth)):
        from src.open_platform.agent_module import (
            AgentModuleNotFoundError, AgentModuleStateError, AgentModuleValidationError)
        m = module_service.get(module_id)
        if m is None: raise HTTPException(status_code=404, detail="AgentModule 不存在")
        if body.name is not None: m.name = body.name
        if body.description is not None: m.description = body.description
        if body.workflow_ids is not None: m.workflow_ids = body.workflow_ids
        if body.version is not None: m.version = body.version
        if body.author is not None: m.author = body.author
        if body.category is not None: m.category = body.category
        if body.icon_url is not None: m.icon_url = body.icon_url
        if body.tags is not None: m.tags = body.tags
        if body.metadata is not None: m.metadata = {**m.metadata, **body.metadata}
        try: module_service._store.update(m)
        except AgentModuleNotFoundError as e: raise HTTPException(status_code=404, detail=str(e))
        except AgentModuleStateError as e: raise HTTPException(status_code=409, detail=str(e))
        except AgentModuleValidationError as e: raise HTTPException(status_code=422, detail={"message": str(e), "errors": e.errors})
        updated = module_service.get(module_id)
        return {"agent_module": updated.to_dict() if updated else None}

    @router.delete("/{module_id}")
    async def delete(module_id: str, payload: TokenPayload = Depends(require_auth)):
        from src.open_platform.agent_module import (
            AgentModuleNotFoundError, AgentModuleStateError)
        try: module_service.delete(module_id)
        except AgentModuleNotFoundError as e: raise HTTPException(status_code=404, detail=str(e))
        except AgentModuleStateError as e: raise HTTPException(status_code=409, detail=str(e))
        return {"success": True, "module_id": module_id}

    @router.patch("/{module_id}/status")
    async def update_status(module_id: str, body: StatusUpdateRequest,
                             payload: TokenPayload = Depends(require_auth)):
        from src.open_platform.agent_module import (
            AgentModuleNotFoundError, AgentModuleStateError)
        try:
            module_service._store.update_status(
                module_id, body.status, reviewed_by=body.reviewer_id or None,
                review_comment=body.review_comment or None, published_by=body.publisher_id or None)
        except AgentModuleNotFoundError as e: raise HTTPException(status_code=404, detail=str(e))
        except AgentModuleStateError as e: raise HTTPException(status_code=409, detail=str(e))
        updated = module_service.get(module_id)
        return {"agent_module": updated.to_dict() if updated else None}

    @router.post("/{module_id}/review")
    async def submit_review(module_id: str, payload: TokenPayload = Depends(require_auth)):
        from src.open_platform.agent_module import (AgentModuleNotFoundError, AgentModuleStateError)
        try: m = module_service.submit_review(module_id)
        except AgentModuleNotFoundError as e: raise HTTPException(status_code=404, detail=str(e))
        except AgentModuleStateError as e: raise HTTPException(status_code=409, detail=str(e))
        return {"agent_module": m.to_dict()}

    @router.post("/{module_id}/approve")
    async def approve(module_id: str, body: ReviewActionRequest,
                       payload: TokenPayload = Depends(require_auth)):
        from src.open_platform.agent_module import (AgentModuleNotFoundError, AgentModuleStateError)
        try: m = module_service.approve(module_id, body.reviewer_id, body.comment)
        except AgentModuleNotFoundError as e: raise HTTPException(status_code=404, detail=str(e))
        except AgentModuleStateError as e: raise HTTPException(status_code=409, detail=str(e))
        return {"agent_module": m.to_dict()}

    @router.post("/{module_id}/reject")
    async def reject(module_id: str, body: ReviewActionRequest,
                      payload: TokenPayload = Depends(require_auth)):
        from src.open_platform.agent_module import (AgentModuleNotFoundError, AgentModuleStateError)
        try: m = module_service.reject(module_id, body.reviewer_id, body.comment)
        except AgentModuleNotFoundError as e: raise HTTPException(status_code=404, detail=str(e))
        except AgentModuleStateError as e: raise HTTPException(status_code=409, detail=str(e))
        return {"agent_module": m.to_dict()}

    @router.post("/{module_id}/publish")
    async def publish(module_id: str, publisher_id: str = Query(..., min_length=1),
                       payload: TokenPayload = Depends(require_auth)):
        from src.open_platform.agent_module import (AgentModuleNotFoundError, AgentModuleStateError)
        try: m = module_service.publish(module_id, publisher_id)
        except AgentModuleNotFoundError as e: raise HTTPException(status_code=404, detail=str(e))
        except AgentModuleStateError as e: raise HTTPException(status_code=409, detail=str(e))
        return {"agent_module": m.to_dict()}

    return router


# ── Marketplace Router ──

def create_marketplace_router(marketplace_service, usage_store=None) -> APIRouter:
    router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])

    @router.get("")
    async def search(
        q: str = Query(default=""), category: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        payload: TokenPayload = Depends(require_auth),
    ):
        if q:
            results = marketplace_service.search(q, category=category, limit=limit)
        else:
            results = marketplace_service.list_published(category=category, limit=limit, offset=offset)
        return {"agent_modules": [m.to_dict() for m in results], "total": len(results)}

    @router.get("/{module_id}")
    async def detail(module_id: str, payload: TokenPayload = Depends(require_auth)):
        m = marketplace_service._store.get(module_id)
        if m is None: raise HTTPException(status_code=404, detail="AgentModule 不存在")
        if not m.is_published():
            raise HTTPException(status_code=404, detail="该模块未发布")
        return {"agent_module": m.to_dict()}

    @router.post("/subscribe", status_code=201)
    async def subscribe(body: SubscribeRequest, payload: TokenPayload = Depends(require_auth)):
        from src.open_platform.agent_module import (
            AgentModuleNotFoundError, AgentModuleStateError, SubscriptionAlreadyExistsError)
        try: sub = marketplace_service.subscribe(body.workspace_id, body.agent_module_id)
        except AgentModuleNotFoundError as e: raise HTTPException(status_code=404, detail=str(e))
        except AgentModuleStateError as e: raise HTTPException(status_code=409, detail=str(e))
        except SubscriptionAlreadyExistsError as e: raise HTTPException(status_code=409, detail=str(e))
        return {"subscription": sub.to_dict()}

    @router.delete("/subscribe")
    async def unsubscribe(body: UnsubscribeRequest, payload: TokenPayload = Depends(require_auth)):
        from src.open_platform.agent_module import SubscriptionNotFoundError
        try: marketplace_service.unsubscribe(body.workspace_id, body.agent_module_id)
        except SubscriptionNotFoundError as e: raise HTTPException(status_code=404, detail=str(e))
        return {"success": True}

    @router.get("/subscriptions/list")
    async def list_subscriptions(
        workspace_id: str = Query(..., min_length=1),
        payload: TokenPayload = Depends(require_auth),
    ):
        subs = marketplace_service.list_subscriptions(workspace_id)
        return {"subscriptions": [s.to_dict() for s in subs], "total": len(subs)}

    return router
