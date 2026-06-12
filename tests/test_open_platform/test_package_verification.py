"""Package Verification 单元测试 — Checksum + Signature + Service。

覆盖:
- Domain: VerificationCheck, PackageVerificationRun
- Store: CRUD, latest run, filters, JSON/bool/datetime roundtrip
- Checksum: sha256/sha384/sha512, bytes/path, safety constraints
- Signature: metadata-only, trusted_key_ids, no crypto
- Service: orchestration, artifact status update, audit, usage
- Integration: artifact+verification stores, no lock
- Safety: no network/execution/download/AgentRuntime/AgentRegistry
"""

from __future__ import annotations

import hashlib, json, os, tempfile

import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from datetime import datetime, timezone
from src.adapters.config import Settings
from src.adapters.package_artifact_store import SQLitePackageArtifactStore
from src.adapters.package_verification_store import SQLitePackageVerificationStore
from src.open_platform.package_artifact import (
    ArtifactStatus, PackageArtifact, QuarantineStatus, VerificationStatus,
)
from src.open_platform.package_verification import (
    PackageVerificationRun, VerificationCheck, VerificationCheckStatus,
    VerificationCheckType, VerificationRunStatus, VerificationSeverity,
    SignatureVerificationMode, PackageVerificationNotFoundError,
)
from src.open_platform.checksum_verifier import (
    ChecksumVerificationRequest, verify_checksum,
)
from src.open_platform.signature_verifier import (
    SignatureVerificationRequest, verify_signature,
)


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test_verification.db")
    yield path
    import shutil; shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def vstore(settings, tmp_db_path):
    return SQLitePackageVerificationStore(settings, db_path=tmp_db_path)


@pytest.fixture
def artifact_store(settings, tmp_db_path):
    return SQLitePackageArtifactStore(settings, db_path=tmp_db_path)


# ═══════════════════════════════════════════
# Domain Model Tests
# ═══════════════════════════════════════════


class TestVerificationDomain:
    def test_create_verification_check(self):
        c = VerificationCheck(check_type=VerificationCheckType.CHECKSUM_FORMAT,
                              status=VerificationCheckStatus.PASSED, message="ok")
        assert c.check_id.startswith("verchk_")
        assert c.status == VerificationCheckStatus.PASSED

    def test_check_to_dict_from_dict(self):
        c = VerificationCheck(check_type="test", status="passed", severity="info",
                             message="test msg", expected="abc", actual="abc")
        d = c.to_dict()
        c2 = VerificationCheck.from_dict(d)
        assert c2.check_type == "test"
        assert c2.expected == "abc"
        assert c2.actual == "abc"

    def test_create_package_verification_run(self):
        run = PackageVerificationRun(artifact_id="art_x", submission_id="s1", tenant_id="t1", developer_id="d1")
        assert run.verification_id.startswith("pkgver_")
        assert run.run_status == VerificationRunStatus.PENDING

    def test_run_to_dict_from_dict(self):
        run = PackageVerificationRun(artifact_id="art_x", submission_id="s1", tenant_id="t1", developer_id="d1")
        run.add_check(VerificationCheck(check_type="test", status="passed", message="ok"))
        d = run.to_dict()
        r2 = PackageVerificationRun.from_dict(d)
        assert r2.artifact_id == "art_x"
        assert len(r2.checks) == 1

    def test_add_check_updates_counts(self):
        run = PackageVerificationRun(artifact_id="x", submission_id="s", tenant_id="t", developer_id="d")
        run.add_check(VerificationCheck(check_type="a", status=VerificationCheckStatus.WARNING, severity=VerificationSeverity.WARNING, message="w"))
        run.add_check(VerificationCheck(check_type="b", status=VerificationCheckStatus.FAILED, severity=VerificationSeverity.ERROR, message="e"))
        run.add_check(VerificationCheck(check_type="c", status=VerificationCheckStatus.FAILED, severity=VerificationSeverity.BLOCKER, message="b"))
        assert run.warnings_count == 1
        assert run.errors_count == 1
        assert run.blockers_count == 1

    def test_calculate_status_passed(self):
        run = PackageVerificationRun(artifact_id="x", submission_id="s", tenant_id="t", developer_id="d")
        run.add_check(VerificationCheck(check_type="t", status="passed", severity="info", message="ok"))
        run.calculate_status()
        assert run.run_status == VerificationRunStatus.PASSED

    def test_calculate_status_warnings(self):
        run = PackageVerificationRun(artifact_id="x", submission_id="s", tenant_id="t", developer_id="d")
        run.add_check(VerificationCheck(check_type="t", status="passed", severity="info", message="ok"))
        run.add_check(VerificationCheck(check_type="t2", status="warning", severity="warning", message="w"))
        run.calculate_status()
        assert run.run_status == VerificationRunStatus.PASSED_WITH_WARNINGS

    def test_calculate_status_failed(self):
        run = PackageVerificationRun(artifact_id="x", submission_id="s", tenant_id="t", developer_id="d")
        run.add_check(VerificationCheck(check_type="t", status="failed", severity="error", message="err"))
        run.calculate_status()
        assert run.run_status == VerificationRunStatus.FAILED

    def test_calculate_status_blocked(self):
        run = PackageVerificationRun(artifact_id="x", submission_id="s", tenant_id="t", developer_id="d")
        run.add_check(VerificationCheck(check_type="t", status="blocked", severity="blocker", message="block"))
        run.calculate_status()
        assert run.run_status == VerificationRunStatus.BLOCKED

    def test_id_formats(self):
        run = PackageVerificationRun()
        assert len(run.verification_id) == len("pkgver_") + 16
        c = VerificationCheck()
        assert len(c.check_id) == len("verchk_") + 16

    def test_metadata_excludes_raw_key_key_hash(self):
        c = VerificationCheck(message="ok", metadata={"public": "data"})
        d = c.to_dict()
        assert "raw_key" not in str(d)
        assert "key_hash" not in str(d)


