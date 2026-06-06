"""Pytest test suite for multi-tenant module.

Covers Tenant, TenantMember, Organization CRUD plus cross-tenant isolation.
"""
import os
import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.tenant_store import TenantStoreAdapter
from src.adapters.config import Settings
from src.core.tenant import (
    Organization,
    OrganizationSize,
    Tenant,
    TenantMember,
    TenantStatus,
)


def make_store() -> TenantStoreAdapter:
    """Return a fresh in-memory TenantStoreAdapter for test isolation."""
    return TenantStoreAdapter(
        Settings(
            _env_file=None,
            deepseek_api_key="test-key",
            sqlite_db_path=":memory:",
        )
    )


def make_tenant(
    name: str = "Test Corp",
    email: str = "admin@testcorp.com",
    slug: str = "test-corp",
    status: TenantStatus = TenantStatus.TRIAL,
    owner_user_id: str = "usr_abc123",
    org_size: OrganizationSize = OrganizationSize.SMALL,
    industry: str = "Technology",
) -> Tenant:
    return Tenant(
        name=name,
        email=email,
        slug=slug,
        status=status,
        owner_user_id=owner_user_id,
        org_size=org_size,
        industry=industry,
    )


def make_member(
    tenant_id: str,
    user_id: str = "usr_member001",
    role: str = "member",
    org_id: str | None = None,
    invited_by: str | None = None,
) -> TenantMember:
    return TenantMember(
        tenant_id=tenant_id,
        user_id=user_id,
        role=role,
        org_id=org_id,
        invited_by=invited_by,
    )


def make_org(
    tenant_id: str,
    name: str = "Engineering",
    parent_org_id: str | None = None,
    description: str = "",
) -> Organization:
    return Organization(
        tenant_id=tenant_id,
        name=name,
        parent_org_id=parent_org_id,
        description=description,
    )


# ── Tenant CRUD ──


def test_create_tenant():
    """Create a tenant and verify the auto-generated id."""
    store = make_store()
    t = make_tenant()
    created = store.create_tenant(t)

    assert created.id == t.id
    assert created.id.startswith("tnt_")
    assert len(created.id) == 16  # "tnt_" + 12 hex chars
    assert created.name == "Test Corp"
    assert created.email == "admin@testcorp.com"
    assert created.slug == "test-corp"
    assert created.status == TenantStatus.TRIAL
    assert created.is_active is True


def test_get_tenant():
    """Retrieve a tenant by id."""
    store = make_store()
    t = make_tenant()
    store.create_tenant(t)

    retrieved = store.get_tenant(t.id)
    assert retrieved is not None
    assert retrieved.id == t.id
    assert retrieved.name == t.name
    assert retrieved.email == t.email


def test_get_tenant_by_slug():
    """Retrieve a tenant by slug."""
    store = make_store()
    t = make_tenant(slug="acme-corp")
    store.create_tenant(t)

    retrieved = store.get_tenant_by_slug("acme-corp")
    assert retrieved is not None
    assert retrieved.id == t.id
    assert retrieved.slug == "acme-corp"


def test_tenant_not_found():
    """get_tenant returns None for a non-existent id."""
    store = make_store()
    assert store.get_tenant("tnt_nonexistent") is None
    assert store.get_tenant_by_slug("no-such-slug") is None


def test_update_tenant():
    """Update tenant name, email, and industry."""
    store = make_store()
    t = make_tenant()
    store.create_tenant(t)

    t.name = "Updated Corp"
    t.email = "new@updated.com"
    t.industry = "Finance"
    store.update_tenant(t)

    retrieved = store.get_tenant(t.id)
    assert retrieved is not None
    assert retrieved.name == "Updated Corp"
    assert retrieved.email == "new@updated.com"
    assert retrieved.industry == "Finance"


def test_delete_tenant_soft():
    """Soft delete: status becomes 'closed', tenant still exists."""
    store = make_store()
    t = make_tenant()
    store.create_tenant(t)

    store.delete_tenant(t.id)

    retrieved = store.get_tenant(t.id)
    assert retrieved is not None  # row still exists
    assert retrieved.status == TenantStatus.CLOSED
    assert retrieved.is_active is False


