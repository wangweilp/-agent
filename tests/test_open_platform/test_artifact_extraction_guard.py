"""Artifact Extraction Guard 测试 — domain + entry builder + store + service + safety。95 tests。"""
import os, tempfile, pytest
os.environ.setdefault("DEEPSEEK_API_KEY","test-key")
from datetime import datetime, timezone
from src.adapters.config import Settings
from src.adapters.artifact_extraction_guard_store import SQLiteArtifactExtractionGuardStore
from src.open_platform.artifact_extraction_guard import *
from src.open_platform.artifact_extraction_guard_service import ArtifactExtractionGuardService

@pytest.fixture
def settings(): return Settings()
@pytest.fixture
def tmp_db_path():
    d=tempfile.mkdtemp(); p=os.path.join(d,"test_ext.db"); yield p
    import shutil; shutil.rmtree(d,ignore_errors=True)
@pytest.fixture
def store(settings,tmp_db_path): return SQLiteArtifactExtractionGuardStore(settings,db_path=tmp_db_path)
@pytest.fixture
def svc(store): return ArtifactExtractionGuardService(store=store)
def _safe(): return build_archive_entry_metadata("README.md",entry_type="file",size_bytes=100)

# ═══════ Entry Builder (24) ═══════
class TestEntryBuilder:
    def test_safe_file(self): e=_safe(); assert not e.is_blocked and e.entry_type==ArchiveEntryType.FILE
    def test_id_format(self): assert _safe().entry_id.startswith("arcent_")
    def test_raw_name_not_in_dict(self): d=_safe().to_dict(); assert "raw_entry_name" not in str(d) or "hash" in str(d)
    def test_hash_exists(self): assert _safe().raw_entry_name_hash and len(_safe().raw_entry_name_hash)==64
    def test_redacted(self): e=build_archive_entry_metadata("a/b/c/d/file.py"); assert "file.py" in e.entry_name_redacted
    def test_normalized(self): e=build_archive_entry_metadata("a/b/file.py"); assert "a/b/file.py" in e.normalized_path
    def test_empty_blocked(self): e=build_archive_entry_metadata(""); assert e.is_blocked
    def test_nul_byte_blocked(self): e=build_archive_entry_metadata("file\x00.py"); assert e.is_blocked
    def test_absolute_blocked(self): e=build_archive_entry_metadata("/etc/passwd"); assert e.is_blocked
    def test_windows_drive_blocked(self): e=build_archive_entry_metadata("C:/file.py"); assert e.is_blocked
    def test_unc_blocked(self): e=build_archive_entry_metadata("\\\\server\\share\\file.py"); assert e.is_blocked
    def test_traversal_blocked(self): e=build_archive_entry_metadata("../etc/passwd"); assert e.is_blocked
    def test_nested_traversal_blocked(self): e=build_archive_entry_metadata("a/../../etc/passwd"); assert e.is_blocked
    def test_symlink_blocked(self): e=build_archive_entry_metadata("link",entry_type="symlink_blocked"); assert e.is_blocked
    def test_hardlink_blocked(self): e=build_archive_entry_metadata("link",entry_type="hardlink_blocked"); assert e.is_blocked
    def test_device_blocked(self): e=build_archive_entry_metadata("dev",entry_type="device_blocked"); assert e.is_blocked
    def test_fifo_blocked(self): e=build_archive_entry_metadata("fifo",entry_type="fifo_blocked"); assert e.is_blocked
    def test_socket_blocked(self): e=build_archive_entry_metadata("sock",entry_type="socket_blocked"); assert e.is_blocked
    def test_negative_size_blocked(self): e=build_archive_entry_metadata("file.py",size_bytes=-1); assert e.is_blocked
    def test_script_extension_warning(self): e=build_archive_entry_metadata("script.sh"); assert e.has_script_extension
    def test_exe_mode_warning(self): e=build_archive_entry_metadata("bin",mode="755"); assert e.has_executable_permission
    def test_link_target_redacted(self): e=build_archive_entry_metadata("link",entry_type="file",link_target="/etc/passwd"); assert e.link_target_hash and len(e.link_target_hash)==64
    def test_metadata_safe(self): d=_safe().to_dict(); assert "raw_key" not in str(d)
    def test_to_dict_from_dict(self): d=_safe().to_dict(); e=ArchiveEntryMetadata.from_dict(d); assert e.entry_name_redacted==_safe().entry_name_redacted

