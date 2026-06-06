"""Pytest test suite for subscription module — adapter store and domain models.

Tests ≥18 functions covering:
  - SubscriptionStoreAdapter CRUD, plan changes, cancel/resume, listing, counting
  - PlanLimit definitions and pricing
  - Subscription domain methods (days_remaining, is_active, is_trial)
  - BillingCycle enum values

Uses in-memory SQLite so no disk I/O.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.subscription_store import SubscriptionStoreAdapter
from src.core.subscription import (
    PLANS,
    PLAN_PRICES,
    BillingCycle,
    PlanLimit,
    PlanTier,
    Subscription,
    SubscriptionStatus,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_settings(**overrides):
    """Create a test Settings instance, suppressing any local .env file."""
    kwargs = {
        "_env_file": None,
        "deepseek_api_key": "test-key",
        "sqlite_db_path": ":memory:",
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


def make_sub(
    tenant_id: str = "tenant-001",
    plan_tier: PlanTier = PlanTier.FREE,
    status: SubscriptionStatus = SubscriptionStatus.TRIAL,
    billing_cycle: BillingCycle = BillingCycle.MONTHLY,
    current_period_end: datetime | None = None,
    trial_end: datetime | None = None,
    **kwargs,
) -> Subscription:
    """Build a Subscription object with sensible defaults."""
    defaults: dict = {
        "tenant_id": tenant_id,
        "plan_tier": plan_tier,
        "status": status,
        "billing_cycle": billing_cycle,
        "current_period_end": current_period_end,
        "trial_end": trial_end,
    }
    defaults.update(kwargs)
    return Subscription(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def store() -> SubscriptionStoreAdapter:
    """In-memory SubscriptionStoreAdapter — fresh per test."""
    adapter = SubscriptionStoreAdapter(make_settings(), db_path=":memory:")
    yield adapter
    adapter.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 1–10: Adapter tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSubscriptionStoreAdapter:
    """Integration tests against the SQLite-backed SubscriptionStoreAdapter."""

    # ── 1. create ──────────────────────────────────────────────────────────

    def test_create_subscription(self, store: SubscriptionStoreAdapter) -> None:
        """Create a free-tier subscription and verify every persisted field."""
        sub = make_sub(tenant_id="t-1", plan_tier=PlanTier.FREE, status=SubscriptionStatus.TRIAL)
        created = store.create_subscription(sub)

        assert created is sub  # same object returned
        assert created.id.startswith("sub_")
        assert len(created.id) > 4
        assert created.tenant_id == "t-1"
        assert created.plan_tier == PlanTier.FREE
        assert created.status == SubscriptionStatus.TRIAL
        assert created.billing_cycle == BillingCycle.MONTHLY
        assert created.current_period_start is not None
        assert created.created_at is not None
        assert created.updated_at is not None
        assert created.auto_renew is True

    def test_create_subscription_with_coupon(self, store: SubscriptionStoreAdapter) -> None:
        """Coupon code is round-tripped correctly."""
        sub = make_sub(tenant_id="t-coupon", coupon_code="LAUNCH50")
        store.create_subscription(sub)
        fetched = store.get_subscription("t-coupon")
        assert fetched is not None
        assert fetched.coupon_code == "LAUNCH50"

    def test_create_duplicate_tenant_raises(self, store: SubscriptionStoreAdapter) -> None:
        """Inserting a second subscription for the same tenant_id must fail
        because tenant_id has a UNIQUE constraint."""
        store.create_subscription(make_sub(tenant_id="t-dup"))
        with pytest.raises(Exception):  # sqlite3.IntegrityError or sqlite_utils wrapper
            store.create_subscription(make_sub(tenant_id="t-dup"))

    # ── 2. get ─────────────────────────────────────────────────────────────

    def test_get_subscription(self, store: SubscriptionStoreAdapter) -> None:
        """Get an existing subscription by tenant_id."""
        store.create_subscription(make_sub(tenant_id="t-2", plan_tier=PlanTier.PERSONAL))
        fetched = store.get_subscription("t-2")
        assert fetched is not None
        assert fetched.tenant_id == "t-2"
        assert fetched.plan_tier == PlanTier.PERSONAL

    # ── 3. get nonexistent ─────────────────────────────────────────────────

    def test_get_nonexistent_subscription(self, store: SubscriptionStoreAdapter) -> None:
        """Querying an unknown tenant_id returns None."""
        result = store.get_subscription("no-such-tenant")
        assert result is None

    # ── 4. change plan ─────────────────────────────────────────────────────

    def test_change_plan(self, store: SubscriptionStoreAdapter) -> None:
        """Upgrade from FREE to PERSONAL with YEARLY billing cycle."""
        store.create_subscription(make_sub(tenant_id="t-4"))
        updated = store.change_plan("t-4", PlanTier.PERSONAL, BillingCycle.YEARLY)

        assert updated.plan_tier == PlanTier.PERSONAL
        assert updated.billing_cycle == BillingCycle.YEARLY

    def test_change_plan_to_enterprise(self, store: SubscriptionStoreAdapter) -> None:
        """Upgrade to ENTERPRISE tier."""
        store.create_subscription(make_sub(tenant_id="t-ent"))
        updated = store.change_plan("t-ent", PlanTier.ENTERPRISE, BillingCycle.MONTHLY)

        assert updated.plan_tier == PlanTier.ENTERPRISE
        assert updated.plan_limit().search_count == 999999

    def test_change_plan_same_tier_different_cycle(self, store: SubscriptionStoreAdapter) -> None:
        """Changing billing cycle without changing tier."""
        store.create_subscription(
            make_sub(tenant_id="t-cycle", plan_tier=PlanTier.PROFESSIONAL, billing_cycle=BillingCycle.MONTHLY)
        )
        updated = store.change_plan("t-cycle", PlanTier.PROFESSIONAL, BillingCycle.YEARLY)
        assert updated.plan_tier == PlanTier.PROFESSIONAL
        assert updated.billing_cycle == BillingCycle.YEARLY

    # ── 5. change plan invalid tenant ──────────────────────────────────────

    def test_change_plan_invalid_tenant(self, store: SubscriptionStoreAdapter) -> None:
        """Changing plan for a non-existent tenant raises ValueError."""
        with pytest.raises(ValueError, match="No subscription found"):
            store.change_plan("ghost-tenant", PlanTier.PERSONAL, BillingCycle.MONTHLY)

    # ── 6. cancel ──────────────────────────────────────────────────────────

    def test_cancel_subscription(self, store: SubscriptionStoreAdapter) -> None:
        """Cancel sets status to CANCELED, populates canceled_at, disables auto_renew."""
        store.create_subscription(make_sub(tenant_id="t-6"))
        cancelled = store.cancel_subscription("t-6")

        assert cancelled.status == SubscriptionStatus.CANCELED
        assert cancelled.canceled_at is not None
        assert cancelled.auto_renew is False

    def test_cancel_nonexistent_subscription(self, store: SubscriptionStoreAdapter) -> None:
        """Cancelling a non-existent tenant raises ValueError."""
        with pytest.raises(ValueError, match="No subscription found"):
            store.cancel_subscription("ghost-tenant")

    # ── 7. resume ──────────────────────────────────────────────────────────

    def test_resume_subscription(self, store: SubscriptionStoreAdapter) -> None:
        """After cancel, resume sets status back to ACTIVE and clears canceled_at."""
        store.create_subscription(make_sub(tenant_id="t-7"))
        store.cancel_subscription("t-7")

        # Simulate resume as the router does: update status + auto_renew + clear canceled_at
        sub = store.get_subscription("t-7")
        assert sub is not None
        sub.status = SubscriptionStatus.ACTIVE
        sub.auto_renew = True
        sub.canceled_at = None
        store.update_subscription(sub)

        resumed = store.get_subscription("t-7")
        assert resumed is not None
        assert resumed.status == SubscriptionStatus.ACTIVE
        assert resumed.canceled_at is None
        assert resumed.auto_renew is True

    # ── 8. list ────────────────────────────────────────────────────────────

    def test_list_subscriptions_all(self, store: SubscriptionStoreAdapter) -> None:
        """list_subscriptions() with no filter returns all rows."""
        store.create_subscription(make_sub(tenant_id="t-a", status=SubscriptionStatus.ACTIVE))
        store.create_subscription(make_sub(tenant_id="t-b", status=SubscriptionStatus.TRIAL))
        store.create_subscription(make_sub(tenant_id="t-c", status=SubscriptionStatus.CANCELED))

        all_subs = store.list_subscriptions()
        assert len(all_subs) == 3

    def test_list_subscriptions_filter_by_status(self, store: SubscriptionStoreAdapter) -> None:
        """list_subscriptions(status=...) returns only matching rows."""
        store.create_subscription(make_sub(tenant_id="t-f1", status=SubscriptionStatus.ACTIVE))
        store.create_subscription(make_sub(tenant_id="t-f2", status=SubscriptionStatus.TRIAL))
        store.create_subscription(make_sub(tenant_id="t-f3", status=SubscriptionStatus.ACTIVE))

        active_subs = store.list_subscriptions(status=SubscriptionStatus.ACTIVE.value)
        assert len(active_subs) == 2
        for s in active_subs:
            assert s.status == SubscriptionStatus.ACTIVE

    def test_list_subscriptions_empty_store(self, store: SubscriptionStoreAdapter) -> None:
        """Empty store returns empty list."""
        assert store.list_subscriptions() == []

    # ── 9. count by tier ───────────────────────────────────────────────────

    def test_count_by_tier(self, store: SubscriptionStoreAdapter) -> None:
        """count_by_tier() returns correct aggregate per tier."""
        for i in range(3):
            store.create_subscription(make_sub(tenant_id=f"free-{i}", plan_tier=PlanTier.FREE))
        for i in range(2):
            store.create_subscription(make_sub(tenant_id=f"pers-{i}", plan_tier=PlanTier.PERSONAL))
        store.create_subscription(make_sub(tenant_id="ent-0", plan_tier=PlanTier.ENTERPRISE))

        counts = store.count_by_tier()
        assert counts[PlanTier.FREE.value] == 3
        assert counts[PlanTier.PERSONAL.value] == 2
        assert counts[PlanTier.ENTERPRISE.value] == 1

    def test_count_by_tier_empty_store(self, store: SubscriptionStoreAdapter) -> None:
        """Empty store returns empty dict."""
        assert store.count_by_tier() == {}

    # ── 10. get active subscriptions ───────────────────────────────────────

    def test_get_active_subscriptions(self, store: SubscriptionStoreAdapter) -> None:
        """Only subscriptions with status ACTIVE or TRIAL are returned."""
        store.create_subscription(make_sub(tenant_id="t-10a", status=SubscriptionStatus.ACTIVE))
        store.create_subscription(make_sub(tenant_id="t-10b", status=SubscriptionStatus.TRIAL))
        store.create_subscription(make_sub(tenant_id="t-10c", status=SubscriptionStatus.CANCELED))
        store.create_subscription(make_sub(tenant_id="t-10d", status=SubscriptionStatus.EXPIRED))
        store.create_subscription(make_sub(tenant_id="t-10e", status=SubscriptionStatus.PAST_DUE))
        store.create_subscription(make_sub(tenant_id="t-10f", status=SubscriptionStatus.PAUSED))

        active = store.get_active_subscriptions()
        assert len(active) == 2
        statuses = {s.status for s in active}
        assert statuses == {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}

    def test_get_active_subscriptions_empty_store(self, store: SubscriptionStoreAdapter) -> None:
        """No subscriptions → empty list."""
        assert store.get_active_subscriptions() == []

    # ── 11. update_subscription ────────────────────────────────────────────

    def test_update_subscription_persisted(self, store: SubscriptionStoreAdapter) -> None:
        """update_subscription writes changes to the database."""
        store.create_subscription(make_sub(tenant_id="t-upd", coupon_code=None))
        sub = store.get_subscription("t-upd")
        assert sub is not None
        sub.coupon_code = "SUMMER2025"
        sub.auto_renew = False
        store.update_subscription(sub)

        refetched = store.get_subscription("t-upd")
        assert refetched is not None
        assert refetched.coupon_code == "SUMMER2025"
        assert refetched.auto_renew is False


# ═══════════════════════════════════════════════════════════════════════════════
# 11–12: PlanLimit domain tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestPlanLimits:
    """Verify that PlanLimit entries in PLANS match expected values."""

    def test_plan_limit_free(self) -> None:
        limit = PLANS[PlanTier.FREE]
        assert limit.tier == PlanTier.FREE
        assert limit.memory_count == 100
        assert limit.search_count == 10
        assert limit.storage_mb == 10
        assert limit.import_per_day == 3
        assert limit.sync_connectors == 1
        assert limit.knowledge_graph is False
        assert limit.ai_coach is False
        assert limit.team_members == 1
        assert limit.api_access is False
        assert limit.priority_support is False
        assert limit.llm_calls_per_day == 20
        assert limit.embedding_calls_per_day == 50

    def test_plan_limit_personal(self) -> None:
        limit = PLANS[PlanTier.PERSONAL]
        assert limit.memory_count == 1000
        assert limit.search_count == 100
        assert limit.storage_mb == 100
        assert limit.import_per_day == 10
        assert limit.sync_connectors == 3
        assert limit.knowledge_graph is True
        assert limit.ai_coach is True
        assert limit.api_access is False

    def test_plan_limit_enterprise(self) -> None:
        """Enterprise tier has 'unlimited' values (999999) and all features enabled."""
        limit = PLANS[PlanTier.ENTERPRISE]
        assert limit.search_count == 999999
        assert limit.import_per_day == 999999
        assert limit.team_members == 999999
        assert limit.memory_count == 100000
        assert limit.sync_connectors == 100
        assert limit.knowledge_graph is True
        assert limit.ai_coach is True
        assert limit.api_access is True
        assert limit.priority_support is True

    def test_plan_limit_all_tiers_have_required_fields(self) -> None:
        """Every tier in PLANS has all PlanLimit fields set (no field is None/0 for criticals)."""
        for tier, limit in PLANS.items():
            assert limit.tier == tier
            assert isinstance(limit.memory_count, int) and limit.memory_count > 0
            assert isinstance(limit.search_count, int) and limit.search_count > 0
            assert isinstance(limit.storage_mb, int) and limit.storage_mb > 0
            assert isinstance(limit.llm_calls_per_day, int) and limit.llm_calls_per_day > 0
            assert isinstance(limit.embedding_calls_per_day, int) and limit.embedding_calls_per_day > 0

    def test_plan_limit_as_dict(self) -> None:
        """as_dict() returns expected keys and values."""
        limit = PLANS[PlanTier.FREE]
        d = limit.as_dict()
        assert d["tier"] == "free"
        assert d["memory_count"] == 100
        assert d["knowledge_graph"] is False
        assert "search_count" in d
        assert "api_access" in d
        assert "priority_support" in d


# ═══════════════════════════════════════════════════════════════════════════════
# 13–14: PLAN_PRICES domain tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestPlanPrices:
    """Verify pricing table values."""

    def test_plan_prices_free(self) -> None:
        prices = PLAN_PRICES[PlanTier.FREE]
        assert prices[BillingCycle.MONTHLY] == 0
        assert prices[BillingCycle.YEARLY] == 0

    def test_plan_prices_personal(self) -> None:
        prices = PLAN_PRICES[PlanTier.PERSONAL]
        assert prices[BillingCycle.MONTHLY] == 2900
        assert prices[BillingCycle.YEARLY] == 29000

    def test_plan_prices_professional(self) -> None:
        prices = PLAN_PRICES[PlanTier.PROFESSIONAL]
        assert prices[BillingCycle.MONTHLY] == 9900
        assert prices[BillingCycle.YEARLY] == 99000

    def test_plan_prices_team(self) -> None:
        prices = PLAN_PRICES[PlanTier.TEAM]
        assert prices[BillingCycle.MONTHLY] == 29900
        assert prices[BillingCycle.YEARLY] == 299000

    def test_plan_prices_enterprise(self) -> None:
        prices = PLAN_PRICES[PlanTier.ENTERPRISE]
        assert prices[BillingCycle.MONTHLY] == 99900
        assert prices[BillingCycle.YEARLY] == 999000

    def test_plan_prices_all_tiers_have_monthly_and_yearly(self) -> None:
        """Every tier defines both MONTHLY and YEARLY prices."""
        for tier in PlanTier:
            prices = PLAN_PRICES[tier]
            assert BillingCycle.MONTHLY in prices, f"{tier} missing MONTHLY price"
            assert BillingCycle.YEARLY in prices, f"{tier} missing YEARLY price"
            assert isinstance(prices[BillingCycle.MONTHLY], int)
            assert isinstance(prices[BillingCycle.YEARLY], int)

    def test_plan_prices_free_monthly_and_yearly_both_zero(self) -> None:
        """Free plan is zero in both cycles."""
        prices = PLAN_PRICES[PlanTier.FREE]
        assert prices[BillingCycle.MONTHLY] == 0
        assert prices[BillingCycle.YEARLY] == 0

    def test_plan_prices_yearly_equals_monthly_times_ten(self) -> None:
        """Yearly price == 10 * monthly price for all paid plans."""
        for tier in [PlanTier.PERSONAL, PlanTier.PROFESSIONAL, PlanTier.TEAM, PlanTier.ENTERPRISE]:
            prices = PLAN_PRICES[tier]
            assert prices[BillingCycle.YEARLY] == 10 * prices[BillingCycle.MONTHLY], (
                f"{tier}: yearly={prices[BillingCycle.YEARLY]} != 10 * monthly={prices[BillingCycle.MONTHLY]}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 15–18: Subscription domain model tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSubscriptionDaysRemaining:
    """Tests for Subscription.days_remaining()."""

    def test_days_remaining_with_future_end(self) -> None:
        """current_period_end 30 days ahead → days_remaining ~= 30.

        Timedelta.days truncates, so sub-second clock drift may yield 29.
        """
        future = _utcnow() + timedelta(days=30)
        sub = make_sub(current_period_end=future)
        assert 29 <= sub.days_remaining() <= 30

    def test_days_remaining_with_past_end(self) -> None:
        """End date in the past → days_remaining == 0 (clamped)."""
        past = _utcnow() - timedelta(days=5)
        sub = make_sub(current_period_end=past)
        assert sub.days_remaining() == 0

    def test_days_remaining_no_end_date(self) -> None:
        """Neither current_period_end nor trial_end → 0."""
        sub = make_sub(current_period_end=None, trial_end=None)
        assert sub.days_remaining() == 0

    def test_days_remaining_uses_trial_end_when_no_period_end(self) -> None:
        """When current_period_end is None but trial_end is set, use trial_end."""
        future_trial = _utcnow() + timedelta(days=14)
        sub = make_sub(current_period_end=None, trial_end=future_trial)
        assert 13 <= sub.days_remaining() <= 14

    def test_days_remaining_prefers_period_over_trial(self) -> None:
        """When both are set, current_period_end takes precedence."""
        period_end = _utcnow() + timedelta(days=10)
        trial_end = _utcnow() + timedelta(days=20)
        sub = make_sub(current_period_end=period_end, trial_end=trial_end)
        assert 9 <= sub.days_remaining() <= 10  # uses period_end (10), not trial_end (20)

    def test_days_remaining_one_day_left(self) -> None:
        """Edge: near-boundary — at least 1 day remaining when 2 days ahead."""
        three_days = _utcnow() + timedelta(days=3)
        sub = make_sub(current_period_end=three_days)
        assert sub.days_remaining() >= 1


class TestSubscriptionIsActive:
    """Tests for Subscription.is_active()."""

    def test_is_active_when_active(self) -> None:
        sub = make_sub(status=SubscriptionStatus.ACTIVE)
        assert sub.is_active() is True

    def test_is_active_when_trial(self) -> None:
        sub = make_sub(status=SubscriptionStatus.TRIAL)
        assert sub.is_active() is True

    def test_is_active_when_canceled(self) -> None:
        sub = make_sub(status=SubscriptionStatus.CANCELED)
        assert sub.is_active() is False

    def test_is_active_when_expired(self) -> None:
        sub = make_sub(status=SubscriptionStatus.EXPIRED)
        assert sub.is_active() is False

    def test_is_active_when_past_due(self) -> None:
        sub = make_sub(status=SubscriptionStatus.PAST_DUE)
        assert sub.is_active() is False

    def test_is_active_when_paused(self) -> None:
        sub = make_sub(status=SubscriptionStatus.PAUSED)
        assert sub.is_active() is False


class TestSubscriptionIsTrial:
    """Tests for Subscription.is_trial()."""

    def test_is_trial_when_trial(self) -> None:
        sub = make_sub(status=SubscriptionStatus.TRIAL)
        assert sub.is_trial() is True

    def test_is_trial_when_active(self) -> None:
        sub = make_sub(status=SubscriptionStatus.ACTIVE)
        assert sub.is_trial() is False

    def test_is_trial_when_canceled(self) -> None:
        sub = make_sub(status=SubscriptionStatus.CANCELED)
        assert sub.is_trial() is False


class TestBillingCycle:
    """Enum value verification."""

    def test_billing_cycle_values(self) -> None:
        assert BillingCycle.MONTHLY.value == "monthly"
        assert BillingCycle.YEARLY.value == "yearly"
        assert BillingCycle.LIFETIME.value == "lifetime"

    def test_billing_cycle_from_string(self) -> None:
        assert BillingCycle("monthly") == BillingCycle.MONTHLY
        assert BillingCycle("yearly") == BillingCycle.YEARLY
        assert BillingCycle("lifetime") == BillingCycle.LIFETIME

    def test_billing_cycle_invalid_string(self) -> None:
        with pytest.raises(ValueError):
            BillingCycle("quarterly")


class TestSubscriptionStatus:
    """SubscriptionStatus enum value verification."""

    def test_all_statuses_exist(self) -> None:
        expected = {"active", "past_due", "canceled", "expired", "trial", "paused"}
        actual = {s.value for s in SubscriptionStatus}
        assert actual == expected


class TestPlanTier:
    """PlanTier enum value verification."""

    def test_all_tiers_exist(self) -> None:
        expected = {"free", "personal", "professional", "team", "enterprise"}
        actual = {t.value for t in PlanTier}
        assert actual == expected

    def test_tier_from_string(self) -> None:
        assert PlanTier("free") == PlanTier.FREE
        assert PlanTier("enterprise") == PlanTier.ENTERPRISE


class TestSubscriptionPlanLimit:
    """Tests for Subscription.plan_limit()."""

    def test_plan_limit_returns_correct_tier_limit(self) -> None:
        sub = make_sub(plan_tier=PlanTier.PERSONAL)
        limit = sub.plan_limit()
        assert limit.tier == PlanTier.PERSONAL
        assert limit.memory_count == 1000

    def test_plan_limit_changes_after_change_plan(self, store: SubscriptionStoreAdapter) -> None:
        """After changing plan, plan_limit() reflects the new tier."""
        store.create_subscription(make_sub(tenant_id="t-pl", plan_tier=PlanTier.FREE))
        store.change_plan("t-pl", PlanTier.PROFESSIONAL, BillingCycle.MONTHLY)
        sub = store.get_subscription("t-pl")
        assert sub is not None
        limit = sub.plan_limit()
        assert limit.tier == PlanTier.PROFESSIONAL
        assert limit.memory_count == 5000


# ═══════════════════════════════════════════════════════════════════════════════
# Edge cases & integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Additional edge case tests for the adapter and domain."""

    def test_change_plan_and_then_cancel(self, store: SubscriptionStoreAdapter) -> None:
        """Smooth sequence: create → change plan → cancel → resume."""
        store.create_subscription(make_sub(tenant_id="t-seq"))
        store.change_plan("t-seq", PlanTier.PERSONAL, BillingCycle.MONTHLY)

        cancelled = store.cancel_subscription("t-seq")
        assert cancelled.status == SubscriptionStatus.CANCELED

        sub = store.get_subscription("t-seq")
        sub.status = SubscriptionStatus.ACTIVE
        sub.auto_renew = True
        sub.canceled_at = None
        store.update_subscription(sub)

        resumed = store.get_subscription("t-seq")
        assert resumed.status == SubscriptionStatus.ACTIVE
        assert resumed.plan_tier == PlanTier.PERSONAL

    def test_lifetime_billing_cycle_persists(self, store: SubscriptionStoreAdapter) -> None:
        """LIFETIME billing cycle round-trips through the store."""
        sub = make_sub(tenant_id="t-life", billing_cycle=BillingCycle.LIFETIME, plan_tier=PlanTier.ENTERPRISE)
        store.create_subscription(sub)
        fetched = store.get_subscription("t-life")
        assert fetched is not None
        assert fetched.billing_cycle == BillingCycle.LIFETIME

    def test_subscription_defaults(self) -> None:
        """Verify Subscription dataclass defaults."""
        sub = Subscription(tenant_id="t-default")
        assert sub.plan_tier == PlanTier.FREE
        assert sub.status == SubscriptionStatus.TRIAL
        assert sub.billing_cycle == BillingCycle.MONTHLY
        assert sub.auto_renew is True
        assert sub.coupon_code is None
        assert sub.canceled_at is None
        assert sub.id.startswith("sub_")

    def test_subscription_explicit_id(self) -> None:
        """Custom subscription id is preserved."""
        sub = make_sub(tenant_id="t-custom-id", id="sub_my_custom_123")
        assert sub.id == "sub_my_custom_123"

    def test_auto_renew_defaults_true(self) -> None:
        sub = Subscription(tenant_id="t-ar")
        assert sub.auto_renew is True
