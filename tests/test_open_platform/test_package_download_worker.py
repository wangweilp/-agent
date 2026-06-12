"""Package Download Worker Tests — Step 26-C: disabled-by-default, metadata-only."""
import os, tempfile, pytest
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
from datetime import datetime, timezone
from src.adapters.config import Settings
from src.adapters.package_download_worker_store import SQLitePackageDownloadWorkerStore
from src.open_platform.package_download_worker import *
from src.open_platform.package_download_worker_service import PackageDownloadWorkerService


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "test_pkgdlwk.db")
    yield p
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def store(settings, tmp_db_path):
    return SQLitePackageDownloadWorkerStore(settings, db_path=tmp_db_path)


@pytest.fixture
def svc(store):
    return PackageDownloadWorkerService(store=store)


# ═══════ Domain (30) ═══════

class TestDomain:
    def test_policy_defaults_worker_disabled(self):
        p = PackageDownloadWorkerPolicy()
        assert p.worker_enabled == False
        assert p.network_enabled == False
        assert p.download_enabled == False
        assert p.file_write_enabled == False
        assert p.extraction_enabled == False
        assert p.package_execution_enabled == False

    def test_policy_is_worker_enabled_false(self):
        p = PackageDownloadWorkerPolicy()
        assert p.is_worker_enabled() == False

    def test_policy_is_download_allowed_false(self):
        p = PackageDownloadWorkerPolicy()
        assert p.is_download_allowed() == False

    def test_policy_is_network_allowed_false(self):
        p = PackageDownloadWorkerPolicy()
        assert p.is_network_allowed() == False

    def test_policy_enabled_metadata_only(self):
        p = PackageDownloadWorkerPolicy()
        assert p.enabled_metadata_only == True

    def test_policy_id_prefix(self):
        assert PackageDownloadWorkerPolicy().policy_id.startswith("pkgwkpol_")

    def test_policy_to_dict_and_back(self):
        p = PackageDownloadWorkerPolicy(tenant_id="t1")
        d = p.to_dict()
        p2 = PackageDownloadWorkerPolicy.from_dict(d)
        assert p2.tenant_id == "t1"
        assert p2.worker_enabled == False

    def test_policy_metadata_roundtrip(self):
        p = PackageDownloadWorkerPolicy(metadata={"k": "v"})
        d = p.to_dict()
        p2 = PackageDownloadWorkerPolicy.from_dict(d)
        assert p2.metadata == {"k": "v"}

    def test_job_defaults_disabled(self):
        j = PackageDownloadWorkerJob()
        assert j.download_performed == False
        assert j.network_used == False
        assert j.file_written == False
        assert j.package_materialized == False
        assert j.package_executed == False
        assert j.entrypoint_executed == False
        assert j.worker_started == False
        assert j.job_dispatched == False

    def test_job_is_download_allowed_false(self):
        assert PackageDownloadWorkerJob().is_download_allowed() == False

    def test_job_is_execution_allowed_false(self):
        assert PackageDownloadWorkerJob().is_execution_allowed() == False

    def test_job_is_worker_start_allowed_false(self):
        assert PackageDownloadWorkerJob().is_worker_start_allowed() == False

    def test_job_no_flags_all_true(self):
        j = PackageDownloadWorkerJob()
        assert j.no_network_used and j.no_download_performed and j.no_file_written
        assert j.no_extraction_performed and j.no_execution_performed
        assert j.no_worker_started and j.no_dispatch_performed

    def test_job_id_prefix(self):
        assert PackageDownloadWorkerJob().job_id.startswith("pkgwkjob_")

    def test_job_to_dict_and_back(self):
        j = PackageDownloadWorkerJob(tenant_id="t1", source_snapshot={"a": 1})
        d = j.to_dict()
        j2 = PackageDownloadWorkerJob.from_dict(d)
        assert j2.tenant_id == "t1"
        assert j2.source_snapshot == {"a": 1}
        assert j2.download_performed == False

    def test_lease_defaults_inactive(self):
        l = PackageDownloadWorkerLease(job_id="j1")
        assert l.lease_active == False
        assert l.worker_started == False
        assert l.heartbeat_enabled == False
        assert l.download_allowed == False

    def test_lease_is_active_false(self):
        assert PackageDownloadWorkerLease(job_id="j1").is_active() == False

    def test_lease_is_download_allowed_false(self):
        assert PackageDownloadWorkerLease(job_id="j1").is_download_allowed() == False

    def test_lease_id_prefix(self):
        assert PackageDownloadWorkerLease(job_id="j1").lease_id.startswith("pkgwklease_")

    def test_lease_to_dict_and_back(self):
        l = PackageDownloadWorkerLease(job_id="j1", tenant_id="t1")
        d = l.to_dict()
        l2 = PackageDownloadWorkerLease.from_dict(d)
        assert l2.tenant_id == "t1"
        assert l2.lease_active == False

    def test_gate_defaults_all_blocked(self):
        g = PackageDownloadWorkerGateResult(job_id="j1")
        assert g.worker_start_allowed == False
        assert g.network_allowed == False
        assert g.download_allowed == False
        assert g.file_write_allowed == False
        assert g.execution_allowed == False

    def test_gate_metadata_only_true(self):
        assert PackageDownloadWorkerGateResult(job_id="j1").metadata_only == True

    def test_gate_id_prefix(self):
        assert PackageDownloadWorkerGateResult(job_id="j1").gate_result_id.startswith("pkgwkgate_")

    def test_gate_to_dict_and_back(self):
        g = PackageDownloadWorkerGateResult(job_id="j1", tenant_id="t1")
        d = g.to_dict()
        g2 = PackageDownloadWorkerGateResult.from_dict(d)
        assert g2.tenant_id == "t1"
        assert g2.download_allowed == False

    def test_audit_event_id(self):
        e = PackageDownloadWorkerAuditEvent()
        assert e.event_id.startswith("pkgwkevt_")

    def test_audit_event_metadata_safe(self):
        d = PackageDownloadWorkerAuditEvent(event_type="t", message="ok").to_dict()
        assert "raw_key" not in str(d)
        assert "package_url" not in str(d).lower()

    def test_enum_no_downloading(self):
        vs = [v.value for v in PackageDownloadWorkerStatus.__members__.values()]
        for bad in ["downloading", "downloaded", "fetched", "completed",
                     "worker_running", "worker_started", "download_success"]:
            assert bad not in vs

    def test_enum_no_kill_in_decision(self):
        vs = [v.value for v in PackageDownloadWorkerDecision.__members__.values()]
        for bad in ["process_killed", "runtime_terminated"]:
            assert bad not in vs

    def test_enum_audit_no_execution(self):
        vs = [v.value for v in PackageDownloadWorkerAuditEventType.__members__.values()]
        for bad in ["package_downloaded", "package_executed", "worker_started"]:
            assert bad not in vs


