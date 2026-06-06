"""Tests for Organization domain models and SQLite adapter."""
import pytest
import tempfile
import os

from src.core.organization import (
    Organization, BusinessUnit, Department, Position, OrgTreeNode,
)
from src.adapters.org_store import OrganizationStoreAdapter
from src.adapters.config import Settings


class FakeSettings:
    sqlite_db_path = ":memory:"


class TestOrganizationModel:
    """Test Organization core domain model."""

    def test_create_organization(self):
        org = Organization(name="测试公司", owner_id="user-1", industry="科技")
        assert org.name == "测试公司"
        assert org.owner_id == "user-1"
        assert org.industry == "科技"
        assert org.id != ""

    def test_create_business_unit(self):
        bu = BusinessUnit(organization_id="org-1", name="研发中心")
        assert bu.organization_id == "org-1"
        assert bu.name == "研发中心"
        assert bu.parent_id is None

    def test_business_unit_with_parent(self):
        parent = BusinessUnit(organization_id="org-1", name="技术中心")
        child = BusinessUnit(organization_id="org-1", name="AI组", parent_id=parent.id)
        assert child.parent_id == parent.id

    def test_create_department(self):
        dept = Department(
            organization_id="org-1", business_unit_id="bu-1", name="后端组",
        )
        assert dept.name == "后端组"
        assert dept.business_unit_id == "bu-1"

    def test_create_position(self):
        pos = Position(
            organization_id="org-1", department_id="dept-1",
            user_id="user-1", title="高级工程师", is_manager=True,
        )
        assert pos.title == "高级工程师"
        assert pos.is_manager is True

    def test_org_tree_node(self):
        node = OrgTreeNode(id="1", name="root", node_type="organization")
        child = OrgTreeNode(id="2", name="bu", node_type="business_unit", member_count=5)
        node.children.append(child)
        assert len(node.children) == 1
        assert node.children[0].member_count == 5


