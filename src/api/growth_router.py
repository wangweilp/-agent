"""
Growth router — invite / referral / coupon / trial endpoints.

Invite flow: user creates invite -> invitee accepts -> chain invite generated for invitee.
Referral flow: user creates referral code -> referred user signs up -> referral completed -> reward granted.
Coupon flow: admin creates coupon -> user redeems against invoice -> discount calculated.
Trial flow: tenant starts trial -> admin extends or user converts.
"""

import logging
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.adapters.growth_store import GrowthStoreAdapter
from src.core.growth import (
    Coupon,
    CouponRedemption,
    CouponStatus,
    CouponType,
    Invite,
    InviteStatus,
    Referral,
    ReferralStatus,
    TrialRecord,
    TrialStatus,
)
from src.api.middleware import require_auth, require_manage
from src.api.saas_schemas import (
    AcceptInviteRequest,
    CouponResponse,
    CreateCouponRequest,
    CreateInviteRequest,
    InviteResponse,
    RedeemCouponRequest,
    RedeemCouponResponse,
    ReferralResponse,
    ReferralStatsResponse,
    TrialConversionStatsResponse,
    TrialResponse,
)

logger = logging.getLogger(__name__)

# ── Helpers ────────────────────────────────────────────────────────────────────

_ALPHABET = string.ascii_uppercase + string.digits


