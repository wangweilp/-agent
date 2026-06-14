"""Sandbox v2 IAM Provider — Step 17.

IAM Provider Protocol 及默认实现:
- DisabledIAMProvider: 默认 disabled, 所有登录拒绝
- MockIAMProvider: 仅用于测试和本地模拟, 不访问外网
- OIDCProviderSkeleton: 只做配置校验, 不连接 discovery/JWKS
- SAMLProviderSkeleton: 只做 metadata path 校验, 不下载/解析

安全约束:
- 不访问外网
- 不验证真实签名
- 不接受真实 token
- 不下载 metadata
- 不存 secret
"""

from __future__ import annotations

import logging
import os
from typing import Any, Protocol

from src.open_platform.sandbox_v2.iam_mapping import SandboxV2IAMClaimMapper
from src.open_platform.sandbox_v2.models import (
    SandboxV2IAMProviderConfig,
    SandboxV2IAMProviderType,
    SandboxV2SSOProtocol,
    SandboxV2SSOLoginStatus,
    SandboxV2IAMMappingStatus,
    SandboxV2PrincipalType,
    SandboxV2IAMClaimSet,
)

logger = logging.getLogger(__name__)


class IAMProvider(Protocol):
    """IAM Provider Protocol — Step 17 骨架接口。"""

    def get_provider_type(self) -> str: ...

    def validate_config(self, config: SandboxV2IAMProviderConfig) -> dict[str, Any]: ...

    def get_readiness(self, config: SandboxV2IAMProviderConfig | None = None) -> dict[str, Any]: ...

    def simulate_login(
        self, claims: dict[str, Any], config: SandboxV2IAMProviderConfig,
    ) -> dict[str, Any]: ...

    def map_to_security_context(
        self, claims: dict[str, Any], config: SandboxV2IAMProviderConfig,
    ) -> dict[str, Any]: ...


class DisabledIAMProvider:
    """默认 disabled provider — 所有登录返回 disabled。"""

    def get_provider_type(self) -> str:
        return SandboxV2IAMProviderType.DISABLED

    def validate_config(self, config: SandboxV2IAMProviderConfig) -> dict[str, Any]:
        return {"valid": True, "reason": "IAM is disabled — no config validation needed"}

    def get_readiness(self, config: SandboxV2IAMProviderConfig | None = None) -> dict[str, Any]:
        return {
            "provider_type": "disabled",
            "available": True,
            "enabled": False,
            "real_oidc_login": False,
            "real_saml_login": False,
            "token_storage": False,
            "token_introspection": False,
            "iam_safe_mode": True,
        }

    def simulate_login(
        self, claims: dict[str, Any], config: SandboxV2IAMProviderConfig,
    ) -> dict[str, Any]:
        return {
            "login_status": SandboxV2SSOLoginStatus.DISABLED,
            "reason": "IAM is disabled. SSO login is not available.",
            "allowed": False,
        }

    def map_to_security_context(
        self, claims: dict[str, Any], config: SandboxV2IAMProviderConfig,
    ) -> dict[str, Any]:
        return {
            "allowed": False,
            "reason": "IAM is disabled.",
            "security_context": None,
        }


