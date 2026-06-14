"""Sandbox v2 OIDC Token Exchange + Identity Mapping — Step 21.

将 Authorization Code → Token Endpoint → ID Token → 验证 → 本地映射 闭环。

两个核心服务：

1. ``SandboxV2OIDCTokenExchangeService``
   - Authorization Code → token_endpoint POST → id_token
   - 默认 disabled (``oidc_token_exchange_enabled=false``)
   - access_token / refresh_token 一律不存 (transient only, immediate redact)
   - id_token 仅保留 audit 摘要

2. ``SandboxV2OIDCIdentityMappingService``
   - validated claims → local user → roles → scopes → SSO session
   - 复用 Step 17 的 IAM Claim Mapper (保证 default deny / fail closed 不变)
   - token_storage=false 永远

安全约束 (与项目其它 SSO 模块一致)：
- 默认 disabled
- 不存任何 token
- 高权限角色不允许通过 default_role 自动赋予
- 不实现真实网络出口 — 通过 ``token_endpoint_client`` 注入；无注入器时 fail closed
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from src.open_platform.sandbox_v2.models import (
    SandboxV2OIDCIdentityMapping,
    SandboxV2OIDCIdentityValidationResult,
    SandboxV2OIDCTokenExchangeResult,
    SandboxV2OIDCValidationMode,
    SandboxV2PrincipalType,
    SandboxV2SSOSession,
    SandboxV2SSOSessionStatus,
)

logger = logging.getLogger(__name__)


class TokenEndpointClientProtocol(Protocol):
    """OIDC Token Endpoint 出口注入接口 — 默认 None (fail closed)。"""

    def exchange_code(
        self,
        token_endpoint: str,
        code: str,
        redirect_uri: str,
        client_id: str,
        client_secret: str = "",
        code_verifier: str = "",
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """POST /token → return parsed JSON token response. Raise on error."""
        ...


class SandboxV2OIDCTokenExchangeService:
    """OIDC Token Exchange 服务。

    Authorization Code → Token Endpoint → ID Token → Identity Validation。
    默认 disabled。access_token / refresh_token 一律不持久化。
    """

    def __init__(
        self,
        settings: Any = None,
        identity_validator: Any = None,
        token_endpoint_client: TokenEndpointClientProtocol | None = None,
    ) -> None:
        self._settings = settings
        self._validator = identity_validator
        self._token_client = token_endpoint_client

    # ── settings helpers ──

    def _cfg(self, key: str, default: Any = None) -> Any:
        if self._settings:
            return getattr(self._settings, key, default)
        return default

    @property
    def enabled(self) -> bool:
        return bool(self._cfg("oidc_token_exchange_enabled", False))

    # ── main API ──

    def exchange(
        self,
        code: str,
        *,
        issuer: str = "",
        client_id: str = "",
        client_secret: str = "",
        redirect_uri: str = "",
        code_verifier: str = "",
        expected_nonce_hash: str = "",
        expected_nonce: str = "",
    ) -> SandboxV2OIDCTokenExchangeResult:
        """Exchange authorization code for id_token, then validate.

        默认关闭；只有显式设置 oidc_token_exchange_enabled=true 才执行。
        access_token / refresh_token 一律丢弃，不存任何 store。
        """
        if not self.enabled:
            return SandboxV2OIDCTokenExchangeResult(
                allowed=False,
                reason="Token exchange disabled (OIDC_TOKEN_EXCHANGE_ENABLED=false)",
                fail_closed=False,
            )

        if not code:
            return SandboxV2OIDCTokenExchangeResult(
                allowed=False, reason="missing authorization code", fail_closed=True,
            )

        token_endpoint = str(self._cfg("oidc_token_endpoint", "") or "")
        if not token_endpoint:
            return SandboxV2OIDCTokenExchangeResult(
                allowed=False, reason="oidc_token_endpoint not configured", fail_closed=True,
            )

        if self._token_client is None:
            # fail closed — no real network outlet
            logger.warning("oidc_token_exchange_fail_closed_no_client")
            return SandboxV2OIDCTokenExchangeResult(
                allowed=False, reason="token endpoint client not configured", fail_closed=True,
            )

        # 1. POST to token endpoint — discard access/refresh tokens immediately
        try:
            token_resp = self._token_client.exchange_code(
                token_endpoint=token_endpoint, code=code,
                redirect_uri=redirect_uri or str(self._cfg("oidc_redirect_uri", "") or ""),
                client_id=client_id or str(self._cfg("oidc_client_id", "") or ""),
                client_secret=client_secret,
                code_verifier=code_verifier,
            )
        except Exception as e:
            logger.warning("oidc_token_exchange_http_failed", extra={"error": str(e)})
            return SandboxV2OIDCTokenExchangeResult(
                allowed=False, reason=f"token endpoint error: {e}", fail_closed=True,
            )

        if not isinstance(token_resp, dict):
            return SandboxV2OIDCTokenExchangeResult(
                allowed=False, reason="invalid token response", fail_closed=True,
            )

        id_token = str(token_resp.get("id_token", "") or "")
        # NOTE: access_token / refresh_token intentionally NOT extracted/stored

        if not id_token:
            return SandboxV2OIDCTokenExchangeResult(
                allowed=False, reason="no id_token in token response", fail_closed=True,
            )

        # 2. Validate id_token (signature + claims) via injected validator
        if self._validator is None:
            logger.warning("oidc_token_exchange_no_validator")
            return SandboxV2OIDCTokenExchangeResult(
                allowed=False, reason="identity validator not configured", fail_closed=True,
            )

        validation: SandboxV2OIDCIdentityValidationResult = self._validator.validate_id_token(
            id_token,
            expected_issuer=issuer,
            expected_audience=client_id or str(self._cfg("oidc_client_id", "") or ""),
            expected_nonce_hash=expected_nonce_hash,
            expected_nonce=expected_nonce,
        )

        result = SandboxV2OIDCTokenExchangeResult(
            allowed=validation.valid,
            reason=validation.reason,
            id_token_received=True,
            id_token_validation=validation.to_dict(),
            claims_redacted=validation.claims_redacted,
            fail_closed=validation.fail_closed,
        )
        # id_token never persisted; only audit summary retained in id_token_validation
        return result

    def readiness(self) -> dict[str, Any]:
        return {
            "token_exchange_enabled": self.enabled,
            "token_endpoint_configured": bool(self._cfg("oidc_token_endpoint", "")),
            "token_endpoint_client_configured": self._token_client is not None,
            "validator_configured": self._validator is not None,
            "token_storage": False,  # invariant
            "access_token_persisted": False,
            "refresh_token_persisted": False,
            "fail_closed": True,
        }


# ═══════════════════════════════════════════
# Step 21.2 — Identity Mapping Service
# ═══════════════════════════════════════════


class SandboxV2OIDCIdentityMappingService:
    """OIDC Claims → Local User → Roles → Scopes → SSO Session 映射。

    复用 Step 17 的 SandboxV2IAMClaimMapper（保证 default deny / fail closed 不变）。
    token_storage=false 永远。
    """

    def __init__(
        self,
        settings: Any = None,
        store: Any = None,
        iam_service: Any = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._iam = iam_service

    def _cfg(self, key: str, default: Any = None) -> Any:
        if self._settings:
            return getattr(self._settings, key, default)
        return default

    def map_validated_identity(
        self,
        validation: SandboxV2OIDCIdentityValidationResult,
        *,
        provider_config: Any = None,
        organization_id: str = "",
        workspace_id: str = "",
        create_session: bool = False,
    ) -> SandboxV2OIDCIdentityMapping:
        """Map a validated identity (claims) → local principal + roles + scopes.

        Pre-condition: caller MUST ensure validation.valid=True before mapping.
        We re-check defensively (defense in depth).
        """
        if not validation.valid:
            return SandboxV2OIDCIdentityMapping(
                allowed=False,
                reason=f"identity not validated: {validation.reason}",
                issuer=validation.issuer,
                subject=validation.subject,
                fail_closed=validation.fail_closed,
            )

        claims = validation.claims_redacted or {}
        # Use existing Step 17 mapper — preserves default deny / elevated-role rules
        try:
            from src.open_platform.sandbox_v2.iam_mapping import SandboxV2IAMClaimMapper
            decision, sec_ctx = SandboxV2IAMClaimMapper.map_claims_to_security_context(
                claims, provider_config=provider_config, mappings=None,
                organization_id=organization_id, workspace_id=workspace_id,
            )
        except Exception as e:
            logger.warning("oidc_identity_mapping_failed", extra={"error": str(e)})
            return SandboxV2OIDCIdentityMapping(
                allowed=False, reason=f"mapping error: {e}",
                issuer=validation.issuer, subject=validation.subject,
                fail_closed=True,
            )

        mapping = SandboxV2OIDCIdentityMapping(
            allowed=decision.allowed,
            reason=decision.reason,
            issuer=validation.issuer,
            subject=validation.subject,
            principal_id=sec_ctx.principal_id if sec_ctx else "",
            external_email=str(claims.get("email", "") or ""),
            email_verified=bool(claims.get("email_verified", False)),
            mapped_roles=decision.mapped_roles,
            mapped_scopes=decision.mapped_scopes,
            matched_rules=decision.matched_rules,
            fail_closed=decision.fail_closed,
        )

        if not mapping.allowed or not sec_ctx:
            return mapping

        # Optionally create SSO session — token_storage=false invariant
        if create_session and self._cfg("sso_session_enabled", False):
            session_id = self._create_sso_session(
                sec_ctx, validation, provider_config,
            )
            if session_id:
                mapping.sso_session_id = session_id
                mapping.sso_session_created = True

        return mapping

    def _create_sso_session(
        self,
        sec_ctx: Any,
        validation: SandboxV2OIDCIdentityValidationResult,
        provider_config: Any,
    ) -> str:
        """Create an SSO session WITHOUT storing any token."""
        if not self._store:
            return ""
        try:
            ttl = int(self._cfg("sso_session_ttl_seconds", 3600))
            session = SandboxV2SSOSession(
                principal_id=getattr(sec_ctx, "principal_id", ""),
                principal_type=getattr(sec_ctx, "principal_type", SandboxV2PrincipalType.USER),
                provider_config_id=getattr(provider_config, "provider_config_id", ""),
                external_identity_id=validation.subject,
                organization_id=getattr(sec_ctx, "organization_id", ""),
                workspace_id=getattr(sec_ctx, "workspace_id", ""),
                roles=list(getattr(sec_ctx, "roles", []) or []),
                scopes=list(getattr(sec_ctx, "scopes", []) or []),
                status=SandboxV2SSOSessionStatus.ACTIVE,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
            )
            self._store.create_sso_session(session)
            return session.session_id
        except Exception as e:
            logger.warning("oidc_sso_session_create_failed", extra={"error": str(e)})
            return ""

    def readiness(self) -> dict[str, Any]:
        return {
            "identity_mapping_enabled": True,
            "iam_mapper_available": True,
            "sso_session_creation_enabled": bool(self._cfg("sso_session_enabled", False)),
            "token_storage": False,  # invariant
            "fail_closed": True,
        }


__all__ = [
    "TokenEndpointClientProtocol",
    "SandboxV2OIDCTokenExchangeService",
    "SandboxV2OIDCIdentityMappingService",
]
