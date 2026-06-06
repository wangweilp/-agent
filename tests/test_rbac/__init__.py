"""Tests for Enterprise RBAC domain models and SQLite adapter."""
import pytest

from src.core.rbac import (
    AccessRequest,
    ActionType,
    EnterpriseRole,
    Permission,
    Policy,
    ResourceType,
    Role,
    RoleAssignment,
    get_default_role_permissions,
    get_default_abac_policies,
)
from src.adapters.rbac_store import RBACStoreAdapter, DefaultABACEngine


class FakeSettings:
    sqlite_db_path = ":memory:"


class TestEnterpriseRole:
    """Test EnterpriseRole enum and hierarchy."""

    def test_hierarchy_order(self):
        h = EnterpriseRole.hierarchy()
        assert h[EnterpriseRole.GUEST] < h[EnterpriseRole.EMPLOYEE]
        assert h[EnterpriseRole.EMPLOYEE] < h[EnterpriseRole.MANAGER]
        assert h[EnterpriseRole.MANAGER] < h[EnterpriseRole.DEPT_ADMIN]
        assert h[EnterpriseRole.DEPT_ADMIN] < h[EnterpriseRole.ORG_ADMIN]
        assert h[EnterpriseRole.ORG_ADMIN] < h[EnterpriseRole.SUPER_ADMIN]

    def test_can_manage_users(self):
        assert EnterpriseRole.SUPER_ADMIN.can_manage_users()
        assert EnterpriseRole.ORG_ADMIN.can_manage_users()
        assert not EnterpriseRole.DEPT_ADMIN.can_manage_users()
        assert not EnterpriseRole.EMPLOYEE.can_manage_users()

    def test_can_access_admin(self):
        assert EnterpriseRole.SUPER_ADMIN.can_access_admin()
        assert EnterpriseRole.ORG_ADMIN.can_access_admin()
        assert EnterpriseRole.DEPT_ADMIN.can_access_admin()
        assert not EnterpriseRole.MANAGER.can_access_admin()
        assert not EnterpriseRole.GUEST.can_access_admin()


class TestPermission:
    """Test Permission model."""

    def test_create_permission(self):
        p = Permission(resource=ResourceType.MEMORY, action=ActionType.CREATE)
        assert p.resource == ResourceType.MEMORY
        assert p.action == ActionType.CREATE
        assert p.key == "memory:create:*"

    def test_permission_key_with_org(self):
        p = Permission(
            resource=ResourceType.WORKSPACE,
            action=ActionType.MANAGE,
            organization_id="org-1",
        )
        assert p.key == "workspace:manage:org-1"


class TestRole:
    """Test Role model."""

    def test_create_role(self):
        role = Role(
            name="custom_role",
            organization_id="org-1",
            permissions=["memory:read:*", "coach:read:*"],
        )
        assert role.name == "custom_role"
        assert len(role.permissions) == 2
        assert not role.is_system

    def test_system_role(self):
        role = Role(name="super_admin", organization_id="org-1", is_system=True)
        assert role.is_system


class TestPolicy:
    """Test ABAC Policy model."""

    def test_create_deny_policy(self):
        policy = Policy(
            name="block-external-ips",
            effect="deny",
            conditions={"subject.ip": {"not_in": ["10.0.0.0/8", "172.16.0.0/12"]}},
            priority=1,
        )
        assert policy.effect == "deny"
        assert policy.priority == 1
        assert policy.enabled

    def test_default_policies(self):
        policies = get_default_abac_policies("org-1")
        assert len(policies) == 2
        deny_policy = policies[0]
        assert deny_policy.effect == "deny"
        assert deny_policy.priority == 1


class TestRoleAssignment:
    """Test RoleAssignment model."""

    def test_create_assignment(self):
        ra = RoleAssignment(
            user_id="user-1", role_id="role-1", organization_id="org-1",
        )
        assert ra.user_id == "user-1"
        assert ra.scope_type == "organization"

    def test_scoped_assignment(self):
        ra = RoleAssignment(
            user_id="user-1", role_id="role-2", organization_id="org-1",
            scope_type="department", scope_id="dept-1",
        )
        assert ra.scope_type == "department"
        assert ra.scope_id == "dept-1"


class TestDefaultPermissions:
    """Test built-in role permission mappings."""

    def test_all_roles_have_permissions(self):
        perms = get_default_role_permissions()
        for role in EnterpriseRole:
            assert role in perms
            assert len(perms[role]) > 0

    def test_super_admin_has_most_permissions(self):
        perms = get_default_role_permissions()
        super_admin_perms = len(perms[EnterpriseRole.SUPER_ADMIN])
        guest_perms = len(perms[EnterpriseRole.GUEST])
        assert super_admin_perms > guest_perms

    def test_guest_permissions_are_read_only(self):
        perms = get_default_role_permissions()
        for pk in perms[EnterpriseRole.GUEST]:
            assert ":create:" not in pk
            assert ":delete:" not in pk
            assert ":manage:" not in pk


