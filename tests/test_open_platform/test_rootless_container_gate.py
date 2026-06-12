"""Rootless Container Gate Tests — Step 26-E: metadata-only, no container start, no Docker/Podman."""
import os, tempfile, pytest
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
from src.adapters.config import Settings
from src.adapters.rootless_container_gate_store import SQLiteRootlessContainerGateStore
from src.open_platform.rootless_container_gate import *
from src.open_platform.rootless_container_gate_service import RootlessContainerGateService


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "test_rtcls.db")
    yield p
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def store(settings, tmp_db_path):
    return SQLiteRootlessContainerGateStore(settings, db_path=tmp_db_path)


@pytest.fixture
def svc(store):
    return RootlessContainerGateService(store=store)


# ═══════ Domain (35) ═══════

class TestDomain:
    def test_policy_defaults_disabled(self):
        p = RootlessContainerPrototypePolicy()
        assert p.rootless_container_enabled == False
        assert p.container_start_enabled == False
        assert p.docker_enabled == False
        assert p.podman_enabled == False
        assert p.namespace_creation_enabled == False
        assert p.cgroup_enabled == False

    def test_policy_is_container_start_allowed_false(self):
        assert RootlessContainerPrototypePolicy().is_container_start_allowed() == False

    def test_policy_is_runtime_enabled_false(self):
        assert RootlessContainerPrototypePolicy().is_runtime_enabled() == False

    def test_policy_is_execution_allowed_false(self):
        assert RootlessContainerPrototypePolicy().is_execution_allowed() == False

    def test_policy_enabled_metadata_only(self):
        assert RootlessContainerPrototypePolicy().enabled_metadata_only == True

    def test_policy_id_prefix(self):
        assert RootlessContainerPrototypePolicy().policy_id.startswith("rtclspl_")

    def test_policy_to_dict_and_back(self):
        p = RootlessContainerPrototypePolicy(tenant_id="t1")
        d = p.to_dict(); p2 = RootlessContainerPrototypePolicy.from_dict(d)
        assert p2.tenant_id == "t1"; assert p2.docker_enabled == False

    def test_policy_metadata_roundtrip(self):
        p = RootlessContainerPrototypePolicy(metadata={"k": "v"})
        d = p.to_dict(); p2 = RootlessContainerPrototypePolicy.from_dict(d)
        assert p2.metadata == {"k": "v"}

    def test_policy_no_execution_flags(self):
        p = RootlessContainerPrototypePolicy()
        assert not p.mount_enabled and not p.network_enabled
        assert not p.package_execution_enabled and not p.third_party_execution_enabled

    def test_request_defaults_disabled(self):
        r = RootlessContainerPrototypeRequest()
        assert r.container_started == False; assert r.runtime_started == False
        assert r.namespace_created == False; assert r.cgroup_created == False
        assert r.mount_created == False; assert r.network_enabled == False
        assert r.package_executed == False; assert r.third_party_code_executed == False

    def test_request_is_container_start_allowed_false(self):
        assert RootlessContainerPrototypeRequest().is_container_start_allowed() == False

    def test_request_is_runtime_enabled_false(self):
        assert RootlessContainerPrototypeRequest().is_runtime_enabled() == False

    def test_request_is_execution_allowed_false(self):
        assert RootlessContainerPrototypeRequest().is_execution_allowed() == False

    def test_request_no_flags_all_true(self):
        r = RootlessContainerPrototypeRequest()
        assert r.no_container_started and r.no_runtime_started
        assert r.no_namespace_created and r.no_cgroup_created
        assert r.no_mount_created and r.no_network_enabled
        assert r.no_execution_performed and r.no_package_executed

    def test_request_id_prefix(self):
        assert RootlessContainerPrototypeRequest().request_id.startswith("rtclsreq_")

    def test_request_to_dict_and_back(self):
        r = RootlessContainerPrototypeRequest(tenant_id="t1", policy_snapshot={"a": 1})
        d = r.to_dict(); r2 = RootlessContainerPrototypeRequest.from_dict(d)
        assert r2.tenant_id == "t1"; assert r2.container_started == False

    def test_plan_defaults_no_container(self):
        p = RootlessContainerPrototypePlan(request_id="r1")
        assert p.is_container_start_allowed() == False
        assert p.is_runtime_enabled() == False
        assert p.is_execution_allowed() == False

    def test_plan_all_allowed_flags_false(self):
        p = RootlessContainerPrototypePlan(request_id="r1")
        assert not p.container_start_allowed and not p.runtime_enabled
        assert not p.network_allowed and not p.mount_allowed
        assert not p.package_execution_allowed and not p.third_party_execution_allowed

    def test_plan_id_prefix(self):
        assert RootlessContainerPrototypePlan(request_id="r1").plan_id.startswith("rtclsplan_")

    def test_plan_to_dict_and_back(self):
        p = RootlessContainerPrototypePlan(request_id="r1", tenant_id="t1")
        d = p.to_dict(); p2 = RootlessContainerPrototypePlan.from_dict(d)
        assert p2.tenant_id == "t1"; assert p2.is_container_start_allowed() == False

    def test_gate_all_allowed_flags_false(self):
        g = RootlessContainerGateResult(request_id="r1")
        assert g.container_start_allowed == False; assert g.runtime_enabled == False
        assert g.network_allowed == False; assert g.mount_allowed == False
        assert g.execution_allowed == False; assert g.third_party_execution_allowed == False
        assert g.package_execution_allowed == False

    def test_gate_ready_for_step26f_may_be_true(self):
        g = RootlessContainerGateResult(request_id="r1", ready_for_step26f=True)
        assert g.ready_for_step26f == True
        assert g.container_start_allowed == False  # still cannot start

    def test_gate_metadata_only_true(self):
        assert RootlessContainerGateResult(request_id="r1").metadata_only == True

    def test_gate_id_prefix(self):
        assert RootlessContainerGateResult(request_id="r1").gate_result_id.startswith("rtclsgate_")

    def test_audit_event_id(self):
        e = RootlessContainerAuditEvent()
        assert e.event_id.startswith("rtclsevt_")

    def test_audit_metadata_safe(self):
        d = RootlessContainerAuditEvent(event_type="t", message="ok").to_dict()
        assert "raw_key" not in str(d); assert "package_url" not in str(d).lower()

    def test_capability_assessment_id_prefix(self):
        a = RootlessContainerCapabilityAssessment(capability_type="t")
        assert a.assessment_id.startswith("rtclscap_")

    def test_capability_to_dict_and_back(self):
        a = RootlessContainerCapabilityAssessment(capability_type="ct", name="n",
                                                   blockers=["b1"], warnings=["w1"])
        d = a.to_dict(); a2 = RootlessContainerCapabilityAssessment.from_dict(d)
        assert a2.name == "n"; assert a2.blockers == ["b1"]

    def test_enum_no_container_started_status(self):
        vs = [v.value for v in RootlessContainerGateStatus.__members__.values()]
        for bad in ["container_starting", "container_started", "container_running",
                     "container_ready", "runtime_ready", "package_executed",
                     "third_party_executed", "sandbox_success"]:
            assert bad not in vs

    def test_enum_no_kill_in_decision(self):
        vs = [v.value for v in RootlessContainerGateDecision.__members__.values()]
        for bad in ["process_killed", "runtime_terminated", "container_started"]:
            assert bad not in vs

    def test_enum_audit_no_execution(self):
        vs = [v.value for v in RootlessContainerAuditEventType.__members__.values()]
        for bad in ["container_started", "package_executed", "docker_run"]:
            assert bad not in vs

    def test_capability_type_count(self):
        assert len(list(RootlessContainerCapabilityType.__members__.values())) >= 22

    # ── Capability Builder ──

    def test_capability_builder_has_22_items(self):
        caps = build_rootless_container_default_capabilities()
        assert len(caps) == 22

    def test_capability_builder_kill_switch_satisfied(self):
        caps = build_rootless_container_default_capabilities()
        ks = [c for c in caps if c.capability_type == RootlessContainerCapabilityType.KILL_SWITCH_REQUIRED]
        assert len(ks) == 1 and ks[0].status == RootlessContainerCapabilityStatus.SATISFIED

    def test_capability_builder_incident_store_satisfied(self):
        caps = build_rootless_container_default_capabilities()
        c = [c for c in caps if c.capability_type == RootlessContainerCapabilityType.INCIDENT_STORE_REQUIRED][0]
        assert c.status == RootlessContainerCapabilityStatus.SATISFIED

    def test_capability_builder_namespace_missing(self):
        caps = build_rootless_container_default_capabilities()
        c = [c for c in caps if c.capability_type == RootlessContainerCapabilityType.ROOTLESS_USER_NAMESPACE_REQUIRED][0]
        assert c.status == RootlessContainerCapabilityStatus.MISSING

    def test_capability_builder_seccomp_missing(self):
        caps = build_rootless_container_default_capabilities()
        c = [c for c in caps if c.capability_type == RootlessContainerCapabilityType.SECCOMP_PROFILE_REQUIRED][0]
        assert c.status == RootlessContainerCapabilityStatus.MISSING


