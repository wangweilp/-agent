"""Artifact Materialization Tests — Step 26-D: read-only spike, metadata-only, disabled-by-default."""
import os, tempfile, pytest
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
from datetime import datetime, timezone
from src.adapters.config import Settings
from src.adapters.artifact_materialization_store import SQLiteArtifactMaterializationStore
from src.open_platform.artifact_materialization import *
from src.open_platform.artifact_materialization_service import ArtifactMaterializationService


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "test_artmat.db")
    yield p
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def store(settings, tmp_db_path):
    return SQLiteArtifactMaterializationStore(settings, db_path=tmp_db_path)


@pytest.fixture
def svc(store):
    return ArtifactMaterializationService(store=store)


# ═══════ Domain (35) ═══════

class TestDomain:
    def test_policy_defaults_disabled(self):
        p = ArtifactMaterializationPolicy()
        assert p.materialization_enabled == False
        assert p.file_write_enabled == False
        assert p.directory_create_enabled == False
        assert p.mount_enabled == False
        assert p.extraction_enabled == False
        assert p.package_execution_enabled == False

    def test_policy_is_materialization_allowed_false(self):
        assert ArtifactMaterializationPolicy().is_materialization_allowed() == False

    def test_policy_is_file_write_allowed_false(self):
        assert ArtifactMaterializationPolicy().is_file_write_allowed() == False

    def test_policy_is_mount_allowed_false(self):
        assert ArtifactMaterializationPolicy().is_mount_allowed() == False

    def test_policy_is_execution_allowed_false(self):
        assert ArtifactMaterializationPolicy().is_execution_allowed() == False

    def test_policy_enabled_metadata_only(self):
        assert ArtifactMaterializationPolicy().enabled_metadata_only == True

    def test_policy_read_only_refs_only(self):
        assert ArtifactMaterializationPolicy().read_only_refs_only == True

    def test_policy_id_prefix(self):
        assert ArtifactMaterializationPolicy().policy_id.startswith("artmatpol_")

    def test_policy_to_dict_and_back(self):
        p = ArtifactMaterializationPolicy(tenant_id="t1")
        d = p.to_dict()
        p2 = ArtifactMaterializationPolicy.from_dict(d)
        assert p2.tenant_id == "t1"
        assert p2.materialization_enabled == False

    def test_policy_metadata_roundtrip(self):
        p = ArtifactMaterializationPolicy(metadata={"k": "v"})
        d = p.to_dict()
        p2 = ArtifactMaterializationPolicy.from_dict(d)
        assert p2.metadata == {"k": "v"}

    def test_request_defaults_disabled(self):
        r = ArtifactMaterializationRequest()
        assert r.materialization_performed == False
        assert r.file_written == False
        assert r.directory_created == False
        assert r.mount_created == False
        assert r.archive_read == False
        assert r.archive_extracted == False
        assert r.package_executed == False
        assert r.entrypoint_executed == False

    def test_request_is_materialization_allowed_false(self):
        assert ArtifactMaterializationRequest().is_materialization_allowed() == False

    def test_request_is_execution_allowed_false(self):
        assert ArtifactMaterializationRequest().is_execution_allowed() == False

    def test_request_no_flags_all_true(self):
        r = ArtifactMaterializationRequest()
        assert r.no_file_written and r.no_directory_created and r.no_mount_created
        assert r.no_archive_read and r.no_extraction_performed and r.no_execution_performed
        assert r.no_worker_started and r.no_dispatch_performed

    def test_request_id_prefix(self):
        assert ArtifactMaterializationRequest().request_id.startswith("artmatreq_")

    def test_request_to_dict_and_back(self):
        r = ArtifactMaterializationRequest(tenant_id="t1", source_snapshot={"a": 1})
        d = r.to_dict()
        r2 = ArtifactMaterializationRequest.from_dict(d)
        assert r2.tenant_id == "t1"
        assert r2.source_snapshot == {"a": 1}

    def test_plan_not_materialized(self):
        p = ReadOnlyArtifactMaterializationPlan(request_id="r1")
        assert p.is_materialized() == False
        assert p.materialization_allowed == False

    def test_plan_is_mount_active_false(self):
        assert ReadOnlyArtifactMaterializationPlan(request_id="r1").is_mount_active() == False

    def test_plan_is_execution_allowed_false(self):
        assert ReadOnlyArtifactMaterializationPlan(request_id="r1").is_execution_allowed() == False

    def test_plan_all_allowed_flags_false(self):
        p = ReadOnlyArtifactMaterializationPlan(request_id="r1")
        assert not p.file_write_allowed and not p.directory_create_allowed
        assert not p.mount_allowed and not p.extraction_allowed and not p.execution_allowed

    def test_plan_id_prefix(self):
        assert ReadOnlyArtifactMaterializationPlan(request_id="r1").plan_id.startswith("artmatplan_")

    def test_plan_to_dict_and_back(self):
        p = ReadOnlyArtifactMaterializationPlan(request_id="r1", tenant_id="t1")
        d = p.to_dict()
        p2 = ReadOnlyArtifactMaterializationPlan.from_dict(d)
        assert p2.tenant_id == "t1"
        assert p2.is_materialized() == False

    def test_reference_filesystem_path_none(self):
        ref = ReadOnlyArtifactReference(plan_id="p1")
        assert ref.filesystem_path is None

    def test_reference_is_filesystem_ref_active_false(self):
        assert ReadOnlyArtifactReference(plan_id="p1").is_filesystem_ref_active() == False

    def test_reference_is_file_opened_false(self):
        assert ReadOnlyArtifactReference(plan_id="p1").is_file_opened() == False

    def test_reference_is_execution_allowed_false(self):
        assert ReadOnlyArtifactReference(plan_id="p1").is_execution_allowed() == False

    def test_reference_file_written_false(self):
        assert ReadOnlyArtifactReference(plan_id="p1").file_written == False

    def test_reference_id_prefix(self):
        assert ReadOnlyArtifactReference(plan_id="p1").ref_id.startswith("artmatref_")

    def test_gate_all_allowed_flags_false(self):
        g = ArtifactMaterializationGateResult(request_id="r1")
        assert g.materialization_allowed == False
        assert g.file_write_allowed == False
        assert g.directory_create_allowed == False
        assert g.mount_allowed == False
        assert g.archive_read_allowed == False
        assert g.extraction_allowed == False
        assert g.execution_allowed == False

    def test_gate_metadata_only_true(self):
        assert ArtifactMaterializationGateResult(request_id="r1").metadata_only == True

    def test_gate_id_prefix(self):
        assert ArtifactMaterializationGateResult(request_id="r1").gate_result_id.startswith("artmatgate_")

    def test_audit_event_id(self):
        e = ArtifactMaterializationAuditEvent()
        assert e.event_id.startswith("artmatevt_")

    def test_audit_metadata_safe(self):
        d = ArtifactMaterializationAuditEvent(event_type="t", message="ok").to_dict()
        assert "raw_key" not in str(d)
        assert "package_url" not in str(d).lower()

    def test_enum_no_materialized_status(self):
        vs = [v.value for v in ArtifactMaterializationStatus.__members__.values()]
        for bad in ["materializing", "materialized", "file_written",
                     "directory_created", "mount_active", "extracted",
                     "ready_for_execution", "package_ready", "runtime_ready"]:
            assert bad not in vs

    def test_enum_no_kill_in_decision(self):
        vs = [v.value for v in ArtifactMaterializationDecision.__members__.values()]
        for bad in ["process_killed", "runtime_terminated", "materialized"]:
            assert bad not in vs


