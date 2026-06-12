"""Cross-Tenant Analytics Domain — 跨租户聚合与趋势。

全部 metadata-only 计算，禁止 runtime/container/microVM。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class AnalyticsPeriod(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class TrendDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


@dataclass
class TenantUsageSummary:
    """单租户用量摘要。"""
    workspace_id: str = ""
    tenant_name: str = ""
    plan_tier: str = "free"
    total_modules: int = 0
    published_modules: int = 0
    total_artifacts: int = 0
    total_packages: int = 0
    total_workflows: int = 0
    total_subscriptions: int = 0
    total_reviews: int = 0
    total_reports: int = 0
    llm_calls: int = 0
    embedding_calls: int = 0
    storage_bytes: int = 0
    last_active: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id, "tenant_name": self.tenant_name,
            "plan_tier": self.plan_tier, "total_modules": self.total_modules,
            "published_modules": self.published_modules,
            "total_artifacts": self.total_artifacts,
            "total_packages": self.total_packages,
            "total_workflows": self.total_workflows,
            "total_subscriptions": self.total_subscriptions,
            "total_reviews": self.total_reviews,
            "total_reports": self.total_reports,
            "llm_calls": self.llm_calls, "embedding_calls": self.embedding_calls,
            "storage_bytes": self.storage_bytes,
            "last_active": self.last_active.isoformat() if self.last_active else None,
        }


@dataclass
class PlatformTrend:
    """平台趋势数据点。"""
    period: str = AnalyticsPeriod.DAILY
    timestamp: str = ""
    metric_name: str = ""
    value: float = 0.0
    previous_value: float = 0.0
    direction: str = TrendDirection.FLAT
    change_percent: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period, "timestamp": self.timestamp,
            "metric_name": self.metric_name, "value": self.value,
            "previous_value": self.previous_value, "direction": self.direction,
            "change_percent": self.change_percent,
        }


@dataclass
class CrossTenantMetrics:
    """跨租户平台指标快照。"""
    total_tenants: int = 0
    active_tenants: int = 0
    trial_tenants: int = 0
    paying_tenants: int = 0
    total_modules: int = 0
    total_artifacts: int = 0
    total_packages: int = 0
    total_workflows: int = 0
    total_subscriptions: int = 0
    total_reviews: int = 0
    total_reports: int = 0
    total_llm_calls: int = 0
    total_embedding_calls: int = 0
    conversion_rate: float = 0.0
    platform_trust_avg: float = 0.0
    platform_rating_avg: float = 0.0
    top_workspaces: list[dict[str, Any]] = field(default_factory=list)
    plan_distribution: dict[str, int] = field(default_factory=dict)
    category_distribution: dict[str, int] = field(default_factory=dict)
    trends: list[dict[str, Any]] = field(default_factory=list)
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tenants": self.total_tenants, "active_tenants": self.active_tenants,
            "trial_tenants": self.trial_tenants, "paying_tenants": self.paying_tenants,
            "total_modules": self.total_modules, "total_artifacts": self.total_artifacts,
            "total_packages": self.total_packages, "total_workflows": self.total_workflows,
            "total_subscriptions": self.total_subscriptions,
            "total_reviews": self.total_reviews, "total_reports": self.total_reports,
            "total_llm_calls": self.total_llm_calls,
            "total_embedding_calls": self.total_embedding_calls,
            "conversion_rate": self.conversion_rate,
            "platform_trust_avg": self.platform_trust_avg,
            "platform_rating_avg": self.platform_rating_avg,
            "top_workspaces": list(self.top_workspaces),
            "plan_distribution": dict(self.plan_distribution),
            "category_distribution": dict(self.category_distribution),
            "trends": list(self.trends),
            "calculated_at": self.calculated_at.isoformat(),
        }


def _safe_dt(raw: str | None) -> datetime:
    if not raw: return datetime.now(timezone.utc)
    try: return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError): return datetime.now(timezone.utc)
