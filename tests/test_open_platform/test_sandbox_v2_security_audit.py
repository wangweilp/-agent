"""Security Audit Service tests (Step 14)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import json, pytest
from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService
from src.open_platform.sandbox_v2.models import SandboxV2AuditEventType, SandboxV2AuditSeverity

@pytest.fixture
def audit_svc():
    from src.adapters.config import Settings as AppSettings
    from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
    store = SQLiteSandboxV2Store(config=AppSettings())
    return SandboxV2SecurityAuditService(store=store)

class TestAuditEventCreation:
    def test_create_event(self, audit_svc):
        event = audit_svc.create_audit_event(event_type="access_allowed", severity="info", principal_id="user-1", principal_type="user", organization_id="org-1", workspace_id="ws-1", resource_type="job", resource_id="job-1", action="read", decision="allow")
        assert event.audit_event_id.startswith("sbxaud_")
        assert event.event_hash != ""
    def test_event_has_previous_hash(self, audit_svc):
        e1 = audit_svc.create_audit_event(event_type="access_allowed", organization_id="org-2", workspace_id="ws-1")
        e2 = audit_svc.create_audit_event(event_type="resource_created", organization_id="org-2", workspace_id="ws-1")
        assert e2.previous_hash == e1.event_hash
    def test_event_persisted(self, audit_svc):
        event = audit_svc.create_audit_event(event_type="job_submitted", organization_id="org-3", principal_id="u1")
        fetched = audit_svc._store.get_security_audit_event(event.audit_event_id)
        assert fetched is not None

class TestAuditHashChain:
    def test_chain_valid(self, audit_svc):
        for i in range(3):
            audit_svc.create_audit_event(event_type="resource_created", organization_id="org-chain", workspace_id="ws-1", principal_id="u1")
        result = audit_svc.verify_audit_chain(organization_id="org-chain", workspace_id="ws-1")
        assert result["valid"]
        assert result["events_checked"] >= 2
    def test_empty_chain_valid(self, audit_svc):
        result = audit_svc.verify_audit_chain(organization_id="org-empty")
        assert result["valid"]

class TestSensitiveRedaction:
    def test_redacts_secret_keys(self, audit_svc):
        meta = {"SANDBOX_V2_POSTGRES_DSN": "postgresql://user:pass@host/db", "non_sensitive": "ok"}
        cleaned = audit_svc.redact_sensitive_metadata(meta)
        assert cleaned["SANDBOX_V2_POSTGRES_DSN"] == "[REDACTED]"
        assert cleaned["non_sensitive"] == "ok"
    def test_redacts_password_key(self, audit_svc):
        meta = {"db_password": "secret123"}
        cleaned = audit_svc.redact_sensitive_metadata(meta)
        assert cleaned["db_password"] == "[REDACTED]"

class TestEvidenceBundle:
    def test_create_bundle(self, audit_svc):
        bundle = audit_svc.create_evidence_bundle(organization_id="org-eb", workspace_id="ws-1", created_by="admin", title="Test Bundle")
        assert bundle.evidence_bundle_id.startswith("sbxev_")
        assert bundle.bundle_hash != ""
        assert bundle.redacted is True
    def test_bundle_persisted(self, audit_svc):
        bundle = audit_svc.create_evidence_bundle(organization_id="org-eb2", created_by="admin", title="T2")
        fetched = audit_svc._store.get_evidence_bundle(bundle.evidence_bundle_id)
        assert fetched is not None
    def test_same_tenant_bundle(self, audit_svc):
        bundle = audit_svc.create_evidence_bundle(organization_id="org-same", workspace_id="ws-1", job_ids=["j1"])
        assert bundle.organization_id == "org-same"
    def test_export_bundle(self, audit_svc):
        bundle = audit_svc.create_evidence_bundle(organization_id="org-export", title="E")
        exported = audit_svc.export_evidence_bundle_json(bundle.evidence_bundle_id)
        assert exported["redacted"] is True
    def test_export_nonexistent(self, audit_svc):
        result = audit_svc.export_evidence_bundle_json("nonexistent-id")
        assert "error" in result

class TestListAndFilter:
    def test_list_events(self, audit_svc):
        audit_svc.create_audit_event(event_type="access_allowed", organization_id="org-list", workspace_id="ws-1")
        events = audit_svc.list_audit_events(organization_id="org-list", workspace_id="ws-1")
        assert len(events) >= 1
    def test_list_bundles(self, audit_svc):
        audit_svc.create_evidence_bundle(organization_id="org-bl", title="B")
        bundles = audit_svc.list_evidence_bundles(organization_id="org-bl")
        assert len(bundles) >= 1
