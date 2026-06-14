"""Red-Team Real SSO tests (Step 20)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.oidc_flow import SandboxV2OIDCFlowService
from src.open_platform.sandbox_v2.saml_flow import SandboxV2SAMLFlowService
from src.open_platform.sandbox_v2.models import SandboxV2SSOFlowStatus, SandboxV2SSOSession
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.config import Settings


class DummySettings:
    real_oidc_login_enabled = False; real_saml_login_enabled = False
    oidc_token_exchange_enabled = False; oidc_pkce_enabled = True
    oidc_require_nonce = True; oidc_require_state = True
    saml_require_signed_response = True; saml_allow_unsigned_dev_assertion = False
    saml_disable_xxe = True; saml_max_response_bytes = 131072
    sso_session_enabled = False; sso_state_ttl_seconds = 300
    sso_session_ttl_seconds = 3600


class TestOIDCRejections:
    def test_authorize_disabled_rejected(self):
        svc = SandboxV2OIDCFlowService(settings=DummySettings())
        r = svc.create_authorization_request(None)
        assert r["status"] == "disabled"

    def test_callback_missing_state_rejected(self):
        s = DummySettings(); s.real_oidc_login_enabled = True
        svc = SandboxV2OIDCFlowService(settings=s)
        r = svc.handle_callback(code="abc", state="")
        assert r["status"] == "rejected"

    def test_state_replay_rejected(self):
        store = SQLiteSandboxV2Store(Settings(), db_path=":memory:")
        s = DummySettings(); s.real_oidc_login_enabled = True
        svc = SandboxV2OIDCFlowService(store=store, settings=s)
        sv = svc.generate_state(); sh = svc.hash_secret(sv)
        from src.open_platform.sandbox_v2.models import SandboxV2SSOState
        from datetime import datetime, timedelta, timezone
        state = SandboxV2SSOState(state_hash=sh, status="created",
                                  expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        store.create_sso_state(state)
        r1 = svc.handle_callback(code="c", state=sv)
        r2 = svc.handle_callback(code="c", state=sv)  # replay
        assert not r2["allowed"]

    def test_alg_none_rejected(self):
        svc = SandboxV2OIDCFlowService(settings=DummySettings())
        result = svc.validate_id_token_claims({"alg": "none"})
        assert not result.alg_allowed

    def test_issuer_spoof_rejected(self):
        svc = SandboxV2OIDCFlowService(settings=DummySettings())
        from unittest.mock import MagicMock
        cfg = MagicMock(); cfg.issuer = "https://real.example.com"; cfg.client_id = ""
        result = svc.validate_id_token_claims({"iss": "https://evil.example.com"}, provider_config=cfg)
        assert not result.issuer_valid

    def test_expired_rejected(self):
        svc = SandboxV2OIDCFlowService(settings=DummySettings())
        result = svc.validate_id_token_claims({"iss": "x", "aud": "x", "exp": 1})
        assert not result.exp_valid

    def test_email_unverified_rejected(self):
        svc = SandboxV2OIDCFlowService(settings=DummySettings())
        result = svc.validate_id_token_claims({"iss": "x", "aud": "x", "email_verified": False})
        assert not result.email_verified

    def test_token_not_in_session(self):
        s = SandboxV2SSOSession(principal_id="u1", roles=["viewer"])
        d = s.to_dict()
        assert "access_token" not in str(d).lower()

    def test_token_storage_false(self):
        svc = SandboxV2OIDCFlowService(settings=DummySettings())
        r = svc.get_oidc_readiness()
        assert not r["token_storage"]


class TestSAMLRejections:
    def test_oversize_blocked(self):
        s = DummySettings(); s.real_saml_login_enabled = True
        svc = SandboxV2SAMLFlowService(settings=s)
        r = svc.handle_acs(saml_response="x" * 200000, relay_state="y")
        assert r["status"] == "rejected"

    def test_xxe_blocked(self):
        s = DummySettings(); s.real_saml_login_enabled = True
        svc = SandboxV2SAMLFlowService(settings=s)
        r = svc.handle_acs(saml_response='<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><foo/>', relay_state="x")
        assert r["status"] == "rejected"

    def test_unsigned_blocked(self):
        s = DummySettings(); s.real_saml_login_enabled = True
        s.saml_require_signed_response = True; s.saml_allow_unsigned_dev_assertion = False
        store = SQLiteSandboxV2Store(Settings(), db_path=":memory:")
        import hashlib
        relay_hash = hashlib.sha256(b"test-relay").hexdigest()
        from src.open_platform.sandbox_v2.models import SandboxV2SSOState
        from datetime import datetime, timedelta, timezone
        state = SandboxV2SSOState(state_hash=relay_hash, status="created",
                                  expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        store.create_sso_state(state)
        svc = SandboxV2SAMLFlowService(store=store, settings=s)
        r = svc.handle_acs(saml_response="<Response></Response>", relay_state="test-relay")
        assert r["status"] == "rejected"

    def test_missing_relay_state(self):
        s = DummySettings(); s.real_saml_login_enabled = True
        svc = SandboxV2SAMLFlowService(settings=s)
        r = svc.handle_acs(saml_response="<Response/>", relay_state="")
        assert r["status"] == "rejected"


class TestFailClosed:
    def test_malformed_callback_no_crash(self):
        s = DummySettings(); s.real_oidc_login_enabled = True
        svc = SandboxV2OIDCFlowService(settings=s)
        r = svc.handle_callback(code="x", state="y")
        assert r.get("status") is not None

    def test_oidc_disabled_default(self):
        svc = SandboxV2OIDCFlowService(settings=DummySettings())
        assert not svc.enabled

    def test_saml_disabled_default(self):
        svc = SandboxV2SAMLFlowService(settings=DummySettings())
        assert not svc.enabled

    def test_readiness_safe_mode(self):
        from src.open_platform.sandbox_v2.iam import SandboxV2IAMService
        from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService
        store = SQLiteSandboxV2Store(Settings(), db_path=":memory:")
        audit = SandboxV2SecurityAuditService(store=store)
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=DummySettings())
        r = svc.get_real_sso_readiness()
        assert r["sso_safe_mode"]
        assert not r["token_storage"]
