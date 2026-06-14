"""IAM Store tests (Step 17)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.config import Settings
from src.open_platform.sandbox_v2.models import (
    SandboxV2IAMProviderConfig, SandboxV2ExternalIdentity,
    SandboxV2IAMRoleMapping, SandboxV2IAMMappingDecision,
    SandboxV2SSOSimulationResult,
    SandboxV2IAMProviderType, SandboxV2SSOProtocol,
    SandboxV2IAMMappingStatus,
)


@pytest.fixture
def store():
    settings = Settings()
    return SQLiteSandboxV2Store(settings, db_path=":memory:")


class TestIAMProviderConfigStore:
    def test_create_and_get(self, store):
        config = SandboxV2IAMProviderConfig(
            provider_type=SandboxV2IAMProviderType.MOCK,
            protocol=SandboxV2SSOProtocol.MOCK,
            enabled=True, issuer="https://mock.example.com",
            client_id="test-client", client_secret_ref="secret://ref",
            organization_id="org-1",
        )
        created = store.create_iam_provider_config(config)
        assert created.provider_config_id != ""
        fetched = store.get_iam_provider_config(created.provider_config_id)
        assert fetched is not None
        assert fetched.issuer == "https://mock.example.com"
        # client_secret_ref, not client_id plaintext in actual storage
        assert fetched.client_secret_ref == "secret://ref"

    def test_list_by_org(self, store):
        store.create_iam_provider_config(SandboxV2IAMProviderConfig(
            provider_type="oidc", organization_id="org-1",
        ))
        store.create_iam_provider_config(SandboxV2IAMProviderConfig(
            provider_type="saml", organization_id="org-2",
        ))
        items = store.list_iam_provider_configs(organization_id="org-1")
        assert all(i.organization_id == "org-1" for i in items)

    def test_list_limit(self, store):
        for i in range(5):
            store.create_iam_provider_config(SandboxV2IAMProviderConfig(
                provider_type="mock", organization_id="org-1",
            ))
        items = store.list_iam_provider_configs(limit=3)
        assert len(items) <= 3

    def test_update_status(self, store):
        config = store.create_iam_provider_config(SandboxV2IAMProviderConfig(
            enabled=False, organization_id="org-1",
        ))
        updated = store.update_iam_provider_config_status(config.provider_config_id, True)
        assert updated is not None
        assert updated.enabled


class TestExternalIdentityStore:
    def test_create_and_list(self, store):
        identity = SandboxV2ExternalIdentity(
            external_subject="ext-sub-1", external_email="user@example.com",
            email_verified=True, organization_id="org-1",
        )
        created = store.create_external_identity(identity)
        assert created.external_identity_id != ""
        items = store.list_external_identities(organization_id="org-1")
        assert len(items) >= 1
        assert items[0].external_email == "user@example.com"

    def test_get_external_identity(self, store):
        identity = store.create_external_identity(SandboxV2ExternalIdentity(
            external_subject="ext-1", organization_id="org-1",
        ))
        fetched = store.get_external_identity(identity.external_identity_id)
        assert fetched is not None
        assert fetched.external_subject == "ext-1"


class TestIAMRoleMappingStore:
    def test_create_and_list(self, store):
        mapping = SandboxV2IAMRoleMapping(
            external_group="developers", sandbox_role="developer",
            organization_id="org-1",
        )
        created = store.create_iam_role_mapping(mapping)
        assert created.mapping_id != ""
        items = store.list_iam_role_mappings(organization_id="org-1")
        assert len(items) >= 1
        assert items[0].sandbox_role == "developer"

    def test_list_by_enabled(self, store):
        store.create_iam_role_mapping(SandboxV2IAMRoleMapping(
            external_group="g1", sandbox_role="viewer", enabled=True,
            organization_id="org-1",
        ))
        store.create_iam_role_mapping(SandboxV2IAMRoleMapping(
            external_group="g2", sandbox_role="auditor", enabled=False,
            organization_id="org-1",
        ))
        items = store.list_iam_role_mappings(organization_id="org-1", enabled=True)
        assert all(i.enabled for i in items)


class TestIAMMappingDecisionStore:
    def test_create_and_list(self, store):
        decision = SandboxV2IAMMappingDecision(
            allowed=True, status=SandboxV2IAMMappingStatus.MAPPED,
            reason="Test mapping", organization_id="org-1",
        )
        created = store.create_iam_mapping_decision(decision)
        assert created.decision_id != ""
        items = store.list_iam_mapping_decisions(organization_id="org-1")
        assert len(items) >= 1


class TestSSOSimulationStore:
    def test_create_and_list(self, store):
        result = SandboxV2SSOSimulationResult(
            protocol=SandboxV2SSOProtocol.MOCK,
            login_status="simulated",
            audit_event_id="audit-1",
        )
        created = store.create_sso_simulation_result(result)
        assert created.simulation_id != ""
        items = store.list_sso_simulation_results()
        assert len(items) >= 1