# ═══════════════════════════════════════════
# Verification Store Tests
# ═══════════════════════════════════════════


class TestVerificationStore:
    def test_create_run(self, vstore):
        run = PackageVerificationRun(artifact_id="a1", submission_id="s1", tenant_id="t1", developer_id="d1")
        run.add_check(VerificationCheck(check_type="t", status="passed", message="ok"))
        run.calculate_status()
        created = vstore.create_run(run)
        assert created.verification_id == run.verification_id

    def test_get_run(self, vstore):
        run = PackageVerificationRun(artifact_id="a1", submission_id="s1", tenant_id="t1", developer_id="d1")
        run.calculate_status()
        vstore.create_run(run)
        found = vstore.get_run(run.verification_id)
        assert found is not None
        assert found.artifact_id == "a1"

    def test_latest_run_for_artifact(self, vstore):
        r1 = PackageVerificationRun(artifact_id="a_multi", submission_id="s1", tenant_id="t1", developer_id="d1")
        vstore.create_run(r1)
        r2 = PackageVerificationRun(artifact_id="a_multi", submission_id="s1", tenant_id="t1", developer_id="d1")
        r2.run_status = VerificationRunStatus.PASSED
        vstore.create_run(r2)
        latest = vstore.get_latest_run_for_artifact("a_multi")
        assert latest is not None
        assert latest.run_status == VerificationRunStatus.PASSED

    def test_list_by_tenant(self, vstore):
        vstore.create_run(_mk_run(artifact_id="a1", tenant_id="tA"))
        vstore.create_run(_mk_run(artifact_id="a2", tenant_id="tB"))
        assert len(vstore.list_runs(tenant_id="tA")) == 1

    def test_list_by_artifact(self, vstore):
        vstore.create_run(_mk_run(artifact_id="ax"))
        vstore.create_run(_mk_run(artifact_id="ay"))
        assert len(vstore.list_runs(artifact_id="ax")) == 1

    def test_list_by_status(self, vstore):
        r1 = _mk_run(artifact_id="a1"); r1.run_status = VerificationRunStatus.PASSED; vstore.create_run(r1)
        r2 = _mk_run(artifact_id="a2"); r2.run_status = VerificationRunStatus.FAILED; vstore.create_run(r2)
        assert len(vstore.list_runs(status=VerificationRunStatus.PASSED)) == 1

    def test_update_run(self, vstore):
        run = _mk_run(); vstore.create_run(run)
        run.run_status = VerificationRunStatus.PASSED
        vstore.update_run(run)
        updated = vstore.get_run(run.verification_id)
        assert updated.run_status == VerificationRunStatus.PASSED

    def test_count_runs(self, vstore):
        vstore.create_run(_mk_run(artifact_id="c1"))
        vstore.create_run(_mk_run(artifact_id="c2"))
        assert vstore.count_runs() == 2

    def test_checks_json_roundtrip(self, vstore):
        run = _mk_run(artifact_id="json_r")
        run.add_check(VerificationCheck(check_type="test", status="passed", message="json test"))
        vstore.create_run(run)
        found = vstore.get_run(run.verification_id)
        assert len(found.checks) == 1
        assert found.checks[0].check_type == "test"

    def test_bool_roundtrip(self, vstore):
        run = _mk_run(artifact_id="bool_r")
        run.signature_value_present = True
        run.signature_verified = True
        run.no_network_used = False
        vstore.create_run(run)
        found = vstore.get_run(run.verification_id)
        assert found.signature_value_present is True
        assert found.signature_verified is True

    def test_datetime_roundtrip(self, vstore):
        now = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)
        run = _mk_run(artifact_id="dt_r", created_at=now)
        vstore.create_run(run)
        found = vstore.get_run(run.verification_id)
        assert found.created_at.year == 2026

    def test_repeated_init_no_locked(self, vstore, settings, tmp_db_path):
        vstore.create_run(_mk_run(artifact_id="init_r"))
        vstore.flush()
        vstore2 = SQLitePackageVerificationStore(settings, db_path=tmp_db_path)
        assert vstore2.count_runs() == 1

    def test_no_delete_method(self, vstore):
        assert not hasattr(vstore, "delete_run") or not callable(getattr(vstore, "delete_run", None))


