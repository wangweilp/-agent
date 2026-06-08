"""Subscription Domain Models — Plan / Subscription / PlanLimit.

六边形架构核心层：纯数据类 + 协议。
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import uuid4


# ── Enums ──

class PlanTier(StrEnum):
    FREE = "free"
    PERSONAL = "personal"
    PROFESSIONAL = "professional"
    TEAM = "team"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    EXPIRED = "expired"
    TRIAL = "trial"
    PAUSED = "paused"


class BillingCycle(StrEnum):
    MONTHLY = "monthly"
    YEARLY = "yearly"
    LIFETIME = "lifetime"


# ── Plan Limits ──


@dataclass
class PlanLimit:
    """单个套餐的用量限制。"""
    tier: PlanTier
    memory_count: int = 1000       # 最大记忆条数
    search_count: int = 100         # 每日搜索次数
    storage_mb: int = 100           # 存储空间（MB）
    import_per_day: int = 10        # 每日导入次数
    sync_connectors: int = 1        # 最大同步连接器数
    knowledge_graph: bool = False   # 是否支持知识图谱
    ai_coach: bool = False          # 是否支持 AI Coach
    team_members: int = 1           # 团队成员数
    api_access: bool = False        # API 访问
    priority_support: bool = False  # 优先支持

    # LLM 相关
    llm_calls_per_day: int = 50
    embedding_calls_per_day: int = 100

    def as_dict(self) -> dict:
        return {
            "tier": self.tier.value,
            "memory_count": self.memory_count,
            "search_count": self.search_count,
            "storage_mb": self.storage_mb,
            "import_per_day": self.import_per_day,
            "sync_connectors": self.sync_connectors,
            "knowledge_graph": self.knowledge_graph,
            "ai_coach": self.ai_coach,
            "team_members": self.team_members,
            "api_access": self.api_access,
            "priority_support": self.priority_support,
            "llm_calls_per_day": self.llm_calls_per_day,
            "embedding_calls_per_day": self.embedding_calls_per_day,
        }


# ── Plan Definitions ──

PLANS: dict[PlanTier, PlanLimit] = {
    PlanTier.FREE: PlanLimit(
        tier=PlanTier.FREE,
        memory_count=100,
        search_count=10,
        storage_mb=10,
        import_per_day=3,
        sync_connectors=1,
        knowledge_graph=False,
        ai_coach=False,
        team_members=1,
        api_access=False,
        priority_support=False,
        llm_calls_per_day=20,
        embedding_calls_per_day=50,
    ),
    PlanTier.PERSONAL: PlanLimit(
        tier=PlanTier.PERSONAL,
        memory_count=1000,
        search_count=100,
        storage_mb=100,
        import_per_day=10,
        sync_connectors=3,
        knowledge_graph=True,
        ai_coach=True,
        team_members=1,
        api_access=False,
        priority_support=False,
        llm_calls_per_day=100,
        embedding_calls_per_day=300,
    ),
    PlanTier.PROFESSIONAL: PlanLimit(
        tier=PlanTier.PROFESSIONAL,
        memory_count=5000,
        search_count=500,
        storage_mb=500,
        import_per_day=50,
        sync_connectors=10,
        knowledge_graph=True,
        ai_coach=True,
        team_members=3,
        api_access=True,
        priority_support=False,
        llm_calls_per_day=500,
        embedding_calls_per_day=1500,
    ),
    PlanTier.TEAM: PlanLimit(
        tier=PlanTier.TEAM,
        memory_count=20000,
        search_count=2000,
        storage_mb=2000,
        import_per_day=200,
        sync_connectors=30,
        knowledge_graph=True,
        ai_coach=True,
        team_members=20,
        api_access=True,
        priority_support=True,
        llm_calls_per_day=2000,
        embedding_calls_per_day=5000,
    ),
    PlanTier.ENTERPRISE: PlanLimit(
        tier=PlanTier.ENTERPRISE,
        memory_count=100000,
        search_count=999999,  # 无限制
        storage_mb=10000,
        import_per_day=999999,
        sync_connectors=100,
        knowledge_graph=True,
        ai_coach=True,
        team_members=999999,
        api_access=True,
        priority_support=True,
        llm_calls_per_day=10000,
        embedding_calls_per_day=50000,
    ),
}

# ── Pricing (月度价格，单位：分) ──

PLAN_PRICES: dict[PlanTier, dict[BillingCycle, int]] = {
    PlanTier.FREE:        {BillingCycle.MONTHLY: 0,     BillingCycle.YEARLY: 0},
    PlanTier.PERSONAL:    {BillingCycle.MONTHLY: 2900,  BillingCycle.YEARLY: 29000},   # ¥29/月  ¥290/年
    PlanTier.PROFESSIONAL:{BillingCycle.MONTHLY: 9900,  BillingCycle.YEARLY: 99000},   # ¥99/月  ¥990/年
    PlanTier.TEAM:        {BillingCycle.MONTHLY: 29900, BillingCycle.YEARLY: 299000},  # ¥299/月 ¥2990/年
    PlanTier.ENTERPRISE:  {BillingCycle.MONTHLY: 100000, BillingCycle.YEARLY: 1000000},  # ¥1000/月 ¥10000/年
}


# ── Data Classes ──


@dataclass
class Subscription:
    """租户订阅。"""
    tenant_id: str
    plan_tier: PlanTier = PlanTier.FREE
    id: str = field(default_factory=lambda: f"sub_{uuid4().hex[:12]}")
    status: SubscriptionStatus = SubscriptionStatus.TRIAL
    billing_cycle: BillingCycle = BillingCycle.MONTHLY
    current_period_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    current_period_end: datetime | None = None
    trial_start: datetime | None = None
    trial_end: datetime | None = None
    canceled_at: datetime | None = None
    auto_renew: bool = True
    coupon_code: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def plan_limit(self) -> PlanLimit:
        return PLANS[self.plan_tier]

    def is_active(self) -> bool:
        return self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL)

    def is_trial(self) -> bool:
        return self.status == SubscriptionStatus.TRIAL

    def days_remaining(self) -> int:
        end = self.current_period_end or self.trial_end
        if not end:
            return 0
        delta = end - datetime.now(timezone.utc)
        return max(0, delta.days)


@dataclass
class PlanChangeRequest:
    """套餐变更请求。"""
    tenant_id: str
    target_tier: PlanTier
    billing_cycle: BillingCycle = BillingCycle.MONTHLY
    effective_immediately: bool = True


@dataclass
class SubscriptionPreview:
    """套餐预览（用于前端展示）。"""
    tier: PlanTier
    limits: PlanLimit
    monthly_price: int  # 分
    yearly_price: int   # 分
    current: bool = False


# ── Protocols ──


@runtime_checkable
class SubscriptionStore(Protocol):
    """订阅存储协议。"""

    def create_subscription(self, sub: Subscription) -> Subscription: ...
    def get_subscription(self, tenant_id: str) -> Subscription | None: ...
    def update_subscription(self, sub: Subscription) -> None: ...
    def change_plan(self, tenant_id: str, target_tier: PlanTier,
                    billing_cycle: BillingCycle) -> Subscription: ...
    def cancel_subscription(self, tenant_id: str) -> Subscription: ...
    def list_subscriptions(self, status: str | None = None) -> list[Subscription]: ...


@runtime_checkable
class LimitEnforcer(Protocol):
    """用量限制执行器协议。"""

    def check_limit(self, tenant_id: str, resource: str) -> bool: ...
    def get_remaining(self, tenant_id: str, resource: str) -> int: ...
    def get_limits(self, tenant_id: str) -> PlanLimit: ...
