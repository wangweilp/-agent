"""Workspace account entitlement bootstrap helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.adapters.auth_store import SQLiteAuthStore
from src.adapters.billing_store import BillingStoreAdapter
from src.adapters.subscription_store import SubscriptionStoreAdapter
from src.adapters.tenant_store import TenantStoreAdapter
from src.core.billing import BillingAccount, Currency
from src.core.subscription import BillingCycle, PlanTier, Subscription, SubscriptionStatus
from src.core.tenant import OrganizationSize, Tenant, TenantMember, TenantStatus


@dataclass(frozen=True)
class EntitlementBootstrapResult:
    tenants_created: int = 0
    tenant_members_created: int = 0
    billing_accounts_created: int = 0
    subscriptions_created: int = 0
    subscriptions_updated: int = 0


def _add_years(dt: datetime, years: int) -> datetime:
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:
        return dt.replace(month=2, day=28, year=dt.year + years)


def _workspace_rows(auth_store: SQLiteAuthStore) -> list[dict[str, Any]]:
    rows = auth_store._db.execute(
        "SELECT id, name, owner_id, created_at FROM workspaces ORDER BY created_at ASC"
    ).fetchall()
    workspaces = [dict(row) for row in rows]
    if not any(row["id"] == "default" for row in workspaces):
        owner_row = auth_store._db.execute(
            "SELECT id FROM users ORDER BY is_super_admin DESC, created_at ASC LIMIT 1"
        ).fetchone()
        workspaces.append(
            {
                "id": "default",
                "name": "Default Workspace",
                "owner_id": owner_row["id"] if owner_row else "",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return workspaces


def _workspace_slug(workspace_id: str) -> str:
    return f"workspace-{workspace_id[:12].lower()}"


def ensure_workspace_account_entitlements(
    auth_store: SQLiteAuthStore,
    tenant_store: TenantStoreAdapter,
    subscription_store: SubscriptionStoreAdapter,
    billing_store: BillingStoreAdapter,
    *,
    years: int = 10,
) -> EntitlementBootstrapResult:
    """Ensure existing auth workspaces have tenant and Enterprise entitlements.

    The app uses JWT ``workspace_id`` as the SaaS ``tenant_id`` in current-tenant
    endpoints. Existing local users may have workspaces but no tenant rows, which
    makes /tenants/current and /subscription return 404 after a restart.
    """
    result = EntitlementBootstrapResult()
    now = datetime.now(timezone.utc)
    period_end = _add_years(now, years)

    for ws in _workspace_rows(auth_store):
        workspace_id = ws["id"]
        owner_id = ws["owner_id"]
        owner = auth_store.get_user_by_id(owner_id) if owner_id else None
        owner_email = owner.email if owner else ""

        tenant = tenant_store.get_tenant(workspace_id)
        if tenant is None:
            tenant_store.create_tenant(
                Tenant(
                    id=workspace_id,
                    name=ws["name"] or "Personal Workspace",
                    email=owner_email,
                    slug=_workspace_slug(workspace_id),
                    status=TenantStatus.ACTIVE,
                    owner_user_id=owner_id,
                    org_size=OrganizationSize.ENTERPRISE,
                    metadata={"source": "workspace_entitlement_bootstrap"},
                )
            )
            result = EntitlementBootstrapResult(
                tenants_created=result.tenants_created + 1,
                tenant_members_created=result.tenant_members_created,
                billing_accounts_created=result.billing_accounts_created,
                subscriptions_created=result.subscriptions_created,
                subscriptions_updated=result.subscriptions_updated,
            )

        if owner_id and tenant_store.get_member(workspace_id, owner_id) is None:
            tenant_store.add_member(
                TenantMember(tenant_id=workspace_id, user_id=owner_id, role="owner")
            )
            result = EntitlementBootstrapResult(
                tenants_created=result.tenants_created,
                tenant_members_created=result.tenant_members_created + 1,
                billing_accounts_created=result.billing_accounts_created,
                subscriptions_created=result.subscriptions_created,
                subscriptions_updated=result.subscriptions_updated,
            )

        if billing_store.get_account(workspace_id) is None:
            billing_store.create_account(
                BillingAccount(
                    tenant_id=workspace_id,
                    currency=Currency.CNY,
                    billing_email=owner_email,
                )
            )
            result = EntitlementBootstrapResult(
                tenants_created=result.tenants_created,
                tenant_members_created=result.tenant_members_created,
                billing_accounts_created=result.billing_accounts_created + 1,
                subscriptions_created=result.subscriptions_created,
                subscriptions_updated=result.subscriptions_updated,
            )

        subscription = subscription_store.get_subscription(workspace_id)
        if subscription is None:
            subscription_store.create_subscription(
                Subscription(
                    tenant_id=workspace_id,
                    plan_tier=PlanTier.ENTERPRISE,
                    status=SubscriptionStatus.ACTIVE,
                    billing_cycle=BillingCycle.YEARLY,
                    current_period_start=now,
                    current_period_end=period_end,
                    auto_renew=False,
                    coupon_code="TEN_YEAR_ENTERPRISE",
                )
            )
            result = EntitlementBootstrapResult(
                tenants_created=result.tenants_created,
                tenant_members_created=result.tenant_members_created,
                billing_accounts_created=result.billing_accounts_created,
                subscriptions_created=result.subscriptions_created + 1,
                subscriptions_updated=result.subscriptions_updated,
            )
        else:
            needs_update = (
                subscription.plan_tier != PlanTier.ENTERPRISE
                or subscription.status != SubscriptionStatus.ACTIVE
                or subscription.current_period_end is None
                or subscription.current_period_end < period_end
            )
            if needs_update:
                subscription.plan_tier = PlanTier.ENTERPRISE
                subscription.status = SubscriptionStatus.ACTIVE
                subscription.billing_cycle = BillingCycle.YEARLY
                subscription.current_period_end = period_end
                subscription.trial_start = None
                subscription.trial_end = None
                subscription.canceled_at = None
                subscription.auto_renew = False
                subscription.coupon_code = subscription.coupon_code or "TEN_YEAR_ENTERPRISE"
                subscription_store.update_subscription(subscription)
                result = EntitlementBootstrapResult(
                    tenants_created=result.tenants_created,
                    tenant_members_created=result.tenant_members_created,
                    billing_accounts_created=result.billing_accounts_created,
                    subscriptions_created=result.subscriptions_created,
                    subscriptions_updated=result.subscriptions_updated + 1,
                )

    return result
