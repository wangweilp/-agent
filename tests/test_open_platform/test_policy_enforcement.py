"""Policy Enforcement Engine Tests — Step 26-G: all deny, no execution."""
import os, tempfile, pytest
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
from src.adapters.config import Settings
from src.adapters.policy_decision_store import SQLitePolicyDecisionStore
from src.open_platform.policy_enforcement import *
from src.open_platform.policy_enforcement_service import PolicyEnforcementService


@pytest.fixture
def settings(): return Settings()

@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp(); p = os.path.join(d, "test_poldec.db"); yield p
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def store(settings, tmp_db_path):
    return SQLitePolicyDecisionStore(settings, db_path=tmp_db_path)

@pytest.fixture
def svc(store):
    return PolicyEnforcementService(store=store)

@pytest.fixture
def engine():
    return PolicyEnforcementEngine()


# ═══════ Domain (25) ═══════

class TestDomain:
    def test_policy_decision_default_denied(self):
        d = PolicyDecision(capability_name="test")
        assert d.allowed == False; assert d.execution_allowed == False
        assert d.runtime_enabled == False; assert d.metadata_only == True

    def test_policy_decision_is_allowed_false(self):
        assert PolicyDecision(capability_name="test").is_allowed() == False

    def test_policy_decision_is_execution_allowed_false(self):
        assert PolicyDecision(capability_name="test").is_execution_allowed() == False

    def test_policy_decision_is_runtime_enabled_false(self):
        assert PolicyDecision(capability_name="test").is_runtime_enabled() == False

    def test_decision_to_dict_and_back(self):
        d = PolicyDecision(capability_name="net", request_type="network_egress",
                           capability_status="blocked", reason="test reason")
        d2 = PolicyDecision.from_dict(d.to_dict())
        assert d2.allowed == False and d2.capability_name == "net"

    def test_permission_request_to_dict(self):
        r = PermissionRequest(request_type="network_egress")
        assert r.to_dict()["request_type"] == "network_egress"

    def test_permission_request_id_prefix(self):
        assert PermissionRequest(request_type="t").request_id.startswith("pmreq_")

    def test_decision_id_prefix(self):
        assert PolicyDecision().decision_id.startswith("poldec_")

    def test_audit_event_id_prefix(self):
        assert PolicyEnforcementAuditEvent().event_id.startswith("penfevt_")

    def test_decision_status_enum(self):
        assert PolicyDecisionStatus.DENIED_BLOCKED == "denied_blocked"
        assert PolicyDecisionStatus.DENIED_PLANNED == "denied_planned"

    def test_permission_request_type_count(self):
        assert len(list(PermissionRequestType.__members__.values())) == 20

    def test_engine_evaluates_all_20(self):
        decisions = PolicyEnforcementEngine().evaluate_all()
        assert len(decisions) == 20

    def test_engine_all_decisions_denied(self, engine):
        decisions = engine.evaluate_all()
        assert all(d.allowed == False for d in decisions)

    def test_engine_all_execution_false(self, engine):
        decisions = engine.evaluate_all()
        assert all(d.execution_allowed == False for d in decisions)
        assert all(d.runtime_enabled == False for d in decisions)
        assert all(d.metadata_only == True for d in decisions)

    def test_engine_network_denied(self, engine):
        d = engine.evaluate(PermissionRequest(request_type="network_egress"))
        assert d.allowed == False and d.capability_status == "blocked"

    def test_engine_package_execution_denied(self, engine):
        d = engine.evaluate(PermissionRequest(request_type="package_execution"))
        assert d.allowed == False

    def test_engine_third_party_denied(self, engine):
        d = engine.evaluate(PermissionRequest(request_type="third_party_execution"))
        assert d.allowed == False

    def test_engine_container_start_denied(self, engine):
        d = engine.evaluate(PermissionRequest(request_type="container_start"))
        assert d.allowed == False

    def test_engine_microvm_start_denied(self, engine):
        d = engine.evaluate(PermissionRequest(request_type="microvm_start"))
        assert d.allowed == False

    def test_engine_planned_allowed_false(self, engine):
        for t in ["memory_limit", "cpu_limit", "rootless_container", "isolated_runtime", "os_isolation"]:
            d = engine.evaluate(PermissionRequest(request_type=t))
            assert d.allowed == False and d.capability_status == "planned"

    def test_engine_ipc_unsupported(self, engine):
        d = engine.evaluate(PermissionRequest(request_type="ipc"))
        assert d.allowed == False and d.capability_status == "unsupported"

    def test_engine_unknown_type_denied(self, engine):
        d = engine.evaluate(PermissionRequest(request_type="nonexistent"))
        assert d.allowed == False

    def test_engine_export_audit_report(self, engine):
        report = engine.export_audit_report()
        assert report["total"] == 20
        assert report["summary"]["allowed_any"] == False
        assert report["summary"]["all_denied"] == True
        assert report["summary"]["metadata_only_all"] == True

    def test_enum_request_type_values(self):
        vals = set(v.value for v in PermissionRequestType.__members__.values())
        assert "network_egress" in vals
        assert "third_party_execution" in vals
        assert "container_start" in vals


