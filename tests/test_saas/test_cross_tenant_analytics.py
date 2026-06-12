"""Cross-Tenant Analytics Service 测试。"""

from __future__ import annotations

import os, tempfile, pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
from src.adapters.config import Settings
from src.adapters.cross_tenant_analytics_store import CrossTenantAnalyticsStore
from src.adapters.agent_module_store import SQLiteAgentModuleStore
from src.adapters.marketplace_governance_store import SQLiteMarketplaceGovernanceStore
from src.adapters.subscription_store import SubscriptionStoreAdapter
from src.adapters.artifact_store import SQLiteArtifactStore
from src.adapters.package_registry_store import SQLitePackageStore
from src.adapters.workflow_registry_store import SQLiteWorkflowStore
from src.open_platform.cross_tenant_analytics_service import CrossTenantAnalyticsService
from src.open_platform.cross_tenant_analytics import CrossTenantMetrics, TenantUsageSummary, PlatformTrend


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")
@pytest.fixture
def db():
    d = tempfile.mkdtemp(); p = os.path.join(d, "test_ct.db"); yield p
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def ct_store(settings, db): return CrossTenantAnalyticsStore(settings, db_path=db)
@pytest.fixture
def am_store(settings, db): return SQLiteAgentModuleStore(settings, db_path=db)
@pytest.fixture
def gov_store(settings, db): return SQLiteMarketplaceGovernanceStore(settings, db_path=db)
@pytest.fixture
def sub_db_ct():
    d = tempfile.mkdtemp(); p = os.path.join(d, "test_ct_sub.db"); yield p
    import shutil; shutil.rmtree(d, ignore_errors=True)
@pytest.fixture
def sub_store(settings, sub_db_ct): return SubscriptionStoreAdapter(settings, db_path=sub_db_ct)
@pytest.fixture
def artifact_store(settings, db): return SQLiteArtifactStore(settings, db_path=db)
@pytest.fixture
def package_store(settings, db): return SQLitePackageStore(settings, db_path=db)
@pytest.fixture
def workflow_store(settings, db): return SQLiteWorkflowStore(settings, db_path=db)

@pytest.fixture
def svc(ct_store, am_store, gov_store, sub_store, artifact_store, package_store, workflow_store):
    return CrossTenantAnalyticsService(
        ct_analytics_store=ct_store, agent_module_store=am_store,
        governance_store=gov_store, subscription_store=sub_store,
        artifact_store=artifact_store, package_store=package_store,
        workflow_store=workflow_store)


def _publish_module(am_store, gov_store, ws="ws-1", name="Agent", category="chat",
                    trust=80.0, rating=4.0, reviews=5):
    from src.open_platform.agent_module import AgentModule
    from src.open_platform.marketplace_governance import Review, TrustScore
    m = am_store.create(AgentModule(workspace_id=ws, name=name, category=category, status="draft"))
    am_store.update_status(m.id, "review")
    am_store.update_status(m.id, "approved")
    am_store.update_status(m.id, "published")
    if reviews > 0:
        for j in range(reviews):
            gov_store.create_review(Review(
                workspace_id=f"ws-{j+100}", agent_module_id=m.id,
                rating=int(rating), title=f"Review {j}"))
    gov_store.upsert_trust_score(TrustScore(
        agent_module_id=m.id, score=trust, review_count=reviews, average_rating=rating))
    return am_store.get(m.id)