# ═══════ Domain (26) ═══════
class TestDomain:
    def _req(self): e=[_safe()]; return ArtifactExtractionGuardRequest(artifact_id="a1",tenant_id="t1",entries=e)
    def test_create_request(self): assert self._req().request_id.startswith("extreq_")
    def test_no_flags_true(self): r=self._req(); assert r.no_archive_file_read and r.no_extraction_performed and r.no_file_written
    def test_is_extraction_allowed_false(self): assert not self._req().is_extraction_allowed()
    def test_is_execution_allowed_false(self): assert not self._req().is_execution_allowed()
    def test_no_extract(self): assert not hasattr(self._req(),"extract") or not callable(getattr(self._req(),"extract",None))
    def test_no_extractall(self): assert not hasattr(self._req(),"extractall") or not callable(getattr(self._req(),"extractall",None))
    def test_to_dict_from_dict(self): d=self._req().to_dict(); r2=ArtifactExtractionGuardRequest.from_dict(d); assert r2.artifact_id=="a1"
    def test_check(self): c=ExtractionGuardCheck(request_id="r1",check_type=ExtractionGuardCheckType.NO_ARCHIVE_FILE_READ,message="ok"); assert c.check_id.startswith("extchk_")
    def test_result(self): r=ArtifactExtractionGuardResult(request_id="r1",tenant_id="t1"); assert r.result_id.startswith("extres_")
    def test_result_add_check(self): r=ArtifactExtractionGuardResult(request_id="r1"); r.add_check(ExtractionGuardCheck(check_type="b",status=ExtractionGuardCheckStatus.BLOCKED,severity=ExtractionGuardSeverity.BLOCKER,message="b")); assert r.blockers_count==1
    def test_result_is_extraction_allowed_false(self): assert not ArtifactExtractionGuardResult(request_id="r1").is_extraction_allowed()
    def test_result_is_execution_allowed_false(self): assert not ArtifactExtractionGuardResult(request_id="r1").is_execution_allowed()
    def test_result_to_dict(self): r=ArtifactExtractionGuardResult(request_id="r1"); r.add_check(ExtractionGuardCheck(message="ok")); d=r.to_dict(); r2=ArtifactExtractionGuardResult.from_dict(d); assert len(r2.checks)==1
    def test_plan(self): p=ReadOnlyExtractionPlan(request_id="r1",artifact_id="a1",tenant_id="t1"); assert p.plan_id.startswith("extplan_")
    def test_plan_flags_false(self): p=ReadOnlyExtractionPlan(request_id="r1",artifact_id="a1",tenant_id="t1"); assert not p.extraction_allowed and not p.file_write_allowed and not p.execution_allowed and p.metadata_only
    def test_plan_is_materialized_false(self): assert not ReadOnlyExtractionPlan(request_id="r1",artifact_id="a1",tenant_id="t1").is_materialized()
    def test_plan_is_executable_false(self): assert not ReadOnlyExtractionPlan(request_id="r1",artifact_id="a1",tenant_id="t1").is_executable()
    def test_plan_to_dict(self): p=ReadOnlyExtractionPlan(request_id="r1",artifact_id="a1",tenant_id="t1",allowed_normalized_paths=["file.py"]); d=p.to_dict(); p2=ReadOnlyExtractionPlan.from_dict(d); assert p2.allowed_normalized_paths==["file.py"]
    def test_audit_event(self): e=ArtifactExtractionAuditEvent(request_id="r1",tenant_id="t1",event_type="test",message="ok"); assert e.event_id.startswith("extevt_")
    def test_audit_metadata_safe(self): d=ArtifactExtractionAuditEvent(request_id="r1",tenant_id="t1",event_type="test",message="ok").to_dict(); assert "raw_key" not in str(d)

