"""Step 21 — OIDC Identity Validation Red-Team Tests (5).

攻击场景验证 — 全部必须拒绝 (valid=False):
 1. alg=none 必须拒绝
 2. unsigned token 必须拒绝
 3. wrong issuer 必须拒绝
 4. wrong audience 必须拒绝
 5. replay nonce 必须拒绝
 + fail closed 验证 (JWKS 拉取失败时绝不放行)
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
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
from tests.test_open_platform.oidc_step21_fixtures import (
    Step21Settings,
    generate_rsa_keypair,
    sign_jwt,
    sign_unsigned_jwt,
    valid_claims,
)

ISSUER = "https://idp.example.com"
AUDIENCE = "test-client-id"
NONCE = "test-nonce-value"


class _RaisingHttpFetcher:
    """HTTP fetcher that always raises — forces fail-closed path."""

    def get_json(self, url, timeout=10.0):
        raise RuntimeError("network unavailable (red-team fail-closed simulation)")


def _make_validator(kids_to_keys=None, settings=None, jwks_uri="https://idp.example.com/.well-known/jwks.json"):
    settings = settings or Step21Settings(oidc_jwks_uri=jwks_uri)
    discovery = SandboxV2OIDCDiscoveryService(settings=settings)
    jwks_cache = SandboxV2JWKSCacheService(settings=settings, discovery_service=discovery)
    if kids_to_keys:
        jwks_cache.seed_static_jwks(ISSUER, jwks_uri, kids_to_keys)
    return SandboxV2OIDCIdentityValidationService(
        settings=settings, jwks_cache=jwks_cache, discovery=discovery,
    )


def _nonce_hash():
    return hashlib.sha256(NONCE.encode()).hexdigest()


# ───────────────────────────────────────────────
# Red-Team 1: alg=none
# ───────────────────────────────────────────────


class TestRedTeamAlgNone:
    def test_alg_none_rejected(self):
        priv, jwk = generate_rsa_keypair(kid="k-rt1")
        validator = _make_validator(kids_to_keys={jwk["kid"]: jwk})
        # Craft an alg=none token manually
        unsigned = sign_unsigned_jwt(valid_claims(), kid="k-rt1")
        result = validator.validate_id_token(
            unsigned, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=_nonce_hash(),
        )
        assert not result.valid
        assert not result.alg_allowed
        assert "alg=none" in result.reason or "none" in result.reason.lower()


# ───────────────────────────────────────────────
# Red-Team 2: unsigned token (3-segment with empty signature)
# ───────────────────────────────────────────────


class TestRedTeamUnsignedToken:
    def test_unsigned_token_rejected(self):
        priv, jwk = generate_rsa_keypair(kid="k-rt2")
        validator = _make_validator(kids_to_keys={jwk["kid"]: jwk})
        # Same as alg=none but framed as "unsigned" attack
        unsigned = sign_unsigned_jwt(valid_claims(), kid="k-rt2")
        result = validator.validate_id_token(
            unsigned, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=_nonce_hash(),
        )
        assert not result.valid
        assert not result.signature_valid


# ───────────────────────────────────────────────
# Red-Team 3: wrong issuer
# ───────────────────────────────────────────────


class TestRedTeamWrongIssuer:
    def test_wrong_issuer_rejected(self):
        priv, jwk = generate_rsa_keypair(kid="k-rt3")
        validator = _make_validator(kids_to_keys={jwk["kid"]: jwk})
        # Token legitimately signed but claims a forged issuer
        token = sign_jwt(priv, claims=valid_claims(issuer="https://evil-idp.example.com"), kid="k-rt3")
        result = validator.validate_id_token(
            token, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=_nonce_hash(),
        )
        assert not result.valid
        assert not result.iss_valid


# ───────────────────────────────────────────────
# Red-Team 4: wrong audience
# ───────────────────────────────────────────────


class TestRedTeamWrongAudience:
    def test_wrong_audience_rejected(self):
        priv, jwk = generate_rsa_keypair(kid="k-rt4")
        validator = _make_validator(kids_to_keys={jwk["kid"]: jwk})
        # Legitimately signed but intended for a different client
        token = sign_jwt(priv, claims=valid_claims(audience="victim-other-client"), kid="k-rt4")
        result = validator.validate_id_token(
            token, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=_nonce_hash(),
        )
        assert not result.valid
        assert not result.aud_valid


# ───────────────────────────────────────────────
# Red-Team 5: replay nonce
# ───────────────────────────────────────────────


class TestRedTeamReplayNonce:
    def test_replay_nonce_rejected(self):
        priv, jwk = generate_rsa_keypair(kid="k-rt5")
        validator = _make_validator(kids_to_keys={jwk["kid"]: jwk})
        # Token uses a DIFFERENT nonce than what the validator expects (replay attempt)
        token = sign_jwt(priv, claims=valid_claims(nonce="captured-from-prior-flow"), kid="k-rt5")
        result = validator.validate_id_token(
            token, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=_nonce_hash(),  # validator expects NONCE, token has different
        )
        assert not result.valid
        assert not result.nonce_valid
        assert "nonce" in result.reason.lower()


# ───────────────────────────────────────────────
# Bonus Red-Team: fail closed when JWKS fetch fails
# ───────────────────────────────────────────────


class TestRedTeamFailClosed:
    def test_jwks_fetch_failure_blocks_validation(self):
        """If JWKS is unreachable, the validator MUST NOT skip verification."""
        priv, jwk = generate_rsa_keypair(kid="k-fc")
        # No static seeding + raising HTTP fetcher → JWKS fetch fails → fail closed
        settings = Step21Settings(
            oidc_jwks_uri="https://idp.example.com/.well-known/jwks.json",
            oidc_jwks_fetch_enabled=True,
        )
        discovery = SandboxV2OIDCDiscoveryService(settings=settings, http_fetcher=_RaisingHttpFetcher())
        jwks_cache = SandboxV2JWKSCacheService(
            settings=settings, http_fetcher=_RaisingHttpFetcher(),
            discovery_service=discovery,
        )
        validator = SandboxV2OIDCIdentityValidationService(
            settings=settings, jwks_cache=jwks_cache, discovery=discovery,
        )
        token = sign_jwt(priv, claims=valid_claims(), kid="k-fc")
        result = validator.validate_id_token(
            token, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=_nonce_hash(),
        )
        # Must NOT validate — signature invalid because key unavailable
        assert not result.valid
        assert not result.signature_valid

    def test_step21_default_disabled_blocks_everything(self):
        """Step 21 service with default settings does not perform validation."""
        svc = SandboxV2OIDCStep21Service(settings=Step21Settings(oidc_signature_validation_enabled=False))
        result = svc.validate_id_token("any.invalid.token", expected_issuer=ISSUER)
        assert not result.valid
        rd = svc.get_oidc_validation_readiness()
        assert rd["signature_validation"]["status"] == "disabled"
        assert rd["token_storage"] is False
        assert rd["fail_closed"] is True

    def test_no_token_persisted_in_results(self):
        """Ensure no token (id/access/refresh) is ever persisted in any result structure."""
        priv, jwk = generate_rsa_keypair(kid="k-nt")
        validator = _make_validator(kids_to_keys={jwk["kid"]: jwk})
        token = sign_jwt(priv, claims=valid_claims(), kid="k-nt")
        result = validator.validate_id_token(
            token, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=_nonce_hash(),
        )
        out = result.to_dict()
        blob = str(out)
        # No raw JWT segments should appear
        assert "eyJ" not in blob
        # No access/refresh token fields
        assert "access_token" not in out
        assert "refresh_token" not in out
        # Sensitive claim keys redacted if present
        for k in ("id_token", "at_hash", "c_hash"):
            if k in out.get("claims", {}):
                assert out["claims"][k] == "***REDACTED***"
