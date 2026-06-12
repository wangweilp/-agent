"""Step 27 Production Migration Tests — metadata-only, no execution, no real connections."""
import os, pytest
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
from src.adapters.postgres_adapter import *
from src.adapters.redis_cache import *
from src.adapters.object_storage_adapter import *
from src.adapters.task_queue_adapter import *
from src.open_platform.import_hub import *
from src.open_platform.sync_hub import *
from src.open_platform.production_migration_subagent import *


# ═══════ PostgreSQL Adapter (12) ═══════

class TestPostgresAdapter:
    @pytest.fixture
    def adapter(self): return PostgresAdapter()

    def test_assess_readiness_returns_report(self, adapter):
        r = adapter.assess_readiness()
        assert isinstance(r, PostgresMigrationReport)
        assert r.status == PostgresMigrationStatus.MIGRATION_PLANNED

    def test_connection_not_active(self, adapter):
        assert not adapter.assess_readiness().connection_active

    def test_migration_not_ready(self, adapter):
        assert not adapter.assess_readiness().is_migration_ready()

    def test_report_is_connected_false(self, adapter):
        assert not adapter.assess_readiness().is_connected()

    def test_execution_blocked(self, adapter):
        r = adapter.assess_readiness()
        assert not r.execution_allowed; assert not r.runtime_enabled

    def test_metadata_only_true(self, adapter):
        assert adapter.assess_readiness().metadata_only == True

    def test_tables_defined(self, adapter):
        assert adapter.assess_readiness().tables_defined >= 7

    def test_target_pg_tables(self, adapter):
        assert "users" in adapter.assess_readiness().target_pg_tables

    def test_generate_migration_plan(self, adapter):
        plan = adapter.generate_migration_plan()
        assert plan["target"] == "PostgreSQL 16+"
        assert len(plan["migration_order"]) == 10
        assert plan["metadata_only"] == True

    def test_export_schema_snapshot(self, adapter):
        snap = adapter.export_schema_snapshot()
        assert "users" in snap
        assert "workspaces" in snap

    def test_no_execution_in_migration_plan(self, adapter):
        plan = adapter.generate_migration_plan()
        assert plan["execution_allowed"] == False

    def test_report_to_dict(self, adapter):
        d = adapter.assess_readiness().to_dict()
        assert "report_id" in d; assert d["connection_active"] == False


# ═══════ Redis Cache Adapter (10) ═══════

class TestRedisCache:
    @pytest.fixture
    def adapter(self): return RedisCacheAdapter()

    def test_assess_readiness_returns_report(self, adapter):
        r = adapter.assess_readiness()
        assert isinstance(r, RedisCacheReport)

    def test_connection_not_active(self, adapter):
        assert not adapter.assess_readiness().connection_active

    def test_cache_not_active(self, adapter):
        assert not adapter.assess_readiness().cache_active

    def test_report_is_connected_false(self, adapter):
        assert not adapter.assess_readiness().is_connected()
        assert not adapter.assess_readiness().is_cache_active()

    def test_execution_blocked(self, adapter):
        r = adapter.assess_readiness()
        assert not r.execution_allowed; assert not r.runtime_enabled

    def test_metadata_only_true(self, adapter):
        assert adapter.assess_readiness().metadata_only == True

    def test_keys_defined(self, adapter):
        assert adapter.assess_readiness().keys_defined >= 5

    def test_cache_key_patterns(self, adapter):
        patterns = adapter.get_cache_key_patterns()
        assert "memory" in patterns
        assert patterns["memory"]["ttl"] == 3600

    def test_export_config(self, adapter):
        cfg = adapter.export_config()
        assert cfg["connection_active"] == False; assert cfg["metadata_only"] == True

    def test_report_to_dict(self, adapter):
        d = adapter.assess_readiness().to_dict()
        assert d["cache_active"] == False


# ═══════ Object Storage Adapter (8) ═══════

class TestObjectStorage:
    @pytest.fixture
    def adapter(self): return ObjectStorageAdapter()

    def test_assess_readiness(self, adapter):
        r = adapter.assess_readiness()
        assert isinstance(r, ObjectStorageReport)
        assert r.status == ObjectStorageStatus.CONFIGURED

    def test_connection_not_active(self, adapter):
        assert not adapter.assess_readiness().connection_active
        assert not adapter.assess_readiness().storage_active

    def test_report_not_connected(self, adapter):
        r = adapter.assess_readiness()
        assert not r.is_connected(); assert not r.is_storage_active()

    def test_execution_blocked(self, adapter):
        r = adapter.assess_readiness()
        assert not r.execution_allowed; assert not r.runtime_enabled

    def test_metadata_only(self, adapter):
        assert adapter.assess_readiness().metadata_only == True

    def test_buckets_defined(self, adapter):
        assert adapter.assess_readiness().buckets_defined >= 4

    def test_bucket_config(self, adapter):
        cfg = adapter.get_bucket_config()
        assert "memory-attachments" in cfg

    def test_export_config(self, adapter):
        cfg = adapter.export_config()
        assert cfg["connection_active"] == False


