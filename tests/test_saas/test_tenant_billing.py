"""Tenant Billing Service + RBAC Service 测试。"""

from __future__ import annotations

import os, tempfile, pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
from src.adapters.config import Settings
from src.adapters.billing_store import BillingStoreAdapter
from src.adapters.subscription_store import SubscriptionStoreAdapter
from src.adapters.usage_store import UsageStoreAdapter
from src.open_platform.saas_billing_service import SaaSBillingService
from src.open_platform.rbac_service import RBACService


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")

@pytest.fixture
def db():
    d = tempfile.mkdtemp(); p = os.path.join(d, "test_billing.db"); yield p
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def billing_db():
    d = tempfile.mkdtemp(); p = os.path.join(d, "test_billing_only.db"); yield p
    import shutil; shutil.rmtree(d, ignore_errors=True)
@pytest.fixture
def sub_db():
    d = tempfile.mkdtemp(); p = os.path.join(d, "test_sub_only.db"); yield p
    import shutil; shutil.rmtree(d, ignore_errors=True)
@pytest.fixture
def usage_db():
    d = tempfile.mkdtemp(); p = os.path.join(d, "test_usage_only.db"); yield p
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def billing_store(settings, billing_db): return BillingStoreAdapter(settings, db_path=billing_db)

@pytest.fixture
def subscription_store(settings, sub_db): return SubscriptionStoreAdapter(settings, db_path=sub_db)

@pytest.fixture
def usage_store(settings, usage_db): return UsageStoreAdapter(settings, db_path=usage_db)

@pytest.fixture
def billing_service(billing_store, subscription_store, usage_store):
    return SaaSBillingService(
        billing_store=billing_store, subscription_store=subscription_store,
        usage_store=usage_store)


class TestSubscription:
    def test_create_free_subscription(self, billing_service):
        r = billing_service.create_subscription("tenant-1", "free")
        assert r["created"] is True
        assert r["subscription"]["plan_tier"] == "free"
        assert r["subscription"]["status"] == "trial"

    def test_get_subscription(self, billing_service):
        billing_service.create_subscription("tenant-1", "free")
        sub = billing_service.get_subscription("tenant-1")
        assert sub is not None
        assert sub["plan_tier"] == "free"

    def test_duplicate_create_returns_existing(self, billing_service):
        billing_service.create_subscription("tenant-1", "free")
        r = billing_service.create_subscription("tenant-1", "professional")
        assert r["created"] is False

    def test_change_plan(self, billing_service):
        billing_service.create_subscription("tenant-1", "free")
        r = billing_service.change_plan("tenant-1", "professional")
        assert "error" not in r
        assert r["subscription"]["plan_tier"] == "professional"

    def test_cancel_subscription(self, billing_service):
        billing_service.create_subscription("tenant-1", "free")
        r = billing_service.cancel_subscription("tenant-1")
        assert "error" not in r


class TestQuota:
    def test_check_quota_free(self, billing_service):
        billing_service.create_subscription("tenant-1", "free")
        r = billing_service.check_quota("tenant-1", "agent_module")
        assert r["allowed"] is True
        assert r["tier"] == "free"

    def test_quota_summary(self, billing_service):
        billing_service.create_subscription("tenant-1", "professional")
        summary = billing_service.get_quota_summary("tenant-1")
        assert summary["plan_tier"] == "professional"
        assert "quotas" in summary
        assert "features" in summary
        assert summary["features"]["api_access"] is True

    def test_quota_summary_no_subscription(self, billing_service):
        summary = billing_service.get_quota_summary("nonexistent")
        assert summary["plan_tier"] == "free"


