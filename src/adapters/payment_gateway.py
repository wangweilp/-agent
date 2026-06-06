"""Payment Gateway Adapters — 微信支付 / 支付宝 / Stripe 统一接口。

生产环境需替换为真实 SDK 调用。当前为 Mock 实现，保留完整接口契约。
"""
import hashlib
import logging
import secrets
import time
from datetime import datetime, timezone

from src.core.billing import (
    Currency,
    Payment,
    PaymentIntent,
    PaymentProvider,
    PaymentStatus,
    Refund,
    RefundStatus,
)

logger = logging.getLogger(__name__)


class BasePaymentGateway:
    """支付网关基类。"""

    provider: PaymentProvider

    def create_payment_intent(
        self, amount: int, currency: str, description: str,
        metadata: dict | None = None,
    ) -> PaymentIntent:
        raise NotImplementedError

    def confirm_payment(self, provider_payment_id: str) -> Payment:
        raise NotImplementedError

    def create_refund(self, provider_payment_id: str, amount: int,
                      reason: str) -> Refund:
        raise NotImplementedError

    def handle_webhook(self, payload: dict) -> dict:
        raise NotImplementedError


class WechatPaymentGateway(BasePaymentGateway):
    """微信支付 (JSAPI / Native) Mock 实现。

    生产环境使用 wechatpayv3 SDK:
        from wechatpayv3 import WeChatPay
    """

    provider = PaymentProvider.WECHAT

    def create_payment_intent(
        self, amount: int, currency: str = "cny", description: str = "",
        metadata: dict | None = None,
    ) -> PaymentIntent:
        prepay_id = f"wx{secrets.token_hex(16)}"
        return PaymentIntent(
            tenant_id=metadata.get("tenant_id", "") if metadata else "",
            amount=amount,
            currency=Currency(currency) if currency else Currency.CNY,
            provider=PaymentProvider.WECHAT,
            description=description,
            client_secret=prepay_id,
            qr_code_url=f"weixin://wxpay/bizpayurl?pr={prepay_id}",
        )

    def confirm_payment(self, provider_payment_id: str) -> Payment:
        # Mock: 直接返回成功
        return Payment(
            tenant_id="",
            billing_account_id="",
            invoice_id=None,
            amount=0,
            provider=PaymentProvider.WECHAT,
            provider_payment_id=provider_payment_id,
            status=PaymentStatus.SUCCEEDED,
        )

    def create_refund(self, provider_payment_id: str, amount: int,
                      reason: str) -> Refund:
        return Refund(
            tenant_id="",
            payment_id="",
            amount=amount,
            provider_refund_id=f"wx_ref_{secrets.token_hex(8)}",
            status=RefundStatus.SUCCEEDED,
            reason=reason,
        )

    def handle_webhook(self, payload: dict) -> dict:
        event_type = payload.get("event_type", "")
        resource = payload.get("resource", {})
        logger.info("wechat_webhook", extra={"event": event_type})
        return {"code": "SUCCESS", "message": "OK"}


class AlipayPaymentGateway(BasePaymentGateway):
    """支付宝 (网页/APP 支付) Mock 实现。

    生产环境使用 alipay SDK:
        from alipay import AliPay
    """

    provider = PaymentProvider.ALIPAY

    def create_payment_intent(
        self, amount: int, currency: str = "cny", description: str = "",
        metadata: dict | None = None,
    ) -> PaymentIntent:
        trade_no = f"ali{secrets.token_hex(16)}"
        return PaymentIntent(
            tenant_id=metadata.get("tenant_id", "") if metadata else "",
            amount=amount,
            currency=Currency(currency) if currency else Currency.CNY,
            provider=PaymentProvider.ALIPAY,
            description=description,
            client_secret=trade_no,
            qr_code_url=f"https://qr.alipay.com/bax{trade_no[:20]}",
        )

    def confirm_payment(self, provider_payment_id: str) -> Payment:
        return Payment(
            tenant_id="",
            billing_account_id="",
            invoice_id=None,
            amount=0,
            provider=PaymentProvider.ALIPAY,
            provider_payment_id=provider_payment_id,
            status=PaymentStatus.SUCCEEDED,
        )

    def create_refund(self, provider_payment_id: str, amount: int,
                      reason: str) -> Refund:
        return Refund(
            tenant_id="",
            payment_id="",
            amount=amount,
            provider_refund_id=f"ali_ref_{secrets.token_hex(8)}",
            status=RefundStatus.SUCCEEDED,
            reason=reason,
        )

    def handle_webhook(self, payload: dict) -> dict:
        logger.info("alipay_webhook", extra={"notify_type": payload.get("notify_type", "")})
        return {"code": "10000", "msg": "Success"}


class StripePaymentGateway(BasePaymentGateway):
    """Stripe 国际支付 Mock 实现。

    生产环境使用 stripe SDK:
        import stripe
        stripe.api_key = "sk_..."
    """

    provider = PaymentProvider.STRIPE

    def create_payment_intent(
        self, amount: int, currency: str = "usd", description: str = "",
        metadata: dict | None = None,
    ) -> PaymentIntent:
        pi_id = f"pi_{secrets.token_hex(12)}"
        return PaymentIntent(
            tenant_id=metadata.get("tenant_id", "") if metadata else "",
            amount=amount,
            currency=Currency(currency) if currency else Currency.USD,
            provider=PaymentProvider.STRIPE,
            description=description,
            client_secret=f"{pi_id}_secret_{secrets.token_hex(12)}",
            qr_code_url="",
        )

    def confirm_payment(self, provider_payment_id: str) -> Payment:
        return Payment(
            tenant_id="",
            billing_account_id="",
            invoice_id=None,
            amount=0,
            provider=PaymentProvider.STRIPE,
            provider_payment_id=provider_payment_id,
            status=PaymentStatus.SUCCEEDED,
        )

    def create_refund(self, provider_payment_id: str, amount: int,
                      reason: str) -> Refund:
        return Refund(
            tenant_id="",
            payment_id="",
            amount=amount,
            provider_refund_id=f"re_{secrets.token_hex(12)}",
            status=RefundStatus.SUCCEEDED,
            reason=reason,
        )

    def handle_webhook(self, payload: dict) -> dict:
        logger.info("stripe_webhook", extra={"type": payload.get("type", "")})
        return {"received": True}


# ── Gateway Registry ──


class PaymentGatewayRegistry:
    """支付网关注册表 — 按 provider 获取对应网关。"""

    def __init__(self) -> None:
        self._gateways: dict[PaymentProvider, BasePaymentGateway] = {
            PaymentProvider.WECHAT: WechatPaymentGateway(),
            PaymentProvider.ALIPAY: AlipayPaymentGateway(),
            PaymentProvider.STRIPE: StripePaymentGateway(),
        }

    def get(self, provider: PaymentProvider) -> BasePaymentGateway:
        gateway = self._gateways.get(provider)
        if gateway is None:
            raise ValueError(f"Unsupported payment provider: {provider}")
        return gateway

    def create_intent(
        self, provider: PaymentProvider, amount: int, currency: str,
        description: str, metadata: dict | None = None,
    ) -> PaymentIntent:
        return self.get(provider).create_payment_intent(
            amount, currency, description, metadata,
        )

    def handle_webhook(self, provider: PaymentProvider, payload: dict) -> dict:
        return self.get(provider).handle_webhook(payload)
