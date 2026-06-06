"""Tenant API Router — Multi-tenant management with tenant isolation.

Endpoints:
    POST   /tenants                         — create tenant + billing + subscription + trial
    GET    /tenants/current                 — get current tenant info
    PATCH  /tenants/current                 — update current tenant
    DELETE /tenants/current                 — close/deactivate current tenant
    GET    /tenants/current/members         — list members
    POST   /tenants/current/members         — add member
    DELETE /tenants/current/members/{user_id} — remove member
    GET    /tenants/current/organizations   — list organizations
    POST   /tenants/current/organizations   — create organization
    PATCH  /tenants/current/organizations/{org_id} — update organization
    DELETE /tenants/current/organizations/{org_id} — delete organization
    GET    /tenants/admin/list              — admin: list all tenants
    GET    /tenants/admin/{tenant_id}       — admin: get specific tenant

Multi-tenant isolation:
- All "current" endpoints read tenant_id from JWT payload.workspace_id.
- Admin endpoints require manage role.
- Member/organization endpoints always filter by current tenant_id.
- Cross-tenant access is blocked at every boundary.
"""
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from src.adapters.auth_store import SQLiteAuthStore
from src.adapters.tenant_store import TenantStoreAdapter
from src.api.middleware import require_auth, require_manage
from src.api.saas_schemas import (
    AddTenantMemberRequest,
    CreateOrgRequest,
    CreateTenantRequest,
    UpdateTenantRequest,
)
from src.core.auth import TokenPayload
from src.core.billing import BillingAccount, Currency
from src.core.growth import TrialRecord, TrialStatus
from src.core.subscription import (
    BillingCycle,
    PlanTier,
    Subscription,
    SubscriptionStatus,
)
from src.core.tenant import (
    Organization,
    OrganizationSize,
    Tenant,
    TenantMember,
    TenantStatus,
)

logger = logging.getLogger(__name__)

# ── Helpers ──


def _slugify(name: str) -> str:
    """Generate a URL-friendly slug from a tenant name.

    Keeps alphanumerics, CJK characters, and replaces everything else
    with hyphens. Falls back to 'tenant' if the result is empty.
    """
    slug = name.lower().strip()
    slug = re.sub(r'[^\w一-鿿]+', '-', slug)
    slug = slug.strip('-')
    return slug or "tenant"


def _make_unique_slug(tenant_store: TenantStoreAdapter, base_slug: str) -> str:
    """Ensure slug uniqueness by appending a numeric suffix if needed."""
    slug = base_slug
    suffix = 1
    while tenant_store.get_tenant_by_slug(slug):
        suffix += 1
        slug = f"{base_slug}-{suffix}"
    return slug


# ── Router Factory ──