# ═══════ Task Queue Adapter (12) ═══════

class TestTaskQueue:
    @pytest.fixture
    def adapter(self): return TaskQueueAdapter()

    def test_assess_readiness(self, adapter):
        r = adapter.assess_readiness()
        assert isinstance(r, TaskQueueReport)
        assert r.status == TaskQueueStatus.CONFIGURED

    def test_connection_not_active(self, adapter):
        r = adapter.assess_readiness()
        assert not r.connection_active; assert not r.queue_active

    def test_enqueue_blocked(self, adapter):
        assert not adapter.assess_readiness().enqueue_allowed

    def test_dispatch_blocked(self, adapter):
        assert not adapter.assess_readiness().dispatch_allowed

    def test_execution_blocked(self, adapter):
        r = adapter.assess_readiness()
        assert not r.execution_allowed

    def test_is_queue_active_false(self, adapter):
        assert not adapter.assess_readiness().is_queue_active()

    def test_metadata_only(self, adapter):
        assert adapter.assess_readiness().metadata_only == True

    def test_queues_defined(self, adapter):
        assert adapter.assess_readiness().queues_defined >= 5

    def test_task_definitions(self, adapter):
        r = adapter.assess_readiness()
        assert len(r.task_definitions) >= 5
        for t in r.task_definitions:
            assert t["enqueue_allowed"] == False
            assert t["dispatch_allowed"] == False

    def test_task_definition_is_enqueue_allowed_false(self):
        t = TaskDefinition(task_name="test")
        assert not t.is_enqueue_allowed(); assert not t.is_dispatch_allowed()

    def test_queue_config(self, adapter):
        assert "memory_write" in adapter.get_queue_config()

    def test_export_config(self, adapter):
        cfg = adapter.export_config()
        assert cfg["enqueue_allowed"] == False


# ═══════ Import Hub (10) ═══════

class TestImportHub:
    @pytest.fixture
    def hub(self): return ImportHub()

    def test_assess_readiness(self, hub):
        r = hub.assess_readiness()
        assert isinstance(r, ImportHubReport)
        assert r.import_active == False

    def test_import_blocked(self, hub):
        assert not hub.assess_readiness().import_allowed

    def test_execution_blocked(self, hub):
        r = hub.assess_readiness()
        assert not r.execution_allowed; assert not r.runtime_enabled

    def test_metadata_only(self, hub):
        assert hub.assess_readiness().metadata_only == True

    def test_sources_configured(self, hub):
        assert hub.assess_readiness().sources_configured >= 5

    def test_get_supported_sources(self, hub):
        srcs = hub.get_supported_sources()
        assert "notion" in srcs; assert "markdown" in srcs
        assert srcs["notion"]["import_allowed"] == False

    def test_import_source_defaults(self):
        s = ImportSource(source_type=ImportSourceType.PDF)
        assert not s.import_allowed; assert not s.is_import_allowed()
        assert s.metadata_only == True

    def test_all_sources_blocked(self, hub):
        for v in hub.get_supported_sources().values():
            assert v["import_allowed"] == False

    def test_report_to_dict(self, hub):
        d = hub.assess_readiness().to_dict()
        assert d["import_allowed"] == False

    def test_enum_types(self):
        assert ImportSourceType.NOTION == "notion"
        assert ImportStatus.CONFIGURED == "configured"


# ═══════ Sync Hub (10) ═══════

class TestSyncHub:
    @pytest.fixture
    def hub(self): return SyncHub()

    def test_assess_readiness(self, hub):
        r = hub.assess_readiness()
        assert isinstance(r, SyncHubReport)
        assert r.sync_active == False

    def test_sync_blocked(self, hub):
        assert not hub.assess_readiness().sync_allowed

    def test_execution_blocked(self, hub):
        r = hub.assess_readiness()
        assert not r.execution_allowed; assert not r.runtime_enabled

    def test_metadata_only(self, hub):
        assert hub.assess_readiness().metadata_only == True

    def test_entities_configured(self, hub):
        assert hub.assess_readiness().entities_configured >= 5

    def test_get_sync_entities(self, hub):
        es = hub.get_sync_entities()
        assert "memory" in es
        assert es["memory"]["sync_allowed"] == False

    def test_sync_entity_defaults(self):
        e = SyncEntity(entity_type=SyncEntityType.MEMORY)
        assert not e.sync_allowed; assert not e.is_sync_allowed()

    def test_all_entities_blocked(self, hub):
        for v in hub.get_sync_entities().values():
            assert v["sync_allowed"] == False
            assert v["network_allowed"] == False

    def test_report_to_dict(self, hub):
        d = hub.assess_readiness().to_dict()
        assert d["sync_allowed"] == False

    def test_enum_types(self):
        assert SyncEntityType.MEMORY == "memory"
        assert SyncMode.INCREMENTAL == "incremental"


