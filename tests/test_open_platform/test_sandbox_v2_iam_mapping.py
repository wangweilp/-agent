"""Claim Mapper tests (Step 17 IAM/SSO)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.iam_mapping import SandboxV2IAMClaimMapper
from src.open_platform.sandbox_v2.models import (
    SandboxV2IAMProviderConfig, SandboxV2IAMRoleMapping,
    SandboxV2IAMMappingStatus, SandboxV2Role,
)

MOCK_CLAIMS = {
    "sub": "user-123", "iss": "https://mock-idp.example.com",
    "email": "user@example.com", "email_verified": True,
    "name": "Test User", "groups": ["developers"],
}

class TestClaimValidation:
    def test_missing_subject_denied(self):
        mapper = SandboxV2IAMClaimMapper()
        ok, reason = mapper.validate_claim_set({"iss": "x", "email": "a@b.com"})
        assert not ok
        assert "subject" in reason.lower()

    def test_missing_issuer_denied(self):
        mapper = SandboxV2IAMClaimMapper()
        ok, reason = mapper.validate_claim_set({"sub": "x", "email": "a@b.com"})
        assert not ok
        assert "issuer" in reason.lower()

    def test_empty_claims_denied(self):
        mapper = SandboxV2IAMClaimMapper()
        ok, _ = mapper.validate_claim_set({})
        assert not ok

    def test_valid_claims_without_provider(self):
        mapper = SandboxV2IAMClaimMapper()
        ok, reason = mapper.validate_claim_set(MOCK_CLAIMS)
        assert ok

    def test_email_verified_required(self):
        mapper = SandboxV2IAMClaimMapper()
        config = SandboxV2IAMProviderConfig(allowed_domains=["example.com"], require_verified_email=True)
        claims = {**MOCK_CLAIMS, "email_verified": False}
        ok, reason = mapper.validate_claim_set(claims, config)
        assert not ok
        assert "verified" in reason.lower()

    def test_email_domain_not_allowed(self):
        mapper = SandboxV2IAMClaimMapper()
        config = SandboxV2IAMProviderConfig(allowed_domains=["trusted.com"], require_verified_email=False)
        ok, reason = mapper.validate_claim_set(MOCK_CLAIMS, config)
        assert not ok
        assert "domain" in reason.lower()

    def test_email_domain_allowed(self):
        mapper = SandboxV2IAMClaimMapper()
        config = SandboxV2IAMProviderConfig(allowed_domains=["example.com"], require_verified_email=False)
        ok, reason = mapper.validate_claim_set(MOCK_CLAIMS, config)
        assert ok


class TestRedaction:
    def test_token_keys_redacted(self):
        mapper = SandboxV2IAMClaimMapper()
        raw = {"access_token": "secret123", "id_token": "secret456", "sub": "user-1"}
        redacted = mapper.redact_claims(raw)
        assert "***REDACTED***" in str(redacted["access_token"])
        assert "***REDACTED***" in str(redacted["id_token"])
        assert redacted["sub"] == "user-1"

    def test_no_token_stored(self):
        mapper = SandboxV2IAMClaimMapper()
        raw = {"refresh_token": "xyz", "client_secret": "abc", "sub": "u"}
        redacted = mapper.redact_claims(raw)
        assert "xyz" not in str(redacted["refresh_token"])
        assert "abc" not in str(redacted["client_secret"])
        assert "***REDACTED***" in str(redacted["refresh_token"])


class TestTenantBoundary:
    def test_tenant_mismatch_rejected(self):
        mapper = SandboxV2IAMClaimMapper()
        claims = {**MOCK_CLAIMS, "tenant": "org-bad"}
        ok, reason = mapper.validate_tenant_boundary(claims, "org-good", "")
        assert not ok

    def test_tenant_match_allowed(self):
        mapper = SandboxV2IAMClaimMapper()
        claims = {**MOCK_CLAIMS, "tenant": "org-1"}
        ok, _ = mapper.validate_tenant_boundary(claims, "org-1", "")
        assert ok

    def test_no_tenant_claim_passes(self):
        mapper = SandboxV2IAMClaimMapper()
        ok, _ = mapper.validate_tenant_boundary(MOCK_CLAIMS, "org-1", "ws-1")
        assert ok


class TestRoleMapping:
    def test_unknown_group_no_elevated(self):
        mapper = SandboxV2IAMClaimMapper()
        config = SandboxV2IAMProviderConfig(default_role="viewer", external_group_mapping_enabled=True)
        claims = {**MOCK_CLAIMS, "groups": ["unknown-group"]}
        mappings = []  # no explicit mapping
        decision, sec_ctx = mapper.map_claims_to_security_context(
            claims, config, mappings=mappings, organization_id="org-1", workspace_id="ws-1",
        )
        assert decision.allowed
        assert "admin" not in decision.mapped_roles
        assert "owner" not in decision.mapped_roles

    def test_default_role_not_admin(self):
        mapper = SandboxV2IAMClaimMapper()
        config = SandboxV2IAMProviderConfig(default_role="admin")
        claims = MOCK_CLAIMS
        decision, _ = mapper.map_claims_to_security_context(
            claims, config, mappings=None, organization_id="org-1", workspace_id="ws-1",
        )
        # admin is elevated — should be rejected if no explicit mapping
        assert not decision.allowed

    def test_default_role_viewer_allowed(self):
        mapper = SandboxV2IAMClaimMapper()
        config = SandboxV2IAMProviderConfig(default_role="viewer", allowed_domains=["example.com"])
        claims = MOCK_CLAIMS
        decision, sec_ctx = mapper.map_claims_to_security_context(
            claims, config, mappings=None, organization_id="org-1", workspace_id="ws-1",
        )
        assert decision.allowed
        assert sec_ctx is not None
        assert "viewer" in sec_ctx.roles

    def test_group_mapping_to_developer(self):
        mapper = SandboxV2IAMClaimMapper()
        config = SandboxV2IAMProviderConfig(
            default_role="viewer", external_group_mapping_enabled=True,
            allowed_domains=["example.com"],
        )
        mapping = SandboxV2IAMRoleMapping(
            external_group="developers", sandbox_role="developer",
            sandbox_scopes=["read", "write"], enabled=True,
        )
        claims = {**MOCK_CLAIMS, "groups": ["developers"]}
        decision, sec_ctx = mapper.map_claims_to_security_context(
            claims, config, mappings=[mapping], organization_id="org-1", workspace_id="ws-1",
        )
        assert decision.allowed
        assert "developer" in decision.mapped_roles
        assert decision.group_mapping_applied

    def test_scope_mapping_effective(self):
        mapper = SandboxV2IAMClaimMapper()
        config = SandboxV2IAMProviderConfig(
            default_role="viewer", external_group_mapping_enabled=True,
            allowed_domains=["example.com"],
        )
        mapping = SandboxV2IAMRoleMapping(
            external_group="operators", sandbox_role="operator",
            sandbox_scopes=["cancel", "kill"], enabled=True,
        )
        claims = {**MOCK_CLAIMS, "groups": ["operators"]}
        decision, sec_ctx = mapper.map_claims_to_security_context(
            claims, config, mappings=[mapping], organization_id="org-1", workspace_id="ws-1",
        )
        assert decision.allowed
        assert "cancel" in decision.mapped_scopes or "cancel" in sec_ctx.scopes

    def test_cross_tenant_claims_rejected(self):
        mapper = SandboxV2IAMClaimMapper()
        config = SandboxV2IAMProviderConfig(allowed_domains=["example.com"])
        claims = {**MOCK_CLAIMS, "tenant": "other-org"}
        decision, _ = mapper.map_claims_to_security_context(
            claims, config, mappings=None, organization_id="my-org", workspace_id="ws-1",
        )
        assert not decision.allowed

    def test_fake_admin_group_rejected(self):
        mapper = SandboxV2IAMClaimMapper()
        config = SandboxV2IAMProviderConfig(default_role="viewer")
        claims = {**MOCK_CLAIMS, "groups": ["fake-admins"]}
        # No mapping for fake-admins group
        decision, _ = mapper.map_claims_to_security_context(
            claims, config, mappings=None, organization_id="org-1", workspace_id="ws-1",
        )
        assert decision.allowed
        assert "admin" not in decision.mapped_roles
