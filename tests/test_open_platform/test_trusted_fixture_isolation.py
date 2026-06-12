"""Trusted Fixture Isolation Tests — Step 26-F: metadata-only gate, no runtime, no container."""
import os, tempfile, pytest
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
from src.adapters.config import Settings
from src.adapters.trusted_fixture_isolation_store import SQLiteTrustedFixtureIsolationStore
from src.open_platform.trusted_fixture_isolation import *
from src.open_platform.trusted_fixture_isolation_service import TrustedFixtureIsolationService


@pytest.fixture
def settings(): return Settings()

@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp(); p = os.path.join(d, "test_tfix.db"); yield p
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def store(settings, tmp_db_path):
    return SQLiteTrustedFixtureIsolationStore(settings, db_path=tmp_db_path)

@pytest.fixture
def svc(store):
    return TrustedFixtureIsolationService(store=store)


# ═══════ Domain (38) ═══════

class TestDomain:
    def test_policy_defaults_disabled(self):
        p = TrustedFixtureIsolationPolicy()
        assert not p.isolated_runtime_enabled and not p.container_start_enabled
        assert not p.microvm_start_enabled and not p.trusted_fixture_execution_enabled
        assert not p.third_party_execution_enabled and not p.package_execution_enabled

    def test_policy_is_isolated_runtime_enabled_false(self):
        assert TrustedFixtureIsolationPolicy().is_isolated_runtime_enabled() == False

    def test_policy_is_fixture_execution_allowed_false(self):
        assert TrustedFixtureIsolationPolicy().is_fixture_execution_allowed() == False

    def test_policy_is_third_party_execution_allowed_false(self):
        assert TrustedFixtureIsolationPolicy().is_third_party_execution_allowed() == False

    def test_policy_is_package_execution_allowed_false(self):
        assert TrustedFixtureIsolationPolicy().is_package_execution_allowed() == False

    def test_policy_enabled_metadata_only(self):
        assert TrustedFixtureIsolationPolicy().enabled_metadata_only == True

    def test_policy_all_sub_flags_false(self):
        p = TrustedFixtureIsolationPolicy()
        assert not p.entrypoint_execution_enabled and not p.network_enabled
        assert not p.filesystem_write_enabled and not p.secrets_enabled
        assert not p.subprocess_enabled and not p.dynamic_import_enabled and not p.eval_exec_enabled

    def test_policy_id(self):
        assert TrustedFixtureIsolationPolicy().policy_id.startswith("tfixpol_")

    def test_policy_to_dict_and_back(self):
        p = TrustedFixtureIsolationPolicy(tenant_id="t1")
        d = p.to_dict(); p2 = TrustedFixtureIsolationPolicy.from_dict(d)
        assert p2.tenant_id == "t1"; assert not p2.isolated_runtime_enabled

    def test_request_defaults_disabled(self):
        r = TrustedFixtureIsolationRequest()
        assert not r.isolated_runtime_started and not r.container_started
        assert not r.microvm_started and not r.fixture_executed_in_isolated_runtime
        assert not r.third_party_code_executed and not r.package_executed
        assert not r.network_used and not r.filesystem_written
        assert not r.secrets_read and not r.subprocess_used

    def test_request_is_fixture_execution_allowed_false(self):
        assert TrustedFixtureIsolationRequest().is_fixture_execution_allowed() == False

    def test_request_is_isolated_runtime_enabled_false(self):
        assert TrustedFixtureIsolationRequest().is_isolated_runtime_enabled() == False

    def test_request_is_third_party_execution_allowed_false(self):
        assert TrustedFixtureIsolationRequest().is_third_party_execution_allowed() == False

    def test_request_no_flags_all_true(self):
        r = TrustedFixtureIsolationRequest()
        assert r.no_isolated_runtime_started and r.no_container_started
        assert r.no_microvm_started and r.no_third_party_code_executed
        assert r.no_package_executed and r.no_entrypoint_executed
        assert r.no_network_used and r.no_filesystem_written and r.no_secrets_read

    def test_request_id(self):
        assert TrustedFixtureIsolationRequest().request_id.startswith("tfixreq_")

    def test_request_to_dict_and_back(self):
        r = TrustedFixtureIsolationRequest(tenant_id="t1", policy_snapshot={"a": 1})
        d = r.to_dict(); r2 = TrustedFixtureIsolationRequest.from_dict(d)
        assert r2.tenant_id == "t1"; assert not r2.container_started

    def test_plan_all_disabled(self):
        p = TrustedFixtureIsolationPlan(request_id="r1")
        assert not p.is_fixture_execution_allowed() and not p.is_runtime_enabled()
        assert not p.is_execution_allowed()

    def test_plan_ready_for_step26g_may_true(self):
        p = TrustedFixtureIsolationPlan(request_id="r1", ready_for_step26g=True)
        assert p.ready_for_step26g == True
        assert not p.isolated_runtime_enabled  # still disabled
        assert not p.fixture_execution_allowed

    def test_plan_all_allowed_false(self):
        p = TrustedFixtureIsolationPlan(request_id="r1")
        assert not p.container_start_allowed and not p.microvm_start_allowed
        assert not p.fixture_execution_allowed and not p.third_party_execution_allowed
        assert not p.package_execution_allowed and not p.network_allowed
        assert not p.filesystem_write_allowed and not p.secrets_allowed and not p.subprocess_allowed

    def test_plan_id(self):
        assert TrustedFixtureIsolationPlan(request_id="r1").plan_id.startswith("tfixplan_")

    def test_plan_to_dict_and_back(self):
        p = TrustedFixtureIsolationPlan(request_id="r1", tenant_id="t1")
        d = p.to_dict(); p2 = TrustedFixtureIsolationPlan.from_dict(d)
        assert p2.tenant_id == "t1"; assert not p2.is_runtime_enabled()

    def test_gate_all_allowed_false(self):
        g = TrustedFixtureIsolationGateResult(request_id="r1")
        assert not g.isolated_runtime_enabled and not g.container_start_allowed
        assert not g.fixture_execution_allowed and not g.third_party_execution_allowed
        assert not g.package_execution_allowed and not g.execution_allowed

    def test_gate_ready_for_step26g_may_true(self):
        g = TrustedFixtureIsolationGateResult(request_id="r1", ready_for_step26g=True)
        assert g.ready_for_step26g; assert not g.execution_allowed

    def test_gate_metadata_only(self):
        assert TrustedFixtureIsolationGateResult(request_id="r1").metadata_only == True

    def test_gate_id(self):
        assert TrustedFixtureIsolationGateResult(request_id="r1").gate_result_id.startswith("tfixgate_")

    def test_audit_event_id(self):
        e = TrustedFixtureIsolationAuditEvent(); assert e.event_id.startswith("tfixevt_")

    def test_audit_metadata_safe(self):
        d = TrustedFixtureIsolationAuditEvent(event_type="t", message="ok").to_dict()
        assert "raw_key" not in str(d); assert "package_url" not in str(d).lower()

    def test_requirement_id(self):
        assert TrustedFixtureIsolationRequirement(requirement_type="ct").requirement_id.startswith("tfixreq_")

    def test_requirement_to_dict_and_back(self):
        r = TrustedFixtureIsolationRequirement(requirement_type="ct", name="n", blockers=["b1"])
        d = r.to_dict(); r2 = TrustedFixtureIsolationRequirement.from_dict(d)
        assert r2.name == "n"; assert r2.blockers == ["b1"]

    def test_enum_no_runtime_started(self):
        vs = [v.value for v in TrustedFixtureIsolationStatus.__members__.values()]
        for bad in ["runtime_started", "container_started", "microvm_started",
                     "fixture_running_in_container", "package_executed",
                     "third_party_executed", "sandbox_success", "runtime_success"]:
            assert bad not in vs

    def test_enum_no_kill_in_decision(self):
        vs = [v.value for v in TrustedFixtureIsolationDecision.__members__.values()]
        for bad in ["process_killed", "runtime_terminated", "runtime_started"]:
            assert bad not in vs

    def test_enum_audit_no_execution(self):
        vs = [v.value for v in TrustedFixtureIsolationAuditEventType.__members__.values()]
        for bad in ["fixture_executed", "runtime_started", "container_started"]:
            assert bad not in vs

    def test_requirement_type_count(self):
        assert len(list(TrustedFixtureIsolationRequirementType.__members__.values())) >= 22

    # ── Requirement Builder ──

    def test_requirement_builder_has_22_items(self):
        r = build_trusted_fixture_isolation_default_requirements()
        assert len(r) == 22

    def test_requirement_builder_registry_satisfied(self):
        r = build_trusted_fixture_isolation_default_requirements()
        c = [x for x in r if x.requirement_type == TrustedFixtureIsolationRequirementType.TRUSTED_FIXTURE_REGISTRY_REQUIRED][0]
        assert c.status == TrustedFixtureIsolationRequirementStatus.SATISFIED

    def test_requirement_builder_builtin_satisfied(self):
        r = build_trusted_fixture_isolation_default_requirements()
        c = [x for x in r if x.requirement_type == TrustedFixtureIsolationRequirementType.BUILTIN_FIXTURE_ONLY_REQUIRED][0]
        assert c.status == TrustedFixtureIsolationRequirementStatus.SATISFIED

    def test_requirement_builder_kill_switch_satisfied(self):
        r = build_trusted_fixture_isolation_default_requirements()
        c = [x for x in r if x.requirement_type == TrustedFixtureIsolationRequirementType.KILL_SWITCH_REQUIRED][0]
        assert c.status == TrustedFixtureIsolationRequirementStatus.SATISFIED

    def test_requirement_builder_isolated_runtime_missing(self):
        r = build_trusted_fixture_isolation_default_requirements()
        c = [x for x in r if x.requirement_type == TrustedFixtureIsolationRequirementType.ISOLATED_RUNTIME_IMPLEMENTATION_MISSING][0]
        assert c.status == TrustedFixtureIsolationRequirementStatus.MISSING


