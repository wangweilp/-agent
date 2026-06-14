"""Security API tests (Step 14)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest

class TestReadinessSecurityFields:
    def test_readiness_has_security_fields(self):
        from src.api.sandbox_v2 import ReadinessResponse
        resp = ReadinessResponse(); data = resp.model_dump()
        fields = ["security_context","access_policy_engine","rbac_scope_policy","tenant_isolation","cross_tenant_deny","security_audit_events","audit_hash_chain","evidence_bundle_export","sensitive_metadata_redaction","external_iam","sso_integration"]
        for f in fields: assert f in data, f"Missing: {f}"
    def test_default_security_values(self):
        from src.api.sandbox_v2 import ReadinessResponse
        resp = ReadinessResponse()
        assert resp.security_context is True; assert resp.access_policy_engine is True
        assert resp.tenant_isolation is True; assert resp.cross_tenant_deny is True
        assert resp.external_iam is False; assert resp.sso_integration is False
        assert resp.legacy_endpoint_enforcement == "incremental"

class TestAccessEvaluateEndpoint:
    def test_basic_evaluation(self):
        from src.open_platform.sandbox_v2.access_policy import SandboxV2AccessPolicyEngine
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="admin", roles=["admin"], organization_id="org-1", workspace_id="ws-1", resource_organization_id="org-1", resource_workspace_id="ws-1", action="read")
        assert r["allowed"]

class TestSecurityStorePersistence:
    def test_access_decision_record(self):
        from src.adapters.config import Settings as AppSettings
        from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        from src.open_platform.sandbox_v2.models import SandboxV2AccessDecision
        store = SQLiteSandboxV2Store(config=AppSettings())
        dec = SandboxV2AccessDecision(allowed=True, action="allow", reason="test", principal_id="u1", principal_type="user", resource_type="job", resource_id="j1", permission_action="read")
        store.create_access_decision_record(dec)
        records = store.list_access_decision_records()
        assert len(records) >= 1

class TestSQLiteTablesExist:
    def test_create_audit_event_table(self):
        from src.adapters.config import Settings as AppSettings
        from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        store = SQLiteSandboxV2Store(config=AppSettings())
        rows = store._exec("SELECT name FROM sqlite_master WHERE type='table' AND name='sandbox_v2_security_audit_events'", [])
        assert len(list(rows)) == 1
    def test_evidence_bundle_table(self):
        from src.adapters.config import Settings as AppSettings
        from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        store = SQLiteSandboxV2Store(config=AppSettings())
        rows = store._exec("SELECT name FROM sqlite_master WHERE type='table' AND name='sandbox_v2_evidence_bundles'", [])
        assert len(list(rows)) == 1
    def test_access_decision_table(self):
        from src.adapters.config import Settings as AppSettings
        from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        store = SQLiteSandboxV2Store(config=AppSettings())
        rows = store._exec("SELECT name FROM sqlite_master WHERE type='table' AND name='sandbox_v2_access_decisions'", [])
        assert len(list(rows)) == 1
