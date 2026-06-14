"""Tenant Isolation tests (Step 14)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.tenant_isolation import SandboxV2TenantIsolationService

class TestValidateResourceOwnership:
    def test_same_org_ws_valid(self):
        ok, _ = SandboxV2TenantIsolationService.validate_resource_ownership("org-1", "ws-1", "org-1", "ws-1")
        assert ok
    def test_cross_org_invalid(self):
        ok, reason = SandboxV2TenantIsolationService.validate_resource_ownership("org-1", "ws-1", "org-2", "ws-1")
        assert not ok
        assert "Organization" in reason
    def test_cross_ws_invalid(self):
        ok, reason = SandboxV2TenantIsolationService.validate_resource_ownership("org-1", "ws-2", "org-1", "ws-1")
        assert not ok
    def test_empty_orgs_ok(self):
        ok, _ = SandboxV2TenantIsolationService.validate_resource_ownership("", "", "", "")
        assert ok

class TestAssertSameTenant:
    def test_assert_same_passes(self):
        SandboxV2TenantIsolationService.assert_same_tenant("org-1", "ws-1", "org-1", "ws-1")
    def test_assert_cross_raises(self):
        with pytest.raises(ValueError, match="Cross-tenant"):
            SandboxV2TenantIsolationService.assert_same_tenant("org-1", "ws-1", "org-2", "ws-1")

class TestFilterResources:
    def test_filter_matching(self):
        resources = [{"organization_id": "org-1", "workspace_id": "ws-1"}, {"organization_id": "org-2", "workspace_id": "ws-1"}]
        filtered = SandboxV2TenantIsolationService.filter_resources_for_context(resources, "org-1", "ws-1")
        assert len(filtered) == 1
    def test_filter_empty(self):
        assert SandboxV2TenantIsolationService.filter_resources_for_context([], "org-1", "ws-1") == []

class TestCrossTenantDetection:
    def test_detect_cross(self):
        svc = SandboxV2TenantIsolationService()
        assert svc.detect_cross_tenant_attempt(resource_org="org-2", organization_id="org-1")

class TestReadiness:
    def test_readiness(self):
        svc = SandboxV2TenantIsolationService()
        r = svc.get_tenant_isolation_readiness()
        assert r["tenant_isolation"] is True
        assert r["cross_tenant_deny"] is True