# ═══════ Store (35) ═══════

_DANGEROUS = ["start_runtime", "start_container", "start_microvm", "run_fixture_in_container",
              "run_fixture_in_microvm", "execute_fixture", "execute_package", "execute_entrypoint",
              "execute_third_party_code", "dispatch_job", "enqueue_job", "start_worker",
              "register_agent", "delete_request"]


class TestStore:
    def _p(self, **kw): return TrustedFixtureIsolationPolicy(**kw)
    def _r(self, **kw): return TrustedFixtureIsolationRequest(**kw)

    def test_create_policy(self, store):
        p = store.create_policy(self._p(tenant_id="t1"))
        assert store.get_policy(p.policy_id) is not None

    def test_get_policy(self, store):
        p = store.create_policy(self._p(tenant_id="tget"))
        assert store.get_policy(p.policy_id).tenant_id == "tget"

    def test_list_policies_tenant(self, store):
        store.create_policy(self._p(tenant_id="tA")); store.create_policy(self._p(tenant_id="tB"))
        assert len(store.list_policies(tenant_id="tA")) == 1

    def test_update_policy(self, store):
        p = store.create_policy(self._p()); p.isolated_runtime_enabled = False
        store.update_policy(p); assert store.get_policy(p.policy_id).isolated_runtime_enabled == False

    def test_policy_disabled_flags_stored(self, store):
        p = store.create_policy(self._p()); f = store.get_policy(p.policy_id)
        assert not f.isolated_runtime_enabled and not f.container_start_enabled
        assert not f.third_party_execution_enabled

    def test_create_request(self, store):
        r = store.create_request(self._r(tenant_id="t1"))
        assert store.get_request(r.request_id) is not None

    def test_get_request(self, store):
        r = store.create_request(self._r(tenant_id="tr"))
        assert store.get_request(r.request_id).tenant_id == "tr"

    def test_list_requests_tenant(self, store):
        store.create_request(self._r(tenant_id="tA")); store.create_request(self._r(tenant_id="tB"))
        assert len(store.list_requests(tenant_id="tA")) == 1

    def test_list_requests_status(self, store):
        store.create_request(self._r())
        assert len(store.list_requests(status=TrustedFixtureIsolationStatus.DISABLED_BY_DEFAULT)) >= 1

    def test_update_request(self, store):
        r = store.create_request(self._r()); r.status = TrustedFixtureIsolationStatus.BLOCKED_DISABLED
        store.update_request(r)
        assert store.get_request(r.request_id).status == TrustedFixtureIsolationStatus.BLOCKED_DISABLED

    def test_set_status(self, store):
        r = store.create_request(self._r())
        store.set_request_status(r.request_id, TrustedFixtureIsolationStatus.CANCELLED, "a", "reason")
        assert store.get_request(r.request_id).status == TrustedFixtureIsolationStatus.CANCELLED

    def test_set_decision(self, store):
        r = store.create_request(self._r())
        store.set_request_decision(r.request_id, TrustedFixtureIsolationDecision.FAIL_CLOSED, "a", "reason")
        assert store.get_request(r.request_id).decision == TrustedFixtureIsolationDecision.FAIL_CLOSED

    def test_create_requirement(self, store):
        r = store.create_requirement(TrustedFixtureIsolationRequirement(requirement_type="ct", name="n"))
        assert r.requirement_id is not None

    def test_list_requirements(self, store):
        store.create_requirement(TrustedFixtureIsolationRequirement(requirement_type="ctA"))
        store.create_requirement(TrustedFixtureIsolationRequirement(requirement_type="ctB"))
        assert len(store.list_requirements(requirement_type="ctA")) >= 1

    def test_reserve_plan(self, store):
        p = store.reserve_plan_metadata_only(TrustedFixtureIsolationPlan(request_id="r1"))
        assert store.get_plan(p.plan_id) is not None

    def test_get_plan(self, store):
        p = store.reserve_plan_metadata_only(TrustedFixtureIsolationPlan(request_id="rpg"))
        assert store.get_plan(p.plan_id).request_id == "rpg"

    def test_get_plan_by_request(self, store):
        store.reserve_plan_metadata_only(TrustedFixtureIsolationPlan(request_id="rpb"))
        assert store.get_plan_by_request("rpb") is not None

    def test_plan_no_runtime(self, store):
        p = store.reserve_plan_metadata_only(TrustedFixtureIsolationPlan(request_id="rpn"))
        assert store.get_plan(p.plan_id).is_runtime_enabled() == False

    def test_create_gate(self, store):
        g = store.create_gate_result(TrustedFixtureIsolationGateResult(request_id="r1"))
        assert store.get_gate_result(g.gate_result_id) is not None

    def test_get_gate(self, store):
        g = store.create_gate_result(TrustedFixtureIsolationGateResult(request_id="rgt"))
        assert store.get_gate_result(g.gate_result_id).request_id == "rgt"

    def test_get_gate_by_request(self, store):
        store.create_gate_result(TrustedFixtureIsolationGateResult(request_id="rgb"))
        assert store.get_gate_result_by_request("rgb") is not None

    def test_gate_all_false(self, store):
        g = store.create_gate_result(TrustedFixtureIsolationGateResult(request_id="rgf"))
        f = store.get_gate_result(g.gate_result_id)
        assert not f.isolated_runtime_enabled and not f.execution_allowed
        assert not f.third_party_execution_allowed

    def test_audit_policy(self, store):
        p = store.create_policy(self._p())
        assert any(e.event_type == TrustedFixtureIsolationAuditEventType.POLICY_CREATED
                   for e in store.list_audit_events(policy_id=p.policy_id))

    def test_audit_request(self, store):
        r = store.create_request(self._r())
        assert any(e.event_type == TrustedFixtureIsolationAuditEventType.REQUEST_CREATED
                   for e in store.list_audit_events(request_id=r.request_id))

    def test_audit_gate(self, store):
        g = store.create_gate_result(TrustedFixtureIsolationGateResult(request_id="rag"))
        assert any(e.event_type == TrustedFixtureIsolationAuditEventType.GATE_EVALUATED
                   for e in store.list_audit_events(request_id="rag"))

    def test_audit_plan(self, store):
        p = store.reserve_plan_metadata_only(TrustedFixtureIsolationPlan(request_id="rap"))
        assert any(e.event_type == TrustedFixtureIsolationAuditEventType.PLAN_RESERVED_METADATA_ONLY
                   for e in store.list_audit_events(request_id="rap"))

    def test_json_rt_policy(self, store):
        p = store.create_policy(self._p(metadata={"k": "v"}))
        assert store.get_policy(p.policy_id).metadata == {"k": "v"}

    def test_json_rt_request(self, store):
        r = store.create_request(self._r(policy_snapshot={"a": 1}))
        assert store.get_request(r.request_id).policy_snapshot == {"a": 1}

    def test_bool_rt_policy(self, store):
        p = store.create_policy(self._p()); f = store.get_policy(p.policy_id)
        assert f.enabled_metadata_only and not f.isolated_runtime_enabled

    def test_bool_rt_request(self, store):
        r = store.create_request(self._r()); f = store.get_request(r.request_id)
        assert not f.isolated_runtime_started and not f.package_executed
        assert f.no_isolated_runtime_started and f.no_package_executed

    def test_count_requests(self, store):
        store.create_request(self._r(tenant_id="tc")); store.create_request(self._r(tenant_id="tc"))
        assert store.count_requests(tenant_id="tc") == 2

    def test_repeated_init(self, store, settings, tmp_db_path):
        store.create_policy(self._p()); store.flush()
        s2 = SQLiteTrustedFixtureIsolationStore(settings, db_path=tmp_db_path)
        assert s2.count_requests() == 0

    def test_no_delete(self, store):
        for m in ["delete_policy", "delete_request", "delete_plan", "delete_gate", "delete_audit"]:
            assert not hasattr(store, m) or not callable(getattr(store, m, None))

    def test_store_no_dangerous(self, store):
        names = [n for n in dir(store) if not n.startswith("_")]
        for bad in _DANGEROUS: assert bad not in names, f"Store should not have {bad}"