# ═══════ Store (36) ═══════

_DANGEROUS = ["start_container", "run_container", "docker_run", "podman_run",
              "create_namespace", "create_cgroup", "mount_filesystem",
              "apply_seccomp", "apply_apparmor", "execute_package", "execute_entrypoint",
              "execute_third_party_code", "dispatch_job", "enqueue_job", "start_worker", "delete_request"]


class TestStore:
    def _p(self, **kw):
        return RootlessContainerPrototypePolicy(**kw)

    def _r(self, **kw):
        return RootlessContainerPrototypeRequest(**kw)

    def test_create_policy(self, store):
        p = store.create_policy(self._p(tenant_id="t1"))
        assert store.get_policy(p.policy_id) is not None

    def test_get_policy(self, store):
        p = store.create_policy(self._p(tenant_id="tget"))
        assert store.get_policy(p.policy_id).tenant_id == "tget"

    def test_list_policies_tenant(self, store):
        store.create_policy(self._p(tenant_id="tA"))
        store.create_policy(self._p(tenant_id="tB"))
        assert len(store.list_policies(tenant_id="tA")) == 1

    def test_update_policy(self, store):
        p = store.create_policy(self._p())
        p.docker_enabled = False; store.update_policy(p)
        assert store.get_policy(p.policy_id).docker_enabled == False

    def test_policy_disabled_flags_stored(self, store):
        p = store.create_policy(self._p())
        f = store.get_policy(p.policy_id)
        assert not f.docker_enabled and not f.podman_enabled and not f.container_start_enabled

    def test_create_request(self, store):
        r = store.create_request(self._r(tenant_id="t1"))
        assert store.get_request(r.request_id) is not None

    def test_get_request(self, store):
        r = store.create_request(self._r(tenant_id="tr"))
        assert store.get_request(r.request_id).tenant_id == "tr"

    def test_list_requests_tenant(self, store):
        store.create_request(self._r(tenant_id="tA"))
        store.create_request(self._r(tenant_id="tB"))
        assert len(store.list_requests(tenant_id="tA")) == 1

    def test_list_requests_status(self, store):
        store.create_request(self._r())
        assert len(store.list_requests(status=RootlessContainerGateStatus.DISABLED_BY_DEFAULT)) >= 1

    def test_update_request(self, store):
        r = store.create_request(self._r())
        r.status = RootlessContainerGateStatus.BLOCKED_DISABLED; store.update_request(r)
        assert store.get_request(r.request_id).status == RootlessContainerGateStatus.BLOCKED_DISABLED

    def test_set_request_status(self, store):
        r = store.create_request(self._r())
        store.set_request_status(r.request_id, RootlessContainerGateStatus.CANCELLED, "a", "reason")
        assert store.get_request(r.request_id).status == RootlessContainerGateStatus.CANCELLED

    def test_set_request_decision(self, store):
        r = store.create_request(self._r())
        store.set_request_decision(r.request_id, RootlessContainerGateDecision.FAIL_CLOSED, "a", "reason")
        assert store.get_request(r.request_id).decision == RootlessContainerGateDecision.FAIL_CLOSED

    def test_create_capability(self, store):
        a = store.create_capability_assessment(
            RootlessContainerCapabilityAssessment(capability_type="ct", name="n"))
        assert a.assessment_id is not None

    def test_list_capabilities(self, store):
        store.create_capability_assessment(
            RootlessContainerCapabilityAssessment(capability_type="ctA"))
        store.create_capability_assessment(
            RootlessContainerCapabilityAssessment(capability_type="ctB"))
        assert len(store.list_capability_assessments(capability_type="ctA")) >= 1

    def test_reserve_plan(self, store):
        p = store.reserve_plan_metadata_only(RootlessContainerPrototypePlan(request_id="r1", tenant_id="t1"))
        assert store.get_plan(p.plan_id) is not None

    def test_get_plan(self, store):
        p = store.reserve_plan_metadata_only(RootlessContainerPrototypePlan(request_id="rpg"))
        assert store.get_plan(p.plan_id).request_id == "rpg"

    def test_get_plan_by_request(self, store):
        store.reserve_plan_metadata_only(RootlessContainerPrototypePlan(request_id="rpb"))
        assert store.get_plan_by_request("rpb") is not None

    def test_plan_no_container_start(self, store):
        p = store.reserve_plan_metadata_only(RootlessContainerPrototypePlan(request_id="rpn"))
        assert store.get_plan(p.plan_id).is_container_start_allowed() == False

    def test_create_gate(self, store):
        g = store.create_gate_result(RootlessContainerGateResult(request_id="r1", tenant_id="t1"))
        assert store.get_gate_result(g.gate_result_id) is not None

    def test_get_gate(self, store):
        g = store.create_gate_result(RootlessContainerGateResult(request_id="rgt", tenant_id="t1"))
        assert store.get_gate_result(g.gate_result_id).request_id == "rgt"

    def test_get_gate_by_request(self, store):
        store.create_gate_result(RootlessContainerGateResult(request_id="rgb"))
        assert store.get_gate_result_by_request("rgb") is not None

    def test_gate_all_allowed_false(self, store):
        g = store.create_gate_result(RootlessContainerGateResult(request_id="rgf"))
        f = store.get_gate_result(g.gate_result_id)
        assert not f.container_start_allowed and not f.runtime_enabled
        assert not f.execution_allowed and not f.third_party_execution_allowed

    def test_audit_policy_create(self, store):
        p = store.create_policy(self._p())
        evts = store.list_audit_events(policy_id=p.policy_id)
        assert any(e.event_type == RootlessContainerAuditEventType.POLICY_CREATED for e in evts)

    def test_audit_request_create(self, store):
        r = store.create_request(self._r())
        evts = store.list_audit_events(request_id=r.request_id)
        assert any(e.event_type == RootlessContainerAuditEventType.REQUEST_CREATED for e in evts)

    def test_audit_gate(self, store):
        g = store.create_gate_result(RootlessContainerGateResult(request_id="rag"))
        evts = store.list_audit_events(request_id="rag")
        assert any(e.event_type == RootlessContainerAuditEventType.GATE_EVALUATED for e in evts)

    def test_audit_plan(self, store):
        p = store.reserve_plan_metadata_only(RootlessContainerPrototypePlan(request_id="rap"))
        evts = store.list_audit_events(request_id="rap")
        assert any(e.event_type == RootlessContainerAuditEventType.PLAN_RESERVED_METADATA_ONLY for e in evts)

    def test_json_rt_policy(self, store):
        p = store.create_policy(self._p(metadata={"k": "v"}))
        assert store.get_policy(p.policy_id).metadata == {"k": "v"}

    def test_json_rt_request(self, store):
        r = store.create_request(self._r(policy_snapshot={"a": 1}))
        assert store.get_request(r.request_id).policy_snapshot == {"a": 1}

    def test_bool_rt_policy(self, store):
        p = store.create_policy(self._p())
        f = store.get_policy(p.policy_id)
        assert f.enabled_metadata_only and not f.docker_enabled

    def test_bool_rt_request(self, store):
        r = store.create_request(self._r())
        f = store.get_request(r.request_id)
        assert not f.container_started and not f.package_executed
        assert f.no_container_started and f.no_execution_performed

    def test_count_requests(self, store):
        store.create_request(self._r(tenant_id="tc"))
        store.create_request(self._r(tenant_id="tc"))
        assert store.count_requests(tenant_id="tc") == 2

    def test_repeated_init(self, store, settings, tmp_db_path):
        store.create_policy(self._p()); store.flush()
        s2 = SQLiteRootlessContainerGateStore(settings, db_path=tmp_db_path)
        assert s2.count_requests() == 0

    def test_no_physical_delete(self, store):
        for m in ["delete_policy", "delete_request", "delete_plan", "delete_gate", "delete_audit"]:
            assert not hasattr(store, m) or not callable(getattr(store, m, None))

    def test_store_no_dangerous_methods(self, store):
        names = [n for n in dir(store) if not n.startswith("_")]
        for bad in _DANGEROUS:
            assert bad not in names, f"Store should not have {bad}"