class MockIAMProvider:
    """Mock IAM Provider — 仅用于测试和本地模拟。

    接收安全 fixture claims，不访问外网，不验证真实签名，不接受 token。
    用于验证 claim mapping、role mapping、tenant boundary、audit。
    """

    def get_provider_type(self) -> str:
        return SandboxV2IAMProviderType.MOCK

    def validate_config(self, config: SandboxV2IAMProviderConfig) -> dict[str, Any]:
        if not config.enabled:
            return {"valid": False, "reason": "Mock provider config is disabled"}
        if not config.issuer:
            return {"valid": False, "reason": "Mock provider requires an issuer (for simulation)"}
        return {"valid": True, "reason": "Mock provider config valid for simulation"}

    def get_readiness(self, config: SandboxV2IAMProviderConfig | None = None) -> dict[str, Any]:
        return {
            "provider_type": "mock",
            "available": True,
            "enabled": bool(config and config.enabled),
            "mock_iam_provider": True,
            "claim_mapping": True,
            "role_scope_mapping": True,
            "real_oidc_login": False,
            "real_saml_login": False,
            "token_storage": False,
            "token_introspection": False,
            "iam_safe_mode": True,
        }

    def simulate_login(
        self, claims: dict[str, Any], config: SandboxV2IAMProviderConfig,
    ) -> dict[str, Any]:
        """模拟 SSO 登录 — 只接受安全 mock claims，不接受真实 token。"""
        # Reject real tokens
        if any(k in claims for k in ("access_token", "id_token", "refresh_token", "token", "jwt")):
            return {
                "login_status": SandboxV2SSOLoginStatus.REJECTED,
                "reason": "Real tokens are not accepted. This provider is for mock simulation only.",
                "allowed": False,
            }

        mapper = SandboxV2IAMClaimMapper()

        # Validate claims
        valid, reason = mapper.validate_claim_set(claims, config)
        if not valid:
            return {
                "login_status": SandboxV2SSOLoginStatus.REJECTED,
                "reason": reason,
                "allowed": False,
            }

        # Check email domain
        email = str(claims.get("email", "")).strip()
        if config.allowed_domains:
            domain_ok, domain_reason = mapper.validate_email_domain(email, config.allowed_domains)
            if not domain_ok:
                return {
                    "login_status": SandboxV2SSOLoginStatus.REJECTED,
                    "reason": domain_reason,
                    "allowed": False,
                }

        # Check email verified
        if config.require_verified_email and not claims.get("email_verified", False):
            return {
                "login_status": SandboxV2SSOLoginStatus.REJECTED,
                "reason": "Email not verified",
                "allowed": False,
            }

        # Build claim set (redacted)
        claim_set = SandboxV2IAMClaimSet(
            issuer=config.issuer,
            subject=str(claims.get("sub", "")),
            email=email,
            email_verified=bool(claims.get("email_verified", False)),
            name=str(claims.get("name", "")),
            groups=list(claims.get("groups", []) or []),
            tenant=str(claims.get("tenant", "") or claims.get("org", "")),
            audience=str(claims.get("aud", "") or claims.get("audience", "")),
            raw_claims_redacted=mapper.redact_claims(claims),
        )

        return {
            "login_status": SandboxV2SSOLoginStatus.SIMULATED,
            "reason": "Mock SSO login simulated successfully",
            "allowed": True,
            "claim_set": claim_set.to_dict(),
        }

    def map_to_security_context(
        self, claims: dict[str, Any], config: SandboxV2IAMProviderConfig,
    ) -> dict[str, Any]:
        """Mock provider: 将 claims 映射为 security context。"""
        mapper = SandboxV2IAMClaimMapper()
        decision, sec_ctx = mapper.map_claims_to_security_context(
            claims, config, mappings=None,
            organization_id=config.organization_id,
            workspace_id=config.workspace_id,
        )
        return {
            "allowed": decision.allowed,
            "decision": decision.to_dict(),
            "security_context": sec_ctx.to_dict() if sec_ctx else None,
        }


class OIDCProviderSkeleton:
    """OIDC Provider 骨架 — 只做配置校验，不访问外网。

    不访问 discovery URL，不下载 JWKS，不验证真实 token。
    discovery_enabled=false → 返回 preflight_only。
    如果用户传 token → 拒绝并提示不在本步骤处理真实 token。
    """

    def get_provider_type(self) -> str:
        return SandboxV2IAMProviderType.OIDC

    def validate_config(self, config: SandboxV2IAMProviderConfig) -> dict[str, Any]:
        issues = []
        if not config.issuer:
            issues.append("OIDC issuer URL is required")
        if not config.client_id:
            issues.append("OIDC client_id is required")
        if config.discovery_enabled:
            issues.append(
                "OIDC discovery is disabled in Step 17 — "
                "real discovery will be enabled in a future step"
            )
        return {"valid": len(issues) == 0, "issues": issues, "reason": "; ".join(issues) if issues else "Config valid (skeleton mode)"}

    def get_readiness(self, config: SandboxV2IAMProviderConfig | None = None) -> dict[str, Any]:
        return {
            "provider_type": "oidc",
            "available": True,
            "enabled": bool(config and config.enabled),
            "oidc_provider_skeleton": True,
            "discovery_enabled": bool(config and config.discovery_enabled),
            "real_oidc_login": False,
            "token_introspection": False,
            "token_storage": False,
            "iam_safe_mode": True,
            "preflight_only": True,
        }

    def simulate_login(
        self, claims: dict[str, Any], config: SandboxV2IAMProviderConfig,
    ) -> dict[str, Any]:
        """OIDC skeleton: 拒绝真实 token，不支持真实登录。"""
        # Reject real tokens
        token_keys = {"access_token", "id_token", "refresh_token", "token", "jwt", "code"}
        if any(k in claims for k in token_keys):
            return {
                "login_status": SandboxV2SSOLoginStatus.REJECTED,
                "reason": "Real OIDC tokens are not accepted in Step 17. Only mock simulation is supported.",
                "allowed": False,
            }
        return {
            "login_status": SandboxV2SSOLoginStatus.DISABLED,
            "reason": "OIDC skeleton: real login not implemented. Use mock provider for simulation.",
            "allowed": False,
        }

    def map_to_security_context(
        self, claims: dict[str, Any], config: SandboxV2IAMProviderConfig,
    ) -> dict[str, Any]:
        return {
            "allowed": False,
            "reason": "OIDC skeleton: token validation not available in Step 17.",
            "security_context": None,
        }


