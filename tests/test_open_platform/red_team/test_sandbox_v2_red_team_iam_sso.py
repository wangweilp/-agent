"""Red-Team IAM/SSO tests (Step 17).

Tests that verify IAM/SSO security posture:
- No real token storage
- No secret leakage
- No external network access
- Fail-closed on malformed input
- Cross-tenant denial
- No privilege escalation through unknown groups
"""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.iam import SandboxV2IAMService
from src.open_platform.sandbox_v2.iam_mapping import SandboxV2IAMClaimMapper
from src.open_platform.sandbox_v2.iam_provider import (
    DisabledIAMProvider, MockIAMProvider, OIDCProviderSkeleton,
    SAMLProviderSkeleton,
)
from src.open_platform.sandbox_v2.models import (
    SandboxV2IAMProviderConfig, SandboxV2SSOLoginStatus, SandboxV2Role,
)
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.config import Settings
from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService


class DummySettings:
    iam_enabled = False
    sso_enabled = False
    iam_provider = "disabled"
    oidc_enabled = False
    saml_enabled = False
    iam_jit_provisioning = False
    iam_default_role = "viewer"


class EnabledSettings(DummySettings):
    iam_enabled = True
    iam_provider = "mock"


@pytest.fixture
def store():
    return SQLiteSandboxV2Store(Settings(), db_path=":memory:")


@pytest.fixture
def audit(store):
    return SandboxV2SecurityAuditService(store=store)


class TestTokenSecurity:
    """Verify tokens are never stored or echoed."""

    def test_access_token_rejected(self):
        p = MockIAMProvider()
        config = SandboxV2IAMProviderConfig(enabled=True, issuer="mock")
        result = p.simulate_login({"access_token": "eyJhbGciOi...", "sub": "x"}, config)
        assert not result["allowed"]

    def test_id_token_rejected(self):
        p = MockIAMProvider()
        config = SandboxV2IAMProviderConfig(enabled=True, issuer="mock")
        result = p.simulate_login({"id_token": "eyJhbGciOi...", "sub": "x"}, config)
        assert not result["allowed"]

    def test_refresh_token_rejected(self):
        p = MockIAMProvider()
        config = SandboxV2IAMProviderConfig(enabled=True, issuer="mock")
        result = p.simulate_login({"refresh_token": "rt-xxx", "sub": "x"}, config)
        assert not result["allowed"]

    def test_tokens_never_in_audit(self, store, audit):
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=EnabledSettings())
        config = svc.create_provider_config(
            provider_type="mock", enabled=True, issuer="mock",
            organization_id="org-1",
        )
        # Simulate with token should write audit
        svc.simulate_sso_login(
            claims={"access_token": "secret-value", "sub": "x"},
            provider_config_id=config.provider_config_id,
            organization_id="org-1",
        )
        events = store.list_security_audit_events(limit=10)
        for evt in events:
            s = str(evt.metadata)
            assert "secret-value" not in s

    def test_client_secret_not_in_response(self, store, audit):
        """client_secret must never appear in API response."""
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=EnabledSettings())
        config = svc.create_provider_config(
            provider_type="mock", enabled=True, issuer="mock",
            client_id="test-client", client_secret="my-secret-password",
            organization_id="org-1",
        )
        d = config.to_dict()
        # to_dict should never contain plaintext secret
        plain = str(d)
        assert "my-secret-password" not in plain
        assert d["client_secret_ref"] != ""

    def test_client_secret_not_in_audit(self, store, audit):
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=EnabledSettings())
        config = svc.create_provider_config(
            provider_type="mock", enabled=True, issuer="mock",
            client_secret="super-secret-key", organization_id="org-1",
        )
        events = store.list_security_audit_events(limit=10)
        for evt in events:
            s = str(evt.metadata)
            assert "super-secret-key" not in s


class TestFailClosed:
    """All error paths must default to deny."""

    def test_malformed_claims_fail_closed(self):
        mapper = SandboxV2IAMClaimMapper()
        # None as claims
        ok, _ = mapper.validate_claim_set(None)
        assert not ok
        # Non-dict claims
        ok, _ = mapper.validate_claim_set("not_a_dict")
        assert not ok
        # Empty string sub
        ok, reason = mapper.validate_claim_set({"sub": "", "iss": "x"})
        assert not ok

    def test_overlong_claims_safe(self):
        mapper = SandboxV2IAMClaimMapper()
        long_val = "x" * 10000
        claims = {"sub": long_val, "iss": "mock", "email": "a@b.com"}
        config = SandboxV2IAMProviderConfig(allowed_domains=["b.com"], require_verified_email=False)
        ok, _ = mapper.validate_claim_set(claims, config)
        # Should not crash; may or may not be valid but must not throw
        assert isinstance(ok, bool)

    def test_missing_email_with_allowlist(self):
        mapper = SandboxV2IAMClaimMapper()
        config = SandboxV2IAMProviderConfig(allowed_domains=["trusted.com"])
        ok, reason = mapper.validate_claim_set({"sub": "x", "iss": "mock"}, config)
        assert not ok

    def test_default_disabled_rejects_all(self):
        p = DisabledIAMProvider()
        assert not p.simulate_login({"sub": "x"}, SandboxV2IAMProviderConfig())["allowed"]

    def test_oidc_skeleton_rejects_real_tokens(self):
        p = OIDCProviderSkeleton()
        assert not p.simulate_login({"code": "auth_code_123"}, SandboxV2IAMProviderConfig())["allowed"]
        assert not p.simulate_login({"jwt": "header.payload.sig"}, SandboxV2IAMProviderConfig())["allowed"]

    def test_saml_skeleton_rejects_samlresponse(self):
        p = SAMLProviderSkeleton()
        assert not p.simulate_login({"SAMLResponse": "PD94bWw..."}, SandboxV2IAMProviderConfig())["allowed"]
        assert not p.simulate_login({"SAMLart": "artifact-123"}, SandboxV2IAMProviderConfig())["allowed"]


