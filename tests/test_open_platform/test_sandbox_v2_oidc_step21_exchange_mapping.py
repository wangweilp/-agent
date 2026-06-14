"""Step 21 — Token Exchange + Identity Mapping tests.

Covers:
- Token Exchange disabled by default
- Token Exchange with no http client → fail closed
- Token Exchange happy path (id_token validated, tokens not persisted)
- Identity Mapping default deny + happy path
- Step 21 Service readiness aggregation
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from src.open_platform.sandbox_v2.oidc_discovery import (
    SandboxV2JWKSCacheService,
    SandboxV2OIDCDiscoveryService,
)
from src.open_platform.sandbox_v2.oidc_identity_validation import (
    SandboxV2OIDCIdentityValidationService,
)
from src.open_platform.sandbox_v2.oidc_step21_service import (
    SandboxV2OIDCStep21Service,
)
from src.open_platform.sandbox_v2.oidc_token_exchange import (
    SandboxV2OIDCIdentityMappingService,
    SandboxV2OIDCTokenExchangeService,
)
from tests.test_open_platform.oidc_step21_fixtures import (
    Step21Settings,
    generate_rsa_keypair,
    sign_jwt,
    valid_claims,
)

ISSUER = "https://idp.example.com"
AUDIENCE = "test-client-id"
NONCE = "test-nonce-value"
JWKS_URI = "https://idp.example.com/.well-known/jwks.json"


class _StubTokenEndpoint:
    """Stub token endpoint — returns id_token only (no access/refresh tokens)."""

    def __init__(self, id_token: str):
        self._id_token = id_token

    def exchange_code(self, token_endpoint, code, redirect_uri, client_id,
                      client_secret="", code_verifier="", timeout=10.0):
        return {"id_token": self._id_token}


class TestTokenExchangeDefaults:
    def test_disabled_by_default(self):
        svc = SandboxV2OIDCTokenExchangeService(settings=Step21Settings())
        result = svc.exchange(code="abc")
        assert not result.allowed
        assert "disabled" in result.reason.lower()
        assert result.fail_closed is False  # disabled ≠ fail

    def test_no_http_client_fail_closed(self):
        svc = SandboxV2OIDCTokenExchangeService(
            settings=Step21Settings(oidc_token_exchange_enabled=True,
                                    oidc_token_endpoint="https://idp.example.com/token"),
        )
        result = svc.exchange(code="abc")
        assert not result.allowed
        assert result.fail_closed is True

    def test_no_code_rejected(self):
        svc = SandboxV2OIDCTokenExchangeService(
            settings=Step21Settings(oidc_token_exchange_enabled=True,
                                    oidc_token_endpoint="https://idp.example.com/token"),
            token_endpoint_client=_StubTokenEndpoint("ignored"),
        )
        result = svc.exchange(code="")
        assert not result.allowed
        assert "code" in result.reason.lower()


class TestTokenExchangeHappyPath:
    def test_exchange_validates_id_token_and_drops_other_tokens(self):
        priv, jwk = generate_rsa_keypair(kid="k-ex")
        settings = Step21Settings(
            oidc_jwks_uri=JWKS_URI,
            oidc_token_exchange_enabled=True,
            oidc_token_endpoint="https://idp.example.com/token",
            oidc_client_id=AUDIENCE,
        )
        discovery = SandboxV2OIDCDiscoveryService(settings=settings)
        jwks_cache = SandboxV2JWKSCacheService(settings=settings, discovery_service=discovery)
        jwks_cache.seed_static_jwks(ISSUER, JWKS_URI, {jwk["kid"]: jwk})
        validator = SandboxV2OIDCIdentityValidationService(
            settings=settings, jwks_cache=jwks_cache, discovery=discovery,
        )
        id_token = sign_jwt(priv, claims=valid_claims(), kid="k-ex")
        token_svc = SandboxV2OIDCTokenExchangeService(
            settings=settings, identity_validator=validator,
            token_endpoint_client=_StubTokenEndpoint(id_token),
        )
        nonce_hash = hashlib.sha256(NONCE.encode()).hexdigest()
        result = token_svc.exchange(
            code="auth-code-123",
            issuer=ISSUER, client_id=AUDIENCE,
            expected_nonce_hash=nonce_hash,
        )
        assert result.allowed
        assert result.id_token_received
        # access/refresh token never appear in result
        out = result.to_dict()
        assert "access_token" not in out
        assert "refresh_token" not in out
        assert "id_token" not in out
        # validation details attached
        assert out["id_token_validation"]["valid"] is True


class TestIdentityMapping:
    def test_mapping_denies_unvalidated_identity(self):
        svc = SandboxV2OIDCIdentityMappingService(settings=Step21Settings())
        # Construct an unvalidated result stub
        from src.open_platform.sandbox_v2.models import (
            SandboxV2OIDCIdentityValidationResult,
        )
        unvalidated = SandboxV2OIDCIdentityValidationResult(valid=False, reason="not validated")
        mapping = svc.map_validated_identity(unvalidated)
        assert not mapping.allowed
        assert "not validated" in mapping.reason.lower()

    def test_mapping_happy_path_no_elevated_roles(self):
        priv, jwk = generate_rsa_keypair(kid="k-map")
        settings = Step21Settings(oidc_jwks_uri=JWKS_URI)
        discovery = SandboxV2OIDCDiscoveryService(settings=settings)
        jwks_cache = SandboxV2JWKSCacheService(settings=settings, discovery_service=discovery)
        jwks_cache.seed_static_jwks(ISSUER, JWKS_URI, {jwk["kid"]: jwk})
        validator = SandboxV2OIDCIdentityValidationService(
            settings=settings, jwks_cache=jwks_cache, discovery=discovery,
        )
        id_token = sign_jwt(priv, claims=valid_claims(), kid="k-map")
        nonce_hash = hashlib.sha256(NONCE.encode()).hexdigest()
        validation = validator.validate_id_token(
            id_token, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=nonce_hash,
        )
        assert validation.valid
        map_svc = SandboxV2OIDCIdentityMappingService(settings=settings)
        mapping = map_svc.map_validated_identity(validation)
        assert mapping.allowed
        assert mapping.principal_id.startswith("ext:")
        # default_role is viewer (never elevated)
        assert "owner" not in mapping.mapped_roles
        assert "admin" not in mapping.mapped_roles
        # token_storage invariant
        assert mapping.to_dict()["token_storage"] is False
        assert mapping.sso_session_created is False  # session disabled by default


class TestStep21ServiceReadiness:
    def test_default_disabled_all(self):
        svc = SandboxV2OIDCStep21Service(settings=Step21Settings(oidc_signature_validation_enabled=False))
        rd = svc.get_oidc_validation_readiness()
        assert rd["signature_validation"]["status"] == "disabled"
        assert rd["oidc_discovery"]["status"] == "disabled"
        assert rd["jwks_cache"]["status"] == "disabled"
        assert rd["token_exchange"]["status"] == "disabled"
        # identity mapping is always logically available (Step 17 mapper exists)
        assert rd["identity_mapping"]["status"] == "ready"
        assert rd["token_storage"] is False
        assert rd["fail_closed"] is True

    def test_signature_enabled_shows_not_ready_without_jwks(self):
        svc = SandboxV2OIDCStep21Service(
            settings=Step21Settings(
                oidc_signature_validation_enabled=True,
                oidc_jwks_uri="",  # no source → not ready
            ),
        )
        rd = svc.get_oidc_validation_readiness()
        assert rd["signature_validation"]["enabled"] is True
        assert rd["signature_validation"]["status"] == "not_ready"  # no key source

    def test_signature_enabled_ready_with_static_jwks(self):
        svc = SandboxV2OIDCStep21Service(
            settings=Step21Settings(
                oidc_signature_validation_enabled=True,
                oidc_jwks_uri=JWKS_URI,
            ),
        )
        rd = svc.get_oidc_validation_readiness()
        assert rd["signature_validation"]["enabled"] is True
        assert rd["signature_validation"]["status"] == "ready"
