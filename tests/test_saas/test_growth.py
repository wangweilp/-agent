"""GrowthStoreAdapter 单元测试。

覆盖：invites / referrals / coupons / coupon redemptions / trials。
"""
import os
import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.growth_store import GrowthStoreAdapter
from src.adapters.config import Settings
from src.core.growth import (
    Invite,
    InviteStatus,
    Referral,
    ReferralStatus,
    Coupon,
    CouponType,
    CouponStatus,
    CouponRedemption,
    TrialRecord,
    TrialStatus,
)
from datetime import datetime, timezone, timedelta


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def settings():
    return Settings(_env_file=None)


@pytest.fixture
def store(settings):
    store = GrowthStoreAdapter(config=settings, db_path=":memory:")
    yield store
    store.close()


# ── Helpers ─────────────────────────────────────────────────────────────

def _future(days=30):
    return datetime.now(timezone.utc) + timedelta(days=days)


def _past(days=10):
    return datetime.now(timezone.utc) - timedelta(days=days)


# ═══════════════════════════════════════════════════════════════════════════
# Invite Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestInvite:
    def test_create_invite(self, store):
        invite = Invite(
            inviter_tenant_id="t1",
            inviter_user_id="u1",
            invitee_email="friend@example.com",
        )
        result = store.create_invite(invite)

        assert result.id == invite.id
        # Auto-generated invite_code should be 8 hex chars
        assert len(invite.invite_code) == 8
        assert result.invite_code == invite.invite_code
        assert result.status == InviteStatus.PENDING
        assert result.invitee_email == "friend@example.com"

    def test_get_invite_by_code(self, store):
        invite = Invite(
            inviter_tenant_id="t1",
            inviter_user_id="u1",
            invitee_email="friend@example.com",
        )
        store.create_invite(invite)

        fetched = store.get_invite_by_code(invite.invite_code)
        assert fetched is not None
        assert fetched.id == invite.id
        assert fetched.invite_code == invite.invite_code
        assert fetched.invitee_email == "friend@example.com"

    def test_get_invite_by_code_not_found(self, store):
        result = store.get_invite_by_code("nonexistent")
        assert result is None

    def test_accept_invite(self, store):
        invite = Invite(
            inviter_tenant_id="t1",
            inviter_user_id="u1",
            invitee_email="friend@example.com",
        )
        store.create_invite(invite)

        result = store.accept_invite(
            invite.id,
            invitee_user_id="u2",
            invitee_tenant_id="t2",
        )

        assert result.status == InviteStatus.ACCEPTED
        assert result.accepted_at is not None
        assert result.accepted_at > invite.created_at

    def test_expired_invite(self, store):
        """Expired invite: verify expires_at is in the past.

        Note: the current adapter does not enforce expiry on accept_invite.
        The invite model records expires_at for the caller to check.
        """
        invite = Invite(
            inviter_tenant_id="t1",
            inviter_user_id="u1",
            invitee_email="friend@example.com",
            expires_at=_past(days=1),
        )
        store.create_invite(invite)

        # Verify the invite is indeed expired
        assert invite.expires_at < datetime.now(timezone.utc)

        # Currently, accept_invite does not reject expired invites.
        # When expiry enforcement is added, this should raise an error.
        result = store.accept_invite(invite.id, "u2", "t2")
        assert result.status == InviteStatus.ACCEPTED

    def test_list_invites(self, store):
        store.create_invite(Invite(
            inviter_tenant_id="t1", inviter_user_id="u1",
            invitee_email="a@example.com",
        ))
        store.create_invite(Invite(
            inviter_tenant_id="t1", inviter_user_id="u1",
            invitee_email="b@example.com",
        ))
        # Different tenant — should not appear
        store.create_invite(Invite(
            inviter_tenant_id="t2", inviter_user_id="u3",
            invitee_email="c@example.com",
        ))

        invites = store.list_invites("t1")
        assert len(invites) == 2
        emails = {inv.invitee_email for inv in invites}
        assert emails == {"a@example.com", "b@example.com"}

    def test_list_invites_empty(self, store):
        invites = store.list_invites("t_none")
        assert invites == []


