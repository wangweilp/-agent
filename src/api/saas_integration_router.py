"""SaaS Integration API — 租户 Dashboard + 配额管理 + 跨 workspace 隔离验证。

端点：
  GET    /api/tenant/dashboard        — 租户总览面板
  GET    /api/tenant/quotas           — 所有资源的配额状态
  POST   /api/tenant/quotas/check     — 单项资源配额检查
  GET    /api/tenant/artifacts        — 租户下所有 Artifacts
  GET    /api/tenant/packages         — 租户下所有 Packages
  GET    /api/tenant/workflows        — 租户下所有 Workflows
  GET    /api/tenant/agent-modules    — 租户下所有 AgentModules
  GET    /api/tenant/subscriptions    — 租户 Marketplace 订阅

约束：metadata_only，不执行。所有查询按 workspace_id 隔离。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.middleware import require_auth, TokenPayload

logger = logging.getLogger(__name__)


class QuotaCheckRequest(BaseModel):
    resource: str = Field(..., min_length=1)


def create_saas_integration_router(
    saas_service,
    artifact_service=None,
    package_service=None,
    workflow_service=None,
    agent_module_service=None,
    marketplace_service=None,
) -> APIRouter:

    router = APIRouter(prefix="/api/tenant", tags=["tenant-saas"])

    # ── Dashboard ──

    @router.get("/dashboard")
    async def get_dashboard(payload: TokenPayload = Depends(require_auth)):
        """租户总览面板 — 所有子系统的状态计数 + 配额。"""
        ws = payload.workspace_id
        dashboard = saas_service.get_dashboard(ws)
        return dashboard.to_dict()

    # ── Quotas ──

    @router.get("/quotas")
    async def get_quotas(payload: TokenPayload = Depends(require_auth)):
        """获取所有资源配额状态。"""
        quotas = saas_service.get_all_quotas(payload.workspace_id)
        return {"workspace_id": payload.workspace_id,
                "quotas": {k: v.to_dict() for k, v in quotas.items()}}

    @router.post("/quotas/check")
    async def check_quota(body: QuotaCheckRequest,
                          payload: TokenPayload = Depends(require_auth)):
        """单项配额检查。"""
        result = saas_service.check_quota(payload.workspace_id, body.resource)
        return result.to_dict()

    # ── Tenant-scoped Lists ──

    @router.get("/artifacts")
    async def list_artifacts(
        status: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        payload: TokenPayload = Depends(require_auth),
    ):
        """当前租户下所有 Artifacts（跨 agent 聚合）。"""
        if not artifact_service:
            raise HTTPException(status_code=501, detail="Artifact service not available")
        artifacts = artifact_service.list(
            workspace_id=payload.workspace_id, status=status,
            limit=limit, offset=offset)
        return {"artifacts": [a.to_dict() for a in artifacts], "total": len(artifacts)}

    @router.get("/packages")
    async def list_packages(
        status: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        payload: TokenPayload = Depends(require_auth),
    ):
        """当前租户下所有 Packages。"""
        if not package_service:
            raise HTTPException(status_code=501, detail="Package service not available")
        pkgs = package_service.list(
            workspace_id=payload.workspace_id, status=status,
            limit=limit, offset=offset)
        return {"packages": [p.to_dict() for p in pkgs], "total": len(pkgs)}

    @router.get("/workflows")
    async def list_workflows(
        status: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        payload: TokenPayload = Depends(require_auth),
    ):
        """当前租户下所有 Workflows。"""
        if not workflow_service:
            raise HTTPException(status_code=501, detail="Workflow service not available")
        wfs = workflow_service.list(
            workspace_id=payload.workspace_id, status=status,
            limit=limit, offset=offset)
        return {"workflows": [w.to_dict() for w in wfs], "total": len(wfs)}

    @router.get("/agent-modules")
    async def list_agent_modules(
        status: str = Query(default=""),
        category: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        payload: TokenPayload = Depends(require_auth),
    ):
        """当前租户下所有 AgentModules。"""
        if not agent_module_service:
            raise HTTPException(status_code=501, detail="AgentModule service not available")
        ms = agent_module_service.list(
            workspace_id=payload.workspace_id, status=status,
            category=category, limit=limit, offset=offset)
        return {"agent_modules": [m.to_dict() for m in ms], "total": len(ms)}

    @router.get("/subscriptions")
    async def list_subscriptions(payload: TokenPayload = Depends(require_auth)):
        """当前租户的 Marketplace 订阅列表。"""
        if not marketplace_service:
            raise HTTPException(status_code=501, detail="Marketplace service not available")
        subs = marketplace_service.list_subscriptions(payload.workspace_id)
        return {"subscriptions": [s.to_dict() for s in subs], "total": len(subs)}

    return router