class SAMLProviderSkeleton:
    """SAML Provider 骨架 — 只做 metadata path 校验，不访问外网。

    不下载 metadata URL，不解析真实 SAML Response。
    metadata_download_enabled=false → 不联网。
    如果用户传 SAMLResponse → 拒绝并提示不在本步骤处理真实 SAML 登录。
    """

    def get_provider_type(self) -> str:
        return SandboxV2IAMProviderType.SAML

    def validate_config(self, config: SandboxV2IAMProviderConfig) -> dict[str, Any]:
        issues = []
        if not config.saml_entity_id:
            issues.append("SAML entity_id is required")
        if not config.saml_metadata_ref and not config.saml_metadata_path:
            issues.append("SAML metadata_path (local file) is required in skeleton mode")
        if config.saml_metadata_ref and not os.path.isfile(config.saml_metadata_ref):
            issues.append(
                f"SAML metadata_ref path does not exist: {config.saml_metadata_ref}"
            )
        if config.discovery_enabled:
            issues.append(
                "SAML metadata download is disabled in Step 17 — "
                "real download will be enabled in a future step"
            )
        return {"valid": len(issues) == 0, "issues": issues, "reason": "; ".join(issues) if issues else "Config valid (skeleton mode)"}

    def get_readiness(self, config: SandboxV2IAMProviderConfig | None = None) -> dict[str, Any]:
        return {
            "provider_type": "saml",
            "available": True,
            "enabled": bool(config and config.enabled),
            "saml_provider_skeleton": True,
            "metadata_download_enabled": False,
            "real_saml_login": False,
            "token_storage": False,
            "iam_safe_mode": True,
        }

    def simulate_login(
        self, claims: dict[str, Any], config: SandboxV2IAMProviderConfig,
    ) -> dict[str, Any]:
        """SAML skeleton: 拒绝真实 SAMLResponse，不支持真实登录。"""
        # Reject SAMLResponse
        if "SAMLResponse" in claims or "saml_response" in claims or "SAMLart" in claims:
            return {
                "login_status": SandboxV2SSOLoginStatus.REJECTED,
                "reason": "Real SAML responses are not accepted in Step 17. Only mock simulation is supported.",
                "allowed": False,
            }
        return {
            "login_status": SandboxV2SSOLoginStatus.DISABLED,
            "reason": "SAML skeleton: real login not implemented. Use mock provider for simulation.",
            "allowed": False,
        }

    def map_to_security_context(
        self, claims: dict[str, Any], config: SandboxV2IAMProviderConfig,
    ) -> dict[str, Any]:
        return {
            "allowed": False,
            "reason": "SAML skeleton: SAMLResponse parsing not available in Step 17.",
            "security_context": None,
        }


def get_iam_provider(provider_type: str) -> Any:
    """Factory: 根据 provider_type 返回对应的 IAM Provider。"""
    providers = {
        SandboxV2IAMProviderType.DISABLED: DisabledIAMProvider(),
        SandboxV2IAMProviderType.MOCK: MockIAMProvider(),
        SandboxV2IAMProviderType.OIDC: OIDCProviderSkeleton(),
        SandboxV2IAMProviderType.SAML: SAMLProviderSkeleton(),
    }
    return providers.get(provider_type, DisabledIAMProvider())
