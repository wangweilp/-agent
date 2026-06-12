"""Marketplace Analytics API — Recommendations / Rankings / Platform Metrics。

端点:
  GET /api/marketplace/recommendations   — 个性化推荐
  GET /api/marketplace/rankings?category= — 排行榜
  GET /api/marketplace/analytics         — 平台分析指标
  GET /api/marketplace/top-rated         — 最高评分
  GET /api/marketplace/most-installed    — 最多安装
  GET /api/marketplace/fastest-growing   — 增长最快
  GET /api/marketplace/trending          — 趋势榜

约束: metadata_only，不执行 runtime/container。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.api.middleware import require_auth, TokenPayload

logger = logging.getLogger(__name__)


class AnalyticsEventRequest(BaseModel):
    event_type: str = Field(..., min_length=1)
    dimension: str = ""
    agent_module_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


def create_marketplace_analytics_router(analytics_service) -> APIRouter:
    router = APIRouter(prefix="/api/marketplace", tags=["marketplace-analytics"])

    @router.get("/recommendations")
    async def get_recommendations(
        limit: int = Query(default=10, ge=1, le=50),
        refresh: bool = Query(default=False),
        payload: TokenPayload = Depends(require_auth),
    ):
        ws = payload.workspace_id
        if refresh:
            recs = analytics_service.generate_recommendations(ws, limit)
        else:
            recs = analytics_service.get_recommendations(ws, limit)
        return {"workspace_id": ws, "recommendations": recs, "total": len(recs)}

    @router.get("/rankings")
    async def get_rankings(
        category: str = Query(default="top_rated"),
        limit: int = Query(default=20, ge=1, le=100),
        refresh: bool = Query(default=False),
        payload: TokenPayload = Depends(require_auth),
    ):
        if refresh:
            ranks = analytics_service.generate_rankings(category, limit)
        else:
            ranks = analytics_service.get_rankings(category, limit)
        return {"category": category, "rankings": ranks, "total": len(ranks)}

    @router.get("/analytics")
    async def get_analytics(
        refresh: bool = Query(default=False),
        payload: TokenPayload = Depends(require_auth),
    ):
        if refresh:
            metrics = analytics_service.calculate_platform_metrics()
        else:
            metrics = analytics_service.get_platform_metrics()
        return metrics

    @router.get("/top-rated")
    async def get_top_rated(
        limit: int = Query(default=10, ge=1, le=50),
        payload: TokenPayload = Depends(require_auth),
    ):
        ranks = analytics_service.get_top_rated_agents(limit)
        return {"category": "top_rated", "rankings": ranks, "total": len(ranks)}

    @router.get("/most-installed")
    async def get_most_installed(
        limit: int = Query(default=10, ge=1, le=50),
        payload: TokenPayload = Depends(require_auth),
    ):
        ranks = analytics_service.get_most_installed_agents(limit)
        return {"category": "most_installed", "rankings": ranks, "total": len(ranks)}

    @router.get("/fastest-growing")
    async def get_fastest_growing(
        limit: int = Query(default=10, ge=1, le=50),
        payload: TokenPayload = Depends(require_auth),
    ):
        ranks = analytics_service.get_fastest_growing_agents(limit)
        return {"category": "fastest_growing", "rankings": ranks, "total": len(ranks)}

    @router.get("/trending")
    async def get_trending(
        limit: int = Query(default=10, ge=1, le=50),
        payload: TokenPayload = Depends(require_auth),
    ):
        ranks = analytics_service.get_trending_agents(limit)
        return {"category": "trending", "rankings": ranks, "total": len(ranks)}

    @router.post("/analytics/event")
    async def record_event(body: AnalyticsEventRequest,
                           payload: TokenPayload = Depends(require_auth)):
        analytics_service.record_analytics_event(
            body.event_type, dimension=body.dimension,
            agent_module_id=body.agent_module_id,
            workspace_id=payload.workspace_id, payload=body.payload)
        return {"success": True}

    return router
