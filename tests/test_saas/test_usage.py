"""UsageStoreAdapter 单元测试。

覆盖：record_event / query_events / monthly_stats / cost_stats /
       daily_usage / user_profile / platform_stats / tenant_usage_summary。
"""
import os
import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.usage_store import UsageStoreAdapter
from src.adapters.config import Settings
from src.core.usage import (
    UsageEvent,
    UsageResource,
    UsageUnit,
    UsageStats,
    CostStats,
    UserProfile,
    PlatformStats,
)
from datetime import datetime, timezone, timedelta


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def settings():
    return Settings(_env_file=None)


@pytest.fixture
def store(settings):
    store = UsageStoreAdapter(config=settings, db_path=":memory:")
    yield store
    store.close()


# ── Helpers ─────────────────────────────────────────────────────────────

def _make_event(
    tenant_id="t1",
    user_id="u1",
    resource=UsageResource.LLM_CALL,
    quantity=1,
    cost_cents=0,
    timestamp=None,
    **kwargs,
):
    return UsageEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        resource=resource,
        quantity=quantity,
        cost_cents=cost_cents,
        timestamp=timestamp or datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
        **kwargs,
    )


def _recent_ts(days_ago=0):
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def _insert_subscription(store, tenant_id="t1", plan_tier="professional",
                         status="active", billing_cycle="monthly"):
    store._db.execute(
        """INSERT INTO subscriptions (id, tenant_id, plan_tier, status, billing_cycle)
           VALUES (?, ?, ?, ?, ?)""",
        (f"sub_{tenant_id}", tenant_id, plan_tier, status, billing_cycle),
    )


# ── Tests ───────────────────────────────────────────────────────────────


class TestRecordEvent:
    def test_record_event(self, store):
        event = _make_event(tenant_id="t1", user_id="u1",
                            resource=UsageResource.LLM_CALL, quantity=5, cost_cents=50)
        event_id = store.record_event(event)
        assert event_id == event.id
        assert event_id.startswith("use_")

    def test_record_multiple_resources(self, store):
        resources = [
            UsageResource.LLM_CALL,
            UsageResource.EMBEDDING,
            UsageResource.SEARCH,
            UsageResource.UPLOAD,
            UsageResource.MEMORY,
        ]
        ids = []
        for i, res in enumerate(resources):
            event = _make_event(tenant_id="t1", user_id="u1",
                                resource=res, quantity=i + 1)
            ids.append(store.record_event(event))

        assert len(ids) == 5
        assert len(set(ids)) == 5  # all unique

    def test_record_with_cost(self, store):
        event = _make_event(tenant_id="t1", user_id="u1",
                            resource=UsageResource.LLM_CALL, quantity=100,
                            cost_cents=42)
        event_id = store.record_event(event)
        assert event_id

        # Query back to verify cost persisted
        events = store.query_events("t1")
        assert len(events) == 1
        assert events[0].cost_cents == 42


class TestQueryEvents:
    def test_query_events(self, store):
        for i in range(3):
            store.record_event(_make_event(tenant_id="t1", user_id="u1",
                                           resource=UsageResource.LLM_CALL,
                                           quantity=i + 1,
                                           timestamp=_recent_ts(i)))

        events = store.query_events("t1")
        assert len(events) == 3
        for e in events:
            assert e.tenant_id == "t1"

    def test_query_events_by_resource(self, store):
        store.record_event(_make_event(tenant_id="t1", user_id="u1",
                                       resource=UsageResource.LLM_CALL,
                                       timestamp=_recent_ts(0)))
        store.record_event(_make_event(tenant_id="t1", user_id="u1",
                                       resource=UsageResource.SEARCH,
                                       timestamp=_recent_ts(1)))

        llm_events = store.query_events("t1", resource="llm_call")
        assert len(llm_events) == 1
        assert llm_events[0].resource == UsageResource.LLM_CALL

        search_events = store.query_events("t1", resource="search")
        assert len(search_events) == 1
        assert search_events[0].resource == UsageResource.SEARCH

    def test_query_events_time_range(self, store):
        t1 = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2025, 6, 10, 0, 0, 0, tzinfo=timezone.utc)
        t3 = datetime(2025, 6, 20, 0, 0, 0, tzinfo=timezone.utc)

        store.record_event(_make_event(tenant_id="t1", user_id="u1",
                                       resource=UsageResource.LLM_CALL, timestamp=t1))
        store.record_event(_make_event(tenant_id="t1", user_id="u1",
                                       resource=UsageResource.LLM_CALL, timestamp=t2))
        store.record_event(_make_event(tenant_id="t1", user_id="u1",
                                       resource=UsageResource.LLM_CALL, timestamp=t3))

        # Query middle range
        events = store.query_events(
            "t1", start=datetime(2025, 6, 5, tzinfo=timezone.utc),
            end=datetime(2025, 6, 15, tzinfo=timezone.utc),
        )
        assert len(events) == 1
        assert events[0].timestamp == t2

        # Query wide range covers all
        events_all = store.query_events(
            "t1", start=datetime(2025, 5, 1, tzinfo=timezone.utc),
            end=datetime(2025, 7, 1, tzinfo=timezone.utc),
        )
        assert len(events_all) == 3