# ═══════ Service (22) ═══════

_SVC_DANGEROUS = ["start_runtime", "start_container", "start_microvm",
                  "run_fixture_in_container", "run_fixture_in_microvm",
                  "execute_fixture", "execute_package", "execute_entrypoint",
                  "execute_third_party_code", "dispatch_job", "enqueue_job",
                  "start_worker", "register_agent"]


class TestService:
    def test_create_disabled_policy(self, svc, store):
        p = svc.create_disabled_isolation_policy(tenant_id="t1")
        assert not p.isolated_runtime_enabled and not p.container_start_enabled
        assert not p.trusted_fixture_execution_enabled and not p.third_party_execution_enabled

    def test_create_policy_all_disabled(self, svc):
        p = svc.create_disabled_isolation_policy()
        assert not p.isolated_runtime_enabled and not p.microvm_start_enabled
        assert not p.network_enabled and not p.filesystem_write_enabled
        assert not p.secrets_enabled and not p.subprocess_enabled
        assert not p.dynamic_import_enabled and not p.eval_exec_enabled

    def test_create_policy_not_runtime(self, svc):
        assert svc.create_disabled_isolation_policy().is_isolated_runtime_enabled() == False

    def test_create_request_disabled(self, svc, store):
        p = svc.create_disabled_isolation_policy()
        r = svc.create_isolation_request_metadata_only(p.policy_id, actor_id="a")
        assert r.status == TrustedFixtureIsolationStatus.DISABLED_BY_DEFAULT
        assert r.decision == TrustedFixtureIsolationDecision.BLOCKED_DISABLED

    def test_create_request_no_runtime(self, svc, store):
        p = svc.create_disabled_isolation_policy()
        r = svc.create_isolation_request_metadata_only(p.policy_id)
        assert not r.isolated_runtime_started and not r.container_started
        assert not r.fixture_executed_in_isolated_runtime and not r.third_party_code_executed

    def test_create_request_no_flags(self, svc, store):
        p = svc.create_disabled_isolation_policy()
        r = svc.create_isolation_request_metadata_only(p.policy_id)
        assert r.no_isolated_runtime_started and r.no_container_started
        assert r.no_third_party_code_executed and r.no_package_executed
        assert r.no_network_used and r.no_secrets_read

    def test_evaluate_gate(self, svc, store):
        p = svc.create_disabled_isolation_policy()
        r = svc.create_isolation_request_metadata_only(p.policy_id)
        g = svc.evaluate_trusted_fixture_isolation_gate(r.request_id)
        assert g.satisfied_count >= 0; assert g.missing_count >= 0
        assert g.ready_for_step26g == True

    def test_evaluate_gate_all_false(self, svc, store):
        p = svc.create_disabled_isolation_policy()
        r = svc.create_isolation_request_metadata_only(p.policy_id)
        g = svc.evaluate_trusted_fixture_isolation_gate(r.request_id)
        assert not g.isolated_runtime_enabled and not g.container_start_allowed
        assert not g.fixture_execution_allowed and not g.third_party_execution_allowed
        assert not g.execution_allowed

    def test_evaluate_gate_checks(self, svc, store):
        p = svc.create_disabled_isolation_policy()
        r = svc.create_isolation_request_metadata_only(p.policy_id)
        g = svc.evaluate_trusted_fixture_isolation_gate(r.request_id)
        assert len(g.checks) >= 22; assert g.metadata_only == True

    def test_reserve_plan(self, svc, store):
        p = svc.create_disabled_isolation_policy()
        r = svc.create_isolation_request_metadata_only(p.policy_id)
        svc.evaluate_trusted_fixture_isolation_gate(r.request_id)
        pl = svc.reserve_isolation_plan_metadata_only(r.request_id)
        assert not pl.is_fixture_execution_allowed() and not pl.is_runtime_enabled()

    def test_reserve_plan_has_missing(self, svc, store):
        p = svc.create_disabled_isolation_policy()
        r = svc.create_isolation_request_metadata_only(p.policy_id)
        svc.evaluate_trusted_fixture_isolation_gate(r.request_id)
        pl = svc.reserve_isolation_plan_metadata_only(r.request_id)
        assert len(pl.missing_requirements) > 0
        assert len(pl.satisfied_requirements) > 0

    def test_reserve_plan_ready_for_step26g(self, svc, store):
        p = svc.create_disabled_isolation_policy()
        r = svc.create_isolation_request_metadata_only(p.policy_id)
        svc.evaluate_trusted_fixture_isolation_gate(r.request_id)
        pl = svc.reserve_isolation_plan_metadata_only(r.request_id)
        assert pl.ready_for_step26g == True
        assert not pl.isolated_runtime_enabled  # still cannot execute

    def test_cancel_request(self, svc, store):
        p = svc.create_disabled_isolation_policy()
        r = svc.create_isolation_request_metadata_only(p.policy_id)
        c = svc.cancel_request(r.request_id, "a", "reason")
        assert c.status == TrustedFixtureIsolationStatus.CANCELLED

    def test_expire_request(self, svc, store):
        p = svc.create_disabled_isolation_policy()
        r = svc.create_isolation_request_metadata_only(p.policy_id)
        e = svc.expire_request(r.request_id, "a", "reason")
        assert e.status == TrustedFixtureIsolationStatus.EXPIRED

    def test_snapshots_stored(self, svc, store):
        p = svc.create_disabled_isolation_policy()
        r = svc.create_isolation_request_metadata_only(
            p.policy_id, policy_snapshot={"k": "v"}, trusted_fixture_snapshot={"fid": 1})
        got = store.get_request(r.request_id)
        assert got.policy_snapshot == {"k": "v"}
        assert got.trusted_fixture_snapshot == {"fid": 1}

    def test_gate_always_blocks(self, svc, store):
        p = svc.create_disabled_isolation_policy()
        r = svc.create_isolation_request_metadata_only(p.policy_id)
        for _ in range(3):
            g = svc.evaluate_trusted_fixture_isolation_gate(r.request_id)
            assert not g.execution_allowed and not g.fixture_execution_allowed

    def test_service_no_dangerous(self, svc):
        names = [n for n in dir(svc) if not n.startswith("_")]
        for bad in _SVC_DANGEROUS: assert bad not in names

    def test_service_no_runtime(self, svc):
        for m in ["start_runtime", "start_container", "start_microvm"]:
            assert not hasattr(svc, m)

    def test_service_no_execute(self, svc):
        for m in ["execute_fixture", "execute_package", "execute_entrypoint", "execute_third_party_code"]:
            assert not hasattr(svc, m)

    def test_service_no_dispatch(self, svc):
        for m in ["dispatch_job", "enqueue_job", "start_worker", "register_agent"]:
            assert not hasattr(svc, m)


