from datetime import datetime, timezone

from src.adapters.auth_store import SQLiteAuthStore
from src.adapters.billing_store import BillingStoreAdapter
from src.adapters.config import Settings
from src.adapters.subscription_store import SubscriptionStoreAdapter
from src.adapters.tenant_store import TenantStoreAdapter
from src.core.account_entitlements import ensure_workspace_account_entitlements
from src.core.subscription import PlanTier, SubscriptionStatus


def test_workspace_gets_tenant_and_ten_year_enterprise_subscription(tmp_path):
    db_path = str(tmp_path / "account.db")
    settings = Settings(deepseek_api_key="sk-test", sqlite_db_path=db_path)
    auth_store = SQLiteAuthStore(settings, db_path=db_path)
    tenant_store = TenantStoreAdapter(settings, db_path=db_path)
    subscription_store = SubscriptionStoreAdapter(settings, db_path=db_path)
    billing_store = BillingStoreAdapter(settings, db_path=db_path)

    user = auth_store.create_user(
        email="owner@example.com",
        name="Owner",
        hashed_password="x",
        is_super_admin=True,
    )
    workspace = auth_store.create_workspace("Owner Workspace", owner_id=user.id)

    result = ensure_workspace_account_entitlements(
        auth_store=auth_store,
        tenant_store=tenant_store,
        subscription_store=subscription_store,
        billing_store=billing_store,
    )

    tenant = tenant_store.get_tenant(workspace.id)
    subscription = subscription_store.get_subscription(workspace.id)
    account = billing_store.get_account(workspace.id)
    member = tenant_store.get_member(workspace.id, user.id)

    default_subscription = subscription_store.get_subscription("default")

    assert result.tenants_created == 2
    assert tenant is not None
    assert tenant.id == workspace.id
    assert tenant.owner_user_id == user.id
    assert member is not None
    assert member.role == "owner"
    assert account is not None
    assert account.billing_email == "owner@example.com"
    assert subscription is not None
    assert subscription.plan_tier == PlanTier.ENTERPRISE
    assert subscription.status == SubscriptionStatus.ACTIVE
    assert subscription.current_period_end is not None
    assert subscription.current_period_end.year >= datetime.now(timezone.utc).year + 10
    assert default_subscription is not None
    assert default_subscription.plan_tier == PlanTier.ENTERPRISE
    assert default_subscription.status == SubscriptionStatus.ACTIVE
