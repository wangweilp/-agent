"""Billing Domain Models — BillingAccount / Invoice / Payment / Refund.

六边形架构核心层：纯数据类 + 协议，不引用外部库。
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import uuid4


# ── Enums ──

class PaymentProvider(StrEnum):
    WECHAT = "wechat"
    ALIPAY = "alipay"
    STRIPE = "stripe"
    MANUAL = "manual"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    VOID = "void"
    OVERDUE = "overdue"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class RefundStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Currency(StrEnum):
    CNY = "cny"
    USD = "usd"
    EUR = "eur"


# ── Data Classes ──


@dataclass
class BillingAccount:
    """用户/租户的计费账户。"""
    tenant_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    currency: Currency = Currency.CNY
    balance: int = 0  # 余额，单位：分（cent）
    credit_limit: int = 0  # 信用额度，单位：分
    wechat_openid: str | None = None
    alipay_user_id: str | None = None
    stripe_customer_id: str | None = None
    billing_email: str = ""
    billing_address: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Invoice:
    """发票/账单。"""
    tenant_id: str
    billing_account_id: str
    amount: int  # 单位：分
    currency: Currency = Currency.CNY
    id: str = field(default_factory=lambda: f"inv_{uuid4().hex[:12]}")
    invoice_number: str = ""  # INV-2026-00001
    status: InvoiceStatus = InvoiceStatus.DRAFT
    description: str = ""
    line_items: list[dict] = field(default_factory=list)
    # [{description, quantity, unit_amount, amount}]
    due_date: datetime | None = None
    paid_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    period_start: datetime | None = None
    period_end: datetime | None = None


@dataclass
class Payment:
    """支付记录。"""
    tenant_id: str
    billing_account_id: str
    invoice_id: str | None  # 可为空（预充值）
    amount: int  # 单位：分
    currency: Currency = Currency.CNY
    provider: PaymentProvider = PaymentProvider.WECHAT
    id: str = field(default_factory=lambda: f"pay_{uuid4().hex[:12]}")
    provider_payment_id: str = ""  # 第三方支付 ID
    status: PaymentStatus = PaymentStatus.PENDING
    description: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Refund:
    """退款记录。"""
    tenant_id: str
    payment_id: str
    amount: int  # 单位：分
    id: str = field(default_factory=lambda: f"ref_{uuid4().hex[:12]}")
    provider_refund_id: str = ""
    status: RefundStatus = RefundStatus.PENDING
    reason: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PaymentIntent:
    """支付意图 — 客户端发起支付前的预创建。"""
    tenant_id: str
    amount: int
    currency: Currency = Currency.CNY
    provider: PaymentProvider = PaymentProvider.WECHAT
    invoice_id: str | None = None
    description: str = ""
    id: str = field(default_factory=lambda: f"pi_{uuid4().hex[:12]}")
    client_secret: str = ""  # Stripe: client_secret; 微信/支付宝: 预支付 ID
    qr_code_url: str = ""  # 微信/支付宝扫码 URL
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Protocols ──


@runtime_checkable
class BillingStore(Protocol):
    """计费存储协议。"""

    def create_account(self, account: BillingAccount) -> BillingAccount: ...
    def get_account(self, tenant_id: str) -> BillingAccount | None: ...
    def update_account(self, account: BillingAccount) -> None: ...

    def create_invoice(self, invoice: Invoice) -> Invoice: ...
    def get_invoice(self, invoice_id: str) -> Invoice | None: ...
    def list_invoices(self, tenant_id: str, status: str | None = None) -> list[Invoice]: ...
    def update_invoice(self, invoice: Invoice) -> None: ...

    def create_payment(self, payment: Payment) -> Payment: ...
    def get_payment(self, payment_id: str) -> Payment | None: ...
    def list_payments(self, tenant_id: str) -> list[Payment]: ...
    def update_payment(self, payment: Payment) -> None: ...

    def create_refund(self, refund: Refund) -> Refund: ...
    def get_refund(self, refund_id: str) -> Refund | None: ...
    def list_refunds(self, tenant_id: str) -> list[Refund]: ...


@runtime_checkable
class PaymentGateway(Protocol):
    """支付网关协议 — 微信/支付宝/Stripe 的统一抽象。"""

    def create_payment_intent(self, amount: int, currency: str,
                              description: str, metadata: dict) -> PaymentIntent: ...
    def confirm_payment(self, payment_id: str) -> Payment: ...
    def create_refund(self, payment_id: str, amount: int,
                      reason: str) -> Refund: ...
    def handle_webhook(self, payload: dict) -> dict: ...
