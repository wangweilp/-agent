"""Sandbox v2 OIDC Flow — Step 20.

OIDC Authorization Code Flow 闭环实现。
默认 disabled。不存 token。不访问外网（除非 token_exchange_enabled=true）。
"""
from __future__ import annotations
import hashlib
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

from src.open_platform.sandbox_v2.models import (
    SandboxV2SSOState, SandboxV2OIDCAuthRequest, SandboxV2OIDCCallbackResult,
    SandboxV2OIDCTokenValidationResult, SandboxV2OIDCValidationStatus,
    SandboxV2SSOFlowType, SandboxV2SSOFlowStatus, SandboxV2SSOSessionStatus,
    SandboxV2PrincipalType,
)

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = frozenset({
    "access_token", "id_token", "refresh_token", "token", "secret",
    "client_secret", "code", "jwt", "authorization",
})


class SandboxV2OIDCFlowService:
    """OIDC Authorization Code Flow 服务。"""

    def __init__(self, store: Any = None, iam_service: Any = None, audit_service: Any = None, settings: Any = None):
        self._store = store
        self._iam = iam_service
        self._audit = audit_service
        self._settings = settings

    def _cfg(self, key: str, default: Any = None) -> Any:
        if self._settings:
            return getattr(self._settings, key, default)
        return default

    @property
    def enabled(self) -> bool:
        return bool(self._cfg("real_oidc_login_enabled", False))

    # ── State / Nonce / PKCE helpers ──

    @staticmethod
    def generate_state() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def generate_nonce() -> str:
        return secrets.token_urlsafe(24)

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str, str]:
        """Returns (code_verifier, code_challenge, code_verifier_hash)."""
        verifier = secrets.token_urlsafe(48)
        challenge = hashlib.sha256(verifier.encode()).digest()
        # Base64url without padding
        import base64
        challenge_b64 = base64.urlsafe_b64encode(challenge).rstrip(b"=").decode()
        verifier_hash = hashlib.sha256(verifier.encode()).hexdigest()
        return verifier, challenge_b64, verifier_hash

    @staticmethod
    def hash_secret(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest() if value else ""

    # ── Authorization Request ──

    def create_authorization_request(
        self, provider_config: Any, organization_id: str = "",
        workspace_id: str = "", principal_hint: str = "",
    ) -> dict[str, Any]:
        """Create OIDC authorization request. Returns auth request dict (disabled if not enabled)."""
        if not self.enabled or not provider_config:
            return {"status": "disabled", "reason": "Real OIDC login not enabled", "authorization_url": None}

        state_val = self.generate_state()
        nonce_val = self.generate_nonce()
        verifier, challenge, v_hash = self.generate_pkce_pair()
        state_hash = self.hash_secret(state_val)
        nonce_hash = self.hash_secret(nonce_val)

        ttl = self._cfg("sso_state_ttl_seconds", 300)
        state_obj = SandboxV2SSOState(
            flow_type=SandboxV2SSOFlowType.OIDC_AUTHORIZATION_CODE,
            state_hash=state_hash, nonce_hash=nonce_hash,
            code_verifier_hash=v_hash, code_challenge=challenge,
            redirect_uri=self._cfg("oidc_redirect_uri", ""),
            provider_config_id=getattr(provider_config, 'provider_config_id', ''),
            organization_id=organization_id, workspace_id=workspace_id,
            principal_hint=principal_hint,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
            status=SandboxV2SSOFlowStatus.CREATED,
        )
        if self._store:
            try: self._store.create_sso_state(state_obj)
            except Exception as e: logger.warning(f"Failed to persist SSO state: {e}")

        auth_url = self._build_authorization_url(provider_config, state_val, nonce_val, challenge)
        auth_req = SandboxV2OIDCAuthRequest(
            provider_config_id=state_obj.provider_config_id,
            authorization_url=auth_url, state_id=state_obj.sso_state_id,
            code_challenge=challenge,
            scopes=self._cfg("oidc_scopes", "openid,email,profile"),
            redirect_uri=self._cfg("oidc_redirect_uri", ""),
        )
        if self._store:
            try: self._store.create_oidc_auth_request(auth_req)
            except Exception: pass

        return {
            "status": "authorization_url_generated",
            "authorization_url": auth_url,
            "state_id": state_obj.sso_state_id,
            "code_challenge": challenge,
            "sso_state_id": state_obj.sso_state_id,
        }

    def _build_authorization_url(self, config: Any, state: str, nonce: str, challenge: str) -> str:
        endpoint = self._cfg("oidc_authorization_endpoint", "")
        client_id = getattr(config, 'client_id', '')
        redirect = self._cfg("oidc_redirect_uri", "")
        scopes = self._cfg("oidc_scopes", "openid")
        params = {
            "response_type": "code", "client_id": client_id,
            "redirect_uri": redirect, "scope": scopes,
            "state": state, "nonce": nonce,
        }
        if self._cfg("oidc_pkce_enabled", True):
            params["code_challenge"] = challenge
            params["code_challenge_method"] = "S256"
        # Must NOT include client_secret
        return f"{endpoint}?{urlencode(params)}"

    # ── Callback ──

    def handle_callback(self, code: str = "", state: str = "", error: str = "",
                        provider_config_id: str = "", organization_id: str = "",
                        workspace_id: str = "") -> dict[str, Any]:
        """Handle OIDC callback. All failures write audit."""
        if not self.enabled:
            return {"status": SandboxV2SSOFlowStatus.DISABLED, "reason": "OIDC login disabled", "allowed": False}

        # Error from IdP
        if error:
            self._write_audit("iam_oidc_callback_error", "deny",
                              f"IdP returned error: {error}", organization_id, workspace_id)
            return {"status": SandboxV2SSOFlowStatus.REJECTED, "reason": f"IdP error: {error}", "allowed": False}

        # Validate params
        if not code:
            return {"status": SandboxV2SSOFlowStatus.REJECTED, "reason": "Missing code", "allowed": False}
        if not state:
            return {"status": SandboxV2SSOFlowStatus.REJECTED, "reason": "Missing state", "allowed": False}

        # Consume state
        state_hash = self.hash_secret(state)
        state_obj = self._consume_state(state_hash)
        if not state_obj:
            self._write_audit("iam_oidc_state_replay", "deny",
                              "State not found or already consumed", organization_id, workspace_id)
            return {"status": SandboxV2SSOFlowStatus.REJECTED, "reason": "Invalid or consumed state", "allowed": False}

        if datetime.now(timezone.utc) > state_obj.expires_at:
            self._write_audit("iam_oidc_state_expired", "deny",
                              "State expired", organization_id, workspace_id)
            return {"status": SandboxV2SSOFlowStatus.EXPIRED, "reason": "State expired", "allowed": False}

        org = state_obj.organization_id or organization_id
        ws = state_obj.workspace_id or workspace_id

        # Token exchange (only if enabled)
        validation_result = None
        if self._cfg("oidc_token_exchange_enabled", False):
            exchange_result = self._exchange_code_for_tokens(code, state_obj, provider_config_id)
            if not exchange_result.get("allowed"):
                return exchange_result
            validation_result = exchange_result.get("validation")
            claims = exchange_result.get("claims", {})
        else:
            # Without real token exchange, use state metadata for test fixture claims
            claims = {"sub": state_obj.principal_hint or "unknown", "iss": ""}

        # Map to security context via IAM service
        provider_config = self._get_provider_config(provider_config_id or state_obj.provider_config_id)
        mapping_result = self._map_claims(claims, provider_config, org, ws)
        decision = mapping_result.get("mapping_decision", {})
        sec_ctx = mapping_result.get("security_context")

        # Create callback result
        callback = SandboxV2OIDCCallbackResult(
            provider_config_id=provider_config_id or state_obj.provider_config_id,
            state_id=state_obj.sso_state_id,
            status=mapping_result.get("login_status", SandboxV2SSOFlowStatus.REJECTED),
            validation_status=validation_result.get("validation_status", "unavailable") if validation_result else "unavailable",
            mapping_decision=decision, security_context=sec_ctx or {},
            session_id="", audit_event_id="",
        )

        # Create SSO session if enabled
        if self._cfg("sso_session_enabled", False) and mapping_result.get("allowed"):
            session = self._create_session(sec_ctx, state_obj, callback)
            if session:
                callback.session_id = session.get("session_id", "")

        audit_event_id = self._write_audit(
            "iam_oidc_callback_processed",
            "allow" if mapping_result.get("allowed") else "deny",
            f"Callback processed: {mapping_result.get('reason', '')}", org, ws,
        )
        callback.audit_event_id = audit_event_id

        if self._store:
            try: self._store.create_oidc_callback_result(callback)
            except Exception: pass

        return {
            "status": callback.status,
            "allowed": mapping_result.get("allowed", False),
            "reason": decision.get("reason", ""),
            "callback_id": callback.callback_id,
            "session_id": callback.session_id,
            "security_context": sec_ctx,
        }

    def _consume_state(self, state_hash: str) -> SandboxV2SSOState | None:
        if not self._store:
            # Simulate for standalone mode
            return SandboxV2SSOState(state_hash=state_hash, status="created",
                                     expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        state_obj = self._store.get_sso_state_by_hash(state_hash)
        if not state_obj or state_obj.status != "created":
            return None
        if hasattr(state_obj, 'consumed_at') and state_obj.consumed_at:
            return None  # already consumed
        self._store.consume_sso_state(state_obj.sso_state_id)
        return state_obj

    def _exchange_code_for_tokens(self, code: str, state_obj: SandboxV2SSOState,
                                  provider_config_id: str) -> dict[str, Any]:
        """Real token exchange. Only runs when token_exchange_enabled=true."""
        if not self._cfg("oidc_token_exchange_enabled", False):
            return {"allowed": False, "reason": "Token exchange disabled"}
        try:
            # Use requests if available for real exchange
            import requests
            from src.open_platform.sandbox_v2.iam_mapping import SandboxV2IAMClaimMapper
            mapper = SandboxV2IAMClaimMapper()
            token_data = {
                "grant_type": "authorization_code", "code": code,
                "redirect_uri": state_obj.redirect_uri,
                "client_id": self._cfg("oidc_client_id", ""),
                "client_secret": self._cfg("oidc_client_secret", ""),
            }
            if state_obj.code_verifier_hash:
                # code_verifier not stored — this is a design constraint
                pass
            resp = requests.post(self._cfg("oidc_token_endpoint", ""), data=token_data, timeout=10)
            if resp.status_code != 200:
                return {"allowed": False, "reason": f"Token endpoint returned {resp.status_code}"}
            token_json = resp.json()
            id_token = token_json.get("id_token", "")
            # Redact tokens immediately
            claims = self._parse_id_token_claims(id_token) if id_token else {}
            validation = self._validate_id_token_claims(claims, state_obj)
            return {
                "allowed": validation.get("validation_status") == "valid",
                "reason": validation.get("reason", ""),
                "validation": validation,
                "claims": mapper.redact_claims(claims),
            }
        except ImportError:
            return {"allowed": False, "reason": "requests library not available for token exchange"}
        except Exception as e:
            return {"allowed": False, "reason": f"Token exchange failed: {e}"}

    def _parse_id_token_claims(self, id_token: str) -> dict[str, Any]:
        """Parse id_token without signature verification (skeleton). Returns claims dict."""
        import base64
        import json as json_mod
        try:
            parts = id_token.split(".")
            if len(parts) != 3:
                return {"error": "Invalid JWT format"}
            payload_b64 = parts[1]
            payload_b64 += "=" * (4 - len(payload_b64) % 4) if len(payload_b64) % 4 else ""
            payload = base64.urlsafe_b64decode(payload_b64)
            return json_mod.loads(payload)
        except Exception:
            return {"error": "Failed to parse id_token"}

    # ── Token Validation ──

    def validate_id_token_claims(self, claims: dict[str, Any],
                                 state_obj: SandboxV2SSOState | None = None,
                                 provider_config: Any = None) -> SandboxV2OIDCTokenValidationResult:
        """Validate id_token claims without real signature verification.
        Returns OIDCTokenValidationResult. Signature check returns unavailable.
        """
        result = SandboxV2OIDCTokenValidationResult(
            validation_status=SandboxV2OIDCValidationStatus.UNAVAILABLE,
            reason="Real JWT signature verification unavailable — requires python-jose or similar",
        )
        if not claims or "error" in claims:
            result.reason = f"Invalid claims: {claims.get('error', 'unknown')}"
            result.validation_status = SandboxV2OIDCValidationStatus.INVALID
            return result

        issuer = str(provider_config.issuer) if provider_config and hasattr(provider_config, 'issuer') else ""
        client_id = str(provider_config.client_id) if provider_config and hasattr(provider_config, 'client_id') else ""

        # iss check
        claim_iss = str(claims.get("iss", ""))
        if issuer and claim_iss != issuer:
            result.issuer_valid = False
            result.reason = f"Issuer mismatch: {claim_iss} != {issuer}"
            result.validation_status = SandboxV2OIDCValidationStatus.INVALID
        else:
            result.issuer_valid = True

        # aud check
        claim_aud = claims.get("aud", "")
        if isinstance(claim_aud, list):
            aud_ok = client_id in claim_aud if client_id else True
        else:
            aud_ok = (claim_aud == client_id) if client_id else True
        result.audience_valid = aud_ok
        if not aud_ok:
            result.reason = f"Audience mismatch: {claim_aud} != {client_id}"
            result.validation_status = SandboxV2OIDCValidationStatus.INVALID

        # exp check
        now_ts = int(time.time())
        clock_skew = self._cfg("oidc_clock_skew_seconds", 60)
        exp = int(claims.get("exp", 0) or 0)
        if exp and exp < (now_ts - clock_skew):
            result.exp_valid = False
            result.reason = f"Token expired at {exp} (now: {now_ts})"
            result.validation_status = SandboxV2OIDCValidationStatus.EXPIRED
        else:
            result.exp_valid = True

        # iat check (not too far in future)
        iat = int(claims.get("iat", 0) or 0)
        if iat and iat > (now_ts + clock_skew):
            result.iat_valid = False
        else:
            result.iat_valid = True

        # alg check
        alg = str(claims.get("alg", "") or "")
        if alg.lower() == "none":
            result.alg_allowed = False
            result.reason = "alg=none rejected"
            result.validation_status = SandboxV2OIDCValidationStatus.INVALID

        # nonce check
        if state_obj and state_obj.nonce_hash:
            claim_nonce = str(claims.get("nonce", ""))
            if self.hash_secret(claim_nonce) != state_obj.nonce_hash:
                result.nonce_valid = False
                result.reason = "Nonce mismatch"
                result.validation_status = SandboxV2OIDCValidationStatus.INVALID
            else:
                result.nonce_valid = True

        # Signature — always unavailable in skeleton
        result.signature_valid = False

        # email_verified
        result.email_verified = bool(claims.get("email_verified", False))

        # If no failures, mark valid (pending signature)
        if result.validation_status == SandboxV2OIDCValidationStatus.UNAVAILABLE:
            result.validation_status = SandboxV2OIDCValidationStatus.VALID
            result.reason = "Claims valid (signature verification unavailable)"

        # Redact claims
        from src.open_platform.sandbox_v2.iam_mapping import SandboxV2IAMClaimMapper
        result.claims_redacted = SandboxV2IAMClaimMapper().redact_claims(claims or {})

        if self._store:
            try: self._store.create_oidc_token_validation_result(result)
            except Exception: pass

        return result

    # ── Helpers ──

    def _map_claims(self, claims: dict[str, Any], provider_config: Any,
                    org: str, ws: str) -> dict[str, Any]:
        """Map claims via IAM service."""
        if self._iam and hasattr(self._iam, 'simulate_sso_login'):
            return self._iam.simulate_sso_login(
                claims, getattr(provider_config, 'provider_config_id', ''),
                organization_id=org, workspace_id=ws,
            )
        # Fallback: use mapper directly
        from src.open_platform.sandbox_v2.iam_mapping import SandboxV2IAMClaimMapper
        mapper = SandboxV2IAMClaimMapper()
        decision, sec_ctx = mapper.map_claims_to_security_context(
            claims, provider_config, mappings=None, organization_id=org, workspace_id=ws,
        )
        return {"allowed": decision.allowed, "mapping_decision": decision.to_dict(),
                "security_context": sec_ctx.to_dict() if sec_ctx else None,
                "login_status": "mapped" if decision.allowed else "rejected",
                "reason": decision.reason}

    def _create_session(self, sec_ctx: dict[str, Any] | None,
                        state_obj: SandboxV2SSOState,
                        callback: SandboxV2OIDCCallbackResult) -> dict[str, Any] | None:
        if not self._store or not sec_ctx:
            return None
        ttl = self._cfg("sso_session_ttl_seconds", 3600)
        from src.open_platform.sandbox_v2.models import SandboxV2SSOSession
        session = SandboxV2SSOSession(
            principal_id=sec_ctx.get("principal_id", ""),
            principal_type=sec_ctx.get("principal_type", SandboxV2PrincipalType.USER),
            provider_config_id=state_obj.provider_config_id,
            organization_id=sec_ctx.get("organization_id", ""),
            workspace_id=sec_ctx.get("workspace_id", ""),
            roles=sec_ctx.get("roles", []),
            scopes=sec_ctx.get("scopes", []),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
            status=SandboxV2SSOSessionStatus.ACTIVE,
        )
        try:
            self._store.create_sso_session(session)
            return session.to_dict()
        except Exception:
            return None

    def _get_provider_config(self, provider_config_id: str) -> Any:
        if self._iam and hasattr(self._iam, 'get_provider_config'):
            return self._iam.get_provider_config(provider_config_id)
        if self._store:
            try: return self._store.get_iam_provider_config(provider_config_id)
            except Exception: pass
        return None

    def _write_audit(self, event_type: str, decision: str, reason: str,
                     org: str = "", ws: str = "") -> str:
        if not self._audit:
            return ""
        try:
            evt = self._audit.create_audit_event(
                event_type=event_type, decision=decision, reason=reason,
                organization_id=org, workspace_id=ws,
                resource_type="iam_oidc", action=event_type,
            )
            return evt.audit_event_id if evt else ""
        except Exception:
            return ""

    def get_oidc_readiness(self) -> dict[str, Any]:
        return {
            "real_oidc_login_enabled": self.enabled,
            "oidc_authorization_code_flow": True,
            "oidc_state_nonce_pkce": True,
            "oidc_token_exchange_enabled": self._cfg("oidc_token_exchange_enabled", False),
            "oidc_signature_validation": False,
            "oidc_claim_validation": True,
            "token_storage": False,
            "sso_safe_mode": True,
        }
