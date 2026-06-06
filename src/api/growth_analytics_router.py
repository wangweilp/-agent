"""Growth Analytics Router — 运营数据分析 API。

端点:
    GET /analytics/metrics          — 核心指标（MRR/ARR/转化率/留存率）
    GET /analytics/memory-trend     — Memory 使用趋势
    GET /analytics/resource-usage   — Embedding/LLM 消耗趋势
    GET /analytics/import-channels  — 导入渠道分析
    GET /analytics/retention        — 留存队列分析
    GET /analytics/realtime         — 实时指标
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.middleware import require_auth, require_manage
from src.api.saas_schemas import (
    AnalyticsMetricsResponse,
    ImportChannelResponse,
    MemoryTrendResponse,
    RealtimeMetricsResponse,
    ResourceUsageTrendResponse,
    RetentionAnalysisResponse,
)
from src.core.usage import UsageResource


def create_growth_analytics_router(usage_store, subscription_store) -> APIRouter:
    router = APIRouter(prefix="/analytics", tags=["Growth Analytics"])

    # ── 1. GET /analytics/metrics ───────────────────────────────────

    @router.get("/metrics", response_model=AnalyticsMetricsResponse)
    async def get_metrics(token=Depends(require_auth)):
        """核心指标：MRR/ARR/转化率/留存率/流失率。"""
        try:
            stats = usage_store.get_platform_stats()
            return stats.as_dict()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")

    # ── 2. GET /analytics/memory-trend ──────────────────────────────

    @router.get("/memory-trend", response_model=MemoryTrendResponse)
    async def get_memory_trend(
        period: str = Query(default="daily", description="daily | weekly | monthly"),
        days: int = Query(default=30, ge=1, le=365),
        token=Depends(require_auth),
    ):
        """Memory 使用趋势（日/周/月）。"""
        try:
            if period == "daily":
                trend = usage_store.get_resource_usage_trend(
                    token.workspace_id, UsageResource.MEMORY.value, days=days,
                )
            elif period == "weekly":
                # 聚合为周
                daily = usage_store.get_resource_usage_trend(
                    token.workspace_id, UsageResource.MEMORY.value, days=days,
                )
                trend = _aggregate_weekly(daily)
            elif period == "monthly":
                daily = usage_store.get_resource_usage_trend(
                    token.workspace_id, UsageResource.MEMORY.value, days=days,
                )
                trend = _aggregate_monthly(daily)
            else:
                raise HTTPException(status_code=400, detail=f"Invalid period: '{period}'")

            return {"tenant_id": token.workspace_id, "period": period, "trend": trend}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get memory trend: {str(e)}")

    # ── 3. GET /analytics/resource-usage ────────────────────────────

    @router.get("/resource-usage", response_model=ResourceUsageTrendResponse)
    async def get_resource_usage(
        resource: str = Query(default="llm_call", description="llm_call | embedding | search | coach"),
        days: int = Query(default=30, ge=1, le=365),
        token=Depends(require_auth),
    ):
        """Embedding/LLM 消耗趋势。"""
        try:
            UsageResource(resource)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid resource: '{resource}'. Valid: {[r.value for r in UsageResource]}",
            )

        try:
            trend = usage_store.get_resource_usage_trend(
                token.workspace_id, resource, days=days,
            )
            return {"tenant_id": token.workspace_id, "resource": resource, "days": days, "trend": trend}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get resource usage: {str(e)}")

    # ── 4. GET /analytics/import-channels ───────────────────────────

    @router.get("/import-channels", response_model=ImportChannelResponse)
    async def get_import_channels(
        days: int = Query(default=30, ge=1, le=365),
        token=Depends(require_auth),
    ):
        """导入渠道分析。"""
        try:
            breakdown = usage_store.get_import_channel_breakdown(token.workspace_id, days=days)
            return {
                "tenant_id": token.workspace_id,
                "channels": breakdown.get("channels", {}),
                "total_imports": breakdown.get("total_imports", 0),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get import channels: {str(e)}")

    # ── 5. GET /analytics/retention ─────────────────────────────────

    @router.get("/retention", response_model=RetentionAnalysisResponse)
    async def get_retention(
        months: int = Query(default=6, ge=1, le=24),
        token=Depends(require_auth),
    ):
        """留存队列分析。"""
        try:
            cohort = usage_store.get_retention_analysis(token.workspace_id, months=months)
            return {"tenant_id": token.workspace_id, "months": months, "cohort": cohort}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get retention: {str(e)}")

    # ── 6. GET /analytics/realtime ──────────────────────────────────

    @router.get("/realtime", response_model=RealtimeMetricsResponse)
    async def get_realtime(token=Depends(require_auth)):
        """实时指标：当前队列深度、DLQ 积压、今日事件数。"""
        try:
            metrics = usage_store.get_realtime_metrics(token.workspace_id)
            return metrics
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get realtime metrics: {str(e)}")

    return router


def _aggregate_weekly(daily: list[dict]) -> list[dict]:
    """将日趋势聚合为周趋势。"""
    from collections import defaultdict
    from datetime import datetime

    weeks: dict[str, dict] = defaultdict(lambda: {"count": 0, "cost": 0})
    for d in daily:
        dt = datetime.fromisoformat(d["date"])
        iso_year, iso_week, _ = dt.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        weeks[week_key]["count"] += d.get("count", 0)
        weeks[week_key]["cost"] += d.get("cost", 0)

    return [
        {"date": wk, "count": v["count"], "cost": v["cost"]}
        for wk, v in sorted(weeks.items())
    ]


def _aggregate_monthly(daily: list[dict]) -> list[dict]:
    """将日趋势聚合为月趋势。"""
    from collections import defaultdict

    months: dict[str, dict] = defaultdict(lambda: {"count": 0, "cost": 0})
    for d in daily:
        month_key = d["date"][:7]  # "2026-06"
        months[month_key]["count"] += d.get("count", 0)
        months[month_key]["cost"] += d.get("cost", 0)

    return [
        {"date": mk, "count": v["count"], "cost": v["cost"]}
        for mk, v in sorted(months.items())
    ]
