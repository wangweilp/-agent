"""OIDC Flow tests (Step 20)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.oidc_flow import SandboxV2OIDCFlowService
from src.open_platform.sandbox_v2.models import (
    SandboxV2SSOState, SandboxV2OIDCTokenValidationResult, SandboxV2OIDCValidationStatus,
    SandboxV2SSOFlowType, SandboxV2SSOFlowStatus,
)
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.config import Settings


class DummySettings:
    real_oidc_login_enabled = False
    real_saml_login_enabled = False
    oidc_authorization_endpoint = ""
    oidc_token_endpoint = ""
    oidc_redirect_uri = "http://localhost:8000/callback"
    oidc_scopes = "openid,email"
    oidc_pkce_enabled = True
    oidc_require_nonce = True
    oidc_require_state = True
    oidc_require_https = True
    oidc_allow_localhost_http = True
    oidc_clock_skew_seconds = 60
    oidc_token_exchange_enabled = False
    oidc_jwks_fetch_enabled = False
    oidc_discovery_fetch_enabled = False
    sso_session_enabled = False
    sso_session_ttl_seconds = 3600
    sso_state_ttl_seconds = 300
    iam_enabled = True


class TestOIDCDefaults:
    def test_default_disabled(self):
        svc = SandboxV2OIDCFlowService(settings=DummySettings())
        assert not svc.enabled

    def test_authorize_disabled(self):
        svc = SandboxV2OIDCFlowService(settings=DummySettings())
        r = svc.create_authorization_request(None)
        assert r["status"] == "disabled"

    def test_callback_disabled(self):
        svc = SandboxV2OIDCFlowService(settings=DummySettings())
        r = svc.handle_callback(code="x", state="y")
        assert r["status"] == SandboxV2SSOFlowStatus.DISABLED


class TestStateNoncePKCE:
    def test_state_generated(self):
        s = SandboxV2OIDCFlowService.generate_state()
        assert len(s) > 20

    def test_nonce_generated(self):
        n = SandboxV2OIDCFlowService.generate_nonce()
        assert len(n) > 10

    def test_pkce_pair(self):
        v, c, h = SandboxV2OIDCFlowService.generate_pkce_pair()
        assert len(v) > 30
        assert len(c) > 20
        assert len(h) == 64

    def test_hash_secret(self):
        h = SandboxV2OIDCFlowService.hash_secret("test-value")
        assert len(h) == 64
        assert SandboxV2OIDCFlowService.hash_secret("") == ""


class TestStateLifecycle:
    def test_state_created_and_consumed(self):
        store = SQLiteSandboxV2Store(Settings(), db_path=":memory:")
        s = DummySettings()
        s.real_oidc_login_enabled = True
        svc = SandboxV2OIDCFlowService(store=store, settings=s)
        state_val = svc.generate_state()
        state_hash = svc.hash_secret(state_val)
        state_obj = SandboxV2SSOState(
            flow_type=SandboxV2SSOFlowType.OIDC_AUTHORIZATION_CODE,
            state_hash=state_hash, status="created",
        )
        store.create_sso_state(state_obj)
        # Consume
        consumed = svc._consume_state(state_hash)
        assert consumed is not None
        # Replay blocked
        replay = svc._consume_state(state_hash)
        assert replay is None

    def test_state_expired(self):
        store = SQLiteSandboxV2Store(Settings(), db_path=":memory:")
        s = DummySettings()
        s.real_oidc_login_enabled = True
        svc = SandboxV2OIDCFlowService(store=store, settings=s)
        state_val = svc.generate_state()
        state_hash = svc.hash_secret(state_val)
        from datetime import datetime, timedelta, timezone
        state_obj = SandboxV2SSOState(
            flow_type=SandboxV2SSOFlowType.OIDC_AUTHORIZATION_CODE,
            state_hash=state_hash, status="created",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        store.create_sso_state(state_obj)
        result = svc.handle_callback(code="test", state=state_val)
        assert result["status"] in ("expired", "rejected")


class TestCallbackSecurity:
    def test_missing_code_rejected(self):
        s = DummySettings(); s.real_oidc_login_enabled = True
        store = SQLiteSandboxV2Store(Settings(), db_path=":memory:")
        svc = SandboxV2OIDCFlowService(store=store, settings=s)
        r = svc.handle_callback(code="", state="x")
        assert r["status"] == "rejected"

    def test_missing_state_rejected(self):
        s = DummySettings(); s.real_oidc_login_enabled = True
        store = SQLiteSandboxV2Store(Settings(), db_path=":memory:")
        svc = SandboxV2OIDCFlowService(store=store, settings=s)
        r = svc.handle_callback(code="abc", state="")
        assert r["status"] == "rejected"

    def test_error_from_idp(self):
        s = DummySettings(); s.real_oidc_login_enabled = True
        store = SQLiteSandboxV2Store(Settings(), db_path=":memory:")
        svc = SandboxV2OIDCFlowService(store=store, settings=s)
        r = svc.handle_callback(code="x", state="y", error="access_denied")
        assert r["status"] == "rejected"

    def test_authorization_url_no_secret(self):
        s = DummySettings()
        s.real_oidc_login_enabled = True
        s.oidc_authorization_endpoint = "https://idp.example.com/auth"
        svc = SandboxV2OIDCFlowService(settings=s)
        from unittest.mock import MagicMock
        cfg = MagicMock()
        cfg.client_id = "test-client"
        cfg.client_secret = "super-secret-do-not-leak"
        cfg.provider_config_id = "cfg-1"
        url = svc._build_authorization_url(cfg, "state1", "nonce1", "challenge1")
        assert "super-secret-do-not-leak" not in url


class TestTokenValidation:
    def test_alg_none_rejected(self):
        svc = SandboxV2OIDCFlowService(settings=DummySettings())
        result = svc.validate_id_token_claims({"alg": "none", "iss": "x", "aud": "x"})
        assert not result.alg_allowed

    def test_expired_rejected(self):
        svc = SandboxV2OIDCFlowService(settings=DummySettings())
        result = svc.validate_id_token_claims({"iss": "x", "aud": "x", "exp": 1})
        assert not result.exp_valid

    def test_issuer_mismatch(self):
        svc = SandboxV2OIDCFlowService(settings=DummySettings())
        from unittest.mock import MagicMock
        cfg = MagicMock(); cfg.issuer = "https://real-idp.example.com"; cfg.client_id = ""
        result = svc.validate_id_token_claims({"iss": "https://fake-idp.example.com"}, provider_config=cfg)
        assert not result.issuer_valid

    def test_signature_unavailable(self):
        svc = SandboxV2OIDCFlowService(settings=DummySettings())
        result = svc.validate_id_token_claims({"iss": "x", "aud": "x"})
        assert not result.signature_valid

    def test_email_verified_false(self):
        svc = SandboxV2OIDCFlowService(settings=DummySettings())
        result = svc.validate_id_token_claims({"iss": "x", "aud": "x", "email_verified": False})
        assert not result.email_verified


class TestOIDCReadiness:
    def test_readiness_fields(self):
        svc = SandboxV2OIDCFlowService(settings=DummySettings())
        r = svc.get_oidc_readiness()
        assert not r["real_oidc_login_enabled"]
        assert not r["oidc_signature_validation"]
        assert not r["token_storage"]
