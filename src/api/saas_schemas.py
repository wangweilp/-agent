"""SaaS API Schemas — Pydantic 请求/响应模型。

为 Billing / Subscription / Usage / Tenant / Growth 模块提供统一的
请求验证和响应序列化。
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Common ──

class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)


class DateRangeParams(BaseModel):
    start_date: str | None = None  # "2026-06-01"
    end_date: str | None = None


# ── Billing ──

class CreatePaymentIntentRequest(BaseModel):
    amount: int = Field(..., gt=0, description="金额（分）")
    currency: str = "cny"
    provider: str = "wechat"  # wechat | alipay | stripe
    description: str = ""
    invoice_id: str | None = None


class PaymentIntentResponse(BaseModel):
    id: str
    client_secret: str
    qr_code_url: str = ""
    amount: int
    currency: str
    provider: str
    created_at: str


class PaymentWebhookRequest(BaseModel):
    provider: str
    payload: dict = Field(default_factory=dict)


class InvoiceResponse(BaseModel):
    id: str
    invoice_number: str
    amount: int
    currency: str
    status: str
    description: str
    due_date: str | None = None
    paid_at: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    created_at: str


class PaymentResponse(BaseModel):
    id: str
    amount: int
    currency: str
    provider: str
    status: str
    description: str
    invoice_id: str | None = None
    created_at: str


class RefundRequest(BaseModel):
    payment_id: str
    amount: int = Field(..., gt=0)
    reason: str = ""


class RefundResponse(BaseModel):
    id: str
    payment_id: str
    amount: int
    status: str
    reason: str
    created_at: str


class BillingAccountResponse(BaseModel):
    id: str
    tenant_id: str
    currency: str
    balance: int
    billing_email: str
    created_at: str


# ── Subscription ──

class PlanPreviewResponse(BaseModel):
    tier: str
    monthly_price: int  # 分
    yearly_price: int   # 分
    current: bool = False
    limits: dict


class ChangePlanRequest(BaseModel):
    target_tier: str  # free | personal | professional | team | enterprise
    billing_cycle: str = "monthly"  # monthly | yearly


class SubscriptionResponse(BaseModel):
    id: str
    tenant_id: str
    plan_tier: str
    status: str
    billing_cycle: str
    current_period_start: str
    current_period_end: str | None = None
    trial_start: str | None = None
    trial_end: str | None = None
    canceled_at: str | None = None
    auto_renew: bool = True
    coupon_code: str | None = None
    days_remaining: int = 0
    created_at: str


class CancelSubscriptionResponse(BaseModel):
    tenant_id: str
    status: str
    canceled_at: str


# ── Usage ──

class RecordUsageRequest(BaseModel):
    resource: str  # llm_call | embedding | search | upload | import | sync | coach
    quantity: int = 1
    unit: str = "count"
    metadata: dict = Field(default_factory=dict)
    cost_cents: int = 0


class UsageStatsResponse(BaseModel):
    tenant_id: str
    period_start: str
    period_end: str
    total_events: int
    by_resource: dict[str, int]
    total_cost_cents: int
    by_resource_cost: dict[str, int]


class DailyUsageItem(BaseModel):
    date: str
    count: int
    cost: int


class UserProfileResponse(BaseModel):
    tenant_id: str
    user_id: str
    total_memories: int
    total_searches: int
    total_imports: int
    coach_sessions: int
    active_days: int
    last_active: str | None = None
    preferred_features: list[str]
    engagement_score: int
    is_power_user: bool


class PlatformStatsResponse(BaseModel):
    mrr_cents: int
    arr_cents: int
    total_tenants: int
    active_tenants: int
    trial_tenants: int
    paying_tenants: int
    conversion_rate: float
    churn_rate: float
    retention_rate: float
    avg_revenue_per_user: int
    total_revenue_cents: int


# ── Tenant ──

class CreateTenantRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str
    slug: str = ""
    industry: str = ""
    website: str = ""
    org_size: str = "solo"


class UpdateTenantRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    industry: str | None = None
    website: str | None = None
    logo_url: str | None = None
    timezone: str | None = None
    locale: str | None = None


class TenantResponse(BaseModel):
    id: str
    name: str
    email: str
    slug: str
    status: str
    owner_user_id: str
    org_size: str
    industry: str
    website: str
    created_at: str


class AddTenantMemberRequest(BaseModel):
    user_id: str
    role: str = "member"


class TenantMemberResponse(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    role: str
    org_id: str | None = None
    joined_at: str


class CreateOrgRequest(BaseModel):
    name: str
    parent_org_id: str | None = None
    description: str = ""


class OrganizationResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    parent_org_id: str | None = None
    description: str
    created_at: str


# ── Growth ──

class CreateInviteRequest(BaseModel):
    invitee_email: str
    workspace_id: str = ""


class InviteResponse(BaseModel):
    id: str
    invite_code: str
    invitee_email: str
    status: str
    expires_at: str
    created_at: str


class AcceptInviteRequest(BaseModel):
    invite_code: str


class ReferralResponse(BaseModel):
    id: str
    referral_code: str
    status: str
    reward_granted: bool
    reward_amount_cents: int
    created_at: str


class ReferralStatsResponse(BaseModel):
    total_referrals: int
    completed_referrals: int
    total_rewards_cents: int


class CreateCouponRequest(BaseModel):
    code: str = Field(..., min_length=3, max_length=20)
    coupon_type: str = "percentage"  # percentage | fixed_amount | trial_extension
    value: int = Field(..., gt=0)
    min_amount_cents: int = 0
    max_discount_cents: int = 0
    applicable_plans: list[str] = Field(default_factory=list)
    usage_limit: int = 0
    valid_days: int = 90


class CouponResponse(BaseModel):
    id: str
    code: str
    coupon_type: str
    value: int
    status: str
    usage_count: int
    usage_limit: int
    valid_until: str


class RedeemCouponRequest(BaseModel):
    code: str
    invoice_id: str = ""


class RedeemCouponResponse(BaseModel):
    id: str
    code: str
    discount_cents: int
    redeemed_at: str


class TrialResponse(BaseModel):
    id: str
    tenant_id: str
    plan_tier: str
    status: str
    trial_days: int
    started_at: str
    ends_at: str
    converted_at: str | None = None
    converted_to_plan: str
    extended_count: int


class TrialConversionStatsResponse(BaseModel):
    total_trials: int
    converted_trials: int
    conversion_rate: float
    avg_days_to_convert: float


# ── Limit Check ──

class LimitCheckResponse(BaseModel):
    resource: str
    allowed: bool
    used: int
    limit: int
    remaining: int


# ── Alert ──


class CreateAlertRuleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    metric: str  # memory_usage_pct | queue_depth | dlq_backlog | api_latency | cost_spike | anomaly_calls
    condition: str = "gt"  # gt | lt | gte | lte
    threshold: float = Field(..., gt=0)
    severity: str = "warning"  # info | warning | critical
    channel: str = "system"  # email | system | both
    cooldown_minutes: int = Field(default=60, ge=1, le=1440)


class UpdateAlertRuleRequest(BaseModel):
    name: str | None = None
    threshold: float | None = None
    severity: str | None = None
    channel: str | None = None
    enabled: bool | None = None
    cooldown_minutes: int | None = None
    condition: str | None = None
    metric: str | None = None


class AlertRuleResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    metric: str
    condition: str
    threshold: float
    severity: str
    channel: str
    enabled: bool
    cooldown_minutes: int
    last_triggered_at: str | None = None
    created_at: str
    updated_at: str


class AlertEventResponse(BaseModel):
    id: str
    tenant_id: str
    rule_id: str
    rule_name: str
    metric: str
    current_value: float
    threshold: float
    severity: str
    channel: str
    message: str
    acknowledged: bool
    triggered_at: str


class TestAlertResponse(BaseModel):
    success: bool
    message: str
    channel: str


# ── Report ──


class GenerateReportRequest(BaseModel):
    report_type: str = "monthly"  # weekly | monthly | quarterly
    format: str = "json"  # json | csv | pdf


class ReportResponse(BaseModel):
    id: str
    tenant_id: str
    report_type: str
    period_start: str
    period_end: str
    format: str
    status: str
    data: dict | None = None
    file_path: str | None = None
    created_at: str


# ── Analytics ──


class AnalyticsMetricsResponse(BaseModel):
    mrr_cents: int = 0
    arr_cents: int = 0
    total_tenants: int = 0
    active_tenants: int = 0
    paying_tenants: int = 0
    trial_tenants: int = 0
    conversion_rate: float = 0.0
    churn_rate: float = 0.0
    retention_rate: float = 0.0
    avg_revenue_per_user: int = 0
    total_revenue_cents: int = 0


class MemoryTrendResponse(BaseModel):
    tenant_id: str
    period: str  # daily | weekly | monthly
    trend: list[dict]


class ResourceUsageTrendResponse(BaseModel):
    tenant_id: str
    resource: str
    days: int
    trend: list[dict]


class ImportChannelResponse(BaseModel):
    tenant_id: str
    channels: dict[str, int]
    total_imports: int


class RetentionAnalysisResponse(BaseModel):
    tenant_id: str
    months: int
    cohort: list[dict]


class RealtimeMetricsResponse(BaseModel):
    tenant_id: str
    today_events: int
    today_cost_cents: int
    active_users_today: int
    max_hourly_events: int
    hourly_breakdown: dict[str, int]