# ═══════ Audit Agent (10) ═══════

class TestAuditAgent:
    def test_constructor_blocks_execution(self):
        with pytest.raises(ValueError):
            PolicyEnforcementAuditSubAgent(metadata_only=False)

    def test_constructor_default(self):
        a = PolicyEnforcementAuditSubAgent()
        assert a.metadata_only == True

    def test_run_audit_total_20(self):
        report = PolicyEnforcementAuditSubAgent().run_audit()
        assert report["total_capabilities"] == 20

    def test_run_audit_all_denied(self):
        report = PolicyEnforcementAuditSubAgent().run_audit()
        assert report["all_denied"] == True

    def test_run_audit_all_execution_blocked(self):
        report = PolicyEnforcementAuditSubAgent().run_audit()
        assert report["all_execution_blocked"] == True

    def test_run_audit_all_runtime_disabled(self):
        report = PolicyEnforcementAuditSubAgent().run_audit()
        assert report["all_runtime_disabled"] == True

    def test_run_audit_all_metadata_only(self):
        report = PolicyEnforcementAuditSubAgent().run_audit()
        assert report["all_metadata_only"] == True

    def test_run_audit_counts(self):
        report = PolicyEnforcementAuditSubAgent().run_audit()
        assert report["blocked_count"] == 14
        assert report["planned_count"] == 5
        assert report["unsupported_count"] == 1

    def test_run_audit_has_enforcement_by_type(self):
        report = PolicyEnforcementAuditSubAgent().run_audit()
        assert "network_egress" in report["enforcement_by_type"]
        assert report["enforcement_by_type"]["network_egress"]["allowed"] == False

    def test_convenience_function(self):
        report = run_policy_audit()
        assert report["all_denied"] == True


# ═══════ Store (18) ═══════

class TestStore:
    def _d(self, **kw):
        kw.setdefault("request_type", "network_egress")
        kw.setdefault("capability_name", "test")
        return PolicyDecision(**kw)

    def test_create_decision(self, store):
        d = store.create_decision(self._d())
        assert store.get_decision(d.decision_id) is not None

    def test_get_decision(self, store):
        d = store.create_decision(self._d(request_type="filesystem_write"))
        assert store.get_decision(d.decision_id).request_type == "filesystem_write"

    def test_list_all(self, store):
        store.create_decision(self._d(request_type="network_egress"))
        store.create_decision(self._d(request_type="container_start"))
        assert len(store.list_decisions()) == 2

    def test_list_by_type(self, store):
        store.create_decision(self._d(request_type="network_egress"))
        store.create_decision(self._d(request_type="filesystem_write"))
        assert len(store.list_decisions(request_type="network_egress")) == 1

    def test_all_stored_denied(self, store):
        store.create_decision(self._d())
        d = store.get_decision(store.list_decisions()[0].decision_id)
        assert d.allowed == False; assert d.execution_allowed == False

    def test_export_decisions(self, store):
        store.seed_all_rules()
        exp = store.export_decisions()
        assert exp["total"] == 20
        assert exp["summary"]["allowed_any"] == False
        assert exp["summary"]["all_denied"] == True

    def test_seed_all_rules(self, store):
        store.seed_all_rules()
        assert len(store.list_decisions()) == 20

    def test_audit_event_created(self, store):
        d = store.create_decision(self._d())
        evts = store.list_audit_events()
        assert len(evts) >= 1
        assert any(e.decision_id == d.decision_id for e in evts)

    def test_repeated_init(self, store, settings, tmp_db_path):
        store.seed_all_rules(); store.flush()
        s2 = SQLitePolicyDecisionStore(settings, db_path=tmp_db_path)
        assert len(s2.list_decisions()) == 20

    def test_no_dangerous_methods(self, store):
        dangerous = ["start_container", "execute_package", "execute_entrypoint",
                     "dispatch_job", "enqueue_job", "start_worker"]
        names = [n for n in dir(store) if not n.startswith("_")]
        for bad in dangerous: assert bad not in names

    def test_no_subprocess(self):
        import src.adapters.policy_decision_store as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_no_docker(self):
        import src.adapters.policy_decision_store as m
        assert "docker" not in str(dir(m)).lower()

    def test_no_requests(self):
        import src.adapters.policy_decision_store as m
        assert "requests" not in str(dir(m)).lower()

    def test_no_AgentRuntime(self):
        import src.adapters.policy_decision_store as m
        assert "AgentRuntime" not in str(dir(m))

    def test_no_execution_allowed_in_stored(self, store):
        store.seed_all_rules()
        for d in store.list_decisions():
            assert d.allowed == False; assert d.execution_allowed == False