class TestOrganizationStore:
    """Test SQLite OrganizationStore adapter."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.settings = FakeSettings()
        self.store = OrganizationStoreAdapter(self.settings)

    def test_create_organization_creates_default_structure(self):
        org = self.store.create_organization("测试集团", "user-1", "科技")
        assert org.name == "测试集团"

        # Verify default BU structure is created
        bus = self.store.list_business_units(org.id)
        assert len(bus) >= 4  # 研发/产品/市场/运营

        # Verify departments under first BU
        depts = self.store.list_departments(org.id, bus[0].id)
        assert len(depts) > 0

    def test_get_organization(self):
        org = self.store.create_organization("测试", "user-1")
        fetched = self.store.get_organization(org.id)
        assert fetched is not None
        assert fetched.name == "测试"

    def test_get_organization_not_found(self):
        assert self.store.get_organization("nonexistent") is None

    def test_list_organizations(self):
        self.store.create_organization("Org A", "user-1")
        self.store.create_organization("Org B", "user-1")
        orgs = self.store.list_organizations("user-1")
        assert len(orgs) >= 2

    def test_update_organization(self):
        org = self.store.create_organization("Old Name", "user-1")
        org.name = "New Name"
        org.industry = "金融"
        self.store.update_organization(org)
        fetched = self.store.get_organization(org.id)
        assert fetched.name == "New Name"
        assert fetched.industry == "金融"

    def test_delete_organization(self):
        org = self.store.create_organization("To Delete", "user-1")
        self.store.delete_organization(org.id)
        assert self.store.get_organization(org.id) is None

    def test_create_business_unit(self):
        org = self.store.create_organization("Test", "user-1")
        bu = self.store.create_business_unit(org.id, "新事业部", description="测试")
        assert bu.name == "新事业部"
        assert bu.organization_id == org.id

    def test_update_business_unit(self):
        org = self.store.create_organization("Test", "user-1")
        bu = self.store.create_business_unit(org.id, "Old BU")
        bu.name = "New BU"
        self.store.update_business_unit(bu)
        fetched = self.store.get_business_unit(bu.id)
        assert fetched.name == "New BU"

    def test_delete_business_unit(self):
        org = self.store.create_organization("Test", "user-1")
        bu = self.store.create_business_unit(org.id, "To Delete")
        self.store.delete_business_unit(bu.id)
        assert self.store.get_business_unit(bu.id) is None

    def test_create_department(self):
        org = self.store.create_organization("Test", "user-1")
        bu = self.store.create_business_unit(org.id, "研发中心")
        dept = self.store.create_department(org.id, bu.id, "后端组")
        assert dept.name == "后端组"
        assert dept.business_unit_id == bu.id

    def test_list_departments_by_bu(self):
        org = self.store.create_organization("Test", "user-1")
        bu = self.store.create_business_unit(org.id, "BU1")
        bu2 = self.store.create_business_unit(org.id, "BU2")
        self.store.create_department(org.id, bu.id, "Dept A")
        self.store.create_department(org.id, bu2.id, "Dept B")

        depts_a = self.store.list_departments(org.id, bu.id)
        assert len(depts_a) == 1
        assert depts_a[0].name == "Dept A"

    def test_create_position(self):
        org = self.store.create_organization("Test", "user-1")
        bu = self.store.create_business_unit(org.id, "BU")
        dept = self.store.create_department(org.id, bu.id, "Dept")
        pos = self.store.create_position(org.id, dept.id, "user-2", "工程师", True)
        assert pos.title == "工程师"
        assert pos.is_manager is True

    def test_get_position_by_user(self):
        org = self.store.create_organization("Test", "user-1")
        bu = self.store.create_business_unit(org.id, "BU")
        dept = self.store.create_department(org.id, bu.id, "Dept")
        self.store.create_position(org.id, dept.id, "user-alice", "PM")

        pos = self.store.get_position_by_user("user-alice", org.id)
        assert pos is not None
        assert pos.title == "PM"

    def test_list_positions_by_user(self):
        org = self.store.create_organization("Test", "user-1")
        bu = self.store.create_business_unit(org.id, "BU")
        dept = self.store.create_department(org.id, bu.id, "Dept")
        self.store.create_position(org.id, dept.id, "user-multi", "Role A")

        org2 = self.store.create_organization("Test2", "user-99")
        bu2 = self.store.create_business_unit(org2.id, "BU")
        dept2 = self.store.create_department(org2.id, bu2.id, "Dept")
        self.store.create_position(org2.id, dept2.id, "user-multi", "Role B")

        positions = self.store.list_positions_by_user("user-multi")
        assert len(positions) == 2

    def test_delete_position(self):
        org = self.store.create_organization("Test", "user-1")
        bu = self.store.create_business_unit(org.id, "BU")
        dept = self.store.create_department(org.id, bu.id, "Dept")
        pos = self.store.create_position(org.id, dept.id, "user-x", "Intern")
        self.store.delete_position(pos.id)
        assert self.store.get_position(pos.id) is None

    def test_get_org_tree(self):
        org = self.store.create_organization("TestGroup", "user-1")
        tree = self.store.get_org_tree(org.id)
        assert tree is not None
        assert tree.node_type == "organization"
        assert len(tree.children) >= 4

    def test_get_org_tree_nonexistent(self):
        assert self.store.get_org_tree("nonexistent") is None

    def test_get_member_count(self):
        org = self.store.create_organization("Test", "user-1")
        bu = self.store.create_business_unit(org.id, "BU")
        dept = self.store.create_department(org.id, bu.id, "Dept")
        self.store.create_position(org.id, dept.id, "user-a", "Eng")
        self.store.create_position(org.id, dept.id, "user-b", "Eng")
        self.store.create_position(org.id, dept.id, "user-a", "Eng")  # same user

        count = self.store.get_member_count(org.id)
        assert count == 2  # DISTINCT users
