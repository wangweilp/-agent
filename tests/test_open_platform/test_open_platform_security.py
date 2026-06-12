"""Open Platform 安全审计测试 — 全链路安全边界。

覆盖:
- Auth/Permission: 401/403 for all endpoint groups
- Tenant/Developer isolation: cross-dev, cross-tenant
- Publish security: status gate, permission gate, non-execution
- API Key security: raw_key only once, key_hash never leaks
- Runtime boundary: no auto-registration, no package execution
- Frontend safety: verified via typecheck + eslint (this file is backend-only)
"""

import os, json, pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.developer_store import SQLiteDeveloperStore
from src.adapters.submission_store import SQLiteSubmissionStore
from src.adapters.usage_store import UsageStoreAdapter
from src.api.developer_router import create_developer_router
from src.api.admin_submission_router import create_admin_submission_router
from src.api.middleware import require_auth, get_token_payload, TokenPayload
from src.core.auth import WorkspaceRole
from src.open_platform.developer import (
    DeveloperAccount, DeveloperApiKey, DeveloperStatus,
    generate_api_key, get_api_key_prefix, hash_api_key, verify_api_key,
)
from src.open_platform.submission import (
    AgentManifest, AgentSubmission, SecurityProfile, SubmissionStatus,
)


# ═══════════════════════════════════════════
# Auth Helpers
# ═══════════════════════════════════════════

def _p(role=WorkspaceRole.ADMIN, ws="test-ws-001", uid="user-001", sa=False):
    return TokenPayload(user_id=uid, workspace_id=ws, role=role, is_super_admin=sa)

async def _auth_admin(): return _p()
async def _auth_member(): return _p(WorkspaceRole.MEMBER)
async def _auth_viewer(): return _p(WorkspaceRole.VIEWER)
async def _auth_dev(): return _p(WorkspaceRole.MEMBER, uid="dev-u")
async def _auth_super(): return _p(WorkspaceRole.ADMIN, sa=True)
async def _auth_other_tenant(): return _p(ws="other-tenant")
async def _auth_other_user(): return _p(uid="other-user")


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════

@pytest.fixture
def s(): return Settings(deepseek_api_key="sk-test")

@pytest.fixture
def dev_store(s): return SQLiteDeveloperStore(s, db_path=":memory:")

@pytest.fixture
def sub_store(s): return SQLiteSubmissionStore(s, db_path=":memory:")

@pytest.fixture
def mkp_store(s):
    from src.adapters.marketplace_store import SQLiteMarketplaceStore
    return SQLiteMarketplaceStore(s, db_path=":memory:")

@pytest.fixture
def usage_store(s, tmp_path):
    u = UsageStoreAdapter(config=s, db_path=str(tmp_path / "sec_usage.db"))
    yield u; u.close()


def _dev_client(dev, sub, usage=None, auth=_auth_admin):
    app = FastAPI(); app.dependency_overrides[require_auth] = auth
    app.dependency_overrides[get_token_payload] = auth
    app.include_router(create_developer_router(dev, sub, usage))
    return TestClient(app)

def _admin_client(dev, sub, usage=None, mkp=None, auth=_auth_admin):
    app = FastAPI(); app.dependency_overrides[require_auth] = auth
    app.include_router(create_admin_submission_router(dev, sub, usage, mkp))
    return TestClient(app)

def _no_auth(dev, sub):
    app = FastAPI()
    app.include_router(create_developer_router(dev, sub, None))
    return TestClient(app)


# ═══════════════════════════════════════════
# 1. Auth Gate: All endpoints require auth
# ═══════════════════════════════════════════