# ═══════ Service (12) ═══════

class TestService:
    def test_evaluate_single(self, svc, store):
        d = svc.evaluate("network_egress", "Network Egress", tenant_id="t1")
        assert d.allowed == False; assert d.capability_status == "blocked"

    def test_evaluate_all(self, svc, store):
        decisions = svc.evaluate_all()
        assert len(decisions) == 20; assert all(d.allowed == False for d in decisions)

    def test_get_decision(self, svc, store):
        d = svc.evaluate("network_egress")
        retrieved = svc.get_decision(d.decision_id)
        assert retrieved.request_type == "network_egress"

    def test_get_not_found(self, svc):
        with pytest.raises(PolicyDecisionNotFoundError):
            svc.get_decision("nonexistent")

    def test_list_decisions(self, svc, store):
        svc.evaluate_all()
        assert len(svc.list_decisions()) == 20

    def test_list_by_type(self, svc, store):
        svc.evaluate_all()
        filtered = svc.list_decisions(request_type="container_start")
        assert len(filtered) >= 1

    def test_export_decisions(self, svc, store):
        svc.evaluate_all()
        exp = svc.export_decisions()
        assert exp["summary"]["allowed_any"] == False

    def test_run_audit(self, svc):
        report = svc.run_audit()
        assert report["all_denied"] == True

    def test_service_no_dangerous(self, svc):
        dangerous = ["start_container", "execute_package", "start_runtime",
                     "dispatch_job", "enqueue_job", "start_worker"]
        names = [n for n in dir(svc) if not n.startswith("_")]
        for bad in dangerous: assert bad not in names

    def test_no_subprocess(self):
        import src.open_platform.policy_enforcement_service as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_no_docker(self):
        import src.open_platform.policy_enforcement_service as m
        assert "docker" not in str(dir(m)).lower()

    def test_no_AgentRuntime(self):
        import src.open_platform.policy_enforcement_service as m
        assert "AgentRuntime" not in str(dir(m))


# ═══════ Safety (5) ═══════

class TestSafety:
    def test_domain_no_subprocess(self):
        import src.open_platform.policy_enforcement as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_domain_no_docker(self):
        import src.open_platform.policy_enforcement as m
        assert "docker" not in str(dir(m)).lower()

    def test_domain_no_AgentRuntime(self):
        import src.open_platform.policy_enforcement as m
        assert "AgentRuntime" not in str(dir(m))

    def test_gate_blocked(self):
        from src.open_platform.runtime_execution_gate import RuntimeExecutionGateResult
        assert not RuntimeExecutionGateResult().is_execution_allowed()

    def test_production_gate_no_runtime(self):
        from src.open_platform.production_sandbox_gate import ProductionSandboxGateResult
        g = ProductionSandboxGateResult()
        assert hasattr(g, "runtime_enabled") and g.runtime_enabled == False
