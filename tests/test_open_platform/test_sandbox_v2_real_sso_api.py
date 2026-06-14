"""Real SSO API tests (Step 20)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from fastapi.testclient import TestClient
from src.api.sandbox_v2 import create_sandbox_v2_router
from src.open_platform.sandbox_v2.service import SandboxV2Service
from src.open_platform.sandbox_v2.iam import SandboxV2IAMService
from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.config import Settings

BASE = "/api/runtime/sandbox-v2"


class DummySettings:
    iam_enabled = True; sso_enabled = True; iam_provider = "mock"
    real_oidc_login_enabled = False; real_saml_login_enabled = False
    oidc_token_exchange_enabled = False; oidc_pkce_enabled = True
    oidc_require_nonce = True; oidc_require_state = True
    oidc_redirect_uri = "http://localhost/callback"
    oidc_scopes = "openid,email"; oidc_clock_skew_seconds = 60
    sso_session_enabled = False; sso_session_ttl_seconds = 3600
    sso_state_ttl_seconds = 300; saml_disable_xxe = True


@pytest.fixture
def client():
    store = SQLiteSandboxV2Store(Settings(), db_path=":memory:")
    audit = SandboxV2SecurityAuditService(store=store)
    iam = SandboxV2IAMService(store=store, audit_service=audit, settings=DummySettings())
    svc = SandboxV2Service(store, iam_service=iam)
    router = create_sandbox_v2_router(svc)
    from fastapi import FastAPI
    app = FastAPI(); app.include_router(router)
    return TestClient(app)


class TestSSOReadiness:
    def test_get_readiness(self, client):
        resp = client.get(f"{BASE}/iam/sso/readiness")
        assert resp.status_code == 200
        d = resp.json()
        assert not d["real_oidc_login_enabled"]
        assert not d["real_saml_login_enabled"]
        assert d["sso_safe_mode"]

    def test_in_main_readiness(self, client):
        resp = client.get(f"{BASE}/readiness")
        assert resp.status_code == 200
        d = resp.json()
        assert "real_oidc_login_enabled" in d


class TestOIDCAPI:
    def test_authorize_disabled(self, client):
        resp = client.post(f"{BASE}/iam/oidc/authorize", json={"provider_config_id": "none"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

    def test_callback_disabled(self, client):
        resp = client.get(f"{BASE}/iam/oidc/callback?code=test&state=test")
        assert resp.status_code == 200

    def test_callback_post(self, client):
        resp = client.post(f"{BASE}/iam/oidc/callback?code=test&state=test")
        assert resp.status_code != 500

    def test_callback_results(self, client):
        resp = client.get(f"{BASE}/iam/oidc/callback-results")
        assert resp.status_code == 200


class TestSAMLAPI:
    def test_authn_request_disabled(self, client):
        resp = client.post(f"{BASE}/iam/saml/authn-request", json={"provider_config_id": "x"})
        assert resp.status_code == 200

    def test_acs_disabled(self, client):
        resp = client.post(f"{BASE}/iam/saml/acs", json={"SAMLResponse": "<xml/>", "RelayState": "x"})
        assert resp.status_code == 200

    def test_acs_malformed_not_500(self, client):
        resp = client.post(f"{BASE}/iam/saml/acs", json={"bad": "data"})
        assert resp.status_code != 500


class TestSessionAPI:
    def test_list_sessions(self, client):
        resp = client.get(f"{BASE}/iam/sso/sessions")
        assert resp.status_code == 200

    def test_revoke_session_404_or_ok(self, client):
        resp = client.post(f"{BASE}/iam/sso/sessions/nonexistent/revoke")
        assert resp.status_code in (200, 404)