# ═══════ Store (41) ═══════

_DANGEROUS = ["start_worker", "run_worker", "download_package", "fetch_package",
              "write_file", "materialize_package", "execute_package", "execute_entrypoint",
              "dispatch_job", "enqueue_job", "heartbeat", "delete_job",
              "start_download", "run_download", "real_download"]


class TestStore:
    def _p(self, **kw):
        return PackageDownloadWorkerPolicy(**kw)

    def _j(self, **kw):
        return PackageDownloadWorkerJob(**kw)

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

    def test_list_policies_scope(self, store):
        store.create_policy(self._p(scope=PackageDownloadWorkerScope.GLOBAL))
        assert len(store.list_policies(scope=PackageDownloadWorkerScope.GLOBAL)) >= 1

    def test_update_policy(self, store):
        p = store.create_policy(self._p())
        p.worker_enabled = False
        store.update_policy(p)
        assert store.get_policy(p.policy_id).worker_enabled == False

    def test_policy_worker_enabled_stored_false(self, store):
        p = store.create_policy(self._p())
        assert store.get_policy(p.policy_id).worker_enabled == False
        assert store.get_policy(p.policy_id).download_enabled == False

    def test_create_job(self, store):
        j = store.create_job(self._j(tenant_id="t1"))
        assert store.get_job(j.job_id) is not None

    def test_get_job(self, store):
        j = store.create_job(self._j(tenant_id="tj"))
        assert store.get_job(j.job_id).tenant_id == "tj"

    def test_list_jobs_tenant(self, store):
        store.create_job(self._j(tenant_id="tA"))
        store.create_job(self._j(tenant_id="tB"))
        assert len(store.list_jobs(tenant_id="tA")) == 1

    def test_list_jobs_status(self, store):
        store.create_job(self._j())  # default disabled_by_default
        assert len(store.list_jobs(status=PackageDownloadWorkerStatus.DISABLED_BY_DEFAULT)) >= 1

    def test_update_job(self, store):
        j = store.create_job(self._j())
        j.status = PackageDownloadWorkerStatus.JOB_BLOCKED
        store.update_job(j)
        assert store.get_job(j.job_id).status == PackageDownloadWorkerStatus.JOB_BLOCKED

    def test_set_job_status(self, store):
        j = store.create_job(self._j())
        store.set_job_status(j.job_id, PackageDownloadWorkerStatus.CANCELLED, "a", "reason")
        assert store.get_job(j.job_id).status == PackageDownloadWorkerStatus.CANCELLED

    def test_set_job_decision(self, store):
        j = store.create_job(self._j())
        store.set_job_decision(j.job_id, PackageDownloadWorkerDecision.FAIL_CLOSED, "a", "reason")
        assert store.get_job(j.job_id).decision == PackageDownloadWorkerDecision.FAIL_CLOSED

    def test_reserve_lease(self, store):
        l = PackageDownloadWorkerLease(job_id="j1", tenant_id="t1")
        r = store.reserve_lease_metadata_only(l)
        assert store.get_lease(r.lease_id) is not None

    def test_get_lease(self, store):
        l = store.reserve_lease_metadata_only(PackageDownloadWorkerLease(job_id="j1"))
        assert store.get_lease(l.lease_id).job_id == "j1"

    def test_get_lease_by_job(self, store):
        store.reserve_lease_metadata_only(PackageDownloadWorkerLease(job_id="jlby"))
        assert store.get_lease_by_job("jlby") is not None

    def test_release_lease(self, store):
        l = store.reserve_lease_metadata_only(PackageDownloadWorkerLease(job_id="jrel"))
        r = store.release_lease_metadata_only(l.lease_id, "admin", "ok")
        assert r.status == PackageDownloadWorkerStatus.RELEASED_METADATA_ONLY

    def test_lease_inactive_after_reserve(self, store):
        l = store.reserve_lease_metadata_only(PackageDownloadWorkerLease(job_id="jina"))
        assert store.get_lease(l.lease_id).lease_active == False
        assert not store.get_lease(l.lease_id).is_active()

    def test_create_gate(self, store):
        g = store.create_gate_result(PackageDownloadWorkerGateResult(job_id="j1", tenant_id="t1"))
        assert store.get_gate_result(g.gate_result_id) is not None

    def test_get_gate(self, store):
        g = store.create_gate_result(PackageDownloadWorkerGateResult(job_id="jgt", tenant_id="t1"))
        assert store.get_gate_result(g.gate_result_id).job_id == "jgt"

    def test_get_gate_by_job(self, store):
        store.create_gate_result(PackageDownloadWorkerGateResult(job_id="jgby"))
        assert store.get_gate_result_by_job("jgby") is not None

    def test_gate_allowed_all_false(self, store):
        g = store.create_gate_result(PackageDownloadWorkerGateResult(job_id="jgf"))
        assert store.get_gate_result(g.gate_result_id).download_allowed == False
        assert store.get_gate_result(g.gate_result_id).worker_start_allowed == False

    def test_audit_policy_create(self, store):
        p = store.create_policy(self._p())
        evts = store.list_audit_events(policy_id=p.policy_id)
        assert any(e.event_type == PackageDownloadWorkerAuditEventType.WORKER_POLICY_CREATED
                   for e in evts)

    def test_audit_job_create(self, store):
        j = store.create_job(self._j())
        evts = store.list_audit_events(job_id=j.job_id)
        assert any(e.event_type == PackageDownloadWorkerAuditEventType.DOWNLOAD_JOB_CREATED
                   for e in evts)

    def test_audit_gate(self, store):
        g = store.create_gate_result(PackageDownloadWorkerGateResult(job_id="jaudg"))
        evts = store.list_audit_events(job_id="jaudg")
        assert any(e.event_type == PackageDownloadWorkerAuditEventType.GATE_EVALUATED
                   for e in evts)

    def test_audit_lease(self, store):
        l = store.reserve_lease_metadata_only(PackageDownloadWorkerLease(job_id="jaudl"))
        evts = store.list_audit_events(job_id="jaudl")
        assert any(e.event_type == PackageDownloadWorkerAuditEventType.LEASE_RESERVED_METADATA_ONLY
                   for e in evts)

    def test_json_rt_policy(self, store):
        p = store.create_policy(self._p(metadata={"k": "v"}))
        assert store.get_policy(p.policy_id).metadata == {"k": "v"}

    def test_json_rt_job(self, store):
        j = store.create_job(self._j(source_snapshot={"a": 1}))
        assert store.get_job(j.job_id).source_snapshot == {"a": 1}

    def test_bool_rt_policy(self, store):
        p = store.create_policy(self._p())
        f = store.get_policy(p.policy_id)
        assert f.enabled_metadata_only and not f.worker_enabled

    def test_bool_rt_job(self, store):
        j = store.create_job(self._j())
        f = store.get_job(j.job_id)
        assert not f.download_performed and not f.network_used
        assert f.no_network_used and f.no_download_performed

    def test_count_jobs(self, store):
        store.create_job(self._j(tenant_id="tc"))
        store.create_job(self._j(tenant_id="tc"))
        assert store.count_jobs(tenant_id="tc") == 2

    def test_repeated_init(self, store, settings, tmp_db_path):
        store.create_policy(self._p())
        store.flush()
        s2 = SQLitePackageDownloadWorkerStore(settings, db_path=tmp_db_path)
        assert s2.count_jobs() == 0

    def test_no_physical_delete(self, store):
        for m in ["delete_policy", "delete_job", "delete_lease", "delete_gate", "delete_audit"]:
            assert not hasattr(store, m) or not callable(getattr(store, m, None))

    def test_store_no_dangerous_methods(self, store):
        names = [n for n in dir(store) if not n.startswith("_")]
        for bad in _DANGEROUS:
            assert bad not in names, f"Store should not have {bad}"

    def test_store_no_start_worker(self, store):
        assert not hasattr(store, "start_worker")

    def test_store_no_download_package(self, store):
        assert not hasattr(store, "download_package")

    def test_store_no_execute_package(self, store):
        assert not hasattr(store, "execute_package")

    def test_store_no_enqueue_job(self, store):
        assert not hasattr(store, "enqueue_job")

    def test_store_no_dispatch_job(self, store):
        assert not hasattr(store, "dispatch_job")


