"""Usage Tracking Domain Models — UsageEvent / UsageStats / CostStats / UserProfile.

六边形架构核心层：纯数据类 + 协议。
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import uuid4


# ── Enums ──

class UsageResource(StrEnum):
    """用量资源类型。"""
    LLM_CALL = "llm_call"
    EMBEDDING = "embedding"
    SEARCH = "search"
    UPLOAD = "upload"
    IMPORT = "import"
    SYNC = "sync"
    COACH = "coach"
    STORAGE = "storage"
    MEMORY = "memory"


class UsageUnit(StrEnum):
    COUNT = "count"
    TOKEN = "token"
    BYTE = "byte"
    SECOND = "second"


# ── Data Classes ──


@dataclass
class UsageEvent:
    """单次用量事件。"""
    tenant_id: str
    user_id: str
    resource: UsageResource
    quantity: int = 1
    id: str = field(default_factory=lambda: f"use_{uuid4().hex[:12]}")
    workspace_id: str = ""
    unit: UsageUnit = UsageUnit.COUNT
    metadata: dict = field(default_factory=dict)
    # {"model": "deepseek-chat", "tokens": 1500, "endpoint": "/chat"}
    cost_cents: int = 0  # 预估成本（分）
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class UsageStats:
    """用量统计（月度/自定义周期）。"""
    tenant_id: str
    period_start: datetime
    period_end: datetime
    total_events: int = 0
    by_resource: dict[str, int] = field(default_factory=dict)
    # {"llm_call": 150, "search": 45, ...}
    total_cost_cents: int = 0
    by_resource_cost: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_events": self.total_events,
            "by_resource": self.by_resource,
            "total_cost_cents": self.total_cost_cents,
            "by_resource_cost": self.by_resource_cost,
        }


@dataclass
class CostStats:
    """成本统计。"""
    tenant_id: str
    month: str  # "2026-06"
    llm_cost_cents: int = 0
    embedding_cost_cents: int = 0
    storage_cost_cents: int = 0
    total_cost_cents: int = 0
    gross_revenue_cents: int = 0  # 毛收入
    net_revenue_cents: int = 0     # 净收入
    margin_percent: float = 0.0

    def as_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "month": self.month,
            "llm_cost_cents": self.llm_cost_cents,
            "embedding_cost_cents": self.embedding_cost_cents,
            "storage_cost_cents": self.storage_cost_cents,
            "total_cost_cents": self.total_cost_cents,
            "gross_revenue_cents": self.gross_revenue_cents,
            "net_revenue_cents": self.net_revenue_cents,
            "margin_percent": self.margin_percent,
        }


@dataclass
class UserProfile:
    """用户画像（基于用量数据聚合）。"""
    tenant_id: str
    user_id: str
    total_memories: int = 0
    total_searches: int = 0
    total_imports: int = 0
    total_syncs: int = 0
    coach_sessions: int = 0
    active_days: int = 0
    last_active: datetime | None = None
    preferred_features: list[str] = field(default_factory=list)
    # 活跃度评分 0-100
    engagement_score: int = 0
    # 是否为重度用户
    is_power_user: bool = False

    def as_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "total_memories": self.total_memories,
            "total_searches": self.total_searches,
            "total_imports": self.total_imports,
            "total_syncs": self.total_syncs,
            "coach_sessions": self.coach_sessions,
            "active_days": self.active_days,
            "last_active": self.last_active.isoformat() if self.last_active else None,
            "preferred_features": self.preferred_features,
            "engagement_score": self.engagement_score,
            "is_power_user": self.is_power_user,
        }


@dataclass
class PlatformStats:
    """平台级统计（SaaS Dashboard 用）。"""
    mrr_cents: int = 0           # Monthly Recurring Revenue
    arr_cents: int = 0           # Annual Run Rate
    total_tenants: int = 0
    active_tenants: int = 0
    trial_tenants: int = 0
    paying_tenants: int = 0
    conversion_rate: float = 0.0  # trial → paid
    churn_rate: float = 0.0       # 月流失率
    retention_rate: float = 0.0   # 月留存率
    avg_revenue_per_user: int = 0  # ARPU（分）
    total_revenue_cents: int = 0

    def as_dict(self) -> dict:
        return {
            "mrr_cents": self.mrr_cents,
            "arr_cents": self.arr_cents,
            "total_tenants": self.total_tenants,
            "active_tenants": self.active_tenants,
            "trial_tenants": self.trial_tenants,
            "paying_tenants": self.paying_tenants,
            "conversion_rate": self.conversion_rate,
            "churn_rate": self.churn_rate,
            "retention_rate": self.retention_rate,
            "avg_revenue_per_user": self.avg_revenue_per_user,
            "total_revenue_cents": self.total_revenue_cents,
        }


# ── Protocols ──


@runtime_checkable
class UsageStore(Protocol):
    """用量存储协议。"""

    def record_event(self, event: UsageEvent) -> str: ...
    def query_events(self, tenant_id: str, resource: str | None = None,
                     start: datetime | None = None, end: datetime | None = None,
                     limit: int = 100) -> list[UsageEvent]: ...
    def get_monthly_stats(self, tenant_id: str, year: int,
                          month: int) -> UsageStats: ...
    def get_cost_stats(self, tenant_id: str, year: int,
                       month: int) -> CostStats: ...
    def get_user_profile(self, tenant_id: str, user_id: str) -> UserProfile: ...
    def get_platform_stats(self) -> PlatformStats: ...
    def get_daily_usage(self, tenant_id: str, resource: str,
                        days: int = 30) -> list[dict]: ...