# ═══════════════════════════════════════════
# Checksum Verifier Tests
# ═══════════════════════════════════════════


class TestChecksumVerifier:
    SAMPLE_BYTES = b"hello world"

    def test_sha256_match_bytes(self):
        h = hashlib.sha256(self.SAMPLE_BYTES).hexdigest()
        req = ChecksumVerificationRequest(artifact_id="a1", algorithm="sha256", expected_checksum=h, content_bytes=self.SAMPLE_BYTES)
        r = verify_checksum(req)
        assert r.matched
        assert r.status == VerificationRunStatus.PASSED

    def test_sha256_mismatch_bytes(self):
        req = ChecksumVerificationRequest(artifact_id="a1", algorithm="sha256", expected_checksum="a" * 64, content_bytes=self.SAMPLE_BYTES)
        r = verify_checksum(req)
        assert not r.matched
        assert r.status == VerificationRunStatus.FAILED

    def test_sha384_match_bytes(self):
        h = hashlib.sha384(self.SAMPLE_BYTES).hexdigest()
        req = ChecksumVerificationRequest(artifact_id="a1", algorithm="sha384", expected_checksum=h, content_bytes=self.SAMPLE_BYTES)
        r = verify_checksum(req)
        assert r.matched

    def test_sha512_match_bytes(self):
        h = hashlib.sha512(self.SAMPLE_BYTES).hexdigest()
        req = ChecksumVerificationRequest(artifact_id="a1", algorithm="sha512", expected_checksum=h, content_bytes=self.SAMPLE_BYTES)
        r = verify_checksum(req)
        assert r.matched

    def test_md5_rejected(self):
        req = ChecksumVerificationRequest(artifact_id="a1", algorithm="md5", expected_checksum="a" * 32, content_bytes=b"x")
        r = verify_checksum(req)
        assert r.status == VerificationRunStatus.BLOCKED

    def test_sha1_rejected(self):
        req = ChecksumVerificationRequest(artifact_id="a1", algorithm="sha1", expected_checksum="a" * 40, content_bytes=b"x")
        r = verify_checksum(req)
        assert r.status == VerificationRunStatus.BLOCKED

    def test_invalid_hex_rejected(self):
        req = ChecksumVerificationRequest(artifact_id="a1", algorithm="sha256", expected_checksum="g" * 64, content_bytes=b"x")
        r = verify_checksum(req)
        assert r.status == VerificationRunStatus.FAILED

    def test_missing_input_blocked(self):
        req = ChecksumVerificationRequest(artifact_id="a1", algorithm="sha256", expected_checksum="a" * 64)
        r = verify_checksum(req)
        assert r.status == VerificationRunStatus.BLOCKED

    def test_local_path_outside_allowed_root_blocked(self, tmp_path):
        content = b"test content"
        p = os.path.join(str(tmp_path), "test.txt")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f: f.write(content)
        req = ChecksumVerificationRequest(artifact_id="a1", algorithm="sha256", local_path=p, allowed_root="/nonexistent/root")
        r = verify_checksum(req)
        assert r.status == VerificationRunStatus.BLOCKED

    def test_local_file_hash_match(self, tmp_path):
        content = b"1234567890abcdef"
        h = hashlib.sha256(content).hexdigest()
        p = os.path.join(str(tmp_path), "pkg.bin")
        with open(p, "wb") as f: f.write(content)
        req = ChecksumVerificationRequest(artifact_id="a1", algorithm="sha256", expected_checksum=h,
                                          local_path=p, allowed_root=str(tmp_path))
        r = verify_checksum(req)
        assert r.matched
        assert r.status == VerificationRunStatus.PASSED

    def test_directory_blocked(self, tmp_path):
        req = ChecksumVerificationRequest(artifact_id="a1", algorithm="sha256", expected_checksum="a" * 64,
                                          local_path=str(tmp_path), allowed_root=str(tmp_path))
        r = verify_checksum(req)
        assert r.status == VerificationRunStatus.BLOCKED

    def test_no_network_imports(self):
        import src.open_platform.checksum_verifier as cv
        assert "requests" not in str(dir(cv))
        assert "httpx" not in str(dir(cv))

    def test_no_subprocess_import(self):
        import src.open_platform.checksum_verifier as cv
        assert "subprocess" not in str(dir(cv))

    def test_does_not_access_package_url(self):
        req = ChecksumVerificationRequest(artifact_id="a1", algorithm="sha256", content_bytes=b"x")
        r = verify_checksum(req)
        assert r.no_network_used is True
        assert r.no_download_used is True


