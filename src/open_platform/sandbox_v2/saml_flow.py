"""Sandbox v2 SAML Flow — Step 20.

SAML SP-Initiated Flow 闭环实现。
默认 disabled。禁止 XXE。拒绝 unsigned assertion。不存原始 SAMLResponse。
"""
from __future__ import annotations
import hashlib
import logging
import secrets
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

from src.open_platform.sandbox_v2.models import (
    SandboxV2SSOState, SandboxV2SAMLAuthRequest, SandboxV2SAMLACSResult,
    SandboxV2SAMLValidationStatus, SandboxV2SSOFlowType, SandboxV2SSOFlowStatus,
    SandboxV2SSOSessionStatus, SandboxV2PrincipalType,
)

logger = logging.getLogger(__name__)

_XXE_PATTERNS = re.compile(r'<!ENTITY|SYSTEM\s+"|SYSTEM\s+\'|<!DOCTYPE.*\[', re.IGNORECASE)
_SENSITIVE_XML = re.compile(r'(<[^>]*?(?:password|secret|token|credential|key)>[^<]*?</)', re.IGNORECASE)


class SandboxV2SAMLFlowService:
    """SAML SP-Initiated Flow 服务。"""

    def __init__(self, store: Any = None, iam_service: Any = None, audit_service: Any = None, settings: Any = None):
        self._store = store
        self._iam = iam_service
        self._audit = audit_service
        self._settings = settings

    def _cfg(self, key: str, default: Any = None) -> Any:
        return getattr(self._settings, key, default) if self._settings else default

    @property
    def enabled(self) -> bool:
        return bool(self._cfg("real_saml_login_enabled", False))

    # ── AuthnRequest ──

    def create_authn_request(self, provider_config: Any, organization_id: str = "",
                             workspace_id: str = "", principal_hint: str = "") -> dict[str, Any]:
        """Create SAML AuthnRequest. Default disabled."""
        if not self.enabled or not provider_config:
            return {"status": "disabled", "reason": "SAML login not enabled"}

        relay_state = secrets.token_urlsafe(32)
        relay_hash = hashlib.sha256(relay_state.encode()).hexdigest()
        ttl = self._cfg("sso_state_ttl_seconds", 300)

        state_obj = SandboxV2SSOState(
            flow_type=SandboxV2SSOFlowType.SAML_SP_INITIATED,
            state_hash=relay_hash,
            code_challenge="",  # SAML doesn't use PKCE
            redirect_uri=self._cfg("saml_acs_url", ""),
            provider_config_id=getattr(provider_config, 'provider_config_id', ''),
            organization_id=organization_id, workspace_id=workspace_id,
            principal_hint=principal_hint,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
            status=SandboxV2SSOFlowStatus.CREATED,
        )
        if self._store:
            try: self._store.create_sso_state(state_obj)
            except Exception: pass

        # Build authn request (template XML, redacted)
        sso_url = getattr(provider_config, 'saml_entity_id', '') or "https://idp.example.com/sso"
        acs_url = self._cfg("saml_acs_url", "")
        saml_request = self._build_saml_authn_request_xml(sso_url, acs_url, relay_state)
        saml_request_redacted = _redact_xml_sensitive(saml_request)

        auth_req = SandboxV2SAMLAuthRequest(
            provider_config_id=state_obj.provider_config_id,
            sso_url=sso_url, relay_state_id=state_obj.sso_state_id,
            saml_request_redacted=saml_request_redacted[:500],
            acs_url=acs_url,
        )
        if self._store:
            try: self._store.create_saml_auth_request(auth_req)
            except Exception: pass

        redirect_url = f"{sso_url}?SAMLRequest={urllib.parse.quote(saml_request_redacted[:200])}&RelayState={relay_state}"

        return {
            "status": "authn_request_generated",
            "redirect_url": redirect_url,
            "sso_url": sso_url,
            "relay_state_id": state_obj.sso_state_id,
            "sso_state_id": state_obj.sso_state_id,
        }

    def _build_saml_authn_request_xml(self, sso_url: str, acs_url: str, relay_state: str) -> str:
        """Build minimal SAML AuthnRequest XML. No secrets in output."""
        request_id = f"_sbx_{secrets.token_hex(16)}"
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
            f'ID="{request_id}" Version="2.0" IssueInstant="{datetime.now(timezone.utc).isoformat()}" '
            f'Destination="{_xml_escape(sso_url)}" '
            f'AssertionConsumerServiceURL="{_xml_escape(acs_url)}">'
            f'<saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">sandbox-v2</saml:Issuer>'
            f'</samlp:AuthnRequest>'
        )

    # ── ACS ──

    def handle_acs(self, saml_response: str = "", relay_state: str = "",
                   provider_config_id: str = "", organization_id: str = "",
                   workspace_id: str = "") -> dict[str, Any]:
        """Handle SAML ACS callback. Default rejects unsigned/untrusted."""
        if not self.enabled:
            return {"status": SandboxV2SSOFlowStatus.DISABLED, "reason": "SAML login disabled", "allowed": False}

        # Size check
        max_bytes = self._cfg("saml_max_response_bytes", 131072)
        if len(saml_response or "") > max_bytes:
            self._write_audit("iam_saml_response_overlimit", "deny",
                              f"SAMLResponse {len(saml_response)} bytes exceeds limit {max_bytes}",
                              organization_id, workspace_id)
            return {"status": SandboxV2SSOFlowStatus.REJECTED, "reason": f"SAMLResponse exceeds {max_bytes} bytes", "allowed": False}

        # XXE check
        if self._cfg("saml_disable_xxe", True) and _XXE_PATTERNS.search(saml_response or ""):
            self._write_audit("iam_saml_xxe_blocked", "deny",
                              "XXE/DTD pattern detected in SAMLResponse", organization_id, workspace_id)
            return {"status": SandboxV2SSOFlowStatus.REJECTED, "reason": "SAMLResponse contains forbidden XXE/DTD patterns", "allowed": False}

        # Relay state validation
        if not relay_state:
            return {"status": SandboxV2SSOFlowStatus.REJECTED, "reason": "Missing RelayState", "allowed": False}

        relay_hash = hashlib.sha256(relay_state.encode()).hexdigest()
        relay_obj = self._consume_relay_state(relay_hash)
        if not relay_obj:
            self._write_audit("iam_saml_relay_state_invalid", "deny",
                              "RelayState not found or already consumed", organization_id, workspace_id)
            return {"status": SandboxV2SSOFlowStatus.REJECTED, "reason": "Invalid or consumed RelayState", "allowed": False}

        if datetime.now(timezone.utc) > relay_obj.expires_at:
            return {"status": SandboxV2SSOFlowStatus.EXPIRED, "reason": "RelayState expired", "allowed": False}

        org = relay_obj.organization_id or organization_id
        ws = relay_obj.workspace_id or workspace_id

        # Signature check
        if self._cfg("saml_require_signed_response", True):
            # In skeleton mode, we can't verify real XML signatures.
            # We check for a Signature element as a heuristic.
            has_sig = "<Signature" in (saml_response or "") or "<ds:Signature" in (saml_response or "")
            if not has_sig and not self._cfg("saml_allow_unsigned_dev_assertion", False):
                return {"status": SandboxV2SSOFlowStatus.REJECTED,
                        "reason": "SAML response is not signed (real signing verification unavailable)", "allowed": False}

        # Extract claims (redacted)
        claims = self._extract_claims_redacted(saml_response or "")

        # Map via IAM
        provider_config = self._get_provider_config(provider_config_id or relay_obj.provider_config_id)
        mapping_result = self._map_claims(claims, provider_config, org, ws)
        decision = mapping_result.get("mapping_decision", {})
        sec_ctx = mapping_result.get("security_context")

        acs_result = SandboxV2SAMLACSResult(
            provider_config_id=provider_config_id or relay_obj.provider_config_id,
            relay_state_id=relay_obj.sso_state_id,
            validation_status="valid" if mapping_result.get("allowed") else "rejected",
            mapping_decision=decision, security_context=sec_ctx or {},
            session_id="", audit_event_id="",
        )

        if self._cfg("sso_session_enabled", False) and mapping_result.get("allowed") and self._store:
            from src.open_platform.sandbox_v2.models import SandboxV2SSOSession
            ttl = self._cfg("sso_session_ttl_seconds", 3600)
            session = SandboxV2SSOSession(
                principal_id=sec_ctx.get("principal_id", "") if sec_ctx else "",
                principal_type=sec_ctx.get("principal_type", SandboxV2PrincipalType.USER) if sec_ctx else SandboxV2PrincipalType.USER,
                provider_config_id=relay_obj.provider_config_id,
                organization_id=org, workspace_id=ws,
                roles=sec_ctx.get("roles", []) if sec_ctx else [],
                scopes=sec_ctx.get("scopes", []) if sec_ctx else [],
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
                status=SandboxV2SSOSessionStatus.ACTIVE,
            )
            try:
                self._store.create_sso_session(session)
                acs_result.session_id = session.session_id
            except Exception: pass

        audit_id = self._write_audit(
            "iam_saml_acs_processed",
            "allow" if mapping_result.get("allowed") else "deny",
            f"ACS processed: {mapping_result.get('reason', '')}", org, ws,
        )
        acs_result.audit_event_id = audit_id

        if self._store:
            try: self._store.create_saml_acs_result(acs_result)
            except Exception: pass

        return {
            "status": "mapped" if mapping_result.get("allowed") else "rejected",
            "allowed": mapping_result.get("allowed", False),
            "reason": decision.get("reason", ""),
            "acs_result_id": acs_result.acs_result_id,
            "session_id": acs_result.session_id,
            "security_context": sec_ctx,
        }

    def _consume_relay_state(self, state_hash: str) -> SandboxV2SSOState | None:
        if not self._store:
            return SandboxV2SSOState(state_hash=state_hash, status="created",
                                     expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        state_obj = self._store.get_sso_state_by_hash(state_hash)
        if not state_obj or state_obj.status != "created":
            return None
        if hasattr(state_obj, 'consumed_at') and state_obj.consumed_at:
            return None
        self._store.consume_sso_state(state_obj.sso_state_id)
        return state_obj

    def _extract_claims_redacted(self, saml_response: str) -> dict[str, Any]:
        """Extract and redact claims from SAMLResponse. Never returns raw XML."""
        import re as re_mod
        claims: dict[str, Any] = {"source": "saml_response"}
        # Extract NameID
        name_id_match = re_mod.search(r'<saml:NameID[^>]*>(.*?)</saml:NameID>', saml_response, re_mod.DOTALL)
        if name_id_match:
            claims["sub"] = name_id_match.group(1).strip()[:100]
        # Extract AttributeValue for email
        email_match = re_mod.search(r'Attribute Name="email"[^>]*[^>]*<saml:AttributeValue[^>]*>(.*?)</saml:AttributeValue>',
                                    saml_response, re_mod.DOTALL | re_mod.IGNORECASE)
        if email_match:
            claims["email"] = email_match.group(1).strip()[:200]
        # Extract groups
        groups: list[str] = []
        for m in re_mod.finditer(r'Attribute Name="(?:group|groups|role|roles)"[^>]*[^>]*<saml:AttributeValue[^>]*>(.*?)</saml:AttributeValue>',
                                  saml_response, re_mod.DOTALL | re_mod.IGNORECASE):
            groups.append(m.group(1).strip()[:100])
        if groups:
            claims["groups"] = groups
        return claims

    def _map_claims(self, claims: dict[str, Any], provider_config: Any, org: str, ws: str) -> dict[str, Any]:
        if self._iam and hasattr(self._iam, 'simulate_sso_login'):
            return self._iam.simulate_sso_login(
                claims, getattr(provider_config, 'provider_config_id', ''),
                organization_id=org, workspace_id=ws,
            )
        from src.open_platform.sandbox_v2.iam_mapping import SandboxV2IAMClaimMapper
        mapper = SandboxV2IAMClaimMapper()
        decision, sec_ctx = mapper.map_claims_to_security_context(
            claims, provider_config, mappings=None, organization_id=org, workspace_id=ws,
        )
        return {"allowed": decision.allowed, "mapping_decision": decision.to_dict(),
                "security_context": sec_ctx.to_dict() if sec_ctx else None,
                "login_status": "mapped" if decision.allowed else "rejected", "reason": decision.reason}

    def _get_provider_config(self, pid: str) -> Any:
        if self._iam and hasattr(self._iam, 'get_provider_config'):
            return self._iam.get_provider_config(pid)
        if self._store:
            try: return self._store.get_iam_provider_config(pid)
            except Exception: pass
        return None

    def _write_audit(self, et: str, dec: str, reason: str, org: str = "", ws: str = "") -> str:
        if not self._audit: return ""
        try:
            evt = self._audit.create_audit_event(event_type=et, decision=dec, reason=reason,
                                                  organization_id=org, workspace_id=ws,
                                                  resource_type="iam_saml", action=et)
            return evt.audit_event_id if evt else ""
        except Exception: return ""

    def get_saml_readiness(self) -> dict[str, Any]:
        return {
            "real_saml_login_enabled": self.enabled,
            "saml_sp_initiated_flow": True,
            "saml_acs_endpoint": True,
            "saml_signature_validation": False,
            "saml_xxe_protection": self._cfg("saml_disable_xxe", True),
            "token_storage": False,
            "sso_safe_mode": True,
        }


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")


def _redact_xml_sensitive(xml: str) -> str:
    return _SENSITIVE_XML.sub("<redacted/>", xml)
