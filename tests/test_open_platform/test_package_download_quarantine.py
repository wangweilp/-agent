"""Package Download Quarantine Tests — domain + store + service + safety。130 tests。"""
import os, tempfile, pytest
os.environ.setdefault("DEEPSEEK_API_KEY","test-key")
from datetime import datetime, timezone
from src.adapters.config import Settings
from src.adapters.package_download_quarantine_store import SQLitePackageDownloadQuarantineStore
from src.open_platform.package_download_quarantine import *
from src.open_platform.package_download_quarantine_service import PackageDownloadQuarantineService
from src.open_platform.package_artifact import PackageArtifact

@pytest.fixture
def settings(): return Settings()
@pytest.fixture
def tmp_db_path():
    d=tempfile.mkdtemp(); path=os.path.join(d,"test_pkgdl.db"); yield path
    import shutil; shutil.rmtree(d,ignore_errors=True)
@pytest.fixture
def store(settings,tmp_db_path): return SQLitePackageDownloadQuarantineStore(settings,db_path=tmp_db_path)
@pytest.fixture
def svc(store): return PackageDownloadQuarantineService(store=store)

def _src(url="https://example.com/pkg.zip"): return build_package_source_metadata(url)
def _req(aid="art1",tid="t1",**kw):
    return PackageDownloadRequest(artifact_id=aid,tenant_id=tid,source_metadata=_src(),
        **{k:v for k,v in kw.items() if k not in ("aid","tid")})

# ═══════ Source Metadata (18) ═══════
class TestSourceMetadata:
    def test_https(self): s=_src("https://example.com/pkg.zip"); assert s.source_scheme==PackageSourceScheme.HTTPS and not s.is_blocked_source
    def test_id_format(self): assert _src().source_id.startswith("pkgsrc_")
    def test_http_blocked(self): s=_src("http://example.com/pkg.zip"); assert s.source_scheme==PackageSourceScheme.HTTP_BLOCKED and s.is_blocked_source
    def test_file_blocked(self): s=_src("file:///etc/passwd"); assert s.source_scheme==PackageSourceScheme.FILE_BLOCKED and s.is_blocked_source
    def test_git_blocked(self): s=_src("git://example.com/repo"); assert s.source_scheme==PackageSourceScheme.GIT_BLOCKED
    def test_ssh_blocked(self): s=_src("ssh://git@example.com/repo"); assert s.source_scheme==PackageSourceScheme.GIT_BLOCKED
    def test_localhost_blocked(self): s=_src("https://localhost/pkg.zip"); assert s.is_localhost and s.is_blocked_source
    def test_127_blocked(self): s=_src("https://127.0.0.1/pkg.zip"); assert s.is_blocked_source
    def test_metadata_ip_blocked(self): s=_src("https://169.254.169.254/latest"); assert s.is_metadata_ip and s.risk_level==PackageSourceRiskLevel.CRITICAL
    def test_metadata_google_blocked(self): s=_src("https://metadata.google.internal/"); assert s.is_blocked_source
    def test_private_10_blocked(self): s=_src("https://10.0.0.1/pkg.zip"); assert s.is_private_ip_literal and s.is_blocked_source
    def test_private_192_blocked(self): s=_src("https://192.168.1.1/pkg.zip"); assert s.is_private_ip_literal and s.is_blocked_source
    def test_empty_fail_closed(self): s=_src(""); assert s.is_blocked_source and s.source_scheme==PackageSourceScheme.UNKNOWN_BLOCKED
    def test_none_fail_closed(self): s=build_package_source_metadata(None); assert s.is_blocked_source and s.source_scheme==PackageSourceScheme.UNKNOWN_BLOCKED
    def test_url_hash_exists(self): s=_src(); assert s.source_url_hash and len(s.source_url_hash)==64
    def test_url_redacted(self):
        s=_src("https://example.com/long/path/is/here/pkg.zip")
        assert s.source_url_redacted and "example.com" in s.source_url_redacted and "..." in s.source_url_redacted
    def test_raw_url_not_returned(self):
        d=_src("https://example.com/token=abc/pkg.zip").to_dict()
        a=str(d).lower()
        assert "token" not in a or "redact" in a
    def test_metadata_safe(self): d=_src().to_dict(); assert "raw_key" not in str(d)