def _generate_code(length: int = 8) -> str:
    """Generate a random alphanumeric code."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def _invite_to_response(invite: Invite) -> dict:
    return {
        "id": invite.id,
        "invite_code": invite.invite_code,
        "invitee_email": invite.invitee_email,
        "status": invite.status.value if hasattr(invite.status, "value") else str(invite.status),
        "expires_at": invite.expires_at.isoformat(),
        "created_at": invite.created_at.isoformat(),
    }


def _referral_to_response(ref: Referral) -> dict:
    return {
        "id": ref.id,
        "referral_code": ref.referral_code,
        "status": ref.status.value if hasattr(ref.status, "value") else str(ref.status),
        "reward_granted": ref.reward_granted,
        "reward_amount_cents": ref.reward_amount_cents,
        "created_at": ref.created_at.isoformat(),
    }


def _coupon_to_response(coupon: Coupon) -> dict:
    return {
        "id": coupon.id,
        "code": coupon.code,
        "coupon_type": coupon.coupon_type.value if hasattr(coupon.coupon_type, "value") else str(coupon.coupon_type),
        "value": coupon.value,
        "status": coupon.status.value if hasattr(coupon.status, "value") else str(coupon.status),
        "usage_count": coupon.usage_count,
        "usage_limit": coupon.usage_limit,
        "valid_until": coupon.valid_until.isoformat(),
    }


def _trial_to_response(trial: TrialRecord) -> dict:
    now = datetime.now(timezone.utc)
    remaining = max(0, (trial.ends_at - now).days)
    return {
        "id": trial.id,
        "tenant_id": trial.tenant_id,
        "plan_tier": trial.plan_tier,
        "status": trial.status.value if hasattr(trial.status, "value") else str(trial.status),
        "trial_days": trial.trial_days,
        "started_at": trial.started_at.isoformat(),
        "ends_at": trial.ends_at.isoformat(),
        "converted_at": trial.converted_at.isoformat() if trial.converted_at else None,
        "converted_to_plan": trial.converted_to_plan,
        "extended_count": trial.extended_count,
        "days_remaining": remaining,
    }


# ── Additional request schemas (not in saas_schemas) ───────────────────────────


class CompleteReferralRequest(BaseModel):
    referral_code: str = Field(..., min_length=1)
    referred_tenant_id: str = Field(..., min_length=1)
    referred_user_id: str = Field(..., min_length=1)
    reward_amount_cents: int = Field(default=2000, ge=0)


class ExtendTrialRequest(BaseModel):
    days: int = Field(..., gt=0, description="Number of days to extend")


class ConvertTrialRequest(BaseModel):
    plan_tier: str = Field(..., min_length=1, description="Target paid plan tier")


# ── Factory ────────────────────────────────────────────────────────────────────


def create_growth_router(
    growth_store,
    subscription_store=None,
    billing_store=None,
    tenant_store=None,
) -> APIRouter:
    """Create the growth router with all invite/referral/coupon/trial endpoints.

    Args:
        growth_store: GrowthStoreAdapter — handles invite/referral/coupon/trial persistence.
        subscription_store: Optional SubscriptionStoreAdapter — for trial-to-plan logic.
        billing_store: Optional BillingStoreAdapter — for referral reward credit.
        tenant_store: Optional TenantStoreAdapter — for auto-creating tenants on invite accept.
    """
    router = APIRouter(prefix="/growth", tags=["Growth"])

    # ═══════════════════════════════════════════════════════════════════════════
    # INVITES
    # ═══════════════════════════════════════════════════════════════════════════

    @router.post("/invites", status_code=201)
    async def create_invite(
        body: CreateInviteRequest,
        token=Depends(require_auth),
    ):
        """Create an invite and send it to the specified email.

        Returns the invite_code for sharing. The invitee receives an email
        (or the code can be shared directly).
        """
        code = _generate_code(8)
        invite = Invite(
            inviter_tenant_id=token.workspace_id,
            inviter_user_id=token.user_id,
            invitee_email=body.invitee_email,
            invite_code=code,
            workspace_id=body.workspace_id or token.workspace_id,
            status=InviteStatus.PENDING,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )

        try:
            created = growth_store.create_invite(invite)
        except Exception as e:
            logger.exception("Failed to create invite")
            raise HTTPException(status_code=500, detail=f"Failed to create invite: {e}")

        logger.info(
            "invite:created",
            extra={"invite_id": created.id, "inviter": token.user_id, "invitee": body.invitee_email},
        )
        return _invite_to_response(created)

    @router.get("/invites")
    async def list_invites(
        token=Depends(require_auth),
    ):
        """List all invites sent from the current tenant."""
        try:
            invites = growth_store.list_invites(tenant_id=token.workspace_id)
        except Exception as e:
            logger.exception("Failed to list invites")
            raise HTTPException(status_code=500, detail=f"Failed to list invites: {e}")
        return [_invite_to_response(i) for i in invites]

    @router.post("/invites/accept", status_code=200)
    async def accept_invite(
        body: AcceptInviteRequest,
        token=Depends(require_auth),
    ):
        """Accept an invite by its invite_code.

        Validates that the code is valid, pending, and not expired.
        On success: marks the invite as accepted, auto-creates a tenant for
        the invitee if needed, and generates a chain invite code so the new
        user can invite others.
        """
        # Look up the invite
        try:
            invite = growth_store.get_invite_by_code(body.invite_code)
        except Exception as e:
            logger.exception("Failed to look up invite by code")
            raise HTTPException(status_code=500, detail=f"Failed to look up invite: {e}")

        if invite is None:
            raise HTTPException(status_code=404, detail="Invite not found")

        if invite.status != InviteStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail=f"Invite is already {invite.status.value}",
            )

        if invite.expires_at < datetime.now(timezone.utc):
            # Mark as expired
            invite.status = InviteStatus.EXPIRED
            try:
                growth_store.create_invite(invite)  # update via re-creation or dedicated update
            except Exception:
                pass
            raise HTTPException(status_code=400, detail="Invite has expired")

        # Determine invitee's tenant — auto-create if needed
        invitee_tenant_id = token.workspace_id
        if tenant_store and (not invitee_tenant_id or invitee_tenant_id == "default"):
            # Auto-create a tenant for the invitee
            from src.core.tenant import Tenant, TenantStatus, OrganizationSize
            from uuid import uuid4

            tenant_name = f"Workspace-{token.user_id[:8]}"
            tenant_slug = f"ws-{uuid4().hex[:8]}"
            new_tenant = Tenant(
                id=f"tnt_{uuid4().hex[:12]}",
                name=tenant_name,
                email=token.email if hasattr(token, "email") else "",
                slug=tenant_slug,
                status=TenantStatus.TRIAL,
                owner_user_id=token.user_id,
                org_size=OrganizationSize.SOLO,
            )
            try:
                tenant_store.create_tenant(new_tenant)
                invitee_tenant_id = new_tenant.id
                logger.info("tenant:autocreated", extra={"tenant_id": invitee_tenant_id, "via": "invite"})
            except Exception as e:
                logger.exception("Failed to auto-create tenant for invitee")
                raise HTTPException(status_code=500, detail=f"Failed to create tenant: {e}")

        # Accept the invite
        try:
            accepted = growth_store.accept_invite(
                invite_id=invite.id,
                invitee_user_id=token.user_id,
                invitee_tenant_id=invitee_tenant_id,
            )
        except Exception as e:
            logger.exception("Failed to accept invite")
            raise HTTPException(status_code=500, detail=f"Failed to accept invite: {e}")

        # Generate chain invite — the new user becomes an inviter
        chain_code = _generate_code(8)
        chain_invite = Invite(
            inviter_tenant_id=invitee_tenant_id,
            inviter_user_id=token.user_id,
            invitee_email="",  # blank — the user will fill in when sending to a friend
            invite_code=chain_code,
            workspace_id=invitee_tenant_id,
            status=InviteStatus.PENDING,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        try:
            growth_store.create_invite(chain_invite)
            logger.info("chain_invite:created", extra={"inviter": token.user_id, "code": chain_code})
        except Exception as e:
            logger.exception("Failed to create chain invite")
            # Non-fatal: the original invite was already accepted
            pass

        response = _invite_to_response(accepted)
        response["chain_invite_code"] = chain_code
        return response

    @router.get("/invites/{invite_id}")
    async def get_invite(
        invite_id: str,
        token=Depends(require_auth),
    ):
        """Get details of a specific invite."""
        try:
            invite = growth_store.get_invite(invite_id)
        except Exception as e:
            logger.exception("Failed to get invite")
            raise HTTPException(status_code=500, detail=f"Failed to get invite: {e}")

        if invite is None:
            raise HTTPException(status_code=404, detail="Invite not found")
        return _invite_to_response(invite)

    # ═══════════════════════════════════════════════════════════════════════════
    # REFERRALS
    # ═══════════════════════════════════════════════════════════════════════════

    @router.post("/referrals", status_code=201)
    async def create_referral(
        token=Depends(require_auth),
    ):
        """Create a referral code for the current user.

        Returns a unique referral_code that the user can share. When a
        referred user signs up using this code, the referral is completed
        and a reward is granted.
        """
        code = _generate_code(8)
        referral = Referral(
            referrer_tenant_id=token.workspace_id,
            referrer_user_id=token.user_id,
            referral_code=code,
            status=ReferralStatus.PENDING,
            reward_amount_cents=2000,
        )

        try:
            created = growth_store.create_referral(referral)
        except Exception as e:
            logger.exception("Failed to create referral")
            raise HTTPException(status_code=500, detail=f"Failed to create referral: {e}")

        logger.info("referral:created", extra={"referral_id": created.id, "referrer": token.user_id})
        return _referral_to_response(created)

    @router.get("/referrals")
    async def list_referrals(
        token=Depends(require_auth),
    ):
        """List all referrals for the current tenant."""
        try:
            referrals = growth_store.list_referrals(tenant_id=token.workspace_id)
        except Exception as e:
            logger.exception("Failed to list referrals")
            raise HTTPException(status_code=500, detail=f"Failed to list referrals: {e}")
        return [_referral_to_response(r) for r in referrals]

    @router.get("/referrals/stats")
    async def get_referral_stats(
        token=Depends(require_auth),
    ):
        """Get referral statistics for the current tenant."""
        try:
            stats = growth_store.get_referral_stats(tenant_id=token.workspace_id)
        except Exception as e:
            logger.exception("Failed to get referral stats")
            raise HTTPException(status_code=500, detail=f"Failed to get referral stats: {e}")
        return stats

    @router.post("/referrals/complete", status_code=200)
    async def complete_referral(
        body: CompleteReferralRequest,
        token=Depends(require_auth),
    ):
        """Complete a referral when the referred user signs up.

        Marks the referral as completed, links it to the referred tenant/user,
        and grants a reward (credit) to the referrer's billing account.
        Default reward is 2000 cents (¥20).
        """
        # Look up the referral by code
        try:
            referral = growth_store.get_referral_by_code(body.referral_code)
        except Exception as e:
            logger.exception("Failed to look up referral by code")
            raise HTTPException(status_code=500, detail=f"Failed to look up referral: {e}")

        if referral is None:
            raise HTTPException(status_code=404, detail="Referral not found")

        if referral.status != ReferralStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail=f"Referral is already {referral.status.value}",
            )

        # Complete the referral
        try:
            completed = growth_store.complete_referral(
                referral_id=referral.id,
                referred_tenant_id=body.referred_tenant_id,
                referred_user_id=body.referred_user_id,
            )
        except Exception as e:
            logger.exception("Failed to complete referral")
            raise HTTPException(status_code=500, detail=f"Failed to complete referral: {e}")

        # Grant reward to referrer's billing account
        reward = completed.reward_amount_cents or body.reward_amount_cents
        if reward > 0 and billing_store:
            try:
                # Grant credit to the referrer
                billing_store.grant_credit(
                    tenant_id=completed.referrer_tenant_id,
                    amount_cents=reward,
                    description=f"Referral reward — {completed.referral_code}",
                )
                # Mark reward as granted
                completed.reward_granted = True
                logger.info(
                    "referral:rewarded",
                    extra={
                        "referral_id": completed.id,
                        "referrer_tenant": completed.referrer_tenant_id,
                        "amount_cents": reward,
                    },
                )
            except AttributeError:
                # billing_store doesn't support grant_credit — log and continue
                logger.warning(
                    "billing_store does not support grant_credit; reward not applied",
                    extra={"referral_id": completed.id, "amount_cents": reward},
                )
            except Exception as e:
                logger.exception("Failed to grant referral reward")
                # Non-fatal: referral is already completed

        # Also grant reward to the referred user (both parties benefit)
        if reward > 0 and billing_store and body.referred_tenant_id:
            try:
                billing_store.grant_credit(
                    tenant_id=body.referred_tenant_id,
                    amount_cents=reward,
                    description=f"Sign-up reward via referral {completed.referral_code}",
                )
            except (AttributeError, Exception):
                pass  # Best-effort

        return _referral_to_response(completed)

    # ═══════════════════════════════════════════════════════════════════════════
    # COUPONS
    # ═══════════════════════════════════════════════════════════════════════════

    @router.post("/coupons", status_code=201)
    async def create_coupon(
        body: CreateCouponRequest,
        token=Depends(require_manage),
    ):
        """Create a new coupon (admin only).

        Coupon types:
          - percentage: percentage discount (value 1-100)
          - fixed_amount: fixed discount in cents
          - trial_extension: extend trial by N days
        """
        # Validate percentage range
        if body.coupon_type == "percentage" and (body.value < 1 or body.value > 100):
            raise HTTPException(status_code=400, detail="Percentage value must be between 1 and 100")

        # Check for duplicate code
        try:
            existing = growth_store.get_coupon_by_code(body.code)
        except Exception as e:
            logger.exception("Failed to check coupon code uniqueness")
            raise HTTPException(status_code=500, detail=f"Failed to validate coupon code: {e}")

        if existing is not None:
            raise HTTPException(status_code=409, detail=f"Coupon code '{body.code}' already exists")

        coupon_type = CouponType(body.coupon_type)
        coupon = Coupon(
            code=body.code,
            coupon_type=coupon_type,
            value=body.value,
            min_amount_cents=body.min_amount_cents,
            max_discount_cents=body.max_discount_cents,
            applicable_plans=body.applicable_plans,
            usage_limit=body.usage_limit,
            status=CouponStatus.ACTIVE,
            valid_from=datetime.now(timezone.utc),
            valid_until=datetime.now(timezone.utc) + timedelta(days=body.valid_days),
            created_by=token.user_id,
        )

        try:
            created = growth_store.create_coupon(coupon)
        except Exception as e:
            logger.exception("Failed to create coupon")
            raise HTTPException(status_code=500, detail=f"Failed to create coupon: {e}")

        logger.info("coupon:created", extra={"coupon_id": created.id, "code": created.code, "by": token.user_id})
        return _coupon_to_response(created)

    @router.get("/coupons")
    async def list_coupons(
        token=Depends(require_auth),
    ):
        """List all currently active coupons."""
        try:
            coupons = growth_store.list_coupons(status=CouponStatus.ACTIVE.value)
        except Exception as e:
            logger.exception("Failed to list coupons")
            raise HTTPException(status_code=500, detail=f"Failed to list coupons: {e}")
        return [_coupon_to_response(c) for c in coupons]

    @router.get("/coupons/admin/list")
    async def admin_list_coupons(
        status: Optional[str] = Query(None, description="Filter by status (active|used|expired|disabled)"),
        token=Depends(require_manage),
    ):
        """Admin: list all coupons, optionally filtered by status."""
        try:
            coupons = growth_store.list_coupons(status=status)
        except Exception as e:
            logger.exception("Failed to list coupons (admin)")
            raise HTTPException(status_code=500, detail=f"Failed to list coupons: {e}")
        return [_coupon_to_response(c) for c in coupons]

    @router.get("/coupons/{code}")
    async def validate_coupon(
        code: str,
        token=Depends(require_auth),
    ):
        """Validate and look up a coupon by its code.

        Returns the coupon details if it is valid (active, not expired,
        not over usage limit). Returns 404 if not found or invalid.
        """
        try:
            coupon = growth_store.get_coupon_by_code(code)
        except Exception as e:
            logger.exception("Failed to look up coupon by code")
            raise HTTPException(status_code=500, detail=f"Failed to look up coupon: {e}")

        if coupon is None:
            raise HTTPException(status_code=404, detail="Coupon not found")

        if not coupon.is_valid():
            raise HTTPException(
                status_code=400,
                detail="Coupon is not valid (expired, used up, or disabled)",
            )

        # Include discount info in response
        response = _coupon_to_response(coupon)
        response["valid"] = True
        return response

    @router.post("/coupons/redeem", status_code=200)
    async def redeem_coupon(
        body: RedeemCouponRequest,
        token=Depends(require_auth),
    ):
        """Redeem a coupon against an invoice.

        Validates the coupon, calculates the discount using
        Coupon.calculate_discount(), records the redemption,
        and increments the coupon usage count.
        """
        # Look up and validate coupon
        try:
            coupon = growth_store.get_coupon_by_code(body.code)
        except Exception as e:
            logger.exception("Failed to look up coupon for redemption")
            raise HTTPException(status_code=500, detail=f"Failed to look up coupon: {e}")

        if coupon is None:
            raise HTTPException(status_code=404, detail="Coupon not found")

        if not coupon.is_valid():
            raise HTTPException(
                status_code=400,
                detail="Coupon is not valid (expired, used up, or disabled)",
            )

        # Determine invoice amount if invoice_id is provided
        invoice_amount = 0
        if body.invoice_id and billing_store:
            try:
                invoice = billing_store.get_invoice(body.invoice_id)
                if invoice:
                    invoice_amount = invoice.amount if hasattr(invoice, "amount") else 0
            except Exception:
                pass  # Invoice lookup is best-effort; proceed with discount=0 if unavailable

        # Calculate discount
        discount = coupon.calculate_discount(invoice_amount)
        if discount == 0 and coupon.coupon_type not in (CouponType.TRIAL_EXTENSION,):
            raise HTTPException(
                status_code=400,
                detail="Coupon discount is zero — check minimum amount or applicable plans",
            )

        # Record redemption
        redemption = CouponRedemption(
            coupon_id=coupon.id,
            tenant_id=token.workspace_id,
            code=coupon.code,
            discount_cents=discount,
            invoice_id=body.invoice_id,
        )

        try:
            saved = growth_store.redeem_coupon(redemption)
        except Exception as e:
            logger.exception("Failed to redeem coupon")
            raise HTTPException(status_code=500, detail=f"Failed to redeem coupon: {e}")

        # Increment usage count on the coupon
        coupon.usage_count += 1
        if coupon.usage_limit > 0 and coupon.usage_count >= coupon.usage_limit:
            coupon.status = CouponStatus.USED
        try:
            growth_store.update_coupon(coupon)
        except Exception as e:
            logger.exception("Failed to update coupon usage count")

        logger.info(
            "coupon:redeemed",
            extra={
                "redemption_id": saved.id,
                "code": coupon.code,
                "tenant": token.workspace_id,
                "discount_cents": discount,
            },
        )

        return {
            "id": saved.id,
            "code": saved.code,
            "discount_cents": saved.discount_cents,
            "redeemed_at": saved.redeemed_at.isoformat(),
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # TRIALS
    # ═══════════════════════════════════════════════════════════════════════════

    @router.get("/trial")
    async def get_trial_status(
        token=Depends(require_auth),
    ):
        """Get the current tenant's trial status, including days remaining."""
        try:
            trial = growth_store.get_trial(tenant_id=token.workspace_id)
        except Exception as e:
            logger.exception("Failed to get trial")
            raise HTTPException(status_code=500, detail=f"Failed to get trial: {e}")

        if trial is None:
            raise HTTPException(status_code=404, detail="No trial found for this tenant")

        return _trial_to_response(trial)

    @router.post("/trial/extend", status_code=200)
    async def extend_trial(
        body: ExtendTrialRequest,
        token=Depends(require_manage),
    ):
        """Admin: extend a trial by N days."""
        try:
            trial = growth_store.get_trial(tenant_id=token.workspace_id)
        except Exception as e:
            logger.exception("Failed to get trial for extension")
            raise HTTPException(status_code=500, detail=f"Failed to get trial: {e}")

        if trial is None:
            raise HTTPException(status_code=404, detail="No trial found for this tenant")

        if trial.status not in (TrialStatus.ACTIVE, TrialStatus.EXTENDED):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot extend trial with status '{trial.status.value}'",
            )

        try:
            extended = growth_store.extend_trial(
                tenant_id=token.workspace_id,
                days=body.days,
            )
        except Exception as e:
            logger.exception("Failed to extend trial")
            raise HTTPException(status_code=500, detail=f"Failed to extend trial: {e}")

        logger.info(
            "trial:extended",
            extra={"tenant": token.workspace_id, "days": body.days, "new_end": extended.ends_at.isoformat()},
        )
        return _trial_to_response(extended)

    @router.post("/trial/convert", status_code=200)
    async def convert_trial(
        body: ConvertTrialRequest,
        token=Depends(require_auth),
    ):
        """Mark the current trial as converted to a paid plan."""
        try:
            trial = growth_store.get_trial(tenant_id=token.workspace_id)
        except Exception as e:
            logger.exception("Failed to get trial for conversion")
            raise HTTPException(status_code=500, detail=f"Failed to get trial: {e}")

        if trial is None:
            raise HTTPException(status_code=404, detail="No trial found for this tenant")

        if trial.status != TrialStatus.ACTIVE and trial.status != TrialStatus.EXTENDED:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot convert trial with status '{trial.status.value}'",
            )

        # If subscription_store is available, create/update the subscription
        if subscription_store:
            try:
                subscription_store.change_plan(
                    tenant_id=token.workspace_id,
                    target_tier=body.plan_tier,
                    billing_cycle="monthly",
                )
            except Exception as e:
                logger.exception("Failed to update subscription during trial conversion")
                # Non-fatal

        try:
            converted = growth_store.convert_trial(
                tenant_id=token.workspace_id,
                plan_tier=body.plan_tier,
            )
        except Exception as e:
            logger.exception("Failed to convert trial")
            raise HTTPException(status_code=500, detail=f"Failed to convert trial: {e}")

        logger.info(
            "trial:converted",
            extra={"tenant": token.workspace_id, "plan": body.plan_tier},
        )
        return _trial_to_response(converted)

    @router.get("/trial/admin/stats")
    async def get_trial_stats(
        token=Depends(require_manage),
    ):
        """Admin: get trial conversion statistics across all tenants."""
        try:
            stats = growth_store.get_trial_conversion_stats()
        except Exception as e:
            logger.exception("Failed to get trial stats")
            raise HTTPException(status_code=500, detail=f"Failed to get trial stats: {e}")
        return stats

    @router.get("/trial/admin/list")
    async def admin_list_trials(
        status: Optional[str] = Query(None, description="Filter by status (active|converted|expired|extended)"),
        token=Depends(require_manage),
    ):
        """Admin: list all trials, optionally filtered by status."""
        try:
            trials = growth_store.list_trials(status=status)
        except Exception as e:
            logger.exception("Failed to list trials (admin)")
            raise HTTPException(status_code=500, detail=f"Failed to list trials: {e}")
        return [_trial_to_response(t) for t in trials]

    return router
