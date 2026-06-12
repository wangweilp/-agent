"""Marketplace Analytics Domain 测试 — RecommendedAgent / AgentRank / AnalyticsMetrics / AnalyticsEvent。"""

from __future__ import annotations

import pytest
from src.open_platform.marketplace_analytics import (
    RecommendedAgent, AgentRank, AnalyticsMetrics, AnalyticsEvent,
    RankingCategory, AnalyticsDimension, RecommendationReason,
)


class TestRecommendedAgent:
    def test_defaults(self):
        r = RecommendedAgent()
        assert r.score == 0.0; assert r.reason == RecommendationReason.POPULAR

    def test_to_dict(self):
        r = RecommendedAgent(agent_module_id="agent_1", agent_name="Bot", score=85.5,
                             reason=RecommendationReason.CATEGORY_MATCH,
                             sub_reasons=["tag_match"], confidence=0.9)
        d = r.to_dict()
        assert d["score"] == 85.5; assert d["reason"] == "category_match"
        assert d["sub_reasons"] == ["tag_match"]

    def test_from_dict(self):
        d = {"agent_module_id": "a", "agent_name": "A", "score": 90.0}
        r = RecommendedAgent.from_dict(d)
        assert r.agent_module_id == "a" and r.score == 90.0


class TestAgentRank:
    def test_defaults(self):
        r = AgentRank()
        assert r.rank == 0; assert r.category == RankingCategory.TOP_RATED

    def test_to_dict(self):
        r = AgentRank(agent_module_id="ag", agent_name="Ranked", rank=1,
                      category=RankingCategory.FASTEST_GROWING, score=92.0,
                      metrics={"reviews": 50})
        d = r.to_dict()
        assert d["rank"] == 1; assert d["category"] == "fastest_growing"
        assert d["metrics"]["reviews"] == 50

    def test_from_dict(self):
        d = {"agent_module_id": "a", "rank": 3, "category": "trending"}
        r = AgentRank.from_dict(d)
        assert r.rank == 3


class TestAnalyticsMetrics:
    def test_defaults(self):
        m = AnalyticsMetrics()
        assert m.total_modules == 0

    def test_to_dict(self):
        m = AnalyticsMetrics(total_modules=100, published_modules=80,
                             average_platform_rating=4.2, average_platform_trust=75.5,
                             total_subscriptions=200, active_workspaces=45,
                             risk_distribution={"low": 60, "medium": 15},
                             top_categories=[{"category": "chat", "count": 30}],
                             trending_tags=["ai", "chat"],
                             recent_growth_rate=12.5)
        d = m.to_dict()
        assert d["total_modules"] == 100
        assert d["risk_distribution"]["low"] == 60
        assert d["trending_tags"] == ["ai", "chat"]


class TestAnalyticsEvent:
    def test_defaults(self):
        e = AnalyticsEvent()
        assert e.id.startswith("aev_")

    def test_to_dict(self):
        e = AnalyticsEvent(event_type="rec_generated", dimension=AnalyticsDimension.REVIEWS,
                           agent_module_id="ag", workspace_id="ws-1",
                           payload={"count": 5})
        d = e.to_dict()
        assert d["event_type"] == "rec_generated"
        assert d["payload"]["count"] == 5

    def test_from_dict(self):
        d = {"id": "aev_1", "event_type": "rank", "agent_module_id": "ag"}
        e = AnalyticsEvent.from_dict(d)
        assert e.agent_module_id == "ag"


class TestEnums:
    def test_ranking_categories(self): assert len(list(RankingCategory)) == 6

    def test_analytics_dimensions(self): assert len(list(AnalyticsDimension)) == 6

    def test_recommendation_reasons(self): assert len(list(RecommendationReason)) == 8
