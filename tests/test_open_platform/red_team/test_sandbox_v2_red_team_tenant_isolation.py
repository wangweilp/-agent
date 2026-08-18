"""Red-Team tenant isolation tests (Step 14)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.access_policy import SandboxV2AccessPolicyEngine
from src.open_platform.sandbox_v2.tenant_isolation import SandboxV2TenantIsolationService

class TestRedTeamCrossTenantRead:
    def test_cross_org_job_read_denied(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(
            principal_type="user", roles=["viewer"],
            organization_id="org-a", workspace_id="ws-1",
            resource_organization_id="org-b", resource_workspace_id="ws-1",
            resource_type="job", action="read")
        assert not r["allowed"]
    def test_cross_ws_artifact_read_denied(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(
            principal_type="user", roles=["viewer"],
            organization_id="org-a", workspace_id="ws-1",
            resource_organization_id="org-a", resource_workspace_id="ws-2",
            resource_type="artifact", action="read")
        assert not r["allowed"]

class TestRedTeamCrossTenantKill:
    def test_cross_tenant_kill_denied(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(
            principal_type="user", roles=["operator"],
            organization_id="org-a", workspace_id="ws-1",
            resource_organization_id="org-b", resource_workspace_id="ws-1",
            resource_type="job", action="kill")
        assert not r["allowed"]
    def test_evidence_bundle_cross_tenant(self):
        svc = SandboxV2TenantIsolationService()
        ok, _ = svc.validate_resource_ownership("org-a", "ws-1", "org-b", "ws-1")
        assert not ok

class TestRedTeamRoleEscalation:
    def test_auditor_cannot_kill(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(
            principal_type="user", roles=["auditor"],
            organization_id="org-1", workspace_id="ws-1", action="kill")
        assert not r["allowed"]
    def test_viewer_cannot_delete(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(
            principal_type="user", roles=["viewer"],
            organization_id="org-1", workspace_id="ws-1", action="delete")
        assert not r["allowed"]
    def test_developer_cannot_approve_package(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(
            principal_type="user", roles=["developer"],
            organization_id="org-1", workspace_id="ws-1", action="approve")
        assert not r["allowed"]
    def test_operator_cannot_approve_package(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(
            principal_type="user", roles=["operator"],
            organization_id="org-1", workspace_id="ws-1", action="approve")
        assert not r["allowed"]
    def test_worker_cannot_review_package(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(
            principal_type="worker", roles=["worker"],
            organization_id="org-1", workspace_id="ws-1", resource_type="package_request", action="review")
        assert not r["allowed"]

class TestRedTeamAnonymousService:
    def test_anonymous_denied(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="anonymous", action="read")
        assert not r["allowed"]
    def test_malformed_context_fail_closed(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(
            principal_type="user", roles=["unknown_x"],
            organization_id="", workspace_id="", action="delete")
        assert not r["allowed"]

class TestRedTeamAuditIntegrity:
    def test_audit_event_no_secret(self):
        from src.open_platform.sandbox_v2.models import SandboxV2AuditEvent
        event = SandboxV2AuditEvent(metadata={"SANDBOX_V2_POSTGRES_DSN": "secret"})
        from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService
        cleaned = SandboxV2SecurityAuditService.redact_sensitive_metadata(event.metadata)
        assert cleaned.get("SANDBOX_V2_POSTGRES_DSN") == "[REDACTED]"
    def test_audit_hash_chain_verifiable(self):
        from src.adapters.config import Settings
        from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService
        # in-memory 隔离，避免审计事件写入真实库或受历史污染
        store = SQLiteSandboxV2Store(config=Settings(), db_path=":memory:")
        audit = SandboxV2SecurityAuditService(store=store)
        for i in range(3):
            audit.create_audit_event(event_type="job_submitted", organization_id="org-rt", principal_id="u1")
        result = audit.verify_audit_chain(organization_id="org-rt")
        assert result["valid"]

class TestRedTeamResourceFiltering:
    def test_list_filtering(self):
        resources = [{"organization_id": "org-x", "workspace_id": "ws-1", "name": "x"}, {"organization_id": "org-y", "workspace_id": "ws-1", "name": "y"}]
        filtered = SandboxV2TenantIsolationService.filter_resources_for_context(resources, "org-x", "ws-1")
        assert len(filtered) == 1
        assert filtered[0]["name"] == "x"
    def test_cross_tenant_detected_and_flagged(self):
        svc = SandboxV2TenantIsolationService()
        is_cross = svc.detect_cross_tenant_attempt(organization_id="org-a", workspace_id="ws-1", resource_org="org-b", resource_ws="ws-1")
        assert is_cross
