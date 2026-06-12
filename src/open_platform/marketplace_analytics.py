"""Marketplace Recommendation & Analytics Domain。

全部 metadata-only 计算，禁止 runtime/container/microVM。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


# ═══════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════

class RankingCategory(StrEnum):
    TOP_RATED = "top_rated"
    MOST_INSTALLED = "most_installed"
    FASTEST_GROWING = "fastest_growing"
    TRENDING = "trending"
    HIGHEST_TRUST = "highest_trust"
    MOST_REVIEWED = "most_reviewed"


class AnalyticsDimension(StrEnum):
    REVIEWS = "reviews"
    RATINGS = "ratings"
    TRUST = "trust"
    SUBSCRIPTIONS = "subscriptions"
    RISK = "risk"
    ACTIVITY = "activity"


class RecommendationReason(StrEnum):
    CATEGORY_MATCH = "category_match"
    TAG_SIMILARITY = "tag_similarity"
    SIMILAR_USERS = "similar_users"
    HIGH_TRUST = "high_trust"
    TOP_RATED = "top_rated"
    POPULAR = "popular"
    FAST_GROWING = "fast_growing"
    CO_INSTALLED = "co_installed"


# ═══════════════════════════════════════════
# Domain Models
# ═══════════════════════════════════════════

@dataclass
class RecommendedAgent:
    """推荐结果。"""
    agent_module_id: str = ""
    agent_name: str = ""
    score: float = 0.0
    reason: str = RecommendationReason.POPULAR
    sub_reasons: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_module_id": self.agent_module_id,
            "agent_name": self.agent_name,
            "score": self.score,
            "reason": self.reason,
            "sub_reasons": list(self.sub_reasons),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RecommendedAgent":
        return cls(
            agent_module_id=str(d.get("agent_module_id", "")),
            agent_name=str(d.get("agent_name", "")),
            score=float(d.get("score", 0.0)),
            reason=str(d.get("reason", RecommendationReason.POPULAR)),
            sub_reasons=list(d.get("sub_reasons", [])),
            confidence=float(d.get("confidence", 0.0)),
        )


@dataclass
class AgentRank:
    """排行榜条目。"""
    agent_module_id: str = ""
    agent_name: str = ""
    rank: int = 0
    category: str = RankingCategory.TOP_RATED
    score: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_module_id": self.agent_module_id,
            "agent_name": self.agent_name,
            "rank": self.rank, "category": self.category,
            "score": self.score, "metrics": dict(self.metrics),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentRank":
        return cls(
            agent_module_id=str(d.get("agent_module_id", "")),
            agent_name=str(d.get("agent_name", "")),
            rank=int(d.get("rank", 0)),
            category=str(d.get("category", RankingCategory.TOP_RATED)),
            score=float(d.get("score", 0.0)),
            metrics=dict(d.get("metrics", {})),
        )


@dataclass
class AnalyticsMetrics:
    """平台分析指标。"""
    total_modules: int = 0
    published_modules: int = 0
    total_reviews: int = 0
    average_platform_rating: float = 0.0
    average_platform_trust: float = 0.0
    total_subscriptions: int = 0
    active_workspaces: int = 0
    risk_distribution: dict[str, int] = field(default_factory=dict)
    top_categories: list[dict[str, Any]] = field(default_factory=list)
    trending_tags: list[str] = field(default_factory=list)
    recent_growth_rate: float = 0.0
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_modules": self.total_modules,
            "published_modules": self.published_modules,
            "total_reviews": self.total_reviews,
            "average_platform_rating": self.average_platform_rating,
            "average_platform_trust": self.average_platform_trust,
            "total_subscriptions": self.total_subscriptions,
            "active_workspaces": self.active_workspaces,
            "risk_distribution": dict(self.risk_distribution),
            "top_categories": list(self.top_categories),
            "trending_tags": list(self.trending_tags),
            "recent_growth_rate": self.recent_growth_rate,
            "calculated_at": self.calculated_at.isoformat(),
        }


@dataclass
class AnalyticsEvent:
    """分析事件记录。"""
    id: str = field(default_factory=lambda: f"aev_{uuid4().hex[:12]}")
    event_type: str = ""
    dimension: str = ""
    agent_module_id: str = ""
    workspace_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "event_type": self.event_type,
            "dimension": self.dimension, "agent_module_id": self.agent_module_id,
            "workspace_id": self.workspace_id, "payload": dict(self.payload),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AnalyticsEvent":
        return cls(
            id=str(d.get("id", "")), event_type=str(d.get("event_type", "")),
            dimension=str(d.get("dimension", "")),
            agent_module_id=str(d.get("agent_module_id", "")),
            workspace_id=str(d.get("workspace_id", "")),
            payload=dict(d.get("payload", {})),
            created_at=_safe_dt(d.get("created_at")),
        )


# ═══════════════════════════════════════════
# Store Protocol
# ═══════════════════════════════════════════

@runtime_checkable
class MarketplaceAnalyticsStore(Protocol):
    def save_recommendations(self, workspace_id: str, recs: list[RecommendedAgent]) -> None: ...
    def get_recommendations(self, workspace_id: str, limit: int) -> list[RecommendedAgent]: ...
    def save_rankings(self, category: str, ranks: list[AgentRank]) -> None: ...
    def get_rankings(self, category: str, limit: int) -> list[AgentRank]: ...
    def save_analytics_metrics(self, m: AnalyticsMetrics) -> None: ...
    def get_latest_metrics(self) -> AnalyticsMetrics | None: ...
    def record_event(self, evt: AnalyticsEvent) -> None: ...
    def get_events(self, agent_module_id: str, limit: int) -> list[AnalyticsEvent]: ...


def _safe_dt(raw: str | None) -> datetime:
    if not raw: return datetime.now(timezone.utc)
    try: return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError): return datetime.now(timezone.utc)
