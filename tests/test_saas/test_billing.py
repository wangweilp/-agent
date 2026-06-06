"""Billing/SaaS 测试套件 — 覆盖 domain models, BillingStoreAdapter, PaymentGateway, 和 billing API 端点。

覆盖范围:
    - BillingAccount / Invoice / Payment / Refund 域模型
    - BillingStoreAdapter SQLite CRUD (account, invoice, payment, refund)
    - PaymentGatewayRegistry 与各 provider gateway
    - billing_router HTTP 端点 (account, payment-intent, invoices, payments, refunds, webhook, admin)
    - 边界情况: not found, invalid status, 权限, 重复请求
"""
import json
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adapters.auth_store import SQLiteAuthStore, WorkspaceContext
from src.adapters.billing_store import BillingStoreAdapter
from src.adapters.config import Settings
from src.adapters.payment_gateway import (
    AlipayPaymentGateway,
    BasePaymentGateway,
    PaymentGatewayRegistry,
    StripePaymentGateway,
    WechatPaymentGateway,
)
from src.api.billing_router import create_billing_router
from src.api.middleware import JWTTokenService, init_auth, require_auth, require_manage
from src.core.auth import TokenPayload, User, WorkspaceRole
from src.core.billing import (
    BillingAccount,
    BillingStore,
    Currency,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentIntent,
    PaymentProvider,
    PaymentStatus,
    Refund,
    RefundStatus,
)


# ── Helpers ──

def _make_token(token_service: JWTTokenService, tenant_id: str, role: WorkspaceRole) -> str:
    """创建一个有效 JWT 供测试用。"""
    user = User(email=f"test@{tenant_id}.com", name="Tester")
    tokens = token_service.create_tokens(user, tenant_id, role)
    return tokens.access_token


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ──


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test-billing")


@pytest.fixture
def billing_store(settings):
    store = BillingStoreAdapter(settings, db_path=":memory:")
    yield store
    store.close()


@pytest.fixture
def payment_gateway():
    return PaymentGatewayRegistry()


@pytest.fixture
def token_service():
    return JWTTokenService()


@pytest.fixture
def auth_store(settings):
    store = SQLiteAuthStore(settings, db_path=":memory:")
    yield store
    store.close()


@pytest.fixture
def client(billing_store, payment_gateway, token_service, auth_store):
    """创建带认证和 billing router 的 TestClient。"""
    init_auth(token_service, auth_store)
    app = FastAPI()
    app.include_router(create_billing_router(billing_store, payment_gateway))
    return TestClient(app)


@pytest.fixture
def owner_token(token_service):
    return _make_token(token_service, "ws-owner", WorkspaceRole.OWNER)


@pytest.fixture
def admin_token(token_service):
    return _make_token(token_service, "ws-admin", WorkspaceRole.ADMIN)


@pytest.fixture
def member_token(token_service):
    return _make_token(token_service, "ws-member", WorkspaceRole.MEMBER)


# ──────────────────────────────────────────────────────────────
# Test: Domain Models
# ──────────────────────────────────────────────────────────────


class TestDomainModels:
    """验证域模型构造和默认值。"""

    def test_billing_account_defaults(self):
        account = BillingAccount(tenant_id="t1")
        assert account.tenant_id == "t1"
        assert account.currency == Currency.CNY
        assert account.balance == 0
        assert account.credit_limit == 0
        assert account.billing_email == ""
        assert isinstance(account.created_at, datetime)

    def test_invoice_defaults(self):
        inv = Invoice(tenant_id="t1", billing_account_id="ba1", amount=1000)
        assert inv.status == InvoiceStatus.DRAFT
        assert inv.currency == Currency.CNY
        assert inv.line_items == []
        assert isinstance(inv.created_at, datetime)

    def test_payment_defaults(self):
        payment = Payment(tenant_id="t1", billing_account_id="ba1", invoice_id=None, amount=5000)
        assert payment.provider == PaymentProvider.WECHAT
        assert payment.status == PaymentStatus.PENDING
        assert payment.metadata == {}

    def test_refund_defaults(self):
        refund = Refund(tenant_id="t1", payment_id="p1", amount=1000)
        assert refund.status == RefundStatus.PENDING
        assert refund.reason == ""

    def test_payment_intent_defaults(self):
        intent = PaymentIntent(tenant_id="t1", amount=2000)
        assert intent.provider == PaymentProvider.WECHAT
        assert intent.currency == Currency.CNY
        assert isinstance(intent.created_at, datetime)


