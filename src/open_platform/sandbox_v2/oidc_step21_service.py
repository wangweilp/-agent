"""Sandbox v2 OIDC Step 21 Coordinator — production-grade identity validation orchestrator.

聚合 Step 21 的各个子服务，对外暴露单一 ``SandboxV2OIDCStep21Service``：

- Discovery + JWKS Cache
- Identity Validation (RS256 + claims)
- Token Exchange (默认关闭)
- Identity Mapping

提供 ``get_oidc_validation_readiness()`` — Runtime Admin 直接消费。
"""
from __future__ import annotations

import logging
from typing import Any

from src.open_platform.sandbox_v2.models import (
    SandboxV2OIDCIdentityMapping,
    SandboxV2OIDCIdentityValidationResult,
    SandboxV2OIDCTokenExchangeResult,
)
from src.open_platform.sandbox_v2.oidc_discovery import (
    HttpFetcherProtocol,
    SandboxV2JWKSCacheService,
    SandboxV2OIDCDiscoveryService,
)
from src.open_platform.sandbox_v2.oidc_identity_validation import (
    SandboxV2OIDCIdentityValidationService,
)
from src.open_platform.sandbox_v2.oidc_token_exchange import (
    SandboxV2OIDCIdentityMappingService,
    SandboxV2OIDCTokenExchangeService,
    TokenEndpointClientProtocol,
)

logger = logging.getLogger(__name__)


def _status_of(*, enabled: bool, ready: bool) -> str:
    """enabled / disabled / ready / not_ready mapping per Step 21 spec."""
    if enabled and ready:
        return "ready"
    if enabled and not ready:
        return "not_ready"
    return "disabled"


class SandboxV2OIDCStep21Service:
    """Step 21 orchestrator. Default deny, all sub-services disabled by default."""

    def __init__(
        self,
        settings: Any = None,
        http_fetcher: HttpFetcherProtocol | None = None,
        token_endpoint_client: TokenEndpointClientProtocol | None = None,
        store: Any = None,
        iam_service: Any = None,
    ) -> None:
        self._settings = settings
        self.discovery = SandboxV2OIDCDiscoveryService(settings=settings, http_fetcher=http_fetcher)
        self.jwks_cache = SandboxV2JWKSCacheService(
            settings=settings, http_fetcher=http_fetcher,
            discovery_service=self.discovery,
        )
        self.identity_validator = SandboxV2OIDCIdentityValidationService(
            settings=settings,
            jwks_cache=self.jwks_cache,
            discovery=self.discovery,
        )
        self.token_exchange = SandboxV2OIDCTokenExchangeService(
            settings=settings,
            identity_validator=self.identity_validator,
            token_endpoint_client=token_endpoint_client,
        )
        self.identity_mapping = SandboxV2OIDCIdentityMappingService(
            settings=settings, store=store, iam_service=iam_service,
        )

    # ── settings helpers ──

    def _cfg(self, key: str, default: Any = None) -> Any:
        if self._settings:
            return getattr(self._settings, key, default)
        return default

    # ── convenience accessors ──

    def validate_id_token(self, id_token: str, **kwargs: Any) -> SandboxV2OIDCIdentityValidationResult:
        return self.identity_validator.validate_id_token(id_token, **kwargs)

    def exchange_code(self, code: str, **kwargs: Any) -> SandboxV2OIDCTokenExchangeResult:
        return self.token_exchange.exchange(code, **kwargs)

    def map_validated_identity(
        self, validation: SandboxV2OIDCIdentityValidationResult, **kwargs: Any,
    ) -> SandboxV2OIDCIdentityMapping:
        return self.identity_mapping.map_validated_identity(validation, **kwargs)

    # ── readiness (consumed by Runtime Admin) ──

    def get_oidc_validation_readiness(self) -> dict[str, Any]:
        """Runtime Admin OIDC Validation Readiness — Step 21.

        Returns per-capability status: enabled / disabled / ready / not_ready.
        """
        sig_enabled = self.identity_validator.signature_validation_enabled
        disc_rdy_dict = self.discovery.readiness()
        jwks_rdy_dict = self.jwks_cache.readiness()
        token_rdy_dict = self.token_exchange.readiness()
        claim_rdy = sig_enabled  # claim validation active iff signature validation on
        mapping_rdy_dict = self.identity_mapping.readiness()

        disc_enabled = bool(disc_rdy_dict.get("discovery_enabled"))
        disc_ready = bool(disc_rdy_dict.get("http_fetcher_configured")) or disc_enabled is False
        jwks_enabled = bool(jwks_rdy_dict.get("jwks_cache_enabled"))
        jwks_ready = bool(jwks_rdy_dict.get("http_fetcher_configured")) or bool(
            self._cfg("oidc_jwks_uri", ""))
        token_enabled = bool(token_rdy_dict.get("token_exchange_enabled"))
        token_ready = (
            bool(token_rdy_dict.get("token_endpoint_configured"))
            and bool(token_rdy_dict.get("token_endpoint_client_configured"))
        )
        mapping_enabled = bool(mapping_rdy_dict.get("identity_mapping_enabled"))

        return {
            "step": "step21_oidc_production_validation",
            "signature_validation": {
                "enabled": sig_enabled,
                "status": _status_of(
                    enabled=sig_enabled,
                    ready=sig_enabled and bool(self.identity_validator.readiness().get("ready")),
                ),
            },
            "oidc_discovery": {
                "enabled": disc_enabled,
                "status": _status_of(enabled=disc_enabled, ready=disc_ready),
            },
            "jwks_cache": {
                "enabled": jwks_enabled,
                "status": _status_of(enabled=jwks_enabled, ready=jwks_ready),
            },
            "token_exchange": {
                "enabled": token_enabled,
                "status": _status_of(enabled=token_enabled, ready=token_ready),
            },
            "claim_validation": {
                "enabled": claim_rdy,
                "status": _status_of(
                    enabled=claim_rdy,
                    ready=claim_rdy and bool(self.identity_validator.readiness().get("ready")),
                ),
            },
            "identity_mapping": {
                "enabled": mapping_enabled,
                "status": _status_of(enabled=mapping_enabled, ready=mapping_enabled),
            },
            # global toggle that bumps legacy readiness flags
            "signature_validation_enabled": sig_enabled,
            "token_storage": False,  # invariant
            "fail_closed": True,
            "secure_by_default": True,
            "components": {
                "discovery": disc_rdy_dict,
                "jwks_cache": jwks_rdy_dict,
                "identity_validator": self.identity_validator.readiness(),
                "token_exchange": token_rdy_dict,
                "identity_mapping": mapping_rdy_dict,
            },
        }


__all__ = ["SandboxV2OIDCStep21Service"]
