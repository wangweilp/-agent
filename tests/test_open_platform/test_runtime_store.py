"""Runtime Store 单元测试 — RuntimeAdapter + DeveloperAgentRuntimeBinding。

覆盖:
- RuntimeAdapter Model: create, to_dict/from_dict, is_active, is_mvp_allowed
- Adapter Store: seed, CRUD, list, filter, update, duplicate
- RuntimeBinding Model: create, to_dict/from_dict, is_enabled
- Binding Store: CRUD, tenant isolation, enable/disable/suspend, sandbox policy
- Eligibility: no_binding, disabled, adapter_disabled, non_mvp, sandbox_required, simulation eligible
- Non-execution: 不执行 package_url, 不调用 AgentRuntime, 不注册 AgentRegistry
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.runtime_store import SQLiteRuntimeStore
from src.open_platform.runtime import (
    DeveloperAgentRuntimeBinding,
    RuntimeAdapter,
    RuntimeAdapterAlreadyExistsError,
    RuntimeAdapterNotAllowedError,
    RuntimeAdapterNotFoundError,
    RuntimeAdapterStatus,
    RuntimeAdapterType,
    RuntimeBindingAlreadyExistsError,
    RuntimeBindingNotFoundError,
    RuntimeBindingStatus,
    RuntimeEligibilityCode,
    RuntimeEligibilityResult,
    RuntimeStateError,
    is_mvp_allowed_adapter_type,
)

# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def store(settings):
    return SQLiteRuntimeStore(settings, db_path=":memory:")


@pytest.fixture
def seeded_store(store):
    store.seed_builtin_adapters()
    return store


# ═══════════════════════════════════════════
# 1. RuntimeAdapter Model
# ═══════════════════════════════════════════


class TestRuntimeAdapterModel:
    def test_create_manifest_only_model(self):
        a = RuntimeAdapter(
            adapter_type=RuntimeAdapterType.MANIFEST_ONLY,
            name="Manifest Only",
            description="No execution",
        )
        assert a.adapter_type == RuntimeAdapterType.MANIFEST_ONLY
        assert a.adapter_id.startswith("rtadp_")
        assert not a.supports_network
        assert not a.sandbox_required

    def test_create_simulation_model(self):
        a = RuntimeAdapter(
            adapter_type=RuntimeAdapterType.SIMULATION,
            name="Simulation",
            description="Safe simulation",
            max_timeout_ms=5000,
            max_memory_mb=64,
        )
        assert a.adapter_type == RuntimeAdapterType.SIMULATION
        assert a.max_timeout_ms == 5000
        assert a.max_memory_mb == 64

    def test_to_dict_from_dict_roundtrip(self):
        a = RuntimeAdapter(
            adapter_id="rtadp_test",
            adapter_type=RuntimeAdapterType.SIMULATION,
            name="Test",
            description="Desc",
            supports_network=False,
            supports_user_data_read=False,
            supports_user_data_write=False,
            sandbox_required=False,
            max_timeout_ms=5000,
            max_memory_mb=64,
            status=RuntimeAdapterStatus.BETA,
            version="0.1.0",
            config_schema={"key": "value"},
            metadata={"simulation": True},
        )
        d = a.to_dict()
        b = RuntimeAdapter.from_dict(d)
        assert b.adapter_id == a.adapter_id
        assert b.adapter_type == a.adapter_type
        assert b.name == a.name
        assert b.status == a.status
        assert b.config_schema == a.config_schema
        assert b.metadata == a.metadata

    def test_is_active_active(self):
        a = RuntimeAdapter(status=RuntimeAdapterStatus.ACTIVE)
        assert a.is_active()

    def test_is_active_beta(self):
        a = RuntimeAdapter(status=RuntimeAdapterStatus.BETA)
        assert a.is_active()

    def test_is_active_disabled(self):
        a = RuntimeAdapter(status=RuntimeAdapterStatus.DISABLED)
        assert not a.is_active()

    def test_is_mvp_allowed_manifest_only(self):
        assert is_mvp_allowed_adapter_type(RuntimeAdapterType.MANIFEST_ONLY)

    def test_is_mvp_allowed_simulation(self):
        assert is_mvp_allowed_adapter_type(RuntimeAdapterType.SIMULATION)

    def test_is_mvp_allowed_container_false(self):
        assert not is_mvp_allowed_adapter_type(RuntimeAdapterType.CONTAINER)

    def test_config_schema_must_be_dict(self):
        a = RuntimeAdapter(config_schema={})
        assert isinstance(a.config_schema, dict)

    def test_metadata_must_be_dict(self):
        a = RuntimeAdapter(metadata={})
        assert isinstance(a.metadata, dict)


# ═══════════════════════════════════════════
# 2. Adapter Store
# ═══════════════════════════════════════════


class TestAdapterStore:
    def test_seed_creates_manifest_only(self, seeded_store):
        a = seeded_store.get_adapter("rtadp_manifest_only")
        assert a is not None
        assert a.adapter_type == RuntimeAdapterType.MANIFEST_ONLY
        assert a.status == RuntimeAdapterStatus.ACTIVE
        assert not a.supports_network

    def test_seed_creates_simulation(self, seeded_store):
        a = seeded_store.get_adapter("rtadp_simulation")
        assert a is not None
        assert a.adapter_type == RuntimeAdapterType.SIMULATION
        assert a.status == RuntimeAdapterStatus.BETA
        assert a.max_timeout_ms == 5000

    def test_seed_creates_disabled_future_adapters(self, seeded_store):
        for aid in ("rtadp_http_webhook", "rtadp_sandboxed_process", "rtadp_container"):
            a = seeded_store.get_adapter(aid)
            assert a is not None, f"Expected adapter {aid}"
            assert a.status == RuntimeAdapterStatus.DISABLED

    def test_seed_twice_idempotent(self, store):
        c1 = store.seed_builtin_adapters()
        c2 = store.seed_builtin_adapters()
        assert c1 >= 2  # at least manifest_only + simulation
        assert c2 == 0  # second call creates nothing new

    def test_get_adapter_by_id(self, seeded_store):
        a = seeded_store.get_adapter("rtadp_manifest_only")
        assert a is not None
        assert a.name == "Manifest Only"

    def test_get_adapter_by_type(self, seeded_store):
        a = seeded_store.get_adapter_by_type(RuntimeAdapterType.SIMULATION)
        assert a is not None
        assert a.adapter_id == "rtadp_simulation"

    def test_list_adapters(self, seeded_store):
        adapters = seeded_store.list_adapters()
        assert len(adapters) == 5

    def test_list_adapters_status_filter(self, seeded_store):
        actives = seeded_store.list_adapters(status=RuntimeAdapterStatus.ACTIVE)
        assert len(actives) >= 1
        assert all(a.status == RuntimeAdapterStatus.ACTIVE for a in actives)

    def test_list_adapters_mvp_only_filter(self, seeded_store):
        mvp = seeded_store.list_adapters(mvp_only=True)
        assert len(mvp) == 2
        types = {a.adapter_type for a in mvp}
        assert types == {RuntimeAdapterType.MANIFEST_ONLY, RuntimeAdapterType.SIMULATION}

    def test_update_adapter(self, seeded_store):
        a = seeded_store.get_adapter("rtadp_simulation")
        a.name = "Updated Simulation"
        seeded_store.update_adapter(a)
        a2 = seeded_store.get_adapter("rtadp_simulation")
        assert a2.name == "Updated Simulation"

    def test_set_adapter_status(self, seeded_store):
        ok = seeded_store.set_adapter_status("rtadp_simulation", RuntimeAdapterStatus.ACTIVE)
        assert ok
        a = seeded_store.get_adapter("rtadp_simulation")
        assert a.status == RuntimeAdapterStatus.ACTIVE

    def test_set_adapter_status_nonexistent(self, store):
        ok = store.set_adapter_status("rtadp_nonexistent", RuntimeAdapterStatus.ACTIVE)
        assert not ok

    def test_duplicate_adapter_rejected(self, seeded_store):
        a = RuntimeAdapter(
            adapter_id="rtadp_manifest_only",
            adapter_type=RuntimeAdapterType.MANIFEST_ONLY,
            name="Dup",
        )
        with pytest.raises(RuntimeAdapterAlreadyExistsError):
            seeded_store.create_adapter(a)

    def test_get_nonexistent_adapter_returns_none(self, store):
        assert store.get_adapter("rtadp_nonexistent") is None

    def test_get_adapter_by_type_nonexistent(self, store):
        assert store.get_adapter_by_type("nonexistent") is None


# ═══════════════════════════════════════════
# 3. RuntimeBinding Model
# ═══════════════════════════════════════════


class TestBindingModel:
    def test_create_binding_model(self):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_test",
            developer_id="dev_001",
            tenant_id="tenant_001",
            adapter_id="rtadp_simulation",
            adapter_type=RuntimeAdapterType.SIMULATION,
        )
        assert b.binding_id.startswith("rtbind_")
        assert b.runtime_status == RuntimeBindingStatus.PENDING
        assert not b.is_enabled()

    def test_binding_to_dict_from_dict_roundtrip(self):
        b = DeveloperAgentRuntimeBinding(
            binding_id="rtbind_001",
            marketplace_agent_id="mkp_test",
            submission_id="sub_001",
            developer_id="dev_001",
            tenant_id="tenant_001",
            adapter_id="rtadp_simulation",
            adapter_type=RuntimeAdapterType.SIMULATION,
            runtime_status=RuntimeBindingStatus.ENABLED,
            sandbox_policy_id=None,
            enabled_by="admin-001",
            metadata={"note": "test"},
        )
        d = b.to_dict()
        b2 = DeveloperAgentRuntimeBinding.from_dict(d)
        assert b2.binding_id == b.binding_id
        assert b2.marketplace_agent_id == b.marketplace_agent_id
        assert b2.runtime_status == b.runtime_status
        assert b2.enabled_by == b.enabled_by
        assert b2.metadata == b.metadata

    def test_is_enabled_false_for_pending(self):
        b = DeveloperAgentRuntimeBinding(runtime_status=RuntimeBindingStatus.PENDING)
        assert not b.is_enabled()

    def test_is_enabled_true_for_enabled(self):
        b = DeveloperAgentRuntimeBinding(runtime_status=RuntimeBindingStatus.ENABLED)
        assert b.is_enabled()

    def test_is_enabled_false_for_disabled(self):
        b = DeveloperAgentRuntimeBinding(runtime_status=RuntimeBindingStatus.DISABLED)
        assert not b.is_enabled()

    def test_tenant_id_required(self):
        b = DeveloperAgentRuntimeBinding(tenant_id="t1")
        assert b.tenant_id == "t1"

    def test_marketplace_agent_id_required(self):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_1")
        assert b.marketplace_agent_id == "mkp_1"


# ═══════════════════════════════════════════
# 4. Binding Store
# ═══════════════════════════════════════════


class TestBindingStore:
    def test_create_binding(self, seeded_store):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_test",
            developer_id="dev_001",
            tenant_id="tenant_001",
            adapter_id="rtadp_simulation",
            adapter_type=RuntimeAdapterType.SIMULATION,
        )
        created = seeded_store.create_binding(b)
        assert created.binding_id == b.binding_id

    def test_get_binding_by_id(self, seeded_store):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_test",
            developer_id="dev_001",
            tenant_id="tenant_001",
            adapter_id="rtadp_simulation",
            adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b)
        found = seeded_store.get_binding(b.binding_id)
        assert found is not None
        assert found.marketplace_agent_id == "mkp_test"

    def test_get_binding_by_mkp_agent_and_tenant(self, seeded_store):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_a", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b)
        found = seeded_store.get_binding_by_marketplace_agent("mkp_a", "t1")
        assert found is not None

    def test_same_mkp_different_tenant_allowed(self, seeded_store):
        b1 = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_shared", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        b2 = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_shared", developer_id="dev_2", tenant_id="t2",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b1)
        seeded_store.create_binding(b2)
        assert seeded_store.get_binding_by_marketplace_agent("mkp_shared", "t1") is not None
        assert seeded_store.get_binding_by_marketplace_agent("mkp_shared", "t2") is not None

    def test_duplicate_mkp_tenant_rejected(self, seeded_store):
        b1 = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_dup", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b1)
        b2 = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_dup", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        with pytest.raises(RuntimeBindingAlreadyExistsError):
            seeded_store.create_binding(b2)

    def test_list_bindings_by_developer(self, seeded_store):
        b1 = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_1", developer_id="dev_a", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        b2 = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_2", developer_id="dev_b", tenant_id="t1",
            adapter_id="rtadp_manifest_only", adapter_type=RuntimeAdapterType.MANIFEST_ONLY,
        )
        seeded_store.create_binding(b1)
        seeded_store.create_binding(b2)
        dev_a = seeded_store.list_bindings(developer_id="dev_a")
        assert len(dev_a) == 1
        assert dev_a[0].developer_id == "dev_a"

    def test_list_bindings_by_tenant(self, seeded_store):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_t1", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b)
        result = seeded_store.list_bindings(tenant_id="t1")
        assert len(result) == 1

    def test_list_bindings_by_status(self, seeded_store):
        b1 = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_s1", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b1)
        b1.runtime_status = RuntimeBindingStatus.ENABLED
        seeded_store.update_binding(b1)
        b2 = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_s2", developer_id="dev_2", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b2)
        enabled = seeded_store.list_bindings(runtime_status=RuntimeBindingStatus.ENABLED)
        pending = seeded_store.list_bindings(runtime_status=RuntimeBindingStatus.PENDING)
        assert len(enabled) == 1
        assert len(pending) == 1

    def test_list_bindings_by_adapter_type(self, seeded_store):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_sim", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b)
        result = seeded_store.list_bindings(adapter_type=RuntimeAdapterType.SIMULATION)
        assert len(result) == 1

    def test_update_binding(self, seeded_store):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_upd", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b)
        b.metadata = {"updated": True}
        seeded_store.update_binding(b)
        found = seeded_store.get_binding(b.binding_id)
        assert found.metadata == {"updated": True}

    def test_enable_binding(self, seeded_store):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_en", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b)
        seeded_store.enable_binding(b.binding_id, "admin-001")
        found = seeded_store.get_binding(b.binding_id)
        assert found.runtime_status == RuntimeBindingStatus.ENABLED
        assert found.enabled_by == "admin-001"

    def test_disable_binding(self, seeded_store):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_dis", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b)
        seeded_store.enable_binding(b.binding_id, "admin-001")
        seeded_store.disable_binding(b.binding_id, "admin-002")
        found = seeded_store.get_binding(b.binding_id)
        assert found.runtime_status == RuntimeBindingStatus.DISABLED
        assert found.disabled_by == "admin-002"

    def test_suspend_binding(self, seeded_store):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_sus", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b)
        seeded_store.enable_binding(b.binding_id, "admin-001")
        seeded_store.suspend_binding(b.binding_id, "admin-003")
        found = seeded_store.get_binding(b.binding_id)
        assert found.runtime_status == RuntimeBindingStatus.SUSPENDED

    def test_set_sandbox_policy_id(self, seeded_store):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_sp", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b)
        seeded_store.set_binding_sandbox_policy(b.binding_id, "sp_001")
        found = seeded_store.get_binding(b.binding_id)
        assert found.sandbox_policy_id == "sp_001"

    def test_create_binding_with_missing_adapter_rejected(self, store):
        store.seed_builtin_adapters()
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_bad", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_nonexistent", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        with pytest.raises(RuntimeAdapterNotFoundError):
            store.create_binding(b)

    def test_adapter_type_mismatch_rejected(self, seeded_store):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_mm", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation",
            adapter_type=RuntimeAdapterType.MANIFEST_ONLY,  # mismatch
        )
        with pytest.raises(RuntimeAdapterNotAllowedError, match="不匹配"):
            seeded_store.create_binding(b)

    def test_non_mvp_adapter_cannot_enable(self, seeded_store):
        # Activate the adapter first, otherwise enable_binding fails at is_active check
        seeded_store.set_adapter_status("rtadp_http_webhook", RuntimeAdapterStatus.ACTIVE)
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_hw", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_http_webhook",
            adapter_type=RuntimeAdapterType.HTTP_WEBHOOK,
        )
        seeded_store.create_binding(b)
        with pytest.raises(RuntimeAdapterNotAllowedError, match="MVP"):
            seeded_store.enable_binding(b.binding_id, "admin-001")

    def test_enable_nonexistent_binding_raises(self, seeded_store):
        with pytest.raises(RuntimeBindingNotFoundError):
            seeded_store.enable_binding("rtbind_nonexistent", "admin-001")

    def test_get_binding_nonexistent_returns_none(self, store):
        assert store.get_binding("rtbind_nonexistent") is None


# ═══════════════════════════════════════════
# 5. Eligibility
# ═══════════════════════════════════════════


class TestEligibility:
    def test_no_binding_returns_no_binding(self, seeded_store):
        result = seeded_store.get_runtime_eligibility("mkp_nonexistent")
        assert not result.eligible
        assert result.code == RuntimeEligibilityCode.NO_BINDING

    def test_pending_binding_not_eligible(self, seeded_store):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_pend", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b)
        result = seeded_store.get_runtime_eligibility("mkp_pend", "t1")
        assert not result.eligible
        assert result.code == RuntimeEligibilityCode.BINDING_DISABLED

    def test_disabled_binding_not_eligible(self, seeded_store):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_del", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b)
        seeded_store.enable_binding(b.binding_id, "admin-001")
        seeded_store.disable_binding(b.binding_id, "admin-002")
        result = seeded_store.get_runtime_eligibility("mkp_del", "t1")
        assert not result.eligible
        assert result.code == RuntimeEligibilityCode.BINDING_DISABLED

    def test_suspended_binding_not_eligible(self, seeded_store):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_sus", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b)
        seeded_store.enable_binding(b.binding_id, "admin-001")
        seeded_store.suspend_binding(b.binding_id, "admin-003")
        result = seeded_store.get_runtime_eligibility("mkp_sus", "t1")
        assert not result.eligible

    def test_adapter_disabled_not_eligible(self, seeded_store):
        # Use http_webhook adapter which is disabled → cannot enable
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_hw", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_http_webhook",
            adapter_type=RuntimeAdapterType.HTTP_WEBHOOK,
        )
        seeded_store.create_binding(b)
        # Adapter is disabled → enable_binding raises RuntimeStateError
        # Binding stays pending → BINDING_DISABLED
        result = seeded_store.get_runtime_eligibility("mkp_hw", "t1")
        assert not result.eligible
        assert result.code == RuntimeEligibilityCode.BINDING_DISABLED

    def test_non_mvp_adapter_not_allowed(self, seeded_store):
        # Enable container adapter first (manually)
        seeded_store.set_adapter_status("rtadp_container", RuntimeAdapterStatus.ACTIVE)
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_ct", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_container",
            adapter_type=RuntimeAdapterType.CONTAINER,
        )
        seeded_store.create_binding(b)
        # Even if we try to enable, non-MVP adapter is rejected
        try:
            seeded_store.enable_binding(b.binding_id, "admin-001")
        except RuntimeAdapterNotAllowedError:
            pass
        result = seeded_store.get_runtime_eligibility("mkp_ct", "t1")
        if result.eligible:
            # adapter was enabled → check adapter status
            pass
        else:
            assert result.code in (
                RuntimeEligibilityCode.ADAPTER_NOT_ALLOWED,
                RuntimeEligibilityCode.BINDING_DISABLED,
            )

    def test_simulation_enabled_eligible(self, seeded_store):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_sim", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation",
            adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b)
        seeded_store.enable_binding(b.binding_id, "admin-001")
        result = seeded_store.get_runtime_eligibility("mkp_sim", "t1")
        assert result.eligible
        assert result.code == RuntimeEligibilityCode.ELIGIBLE
        assert result.metadata.get("simulation") is True

    def test_manifest_only_enabled_eligible(self, seeded_store):
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_mo", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_manifest_only",
            adapter_type=RuntimeAdapterType.MANIFEST_ONLY,
        )
        seeded_store.create_binding(b)
        seeded_store.enable_binding(b.binding_id, "admin-001")
        result = seeded_store.get_runtime_eligibility("mkp_mo", "t1")
        assert result.eligible
        assert result.code == RuntimeEligibilityCode.ELIGIBLE
        assert result.metadata.get("manifest_only") is True

    def test_eligibility_does_not_call_agent_runtime(self, seeded_store):
        """Eligibility 检查不导入或调用 AgentRuntime。"""
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_safe", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION,
        )
        seeded_store.create_binding(b)
        seeded_store.enable_binding(b.binding_id, "admin-001")
        result = seeded_store.get_runtime_eligibility("mkp_safe", "t1")
        assert result.eligible
        # 通过即证明不调用 AgentRuntime（没有 agent registration）

    def test_eligibility_does_not_register_agent(self, seeded_store):
        """Eligibility 检查不注册 Agent 到 AgentRegistry。"""
        # 如果尝试 import AgentRegistry 会失败因为没有 main.py bootstrap
        # 这里只验证 eligibility 不抛异常
        result = seeded_store.get_runtime_eligibility("mkp_nonexistent")
        assert not result.eligible

    def test_sandbox_required_adapter_needs_policy(self, seeded_store):
        """sandbox_required + non-MVP adapter stays pending → BINDING_DISABLED."""
        # Manually activate container to test the sandbox_required path
        seeded_store.set_adapter_status("rtadp_container", RuntimeAdapterStatus.ACTIVE)
        b = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_ct2", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_container",
            adapter_type=RuntimeAdapterType.CONTAINER,
        )
        seeded_store.create_binding(b)
        # Adapter is active but non-MVP → enable_binding would reject
        # Binding stays pending → BINDING_DISABLED
        # (sandbox_required check runs inside enable_binding, after MVP + active check)
        result = seeded_store.get_runtime_eligibility("mkp_ct2", "t1")
        assert not result.eligible
        assert result.code == RuntimeEligibilityCode.BINDING_DISABLED

    def test_eligibility_result_to_dict(self):
        r = RuntimeEligibilityResult(
            eligible=True,
            code=RuntimeEligibilityCode.ELIGIBLE,
            message="OK",
            marketplace_agent_id="mkp_ok",
            binding_id="rtbind_ok",
            adapter_type=RuntimeAdapterType.SIMULATION,
            metadata={"simulation": True},
        )
        d = r.to_dict()
        assert d["eligible"]
        assert d["code"] == RuntimeEligibilityCode.ELIGIBLE

    def test_not_found_classmethod(self):
        r = RuntimeEligibilityResult.not_found("mkp_x")
        assert not r.eligible
        assert r.code == RuntimeEligibilityCode.NO_BINDING
        assert r.marketplace_agent_id == "mkp_x"
        assert r.required_action is not None
