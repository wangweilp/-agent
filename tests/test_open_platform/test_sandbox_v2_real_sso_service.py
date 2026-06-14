"""Real SSO Service tests (Step 20)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.iam import SandboxV2IAMService
from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.config import Settings


class DummySettings:
    iam_enabled = False; sso_enabled = False; iam_provider = "disabled"
    oidc_enabled = False; saml_enabled = False
    real_oidc_login_enabled = False; real_saml_login_enabled = False
    oidc_token_exchange_enabled = False; oidc_signature_validation = False
    sso_session_enabled = False; saml_disable_xxe = True


@pytest.fixture
def store():
    return SQLiteSandboxV2Store(Settings(), db_path=":memory:")


class TestSSOSession:
    def test_create_session_no_token(self, store):
        audit = SandboxV2SecurityAuditService(store=store)
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=DummySettings())
        session = svc.create_sso_session(
            principal_id="ext:user-1", principal_type="user",
            organization_id="org-1", roles=["viewer"], scopes=["read"],
        )
        assert session is not None
        d = session.to_dict()
        assert "token" not in str(d).lower() or "token_storage" in str(d).lower()

    def test_list_sessions(self, store):
        audit = SandboxV2SecurityAuditService(store=store)
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=DummySettings())
        svc.create_sso_session(principal_id="u1", organization_id="org-1", roles=["viewer"])
        sessions = svc.list_sso_sessions(organization_id="org-1")
        assert len(sessions) >= 1

    def test_revoke_session(self, store):
        audit = SandboxV2SecurityAuditService(store=store)
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=DummySettings())
        s = svc.create_sso_session(principal_id="u1", organization_id="org-1")
        result = svc.revoke_sso_session(s.session_id, "test")
        assert result["revoked"]

    def test_get_session(self, store):
        audit = SandboxV2SecurityAuditService(store=store)
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=DummySettings())
        s = svc.create_sso_session(principal_id="u1", organization_id="org-1")
        fetched = svc.get_sso_session(s.session_id)
        assert fetched is not None

    def test_real_sso_readiness(self, store):
        audit = SandboxV2SecurityAuditService(store=store)
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=DummySettings())
        r = svc.get_real_sso_readiness()
        assert not r["real_oidc_login_enabled"]
        assert not r["oidc_signature_validation"]
        assert not r["token_storage"]
        assert r["sso_safe_mode"]