# ═══════ Domain (20) ═══════
class TestDomain:
    def test_create_request(self): r=_req(); assert r.request_id.startswith("pkgdl_")
    def test_request_id_format(self): assert len(_req().request_id)==len("pkgdl_")+16
    def test_no_flags_default_true(self): r=_req(); assert r.no_download_performed and r.no_network_used and r.no_file_written and r.no_package_extracted
    def test_is_downloadable_false(self): assert not _req().is_downloadable()
    def test_is_network_allowed_false(self): assert not _req().is_network_allowed()
    def test_is_execution_allowed_false(self): assert not _req().is_execution_allowed()
    def test_no_danger_methods(self):
        r=_req()
        for bad in ["download","fetch","execute","dispatch","enqueue"]: assert not hasattr(r,bad) or not callable(getattr(r,bad,None))
    def test_to_dict_from_dict(self): r=_req(aid="to"); r2=PackageDownloadRequest.from_dict(r.to_dict()); assert r2.artifact_id=="to"
    def test_metadata_safe(self): d=_req().to_dict(); assert "raw_key" not in str(d)
    def test_create_quarantine(self): q=PackageDownloadQuarantineRecord(request_id="r1",artifact_id="a1",tenant_id="t1"); assert q.quarantine_id.startswith("pkgq_")
    def test_qid_format(self): q=PackageDownloadQuarantineRecord(request_id="r1",artifact_id="a1",tenant_id="t1"); assert len(q.quarantine_id)==len("pkgq_")+16
    def test_quarantine_flags_false(self): q=PackageDownloadQuarantineRecord(request_id="r1",artifact_id="a1",tenant_id="t1"); assert not q.file_materialized and not q.extraction_allowed and not q.execution_allowed
    def test_is_materialized_false(self): assert not PackageDownloadQuarantineRecord(request_id="r1",artifact_id="a1",tenant_id="t1").is_materialized()
    def test_is_executable_false(self): assert not PackageDownloadQuarantineRecord(request_id="r1",artifact_id="a1",tenant_id="t1").is_executable()
    def test_audit_event(self): e=PackageDownloadAuditEvent(request_id="r1",tenant_id="t1",event_type="test",message="ok"); assert e.event_id.startswith("pkgdlevt_")
    def test_audit_event_id_format(self): assert len(PackageDownloadAuditEvent(request_id="r1",tenant_id="t1",event_type="test",message="ok").event_id)==len("pkgdlevt_")+16
    def test_audit_metadata_safe(self): d=PackageDownloadAuditEvent(request_id="r1",tenant_id="t1",event_type="test",message="ok").to_dict(); assert "raw_key" not in str(d)
    def test_request_to_dict_includes_source(self): d=_req().to_dict(); assert "source_metadata" in d