# ──────────────────────────────────────────────────────────────
# Test: BillingStore — Account CRUD
# ──────────────────────────────────────────────────────────────


class TestBillingAccountStore:
    """BillingAccount 存储 CRUD 测试。"""

    def test_create_account(self, billing_store):
        account = BillingAccount(tenant_id="acc-1", currency=Currency.USD)
        result = billing_store.create_account(account)
        assert result.tenant_id == "acc-1"
        assert result.currency == Currency.USD

    def test_get_account_found(self, billing_store):
        billing_store.create_account(BillingAccount(tenant_id="acc-2"))
        acct = billing_store.get_account("acc-2")
        assert acct is not None
        assert acct.tenant_id == "acc-2"

    def test_get_account_not_found(self, billing_store):
        assert billing_store.get_account("nonexistent") is None

    def test_update_account(self, billing_store):
        acct = billing_store.create_account(BillingAccount(tenant_id="acc-3", balance=0))
        acct.balance = 50000
        acct.billing_email = "test@example.com"
        billing_store.update_account(acct)

        reloaded = billing_store.get_account("acc-3")
        assert reloaded is not None
        assert reloaded.balance == 50000
        assert reloaded.billing_email == "test@example.com"

    def test_create_duplicate_tenant_overwrites(self, billing_store):
        """相同 tenant_id 的第二次 create 会因 UNIQUE 约束失败。"""
        billing_store.create_account(BillingAccount(tenant_id="dup"))
        with pytest.raises(Exception):
            billing_store.create_account(BillingAccount(tenant_id="dup"))


# ──────────────────────────────────────────────────────────────
# Test: BillingStore — Invoice CRUD
# ──────────────────────────────────────────────────────────────


class TestInvoiceStore:
    """Invoice 存储 CRUD 测试。"""

    def test_create_invoice_auto_number(self, billing_store):
        billing_store.create_account(BillingAccount(tenant_id="inv-t"))
        inv = Invoice(
            tenant_id="inv-t", billing_account_id="ba-x", amount=9900,
            description="月度订阅费",
        )
        result = billing_store.create_invoice(inv)
        assert result.invoice_number != ""
        assert result.status == InvoiceStatus.DRAFT

    def test_get_invoice_found(self, billing_store):
        billing_store.create_account(BillingAccount(tenant_id="inv-t2"))
        inv = billing_store.create_invoice(Invoice(
            tenant_id="inv-t2", billing_account_id="ba-x", amount=100,
        ))
        retrieved = billing_store.get_invoice(inv.id)
        assert retrieved is not None
        assert retrieved.amount == 100

    def test_get_invoice_not_found(self, billing_store):
        assert billing_store.get_invoice("no-such-inv") is None

    def test_list_invoices_by_tenant(self, billing_store):
        billing_store.create_account(BillingAccount(tenant_id="list-t"))
        for _ in range(3):
            billing_store.create_invoice(Invoice(
                tenant_id="list-t", billing_account_id="ba-x", amount=500,
            ))
        invoices = billing_store.list_invoices("list-t")
        assert len(invoices) == 3

    def test_list_invoices_by_status(self, billing_store):
        billing_store.create_account(BillingAccount(tenant_id="status-t"))
        i1 = billing_store.create_invoice(Invoice(
            tenant_id="status-t", billing_account_id="ba-x", amount=100,
        ))
        billing_store.create_invoice(Invoice(
            tenant_id="status-t", billing_account_id="ba-x", amount=200,
        ))
        # Mark first as paid
        i1.status = InvoiceStatus.PAID
        billing_store.update_invoice(i1)

        paid = billing_store.list_invoices("status-t", status="paid")
        assert len(paid) == 1
        assert paid[0].status == InvoiceStatus.PAID

    def test_update_invoice_status(self, billing_store):
        billing_store.create_account(BillingAccount(tenant_id="upd-t"))
        inv = billing_store.create_invoice(Invoice(
            tenant_id="upd-t", billing_account_id="ba-x", amount=300,
        ))
        inv.status = InvoiceStatus.VOID
        billing_store.update_invoice(inv)

        reloaded = billing_store.get_invoice(inv.id)
        assert reloaded is not None
        assert reloaded.status == InvoiceStatus.VOID

    def test_invoice_with_line_items(self, billing_store):
        billing_store.create_account(BillingAccount(tenant_id="items-t"))
        inv = Invoice(
            tenant_id="items-t", billing_account_id="ba-x", amount=1500,
            line_items=[
                {"description": "API调用", "quantity": 1000, "unit_amount": 1, "amount": 1000},
                {"description": "存储", "quantity": 5, "unit_amount": 100, "amount": 500},
            ],
        )
        result = billing_store.create_invoice(inv)
        retrieved = billing_store.get_invoice(result.id)
        assert retrieved is not None
        assert len(retrieved.line_items) == 2
        assert retrieved.line_items[0]["description"] == "API调用"


