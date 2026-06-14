"""IAM Service tests (Step 17)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.iam import SandboxV2IAMService
from src.open_platform.sandbox_v2.iam_provider import MockIAMProvider
from src.open_platform.sandbox_v2.models import (
    SandboxV2IAMProviderConfig, SandboxV2SSOLoginStatus, SandboxV2Role,
)
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.config import Settings
from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService


@pytest.fixture
def store():
    settings = Settings()
    store = SQLiteSandboxV2Store(settings, db_path=":memory:")
    return store


@pytest.fixture
def audit(store):
    return SandboxV2SecurityAuditService(store=store)


class DummySettings:
    iam_enabled = False
    sso_enabled = False
    iam_provider = "disabled"
    oidc_enabled = False
    saml_enabled = False
    iam_jit_provisioning = False
    iam_default_role = "viewer"


class TestIAMServiceDefaults:
    def test_iam_disabled_by_default(self):
        svc = SandboxV2IAMService(settings=DummySettings())
        assert not svc.iam_enabled
        assert not svc.sso_enabled

    def test_simulate_login_when_disabled(self):
        svc = SandboxV2IAMService(settings=DummySettings())
        result = svc.simulate_sso_login({}, "some-id")
        assert result["login_status"] == SandboxV2SSOLoginStatus.DISABLED
        assert not result["allowed"]

    def test_readiness_shows_disabled(self):
        svc = SandboxV2IAMService(settings=DummySettings())
        r = svc.get_iam_readiness()
        assert not r["external_iam_enabled"]
        assert not r["sso_enabled"]
        assert not r["real_oidc_login"]
        assert not r["token_storage"]


class TestIAMServiceWithStore:
    def test_create_provider_config(self, store, audit):
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=DummySettings())
        config = svc.create_provider_config(
            provider_type="mock", protocol="mock", enabled=True,
            issuer="https://mock.example.com", client_id="test-client",
            client_secret="secret-123",
            allowed_domains=["example.com"],
            organization_id="org-1", workspace_id="ws-1",
        )
        assert config is not None
        # Secret must be stored as ref, not plaintext
        d = config.to_dict()
        assert d.get("client_secret_ref", "") != ""
        # to_dict should mask client_id
        assert "test-client" not in str(d.get("client_id", ""))

    def test_list_provider_configs(self, store, audit):
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=DummySettings())
        svc.create_provider_config(provider_type="mock", protocol="mock", enabled=True,
                                   issuer="mock", organization_id="org-1")
        items = svc.list_provider_configs(organization_id="org-1")
        assert len(items) >= 1

    def test_get_provider_config(self, store, audit):
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=DummySettings())
        created = svc.create_provider_config(provider_type="mock", protocol="mock", enabled=True,
                                             issuer="mock", organization_id="org-1")
        assert created is not None
        fetched = svc.get_provider_config(created.provider_config_id)
        assert fetched is not None
        assert fetched.issuer == "mock"

    def test_create_role_mapping(self, store, audit):
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=DummySettings())
        mapping = svc.create_role_mapping(
            external_group="developers", sandbox_role="developer",
            sandbox_scopes=["read", "write"], organization_id="org-1",
        )
        assert mapping is not None
        assert mapping.sandbox_role == "developer"

    def test_role_mapping_audit_written(self, store, audit):
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=DummySettings())
        mapping = svc.create_role_mapping(
            external_group="engineers", sandbox_role="developer",
            organization_id="org-1",
        )
        # Audit events should be written
        events = store.list_security_audit_events(organization_id="org-1", limit=10)
        assert len(events) > 0

    def test_simulate_sso_with_mock(self, store, audit):
        enabled_settings = DummySettings()
        enabled_settings.iam_enabled = True
        enabled_settings.iam_provider = "mock"

        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=enabled_settings)
        config = svc.create_provider_config(
            provider_type="mock", protocol="mock", enabled=True,
            issuer="https://mock.example.com",
            allowed_domains=["example.com"],
            organization_id="org-1",
        )
        assert config is not None

        result = svc.simulate_sso_login(
            claims={"sub": "u1", "iss": "https://mock.example.com",
                    "email": "user@example.com", "email_verified": True,
                    "name": "Test User"},
            provider_config_id=config.provider_config_id,
            organization_id="org-1",
        )
        assert result["allowed"]

    def test_simulate_sso_reject_token(self, store, audit):
        enabled_settings = DummySettings()
        enabled_settings.iam_enabled = True
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=enabled_settings)
        result = svc.simulate_sso_login(
            claims={"access_token": "fake-token"},
            provider_config_id="some-id", organization_id="org-1",
        )
        assert not result["allowed"]

    def test_cross_tenant_rejected(self, store, audit):
        enabled_settings = DummySettings()
        enabled_settings.iam_enabled = True
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=enabled_settings)
        config = svc.create_provider_config(
            provider_type="mock", protocol="mock", enabled=True,
            issuer="mock", organization_id="org-A",
        )
        result = svc.simulate_sso_login(
            claims={"sub": "u1", "iss": "mock", "email": "u@b.com", "email_verified": True},
            provider_config_id=config.provider_config_id,
            organization_id="org-B",  # different org!
        )
        assert not result["allowed"]

    def test_list_external_identities(self, store, audit):
        enabled_settings = DummySettings()
        enabled_settings.iam_enabled = True
        svc = SandboxV2IAMService(store=store, audit_service=audit, settings=enabled_settings)
        # Map an identity
        config = svc.create_provider_config(provider_type="mock", protocol="mock", enabled=True,
                                            issuer="mock", organization_id="org-1")
        svc.map_external_identity(
            claims={"sub": "ext-1", "email": "user@example.com", "email_verified": True},
            provider_config_id=config.provider_config_id,
            organization_id="org-1",
        )
        identities = svc.list_external_identities(organization_id="org-1")
        assert len(identities) >= 1