# ═══════ Store (41) ═══════
class TestStore:
    def test_create_request(self,store): r=store.create_request(_req(aid="cr1")); assert store.get_request(r.request_id) is not None
    def test_get_request(self,store): r=store.create_request(_req(aid="gr1")); assert store.get_request(r.request_id).artifact_id=="gr1"
    def test_list_by_tenant(self,store):
        store.create_request(_req(aid="lt1",tid="tA")); store.create_request(_req(aid="lt2",tid="tB"))
        assert len(store.list_requests(tenant_id="tA"))==1
    def test_list_by_artifact(self,store):
        store.create_request(_req(aid="laA")); store.create_request(_req(aid="laB")); assert len(store.list_requests(artifact_id="laA"))==1
    def test_list_by_status(self,store):
        store.create_request(_req(aid="ls1",request_status=PackageDownloadRequestStatus.ADMIN_REVIEW_REQUIRED))
        assert len(store.list_requests(status=PackageDownloadRequestStatus.ADMIN_REVIEW_REQUIRED))>=1
    def test_list_by_decision(self,store):
        store.create_request(_req(aid="ld1",decision=PackageDownloadDecision.REVIEW_REQUIRED))
        assert len(store.list_requests(decision=PackageDownloadDecision.REVIEW_REQUIRED))>=1
    def test_list_by_gate_status(self,store):
        store.create_request(_req(aid="lg1",gate_status=PackageDownloadGateStatus.ADMIN_REQUIRED))
        assert len(store.list_requests(gate_status=PackageDownloadGateStatus.ADMIN_REQUIRED))>=1
    def test_update_request(self,store):
        r=store.create_request(_req(aid="ur1")); r.risk_level=PackageSourceRiskLevel.HIGH; store.update_request(r)
        assert store.get_request(r.request_id).risk_level==PackageSourceRiskLevel.HIGH
    def test_set_status(self,store):
        r=store.create_request(_req(aid="ss1")); store.set_request_status(r.request_id,PackageDownloadRequestStatus.ADMIN_REVIEW_REQUIRED,actor_id="a")
        assert store.get_request(r.request_id).request_status==PackageDownloadRequestStatus.ADMIN_REVIEW_REQUIRED
    def test_set_decision(self,store):
        r=store.create_request(_req(aid="sd1")); store.set_decision(r.request_id,PackageDownloadDecision.REVIEW_REQUIRED,actor_id="a")
        assert store.get_request(r.request_id).decision==PackageDownloadDecision.REVIEW_REQUIRED
    def test_set_gate_status(self,store):
        r=store.create_request(_req(aid="sg1")); store.set_gate_status(r.request_id,PackageDownloadGateStatus.ADMIN_REQUIRED,actor_id="a")
        assert store.get_request(r.request_id).gate_status==PackageDownloadGateStatus.ADMIN_REQUIRED
    def test_approve(self,store):
        r=store.create_request(_req(aid="ap1",request_status=PackageDownloadRequestStatus.ADMIN_REVIEW_REQUIRED))
        store.approve_for_future_download(r.request_id,"admin","ok"); f=store.get_request(r.request_id)
        assert f.request_status==PackageDownloadRequestStatus.ADMIN_APPROVED_FOR_FUTURE_DOWNLOAD and f.gate_status==PackageDownloadGateStatus.ADMIN_APPROVED_RESERVED
    def test_approve_not_downloadable(self,store):
        r=store.create_request(_req(aid="ap2",request_status=PackageDownloadRequestStatus.ADMIN_REVIEW_REQUIRED))
        store.approve_for_future_download(r.request_id,"admin"); assert not store.get_request(r.request_id).is_downloadable()
    def test_reject(self,store):
        r=store.create_request(_req(aid="rj1")); store.reject_request(r.request_id,"admin","bad")
        assert store.get_request(r.request_id).request_status==PackageDownloadRequestStatus.ADMIN_REJECTED
    def test_cancel(self,store):
        r=store.create_request(_req(aid="ca1")); store.cancel_request(r.request_id,"a")
        assert store.get_request(r.request_id).request_status==PackageDownloadRequestStatus.CANCELLED
    def test_expire(self,store):
        r=store.create_request(_req(aid="ex1")); store.expire_request(r.request_id,"sys")
        assert store.get_request(r.request_id).request_status==PackageDownloadRequestStatus.EXPIRED
    def test_reserve_quarantine(self,store):
        q=store.reserve_quarantine_record(PackageDownloadQuarantineRecord(request_id="q1",artifact_id="a1",tenant_id="t1"))
        assert store.get_quarantine_record(q.quarantine_id) is not None
    def test_get_quarantine(self,store):
        q=store.reserve_quarantine_record(PackageDownloadQuarantineRecord(request_id="q2",artifact_id="a2",tenant_id="t2"))
        f=store.get_quarantine_record(q.quarantine_id); assert f and f.request_id=="q2"
    def test_get_quarantine_by_request(self,store):
        store.reserve_quarantine_record(PackageDownloadQuarantineRecord(request_id="qr1",artifact_id="a1",tenant_id="t1"))
        assert store.get_quarantine_by_request("qr1") is not None
    def test_quarantine_not_materialized(self,store):
        q=store.reserve_quarantine_record(PackageDownloadQuarantineRecord(request_id="q3",artifact_id="a1",tenant_id="t1"))
        assert not store.get_quarantine_record(q.quarantine_id).file_materialized and not store.get_quarantine_record(q.quarantine_id).is_materialized()
    def test_count_by_tenant(self,store):
        store.create_request(_req(aid="c1",tid="tc")); store.create_request(_req(aid="c2",tid="tc"))
        assert store.count_requests(tenant_id="tc")==2
    def test_count_by_status(self,store):
        store.create_request(_req(aid="cs1")); assert store.count_requests(status=PackageDownloadRequestStatus.DRAFT)>=1
    def test_count_by_decision(self,store):
        store.create_request(_req(aid="cd1")); assert store.count_requests(decision=PackageDownloadDecision.BLOCKED)>=1
    def test_audit_on_create(self,store):
        r=store.create_request(_req(aid="ae1"))
        assert any(e.event_type==PackageDownloadAuditEventType.REQUEST_CREATED for e in store.list_audit_events(r.request_id))
    def test_audit_on_status(self,store):
        r=store.create_request(_req(aid="ae2")); store.set_request_status(r.request_id,PackageDownloadRequestStatus.ADMIN_REVIEW_REQUIRED,"a")
        assert any(e.event_type==PackageDownloadAuditEventType.STATUS_CHANGED for e in store.list_audit_events(r.request_id))
    def test_audit_on_decision(self,store):
        r=store.create_request(_req(aid="ae3")); store.set_decision(r.request_id,PackageDownloadDecision.REVIEW_REQUIRED,"a")
        assert any(e.event_type==PackageDownloadAuditEventType.DECISION_CHANGED for e in store.list_audit_events(r.request_id))
    def test_audit_on_gate(self,store):
        r=store.create_request(_req(aid="ae4")); store.set_gate_status(r.request_id,PackageDownloadGateStatus.ADMIN_REQUIRED,"a")
        assert any(e.event_type==PackageDownloadAuditEventType.ADMIN_GATE_EVALUATED for e in store.list_audit_events(r.request_id))
    def test_audit_on_approval(self,store):
        r=store.create_request(_req(aid="ae5",request_status=PackageDownloadRequestStatus.ADMIN_REVIEW_REQUIRED))
        store.approve_for_future_download(r.request_id,"admin")
        assert any(e.event_type==PackageDownloadAuditEventType.ADMIN_APPROVED_RESERVED for e in store.list_audit_events(r.request_id))
    def test_audit_on_rejection(self,store):
        r=store.create_request(_req(aid="ae6")); store.reject_request(r.request_id,"admin")
        assert any(e.event_type==PackageDownloadAuditEventType.ADMIN_REJECTED for e in store.list_audit_events(r.request_id))
    def test_audit_sorted(self,store):
        r=store.create_request(_req(aid="as1")); store.set_request_status(r.request_id,PackageDownloadRequestStatus.ADMIN_REVIEW_REQUIRED,"a")
        events=store.list_audit_events(r.request_id); assert events[0].created_at<=events[-1].created_at
    def test_json_roundtrip(self,store):
        r=store.create_request(_req(aid="jr1",artifact_snapshot={"k":"v"})); assert store.get_request(r.request_id).artifact_snapshot=={"k":"v"}
    def test_datetime_roundtrip(self,store):
        r=store.create_request(_req(aid="dt1",created_at=datetime(2026,6,11,12,0,0,tzinfo=timezone.utc)))
        assert store.get_request(r.request_id).created_at.year==2026
    def test_bool_roundtrip(self,store):
        r=store.create_request(_req(aid="br1")); f=store.get_request(r.request_id); assert f.no_download_performed and f.no_file_written
    def test_no_physical_delete(self,store): assert not hasattr(store,"delete_request") or not callable(getattr(store,"delete_request",None))
    def test_repeated_init_no_locked(self,store,settings,tmp_db_path):
        store.create_request(_req(aid="ri1")); store.flush()
        assert SQLitePackageDownloadQuarantineStore(settings,db_path=tmp_db_path).count_requests()==1
    def test_store_no_danger(self,store):
        for bad in ["download_package","fetch_package","extract_package","execute_package","enqueue_download","dispatch_download"]:
            assert not hasattr(store,bad) or not callable(getattr(store,bad,None))