# ═══════ Production Migration Sub-Agent (12) ═══════

class TestMigrationSubAgent:
    @pytest.fixture
    def agent(self): return ProductionMigrationSubAgent()

    def test_constructor_blocks_execution(self):
        with pytest.raises(ValueError):
            ProductionMigrationSubAgent(execution_allowed=True)
        with pytest.raises(ValueError):
            ProductionMigrationSubAgent(runtime_enabled=True)

    def test_constructor_defaults(self, agent):
        assert agent.metadata_only; assert not agent.execution_allowed
        assert not agent.runtime_enabled

    def test_run_assessment(self, agent):
        r = agent.run_migration_assessment()
        assert isinstance(r, ProductionMigrationReport)
        assert r.ready_for_step27_demo == True

    def test_assessment_not_production_ready(self, agent):
        r = agent.run_migration_assessment()
        assert r.ready_for_production == False

    def test_all_connections_blocked(self, agent):
        r = agent.run_migration_assessment()
        assert r.all_connections_blocked == True

    def test_all_execution_blocked(self, agent):
        r = agent.run_migration_assessment()
        assert r.all_execution_blocked == True

    def test_execution_flags(self, agent):
        r = agent.run_migration_assessment()
        assert not r.execution_allowed; assert not r.runtime_enabled
        assert not r.fixture_execution_allowed; assert r.metadata_only

    def test_six_components(self, agent):
        r = agent.run_migration_assessment()
        assert r.summary["total_components"] == 6
        assert r.summary["components_assessed"] == 6
        assert r.summary["connections_active"] == 0

    def test_report_to_dict(self, agent):
        d = agent.run_migration_assessment().to_dict()
        assert "postgres" in d; assert "redis" in d
        assert d["execution_allowed"] == False

    def test_generate_test_data(self, agent):
        data = agent.generate_usage_and_memory_test_data()
        assert len(data["test_users"]) == 3
        assert len(data["test_memories"]) == 3
        assert data["metadata_only"] == True
        assert data["execution_allowed"] == False

    def test_no_subprocess_import(self):
        import src.open_platform.production_migration_subagent as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_no_docker_import(self):
        import src.open_platform.production_migration_subagent as m
        assert "docker" not in str(dir(m)).lower()


# ═══════ Static Safety (8) ═══════

class TestSafety:
    _ADAPTERS = [
        "src.adapters.postgres_adapter",
        "src.adapters.redis_cache",
        "src.adapters.object_storage_adapter",
        "src.adapters.task_queue_adapter",
        "src.open_platform.import_hub",
        "src.open_platform.sync_hub",
        "src.open_platform.production_migration_subagent",
    ]

    def test_no_subprocess_imports(self):
        import importlib
        for mod_path in self._ADAPTERS:
            m = importlib.import_module(mod_path)
            assert "subprocess" not in str(dir(m)).lower(), f"{mod_path} should not import subprocess"

    def test_no_docker_imports(self):
        import importlib
        for mod_path in self._ADAPTERS:
            m = importlib.import_module(mod_path)
            assert "docker" not in str(dir(m)).lower(), f"{mod_path} should not import docker"

    def test_no_requests_imports(self):
        import importlib
        for mod_path in self._ADAPTERS:
            m = importlib.import_module(mod_path)
            assert "requests" not in str(dir(m)).lower(), f"{mod_path} should not import requests"

    def test_no_AgentRuntime_imports(self):
        import importlib
        for mod_path in self._ADAPTERS:
            m = importlib.import_module(mod_path)
            assert "AgentRuntime" not in str(dir(m)), f"{mod_path} should not import AgentRuntime"

    def test_gate_blocked(self):
        from src.open_platform.runtime_execution_gate import RuntimeExecutionGateResult
        assert not RuntimeExecutionGateResult().is_execution_allowed()

    def test_production_gate_no_runtime(self):
        from src.open_platform.production_sandbox_gate import ProductionSandboxGateResult
        g = ProductionSandboxGateResult()
        assert hasattr(g, "runtime_enabled") and g.runtime_enabled == False

    def test_kill_switch_not_active(self):
        from src.open_platform.runtime_kill_switch import RuntimeKillSwitchTrigger
        assert not RuntimeKillSwitchTrigger(policy_id="p").is_runtime_kill_active()

    def test_policy_enforcement_all_denied(self):
        from src.open_platform.policy_enforcement import PolicyEnforcementEngine
        decisions = PolicyEnforcementEngine().evaluate_all()
        assert all(d.allowed == False for d in decisions)