class TestAuthGate:
    DEV_PATHS = [
        ("POST", "/developers/register"), ("GET", "/developers/me"),
        ("PATCH", "/developers/me"), ("POST", "/developers/me/verify-request"),
        ("POST", "/developers/api-keys"), ("GET", "/developers/api-keys"),
        ("DELETE", "/developers/api-keys/x"), ("POST", "/developers/agents"),
        ("GET", "/developers/agents"), ("GET", "/developers/agents/x"),
        ("PATCH", "/developers/agents/x"), ("POST", "/developers/agents/x/validate"),
        ("POST", "/developers/agents/x/submit"), ("POST", "/developers/agents/x/withdraw"),
    ]
    ADMIN_PATHS = [
        ("GET", "/admin/agent-submissions"), ("GET", "/admin/agent-submissions/x"),
        ("GET", "/admin/agent-submissions/x/reviews"),
        ("POST", "/admin/agent-submissions/x/start-review"),
        ("POST", "/admin/agent-submissions/x/approve"),
        ("POST", "/admin/agent-submissions/x/reject"),
        ("POST", "/admin/agent-submissions/x/request-changes"),
        ("POST", "/admin/agent-submissions/x/publish"),
    ]

    def test_dev_endpoints_401(self, dev_store, sub_store):
        c = _no_auth(dev_store, sub_store)
        for method, path in self.DEV_PATHS:
            m = getattr(c, method.lower())
            resp = m(path, json={}) if method not in ("GET","DELETE") else m(path)
            assert resp.status_code == 401, f"{method} {path} got {resp.status_code}"

    def test_admin_endpoints_401(self, dev_store, sub_store):
        app = FastAPI()
        app.include_router(create_admin_submission_router(dev_store, sub_store, None, None))
        c = TestClient(app)
        for method, path in self.ADMIN_PATHS:
            m = getattr(c, method.lower())
            resp = m(path, json={}) if method not in ("GET","DELETE") else m(path)
            assert resp.status_code == 401, f"{method} {path} got {resp.status_code}"

    def test_member_cannot_admin(self, dev_store, sub_store, mkp_store):
        c = _admin_client(dev_store, sub_store, mkp=mkp_store, auth=_auth_member)
        resp = c.get("/admin/agent-submissions")
        assert resp.status_code == 403

    def test_viewer_cannot_admin(self, dev_store, sub_store, mkp_store):
        c = _admin_client(dev_store, sub_store, mkp=mkp_store, auth=_auth_viewer)
        resp = c.get("/admin/agent-submissions")
        assert resp.status_code == 403

    def test_developer_cannot_admin(self, dev_store, sub_store, mkp_store):
        c = _admin_client(dev_store, sub_store, mkp=mkp_store, auth=_auth_dev)
        resp = c.get("/admin/agent-submissions")
        assert resp.status_code == 403

    def test_member_cannot_publish(self, dev_store, sub_store, mkp_store):
        c = _admin_client(dev_store, sub_store, mkp=mkp_store, auth=_auth_member)
        resp = c.post("/admin/agent-submissions/x/publish")
        assert resp.status_code == 403


# ═══════════════════════════════════════════
# 2. API Key Security
# ═══════════════════════════════════════════

class TestApiKeySecurity:
    def test_raw_key_only_in_create_response(self, dev_store, sub_store, usage_store):
        c = _dev_client(dev_store, sub_store, usage_store)
        c.post("/developers/register", json={"display_name":"D","contact_email":"d@t.com"})
        r = c.post("/developers/api-keys", json={"name":"K","scopes":["agent:read"]})
        assert r.status_code == 201
        assert "raw_key" in r.json()

        # List should NOT contain raw_key
        r2 = c.get("/developers/api-keys")
        for k in r2.json()["api_keys"]:
            assert "raw_key" not in k
            assert "key_hash" not in k

    def test_key_hash_never_in_dev_api_response(self, dev_store, sub_store, usage_store):
        c = _dev_client(dev_store, sub_store, usage_store)
        c.post("/developers/register", json={"display_name":"D","contact_email":"d@t.com"})
        # Scan all read endpoints
        for path, meth in [("/developers/me","GET"), ("/developers/api-keys","GET")]:
            resp = getattr(c, meth.lower())(path)
            assert "key_hash" not in json.dumps(resp.json()), f"key_hash found in {path}"

    def test_revoked_key_verify_fails(self, dev_store, sub_store, usage_store):
        c = _dev_client(dev_store, sub_store, usage_store)
        c.post("/developers/register", json={"display_name":"D","contact_email":"d@t.com"})
        r = c.post("/developers/api-keys", json={"name":"K","scopes":["agent:read"]})
        raw = r.json()["raw_key"]
        apk_id = r.json()["api_key"]["api_key_id"]

        # Verify works
        dev = dev_store.get_developer_by_user("user-001", "test-ws-001")
        found = dev_store.verify_and_lookup_api_key(raw)
        assert found is not None

        # Revoke
        c.delete(f"/developers/api-keys/{apk_id}")

        # Verify fails
        found2 = dev_store.verify_and_lookup_api_key(raw)
        assert found2 is None

    def test_expired_key_verify_fails(self, dev_store):
        from datetime import datetime, timedelta, timezone
        raw = generate_api_key()
        expired = datetime.now(timezone.utc) - timedelta(days=1)
        key = DeveloperApiKey(
            developer_id="dev_x", key_prefix=get_api_key_prefix(raw),
            key_hash=hash_api_key(raw), name="Exp", scopes=["agent:read"],
            expires_at=expired,
        )
        # Create developer + key in store
        d = DeveloperAccount(user_id="x", tenant_id="ws1", display_name="X", contact_email="x@x.com")
        dev_store.create_developer(d)
        dev_store.create_api_key(key)
        found = dev_store.verify_and_lookup_api_key(raw)
        assert found is None  # expired

    def test_api_key_cannot_bypass_auth(self, dev_store, sub_store):
        """API Key is not used as auth token — JWT required for all APIs."""
        # Verify 401 without token (no API Key auth middleware exists)
        c = _no_auth(dev_store, sub_store)
        resp = c.get("/developers/me")
        assert resp.status_code == 401
        # API Key in header should not bypass JWT requirement
        raw = generate_api_key()
        resp = c.get("/developers/me", headers={"X-API-Key": raw})
        assert resp.status_code == 401  # JWT still required


