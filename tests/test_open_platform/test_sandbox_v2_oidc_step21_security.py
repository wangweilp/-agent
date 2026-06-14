"""Step 21 — Production-Grade OIDC Identity Validation Security Tests (10).

覆盖：
 1. invalid issuer
 2. invalid audience
 3. expired token
 4. future nbf
 5. nonce mismatch
 6. unknown kid
 7. JWKS rotation
 8. invalid signature
 9. missing claims
10. disabled validation mode

默认 fail closed — 每个用例都断言 valid=False 且不存 token。
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
from src.open_platform.sandbox_v2.models import SandboxV2OIDCValidationMode
from tests.test_open_platform.oidc_step21_fixtures import (
    Step21Settings,
    build_jwks,
    generate_rsa_keypair,
    sign_jwt,
    valid_claims,
)

ISSUER = "https://idp.example.com"
AUDIENCE = "test-client-id"
NONCE = "test-nonce-value"


def _make_validator(settings=None, *, kids_to_keys: dict[str, dict] | None = None,
                    jwks_uri: str = "https://idp.example.com/.well-known/jwks.json"):
    """Build a fully-wired validator with the given keys seeded into the JWKS cache."""
    settings = settings or Step21Settings(oidc_jwks_uri=jwks_uri)
    discovery = SandboxV2OIDCDiscoveryService(settings=settings)
    jwks_cache = SandboxV2JWKSCacheService(settings=settings, discovery_service=discovery)
    if kids_to_keys:
        jwks_cache.seed_static_jwks(ISSUER, jwks_uri, kids_to_keys)
    return SandboxV2OIDCIdentityValidationService(
        settings=settings, jwks_cache=jwks_cache, discovery=discovery,
    )


# ───────────────────────────────────────────────
# 1. invalid issuer
# ───────────────────────────────────────────────


class TestInvalidIssuer:
    def test_issuer_mismatch_rejected(self):
        priv, jwk = generate_rsa_keypair(kid="k1")
        validator = _make_validator(kids_to_keys={jwk["kid"]: jwk})
        # Token signed with a DIFFERENT issuer than expected
        token = sign_jwt(priv, claims=valid_claims(issuer="https://attacker.example.com"), kid=jwk["kid"])
        nonce_hash = hashlib.sha256(NONCE.encode()).hexdigest()
        result = validator.validate_id_token(
            token, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=nonce_hash,
        )
        assert not result.valid
        assert not result.iss_valid
        assert "issuer" in result.reason.lower()
        # token never leaked into result
        assert "eyJ" not in str(result.claims_redacted)


# ───────────────────────────────────────────────
# 2. invalid audience
# ───────────────────────────────────────────────


class TestInvalidAudience:
    def test_audience_mismatch_rejected(self):
        priv, jwk = generate_rsa_keypair(kid="k2")
        validator = _make_validator(kids_to_keys={jwk["kid"]: jwk})
        token = sign_jwt(priv, claims=valid_claims(audience="some-other-client"), kid=jwk["kid"])
        nonce_hash = hashlib.sha256(NONCE.encode()).hexdigest()
        result = validator.validate_id_token(
            token, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=nonce_hash,
        )
        assert not result.valid
        assert not result.aud_valid
        assert "audience" in result.reason.lower()


# ───────────────────────────────────────────────
# 3. expired token
# ───────────────────────────────────────────────


class TestExpiredToken:
    def test_expired_rejected(self):
        priv, jwk = generate_rsa_keypair(kid="k3")
        validator = _make_validator(kids_to_keys={jwk["kid"]: jwk})
        token = sign_jwt(priv, claims=valid_claims(exp_offset=-3600), kid=jwk["kid"])
        nonce_hash = hashlib.sha256(NONCE.encode()).hexdigest()
        result = validator.validate_id_token(
            token, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=nonce_hash,
        )
        assert not result.valid
        assert not result.exp_valid
        assert "expired" in result.reason.lower()


# ───────────────────────────────────────────────
# 4. future nbf
# ───────────────────────────────────────────────


class TestFutureNbf:
    def test_future_nbf_rejected(self):
        priv, jwk = generate_rsa_keypair(kid="k4")
        validator = _make_validator(kids_to_keys={jwk["kid"]: jwk})
        token = sign_jwt(priv, claims=valid_claims(nbf_offset=7200), kid=jwk["kid"])
        nonce_hash = hashlib.sha256(NONCE.encode()).hexdigest()
        result = validator.validate_id_token(
            token, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=nonce_hash,
        )
        assert not result.valid
        assert not result.nbf_valid
        assert "nbf" in result.reason.lower() or "not yet valid" in result.reason.lower()


# ───────────────────────────────────────────────
# 5. nonce mismatch
# ───────────────────────────────────────────────


class TestNonceMismatch:
    def test_nonce_mismatch_rejected(self):
        priv, jwk = generate_rsa_keypair(kid="k5")
        validator = _make_validator(kids_to_keys={jwk["kid"]: jwk})
        token = sign_jwt(priv, claims=valid_claims(nonce="wrong-nonce"), kid=jwk["kid"])
        expected_hash = hashlib.sha256(NONCE.encode()).hexdigest()
        result = validator.validate_id_token(
            token, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=expected_hash,
        )
        assert not result.valid
        assert not result.nonce_valid
        assert "nonce" in result.reason.lower()


# ───────────────────────────────────────────────
# 6. unknown kid
# ───────────────────────────────────────────────


class TestUnknownKid:
    def test_unknown_kid_rejected(self):
        priv, jwk = generate_rsa_keypair(kid="legit-kid")
        # JWKS only has legit-kid, but token signs with bogus-kid
        token = sign_jwt(priv, claims=valid_claims(), kid="bogus-kid")
        validator = _make_validator(kids_to_keys={jwk["kid"]: jwk})
        nonce_hash = hashlib.sha256(NONCE.encode()).hexdigest()
        result = validator.validate_id_token(
            token, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=nonce_hash,
        )
        assert not result.valid
        assert not result.signature_valid


# ───────────────────────────────────────────────
# 7. JWKS rotation (old kid rejected after rotation)
# ───────────────────────────────────────────────


class TestJWKSRotation:
    def test_rotation_old_key_rejected(self):
        priv_old, jwk_old = generate_rsa_keypair(kid="old-kid")
        priv_new, jwk_new = generate_rsa_keypair(kid="new-kid")
        jwks_uri = "https://idp.example.com/.well-known/jwks.json"
        settings = Step21Settings(oidc_jwks_uri=jwks_uri)
        discovery = SandboxV2OIDCDiscoveryService(settings=settings)
        jwks_cache = SandboxV2JWKSCacheService(settings=settings, discovery_service=discovery)
        # First seed with old key
        jwks_cache.seed_static_jwks(
            ISSUER, jwks_uri,
            {jwk_old["kid"]: jwk_old},
        )
        # Simulate rotation: replace with new key only
        jwks_cache.seed_static_jwks(
            ISSUER, jwks_uri,
            {jwk_new["kid"]: jwk_new},
        )
        validator = SandboxV2OIDCIdentityValidationService(
            settings=settings, jwks_cache=jwks_cache, discovery=discovery,
        )
        # Token signed with OLD key (kid=old-kid) — should be rejected now
        token = sign_jwt(priv_old, claims=valid_claims(), kid="old-kid")
        nonce_hash = hashlib.sha256(NONCE.encode()).hexdigest()
        result = validator.validate_id_token(
            token, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=nonce_hash,
        )
        assert not result.valid
        # New key still works
        token_new = sign_jwt(priv_new, claims=valid_claims(), kid="new-kid")
        result_new = validator.validate_id_token(
            token_new, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=nonce_hash,
        )
        assert result_new.valid


# ───────────────────────────────────────────────
# 8. invalid signature
# ───────────────────────────────────────────────


class TestInvalidSignature:
    def test_wrong_signature_rejected(self):
        priv_legit, jwk_legit = generate_rsa_keypair(kid="k-legit")
        priv_attacker, _ = generate_rsa_keypair(kid="k-attacker")
        validator = _make_validator(kids_to_keys={jwk_legit["kid"]: jwk_legit})
        # Sign with attacker's key but use the legit kid
        token = sign_jwt(priv_attacker, claims=valid_claims(), kid="k-legit")
        nonce_hash = hashlib.sha256(NONCE.encode()).hexdigest()
        result = validator.validate_id_token(
            token, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=nonce_hash,
        )
        assert not result.valid
        assert not result.signature_valid
        assert "signature" in result.reason.lower()


# ───────────────────────────────────────────────
# 9. missing claims
# ───────────────────────────────────────────────


class TestMissingClaims:
    def test_missing_sub_rejected(self):
        priv, jwk = generate_rsa_keypair(kid="k-mc")
        validator = _make_validator(kids_to_keys={jwk["kid"]: jwk})
        claims = valid_claims()
        claims.pop("sub")
        token = sign_jwt(priv, claims=claims, kid=jwk["kid"])
        nonce_hash = hashlib.sha256(NONCE.encode()).hexdigest()
        result = validator.validate_id_token(
            token, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=nonce_hash,
        )
        assert not result.valid
        assert not result.sub_valid


# ───────────────────────────────────────────────
# 10. disabled validation mode
# ───────────────────────────────────────────────


class TestDisabledValidationMode:
    def test_disabled_mode_returns_unvalidated(self):
        # oidc_signature_validation_enabled=false → no validation performed
        settings = Step21Settings(oidc_signature_validation_enabled=False)
        validator = _make_validator(settings=settings, kids_to_keys=None)
        result = validator.validate_id_token("any.token.here")
        assert not result.valid
        assert result.validation_mode == SandboxV2OIDCValidationMode.DISABLED
        assert "disabled" in result.reason.lower()
        assert result.fail_closed is False  # disabled, not failed


# ───────────────────────────────────────────────
# Bonus: positive case + no-token-storage invariant
# ───────────────────────────────────────────────


class TestPositiveCase:
    def test_valid_token_accepted(self):
        priv, jwk = generate_rsa_keypair(kid="k-pos")
        validator = _make_validator(kids_to_keys={jwk["kid"]: jwk})
        token = sign_jwt(priv, claims=valid_claims(), kid=jwk["kid"])
        nonce_hash = hashlib.sha256(NONCE.encode()).hexdigest()
        result = validator.validate_id_token(
            token, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            expected_nonce_hash=nonce_hash,
        )
        assert result.valid, f"expected valid, reason={result.reason}"
        assert result.signature_valid
        assert result.iss_valid
        assert result.aud_valid
        assert result.exp_valid
        assert result.nonce_valid
        # Result MUST be a plain dict structure (no token stored)
        out = result.to_dict()
        assert "valid" in out and "claims" in out and "issuer" in out
        # No token in serialized result
        assert "eyJ" not in str(out)
