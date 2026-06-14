"""IAM API tests (Step 17)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from fastapi.testclient import TestClient
from src.api.sandbox_v2 import create_sandbox_v2_router
from src.open_platform.sandbox_v2.service import SandboxV2Service
from src.open_platform.sandbox_v2.iam import SandboxV2IAMService
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.config import Settings
from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService

BASE = "/api/runtime/sandbox-v2"

class DummySettings:
    iam_enabled = False
    sso_enabled = False
    iam_provider = "disabled"
    oidc_enabled = False
    saml_enabled = False
    iam_jit_provisioning = False
    iam_default_role = "viewer"


class IAMEnabledSettings(DummySettings):
    iam_enabled = True
    iam_provider = "mock"


@pytest.fixture
def client():
    store = SQLiteSandboxV2Store(Settings(), db_path=":memory:")
    audit = SandboxV2SecurityAuditService(store=store)
    settings = DummySettings()
    iam_svc = SandboxV2IAMService(store=store, audit_service=audit, settings=settings)
    svc = SandboxV2Service(store, iam_service=iam_svc)
    router = create_sandbox_v2_router(svc)
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestIAMReadiness:
    def test_iam_readiness_disabled(self, client):
        resp = client.get(f"{BASE}/iam/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert not data["external_iam_enabled"]
        assert not data["sso_enabled"]
        assert data["iam_safe_mode"]

    def test_iam_fields_in_main_readiness(self, client):
        resp = client.get(f"{BASE}/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert "iam_provider_config" in data
        assert "iam_safe_mode" in data


class TestProviderConfigAPI:
    def test_create_provider_config(self, client):
        payload = {
            "provider_type": "mock", "protocol": "mock",
            "enabled": True, "issuer": "https://mock.example.com",
            "client_id": "test-client", "client_secret": "secret-123",
            "allowed_domains": ["example.com"],
            "organization_id": "org-1",
        }
        resp = client.post(f"{BASE}/iam/provider-configs", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        cfg = data["provider_config"]
        assert cfg["provider_type"] == "mock"
        # client_secret must not appear in response
        assert "secret-123" not in str(data)

    def test_list_provider_configs(self, client):
        resp = client.get(f"{BASE}/iam/provider-configs")
        assert resp.status_code == 200
        data = resp.json()
        assert "provider_configs" in data

    def test_get_provider_config_404(self, client):
        resp = client.get(f"{BASE}/iam/provider-configs/nonexistent")
        assert resp.status_code == 404

    def test_malformed_body_not_500(self, client):
        resp = client.post(f"{BASE}/iam/provider-configs", json={"bad": "field"})
        # Should not be 500
        assert resp.status_code != 500


class TestRoleMappingAPI:
    def test_create_role_mapping(self, client):
        payload = {
            "external_group": "developers", "sandbox_role": "developer",
            "sandbox_scopes": ["read", "write"],
            "organization_id": "org-1",
        }
        resp = client.post(f"{BASE}/iam/role-mappings", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["role_mapping"]["sandbox_role"] == "developer"

    def test_list_role_mappings(self, client):
        resp = client.get(f"{BASE}/iam/role-mappings")
        assert resp.status_code == 200
        assert "role_mappings" in resp.json()

    def test_malformed_body_not_500(self, client):
        resp = client.post(f"{BASE}/iam/role-mappings", json={"bad": "field"})
        assert resp.status_code != 500


class TestSimulateLoginAPI:
    def test_simulate_login_disabled(self, client):
        payload = {"claims": {"sub": "u1"}, "provider_config_id": "fake"}
        resp = client.post(f"{BASE}/iam/simulate-login", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert not data["allowed"]

    def test_simulate_login_rejects_token(self, client):
        payload = {"claims": {"access_token": "fake"}, "provider_config_id": "x"}
        resp = client.post(f"{BASE}/iam/simulate-login", json=payload)
        assert resp.status_code == 400

    def test_simulate_login_malformed_not_500(self, client):
        resp = client.post(f"{BASE}/iam/simulate-login", json={"bad": "data"})
        assert resp.status_code != 500


class TestExternalIdentitiesAPI:
    def test_list_empty(self, client):
        resp = client.get(f"{BASE}/iam/external-identities")
        assert resp.status_code == 200
        assert "external_identities" in resp.json()


class TestMappingDecisionsAPI:
    def test_list_empty(self, client):
        resp = client.get(f"{BASE}/iam/mapping-decisions")
        assert resp.status_code == 200
        assert "mapping_decisions" in resp.json()


class TestSSOSimulationsAPI:
    def test_list_empty(self, client):
        resp = client.get(f"{BASE}/iam/sso-simulations")
        assert resp.status_code == 200
        assert "sso_simulations" in resp.json()