# ═══════ Service (20) ═══════

_SVC_DANGEROUS = ["start_container", "run_container", "docker_run", "podman_run",
                  "create_namespace", "create_cgroup", "mount_filesystem",
                  "apply_seccomp", "apply_apparmor", "execute_package", "execute_entrypoint",
                  "execute_third_party_code", "dispatch_job", "enqueue_job", "start_worker"]


class TestService:
    def test_create_disabled_policy(self, svc, store):
        p = svc.create_disabled_rootless_container_policy(tenant_id="t1")
        assert p.rootless_container_enabled == False
        assert p.docker_enabled == False; assert p.podman_enabled == False
        assert p.container_start_enabled == False
        assert p.package_execution_enabled == False

    def test_create_disabled_policy_all_no(self, svc):
        p = svc.create_disabled_rootless_container_policy()
        assert not p.docker_enabled and not p.podman_enabled
        assert not p.namespace_creation_enabled and not p.cgroup_enabled
        assert not p.mount_enabled and not p.network_enabled
        assert not p.package_execution_enabled and not p.third_party_execution_enabled

    def test_create_policy_not_container_start(self, svc):
        p = svc.create_disabled_rootless_container_policy()
        assert p.is_container_start_allowed() == False

    def test_create_request_disabled(self, svc, store):
        p = svc.create_disabled_rootless_container_policy(tenant_id="t1")
        r = svc.create_prototype_request_metadata_only(p.policy_id, actor_id="a")
        assert r.status == RootlessContainerGateStatus.DISABLED_BY_DEFAULT
        assert r.decision == RootlessContainerGateDecision.BLOCKED_DISABLED

    def test_create_request_no_container(self, svc, store):
        p = svc.create_disabled_rootless_container_policy()
        r = svc.create_prototype_request_metadata_only(p.policy_id)
        assert r.container_started == False; assert r.runtime_started == False
        assert r.namespace_created == False; assert r.cgroup_created == False
        assert r.package_executed == False

    def test_create_request_no_flags(self, svc, store):
        p = svc.create_disabled_rootless_container_policy()
        r = svc.create_prototype_request_metadata_only(p.policy_id)
        assert r.no_container_started and r.no_runtime_started
        assert r.no_namespace_created and r.no_cgroup_created
        assert r.no_execution_performed and r.no_package_executed

    def test_evaluate_gate_returns_result(self, svc, store):
        p = svc.create_disabled_rootless_container_policy()
        r = svc.create_prototype_request_metadata_only(p.policy_id)
        g = svc.evaluate_rootless_container_gate(r.request_id)
        assert g.satisfied_count >= 0; assert g.missing_count >= 0
        assert g.ready_for_step26f == True

    def test_evaluate_gate_all_false(self, svc, store):
        p = svc.create_disabled_rootless_container_policy()
        r = svc.create_prototype_request_metadata_only(p.policy_id)
        g = svc.evaluate_rootless_container_gate(r.request_id)
        assert not g.container_start_allowed and not g.runtime_enabled
        assert not g.network_allowed and not g.mount_allowed
        assert not g.execution_allowed and not g.third_party_execution_allowed
        assert not g.package_execution_allowed

    def test_evaluate_gate_has_checks(self, svc, store):
        p = svc.create_disabled_rootless_container_policy()
        r = svc.create_prototype_request_metadata_only(p.policy_id)
        g = svc.evaluate_rootless_container_gate(r.request_id)
        assert len(g.checks) >= 22
        assert g.metadata_only == True

    def test_reserve_plan(self, svc, store):
        p = svc.create_disabled_rootless_container_policy()
        r = svc.create_prototype_request_metadata_only(p.policy_id)
        svc.evaluate_rootless_container_gate(r.request_id)
        pl = svc.reserve_prototype_plan_metadata_only(r.request_id)
        assert pl.is_container_start_allowed() == False
        assert pl.is_runtime_enabled() == False
        assert pl.is_execution_allowed() == False

    def test_reserve_plan_has_missing(self, svc, store):
        p = svc.create_disabled_rootless_container_policy()
        r = svc.create_prototype_request_metadata_only(p.policy_id)
        svc.evaluate_rootless_container_gate(r.request_id)
        pl = svc.reserve_prototype_plan_metadata_only(r.request_id)
        assert len(pl.missing_controls) > 0
        assert len(pl.required_controls) > 0

    def test_cancel_request(self, svc, store):
        p = svc.create_disabled_rootless_container_policy()
        r = svc.create_prototype_request_metadata_only(p.policy_id)
        c = svc.cancel_request(r.request_id, "a", "reason")
        assert c.status == RootlessContainerGateStatus.CANCELLED

    def test_expire_request(self, svc, store):
        p = svc.create_disabled_rootless_container_policy()
        r = svc.create_prototype_request_metadata_only(p.policy_id)
        e = svc.expire_request(r.request_id, "a", "reason")
        assert e.status == RootlessContainerGateStatus.EXPIRED

    def test_request_snapshots_stored(self, svc, store):
        p = svc.create_disabled_rootless_container_policy()
        r = svc.create_prototype_request_metadata_only(
            p.policy_id, policy_snapshot={"k": "v"},
            production_gate_snapshot={"pg": 1})
        got = store.get_request(r.request_id)
        assert got.policy_snapshot == {"k": "v"}
        assert got.production_gate_snapshot == {"pg": 1}

    def test_gate_always_blocks_container(self, svc, store):
        p = svc.create_disabled_rootless_container_policy()
        r = svc.create_prototype_request_metadata_only(p.policy_id)
        for _ in range(3):
            g = svc.evaluate_rootless_container_gate(r.request_id)
            assert g.container_start_allowed == False; assert g.execution_allowed == False

    def test_service_no_dangerous_methods(self, svc):
        names = [n for n in dir(svc) if not n.startswith("_")]
        for bad in _SVC_DANGEROUS:
            assert bad not in names

    def test_service_no_docker(self, svc):
        for m in ["docker_run", "podman_run", "start_container", "run_container"]:
            assert not hasattr(svc, m)

    def test_service_no_execute(self, svc):
        for m in ["execute_package", "execute_entrypoint", "execute_third_party_code"]:
            assert not hasattr(svc, m)

    def test_service_no_dispatch(self, svc):
        for m in ["dispatch_job", "enqueue_job", "start_worker"]:
            assert not hasattr(svc, m)