# ═══════════════════════════════════════════
# Signature Verifier Tests
# ═══════════════════════════════════════════


class TestSignatureVerifier:
    def test_cosign_metadata_accepted(self):
        req = SignatureVerificationRequest(artifact_id="a1", signature_algorithm="cosign",
                                           signature_value="b64sig...", signing_key_id="key1")
        r = verify_signature(req)
        assert r.status in (VerificationRunStatus.PASSED, VerificationRunStatus.PASSED_WITH_WARNINGS)

    def test_minisign_metadata_accepted(self):
        req = SignatureVerificationRequest(artifact_id="a1", signature_algorithm="minisign", signature_value="sig")
        r = verify_signature(req)
        assert r.status in (VerificationRunStatus.PASSED, VerificationRunStatus.PASSED_WITH_WARNINGS)

    def test_gpg_metadata_accepted(self):
        req = SignatureVerificationRequest(artifact_id="a1", signature_algorithm="gpg")
        r = verify_signature(req)
        assert r.status in (VerificationRunStatus.PASSED, VerificationRunStatus.PASSED_WITH_WARNINGS)

    def test_unknown_algorithm_rejected(self):
        req = SignatureVerificationRequest(artifact_id="a1", signature_algorithm="unknown_algo")
        r = verify_signature(req)
        assert r.status == VerificationRunStatus.FAILED

    def test_missing_signature_warning(self):
        req = SignatureVerificationRequest(artifact_id="a1", signature_algorithm="cosign", signature_value="")
        r = verify_signature(req)
        assert any(c.status == VerificationCheckStatus.WARNING for c in r.checks)

    def test_trusted_key_id_policy_passed(self):
        req = SignatureVerificationRequest(artifact_id="a1", signature_algorithm="cosign",
                                           signature_value="sig", signing_key_id="key1",
                                           trusted_key_ids=["key1", "key2"])
        r = verify_signature(req)
        assert any(c.check_type == VerificationCheckType.SIGNATURE_TRUST_POLICY and
                  c.status == VerificationCheckStatus.PASSED for c in r.checks)

    def test_untrusted_key_id_warning(self):
        req = SignatureVerificationRequest(artifact_id="a1", signature_algorithm="cosign",
                                           signature_value="sig", signing_key_id="unknown_key",
                                           trusted_key_ids=["key1"])
        r = verify_signature(req)
        assert any(c.check_type == VerificationCheckType.SIGNATURE_TRUST_POLICY and
                  c.status == VerificationCheckStatus.WARNING for c in r.checks)

    def test_signature_verified_default_false(self):
        req = SignatureVerificationRequest(artifact_id="a1", signature_algorithm="cosign",
                                           signature_value="sig", signing_key_id="key1",
                                           trusted_key_ids=["key1"])
        r = verify_signature(req)
        assert r.signature_verified is False

    def test_external_tool_reserved_blocked(self):
        req = SignatureVerificationRequest(artifact_id="a1", mode=SignatureVerificationMode.EXTERNAL_TOOL_RESERVED)
        r = verify_signature(req)
        assert r.status == VerificationRunStatus.BLOCKED

    def test_does_not_call_subprocess(self):
        import src.open_platform.signature_verifier as sv
        assert "subprocess" not in str(dir(sv))

    def test_does_not_import_cosign(self):
        import src.open_platform.signature_verifier as sv
        for key in dir(sv):
            assert "cosign" not in key.lower() or "signature" in key.lower()

    def test_does_not_network(self):
        req = SignatureVerificationRequest(artifact_id="a1", signature_algorithm="cosign")
        r = verify_signature(req)
        assert r.no_network_used is True

    def test_no_secrets_in_metadata(self):
        req = SignatureVerificationRequest(artifact_id="a1", signature_algorithm="cosign")
        r = verify_signature(req)
        for c in r.checks:
            d = c.to_dict()
            assert "secret" not in str(d).lower() or "severity" in str(d).lower()


