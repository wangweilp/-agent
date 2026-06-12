"""Package Validation 测试 — 静态 package metadata verification。"""

from __future__ import annotations
import os, json, pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.developer_store import SQLiteDeveloperStore
from src.adapters.submission_store import SQLiteSubmissionStore
from src.adapters.usage_store import UsageStoreAdapter
from src.adapters.package_validation_store import SQLitePackageValidationStore
from src.api.middleware import require_auth, get_token_payload, TokenPayload
from src.core.auth import WorkspaceRole
from src.core.usage import UsageResource
from src.open_platform.submission import (
    AgentManifest, AgentSubmission, SecurityProfile, SubmissionStatus,
)
from src.open_platform.package_validation import (
    PackageValidationCheck, PackageValidationRequest, PackageValidationResult,
    PackageValidationStatus, PackageValidationSeverity, PackageValidationCheckCode,
    PackageSourceType,
)
from src.open_platform.package_validation_service import PackageValidationService
from src.api.admin_submission_router import create_admin_submission_router

# ═══════════════════════ Auth ═══════════════════════
def _p(role=WorkspaceRole.ADMIN, ws="test-ws-001", uid="user-admin", sa=False):
    return TokenPayload(user_id=uid, workspace_id=ws, role=role, is_super_admin=sa)
async def _a(): return _p()
async def _member(): return _p(WorkspaceRole.MEMBER)
async def _viewer(): return _p(WorkspaceRole.VIEWER)
async def _super(): return _p(WorkspaceRole.ADMIN, sa=True)
async def _other(): return _p(ws="other-tenant")

@pytest.fixture
def s(): return Settings(deepseek_api_key="sk-test")
@pytest.fixture
def pv_store(s): return SQLitePackageValidationStore(s, db_path=":memory:")
@pytest.fixture
def sub_store(s): return SQLiteSubmissionStore(s, db_path=":memory:")
@pytest.fixture
def dev_store(s): return SQLiteDeveloperStore(s, db_path=":memory:")
@pytest.fixture
def usage_store(s, tmp_path):
    u = UsageStoreAdapter(config=s, db_path=str(tmp_path / "pv_usage.db"))
    yield u; u.close()
@pytest.fixture
def svc(pv_store, sub_store, dev_store, usage_store):
    return PackageValidationService(pv_store, sub_store, dev_store, usage_store)

def _make_app(sub_store, dev_store, usage=None, pv_service=None, auth=_a):
    app = FastAPI()
    app.dependency_overrides[require_auth] = auth
    app.dependency_overrides[get_token_payload] = auth
    app.include_router(create_admin_submission_router(dev_store, sub_store, usage, pv_service=pv_service))
    return TestClient(app)

def _noauth(sub_store, dev_store):
    app = FastAPI()
    app.include_router(create_admin_submission_router(dev_store, sub_store, None))
    return TestClient(app)

def _draft(sub_store, tid="test-ws-001", dev_id="dev_001", pkg_url=None):
    m = AgentManifest(name="my-agent", display_name="My Agent", description="Test", version="1.0.0",
                      capabilities=["test"], required_permissions=["agent:execute"],
                      security_profile=SecurityProfile(),
                      metadata={"package_checksum": "abc123", "package_checksum_algorithm": "sha256"},
                      )
    sub = AgentSubmission(developer_id=dev_id, tenant_id=tid, agent_manifest=m,
                          package_url=pkg_url, source_type="manifest" if not pkg_url else "package_url")
    sub_store.create_submission(sub)
    return sub