# ──────────────────────────────────────────────────────────────
# Test: BillingStore — Payment CRUD
# ──────────────────────────────────────────────────────────────


class TestPaymentStore:
    """Payment 存储 CRUD 测试。"""

    def test_create_payment(self, billing_store):
        billing_store.create_account(BillingAccount(tenant_id="pay-t"))
        payment = Payment(
            tenant_id="pay-t", billing_account_id="ba-x", invoice_id=None,
            amount=5000, provider=PaymentProvider.ALIPAY,
            description="充值",
        )
        result = billing_store.create_payment(payment)
        assert result.provider == PaymentProvider.ALIPAY
        assert result.status == PaymentStatus.PENDING

    def test_get_payment_found(self, billing_store):
        billing_store.create_account(BillingAccount(tenant_id="pay-t2"))
        payment = billing_store.create_payment(Payment(
            tenant_id="pay-t2", billing_account_id="ba-x", invoice_id=None, amount=100,
        ))
        result = billing_store.get_payment(payment.id)
        assert result is not None
        assert result.amount == 100

    def test_get_payment_not_found(self, billing_store):
        assert billing_store.get_payment("no-such-payment") is None

    def test_list_payments_by_tenant(self, billing_store):
        billing_store.create_account(BillingAccount(tenant_id="pay-list"))
        for _ in range(2):
            billing_store.create_payment(Payment(
                tenant_id="pay-list", billing_account_id="ba-x", invoice_id=None, amount=200,
            ))
        payments = billing_store.list_payments("pay-list")
        assert len(payments) == 2

    def test_update_payment_status(self, billing_store):
        billing_store.create_account(BillingAccount(tenant_id="pay-upd"))
        payment = billing_store.create_payment(Payment(
            tenant_id="pay-upd", billing_account_id="ba-x", invoice_id=None, amount=300,
        ))
        payment.status = PaymentStatus.SUCCEEDED
        payment.provider_payment_id = "wx_abc123"
        billing_store.update_payment(payment)

        reloaded = billing_store.get_payment(payment.id)
        assert reloaded is not None
        assert reloaded.status == PaymentStatus.SUCCEEDED
        assert reloaded.provider_payment_id == "wx_abc123"

    def test_payment_with_metadata(self, billing_store):
        billing_store.create_account(BillingAccount(tenant_id="pay-meta"))
        payment = Payment(
            tenant_id="pay-meta", billing_account_id="ba-x", invoice_id=None, amount=100,
            metadata={"ip": "1.2.3.4", "coupon_code": "SAVE10"},
        )
        result = billing_store.create_payment(payment)
        reloaded = billing_store.get_payment(result.id)
        assert reloaded is not None
        assert reloaded.metadata["coupon_code"] == "SAVE10"


# ──────────────────────────────────────────────────────────────
# Test: BillingStore — Refund CRUD
# ──────────────────────────────────────────────────────────────


