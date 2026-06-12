"""Marketplace Analytics Store 测试 — 4 表 CRUD。"""

from __future__ import annotations

import os, tempfile, pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
from src.adapters.config import Settings
from src.adapters.marketplace_analytics_store import SQLiteMarketplaceAnalyticsStore
from src.open_platform.marketplace_analytics import (
    RecommendedAgent, AgentRank, AnalyticsMetrics, AnalyticsEvent,
    RankingCategory, RecommendationReason,
)


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")
@pytest.fixture
def db():
    d = tempfile.mkdtemp(); p = os.path.join(d, "test_analytics.db"); yield p
    import shutil; shutil.rmtree(d, ignore_errors=True)
@pytest.fixture
def store(settings, db): return SQLiteMarketplaceAnalyticsStore(settings, db_path=db)


def _recs(*items):
    return [RecommendedAgent(agent_module_id=f"ag_{i}", agent_name=f"Agent{i}",
            score=90.0 - i * 5, reason=RecommendationReason.POPULAR,
            sub_reasons=["popular"], confidence=0.8) for i in items]


class TestRecommendationsStore:
    def test_save_and_get(self, store):
        store.save_recommendations("ws-1", _recs(1, 2, 3))
        recs = store.get_recommendations("ws-1")
        assert len(recs) == 3
        assert recs[0].score >= recs[1].score  # desc order

    def test_overwrite_old(self, store):
        store.save_recommendations("ws-1", _recs(1, 2))
        store.save_recommendations("ws-1", _recs(3, 4, 5))
        assert len(store.get_recommendations("ws-1")) == 3

    def test_empty(self, store):
        assert store.get_recommendations("none") == []

    def test_limit(self, store):
        store.save_recommendations("ws-1", _recs(*range(10)))
        assert len(store.get_recommendations("ws-1", limit=4)) == 4

    def test_different_workspaces_isolated(self, store):
        store.save_recommendations("ws-1", _recs(1, 2))
        store.save_recommendations("ws-2", _recs(3,))
        assert len(store.get_recommendations("ws-1")) == 2
        assert len(store.get_recommendations("ws-2")) == 1


def _ranks(cat, *items):
    return [AgentRank(agent_module_id=f"ag_{i}", agent_name=f"Agent{i}",
            rank=i + 1, category=cat, score=100 - i * 5) for i in items]


class TestRankingsStore:
    def test_save_and_get(self, store):
        store.save_rankings("top_rated", _ranks("top_rated", 0, 1, 2))
        ranks = store.get_rankings("top_rated")
        assert len(ranks) == 3
        assert ranks[0].rank == 1

    def test_overwrite_old(self, store):
        store.save_rankings("trending", _ranks("trending", 0, 1))
        store.save_rankings("trending", _ranks("trending", 0, 1, 2))
        assert len(store.get_rankings("trending")) == 3

    def test_different_categories(self, store):
        store.save_rankings("top_rated", _ranks("top_rated", 0, 1))
        store.save_rankings("trending", _ranks("trending", 0,))
        assert len(store.get_rankings("top_rated")) == 2
        assert len(store.get_rankings("trending")) == 1

    def test_empty_category(self, store):
        assert store.get_rankings("none") == []

    def test_limit(self, store):
        store.save_rankings("top_rated", _ranks("top_rated", *range(15)))
        assert len(store.get_rankings("top_rated", limit=5)) == 5


class TestMetricsStore:
    def test_save_and_get(self, store):
        m = AnalyticsMetrics(total_modules=42, average_platform_rating=4.1)
        store.save_analytics_metrics(m)
        fetched = store.get_latest_metrics()
        assert fetched is not None
        assert fetched.total_modules == 42

    def test_latest(self, store):
        store.save_analytics_metrics(AnalyticsMetrics(total_modules=1))
        store.save_analytics_metrics(AnalyticsMetrics(total_modules=2))
        assert store.get_latest_metrics().total_modules == 2

    def test_no_metrics_returns_none(self, store):
        assert store.get_latest_metrics() is None

    def test_history(self, store):
        for i in range(5):
            store.save_analytics_metrics(AnalyticsMetrics(total_modules=i * 10))
        hist = store.get_metrics_history(3)
        assert len(hist) == 3


class TestEventsStore:
    def test_record_and_get(self, store):
        store.record_event(AnalyticsEvent(event_type="test", agent_module_id="ag"))
        events = store.get_events("ag")
        assert len(events) == 1

    def test_filter_by_agent(self, store):
        store.record_event(AnalyticsEvent(event_type="e1", agent_module_id="ag_A"))
        store.record_event(AnalyticsEvent(event_type="e2", agent_module_id="ag_B"))
        assert len(store.get_events("ag_A")) == 1

    def test_limit(self, store):
        for i in range(10):
            store.record_event(AnalyticsEvent(event_type=f"e{i}", agent_module_id="ag"))
        assert len(store.get_events("ag", limit=4)) == 4

    def test_empty(self, store):
        assert store.get_events("none") == []