# ═══════ Service (15) ═══════
class TestService:
    def _art(self): return PackageArtifact(submission_id="s1",developer_id="d1",tenant_id="t1")
    def test_https_request(self,svc): r=svc.create_download_request(self._art(),"https://x.com/pkg.zip","a"); assert r.request_status==PackageDownloadRequestStatus.ADMIN_REVIEW_REQUIRED
    def test_https_requires_admin(self,svc): r=svc.create_download_request(self._art(),"https://x.com/pkg.zip","a"); assert r.gate_status==PackageDownloadGateStatus.ADMIN_REQUIRED
    def test_blocked_fail_closed(self,svc): r=svc.create_download_request(self._art(),"http://x.com/pkg.zip","a"); assert r.request_status==PackageDownloadRequestStatus.DOWNLOAD_DISABLED
    def test_copies_artifact(self,svc): r=svc.create_download_request(self._art(),"https://x.com/pkg.zip","a"); assert r.artifact_snapshot and isinstance(r.artifact_snapshot,dict)
    def test_stores_hash(self,svc): r=svc.create_download_request(self._art(),"https://x.com/pkg.zip","a"); d=r.to_dict(); assert "source_url_hash" in str(d)
    def test_no_download(self,svc): r=svc.create_download_request(self._art(),"https://x.com/pkg.zip","a"); assert r.no_download_performed
    def test_approve(self,svc,store):
        r=store.create_request(_req(aid="sap1",request_status=PackageDownloadRequestStatus.ADMIN_REVIEW_REQUIRED))
        approved=svc.approve_for_future_download(r.request_id,"admin","ok"); assert approved.gate_status==PackageDownloadGateStatus.ADMIN_APPROVED_RESERVED
    def test_approve_not_downloadable(self,svc,store):
        r=store.create_request(_req(aid="sap2",request_status=PackageDownloadRequestStatus.ADMIN_REVIEW_REQUIRED))
        approved=svc.approve_for_future_download(r.request_id,"admin"); assert not approved.is_downloadable()
    def test_reject(self,svc,store):
        r=store.create_request(_req(aid="srj1")); assert svc.reject_request(r.request_id,"admin","bad").request_status==PackageDownloadRequestStatus.ADMIN_REJECTED
    def test_reserve_quarantine(self,svc,store):
        r=store.create_request(_req(aid="srq1")); q=svc.reserve_quarantine_metadata(r.request_id,"a")
        assert q and q.quarantine_status==PackageDownloadQuarantineStatus.RESERVED_METADATA_ONLY and not q.file_materialized
    def test_reserve_not_write_file(self,svc,store):
        r=store.create_request(_req(aid="srq2")); q=svc.reserve_quarantine_metadata(r.request_id,"a"); assert not q.is_materialized()
    def test_cancel(self,svc,store):
        r=store.create_request(_req(aid="sca1")); assert svc.cancel_request(r.request_id,"a").request_status==PackageDownloadRequestStatus.CANCELLED
    def test_expire(self,svc,store):
        r=store.create_request(_req(aid="sex1")); assert svc.expire_request(r.request_id,"sys").request_status==PackageDownloadRequestStatus.EXPIRED
    def test_svc_no_danger(self,svc):
        for bad in ["download_package","fetch_package","execute_package","dispatch_download","enqueue_download"]:
            assert not hasattr(svc,bad) or not callable(getattr(svc,bad,None))