def create_tenant_router(
    tenant_store: TenantStoreAdapter,
    billing_store,
    subscription_store,
    trial_store=None,
    auth_store: SQLiteAuthStore | None = None,
) -> APIRouter:
    """Create a FastAPI router for multi-tenant management.

    Args:
        tenant_store: TenantStoreAdapter instance.
        billing_store: BillingStoreAdapter-compatible instance.
        subscription_store: SubscriptionStoreAdapter-compatible instance.
        trial_store: Optional GrowthStore-compatible instance for trial tracking.
        auth_store: Optional SQLiteAuthStore for user validation in member ops.

    Returns:
        APIRouter with all tenant endpoints registered.
    """
    router = APIRouter(tags=["tenants"])

    # ── Internal helpers ──

    def _tenant_id_from(payload: TokenPayload) -> str:
        """Extract tenant_id from the JWT payload (workspace_id field)."""
        return payload.workspace_id

    def _require_active(tenant: Tenant | None, tenant_id: str) -> Tenant:
        """404 if missing, 403 if closed/suspended."""
        if tenant is None:
            raise HTTPException(404, f"租户不存在: {tenant_id}")
        if not tenant.is_active:
            raise HTTPException(403, "租户已关闭或暂停")
        return tenant

    # ═══════════════════════════════════════════════════════════════
    # Tenant CRUD (current)
    # ═══════════════════════════════════════════════════════════════

    @router.post("/tenants")
    async def create_tenant(
        body: CreateTenantRequest,
        payload: TokenPayload = Depends(require_auth),
    ):
        """Create a new tenant.

        Side effects (transactional best-effort):
          1. Create Tenant row.
          2. Create BillingAccount.
          3. Create Subscription (14-day free trial on Professional plan).
          4. Create TrialRecord (when trial_store is provided).
        """
        # ── Validate org_size ──
        try:
            org_size = OrganizationSize(body.org_size)
        except ValueError:
            raise HTTPException(400, f"无效的组织规模: {body.org_size}")

        # ── Slug generation & uniqueness ──
        base_slug = body.slug or _slugify(body.name)
        slug = _make_unique_slug(tenant_store, base_slug)

        # ── 1. Create Tenant ──
        tenant = Tenant(
            name=body.name,
            email=body.email,
            slug=slug,
            status=TenantStatus.TRIAL,
            owner_user_id=payload.user_id,
            org_size=org_size,
            industry=body.industry,
            website=body.website,
        )
        tenant = tenant_store.create_tenant(tenant)
        logger.info("tenant:created", extra={"tenant_id": tenant.id, "slug": slug})

        # ── 2. Create BillingAccount ──
        billing_account = BillingAccount(
            tenant_id=tenant.id,
            billing_email=body.email,
        )
        billing_store.create_account(billing_account)

        # ── 3. Create Subscription (14-day free trial) ──
        now = datetime.now(timezone.utc)
        trial_end = now + timedelta(days=14)
        subscription = Subscription(
            tenant_id=tenant.id,
            plan_tier=PlanTier.PROFESSIONAL,
            status=SubscriptionStatus.TRIAL,
            billing_cycle=BillingCycle.MONTHLY,
            current_period_start=now,
            current_period_end=trial_end,
            trial_start=now,
            trial_end=trial_end,
        )
        subscription_store.create_subscription(subscription)

        # ── 4. Create TrialRecord (optional) ──
        trial_record = None
        if trial_store:
            trial_record = TrialRecord(
                tenant_id=tenant.id,
                plan_tier="professional",
                trial_days=14,
                status=TrialStatus.ACTIVE,
                started_at=now,
                ends_at=trial_end,
                source="signup",
            )
            trial_store.create_trial(trial_record)

        return {
            "tenant": {
                "id": tenant.id,
                "name": tenant.name,
                "email": tenant.email,
                "slug": tenant.slug,
                "status": tenant.status.value,
                "owner_user_id": tenant.owner_user_id,
                "org_size": tenant.org_size.value,
                "industry": tenant.industry,
                "website": tenant.website,
                "created_at": tenant.created_at.isoformat(),
            },
            "billing_account": {
                "id": billing_account.id,
                "tenant_id": billing_account.tenant_id,
                "currency": billing_account.currency.value,
                "balance": billing_account.balance,
                "billing_email": billing_account.billing_email,
                "created_at": billing_account.created_at.isoformat(),
            },
            "subscription": {
                "id": subscription.id,
                "tenant_id": subscription.tenant_id,
                "plan_tier": subscription.plan_tier.value,
                "status": subscription.status.value,
                "billing_cycle": subscription.billing_cycle.value,
                "current_period_start": subscription.current_period_start.isoformat(),
                "current_period_end": (
                    subscription.current_period_end.isoformat()
                    if subscription.current_period_end
                    else None
                ),
                "trial_start": (
                    subscription.trial_start.isoformat()
                    if subscription.trial_start
                    else None
                ),
                "trial_end": (
                    subscription.trial_end.isoformat()
                    if subscription.trial_end
                    else None
                ),
                "days_remaining": subscription.days_remaining(),
                "created_at": subscription.created_at.isoformat(),
            },
            "trial": (
                {
                    "id": trial_record.id,
                    "tenant_id": trial_record.tenant_id,
                    "plan_tier": trial_record.plan_tier,
                    "status": trial_record.status.value,
                    "trial_days": trial_record.trial_days,
                    "started_at": trial_record.started_at.isoformat(),
                    "ends_at": trial_record.ends_at.isoformat(),
                }
                if trial_record
                else None
            ),
        }

    @router.get("/tenants/current")
    async def get_current_tenant(payload: TokenPayload = Depends(require_auth)):
        """Return the current tenant with member count and subscription info.

        tenant_id is read from JWT payload.workspace_id — cross-tenant
        access is impossible by construction.
        """
        tenant_id = _tenant_id_from(payload)
        tenant = _require_active(tenant_store.get_tenant(tenant_id), tenant_id)

        members = tenant_store.list_members(tenant_id)
        subscription = subscription_store.get_subscription(tenant_id)
        billing_account = billing_store.get_account(tenant_id)

        return {
            "id": tenant.id,
            "name": tenant.name,
            "email": tenant.email,
            "slug": tenant.slug,
            "status": tenant.status.value,
            "owner_user_id": tenant.owner_user_id,
            "org_size": tenant.org_size.value,
            "industry": tenant.industry,
            "website": tenant.website,
            "logo_url": tenant.logo_url,
            "timezone": tenant.timezone,
            "locale": tenant.locale,
            "metadata": tenant.metadata,
            "members_count": len(members),
            "created_at": tenant.created_at.isoformat(),
            "updated_at": tenant.updated_at.isoformat(),
            "subscription": (
                {
                    "id": subscription.id,
                    "tenant_id": subscription.tenant_id,
                    "plan_tier": subscription.plan_tier.value,
                    "status": subscription.status.value,
                    "billing_cycle": subscription.billing_cycle.value,
                    "current_period_start": subscription.current_period_start.isoformat(),
                    "current_period_end": (
                        subscription.current_period_end.isoformat()
                        if subscription.current_period_end
                        else None
                    ),
                    "trial_start": (
                        subscription.trial_start.isoformat()
                        if subscription.trial_start
                        else None
                    ),
                    "trial_end": (
                        subscription.trial_end.isoformat()
                        if subscription.trial_end
                        else None
                    ),
                    "canceled_at": (
                        subscription.canceled_at.isoformat()
                        if subscription.canceled_at
                        else None
                    ),
                    "auto_renew": subscription.auto_renew,
                    "coupon_code": subscription.coupon_code,
                    "days_remaining": subscription.days_remaining(),
                    "created_at": subscription.created_at.isoformat(),
                }
                if subscription
                else None
            ),
            "billing_account": (
                {
                    "id": billing_account.id,
                    "tenant_id": billing_account.tenant_id,
                    "currency": billing_account.currency.value,
                    "balance": billing_account.balance,
                    "billing_email": billing_account.billing_email,
                    "created_at": billing_account.created_at.isoformat(),
                }
                if billing_account
                else None
            ),
        }

    @router.patch("/tenants/current")
    async def update_current_tenant(
        body: UpdateTenantRequest,
        payload: TokenPayload = Depends(require_auth),
    ):
        """Update the current tenant's profile fields.

        Only non-None fields in the request body are applied.
        """
        tenant_id = _tenant_id_from(payload)
        tenant = _require_active(tenant_store.get_tenant(tenant_id), tenant_id)

        if body.name is not None:
            tenant.name = body.name
        if body.email is not None:
            tenant.email = body.email
        if body.industry is not None:
            tenant.industry = body.industry
        if body.website is not None:
            tenant.website = body.website
        if body.logo_url is not None:
            tenant.logo_url = body.logo_url
        if body.timezone is not None:
            tenant.timezone = body.timezone
        if body.locale is not None:
            tenant.locale = body.locale

        tenant_store.update_tenant(tenant)
        return {
            "id": tenant.id,
            "name": tenant.name,
            "updated_at": tenant.updated_at.isoformat(),
        }

    @router.delete("/tenants/current")
    async def close_current_tenant(payload: TokenPayload = Depends(require_manage)):
        """Close (soft-delete) the current tenant.

        Sets status=closed and cancels the associated subscription.
        Requires manage (admin+) role.
        """
        tenant_id = _tenant_id_from(payload)
        tenant = tenant_store.get_tenant(tenant_id)
        if tenant is None:
            raise HTTPException(404, f"租户不存在: {tenant_id}")
        if tenant.status == TenantStatus.CLOSED:
            raise HTTPException(400, "租户已关闭")

        tenant_store.delete_tenant(tenant_id)

        # Best-effort subscription cancellation
        try:
            subscription_store.cancel_subscription(tenant_id)
        except Exception:
            logger.warning(
                "tenant:close_sub_cancel_failed",
                extra={"tenant_id": tenant_id},
                exc_info=True,
            )

        logger.info("tenant:closed", extra={"tenant_id": tenant_id})
        return {"id": tenant_id, "status": TenantStatus.CLOSED.value}

    # ═══════════════════════════════════════════════════════════════
    # Member Management
    # ═══════════════════════════════════════════════════════════════

    @router.get("/tenants/current/members")
    async def list_members(payload: TokenPayload = Depends(require_auth)):
        """List all members of the current tenant."""
        tenant_id = _tenant_id_from(payload)
        members = tenant_store.list_members(tenant_id)
        result = []
        for m in members:
            user_name = ""
            user_email = ""
            if auth_store:
                user = auth_store.get_user_by_id(m.user_id)
                if user:
                    user_name = user.name
                    user_email = user.email
            result.append({
                "id": m.id,
                "tenant_id": m.tenant_id,
                "user_id": m.user_id,
                "user_name": user_name,
                "user_email": user_email,
                "role": m.role,
                "org_id": m.org_id,
                "joined_at": m.joined_at.isoformat(),
                "invited_by": m.invited_by,
            })
        return result

    @router.post("/tenants/current/members")
    async def add_member(
        body: AddTenantMemberRequest,
        payload: TokenPayload = Depends(require_manage),
    ):
        """Add a member to the current tenant.

        Validates that the user exists and is not already a member.
        Requires manage (admin+) role.
        """
        tenant_id = _tenant_id_from(payload)

        # Validate user exists
        if auth_store:
            user = auth_store.get_user_by_id(body.user_id)
            if user is None:
                raise HTTPException(404, f"用户不存在: {body.user_id}")

        # Guard: not already a member
        existing = tenant_store.get_member(tenant_id, body.user_id)
        if existing:
            raise HTTPException(409, "该用户已经是租户成员")

        member = TenantMember(
            tenant_id=tenant_id,
            user_id=body.user_id,
            role=body.role,
            invited_by=payload.user_id,
        )
        member = tenant_store.add_member(member)
        logger.info(
            "tenant:member_added",
            extra={"tenant_id": tenant_id, "user_id": body.user_id, "role": body.role},
        )
        return {
            "id": member.id,
            "tenant_id": member.tenant_id,
            "user_id": member.user_id,
            "role": member.role,
            "org_id": member.org_id,
            "joined_at": member.joined_at.isoformat(),
        }

    @router.delete("/tenants/current/members/{user_id}")
    async def remove_member(
        user_id: str,
        payload: TokenPayload = Depends(require_manage),
    ):
        """Remove a member from the current tenant.

        Guards:
        - Cannot remove yourself.
        - Cannot remove the last owner (tenant would be orphaned).
        Requires manage (admin+) role.
        """
        tenant_id = _tenant_id_from(payload)

        if user_id == payload.user_id:
            raise HTTPException(400, "不能移除自己")

        target = tenant_store.get_member(tenant_id, user_id)
        if target is None:
            raise HTTPException(404, "该用户不是租户成员")

        # Prevent orphaning: refuse to remove the last owner
        if target.role == "owner":
            members = tenant_store.list_members(tenant_id)
            owner_count = sum(1 for m in members if m.role == "owner")
            if owner_count <= 1:
                raise HTTPException(400, "不能移除唯一的 owner")

        tenant_store.remove_member(tenant_id, user_id)
        logger.info(
            "tenant:member_removed",
            extra={"tenant_id": tenant_id, "user_id": user_id},
        )
        return {"status": "removed"}

    # ═══════════════════════════════════════════════════════════════
    # Organization Management
    # ═══════════════════════════════════════════════════════════════

    @router.get("/tenants/current/organizations")
    async def list_organizations(payload: TokenPayload = Depends(require_auth)):
        """List all organizations in the current tenant."""
        tenant_id = _tenant_id_from(payload)
        orgs = tenant_store.list_organizations(tenant_id)
        return [
            {
                "id": o.id,
                "tenant_id": o.tenant_id,
                "name": o.name,
                "parent_org_id": o.parent_org_id,
                "description": o.description,
                "metadata": o.metadata,
                "created_at": o.created_at.isoformat(),
                "updated_at": o.updated_at.isoformat(),
            }
            for o in orgs
        ]

    @router.post("/tenants/current/organizations")
    async def create_organization(
        body: CreateOrgRequest,
        payload: TokenPayload = Depends(require_manage),
    ):
        """Create a new organization scoped to the current tenant.

        Supports parent_org_id for hierarchy. The parent must belong
        to the same tenant (cross-tenant nesting is rejected).
        """
        tenant_id = _tenant_id_from(payload)

        # Validate parent belongs to the same tenant
        if body.parent_org_id:
            parent = tenant_store.get_organization(body.parent_org_id)
            if parent is None:
                raise HTTPException(404, f"上级组织不存在: {body.parent_org_id}")
            if parent.tenant_id != tenant_id:
                raise HTTPException(403, "上级组织不属于当前租户")

        org = Organization(
            tenant_id=tenant_id,
            name=body.name,
            parent_org_id=body.parent_org_id,
            description=body.description,
        )
        org = tenant_store.create_organization(org)
        logger.info(
            "tenant:org_created",
            extra={"tenant_id": tenant_id, "org_id": org.id, "org_name": org.name},
        )
        return {
            "id": org.id,
            "tenant_id": org.tenant_id,
            "name": org.name,
            "parent_org_id": org.parent_org_id,
            "description": org.description,
            "created_at": org.created_at.isoformat(),
        }

    @router.patch("/tenants/current/organizations/{org_id}")
    async def update_organization(
        org_id: str,
        body: CreateOrgRequest,
        payload: TokenPayload = Depends(require_manage),
    ):
        """Update an organization. The org must belong to the current tenant.

        All fields are replaced with the request body values (full update
        via PATCH semantics for simplicity).
        """
        tenant_id = _tenant_id_from(payload)
        org = tenant_store.get_organization(org_id)
        if org is None:
            raise HTTPException(404, f"组织不存在: {org_id}")
        if org.tenant_id != tenant_id:
            raise HTTPException(403, "不能修改其他租户的组织")

        # Validate new parent if changed
        if body.parent_org_id:
            if body.parent_org_id == org_id:
                raise HTTPException(400, "上级组织不能是自己")
            parent = tenant_store.get_organization(body.parent_org_id)
            if parent is None:
                raise HTTPException(404, f"上级组织不存在: {body.parent_org_id}")
            if parent.tenant_id != tenant_id:
                raise HTTPException(403, "上级组织不属于当前租户")

        org.name = body.name
        org.parent_org_id = body.parent_org_id
        org.description = body.description

        tenant_store.update_organization(org)
        return {
            "id": org.id,
            "tenant_id": org.tenant_id,
            "name": org.name,
            "parent_org_id": org.parent_org_id,
            "description": org.description,
            "updated_at": org.updated_at.isoformat(),
        }

    @router.delete("/tenants/current/organizations/{org_id}")
    async def delete_organization(
        org_id: str,
        payload: TokenPayload = Depends(require_manage),
    ):
        """Delete an organization. The org must belong to the current tenant.

        Cross-tenant deletion is rejected.
        """
        tenant_id = _tenant_id_from(payload)
        org = tenant_store.get_organization(org_id)
        if org is None:
            raise HTTPException(404, f"组织不存在: {org_id}")
        if org.tenant_id != tenant_id:
            raise HTTPException(403, "不能删除其他租户的组织")

        tenant_store.delete_organization(org_id)
        logger.info(
            "tenant:org_deleted",
            extra={"tenant_id": tenant_id, "org_id": org_id},
        )
        return {"status": "deleted"}

    # ═══════════════════════════════════════════════════════════════
    # Admin Endpoints
    # ═══════════════════════════════════════════════════════════════

    @router.get("/tenants/admin/list")
    async def admin_list_tenants(
        status: str = Query(default=None, description="Filter by tenant status"),
        payload: TokenPayload = Depends(require_manage),
    ):
        """Admin: list all tenants with optional ?status= filter.

        Requires manage (admin+) role. The caller's own tenant_id from
        JWT does NOT constrain the result — this is an admin endpoint.
        """
        tenants = tenant_store.list_tenants(status=status if status else None)
        return [
            {
                "id": t.id,
                "name": t.name,
                "email": t.email,
                "slug": t.slug,
                "status": t.status.value,
                "owner_user_id": t.owner_user_id,
                "org_size": t.org_size.value,
                "industry": t.industry,
                "website": t.website,
                "members_count": len(tenant_store.list_members(t.id)),
                "created_at": t.created_at.isoformat(),
                "updated_at": t.updated_at.isoformat(),
            }
            for t in tenants
        ]

    @router.get("/tenants/admin/{tenant_id}")
    async def admin_get_tenant(
        tenant_id: str,
        payload: TokenPayload = Depends(require_manage),
    ):
        """Admin: get a specific tenant with full details.

        Cross-tenant access is intentionally allowed here because the
        caller has already passed the require_manage gate. This is
        the admin backdoor — use with audit logging.
        Requires manage (admin+) role.
        """
        tenant = tenant_store.get_tenant(tenant_id)
        if tenant is None:
            raise HTTPException(404, f"租户不存在: {tenant_id}")

        members = tenant_store.list_members(tenant_id)
        subscription = subscription_store.get_subscription(tenant_id)
        billing_account = billing_store.get_account(tenant_id)
        organizations = tenant_store.list_organizations(tenant_id)

        return {
            "id": tenant.id,
            "name": tenant.name,
            "email": tenant.email,
            "slug": tenant.slug,
            "status": tenant.status.value,
            "owner_user_id": tenant.owner_user_id,
            "org_size": tenant.org_size.value,
            "industry": tenant.industry,
            "website": tenant.website,
            "logo_url": tenant.logo_url,
            "timezone": tenant.timezone,
            "locale": tenant.locale,
            "metadata": tenant.metadata,
            "members_count": len(members),
            "organizations_count": len(organizations),
            "created_at": tenant.created_at.isoformat(),
            "updated_at": tenant.updated_at.isoformat(),
            "subscription": (
                {
                    "id": subscription.id,
                    "tenant_id": subscription.tenant_id,
                    "plan_tier": subscription.plan_tier.value,
                    "status": subscription.status.value,
                    "billing_cycle": subscription.billing_cycle.value,
                    "current_period_start": subscription.current_period_start.isoformat(),
                    "current_period_end": (
                        subscription.current_period_end.isoformat()
                        if subscription.current_period_end
                        else None
                    ),
                    "trial_start": (
                        subscription.trial_start.isoformat()
                        if subscription.trial_start
                        else None
                    ),
                    "trial_end": (
                        subscription.trial_end.isoformat()
                        if subscription.trial_end
                        else None
                    ),
                    "days_remaining": subscription.days_remaining(),
                    "auto_renew": subscription.auto_renew,
                    "created_at": subscription.created_at.isoformat(),
                }
                if subscription
                else None
            ),
            "billing_account": (
                {
                    "id": billing_account.id,
                    "tenant_id": billing_account.tenant_id,
                    "currency": billing_account.currency.value,
                    "balance": billing_account.balance,
                    "billing_email": billing_account.billing_email,
                    "created_at": billing_account.created_at.isoformat(),
                }
                if billing_account
                else None
            ),
            "members": [
                {
                    "id": m.id,
                    "user_id": m.user_id,
                    "role": m.role,
                    "org_id": m.org_id,
                    "joined_at": m.joined_at.isoformat(),
                    "invited_by": m.invited_by,
                }
                for m in members
            ],
            "organizations": [
                {
                    "id": o.id,
                    "name": o.name,
                    "parent_org_id": o.parent_org_id,
                    "description": o.description,
                }
                for o in organizations
            ],
        }

    return router
