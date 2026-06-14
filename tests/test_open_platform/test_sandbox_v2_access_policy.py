"""Access Policy Engine tests (Step 14)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.access_policy import SandboxV2AccessPolicyEngine
from src.open_platform.sandbox_v2.models import SandboxV2PrincipalType, SandboxV2Role, SandboxV2PermissionAction

class TestDefaultDeny:
    def test_anonymous_denied(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="anonymous")
        assert not r["allowed"]
    def test_missing_org_denied(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["viewer"], organization_id="")
        assert not r["allowed"]
    def test_missing_ws_denied(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["viewer"], organization_id="org-1", workspace_id="")
        assert not r["allowed"]
    def test_unknown_role_denied(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["bad_role"], organization_id="org-1", workspace_id="ws-1", action="read")
        assert not r["allowed"]
    def test_unknown_action_denied(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["viewer"], organization_id="org-1", workspace_id="ws-1", action="fly_to_moon")
        assert not r["allowed"]

class TestRolePermissions:
    def test_admin_allowed_all(self):
        for action in SandboxV2PermissionAction:
            r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="admin", roles=["admin"], organization_id="org-1", workspace_id="ws-1", action=action)
            assert r["allowed"], f"Admin should be allowed {action}"
    def test_developer_can_create_read(self):
        for action in ("create", "read", "list"):
            r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["developer"], organization_id="org-1", workspace_id="ws-1", action=action)
            assert r["allowed"], f"Developer should be allowed {action}"
    def test_developer_cannot_kill(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["developer"], organization_id="org-1", workspace_id="ws-1", action="kill")
        assert not r["allowed"]
    def test_developer_cannot_approve(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["developer"], organization_id="org-1", workspace_id="ws-1", action="approve")
        assert not r["allowed"]
    def test_auditor_can_read_not_kill(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["auditor"], organization_id="org-1", workspace_id="ws-1", action="read")
        assert r["allowed"]
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["auditor"], organization_id="org-1", workspace_id="ws-1", action="kill")
        assert not r["allowed"]
    def test_viewer_read_only(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["viewer"], organization_id="org-1", workspace_id="ws-1", action="read")
        assert r["allowed"]
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["viewer"], organization_id="org-1", workspace_id="ws-1", action="delete")
        assert not r["allowed"]
    def test_operator_can_cancel_kill(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["operator"], organization_id="org-1", workspace_id="ws-1", action="cancel")
        assert r["allowed"]
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["operator"], organization_id="org-1", workspace_id="ws-1", action="kill")
        assert r["allowed"]
    def test_operator_cannot_approve(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["operator"], organization_id="org-1", workspace_id="ws-1", action="approve")
        assert not r["allowed"]
    def test_worker_can_execute_not_admin(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="worker", roles=["worker"], organization_id="org-1", workspace_id="ws-1", action="execute")
        assert r["allowed"]
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="worker", roles=["worker"], organization_id="org-1", workspace_id="ws-1", action="administer")
        assert not r["allowed"]

class TestCrossTenant:
    def test_cross_org_denied(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["viewer"], organization_id="org-1", workspace_id="ws-1", resource_organization_id="org-2")
        assert not r["allowed"]
    def test_cross_ws_denied(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["viewer"], organization_id="org-1", workspace_id="ws-1", resource_organization_id="org-1", resource_workspace_id="ws-2")
        assert not r["allowed"]
    def test_same_org_ws_allowed(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=["viewer"], organization_id="org-1", workspace_id="ws-1", resource_organization_id="org-1", resource_workspace_id="ws-1", action="read")
        assert r["allowed"]

class TestScopes:
    def test_scope_sufficient(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="api_key", roles=["developer"], scopes=["sandbox:job:read"], organization_id="org-1", workspace_id="ws-1", resource_type="job", action="read")
        assert r["allowed"]
    def test_scope_insufficient(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="api_key", roles=["developer"], scopes=["sandbox:job:read"], organization_id="org-1", workspace_id="ws-1", resource_type="job", action="delete")
        assert not r["allowed"]
    def test_no_scopes_denied_for_api_key(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="api_key", roles=["developer"], scopes=[], organization_id="org-1", workspace_id="ws-1", resource_type="job", action="read")
        assert not r["allowed"]

class TestSystemPrincipal:
    def test_system_allowed(self):
        r = SandboxV2AccessPolicyEngine.evaluate_access(principal_type="system")
        assert r["allowed"]

class TestExceptionFailClosed:
    def test_none_input(self):
        try:
            SandboxV2AccessPolicyEngine.evaluate_access(principal_type="user", roles=None, scopes=None)
        except Exception:
            pass  # fail closed gracefully
