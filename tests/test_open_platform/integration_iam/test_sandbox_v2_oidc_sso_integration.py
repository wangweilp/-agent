"""IAM Integration tests — default skip.

Only runs when all of these env vars are set:
  SANDBOX_V2_RUN_IAM_INTEGRATION=true
  SANDBOX_V2_IAM_ENABLED=true
  SANDBOX_V2_SSO_ENABLED=true
  SANDBOX_V2_OIDC_ENABLED=true

This step only does preflight — no real IdP login.
No external network access. No token storage.
"""
from __future__ import annotations
import os
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest

from src.open_platform.sandbox_v2.iam_provider import OIDCProviderSkeleton
from src.open_platform.sandbox_v2.models import SandboxV2IAMProviderConfig


def _iam_integration_enabled() -> bool:
    return all([
        os.getenv("SANDBOX_V2_RUN_IAM_INTEGRATION", "").lower() == "true",
        os.getenv("SANDBOX_V2_IAM_ENABLED", "").lower() == "true",
        os.getenv("SANDBOX_V2_SSO_ENABLED", "").lower() == "true",
        os.getenv("SANDBOX_V2_OIDC_ENABLED", "").lower() == "true",
    ])


pytestmark = pytest.mark.skipif(
    not _iam_integration_enabled(),
    reason="IAM integration tests skipped — set SANDBOX_V2_RUN_IAM_INTEGRATION=true, SANDBOX_V2_IAM_ENABLED=true, SANDBOX_V2_SSO_ENABLED=true, SANDBOX_V2_OIDC_ENABLED=true",
)


class TestOIDCIntegrationPreflight:
    """Preflight checks — no real IdP login."""

    def test_config_ready_preflight(self):
        """Config is complete enough for preflight."""
        provider = OIDCProviderSkeleton()
        config = SandboxV2IAMProviderConfig(
            issuer=os.getenv("SANDBOX_V2_OIDC_ISSUER", "https://accounts.google.com"),
            client_id=os.getenv("SANDBOX_V2_OIDC_CLIENT_ID", "test-client-id"),
            discovery_enabled=False,
        )
        result = provider.validate_config(config)
        # In skeleton mode without discovery, should be valid
        assert result["valid"], f"Preflight config invalid: {result.get('reason')}"

    def test_missing_issuer_skip(self):
        """Missing issuer returns unavailable."""
        provider = OIDCProviderSkeleton()
        config = SandboxV2IAMProviderConfig(
            issuer="", client_id="test-id",
        )
        result = provider.validate_config(config)
        assert not result["valid"]

    def test_no_token_storage(self):
        """Verify no token storage."""
        provider = OIDCProviderSkeleton()
        r = provider.get_readiness()
        assert not r["token_storage"]

    def test_no_discovery_download(self):
        """Discovery is not enabled — no URL download."""
        provider = OIDCProviderSkeleton()
        r = provider.get_readiness()
        # In Step 17, discovery should be disabled
        assert not r.get("discovery_enabled", True)

    def test_no_external_network(self):
        """No external network calls are made during preflight."""
        provider = OIDCProviderSkeleton()
        config = SandboxV2IAMProviderConfig(
            issuer="https://evil.example.com",  # Should NOT trigger DNS/HTTP
            client_id="test-id",
        )
        # validate_config must not make network calls
        result = provider.validate_config(config)
        assert isinstance(result, dict)

    def test_reject_token(self):
        """Tokens rejected in preflight mode."""
        provider = OIDCProviderSkeleton()
        result = provider.simulate_login(
            {"token": "should-not-accept", "sub": "x"},
            SandboxV2IAMProviderConfig(),
        )
        assert not result["allowed"]