# ═══════════════════════════════════════════════════════════════════════════
# Referral Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestReferral:
    def test_create_referral(self, store):
        referral = Referral(
            referrer_tenant_id="t1",
            referrer_user_id="u1",
        )
        result = store.create_referral(referral)

        assert result.id == referral.id
        assert len(referral.referral_code) == 8  # auto-generated
        assert result.referral_code == referral.referral_code
        assert result.status == ReferralStatus.PENDING

    def test_create_referral_with_reward(self, store):
        referral = Referral(
            referrer_tenant_id="t1",
            referrer_user_id="u1",
            reward_amount_cents=500,
        )
        result = store.create_referral(referral)
        assert result.reward_amount_cents == 500

    def test_complete_referral(self, store):
        referral = Referral(
            referrer_tenant_id="t1",
            referrer_user_id="u1",
        )
        store.create_referral(referral)

        result = store.complete_referral(
            referral.id,
            referred_tenant_id="t2",
            referred_user_id="u2",
        )

        assert result.status == ReferralStatus.COMPLETED
        assert result.referred_tenant_id == "t2"
        assert result.referred_user_id == "u2"
        assert result.completed_at is not None

    def test_get_referral_stats(self, store):
        # Create 3 referrals, complete 1
        for _ in range(3):
            ref = Referral(
                referrer_tenant_id="t1",
                referrer_user_id="u1",
                reward_amount_cents=200,
            )
            store.create_referral(ref)

        refs = store.list_referrals("t1")
        store.complete_referral(refs[0].id, "t2", "u2")

        stats = store.get_referral_stats("t1")
        assert stats["total_referrals"] == 3
        assert stats["completed_referrals"] == 1
        assert stats["total_rewards_cents"] == 600  # 3 * 200

    def test_get_referral_stats_empty(self, store):
        stats = store.get_referral_stats("t_none")
        assert stats["total_referrals"] == 0
        assert stats["completed_referrals"] == 0
        assert stats["total_rewards_cents"] == 0

    def test_get_referral_by_code(self, store):
        referral = Referral(
            referrer_tenant_id="t1",
            referrer_user_id="u1",
        )
        store.create_referral(referral)

        fetched = store.get_referral_by_code(referral.referral_code)
        assert fetched is not None
        assert fetched.id == referral.id

    def test_get_referral_by_code_not_found(self, store):
        result = store.get_referral_by_code("nonexistent")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# Coupon Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCoupon:
    def test_create_coupon(self, store):
        coupon = Coupon(
            code="WELCOME20",
            coupon_type=CouponType.PERCENTAGE,
            value=20,
            valid_until=_future(30),
        )
        result = store.create_coupon(coupon)

        assert result.id == coupon.id
        assert result.code == "WELCOME20"
        assert result.coupon_type == CouponType.PERCENTAGE
        assert result.value == 20
        assert result.status == CouponStatus.ACTIVE
        assert result.usage_count == 0

    def test_get_coupon_by_code(self, store):
        coupon = Coupon(
            code="SAVE50",
            coupon_type=CouponType.FIXED_AMOUNT,
            value=500,
            valid_until=_future(30),
        )
        store.create_coupon(coupon)

        fetched = store.get_coupon_by_code("SAVE50")
        assert fetched is not None
        assert fetched.code == "SAVE50"
        assert fetched.value == 500
        # get_coupon_by_code increments usage_count as a side effect
        assert fetched.usage_count == 1

    def test_get_coupon_by_code_not_found(self, store):
        result = store.get_coupon_by_code("NONEXISTENT")
        assert result is None

    def test_redeem_coupon(self, store):
        coupon = Coupon(
            code="REDEEM10",
            coupon_type=CouponType.PERCENTAGE,
            value=10,
            valid_until=_future(30),
        )
        store.create_coupon(coupon)

        redemption = CouponRedemption(
            coupon_id=coupon.id,
            tenant_id="t1",
            code=coupon.code,
            discount_cents=100,
        )
        result = store.redeem_coupon(redemption)

        assert result.id == redemption.id
        assert result.discount_cents == 100
        assert result.tenant_id == "t1"

        # Verify usage_count was incremented on the coupon itself
        # Use get_coupon (no side effect) to verify
        updated = store.get_coupon(coupon.id)
        assert updated.usage_count == 1

    def test_coupon_usage_limit(self, store):
        coupon = Coupon(
            code="ONCEONLY",
            coupon_type=CouponType.FIXED_AMOUNT,
            value=500,
            usage_limit=1,
            valid_until=_future(30),
        )
        store.create_coupon(coupon)

        # Redeem once — should exhaust the limit
        redemption = CouponRedemption(
            coupon_id=coupon.id,
            tenant_id="t1",
            code=coupon.code,
            discount_cents=500,
        )
        store.redeem_coupon(redemption)

        # Fetch without side effect
        updated = store.get_coupon(coupon.id)
        assert updated.usage_count == 1
        # Coupon should no longer be valid due to exhausted usage_limit
        assert updated.is_valid(amount_cents=1000) is False

    def test_list_coupons(self, store):
        store.create_coupon(Coupon(
            code="A", coupon_type=CouponType.PERCENTAGE, value=10,
            valid_until=_future(30),
        ))
        store.create_coupon(Coupon(
            code="B", coupon_type=CouponType.FIXED_AMOUNT, value=500,
            valid_until=_future(30),
        ))

        all_coupons = store.list_coupons()
        assert len(all_coupons) == 2

        # Filter by status
        active = store.list_coupons(status="active")
        assert len(active) == 2

        # Filter by non-matching status
        disabled = store.list_coupons(status="disabled")
        assert len(disabled) == 0

    def test_calculate_discount_percentage(self):
        """Coupon.calculate_discount for percentage type — pure model test."""
        coupon = Coupon(
            code="PCT20",
            coupon_type=CouponType.PERCENTAGE,
            value=20,
            max_discount_cents=500,
            valid_until=_future(30),
        )

        # 20% of 1000 cents = 200 cents
        discount = coupon.calculate_discount(amount_cents=1000)
        assert discount == 200

        # 20% of 3000 cents = 600, capped at max_discount_cents=500
        discount = coupon.calculate_discount(amount_cents=3000)
        assert discount == 500

        # Below min_amount_cents
        coupon_limited = Coupon(
            code="PCT_MIN",
            coupon_type=CouponType.PERCENTAGE,
            value=20,
            min_amount_cents=1000,
            valid_until=_future(30),
        )
        discount = coupon_limited.calculate_discount(amount_cents=500)
        assert discount == 0  # does not meet minimum

    def test_calculate_discount_fixed(self):
        """Coupon.calculate_discount for fixed amount type — pure model test."""
        coupon = Coupon(
            code="FLAT5",
            coupon_type=CouponType.FIXED_AMOUNT,
            value=500,
            valid_until=_future(30),
        )

        # Order amount larger than fixed discount
        discount = coupon.calculate_discount(amount_cents=2000)
        assert discount == 500

        # Order amount smaller than fixed discount — capped at order amount
        discount = coupon.calculate_discount(amount_cents=300)
        assert discount == 300

    def test_calculate_discount_expired_coupon(self):
        """Expired coupon returns zero discount."""
        coupon = Coupon(
            code="EXPIRED",
            coupon_type=CouponType.FIXED_AMOUNT,
            value=500,
            valid_until=_past(days=1),  # expired yesterday
        )
        discount = coupon.calculate_discount(amount_cents=2000)
        assert discount == 0

    def test_calculate_discount_disabled_coupon(self):
        """Disabled coupon returns zero discount."""
        coupon = Coupon(
            code="DISABLED",
            coupon_type=CouponType.PERCENTAGE,
            value=20,
            status=CouponStatus.DISABLED,
            valid_until=_future(30),
        )
        discount = coupon.calculate_discount(amount_cents=1000)
        assert discount == 0


