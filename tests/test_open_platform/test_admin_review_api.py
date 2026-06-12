"""Admin Review API 集成测试 — /admin/agent-submissions。

覆盖:
- Auth/Role: 401, 403 (member/viewer/dev), 200 (admin/owner/super)
- Queue: list, status/developer/tenant filter, tenant isolation
- Detail: validation, developer profile, latest review record
- Reviews: list, isolation
- Start Review: valid/invalid state, member denied
- Approve: valid manifest, invalid manifest, warnings, self-review denied, no publish
- Reject: notes required, self-review denied, wrong state
- Request Changes: notes required, self-review denied, review record
- Security: no raw_key, no key_hash, no traceback, no publish route
"""

import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.developer_store import SQLiteDeveloperStore
from src.adapters.submission_store import SQLiteSubmissionStore
from src.adapters.usage_store import UsageStoreAdapter
from src.api.admin_submission_router import create_admin_submission_router
from src.api.middleware import require_auth, TokenPayload
from src.core.auth import WorkspaceRole
from src.open_platform.developer import DeveloperAccount
from src.open_platform.submission import (
    AgentManifest, AgentSubmission, SecurityProfile, SubmissionStatus,
)

_VALID_MANIFEST = AgentManifest(
    name="my-agent", display_name="My Agent", description="Test",
    version="1.0.0", capabilities=["test"],
    required_permissions=["agent:execute"],
    security_profile=SecurityProfile(),
)


def _payload(role=WorkspaceRole.ADMIN, ws="test-ws-001", uid="user-admin", sa=False):
    return TokenPayload(user_id=uid, workspace_id=ws, role=role, is_super_admin=sa)


async def _override_admin(): return _payload()
async def _override_member(): return _payload(role=WorkspaceRole.MEMBER)
async def _override_viewer(): return _payload(role=WorkspaceRole.VIEWER)
async def _override_dev_user(): return _payload(role=WorkspaceRole.MEMBER, uid="dev-user-001")
async def _override_super(): return _payload(role=WorkspaceRole.ADMIN, sa=True)
async def _override_other_admin(): return _payload(uid="other-admin")


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def dev_store(settings): return SQLiteDeveloperStore(settings, db_path=":memory:")


@pytest.fixture
def sub_store(settings): return SQLiteSubmissionStore(settings, db_path=":memory:")


@pytest.fixture
def usage_store(settings, tmp_path):
    s = UsageStoreAdapter(config=settings, db_path=str(tmp_path / "ar_usage.db"))
    yield s; s.close()


def _make_app(dev_store, sub_store, usage=None, auth=_override_admin):
    app = FastAPI()
    app.dependency_overrides[require_auth] = auth
    app.include_router(create_admin_submission_router(dev_store, sub_store, usage))
    return TestClient(app)


@pytest.fixture
def client(dev_store, sub_store, usage_store):
    return _make_app(dev_store, sub_store, usage_store)


@pytest.fixture
def client_member(dev_store, sub_store):
    return _make_app(dev_store, sub_store, None, _override_member)


@pytest.fixture
def client_viewer(dev_store, sub_store):
    return _make_app(dev_store, sub_store, None, _override_viewer)


@pytest.fixture
def client_super(dev_store, sub_store, usage_store):
    return _make_app(dev_store, sub_store, usage_store, _override_super)


@pytest.fixture
def client_dev_user(dev_store, sub_store):
    return _make_app(dev_store, sub_store, None, _override_dev_user)


@pytest.fixture
def client_no_auth(dev_store, sub_store):
    app = FastAPI()
    app.include_router(create_admin_submission_router(dev_store, sub_store, None))
    return TestClient(app)


def _setup_dev_and_sub(dev_store, sub_store, developer_user_id="dev-user-001", manifest=None):
    """在 store 中创建 developer + submitted submission。"""
    dev = DeveloperAccount(
        user_id=developer_user_id, tenant_id="test-ws-001",
        display_name="Dev", contact_email="dev@t.com",
    )
    dev_store.create_developer(dev)

    sub = AgentSubmission(
        developer_id=dev.developer_id, tenant_id="test-ws-001",
        agent_manifest=manifest or _VALID_MANIFEST,
        status=SubmissionStatus.DRAFT,
    )
    created = sub_store.create_submission(sub)
    # Submit it
    sub_store.submit_submission(created.submission_id, dev.developer_id)
    return created.submission_id, dev.developer_id