class TestBilling:
    def test_generate_invoice(self, billing_service):
        billing_service.create_subscription("tenant-1", "professional")
        r = billing_service.generate_invoice("tenant-1", 9900, "cny", "Monthly Pro")
        assert "error" not in r
        assert r["amount"] == 9900

    def test_record_payment(self, billing_service):
        billing_service.create_subscription("tenant-1", "professional")
        inv = billing_service.generate_invoice("tenant-1", 9900, "cny", "Pro")
        r = billing_service.record_payment(
            "tenant-1", inv["id"], 9900, "stripe", "pi_test_123")
        assert "error" not in r
        assert r["provider"] == "stripe"

    def test_payment_nonexistent_invoice(self, billing_service):
        r = billing_service.record_payment(
            "tenant-1", "inv_nonexistent", 1000)
        assert "error" in r


class TestBillingWithoutStores:
    def test_create_subscription_no_store(self):
        svc = SaaSBillingService()
        r = svc.create_subscription("t1")
        assert "error" in r

    def test_generate_invoice_no_store(self):
        svc = SaaSBillingService()
        r = svc.generate_invoice("t1", 100)
        assert "error" in r

    def test_record_payment_no_store(self):
        svc = SaaSBillingService()
        r = svc.record_payment("t1", "inv", 100)
        assert "error" in r


class TestRBACService:
    @pytest.fixture
    def rbac(self): return RBACService()

    def test_check_permission_owner(self, rbac):
        assert rbac.check_permission("owner", "artifact", "create") is True
        assert rbac.check_permission("owner", "artifact", "publish") is True
        assert rbac.check_permission("owner", "marketplace", "subscribe") is True

    def test_check_permission_admin(self, rbac):
        assert rbac.check_permission("admin", "artifact", "create") is True
        assert rbac.check_permission("admin", "artifact", "delete") is False
        assert rbac.check_permission("admin", "billing", "manage") is False

    def test_check_permission_member(self, rbac):
        assert rbac.check_permission("member", "artifact", "create") is True
        assert rbac.check_permission("member", "artifact", "approve") is False
        assert rbac.check_permission("member", "marketplace", "subscribe") is True

    def test_check_permission_viewer(self, rbac):
        assert rbac.check_permission("viewer", "artifact", "read") is True
        assert rbac.check_permission("viewer", "artifact", "create") is False
        assert rbac.check_permission("viewer", "marketplace", "subscribe") is False

    def test_invalid_role(self, rbac):
        assert rbac.check_permission("hacker", "artifact", "read") is False

    def test_invalid_resource(self, rbac):
        assert rbac.check_permission("admin", "nonexistent", "read") is False

    def test_get_role_permissions(self, rbac):
        perms = rbac.get_role_permissions("owner")
        assert "artifact" in perms
        assert "create" in perms["artifact"]

    def test_get_role_permissions_invalid(self, rbac):
        assert rbac.get_role_permissions("nobody") == {}

    def test_get_permission_matrix(self, rbac):
        matrix = rbac.get_permission_matrix()
        assert "owner" in matrix
        assert "admin" in matrix
        assert "member" in matrix
        assert "viewer" in matrix
        for role in ["owner", "admin", "member", "viewer"]:
            assert "artifact" in matrix[role]
            assert "marketplace" in matrix[role]

    def test_list_roles(self, rbac):
        assert sorted(rbac.list_roles()) == sorted(["owner", "admin", "member", "viewer"])

    def test_list_resources(self, rbac):
        resources = rbac.list_resources()
        assert "artifact" in resources
        assert "marketplace" in resources
        assert "billing" in resources

    def test_list_actions(self, rbac):
        actions = rbac.list_actions()
        assert "create" in actions
        assert "read" in actions
        assert "publish" in actions

    def test_assign_role(self, rbac):
        r = rbac.assign_role("user-1", "ws-1", "admin")
        assert r["assigned"] is True
        assert r["role"] == "admin"

    def test_assign_invalid_role(self, rbac):
        r = rbac.assign_role("user-1", "ws-1", "superuser")
        assert "error" in r

    def test_revoke_role(self, rbac):
        r = rbac.revoke_role("user-1", "ws-1")
        assert r["revoked"] is True