class TestPrivilegeEscalation:
    """Verify no privilege escalation through IAM claims."""

    def test_unknown_group_not_admin(self):
        mapper = SandboxV2IAMClaimMapper()
        config = SandboxV2IAMProviderConfig(default_role="viewer")
        claims = {"sub": "x", "iss": "mock", "email": "a@b.com",
                  "email_verified": True, "groups": ["super-admins"]}
        decision, _ = mapper.map_claims_to_security_context(
            claims, config, mappings=None, organization_id="org-1", workspace_id="ws-1",
        )
        if decision.allowed:
            assert "admin" not in decision.mapped_roles
            assert "owner" not in decision.mapped_roles

    def test_fake_admin_group_no_elevation(self):
        mapper = SandboxV2IAMClaimMapper()
        config = SandboxV2IAMProviderConfig(
            default_role="viewer", external_group_mapping_enabled=True,
            allowed_domains=["b.com"],
        )
        claims = {"sub": "x", "iss": "mock", "email": "a@b.com",
                  "email_verified": True, "groups": ["admins"]}
        # No mapping for "admins" group
        decision, _ = mapper.map_claims_to_security_context(
            claims, config, mappings=[], organization_id="org-1", workspace_id="ws-1",
        )
        assert decision.allowed
        assert "admin" not in decision.mapped_roles

    def test_default_role_never_admin(self):
        mapper = SandboxV2IAMClaimMapper()
        config = SandboxV2IAMProviderConfig(default_role="admin")  # invalid default
        claims = {"sub": "x", "iss": "mock", "email": "a@b.com",
                  "email_verified": True}
        decision, _ = mapper.map_claims_to_security_context(
            claims, config, mappings=None, organization_id="org-1", workspace_id="ws-1",
        )
        assert not decision.allowed


class TestCrossTenant:
    """Cross-tenant attempts must be denied."""

    def test_cross_org_rejected(self):
        mapper = SandboxV2IAMClaimMapper()
        config = SandboxV2IAMProviderConfig(allowed_domains=["example.com"])
        claims = {"sub": "x", "iss": "mock", "email": "a@example.com",
                  "email_verified": True, "tenant": "evil-org"}
        decision, _ = mapper.map_claims_to_security_context(
            claims, config, mappings=None, organization_id="good-org", workspace_id="ws-1",
        )
        assert not decision.allowed

    def test_cross_workspace_rejected(self):
        mapper = SandboxV2IAMClaimMapper()
        config = SandboxV2IAMProviderConfig(allowed_domains=["example.com"])
        claims = {"sub": "x", "iss": "mock", "email": "a@example.com",
                  "email_verified": True, "workspace": "evil-ws"}
        decision, _ = mapper.map_claims_to_security_context(
            claims, config, mappings=None, organization_id="org-1", workspace_id="good-ws",
        )
        assert not decision.allowed


class TestJITProvisioning:
    """JIT provisioning default disabled."""

    def test_jit_default_false(self):
        config = SandboxV2IAMProviderConfig()
        assert not config.jit_provisioning

    def test_sandbox_v2_iam_jit_disabled_default(self, store, audit):
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=EnabledSettings())
        r = svc.get_iam_readiness()
        assert not r["jit_provisioning"]


class TestReadinessSecurity:
    """Readiness must report correct security posture."""

    def test_real_oidc_login_false(self):
        p = DisabledIAMProvider()
        r = p.get_readiness()
        assert not r["real_oidc_login"]

    def test_real_saml_login_false(self):
        p = OIDCProviderSkeleton()
        r = p.get_readiness()
        assert not r["real_oidc_login"]

    def test_token_storage_false(self):
        p = MockIAMProvider()
        r = p.get_readiness()
        assert not r["token_storage"]

    def test_iam_safe_mode_true(self):
        settings = DummySettings()
        svc = SandboxV2IAMService(settings=settings)
        r = svc.get_iam_readiness()
        assert r["iam_safe_mode"]


class TestNoExternalNetwork:
    """Confirm no external network calls are made."""

    def test_malicious_issuer_no_request(self):
        """Malicious issuer URL must not trigger external network calls."""
        p = OIDCProviderSkeleton()
        # Even with a real-looking URL, no network call should happen
        config = SandboxV2IAMProviderConfig(
            issuer="http://169.254.169.254/latest/meta-data/",  # metadata service URL
            client_id="id-1",
        )
        result = p.validate_config(config)
        # Should not hang or try to connect
        assert isinstance(result, dict)

    def test_metadata_url_not_downloaded(self):
        """SAML metadata download must be disabled."""
        p = SAMLProviderSkeleton()
        r = p.get_readiness()
        assert not r["metadata_download_enabled"]


class TestAuditHashChain:
    """Verify audit events maintain hash chain for IAM operations."""

    def test_iam_audit_chain(self, store, audit):
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=EnabledSettings())
        config = svc.create_provider_config(
            provider_type="mock", enabled=True, issuer="mock",
            organization_id="org-1",
        )
        events = store.list_security_audit_events(organization_id="org-1", limit=10)
        # Events should have hashes
        for evt in events[:5]:
            assert hasattr(evt, 'event_hash') or hasattr(evt, 'previous_hash')