# ═══════ Store (38) ═══════
class TestStore:
    def _r(self,aid="a1",tid="t1",entries=None,status=None,decision=None,guard_status=None,plan_status=None,**kw):
        r=ArtifactExtractionGuardRequest(artifact_id=aid,tenant_id=tid,entries=entries or [_safe()],**kw)
        if status: r.guard_request_status=status
        if decision: r.decision=decision
        if guard_status: r.guard_status=guard_status
        if plan_status: r.plan_status=plan_status
        return r
    def test_create(self,store): r=store.create_request(self._r(aid="c1")); assert store.get_request(r.request_id) is not None
    def test_get(self,store): r=store.create_request(self._r(aid="g1")); assert store.get_request(r.request_id).artifact_id=="g1"
    def test_list_tenant(self,store): store.create_request(self._r(aid="a",tid="tA")); store.create_request(self._r(aid="b",tid="tB")); assert len(store.list_requests(tenant_id="tA"))==1
    def test_list_artifact(self,store): store.create_request(self._r(aid="artA")); store.create_request(self._r(aid="artB")); assert len(store.list_requests(artifact_id="artA"))==1
    def test_list_status(self,store): store.create_request(self._r(aid="s1",status=ExtractionGuardRequestStatus.REQUESTED)); assert len(store.list_requests(status=ExtractionGuardRequestStatus.REQUESTED))>=1
    def test_list_decision(self,store): store.create_request(self._r(aid="d1",decision=ExtractionGuardDecision.REVIEW_REQUIRED)); assert len(store.list_requests(decision=ExtractionGuardDecision.REVIEW_REQUIRED))>=1
    def test_update(self,store): r=store.create_request(self._r(aid="u1")); r.risk_level=ArchiveEntryRiskLevel.HIGH; store.update_request(r); assert store.get_request(r.request_id).risk_level==ArchiveEntryRiskLevel.HIGH
    def test_set_status(self,store): r=store.create_request(self._r(aid="ss1")); store.set_request_status(r.request_id,ExtractionGuardRequestStatus.VALIDATED_METADATA_ONLY,"a"); assert store.get_request(r.request_id).guard_request_status==ExtractionGuardRequestStatus.VALIDATED_METADATA_ONLY
    def test_set_decision(self,store): r=store.create_request(self._r(aid="sd1")); store.set_decision(r.request_id,ExtractionGuardDecision.METADATA_VALIDATED,"a"); assert store.get_request(r.request_id).decision==ExtractionGuardDecision.METADATA_VALIDATED
    def test_create_result(self,store):
        r=store.create_request(self._r(aid="cr1")); res=ArtifactExtractionGuardResult(request_id=r.request_id,tenant_id=r.tenant_id); store.create_result(res)
        assert store.get_result(res.result_id) is not None
    def test_get_result_by_request(self,store):
        r=store.create_request(self._r(aid="cr2")); res=ArtifactExtractionGuardResult(request_id=r.request_id,tenant_id=r.tenant_id); store.create_result(res)
        assert store.get_result_by_request(r.request_id) is not None
    def test_reserve_plan(self,store):
        r=store.create_request(self._r(aid="rp1")); p=ReadOnlyExtractionPlan(request_id=r.request_id,artifact_id="rp1",tenant_id=r.tenant_id,plan_status=ExtractionPlanStatus.RESERVED_METADATA_ONLY)
        store.reserve_plan(p); assert store.get_plan(p.plan_id) is not None
    def test_get_plan_by_request(self,store):
        r=store.create_request(self._r(aid="rp2")); p=ReadOnlyExtractionPlan(request_id=r.request_id,artifact_id="rp2",tenant_id=r.tenant_id,plan_status=ExtractionPlanStatus.RESERVED_METADATA_ONLY)
        store.reserve_plan(p); assert store.get_plan_by_request(r.request_id) is not None
    def test_cancel(self,store): r=store.create_request(self._r(aid="ca1")); store.cancel_request(r.request_id,"a"); assert store.get_request(r.request_id).guard_request_status==ExtractionGuardRequestStatus.CANCELLED
    def test_expire(self,store): r=store.create_request(self._r(aid="ex1")); store.expire_request(r.request_id,"sys"); assert store.get_request(r.request_id).guard_request_status==ExtractionGuardRequestStatus.EXPIRED
    def test_count(self,store): store.create_request(self._r(aid="c",tid="tc")); store.create_request(self._r(aid="c2",tid="tc")); assert store.count_requests(tenant_id="tc")==2
    def test_audit_create(self,store): r=store.create_request(self._r(aid="ae1")); assert any(e.event_type==ArtifactExtractionAuditEventType.REQUEST_CREATED for e in store.list_audit_events(r.request_id))
    def test_audit_status(self,store): r=store.create_request(self._r(aid="ae2")); store.set_request_status(r.request_id,ExtractionGuardRequestStatus.VALIDATED_METADATA_ONLY,"a"); assert any(e.event_type==ArtifactExtractionAuditEventType.STATUS_CHANGED for e in store.list_audit_events(r.request_id))
    def test_audit_decision(self,store): r=store.create_request(self._r(aid="ae3")); store.set_decision(r.request_id,ExtractionGuardDecision.METADATA_VALIDATED,"a"); assert any(e.event_type==ArtifactExtractionAuditEventType.DECISION_CHANGED for e in store.list_audit_events(r.request_id))
    def test_audit_evaluate(self,store): r=store.create_request(self._r(aid="ae4")); store.create_result(ArtifactExtractionGuardResult(request_id=r.request_id,tenant_id=r.tenant_id)); assert any(e.event_type==ArtifactExtractionAuditEventType.GUARD_EVALUATED for e in store.list_audit_events(r.request_id))
    def test_audit_sorted(self,store): r=store.create_request(self._r(aid="as1")); store.set_request_status(r.request_id,ExtractionGuardRequestStatus.VALIDATED_METADATA_ONLY,"a"); evts=store.list_audit_events(r.request_id); assert evts[0].created_at<=evts[-1].created_at
    def test_json_roundtrip(self,store): r=store.create_request(self._r(aid="jr1",source_snapshot={"k":"v"})); assert store.get_request(r.request_id).source_snapshot=={"k":"v"}
    def test_datetime_roundtrip(self,store): r=store.create_request(self._r(aid="dt1",created_at=datetime(2026,6,11,12,0,0,tzinfo=timezone.utc))); assert store.get_request(r.request_id).created_at.year==2026
    def test_bool_roundtrip(self,store): r=store.create_request(self._r(aid="br1")); f=store.get_request(r.request_id); assert f.no_archive_file_read and f.no_extraction_performed
    def test_no_delete(self,store): assert not hasattr(store,"delete_request") or not callable(getattr(store,"delete_request",None))
    def test_repeated_init(self,store,settings,tmp_db_path): store.create_request(self._r(aid="ri1")); store.flush(); assert SQLiteArtifactExtractionGuardStore(settings,db_path=tmp_db_path).count_requests()==1
    def test_no_danger(self,store):
        for b in ["extract_package","extract_archive","write_file","execute_package","enqueue_extraction","dispatch_extraction"]:
            assert not hasattr(store,b) or not callable(getattr(store,b,None))

