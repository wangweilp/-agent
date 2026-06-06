"""Growth Domain Models — Invite / Referral / Coupon / Trial。

六边形架构核心层：纯数据类 + 协议。
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import uuid4


# ── Enums ──

class InviteStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"


class CouponType(StrEnum):
    PERCENTAGE = "percentage"    # 百分比折扣
    FIXED_AMOUNT = "fixed_amount"  # 固定金额
    TRIAL_EXTENSION = "trial_extension"  # 延长试用期


class CouponStatus(StrEnum):
    ACTIVE = "active"
    USED = "used"
    EXPIRED = "expired"
    DISABLED = "disabled"


class ReferralStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    REWARDED = "rewarded"


class TrialStatus(StrEnum):
    ACTIVE = "active"
    CONVERTED = "converted"
    EXPIRED = "expired"
    EXTENDED = "extended"


# ── Data Classes ──


@dataclass
class Invite:
    """邀请记录。"""
    inviter_tenant_id: str
    inviter_user_id: str
    invitee_email: str
    id: str = field(default_factory=lambda: f"inv_{uuid4().hex[:12]}")
    invite_code: str = ""  # 8位邀请码
    status: InviteStatus = InviteStatus.PENDING
    workspace_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    accepted_at: datetime | None = None
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=7))


@dataclass
class Referral:
    """推荐记录。"""
    referrer_tenant_id: str
    referrer_user_id: str
    referred_tenant_id: str = ""
    referred_user_id: str = ""
    id: str = field(default_factory=lambda: f"ref_{uuid4().hex[:12]}")
    referral_code: str = ""  # 推荐码，分享给好友
    status: ReferralStatus = ReferralStatus.PENDING
    reward_granted: bool = False
    reward_amount_cents: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


@dataclass
class Coupon:
    """优惠券。"""
    code: str  # 优惠码，如 "WELCOME20"
    coupon_type: CouponType = CouponType.PERCENTAGE
    id: str = field(default_factory=lambda: f"cpn_{uuid4().hex[:12]}")
    value: int = 0  # 百分比(1-100) 或 固定金额(分) 或 试用延长天数
    min_amount_cents: int = 0  # 最低消费金额
    max_discount_cents: int = 0  # 最大折扣金额（百分比券用）
    status: CouponStatus = CouponStatus.ACTIVE
    applicable_plans: list[str] = field(default_factory=list)  # 适用套餐，空=全部
    usage_limit: int = 0  # 0=无限制
    usage_count: int = 0
    valid_from: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    valid_until: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=90))
    created_by: str = ""  # admin user_id
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_valid(self, amount_cents: int = 0, plan: str = "") -> bool:
        now = datetime.now(timezone.utc)
        if self.status != CouponStatus.ACTIVE:
            return False
        if now < self.valid_from or now > self.valid_until:
            return False
        if self.usage_limit > 0 and self.usage_count >= self.usage_limit:
            return False
        if amount_cents < self.min_amount_cents:
            return False
        if self.applicable_plans and plan not in self.applicable_plans:
            return False
        return True

    def calculate_discount(self, amount_cents: int) -> int:
        if not self.is_valid(amount_cents):
            return 0
        if self.coupon_type == CouponType.PERCENTAGE:
            discount = int(amount_cents * self.value / 100)
            if self.max_discount_cents > 0:
                discount = min(discount, self.max_discount_cents)
            return discount
        elif self.coupon_type == CouponType.FIXED_AMOUNT:
            return min(self.value, amount_cents)
        return 0


@dataclass
class CouponRedemption:
    """优惠券兑换记录。"""
    coupon_id: str
    tenant_id: str
    code: str
    id: str = field(default_factory=lambda: f"cpr_{uuid4().hex[:12]}")
    discount_cents: int = 0
    invoice_id: str = ""
    redeemed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TrialRecord:
    """试用记录。"""
    tenant_id: str
    plan_tier: str
    id: str = field(default_factory=lambda: f"tri_{uuid4().hex[:12]}")
    status: TrialStatus = TrialStatus.ACTIVE
    trial_days: int = 14
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ends_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=14))
    converted_at: datetime | None = None
    converted_to_plan: str = ""
    extended_count: int = 0  # 延长次数
    source: str = ""  # "signup" | "invite" | "referral" | "coupon"


# ── Protocols ──


@runtime_checkable
class GrowthStore(Protocol):
    """增长存储协议。"""

    # Invite
    def create_invite(self, invite: Invite) -> Invite: ...
    def get_invite(self, invite_id: str) -> Invite | None: ...
    def get_invite_by_code(self, code: str) -> Invite | None: ...
    def accept_invite(self, invite_id: str, invitee_user_id: str,
                      invitee_tenant_id: str) -> Invite: ...
    def list_invites(self, tenant_id: str) -> list[Invite]: ...

    # Referral
    def create_referral(self, referral: Referral) -> Referral: ...
    def get_referral(self, referral_id: str) -> Referral | None: ...
    def get_referral_by_code(self, code: str) -> Referral | None: ...
    def complete_referral(self, referral_id: str,
                          referred_tenant_id: str, referred_user_id: str) -> Referral: ...
    def list_referrals(self, tenant_id: str) -> list[Referral]: ...
    def get_referral_stats(self, tenant_id: str) -> dict: ...

    # Coupon
    def create_coupon(self, coupon: Coupon) -> Coupon: ...
    def get_coupon(self, coupon_id: str) -> Coupon | None: ...
    def get_coupon_by_code(self, code: str) -> Coupon | None: ...
    def redeem_coupon(self, redemption: CouponRedemption) -> CouponRedemption: ...
    def list_coupons(self, status: str | None = None) -> list[Coupon]: ...
    def update_coupon(self, coupon: Coupon) -> None: ...

    # Trial
    def create_trial(self, trial: TrialRecord) -> TrialRecord: ...
    def get_trial(self, tenant_id: str) -> TrialRecord | None: ...
    def extend_trial(self, tenant_id: str, days: int) -> TrialRecord: ...
    def convert_trial(self, tenant_id: str, plan_tier: str) -> TrialRecord: ...
    def list_trials(self, status: str | None = None) -> list[TrialRecord]: ...
    def get_trial_conversion_stats(self) -> dict: ...
