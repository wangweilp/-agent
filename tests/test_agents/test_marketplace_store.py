"""Marketplace Store 测试。"""
import pytest

from src.adapters.config import Settings
from src.adapters.marketplace_store import (
    SQLiteMarketplaceStore,
    DuplicateInstallationError,
)
from src.agents.marketplace import (
    MarketplaceAgent,
    MarketplaceAgentStatus,
    MarketplaceAgentVisibility,
    TenantAgentInstallation,
    InstallationStatus,
    seed_builtin_marketplace_agents,
)


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def store(settings):
    """使用 :memory: SQLite 的 MarketplaceStore（测试隔离）。"""
    return SQLiteMarketplaceStore(settings, db_path=":memory:")


@pytest.fixture
def sample_agent():
    return MarketplaceAgent(
        marketplace_agent_id="mkp_test_001",
        agent_id="test-agent-001",
        name="test-agent",
        display_name="测试 Agent",
        description="测试用 Agent",
        long_description="详细的测试描述",
        category="automation",
        department="研发部",
        capabilities=["测试能力A", "测试能力B"],
        required_permissions=["agent:execute", "memory:read"],
        supported_workflows=["test-workflow-1"],
        version="1.2.3",
        publisher_type="platform",
        publisher_name="Test Publisher",
        icon="Bot",
        visibility="public",
        pricing_model="free",
        usage_limits={"max_calls_per_day": 100},
        status="active",
    )


# ═══════════════════════════════════════════
# MarketplaceAgent CRUD
# ═══════════════════════════════════════════


class TestMarketplaceAgentCrud:
    def test_create_and_get(self, store, sample_agent):
        store.create_agent(sample_agent)
        agent = store.get_agent("mkp_test_001")
        assert agent is not None
        assert agent.display_name == "测试 Agent"
        assert agent.category == "automation"
        assert agent.department == "研发部"
        assert agent.capabilities == ["测试能力A", "测试能力B"]
        assert agent.version == "1.2.3"
        assert agent.publisher_type == "platform"

    def test_get_by_agent_id(self, store, sample_agent):
        store.create_agent(sample_agent)
        agent = store.get_agent_by_agent_id("test-agent-001")
        assert agent is not None
        assert agent.marketplace_agent_id == "mkp_test_001"

    def test_get_nonexistent(self, store):
        assert store.get_agent("nonexistent") is None
        assert store.get_agent_by_agent_id("nonexistent") is None

    def test_list_all(self, store):
        store.create_agent(MarketplaceAgent(marketplace_agent_id="mkp_a", agent_id="a", name="A", category="automation"))
        store.create_agent(MarketplaceAgent(marketplace_agent_id="mkp_b", agent_id="b", name="B", category="assistant"))
        agents = store.list_agents()
        assert len(agents) == 2

    def test_filter_by_category(self, store):
        store.create_agent(MarketplaceAgent(marketplace_agent_id="mkp_a", agent_id="a", name="A", category="automation"))
        store.create_agent(MarketplaceAgent(marketplace_agent_id="mkp_b", agent_id="b", name="B", category="assistant"))
        result = store.list_agents(category="automation")
        assert len(result) == 1
        assert result[0].category == "automation"

    def test_filter_by_department(self, store):
        store.create_agent(MarketplaceAgent(marketplace_agent_id="mkp_a", agent_id="a", name="A", department="研发部"))
        store.create_agent(MarketplaceAgent(marketplace_agent_id="mkp_b", agent_id="b", name="B", department="销售部"))
        result = store.list_agents(department="研发部")
        assert len(result) == 1
        assert result[0].department == "研发部"

    def test_filter_by_status(self, store):
        store.create_agent(MarketplaceAgent(marketplace_agent_id="mkp_a", agent_id="a", name="A", status="active"))
        store.create_agent(MarketplaceAgent(marketplace_agent_id="mkp_b", agent_id="b", name="B", status="beta"))
        result = store.list_agents(status="beta")
        assert len(result) == 1

    def test_update_agent(self, store, sample_agent):
        store.create_agent(sample_agent)
        sample_agent.display_name = "更新后的名称"
        sample_agent.capabilities = ["新能力"]
        store.update_agent(sample_agent)
        agent = store.get_agent("mkp_test_001")
        assert agent.display_name == "更新后的名称"
        assert agent.capabilities == ["新能力"]

    def test_deactivate_agent(self, store, sample_agent):
        store.create_agent(sample_agent)
        store.deactivate_agent("mkp_test_001")
        agent = store.get_agent("mkp_test_001")
        assert agent.status == "disabled"

    def test_increment_install_count(self, store, sample_agent):
        store.create_agent(sample_agent)
        store.increment_install_count("mkp_test_001")
        store.increment_install_count("mkp_test_001")
        agent = store.get_agent("mkp_test_001")
        assert agent.install_count == 2


