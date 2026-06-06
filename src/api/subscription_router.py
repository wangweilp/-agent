"""Subscription Management API — 套餐订阅 / 用量限制 / 计费管理。

端点:
    GET    /subscription                  — 当前租户订阅详情（含限制）
    GET    /subscription/plans            — 所有可用套餐
    GET    /subscription/plans/{tier}     — 套餐详情
    POST   /subscription/change-plan      — 升级/降级套餐
    POST   /subscription/cancel           — 取消订阅
    POST   /subscription/resume           — 恢复订阅
    GET    /subscription/check-limit      — 检查资源限制
    GET    /subscription/limits           — 所有限制与当前用量
    GET    /subscription/admin/stats      — 管理员：订阅统计
    GET    /subscription/admin/list       — 管理员：所有订阅列表
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.adapters.billing_store import BillingStoreAdapter
from src.adapters.subscription_store import SubscriptionStoreAdapter
from src.adapters.usage_store import UsageStoreAdapter
from src.api.middleware import get_token_payload, require_auth, require_manage
from src.api.saas_schemas import (
    ChangePlanRequest,
    LimitCheckResponse,
    SubscriptionResponse,
)
from src.core.auth import TokenPayload
from src.core.billing import (
    BillingAccount,
    Currency,
    Invoice,
    InvoiceStatus,
)
from src.core.subscription import (
    PLANS,
    PLAN_PRICES,
    BillingCycle,
    PlanLimit,
    PlanTier,
    Subscription,
    SubscriptionStatus,
)

logger = logging.getLogger(__name__)


# ── Pydantic 请求/响应模型 ──


class PlanDetailResponse(BaseModel):
    """套餐详情响应。"""
    tier: str
    monthly_price: int  # 分
    yearly_price: int   # 分
    current: bool = False
    limits: dict


class ChangePlanBody(BaseModel):
    target_tier: str = Field(..., pattern=r"^(free|personal|professional|team|enterprise)$")
    billing_cycle: str = Field(default="monthly", pattern=r"^(monthly|yearly)$")


class LimitCheckQuery(BaseModel):
    resource: str = Field(..., description="资源类型: memory_count, search_count, import_per_day, llm_calls_per_day, embedding_calls_per_day")


class LimitsResponseItem(BaseModel):
    resource: str
    used: int
    limit: int
    remaining: int


# ── 资源名映射: PlanLimit 字段 → usage resource ──

_LIMIT_TO_USAGE_RESOURCE: dict[str, str] = {
    "memory_count": "memory",
    "search_count": "search",
    "import_per_day": "import",
    "llm_calls_per_day": "llm_call",
    "embedding_calls_per_day": "embedding",
}

# ── 哪些字段是"每日"限制 ──

_DAILY_LIMIT_FIELDS = frozenset({
    "search_count", "import_per_day", "llm_calls_per_day", "embedding_calls_per_day",
})

# ── Helper: 计费账户 ──


def _ensure_billing_account(billing_store: BillingStoreAdapter, tenant_id: str) -> BillingAccount:
    """获取或创建计费账户。"""
    account = billing_store.get_account(tenant_id)
    if account is None:
        account = BillingAccount(
            tenant_id=tenant_id,
            currency=Currency.CNY,
            billing_email="",
        )
        account = billing_store.create_account(account)
    return account


# ── Helper: 用量统计 ──


def _count_events(
    usage_store: UsageStoreAdapter,
    tenant_id: str,
    resource: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> int:
    """统计指定资源的用量事件数。传 start/end 按时间范围过滤，不传则统计全部。"""
    limit = 1000000  # 足够大的 limit
    events = usage_store.query_events(
        tenant_id=tenant_id, resource=resource,
        start=start, end=end, limit=limit,
    )
    return sum(e.quantity for e in events)


def _get_usage_for_limit(
    usage_store: UsageStoreAdapter,
    tenant_id: str,
    limit_name: str,
) -> int:
    """根据 PlanLimit 字段名获取当前用量。"""
    resource = _LIMIT_TO_USAGE_RESOURCE.get(limit_name)
    if resource is None:
        return 0

    if limit_name in _DAILY_LIMIT_FIELDS:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        return _count_events(usage_store, tenant_id, resource, start=today_start, end=today_end)
    else:
        # memory_count: 统计全部
        return _count_events(usage_store, tenant_id, resource)


# ── Router Factory ──


def create_subscription_router(
    subscription_store: SubscriptionStoreAdapter,
    usage_store: UsageStoreAdapter,
    billing_store: BillingStoreAdapter,
) -> APIRouter:
    router = APIRouter(tags=["subscription"])

    # ── Helper: 获取 tenant_id ──

    def _tenant_id(payload: TokenPayload) -> str:
        return payload.workspace_id

    # ═══════════════════════════════════════════════════════════════
    # GET /subscription — 当前租户订阅详情
    # ═══════════════════════════════════════════════════════════════

    @router.get("/subscription")
    async def get_subscription(payload: TokenPayload = Depends(require_auth)):
        """获取当前租户的订阅信息，包含套餐限制详情和剩余天数。"""
        tid = _tenant_id(payload)
        sub = subscription_store.get_subscription(tid)
        if sub is None:
            raise HTTPException(status_code=404, detail="未找到订阅")

        plan_limit = sub.plan_limit()
        days_remaining = sub.days_remaining()

        return {
            "id": sub.id,
            "tenant_id": sub.tenant_id,
            "plan_tier": sub.plan_tier.value,
            "status": sub.status.value,
            "billing_cycle": sub.billing_cycle.value,
            "current_period_start": sub.current_period_start.isoformat(),
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            "trial_start": sub.trial_start.isoformat() if sub.trial_start else None,
            "trial_end": sub.trial_end.isoformat() if sub.trial_end else None,
            "canceled_at": sub.canceled_at.isoformat() if sub.canceled_at else None,
            "auto_renew": sub.auto_renew,
            "coupon_code": sub.coupon_code,
            "days_remaining": days_remaining,
            "created_at": sub.created_at.isoformat(),
            "limits": plan_limit.as_dict(),
        }

    # ═══════════════════════════════════════════════════════════════
    # GET /subscription/plans — 所有可用套餐
    # ═══════════════════════════════════════════════════════════════

    @router.get("/subscription/plans")
    async def list_plans(payload: TokenPayload = Depends(require_auth)):
        """列出所有可用套餐，含价格和限制。标记当前套餐。"""
        tid = _tenant_id(payload)
        sub = subscription_store.get_subscription(tid)
        current_tier = sub.plan_tier if sub else PlanTier.FREE

        result = []
        for tier, plan_limit in PLANS.items():
            prices = PLAN_PRICES.get(tier, {})
            result.append({
                "tier": tier.value,
                "limits": plan_limit.as_dict(),
                "monthly_price": prices.get(BillingCycle.MONTHLY, 0),
                "yearly_price": prices.get(BillingCycle.YEARLY, 0),
                "current": tier == current_tier,
            })
        return result

    # ═══════════════════════════════════════════════════════════════
    # GET /subscription/plans/{tier} — 套餐详情
    # ═══════════════════════════════════════════════════════════════

    @router.get("/subscription/plans/{tier}")
    async def get_plan_detail(
        tier: str,
        payload: TokenPayload = Depends(require_auth),
    ):
        """获取指定套餐的详细信息。"""
        try:
            plan_tier = PlanTier(tier)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效套餐层级: {tier}。可选: free/personal/professional/team/enterprise")

        plan_limit = PLANS.get(plan_tier)
        if plan_limit is None:
            raise HTTPException(status_code=404, detail=f"套餐 '{tier}' 不存在")

        prices = PLAN_PRICES.get(plan_tier, {})
        tid = _tenant_id(payload)
        sub = subscription_store.get_subscription(tid)
        current = sub.plan_tier == plan_tier if sub else False

        return {
            "tier": tier,
            "monthly_price": prices.get(BillingCycle.MONTHLY, 0),
            "yearly_price": prices.get(BillingCycle.YEARLY, 0),
            "current": current,
            "limits": plan_limit.as_dict(),
        }

    # ═══════════════════════════════════════════════════════════════
    # POST /subscription/change-plan — 升级/降级套餐
    # ═══════════════════════════════════════════════════════════════

    @router.post("/subscription/change-plan")
    async def change_plan(
        body: ChangePlanBody,
        payload: TokenPayload = Depends(require_auth),
    ):
        """升级或降级订阅套餐。升级到付费套餐时自动生成发票。"""
        tid = _tenant_id(payload)

        try:
            target_tier = PlanTier(body.target_tier)
            target_cycle = BillingCycle(body.billing_cycle)
        except ValueError as e:
            raise HTTPException(status_code=400, detail="请求参数无效")

        sub = subscription_store.get_subscription(tid)
        if sub is None:
            raise HTTPException(status_code=404, detail="未找到订阅")

        # 如果目标套餐与当前相同且周期相同，无需变更
        if sub.plan_tier == target_tier and sub.billing_cycle == target_cycle:
            return {
                "tenant_id": tid,
                "plan_tier": sub.plan_tier.value,
                "billing_cycle": sub.billing_cycle.value,
                "status": sub.status.value,
                "message": "当前已是该套餐",
            }

        # 升级到付费套餐 → 生成发票
        price = PLAN_PRICES.get(target_tier, {}).get(target_cycle, 0)
        if price > 0:
            account = _ensure_billing_account(billing_store, tid)
            invoice = Invoice(
                tenant_id=tid,
                billing_account_id=account.id,
                amount=price,
                currency=account.currency,
                status=InvoiceStatus.OPEN,
                description=f"订阅变更: {target_tier.value} ({target_cycle.value})",
                line_items=[{
                    "description": f"{target_tier.value} 套餐 ({target_cycle.value})",
                    "quantity": 1,
                    "unit_amount": price,
                    "amount": price,
                }],
                due_date=datetime.now(timezone.utc) + timedelta(days=30),
                period_start=datetime.now(timezone.utc),
                period_end=datetime.now(timezone.utc) + (timedelta(days=365) if target_cycle == BillingCycle.YEARLY else timedelta(days=30)),
            )
            billing_store.create_invoice(invoice)

        # 执行套餐变更
        updated = subscription_store.change_plan(tid, target_tier, target_cycle)

        return {
            "tenant_id": tid,
            "plan_tier": updated.plan_tier.value,
            "billing_cycle": updated.billing_cycle.value,
            "status": updated.status.value,
            "changed_at": updated.updated_at.isoformat(),
            "price_cents": price,
        }

    # ═══════════════════════════════════════════════════════════════
    # POST /subscription/cancel — 取消订阅
    # ═══════════════════════════════════════════════════════════════

    @router.post("/subscription/cancel")
    async def cancel_subscription(payload: TokenPayload = Depends(require_auth)):
        """取消当前订阅。到期后不再自动续费。"""
        tid = _tenant_id(payload)

        try:
            updated = subscription_store.cancel_subscription(tid)
        except ValueError as e:
            raise HTTPException(status_code=404, detail="请求的资源不存在")

        return {
            "tenant_id": tid,
            "status": updated.status.value,
            "canceled_at": updated.canceled_at.isoformat() if updated.canceled_at else None,
        }

    # ═══════════════════════════════════════════════════════════════
    # POST /subscription/resume — 恢复订阅
    # ═══════════════════════════════════════════════════════════════

    @router.post("/subscription/resume")
    async def resume_subscription(payload: TokenPayload = Depends(require_auth)):
        """恢复已取消的订阅，状态重新设为 active。"""
        tid = _tenant_id(payload)

        sub = subscription_store.get_subscription(tid)
        if sub is None:
            raise HTTPException(status_code=404, detail="未找到订阅")

        if sub.status != SubscriptionStatus.CANCELED:
            raise HTTPException(status_code=400, detail="仅已取消的订阅可恢复")

        sub.status = SubscriptionStatus.ACTIVE
        sub.auto_renew = True
        sub.canceled_at = None
        subscription_store.update_subscription(sub)

        updated = subscription_store.get_subscription(tid)
        return {
            "tenant_id": tid,
            "status": updated.status.value if updated else "active",
        }

    # ═══════════════════════════════════════════════════════════════
    # GET /subscription/check-limit — 检查资源限制
    # ═══════════════════════════════════════════════════════════════

    @router.get("/subscription/check-limit")
    async def check_limit(
        resource: str = Query(..., description="资源类型: memory_count, search_count, import_per_day, llm_calls_per_day, embedding_calls_per_day"),
        payload: TokenPayload = Depends(require_auth),
    ):
        """检查指定资源是否在套餐限制内。"""
        tid = _tenant_id(payload)

        sub = subscription_store.get_subscription(tid)
        if sub is None:
            raise HTTPException(status_code=404, detail="未找到订阅")

        plan_limit = sub.plan_limit()
        limit_dict = plan_limit.as_dict()

        if resource not in limit_dict:
            raise HTTPException(status_code=400, detail=f"未知资源类型: {resource}")

        limit_value = limit_dict[resource]

        # 对布尔型限制(如 knowledge_graph)，直接返回 allowed
        if isinstance(limit_value, bool):
            return {
                "resource": resource,
                "allowed": limit_value,
                "used": 0,
                "limit": 1 if limit_value else 0,
                "remaining": 1 if limit_value else 0,
            }

        used = _get_usage_for_limit(usage_store, tid, resource)
        allowed = used < limit_value
        remaining = max(0, limit_value - used)

        return {
            "resource": resource,
            "allowed": allowed,
            "used": used,
            "limit": limit_value,
            "remaining": remaining,
        }

    # ═══════════════════════════════════════════════════════════════
    # GET /subscription/limits — 所有限制与当前用量
    # ═══════════════════════════════════════════════════════════════

    @router.get("/subscription/limits")
    async def get_limits(payload: TokenPayload = Depends(require_auth)):
        """返回所有套餐限制及当前用量。"""
        tid = _tenant_id(payload)

        sub = subscription_store.get_subscription(tid)
        if sub is None:
            raise HTTPException(status_code=404, detail="未找到订阅")

        plan_limit = sub.plan_limit()
        limit_dict = plan_limit.as_dict()

        result = []
        for resource, limit_value in limit_dict.items():
            if resource == "tier":
                continue

            if isinstance(limit_value, bool):
                item = {
                    "resource": resource,
                    "used": 0,
                    "limit": 1 if limit_value else 0,
                    "remaining": 1 if limit_value else 0,
                    "is_bool": True,
                }
            else:
                used = _get_usage_for_limit(usage_store, tid, resource)
                item = {
                    "resource": resource,
                    "used": used,
                    "limit": limit_value,
                    "remaining": max(0, limit_value - used),
                    "is_bool": False,
                }
            result.append(item)

        return {
            "tenant_id": tid,
            "plan_tier": plan_limit.tier.value,
            "limits": result,
        }

    # ═══════════════════════════════════════════════════════════════
    # GET /subscription/admin/stats — 管理员：订阅统计
    # ═══════════════════════════════════════════════════════════════

    @router.get("/subscription/admin/stats")
    async def admin_subscription_stats(payload: TokenPayload = Depends(require_manage)):
        """管理员：订阅统计（各套餐数量、MRR 等）。"""
        count_by_tier = subscription_store.count_by_tier()
        all_subs = subscription_store.list_subscriptions()

        total_subscriptions = len(all_subs)
        active_subscriptions = 0
        trial_subscriptions = 0
        canceled_subscriptions = 0
        mrr_cents = 0

        for sub in all_subs:
            if sub.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL):
                active_subscriptions += 1
                # 计算 MRR
                tier = sub.plan_tier
                cycle = sub.billing_cycle
                monthly_price = PLAN_PRICES.get(tier, {}).get(BillingCycle.MONTHLY, 0)
                if cycle == BillingCycle.YEARLY:
                    yearly = PLAN_PRICES.get(tier, {}).get(BillingCycle.YEARLY, 0)
                    monthly_price = yearly // 12
                mrr_cents += monthly_price

            if sub.status == SubscriptionStatus.TRIAL:
                trial_subscriptions += 1
            elif sub.status == SubscriptionStatus.CANCELED:
                canceled_subscriptions += 1

        return {
            "total_subscriptions": total_subscriptions,
            "active_subscriptions": active_subscriptions,
            "trial_subscriptions": trial_subscriptions,
            "canceled_subscriptions": canceled_subscriptions,
            "count_by_tier": count_by_tier,
            "mrr_cents": mrr_cents,
            "arr_cents": mrr_cents * 12,
            "churn_rate": round(canceled_subscriptions / total_subscriptions, 4) if total_subscriptions > 0 else 0.0,
        }

    # ═══════════════════════════════════════════════════════════════
    # GET /subscription/admin/list — 管理员：所有订阅列表
    # ═══════════════════════════════════════════════════════════════

    @router.get("/subscription/admin/list")
    async def admin_list_subscriptions(
        status: str = Query(default="", description="按状态过滤: active/trial/canceled/past_due/expired/paused"),
        payload: TokenPayload = Depends(require_manage),
    ):
        """管理员：列出所有订阅。可按状态过滤。"""
        filter_status = status if status else None
        subs = subscription_store.list_subscriptions(status=filter_status)

        return [
            {
                "id": sub.id,
                "tenant_id": sub.tenant_id,
                "plan_tier": sub.plan_tier.value,
                "status": sub.status.value,
                "billing_cycle": sub.billing_cycle.value,
                "current_period_start": sub.current_period_start.isoformat(),
                "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
                "trial_start": sub.trial_start.isoformat() if sub.trial_start else None,
                "trial_end": sub.trial_end.isoformat() if sub.trial_end else None,
                "canceled_at": sub.canceled_at.isoformat() if sub.canceled_at else None,
                "auto_renew": sub.auto_renew,
                "days_remaining": sub.days_remaining(),
                "created_at": sub.created_at.isoformat(),
            }
            for sub in subs
        ]

    return router
