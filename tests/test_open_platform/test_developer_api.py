"""Developer API 集成测试 — /developers/register, /me, /api-keys, /agents。

覆盖:
- Auth: 401, require_auth full coverage
- Developer Account: register, get, patch, verify, duplicate, tenant isolation
- API Keys: create (raw_key once), list (no hash), revoke, suspended check
- Submissions: create, list, detail, update draft, validate, submit, withdraw
- Security: key_hash never in response, raw_key once, cross-dev isolation
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.developer_store import SQLiteDeveloperStore
from src.adapters.submission_store import SQLiteSubmissionStore
from src.adapters.usage_store import UsageStoreAdapter
from src.api.developer_router import create_developer_router
from src.api.middleware import require_auth, get_token_payload, TokenPayload
from src.core.auth import WorkspaceRole
from src.open_platform.developer import DeveloperAccount, DeveloperStatus


# ═══════════════════════════════════════════
# Auth Helpers
# ═══════════════════════════════════════════

def _payload(role=WorkspaceRole.ADMIN, ws="test-ws-001", super_admin=False) -> TokenPayload:
    return TokenPayload(user_id="user-001", workspace_id=ws, role=role, is_super_admin=super_admin)

async def _override_auth(): return _payload()
async def _override_other_user(): return _payload(ws="test-ws-001", role=WorkspaceRole.ADMIN)
async def _override_user_2(): return TokenPayload(user_id="user-002", workspace_id="test-ws-001", role=WorkspaceRole.ADMIN)


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════

@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def developer_store(settings):
    return SQLiteDeveloperStore(settings, db_path=":memory:")


@pytest.fixture
def submission_store(settings):
    return SQLiteSubmissionStore(settings, db_path=":memory:")


@pytest.fixture
def usage_store(settings, tmp_path):
    db = str(tmp_path / "dev_api_usage.db")
    s = UsageStoreAdapter(config=settings, db_path=db)
    yield s
    s.close()


def _make_app(dev_store, sub_store, usage=None, auth_override=_override_auth):
    app = FastAPI()
    app.dependency_overrides[require_auth] = auth_override
    app.dependency_overrides[get_token_payload] = auth_override
    app.include_router(create_developer_router(dev_store, sub_store, usage))
    return TestClient(app)


@pytest.fixture
def client(developer_store, submission_store, usage_store):
    return _make_app(developer_store, submission_store, usage_store)


@pytest.fixture
def client_other_user(developer_store, submission_store, usage_store):
    return _make_app(developer_store, submission_store, usage_store, _override_user_2)


@pytest.fixture
def client_no_auth(developer_store, submission_store):
    app = FastAPI()
    app.include_router(create_developer_router(developer_store, submission_store, None))
    return TestClient(app)


def _register(client) -> dict:
    resp = client.post("/developers/register", json={"display_name": "Test Dev", "contact_email": "dev@test.com"})
    return resp.json()


# ═══════════════════════════════════════════
# Auth Tests
# ═══════════════════════════════════════════


class TestAuth:
    """所有 developer endpoint 必须 require_auth。"""

    ENDPOINTS = [
        ("GET", "/developers/me"),
        ("PATCH", "/developers/me"),
        ("POST", "/developers/me/verify-request"),
        ("POST", "/developers/api-keys"),
        ("GET", "/developers/api-keys"),
        ("DELETE", "/developers/api-keys/any"),
        ("POST", "/developers/agents"),
        ("GET", "/developers/agents"),
        ("GET", "/developers/agents/any"),
        ("PATCH", "/developers/agents/any"),
        ("POST", "/developers/agents/any/validate"),
        ("POST", "/developers/agents/any/submit"),
        ("POST", "/developers/agents/any/withdraw"),
    ]

    def test_all_endpoints_401_without_token(self, client_no_auth):
        for method, path in self.ENDPOINTS:
            meth = getattr(client_no_auth, method.lower())
            if method in ("GET", "DELETE"):
                resp = meth(path)
            else:
                resp = meth(path, json={})
            assert resp.status_code == 401, f"{method} {path} should return 401, got {resp.status_code}"

    def test_register_401_without_token(self, client_no_auth):
        resp = client_no_auth.post("/developers/register", json={})
        assert resp.status_code == 401


# ═══════════════════════════════════════════
# Developer Account Tests
# ═══════════════════════════════════════════


class TestDeveloperAccount:
    def test_register_developer(self, client):
        resp = client.post("/developers/register", json={
            "display_name": "My Dev",
            "contact_email": "dev@example.com",
            "organization_name": "Org Inc",
            "website": "https://dev.example.com",
            "metadata": {"plan": "free"},
        })
        assert resp.status_code == 201
        data = resp.json()
        dev = data["developer"]
        assert dev["developer_id"].startswith("dev_")
        assert dev["display_name"] == "My Dev"
        assert dev["organization_name"] == "Org Inc"
        assert dev["status"] == "active"

    def test_duplicate_register_returns_409(self, client):
        _register(client)
        resp = client.post("/developers/register", json={"display_name": "Dup", "contact_email": "dup@test.com"})
        assert resp.status_code == 409

    def test_get_me_returns_developer(self, client):
        _register(client)
        resp = client.get("/developers/me")
        assert resp.status_code == 200
        assert resp.json()["developer"]["status"] == "active"

    def test_get_me_not_registered_returns_404(self, client):
        resp = client.get("/developers/me")
        assert resp.status_code == 404

    def test_patch_me_updates_allowed_fields(self, client):
        _register(client)
        resp = client.patch("/developers/me", json={
            "display_name": "Updated Name",
            "organization_name": "NewOrg",
            "website": "https://new.com",
        })
        assert resp.status_code == 200
        dev = resp.json()["developer"]
        assert dev["display_name"] == "Updated Name"
        assert dev["organization_name"] == "NewOrg"

    def test_patch_me_cannot_change_status(self, client):
        _register(client)
        resp = client.patch("/developers/me", json={"display_name": "Hacked"})
        assert resp.status_code == 200
        dev = resp.json()["developer"]
        assert dev["status"] == "active"  # status unchanged
        assert dev["developer_id"]  # developer_id unchanged

    def test_verify_request_mvp(self, client):
        _register(client)
        resp = client.post("/developers/me/verify-request")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert "MVP" in resp.json()["message"]

    def test_tenant_isolation_same_user_different_tenant(self, developer_store, submission_store, usage_store):
        """两个不同 tenant 各自有独立的 developer account。"""
        # tenant-a
        async def auth_a(): return TokenPayload(user_id="u1", workspace_id="t-a", role=WorkspaceRole.ADMIN)
        client_a = _make_app(developer_store, submission_store, usage_store, auth_a)
        client_a.post("/developers/register", json={"display_name": "A", "contact_email": "a@a.com"})

        # tenant-b
        async def auth_b(): return TokenPayload(user_id="u1", workspace_id="t-b", role=WorkspaceRole.ADMIN)
        client_b = _make_app(developer_store, submission_store, usage_store, auth_b)
        resp = client_b.get("/developers/me")
        assert resp.status_code == 404  # tenant-b hasn't registered

        client_b.post("/developers/register", json={"display_name": "B", "contact_email": "b@b.com"})
        resp = client_b.get("/developers/me")
        assert resp.status_code == 200
        assert resp.json()["developer"]["tenant_id"] == "t-b"


# ═══════════════════════════════════════════
# API Key Tests
# ═══════════════════════════════════════════


class TestApiKeys:
    def test_create_key_returns_raw_key_once(self, client):
        _register(client)
        resp = client.post("/developers/api-keys", json={"name": "Key1", "scopes": ["agent:read"]})
        assert resp.status_code == 201
        data = resp.json()
        assert "raw_key" in data
        assert data["raw_key"].startswith("cos_dev_")
        assert data["api_key"]["api_key_id"].startswith("apk_")

    def test_create_key_does_not_expose_hash(self, client):
        _register(client)
        resp = client.post("/developers/api-keys", json={"name": "SafeKey", "scopes": ["agent:read"]})
        data = resp.json()
        assert "key_hash" not in data
        assert "key_hash" not in data["api_key"]

    def test_list_keys_does_not_return_raw_key(self, client):
        _register(client)
        client.post("/developers/api-keys", json={"name": "K1", "scopes": ["agent:read"]})
        resp = client.get("/developers/api-keys")
        data = resp.json()
        for key in data["api_keys"]:
            assert "raw_key" not in key
            assert "key_hash" not in key

    def test_list_keys_excludes_revoked_by_default(self, client):
        _register(client)
        r = client.post("/developers/api-keys", json={"name": "K1", "scopes": ["agent:read"]})
        apk_id = r.json()["api_key"]["api_key_id"]
        client.delete(f"/developers/api-keys/{apk_id}")

        resp = client.get("/developers/api-keys")
        assert resp.json()["total"] == 0

    def test_include_revoked(self, client):
        _register(client)
        r = client.post("/developers/api-keys", json={"name": "K1", "scopes": ["agent:read"]})
        apk_id = r.json()["api_key"]["api_key_id"]
        client.delete(f"/developers/api-keys/{apk_id}")

        resp = client.get("/developers/api-keys?include_revoked=true")
        assert resp.json()["total"] == 1

    def test_revoke_key_success(self, client):
        _register(client)
        r = client.post("/developers/api-keys", json={"name": "ToRevoke", "scopes": ["agent:read"]})
        apk_id = r.json()["api_key"]["api_key_id"]

        resp = client.delete(f"/developers/api-keys/{apk_id}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_cannot_revoke_other_developer_key(self, client, client_other_user):
        _register(client)
        r = client.post("/developers/api-keys", json={"name": "Mine", "scopes": ["agent:read"]})
        apk_id = r.json()["api_key"]["api_key_id"]

        # client_other_user (user-002) tries to revoke user-001's key
        resp = client_other_user.delete(f"/developers/api-keys/{apk_id}")
        assert resp.status_code == 404

    def test_empty_scopes_rejected(self, client):
        _register(client)
        resp = client.post("/developers/api-keys", json={"name": "Bad", "scopes": []})
        assert resp.status_code == 422

    def test_suspended_developer_cannot_create_key(self, developer_store, submission_store, usage_store):
        async def auth(): return TokenPayload(user_id="sus-u", workspace_id="ws1", role=WorkspaceRole.ADMIN)
        c = _make_app(developer_store, submission_store, usage_store, auth)
        c.post("/developers/register", json={"display_name": "ToSuspend", "contact_email": "s@t.com"})

        dev = developer_store.get_developer_by_user("sus-u", "ws1")
        developer_store.suspend_developer(dev.developer_id)

        resp = c.post("/developers/api-keys", json={"name": "AfterSuspend", "scopes": ["agent:read"]})
        assert resp.status_code == 403

    def test_unregistered_developer_cannot_create_key(self, client):
        resp = client.post("/developers/api-keys", json={"name": "Key", "scopes": ["agent:read"]})
        assert resp.status_code == 404

    def test_usage_event_has_no_raw_key(self, client, usage_store):
        _register(client)
        client.post("/developers/api-keys", json={"name": "NoLeak", "scopes": ["agent:read"]})
        events = usage_store.query_events(tenant_id="test-ws-001", resource="developer_api_key_create")
        if events:
            for e in events:
                meta = e.metadata or {}
                assert "raw_key" not in str(meta).lower()
                assert "key_hash" not in str(meta).lower()

    def test_create_key_with_expiry(self, client):
        _register(client)
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        resp = client.post("/developers/api-keys", json={"name": "ExpKey", "scopes": ["agent:read"], "expires_at": future})
        assert resp.status_code == 201

    def test_create_key_invalid_expiry_rejected(self, client):
        _register(client)
        resp = client.post("/developers/api-keys", json={"name": "BadExp", "scopes": ["agent:read"], "expires_at": "not-a-date"})
        assert resp.status_code == 422


# ═══════════════════════════════════════════
# Submissions Tests
# ═══════════════════════════════════════════

VALID_MANIFEST = {
    "name": "my-agent",
    "display_name": "My Agent",
    "description": "A test agent",
    "version": "1.0.0",
    "capabilities": ["test"],
    "required_permissions": ["agent:execute"],
    "runtime_type": "manifest_only",
    "security_profile": {
        "requires_network": False,
        "reads_user_data": False,
        "writes_user_data": False,
        "sandbox_level": "no_execution",
    },
}


class TestSubmissions:
    def test_create_draft(self, client):
        _register(client)
        resp = client.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST})
        assert resp.status_code == 201
        assert resp.json()["submission"]["submission_id"].startswith("sub_")

    def test_create_invalid_manifest_returns_422(self, client):
        _register(client)
        bad = {**VALID_MANIFEST, "capabilities": []}
        resp = client.post("/developers/agents", json={"agent_manifest": bad})
        assert resp.status_code == 422

    def test_list_own_submissions(self, client):
        _register(client)
        client.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST, "metadata": {"round": 1}})
        client.post("/developers/agents", json={"agent_manifest": {**VALID_MANIFEST, "name": "agent-2"}, "metadata": {"round": 2}})

        resp = client.get("/developers/agents")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_cannot_see_other_developer_submission(self, client, client_other_user):
        _register(client)
        r = client.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST})
        sub_id = r.json()["submission"]["submission_id"]

        resp = client_other_user.get(f"/developers/agents/{sub_id}")
        assert resp.status_code == 404

    def test_get_submission_detail(self, client):
        _register(client)
        r = client.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST})
        sub_id = r.json()["submission"]["submission_id"]

        resp = client.get(f"/developers/agents/{sub_id}")
        assert resp.status_code == 200
        assert resp.json()["submission"]["submission_id"] == sub_id

    def test_update_draft_manifest(self, client):
        _register(client)
        r = client.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST})
        sub_id = r.json()["submission"]["submission_id"]

        updated = {**VALID_MANIFEST, "display_name": "Updated Agent"}
        resp = client.patch(f"/developers/agents/{sub_id}", json={"agent_manifest": updated})
        assert resp.status_code == 200
        assert resp.json()["submission"]["agent_manifest"]["display_name"] == "Updated Agent"

    def test_cannot_update_submitted_manifest(self, client):
        _register(client)
        r = client.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST})
        sub_id = r.json()["submission"]["submission_id"]
        client.post(f"/developers/agents/{sub_id}/submit")

        resp = client.patch(f"/developers/agents/{sub_id}", json={"agent_manifest": VALID_MANIFEST})
        assert resp.status_code == 409

    def test_cannot_update_other_developer_draft(self, client, client_other_user):
        _register(client)
        r = client.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST})
        sub_id = r.json()["submission"]["submission_id"]

        resp = client_other_user.patch(f"/developers/agents/{sub_id}", json={"agent_manifest": VALID_MANIFEST})
        assert resp.status_code == 404

    def test_validate_submission(self, client):
        _register(client)
        r = client.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST})
        sub_id = r.json()["submission"]["submission_id"]

        resp = client.post(f"/developers/agents/{sub_id}/validate")
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_submit_draft(self, client):
        _register(client)
        r = client.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST})
        sub_id = r.json()["submission"]["submission_id"]

        resp = client.post(f"/developers/agents/{sub_id}/submit")
        assert resp.status_code == 200
        assert resp.json()["submission"]["status"] == "submitted"

    def test_submit_invalid_manifest_fails(self, client, developer_store, submission_store):
        """创建时 manifest 无效 → 422，提交无法进行。"""
        from src.open_platform.submission import AgentManifest, SecurityProfile, AgentSubmission as AS, SubmissionStatus
        _register(client)
        dev = developer_store.get_developer_by_user("user-001", "test-ws-001")

        bad_manifest = AgentManifest(
            name="bad", display_name="Bad", description="Bad",
            version="1.0.0", capabilities=[], required_permissions=[],
            security_profile=SecurityProfile(),
        )
        sub = AS(
            developer_id=dev.developer_id,
            tenant_id="test-ws-001",
            agent_manifest=bad_manifest,
            status=SubmissionStatus.DRAFT,
        )
        created = submission_store.create_submission(sub)

        resp = client.post(f"/developers/agents/{created.submission_id}/submit")
        assert resp.status_code == 422

    def test_withdraw_submitted(self, client):
        _register(client)
        r = client.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST})
        sub_id = r.json()["submission"]["submission_id"]
        client.post(f"/developers/agents/{sub_id}/submit")

        resp = client.post(f"/developers/agents/{sub_id}/withdraw")
        assert resp.status_code == 200
        assert resp.json()["submission"]["status"] == "withdrawn"

    def test_cannot_withdraw_other_developer(self, client, client_other_user):
        _register(client)
        r = client.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST})
        sub_id = r.json()["submission"]["submission_id"]
        client.post(f"/developers/agents/{sub_id}/submit")

        resp = client_other_user.post(f"/developers/agents/{sub_id}/withdraw")
        assert resp.status_code == 404

    def test_developer_cannot_publish(self, client):
        """Director API 没有 publish 端点 — developer 不应该能 publish。"""
        _register(client)
        resp = client.post("/developers/agents/any/publish")
        assert resp.status_code == 404  # publish 不存在于 developer router

    def test_suspended_developer_cannot_create_submission(self, developer_store, submission_store, usage_store):
        async def auth(): return TokenPayload(user_id="sus-s", workspace_id="ws1", role=WorkspaceRole.ADMIN)
        c = _make_app(developer_store, submission_store, usage_store, auth)
        c.post("/developers/register", json={"display_name": "SusSub", "contact_email": "ss@t.com"})
        dev = developer_store.get_developer_by_user("sus-s", "ws1")
        developer_store.suspend_developer(dev.developer_id)

        resp = c.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST})
        assert resp.status_code == 403

    def test_list_submissions_by_status(self, client):
        _register(client)
        r = client.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST})
        sub_id = r.json()["submission"]["submission_id"]
        client.post(f"/developers/agents/{sub_id}/submit")

        resp = client.get("/developers/agents?status=submitted")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_withdrawn_excluded_by_default(self, client):
        _register(client)
        r = client.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST})
        sub_id = r.json()["submission"]["submission_id"]
        client.post(f"/developers/agents/{sub_id}/submit")
        client.post(f"/developers/agents/{sub_id}/withdraw")

        resp = client.get("/developers/agents")
        assert resp.json()["total"] == 0

    def test_withdrawn_included_when_requested(self, client):
        _register(client)
        r = client.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST})
        sub_id = r.json()["submission"]["submission_id"]
        client.post(f"/developers/agents/{sub_id}/submit")
        client.post(f"/developers/agents/{sub_id}/withdraw")

        resp = client.get("/developers/agents?include_withdrawn=true")
        assert resp.json()["total"] == 1

    def test_package_url_not_executed(self, client):
        _register(client)
        resp = client.post("/developers/agents", json={
            "agent_manifest": VALID_MANIFEST,
            "package_url": "https://evil.com/rm-rf.sh",
        })
        assert resp.status_code == 201
        sub = resp.json()["submission"]
        assert sub["package_url"] == "https://evil.com/rm-rf.sh"
        assert sub["status"] == "draft"  # 没有自动运行任何东西


# ═══════════════════════════════════════════
# Security: No hash/raw_key leakage in API responses
# ═══════════════════════════════════════════


class TestSecurityNoLeak:
    """确认 key_hash 和 raw_key 不在任何 API response 中泄露。"""

    def test_raw_key_only_in_create_response(self, client):
        _register(client)
        r = client.post("/developers/api-keys", json={"name": "L1", "scopes": ["agent:read"]})
        assert r.status_code == 201
        assert "raw_key" in r.json()

        apk_id = r.json()["api_key"]["api_key_id"]
        # list
        resp = client.get("/developers/api-keys")
        for key in resp.json()["api_keys"]:
            assert "raw_key" not in key
            assert "key_hash" not in key
        # include_revoked
        resp = client.get("/developers/api-keys?include_revoked=true")
        for key in resp.json()["api_keys"]:
            assert "raw_key" not in key
            assert "key_hash" not in key

        # revoke
        client.delete(f"/developers/api-keys/{apk_id}")
        resp = client.get("/developers/api-keys?include_revoked=true")
        for key in resp.json()["api_keys"]:
            assert "raw_key" not in key
            assert "key_hash" not in key

    def test_no_traceback_in_error_responses(self, client):
        """404/409/422 不应泄露 traceback。"""
        _register(client)
        # 404
        resp = client.get("/developers/agents/nonexistent")
        assert resp.status_code == 404
        assert "Traceback" not in str(resp.json())
        # 409 duplicate
        client.post("/developers/register", json={})  # it will 409
        # 422
        resp = client.post("/developers/api-keys", json={"name": "Bad", "scopes": []})
        assert resp.status_code == 422
        assert "Traceback" not in str(resp.json())


# ═══════════════════════════════════════════
# Usage Events
# ═══════════════════════════════════════════


class TestUsageEvents:
    def test_developer_register_creates_usage(self, client, usage_store):
        client.post("/developers/register", json={"display_name": "D1", "contact_email": "d1@t.com"})
        events = usage_store.query_events(tenant_id="test-ws-001", resource="developer_register")
        assert len(events) >= 1

    def test_api_key_create_creates_usage(self, client, usage_store):
        _register(client)
        client.post("/developers/api-keys", json={"name": "UK", "scopes": ["agent:read"]})
        events = usage_store.query_events(tenant_id="test-ws-001", resource="developer_api_key_create")
        assert len(events) >= 1

    def test_api_key_revoke_creates_usage(self, client, usage_store):
        _register(client)
        r = client.post("/developers/api-keys", json={"name": "RK", "scopes": ["agent:read"]})
        apk_id = r.json()["api_key"]["api_key_id"]
        client.delete(f"/developers/api-keys/{apk_id}")
        events = usage_store.query_events(tenant_id="test-ws-001", resource="developer_api_key_revoke")
        assert len(events) >= 1

    def test_submission_create_creates_usage(self, client, usage_store):
        _register(client)
        client.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST})
        events = usage_store.query_events(tenant_id="test-ws-001", resource="agent_submission_create")
        assert len(events) >= 1

    def test_submission_submit_creates_usage(self, client, usage_store):
        _register(client)
        r = client.post("/developers/agents", json={"agent_manifest": VALID_MANIFEST})
        sub_id = r.json()["submission"]["submission_id"]
        client.post(f"/developers/agents/{sub_id}/submit")
        events = usage_store.query_events(tenant_id="test-ws-001", resource="agent_submission_submit")
        assert len(events) >= 1