# ═══════ Safety Static Scans (15) ═══════

class TestSafety:
    _DANGEROUS = ["docker", "podman", "nerdctl", "containerd", "runc", "crun",
                  "subprocess", "socket", "requests", "httpx", "urllib.request",
                  "os.system", "eval(", "exec(", "open(",
                  "Path.exists", "Path.resolve", "mount", "unshare", "nsenter",
                  "cgroup", "seccomp", "apparmor_parser", "AgentRuntime", "AgentRegistry"]

    def test_domain_no_dangerous_imports(self):
        import src.open_platform.rootless_container_gate as m
        s = str(dir(m)).lower()
        for bad in self._DANGEROUS:
            assert bad.lower() not in s, f"Domain should not import {bad}"

    def test_domain_no_subprocess(self):
        import src.open_platform.rootless_container_gate as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_domain_no_docker(self):
        import src.open_platform.rootless_container_gate as m
        assert "docker" not in str(dir(m)).lower()

    def test_domain_no_requests(self):
        import src.open_platform.rootless_container_gate as m
        assert "requests" not in str(dir(m)).lower()

    def test_domain_no_AgentRuntime(self):
        import src.open_platform.rootless_container_gate as m
        assert "AgentRuntime" not in str(dir(m))

    def test_store_no_dangerous_imports(self):
        import src.adapters.rootless_container_gate_store as m
        s = str(dir(m)).lower()
        for bad in self._DANGEROUS:
            assert bad.lower() not in s, f"Store should not import {bad}"

    def test_store_no_subprocess(self):
        import src.adapters.rootless_container_gate_store as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_store_no_docker(self):
        import src.adapters.rootless_container_gate_store as m
        assert "docker" not in str(dir(m)).lower()

    def test_store_no_AgentRuntime(self):
        import src.adapters.rootless_container_gate_store as m
        assert "AgentRuntime" not in str(dir(m))

    def test_service_no_dangerous_imports(self):
        import src.open_platform.rootless_container_gate_service as m
        s = str(dir(m)).lower()
        for bad in self._DANGEROUS:
            assert bad.lower() not in s, f"Service should not import {bad}"

    def test_service_no_subprocess(self):
        import src.open_platform.rootless_container_gate_service as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_service_no_docker(self):
        import src.open_platform.rootless_container_gate_service as m
        assert "docker" not in str(dir(m)).lower()

    def test_service_no_AgentRuntime(self):
        import src.open_platform.rootless_container_gate_service as m
        assert "AgentRuntime" not in str(dir(m))

    def test_gate_blocked(self):
        from src.open_platform.runtime_execution_gate import RuntimeExecutionGateResult
        assert not RuntimeExecutionGateResult().is_execution_allowed()

    def test_production_sandbox_gate_no_runtime(self):
        from src.open_platform.production_sandbox_gate import ProductionSandboxGateResult
        g = ProductionSandboxGateResult()
        assert hasattr(g, "runtime_enabled") and g.runtime_enabled == False