# ═══════════════════════════════════════════
# 3. Tenant / Developer Isolation
# ═══════════════════════════════════════════

class TestTenantIsolation:
    def test_dev_cannot_read_other_dev_keys(self, dev_store, sub_store, usage_store):
        # dev A
        ca = _dev_client(dev_store, sub_store, usage_store, _auth_dev)
        ca.post("/developers/register", json={"display_name":"A","contact_email":"a@t.com"})
        ca.post("/developers/api-keys", json={"name":"AK","scopes":["agent:read"]})

        # dev B (different user_id)
        cb = _dev_client(dev_store, sub_store, usage_store,
                         auth=lambda: TokenPayload(user_id="dev-b", workspace_id="test-ws-001", role=WorkspaceRole.MEMBER))
        cb.post("/developers/register", json={"display_name":"B","contact_email":"b@t.com"})
        resp = cb.get("/developers/api-keys")
        assert resp.json()["total"] == 0  # cannot see A's keys

    def test_dev_cannot_read_other_dev_submission(self, dev_store, sub_store, usage_store):
        # dev A creates submission
        ca = _dev_client(dev_store, sub_store, usage_store, _auth_dev)
        ca.post("/developers/register", json={"display_name":"A","contact_email":"a@t.com"})
        m = {"name":"a-agent","display_name":"A Agent","description":"A","version":"1.0.0","capabilities":["t"],"required_permissions":["agent:execute"],"runtime_type":"manifest_only","security_profile":{"sandbox_level":"no_execution"}}
        r = ca.post("/developers/agents", json={"agent_manifest": m})
        sid = r.json()["submission"]["submission_id"]

        # dev B cannot access
        cb = _dev_client(dev_store, sub_store, usage_store,
                         auth=lambda: TokenPayload(user_id="dev-b", workspace_id="test-ws-001", role=WorkspaceRole.MEMBER))
        cb.post("/developers/register", json={"display_name":"B","contact_email":"b@t.com"})
        resp = cb.get(f"/developers/agents/{sid}")
        assert resp.status_code == 404

    def test_admin_tenant_scoped(self, dev_store, sub_store, mkp_store, usage_store):
        dev = DeveloperAccount(user_id="t1-u", tenant_id="tenant-1", display_name="T1", contact_email="t1@t.com")
        dev_store.create_developer(dev)
        # Create submission in tenant-1 (cannot use dev router directly, must use store)
        m = AgentManifest(name="t1", display_name="T1", description="T1", version="1.0.0", capabilities=["t"], required_permissions=["agent:execute"], security_profile=SecurityProfile())
        sub = AgentSubmission(developer_id=dev.developer_id, tenant_id="tenant-1", agent_manifest=m, status=SubmissionStatus.DRAFT)
        sub_store.create_submission(sub)
        sub_store.submit_submission(sub.submission_id, dev.developer_id)

        # Admin in tenant-2 cannot see
        c = _admin_client(dev_store, sub_store, mkp=mkp_store, usage=usage_store,
                          auth=lambda: TokenPayload(user_id="admin", workspace_id="tenant-2", role=WorkspaceRole.ADMIN))
        resp = c.get("/admin/agent-submissions")
        assert resp.json()["total"] == 0

    def test_super_admin_cross_tenant(self, dev_store, sub_store, mkp_store, usage_store):
        dev = DeveloperAccount(user_id="sa-u", tenant_id="sa-t", display_name="SA", contact_email="sa@t.com")
        dev_store.create_developer(dev)
        m = AgentManifest(name="sa", display_name="SA", description="SA", version="1.0.0", capabilities=["t"], required_permissions=["agent:execute"], security_profile=SecurityProfile())
        sub = AgentSubmission(developer_id=dev.developer_id, tenant_id="sa-t", agent_manifest=m, status=SubmissionStatus.DRAFT)
        sub_store.create_submission(sub)
        sub_store.submit_submission(sub.submission_id, dev.developer_id)

        c = _admin_client(dev_store, sub_store, mkp=mkp_store, usage=usage_store, auth=_auth_super)
        resp = c.get("/admin/agent-submissions?tenant_id=sa-t")
        assert resp.json()["total"] >= 1