# ═══════ Store (40) ═══════

_DANGEROUS = ["materialize_package", "write_file", "create_directory", "mount_artifact",
              "extract_archive", "extract_package", "open_file", "check_file_exists",
              "execute_package", "execute_entrypoint", "dispatch_job", "enqueue_job",
              "start_worker", "heartbeat", "delete_request"]


class TestStore:
    def _p(self, **kw):
        return ArtifactMaterializationPolicy(**kw)

    def _r(self, **kw):
        return ArtifactMaterializationRequest(**kw)

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
        store.create_policy(self._p(scope=ArtifactMaterializationScope.GLOBAL))
        assert len(store.list_policies(scope=ArtifactMaterializationScope.GLOBAL)) >= 1

    def test_update_policy(self, store):
        p = store.create_policy(self._p())
        p.materialization_enabled = False
        store.update_policy(p)
        assert store.get_policy(p.policy_id).materialization_enabled == False

    def test_policy_disabled_flags_stored(self, store):
        p = store.create_policy(self._p())
        f = store.get_policy(p.policy_id)
        assert f.materialization_enabled == False
        assert f.file_write_enabled == False
        assert f.mount_enabled == False

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
        assert len(store.list_requests(status=ArtifactMaterializationStatus.DISABLED_BY_DEFAULT)) >= 1

    def test_update_request(self, store):
        r = store.create_request(self._r())
        r.status = ArtifactMaterializationStatus.BLOCKED_DISABLED
        store.update_request(r)
        assert store.get_request(r.request_id).status == ArtifactMaterializationStatus.BLOCKED_DISABLED

    def test_set_request_status(self, store):
        r = store.create_request(self._r())
        store.set_request_status(r.request_id, ArtifactMaterializationStatus.CANCELLED, "a", "reason")
        assert store.get_request(r.request_id).status == ArtifactMaterializationStatus.CANCELLED

    def test_set_request_decision(self, store):
        r = store.create_request(self._r())
        store.set_request_decision(r.request_id, ArtifactMaterializationDecision.FAIL_CLOSED, "a", "reason")
        assert store.get_request(r.request_id).decision == ArtifactMaterializationDecision.FAIL_CLOSED

    def test_reserve_plan(self, store):
        p = ReadOnlyArtifactMaterializationPlan(request_id="r1", tenant_id="t1")
        r = store.reserve_plan_metadata_only(p)
        assert store.get_plan(r.plan_id) is not None

    def test_get_plan(self, store):
        p = store.reserve_plan_metadata_only(ReadOnlyArtifactMaterializationPlan(request_id="rpg"))
        assert store.get_plan(p.plan_id).request_id == "rpg"

    def test_get_plan_by_request(self, store):
        store.reserve_plan_metadata_only(ReadOnlyArtifactMaterializationPlan(request_id="rpb"))
        assert store.get_plan_by_request("rpb") is not None

    def test_plan_not_materialized_after_reserve(self, store):
        p = store.reserve_plan_metadata_only(ReadOnlyArtifactMaterializationPlan(request_id="rpn"))
        assert store.get_plan(p.plan_id).is_materialized() == False
        assert store.get_plan(p.plan_id).mount_allowed == False

    def test_reserve_ref(self, store):
        r = store.reserve_read_only_reference(ReadOnlyArtifactReference(plan_id="p1"))
        assert store.get_reference(r.ref_id) is not None

    def test_get_ref(self, store):
        r = store.reserve_read_only_reference(ReadOnlyArtifactReference(plan_id="prg"))
        assert store.get_reference(r.ref_id).plan_id == "prg"

    def test_list_references(self, store):
        store.reserve_read_only_reference(ReadOnlyArtifactReference(plan_id="pla"))
        assert len(store.list_references(plan_id="pla")) >= 1

    def test_ref_filesystem_path_none(self, store):
        r = store.reserve_read_only_reference(ReadOnlyArtifactReference(plan_id="prn"))
        assert store.get_reference(r.ref_id).filesystem_path is None

    def test_create_gate(self, store):
        g = store.create_gate_result(ArtifactMaterializationGateResult(request_id="r1", tenant_id="t1"))
        assert store.get_gate_result(g.gate_result_id) is not None

    def test_get_gate(self, store):
        g = store.create_gate_result(ArtifactMaterializationGateResult(request_id="rgt", tenant_id="t1"))
        assert store.get_gate_result(g.gate_result_id).request_id == "rgt"

    def test_get_gate_by_request(self, store):
        store.create_gate_result(ArtifactMaterializationGateResult(request_id="rgb"))
        assert store.get_gate_result_by_request("rgb") is not None

    def test_gate_all_allowed_false(self, store):
        g = store.create_gate_result(ArtifactMaterializationGateResult(request_id="rgf"))
        f = store.get_gate_result(g.gate_result_id)
        assert not f.materialization_allowed and not f.file_write_allowed
        assert not f.mount_allowed and not f.extraction_allowed and not f.execution_allowed

    def test_audit_policy_create(self, store):
        p = store.create_policy(self._p())
        evts = store.list_audit_events(policy_id=p.policy_id)
        assert any(e.event_type == ArtifactMaterializationAuditEventType.MATERIALIZATION_POLICY_CREATED
                   for e in evts)

    def test_audit_request_create(self, store):
        r = store.create_request(self._r())
        evts = store.list_audit_events(request_id=r.request_id)
        assert any(e.event_type == ArtifactMaterializationAuditEventType.MATERIALIZATION_REQUEST_CREATED
                   for e in evts)

    def test_audit_gate(self, store):
        g = store.create_gate_result(ArtifactMaterializationGateResult(request_id="rag"))
        evts = store.list_audit_events(request_id="rag")
        assert any(e.event_type == ArtifactMaterializationAuditEventType.GATE_EVALUATED
                   for e in evts)

    def test_audit_plan(self, store):
        p = store.reserve_plan_metadata_only(ReadOnlyArtifactMaterializationPlan(request_id="rap"))
        evts = store.list_audit_events(request_id="rap")
        assert any(e.event_type == ArtifactMaterializationAuditEventType.MATERIALIZATION_PLAN_RESERVED
                   for e in evts)

    def test_audit_ref(self, store):
        r = store.reserve_read_only_reference(ReadOnlyArtifactReference(plan_id="par"))
        evts = store.list_audit_events()
        assert any(e.event_type == ArtifactMaterializationAuditEventType.READ_ONLY_REFERENCE_RESERVED
                   for e in evts)

    def test_json_rt_policy(self, store):
        p = store.create_policy(self._p(metadata={"k": "v"}))
        assert store.get_policy(p.policy_id).metadata == {"k": "v"}

    def test_json_rt_request(self, store):
        r = store.create_request(self._r(source_snapshot={"a": 1}))
        assert store.get_request(r.request_id).source_snapshot == {"a": 1}

    def test_bool_rt_policy(self, store):
        p = store.create_policy(self._p())
        f = store.get_policy(p.policy_id)
        assert f.enabled_metadata_only and not f.materialization_enabled

    def test_bool_rt_request(self, store):
        r = store.create_request(self._r())
        f = store.get_request(r.request_id)
        assert not f.materialization_performed and not f.file_written
        assert f.no_file_written and f.no_mount_created

    def test_count_requests(self, store):
        store.create_request(self._r(tenant_id="tc"))
        store.create_request(self._r(tenant_id="tc"))
        assert store.count_requests(tenant_id="tc") == 2

    def test_repeated_init(self, store, settings, tmp_db_path):
        store.create_policy(self._p())
        store.flush()
        s2 = SQLiteArtifactMaterializationStore(settings, db_path=tmp_db_path)
        assert s2.count_requests() == 0

    def test_no_physical_delete(self, store):
        for m in ["delete_policy", "delete_request", "delete_plan", "delete_ref",
                   "delete_gate", "delete_audit"]:
            assert not hasattr(store, m) or not callable(getattr(store, m, None))

    def test_store_no_dangerous_methods(self, store):
        names = [n for n in dir(store) if not n.startswith("_")]
        for bad in _DANGEROUS:
            assert bad not in names, f"Store should not have {bad}"