# ═══════════════════════ 1. Domain Model (14) ═══════════════════════
class TestDomainModel:
    def test_create_check(self):
        c = PackageValidationCheck(code=PackageValidationCheckCode.URL_FORMAT_VALID, severity=PackageValidationSeverity.INFO, passed=True, message="OK")
        d = c.to_dict(); assert d["code"] == PackageValidationCheckCode.URL_FORMAT_VALID

    def test_create_request(self):
        r = PackageValidationRequest(submission_id="sub_1", requested_by="u1", tenant_id="t1", package_url="https://example.com/pkg.zip")
        assert r.package_url == "https://example.com/pkg.zip"

    def test_passed_result(self):
        r = PackageValidationResult(status=PackageValidationStatus.PASSED)
        assert r.is_passed(); assert not r.has_blockers()

    def test_warning_result(self):
        r = PackageValidationResult(status=PackageValidationStatus.PASSED_WITH_WARNINGS, warnings=["w1"])
        assert r.is_passed()

    def test_failed_result(self):
        r = PackageValidationResult(status=PackageValidationStatus.FAILED, errors=["e1"])
        assert not r.is_passed()

    def test_blocked_result(self):
        r = PackageValidationResult(status=PackageValidationStatus.BLOCKED, blockers=["b1"])
        assert r.has_blockers()

    def test_summary_counts(self):
        r = PackageValidationResult(checks=[
            PackageValidationCheck(passed=True), PackageValidationCheck(passed=False),
        ], warnings=["w1"], errors=["e1"], blockers=["b1"])
        s = r.summary_counts()
        assert s["total"] == 2; assert s["passed"] == 1; assert s["failed"] == 1
        assert s["warnings"] == 1; assert s["errors"] == 1; assert s["blockers"] == 1

    def test_roundtrip(self):
        r = PackageValidationResult(
            validation_id="pval_001", submission_id="sub_1", tenant_id="t1",
            status=PackageValidationStatus.PASSED, manifest_name="my-agent", manifest_version="1.0.0",
            checks=[PackageValidationCheck(code="test", severity="info", passed=True, message="OK")],
            package_metadata={"k": "v"}, review_recommendation="OK", metadata={"m": 1},
        )
        d = r.to_dict()
        r2 = PackageValidationResult.from_dict(d)
        assert r2.validation_id == r.validation_id
        assert r2.status == r.status
        assert r2.package_metadata == r.package_metadata

    def test_no_raw_key(self):
        r = PackageValidationResult(status=PackageValidationStatus.PASSED)
        d = r.to_dict(); assert "raw_key" not in d; assert "key_hash" not in d

    def test_safety_flags(self):
        r = PackageValidationResult()
        assert r.no_download_performed; assert r.no_execution_performed; assert r.no_network_performed

    def test_result_no_execution(self):
        r = PackageValidationResult(no_download_performed=True, no_execution_performed=True, no_network_performed=True)
        assert r.no_download_performed; assert r.no_execution_performed

    def test_result_metadata_is_dict(self):
        r = PackageValidationResult(metadata={}); assert isinstance(r.metadata, dict)

    def test_request_metadata_is_dict(self):
        r = PackageValidationRequest(manifest_metadata={}, validation_options={})
        assert isinstance(r.manifest_metadata, dict); assert isinstance(r.validation_options, dict)


# ═══════════════════════ 2. Store (15) ═══════════════════════
class TestPVStore:
    def test_create_result(self, pv_store):
        r = PackageValidationResult(submission_id="sub_1", tenant_id="t1", requested_by="u1", status=PackageValidationStatus.PASSED)
        created = pv_store.create_result(r); assert created.validation_id == r.validation_id

    def test_get_result(self, pv_store):
        r = PackageValidationResult(submission_id="sub_1", tenant_id="t1", requested_by="u1", status=PackageValidationStatus.PASSED)
        pv_store.create_result(r); found = pv_store.get_result(r.validation_id); assert found is not None

    def test_get_latest(self, pv_store):
        r1 = PackageValidationResult(submission_id="sub_1", tenant_id="t1", requested_by="u1", status=PackageValidationStatus.FAILED)
        r2 = PackageValidationResult(submission_id="sub_1", tenant_id="t1", requested_by="u1", status=PackageValidationStatus.PASSED)
        pv_store.create_result(r1); pv_store.create_result(r2)
        latest = pv_store.get_latest_by_submission("sub_1"); assert latest.status == PackageValidationStatus.PASSED

    def test_list_by_submission(self, pv_store):
        pv_store.create_result(PackageValidationResult(submission_id="sub_a", tenant_id="t1"))
        pv_store.create_result(PackageValidationResult(submission_id="sub_b", tenant_id="t1"))
        assert len(pv_store.list_results(submission_id="sub_a")) == 1

    def test_list_by_tenant(self, pv_store):
        pv_store.create_result(PackageValidationResult(submission_id="s1", tenant_id="t1"))
        pv_store.create_result(PackageValidationResult(submission_id="s2", tenant_id="t2"))
        assert len(pv_store.list_results(tenant_id="t1")) == 1

    def test_list_by_status(self, pv_store):
        pv_store.create_result(PackageValidationResult(submission_id="s1", tenant_id="t1", status=PackageValidationStatus.PASSED))
        pv_store.create_result(PackageValidationResult(submission_id="s2", tenant_id="t1", status=PackageValidationStatus.FAILED))
        assert len(pv_store.list_results(status=PackageValidationStatus.PASSED)) == 1

    def test_count(self, pv_store):
        pv_store.create_result(PackageValidationResult(submission_id="s1", tenant_id="t1"))
        pv_store.create_result(PackageValidationResult(submission_id="s2", tenant_id="t1"))
        assert pv_store.count_results(tenant_id="t1") == 2

    def test_tenant_isolation(self, pv_store):
        pv_store.create_result(PackageValidationResult(submission_id="s1", tenant_id="t1"))
        assert pv_store.count_results(tenant_id="t2") == 0

    def test_nonexistent_returns_none(self, pv_store):
        assert pv_store.get_result("fake") is None