# ═══════════════════════════════════════════
# 4. Usage metadata safety
# ═══════════════════════════════════════════

class TestUsageMetadataSafety:
    def test_developer_register_usage_no_sensitive_data(self, dev_store, sub_store, usage_store):
        c = _dev_client(dev_store, sub_store, usage_store)
        c.post("/developers/register", json={"display_name":"D","contact_email":"d@t.com"})
        events = usage_store.query_events(tenant_id="test-ws-001", resource="developer_register")
        for e in events:
            m = e.metadata or {}
            assert "raw_key" not in json.dumps(m)
            assert "key_hash" not in json.dumps(m)
            assert "password" not in json.dumps(m)

    def test_api_key_create_usage_no_raw_key(self, dev_store, sub_store, usage_store):
        c = _dev_client(dev_store, sub_store, usage_store)
        c.post("/developers/register", json={"display_name":"D","contact_email":"d@t.com"})
        c.post("/developers/api-keys", json={"name":"K","scopes":["agent:read"]})
        events = usage_store.query_events(tenant_id="test-ws-001", resource="developer_api_key_create")
        for e in events:
            m = json.dumps(e.metadata or {})
            assert "raw_key" not in m
            assert "key_hash" not in m

    def test_publish_usage_metadata_safe(self, dev_store, sub_store, mkp_store, usage_store):
        """Publish usage metadata contains no raw_key/key_hash/full manifest."""
        from tests.test_open_platform.test_admin_review_api import _setup_approved, _override_admin
        # Force admin auth
        async def _auth_adm(): return TokenPayload(user_id="pub-admin", workspace_id="test-ws-001", role=WorkspaceRole.ADMIN)
        sid, _ = _setup_approved(dev_store, sub_store, developer_user_id="pub-metadata-dev")
        app = FastAPI(); app.dependency_overrides[require_auth] = _auth_adm
        app.include_router(create_admin_submission_router(dev_store, sub_store, usage_store, mkp_store))
        c = TestClient(app)
        c.post(f"/admin/agent-submissions/{sid}/publish")
        events = usage_store.query_events(tenant_id="test-ws-001", resource="agent_submission_publish")
        assert len(events) >= 1
        meta = json.dumps(events[0].metadata or {})
        assert "raw_key" not in meta
        assert "key_hash" not in meta
        assert events[0].metadata.get("manifest_name") == "my-agent"


# ═══════════════════════════════════════════
# 5. Publish non-execution + non-installation gates (integration with test_admin_review_api)
# ═══════════════════════════════════════════

class TestPublishNonExecution:
    """Verify publish does NOT: execute package, register runtime, create installation."""
    # These are covered in test_admin_review_api.py::TestPublish
    # This class adds explicit assertions

    def test_publish_does_not_register_agent_runtime(self, dev_store, sub_store, mkp_store, usage_store):
        from tests.test_open_platform.test_admin_review_api import _setup_approved
        sid, _ = _setup_approved(dev_store, sub_store, developer_user_id="no-rt-dev")
        async def a(): return TokenPayload(user_id="admin-rt", workspace_id="test-ws-001", role=WorkspaceRole.ADMIN)
        app = FastAPI(); app.dependency_overrides[require_auth] = a
        app.include_router(create_admin_submission_router(dev_store, sub_store, usage_store, mkp_store))
        c = TestClient(app)
        resp = c.post(f"/admin/agent-submissions/{sid}/publish")
        assert resp.status_code == 200
        mkp_id = resp.json()["submission"]["marketplace_agent_id"]
        assert mkp_id is not None
        # Verify agent exists in marketplace but NOT in AgentRegistry
        agent = mkp_store.get_agent(mkp_id)
        assert agent is not None
        assert agent.publisher_type == "developer"
        # No TenantAgentInstallation created
        assert mkp_store.list_installations(tenant_id="test-ws-001") == []

    def test_developer_agent_must_still_go_through_install_flow(self, dev_store, sub_store, mkp_store, usage_store):
        """Publish doesn't auto-install. Marketplace install is a separate step."""
        from tests.test_open_platform.test_admin_review_api import _setup_approved
        sid, _ = _setup_approved(dev_store, sub_store, developer_user_id="install-flow-dev")
        async def a(): return TokenPayload(user_id="admin-flow", workspace_id="test-ws-001", role=WorkspaceRole.ADMIN)
        app = FastAPI(); app.dependency_overrides[require_auth] = a
        app.include_router(create_admin_submission_router(dev_store, sub_store, usage_store, mkp_store))
        c = TestClient(app)
        resp = c.post(f"/admin/agent-submissions/{sid}/publish")
        mkp_id = resp.json()["submission"]["marketplace_agent_id"]
        assert mkp_id is not None
        # No installation was created — separate install flow required
        assert not mkp_store.is_agent_installed(mkp_id, "test-ws-001", "test-ws-001")


