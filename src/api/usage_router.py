"""
Usage router — usage tracking, monthly stats, cost analytics,
user profiles, admin platform analytics.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.core.usage import UsageEvent, UsageResource, UsageUnit, UsageStats
from src.adapters.usage_store import UsageStoreAdapter
from src.api.middleware import require_auth, require_manage
from src.api.saas_schemas import (
    DailyUsageItem,
    PlatformStatsResponse,
    RecordUsageRequest,
    UsageStatsResponse,
    UserProfileResponse,
)


# ── Pydantic models (not in saas_schemas) ──────────────────────────────────


class CostStatsResponse(BaseModel):
    tenant_id: str
    month: str
    llm_cost_cents: int = 0
    embedding_cost_cents: int = 0
    storage_cost_cents: int = 0
    total_cost_cents: int = 0
    gross_revenue_cents: int = 0
    net_revenue_cents: int = 0
    margin_percent: float = 0.0

    class Config:
        from_attributes = True


class TenantUsageSummaryResponse(BaseModel):
    tenant_id: str
    plan_tier: str = ""
    status: str = ""
    period_days: int
    total_events: int = 0
    total_cost_cents: int = 0
    active_users: int = 0
    by_resource: dict = Field(default_factory=dict)

    class Config:
        from_attributes = True


class PlatformCostBreakdownResponse(BaseModel):
    period: str  # e.g. "2026-06"
    tenant_count: int
    llm_cost_cents: int = 0
    embedding_cost_cents: int = 0
    storage_cost_cents: int = 0
    other_cost_cents: int = 0
    total_cost_cents: int = 0
    total_revenue_cents: int = 0
    net_cents: int = 0
    margin_percent: float = 0.0
    by_tenant: list[dict] = Field(default_factory=list)

    class Config:
        from_attributes = True


class DailyUsageResponse(BaseModel):
    resource: str
    tenant_id: str
    daily: list[DailyUsageItem]

    class Config:
        from_attributes = True


# ── Factory ────────────────────────────────────────────────────────────────


def create_usage_router(usage_store, subscription_store, billing_store) -> APIRouter:
    router = APIRouter(prefix="/usage", tags=["Usage"])

    # ── Helpers ─────────────────────────────────────────────────────────

    def _current_year_month() -> tuple[int, int]:
        now = datetime.now(timezone.utc)
        return now.year, now.month

    # ── 1. POST /usage/record ───────────────────────────────────────────

    @router.post("/record", status_code=201)
    async def record_usage(
        body: RecordUsageRequest,
        token=Depends(require_auth),
    ):
        """Record a usage event. This is the main tracking endpoint called by other services."""
        try:
            resource = UsageResource(body.resource)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid resource: '{body.resource}'. "
                       f"Valid values: {[r.value for r in UsageResource]}",
            )
        try:
            unit = UsageUnit(body.unit)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid unit: '{body.unit}'. "
                       f"Valid values: {[u.value for u in UsageUnit]}",
            )

        event = UsageEvent(
            tenant_id=token.workspace_id,
            user_id=token.user_id,
            resource=resource,
            quantity=body.quantity,
            unit=unit,
            metadata=body.metadata,
            cost_cents=body.cost_cents,
        )
        try:
            event_id = usage_store.record_event(event)
            return {"id": event_id, "status": "recorded"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to record usage: {str(e)}")

    # ── 2. GET /usage/stats ─────────────────────────────────────────────

    @router.get("/stats", response_model=UsageStatsResponse)
    async def get_monthly_stats(
        year: int = Query(None, description="Year (defaults to current)"),
        month: int = Query(None, ge=1, le=12, description="Month 1-12 (defaults to current)"),
        token=Depends(require_auth),
    ):
        """Get monthly usage stats for the current tenant."""
        if year is None or month is None:
            year, month = _current_year_month()
        try:
            stats = usage_store.get_monthly_stats(
                tenant_id=token.workspace_id, year=year, month=month,
            )
            return stats.as_dict()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

    # ── 3. GET /usage/cost ──────────────────────────────────────────────

    @router.get("/cost", response_model=CostStatsResponse)
    async def get_cost_stats(
        year: int = Query(None, description="Year (defaults to current)"),
        month: int = Query(None, ge=1, le=12, description="Month 1-12 (defaults to current)"),
        token=Depends(require_auth),
    ):
        """Get cost stats for the current tenant this month."""
        if year is None or month is None:
            year, month = _current_year_month()
        try:
            stats = usage_store.get_cost_stats(
                tenant_id=token.workspace_id, year=year, month=month,
            )
            return stats.as_dict()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get cost stats: {str(e)}")

    # ── 4. GET /usage/daily ─────────────────────────────────────────────

    @router.get("/daily", response_model=DailyUsageResponse)
    async def get_daily_usage(
        resource: str = Query(..., description="Resource type (e.g. llm_call, search, upload)"),
        days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
        token=Depends(require_auth),
    ):
        """Get daily usage for a specific resource over the last N days."""
        try:
            UsageResource(resource)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid resource: '{resource}'. "
                       f"Valid values: {[r.value for r in UsageResource]}",
            )
        try:
            daily = usage_store.get_daily_usage(
                tenant_id=token.workspace_id, resource=resource, days=days,
            )
            return {
                "resource": resource,
                "tenant_id": token.workspace_id,
                "daily": daily,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get daily usage: {str(e)}")

    # ── 5. GET /usage/profile ───────────────────────────────────────────

    @router.get("/profile", response_model=UserProfileResponse)
    async def get_my_profile(
        token=Depends(require_auth),
    ):
        """Get the current user's usage profile."""
        try:
            profile = usage_store.get_user_profile(
                tenant_id=token.workspace_id, user_id=token.user_id,
            )
            return profile.as_dict()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get profile: {str(e)}")

    # ── 6. GET /usage/profiles/{user_id} ────────────────────────────────

    @router.get("/profiles/{user_id}", response_model=UserProfileResponse)
    async def get_user_profile(
        user_id: str,
        token=Depends(require_manage),
    ):
        """Admin: get usage profile for a specific user within the current tenant."""
        try:
            profile = usage_store.get_user_profile(
                tenant_id=token.workspace_id, user_id=user_id,
            )
            return profile.as_dict()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get user profile: {str(e)}")

    # ── 7. GET /usage/tenant-summary ────────────────────────────────────

    @router.get("/tenant-summary", response_model=TenantUsageSummaryResponse)
    async def get_tenant_summary(
        days: int = Query(30, ge=1, le=365, description="Number of days to summarize"),
        token=Depends(require_auth),
    ):
        """Get the current tenant's usage summary for the last N days."""
        try:
            summary = usage_store.get_tenant_usage_summary(
                tenant_id=token.workspace_id, days=days,
            )
            # Enrich with subscription info
            sub = subscription_store.get_subscription(token.workspace_id)
            plan_tier = ""
            status = ""
            if sub:
                plan_tier = sub.plan_tier.value if hasattr(sub.plan_tier, "value") else str(sub.plan_tier)
                status = sub.status.value if hasattr(sub.status, "value") else str(sub.status)
            summary["plan_tier"] = plan_tier
            summary["status"] = status
            return summary
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get tenant summary: {str(e)}")

    # ── 8. GET /usage/admin/platform-stats ──────────────────────────────

    @router.get("/admin/platform-stats", response_model=PlatformStatsResponse)
    async def get_platform_stats(
        token=Depends(require_manage),
    ):
        """Admin: get platform-wide stats (MRR, ARR, churn, retention, conversion)."""
        try:
            stats = usage_store.get_platform_stats()
            return stats.as_dict()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get platform stats: {str(e)}")

    # ── 9. GET /usage/admin/tenants ─────────────────────────────────────

    @router.get("/admin/tenants")
    async def list_tenant_summaries(
        days: int = Query(30, ge=1, le=365, description="Number of days to summarize"),
        token=Depends(require_manage),
    ):
        """Admin: list all tenant usage summaries with subscription info."""
        try:
            all_subs = subscription_store.list_all_subscriptions()
            summaries: list[dict] = []
            for sub in all_subs:
                tid = sub.tenant_id
                plan_tier = sub.plan_tier.value if hasattr(sub.plan_tier, "value") else str(sub.plan_tier)
                status = sub.status.value if hasattr(sub.status, "value") else str(sub.status)
                try:
                    ts = usage_store.get_tenant_usage_summary(
                        tenant_id=tid, days=days,
                    )
                    ts["plan_tier"] = plan_tier
                    ts["status"] = status
                    summaries.append(ts)
                except Exception:
                    # Tenant may have no usage events yet
                    summaries.append({
                        "tenant_id": tid,
                        "plan_tier": plan_tier,
                        "status": status,
                        "period_days": days,
                        "total_events": 0,
                        "total_cost_cents": 0,
                        "active_users": 0,
                        "by_resource": {},
                    })
            return {"tenants": summaries, "total": len(summaries)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to list tenant summaries: {str(e)}")

    # ── 10. GET /usage/admin/costs ──────────────────────────────────────

    @router.get("/admin/costs", response_model=PlatformCostBreakdownResponse)
    async def get_platform_cost_breakdown(
        year: int = Query(None, description="Year (defaults to current)"),
        month: int = Query(None, ge=1, le=12, description="Month 1-12 (defaults to current)"),
        token=Depends(require_manage),
    ):
        """Admin: get platform-wide cost breakdown aggregated across all tenants."""
        if year is None or month is None:
            year, month = _current_year_month()

        month_str = f"{year:04d}-{month:02d}"
        try:
            all_subs = subscription_store.list_all_subscriptions()

            llm_total = 0
            embedding_total = 0
            storage_total = 0
            other_total = 0
            grand_cost = 0
            grand_revenue = 0
            by_tenant: list[dict] = []

            for sub in all_subs:
                tid = sub.tenant_id
                try:
                    cs = usage_store.get_cost_stats(
                        tenant_id=tid, year=year, month=month,
                    )
                    by_tenant.append(cs.as_dict())
                    llm_total += cs.llm_cost_cents
                    embedding_total += cs.embedding_cost_cents
                    storage_total += cs.storage_cost_cents
                    # other = total - (llm + embedding + storage)
                    other_total += (
                        cs.total_cost_cents
                        - cs.llm_cost_cents
                        - cs.embedding_cost_cents
                        - cs.storage_cost_cents
                    )
                    grand_cost += cs.total_cost_cents
                    grand_revenue += cs.gross_revenue_cents
                except Exception:
                    by_tenant.append({
                        "tenant_id": tid,
                        "month": month_str,
                        "llm_cost_cents": 0,
                        "embedding_cost_cents": 0,
                        "storage_cost_cents": 0,
                        "total_cost_cents": 0,
                        "gross_revenue_cents": 0,
                        "net_revenue_cents": 0,
                        "margin_percent": 0.0,
                    })

            net = grand_revenue - grand_cost
            margin = round((net / grand_revenue) * 100, 1) if grand_revenue > 0 else 0.0

            return {
                "period": month_str,
                "tenant_count": len(all_subs),
                "llm_cost_cents": llm_total,
                "embedding_cost_cents": embedding_total,
                "storage_cost_cents": storage_total,
                "other_cost_cents": other_total,
                "total_cost_cents": grand_cost,
                "total_revenue_cents": grand_revenue,
                "net_cents": net,
                "margin_percent": margin,
                "by_tenant": by_tenant,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get platform costs: {str(e)}")

    return router