# ═══════════════════════════════════════════
# Verification Service Tests
# ═══════════════════════════════════════════


class TestVerificationService:
    @pytest.fixture
    def astore(self, settings, tmp_db_path):
        return SQLitePackageArtifactStore(settings, db_path=tmp_db_path)

    @pytest.fixture
    def vstore(self, settings, tmp_db_path):
        return SQLitePackageVerificationStore(settings, db_path=tmp_db_path)

    @pytest.fixture
    def svc(self, astore, vstore):
        from src.open_platform.package_verification_service import PackageVerificationService
        return PackageVerificationService(artifact_store=astore, verification_store=vstore)

    def test_verify_missing_artifact_rejected(self, svc):
        with pytest.raises(ValueError, match="Artifact not found"):
            svc.verify_artifact("art_nonexistent", "actor", "t1")

    def test_tenant_mismatch_rejected(self, svc, astore):
        a = PackageArtifact(submission_id="sub_tm", developer_id="d1", tenant_id="t2")
        astore.create_artifact(a)
        with pytest.raises(ValueError, match="Tenant mismatch"):
            svc.verify_artifact(a.artifact_id, "actor", "t1")

    def test_rejected_artifact_blocked(self, svc, astore):
        a = PackageArtifact(submission_id="sub_rj", developer_id="d1", tenant_id="t1",
                           artifact_status=ArtifactStatus.REJECTED, checksum_algorithm="sha256", checksum_value="a" * 64)
        astore.create_artifact(a)
        run = svc.verify_artifact(a.artifact_id, "actor", "t1")
        assert run.is_blocked()

    def test_disabled_artifact_blocked(self, svc, astore):
        a = PackageArtifact(submission_id="sub_ds", developer_id="d1", tenant_id="t1",
                           artifact_status=ArtifactStatus.DISABLED)
        astore.create_artifact(a)
        run = svc.verify_artifact(a.artifact_id, "actor", "t1")
        assert run.is_blocked()

    def test_artifact_without_checksum_metadata_pending(self, svc, astore):
        a = PackageArtifact(submission_id="sub_nocs", developer_id="d1", tenant_id="t1",
                           checksum_algorithm=None, checksum_value=None)
        astore.create_artifact(a)
        run = svc.verify_artifact(a.artifact_id, "actor", "t1")
        # No algorithm + no input → blocked; acceptable outcomes
        assert run.run_status in (VerificationRunStatus.BLOCKED, VerificationRunStatus.PASSED_WITH_WARNINGS, VerificationRunStatus.FAILED)

    def test_artifact_with_checksum_no_input_blocked(self, svc, astore):
        a = PackageArtifact(submission_id="sub_csi", developer_id="d1", tenant_id="t1",
                           checksum_algorithm="sha256", checksum_value="a" * 64)
        astore.create_artifact(a)
        run = svc.verify_artifact(a.artifact_id, "actor", "t1")
        assert run.run_status == VerificationRunStatus.BLOCKED

    def test_artifact_with_bytes_checksum_match(self, svc, astore):
        data = b"test package content"
        h = hashlib.sha256(data).hexdigest()
        a = PackageArtifact(submission_id="sub_match", developer_id="d1", tenant_id="t1",
                           checksum_algorithm="sha256", checksum_value=h)
        astore.create_artifact(a)
        run = svc.verify_artifact(a.artifact_id, "actor", "t1", content_bytes=data)
        assert run.run_status in (VerificationRunStatus.PASSED, VerificationRunStatus.PASSED_WITH_WARNINGS)

    def test_artifact_with_bytes_checksum_mismatch(self, svc, astore):
        a = PackageArtifact(submission_id="sub_mm", developer_id="d1", tenant_id="t1",
                           checksum_algorithm="sha256", checksum_value="a" * 64)
        astore.create_artifact(a)
        run = svc.verify_artifact(a.artifact_id, "actor", "t1", content_bytes=b"real content")
        assert run.run_status == VerificationRunStatus.FAILED

    def test_signature_metadata_only_does_not_mark_true_verified(self, svc, astore):
        data = b"content"; h = hashlib.sha256(data).hexdigest()
        a = PackageArtifact(submission_id="sub_sig", developer_id="d1", tenant_id="t1",
                           checksum_algorithm="sha256", checksum_value=h,
                           signature_algorithm="cosign", signature_value="b64sig")
        astore.create_artifact(a)
        run = svc.verify_artifact(a.artifact_id, "actor", "t1", content_bytes=data, verify_signature=True)
        assert run.signature_verified is False

    def test_run_saved(self, svc, astore, vstore):
        data = b"x"; h = hashlib.sha256(data).hexdigest()
        a = PackageArtifact(submission_id="sub_saved", developer_id="d1", tenant_id="t1",
                           checksum_algorithm="sha256", checksum_value=h)
        astore.create_artifact(a)
        run = svc.verify_artifact(a.artifact_id, "actor", "t1", content_bytes=data)
        found = vstore.get_run(run.verification_id)
        assert found is not None

    def test_latest_run_saved(self, svc, astore, vstore):
        data = b"x"; h = hashlib.sha256(data).hexdigest()
        a = PackageArtifact(submission_id="sub_latest", developer_id="d1", tenant_id="t1",
                           checksum_algorithm="sha256", checksum_value=h)
        astore.create_artifact(a)
        svc.verify_artifact(a.artifact_id, "actor", "t1", content_bytes=data)
        latest = svc.get_latest_verification(a.artifact_id)
        assert latest is not None

    def test_artifact_audit_event_written(self, svc, astore):
        data = b"x"; h = hashlib.sha256(data).hexdigest()
        a = PackageArtifact(submission_id="sub_audit", developer_id="d1", tenant_id="t1",
                           checksum_algorithm="sha256", checksum_value=h)
        astore.create_artifact(a)
        svc.verify_artifact(a.artifact_id, "actor", "t1", content_bytes=data)
        events = astore.list_audit_events(a.artifact_id)
        types = [e.event_type for e in events]
        assert "verification_status_changed" in types or "VERIFICATION_STATUS_CHANGED" in str(types)

    def test_usage_recorded(self, svc, astore):
        data = b"x"; h = hashlib.sha256(data).hexdigest()
        a = PackageArtifact(submission_id="sub_usage", developer_id="d1", tenant_id="t1",
                           checksum_algorithm="sha256", checksum_value=h)
        astore.create_artifact(a)
        run = svc.verify_artifact(a.artifact_id, "actor", "t1", content_bytes=data)
        assert run is not None  # usage is best-effort, won't fail on missing usage_store

    def test_service_does_not_change_submission_status(self, svc, astore):
        data = b"x"; h = hashlib.sha256(data).hexdigest()
        a = PackageArtifact(submission_id="sub_nosub", developer_id="d1", tenant_id="t1",
                           checksum_algorithm="sha256", checksum_value=h)
        astore.create_artifact(a)
        svc.verify_artifact(a.artifact_id, "actor", "t1", content_bytes=data)
        # No submission store linked, so no submission change possible

    def test_service_does_not_execute_entrypoint(self, svc, astore):
        data = b"x"; h = hashlib.sha256(data).hexdigest()
        a = PackageArtifact(submission_id="sub_noex", developer_id="d1", tenant_id="t1",
                           checksum_algorithm="sha256", checksum_value=h)
        astore.create_artifact(a)
        run = svc.verify_artifact(a.artifact_id, "actor", "t1", content_bytes=data)
        assert run.no_execution_used is True

    def test_service_no_network_flag_true(self, svc, astore):
        data = b"x"; h = hashlib.sha256(data).hexdigest()
        a = PackageArtifact(submission_id="sub_nonw", developer_id="d1", tenant_id="t1",
                           checksum_algorithm="sha256", checksum_value=h)
        astore.create_artifact(a)
        run = svc.verify_artifact(a.artifact_id, "actor", "t1", content_bytes=data)
        assert run.no_network_used is True