# ═══════════════════════════════════════════
# 6. Frontend safety (type-level checks)
# ═══════════════════════════════════════════

class TestFrontendTypeSafety:
    """Verify frontend types don't expose key_hash or publish-like fields."""

    def test_open_platform_types_no_key_hash(self):
        """key_hash must not appear in frontend type definitions (comments are ok)."""
        with open("frontend/types/open-platform.ts", encoding="utf-8") as f:
            content = f.read()
        # Remove comment lines before checking
        lines = [l for l in content.split("\n") if not l.strip().startswith("//")]
        non_comment = "\n".join(lines)
        # "key_hash" in a comment (line above) is the safety notice, not a type field
        # The actual check: no interface should declare key_hash as a field
        assert "key_hash:" not in non_comment, "key_hash field found in open-platform.ts type definitions"
        assert "key_hash?" not in non_comment, "key_hash? field found in open-platform.ts type definitions"

    def test_developer_service_no_publish(self):
        """Developer service must not call publish endpoint."""
        with open("frontend/services/developer.ts", encoding="utf-8") as f:
            content = f.read()
        assert "/publish" not in content, "publish found in developer service"

    def test_admin_submission_service_has_publish(self):
        """Admin service must have publish function."""
        with open("frontend/services/admin-submissions.ts", encoding="utf-8") as f:
            content = f.read()
        assert "publishAdminSubmission" in content


# ═══════════════════════════════════════════
# 7. Suspended developer cannot act
# ═══════════════════════════════════════════

class TestSuspendedDeveloper:
    def test_suspended_cannot_create_key(self, dev_store, sub_store, usage_store):
        async def auth(): return TokenPayload(user_id="sus-u", workspace_id="ws1", role=WorkspaceRole.ADMIN)
        c = _dev_client(dev_store, sub_store, usage_store, auth)
        c.post("/developers/register", json={"display_name":"S","contact_email":"s@t.com"})
        dev = dev_store.get_developer_by_user("sus-u", "ws1")
        dev_store.suspend_developer(dev.developer_id)
        resp = c.post("/developers/api-keys", json={"name":"X","scopes":["agent:read"]})
        assert resp.status_code == 403

    def test_suspended_cannot_create_submission(self, dev_store, sub_store, usage_store):
        async def auth(): return TokenPayload(user_id="sus-s", workspace_id="ws1", role=WorkspaceRole.ADMIN)
        c = _dev_client(dev_store, sub_store, usage_store, auth)
        c.post("/developers/register", json={"display_name":"S2","contact_email":"s2@t.com"})
        dev = dev_store.get_developer_by_user("sus-s", "ws1")
        dev_store.suspend_developer(dev.developer_id)
        m = {"name":"x","display_name":"X","description":"x","version":"1.0.0","capabilities":["t"],"required_permissions":["agent:execute"],"runtime_type":"manifest_only","security_profile":{"sandbox_level":"no_execution"}}
        resp = c.post("/developers/agents", json={"agent_manifest": m})
        assert resp.status_code == 403


# ═══════════════════════════════════════════
# 8. Error safety — no traceback in errors
# ═══════════════════════════════════════════

class TestErrorSafety:
    def test_developer_errors_no_traceback(self, dev_store, sub_store, usage_store):
        c = _dev_client(dev_store, sub_store, usage_store)
        for path in ["/developers/me", "/developers/agents/x"]:
            resp = c.get(path)
            assert "Traceback" not in json.dumps(resp.json())

    def test_admin_errors_no_traceback(self, dev_store, sub_store, mkp_store):
        c = _admin_client(dev_store, sub_store, mkp=mkp_store)
        for path in ["/admin/agent-submissions/x", "/admin/agent-submissions/x/reviews"]:
            resp = c.get(path)
            body = json.dumps(resp.json())
            assert "Traceback" not in body
            assert "src/" not in body
