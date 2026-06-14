"""Sandbox v2 SAML Identity Mapping Service — Step 22.

SAML Assertion → Identity Mapping → Local User → Roles → Scopes → SSO Session。
与 Step 21 OIDC Identity Mapping 保持一致。

安全原则：
1. 默认 disabled
2. 未映射 → 拒绝
3. 与 OIDC Mapping 共用 IAM ClaimMapper
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.open_platform.sandbox_v2.models import (
    SandboxV2SAMLIdentityMapping,
    SandboxV2PrincipalType,
)
from src.open_platform.sandbox_v2.iam_mapping import SandboxV2IAMClaimMapper

logger = logging.getLogger(__name__)


class SandboxV2SAMLIdentityMappingService:
    """SAML Assertion → Local Identity Mapping Service。默认 disabled。"""

    def __init__(self, settings: Any = None, iam_service: Any = None, store: Any = None):
        self._settings = settings
        self._iam = iam_service
        self._store = store
        self._mapper = SandboxV2IAMClaimMapper()

    def _cfg(self, key: str, default: Any = None) -> Any:
        return getattr(self._settings, key, default) if self._settings else default

    @property
    def enabled(self) -> bool:
        return bool(self._cfg("saml_identity_mapping_enabled", False))

    def map_assertion_to_identity(self, claims: dict[str, Any],
                                  provider_config: Any = None,
                                  organization_id: str = "",
                                  workspace_id: str = "") -> SandboxV2SAMLIdentityMapping:
        """Map SAML assertion claims to local identity.

        Priority:
        1. Use IAM service (if available) — same path as OIDC
        2. Use IAM ClaimMapper directly
        """
        result = SandboxV2SAMLIdentityMapping(
            organization_id=organization_id,
            workspace_id=workspace_id,
            allowed=False,
            reason="Default deny",
            fail_closed=True,
        )

        if not self.enabled:
            result.reason = "SAML identity mapping disabled (SAML_IDENTITY_MAPPING_ENABLED=false)"
            return result

        # Extract claims from assertion
        sub = str(claims.get("sub", "") or claims.get("name_id", "") or "").strip()
        email = str(claims.get("email", "")).strip()
        groups = list(claims.get("groups", []) or claims.get("external_groups", []) or [])
        display_name = str(claims.get("display_name", "") or claims.get("name", "") or "").strip()

        if not sub:
            result.reason = "No subject identifier in SAML claims (missing sub/name_id)"
            return result

        result.external_subject = sub
        result.external_email = email
        result.external_groups = groups
        result.display_name = display_name

        # Route through IAM service if available (same path as OIDC)
        if self._iam and hasattr(self._iam, 'simulate_sso_login'):
            try:
                sim_result = self._iam.simulate_sso_login(
                    claims,
                    getattr(provider_config, 'provider_config_id', ''),
                    organization_id=organization_id,
                    workspace_id=workspace_id,
                )
                if sim_result.get("allowed"):
                    sec_ctx = sim_result.get("security_context", {}) or {}
                    result.allowed = True
                    result.mapped_principal_id = sec_ctx.get("principal_id", f"ext:{sub}")
                    result.mapped_principal_type = sec_ctx.get("principal_type", SandboxV2PrincipalType.USER)
                    result.mapped_roles = list(sec_ctx.get("roles", []) or [])
                    result.mapped_scopes = list(sec_ctx.get("scopes", []) or [])
                    result.reason = "Identity mapped via IAM service"
                    return result
                else:
                    result.reason = sim_result.get("reason", "IAM service denied mapping")
                    return result
            except Exception as e:
                logger.warning(f"IAM service mapping failed: {e}, fallback to direct mapper")

        # Fallback: use IAMClaimMapper directly
        mapping = None
        if self._iam and self._store:
            try:
                mapping = self._iam.list_role_mappings(
                    provider_config_id=getattr(provider_config, 'provider_config_id', ''),
                    organization_id=organization_id,
                    workspace_id=workspace_id,
                    enabled=True,
                )
            except Exception:
                pass

        decision, sec_ctx = self._mapper.map_claims_to_security_context(
            claims, provider_config, mappings=mapping,
            organization_id=organization_id, workspace_id=workspace_id,
        )

        if decision.allowed and sec_ctx:
            result.allowed = True
            result.mapped_principal_id = sec_ctx.principal_id
            result.mapped_principal_type = sec_ctx.principal_type
            result.mapped_roles = list(sec_ctx.roles)
            result.mapped_scopes = list(sec_ctx.scopes)
            result.reason = "Identity mapped via IAM ClaimMapper"
        else:
            result.reason = decision.reason

        return result

    def extract_claims_from_validation(self,
                                       validation_result: Any) -> dict[str, Any]:
        """Extract mappable claims from an assertion validation result."""
        claims: dict[str, Any] = {}
        if hasattr(validation_result, 'claims_redacted'):
            claims = dict(validation_result.claims_redacted)
        claims["sub"] = getattr(validation_result, 'name_id', '') or claims.get("sub", "")
        claims["name_id"] = getattr(validation_result, 'name_id', '')
        return claims

    def get_readiness(self) -> dict[str, Any]:
        """Identity Mapping Readiness。"""
        return {
            "enabled": self.enabled,
            "ready": self.enabled and self._mapper is not None,
            "iam_available": self._iam is not None,
            "mapper_type": type(self._mapper).__name__,
            "status": "ready" if (self.enabled and self._mapper is not None) else "disabled",
            "reason": "" if self.enabled else "SAML_IDENTITY_MAPPING_ENABLED=false",
        }