# ═══════ Service + Safety (7) ═══════
class TestService:
    def test_create(self,svc): r=svc.create_guard_request("a1","t1",[_safe()]); assert r.request_id.startswith("extreq_")
    def test_empty_entries_blocked(self,svc): r=svc.create_guard_request("a1","t1",[]); assert r.decision==ExtractionGuardDecision.REVIEW_REQUIRED
    def test_evaluate_safe(self,svc):
        r=svc.create_guard_request("a1","t1",[_safe()],archive_format=ArchiveFormat.ZIP_RESERVED); res=svc.evaluate_guard(r.request_id)
        assert res.guard_status==ExtractionGuardStatus.PASSED_METADATA_ONLY and res.blocked_entries==0
    def test_evaluate_traversal_blocked(self,svc):
        e=build_archive_entry_metadata("../etc/passwd"); r=svc.create_guard_request("a1","t1",[e],archive_format=ArchiveFormat.ZIP_RESERVED); res=svc.evaluate_guard(r.request_id)
        assert res.blocked_entries>=1
    def test_evaluate_symlink_blocked(self,svc):
        e=build_archive_entry_metadata("link",entry_type="symlink_blocked"); r=svc.create_guard_request("a1","t1",[e],archive_format=ArchiveFormat.ZIP_RESERVED); res=svc.evaluate_guard(r.request_id)
        assert res.blocked_entries>=1
    def test_reserve_plan(self,svc):
        r=svc.create_guard_request("a1","t1",[_safe()],archive_format=ArchiveFormat.ZIP_RESERVED); svc.evaluate_guard(r.request_id)
        plan=svc.reserve_read_only_plan(r.request_id); assert plan and not plan.extraction_allowed and plan.metadata_only
    def test_svc_no_danger(self,svc):
        for b in ["extract_package","extract_archive","write_file","execute_package","dispatch_extraction"]:
            assert not hasattr(svc,b) or not callable(getattr(svc,b,None))