# ═══════ Safety (15) ═══════

class TestSafety:
    _DANGEROUS = ["docker", "podman", "nerdctl", "containerd", "runc", "crun",
                  "subprocess", "socket", "requests", "httpx", "urllib.request",
                  "os.system", "eval(", "exec(", "open(",
                  "importlib", "__import__", "AgentRuntime", "AgentRegistry"]

    def test_domain_no_dangerous(self):
        import src.open_platform.trusted_fixture_isolation as m
        s = str(dir(m)).lower()
        for bad in self._DANGEROUS: assert bad.lower() not in s

    def test_domain_no_subprocess(self):
        import src.open_platform.trusted_fixture_isolation as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_domain_no_docker(self):
        import src.open_platform.trusted_fixture_isolation as m
        assert "docker" not in str(dir(m)).lower()

    def test_domain_no_AgentRuntime(self):
        import src.open_platform.trusted_fixture_isolation as m
        assert "AgentRuntime" not in str(dir(m))

    def test_store_no_dangerous(self):
        import src.adapters.trusted_fixture_isolation_store as m
        s = str(dir(m)).lower()
        for bad in self._DANGEROUS: assert bad.lower() not in s

    def test_store_no_subprocess(self):
        import src.adapters.trusted_fixture_isolation_store as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_store_no_docker(self):
        import src.adapters.trusted_fixture_isolation_store as m
        assert "docker" not in str(dir(m)).lower()

    def test_store_no_AgentRuntime(self):
        import src.adapters.trusted_fixture_isolation_store as m
        assert "AgentRuntime" not in str(dir(m))

    def test_service_no_dangerous(self):
        import src.open_platform.trusted_fixture_isolation_service as m
        s = str(dir(m)).lower()
        for bad in self._DANGEROUS: assert bad.lower() not in s

    def test_service_no_subprocess(self):
        import src.open_platform.trusted_fixture_isolation_service as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_service_no_docker(self):
        import src.open_platform.trusted_fixture_isolation_service as m
        assert "docker" not in str(dir(m)).lower()

    def test_service_no_AgentRuntime(self):
        import src.open_platform.trusted_fixture_isolation_service as m
        assert "AgentRuntime" not in str(dir(m))

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