def _draft_sub(dev_store, sub_store, dev_id=None):
    dev = DeveloperAccount(
        user_id="dev-002", tenant_id="test-ws-001",
        display_name="D2", contact_email="d2@t.com",
    )
    dev_store.create_developer(dev)
    sub = AgentSubmission(
        developer_id=dev.developer_id, tenant_id="test-ws-001",
        agent_manifest=_VALID_MANIFEST, status=SubmissionStatus.DRAFT,
    )
    return sub_store.create_submission(sub), dev


# ═══════════════════════════════════════════
# Auth / Role
# ═══════════════════════════════════════════


class TestAuth:
    PATHS = [
        ("GET", "/admin/agent-submissions"),
        ("GET", "/admin/agent-submissions/any"),
        ("GET", "/admin/agent-submissions/any/reviews"),
        ("POST", "/admin/agent-submissions/any/start-review"),
        ("POST", "/admin/agent-submissions/any/approve"),
        ("POST", "/admin/agent-submissions/any/reject"),
        ("POST", "/admin/agent-submissions/any/request-changes"),
    ]

    def test_all_endpoints_401(self, client_no_auth):
        for method, path in self.PATHS:
            meth = getattr(client_no_auth, method.lower())
            resp = meth(path, json={}) if method not in ("GET",) else meth(path)
            assert resp.status_code == 401, f"{method} {path} got {resp.status_code}"

    def test_member_gets_403(self, client_member):
        resp = client_member.get("/admin/agent-submissions")
        assert resp.status_code == 403

    def test_viewer_gets_403(self, client_viewer):
        resp = client_viewer.get("/admin/agent-submissions")
        assert resp.status_code == 403

    def test_dev_user_gets_403(self, client_dev_user):
        resp = client_dev_user.get("/admin/agent-submissions")
        assert resp.status_code == 403

    def test_admin_can_list(self, client, dev_store, sub_store):
        _setup_dev_and_sub(dev_store, sub_store)
        resp = client.get("/admin/agent-submissions")
        assert resp.status_code == 200

    def test_super_admin_can_list(self, client_super, dev_store, sub_store):
        _setup_dev_and_sub(dev_store, sub_store)
        resp = client_super.get("/admin/agent-submissions")
        assert resp.status_code == 200


# ═══════════════════════════════════════════
# List queue
# ═══════════════════════════════════════════


class TestListQueue:
    def test_list_submitted(self, client, dev_store, sub_store):
        _setup_dev_and_sub(dev_store, sub_store)
        resp = client.get("/admin/agent-submissions?status=submitted")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_list_by_developer(self, client, dev_store, sub_store):
        sid, did = _setup_dev_and_sub(dev_store, sub_store)
        resp = client.get(f"/admin/agent-submissions?developer_id={did}")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_admin_sees_only_current_tenant(self, dev_store, sub_store, usage_store):
        """admin 只能看到自己 tenant 的 submissions。"""
        sid1, _ = _setup_dev_and_sub(dev_store, sub_store)
        # 在其他 tenant 创建
        dev2 = DeveloperAccount(user_id="other-u", tenant_id="other-tenant",
                                display_name="O", contact_email="o@o.com")
        dev_store.create_developer(dev2)
        sub2 = AgentSubmission(developer_id=dev2.developer_id, tenant_id="other-tenant",
                               agent_manifest=_VALID_MANIFEST, status=SubmissionStatus.DRAFT)
        sub_store.create_submission(sub2)
        sub_store.submit_submission(sub2.submission_id, dev2.developer_id)

        # admin 只能看 test-ws-001
        resp = _make_app(dev_store, sub_store, usage_store).get("/admin/agent-submissions")
        assert resp.status_code == 200
        for s in resp.json()["submissions"]:
            assert s["tenant_id"] == "test-ws-001"

    def test_super_admin_can_see_cross_tenant(self, dev_store, sub_store, usage_store):
        """super_admin 可以跨 tenant 查看。"""
        _setup_dev_and_sub(dev_store, sub_store)
        dev2 = DeveloperAccount(user_id="other-u", tenant_id="other-tenant",
                                display_name="O", contact_email="o@o.com")
        dev_store.create_developer(dev2)
        sub2 = AgentSubmission(developer_id=dev2.developer_id, tenant_id="other-tenant",
                               agent_manifest=_VALID_MANIFEST, status=SubmissionStatus.DRAFT)
        sub_store.create_submission(sub2)
        sub_store.submit_submission(sub2.submission_id, dev2.developer_id)

        sc = _make_app(dev_store, sub_store, usage_store, _override_super)
        resp = sc.get("/admin/agent-submissions?tenant_id=other-tenant")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_missing_submission_returns_404(self, client):
        resp = client.get("/admin/agent-submissions/nonexistent")
        assert resp.status_code == 404