class TestRefundStore:
    """Refund 存储 CRUD 测试。"""

    def test_create_refund(self, billing_store):
        billing_store.create_account(BillingAccount(tenant_id="ref-t"))
        payment = billing_store.create_payment(Payment(
            tenant_id="ref-t", billing_account_id="ba-x", invoice_id=None, amount=1000,
        ))
        refund = Refund(
            tenant_id="ref-t", payment_id=payment.id, amount=1000,
            reason="客户请求退款",
        )
        result = billing_store.create_refund(refund)
        assert result.status == RefundStatus.PENDING
        assert result.reason == "客户请求退款"

    def test_get_refund_found(self, billing_store):
        billing_store.create_account(BillingAccount(tenant_id="ref-t2"))
        payment = billing_store.create_payment(Payment(
            tenant_id="ref-t2", billing_account_id="ba-x", invoice_id=None, amount=500,
        ))
        refund = billing_store.create_refund(Refund(
            tenant_id="ref-t2", payment_id=payment.id, amount=500,
        ))
        result = billing_store.get_refund(refund.id)
        assert result is not None
        assert result.amount == 500

    def test_get_refund_not_found(self, billing_store):
        assert billing_store.get_refund("no-such-refund") is None

    def test_list_refunds_by_tenant(self, billing_store):
        billing_store.create_account(BillingAccount(tenant_id="ref-list"))
        payment = billing_store.create_payment(Payment(
            tenant_id="ref-list", billing_account_id="ba-x", invoice_id=None, amount=1000,
        ))
        billing_store.create_refund(Refund(
            tenant_id="ref-list", payment_id=payment.id, amount=300,
        ))
        billing_store.create_refund(Refund(
            tenant_id="ref-list", payment_id=payment.id, amount=700,
        ))
        refunds = billing_store.list_refunds("ref-list")
        assert len(refunds) == 2


# ──────────────────────────────────────────────────────────────
# Test: Payment Gateways
# ──────────────────────────────────────────────────────────────


class TestPaymentGatewayProviders:
    """各支付网关 provider 的单元测试。"""

    def test_wechat_create_intent(self):
        gateway = WechatPaymentGateway()
        intent = gateway.create_payment_intent(
            amount=1000, currency="cny", description="测试商品",
            metadata={"tenant_id": "t1"},
        )
        assert intent.provider == PaymentProvider.WECHAT
        assert intent.amount == 1000
        assert intent.client_secret != ""
        assert "weixin" in intent.qr_code_url or intent.qr_code_url.startswith("weixin://")

    def test_alipay_create_intent(self):
        gateway = AlipayPaymentGateway()
        intent = gateway.create_payment_intent(
            amount=2000, currency="cny", description="测试商品",
            metadata={"tenant_id": "t2"},
        )
        assert intent.provider == PaymentProvider.ALIPAY
        assert intent.amount == 2000
        assert intent.client_secret.startswith("ali")

    def test_stripe_create_intent(self):
        gateway = StripePaymentGateway()
        intent = gateway.create_payment_intent(
            amount=3000, currency="usd", description="Test Product",
            metadata={"tenant_id": "t3"},
        )
        assert intent.provider == PaymentProvider.STRIPE
        assert intent.amount == 3000
        assert intent.currency == Currency.USD
        assert intent.client_secret.startswith("pi_")

    def test_wechat_refund(self):
        gateway = WechatPaymentGateway()
        refund = gateway.create_refund("wx_pay_123", 500, "重复支付")
        assert refund.status == RefundStatus.SUCCEEDED
        assert refund.amount == 500

    def test_wechat_webhook(self):
        gateway = WechatPaymentGateway()
        result = gateway.handle_webhook({"event_type": "TRANSACTION.SUCCESS", "resource": {}})
        assert result["code"] == "SUCCESS"

    def test_alipay_webhook(self):
        gateway = AlipayPaymentGateway()
        result = gateway.handle_webhook({"notify_type": "trade_status_sync"})
        assert result["code"] == "10000"

    def test_stripe_webhook(self):
        gateway = StripePaymentGateway()
        result = gateway.handle_webhook({"type": "payment_intent.succeeded"})
        assert result["received"] is True

    def test_confirm_payment_returns_succeeded(self):
        for gateway_cls in [WechatPaymentGateway, AlipayPaymentGateway, StripePaymentGateway]:
            gateway = gateway_cls()
            payment = gateway.confirm_payment("test_payment_id")
            assert payment.status == PaymentStatus.SUCCEEDED