class TestMonthlyStats:
    def test_get_monthly_stats(self, store):
        # Insert known events in 2025-06
        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.LLM_CALL,
            quantity=10, cost_cents=100,
            timestamp=datetime(2025, 6, 5, 12, 0, 0, tzinfo=timezone.utc),
        ))
        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.LLM_CALL,
            quantity=5, cost_cents=30,
            timestamp=datetime(2025, 6, 10, 12, 0, 0, tzinfo=timezone.utc),
        ))
        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.SEARCH,
            quantity=20, cost_cents=40,
            timestamp=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        ))
        # Event outside the month — should not be included
        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.LLM_CALL,
            quantity=999, cost_cents=9999,
            timestamp=datetime(2025, 7, 1, 12, 0, 0, tzinfo=timezone.utc),
        ))

        stats = store.get_monthly_stats("t1", 2025, 6)

        assert isinstance(stats, UsageStats)
        assert stats.tenant_id == "t1"
        assert stats.total_events == 35  # 10 + 5 + 20
        assert stats.total_cost_cents == 170  # 100 + 30 + 40
        assert stats.by_resource["llm_call"] == 15
        assert stats.by_resource["search"] == 20
        assert stats.by_resource_cost["llm_call"] == 130
        assert stats.by_resource_cost["search"] == 40

    def test_get_monthly_stats_empty_month(self, store):
        stats = store.get_monthly_stats("t1", 2025, 6)
        assert stats.total_events == 0
        assert stats.total_cost_cents == 0
        assert stats.by_resource == {}


class TestCostStats:
    def test_get_cost_stats(self, store):
        # Insert events for LLM, embedding, storage in 2025-06
        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.LLM_CALL,
            quantity=10, cost_cents=200,
            timestamp=datetime(2025, 6, 5, 12, 0, 0, tzinfo=timezone.utc),
        ))
        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.COACH,
            quantity=3, cost_cents=60,
            timestamp=datetime(2025, 6, 8, 12, 0, 0, tzinfo=timezone.utc),
        ))
        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.EMBEDDING,
            quantity=100, cost_cents=50,
            timestamp=datetime(2025, 6, 10, 12, 0, 0, tzinfo=timezone.utc),
        ))
        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.STORAGE,
            quantity=500, cost_cents=30,
            timestamp=datetime(2025, 6, 12, 12, 0, 0, tzinfo=timezone.utc),
        ))

        # Insert subscription for revenue calculation
        _insert_subscription(store, tenant_id="t1", plan_tier="professional",
                             status="active", billing_cycle="monthly")

        stats = store.get_cost_stats("t1", 2025, 6)

        assert isinstance(stats, CostStats)
        assert stats.tenant_id == "t1"
        assert stats.month == "2025-06"
        # llm_cost = llm_call(200) + coach(60) = 260
        assert stats.llm_cost_cents == 260
        assert stats.embedding_cost_cents == 50
        assert stats.storage_cost_cents == 30
        # total = 200 + 60 + 50 + 30 = 340
        assert stats.total_cost_cents == 340
        # professional monthly = 9900 cents
        assert stats.gross_revenue_cents == 9900
        assert stats.net_revenue_cents == 9900 - 340  # 9560
        assert stats.margin_percent > 0


class TestDailyUsage:
    def test_get_daily_usage(self, store):
        today = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)

        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.LLM_CALL,
            quantity=3, cost_cents=30, timestamp=yesterday,
        ))
        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.LLM_CALL,
            quantity=7, cost_cents=70, timestamp=yesterday,
        ))
        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.LLM_CALL,
            quantity=1, cost_cents=10, timestamp=two_days_ago,
        ))

        daily = store.get_daily_usage("t1", "llm_call", days=30)

        assert len(daily) >= 2  # at least yesterday and two_days_ago
        # Find yesterday entry
        yesterday_date = yesterday.strftime("%Y-%m-%d")
        yesterday_entry = [d for d in daily if d["date"] == yesterday_date]
        assert len(yesterday_entry) == 1
        assert yesterday_entry[0]["count"] == 10  # 3 + 7
        assert yesterday_entry[0]["cost"] == 100   # 30 + 70

    def test_get_daily_usage_resource_filter(self, store):
        today = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)

        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.LLM_CALL,
            quantity=5, cost_cents=50, timestamp=yesterday,
        ))
        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.SEARCH,
            quantity=8, cost_cents=16, timestamp=yesterday,
        ))

        llm_daily = store.get_daily_usage("t1", "llm_call", days=30)
        search_daily = store.get_daily_usage("t1", "search", days=30)

        assert len(llm_daily) >= 1
        assert len(search_daily) >= 1
        # search results should not contain llm_call data
        search_entry = [d for d in search_daily
                        if d["date"] == yesterday.strftime("%Y-%m-%d")]
        assert search_entry[0]["count"] == 8


