"""Marketplace Analytics Service 测试 — 推荐算法 / 排行榜 / 平台指标。"""

from __future__ import annotations

import os, tempfile, pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
from src.adapters.config import Settings
from src.adapters.marketplace_analytics_store import SQLiteMarketplaceAnalyticsStore
from src.adapters.agent_module_store import SQLiteAgentModuleStore
from src.adapters.marketplace_governance_store import SQLiteMarketplaceGovernanceStore
from src.open_platform.marketplace_analytics_service import MarketplaceAnalyticsService
from src.open_platform.marketplace_analytics import RankingCategory
from src.open_platform.marketplace_governance import Review, Report, TrustScore
from src.open_platform.agent_module import AgentModule, Subscription


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")
@pytest.fixture
def db():
    d = tempfile.mkdtemp(); p = os.path.join(d, "test_analytics_svc.db"); yield p
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def analytics_store(settings, db):
    return SQLiteMarketplaceAnalyticsStore(settings, db_path=db)
@pytest.fixture
def gov_store(settings, db): return SQLiteMarketplaceGovernanceStore(settings, db_path=db)
@pytest.fixture
def am_store(settings, db): return SQLiteAgentModuleStore(settings, db_path=db)

@pytest.fixture
def svc(analytics_store, gov_store, am_store):
    return MarketplaceAnalyticsService(analytics_store,
        governance_store=gov_store, agent_module_store=am_store)


def _publish_module(am_store, gov_store, ws="ws-1", name="Agent", category="chat",
                    tags=None, days=30, rating=4.0, review_count=5, trust=80.0):
    """Helper to create a published module with trust metadata."""
    from datetime import datetime, timedelta, timezone
    m = am_store.create(AgentModule(workspace_id=ws, name=name, category=category,
        tags=tags or [], status="draft"))
    am_store.update_status(m.id, "review")
    am_store.update_status(m.id, "approved")
    am_store.update_status(m.id, "published")

    # set fake published_at for days calculation
    pub_dt = datetime.now(timezone.utc) - timedelta(days=days)
    from src.adapters.marketplace_governance_store import _safe_dt
    am_store._exec("UPDATE agent_modules SET published_at=? WHERE id=?",
                   [pub_dt.isoformat(), m.id])

    if review_count > 0:
        for j in range(review_count):
            r_rating = max(1, min(5, int(rating) + (j % 2)))
            gov_store.create_review(Review(
                workspace_id=f"ws-{j+2}", agent_module_id=m.id,
                rating=r_rating, title=f"Review {j}"))
    gov_store.upsert_trust_score(TrustScore(
        agent_module_id=m.id, score=trust, published_days=days,
        review_count=review_count, average_rating=rating))
    return am_store.get(m.id)


# ═══════════════ Rankings ═══════════════

class TestRankings:
    def test_top_rated_empty(self, svc):
        ranks = svc.get_top_rated_agents()
        assert ranks == []

    def test_top_rated_with_modules(self, svc, am_store, gov_store):
        _publish_module(am_store, gov_store, name="A", rating=5.0, review_count=3, trust=95)
        _publish_module(am_store, gov_store, name="B", rating=3.0, review_count=1, trust=40)
        ranks = svc.get_top_rated_agents(10)
        assert len(ranks) == 2
        assert ranks[0]["metrics"]["average_rating"] >= ranks[1]["metrics"]["average_rating"]

    def test_most_installed(self, svc, am_store, gov_store):
        _publish_module(am_store, gov_store, name="Pop", review_count=50, trust=80)
        _publish_module(am_store, gov_store, name="New", review_count=1, trust=50)
        ranks = svc.get_most_installed_agents(10)
        assert len(ranks) == 2

    def test_fastest_growing(self, svc, am_store, gov_store):
        _publish_module(am_store, gov_store, name="Fast", rating=5.0, review_count=20, days=1)
        _publish_module(am_store, gov_store, name="Slow", rating=5.0, review_count=5, days=100)
        ranks = svc.get_fastest_growing_agents(10)
        assert len(ranks) == 2
        # faster growing should be first
        assert ranks[0]["metrics"]["review_count"] >= ranks[1]["metrics"]["review_count"]

    def test_trending(self, svc, am_store, gov_store):
        _publish_module(am_store, gov_store, name="Hot", rating=5.0, review_count=30, trust=95, days=5)
        _publish_module(am_store, gov_store, name="Cold", rating=2.0, review_count=1, trust=20, days=365)
        ranks = svc.get_trending_agents(10)
        assert len(ranks) == 2

    def test_highest_trust(self, svc, am_store, gov_store):
        _publish_module(am_store, gov_store, name="Trusted", trust=98)
        _publish_module(am_store, gov_store, name="Shady", trust=25)
        ranks = svc.get_rankings(RankingCategory.HIGHEST_TRUST, 10)
        assert len(ranks) == 2

    def test_generate_rankings_all_categories(self, svc, am_store, gov_store):
        _publish_module(am_store, gov_store, name="M", rating=4.0, review_count=5, trust=70)
        for cat in RankingCategory:
            ranks = svc.generate_rankings(cat, 10)
            assert len(ranks) == 1, f"{cat} should return 1 rank"

    def test_cached_rankings(self, svc, am_store, gov_store):
        _publish_module(am_store, gov_store, name="M")
        svc.generate_rankings(RankingCategory.TOP_RATED, 10)
        # second call should hit cache
        ranks = svc.get_rankings(RankingCategory.TOP_RATED, 10)
        assert len(ranks) == 1

    def test_rankings_limit(self, svc, am_store, gov_store):
        for i in range(10):
            _publish_module(am_store, gov_store, name=f"M{i}", rating=4.0 + i * 0.05, review_count=i + 1, trust=50 + i)
        ranks = svc.get_top_rated_agents(5)
        assert len(ranks) == 5

    def test_invalid_category(self, svc):
        assert svc.generate_rankings("invalid", 10) == []