# ═══════════════════════════════════════════════════════════════════════════
# Trial Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestTrial:
    def test_create_trial(self, store):
        trial = TrialRecord(
            tenant_id="t1",
            plan_tier="professional",
            trial_days=14,
            source="signup",
        )
        result = store.create_trial(trial)

        assert result.id == trial.id
        assert result.tenant_id == "t1"
        assert result.plan_tier == "professional"
        assert result.status == TrialStatus.ACTIVE
        assert result.trial_days == 14
        assert result.extended_count == 0
        assert result.source == "signup"
        assert result.ends_at > result.started_at

    def test_extend_trial(self, store):
        trial = TrialRecord(
            tenant_id="t1",
            plan_tier="personal",
            trial_days=7,
        )
        store.create_trial(trial)

        original_ends_at = trial.ends_at
        result = store.extend_trial("t1", days=5)

        assert result.status == TrialStatus.EXTENDED
        assert result.extended_count == 1
        # ends_at should have moved forward by 5 days
        expected_end = original_ends_at + timedelta(days=5)
        assert result.ends_at == expected_end

    def test_extend_trial_multiple_times(self, store):
        trial = TrialRecord(tenant_id="t1", plan_tier="personal", trial_days=7)
        store.create_trial(trial)
        original_ends = trial.ends_at

        store.extend_trial("t1", days=3)
        result = store.extend_trial("t1", days=4)

        assert result.extended_count == 2
        assert result.ends_at == original_ends + timedelta(days=7)

    def test_extend_trial_not_found(self, store):
        with pytest.raises(ValueError, match="Trial not found"):
            store.extend_trial("nonexistent", days=5)

    def test_convert_trial(self, store):
        trial = TrialRecord(
            tenant_id="t1",
            plan_tier="professional",
        )
        store.create_trial(trial)

        result = store.convert_trial("t1", plan_tier="team")

        assert result.status == TrialStatus.CONVERTED
        assert result.converted_to_plan == "team"
        assert result.converted_at is not None

    def test_get_trial_conversion_stats(self, store):
        # Create 4 trials, convert 2
        for i in range(4):
            t = TrialRecord(
                tenant_id=f"t{i}",
                plan_tier="professional",
            )
            store.create_trial(t)

        store.convert_trial("t0", plan_tier="professional")
        store.convert_trial("t1", plan_tier="team")

        stats = store.get_trial_conversion_stats()

        assert stats["total_trials"] == 4
        assert stats["converted_trials"] == 2
        assert stats["conversion_rate"] == 0.5
        assert stats["avg_days_to_convert"] >= 0

    def test_get_trial_conversion_stats_empty(self, store):
        stats = store.get_trial_conversion_stats()
        assert stats["total_trials"] == 0
        assert stats["converted_trials"] == 0
        assert stats["conversion_rate"] == 0.0

    def test_get_trial(self, store):
        trial = TrialRecord(tenant_id="t1", plan_tier="professional")
        store.create_trial(trial)

        fetched = store.get_trial("t1")
        assert fetched is not None
        assert fetched.id == trial.id
        assert fetched.plan_tier == "professional"

    def test_get_trial_not_found(self, store):
        result = store.get_trial("nonexistent")
        assert result is None

    def test_list_trials_filtered(self, store):
        store.create_trial(TrialRecord(tenant_id="t1", plan_tier="personal"))
        t2 = TrialRecord(tenant_id="t2", plan_tier="professional")
        store.create_trial(t2)
        store.convert_trial("t2", plan_tier="professional")

        active_trials = store.list_trials(status="active")
        converted_trials = store.list_trials(status="converted")

        assert len(active_trials) == 1
        assert active_trials[0].tenant_id == "t1"
        assert len(converted_trials) == 1
        assert converted_trials[0].tenant_id == "t2"