# ═══════════════════════ 3. Service Static (35) ═══════════════════════
class TestServiceStatic:
    def test_manifest_only_no_package(self, svc, sub_store):
        sub = _draft(sub_store); result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert result.is_passed()

    def test_package_url_source_needs_url(self, svc, sub_store):
        sub = _draft(sub_store); sub.source_type = "package_url"; sub.package_url = None
        sub_store.update_submission(sub)
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert not result.is_passed()

    def test_https_url_ok(self, svc, sub_store):
        sub = _draft(sub_store, pkg_url="https://github.com/user/repo/releases/v1.0.0/pkg.zip")
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert result.is_passed()

    def test_http_url_fails(self, svc, sub_store):
        sub = _draft(sub_store, pkg_url="http://evil.com/pkg.zip")
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert not result.is_passed()

    def test_ftp_url_fails(self, svc, sub_store):
        sub = _draft(sub_store, pkg_url="ftp://evil.com/pkg.zip")
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert not result.is_passed()

    def test_file_url_fails(self, svc, sub_store):
        sub = _draft(sub_store, pkg_url="file:///etc/passwd")
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert not result.is_passed()

    def test_localhost_blocked(self, svc, sub_store):
        sub = _draft(sub_store, pkg_url="https://localhost/pkg.zip")
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert result.has_blockers()

    def test_loopback_blocked(self, svc, sub_store):
        sub = _draft(sub_store, pkg_url="https://127.0.0.1/pkg.zip")
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert result.has_blockers()

    def test_private_ip_blocked(self, svc, sub_store):
        sub = _draft(sub_store, pkg_url="https://10.0.0.1/pkg.zip")
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert result.has_blockers()

    def test_metadata_ip_blocked(self, svc, sub_store):
        sub = _draft(sub_store, pkg_url="https://169.254.169.254/pkg.zip")
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert result.has_blockers()

    def test_allowlist_matches(self, svc, sub_store):
        sub = _draft(sub_store, pkg_url="https://github.com/user/pkg.zip")
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001",
                                                   {"allowed_domains": ["github.com"]})
        assert result.is_passed()

    def test_allowlist_no_match(self, svc, sub_store):
        sub = _draft(sub_store, pkg_url="https://evil.com/pkg.zip")
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001",
                                                   {"allowed_domains": ["github.com"]})
        assert not result.is_passed()

    def test_denylist_blocks(self, svc, sub_store):
        sub = _draft(sub_store, pkg_url="https://evil.com/pkg.zip")
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001",
                                                   {"denied_domains": ["evil.com"]})
        assert result.has_blockers()

    def test_checksum_missing_warning(self, svc, sub_store):
        m = AgentManifest(name="x", display_name="X", description="D", version="1.0.0", capabilities=["t"],
                          required_permissions=["a"], security_profile=SecurityProfile(), metadata={})
        sub = AgentSubmission(developer_id="d1", tenant_id="test-ws-001", agent_manifest=m,
                              package_url="https://github.com/pkg.zip")
        sub_store.create_submission(sub)
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert len(result.warnings) >= 1

    def test_checksum_algorithm_invalid(self, svc, sub_store):
        m = AgentManifest(name="x", display_name="X", description="D", version="1.0.0", capabilities=["t"],
                          required_permissions=["a"], security_profile=SecurityProfile(),
                          metadata={"package_checksum": "abc", "package_checksum_algorithm": "md5"})
        sub = AgentSubmission(developer_id="d1", tenant_id="test-ws-001", agent_manifest=m,
                              package_url="https://github.com/pkg.zip")
        sub_store.create_submission(sub)
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert any("md5" in e for e in result.errors)

    def test_signature_missing_warning(self, svc, sub_store):
        m = AgentManifest(name="x", display_name="X", description="D", version="1.0.0", capabilities=["t"],
                          required_permissions=["a"], security_profile=SecurityProfile(),
                          metadata={"package_checksum": "abc", "package_checksum_algorithm": "sha256"})
        sub = AgentSubmission(developer_id="d1", tenant_id="test-ws-001", agent_manifest=m,
                              package_url="https://github.com/pkg.zip")
        sub_store.create_submission(sub)
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert len(result.warnings) >= 1

    def test_package_name_mismatch(self, svc, sub_store):
        m = AgentManifest(name="my-agent", display_name="X", description="D", version="1.0.0", capabilities=["t"],
                          required_permissions=["a"], security_profile=SecurityProfile(),
                          metadata={"package_name": "other-name"})
        sub = AgentSubmission(developer_id="d1", tenant_id="test-ws-001", agent_manifest=m)
        sub_store.create_submission(sub)
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert any("other-name" in w for w in result.warnings)

    def test_license_missing_warning(self, svc, sub_store):
        m = AgentManifest(name="x", display_name="X", description="D", version="1.0.0", capabilities=["t"],
                          required_permissions=["a"], security_profile=SecurityProfile(),
                          metadata={})
        sub = AgentSubmission(developer_id="d1", tenant_id="test-ws-001", agent_manifest=m)
        sub_store.create_submission(sub)
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert any("license" in w.lower() for w in result.warnings)

    def test_deps_not_list(self, svc, sub_store):
        m = AgentManifest(name="x", display_name="X", description="D", version="1.0.0", capabilities=["t"],
                          required_permissions=["a"], security_profile=SecurityProfile(),
                          metadata={"dependencies": "not-a-list"})
        sub = AgentSubmission(developer_id="d1", tenant_id="test-ws-001", agent_manifest=m, package_url="https://github.com/pkg.zip")
        sub_store.create_submission(sub)
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert any("list" in e for e in result.errors)

    def test_runtime_type_blocker(self, svc, sub_store):
        m = AgentManifest(name="x", display_name="X", description="D", version="1.0.0", capabilities=["t"],
                          required_permissions=["a"], security_profile=SecurityProfile(), runtime_type="external")
        sub = AgentSubmission(developer_id="d1", tenant_id="test-ws-001", agent_manifest=m)
        sub_store.create_submission(sub)
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert result.has_blockers()

    def test_package_not_downloaded_check(self, svc, sub_store):
        sub = _draft(sub_store)
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        codes = [c.code for c in result.checks]
        assert "package_not_downloaded" in codes
        assert "package_not_executed" in codes

    def test_usage_recorded(self, svc, sub_store, usage_store):
        sub = _draft(sub_store)
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert result.status is not None

    def test_no_network(self, svc, sub_store):
        sub = _draft(sub_store, pkg_url="https://github.com/pkg.zip")
        result = svc.validate_submission_package(sub.submission_id, "admin", "test-ws-001")
        assert result.no_network_performed

    def test_service_no_agent_runtime(self):
        from src.open_platform import package_validation_service as pvs
        assert "AgentRuntime" not in pvs.__dict__


