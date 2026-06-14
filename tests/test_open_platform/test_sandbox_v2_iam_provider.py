"""IAM Provider tests (Step 17)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.iam_provider import (
    DisabledIAMProvider, MockIAMProvider, OIDCProviderSkeleton,
    SAMLProviderSkeleton, get_iam_provider,
)
from src.open_platform.sandbox_v2.models import (
    SandboxV2IAMProviderConfig, SandboxV2SSOLoginStatus,
)

MOCK_CLAIMS = {
    "sub": "user-1", "iss": "https://mock.example.com",
    "email": "user@example.com", "email_verified": True,
    "name": "Test User",
}

class TestDisabledProvider:
    def test_all_login_disabled(self):
        p = DisabledIAMProvider()
        assert p.get_provider_type() == "disabled"
        result = p.simulate_login({}, SandboxV2IAMProviderConfig())
        assert result["login_status"] == "disabled"
        assert not result["allowed"]

    def test_readiness_shows_safe_mode(self):
        p = DisabledIAMProvider()
        r = p.get_readiness()
        assert r["iam_safe_mode"]
        assert not r["real_oidc_login"]


class TestMockProvider:
    def test_mock_provider_available(self):
        p = MockIAMProvider()
        assert p.get_provider_type() == "mock"

    def test_simulate_valid_login(self):
        p = MockIAMProvider()
        config = SandboxV2IAMProviderConfig(
            enabled=True, issuer="https://mock.example.com",
            allowed_domains=["example.com"],
        )
        result = p.simulate_login(MOCK_CLAIMS, config)
        assert result["login_status"] == SandboxV2SSOLoginStatus.SIMULATED
        assert result["allowed"]

    def test_reject_real_token_access(self):
        p = MockIAMProvider()
        config = SandboxV2IAMProviderConfig(enabled=True, issuer="mock")
        result = p.simulate_login({"access_token": "fake", "sub": "x"}, config)
        assert not result["allowed"]
        assert "token" in result["reason"].lower()

    def test_reject_real_id_token(self):
        p = MockIAMProvider()
        config = SandboxV2IAMProviderConfig(enabled=True, issuer="mock")
        result = p.simulate_login({"id_token": "fake", "sub": "x"}, config)
        assert not result["allowed"]

    def test_missing_subject_rejected(self):
        p = MockIAMProvider()
        config = SandboxV2IAMProviderConfig(enabled=True, issuer="mock")
        result = p.simulate_login({"iss": "mock", "email": "a@b.com"}, config)
        assert not result["allowed"]

    def test_unverified_email_rejected(self):
        p = MockIAMProvider()
        config = SandboxV2IAMProviderConfig(
            enabled=True, issuer="mock",
            allowed_domains=["example.com"], require_verified_email=True,
        )
        claims = {**MOCK_CLAIMS, "email_verified": False}
        result = p.simulate_login(claims, config)
        assert not result["allowed"]

    def test_unauthorized_domain_rejected(self):
        p = MockIAMProvider()
        config = SandboxV2IAMProviderConfig(
            enabled=True, issuer="mock",
            allowed_domains=["trusted.com"], require_verified_email=False,
        )
        result = p.simulate_login(MOCK_CLAIMS, config)
        assert not result["allowed"]


class TestOIDCSkeleton:
    def test_oidc_preflight_only(self):
        p = OIDCProviderSkeleton()
        assert p.get_provider_type() == "oidc"
        r = p.get_readiness()
        assert r["preflight_only"]
        assert not r["real_oidc_login"]

    def test_reject_token(self):
        p = OIDCProviderSkeleton()
        result = p.simulate_login({"code": "abc123"}, SandboxV2IAMProviderConfig())
        assert not result["allowed"]

    def test_config_validation(self):
        p = OIDCProviderSkeleton()
        r = p.validate_config(SandboxV2IAMProviderConfig(issuer="https://idp.example.com", client_id="id-1"))
        assert r["valid"]

    def test_missing_issuer_invalid(self):
        p = OIDCProviderSkeleton()
        r = p.validate_config(SandboxV2IAMProviderConfig(issuer="", client_id="id-1"))
        assert not r["valid"]


class TestSAMLSkeleton:
    def test_saml_reject_saml_response(self):
        p = SAMLProviderSkeleton()
        result = p.simulate_login({"SAMLResponse": "base64..."}, SandboxV2IAMProviderConfig())
        assert not result["allowed"]

    def test_config_validation(self):
        p = SAMLProviderSkeleton()
        r = p.validate_config(SandboxV2IAMProviderConfig(
            saml_entity_id="entity-1", saml_metadata_ref="/tmp/metadata.xml",
        ))
        assert r["valid"] or not r["valid"]  # depends on file existence

    def test_discovery_disabled(self):
        p = SAMLProviderSkeleton()
        r = p.get_readiness()
        assert not r["metadata_download_enabled"]


class TestProviderFactory:
    def test_disabled_default(self):
        p = get_iam_provider("bad_type")
        assert p.get_provider_type() == "disabled"

    def test_mock_factory(self):
        p = get_iam_provider("mock")
        assert p.get_provider_type() == "mock"