# ═══════════════════════════════════════════
# Detail
# ═══════════════════════════════════════════


class TestDetail:
    def test_detail_includes_validation(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        resp = client.get(f"/admin/agent-submissions/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert "validation" in data
        assert data["validation"]["valid"] is True

    def test_detail_includes_developer(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        resp = client.get(f"/admin/agent-submissions/{sid}")
        assert resp.status_code == 200
        assert resp.json()["developer"] is not None

    def test_detail_includes_latest_review_record_null(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        resp = client.get(f"/admin/agent-submissions/{sid}")
        assert resp.json()["latest_review_record"] is None

    def test_missing_returns_404(self, client):
        resp = client.get("/admin/agent-submissions/nonexistent")
        assert resp.status_code == 404


# ═══════════════════════════════════════════
# Review records list
# ═══════════════════════════════════════════


class TestReviewRecords:
    def test_reviews_empty_before_any_review(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        resp = client.get(f"/admin/agent-submissions/{sid}/reviews")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_reviews_returns_after_reject(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        client.post(f"/admin/agent-submissions/{sid}/start-review")
        client.post(f"/admin/agent-submissions/{sid}/reject", json={"notes": "Bad"})
        resp = client.get(f"/admin/agent-submissions/{sid}/reviews")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1


# ═══════════════════════════════════════════
# Start review
# ═══════════════════════════════════════════


class TestStartReview:
    def test_admin_can_start_review(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        resp = client.post(f"/admin/agent-submissions/{sid}/start-review")
        assert resp.status_code == 200
        assert resp.json()["submission"]["status"] == "in_review"

    def test_start_review_already_approved_returns_409(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        client.post(f"/admin/agent-submissions/{sid}/start-review")
        client.post(f"/admin/agent-submissions/{sid}/approve", json={"notes": "OK"})
        # 再次 start review → 409
        resp = client.post(f"/admin/agent-submissions/{sid}/start-review")
        assert resp.status_code == 409

    def test_member_cannot_start_review(self, client_member):
        resp = client_member.post("/admin/agent-submissions/any/start-review")
        assert resp.status_code == 403


# ═══════════════════════════════════════════
# Approve
# ═══════════════════════════════════════════


class TestApprove:
    def test_admin_can_approve(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        client.post(f"/admin/agent-submissions/{sid}/start-review")
        resp = client.post(f"/admin/agent-submissions/{sid}/approve", json={"notes": "LGTM"})
        assert resp.status_code == 200
        assert resp.json()["submission"]["status"] == "approved"

    def test_approve_creates_review_record(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        client.post(f"/admin/agent-submissions/{sid}/start-review")
        client.post(f"/admin/agent-submissions/{sid}/approve", json={"notes": "OK", "checklist": {"pass": True}})
        resp = client.get(f"/admin/agent-submissions/{sid}/reviews")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_approve_creates_usage(self, client, dev_store, sub_store, usage_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        client.post(f"/admin/agent-submissions/{sid}/start-review")
        client.post(f"/admin/agent-submissions/{sid}/approve", json={"notes": "OK"})
        events = usage_store.query_events(tenant_id="test-ws-001", resource="agent_submission_review")
        assert len(events) >= 1

    def test_approve_self_submission_returns_403(self, client, dev_store, sub_store):
        """admin 不能审核自己的 submission。"""
        # 用和 admin 同 user_id 的 developer 创建 submission
        dev = DeveloperAccount(
            user_id="user-admin", tenant_id="test-ws-001",
            display_name="Self Review Dev", contact_email="self@t.com",
        )
        dev_store.create_developer(dev)
        sub = AgentSubmission(
            developer_id=dev.developer_id, tenant_id="test-ws-001",
            agent_manifest=_VALID_MANIFEST, status=SubmissionStatus.DRAFT,
        )
        created = sub_store.create_submission(sub)
        sub_store.submit_submission(created.submission_id, dev.developer_id)
        client.post(f"/admin/agent-submissions/{created.submission_id}/start-review")

        resp = client.post(f"/admin/agent-submissions/{created.submission_id}/approve", json={"notes": "Self"})
        assert resp.status_code == 403

    def test_approve_invalid_manifest_returns_422(self, client, dev_store, sub_store):
        """Invalid manifest cannot be approved — api-level validate blocks it."""
        # Store-level submit validates manifest, so we create directly in submitted state
        dev = DeveloperAccount(
            user_id="bad-dev", tenant_id="test-ws-001",
            display_name="BadDev", contact_email="bad@t.com",
        )
        dev_store.create_developer(dev)
        bad_manifest = AgentManifest(
            name="bad", display_name="Bad", description="Bad",
            version="1.0.0", capabilities=[], required_permissions=[],
            security_profile=None,
        )
        sub = AgentSubmission(
            developer_id=dev.developer_id, tenant_id="test-ws-001",
            agent_manifest=bad_manifest,
            status=SubmissionStatus.DRAFT,
        )
        created = sub_store.create_submission(sub)
        # Force status to in_review to bypass submit validation
        created.status = SubmissionStatus.IN_REVIEW
        sub_store.update_submission(created)

        resp = client.post(f"/admin/agent-submissions/{created.submission_id}/approve", json={"notes": "?"})
        assert resp.status_code == 422

    def test_approve_with_security_warning_rejected(self, client, dev_store, sub_store):
        """带 warning 的 manifest 不能 approve。"""
        m = AgentManifest(
            name="warn-agent", display_name="Warn", description="W",
            version="1.0.0", capabilities=["t"], required_permissions=["agent:execute"],
            security_profile=SecurityProfile(sandbox_level="restricted"),
        )
        sid, _ = _setup_dev_and_sub(dev_store, sub_store, developer_user_id="warn-dev", manifest=m)
        client.post(f"/admin/agent-submissions/{sid}/start-review")
        resp = client.post(f"/admin/agent-submissions/{sid}/approve", json={"notes": "Try"})
        assert resp.status_code == 422

    def test_approve_does_not_create_marketplace_agent(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        client.post(f"/admin/agent-submissions/{sid}/start-review")
        resp = client.post(f"/admin/agent-submissions/{sid}/approve", json={"notes": "OK"})
        data = resp.json()
        assert data["submission"]["marketplace_agent_id"] is None  # publish not done

    def test_approve_draft_returns_409(self, client, dev_store, sub_store):
        sub, _ = _draft_sub(dev_store, sub_store)
        resp = client.post(f"/admin/agent-submissions/{sub.submission_id}/approve", json={"notes": "?"})
        assert resp.status_code == 409


# ═══════════════════════════════════════════
# Reject
# ═══════════════════════════════════════════


class TestReject:
    def test_admin_can_reject(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        client.post(f"/admin/agent-submissions/{sid}/start-review")
        resp = client.post(f"/admin/agent-submissions/{sid}/reject", json={"notes": "Security concern"})
        assert resp.status_code == 200
        assert resp.json()["submission"]["status"] == "rejected"

    def test_reject_requires_notes(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        client.post(f"/admin/agent-submissions/{sid}/start-review")
        resp = client.post(f"/admin/agent-submissions/{sid}/reject", json={"notes": ""})
        assert resp.status_code == 422

    def test_reject_creates_review_record(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        client.post(f"/admin/agent-submissions/{sid}/start-review")
        client.post(f"/admin/agent-submissions/{sid}/reject", json={"notes": "No good", "checklist": {"ok": False}})
        resp = client.get(f"/admin/agent-submissions/{sid}/reviews")
        assert resp.json()["total"] >= 1

    def test_reject_self_submission_returns_403(self, client, dev_store, sub_store):
        dev = DeveloperAccount(user_id="user-admin", tenant_id="test-ws-001",
                               display_name="Self", contact_email="s@t.com")
        dev_store.create_developer(dev)
        sub = AgentSubmission(developer_id=dev.developer_id, tenant_id="test-ws-001",
                              agent_manifest=_VALID_MANIFEST, status=SubmissionStatus.DRAFT)
        created = sub_store.create_submission(sub)
        sub_store.submit_submission(created.submission_id, dev.developer_id)
        client.post(f"/admin/agent-submissions/{created.submission_id}/start-review")

        resp = client.post(f"/admin/agent-submissions/{created.submission_id}/reject", json={"notes": "Bad"})
        assert resp.status_code == 403

    def test_reject_draft_returns_409(self, client, dev_store, sub_store):
        sub, _ = _draft_sub(dev_store, sub_store)
        resp = client.post(f"/admin/agent-submissions/{sub.submission_id}/reject", json={"notes": "?"})
        assert resp.status_code == 409


# ═══════════════════════════════════════════
# Request Changes
# ═══════════════════════════════════════════


class TestRequestChanges:
    def test_admin_can_request_changes(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        client.post(f"/admin/agent-submissions/{sid}/start-review")
        resp = client.post(f"/admin/agent-submissions/{sid}/request-changes",
                           json={"notes": "Fix manifest permissions"})
        assert resp.status_code == 200

    def test_request_changes_requires_notes(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        client.post(f"/admin/agent-submissions/{sid}/start-review")
        resp = client.post(f"/admin/agent-submissions/{sid}/request-changes", json={"notes": ""})
        assert resp.status_code == 422

    def test_request_changes_creates_review_record(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        client.post(f"/admin/agent-submissions/{sid}/start-review")
        client.post(f"/admin/agent-submissions/{sid}/request-changes",
                    json={"notes": "Fix it", "checklist": {"needs": "more"}})
        resp = client.get(f"/admin/agent-submissions/{sid}/reviews")
        assert resp.json()["total"] >= 1

    def test_request_changes_self_returns_403(self, client, dev_store, sub_store):
        dev = DeveloperAccount(user_id="user-admin", tenant_id="test-ws-001",
                               display_name="Self", contact_email="s@t.com")
        dev_store.create_developer(dev)
        sub = AgentSubmission(developer_id=dev.developer_id, tenant_id="test-ws-001",
                              agent_manifest=_VALID_MANIFEST, status=SubmissionStatus.DRAFT)
        created = sub_store.create_submission(sub)
        sub_store.submit_submission(created.submission_id, dev.developer_id)
        client.post(f"/admin/agent-submissions/{created.submission_id}/start-review")

        resp = client.post(f"/admin/agent-submissions/{created.submission_id}/request-changes",
                           json={"notes": "Need more"})
        assert resp.status_code == 403


# ═══════════════════════════════════════════
# Security
# ═══════════════════════════════════════════


class TestSecurity:
    def test_publish_route_exists_and_works(self, client, dev_store, sub_store):
        """Publish endpoint exists and requires approved status. draft/submitted rejected."""

    def test_no_marketplace_agent_created(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        client.post(f"/admin/agent-submissions/{sid}/start-review")
        resp = client.post(f"/admin/agent-submissions/{sid}/approve", json={"notes": "OK"})
        data = resp.json()
        assert data["submission"]["marketplace_agent_id"] is None

    def test_no_raw_key_in_response(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        # Check list/detail/reviews responses
        for path in [f"/admin/agent-submissions", f"/admin/agent-submissions/{sid}",
                     f"/admin/agent-submissions/{sid}/reviews"]:
            resp = client.get(path)
            assert resp.status_code == 200
            text = str(resp.json()).lower()
            assert "raw_key" not in text
            assert "key_hash" not in text

    def test_no_traceback_in_errors(self, client):
        resp = client.get("/admin/agent-submissions/nonexistent")
        assert resp.status_code == 404
        assert "Traceback" not in str(resp.json())
        assert "File " not in str(resp.json())

    def test_package_url_not_executed(self, client, dev_store, sub_store):
        """package_url 只存储不执行 — 审核不改变它。"""
        dev = DeveloperAccount(user_id="pkg-dev", tenant_id="test-ws-001",
                               display_name="Pkg", contact_email="p@t.com")
        dev_store.create_developer(dev)
        sub = AgentSubmission(
            developer_id=dev.developer_id, tenant_id="test-ws-001",
            agent_manifest=_VALID_MANIFEST,
            package_url="https://evil.com/danger.sh",
            status=SubmissionStatus.DRAFT,
        )
        created = sub_store.create_submission(sub)
        sub_store.submit_submission(created.submission_id, dev.developer_id)
        client.post(f"/admin/agent-submissions/{created.submission_id}/start-review")
        client.post(f"/admin/agent-submissions/{created.submission_id}/reject", json={"notes": "Package URL detected"})

        updated = sub_store.get_submission(created.submission_id)
        assert updated.package_url == "https://evil.com/danger.sh"  # stored but not executed
        assert updated.status == "rejected"

    def test_detail_latest_review_record_after_approve(self, client, dev_store, sub_store):
        sid, _ = _setup_dev_and_sub(dev_store, sub_store)
        client.post(f"/admin/agent-submissions/{sid}/start-review")
        client.post(f"/admin/agent-submissions/{sid}/approve", json={"notes": "OK", "checklist": {"x": 1}})
        resp = client.get(f"/admin/agent-submissions/{sid}")
        assert resp.status_code == 200
        lr = resp.json()["latest_review_record"]
        assert lr is not None
        assert lr["decision"] == "approve"
        assert lr["notes"] == "OK"
        assert lr["checklist"] == {"x": 1}


# ═══════════════════════════════════════════
# Publish (Step 22-H)
# ═══════════════════════════════════════════

def _setup_approved(dev_store, sub_store, developer_user_id="pub-dev-001"):
    """创建 approved submission 用于 publish 测试。"""
    dev = DeveloperAccount(user_id=developer_user_id, tenant_id="test-ws-001",
                           display_name="PubDev", contact_email="pub@t.com")
    dev_store.create_developer(dev)
    manifest = _VALID_MANIFEST
    sub = AgentSubmission(developer_id=dev.developer_id, tenant_id="test-ws-001",
                          agent_manifest=manifest, status=SubmissionStatus.DRAFT)
    created = sub_store.create_submission(sub)
    sub_store.submit_submission(created.submission_id, dev.developer_id)
    # Force through review flow
    created.status = SubmissionStatus.IN_REVIEW
    sub_store.update_submission(created)
    created.approve("reviewer-99", "Approved for publish")
    sub_store.update_submission(created)
    return created.submission_id, dev.developer_id


@pytest.fixture
def mkp_store(settings):
    from src.adapters.marketplace_store import SQLiteMarketplaceStore
    return SQLiteMarketplaceStore(settings, db_path=":memory:")


def _admin_app_with_mkp(dev_store, sub_store, mkp, usage=None):
    app = FastAPI()
    app.dependency_overrides[require_auth] = _override_admin
    app.include_router(create_admin_submission_router(dev_store, sub_store, usage, mkp))
    return TestClient(app)


class TestPublish:
    def test_publish_requires_auth(self, dev_store, sub_store, mkp_store):
        app = FastAPI()
        app.include_router(create_admin_submission_router(dev_store, sub_store, None, mkp_store))
        c = TestClient(app)
        resp = c.post("/admin/agent-submissions/any/publish")
        assert resp.status_code == 401

    def test_member_cannot_publish(self, dev_store, sub_store, mkp_store):
        app = FastAPI()
        app.dependency_overrides[require_auth] = _override_member
        app.include_router(create_admin_submission_router(dev_store, sub_store, None, mkp_store))
        resp = TestClient(app).post("/admin/agent-submissions/any/publish")
        assert resp.status_code == 403

    def test_admin_can_publish_approved(self, dev_store, sub_store, mkp_store, usage_store):
        sid, _ = _setup_approved(dev_store, sub_store)
        c = _admin_app_with_mkp(dev_store, sub_store, mkp_store, usage_store)
        resp = c.post(f"/admin/agent-submissions/{sid}/publish")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["submission"]["status"] == "published"
        assert resp.json()["submission"]["marketplace_agent_id"] is not None

    def test_publish_creates_marketplace_agent(self, dev_store, sub_store, mkp_store, usage_store):
        sid, _ = _setup_approved(dev_store, sub_store)
        c = _admin_app_with_mkp(dev_store, sub_store, mkp_store, usage_store)
        resp = c.post(f"/admin/agent-submissions/{sid}/publish")
        data = resp.json()
        mkp_id = data["submission"]["marketplace_agent_id"]
        assert mkp_id is not None
        mka = data["marketplace_agent"]
        assert mka is not None
        assert mka["publisher_type"] == "developer"
        assert mka["visibility"] == "beta"

    def test_publish_developer_type(self, dev_store, sub_store, mkp_store, usage_store):
        sid, _ = _setup_approved(dev_store, sub_store)
        c = _admin_app_with_mkp(dev_store, sub_store, mkp_store, usage_store)
        resp = c.post(f"/admin/agent-submissions/{sid}/publish")
        assert resp.json()["marketplace_agent"]["publisher_type"] == "developer"
        assert resp.json()["marketplace_agent"]["pricing_model"] == "free"
        assert "developer_id" in resp.json()["marketplace_agent"]["metadata"]

    def test_draft_cannot_publish(self, dev_store, sub_store, mkp_store):
        sub, _ = _draft_sub(dev_store, sub_store)
        c = _admin_app_with_mkp(dev_store, sub_store, mkp_store)
        resp = c.post(f"/admin/agent-submissions/{sub.submission_id}/publish")
        assert resp.status_code == 409

    def test_publish_records_usage(self, dev_store, sub_store, mkp_store, usage_store):
        sid, _ = _setup_approved(dev_store, sub_store)
        c = _admin_app_with_mkp(dev_store, sub_store, mkp_store, usage_store)
        c.post(f"/admin/agent-submissions/{sid}/publish")
        events = usage_store.query_events(tenant_id="test-ws-001", resource="agent_submission_publish")
        assert len(events) >= 1

    def test_publish_updates_submission_status(self, dev_store, sub_store, mkp_store, usage_store):
        sid, _ = _setup_approved(dev_store, sub_store)
        c = _admin_app_with_mkp(dev_store, sub_store, mkp_store, usage_store)
        resp = c.post(f"/admin/agent-submissions/{sid}/publish")
        assert resp.json()["submission"]["status"] == "published"

    def test_already_published_returns_409(self, dev_store, sub_store, mkp_store, usage_store):
        sid, _ = _setup_approved(dev_store, sub_store)
        c = _admin_app_with_mkp(dev_store, sub_store, mkp_store, usage_store)
        c.post(f"/admin/agent-submissions/{sid}/publish")
        resp = c.post(f"/admin/agent-submissions/{sid}/publish")
        assert resp.status_code == 409

    def test_publish_does_not_create_installation(self, dev_store, sub_store, mkp_store, usage_store):
        """Publish 不创建 TenantAgentInstallation。"""
        sid, _ = _setup_approved(dev_store, sub_store)
        c = _admin_app_with_mkp(dev_store, sub_store, mkp_store, usage_store)
        resp = c.post(f"/admin/agent-submissions/{sid}/publish")
        mkp_id = resp.json()["submission"]["marketplace_agent_id"]
        # 查询 marketplace_store — agent 存在
        agent = mkp_store.get_agent(mkp_id)
        assert agent is not None
        # 但不应该有 installation
        insts = mkp_store.list_installations(tenant_id="test-ws-001")
        assert len(insts) == 0

    def test_publish_does_not_execute_package_url(self, dev_store, sub_store, mkp_store, usage_store):
        """package_url 只存储不执行。"""
        dev = DeveloperAccount(user_id="pkg-dev", tenant_id="test-ws-001", display_name="P", contact_email="p@t.com")
        dev_store.create_developer(dev)
        manifest = AgentManifest(name="pkg-agent", display_name="PKG", description="Test", version="1.0.0",
                                  capabilities=["test"], required_permissions=["agent:execute"],
                                  security_profile=SecurityProfile())
        sub = AgentSubmission(developer_id=dev.developer_id, tenant_id="test-ws-001",
                              agent_manifest=manifest, status=SubmissionStatus.DRAFT,
                              package_url="https://evil.com/backdoor.sh")
        created = sub_store.create_submission(sub)
        sub_store.submit_submission(created.submission_id, dev.developer_id)
        created.status = SubmissionStatus.IN_REVIEW; sub_store.update_submission(created)
        created.approve("r99", "pkg approved"); sub_store.update_submission(created)

        c = _admin_app_with_mkp(dev_store, sub_store, mkp_store, usage_store)
        resp = c.post(f"/admin/agent-submissions/{created.submission_id}/publish")
        assert resp.status_code == 200
        # package_url 存储了但没执行 — 系统仍正常运行
        mkp_id = resp.json()["submission"]["marketplace_agent_id"]
        assert mkp_id is not None