class TestABACEngine:
    """Test DefaultABACEngine."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.engine = DefaultABACEngine()

    def _make_request(self, user_id="user-1", org_id="org-1"):
        return AccessRequest(
            user_id=user_id,
            organization_id=org_id,
            resource=ResourceType.MEMORY,
            action=ActionType.READ,
        )

    def test_allow_matching_policy(self):
        policies = [
            Policy(name="allow-all", effect="allow", priority=100, conditions={}),
        ]
        decision = self.engine.evaluate(
            self._make_request(), policies,
            subject_attrs={"org_id": "org-1"},
            resource_attrs={"org_id": "org-1"},
        )
        assert decision.allowed

    def test_deny_overrides_allow(self):
        policies = [
            Policy(name="allow-all", effect="allow", priority=100, conditions={}),
            Policy(name="deny-all", effect="deny", priority=50, conditions={}),
        ]
        decision = self.engine.evaluate(
            self._make_request(), policies,
            subject_attrs={"org_id": "org-1"},
            resource_attrs={"org_id": "org-1"},
        )
        assert not decision.allowed
        assert decision.matched_policy == policies[1].id

    def test_no_matching_policy_defaults_to_deny(self):
        policies = [
            Policy(name="allow-only-org-2", effect="allow", priority=100,
                  conditions={"subject.org_id": {"eq": "org-2"}}),
        ]
        decision = self.engine.evaluate(
            self._make_request(org_id="org-1"), policies,
            subject_attrs={"org_id": "org-1"},
            resource_attrs={"org_id": "org-1"},
        )
        assert not decision.allowed

    def test_cross_org_access_denied(self):
        policies = get_default_abac_policies("org-1")
        decision = self.engine.evaluate(
            self._make_request(user_id="user-1", org_id="org-1"),
            policies,
            subject_attrs={"org_id": "org-1"},
            resource_attrs={"org_id": "org-2"},  # Different org!
        )
        assert not decision.allowed

    def test_same_org_access_allowed(self):
        policies = get_default_abac_policies("org-1")
        decision = self.engine.evaluate(
            self._make_request(user_id="user-1", org_id="org-1"),
            policies,
            subject_attrs={"org_id": "org-1"},
            resource_attrs={"org_id": "org-1"},
        )
        assert decision.allowed

    def test_disabled_policy_ignored(self):
        policies = [
            Policy(name="disabled-deny", effect="deny", priority=1, enabled=False, conditions={}),
            Policy(name="allow-all", effect="allow", priority=100, conditions={}),
        ]
        decision = self.engine.evaluate(
            self._make_request(), policies,
            subject_attrs={}, resource_attrs={},
        )
        assert decision.allowed


class TestRBACStore:
    """Test SQLite RBACStore adapter."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.settings = FakeSettings()
        self.store = RBACStoreAdapter(self.settings)

    def test_create_permission(self):
        p = Permission(resource=ResourceType.MEMORY, action=ActionType.READ)
        created = self.store.create_permission(p)
        assert created.key == p.key

    def test_list_permissions(self):
        p1 = Permission(resource=ResourceType.MEMORY, action=ActionType.READ)
        p2 = Permission(resource=ResourceType.COACH, action=ActionType.READ)
        self.store.create_permission(p1)
        self.store.create_permission(p2)
        perms = self.store.list_permissions("*")
        assert len(perms) >= 2

    def test_create_role(self):
        role = Role(
            name="test_role", organization_id="org-1",
            permissions=["memory:read:*", "coach:read:*"],
        )
        created = self.store.create_role(role)
        assert created.name == "test_role"
        fetched = self.store.get_role(created.id)
        assert fetched is not None
        assert len(fetched.permissions) == 2

    def test_get_role_by_name(self):
        role = Role(name="finder_role", organization_id="org-1", permissions=[])
        self.store.create_role(role)
        fetched = self.store.get_role_by_name("finder_role", "org-1")
        assert fetched is not None

    def test_get_role_by_name_not_found(self):
        assert self.store.get_role_by_name("no_such_role", "org-1") is None

    def test_list_roles(self):
        r1 = Role(name="role_a", organization_id="org-1", permissions=[])
        r2 = Role(name="role_b", organization_id="org-1", permissions=[])
        self.store.create_role(r1)
        self.store.create_role(r2)
        roles = self.store.list_roles("org-1")
        assert len(roles) == 2

    def test_delete_role(self):
        role = Role(name="temp_role", organization_id="org-1", permissions=[])
        created = self.store.create_role(role)
        self.store.delete_role(created.id)
        assert self.store.get_role(created.id) is None

    def test_cannot_delete_system_role(self):
        role = Role(name="super_admin", organization_id="org-1", is_system=True, permissions=[])
        created = self.store.create_role(role)
        self.store.delete_role(created.id)
        # System role should still exist (WHERE is_system = 0)
        # Actually our delete_role only deletes WHERE is_system = 0
        fetched = self.store.get_role(created.id)
        assert fetched is not None

    def test_add_remove_permission_from_role(self):
        role = Role(name="mod_role", organization_id="org-1", permissions=[])
        created = self.store.create_role(role)
        self.store.add_permission_to_role(created.id, "memory:read:*")
        self.store.add_permission_to_role(created.id, "import:create:*")
        fetched = self.store.get_role(created.id)
        assert len(fetched.permissions) == 2

        self.store.remove_permission_from_role(created.id, "memory:read:*")
        fetched = self.store.get_role(created.id)
        assert len(fetched.permissions) == 1
        assert fetched.permissions[0] == "import:create:*"

    def test_create_policy(self):
        policy = Policy(
            name="test-policy", effect="deny", organization_id="org-1",
            conditions={"ip": {"not_in": ["10.0.0.0/8"]}},
        )
        created = self.store.create_policy(policy)
        assert created.name == "test-policy"
        fetched = self.store.get_policy(created.id)
        assert fetched is not None
        assert fetched.conditions == policy.conditions

    def test_list_policies(self):
        p1 = Policy(name="p1", effect="allow", organization_id="org-1", conditions={})
        p2 = Policy(name="p2", effect="deny", organization_id="org-1", conditions={})
        self.store.create_policy(p1)
        self.store.create_policy(p2)
        policies = self.store.list_policies("org-1")
        assert len(policies) == 2

    def test_delete_policy(self):
        policy = Policy(name="temp", effect="allow", organization_id="org-1", conditions={})
        created = self.store.create_policy(policy)
        self.store.delete_policy(created.id)
        assert self.store.get_policy(created.id) is None

    def test_assign_role(self):
        role = Role(name="assigned_role", organization_id="org-1", permissions=["memory:read:*"])
        created_role = self.store.create_role(role)

        assignment = RoleAssignment(
            user_id="user-1", role_id=created_role.id, organization_id="org-1",
        )
        self.store.assign_role(assignment)

        assignments = self.store.get_user_assignments("user-1", "org-1")
        assert len(assignments) == 1
        assert assignments[0].role_id == created_role.id

    def test_get_user_roles(self):
        role = Role(name="test_get_roles", organization_id="org-1",
                   permissions=["memory:read:*"])
        created_role = self.store.create_role(role)

        assignment = RoleAssignment(
            user_id="user-1", role_id=created_role.id, organization_id="org-1",
        )
        self.store.assign_role(assignment)

        roles = self.store.get_user_roles("user-1", "org-1")
        assert len(roles) == 1
        assert roles[0].name == "test_get_roles"

    def test_remove_assignment(self):
        role = Role(name="removable", organization_id="org-1", permissions=[])
        created_role = self.store.create_role(role)

        assignment = RoleAssignment(
            user_id="user-1", role_id=created_role.id, organization_id="org-1",
        )
        self.store.assign_role(assignment)

        assignments = self.store.get_user_assignments("user-1", "org-1")
        self.store.remove_assignment(assignments[0].id)

        remaining = self.store.get_user_assignments("user-1", "org-1")
        assert len(remaining) == 0

    def test_check_access_allowed(self):
        role = Role(name="test_access", organization_id="org-1",
                   permissions=["memory:read:*"])
        created_role = self.store.create_role(role)
        self.store.assign_role(RoleAssignment(
            user_id="user-1", role_id=created_role.id, organization_id="org-1",
        ))

        request = AccessRequest(
            user_id="user-1", organization_id="org-1",
            resource=ResourceType.MEMORY, action=ActionType.READ,
        )
        decision = self.store.check_access(request)
        assert decision.allowed

    def test_check_access_denied_no_permission(self):
        role = Role(name="limited", organization_id="org-1",
                   permissions=["coach:read:*"])
        created_role = self.store.create_role(role)
        self.store.assign_role(RoleAssignment(
            user_id="user-1", role_id=created_role.id, organization_id="org-1",
        ))

        request = AccessRequest(
            user_id="user-1", organization_id="org-1",
            resource=ResourceType.ADMIN, action=ActionType.MANAGE,
        )
        decision = self.store.check_access(request)
        assert not decision.allowed

    def test_check_access_no_roles(self):
        request = AccessRequest(
            user_id="user-no-roles", organization_id="org-1",
            resource=ResourceType.MEMORY, action=ActionType.READ,
        )
        decision = self.store.check_access(request)
        assert not decision.allowed

    def test_bootstrap_organization_roles(self):
        roles = self.store.bootstrap_organization_roles("org-bootstrap")
        assert len(roles) == 6  # super_admin, org_admin, dept_admin, manager, employee, guest
        assert "super_admin" in roles
        assert "guest" in roles

        # Second bootstrap should be idempotent
        roles2 = self.store.bootstrap_organization_roles("org-bootstrap")
        assert len(roles2) == 6
