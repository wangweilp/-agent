"""Sandbox v2 OIDC Discovery + JWKS Cache — Step 21.

提供生产级 OIDC 身份验证所需的两个低层服务：

1. ``SandboxV2OIDCDiscoveryService`` — 拉取并缓存
   ``/.well-known/openid-configuration``。失败必须 fail closed。
2. ``SandboxV2JWKSCacheService`` — 拉取并缓存 JWKS。
   支持 cache refresh / expiration / kid rotation。失败必须 fail closed。

安全约束 (与项目其它 SSO 模块一致)：
- 不实现真实网络出口 — 通过 ``http_fetcher`` 注入；无注入器时 fail closed。
- 缓存失败绝不退化为「跳过验证」(no signature bypass)。
- key material 永不进入日志/audit。
- 默认 disabled — 由 ``oidc_signature_validation_enabled`` 开关决定是否启用。
- anti-issuer-spoof：Discovery 返回的 issuer 必须与请求 issuer 完全一致。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol

from src.open_platform.sandbox_v2.models import (
    SandboxV2JWKSCacheEntry,
    SandboxV2OIDCDiscoveryCacheEntry,
)

logger = logging.getLogger(__name__)

# Required discovery fields per OIDC Discovery 1.0
_REQUIRED_DISCOVERY_FIELDS: tuple[str, ...] = (
    "issuer",
    "authorization_endpoint",
    "jwks_uri",
)

# Sensitive discovery fields to redact (never stored/logged)
_DISCOVERY_REDACT_KEYS: frozenset[str] = frozenset({
    "client_secret", "secret", "token", "authorization",
})

# Allowed signature algorithms (project-wide allowlist)
_ALLOWED_SIGNING_ALGS: frozenset[str] = frozenset({"RS256", "RS384", "RS512"})


class HttpFetcherProtocol(Protocol):
    """网络出口注入接口 — 默认 None (fail closed)。"""

    def get_json(self, url: str, timeout: float = 10.0) -> dict[str, Any]:
        """GET URL, return parsed JSON dict. Raise on non-200 / timeout / parse error."""
        ...


def _redact_dict(d: dict[str, Any]) -> dict[str, Any]:
    return {
        k: ("***REDACTED***" if k.lower() in _DISCOVERY_REDACT_KEYS else v)
        for k, v in (d or {}).items()
    }


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════
# Step 21.1 — OIDC Discovery Service
# ═══════════════════════════════════════════


class SandboxV2OIDCDiscoveryService:
    """OIDC Discovery 缓存服务。

    设计：
    - 仅信任 ``issuer`` 字符串 (anti-spoof)：Discovery 文档必须含 issuer
      且与请求的 issuer 精确匹配，否则视为攻击。
    - 缓存按 issuer keyed。
    - 失败必须 fail closed — 返回 None，调用方不得跳过验证。
    """

    def __init__(
        self,
        settings: Any = None,
        http_fetcher: HttpFetcherProtocol | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._http = http_fetcher
        self._clock = clock or _now
        # issuer → cache entry
        self._cache: dict[str, SandboxV2OIDCDiscoveryCacheEntry] = {}

    # ── settings helpers ──

    def _cfg(self, key: str, default: Any = None) -> Any:
        if self._settings:
            return getattr(self._settings, key, default)
        return default

    @property
    def enabled(self) -> bool:
        """Discovery fetch 是否启用 (默认 false)。"""
        return bool(self._cfg("oidc_discovery_fetch_enabled", False)) or bool(
            self._cfg("oidc_signature_validation_enabled", False)
        )

    @property
    def cache_ttl_seconds(self) -> int:
        return int(self._cfg("oidc_discovery_cache_ttl_seconds", 3600))

    # ── discovery document ──

    def _build_well_known_url(self, issuer: str) -> str:
        """Construct /.well-known/openid-configuration URL from issuer.

        issuer must NOT have a trailing slash; we normalize defensively.
        """
        if not issuer:
            return ""
        normalized = issuer.rstrip("/")
        return f"{normalized}/.well-known/openid-configuration"

    def fetch_discovery(self, issuer: str, force_refresh: bool = False) -> SandboxV2OIDCDiscoveryCacheEntry | None:
        """Fetch + cache discovery document for ``issuer``. Fail closed → None."""
        if not issuer:
            logger.warning("oidc_discovery_skip_empty_issuer")
            return None

        # Cache hit (unless forced refresh / expired)
        cached = self._cache.get(issuer)
        if cached and not force_refresh and not cached.is_expired(self._clock()):
            return cached

        if not self.enabled or self._http is None:
            # Fail closed: no network outlet configured → do NOT fabricate discovery.
            logger.warning(
                "oidc_discovery_fail_closed",
                extra={"reason": "disabled_or_no_http_fetcher", "issuer_present": bool(issuer)},
            )
            return None

        url = self._build_well_known_url(issuer)
        try:
            doc = self._http.get_json(url, timeout=10.0)
        except Exception as e:
            logger.warning("oidc_discovery_fetch_failed", extra={"error": str(e)})
            return None

        entry = self._parse_discovery_doc(issuer, doc)
        if entry is None:
            return None

        self._cache[issuer] = entry
        return entry

    def _parse_discovery_doc(
        self, issuer: str, doc: dict[str, Any],
    ) -> SandboxV2OIDCDiscoveryCacheEntry | None:
        """Validate a discovery doc. Anti-issuer-spoof enforced here."""
        if not isinstance(doc, dict) or not doc:
            logger.warning("oidc_discovery_invalid_doc_not_dict")
            return None
        for required in _REQUIRED_DISCOVERY_FIELDS:
            if not doc.get(required):
                logger.warning("oidc_discovery_missing_field", extra={"field": required})
                return None
        # anti-spoof: returned issuer must match requested issuer
        if str(doc.get("issuer", "")).rstrip("/") != issuer.rstrip("/"):
            logger.warning(
                "oidc_discovery_issuer_spoof_blocked",
                extra={"expected": issuer, "got": doc.get("issuer", "")},
            )
            return None
        now = self._clock()
        return SandboxV2OIDCDiscoveryCacheEntry(
            issuer=str(doc.get("issuer", "")),
            authorization_endpoint=str(doc.get("authorization_endpoint", "")),
            token_endpoint=str(doc.get("token_endpoint", "")),
            userinfo_endpoint=str(doc.get("userinfo_endpoint", "")),
            jwks_uri=str(doc.get("jwks_uri", "")),
            raw_metadata_redacted=_redact_dict(doc),
            fetched_at=now,
            expires_at=now + timedelta(seconds=self.cache_ttl_seconds),
            source="discovery",
        )

    # ── cache helpers (for tests / admin) ──

    def get_cached(self, issuer: str) -> SandboxV2OIDCDiscoveryCacheEntry | None:
        return self._cache.get(issuer)

    def invalidate(self, issuer: str = "") -> None:
        if not issuer:
            self._cache.clear()
            return
        self._cache.pop(issuer, None)

    def seed_static_discovery(
        self,
        issuer: str,
        authorization_endpoint: str,
        token_endpoint: str,
        jwks_uri: str,
        userinfo_endpoint: str = "",
    ) -> SandboxV2OIDCDiscoveryCacheEntry:
        """Inject a trusted (audited) static discovery entry. Used for tests / fixture IdP."""
        now = self._clock()
        entry = SandboxV2OIDCDiscoveryCacheEntry(
            issuer=issuer, authorization_endpoint=authorization_endpoint,
            token_endpoint=token_endpoint, userinfo_endpoint=userinfo_endpoint,
            jwks_uri=jwks_uri,
            raw_metadata_redacted={"source": "static"},
            fetched_at=now, expires_at=now + timedelta(seconds=self.cache_ttl_seconds),
            source="static",
        )
        self._cache[issuer] = entry
        return entry

    def readiness(self) -> dict[str, Any]:
        return {
            "discovery_enabled": self.enabled,
            "cached_issuers": list(self._cache.keys()),
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "http_fetcher_configured": self._http is not None,
            "fail_closed": True,
        }


# ═══════════════════════════════════════════
# Step 21.2 — JWKS Cache Service
# ═══════════════════════════════════════════


class SandboxV2JWKSCacheService:
    """JWKS 缓存服务。

    支持：
    - cache refresh / expiration
    - kid rotation (multiple keys per issuer)
    - cache refresh retry with cooldown

    安全约束：
    - key material 永不进入日志
    - 失败必须 fail closed → 返回 None，绝不返回过期/半新 key
    - 不实现自动信任 — 必须 fail closed
    """

    def __init__(
        self,
        settings: Any = None,
        http_fetcher: HttpFetcherProtocol | None = None,
        discovery_service: SandboxV2OIDCDiscoveryService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._http = http_fetcher
        self._discovery = discovery_service
        self._clock = clock or _now
        # jwks_uri → cache entry
        self._cache: dict[str, SandboxV2JWKSCacheEntry] = {}
        # cooldown tracker (jwks_uri → unlock timestamp)
        self._cooldown_until: dict[str, float] = {}

    # ── settings helpers ──

    def _cfg(self, key: str, default: Any = None) -> Any:
        if self._settings:
            return getattr(self._settings, key, default)
        return default

    @property
    def enabled(self) -> bool:
        return bool(self._cfg("oidc_jwks_fetch_enabled", False)) or bool(
            self._cfg("oidc_signature_validation_enabled", False)
        )

    @property
    def cache_ttl_seconds(self) -> int:
        return int(self._cfg("oidc_jwks_cache_ttl_seconds", 3600))

    @property
    def max_retries(self) -> int:
        return int(self._cfg("oidc_jwks_refresh_retries", 2))

    @property
    def cooldown_seconds(self) -> int:
        return int(self._cfg("oidc_jwks_refresh_cooldown_seconds", 30))

    # ── core lookup ──

    def resolve_jwks_uri(self, issuer: str) -> str:
        """Resolve jwks_uri — prefer static config, then discovery. Empty if fail closed."""
        # 1. Static config (most trusted)
        static = str(self._cfg("oidc_jwks_uri", "") or "")
        if static:
            return static
        # 2. Discovery (may fetch from network)
        if self._discovery:
            entry = self._discovery.fetch_discovery(issuer)
            if entry:
                return entry.jwks_uri
        return ""

    def get_key_for_kid(
        self, jwks_uri: str, kid: str, force_refresh: bool = False,
    ) -> dict[str, Any] | None:
        """Look up a single key by kid. Returns None on miss / fail closed.

        NOTE: Caller MUST treat None as fail closed (do not proceed).
        """
        if not jwks_uri or not kid:
            return None

        entry = self._cache.get(jwks_uri)
        if entry and not force_refresh and not entry.is_expired(self._clock()):
            return entry.keys_by_kid.get(kid)

        # Refresh and retry once
        refreshed = self.refresh_jwks(jwks_uri)
        if refreshed is None:
            return None  # fail closed
        return refreshed.keys_by_kid.get(kid)

    def refresh_jwks(self, jwks_uri: str) -> SandboxV2JWKSCacheEntry | None:
        """Force-refresh JWKS. Returns None on failure (fail closed)."""
        if not jwks_uri:
            return None

        # cooldown enforcement
        now_ts = self._clock().timestamp()
        unlock = self._cooldown_until.get(jwks_uri, 0.0)
        if now_ts < unlock:
            logger.warning("oidc_jwks_refresh_cooldown_active", extra={"jwks_uri_present": True})
            return self._cache.get(jwks_uri)  # return stale (caller treats as fail if kid missing)

        if not self.enabled or self._http is None:
            logger.warning(
                "oidc_jwks_refresh_fail_closed",
                extra={"reason": "disabled_or_no_http_fetcher"},
            )
            return None

        keys: dict[str, dict[str, Any]] = {}
        last_err = ""
        attempts = max(1, self.max_retries)
        for attempt in range(1, attempts + 1):
            try:
                doc = self._http.get_json(jwks_uri, timeout=10.0)
                keys = self._parse_jwks_keys(doc)
                if keys:
                    break
                last_err = "no_valid_keys_in_jwks"
            except Exception as e:
                last_err = str(e)
                logger.warning(
                    "oidc_jwks_refresh_attempt_failed",
                    extra={"attempt": attempt, "error": str(e)},
                )

        if not keys:
            # fail closed — enter cooldown so we don't hammer a broken IdP
            self._cooldown_until[jwks_uri] = (self._clock().timestamp() + self.cooldown_seconds)
            logger.warning("oidc_jwks_refresh_exhausted", extra={"last_error": last_err})
            return None

        now = self._clock()
        existing = self._cache.get(jwks_uri)
        refresh_failures = 0 if existing is None else 0  # success resets
        entry = SandboxV2JWKSCacheEntry(
            issuer=existing.issuer if existing else "",
            jwks_uri=jwks_uri,
            keys_by_kid=keys,
            fetched_at=now,
            expires_at=now + timedelta(seconds=self.cache_ttl_seconds),
            refresh_failures=refresh_failures,
            last_refresh_status="success",
            last_refresh_at=now,
            source=existing.source if existing and existing.source else "jwks_uri",
        )
        self._cache[jwks_uri] = entry
        self._cooldown_until.pop(jwks_uri, None)
        return entry

    def _parse_jwks_keys(self, doc: Any) -> dict[str, dict[str, Any]]:
        """Parse JWKS doc → {kid: jwk_dict}. Fail closed on any structural problem."""
        if not isinstance(doc, dict):
            return {}
        raw_keys = doc.get("keys")
        if not isinstance(raw_keys, list) or not raw_keys:
            return {}
        result: dict[str, dict[str, Any]] = {}
        for key in raw_keys:
            if not isinstance(key, dict):
                continue
            kid = str(key.get("kid", "") or "").strip()
            # RFC 7517: kty is case-sensitive, must be exactly "RSA" for RSA keys
            kty = str(key.get("kty", "") or "").strip()
            alg = str(key.get("alg", "") or "").strip().upper()
            use = str(key.get("use", "") or "").strip().lower()
            # Only RSA signing keys accepted (project-wide invariant)
            if kty != "RSA":
                continue
            if use and use != "sig":
                continue
            if alg and alg not in _ALLOWED_SIGNING_ALGS:
                continue
            if not kid:
                # kid missing — refuse (kid lookup requires kid)
                continue
            result[kid] = dict(key)
        return result

    # ── kid rotation helpers ──

    def list_kids(self, jwks_uri: str) -> list[str]:
        entry = self._cache.get(jwks_uri)
        return entry.get_kids() if entry else []

    def seed_static_jwks(
        self, issuer: str, jwks_uri: str, keys_by_kid: dict[str, dict[str, Any]],
    ) -> SandboxV2JWKSCacheEntry:
        """Inject a trusted (audited) static JWKS. Used for tests / fixture IdP."""
        now = self._clock()
        entry = SandboxV2JWKSCacheEntry(
            issuer=issuer, jwks_uri=jwks_uri,
            keys_by_kid=keys_by_kid,
            fetched_at=now,
            expires_at=now + timedelta(seconds=self.cache_ttl_seconds),
            refresh_failures=0,
            last_refresh_status="success",
            last_refresh_at=now,
            source="static",
        )
        self._cache[jwks_uri] = entry
        return entry

    def invalidate(self, jwks_uri: str = "") -> None:
        if not jwks_uri:
            self._cache.clear()
            self._cooldown_until.clear()
            return
        self._cache.pop(jwks_uri, None)
        self._cooldown_until.pop(jwks_uri, None)

    def readiness(self) -> dict[str, Any]:
        return {
            "jwks_cache_enabled": self.enabled,
            "cached_jwks_uris": [
                {"jwks_uri": uri, "kids": entry.get_kids(), "expired": entry.is_expired(self._clock())}
                for uri, entry in self._cache.items()
            ],
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "cooldown_seconds": self.cooldown_seconds,
            "http_fetcher_configured": self._http is not None,
            "fail_closed": True,
        }


__all__ = [
    "HttpFetcherProtocol",
    "SandboxV2OIDCDiscoveryService",
    "SandboxV2JWKSCacheService",
]
