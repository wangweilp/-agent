"""Sandbox v2 OIDC Identity Validation — Step 21.

生产级 OIDC ID Token 验证。这是 Real SSO Skeleton → Production-Grade SSO
的核心升级。

主要服务 ``SandboxV2OIDCIdentityValidationService``：

1. JWKS Discovery + kid lookup
2. RS256 签名验证 (via python-jose)
3. iss / aud / exp / nbf / iat / sub / nonce 校验
4. alg whitelist (默认仅 RS256；alg=none 必拒)
5. fail closed — 任何缺失/异常都拒绝，不退化为跳过校验

安全约束 (与项目其它 SSO 模块一致)：
- 默认 disabled (``oidc_signature_validation_enabled=false``)
- 不存 token / access_token / refresh_token
- 不暴露 key material 到日志
- ``alg=none`` / 未签名 token 必拒
- wrong issuer / wrong audience 必拒
- replay nonce 必拒
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json as _json
import logging
import time
from typing import Any

from src.open_platform.sandbox_v2.models import (
    SandboxV2JWKSCacheEntry,
    SandboxV2OIDCIdentityValidationResult,
    SandboxV2OIDCValidationMode,
)
from src.open_platform.sandbox_v2.oidc_discovery import (
    SandboxV2JWKSCacheService,
    SandboxV2OIDCDiscoveryService,
)

logger = logging.getLogger(__name__)

# Default clock skew tolerance (seconds)
_DEFAULT_CLOCK_SKEW = 60

# alg=none must always be rejected
_NONE_ALG_TOKENS: frozenset[str] = frozenset({"none", ""})

# Sensitive claim keys to redact in result
_REDACT_KEYS: frozenset[str] = frozenset({
    "access_token", "id_token", "refresh_token", "token", "secret",
    "client_secret", "code", "jwt", "authorization", "at_hash", "c_hash",
})


def _redact_claims(claims: dict[str, Any]) -> dict[str, Any]:
    return {
        k: ("***REDACTED***" if k.lower() in _REDACT_KEYS else v)
        for k, v in (claims or {}).items()
    }


def _b64url_decode(segment: str) -> bytes:
    """Base64url decode with padding recovery."""
    if isinstance(segment, str):
        segment = segment.encode("ascii")
    rem = len(segment) % 4
    if rem > 0:
        segment += b"=" * (4 - rem)
    return base64.urlsafe_b64decode(segment)


def _decode_jwt_unverified(id_token: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Decode JWT header/payload WITHOUT verifying signature (for kid pre-flight only).

    Returns (header, payload, raw_signing_input). Raises ValueError on malformed JWT.
    """
    if not id_token or not isinstance(id_token, str):
        raise ValueError("empty id_token")
    parts = id_token.split(".")
    if len(parts) != 3:
        raise ValueError(f"invalid JWT segment count: {len(parts)}")
    header_b64, payload_b64, signature_b64 = parts
    if not signature_b64:
        raise ValueError("missing signature segment (alg=none)")
    try:
        header = _json.loads(_b64url_decode(header_b64))
        payload = _json.loads(_b64url_decode(payload_b64))
    except Exception as e:
        raise ValueError(f"invalid JWT encoding: {e}") from e
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise ValueError("invalid JWT structure")
    signing_input = f"{header_b64}.{payload_b64}"
    return header, payload, signing_input


def _safe_parse_header(id_token: str) -> dict[str, Any] | None:
    """Parse ONLY the JWT header (best-effort, never raises). Used to detect alg=none.

    Returns None on any parse error (caller treats as 'not an alg=none token' and
    falls through to the strict structural check).
    """
    if not id_token or not isinstance(id_token, str):
        return None
    parts = id_token.split(".")
    if len(parts) < 2:
        return None
    try:
        header = _json.loads(_b64url_decode(parts[0]))
        return header if isinstance(header, dict) else None
    except Exception:
        return None