# ═══════ Service (26) ═══════

_SVC_DANGEROUS = ["start_worker", "run_worker", "download_package", "fetch_package",
                  "write_file", "materialize_package", "execute_package", "execute_entrypoint",
                  "dispatch_job", "enqueue_job", "heartbeat"]


class TestService:
    def test_create_disabled_policy(self, svc, store):
        p = svc.create_disabled_worker_policy(tenant_id="t1")
        assert p.worker_enabled == False
        assert p.download_enabled == False
        assert p.network_enabled == False
        assert p.package_execution_enabled == False

    def test_create_disabled_policy_all_no(self, svc):
        p = svc.create_disabled_worker_policy()
        assert not p.worker_enabled and not p.download_enabled and not p.network_enabled
        assert not p.file_write_enabled and not p.extraction_enabled and not p.package_execution_enabled

    def test_create_disabled_policy_not_worker_enabled(self, svc):
        p = svc.create_disabled_worker_policy()
        assert p.is_worker_enabled() == False

    def test_create_download_job_disabled(self, svc, store):
        p = svc.create_disabled_worker_policy(tenant_id="t1")
        j = svc.create_download_job_metadata_only(p.policy_id, actor_id="a")
        assert j.status == PackageDownloadWorkerStatus.DISABLED_BY_DEFAULT
        assert j.decision == PackageDownloadWorkerDecision.BLOCKED_DISABLED

    def test_create_download_job_no_download(self, svc, store):
        p = svc.create_disabled_worker_policy()
        j = svc.create_download_job_metadata_only(p.policy_id)
        assert j.download_performed == False
        assert j.network_used == False
        assert j.file_written == False
        assert j.package_executed == False
        assert j.worker_started == False

    def test_create_download_job_no_flags(self, svc, store):
        p = svc.create_disabled_worker_policy()
        j = svc.create_download_job_metadata_only(p.policy_id)
        assert j.no_download_performed and j.no_network_used and j.no_file_written
        assert j.no_execution_performed and j.no_worker_started and j.no_dispatch_performed

    def test_evaluate_gate_blocked(self, svc, store):
        p = svc.create_disabled_worker_policy()
        j = svc.create_download_job_metadata_only(p.policy_id)
        g = svc.evaluate_download_worker_gate(j.job_id)
        assert g.decision == PackageDownloadWorkerDecision.BLOCKED_DISABLED
        assert g.worker_start_allowed == False
        assert g.download_allowed == False

    def test_evaluate_gate_all_false(self, svc, store):
        p = svc.create_disabled_worker_policy()
        j = svc.create_download_job_metadata_only(p.policy_id)
        g = svc.evaluate_download_worker_gate(j.job_id)
        assert not g.worker_start_allowed and not g.network_allowed
        assert not g.download_allowed and not g.file_write_allowed and not g.execution_allowed

    def test_evaluate_gate_blocked_with_checks(self, svc, store):
        p = svc.create_disabled_worker_policy()
        j = svc.create_download_job_metadata_only(p.policy_id)
        g = svc.evaluate_download_worker_gate(j.job_id)
        assert len(g.checks) >= 2  # policy disabled + kill switch clear
        assert g.metadata_only == True

    def test_reserve_lease_inactive(self, svc, store):
        p = svc.create_disabled_worker_policy()
        j = svc.create_download_job_metadata_only(p.policy_id)
        l = svc.reserve_worker_lease_metadata_only(j.job_id)
        assert l.lease_active == False
        assert l.worker_started == False
        assert l.download_allowed == False

    def test_reserve_lease_not_active(self, svc, store):
        p = svc.create_disabled_worker_policy()
        j = svc.create_download_job_metadata_only(p.policy_id)
        l = svc.reserve_worker_lease_metadata_only(j.job_id)
        assert not l.is_active()

    def test_reserve_lease_no_download(self, svc, store):
        p = svc.create_disabled_worker_policy()
        j = svc.create_download_job_metadata_only(p.policy_id)
        l = svc.reserve_worker_lease_metadata_only(j.job_id)
        assert not l.is_download_allowed()

    def test_release_lease(self, svc, store):
        p = svc.create_disabled_worker_policy()
        j = svc.create_download_job_metadata_only(p.policy_id)
        l = svc.reserve_worker_lease_metadata_only(j.job_id)
        r = svc.release_worker_lease_metadata_only(l.lease_id, "admin", "ok")
        assert r.status == PackageDownloadWorkerStatus.RELEASED_METADATA_ONLY
        assert r.lease_active == False

    def test_cancel_job(self, svc, store):
        p = svc.create_disabled_worker_policy()
        j = svc.create_download_job_metadata_only(p.policy_id)
        c = svc.cancel_job(j.job_id, "a", "reason")
        assert c.status == PackageDownloadWorkerStatus.CANCELLED

    def test_expire_job(self, svc, store):
        p = svc.create_disabled_worker_policy()
        j = svc.create_download_job_metadata_only(p.policy_id)
        e = svc.expire_job(j.job_id, "a", "reason")
        assert e.status == PackageDownloadWorkerStatus.EXPIRED

    def test_job_snapshots_stored(self, svc, store):
        p = svc.create_disabled_worker_policy()
        j = svc.create_download_job_metadata_only(
            p.policy_id, source_snapshot={"url_hash": "abc"},
            request_snapshot={"sid": "r1"}, quarantine_snapshot={"qid": "q1"})
        got = store.get_job(j.job_id)
        assert got.source_snapshot == {"url_hash": "abc"}
        assert got.package_request_snapshot == {"sid": "r1"}
        assert got.quarantine_snapshot == {"qid": "q1"}

    def test_gate_on_disabled_policy_always_blocked(self, svc, store):
        p = svc.create_disabled_worker_policy()
        j = svc.create_download_job_metadata_only(p.policy_id)
        for _ in range(3):
            g = svc.evaluate_download_worker_gate(j.job_id)
            assert g.decision == PackageDownloadWorkerDecision.BLOCKED_DISABLED

    def test_lease_release_does_not_enable_worker(self, svc, store):
        p = svc.create_disabled_worker_policy()
        j = svc.create_download_job_metadata_only(p.policy_id)
        l = svc.reserve_worker_lease_metadata_only(j.job_id)
        r = svc.release_worker_lease_metadata_only(l.lease_id, "admin")
        assert not r.is_active() and not r.is_download_allowed()

    def test_service_no_dangerous_methods(self, svc):
        names = [n for n in dir(svc) if not n.startswith("_")]
        for bad in _SVC_DANGEROUS:
            assert bad not in names

    def test_service_no_start_worker(self, svc):
        assert not hasattr(svc, "start_worker")

    def test_service_no_download_package(self, svc):
        assert not hasattr(svc, "download_package")

    def test_service_no_execute_package(self, svc):
        assert not hasattr(svc, "execute_package")

    def test_service_no_enqueue_job(self, svc):
        assert not hasattr(svc, "enqueue_job")

    def test_service_no_dispatch_job(self, svc):
        assert not hasattr(svc, "dispatch_job")

    def test_service_no_heartbeat(self, svc):
        assert not hasattr(svc, "heartbeat")