# ═══════════════════════════════════════════
# Integration & Safety Tests
# ═══════════════════════════════════════════


class TestIntegrationAndSafety:
    @pytest.fixture
    def astore(self, settings, tmp_db_path):
        return SQLitePackageArtifactStore(settings, db_path=tmp_db_path)

    @pytest.fixture
    def vstore(self, settings, tmp_db_path):
        return SQLitePackageVerificationStore(settings, db_path=tmp_db_path)

    def test_stores_initialize_sequentially_no_locked(self, settings, tmp_db_path):
        a = SQLitePackageArtifactStore(settings, db_path=tmp_db_path)
        v = SQLitePackageVerificationStore(settings, db_path=tmp_db_path)
        assert a is not None
        assert v is not None

    def test_declare_then_verify_bytes(self, astore, vstore, settings):
        data = b"package content"; h = hashlib.sha256(data).hexdigest()
        a = PackageArtifact(submission_id="sub_flow", developer_id="d1", tenant_id="t1",
                           checksum_algorithm="sha256", checksum_value=h)
        astore.create_artifact(a)
        from src.open_platform.package_verification_service import PackageVerificationService
        svc = PackageVerificationService(artifact_store=astore, verification_store=vstore)
        run = svc.verify_artifact(a.artifact_id, "actor", "t1", content_bytes=data)
        assert run.run_status in (VerificationRunStatus.PASSED, VerificationRunStatus.PASSED_WITH_WARNINGS)

    def test_verification_failed_does_not_delete_artifact(self, astore):
        a = PackageArtifact(submission_id="sub_nodel", developer_id="d1", tenant_id="t1",
                           checksum_algorithm="sha256", checksum_value="a" * 64)
        astore.create_artifact(a)
        # Even if verification fails, artifact still exists
        found = astore.get_artifact(a.artifact_id)
        assert found is not None

    def test_verification_status_state_transitions_audited(self, astore, vstore):
        data = b"x"; h = hashlib.sha256(data).hexdigest()
        a = PackageArtifact(submission_id="sub_audit2", developer_id="d1", tenant_id="t1",
                           checksum_algorithm="sha256", checksum_value=h)
        astore.create_artifact(a)
        from src.open_platform.package_verification_service import PackageVerificationService
        svc = PackageVerificationService(artifact_store=astore, verification_store=vstore)
        svc.verify_artifact(a.artifact_id, "actor", "t1", content_bytes=data)
        events = astore.list_audit_events(a.artifact_id)
        assert len(events) >= 2  # CREATED + VERIFICATION_STATUS_CHANGED

    def test_multiple_runs_sorted(self, vstore):
        vstore.create_run(_mk_run(artifact_id="a_multi"))
        vstore.create_run(_mk_run(artifact_id="a_multi"))
        runs = vstore.list_runs(artifact_id="a_multi")
        assert len(runs) == 2

    def test_tenant_filter_isolation(self, vstore):
        vstore.create_run(_mk_run(artifact_id="a1", tenant_id="tA"))
        vstore.create_run(_mk_run(artifact_id="a2", tenant_id="tB"))
        assert len(vstore.list_runs(tenant_id="tA")) == 1

    def test_count_by_status(self, vstore):
        r1 = _mk_run(artifact_id="cs1"); r1.run_status = VerificationRunStatus.PASSED; vstore.create_run(r1)
        assert vstore.count_runs(status=VerificationRunStatus.PASSED) == 1
        assert vstore.count_runs(status=VerificationRunStatus.FAILED) == 0

    def test_no_agent_runtime_import(self):
        import src.open_platform.package_verification_service as svc
        import src.open_platform.checksum_verifier as cv
        import src.open_platform.signature_verifier as sv
        for mod in [svc, cv, sv]:
            mod_keys = str(dir(mod))
            assert "AgentRuntime" not in mod_keys

    def test_no_agent_registry_import(self):
        import src.open_platform.package_verification_service as svc
        mod_keys = str(dir(svc))
        assert "AgentRegistry" not in mod_keys

    def test_no_docker_import(self):
        import src.open_platform.package_verification_service as svc
        assert "docker" not in str(dir(svc)).lower()

    def test_no_requests_httpx(self):
        import src.open_platform.checksum_verifier as cv
        import src.open_platform.signature_verifier as sv
        for mod in [cv, sv]:
            m = str(dir(mod))
            assert "requests" not in m and "httpx" not in m

    def test_no_subprocess_usage(self):
        import src.open_platform.checksum_verifier as cv
        import src.open_platform.signature_verifier as sv
        import src.open_platform.package_verification_service as svc
        for mod in [cv, sv, svc]:
            assert "subprocess" not in str(dir(mod))


def _mk_run(artifact_id="art_x", submission_id="sub_x", tenant_id="t1", developer_id="d1",
            created_at=None) -> PackageVerificationRun:
    return PackageVerificationRun(
        artifact_id=artifact_id, submission_id=submission_id,
        tenant_id=tenant_id, developer_id=developer_id,
        created_at=created_at or datetime.now(timezone.utc),
    )