class TestPaymentGatewayRegistry:
    """PaymentGatewayRegistry 集成测试。"""

    def test_registry_get_wechat(self, payment_gateway):
        gw = payment_gateway.get(PaymentProvider.WECHAT)
        assert isinstance(gw, WechatPaymentGateway)

    def test_registry_get_alipay(self, payment_gateway):
        gw = payment_gateway.get(PaymentProvider.ALIPAY)
        assert isinstance(gw, AlipayPaymentGateway)

    def test_registry_get_stripe(self, payment_gateway):
        gw = payment_gateway.get(PaymentProvider.STRIPE)
        assert isinstance(gw, StripePaymentGateway)

    def test_registry_get_invalid(self, payment_gateway):
        with pytest.raises(ValueError, match="Unsupported"):
            payment_gateway.get(PaymentProvider.MANUAL)

    def test_registry_create_intent(self, payment_gateway):
        intent = payment_gateway.create_intent(
            provider=PaymentProvider.WECHAT, amount=999,
            currency="cny", description="test",
        )
        assert intent.provider == PaymentProvider.WECHAT
        assert intent.amount == 999

    def test_registry_handle_webhook(self, payment_gateway):
        result = payment_gateway.handle_webhook(
            PaymentProvider.WECHAT, {"event_type": "test"},
        )
        assert result["code"] == "SUCCESS"


# ──────────────────────────────────────────────────────────────
# Test: Billing API — Account
# ──────────────────────────────────────────────────────────────


class TestBillingAccountAPI:
    """GET /billing/account 端点测试。"""

    def test_get_account_creates_if_missing(self, client, owner_token):
        res = client.get("/billing/account", headers=_auth_headers(owner_token))
        assert res.status_code == 200
        data = res.json()
        assert data["tenant_id"] == "ws-owner"
        assert data["currency"] == "cny"
        assert data["balance"] == 0

    def test_get_account_unauthorized(self, client):
        res = client.get("/billing/account")
        assert res.status_code == 401

    def test_get_account_idempotent(self, client, owner_token):
        """再次请求返回同一账户。"""
        r1 = client.get("/billing/account", headers=_auth_headers(owner_token))
        r2 = client.get("/billing/account", headers=_auth_headers(owner_token))
        assert r1.json()["id"] == r2.json()["id"]


# ──────────────────────────────────────────────────────────────
# Test: Billing API — Payment Intent
# ──────────────────────────────────────────────────────────────


class TestPaymentIntentAPI:
    """POST /billing/payment-intent 端点测试。"""

    def test_create_payment_intent_wechat(self, client, owner_token):
        res = client.post("/billing/payment-intent", json={
            "amount": 1000, "provider": "wechat", "currency": "cny",
        }, headers=_auth_headers(owner_token))
        assert res.status_code == 200
        data = res.json()
        assert data["provider"] == "wechat"
        assert data["amount"] == 1000
        assert data["client_secret"] != ""

    def test_create_payment_intent_alipay(self, client, owner_token):
        res = client.post("/billing/payment-intent", json={
            "amount": 2000, "provider": "alipay", "currency": "cny",
        }, headers=_auth_headers(owner_token))
        assert res.status_code == 200
        data = res.json()
        assert data["provider"] == "alipay"

    def test_create_payment_intent_stripe(self, client, owner_token):
        res = client.post("/billing/payment-intent", json={
            "amount": 3000, "provider": "stripe", "currency": "usd",
        }, headers=_auth_headers(owner_token))
        assert res.status_code == 200
        data = res.json()
        assert data["provider"] == "stripe"
        assert data["currency"] == "usd"

    def test_create_payment_intent_invalid_provider(self, client, owner_token):
        res = client.post("/billing/payment-intent", json={
            "amount": 1000, "provider": "bitcoin",
        }, headers=_auth_headers(owner_token))
        assert res.status_code == 400

    def test_create_payment_intent_unauthorized(self, client):
        res = client.post("/billing/payment-intent", json={
            "amount": 1000, "provider": "wechat",
        })
        assert res.status_code == 401

    def test_create_payment_intent_validation(self, client, owner_token):
        """amount 必须 > 0。"""
        res = client.post("/billing/payment-intent", json={
            "amount": 0, "provider": "wechat",
        }, headers=_auth_headers(owner_token))
        assert res.status_code == 422


# ──────────────────────────────────────────────────────────────
# Test: Billing API — Invoices
# ──────────────────────────────────────────────────────────────


