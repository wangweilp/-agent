"""Sandbox v2 IAM Claim Mapper — Step 17.

将外部身份声明 (claims) 映射为 Sandbox v2 Security Context。
默认 deny + fail closed。不存 token，不泄露 secret。

安全原则：
1. 缺 subject → 拒绝
2. 缺 issuer → 拒绝
3. email 未验证且 require_verified_email=true → 拒绝
4. email domain 不在 allowed_domains → 拒绝
5. tenant claim 与 organization/workspace 不匹配 → 拒绝
6. unknown group → 不给高权限 (default_role 不能是 owner/admin)
7. raw claims 必须 redacted
8. 不存 token
"""

from __future__ import annotations

import logging
from typing import Any

from src.open_platform.sandbox_v2.models import (
    SandboxV2IAMClaimSet,
    SandboxV2IAMMappingDecision,
    SandboxV2IAMMappingStatus,
    SandboxV2IAMRoleMapping,
    SandboxV2IAMProviderConfig,
    SandboxV2PrincipalType,
    SandboxV2Role,
    SandboxV2SecurityContext,
)

logger = logging.getLogger(__name__)

# Sensitive claim keys to redact
_REDACT_KEYS = frozenset({
    "access_token", "id_token", "refresh_token", "token", "secret",
    "client_secret", "password", "credential", "key", "private_key",
    "jwt", "authorization", "cookie", "session",
})

# Elevated roles that must NOT be assigned by default
_ELEVATED_ROLES = frozenset({SandboxV2Role.OWNER, SandboxV2Role.ADMIN})