def test_list_tenants():
    """List all tenants and filter by status."""
    store = make_store()

    t1 = make_tenant(name="A Corp", slug="a-corp", status=TenantStatus.ACTIVE)
    t2 = make_tenant(name="B Corp", slug="b-corp", status=TenantStatus.TRIAL)
    t3 = make_tenant(name="C Corp", slug="c-corp", status=TenantStatus.CLOSED)

    store.create_tenant(t1)
    store.create_tenant(t2)
    store.create_tenant(t3)

    # List all
    all_tenants = store.list_tenants()
    assert len(all_tenants) == 3

    # Filter by active
    active = store.list_tenants(status="active")
    assert len(active) == 1
    assert active[0].id == t1.id

    # Filter by trial
    trial = store.list_tenants(status="trial")
    assert len(trial) == 1
    assert trial[0].id == t2.id

    # Filter by closed
    closed = store.list_tenants(status="closed")
    assert len(closed) == 1
    assert closed[0].id == t3.id


def test_tenant_exists():
    """tenant_exists helper returns True/False correctly."""
    store = make_store()
    t = make_tenant()
    store.create_tenant(t)

    assert store.tenant_exists(t.id) is True
    assert store.tenant_exists("tnt_nonexistent") is False


# ── Member Management ──


def test_add_member():
    """Add a member and verify role."""
    store = make_store()
    t = make_tenant()
    store.create_tenant(t)

    member = make_member(tenant_id=t.id, user_id="usr_alice", role="admin")
    added = store.add_member(member)

    assert added.id == member.id
    assert added.id.startswith("tmem_")
    assert added.tenant_id == t.id
    assert added.user_id == "usr_alice"
    assert added.role == "admin"


def test_list_members():
    """List all members of a tenant."""
    store = make_store()
    t = make_tenant()
    store.create_tenant(t)

    m1 = store.add_member(make_member(t.id, "usr_alice"))
    m2 = store.add_member(make_member(t.id, "usr_bob"))
    m3 = store.add_member(make_member(t.id, "usr_carol"))

    members = store.list_members(t.id)
    assert len(members) == 3
    user_ids = {m.user_id for m in members}
    assert user_ids == {"usr_alice", "usr_bob", "usr_carol"}


def test_remove_member():
    """Remove a member, verify they are gone."""
    store = make_store()
    t = make_tenant()
    store.create_tenant(t)

    store.add_member(make_member(t.id, "usr_alice"))
    store.add_member(make_member(t.id, "usr_bob"))

    store.remove_member(t.id, "usr_alice")

    members = store.list_members(t.id)
    assert len(members) == 1
    assert members[0].user_id == "usr_bob"

    # Verify get_member returns None
    assert store.get_member(t.id, "usr_alice") is None


def test_get_member():
    """Retrieve a specific member by tenant_id and user_id."""
    store = make_store()
    t = make_tenant()
    store.create_tenant(t)

    store.add_member(make_member(t.id, "usr_dave", role="viewer"))

    m = store.get_member(t.id, "usr_dave")
    assert m is not None
    assert m.user_id == "usr_dave"
    assert m.role == "viewer"

    # Non-existent member
    assert store.get_member(t.id, "usr_ghost") is None


def test_duplicate_member():
    """Unique constraint on (tenant_id, user_id) prevents duplicates."""
    store = make_store()
    t = make_tenant()
    store.create_tenant(t)

    store.add_member(make_member(t.id, "usr_eve"))

    with pytest.raises(Exception):
        store.add_member(make_member(t.id, "usr_eve"))


# ── Organization Management ──


def test_create_organization():
    """Create an organization under a tenant."""
    store = make_store()
    t = make_tenant()
    store.create_tenant(t)

    org = make_org(t.id, name="Engineering", description="Main engineering org")
    created = store.create_organization(org)

    assert created.id == org.id
    assert created.id.startswith("org_")
    assert created.tenant_id == t.id
    assert created.name == "Engineering"
    assert created.description == "Main engineering org"
    assert created.parent_org_id is None