class SandboxV2OIDCIdentityValidationService:
    """生产级 OIDC ID Token 校验服务。

    依赖注入 (便于测试 / 离线 fixture)：
    - ``settings`` — Sandbox v2 配置 (决定是否启用 / 允许的 alg / clock skew)
    - ``jwks_cache`` — JWKS 缓存服务
    - ``discovery`` — Discovery 缓存服务
    - ``jose_backend`` — 可注入的 RS256 验签后端 (默认 lazy import python-jose)
    """

    def __init__(
        self,
        settings: Any = None,
        jwks_cache: SandboxV2JWKSCacheService | None = None,
        discovery: SandboxV2OIDCDiscoveryService | None = None,
        jose_backend: Any = None,
        clock_ts: Any = None,
    ) -> None:
        self._settings = settings
        self._discovery = discovery
        self._jwks_cache = jwks_cache
        self._jose = jose_backend
        self._clock_ts = clock_ts or time.time

    # ── settings helpers ──

    def _cfg(self, key: str, default: Any = None) -> Any:
        if self._settings:
            return getattr(self._settings, key, default)
        return default

    @property
    def signature_validation_enabled(self) -> bool:
        """是否启用 RS256 签名校验 — 默认 false。"""
        return bool(self._cfg("oidc_signature_validation_enabled", False))

    @property
    def allowed_algs(self) -> list[str]:
        algs = self._cfg("oidc_allowed_algs", ["RS256"])
        if not algs:
            return ["RS256"]
        return [str(a).strip().upper() for a in algs if str(a).strip()]

    @property
    def require_kid(self) -> bool:
        return bool(self._cfg("oidc_require_kid", True))

    @property
    def clock_skew(self) -> int:
        return int(self._cfg("oidc_clock_skew_seconds", _DEFAULT_CLOCK_SKEW))

    # ── main API ──

    def validate_id_token(
        self,
        id_token: str,
        *,
        expected_issuer: str = "",
        expected_audience: str = "",
        expected_nonce_hash: str = "",
        expected_nonce: str = "",
    ) -> SandboxV2OIDCIdentityValidationResult:
        """完整校验 id_token。失败 fail closed (valid=False)。"""
        # Mode gate
        if not self.signature_validation_enabled:
            return SandboxV2OIDCIdentityValidationResult(
                valid=False,
                validation_mode=SandboxV2OIDCValidationMode.DISABLED,
                reason="OIDC signature validation disabled (OIDC_SIGNATURE_VALIDATION_ENABLED=false)",
                fail_closed=False,  # disabled ≠ fail-closed; it's just off
            )

        result = SandboxV2OIDCIdentityValidationResult(
            validation_mode=SandboxV2OIDCValidationMode.ENABLED,
            fail_closed=True,
        )

        # 1. Structural + alg=none reject (pre-flight, no signature)
        # Pre-parse the header WITHOUT raising so we can detect alg=none tokens
        # (which often have an empty signature segment) and mark alg_allowed=False.
        pre_header = _safe_parse_header(id_token)
        if pre_header is not None:
            pre_alg = str(pre_header.get("alg", "") or "").strip()
            if pre_alg.lower() == "none" or (not pre_alg):
                result.alg_allowed = False
                result.reason = "alg=none rejected (unsigned token)"
                return result

        try:
            header, payload, signing_input = _decode_jwt_unverified(id_token)
        except ValueError as e:
            result.reason = f"malformed_jwt: {e}"
            result.validation_mode = SandboxV2OIDCValidationMode.FAIL_CLOSED
            return result

        alg = str(header.get("alg", "") or "").strip()
        kid = str(header.get("kid", "") or "").strip()

        # alg whitelist (defence in depth — also caught above)
        if alg.lower() in {a.lower() for a in _NONE_ALG_TOKENS} or not alg:
            result.alg_allowed = False
            result.reason = "alg=none rejected (unsigned token)"
            return result
        if alg not in self.allowed_algs:
            result.alg_allowed = False
            result.reason = f"alg={alg} not in allowed_algs {self.allowed_algs}"
            return result
        result.alg_allowed = True

        # kid required (prevents key confusion / alg confusion attacks)
        if self.require_kid and not kid:
            result.reason = "missing kid header — required to prevent key confusion"
            return result
        result.kid = kid

        # 2. RS256 signature verification
        try:
            sig_ok = self._verify_rs256_signature(id_token, header, kid, expected_issuer)
        except Exception as e:
            logger.warning("oidc_signature_verify_error", extra={"error": str(e)})
            result.reason = f"signature_verify_error: {e}"
            result.validation_mode = SandboxV2OIDCValidationMode.FAIL_CLOSED
            return result

        if not sig_ok:
            result.reason = "invalid signature"
            return result
        result.signature_valid = True

        # 3. Claim validation
        self._validate_claims(
            result, payload,
            expected_issuer=expected_issuer,
            expected_audience=expected_audience,
            expected_nonce_hash=expected_nonce_hash,
            expected_nonce=expected_nonce,
        )

        # 4. Finalize
        result.claims_redacted = _redact_claims(payload)
        result.issuer = str(payload.get("iss", "") or "")
        result.subject = str(payload.get("sub", "") or "")
        aud = payload.get("aud", "")
        result.audience = aud if isinstance(aud, str) else (aud[0] if isinstance(aud, list) and aud else "")

        result.valid = (
            result.signature_valid
            and result.sub_valid
            and result.iss_valid
            and result.aud_valid
            and result.exp_valid
            and result.iat_valid
            and result.nbf_valid
            and result.nonce_valid
        )
        if not result.valid and not result.reason:
            result.reason = "claim validation failed"
        elif result.valid:
            result.reason = "id_token valid (signature + claims verified)"

        return result

    # ── signature verification ──

    def _verify_rs256_signature(
        self,
        id_token: str,
        header: dict[str, Any],
        kid: str,
        expected_issuer: str,
    ) -> bool:
        """Verify RS256 signature via python-jose. Fail closed → returns False."""
        if self._jwks_cache is None:
            logger.warning("oidc_sig_verify_no_jwks_cache")
            return False

        jwks_uri = self._jwks_cache.resolve_jwks_uri(expected_issuer)
        if not jwks_uri:
            logger.warning("oidc_sig_verify_no_jwks_uri", extra={"issuer_present": bool(expected_issuer)})
            return False

        jwk = self._jwks_cache.get_key_for_kid(jwks_uri, kid)
        if jwk is None:
            logger.warning("oidc_sig_verify_unknown_kid", extra={"kid_present": bool(kid)})
            return False

        # lazy import python-jose
        try:
            if self._jose is None:
                from jose import jwt as _jwt  # type: ignore
                self._jose = _jwt
            jose_jwt = self._jose
        except ImportError:
            logger.warning("oidc_sig_verify_no_jose_backend")
            return False

        # Build RSA public key from JWK (RS256 only — kty=rsa enforced upstream)
        try:
            from jose import jwk as _jwk  # type: ignore
            public_key = _jwk.construct(jwk, algorithm="RS256")
        except Exception as e:
            logger.warning("oidc_jwk_construct_failed", extra={"error": str(e)})
            return False

        # Verify with allowed alg whitelist (jose enforces alg match against key)
        try:
            jose_jwt.decode(
                id_token,
                public_key,
                algorithms=self.allowed_algs,
                # claims verified manually below for full control
                options={"verify_aud": False, "verify_iss": False, "verify_exp": False,
                         "verify_nbf": False, "verify_iat": False, "verify_sub": False},
            )
            return True
        except Exception as e:
            logger.warning("oidc_signature_invalid", extra={"error": str(e)})
            return False

    # ── claim validation ──

    def _validate_claims(
        self,
        result: SandboxV2OIDCIdentityValidationResult,
        payload: dict[str, Any],
        *,
        expected_issuer: str,
        expected_audience: str,
        expected_nonce_hash: str,
        expected_nonce: str,
    ) -> None:
        now_ts = int(self._clock_ts())
        skew = self.clock_skew

        # sub
        sub = str(payload.get("sub", "") or "").strip()
        result.sub_valid = bool(sub)
        if not result.sub_valid:
            result.reason = "missing subject (sub)"

        # iss
        iss = str(payload.get("iss", "") or "").strip()
        if expected_issuer:
            result.iss_valid = iss == expected_issuer.rstrip("/")
            if not result.iss_valid:
                result.reason = f"issuer mismatch: {iss!r} != {expected_issuer!r}"
        else:
            result.iss_valid = bool(iss)
            if not result.iss_valid:
                result.reason = "missing issuer (iss)"

        # aud (string or list)
        aud = payload.get("aud", "")
        if expected_audience:
            if isinstance(aud, list):
                result.aud_valid = expected_audience in aud
            else:
                result.aud_valid = (str(aud).strip() == expected_audience)
            if not result.aud_valid:
                result.reason = f"audience mismatch: {aud!r} != {expected_audience!r}"
        else:
            result.aud_valid = bool(aud)
            if not result.aud_valid:
                result.reason = "missing audience (aud)"

        # exp
        exp = int(payload.get("exp", 0) or 0)
        if not exp:
            result.exp_valid = False
            result.reason = "missing exp"
        elif exp < (now_ts - skew):
            result.exp_valid = False
            result.reason = f"token expired at {exp} (now: {now_ts})"
        else:
            result.exp_valid = True

        # nbf (if present)
        nbf = int(payload.get("nbf", 0) or 0)
        if nbf:
            if nbf > (now_ts + skew):
                result.nbf_valid = False
                result.reason = f"token not yet valid (nbf={nbf}, now={now_ts})"
            else:
                result.nbf_valid = True
        else:
            # nbf optional — treat as valid if absent
            result.nbf_valid = True

        # iat
        iat = int(payload.get("iat", 0) or 0)
        if iat and iat > (now_ts + skew):
            result.iat_valid = False
            result.reason = f"iat in future: {iat} (now: {now_ts})"
        elif not iat:
            # iat optional but recommended
            result.iat_valid = True
        else:
            result.iat_valid = True

        # nonce (replay protection)
        # Either expected_nonce (plaintext, hash internally) or pre-hashed
        claim_nonce = str(payload.get("nonce", "") or "").strip()
        if expected_nonce_hash:
            computed = hashlib.sha256(claim_nonce.encode()).hexdigest()
            result.nonce_valid = hmac_safe_compare(computed, expected_nonce_hash)
            if not result.nonce_valid:
                result.reason = "nonce mismatch (replay blocked)"
        elif expected_nonce:
            result.nonce_valid = hmac_safe_compare(claim_nonce, expected_nonce)
            if not result.nonce_valid:
                result.reason = "nonce mismatch (replay blocked)"
        else:
            # No nonce expectation configured — treat as valid (out-of-band trust)
            result.nonce_valid = True

        result.kid_resolved = bool(result.kid)

    # ── readiness ──

    def readiness(self) -> dict[str, Any]:
        enabled = self.signature_validation_enabled
        discovery_ready = bool(self._discovery and self._discovery.enabled)
        jose_ready = self._jose is not None or _jose_available()
        # A resolvable key source is REQUIRED before signature validation is "ready".
        # Sources: static oidc_jwks_uri, OR jwks fetch, OR discovery fetch.
        static_jwks_uri = bool(self._cfg("oidc_jwks_uri", ""))
        jwks_fetch = bool(self._cfg("oidc_jwks_fetch_enabled", False))
        discovery_fetch = bool(self._cfg("oidc_discovery_fetch_enabled", False))
        key_source_available = static_jwks_uri or jwks_fetch or discovery_fetch
        jwks_ready = key_source_available and bool(self._jwks_cache)
        ready = enabled and jose_ready and key_source_available and jwks_ready
        return {
            "signature_validation_enabled": enabled,
            "discovery_ready": discovery_ready,
            "jwks_cache_ready": jwks_ready,
            "key_source_available": key_source_available,
            "claim_validation": True,  # always-on logic when signature enabled
            "identity_mapping": True,
            "allowed_algs": self.allowed_algs,
            "require_kid": self.require_kid,
            "jose_backend_available": jose_ready,
            "clock_skew_seconds": self.clock_skew,
            "ready": ready,
            "fail_closed": True,
        }


# ── helpers ──


def _jose_available() -> bool:
    try:
        import jose  # noqa: F401
        return True
    except ImportError:
        return False


def hmac_safe_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks on nonce check."""
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    try:
        return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
    except Exception:
        return a == b


# lazy import hmac at module level (used in helper above)


__all__ = [
    "SandboxV2OIDCIdentityValidationService",
    "hmac_safe_compare",
]