class TestInvoiceAPI:
    """GET /billing/invoices 和 /billing/invoices/{id} 端点测试。"""

    def _ensure_account(self, billing_store, tenant_id: str):
        if billing_store.get_account(tenant_id) is None:
            billing_store.create_account(BillingAccount(tenant_id=tenant_id))

    def _create_invoice(self, billing_store, tenant_id: str, amount: int = 1000, status: InvoiceStatus = InvoiceStatus.DRAFT):
        self._ensure_account(billing_store, tenant_id)
        return billing_store.create_invoice(Invoice(
            tenant_id=tenant_id, billing_account_id="ba-test", amount=amount, status=status,
        ))

    def test_list_invoices_empty(self, client, member_token):
        res = client.get("/billing/invoices", headers=_auth_headers(member_token))
        assert res.status_code == 200
        assert res.json() == []

    def test_list_invoices_with_data(self, client, billing_store, owner_token):
        self._create_invoice(billing_store, "ws-owner", amount=500)
        self._create_invoice(billing_store, "ws-owner", amount=1500)
        res = client.get("/billing/invoices", headers=_auth_headers(owner_token))
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2

    def test_list_invoices_status_filter(self, client, billing_store, owner_token):
        self._create_invoice(billing_store, "ws-owner", amount=100, status=InvoiceStatus.PAID)
        self._create_invoice(billing_store, "ws-owner", amount=200, status=InvoiceStatus.DRAFT)
        res = client.get("/billing/invoices?status=paid", headers=_auth_headers(owner_token))
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["status"] == "paid"

    def test_get_invoice_by_id(self, client, billing_store, owner_token):
        inv = self._create_invoice(billing_store, "ws-owner", amount=999)
        res = client.get(f"/billing/invoices/{inv.id}", headers=_auth_headers(owner_token))
        assert res.status_code == 200
        assert res.json()["amount"] == 999

    def test_get_invoice_not_found(self, client, owner_token):
        res = client.get("/billing/invoices/no-such-id", headers=_auth_headers(owner_token))
        assert res.status_code == 404

    def test_get_invoice_other_tenant(self, client, billing_store, owner_token, member_token):
        """跨租户访问发票应返回 404。"""
        inv = self._create_invoice(billing_store, "ws-owner", amount=500)
        # member_token uses "ws-member" tenant
        res = client.get(f"/billing/invoices/{inv.id}", headers=_auth_headers(member_token))
        assert res.status_code == 404

    def test_list_invoices_unauthorized(self, client):
        res = client.get("/billing/invoices")
        assert res.status_code == 401


# ──────────────────────────────────────────────────────────────
# Test: Billing API — Payments
# ──────────────────────────────────────────────────────────────


class TestPaymentAPI:
    """GET /billing/payments 端点测试。"""

    def _create_payment(self, billing_store, tenant_id: str, amount: int = 500):
        if billing_store.get_account(tenant_id) is None:
            billing_store.create_account(BillingAccount(tenant_id=tenant_id))
        return billing_store.create_payment(Payment(
            tenant_id=tenant_id, billing_account_id="ba-test", invoice_id=None, amount=amount,
        ))

    def test_list_payments_empty(self, client, member_token):
        res = client.get("/billing/payments", headers=_auth_headers(member_token))
        assert res.status_code == 200
        assert res.json() == []

    def test_list_payments_with_data(self, client, billing_store, owner_token):
        self._create_payment(billing_store, "ws-owner", amount=1000)
        self._create_payment(billing_store, "ws-owner", amount=2000)
        res = client.get("/billing/payments", headers=_auth_headers(owner_token))
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2

    def test_list_payments_unauthorized(self, client):
        res = client.get("/billing/payments")
        assert res.status_code == 401


# ──────────────────────────────────────────────────────────────
# Test: Billing API — Refund
# ──────────────────────────────────────────────────────────────