class SandboxV2IAMClaimMapper:
    """外部身份声明 → Security Context 映射器。默认 deny。"""

    # ── Safe defaults for default_role ──
    VALID_DEFAULT_ROLES = frozenset({
        SandboxV2Role.VIEWER, SandboxV2Role.AUDITOR,
        SandboxV2Role.DEVELOPER, SandboxV2Role.OPERATOR,
    })

    @staticmethod
    def redact_claims(claims: dict[str, Any]) -> dict[str, Any]:
        """Redact sensitive keys from raw claims. Never stores tokens."""
        return {
            k: ("***REDACTED***" if k.lower() in _REDACT_KEYS else v)
            for k, v in (claims or {}).items()
        }

    @staticmethod
    def validate_claim_set(
        claims: dict[str, Any],
        provider_config: SandboxV2IAMProviderConfig | None = None,
    ) -> tuple[bool, str]:
        """Validate claims. Returns (valid, reason). Default deny."""
        if not claims or not isinstance(claims, dict):
            return False, "Missing or invalid claims"

        subject = str(claims.get("sub", "") or claims.get("subject", "")).strip()
        if not subject:
            return False, "Missing subject (sub) in claims"

        issuer = str(claims.get("iss", "") or claims.get("issuer", "")).strip()
        if not issuer:
            return False, "Missing issuer (iss) in claims"

        # Require email if provider config says so
        if provider_config:
            email = str(claims.get("email", "")).strip()
            if not email:
                return False, "Missing email in claims"

            # Check email_verified
            if provider_config.require_verified_email:
                email_verified = claims.get("email_verified", False)
                if not email_verified:
                    return False, "Email not verified"

            # Check domain allowlist
            if provider_config.allowed_domains:
                domain_ok, reason = SandboxV2IAMClaimMapper.validate_email_domain(
                    email, provider_config.allowed_domains,
                )
                if not domain_ok:
                    return False, reason

        return True, "Claims valid"

    @staticmethod
    def validate_email_domain(
        email: str, allowed_domains: list[str],
    ) -> tuple[bool, str]:
        """Validate email domain against allowlist. Returns (allowed, reason)."""
        if not allowed_domains:
            return False, "No allowed email domains configured"
        if "@" not in email:
            return False, f"Invalid email format: {email}"
        domain = email.rsplit("@", 1)[1].lower()
        if domain not in [d.lower().strip() for d in allowed_domains]:
            return False, f"Email domain '{domain}' not in allowed domains"
        return True, f"Email domain '{domain}' allowed"

    @staticmethod
    def validate_tenant_boundary(
        claims: dict[str, Any],
        organization_id: str = "",
        workspace_id: str = "",
    ) -> tuple[bool, str]:
        """Validate tenant claim matches org/workspace. Returns (valid, reason)."""
        tenant = str(claims.get("tenant", "") or claims.get("org", "") or "").strip()
        # If tenant claim exists, it must match
        if tenant and organization_id and tenant != organization_id:
            return False, f"Tenant claim '{tenant}' does not match organization '{organization_id}'"
        # workspace check
        ws_claim = str(claims.get("workspace", "") or claims.get("ws", "") or "").strip()
        if ws_claim and workspace_id and ws_claim != workspace_id:
            return False, f"Workspace claim '{ws_claim}' does not match workspace '{workspace_id}'"
        return True, "Tenant boundary valid"

    @staticmethod
    def map_claims_to_identity(
        claims: dict[str, Any],
        provider_config: SandboxV2IAMProviderConfig | None = None,
    ) -> dict[str, Any]:
        """Map claims to external identity dict."""
        sub = str(claims.get("sub", "") or claims.get("subject", "")).strip()
        email = str(claims.get("email", "")).strip()
        return {
            "external_subject": sub,
            "external_email": email,
            "email_verified": bool(claims.get("email_verified", False)),
            "external_groups": list(claims.get("groups", []) or []),
            "display_name": str(claims.get("name", "") or claims.get("preferred_username", "") or ""),
            "provider_type": provider_config.provider_type if provider_config else "unknown",
            "provider_config_id": provider_config.provider_config_id if provider_config else "",
        }

    @staticmethod
    def evaluate_role_mapping(
        claims: dict[str, Any],
        provider_config: SandboxV2IAMProviderConfig,
        mappings: list[SandboxV2IAMRoleMapping],
    ) -> tuple[list[str], list[str], list[str]]:
        """Evaluate external group/claim to role/scope mappings.

        Returns (roles, scopes, matched_rules).
        - unknown group → no role (falls back to default_role)
        - unknown group → no elevated permissions
        - role mapping ignored if it produces admin/owner (unless explicit mapping from known group)
        """
        roles: list[str] = []
        scopes: list[str] = []
        matched_rules: list[str] = []

        external_groups = set(
            str(g).lower().strip()
            for g in (claims.get("groups", []) or [])
            if g
        )

        for mapping in mappings:
            if not mapping.enabled:
                continue
            group = str(mapping.external_group).lower().strip()
            claim_key = str(mapping.external_claim).strip()

            match = False
            if group and group in external_groups:
                match = True
            if claim_key and claims.get(claim_key):
                match = True

            if match:
                matched_rules.append(mapping.mapping_id)
                role = mapping.sandbox_role
                # Forbid elevated roles through group mapping unless explicitly configured
                # (admin/owner are still allowed if explicitly mapped — the calling code
                #  further validates that default_role is not elevated)
                if role and role not in roles:
                    roles.append(role)
                for s in (mapping.sandbox_scopes or []):
                    if s and s not in scopes:
                        scopes.append(s)

        return roles, scopes, matched_rules

    @staticmethod
    def map_claims_to_security_context(
        claims: dict[str, Any],
        provider_config: SandboxV2IAMProviderConfig | None = None,
        mappings: list[SandboxV2IAMRoleMapping] | None = None,
        organization_id: str = "",
        workspace_id: str = "",
    ) -> tuple[SandboxV2IAMMappingDecision, SandboxV2SecurityContext | None]:
        """Full claim → security context mapping. Returns (decision, security_context).

        Security context is None if mapping is denied.
        """
        decision = SandboxV2IAMMappingDecision(
            allowed=False,
            status=SandboxV2IAMMappingStatus.REJECTED,
            reason="Default deny.",
            fail_closed=True,
            organization_id=organization_id,
            workspace_id=workspace_id,
        )

        # 1. Validate claims
        valid, reason = SandboxV2IAMClaimMapper.validate_claim_set(claims, provider_config)
        if not valid:
            decision.reason = reason
            decision.status = SandboxV2IAMMappingStatus.REJECTED
            return decision, None

        # 2. Check email domain
        email = str(claims.get("email", "")).strip()
        if provider_config and provider_config.allowed_domains:
            domain_ok, domain_reason = SandboxV2IAMClaimMapper.validate_email_domain(
                email, provider_config.allowed_domains,
            )
            decision.email_domain_allowed = domain_ok
            if not domain_ok:
                decision.reason = domain_reason
                decision.status = SandboxV2IAMMappingStatus.REJECTED
                return decision, None
        else:
            decision.email_domain_allowed = False

        # 3. Check email verified
        decision.email_verified = bool(claims.get("email_verified", False))
        if provider_config and provider_config.require_verified_email and not decision.email_verified:
            decision.reason = "Email not verified"
            decision.status = SandboxV2IAMMappingStatus.REJECTED
            return decision, None

        # 4. Check tenant boundary
        tenant_ok, tenant_reason = SandboxV2IAMClaimMapper.validate_tenant_boundary(
            claims, organization_id, workspace_id,
        )
        decision.tenant_match = tenant_ok
        if not tenant_ok:
            decision.reason = tenant_reason
            decision.status = SandboxV2IAMMappingStatus.REJECTED
            return decision, None

        # 5. Evaluate role mappings
        roles: list[str] = []
        scopes: list[str] = []
        matched_rules: list[str] = []

        if provider_config and provider_config.external_group_mapping_enabled and mappings:
            roles, scopes, matched_rules = SandboxV2IAMClaimMapper.evaluate_role_mapping(
                claims, provider_config, mappings,
            )
            decision.group_mapping_applied = True

        # 6. Apply default_role if no roles from group mapping
        if not roles and provider_config:
            default_role = provider_config.default_role
            if default_role not in SandboxV2IAMClaimMapper.VALID_DEFAULT_ROLES:
                decision.reason = f"Invalid default_role '{default_role}' — must be viewer|auditor|developer|operator"
                decision.status = SandboxV2IAMMappingStatus.REJECTED
                return decision, None
            roles = [default_role]

        # 7. Elevated role check — never auto-elevate through default or unknown group
        elevated = [r for r in roles if r in _ELEVATED_ROLES]
        if elevated and not matched_rules:
            decision.reason = (
                f"Cannot assign elevated role(s) {elevated} without explicit group mapping. "
                f"Default role or unknown group must not produce admin/owner."
            )
            decision.status = SandboxV2IAMMappingStatus.REJECTED
            return decision, None

        decision.matched_rules = matched_rules
        decision.mapped_roles = roles
        decision.mapped_scopes = scopes

        # 8. Build security context
        sub = str(claims.get("sub", "") or claims.get("subject", "")).strip()
        security_context = SandboxV2SecurityContext(
            principal_id=f"ext:{sub}",
            principal_type=SandboxV2PrincipalType.USER,
            roles=roles,
            scopes=scopes,
            organization_id=organization_id,
            workspace_id=workspace_id,
        )

        decision.allowed = True
        decision.status = SandboxV2IAMMappingStatus.MAPPED
        decision.principal_id = security_context.principal_id
        decision.principal_type = security_context.principal_type
        decision.reason = "Claims mapped successfully"

        # 9. Check if JIT provisioning is needed
        if provider_config and provider_config.jit_provisioning:
            decision.jit_provisioning_required = True

        return decision, security_context

    @staticmethod
    def create_mapping_decision(
        *,
        allowed: bool = False,
        status: str = SandboxV2IAMMappingStatus.REJECTED,
        reason: str = "Default deny.",
        principal_id: str = "",
        principal_type: str = SandboxV2PrincipalType.ANONYMOUS,
        mapped_roles: list[str] | None = None,
        mapped_scopes: list[str] | None = None,
        organization_id: str = "",
        workspace_id: str = "",
        email_domain_allowed: bool = False,
        email_verified: bool = False,
        tenant_match: bool = False,
        group_mapping_applied: bool = False,
        jit_provisioning_required: bool = False,
        fail_closed: bool = True,
        matched_rules: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SandboxV2IAMMappingDecision:
        """Create a mapping decision record."""
        return SandboxV2IAMMappingDecision(
            allowed=allowed,
            status=status,
            reason=reason,
            principal_id=principal_id,
            principal_type=principal_type,
            mapped_roles=mapped_roles or [],
            mapped_scopes=mapped_scopes or [],
            organization_id=organization_id,
            workspace_id=workspace_id,
            email_domain_allowed=email_domain_allowed,
            email_verified=email_verified,
            tenant_match=tenant_match,
            group_mapping_applied=group_mapping_applied,
            jit_provisioning_required=jit_provisioning_required,
            fail_closed=fail_closed,
            matched_rules=matched_rules or [],
            metadata=metadata or {},
        )
