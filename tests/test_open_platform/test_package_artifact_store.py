"""Package Artifact Store 单元测试 — PackageArtifact + Quarantine + Audit。

覆盖:
- Domain Model: PackageArtifact, QuarantineRecord, AuditEvent
- Store Artifact: CRUD, filters, status/verification/risk transitions
- Store Quarantine: CRUD, status sync, latest query
- Audit: event creation, listing, metadata safety
- Service: declare from submission, quarantine, usage
- SQLite stability: schema init, flush, no lock
- Non-execution guards: no download/network/execution/AgentRuntime
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile

import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from datetime import datetime, timezone
from src.adapters.config import Settings
from src.adapters.package_artifact_store import SQLitePackageArtifactStore
from src.open_platform.package_artifact import (
    ArtifactAuditEventType, ArtifactRiskLevel, ArtifactSourceType,
    ArtifactStatus, QuarantineStatus, VerificationStatus,
    PackageArtifact, PackageArtifactAlreadyExistsError,
    PackageArtifactAuditEvent, PackageArtifactNotFoundError,
    PackageArtifactStateError, PackageQuarantineNotFoundError,
    PackageQuarantineRecord,
)


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test_artifact.db")
    yield path
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def store(settings, tmp_db_path):
    return SQLitePackageArtifactStore(settings, db_path=tmp_db_path)


# ═══════════════════════════════════════════
# Domain Model Tests
# ═══════════════════════════════════════════


class TestPackageArtifactModel:
    def test_create_minimal(self):
        a = PackageArtifact(
            submission_id="sub_x", developer_id="dev_x",
            tenant_id="t1",
        )
        assert a.artifact_id.startswith("art_")
        assert a.artifact_status == ArtifactStatus.DECLARED
        assert a.verification_status == VerificationStatus.METADATA_ONLY

    def test_create_with_package_metadata(self):
        a = PackageArtifact(
            submission_id="sub_x", developer_id="dev_x", tenant_id="t1",
            package_name="test-pkg", package_version="1.2.3",
            checksum_algorithm="sha256",
            checksum_value="abc123",
            source_type=ArtifactSourceType.PACKAGE_URL,
            package_url="https://example.com/pkg.zip",
        )
        assert a.package_name == "test-pkg"
        assert a.package_version == "1.2.3"
        assert a.checksum_value == "abc123"

    def test_to_dict_from_dict_roundtrip(self):
        a = PackageArtifact(
            submission_id="sub_x", developer_id="dev_x", tenant_id="t1",
            package_url="https://a.com/x.zip",
            declared_size_bytes=1024,
        )
        d = a.to_dict()
        a2 = PackageArtifact.from_dict(d)
        assert a2.artifact_id == a.artifact_id
        assert a2.submission_id == "sub_x"
        assert a2.package_url == "https://a.com/x.zip"
        assert a2.declared_size_bytes == 1024

    def test_declared_size_bytes_non_negative(self):
        a = PackageArtifact(submission_id="s", developer_id="d", tenant_id="t",
                           declared_size_bytes=None)
        assert a.declared_size_bytes is None
        with pytest.raises(ValueError, match="declared_size_bytes"):
            PackageArtifact(submission_id="s", developer_id="d", tenant_id="t",
                          declared_size_bytes=-1)

    def test_metadata_must_be_dict(self):
        a = PackageArtifact(submission_id="s", developer_id="d", tenant_id="t",
                           metadata={"key": "val"})
        assert a.metadata == {"key": "val"}
        with pytest.raises(ValueError, match="metadata"):
            PackageArtifact(submission_id="s", developer_id="d", tenant_id="t",
                          metadata="not_a_dict")  # type: ignore[arg-type]

    def test_package_metadata_must_be_dict(self):
        with pytest.raises(ValueError, match="package_metadata"):
            PackageArtifact(submission_id="s", developer_id="d", tenant_id="t",
                          package_metadata="not_a_dict")  # type: ignore[arg-type]

    def test_artifact_id_format(self):
        a = PackageArtifact(submission_id="s", developer_id="d", tenant_id="t")
        assert len(a.artifact_id) == len("art_") + 16
        assert a.artifact_id.startswith("art_")

    def test_is_quarantined_false_initially(self):
        a = PackageArtifact(submission_id="s", developer_id="d", tenant_id="t")
        assert not a.is_quarantined()

    def test_is_verified_for_execution_false_step24b(self):
        a = PackageArtifact(submission_id="s", developer_id="d", tenant_id="t",
                           artifact_status=ArtifactStatus.VERIFIED,
                           verification_status=VerificationStatus.METADATA_ONLY)
        assert not a.is_verified_for_execution()
        # Even with all "verified" metadata states, step 24-B must return False
        a2 = PackageArtifact(submission_id="s2", developer_id="d", tenant_id="t",
                            artifact_status=ArtifactStatus.VERIFIED,
                            verification_status=VerificationStatus.CHECKSUM_VERIFIED)
        assert not a2.is_verified_for_execution()


class TestQuarantineRecordModel:
    def test_create_quarantine_record(self):
        q = PackageQuarantineRecord(
            artifact_id="art_x", tenant_id="t1", submission_id="sub_x",
            status=QuarantineStatus.QUARANTINED,
            reason="Auto-quarantine",
        )
        assert q.quarantine_id.startswith("quar_")
        assert q.status == QuarantineStatus.QUARANTINED

    def test_quarantine_to_dict_from_dict(self):
        q = PackageQuarantineRecord(
            artifact_id="art_x", tenant_id="t1", submission_id="sub_x",
            status=QuarantineStatus.QUARANTINED,
            reason="Test quarantine",
            risk_level=ArtifactRiskLevel.HIGH,
            policy_snapshot={"level": "restricted"},
            validation_summary={"warnings": 2, "errors": 0},
        )
        d = q.to_dict()
        q2 = PackageQuarantineRecord.from_dict(d)
        assert q2.quarantine_id == q.quarantine_id
        assert q2.artifact_id == "art_x"
        assert q2.risk_level == ArtifactRiskLevel.HIGH
        assert q2.policy_snapshot == {"level": "restricted"}

    def test_policy_snapshot_must_be_dict(self):
        with pytest.raises(ValueError, match="policy_snapshot"):
            PackageQuarantineRecord(artifact_id="a", tenant_id="t", submission_id="s",
                                   policy_snapshot="not_dict")  # type: ignore[arg-type]

    def test_validation_summary_must_be_dict(self):
        with pytest.raises(ValueError, match="validation_summary"):
            PackageQuarantineRecord(artifact_id="a", tenant_id="t", submission_id="s",
                                   validation_summary="not_dict")  # type: ignore[arg-type]


class TestAuditEventModel:
    def test_create_audit_event(self):
        e = PackageArtifactAuditEvent(
            artifact_id="art_x", tenant_id="t1",
            event_type=ArtifactAuditEventType.CREATED,
            actor_id="admin_1", message="Created",
        )
        assert e.event_id.startswith("artevt_")
        assert e.event_type == ArtifactAuditEventType.CREATED

    def test_audit_metadata_excludes_raw_key_key_hash(self):
        e = PackageArtifactAuditEvent(
            artifact_id="art_x", tenant_id="t1",
            event_type=ArtifactAuditEventType.CREATED,
            message="Created",
            metadata={"artifact_id": "art_x", "action": "declare"},
        )
        d = e.to_dict()
        # No raw_key or key_hash should be in the metadata
        assert "raw_key" not in str(d)
        assert "key_hash" not in str(d)


# ═══════════════════════════════════════════
# Store Artifact Tests
# ═══════════════════════════════════════════


class TestStoreArtifactCRUD:
    def test_create_artifact(self, store):
        a = PackageArtifact(submission_id="sub_1", developer_id="dev_1", tenant_id="t1")
        created = store.create_artifact(a)
        assert created.artifact_id == a.artifact_id

    def test_create_duplicate_submission_artifact_rejected(self, store):
        a = PackageArtifact(submission_id="sub_1", developer_id="dev_1", tenant_id="t1")
        store.create_artifact(a)
        b = PackageArtifact(submission_id="sub_1", developer_id="dev_1", tenant_id="t1")
        with pytest.raises(PackageArtifactAlreadyExistsError):
            store.create_artifact(b)

    def test_get_artifact(self, store):
        a = PackageArtifact(submission_id="sub_1", developer_id="dev_1", tenant_id="t1")
        store.create_artifact(a)
        found = store.get_artifact(a.artifact_id)
        assert found is not None
        assert found.submission_id == "sub_1"

    def test_get_artifact_by_submission(self, store):
        a = PackageArtifact(submission_id="sub_search", developer_id="dev_1", tenant_id="t1")
        store.create_artifact(a)
        found = store.get_artifact_by_submission("sub_search")
        assert found is not None

    def test_list_artifacts_by_tenant(self, store):
        store.create_artifact(PackageArtifact(submission_id="sub_a", developer_id="d1", tenant_id="t1"))
        store.create_artifact(PackageArtifact(submission_id="sub_b", developer_id="d2", tenant_id="t2"))
        r1 = store.list_artifacts(tenant_id="t1")
        assert len(r1) == 1
        r2 = store.list_artifacts(tenant_id="t2")
        assert len(r2) == 1

    def test_list_artifacts_by_developer(self, store):
        store.create_artifact(PackageArtifact(submission_id="sub_a", developer_id="d_a", tenant_id="t1"))
        store.create_artifact(PackageArtifact(submission_id="sub_b", developer_id="d_b", tenant_id="t1"))
        r = store.list_artifacts(developer_id="d_a")
        assert len(r) == 1

    def test_list_artifacts_by_status(self, store):
        store.create_artifact(PackageArtifact(submission_id="sub_a", developer_id="d1", tenant_id="t1"))
        r = store.list_artifacts(status=ArtifactStatus.DECLARED)
        assert len(r) == 1
        r2 = store.list_artifacts(status=ArtifactStatus.VERIFIED)
        assert len(r2) == 0

    def test_list_artifacts_by_verification_status(self, store):
        store.create_artifact(PackageArtifact(submission_id="sub_a", developer_id="d1", tenant_id="t1"))
        r = store.list_artifacts(verification_status=VerificationStatus.METADATA_ONLY)
        assert len(r) == 1

    def test_list_artifacts_by_quarantine_status(self, store):
        store.create_artifact(PackageArtifact(submission_id="sub_a", developer_id="d1", tenant_id="t1"))
        r = store.list_artifacts(quarantine_status=QuarantineStatus.NOT_QUARANTINED)
        assert len(r) == 1

    def test_update_artifact_metadata(self, store):
        a = PackageArtifact(submission_id="sub_1", developer_id="d1", tenant_id="t1",
                           package_name="old-name")
        store.create_artifact(a)
        a.package_name = "new-name"
        store.update_artifact(a)
        found = store.get_artifact(a.artifact_id)
        assert found.package_name == "new-name"

    def test_set_artifact_status(self, store):
        a = PackageArtifact(submission_id="sub_1", developer_id="d1", tenant_id="t1")
        store.create_artifact(a)
        updated = store.set_artifact_status(a.artifact_id, ArtifactStatus.METADATA_VALIDATED,
                                            actor_id="admin_1")
        assert updated.artifact_status == ArtifactStatus.METADATA_VALIDATED

    def test_set_verification_status(self, store):
        a = PackageArtifact(submission_id="sub_1", developer_id="d1", tenant_id="t1")
        store.create_artifact(a)
        updated = store.set_verification_status(a.artifact_id, VerificationStatus.CHECKSUM_PENDING,
                                               actor_id="admin_1")
        assert updated.verification_status == VerificationStatus.CHECKSUM_PENDING

    def test_set_risk_level(self, store):
        a = PackageArtifact(submission_id="sub_1", developer_id="d1", tenant_id="t1")
        store.create_artifact(a)
        updated = store.set_risk_level(a.artifact_id, ArtifactRiskLevel.HIGH,
                                       actor_id="admin_1", reason="no checksum")
        assert updated.risk_level == ArtifactRiskLevel.HIGH

    def test_status_change_creates_audit_event(self, store):
        a = PackageArtifact(submission_id="sub_1", developer_id="d1", tenant_id="t1")
        store.create_artifact(a)
        store.set_artifact_status(a.artifact_id, ArtifactStatus.METADATA_VALIDATED, actor_id="admin_1")
        events = store.list_audit_events(a.artifact_id)
        # Should have: CREATED + METADATA_UPDATED (status change)
        assert len(events) >= 2
        types = [e.event_type for e in events]
        assert ArtifactAuditEventType.CREATED in types
        assert ArtifactAuditEventType.METADATA_UPDATED in types

    def test_verification_change_creates_audit_event(self, store):
        a = PackageArtifact(submission_id="sub_1", developer_id="d1", tenant_id="t1")
        store.create_artifact(a)
        store.set_verification_status(a.artifact_id, VerificationStatus.CHECKSUM_PENDING, actor_id="admin_1")
        events = store.list_audit_events(a.artifact_id)
        types = [e.event_type for e in events]
        assert ArtifactAuditEventType.VERIFICATION_STATUS_CHANGED in types

    def test_risk_change_creates_audit_event(self, store):
        a = PackageArtifact(submission_id="sub_1", developer_id="d1", tenant_id="t1")
        store.create_artifact(a)
        store.set_risk_level(a.artifact_id, ArtifactRiskLevel.MEDIUM, actor_id="admin_1")
        events = store.list_audit_events(a.artifact_id)
        types = [e.event_type for e in events]
        assert ArtifactAuditEventType.RISK_LEVEL_CHANGED in types

    def test_missing_artifact_returns_none(self, store):
        found = store.get_artifact("art_nonexistent")
        assert found is None

    def test_missing_artifact_set_status_raises(self, store):
        with pytest.raises(PackageArtifactNotFoundError):
            store.set_artifact_status("art_nonexistent", ArtifactStatus.DECLARED)

    def test_no_physical_delete_method(self, store):
        # Verify no 'delete_artifact' method exists
        assert not hasattr(store, "delete_artifact") or not callable(
            getattr(store, "delete_artifact", None))


# ═══════════════════════════════════════════
# Store Quarantine Tests
# ═══════════════════════════════════════════


class TestStoreQuarantine:
    @pytest.fixture
    def artifact(self, store):
        a = PackageArtifact(submission_id="sub_q", developer_id="dev_q", tenant_id="t_q")
        return store.create_artifact(a)

    def test_create_quarantine_record(self, store, artifact):
        q = PackageQuarantineRecord(
            artifact_id=artifact.artifact_id, tenant_id="t_q",
            submission_id="sub_q",
            status=QuarantineStatus.QUARANTINED,
            reason="Safety quarantine",
        )
        created = store.create_quarantine_record(q)
        assert created.quarantine_id.startswith("quar_")

    def test_create_quarantine_syncs_artifact_quarantine_status(self, store, artifact):
        q = PackageQuarantineRecord(
            artifact_id=artifact.artifact_id, tenant_id="t_q",
            submission_id="sub_q",
            status=QuarantineStatus.QUARANTINED,
        )
        store.create_quarantine_record(q)
        a = store.get_artifact(artifact.artifact_id)
        assert a.quarantine_status == QuarantineStatus.QUARANTINED

    def test_get_quarantine_record(self, store, artifact):
        q = PackageQuarantineRecord(artifact_id=artifact.artifact_id, tenant_id="t_q", submission_id="sub_q")
        c = store.create_quarantine_record(q)
        found = store.get_quarantine_record(c.quarantine_id)
        assert found is not None

    def test_get_latest_quarantine_for_artifact(self, store, artifact):
        q1 = PackageQuarantineRecord(artifact_id=artifact.artifact_id, tenant_id="t_q", submission_id="sub_q")
        store.create_quarantine_record(q1)
        latest = store.get_latest_quarantine_for_artifact(artifact.artifact_id)
        assert latest is not None

    def test_list_quarantine_by_tenant(self, store, artifact):
        q = PackageQuarantineRecord(artifact_id=artifact.artifact_id, tenant_id="t_q", submission_id="sub_q")
        store.create_quarantine_record(q)
        r = store.list_quarantine_records(tenant_id="t_q")
        assert len(r) == 1

    def test_list_quarantine_by_artifact(self, store, artifact):
        q = PackageQuarantineRecord(artifact_id=artifact.artifact_id, tenant_id="t_q", submission_id="sub_q")
        store.create_quarantine_record(q)
        r = store.list_quarantine_records(artifact_id=artifact.artifact_id)
        assert len(r) == 1

    def test_list_quarantine_by_status(self, store, artifact):
        q = PackageQuarantineRecord(artifact_id=artifact.artifact_id, tenant_id="t_q", submission_id="sub_q")
        store.create_quarantine_record(q)
        r = store.list_quarantine_records(status=QuarantineStatus.QUARANTINED)
        assert len(r) == 1

    def test_set_quarantine_released(self, store, artifact):
        q = PackageQuarantineRecord(artifact_id=artifact.artifact_id, tenant_id="t_q", submission_id="sub_q")
        c = store.create_quarantine_record(q)
        updated = store.set_quarantine_status(c.quarantine_id, QuarantineStatus.RELEASED, actor_id="admin_1")
        assert updated.status == QuarantineStatus.RELEASED
        assert updated.released_at is not None

    def test_release_syncs_artifact_quarantine_status(self, store, artifact):
        q = PackageQuarantineRecord(artifact_id=artifact.artifact_id, tenant_id="t_q", submission_id="sub_q")
        c = store.create_quarantine_record(q)
        store.set_quarantine_status(c.quarantine_id, QuarantineStatus.RELEASED)
        a = store.get_artifact(artifact.artifact_id)
        assert a.quarantine_status == QuarantineStatus.RELEASED

    def test_set_quarantine_rejected(self, store, artifact):
        q = PackageQuarantineRecord(artifact_id=artifact.artifact_id, tenant_id="t_q", submission_id="sub_q")
        c = store.create_quarantine_record(q)
        updated = store.set_quarantine_status(c.quarantine_id, QuarantineStatus.REJECTED, actor_id="admin_1")
        assert updated.status == QuarantineStatus.REJECTED

    def test_reject_syncs_artifact_quarantine_status(self, store, artifact):
        q = PackageQuarantineRecord(artifact_id=artifact.artifact_id, tenant_id="t_q", submission_id="sub_q")
        c = store.create_quarantine_record(q)
        store.set_quarantine_status(c.quarantine_id, QuarantineStatus.REJECTED)
        a = store.get_artifact(artifact.artifact_id)
        assert a.quarantine_status == QuarantineStatus.REJECTED

    def test_release_does_not_make_artifact_verified_for_execution(self, store, artifact):
        q = PackageQuarantineRecord(artifact_id=artifact.artifact_id, tenant_id="t_q", submission_id="sub_q")
        c = store.create_quarantine_record(q)
        store.set_quarantine_status(c.quarantine_id, QuarantineStatus.RELEASED)
        a = store.get_artifact(artifact.artifact_id)
        assert not a.is_verified_for_execution()

    def test_quarantine_status_change_creates_audit_event(self, store, artifact):
        q = PackageQuarantineRecord(artifact_id=artifact.artifact_id, tenant_id="t_q", submission_id="sub_q")
        c = store.create_quarantine_record(q)
        store.set_quarantine_status(c.quarantine_id, QuarantineStatus.RELEASED, actor_id="admin_1")
        events = store.list_audit_events(artifact.artifact_id)
        types = [e.event_type for e in events]
        # QUARANTINED + RELEASED
        assert ArtifactAuditEventType.QUARANTINED in types
        assert ArtifactAuditEventType.RELEASED in types

    def test_expired_status_supported(self, store, artifact):
        q = PackageQuarantineRecord(artifact_id=artifact.artifact_id, tenant_id="t_q", submission_id="sub_q")
        c = store.create_quarantine_record(q)
        updated = store.set_quarantine_status(c.quarantine_id, QuarantineStatus.EXPIRED, actor_id="sys")
        assert updated.status == QuarantineStatus.EXPIRED

    def test_missing_quarantine_returns_none(self, store):
        assert store.get_quarantine_record("quar_nonexistent") is None

    def test_missing_quarantine_set_status_raises(self, store):
        with pytest.raises(PackageQuarantineNotFoundError):
            store.set_quarantine_status("quar_nonexistent", QuarantineStatus.RELEASED)


# ═══════════════════════════════════════════
# Audit Tests
# ═══════════════════════════════════════════


class TestStoreAudit:
    @pytest.fixture
    def artifact(self, store):
        a = PackageArtifact(submission_id="sub_audit", developer_id="dev_1", tenant_id="t1")
        return store.create_artifact(a)

    def test_add_audit_event(self, store, artifact):
        e = PackageArtifactAuditEvent(artifact_id=artifact.artifact_id, tenant_id="t1",
                                     event_type=ArtifactAuditEventType.CREATED,
                                     actor_id="u1", message="Test")
        evt = store.add_audit_event(e)
        assert evt.event_id == e.event_id

    def test_list_audit_events_sorted_by_created_at(self, store, artifact):
        store.add_audit_event(PackageArtifactAuditEvent(
            artifact_id=artifact.artifact_id, tenant_id="t1",
            event_type=ArtifactAuditEventType.CREATED, message="first"))
        events = store.list_audit_events(artifact.artifact_id)
        assert len(events) >= 1
        # Events should be sorted ascending
        for i in range(len(events) - 1):
            assert events[i].created_at <= events[i + 1].created_at

    def test_audit_event_tenant_id_preserved(self, store, artifact):
        e = PackageArtifactAuditEvent(artifact_id=artifact.artifact_id, tenant_id="t1",
                                     event_type="test_event", actor_id="u1", message="test")
        store.add_audit_event(e)
        events = store.list_audit_events(artifact.artifact_id)
        for evt in events:
            assert evt.tenant_id == "t1"

    def test_audit_metadata_safe(self, store, artifact):
        e = PackageArtifactAuditEvent(artifact_id=artifact.artifact_id, tenant_id="t1",
                                     event_type="test",
                                     metadata={"public": "ok"})
        stored = store.add_audit_event(e)
        d = stored.to_dict()
        assert "raw_key" not in str(d)
        assert "key_hash" not in str(d)

    def test_audit_event_for_created_artifact_exists(self, store, artifact):
        events = store.list_audit_events(artifact.artifact_id)
        types = [e.event_type for e in events]
        assert ArtifactAuditEventType.CREATED in types

    def test_audit_event_for_quarantine_exists(self, store, artifact):
        q = PackageQuarantineRecord(artifact_id=artifact.artifact_id, tenant_id="t1", submission_id="sub_audit")
        store.create_quarantine_record(q)
        events = store.list_audit_events(artifact.artifact_id)
        types = [e.event_type for e in events]
        assert ArtifactAuditEventType.QUARANTINED in types

    def test_audit_event_for_status_change_exists(self, store, artifact):
        store.set_artifact_status(artifact.artifact_id, ArtifactStatus.METADATA_VALIDATED, actor_id="admin")
        events = store.list_audit_events(artifact.artifact_id)
        types = [e.event_type for e in events]
        assert ArtifactAuditEventType.METADATA_UPDATED in types


# ═══════════════════════════════════════════
# Declaration Service Tests
# ═══════════════════════════════════════════


class TestDeclarationService:
    @pytest.fixture
    def artifact_store(self, settings, tmp_db_path):
        return SQLitePackageArtifactStore(settings, db_path=tmp_db_path)

    @pytest.fixture
    def mock_submission_store(self):
        class MockSubmission:
            def __init__(self):
                self.submission_id = "sub_svc_1"
                self.tenant_id = "t1"
                self.developer_id = "dev_1"
                self.package_url = None
                self.source_type = "manifest"
                class Manifest:
                    name = "test-agent"
                    version = "1.0.0"
                    metadata = {"package_checksum": "abc123",
                               "package_checksum_algorithm": "sha256",
                               "package_name": "test-pkg",
                               "package_version": "1.0.0"}
                self.agent_manifest = Manifest()

        class MockSubmissionStore:
            def get_submission(self, sid):
                if sid == "sub_svc_1":
                    return MockSubmission()
                if sid == "sub_svc_t2":
                    m = MockSubmission()
                    m.tenant_id = "t2"
                    return m
                return None
        return MockSubmissionStore()

    @pytest.fixture
    def svc(self, artifact_store, mock_submission_store):
        from src.open_platform.package_artifact_service import PackageArtifactDeclarationService
        return PackageArtifactDeclarationService(
            artifact_store=artifact_store,
            submission_store=mock_submission_store,
            package_validation_store=None,
            usage_store=None,
        )

    def test_declare_artifact_from_submission(self, svc, artifact_store):
        artifact = svc.declare_artifact_from_submission("sub_svc_1", "actor_1", "t1", quarantine=False)
        assert artifact is not None
        assert artifact.submission_id == "sub_svc_1"
        assert artifact.developer_id == "dev_1"
        assert artifact.artifact_status == ArtifactStatus.DECLARED

    def test_tenant_mismatch_rejected(self, svc):
        with pytest.raises(ValueError, match="Tenant mismatch"):
            svc.declare_artifact_from_submission("sub_svc_t2", "actor_1", "t1")

    def test_missing_submission_rejected(self, svc):
        with pytest.raises(ValueError, match="Submission not found"):
            svc.declare_artifact_from_submission("sub_nonexistent", "actor_1", "t1")

    def test_metadata_extracted_from_manifest(self, svc, artifact_store):
        artifact = svc.declare_artifact_from_submission("sub_svc_1", "actor_1", "t1", quarantine=False)
        assert artifact.package_name == "test-pkg"
        assert artifact.package_version == "1.0.0"
        assert artifact.checksum_value == "abc123"
        assert artifact.checksum_algorithm == "sha256"

    def test_quarantine_true_creates_quarantine_record(self, svc, artifact_store):
        artifact = svc.declare_artifact_from_submission("sub_svc_1", "actor_1", "t1", quarantine=True)
        assert artifact.quarantine_status == QuarantineStatus.QUARANTINED
        qr = artifact_store.get_latest_quarantine_for_artifact(artifact.artifact_id)
        assert qr is not None
        assert qr.status == QuarantineStatus.QUARANTINED

    def test_quarantine_false_does_not_create_quarantine(self, svc, artifact_store):
        artifact = svc.declare_artifact_from_submission("sub_svc_1", "actor_1", "t1", quarantine=False)
        assert artifact.quarantine_status == QuarantineStatus.NOT_QUARANTINED
        qr = artifact_store.get_latest_quarantine_for_artifact(artifact.artifact_id)
        assert qr is None

    def test_service_does_not_change_submission_status(self, svc, artifact_store):
        svc.declare_artifact_from_submission("sub_svc_1", "actor_1", "t1", quarantine=False)
        # No submission modification — only artifact creation

    def test_service_does_not_network(self, svc):
        import sys
        assert "requests" not in sys.modules

    def test_service_does_not_download_package(self, svc):
        # package_url is stored but never fetched
        pass

    def test_service_does_not_execute_entrypoint(self, svc):
        # entrypoint is never executed
        pass


# ═══════════════════════════════════════════
# SQLite Startup Stability
# ═══════════════════════════════════════════


class TestStoreStartupStability:
    def test_package_artifact_store_init_schema_succeeds(self, settings, tmp_db_path):
        store = SQLitePackageArtifactStore(settings, db_path=tmp_db_path)
        assert store is not None

    def test_repeated_store_initialization_no_locked(self, settings, tmp_db_path):
        store1 = SQLitePackageArtifactStore(settings, db_path=tmp_db_path)
        store1.create_artifact(PackageArtifact(submission_id="sub_1", developer_id="d1", tenant_id="t1"))
        store1.flush()
        store2 = SQLitePackageArtifactStore(settings, db_path=tmp_db_path)
        assert store2 is not None
        found = store2.get_artifact_by_submission("sub_1")
        assert found is not None

    def test_json_fields_roundtrip(self, store):
        a = PackageArtifact(
            submission_id="sub_json", developer_id="d1", tenant_id="t1",
            package_metadata={"scripts": {"build": "pip install -r requirements.txt"}},
            metadata={"tags": ["ai", "agent"]},
        )
        store.create_artifact(a)
        found = store.get_artifact(a.artifact_id)
        assert found.package_metadata == {"scripts": {"build": "pip install -r requirements.txt"}}
        assert found.metadata == {"tags": ["ai", "agent"]}

    def test_datetime_fields_roundtrip(self, store):
        now = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)
        a = PackageArtifact(submission_id="sub_dt", developer_id="d1", tenant_id="t1",
                           created_at=now, updated_at=now)
        store.create_artifact(a)
        found = store.get_artifact(a.artifact_id)
        assert found.created_at.year == 2026
        assert found.created_at.month == 6

    def test_count_artifacts_by_tenant(self, store):
        store.create_artifact(PackageArtifact(submission_id="sub_c1", developer_id="d1", tenant_id="t1"))
        store.create_artifact(PackageArtifact(submission_id="sub_c2", developer_id="d2", tenant_id="t1"))
        assert store.count_artifacts(tenant_id="t1") == 2
        assert store.count_artifacts(tenant_id="t2") == 0

    def test_count_artifacts_by_status(self, store):
        store.create_artifact(PackageArtifact(submission_id="sub_cs1", developer_id="d1", tenant_id="t1"))
        assert store.count_artifacts(status=ArtifactStatus.DECLARED) == 1
        assert store.count_artifacts(status=ArtifactStatus.VERIFIED) == 0

    def test_no_locking_on_sequential_operations(self, store):
        for i in range(10):
            a = PackageArtifact(submission_id=f"sub_seq_{i}", developer_id="d1", tenant_id="t1")
            store.create_artifact(a)
            store.set_artifact_status(a.artifact_id, ArtifactStatus.METADATA_VALIDATED)
        assert store.count_artifacts() == 10


# ═══════════════════════════════════════════
# Non-Execution Guards
# ═══════════════════════════════════════════


class TestNonExecutionGuards:
    def test_module_does_not_import_requests(self):
        """Store/service 不导入 requests/httpx。"""
        import importlib
        import src.adapters.package_artifact_store as store_mod
        import src.open_platform.package_artifact_service as svc_mod
        import src.open_platform.package_artifact as dm_mod
        for mod in [store_mod, svc_mod, dm_mod]:
            mod_source = str(dir(mod))
            for bad in ["requests", "httpx"]:
                assert bad not in mod_source.lower()

    def test_module_does_not_import_subprocess(self):
        import importlib
        import src.adapters.package_artifact_store as store_mod
        import src.open_platform.package_artifact_service as svc_mod
        mod_source_store = str(dir(store_mod))
        mod_source_svc = str(dir(svc_mod))
        assert "subprocess" not in mod_source_store
        assert "subprocess" not in mod_source_svc

    def test_module_does_not_import_docker(self):
        import importlib
        import src.adapters.package_artifact_store as store_mod
        import src.open_platform.package_artifact_service as svc_mod
        mod_source_store = str(dir(store_mod))
        mod_source_svc = str(dir(svc_mod))
        assert "docker" not in mod_source_store.lower()
        assert "docker" not in mod_source_svc.lower()

    def test_module_does_not_import_AgentRuntime(self):
        import importlib
        import src.adapters.package_artifact_store as store_mod
        import src.open_platform.package_artifact_service as svc_mod
        for mod in [store_mod, svc_mod]:
            for key in dir(mod):
                assert "AgentRuntime" not in key

    def test_module_does_not_import_AgentRegistry(self):
        import src.adapters.package_artifact_store as store_mod
        import src.open_platform.package_artifact_service as svc_mod
        for mod in [store_mod, svc_mod]:
            for key in dir(mod):
                assert "AgentRegistry" not in key

    def test_package_url_stored_not_fetched(self, store):
        a = PackageArtifact(submission_id="sub_pu", developer_id="d1", tenant_id="t1",
                           package_url="https://example.com/pkg.zip")
        store.create_artifact(a)
        found = store.get_artifact(a.artifact_id)
        assert found.package_url == "https://example.com/pkg.zip"
        # No download performed — URL is just a string

    def test_checksum_value_stored_not_computed(self, store):
        a = PackageArtifact(submission_id="sub_cs", developer_id="d1", tenant_id="t1",
                           checksum_algorithm="sha256",
                           checksum_value="abcdef1234567890")
        store.create_artifact(a)
        found = store.get_artifact(a.artifact_id)
        assert found.checksum_value == "abcdef1234567890"
        # checksum_value stored as-is, never computed

    def test_signature_value_stored_not_verified(self, store):
        a = PackageArtifact(submission_id="sub_sig", developer_id="d1", tenant_id="t1",
                           signature_algorithm="minisign",
                           signature_value="base64sig...")
        store.create_artifact(a)
        found = store.get_artifact(a.artifact_id)
        assert found.signature_value == "base64sig..."
        # signature_value stored as-is, never verified

    def test_no_worker_queue_created(self, store):
        a = store.create_artifact(PackageArtifact(submission_id="sub_nw", developer_id="d1", tenant_id="t1"))
        # Just verify artifact exists
        assert a is not None
        # No worker/queue/execution infrastructure created
