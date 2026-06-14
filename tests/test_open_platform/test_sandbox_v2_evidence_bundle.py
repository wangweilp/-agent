"""Evidence Bundle tests (Step 14)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest

@pytest.fixture
def audit_svc():
    from src.adapters.config import Settings as AppSettings
    from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
    from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService
    store = SQLiteSandboxV2Store(config=AppSettings())
    return SandboxV2SecurityAuditService(store=store)

class TestEvidenceBundleBasics:
    def test_bundle_hash_consistent(self, audit_svc):
        b1 = audit_svc.create_evidence_bundle(organization_id="org-h", title="H1", created_by="admin")
        assert b1.bundle_hash != ""
        assert len(b1.bundle_hash) == 64
    def test_bundle_always_redacted(self, audit_svc):
        b = audit_svc.create_evidence_bundle(organization_id="org-r", title="R")
        assert b.redacted is True
    def test_export_output_redacted(self, audit_svc):
        b = audit_svc.create_evidence_bundle(organization_id="org-e", title="E")
        exported = audit_svc.export_evidence_bundle_json(b.evidence_bundle_id)
        assert exported["redacted"] is True
    def test_bundle_with_audit_events(self, audit_svc):
        e1 = audit_svc.create_audit_event(event_type="job_submitted", organization_id="org-be", workspace_id="ws-1", principal_id="u1")
        e2 = audit_svc.create_audit_event(event_type="resource_created", organization_id="org-be", workspace_id="ws-1", principal_id="u1")
        b = audit_svc.create_evidence_bundle(organization_id="org-be", workspace_id="ws-1", audit_event_ids=[e1.audit_event_id, e2.audit_event_id], job_ids=["job-1"])
        fetched = audit_svc._store.get_evidence_bundle(b.evidence_bundle_id)
        assert fetched is not None
        assert len(fetched.audit_event_ids) == 2
        assert "job-1" in fetched.job_ids
    def test_bundle_resource_refs(self, audit_svc):
        refs = [{"resource_type": "job", "resource_id": "j1", "organization_id": "org-ref"}, {"resource_type": "artifact", "resource_id": "a1", "organization_id": "org-ref"}]
        b = audit_svc.create_evidence_bundle(organization_id="org-ref", resource_refs=refs, title="Refs")
        assert len(b.resource_refs) == 2
    def test_compute_event_hash_deterministic(self, audit_svc):
        e1 = audit_svc.create_audit_event(event_type="test", organization_id="org-det")
        h1 = audit_svc.compute_event_hash(e1)
        h2 = audit_svc.compute_event_hash(e1)
        assert h1 == h2

class TestEvidenceBundleStore:
    def test_list_bundles_by_org(self, audit_svc):
        audit_svc.create_evidence_bundle(organization_id="org-lo1", title="B1")
        audit_svc.create_evidence_bundle(organization_id="org-lo1", title="B2")
        bundles = audit_svc.list_evidence_bundles(organization_id="org-lo1")
        assert len(bundles) >= 2
    def test_get_bundle_by_id(self, audit_svc):
        b = audit_svc.create_evidence_bundle(organization_id="org-gi", title="G")
        fetched = audit_svc.get_evidence_bundle(b.evidence_bundle_id)
        assert fetched is not None
        assert fetched.title == "G"
