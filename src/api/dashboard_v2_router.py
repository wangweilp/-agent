"""Dashboard V2 Router — P0 指标 API。

端点:
    GET /dashboard/v2/overview            — 概览 KPI 墙
    GET /dashboard/v2/growth              — 增长指标
    GET /dashboard/v2/agent-performance   — Agent 性能
    GET /dashboard/v2/memory-health       — Memory 健康

所有端点：
- 使用 require_auth 认证
- response_model 完整声明
- 通过 app.openapi() 验证
"""
from fastapi import APIRouter, Depends, Query

from src.api.dashboard_v2_schemas import (
    AgentPerformanceResponse,
    GrowthResponse,
    MemoryHealthResponse,
    OverviewResponse,
)
from src.api.middleware import TokenPayload, require_auth
from src.core.dashboard_v2_service import DashboardV2Service


def create_dashboard_v2_router(service: DashboardV2Service) -> APIRouter:
    """创建 Dashboard V2 路由。

    Args:
        service: DashboardV2Service 实例（已注入 AnalyticsRepository）
    """
    router = APIRouter(prefix="/dashboard/v2", tags=["Dashboard V2"])

    # ── GET /dashboard/v2/overview ───────────────────────

    @router.get("/overview", response_model=OverviewResponse)
    async def overview(payload: TokenPayload = Depends(require_auth)) -> OverviewResponse:
        """概览 KPI 墙 — 商业 + 增长 + Agent + Memory + 成本 核心指标。"""
        return service.get_overview(payload.workspace_id)

    # ── GET /dashboard/v2/growth ─────────────────────────

    @router.get("/growth", response_model=GrowthResponse)
    async def growth(
        days: int = Query(default=30, ge=1, le=365, description="时间范围（天）"),
        payload: TokenPayload = Depends(require_auth),
    ) -> GrowthResponse:
        """增长指标 — DAU/WAU/MAU 趋势 + 留存队列 + 转化漏斗 + 激活率。"""
        return service.get_growth(payload.workspace_id, days=days)

    # ── GET /dashboard/v2/agent-performance ─────────────

    @router.get("/agent-performance", response_model=AgentPerformanceResponse)
    async def agent_performance(
        days: int = Query(default=7, ge=1, le=90, description="时间范围（天）"),
        payload: TokenPayload = Depends(require_auth),
    ) -> AgentPerformanceResponse:
        """Agent 性能指标 — 调用量 + 成功率 + 延迟 + Token。"""
        return service.get_agent_performance(payload.workspace_id, days=days)

    # ── GET /dashboard/v2/memory-health ─────────────────

    @router.get("/memory-health", response_model=MemoryHealthResponse)
    async def memory_health(
        days: int = Query(default=30, ge=1, le=365, description="时间范围（天）"),
        payload: TokenPayload = Depends(require_auth),
    ) -> MemoryHealthResponse:
        """Memory 健康指标 — 增长 + 命中率 + 类型分布。"""
        return service.get_memory_health(payload.workspace_id, days=days)

    return router
