"""SSO Session tests (Step 20)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.models import SandboxV2SSOSession, SandboxV2SSOSessionStatus
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.config import Settings


@pytest.fixture
def store():
    return SQLiteSandboxV2Store(Settings(), db_path=":memory:")


class TestSSOSessionModel:
    def test_create_session(self):
        s = SandboxV2SSOSession(principal_id="u1", organization_id="org-1", roles=["viewer"])
        assert s.session_id != ""
        assert s.status == "active"

    def test_no_token_in_session(self):
        s = SandboxV2SSOSession(principal_id="u1")
        d = s.to_dict()
        assert "token" not in str(d).lower() or "access_token" not in str(d).lower()

    def test_session_persist(self, store):
        s = SandboxV2SSOSession(principal_id="u1", organization_id="org-1")
        store.create_sso_session(s)
        fetched = store.get_sso_session(s.session_id)
        assert fetched is not None
        assert fetched.principal_id == "u1"

    def test_revoke(self, store):
        s = SandboxV2SSOSession(principal_id="u1", organization_id="org-1")
        store.create_sso_session(s)
        revoked = store.revoke_sso_session(s.session_id)
        assert revoked.status == "revoked"

    def test_list_by_org(self, store):
        store.create_sso_session(SandboxV2SSOSession(principal_id="u-a", organization_id="org-A"))
        store.create_sso_session(SandboxV2SSOSession(principal_id="u-b", organization_id="org-B"))
        sessions = store.list_sso_sessions(organization_id="org-A")
        assert all(s.organization_id == "org-A" for s in sessions)
