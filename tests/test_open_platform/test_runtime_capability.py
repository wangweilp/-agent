"""Runtime Capability Matrix Tests — Step 26-F.5: metadata registry, no execution."""
import os, tempfile, pytest
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
from src.adapters.config import Settings
from src.adapters.runtime_capability_store import SQLiteRuntimeCapabilityStore
from src.open_platform.runtime_capability import *
from src.open_platform.runtime_capability_service import RuntimeCapabilityService


@pytest.fixture
def settings(): return Settings()

@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp(); p = os.path.join(d, "test_rtcap.db"); yield p
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def store(settings, tmp_db_path):
    return SQLiteRuntimeCapabilityStore(settings, db_path=tmp_db_path)

@pytest.fixture
def svc(store):
    return RuntimeCapabilityService(store=store)

@pytest.fixture
def seeded_store(store):
    store.seed_default_capabilities(); return store

@pytest.fixture
def seeded_svc(seeded_store):
    return RuntimeCapabilityService(store=seeded_store)


# ═══════ Domain (20) ═══════

class TestDomain:
    def test_capability_defaults_blocked(self):
        c = RuntimeCapability(name="test", category="network")
        assert c.status == CapabilityStatus.BLOCKED
        assert c.execution_allowed == False
        assert c.fixture_execution_allowed == False
        assert c.runtime_enabled == False
        assert c.metadata_only == True

    def test_capability_id_prefix(self):
        assert RuntimeCapability(name="t").capability_id.startswith("rtcap_")

    def test_capability_to_dict_and_back(self):
        c = RuntimeCapability(name="n", category=CapabilityCategory.NETWORK,
                              status=CapabilityStatus.BLOCKED, reason="r")
        d = c.to_dict(); c2 = RuntimeCapability.from_dict(d)
        assert c2.name == "n"; assert c2.category == CapabilityCategory.NETWORK
        assert c2.execution_allowed == False

    def test_capability_metadata_roundtrip(self):
        c = RuntimeCapability(name="n", metadata={"k": "v"})
        d = c.to_dict(); c2 = RuntimeCapability.from_dict(d)
        assert c2.metadata == {"k": "v"}

    def test_capability_category_count(self):
        assert len(list(CapabilityCategory.__members__.values())) >= 10

    def test_capability_status_has_blocked(self):
        assert CapabilityStatus.BLOCKED == "blocked"

    def test_default_matrix_count(self):
        m = build_default_capability_matrix()
        assert len(m) == 20

    def test_default_matrix_all_blocked_or_planned(self):
        m = build_default_capability_matrix()
        for c in m:
            assert c.status in (CapabilityStatus.BLOCKED, CapabilityStatus.PLANNED,
                                CapabilityStatus.UNSUPPORTED)
            assert c.execution_allowed == False
            assert c.runtime_enabled == False
            assert c.metadata_only == True

    def test_default_matrix_blocked_count(self):
        m = build_default_capability_matrix()
        blocked = [c for c in m if c.status == CapabilityStatus.BLOCKED]
        planned = [c for c in m if c.status == CapabilityStatus.PLANNED]
        unsupported = [c for c in m if c.status == CapabilityStatus.UNSUPPORTED]
        assert len(blocked) >= 12  # majority blocked
        assert len(planned) >= 5
        assert len(unsupported) >= 1

    def test_default_matrix_all_metadata_only(self):
        m = build_default_capability_matrix()
        assert all(c.metadata_only for c in m)

    def test_default_matrix_no_execution(self):
        m = build_default_capability_matrix()
        assert not any(c.execution_allowed for c in m)
        assert not any(c.runtime_enabled for c in m)
        assert not any(c.fixture_execution_allowed for c in m)

    def test_matrix_network_blocked(self):
        m = build_default_capability_matrix()
        net = [c for c in m if c.category == CapabilityCategory.NETWORK]
        assert all(c.status == CapabilityStatus.BLOCKED for c in net)

    def test_matrix_container_planned(self):
        m = build_default_capability_matrix()
        ct = [c for c in m if c.name == "Rootless Container"]
        assert len(ct) == 1 and ct[0].status == CapabilityStatus.PLANNED

    def test_matrix_third_party_execution_blocked(self):
        m = build_default_capability_matrix()
        tpe = [c for c in m if c.name == "Third-Party Execution"]
        assert len(tpe) == 1 and tpe[0].status == CapabilityStatus.BLOCKED

    def test_enum_category_values(self):
        expected = {"network", "filesystem", "secrets", "subprocess", "memory",
                    "cpu", "container", "microvm", "ipc", "environment"}
        actual = set(v.value for v in CapabilityCategory.__members__.values())
        assert expected == actual

    def test_enum_status_values(self):
        expected = {"supported", "unsupported", "blocked", "planned", "experimental"}
        actual = set(v.value for v in CapabilityStatus.__members__.values())
        assert expected == actual

    def test_capability_source_policy(self):
        m = build_default_capability_matrix()
        with_policy = [c for c in m if c.source_policy]
        assert len(with_policy) >= 10

    def test_capability_source_step(self):
        m = build_default_capability_matrix()
        with_step = [c for c in m if c.source_step]
        assert len(with_step) >= 15

    def test_capability_requires_gate_flags(self):
        m = build_default_capability_matrix()
        with_gate = [c for c in m if c.requires_additional_gate]
        assert len(with_gate) >= 6  # runtime capabilities need gates


