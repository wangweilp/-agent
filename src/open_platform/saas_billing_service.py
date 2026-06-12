"""SaaS Billing Service — 订阅计费 + 配额检查 + 账单生成。

metadata-only，不执行 runtime/container/microVM。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class SaaSBillingService:
    """SaaS 计费服务 — 订阅管理 / 计费 / 配额。"""

    def __init__(self, billing_store=None, subscription_store=None, usage_store=None,
                 payment_gateway=None):
        self._billing = billing_store
        self._subscription = subscription_store
        self._usage = usage_store
        self._payment = payment_gateway

    # ═══════════════ Subscription ═══════════════

    def create_subscription(self, tenant_id: str, plan_tier: str = "free",
                            billing_cycle: str = "monthly") -> dict:
        from src.core.subscription import Subscription, SubscriptionStatus, BillingCycle, PlanTier
        if not self._subscription:
            return {"error": "subscription store unavailable"}
        existing = self._subscription.get_subscription(tenant_id)
        if existing:
            return {"subscription": self._subscription_to_dict(existing), "created": False}
        sub = Subscription(
            tenant_id=tenant_id,
            plan_tier=PlanTier(plan_tier),
            status=SubscriptionStatus.TRIAL,
            billing_cycle=BillingCycle(billing_cycle),
            trial_start=datetime.now(timezone.utc),
            trial_end=datetime.fromtimestamp(
                datetime.now(timezone.utc).timestamp() + 14 * 86400, tz=timezone.utc),
        )
        created = self._subscription.create_subscription(sub)
        self._record_usage(tenant_id, "subscription_create", 1, {"plan": plan_tier})
        return {"subscription": self._subscription_to_dict(created), "created": True}

    def get_subscription(self, tenant_id: str) -> dict | None:
        if not self._subscription: return None
        sub = self._subscription.get_subscription(tenant_id)
        return self._subscription_to_dict(sub) if sub else None

    def change_plan(self, tenant_id: str, target_tier: str, billing_cycle: str = "monthly") -> dict:
        from src.core.subscription import PlanTier, BillingCycle
        if not self._subscription:
            return {"error": "subscription store unavailable"}
        try:
            updated = self._subscription.change_plan(
                tenant_id, PlanTier(target_tier), BillingCycle(billing_cycle))
        except Exception as e:
            return {"error": str(e)}
        self._record_usage(tenant_id, "plan_change", 1, {"target": target_tier})
        return {"subscription": self._subscription_to_dict(updated)}

    def cancel_subscription(self, tenant_id: str) -> dict:
        if not self._subscription:
            return {"error": "subscription store unavailable"}
        cancelled = self._subscription.cancel_subscription(tenant_id)
        return {"subscription": self._subscription_to_dict(cancelled)}

    # ═══════════════ Billing ═══════════════

    def generate_invoice(self, tenant_id: str, amount_cents: int, currency: str = "cny",
                         description: str = "") -> dict:
        from src.core.billing import Invoice, InvoiceStatus, BillingAccount, Currency
        from uuid import uuid4
        if not self._billing: return {"error": "billing store unavailable"}
        cur = Currency(currency) if isinstance(currency, str) else currency
        account = self._billing.get_account(tenant_id)
        if not account:
            self._billing.create_account(BillingAccount(tenant_id=tenant_id, currency=cur))

        from datetime import timedelta
        now = datetime.now(timezone.utc)
        inv = Invoice(
            id=f"inv_{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            billing_account_id=tenant_id,
            amount=amount_cents,
            currency=cur,
            invoice_number=self._generate_invoice_number(),
            status=InvoiceStatus.OPEN,
            line_items=[{"description": description, "amount": amount_cents}],
            due_date=now + timedelta(days=30),
            period_start=now.replace(day=1),
            period_end=(now.replace(day=1) + timedelta(days=30)),
        )
        saved = self._billing.create_invoice(inv)
        return self._invoice_to_dict(saved)

    def record_payment(self, tenant_id: str, invoice_id: str, amount_cents: int,
                       provider: str = "stripe", provider_payment_id: str = "") -> dict:
        from src.core.billing import Payment, PaymentStatus, PaymentProvider
        from uuid import uuid4
        if not self._billing: return {"error": "billing store unavailable"}
        inv = self._billing.get_invoice(invoice_id)
        if inv is None: return {"error": f"invoice {invoice_id} not found"}
        pv = PaymentProvider(provider) if isinstance(provider, str) else provider
        payment = Payment(
            id=f"pay_{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            billing_account_id=tenant_id,
            invoice_id=invoice_id,
            amount=amount_cents,
            currency=inv.currency,
            provider=pv,
            provider_payment_id=provider_payment_id,
            status=PaymentStatus.SUCCEEDED,
        )
        saved = self._billing.create_payment(payment)
        # Mark invoice paid with updated invoice
        from src.core.billing import InvoiceStatus
        inv.status = InvoiceStatus.PAID
        inv.paid_at = datetime.now(timezone.utc)
        self._billing.update_invoice(inv)
        self._record_usage(tenant_id, "payment", 1, {"amount_cents": amount_cents, "provider": provider})
        return self._payment_to_dict(saved)

    # ═══════════════ Quota ═══════════════

    def check_quota(self, tenant_id: str, resource: str) -> dict:
        from src.core.subscription import PlanTier, PLANS
        if not self._subscription: return {"allowed": True, "resource": resource, "quota": -1}
        sub = self._subscription.get_subscription(tenant_id)
        tier = sub.plan_tier if sub else PlanTier.FREE
        limits = PLANS[tier]
        quota_map = {
            "agent_module": limits.max_marketplace_agents,
            "marketplace_subscription": limits.max_marketplace_agents,
            "artifact": limits.max_marketplace_agents * 10,
            "package": limits.max_marketplace_agents * 2,
            "workflow": limits.max_marketplace_agents,
            "llm_calls_per_day": limits.llm_calls_per_day,
            "embedding_calls_per_day": limits.embedding_calls_per_day,
            "storage_mb": limits.storage_mb,
            "search_count": limits.search_count,
        }
        limit = quota_map.get(resource, limits.max_marketplace_agents)
        allowed = limit == -1 or limit > 0  # -1 = unlimited
        return {"allowed": allowed, "resource": resource, "quota": limit, "tier": tier.value}

    def get_quota_summary(self, tenant_id: str) -> dict:
        from src.core.subscription import PlanTier, PLANS
        sub = None
        if self._subscription:
            sub = self._subscription.get_subscription(tenant_id)
        tier = sub.plan_tier if sub else PlanTier.FREE
        limits = PLANS[tier]
        return {
            "tenant_id": tenant_id,
            "plan_tier": tier.value,
            "status": sub.status.value if sub else "none",
            "auto_renew": sub.auto_renew if sub else False,
            "days_remaining": sub.days_remaining() if sub else 0,
            "quotas": {
                "agent_modules": limits.max_marketplace_agents,
                "artifacts": limits.max_marketplace_agents * 10,
                "packages": limits.max_marketplace_agents * 2,
                "workflows": limits.max_marketplace_agents,
                "llm_calls_per_day": limits.llm_calls_per_day,
                "embedding_calls_per_day": limits.embedding_calls_per_day,
                "storage_mb": limits.storage_mb,
            },
            "features": {
                "knowledge_graph": limits.knowledge_graph,
                "ai_coach": limits.ai_coach,
                "api_access": limits.api_access,
                "priority_support": limits.priority_support,
                "team_members": limits.team_members,
            },
        }

    # ═══════════════ Helpers ═══════════════

    def _record_usage(self, tenant_id: str, resource: str, quantity: int,
                      metadata: dict | None = None):
        if not self._usage: return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            resource_map = {
                "subscription_create": UsageResource.AGENT_INSTALL,
                "plan_change": UsageResource.AGENT_SUBMISSION_PUBLISH,
                "payment": UsageResource.AGENT_INSTALL,
            }
            evt = UsageEvent(
                tenant_id=tenant_id, user_id="system", workspace_id=tenant_id,
                resource=resource_map.get(resource, UsageResource.STORAGE),
                quantity=quantity, unit=UsageUnit.COUNT, metadata=metadata or {},
            )
            self._usage.record_event(evt)
        except Exception:
            logger.debug("record_usage_silent_fail", exc_info=True)

    @staticmethod
    def _subscription_to_dict(sub) -> dict:
        return {
            "id": sub.id, "tenant_id": sub.tenant_id,
            "plan_tier": sub.plan_tier.value, "status": sub.status.value,
            "billing_cycle": sub.billing_cycle.value,
            "current_period_start": sub.current_period_start.isoformat(),
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            "trial_start": sub.trial_start.isoformat() if sub.trial_start else None,
            "trial_end": sub.trial_end.isoformat() if sub.trial_end else None,
            "auto_renew": sub.auto_renew, "days_remaining": sub.days_remaining(),
        }

    @staticmethod
    def _invoice_to_dict(inv) -> dict:
        return {
            "id": inv.id, "tenant_id": inv.tenant_id, "amount": inv.amount,
            "currency": inv.currency, "invoice_number": inv.invoice_number,
            "status": inv.status.value, "line_items": inv.line_items,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "paid_at": inv.paid_at.isoformat() if inv.paid_at else None,
        }

    @staticmethod
    def _payment_to_dict(payment) -> dict:
        return {
            "id": payment.id, "tenant_id": payment.tenant_id,
            "invoice_id": payment.invoice_id, "amount": payment.amount,
            "currency": payment.currency, "provider": payment.provider,
            "provider_payment_id": payment.provider_payment_id,
            "status": payment.status.value,
        }

    def _generate_invoice_number(self) -> str:
        from datetime import datetime
        now = datetime.now(timezone.utc)
        return f"INV-{now.year}{now.month:02d}{now.day:02d}-{now.strftime('%H%M%S')}"