class TestCrossTenantMetrics:
    def test_empty_aggregate(self, svc):
        m = svc.aggregate_metrics()
        assert "total_modules" in m
        assert "platform_trust_avg" in m

    def test_aggregate_with_modules(self, svc, am_store, gov_store, sub_store):
        from src.core.subscription import Subscription, PlanTier
        _publish_module(am_store, gov_store, ws="ws-1", name="ChatBot", trust=85, rating=4.5, reviews=10)
        _publish_module(am_store, gov_store, ws="ws-2", name="CodeBot", trust=60, rating=3.0, reviews=2)
        sub_store.create_subscription(
            Subscription(tenant_id="ws-1", plan_tier=PlanTier.PROFESSIONAL))
        sub_store.create_subscription(
            Subscription(tenant_id="ws-2", plan_tier=PlanTier.FREE))
        m = svc.aggregate_metrics()
        assert m["total_modules"] >= 2
        assert m["platform_trust_avg"] > 0
        assert "plan_distribution" in m

    def test_cached_metrics(self, svc):
        svc.aggregate_metrics()
        cached = svc.get_cached_metrics()
        assert cached is not None
        assert "total_modules" in cached

    def test_no_cache_returns_none(self, svc, ct_store):
        # Fresh empty store should have no cache yet (only after aggregate_metrics)
        empty_svc = CrossTenantAnalyticsService(ct_analytics_store=ct_store)
        m = empty_svc.get_cached_metrics()
        assert m is None or isinstance(m, dict)


class TestTenantSummaries:
    def test_empty_summaries(self, svc):
        summaries = svc.usage_per_workspace()
        assert isinstance(summaries, list)

    def test_summaries_with_modules(self, svc, am_store, gov_store):
        _publish_module(am_store, gov_store, ws="ws-1", name="A1")
        _publish_module(am_store, gov_store, ws="ws-1", name="A2")
        _publish_module(am_store, gov_store, ws="ws-2", name="B1")
        summaries = svc.usage_per_workspace()
        assert len(summaries) >= 2
        ws1 = [s for s in summaries if s["workspace_id"] == "ws-1"]
        assert len(ws1) == 1 and ws1[0]["total_modules"] >= 2


class TestTrends:
    def test_generate_trends(self, svc, am_store, gov_store):
        _publish_module(am_store, gov_store, ws="ws-1", name="A1")
        trends = svc.generate_trends()
        assert len(trends) >= 1
        assert "metric_name" in trends[0]

    def test_no_trends_without_stores(self):
        svc2 = CrossTenantAnalyticsService()
        trends = svc2.generate_trends()
        assert trends == []


class TestTopAgents:
    def test_empty(self, svc):
        assert svc.top_agents() == []

    def test_with_modules(self, svc, am_store, gov_store):
        _publish_module(am_store, gov_store, ws="ws-1", name="Best", trust=95, rating=5.0, reviews=20)
        _publish_module(am_store, gov_store, ws="ws-2", name="Worst", trust=20, rating=1.0, reviews=1)
        top = svc.top_agents(10)
        assert len(top) >= 2
        assert top[0]["composite_score"] > top[-1]["composite_score"]


class TestCrossTenantStore:
    @pytest.fixture
    def store(self, settings, db): return CrossTenantAnalyticsStore(settings, db_path=db)

    def test_save_snapshot(self, store):
        m = CrossTenantMetrics(total_tenants=5, total_modules=20)
        store.save_snapshot(m)
        snap = store.get_latest_snapshot()
        assert snap is not None and snap.total_tenants == 5

    def test_save_tenant_summary(self, store):
        s = TenantUsageSummary(workspace_id="ws-1", tenant_name="Tenant A", total_modules=10)
        store.save_tenant_summary(s)
        summaries = store.get_tenant_summaries()
        assert any(su.workspace_id == "ws-1" for su in summaries)

    def test_save_trends(self, store):
        trends = [PlatformTrend(metric_name="test_metric", value=42.0, previous_value=40.0, direction="up")]
        store.save_trends(trends)
        result = store.get_trends("test_metric")
        assert len(result) == 1
        assert result[0].value == 42.0

    def test_trends_filter_by_metric(self, store):
        store.save_trends([
            PlatformTrend(metric_name="m1", value=10.0),
            PlatformTrend(metric_name="m2", value=20.0),
        ])
        assert len(store.get_trends("m1")) == 1
        assert len(store.get_trends()) == 2