# ═══════ Store (20) ═══════

class TestStore:
    def _c(self, **kw):
        kw.setdefault("name", "test"); kw.setdefault("category", CapabilityCategory.NETWORK)
        return RuntimeCapability(**kw)

    def test_create_capability(self, store):
        c = store.create_capability(self._c())
        assert store.get_capability(c.capability_id) is not None

    def test_get_capability(self, store):
        c = store.create_capability(self._c(name="get_test"))
        assert store.get_capability(c.capability_id).name == "get_test"

    def test_list_all(self, store):
        store.create_capability(self._c(category=CapabilityCategory.NETWORK))
        store.create_capability(self._c(category=CapabilityCategory.CONTAINER))
        assert len(store.list_capabilities()) == 2

    def test_list_by_category(self, store):
        store.create_capability(self._c(category=CapabilityCategory.NETWORK))
        store.create_capability(self._c(category=CapabilityCategory.FILESYSTEM))
        assert len(store.list_capabilities(category=CapabilityCategory.NETWORK)) == 1

    def test_list_by_status(self, store):
        store.create_capability(self._c(status=CapabilityStatus.BLOCKED))
        store.create_capability(self._c(status=CapabilityStatus.PLANNED))
        assert len(store.list_capabilities(status=CapabilityStatus.BLOCKED)) == 1

    def test_update_capability(self, store):
        c = store.create_capability(self._c())
        c.status = CapabilityStatus.PLANNED; c.reason = "updated"
        store.update_capability(c)
        f = store.get_capability(c.capability_id)
        assert f.status == CapabilityStatus.PLANNED; assert f.reason == "updated"

    def test_execution_flags_stored_false(self, store):
        c = store.create_capability(self._c())
        f = store.get_capability(c.capability_id)
        assert f.execution_allowed == False; assert f.runtime_enabled == False
        assert f.metadata_only == True

    def test_metadata_json_roundtrip(self, store):
        c = store.create_capability(self._c(metadata={"k": "v"}))
        assert store.get_capability(c.capability_id).metadata == {"k": "v"}

    def test_seed_defaults(self, store):
        store.seed_default_capabilities()
        assert len(store.list_capabilities()) == 20

    def test_seed_idempotent(self, store):
        store.seed_default_capabilities()
        store.seed_default_capabilities()
        assert len(store.list_capabilities()) == 20  # not duplicated

    def test_export_matrix(self, store):
        store.seed_default_capabilities()
        exp = store.export_matrix()
        assert exp["total"] == 20
        assert "by_category" in exp
        assert "by_status" in exp
        assert exp["summary"]["execution_allowed_any"] == False
        assert exp["summary"]["runtime_enabled_any"] == False
        assert exp["summary"]["metadata_only_all"] == True
        assert "exported_at" in exp

    def test_seed_all_blocked_or_planned(self, store):
        store.seed_default_capabilities()
        for c in store.list_capabilities():
            assert c.status in (CapabilityStatus.BLOCKED, CapabilityStatus.PLANNED,
                                CapabilityStatus.UNSUPPORTED)

    def test_seed_no_execution_any(self, store):
        store.seed_default_capabilities()
        assert not any(c.execution_allowed for c in store.list_capabilities())
        assert not any(c.runtime_enabled for c in store.list_capabilities())

    def test_repeated_init(self, store, settings, tmp_db_path):
        store.seed_default_capabilities(); store.flush()
        s2 = SQLiteRuntimeCapabilityStore(settings, db_path=tmp_db_path)
        assert len(s2.list_capabilities()) == 20  # same db file, data persists

    def test_no_dangerous_methods(self, store):
        dangerous = ["start_container", "execute_package", "execute_entrypoint",
                     "dispatch_job", "enqueue_job", "start_worker", "download_package"]
        names = [n for n in dir(store) if not n.startswith("_")]
        for bad in dangerous: assert bad not in names

    def test_no_subprocess_import(self, store):
        import src.adapters.runtime_capability_store as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_no_docker_import(self, store):
        import src.adapters.runtime_capability_store as m
        assert "docker" not in str(dir(m)).lower()

    def test_no_requests_import(self, store):
        import src.adapters.runtime_capability_store as m
        assert "requests" not in str(dir(m)).lower()

    def test_no_AgentRuntime_import(self, store):
        import src.adapters.runtime_capability_store as m
        assert "AgentRuntime" not in str(dir(m))