# ═══════════════════════════════════════════
# TenantAgentInstallation
# ═══════════════════════════════════════════


class TestInstallation:
    def test_install_agent(self, store, sample_agent):
        store.create_agent(sample_agent)
        inst = store.install_agent(
            "mkp_test_001", "test-agent-001", "t1", "ws1", "user-1",
            config={"timeout": 30},
            permissions_granted=["agent:execute"],
        )
        assert inst.installation_id.startswith("inst_")
        assert inst.status == "active"
        assert inst.enabled is True
        assert inst.config == {"timeout": 30}
        assert inst.permissions_granted == ["agent:execute"]
        assert inst.tenant_id == "t1"

    def test_duplicate_install_rejected(self, store, sample_agent):
        store.create_agent(sample_agent)
        store.install_agent("mkp_test_001", "test-agent-001", "t1", "ws1", "user-1")
        with pytest.raises(DuplicateInstallationError):
            store.install_agent("mkp_test_001", "test-agent-001", "t1", "ws1", "user-2")

    def test_get_installation(self, store, sample_agent):
        store.create_agent(sample_agent)
        inst = store.install_agent("mkp_test_001", "test-agent-001", "t1", "ws1", "user-1")
        found = store.get_installation(inst.installation_id)
        assert found is not None
        assert found.marketplace_agent_id == "mkp_test_001"

    def test_get_installation_nonexistent(self, store):
        assert store.get_installation("nonexistent") is None

    def test_list_installations_by_tenant(self, store, sample_agent):
        store.create_agent(sample_agent)
        store.install_agent("mkp_test_001", "test-agent-001", "t1", "ws1", "user-1")
        store.install_agent("mkp_test_001", "test-agent-001", "t2", "ws1", "user-2")
        # t1 only
        result = store.list_installations(tenant_id="t1")
        assert len(result) == 1
        assert result[0].tenant_id == "t1"

    def test_list_installations_by_workspace(self, store, sample_agent):
        store.create_agent(sample_agent)
        store.install_agent("mkp_test_001", "test-agent-001", "t1", "ws-a", "user-1")
        store.install_agent("mkp_test_001", "test-agent-001", "t1", "ws-b", "user-1")
        result = store.list_installations(tenant_id="t1", workspace_id="ws-a")
        assert len(result) == 1

    def test_tenant_isolation(self, store, sample_agent):
        """tenant A 不应该看到 tenant B 的 installation。"""
        store.create_agent(sample_agent)
        store.install_agent("mkp_test_001", "test-agent-001", "t-a", "ws1", "user-a")
        # t-b 查询 t-a 的 installation
        inst = store.get_installation_by_agent("mkp_test_001", "t-b", "ws1")
        assert inst is None

    def test_workspace_isolation(self, store, sample_agent):
        """workspace A 不应该看到 workspace B 的 installation。"""
        store.create_agent(sample_agent)
        store.install_agent("mkp_test_001", "test-agent-001", "t1", "ws-a", "user-1")
        inst = store.get_installation_by_agent("mkp_test_001", "t1", "ws-b")
        assert inst is None

    def test_enable_disable_installation(self, store, sample_agent):
        store.create_agent(sample_agent)
        inst = store.install_agent("mkp_test_001", "test-agent-001", "t1", "ws1", "user-1")

        ok = store.disable_installation(inst.installation_id, "t1", "ws1")
        assert ok is True
        found = store.get_installation(inst.installation_id)
        assert found.status == "disabled"
        assert found.enabled is False

        ok = store.enable_installation(inst.installation_id, "t1", "ws1")
        assert ok is True
        found = store.get_installation(inst.installation_id)
        assert found.status == "active"
        assert found.enabled is True

    def test_enable_wrong_tenant_rejected(self, store, sample_agent):
        """错误 tenant 不能操作其他 tenant 的 installation。"""
        store.create_agent(sample_agent)
        inst = store.install_agent("mkp_test_001", "test-agent-001", "t1", "ws1", "user-1")
        ok = store.disable_installation(inst.installation_id, "t-evil", "ws1")
        assert ok is False

    def test_update_installation_config(self, store, sample_agent):
        store.create_agent(sample_agent)
        inst = store.install_agent("mkp_test_001", "test-agent-001", "t1", "ws1", "user-1",
                                    config={"key1": "val1"})
        ok = store.update_installation_config(inst.installation_id, "t1", "ws1", {"key2": "val2"})
        assert ok is True
        found = store.get_installation(inst.installation_id)
        assert found.config == {"key1": "val1", "key2": "val2"}

    def test_uninstall_soft_delete(self, store, sample_agent):
        store.create_agent(sample_agent)
        inst = store.install_agent("mkp_test_001", "test-agent-001", "t1", "ws1", "user-1")

        ok = store.uninstall_agent(inst.installation_id, "t1", "ws1")
        assert ok is True

        # 直接 get 仍然能拿到（软删除）
        found = store.get_installation(inst.installation_id)
        assert found.status == "uninstalled"
        assert found.enabled is False

        # 但默认 list 不包含 uninstalled
        result = store.list_installations(tenant_id="t1")
        assert len(result) == 0

    def test_uninstalled_can_reinstall(self, store, sample_agent):
        """卸载后允许重新安装。"""
        store.create_agent(sample_agent)
        inst = store.install_agent("mkp_test_001", "test-agent-001", "t1", "ws1", "user-1")
        store.uninstall_agent(inst.installation_id, "t1", "ws1")
        # 重新安装不应抛异常
        inst2 = store.install_agent("mkp_test_001", "test-agent-001", "t1", "ws1", "user-2")
        assert inst2.installation_id != inst.installation_id

    def test_is_agent_installed(self, store, sample_agent):
        store.create_agent(sample_agent)
        assert store.is_agent_installed("mkp_test_001", "t1", "ws1") is False
        store.install_agent("mkp_test_001", "test-agent-001", "t1", "ws1", "user-1")
        assert store.is_agent_installed("mkp_test_001", "t1", "ws1") is True

    def test_permissions_granted_persist(self, store, sample_agent):
        store.create_agent(sample_agent)
        inst = store.install_agent("mkp_test_001", "test-agent-001", "t1", "ws1", "user-1",
                                     permissions_granted=["agent:execute", "memory:read"])
        found = store.get_installation(inst.installation_id)
        assert "agent:execute" in found.permissions_granted
        assert "memory:read" in found.permissions_granted

    def test_version_pinned_persist(self, store, sample_agent):
        store.create_agent(sample_agent)
        inst = store.install_agent("mkp_test_001", "test-agent-001", "t1", "ws1", "user-1")
        # Direct DB update to simulate version pinning
        from datetime import datetime, timezone
        store._db.execute(
            "UPDATE tenant_agent_installations SET version_pinned = ? WHERE installation_id = ?",
            ["1.0.0-locked", inst.installation_id],
        )
        found = store.get_installation(inst.installation_id)
        assert found.version_pinned == "1.0.0-locked"


# ═══════════════════════════════════════════
# Built-in Catalog
# ═══════════════════════════════════════════


class TestBuiltinCatalog:
    def test_seed_creates_agents(self, store):
        created = seed_builtin_marketplace_agents(store)
        assert created >= 1
        all_agents = store.list_agents()
        assert len(all_agents) >= 3  # at least meeting, knowledge, department

    def test_seed_idempotent(self, store):
        seed_builtin_marketplace_agents(store)
        first_count = len(store.list_agents())
        created = seed_builtin_marketplace_agents(store)
        # Second call should create 0 new agents
        assert created == 0
        assert len(store.list_agents()) == first_count

    def test_builtin_has_categories(self, store):
        seed_builtin_marketplace_agents(store)
        agents = store.list_agents()
        categories = {a.category for a in agents}
        assert "automation" in categories
        assert "knowledge" in categories
        assert "assistant" in categories

    def test_builtin_has_capabilities(self, store):
        seed_builtin_marketplace_agents(store)
        meeting = store.get_agent("mkp_meeting_training")
        assert meeting is not None
        assert "会议纪要提取" in meeting.capabilities
        assert "agent:execute" in meeting.required_permissions