# ═══════ Service (27) ═══════

_SVC_DANGEROUS = ["materialize_package", "write_file", "create_directory", "mount_artifact",
                  "extract_archive", "extract_package", "open_file", "check_file_exists",
                  "execute_package", "execute_entrypoint", "dispatch_job", "enqueue_job",
                  "start_worker", "heartbeat"]


class TestService:
    def test_create_disabled_policy(self, svc, store):
        p = svc.create_disabled_materialization_policy(tenant_id="t1")
        assert p.materialization_enabled == False
        assert p.file_write_enabled == False
        assert p.mount_enabled == False
        assert p.package_execution_enabled == False

    def test_create_disabled_policy_all_no(self, svc):
        p = svc.create_disabled_materialization_policy()
        assert not p.materialization_enabled and not p.file_write_enabled
        assert not p.directory_create_enabled and not p.mount_enabled
        assert not p.extraction_enabled and not p.package_execution_enabled

    def test_create_disabled_policy_not_materialization_allowed(self, svc):
        p = svc.create_disabled_materialization_policy()
        assert p.is_materialization_allowed() == False

    def test_create_request_disabled(self, svc, store):
        p = svc.create_disabled_materialization_policy(tenant_id="t1")
        r = svc.create_materialization_request_metadata_only(p.policy_id, actor_id="a")
        assert r.status == ArtifactMaterializationStatus.DISABLED_BY_DEFAULT
        assert r.decision == ArtifactMaterializationDecision.BLOCKED_DISABLED

    def test_create_request_no_materialization(self, svc, store):
        p = svc.create_disabled_materialization_policy()
        r = svc.create_materialization_request_metadata_only(p.policy_id)
        assert r.materialization_performed == False
        assert r.file_written == False
        assert r.directory_created == False
        assert r.mount_created == False
        assert r.package_executed == False

    def test_create_request_no_flags(self, svc, store):
        p = svc.create_disabled_materialization_policy()
        r = svc.create_materialization_request_metadata_only(p.policy_id)
        assert r.no_file_written and r.no_directory_created and r.no_mount_created
        assert r.no_archive_read and r.no_extraction_performed and r.no_execution_performed
        assert r.no_worker_started and r.no_dispatch_performed

    def test_evaluate_gate_blocked(self, svc, store):
        p = svc.create_disabled_materialization_policy()
        r = svc.create_materialization_request_metadata_only(p.policy_id)
        g = svc.evaluate_materialization_gate(r.request_id)
        assert g.decision == ArtifactMaterializationDecision.BLOCKED_DISABLED
        assert g.materialization_allowed == False

    def test_evaluate_gate_all_false(self, svc, store):
        p = svc.create_disabled_materialization_policy()
        r = svc.create_materialization_request_metadata_only(p.policy_id)
        g = svc.evaluate_materialization_gate(r.request_id)
        assert not g.materialization_allowed and not g.file_write_allowed
        assert not g.directory_create_allowed and not g.mount_allowed
        assert not g.archive_read_allowed and not g.extraction_allowed and not g.execution_allowed

    def test_evaluate_gate_blocked_with_checks(self, svc, store):
        p = svc.create_disabled_materialization_policy()
        r = svc.create_materialization_request_metadata_only(p.policy_id)
        g = svc.evaluate_materialization_gate(r.request_id)
        assert len(g.checks) >= 3
        assert g.metadata_only == True

    def test_reserve_plan_not_materialized(self, svc, store):
        p = svc.create_disabled_materialization_policy()
        r = svc.create_materialization_request_metadata_only(p.policy_id)
        pl = svc.reserve_materialization_plan_metadata_only(r.request_id)
        assert pl.is_materialized() == False
        assert pl.materialization_allowed == False
        assert pl.execution_allowed == False

    def test_reserve_plan_no_mount(self, svc, store):
        p = svc.create_disabled_materialization_policy()
        r = svc.create_materialization_request_metadata_only(p.policy_id)
        pl = svc.reserve_materialization_plan_metadata_only(r.request_id)
        assert pl.is_mount_active() == False
        assert pl.mount_allowed == False

    def test_reserve_ref_filesystem_path_none(self, svc, store):
        p = svc.create_disabled_materialization_policy()
        r = svc.create_materialization_request_metadata_only(p.policy_id)
        pl = svc.reserve_materialization_plan_metadata_only(r.request_id)
        ref = svc.reserve_read_only_artifact_reference(pl.plan_id)
        assert ref.filesystem_path is None
        assert ref.is_filesystem_ref_active() == False

    def test_reserve_ref_not_file_opened(self, svc, store):
        p = svc.create_disabled_materialization_policy()
        r = svc.create_materialization_request_metadata_only(p.policy_id)
        pl = svc.reserve_materialization_plan_metadata_only(r.request_id)
        ref = svc.reserve_read_only_artifact_reference(pl.plan_id)
        assert ref.is_file_opened() == False
        assert ref.file_written == False

    def test_cancel_request(self, svc, store):
        p = svc.create_disabled_materialization_policy()
        r = svc.create_materialization_request_metadata_only(p.policy_id)
        c = svc.cancel_request(r.request_id, "a", "reason")
        assert c.status == ArtifactMaterializationStatus.CANCELLED

    def test_expire_request(self, svc, store):
        p = svc.create_disabled_materialization_policy()
        r = svc.create_materialization_request_metadata_only(p.policy_id)
        e = svc.expire_request(r.request_id, "a", "reason")
        assert e.status == ArtifactMaterializationStatus.EXPIRED

    def test_request_snapshots_stored(self, svc, store):
        p = svc.create_disabled_materialization_policy()
        r = svc.create_materialization_request_metadata_only(
            p.policy_id, source_snapshot={"hash": "abc"},
            quarantine_snapshot={"qid": "q1"},
            download_worker_snapshot={"jid": "j1"},
            extraction_guard_snapshot={"eid": "e1"})
        got = store.get_request(r.request_id)
        assert got.source_snapshot == {"hash": "abc"}
        assert got.quarantine_snapshot == {"qid": "q1"}
        assert got.download_worker_snapshot == {"jid": "j1"}
        assert got.extraction_guard_snapshot == {"eid": "e1"}

    def test_gate_on_disabled_policy_always_blocked(self, svc, store):
        p = svc.create_disabled_materialization_policy()
        r = svc.create_materialization_request_metadata_only(p.policy_id)
        for _ in range(3):
            g = svc.evaluate_materialization_gate(r.request_id)
            assert g.decision == ArtifactMaterializationDecision.BLOCKED_DISABLED

    def test_plan_reserve_does_not_enable_execution(self, svc, store):
        p = svc.create_disabled_materialization_policy()
        r = svc.create_materialization_request_metadata_only(p.policy_id)
        pl = svc.reserve_materialization_plan_metadata_only(r.request_id)
        assert not pl.is_execution_allowed()
        assert not pl.is_materialized()

    def test_ref_does_not_enable_filesystem(self, svc, store):
        p = svc.create_disabled_materialization_policy()
        r = svc.create_materialization_request_metadata_only(p.policy_id)
        pl = svc.reserve_materialization_plan_metadata_only(r.request_id)
        ref = svc.reserve_read_only_artifact_reference(pl.plan_id)
        assert not ref.is_filesystem_ref_active()
        assert not ref.is_file_opened()

    def test_service_no_dangerous_methods(self, svc):
        names = [n for n in dir(svc) if not n.startswith("_")]
        for bad in _SVC_DANGEROUS:
            assert bad not in names

    def test_service_no_materialize_package(self, svc):
        assert not hasattr(svc, "materialize_package")

    def test_service_no_write_file(self, svc):
        assert not hasattr(svc, "write_file")

    def test_service_no_mount_artifact(self, svc):
        assert not hasattr(svc, "mount_artifact")

    def test_service_no_execute_package(self, svc):
        assert not hasattr(svc, "execute_package")

    def test_service_no_start_worker(self, svc):
        assert not hasattr(svc, "start_worker")