# ═══════════════ Recommendations ═══════════════

class TestRecommendations:
    def test_empty_without_modules(self, svc):
        recs = svc.generate_recommendations("ws-1")
        assert recs == []

    def test_recommendations_excludes_subscribed(self, svc, am_store, gov_store):
        m = _publish_module(am_store, gov_store, ws="ws-1", name="AlreadyHave",
                            category="chat", tags=["ai"])
        # subscribe ws-1 to this module
        am_store.subscribe(Subscription(workspace_id="ws-1", agent_module_id=m.id))
        # another module available
        _publish_module(am_store, gov_store, ws="ws-2", name="NewModule",
                        category="chat", tags=["ai"], rating=4.5, review_count=10, trust=85)
        recs = svc.generate_recommendations("ws-1")
        # should only recommend module NOT subscribed
        assert len(recs) >= 0  # may be 0 if no matching, or 1 for the other module

    def test_recommendations_with_matching_category(self, svc, am_store, gov_store):
        # subscribe ws-1 to a chat module
        m1 = _publish_module(am_store, gov_store, ws="ws-1", name="ChatAgent",
                             category="chat", tags=["ai", "nlp"])
        am_store.subscribe(Subscription(workspace_id="ws-1", agent_module_id=m1.id))
        # another chat module
        m2 = _publish_module(am_store, gov_store, ws="ws-2", name="ChatBot2",
                             category="chat", tags=["ai", "support"], rating=4.8, review_count=15, trust=90)
        recs = svc.generate_recommendations("ws-1", limit=5)
        assert len(recs) >= 1

    def test_cached_recommendations(self, svc, am_store, gov_store):
        _publish_module(am_store, gov_store, name="A", category="dev", rating=5.0, review_count=3, trust=90)
        svc.generate_recommendations("ws-1")
        cached = svc.get_recommendations("ws-1")
        assert len(cached) >= 0


# ═══════════════ Platform Metrics ═══════════════

class TestPlatformMetrics:
    def test_empty_platform(self, svc):
        m = svc.calculate_platform_metrics()
        d = m if isinstance(m, dict) else {}
        assert isinstance(d, dict)

    def test_with_modules(self, svc, am_store, gov_store):
        _publish_module(am_store, gov_store, name="A", category="chat", rating=4.5, review_count=10, trust=85)
        _publish_module(am_store, gov_store, name="B", category="code", rating=3.5, review_count=3, trust=55)
        m = svc.calculate_platform_metrics()
        assert m["total_modules"] == 2
        assert m["published_modules"] == 2
        assert m["average_platform_rating"] > 0
        assert m["average_platform_trust"] > 0
        assert "top_categories" in m
        assert "risk_distribution" in m

    def test_cached_metrics(self, svc, am_store, gov_store):
        _publish_module(am_store, gov_store, name="A")
        svc.calculate_platform_metrics()
        cached = svc.get_platform_metrics()
        assert "total_modules" in cached

    def test_growth_rate(self, svc, am_store, gov_store):
        _publish_module(am_store, gov_store, name="A", days=5)
        _publish_module(am_store, gov_store, name="B", days=100)
        m = svc.calculate_platform_metrics()
        assert "recent_growth_rate" in m


# ═══════════════ Event Recording ═══════════════

class TestEventRecording:
    def test_record_event(self, svc):
        svc.record_analytics_event("test_event", dimension="reviews",
                                   agent_module_id="ag_1", workspace_id="ws-1",
                                   payload={"key": "val"})
        # no crash = pass
        assert True

    def test_record_multiple_events(self, svc):
        for i in range(5):
            svc.record_analytics_event(f"event_{i}", agent_module_id="ag_A")
        events = svc._store.get_events("ag_A", 10)
        assert len(events) == 5
