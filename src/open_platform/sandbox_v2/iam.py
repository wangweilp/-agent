"""Sandbox v2 IAM Service — Step 17.

IAM / SSO 集成服务层。
默认 SSO disabled，不接受真实 token，不访问外网，不下载 metadata。
所有 mapping decision 写 security audit。

安全约束:
1. 默认 SSO disabled
2. simulate_sso_login 只允许 mock/safe fixture claims
3. 不接受真实 token
4. 不访问外网
5. 不下载 metadata
6. 所有 mapping decision 写 security audit
7. cross tenant mapping 拒绝并写 audit
8. JIT provisioning 默认 false
9. 不存 secret
10. 所有返回中 mask secret
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.open_platform.sandbox_v2.iam_mapping import SandboxV2IAMClaimMapper
from src.open_platform.sandbox_v2.iam_provider import get_iam_provider
from src.open_platform.sandbox_v2.models import (
    SandboxV2IAMProviderConfig,
    SandboxV2IAMProviderType,
    SandboxV2SSOProtocol,
    SandboxV2SSOLoginStatus,
    SandboxV2IAMMappingStatus,
    SandboxV2IAMRoleMapping,
    SandboxV2ExternalIdentity,
    SandboxV2IdentityLinkStatus,
    SandboxV2IAMMappingDecision,
    SandboxV2SSOSimulationResult,
    SandboxV2SecurityContext,
    SandboxV2PrincipalType,
    SandboxV2Role,
    SandboxV2AuditEventType,
    SandboxV2AuditSeverity,
    SandboxV2ResourceType,
)

logger = logging.getLogger(__name__)


class SandboxV2IAMService:
    """Sandbox v2 IAM / SSO 集成服务。"""

    def __init__(self, store: Any = None, audit_service: Any = None, settings: Any = None):
        self._store = store
        self._audit = audit_service
        self._settings = settings
        self._mapper = SandboxV2IAMClaimMapper()

    @property
    def iam_enabled(self) -> bool:
        if self._settings:
            return bool(getattr(self._settings, "iam_enabled", False))
        return False

    @property
    def sso_enabled(self) -> bool:
        if self._settings:
            return bool(getattr(self._settings, "sso_enabled", False))
        return False

    # ── Audit helper ──

    def _audit_iam_event(
        self, *, event_type: str, decision: str = "deny",
        reason: str = "", principal_id: str = "",
        principal_type: str = SandboxV2PrincipalType.ANONYMOUS,
        organization_id: str = "", workspace_id: str = "",
        resource_type: str = "", resource_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Write an IAM audit event. Returns audit_event_id."""
        if not self._audit:
            return ""
        try:
            event = self._audit.create_audit_event(
                event_type=event_type,
                severity=SandboxV2AuditSeverity.HIGH if decision == "deny" else SandboxV2AuditSeverity.INFO,
                principal_id=principal_id,
                principal_type=principal_type,
                organization_id=organization_id,
                workspace_id=workspace_id,
                resource_type=resource_type,
                resource_id=resource_id,
                action=event_type,
                decision=decision,
                reason=reason,
                metadata=metadata or {},
            )
            return event.audit_event_id if event else ""
        except Exception as e:
            logger.warning(f"Failed to write IAM audit event: {e}")
            return ""

    # ── Provider Config ──

    def create_provider_config(self, **kwargs) -> SandboxV2IAMProviderConfig | None:
        """Create IAM provider config. Client secret is stored as ref, never plaintext."""
        client_secret = kwargs.pop("client_secret", None)
        if client_secret:
            # Store as ref — never store plaintext secret
            kwargs["client_secret_ref"] = f"secret://sandbox-v2/iam/{kwargs.get('provider_type', 'unknown')}/{kwargs.get('organization_id', 'default')}"
        else:
            kwargs["client_secret_ref"] = ""

        config = SandboxV2IAMProviderConfig(**kwargs)

        if self._store:
            try:
                self._store.create_iam_provider_config(config)
            except Exception as e:
                logger.error(f"Failed to create IAM provider config: {e}")
                return None

        self._audit_iam_event(
            event_type=SandboxV2AuditEventType.IAM_PROVIDER_CONFIG_CREATED,
            decision="allow",
            reason=f"Provider config created: {config.provider_type}",
            organization_id=config.organization_id,
            workspace_id=config.workspace_id,
            resource_type=SandboxV2ResourceType.IAM_PROVIDER_CONFIG,
            resource_id=config.provider_config_id,
            metadata={"provider_type": config.provider_type, "protocol": config.protocol},
        )

        return config

    def get_provider_config(self, provider_config_id: str) -> SandboxV2IAMProviderConfig | None:
        if not self._store:
            return None
        return self._store.get_iam_provider_config(provider_config_id)

    def list_provider_configs(
        self, organization_id: str = "", workspace_id: str = "", limit: int = 50,
    ) -> list[SandboxV2IAMProviderConfig]:
        if not self._store:
            return []
        return self._store.list_iam_provider_configs(
            organization_id=organization_id, workspace_id=workspace_id, limit=limit,
        )

    def update_provider_config_status(
        self, provider_config_id: str, enabled: bool, reason: str = "",
    ) -> SandboxV2IAMProviderConfig | None:
        if not self._store:
            return None
        config = self._store.update_iam_provider_config_status(provider_config_id, enabled, reason)
        if config:
            self._audit_iam_event(
                event_type=SandboxV2AuditEventType.IAM_PROVIDER_CONFIG_UPDATED,
                decision="allow",
                reason=reason or f"Provider config status changed to enabled={enabled}",
                organization_id=config.organization_id,
                workspace_id=config.workspace_id,
                resource_type=SandboxV2ResourceType.IAM_PROVIDER_CONFIG,
                resource_id=provider_config_id,
            )
        return config

    # ── Role Mapping ──

    def create_role_mapping(self, **kwargs) -> SandboxV2IAMRoleMapping | None:
        mapping = SandboxV2IAMRoleMapping(**kwargs)
        if self._store:
            try:
                self._store.create_iam_role_mapping(mapping)
            except Exception as e:
                logger.error(f"Failed to create IAM role mapping: {e}")
                return None

        self._audit_iam_event(
            event_type=SandboxV2AuditEventType.IAM_ROLE_MAPPING_CREATED,
            decision="allow",
            reason=f"Role mapping created: {mapping.external_group} -> {mapping.sandbox_role}",
            organization_id=mapping.organization_id,
            workspace_id=mapping.workspace_id,
            resource_type=SandboxV2ResourceType.IAM_ROLE_MAPPING,
            resource_id=mapping.mapping_id,
        )
        return mapping

    def list_role_mappings(
        self, provider_config_id: str = "", organization_id: str = "",
        workspace_id: str = "", enabled: bool | None = None, limit: int = 50,
    ) -> list[SandboxV2IAMRoleMapping]:
        if not self._store:
            return []
        return self._store.list_iam_role_mappings(
            provider_config_id=provider_config_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            enabled=enabled,
            limit=limit,
        )

    # ── SSO Simulation ──

    def simulate_sso_login(
        self, claims: dict[str, Any], provider_config_id: str,
        organization_id: str = "", workspace_id: str = "",
    ) -> dict[str, Any]:
        """Simulate SSO login — only mock/safe fixture claims allowed. No real tokens."""
        # 1. Check IAM enabled
        if not self.iam_enabled:
            return {
                "login_status": SandboxV2SSOLoginStatus.DISABLED,
                "reason": "IAM is disabled. Enable SANDBOX_V2_IAM_ENABLED=true to use IAM features.",
                "allowed": False,
                "claim_set": None,
                "mapping_decision": None,
                "security_context": None,
            }

        # 2. Get provider config
        config = self.get_provider_config(provider_config_id) if self._store else None
        if not config:
            return {
                "login_status": SandboxV2SSOLoginStatus.FAILED,
                "reason": f"Provider config not found: {provider_config_id}",
                "allowed": False,
            }

        # 3. Validate tenant boundary on config
        if config.organization_id and organization_id and config.organization_id != organization_id:
            self._audit_iam_event(
                event_type=SandboxV2AuditEventType.IAM_CROSS_TENANT_DENIED,
                decision="deny",
                reason=f"Provider config org {config.organization_id} != request org {organization_id}",
                organization_id=organization_id, workspace_id=workspace_id,
                resource_type=SandboxV2ResourceType.IAM_PROVIDER_CONFIG,
                resource_id=provider_config_id,
            )
            return {
                "login_status": SandboxV2SSOLoginStatus.REJECTED,
                "reason": "Cross-tenant mapping denied: provider config belongs to different organization",
                "allowed": False,
            }

        # 4. Get provider
        provider = get_iam_provider(config.provider_type)

        # 5. Reject tokens
        token_keys = {"access_token", "id_token", "refresh_token", "token", "jwt", "code", "SAMLResponse"}
        if any(k in claims for k in token_keys):
            self._audit_iam_event(
                event_type=SandboxV2AuditEventType.IAM_CLAIM_MAPPING_DENIED,
                decision="deny",
                reason="Real token submission rejected — Step 17 does not process real tokens",
                organization_id=organization_id, workspace_id=workspace_id,
                resource_type=SandboxV2ResourceType.IAM_PROVIDER_CONFIG,
                resource_id=provider_config_id,
            )
            return {
                "login_status": SandboxV2SSOLoginStatus.REJECTED,
                "reason": "Real tokens are not accepted in Step 17. Use mock claims simulation.",
                "allowed": False,
            }

        # 6. Simulate login via provider
        result = provider.simulate_login(claims, config)

        claim_set_dict = result.get("claim_set", {})
        login_status = result.get("login_status", SandboxV2SSOLoginStatus.REJECTED)
        allowed = result.get("allowed", False)

        # 7. If login simulated successfully, map to security context
        mapping_decision_dict = {}
        security_context_dict = {}

        if allowed:
            # Get role mappings
            role_mappings = self.list_role_mappings(
                provider_config_id=provider_config_id,
                organization_id=organization_id,
                workspace_id=workspace_id,
                enabled=True,
            ) if config.external_group_mapping_enabled else []

            decision, sec_ctx = self._mapper.map_claims_to_security_context(
                claims, config, mappings=role_mappings,
                organization_id=organization_id, workspace_id=workspace_id,
            )
            mapping_decision_dict = decision.to_dict()
            security_context_dict = sec_ctx.to_dict() if sec_ctx else {}

            # Update login status based on mapping decision
            if not decision.allowed:
                login_status = SandboxV2SSOLoginStatus.REJECTED
                allowed = False
            else:
                login_status = SandboxV2SSOLoginStatus.MAPPED

            # Persist mapping decision
            if self._store:
                try:
                    self._store.create_iam_mapping_decision(decision)
                except Exception as e:
                    logger.warning(f"Failed to persist mapping decision: {e}")

            # Audit
            audit_event_id = self._audit_iam_event(
                event_type=SandboxV2AuditEventType.IAM_SSO_SIMULATION_RUN
                if allowed else SandboxV2AuditEventType.IAM_CLAIM_MAPPING_DENIED,
                decision="allow" if allowed else "deny",
                reason=decision.reason if not allowed else "SSO simulation completed",
                principal_id=decision.principal_id,
                principal_type=decision.principal_type,
                organization_id=organization_id, workspace_id=workspace_id,
                resource_type=SandboxV2ResourceType.IAM_SSO_SIMULATION,
                resource_id=provider_config_id,
                metadata={
                    "provider_type": config.provider_type,
                    "login_status": login_status,
                    "email_domain_allowed": decision.email_domain_allowed,
                    "email_verified": decision.email_verified,
                    "tenant_match": decision.tenant_match,
                },
            )

            # 8. Persist simulation result
            simulation = SandboxV2SSOSimulationResult(
                provider_config_id=provider_config_id,
                protocol=config.protocol,
                login_status=login_status,
                claim_set=claim_set_dict,
                mapping_decision=mapping_decision_dict,
                security_context=security_context_dict,
                audit_event_id=audit_event_id,
            )
            if self._store:
                try:
                    self._store.create_sso_simulation_result(simulation)
                except Exception as e:
                    logger.warning(f"Failed to persist SSO simulation result: {e}")
        else:
            # Audit denied simulation
            self._audit_iam_event(
                event_type=SandboxV2AuditEventType.IAM_CLAIM_MAPPING_DENIED,
                decision="deny",
                reason=result.get("reason", "SSO simulation denied"),
                organization_id=organization_id, workspace_id=workspace_id,
                resource_type=SandboxV2ResourceType.IAM_SSO_SIMULATION,
                resource_id=provider_config_id,
            )

        return {
            "login_status": login_status,
            "reason": result.get("reason", ""),
            "allowed": allowed,
            "claim_set": claim_set_dict,
            "mapping_decision": mapping_decision_dict,
            "security_context": security_context_dict,
        }

    # ── External Identity ──

    def map_external_identity(
        self, claims: dict[str, Any], provider_config_id: str,
        organization_id: str = "", workspace_id: str = "",
    ) -> dict[str, Any]:
        """Map external identity from claims. Creates/updates external identity record."""
        if not self._store:
            return {"allowed": False, "reason": "No store available"}

        config = self.get_provider_config(provider_config_id)
        if not config:
            return {"allowed": False, "reason": f"Provider config not found: {provider_config_id}"}

        identity_data = self._mapper.map_claims_to_identity(claims, config)
        identity = SandboxV2ExternalIdentity(
            provider_config_id=provider_config_id,
            provider_type=config.provider_type,
            external_subject=identity_data["external_subject"],
            external_email=identity_data["external_email"],
            email_verified=identity_data["email_verified"],
            external_groups=identity_data["external_groups"],
            display_name=identity_data["display_name"],
            organization_id=organization_id,
            workspace_id=workspace_id,
            status=SandboxV2IdentityLinkStatus.ACTIVE,
            last_seen_at=datetime.now(timezone.utc),
        )

        try:
            self._store.create_external_identity(identity)
        except Exception as e:
            logger.error(f"Failed to create external identity: {e}")
            return {"allowed": False, "reason": str(e)}

        self._audit_iam_event(
            event_type=SandboxV2AuditEventType.IAM_EXTERNAL_IDENTITY_LINKED,
            decision="allow",
            reason=f"External identity linked: {identity.external_subject}",
            principal_id=identity.linked_principal_id,
            principal_type=SandboxV2PrincipalType.USER,
            organization_id=organization_id, workspace_id=workspace_id,
            resource_type=SandboxV2ResourceType.IAM_EXTERNAL_IDENTITY,
            resource_id=identity.external_identity_id,
        )

        return {"allowed": True, "identity": identity.to_dict()}

    def get_external_identity(self, external_identity_id: str) -> SandboxV2ExternalIdentity | None:
        if not self._store:
            return None
        return self._store.get_external_identity(external_identity_id)

    def list_external_identities(
        self, organization_id: str = "", workspace_id: str = "",
        provider_config_id: str = "", limit: int = 50,
    ) -> list[SandboxV2ExternalIdentity]:
        if not self._store:
            return []
        return self._store.list_external_identities(
            organization_id=organization_id, workspace_id=workspace_id,
            provider_config_id=provider_config_id, limit=limit,
        )

    # ── Mapping Decisions ──

    def list_iam_mapping_decisions(
        self, organization_id: str = "", workspace_id: str = "", limit: int = 50,
    ) -> list[SandboxV2IAMMappingDecision]:
        if not self._store:
            return []
        return self._store.list_iam_mapping_decisions(
            organization_id=organization_id, workspace_id=workspace_id, limit=limit,
        )

    # ── SSO Simulations ──

    def list_sso_simulation_results(
        self, organization_id: str = "", workspace_id: str = "", limit: int = 50,
    ) -> list[SandboxV2SSOSimulationResult]:
        if not self._store:
            return []
        return self._store.list_sso_simulation_results(
            organization_id=organization_id, workspace_id=workspace_id, limit=limit,
        )

    # ── Readiness ──

    def get_iam_readiness(self) -> dict[str, Any]:
        """IAM readiness check."""
        iam_enabled = self.iam_enabled
        sso_enabled = self.sso_enabled
        provider_type = getattr(self._settings, "iam_provider", "disabled") if self._settings else "disabled"

        provider = get_iam_provider(provider_type)
        provider_readiness = provider.get_readiness() if hasattr(provider, 'get_readiness') else {}

        return {
            "iam_provider_config": True,
            "sso_config_model": True,
            "oidc_provider_skeleton": True,
            "saml_provider_skeleton": True,
            "mock_iam_provider": True,
            "claim_mapping": True,
            "role_scope_mapping": True,
            "jit_provisioning": self._settings.iam_jit_provisioning if self._settings else False,
            "external_iam_enabled": iam_enabled,
            "sso_enabled": sso_enabled,
            "real_oidc_login": False,
            "real_saml_login": False,
            "token_storage": False,
            "token_introspection": False,
            "iam_safe_mode": True,
            **provider_readiness,
        }

    def get_sso_readiness(self) -> dict[str, Any]:
        """SSO readiness check."""
        return {
            "sso_enabled": self.sso_enabled,
            "oidc_enabled": bool(getattr(self._settings, "oidc_enabled", False) if self._settings else False),
            "saml_enabled": bool(getattr(self._settings, "saml_enabled", False) if self._settings else False),
            "real_oidc_login": False,
            "real_saml_login": False,
            "token_storage": False,
            "safe_mode": True,
        }

    # ── Step 20 — Real SSO Flow ──

    def create_sso_session(self, **kwargs) -> Any | None:
        from src.open_platform.sandbox_v2.models import SandboxV2SSOSession
        session = SandboxV2SSOSession(**kwargs)
        if self._store:
            try: self._store.create_sso_session(session); return session
            except Exception as e: logger.warning(f"Failed to create SSO session: {e}")
        return session

    def get_sso_session(self, session_id: str) -> Any | None:
        if not self._store: return None
        try: return self._store.get_sso_session(session_id)
        except Exception: return None

    def list_sso_sessions(self, organization_id: str = "", workspace_id: str = "",
                          status: str = "", limit: int = 50) -> list[Any]:
        if not self._store: return []
        try:
            return self._store.list_sso_sessions(
                organization_id=organization_id or None, workspace_id=workspace_id or None,
                status=status or None, limit=min(max(int(limit or 50), 1), 100),
            )
        except Exception: return []

    def revoke_sso_session(self, session_id: str, reason: str = "") -> dict[str, Any]:
        if not self._store: return {"revoked": False, "reason": "No store"}
        try:
            session = self._store.revoke_sso_session(session_id, reason)
            if session:
                self._audit_iam_event(
                    event_type=SandboxV2AuditEventType.RESOURCE_UPDATED,
                    decision="allow", reason=f"SSO session revoked: {reason or 'manual'}",
                    organization_id=getattr(session, 'organization_id', ''),
                    workspace_id=getattr(session, 'workspace_id', ''),
                    resource_type="iam_sso_session", resource_id=session_id,
                )
            return {"revoked": session is not None, "session_id": session_id}
        except Exception as e:
            return {"revoked": False, "reason": str(e)}

    def get_real_sso_readiness(self) -> dict[str, Any]:
        s = self._settings
        # Step 21 — signature_validation now driven by oidc_signature_validation_enabled
        sig_enabled = bool(getattr(s, 'oidc_signature_validation_enabled', False))
        return {
            "real_oidc_login_enabled": bool(getattr(s, 'real_oidc_login_enabled', False)),
            "real_saml_login_enabled": bool(getattr(s, 'real_saml_login_enabled', False)),
            "oidc_authorization_code_flow": True,
            "oidc_state_nonce_pkce": True,
            "oidc_token_exchange_enabled": bool(getattr(s, 'oidc_token_exchange_enabled', False)),
            "oidc_signature_validation": sig_enabled,
            "oidc_claim_validation": True,
            "saml_sp_initiated_flow": True,
            "saml_acs_endpoint": True,
            "saml_signature_validation": False,
            "saml_xxe_protection": bool(getattr(s, 'saml_disable_xxe', True)),
            "sso_session_binding": bool(getattr(s, 'sso_session_enabled', False)),
            "token_storage": False,
            "sso_safe_mode": True,
        }

    # ═══════════════════════════════════════════
    # Step 21 — Production-Grade OIDC Identity Validation
    # ═══════════════════════════════════════════

    def get_oidc_validation_readiness(self) -> dict[str, Any]:
        """Step 21 OIDC Validation Readiness — Runtime Admin 直接消费。

        所有子能力默认 disabled。signature_validation 仅在
        ``oidc_signature_validation_enabled=true`` 后才显示 enabled。
        """
        # Lazy import to avoid hard dep at module load time
        try:
            from src.open_platform.sandbox_v2.oidc_step21_service import (
                SandboxV2OIDCStep21Service,
            )
        except ImportError as e:
            logger.warning("step21_service_unavailable", extra={"error": str(e)})
            return {
                "step": "step21_oidc_production_validation",
                "available": False,
                "reason": f"step21 service unavailable: {e}",
                "fail_closed": True,
            }
        svc = SandboxV2OIDCStep21Service(settings=self._settings)
        return svc.get_oidc_validation_readiness()

    # ═══════════════════════════════════════════
    # Step 22 — Production-Grade SAML Validation Readiness
    # ═══════════════════════════════════════════

    def get_saml_validation_readiness(self) -> dict[str, Any]:
        """Step 22 SAML Validation Readiness — Runtime Admin 直接消费。

        所有子能力默认 disabled。每项包含 enabled / ready / status / reason。
        """
        try:
            from src.open_platform.sandbox_v2.saml_step22_service import (
                SandboxV2SAMLStep22Service,
            )
        except ImportError as e:
            logger.warning("step22_service_unavailable", extra={"error": str(e)})
            return {
                "step": "step22_saml_production_validation",
                "available": False,
                "reason": f"step22 service unavailable: {e}",
                "fail_closed": True,
            }
        svc = SandboxV2SAMLStep22Service(
            settings=self._settings, store=self._store,
            iam_service=self, audit_service=self._audit,
        )
        return svc.get_saml_validation_readiness()