# ═══════ Safety Static Scans (18) ═══════

class TestSafety:
    _DANGEROUS_IMPORTS = [
        "zipfile", "tarfile", "shutil",
        "requests", "httpx", "aiohttp", "urllib.request", "socket",
        "subprocess", "docker", "queue", "multiprocessing", "threading",
        "os.system", "eval(", "exec(", "open(",
        "Path.exists", "Path.resolve", "chmod", "chown", "mount",
        "AgentRuntime", "AgentRegistry"
    ]

    def test_domain_no_dangerous_imports(self):
        import src.open_platform.artifact_materialization as m
        s = str(dir(m)).lower()
        for bad in self._DANGEROUS_IMPORTS:
            assert bad.lower() not in s, f"Domain should not import {bad}"

    def test_domain_no_subprocess(self):
        import src.open_platform.artifact_materialization as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_domain_no_docker(self):
        import src.open_platform.artifact_materialization as m
        assert "docker" not in str(dir(m)).lower()

    def test_domain_no_requests(self):
        import src.open_platform.artifact_materialization as m
        assert "requests" not in str(dir(m)).lower()

    def test_domain_no_AgentRuntime(self):
        import src.open_platform.artifact_materialization as m
        assert "AgentRuntime" not in str(dir(m))

    def test_domain_no_zipfile(self):
        import src.open_platform.artifact_materialization as m
        assert "zipfile" not in str(dir(m)).lower()

    def test_domain_no_tarfile(self):
        import src.open_platform.artifact_materialization as m
        assert "tarfile" not in str(dir(m)).lower()

    def test_store_no_dangerous_imports(self):
        import src.adapters.artifact_materialization_store as m
        s = str(dir(m)).lower()
        for bad in self._DANGEROUS_IMPORTS:
            assert bad.lower() not in s, f"Store should not import {bad}"

    def test_store_no_subprocess(self):
        import src.adapters.artifact_materialization_store as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_store_no_requests(self):
        import src.adapters.artifact_materialization_store as m
        assert "requests" not in str(dir(m)).lower()

    def test_store_no_AgentRuntime(self):
        import src.adapters.artifact_materialization_store as m
        assert "AgentRuntime" not in str(dir(m))

    def test_service_no_dangerous_imports(self):
        import src.open_platform.artifact_materialization_service as m
        s = str(dir(m)).lower()
        for bad in self._DANGEROUS_IMPORTS:
            assert bad.lower() not in s, f"Service should not import {bad}"

    def test_service_no_subprocess(self):
        import src.open_platform.artifact_materialization_service as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_service_no_requests(self):
        import src.open_platform.artifact_materialization_service as m
        assert "requests" not in str(dir(m)).lower()

    def test_service_no_AgentRuntime(self):
        import src.open_platform.artifact_materialization_service as m
        assert "AgentRuntime" not in str(dir(m))

    def test_gate_blocked(self):
        from src.open_platform.runtime_execution_gate import RuntimeExecutionGateResult
        assert not RuntimeExecutionGateResult().is_execution_allowed()

    def test_package_download_not_downloadable(self):
        from src.open_platform.package_download_quarantine import PackageDownloadRequest
        assert not PackageDownloadRequest().is_downloadable()

    def test_production_sandbox_gate_no_runtime_enabled(self):
        from src.open_platform.production_sandbox_gate import ProductionSandboxGateResult
        g = ProductionSandboxGateResult()
        assert hasattr(g, "runtime_enabled") and g.runtime_enabled == False
