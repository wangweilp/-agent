"""Billing / RBAC / Cross-Tenant Analytics API。

端点:
  Billing & Subscription:
    POST /api/tenant/subscribe              — 创建订阅
    GET  /api/tenant/subscription            — 订阅信息
    POST /api/tenant/change-plan             — 套餐变更
    POST /api/tenant/cancel-subscription     — 取消订阅
    GET  /api/tenant/quota-summary           — 配额总览

  Billing:
    POST /api/tenant/invoices/generate       — 生成账单
    POST /api/tenant/invoices/pay            — 支付账单
    GET  /api/tenant/invoices                — 账单列表

  RBAC:
    GET  /api/rbac/matrix                    — 完整权限矩阵
    GET  /api/rbac/check                     — 权限检查
    POST /api/rbac/assign                    — 分配角色
    DELETE /api/rbac/revoke                  — 撤销角色

  Cross-Tenant Analytics:
    GET /api/analytics/cross-tenant          — 跨租户聚合
    GET /api/analytics/tenants               — 各租户摘要
    GET /api/analytics/cross-tenant/trends   — 趋势
    GET /api/analytics/cross-tenant/top-agents — 全平台 Top Agents

约束: metadata_only，不执行 runtime/container。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.middleware import require_auth, TokenPayload

logger = logging.getLogger(__name__)


# ── Request Models ──

class SubscribeRequest(BaseModel):
    plan_tier: str = Field(default="free")
    billing_cycle: str = Field(default="monthly")


class ChangePlanRequest(BaseModel):
    target_tier: str = Field(..., min_length=1)
    billing_cycle: str = "monthly"


class GenerateInvoiceRequest(BaseModel):
    amount_cents: int = Field(..., ge=0)
    currency: str = "cny"
    description: str = ""


class PayInvoiceRequest(BaseModel):
    invoice_id: str = Field(..., min_length=1)
    amount_cents: int = Field(..., ge=0)
    provider: str = "stripe"
    provider_payment_id: str = ""


class RBACAssignRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)


class RBACCheckRequest(BaseModel):
    role: str = Field(..., min_length=1)
    resource: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)


class RBACRevokeRequest(BaseModel):
    user_id: str = Field(..., min_length=1)


# ── Router Factory ──

def create_billing_analytics_router(
    billing_service=None, rbac_service=None, ct_analytics_service=None,
) -> APIRouter:

    router = APIRouter(tags=["billing-rbac-analytics"])

    # ═══════════════ Billing & Subscription ═══════════════

    @router.post("/api/tenant/subscribe", status_code=201)
    async def subscribe(body: SubscribeRequest,
                         payload: TokenPayload = Depends(require_auth)):
        if not billing_service:
            raise HTTPException(501, "Billing service not available")
        result = billing_service.create_subscription(
            payload.workspace_id, body.plan_tier, body.billing_cycle)
        if "error" in result: raise HTTPException(400, result["error"])
        return result

    @router.get("/api/tenant/subscription")
    async def get_subscription(payload: TokenPayload = Depends(require_auth)):
        if not billing_service:
            raise HTTPException(501, "Billing service not available")
        sub = billing_service.get_subscription(payload.workspace_id)
        if not sub: raise HTTPException(404, "No subscription found")
        return sub

    @router.post("/api/tenant/change-plan")
    async def change_plan(body: ChangePlanRequest,
                          payload: TokenPayload = Depends(require_auth)):
        if not billing_service:
            raise HTTPException(501, "Billing service not available")
        result = billing_service.change_plan(
            payload.workspace_id, body.target_tier, body.billing_cycle)
        if "error" in result: raise HTTPException(400, result["error"])
        return result

    @router.post("/api/tenant/cancel-subscription")
    async def cancel(payload: TokenPayload = Depends(require_auth)):
        if not billing_service:
            raise HTTPException(501, "Billing service not available")
        return billing_service.cancel_subscription(payload.workspace_id)

    @router.get("/api/tenant/quota-summary")
    async def quota_summary(payload: TokenPayload = Depends(require_auth)):
        if not billing_service:
            raise HTTPException(501, "Billing service not available")
        return billing_service.get_quota_summary(payload.workspace_id)

    @router.post("/api/tenant/invoices/generate", status_code=201)
    async def generate_invoice(body: GenerateInvoiceRequest,
                                payload: TokenPayload = Depends(require_auth)):
        if not billing_service:
            raise HTTPException(501, "Billing service not available")
        result = billing_service.generate_invoice(
            payload.workspace_id, body.amount_cents, body.currency, body.description)
        if "error" in result: raise HTTPException(400, result["error"])
        return result

    @router.post("/api/tenant/invoices/pay")
    async def pay_invoice(body: PayInvoiceRequest,
                          payload: TokenPayload = Depends(require_auth)):
        if not billing_service:
            raise HTTPException(501, "Billing service not available")
        result = billing_service.record_payment(
            payload.workspace_id, body.invoice_id, body.amount_cents,
            body.provider, body.provider_payment_id)
        if "error" in result: raise HTTPException(400, result["error"])
        return result

    @router.get("/api/tenant/invoices")
    async def list_invoices(payload: TokenPayload = Depends(require_auth)):
        if not billing_service or not billing_service._billing:
            raise HTTPException(501, "Billing service not available")
        invoices = billing_service._billing.list_invoices(payload.workspace_id)
        return {"invoices": [billing_service._invoice_to_dict(inv) for inv in invoices],
                "total": len(invoices)}

    # ═══════════════ RBAC ═══════════════

    @router.get("/api/rbac/matrix")
    async def rbac_matrix(payload: TokenPayload = Depends(require_auth)):
        if not rbac_service: raise HTTPException(501, "RBAC service not available")
        matrix = rbac_service.get_permission_matrix()
        roles = rbac_service.list_roles()
        resources = rbac_service.list_resources()
        actions = rbac_service.list_actions()
        return {"matrix": matrix, "roles": roles, "resources": resources, "actions": actions}

    @router.post("/api/rbac/check")
    async def rbac_check(body: RBACCheckRequest,
                         payload: TokenPayload = Depends(require_auth)):
        if not rbac_service: raise HTTPException(501, "RBAC service not available")
        allowed = rbac_service.check_permission(body.role, body.resource, body.action)
        return {"role": body.role, "resource": body.resource, "action": body.action,
                "allowed": allowed}

    @router.post("/api/rbac/assign")
    async def rbac_assign(body: RBACAssignRequest,
                          payload: TokenPayload = Depends(require_auth)):
        if not rbac_service: raise HTTPException(501, "RBAC service not available")
        return rbac_service.assign_role(body.user_id, payload.workspace_id, body.role)

    @router.delete("/api/rbac/revoke")
    async def rbac_revoke(body: RBACRevokeRequest,
                          payload: TokenPayload = Depends(require_auth)):
        if not rbac_service: raise HTTPException(501, "RBAC service not available")
        return rbac_service.revoke_role(body.user_id, payload.workspace_id)

    # ═══════════════ Cross-Tenant Analytics ═══════════════

    @router.get("/api/analytics/cross-tenant")
    async def cross_tenant_metrics(refresh: bool = Query(default=False),
                                   payload: TokenPayload = Depends(require_auth)):
        if not ct_analytics_service: raise HTTPException(501, "Analytics not available")
        if refresh:
            return ct_analytics_service.aggregate_metrics()
        cached = ct_analytics_service.get_cached_metrics()
        return cached or ct_analytics_service.aggregate_metrics()

    @router.get("/api/analytics/tenants")
    async def tenant_summaries(refresh: bool = Query(default=False),
                               payload: TokenPayload = Depends(require_auth)):
        if not ct_analytics_service: raise HTTPException(501, "Analytics not available")
        if refresh:
            return {"tenants": ct_analytics_service.usage_per_workspace()}
        cached = ct_analytics_service.get_cached_tenant_summaries()
        return {"tenants": cached or ct_analytics_service.usage_per_workspace()}

    @router.get("/api/analytics/cross-tenant/trends")
    async def trends(metric: str = Query(default=""),
                     limit: int = Query(default=10, ge=1, le=100),
                     refresh: bool = Query(default=False),
                     payload: TokenPayload = Depends(require_auth)):
        if not ct_analytics_service: raise HTTPException(501, "Analytics not available")
        if refresh:
            return {"trends": ct_analytics_service.generate_trends(limit)}
        cached = ct_analytics_service.get_cached_trends(metric_name=metric, limit=limit)
        return {"trends": cached or ct_analytics_service.generate_trends(limit)}

    @router.get("/api/analytics/cross-tenant/top-agents")
    async def top_agents(limit: int = Query(default=10, ge=1, le=100),
                         payload: TokenPayload = Depends(require_auth)):
        if not ct_analytics_service: raise HTTPException(501, "Analytics not available")
        return {"top_agents": ct_analytics_service.top_agents(limit)}

    return router
