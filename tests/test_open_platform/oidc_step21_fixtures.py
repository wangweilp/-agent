"""Step 21 OIDC test fixtures — RSA keypair + signed JWT + JWKS generator.

Reusable helpers for both Security Tests (10) and Red-Team Tests (5).
"""
from __future__ import annotations

import base64
import time
from typing import Any


def _b64url_uint(value: int) -> str:
    """Encode an integer to base64url-without-padding (JWK 'n'/'e' format)."""
    if value == 0:
        b = b"\x00"
    else:
        length = (value.bit_length() + 7) // 8
        b = value.to_bytes(length, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def generate_rsa_keypair(kid: str = "test-kid-1"):
    """Generate an RSA keypair + JWK public key. Returns (private_pem, jwk_public_dict)."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")

    public_numbers = private_key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": _b64url_uint(public_numbers.n),
        "e": _b64url_uint(public_numbers.e),
    }
    return private_pem, jwk


def sign_jwt(
    private_pem: str,
    *,
    claims: dict[str, Any],
    kid: str = "test-kid-1",
    alg: str = "RS256",
    header_extra: dict[str, Any] | None = None,
) -> str:
    """Sign a JWT with the given key. Allows header overrides for attack simulation.

    Security note: For 'none' attack simulation, the caller should use
    ``sign_unsigned_jwt`` instead, since jose refuses to sign with alg=none.
    """
    from jose import jwt as _jwt

    headers = {"kid": kid, "alg": alg}
    if header_extra:
        headers.update(header_extra)
    return _jwt.encode(claims, private_pem, algorithm=alg, headers=headers)


def sign_unsigned_jwt(claims: dict[str, Any], kid: str = "test-kid-1") -> str:
    """Construct an unsigned JWT with alg=none (for Red-Team simulation only).

    jose refuses to produce these — we craft manually so the validator can be tested.
    """
    header = {"alg": "none", "typ": "JWT", "kid": kid}
    header_b64 = base64.urlsafe_b64encode(
        __import__("json").dumps(header, separators=(",", ":")).encode(),
    ).rstrip(b"=").decode("ascii")
    payload_b64 = base64.urlsafe_b64encode(
        __import__("json").dumps(claims, separators=(",", ":")).encode(),
    ).rstrip(b"=").decode("ascii")
    # alg=none JWTs have an empty signature segment
    return f"{header_b64}.{payload_b64}."


def sign_jwt_wrong_signature(
    private_pem_attacker: str,
    *,
    claims: dict[str, Any],
    kid: str = "test-kid-1",
) -> str:
    """Sign with a different key but use the legit kid — for invalid-signature tests."""
    return sign_jwt(private_pem_attacker, claims=claims, kid=kid, alg="RS256")


def build_jwks(jwks_keys: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap a list of JWKs in a JWKS document."""
    return {"keys": jwks_keys}


def valid_claims(
    *,
    issuer: str = "https://idp.example.com",
    subject: str = "user-123",
    audience: str = "test-client-id",
    nonce: str = "test-nonce-value",
    exp_offset: int = 600,
    nbf_offset: int = -60,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a baseline valid claim set (positive case)."""
    now = int(time.time())
    c = {
        "iss": issuer,
        "sub": subject,
        "aud": audience,
        "nonce": nonce,
        "iat": now - 60,
        "nbf": now + nbf_offset,
        "exp": now + exp_offset,
        "email": "user@example.com",
        "email_verified": True,
    }
    if extra:
        c.update(extra)
    return c


class Step21Settings:
    """Minimal in-memory settings stub used by Step 21 tests."""

    def __init__(self, **overrides: Any) -> None:
        base = dict(
            oidc_signature_validation_enabled=True,
            oidc_allowed_algs=["RS256"],
            oidc_jwks_uri="",
            oidc_jwks_fetch_enabled=False,
            oidc_discovery_fetch_enabled=False,
            oidc_jwks_cache_ttl_seconds=3600,
            oidc_jwks_refresh_retries=2,
            oidc_jwks_refresh_cooldown_seconds=30,
            oidc_discovery_cache_ttl_seconds=3600,
            oidc_require_kid=True,
            oidc_clock_skew_seconds=60,
            oidc_token_exchange_enabled=False,
            oidc_token_endpoint="",
            oidc_client_id="test-client-id",
            sso_session_enabled=False,
            sso_session_ttl_seconds=3600,
            iam_default_role="viewer",
            iam_allowed_domains=["example.com"],
            iam_require_verified_email=True,
        )
        base.update(overrides)
        for k, v in base.items():
            setattr(self, k, v)


__all__ = [
    "generate_rsa_keypair",
    "sign_jwt",
    "sign_unsigned_jwt",
    "sign_jwt_wrong_signature",
    "build_jwks",
    "valid_claims",
    "Step21Settings",
]