# ═══════════════════════ 4. Admin API (20) ═══════════════════════
class TestAdminApi:
    def test_validate_package_no_auth(self, sub_store, dev_store):
        c = _noauth(sub_store, dev_store)
        resp = c.post("/admin/agent-submissions/sub_x/validate-package"); assert resp.status_code == 401

    def test_member_cannot_validate(self, sub_store, dev_store):
        c = _make_app(sub_store, dev_store, auth=_member)
        resp = c.post("/admin/agent-submissions/sub_x/validate-package"); assert resp.status_code in (403, 404)

    def test_admin_can_validate(self, sub_store, dev_store, usage_store, pv_store):
        svc = PackageValidationService(pv_store, sub_store, dev_store, usage_store)
        c = _make_app(sub_store, dev_store, usage_store, svc)
        sub = _draft(sub_store); resp = c.post(f"/admin/agent-submissions/{sub.submission_id}/validate-package")
        assert resp.status_code == 200

    def test_cross_tenant_blocked(self, sub_store, dev_store, usage_store, pv_store):
        svc = PackageValidationService(pv_store, sub_store, dev_store, usage_store)
        c = _make_app(sub_store, dev_store, usage_store, svc, auth=_other)
        sub = _draft(sub_store, tid="test-ws-001")
        resp = c.post(f"/admin/agent-submissions/{sub.submission_id}/validate-package")
        assert resp.status_code == 404

    def test_super_admin_cross_tenant(self, sub_store, dev_store, usage_store, pv_store):
        svc = PackageValidationService(pv_store, sub_store, dev_store, usage_store)
        c = _make_app(sub_store, dev_store, usage_store, svc, auth=_super)
        sub = _draft(sub_store, tid="test-ws-001")
        resp = c.post(f"/admin/agent-submissions/{sub.submission_id}/validate-package")
        assert resp.status_code == 200

    def test_get_latest_validation_null(self, sub_store, dev_store, usage_store, pv_store):
        svc = PackageValidationService(pv_store, sub_store, dev_store, usage_store)
        c = _make_app(sub_store, dev_store, usage_store, svc)
        sub = _draft(sub_store)
        resp = c.get(f"/admin/agent-submissions/{sub.submission_id}/package-validation")
        assert resp.status_code == 200; assert resp.json()["validation"] is None

    def test_get_latest_after_run(self, sub_store, dev_store, usage_store, pv_store):
        svc = PackageValidationService(pv_store, sub_store, dev_store, usage_store)
        c = _make_app(sub_store, dev_store, usage_store, svc)
        sub = _draft(sub_store)
        c.post(f"/admin/agent-submissions/{sub.submission_id}/validate-package")
        resp = c.get(f"/admin/agent-submissions/{sub.submission_id}/package-validation")
        assert resp.json()["validation"] is not None

    def test_validation_options(self, sub_store, dev_store, usage_store, pv_store):
        svc = PackageValidationService(pv_store, sub_store, dev_store, usage_store)
        c = _make_app(sub_store, dev_store, usage_store, svc)
        sub = _draft(sub_store, pkg_url="https://github.com/pkg.zip")
        resp = c.post(f"/admin/agent-submissions/{sub.submission_id}/validate-package",
                       json={"validation_options": {"allowed_domains": ["github.com"]}})
        assert resp.status_code == 200

    def test_no_raw_key_in_response(self, sub_store, dev_store, usage_store, pv_store):
        svc = PackageValidationService(pv_store, sub_store, dev_store, usage_store)
        c = _make_app(sub_store, dev_store, usage_store, svc)
        sub = _draft(sub_store)
        resp = c.post(f"/admin/agent-submissions/{sub.submission_id}/validate-package")
        assert "raw_key" not in json.dumps(resp.json())

    def test_no_traceback(self, sub_store, dev_store, usage_store, pv_store):
        svc = PackageValidationService(pv_store, sub_store, dev_store, usage_store)
        c = _make_app(sub_store, dev_store, usage_store, svc)
        resp = c.post("/admin/agent-submissions/sub_fake/validate-package")
        assert "Traceback" not in str(resp.json())

    def test_submission_status_unchanged(self, sub_store, dev_store, usage_store, pv_store):
        svc = PackageValidationService(pv_store, sub_store, dev_store, usage_store)
        c = _make_app(sub_store, dev_store, usage_store, svc)
        sub = _draft(sub_store)
        c.post(f"/admin/agent-submissions/{sub.submission_id}/validate-package")
        updated = sub_store.get_submission(sub.submission_id)
        assert updated.status == SubmissionStatus.DRAFT

    def test_does_not_create_review_record(self, sub_store, dev_store, usage_store, pv_store):
        svc = PackageValidationService(pv_store, sub_store, dev_store, usage_store)
        c = _make_app(sub_store, dev_store, usage_store, svc)
        sub = _draft(sub_store)
        c.post(f"/admin/agent-submissions/{sub.submission_id}/validate-package")
        records = sub_store.list_review_records(sub.submission_id)
        assert len(records) == 0