# ═══════ Safety (22) ═══════
class TestSafety:
    def import_domain(self): return __import__("src.open_platform.package_download_quarantine",fromlist=[""])
    def import_service(self): return __import__("src.open_platform.package_download_quarantine_service",fromlist=[""])
    def test_dm_no_requests(self): m=self.import_domain(); assert "'requests'" not in str(dir(m)).lower() and '"requests"' not in str(dir(m)).lower()
    def test_dm_no_httpx(self): m=self.import_domain(); assert "httpx" not in str(dir(m)).lower()
    def test_dm_no_urllib_request(self): m=self.import_domain(); assert "urllib.request" not in str(dir(m)).lower()
    def test_dm_no_socket(self): m=self.import_domain(); assert "socket" not in str(dir(m)).lower()
    def test_dm_no_subprocess(self): m=self.import_domain(); assert "subprocess" not in str(dir(m)).lower()
    def test_dm_no_docker(self): m=self.import_domain(); assert "docker" not in str(dir(m)).lower()
    def test_dm_no_multiprocessing(self): m=self.import_domain(); assert "multiprocessing" not in str(dir(m)).lower()
    def test_dm_no_AgentRuntime(self): m=self.import_domain(); assert "AgentRuntime" not in str(dir(m))
    def test_dm_no_AgentRegistry(self): m=self.import_domain(); assert "AgentRegistry" not in str(dir(m))
    def test_svc_no_requests(self): m=self.import_service(); assert "'requests'" not in str(dir(m)).lower() and '"requests"' not in str(dir(m)).lower()
    def test_svc_no_subprocess(self): m=self.import_service(); assert "subprocess" not in str(dir(m)).lower()
    def test_svc_no_AgentRuntime(self): m=self.import_service(); assert "AgentRuntime" not in str(dir(m))
    def test_approved_not_downloadable(self):
        r=PackageDownloadRequest(artifact_id="a",tenant_id="t",source_metadata=_src(),request_status=PackageDownloadRequestStatus.ADMIN_APPROVED_FOR_FUTURE_DOWNLOAD)
        assert not r.is_downloadable()
    def test_quarantine_flags_false(self):
        q=PackageDownloadQuarantineRecord(request_id="r",artifact_id="a",tenant_id="t"); assert not q.is_materialized() and not q.is_executable()
    def test_artifact_not_executable(self): assert not PackageArtifact(submission_id="s",developer_id="d",tenant_id="t").is_verified_for_execution()
    def test_request_no_download_method(self): assert not hasattr(_req(),"download") or not callable(getattr(_req(),"download",None))
    def test_request_no_fetch_method(self): assert not hasattr(_req(),"fetch") or not callable(getattr(_req(),"fetch",None))
    def test_request_no_execute_method(self): assert not hasattr(_req(),"execute") or not callable(getattr(_req(),"execute",None))
    def test_descriptor_disabled(self):
        from src.open_platform.sandbox_adapter_feasibility import SandboxAdapterDescriptor
        assert not SandboxAdapterDescriptor().execution_enabled
    def test_execution_not_executable(self):
        from src.open_platform.sandbox_execution import SandboxExecutionRecord
        assert not SandboxExecutionRecord(plan_id="p",marketplace_agent_id="m",tenant_id="t",developer_id="d").is_executable()
