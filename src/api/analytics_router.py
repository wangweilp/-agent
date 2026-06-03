"""Analytics Router — 工作区分析 API。

端点:
    GET /workspace/{id}/analytics           — 完整工作区分析
    GET /workspace/{id}/analytics/growth    — 增长趋势 (参数: days)
    GET /workspace/{id}/analytics/contributors — 贡献排行 (参数: days)
    GET /workspace/{id}/analytics/media     — 媒体类型分布
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from src.adapters.collab_store import CollaborationService
from src.api.middleware import require_auth
from src.core.auth import TokenPayload

logger = logging.getLogger(__name__)


def create_analytics_router(
    collab_service: CollaborationService,
    agent=None,
) -> APIRouter:
    router = APIRouter(tags=["analytics"])

    @router.get("/workspace/{id}/analytics")
    async def workspace_analytics(id: str, payload: TokenPayload = Depends(require_auth)):
        """完整工作区分析 — 聚合所有指标。"""
        mem_store = agent._memory_store if agent is not None else None
        analytics = collab_service.get_workspace_analytics(id, mem_store)
        return {
            "member_count": analytics.member_count,
            "memory_by_type": analytics.memory_by_type,
            "memory_growth": analytics.memory_growth,
            "top_entities": analytics.top_entities,
            "top_contributors": analytics.top_contributors,
            "action_completion_rate": analytics.action_completion_rate,
            "media_breakdown": analytics.media_breakdown,
            "weekly_active_users": analytics.weekly_active_users,
        }

    @router.get("/workspace/{id}/analytics/growth")
    async def analytics_growth(
        id: str,
        days: int = Query(default=30, ge=1, le=365),
        payload: TokenPayload = Depends(require_auth),
    ):
        """增长趋势 — 每日新增记忆计数。"""
        mem_store = agent._memory_store if agent is not None else None
        return collab_service.get_analytics_growth(id, mem_store, days)

    @router.get("/workspace/{id}/analytics/contributors")
    async def analytics_contributors(
        id: str,
        days: int = Query(default=30, ge=1, le=365),
        payload: TokenPayload = Depends(require_auth),
    ):
        """贡献排行 — 成员在指定天数内的操作计数。"""
        return collab_service.get_analytics_contributors(id, days)

    @router.get("/workspace/{id}/analytics/media")
    async def analytics_media(id: str, payload: TokenPayload = Depends(require_auth)):
        """媒体类型分布 — 文本/图片/音频/视频 占比。"""
        mem_store = agent._memory_store if agent is not None else None
        return collab_service.get_analytics_media(id, mem_store)

    return router