def test_list_organizations():
    """List organizations, verify parent hierarchy."""
    store = make_store()
    t = make_tenant()
    store.create_tenant(t)

    eng = store.create_organization(make_org(t.id, name="Engineering"))
    be = store.create_organization(
        make_org(t.id, name="Backend", parent_org_id=eng.id)
    )
    fe = store.create_organization(
        make_org(t.id, name="Frontend", parent_org_id=eng.id)
    )

    orgs = store.list_organizations(t.id)
    assert len(orgs) == 3

    names = {o.name for o in orgs}
    assert names == {"Engineering", "Backend", "Frontend"}

    # Verify parent hierarchy
    be_retrieved = store.get_organization(be.id)
    assert be_retrieved is not None
    assert be_retrieved.parent_org_id == eng.id

    fe_retrieved = store.get_organization(fe.id)
    assert fe_retrieved is not None
    assert fe_retrieved.parent_org_id == eng.id


def test_delete_organization():
    """Hard delete an organization."""
    store = make_store()
    t = make_tenant()
    store.create_tenant(t)

    org = store.create_organization(make_org(t.id, name="Temp Org"))

    # Verify it exists
    assert store.get_organization(org.id) is not None

    store.delete_organization(org.id)

    # Verify it is gone
    assert store.get_organization(org.id) is None
    assert len(store.list_organizations(t.id)) == 0


# ── Cross-Tenant Isolation ──


def test_cross_tenant_isolation():
    """CRITICAL: Members and orgs of tenant A do not leak into tenant B,
    and deletion of one tenant does not affect the other."""
    store = make_store()

    # Create two tenants
    tenant_a = make_tenant(name="Tenant A", slug="tenant-a", email="a@corp.com")
    tenant_b = make_tenant(name="Tenant B", slug="tenant-b", email="b@corp.com")
    store.create_tenant(tenant_a)
    store.create_tenant(tenant_b)

    # Add members to each
    store.add_member(make_member(tenant_a.id, "usr_alice", role="admin"))
    store.add_member(make_member(tenant_a.id, "usr_bob", role="member"))
    store.add_member(make_member(tenant_b.id, "usr_carol", role="owner"))
    store.add_member(make_member(tenant_b.id, "usr_dave", role="member"))

    # Add organizations to each
    store.create_organization(make_org(tenant_a.id, name="Engineering A"))
    store.create_organization(make_org(tenant_a.id, name="Design A"))
    store.create_organization(make_org(tenant_b.id, name="Engineering B"))

    # --- Assertion 1: Members of tenant A do NOT appear in tenant B ---
    members_a = store.list_members(tenant_a.id)
    members_b = store.list_members(tenant_b.id)

    assert len(members_a) == 2
    assert len(members_b) == 2

    user_ids_a = {m.user_id for m in members_a}
    user_ids_b = {m.user_id for m in members_b}
    assert user_ids_a == {"usr_alice", "usr_bob"}
    assert user_ids_b == {"usr_carol", "usr_dave"}
    assert user_ids_a.isdisjoint(user_ids_b)

    # Verify get_member with wrong tenant returns None
    assert store.get_member(tenant_a.id, "usr_carol") is None
    assert store.get_member(tenant_b.id, "usr_alice") is None

    # --- Assertion 2: Organizations of tenant A do NOT appear in tenant B ---
    orgs_a = store.list_organizations(tenant_a.id)
    orgs_b = store.list_organizations(tenant_b.id)

    assert len(orgs_a) == 2
    assert len(orgs_b) == 1

    org_names_a = {o.name for o in orgs_a}
    org_names_b = {o.name for o in orgs_b}
    assert org_names_a == {"Engineering A", "Design A"}
    assert org_names_b == {"Engineering B"}

    # --- Assertion 3: Deletion of tenant A does NOT affect tenant B ---
    store.delete_tenant(tenant_a.id)

    # Tenant A should be CLOSED
    a_after = store.get_tenant(tenant_a.id)
    assert a_after is not None
    assert a_after.status == TenantStatus.CLOSED

    # Tenant B should still be active
    b_after = store.get_tenant(tenant_b.id)
    assert b_after is not None
    assert b_after.status == TenantStatus.TRIAL  # unchanged

    # Tenant B members and orgs still intact
    assert len(store.list_members(tenant_b.id)) == 2
    assert len(store.list_organizations(tenant_b.id)) == 1
