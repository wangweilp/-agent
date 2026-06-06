"""Billing/SaaS Router — 计费账户 / 支付意图 / 发票 / 退款 / Webhook。

端点:
    GET    /billing/account
    POST   /billing/payment-intent
    GET    /billing/invoices
    GET    /billing/invoices/{invoice_id}
    GET    /billing/payments
    POST   /billing/payments/{payment_id}/refund
    GET    /billing/refunds
    POST   /billing/webhook
    GET    /billing/admin/invoices
    GET    /billing/admin/payments
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.adapters.billing_store import BillingStoreAdapter
from src.adapters.payment_gateway import PaymentGatewayRegistry
from src.api.middleware import require_auth, require_manage
from src.api.saas_schemas import (
    BillingAccountResponse,
    CreatePaymentIntentRequest,
    InvoiceResponse,
    PaymentIntentResponse,
    PaymentResponse,
    PaymentWebhookRequest,
    RefundResponse,
)
from src.core.auth import TokenPayload
from src.core.billing import (
    BillingAccount,
    Invoice,
    Payment,
    PaymentProvider,
    PaymentStatus,
    Refund,
)

logger = logging.getLogger(__name__)


# ── Inline Schemas ──


class RefundBody(BaseModel):
    amount: int = Field(..., gt=0, description="退款金额（分）")
    reason: str = ""


# ── Router Factory ──


def create_billing_router(
    billing_store: BillingStoreAdapter,
    payment_gateway: PaymentGatewayRegistry,
) -> APIRouter:
    router = APIRouter(prefix="/billing", tags=["billing"])

    # ── Helpers ──

    def _tenant(payload: TokenPayload) -> str:
        return payload.workspace_id

    def _get_or_create_account(tenant_id: str) -> BillingAccount:
        account = billing_store.get_account(tenant_id)
        if account is None:
            account = BillingAccount(tenant_id=tenant_id)
            account = billing_store.create_account(account)
            logger.info("billing:account_auto_created", extra={"tenant_id": tenant_id})
        return account

    # ── Billing Account ──

    @router.get("/account")
    async def get_account(payload: TokenPayload = Depends(require_auth)):
        """获取当前租户的计费账户。不存在则自动创建。"""
        account = _get_or_create_account(_tenant(payload))
        return BillingAccountResponse(
            id=account.id,
            tenant_id=account.tenant_id,
            currency=account.currency.value,
            balance=account.balance,
            billing_email=account.billing_email,
            created_at=account.created_at.isoformat(),
        )

    # ── Payment Intent ──

    @router.post("/payment-intent")
    async def create_payment_intent(
        body: CreatePaymentIntentRequest,
        payload: TokenPayload = Depends(require_auth),
    ):
        """创建支付意图（微信/支付宝/Stripe）。"""
        tenant_id = _tenant(payload)

        # Validate provider
        try:
            provider = PaymentProvider(body.provider)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的支付提供商: {body.provider}。支持: wechat, alipay, stripe",
            )

        # Ensure billing account exists
        _get_or_create_account(tenant_id)

        intent = payment_gateway.create_intent(
            provider=provider,
            amount=body.amount,
            currency=body.currency,
            description=body.description,
            metadata={"tenant_id": tenant_id},
        )

        logger.info(
            "billing:payment_intent_created",
            extra={"tenant_id": tenant_id, "provider": body.provider, "amount": body.amount},
        )

        return PaymentIntentResponse(
            id=intent.id,
            client_secret=intent.client_secret,
            qr_code_url=intent.qr_code_url,
            amount=intent.amount,
            currency=intent.currency.value,
            provider=intent.provider.value,
            created_at=intent.created_at.isoformat(),
        )

    # ── Invoices ──

    @router.get("/invoices")
    async def list_invoices(
        status: str = Query(default=""),
        payload: TokenPayload = Depends(require_auth),
    ):
        """列出当前租户的发票。可选 ?status=paid|open|draft|void|overdue 过滤。"""
        tenant_id = _tenant(payload)
        status_filter = status if status else None
        invoices = billing_store.list_invoices(tenant_id, status_filter)
        return [
            InvoiceResponse(
                id=inv.id,
                invoice_number=inv.invoice_number,
                amount=inv.amount,
                currency=inv.currency.value,
                status=inv.status.value,
                description=inv.description,
                due_date=inv.due_date.isoformat() if inv.due_date else None,
                paid_at=inv.paid_at.isoformat() if inv.paid_at else None,
                period_start=inv.period_start.isoformat() if inv.period_start else None,
                period_end=inv.period_end.isoformat() if inv.period_end else None,
                created_at=inv.created_at.isoformat(),
            )
            for inv in invoices
        ]

    @router.get("/invoices/{invoice_id}")
    async def get_invoice(
        invoice_id: str,
        payload: TokenPayload = Depends(require_auth),
    ):
        """获取单张发票。"""
        tenant_id = _tenant(payload)
        invoice = billing_store.get_invoice(invoice_id)
        if invoice is None or invoice.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="发票不存在")
        return InvoiceResponse(
            id=invoice.id,
            invoice_number=invoice.invoice_number,
            amount=invoice.amount,
            currency=invoice.currency.value,
            status=invoice.status.value,
            description=invoice.description,
            due_date=invoice.due_date.isoformat() if invoice.due_date else None,
            paid_at=invoice.paid_at.isoformat() if invoice.paid_at else None,
            period_start=invoice.period_start.isoformat() if invoice.period_start else None,
            period_end=invoice.period_end.isoformat() if invoice.period_end else None,
            created_at=invoice.created_at.isoformat(),
        )

    # ── Payments ──

    @router.get("/payments")
    async def list_payments(payload: TokenPayload = Depends(require_auth)):
        """列出当前租户的支付记录。"""
        tenant_id = _tenant(payload)
        payments = billing_store.list_payments(tenant_id)
        return [
            PaymentResponse(
                id=p.id,
                amount=p.amount,
                currency=p.currency.value,
                provider=p.provider.value,
                status=p.status.value,
                description=p.description,
                invoice_id=p.invoice_id,
                created_at=p.created_at.isoformat(),
            )
            for p in payments
        ]

    @router.post("/payments/{payment_id}/refund")
    async def refund_payment(
        payment_id: str,
        body: RefundBody,
        payload: TokenPayload = Depends(require_auth),
    ):
        """对支付发起退款。"""
        tenant_id = _tenant(payload)

        # Get payment and validate ownership
        payment = billing_store.get_payment(payment_id)
        if payment is None or payment.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="支付记录不存在")

        if payment.status == PaymentStatus.REFUNDED:
            raise HTTPException(status_code=400, detail="该支付已全额退款")

        if body.amount > payment.amount:
            raise HTTPException(status_code=400, detail="退款金额不能超过支付金额")

        # Create refund via the payment's gateway provider
        gateway = payment_gateway.get(payment.provider)
        gateway_refund = gateway.create_refund(
            provider_payment_id=payment.provider_payment_id,
            amount=body.amount,
            reason=body.reason,
        )

        # Save refund record
        refund = Refund(
            tenant_id=tenant_id,
            payment_id=payment_id,
            amount=body.amount,
            provider_refund_id=gateway_refund.provider_refund_id,
            status=gateway_refund.status,
            reason=body.reason,
        )
        refund = billing_store.create_refund(refund)

        # Update payment status
        if body.amount >= payment.amount:
            payment.status = PaymentStatus.REFUNDED
        else:
            payment.status = PaymentStatus.PARTIALLY_REFUNDED
        billing_store.update_payment(payment)

        logger.info(
            "billing:refund_created",
            extra={
                "tenant_id": tenant_id,
                "payment_id": payment_id,
                "amount": body.amount,
                "reason": body.reason,
            },
        )

        return RefundResponse(
            id=refund.id,
            payment_id=refund.payment_id,
            amount=refund.amount,
            status=refund.status.value,
            reason=refund.reason,
            created_at=refund.created_at.isoformat(),
        )

    # ── Refunds ──

    @router.get("/refunds")
    async def list_refunds(payload: TokenPayload = Depends(require_auth)):
        """列出当前租户的退款记录。"""
        tenant_id = _tenant(payload)
        refunds = billing_store.list_refunds(tenant_id)
        return [
            RefundResponse(
                id=r.id,
                payment_id=r.payment_id,
                amount=r.amount,
                status=r.status.value,
                reason=r.reason,
                created_at=r.created_at.isoformat(),
            )
            for r in refunds
        ]

    # ── Webhook ──

    @router.post("/webhook")
    async def webhook(body: PaymentWebhookRequest):
        """支付网关 Webhook 接收端点（微信/支付宝/Stripe 回调）。"""
        try:
            provider = PaymentProvider(body.provider)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的支付提供商: {body.provider}",
            )

        result = payment_gateway.handle_webhook(provider, body.payload)
        logger.info(
            "billing:webhook_received",
            extra={"provider": body.provider},
        )
        return {"status": "success", "result": result}

    # ── Admin Endpoints ──

    @router.get("/admin/invoices")
    async def admin_list_invoices(payload: TokenPayload = Depends(require_manage)):
        """管理员：列出当前租户的所有发票。"""
        tenant_id = _tenant(payload)
        invoices = billing_store.list_invoices(tenant_id)
        return [
            InvoiceResponse(
                id=inv.id,
                invoice_number=inv.invoice_number,
                amount=inv.amount,
                currency=inv.currency.value,
                status=inv.status.value,
                description=inv.description,
                due_date=inv.due_date.isoformat() if inv.due_date else None,
                paid_at=inv.paid_at.isoformat() if inv.paid_at else None,
                period_start=inv.period_start.isoformat() if inv.period_start else None,
                period_end=inv.period_end.isoformat() if inv.period_end else None,
                created_at=inv.created_at.isoformat(),
            )
            for inv in invoices
        ]

    @router.get("/admin/payments")
    async def admin_list_payments(payload: TokenPayload = Depends(require_manage)):
        """管理员：列出当前租户的所有支付记录。"""
        tenant_id = _tenant(payload)
        payments = billing_store.list_payments(tenant_id)
        return [
            PaymentResponse(
                id=p.id,
                amount=p.amount,
                currency=p.currency.value,
                provider=p.provider.value,
                status=p.status.value,
                description=p.description,
                invoice_id=p.invoice_id,
                created_at=p.created_at.isoformat(),
            )
            for p in payments
        ]

    return router