# ═══════ Service (15) ═══════

class TestService:
    def test_list_capabilities(self, seeded_svc):
        caps = seeded_svc.list_capabilities()
        assert len(caps) == 20

    def test_list_by_category(self, seeded_svc):
        caps = seeded_svc.list_capabilities(category=CapabilityCategory.NETWORK)
        assert all(c.category == CapabilityCategory.NETWORK for c in caps)

    def test_list_by_status(self, seeded_svc):
        caps = seeded_svc.list_capabilities(status=CapabilityStatus.BLOCKED)
        assert all(c.status == CapabilityStatus.BLOCKED for c in caps)

    def test_get_capability(self, seeded_svc, seeded_store):
        all_caps = seeded_store.list_capabilities()
        c = seeded_svc.get_capability(all_caps[0].capability_id)
        assert c is not None

    def test_get_not_found(self, seeded_svc):
        with pytest.raises(RuntimeCapabilityNotFoundError):
            seeded_svc.get_capability("nonexistent")

    def test_update_status(self, seeded_svc, seeded_store):
        all_caps = seeded_store.list_capabilities()
        cid = all_caps[0].capability_id
        updated = seeded_svc.update_capability(cid, status=CapabilityStatus.PLANNED, reason="test update")
        assert updated.status == CapabilityStatus.PLANNED

    def test_update_execution_flags_stay_false(self, seeded_svc, seeded_store):
        all_caps = seeded_store.list_capabilities()
        cid = all_caps[0].capability_id
        updated = seeded_svc.update_capability(cid, status=CapabilityStatus.EXPERIMENTAL)
        assert updated.execution_allowed == False
        assert updated.runtime_enabled == False
        assert updated.metadata_only == True

    def test_export_matrix(self, seeded_svc):
        exp = seeded_svc.export_matrix()
        assert exp["total"] == 20
        assert exp["summary"]["execution_allowed_any"] == False
        assert exp["summary"]["runtime_enabled_any"] == False
        assert exp["summary"]["metadata_only_all"] == True

    def test_export_has_network_category(self, seeded_svc):
        exp = seeded_svc.export_matrix()
        assert CapabilityCategory.NETWORK.value in exp["by_category"]

    def test_export_has_blocked_status(self, seeded_svc):
        exp = seeded_svc.export_matrix()
        assert CapabilityStatus.BLOCKED.value in exp["by_status"]

    def test_seed_defaults(self, svc, store):
        svc.seed_defaults()
        assert len(store.list_capabilities()) == 20

    def test_service_no_dangerous_methods(self, svc):
        dangerous = ["start_container", "execute_package", "start_runtime",
                     "dispatch_job", "enqueue_job", "start_worker"]
        names = [n for n in dir(svc) if not n.startswith("_")]
        for bad in dangerous: assert bad not in names

    def test_service_no_subprocess_import(self):
        import src.open_platform.runtime_capability_service as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_service_no_docker_import(self):
        import src.open_platform.runtime_capability_service as m
        assert "docker" not in str(dir(m)).lower()

    def test_service_no_AgentRuntime_import(self):
        import src.open_platform.runtime_capability_service as m
        assert "AgentRuntime" not in str(dir(m))


# ═══════ Safety (5) ═══════

class TestSafety:
    def test_domain_no_subprocess(self):
        import src.open_platform.runtime_capability as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_domain_no_docker(self):
        import src.open_platform.runtime_capability as m
        assert "docker" not in str(dir(m)).lower()

    def test_domain_no_AgentRuntime(self):
        import src.open_platform.runtime_capability as m
        assert "AgentRuntime" not in str(dir(m))

    def test_gate_blocked(self):
        from src.open_platform.runtime_execution_gate import RuntimeExecutionGateResult
        assert not RuntimeExecutionGateResult().is_execution_allowed()

    def test_production_gate_no_runtime(self):
        from src.open_platform.production_sandbox_gate import ProductionSandboxGateResult
        g = ProductionSandboxGateResult()
        assert hasattr(g, "runtime_enabled") and g.runtime_enabled == False