class TestUserProfile:
    def test_get_user_profile(self, store):
        # Create varied usage for user u1
        for _ in range(5):
            store.record_event(_make_event(
                tenant_id="t1", user_id="u1", resource=UsageResource.MEMORY,
                timestamp=_recent_ts(0),
            ))
        for _ in range(3):
            store.record_event(_make_event(
                tenant_id="t1", user_id="u1", resource=UsageResource.SEARCH,
                timestamp=_recent_ts(0),
            ))
        for _ in range(2):
            store.record_event(_make_event(
                tenant_id="t1", user_id="u1", resource=UsageResource.COACH,
                timestamp=_recent_ts(0),
            ))

        profile = store.get_user_profile("t1", "u1")

        assert isinstance(profile, UserProfile)
        assert profile.tenant_id == "t1"
        assert profile.user_id == "u1"
        assert profile.total_memories == 5
        assert profile.total_searches == 3
        assert profile.coach_sessions == 2
        assert profile.active_days >= 1
        assert 0 <= profile.engagement_score <= 100
        # With only one user, engagement_score should be 50
        assert profile.engagement_score == 50
        # With one user, top 20% threshold means this user IS power user
        # if they have events
        assert profile.is_power_user is True
        # preferred_features should rank memory first
        assert len(profile.preferred_features) >= 1
        assert profile.preferred_features[0] == "memory"

    def test_get_user_profile_multiple_users(self, store):
        # User u1: heavy user (10 events)
        for _ in range(10):
            store.record_event(_make_event(
                tenant_id="t1", user_id="u1", resource=UsageResource.LLM_CALL,
                timestamp=_recent_ts(0),
            ))
        # User u2: light user (2 events)
        for _ in range(2):
            store.record_event(_make_event(
                tenant_id="t1", user_id="u2", resource=UsageResource.LLM_CALL,
                timestamp=_recent_ts(0),
            ))

        heavy = store.get_user_profile("t1", "u1")
        light = store.get_user_profile("t1", "u2")

        # Heavy user should score higher
        assert heavy.engagement_score > light.engagement_score
        # Heavy user (top 20% by event count) should be power user
        assert heavy.is_power_user is True
        assert light.is_power_user is False

    def test_get_user_profile_no_events(self, store):
        profile = store.get_user_profile("t_none", "u_none")
        assert profile.tenant_id == "t_none"
        assert profile.user_id == "u_none"
        assert profile.total_memories == 0
        assert profile.total_searches == 0
        assert profile.active_days == 0
        assert profile.engagement_score == 0


class TestPlatformStats:
    def test_get_platform_stats(self, store):
        # Insert subscriptions
        _insert_subscription(store, tenant_id="t1", plan_tier="professional",
                             status="active", billing_cycle="monthly")
        _insert_subscription(store, tenant_id="t2", plan_tier="personal",
                             status="trial", billing_cycle="monthly")
        _insert_subscription(store, tenant_id="t3", plan_tier="free",
                             status="active", billing_cycle="monthly")

        # Insert usage events for this month
        now = datetime.now(timezone.utc)
        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.LLM_CALL,
            quantity=5, cost_cents=50, timestamp=now,
        ))

        stats = store.get_platform_stats()

        assert isinstance(stats, PlatformStats)
        assert stats.total_tenants == 3
        assert stats.trial_tenants == 1
        assert stats.paying_tenants == 1  # professional active = paying
        # conversion_rate = paying / (paying + trial) = 1 / 2 = 0.5
        assert stats.conversion_rate == 0.5
        assert stats.total_revenue_cents == 50

    def test_get_platform_stats_empty(self, store):
        stats = store.get_platform_stats()
        assert stats.total_tenants == 0
        assert stats.mrr_cents == 0
        assert stats.arr_cents == 0


class TestTenantUsageSummary:
    def test_get_tenant_usage_summary(self, store):
        yesterday = _recent_ts(1)
        two_days_ago = _recent_ts(2)
        thirty_one_days_ago = _recent_ts(31)  # outside default 30-day window

        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.LLM_CALL,
            quantity=10, cost_cents=100, timestamp=yesterday,
        ))
        store.record_event(_make_event(
            tenant_id="t1", user_id="u2", resource=UsageResource.LLM_CALL,
            quantity=5, cost_cents=30, timestamp=two_days_ago,
        ))
        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.SEARCH,
            quantity=3, cost_cents=9, timestamp=yesterday,
        ))
        # This event is outside the 30-day window, should be excluded
        store.record_event(_make_event(
            tenant_id="t1", user_id="u1", resource=UsageResource.LLM_CALL,
            quantity=999, cost_cents=9999, timestamp=thirty_one_days_ago,
        ))

        summary = store.get_tenant_usage_summary("t1", days=30)

        assert summary["tenant_id"] == "t1"
        assert summary["period_days"] == 30
        assert summary["active_users"] == 2
        # 3 events inside window (not the 31-days-ago one)
        assert summary["total_events"] == 3
        assert summary["total_cost_cents"] == 139  # 100 + 30 + 9
        assert "llm_call" in summary["by_resource"]
        assert "search" in summary["by_resource"]
        assert summary["by_resource"]["llm_call"]["quantity"] == 15  # 10 + 5
        assert summary["by_resource"]["search"]["quantity"] == 3