class TestRefundAPI:
    """POST /billing/payments/{id}/refund 和 GET /billing/refunds 端点测试。"""

    def _create_payment(self, billing_store, tenant_id: str, amount: int = 1000,
                        provider: PaymentProvider = PaymentProvider.WECHAT):
        if billing_store.get_account(tenant_id) is None:
            billing_store.create_account(BillingAccount(tenant_id=tenant_id))
        return billing_store.create_payment(Payment(
            tenant_id=tenant_id, billing_account_id="ba-test", invoice_id=None,
            amount=amount, provider=provider,
            provider_payment_id=f"wx_test_{tenant_id}",
        ))

    def test_full_refund(self, client, billing_store, owner_token):
        payment = self._create_payment(billing_store, "ws-owner", amount=2000)
        res = client.post(
            f"/billing/payments/{payment.id}/refund",
            json={"amount": 2000, "reason": "不满意"},
            headers=_auth_headers(owner_token),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["amount"] == 2000
        assert data["status"] in ("succeeded", "pending")

    def test_partial_refund(self, client, billing_store, owner_token):
        payment = self._create_payment(billing_store, "ws-owner", amount=5000)
        res = client.post(
            f"/billing/payments/{payment.id}/refund",
            json={"amount": 2000, "reason": "多付"},
            headers=_auth_headers(owner_token),
        )
        assert res.status_code == 200

    def test_refund_payment_not_found(self, client, owner_token):
        res = client.post(
            "/billing/payments/no-such-payment/refund",
            json={"amount": 1000},
            headers=_auth_headers(owner_token),
        )
        assert res.status_code == 404

    def test_refund_amount_exceeds_payment(self, client, billing_store, owner_token):
        payment = self._create_payment(billing_store, "ws-owner", amount=1000)
        res = client.post(
            f"/billing/payments/{payment.id}/refund",
            json={"amount": 2000, "reason": "超额退款"},
            headers=_auth_headers(owner_token),
        )
        assert res.status_code == 400

    def test_refund_already_fully_refunded(self, client, billing_store, owner_token):
        payment = self._create_payment(billing_store, "ws-owner", amount=1000)
        # First refund — full
        client.post(
            f"/billing/payments/{payment.id}/refund",
            json={"amount": 1000},
            headers=_auth_headers(owner_token),
        )
        # Second refund — rejected
        res = client.post(
            f"/billing/payments/{payment.id}/refund",
            json={"amount": 500},
            headers=_auth_headers(owner_token),
        )
        assert res.status_code == 400

    def test_list_refunds(self, client, billing_store, owner_token):
        payment = self._create_payment(billing_store, "ws-owner", amount=3000)
        client.post(
            f"/billing/payments/{payment.id}/refund",
            json={"amount": 1000, "reason": "部分退款"},
            headers=_auth_headers(owner_token),
        )
        res = client.get("/billing/refunds", headers=_auth_headers(owner_token))
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 1

    def test_list_refunds_unauthorized(self, client):
        res = client.get("/billing/refunds")
        assert res.status_code == 401


# ──────────────────────────────────────────────────────────────
# Test: Billing API — Webhook
# ──────────────────────────────────────────────────────────────


class TestWebhookAPI:
    """POST /billing/webhook 端点测试。"""

    def test_wechat_webhook(self, client):
        res = client.post("/billing/webhook", json={
            "provider": "wechat",
            "payload": {"event_type": "TRANSACTION.SUCCESS"},
        })
        assert res.status_code == 200
        assert res.json()["status"] == "success"

    def test_alipay_webhook(self, client):
        res = client.post("/billing/webhook", json={
            "provider": "alipay",
            "payload": {"notify_type": "trade_status_sync"},
        })
        assert res.status_code == 200

    def test_stripe_webhook(self, client):
        res = client.post("/billing/webhook", json={
            "provider": "stripe",
            "payload": {"type": "payment_intent.succeeded"},
        })
        assert res.status_code == 200

    def test_webhook_invalid_provider(self, client):
        res = client.post("/billing/webhook", json={
            "provider": "unknown",
            "payload": {},
        })
        assert res.status_code == 400


# ──────────────────────────────────────────────────────────────
# Test: Billing API — Admin
# ──────────────────────────────────────────────────────────────


class TestAdminAPI:
    """GET /billing/admin/invoices 和 /billing/admin/payments 端点测试。"""

    def _seed(self, billing_store, tenant_id: str):
        billing_store.create_account(BillingAccount(tenant_id=tenant_id))
        billing_store.create_invoice(Invoice(
            tenant_id=tenant_id, billing_account_id="ba-adm", amount=500,
        ))
        billing_store.create_payment(Payment(
            tenant_id=tenant_id, billing_account_id="ba-adm", invoice_id=None, amount=500,
        ))

    def test_admin_list_invoices_owner(self, client, billing_store, owner_token):
        self._seed(billing_store, "ws-owner")
        res = client.get("/billing/admin/invoices", headers=_auth_headers(owner_token))
        assert res.status_code == 200
        assert len(res.json()) >= 1

    def test_admin_list_invoices_admin(self, client, billing_store, admin_token):
        self._seed(billing_store, "ws-admin")
        res = client.get("/billing/admin/invoices", headers=_auth_headers(admin_token))
        assert res.status_code == 200

    def test_admin_list_invoices_member_forbidden(self, client, billing_store, member_token):
        self._seed(billing_store, "ws-member")
        res = client.get("/billing/admin/invoices", headers=_auth_headers(member_token))
        assert res.status_code == 403

    def test_admin_list_payments(self, client, billing_store, owner_token):
        self._seed(billing_store, "ws-owner")
        res = client.get("/billing/admin/payments", headers=_auth_headers(owner_token))
        assert res.status_code == 200
        assert len(res.json()) >= 1

    def test_admin_unauthorized(self, client):
        res = client.get("/billing/admin/invoices")
        assert res.status_code == 401


# ──────────────────────────────────────────────────────────────
# Test: Integration — End-to-End Flow
# ──────────────────────────────────────────────────────────────


class TestBillingIntegration:
    """端到端计费流程测试。"""

    def test_full_billing_flow(self, client, billing_store, owner_token):
        """完整流程: 创建账户 -> 支付意图 -> 发票 -> 退款。"""
        headers = _auth_headers(owner_token)

        # 1. Get/auto-create account
        r_account = client.get("/billing/account", headers=headers)
        assert r_account.status_code == 200
        account = r_account.json()

        # 2. Create payment intent
        r_intent = client.post("/billing/payment-intent", json={
            "amount": 50000, "provider": "wechat", "currency": "cny",
            "description": "年度订阅",
        }, headers=headers)
        assert r_intent.status_code == 200

        # 3. Manual: create a payment record (simulating webhook callback)
        payment = Payment(
            tenant_id="ws-owner",
            billing_account_id=account["id"],
            invoice_id=None,
            amount=50000,
            provider=PaymentProvider.WECHAT,
            status=PaymentStatus.SUCCEEDED,
            provider_payment_id="wx_real_pay_id",
        )
        billing_store.create_payment(payment)

        # 4. List payments
        r_payments = client.get("/billing/payments", headers=headers)
        assert r_payments.status_code == 200
        assert len(r_payments.json()) >= 1

        # 5. Create invoice and pay it
        inv = billing_store.create_invoice(Invoice(
            tenant_id="ws-owner", billing_account_id=account["id"],
            amount=50000, description="年度订阅 - 专业版",
        ))
        inv.status = InvoiceStatus.PAID
        billing_store.update_invoice(inv)

        # 6. Verify invoice
        r_inv = client.get(f"/billing/invoices/{inv.id}", headers=headers)
        assert r_inv.status_code == 200
        assert r_inv.json()["status"] == "paid"

    def test_multi_tenant_isolation(self, client, billing_store, owner_token, member_token):
        """验证租户间数据隔离。"""
        # Owner tenant creates a payment
        billing_store.create_account(BillingAccount(tenant_id="ws-owner"))
        payment_owner = billing_store.create_payment(Payment(
            tenant_id="ws-owner", billing_account_id="ba-o", invoice_id=None, amount=100,
        ))
        # Member tenant creates a payment
        billing_store.create_account(BillingAccount(tenant_id="ws-member"))
        billing_store.create_payment(Payment(
            tenant_id="ws-member", billing_account_id="ba-m", invoice_id=None, amount=200,
        ))

        # Owner sees their payments
        r_owner = client.get("/billing/payments", headers=_auth_headers(owner_token))
        owner_ids = {p["id"] for p in r_owner.json()}
        assert payment_owner.id in owner_ids

        # Member does NOT see owner's refund endpoint
        r_refund = client.post(
            f"/billing/payments/{payment_owner.id}/refund",
            json={"amount": 100},
            headers=_auth_headers(member_token),
        )
        assert r_refund.status_code == 404  # payment belongs to other tenant