# ═══════ Safety Static Scans (13) ═══════

class TestSafety:
    _DANGEROUS_IMPORTS = [
        "requests", "httpx", "aiohttp", "urllib.request", "socket",
        "subprocess", "docker", "queue", "multiprocessing", "threading",
        "os.system", "eval(", "exec(", "open(",
        "AgentRuntime", "AgentRegistry"
    ]

    def test_domain_no_dangerous_imports(self):
        import src.open_platform.package_download_worker as m
        s = str(dir(m)).lower()
        for bad in self._DANGEROUS_IMPORTS:
            assert bad.lower() not in s, f"Domain should not import {bad}"

    def test_domain_no_subprocess(self):
        import src.open_platform.package_download_worker as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_domain_no_docker(self):
        import src.open_platform.package_download_worker as m
        assert "docker" not in str(dir(m)).lower()

    def test_domain_no_requests(self):
        import src.open_platform.package_download_worker as m
        assert "requests" not in str(dir(m)).lower()

    def test_domain_no_AgentRuntime(self):
        import src.open_platform.package_download_worker as m
        assert "AgentRuntime" not in str(dir(m))

    def test_store_no_dangerous_imports(self):
        import src.adapters.package_download_worker_store as m
        s = str(dir(m)).lower()
        for bad in self._DANGEROUS_IMPORTS:
            assert bad.lower() not in s, f"Store should not import {bad}"

    def test_store_no_subprocess(self):
        import src.adapters.package_download_worker_store as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_store_no_requests(self):
        import src.adapters.package_download_worker_store as m
        assert "requests" not in str(dir(m)).lower()

    def test_service_no_dangerous_imports(self):
        import src.open_platform.package_download_worker_service as m
        s = str(dir(m)).lower()
        for bad in self._DANGEROUS_IMPORTS:
            assert bad.lower() not in s, f"Service should not import {bad}"

    def test_service_no_subprocess(self):
        import src.open_platform.package_download_worker_service as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_service_no_requests(self):
        import src.open_platform.package_download_worker_service as m
        assert "requests" not in str(dir(m)).lower()

    def test_service_no_AgentRuntime(self):
        import src.open_platform.package_download_worker_service as m
        assert "AgentRuntime" not in str(dir(m))

    def test_gate_blocked(self):
        from src.open_platform.runtime_execution_gate import RuntimeExecutionGateResult
        assert not RuntimeExecutionGateResult().is_execution_allowed()

    def test_package_download_request_not_downloadable(self):
        from src.open_platform.package_download_quarantine import PackageDownloadRequest
        assert not PackageDownloadRequest().is_downloadable()

    def test_production_sandbox_gate_execution_blocked(self):
        from src.open_platform.production_sandbox_gate import ProductionSandboxGateResult
        g = ProductionSandboxGateResult()
        assert not hasattr(g, "runtime_enabled") or not getattr(g, "runtime_enabled", True)

    def test_store_module_no_httpx(self):
        import src.adapters.package_download_worker_store as m
        assert "httpx" not in str(dir(m)).lower()

    def test_service_module_no_httpx(self):
        import src.open_platform.package_download_worker_service as m
        assert "httpx" not in str(dir(m)).lower()

    def test_store_module_no_AgentRuntime(self):
        import src.adapters.package_download_worker_store as m
        assert "AgentRuntime" not in str(dir(m))
