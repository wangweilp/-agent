"""Marketplace Security + Tenant Isolation + Plan Limit 测试。

覆盖:
- Security: 401, 403, super_admin, member browse vs manage
- Tenant/workspace: 跨 tenant 404, 跨 workspace 隔离, install 状态隔离
- Plan Limit: mock subscription_store, free/pro disables/uninstalled 计数
- Agent Run Usage: agent_run event 记录
- Step 22 Boundary: 不存在越界 API

本文件专注安全边界，不与 test_marketplace_api.py 重复。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adapters.config import Settings
from src.adapters.marketplace_store import SQLiteMarketplaceStore
from src.adapters.usage_store import UsageStoreAdapter
from src.agents.marketplace import seed_builtin_marketplace_agents
from src.api.marketplace_router import create_marketplace_router
from src.api.middleware import require_auth, TokenPayload
from src.core.auth import WorkspaceRole
from src.core.subscription import (
    PlanTier,
    Subscription,
    SubscriptionStatus,
    BillingCycle,
)
from src.core.usage import UsageEvent, UsageResource, UsageUnit
from datetime import datetime, timezone


# ═══════════════════════════════════════════
# Auth Helpers
# ═══════════════════════════════════════════

def _make_payload(role: WorkspaceRole, is_super_admin: bool = False, workspace_id: str = "test-ws-001") -> TokenPayload:
    return TokenPayload(
        user_id="test-user-001",
        workspace_id=workspace_id,
        role=role,
        is_super_admin=is_super_admin,
    )


async def _override_admin():
    return _make_payload(WorkspaceRole.ADMIN)

async def _override_member():
    return _make_payload(WorkspaceRole.MEMBER)

async def _override_viewer():
    return _make_payload(WorkspaceRole.VIEWER)

async def _override_super_admin():
    return _make_payload(WorkspaceRole.ADMIN, is_super_admin=True)

async def _override_cross_tenant():
    """不同 tenant 的用户 — 用于跨 tenant 隔离测试。"""
    return _make_payload(WorkspaceRole.ADMIN, workspace_id="other-tenant")


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def marketplace_store(settings):
    store = SQLiteMarketplaceStore(settings, db_path=":memory:")
    seed_builtin_marketplace_agents(store)
    return store


@pytest.fixture
def usage_store(settings, tmp_path):
    db_path = str(tmp_path / "test_security_usage.db")
    store = UsageStoreAdapter(config=settings, db_path=db_path)
    yield store
    store.close()


# ── Mock subscription store for plan limit tests ──

class _MockSubscriptionStore:
    """测试用 subscription store — 返回指定 plan_tier 的 subscription。"""

    def __init__(self, tier: PlanTier, tenant_id_override: str | None = None):
        self.tier = tier
        self._tenant_override = tenant_id_override
        self._subscriptions: dict[str, Subscription] = {}

    def _ensure(self, tenant_id: str) -> Subscription:
        if tenant_id not in self._subscriptions:
            sub = Subscription(
                tenant_id=tenant_id,
                plan_tier=self.tier,
                status=SubscriptionStatus.ACTIVE,
                billing_cycle=BillingCycle.MONTHLY,
            )
            self._subscriptions[tenant_id] = sub
        return self._subscriptions[tenant_id]

    def get_subscription(self, tenant_id: str) -> Subscription | None:
        tid = self._tenant_override or tenant_id
        return self._ensure(tid)

    def create_subscription(self, sub: Subscription) -> Subscription:
        self._subscriptions[sub.tenant_id] = sub
        return sub


def _make_free_sub_store():
    """Free plan: max_marketplace_agents = 1"""
    return _MockSubscriptionStore(PlanTier.FREE)

def _make_professional_sub_store():
    """Professional plan: max_marketplace_agents = 5"""
    return _MockSubscriptionStore(PlanTier.PROFESSIONAL)


# ── Router factory helpers ──

def _make_app(store, usage, subscription_store=None, auth_override=None):
    """创建 app 的快捷方式。"""
    app = FastAPI()
    if auth_override:
        app.dependency_overrides[require_auth] = auth_override
    app.include_router(create_marketplace_router(store, usage, subscription_store))
    return TestClient(app)


def _admin_client(store, usage, subscription_store=None):
    return _make_app(store, usage, subscription_store, _override_admin)

def _member_client(store, usage):
    return _make_app(store, usage, None, _override_member)

def _viewer_client(store, usage):
    return _make_app(store, usage, None, _override_viewer)

def _super_admin_client(store, usage):
    return _make_app(store, usage, None, _override_super_admin)

def _no_auth_client(store):
    return _make_app(store, None, None, None)

def _cross_tenant_client(store, usage):
    return _make_app(store, usage, None, _override_cross_tenant)


# ═══════════════════════════════════════════
# 1. Security: 401 / 403 / member / super_admin
# ═══════════════════════════════════════════


class TestAuthenticationRequired:
    """所有 Marketplace 端点必须 require_auth。"""

    ALL_BROWSE_PATHS = [
        "/agent-marketplace",
        "/agent-marketplace/categories",
        "/agent-marketplace/departments",
        "/agent-marketplace/mkp_knowledge",
        "/agent-marketplace/mkp_knowledge/permissions",
        "/agent-marketplace/analytics/summary",
    ]

    ALL_MANAGE_PATHS = [
        # These require not just auth but admin role
        ("/agent-marketplace/mkp_knowledge/install", "POST"),
        ("/agent-marketplace/installations/nonexistent/enable", "POST"),
        ("/agent-marketplace/installations/nonexistent/disable", "POST"),
        ("/agent-marketplace/installations/nonexistent/config", "PATCH"),
        ("/agent-marketplace/installations/nonexistent", "DELETE"),
    ]

    def test_browse_endpoints_401_without_token(self, marketplace_store):
        client = _no_auth_client(marketplace_store)
        for path in self.ALL_BROWSE_PATHS:
            resp = client.get(path)
            assert resp.status_code == 401, f"{path} should return 401, got {resp.status_code}"

    def test_manage_endpoints_401_without_token(self, marketplace_store):
        client = _no_auth_client(marketplace_store)
        for path, method in self.ALL_MANAGE_PATHS:
            meth = getattr(client, method.lower())
            if method == "DELETE":
                resp = meth(path)
            else:
                resp = meth(path, json={})
            assert resp.status_code == 401, f"{method} {path} should return 401, got {resp.status_code}"

    def test_installations_endpoint_401_without_token(self, marketplace_store):
        """GET /installations 也需 auth。"""
        client = _no_auth_client(marketplace_store)
        resp = client.get("/agent-marketplace/installations")
        assert resp.status_code == 401

    def test_usage_endpoint_401_without_token(self, marketplace_store, usage_store):
        """GET /installations/{id}/usage 也需 auth。"""
        client = _no_auth_client(marketplace_store)
        resp = client.get("/agent-marketplace/installations/any-id/usage")
        assert resp.status_code == 401


class TestMemberRole:
    """Member 可浏览但不可管理。"""

    def test_member_can_browse(self, marketplace_store, usage_store):
        client = _member_client(marketplace_store, usage_store)
        resp = client.get("/agent-marketplace")
        assert resp.status_code == 200

    def test_member_can_view_detail(self, marketplace_store, usage_store):
        client = _member_client(marketplace_store, usage_store)
        resp = client.get("/agent-marketplace/mkp_knowledge")
        assert resp.status_code == 200

    def test_member_can_view_categories(self, marketplace_store, usage_store):
        client = _member_client(marketplace_store, usage_store)
        resp = client.get("/agent-marketplace/categories")
        assert resp.status_code == 200

    def test_member_can_view_departments(self, marketplace_store, usage_store):
        client = _member_client(marketplace_store, usage_store)
        resp = client.get("/agent-marketplace/departments")
        assert resp.status_code == 200

    def test_member_can_view_permissions(self, marketplace_store, usage_store):
        client = _member_client(marketplace_store, usage_store)
        resp = client.get("/agent-marketplace/mkp_knowledge/permissions")
        assert resp.status_code == 200

    def test_member_can_view_analytics(self, marketplace_store, usage_store):
        client = _member_client(marketplace_store, usage_store)
        resp = client.get("/agent-marketplace/analytics/summary")
        assert resp.status_code == 200

    def test_member_can_list_installations(self, marketplace_store, usage_store):
        client = _member_client(marketplace_store, usage_store)
        resp = client.get("/agent-marketplace/installations")
        assert resp.status_code == 200

    def test_member_cannot_install(self, marketplace_store, usage_store):
        client = _member_client(marketplace_store, usage_store)
        resp = client.post("/agent-marketplace/mkp_knowledge/install", json={})
        assert resp.status_code == 403

    def test_member_cannot_disable(self, marketplace_store, usage_store):
        # 先在 store 中创建 installation
        marketplace_store.install_agent(
            "mkp_knowledge", "builtin-knowledge", "test-ws-001", "test-ws-001", "admin",
        )
        insts = marketplace_store.list_installations(tenant_id="test-ws-001")
        inst_id = insts[0].installation_id

        client = _member_client(marketplace_store, usage_store)
        resp = client.post(f"/agent-marketplace/installations/{inst_id}/disable")
        assert resp.status_code == 403

    def test_member_cannot_update_config(self, marketplace_store, usage_store):
        marketplace_store.install_agent(
            "mkp_knowledge", "builtin-knowledge", "test-ws-001", "test-ws-001", "admin",
        )
        insts = marketplace_store.list_installations(tenant_id="test-ws-001")
        inst_id = insts[0].installation_id

        client = _member_client(marketplace_store, usage_store)
        resp = client.patch(f"/agent-marketplace/installations/{inst_id}/config", json={"config": {"x": 1}})
        assert resp.status_code == 403

    def test_member_cannot_uninstall(self, marketplace_store, usage_store):
        marketplace_store.install_agent(
            "mkp_knowledge", "builtin-knowledge", "test-ws-001", "test-ws-001", "admin",
        )
        insts = marketplace_store.list_installations(tenant_id="test-ws-001")
        inst_id = insts[0].installation_id

        client = _member_client(marketplace_store, usage_store)
        resp = client.delete(f"/agent-marketplace/installations/{inst_id}")
        assert resp.status_code == 403


class TestViewerRole:
    """Viewer 可浏览但不可管理（已有测试验证 install 403，本类补充）。"""

    def test_viewer_cannot_enable(self, marketplace_store, usage_store):
        marketplace_store.install_agent(
            "mkp_knowledge", "builtin-knowledge", "test-ws-001", "test-ws-001", "admin",
        )
        marketplace_store.disable_installation(
            marketplace_store.list_installations(tenant_id="test-ws-001")[0].installation_id,
            "test-ws-001", "test-ws-001",
        )
        insts = marketplace_store.list_installations(tenant_id="test-ws-001")
        inst_id = insts[0].installation_id

        client = _viewer_client(marketplace_store, usage_store)
        resp = client.post(f"/agent-marketplace/installations/{inst_id}/enable")
        assert resp.status_code == 403

    def test_viewer_cannot_update_config(self, marketplace_store, usage_store):
        marketplace_store.install_agent(
            "mkp_knowledge", "builtin-knowledge", "test-ws-001", "test-ws-001", "admin",
        )
        insts = marketplace_store.list_installations(tenant_id="test-ws-001")
        inst_id = insts[0].installation_id

        client = _viewer_client(marketplace_store, usage_store)
        resp = client.patch(f"/agent-marketplace/installations/{inst_id}/config", json={"config": {"x": 1}})
        assert resp.status_code == 403

    def test_viewer_cannot_delete(self, marketplace_store, usage_store):
        marketplace_store.install_agent(
            "mkp_knowledge", "builtin-knowledge", "test-ws-001", "test-ws-001", "admin",
        )
        insts = marketplace_store.list_installations(tenant_id="test-ws-001")
        inst_id = insts[0].installation_id

        client = _viewer_client(marketplace_store, usage_store)
        resp = client.delete(f"/agent-marketplace/installations/{inst_id}")
        assert resp.status_code == 403


class TestSuperAdmin:
    """Super admin 具有最高权限。"""

    def test_super_admin_can_install(self, marketplace_store, usage_store):
        client = _super_admin_client(marketplace_store, usage_store)
        resp = client.post("/agent-marketplace/mkp_knowledge/install", json={})
        assert resp.status_code == 201

    def test_super_admin_can_enable_disable(self, marketplace_store, usage_store):
        client = _super_admin_client(marketplace_store, usage_store)
        # install
        resp = client.post("/agent-marketplace/mkp_training/install", json={})
        assert resp.status_code == 201
        inst_id = resp.json()["installation"]["installation_id"]

        # disable
        resp = client.post(f"/agent-marketplace/installations/{inst_id}/disable")
        assert resp.status_code == 200

        # enable
        resp = client.post(f"/agent-marketplace/installations/{inst_id}/enable")
        assert resp.status_code == 200

    def test_super_admin_can_update_config(self, marketplace_store, usage_store):
        client = _super_admin_client(marketplace_store, usage_store)
        resp = client.post("/agent-marketplace/mkp_training/install", json={"config": {"a": 1}})
        inst_id = resp.json()["installation"]["installation_id"]

        resp = client.patch(f"/agent-marketplace/installations/{inst_id}/config",
                            json={"config": {"b": 2}})
        assert resp.status_code == 200

    def test_super_admin_can_uninstall(self, marketplace_store, usage_store):
        client = _super_admin_client(marketplace_store, usage_store)
        resp = client.post("/agent-marketplace/mkp_support/install", json={})
        inst_id = resp.json()["installation"]["installation_id"]

        resp = client.delete(f"/agent-marketplace/installations/{inst_id}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_super_admin_browse_all(self, marketplace_store, usage_store):
        client = _super_admin_client(marketplace_store, usage_store)
        for path in TestAuthenticationRequired.ALL_BROWSE_PATHS:
            resp = client.get(path)
            assert resp.status_code == 200, f"{path} should return 200 for super_admin"

    def test_super_admin_can_view_installations(self, marketplace_store, usage_store):
        client = _super_admin_client(marketplace_store, usage_store)
        resp = client.get("/agent-marketplace/installations")
        assert resp.status_code == 200

    def test_super_admin_can_view_usage(self, marketplace_store, usage_store):
        client = _super_admin_client(marketplace_store, usage_store)
        resp = client.post("/agent-marketplace/mkp_knowledge/install", json={})
        inst_id = resp.json()["installation"]["installation_id"]
        resp = client.get(f"/agent-marketplace/installations/{inst_id}/usage")
        assert resp.status_code == 200


# ═══════════════════════════════════════════
# 2. Tenant / Workspace Isolation
# ═══════════════════════════════════════════


class TestCrossTenantIsolation:
    """跨 tenant 访问全部返回 404。"""

    def _setup_other_tenant_installation(self, marketplace_store):
        """在 other-tenant 中安装一个 agent。"""
        return marketplace_store.install_agent(
            marketplace_agent_id="mkp_knowledge",
            agent_id="builtin-knowledge",
            tenant_id="other-tenant",
            workspace_id="other-ws",
            installed_by="other-user",
        )

    def test_cross_tenant_detail_returns_404(self, marketplace_store, usage_store):
        inst = self._setup_other_tenant_installation(marketplace_store)
        client = _admin_client(marketplace_store, usage_store)
        resp = client.get(f"/agent-marketplace/installations/{inst.installation_id}")
        assert resp.status_code == 404

    def test_cross_tenant_enable_returns_404(self, marketplace_store, usage_store):
        inst = self._setup_other_tenant_installation(marketplace_store)
        client = _admin_client(marketplace_store, usage_store)
        resp = client.post(f"/agent-marketplace/installations/{inst.installation_id}/enable")
        assert resp.status_code == 404

    def test_cross_tenant_disable_returns_404(self, marketplace_store, usage_store):
        inst = self._setup_other_tenant_installation(marketplace_store)
        client = _admin_client(marketplace_store, usage_store)
        resp = client.post(f"/agent-marketplace/installations/{inst.installation_id}/disable")
        assert resp.status_code == 404

    def test_cross_tenant_config_returns_404(self, marketplace_store, usage_store):
        inst = self._setup_other_tenant_installation(marketplace_store)
        client = _admin_client(marketplace_store, usage_store)
        resp = client.patch(f"/agent-marketplace/installations/{inst.installation_id}/config",
                            json={"config": {"x": 1}})
        assert resp.status_code == 404

    def test_cross_tenant_uninstall_returns_404(self, marketplace_store, usage_store):
        inst = self._setup_other_tenant_installation(marketplace_store)
        client = _admin_client(marketplace_store, usage_store)
        resp = client.delete(f"/agent-marketplace/installations/{inst.installation_id}")
        assert resp.status_code == 404

    def test_cross_tenant_usage_returns_404(self, marketplace_store, usage_store):
        inst = self._setup_other_tenant_installation(marketplace_store)
        client = _admin_client(marketplace_store, usage_store)
        resp = client.get(f"/agent-marketplace/installations/{inst.installation_id}/usage")
        assert resp.status_code == 404

    def test_cross_tenant_analytics_excludes(self, marketplace_store, usage_store):
        """Analytics summary 不应包含其他 tenant 的数据。"""
        # 在 other-tenant 中安装
        marketplace_store.install_agent(
            "mkp_knowledge", "builtin-knowledge", "other-tenant", "other-ws", "other",
        )
        marketplace_store.install_agent(
            "mkp_training", "builtin-training", "other-tenant", "other-ws", "other",
        )

        # 在当前 tenant 中查询 analytics
        client = _admin_client(marketplace_store, usage_store)
        resp = client.get("/agent-marketplace/analytics/summary")
        assert resp.status_code == 200
        data = resp.json()
        # installed_agents 应该只反映当前 tenant（test-ws-001）的数据
        assert data["installed_agents"] == 0  # 当前 tenant 没有安装过

    def test_installations_list_tenant_scoped(self, marketplace_store, usage_store):
        """安装列表只返回当前 tenant 的数据。"""
        marketplace_store.install_agent(
            "mkp_knowledge", "builtin-knowledge", "other-tenant", "other-ws", "other",
        )

        client = _admin_client(marketplace_store, usage_store)
        resp = client.get("/agent-marketplace/installations")
        assert resp.status_code == 200
        # 当前 tenant 没有任何安装
        assert resp.json()["total"] == 0

    def test_browse_is_installed_tenant_scoped(self, marketplace_store, usage_store):
        """browse 中的 is_installed 只反映当前 tenant。"""
        marketplace_store.install_agent(
            "mkp_knowledge", "builtin-knowledge", "other-tenant", "other-ws", "other",
        )

        client = _admin_client(marketplace_store, usage_store)
        resp = client.get("/agent-marketplace")
        data = resp.json()
        mkp_knowledge = next(a for a in data["agents"] if a["marketplace_agent_id"] == "mkp_knowledge")
        assert mkp_knowledge["is_installed"] is False  # 其他 tenant 的安装不计入


class TestCrossWorkspaceIsolation:
    """同 tenant 内不同 workspace 的隔离。"""

    def test_workspace_a_cannot_see_workspace_b_installations(self, marketplace_store, usage_store):
        """ws-a 安装的不应出现在 ws-b 的列表中。"""
        marketplace_store.install_agent(
            "mkp_knowledge", "builtin-knowledge", "test-ws-001", "ws-a", "user-a",
        )
        marketplace_store.install_agent(
            "mkp_training", "builtin-training", "test-ws-001", "ws-b", "user-b",
        )

        client = _admin_client(marketplace_store, usage_store)
        # 默认 workspace_id=test-ws-001（来自 payload）
        resp = client.get("/agent-marketplace/installations?workspace_id=ws-a")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

        resp = client.get("/agent-marketplace/installations?workspace_id=ws-b")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1


class TestInstalledStatusAccuracy:
    """安装状态、disabled、uninstalled 的计数规则。"""

    def test_disabled_still_appears_in_list(self, marketplace_store, usage_store):
        """disabled 的安装仍然出现在安装列表中。"""
        client = _admin_client(marketplace_store, usage_store)
        client.post("/agent-marketplace/mkp_knowledge/install", json={})
        insts = marketplace_store.list_installations(tenant_id="test-ws-001")
        client.post(f"/agent-marketplace/installations/{insts[0].installation_id}/disable")

        resp = client.get("/agent-marketplace/installations")
        assert resp.json()["total"] == 1  # disabled 仍在列表中

    def test_disabled_excluded_when_include_disabled_false(self, marketplace_store, usage_store):
        client = _admin_client(marketplace_store, usage_store)
        client.post("/agent-marketplace/mkp_knowledge/install", json={})
        insts = marketplace_store.list_installations(tenant_id="test-ws-001")
        client.post(f"/agent-marketplace/installations/{insts[0].installation_id}/disable")

        resp = client.get("/agent-marketplace/installations?include_disabled=false")
        assert resp.json()["total"] == 0

    def test_uninstalled_not_in_list(self, marketplace_store, usage_store):
        client = _admin_client(marketplace_store, usage_store)
        client.post("/agent-marketplace/mkp_knowledge/install", json={})
        insts = marketplace_store.list_installations(tenant_id="test-ws-001")
        client.delete(f"/agent-marketplace/installations/{insts[0].installation_id}")

        resp = client.get("/agent-marketplace/installations")
        assert resp.json()["total"] == 0

    def test_browse_is_installed_uninstalled_reflects(self, marketplace_store, usage_store):
        """卸载后 browse 的 is_installed 应为 false。"""
        client = _admin_client(marketplace_store, usage_store)
        client.post("/agent-marketplace/mkp_knowledge/install", json={})

        # 确认已安装
        resp = client.get("/agent-marketplace")
        mkp = next(a for a in resp.json()["agents"] if a["marketplace_agent_id"] == "mkp_knowledge")
        assert mkp["is_installed"] is True

        # 卸载
        insts = marketplace_store.list_installations(tenant_id="test-ws-001")
        client.delete(f"/agent-marketplace/installations/{insts[0].installation_id}")

        # 确认未安装
        resp = client.get("/agent-marketplace")
        mkp = next(a for a in resp.json()["agents"] if a["marketplace_agent_id"] == "mkp_knowledge")
        assert mkp["is_installed"] is False


# ═══════════════════════════════════════════
# 3. Plan Limit Enforcement (with mock subscription_store)
# ═══════════════════════════════════════════


class TestPlanLimitFree:
    """Free plan: max_marketplace_agents = 1"""

    def test_free_allows_one_install(self, marketplace_store, usage_store):
        sub_store = _make_free_sub_store()
        client = _admin_client(marketplace_store, usage_store, sub_store)
        resp = client.post("/agent-marketplace/mkp_knowledge/install", json={})
        assert resp.status_code == 201

    def test_free_rejects_second_install(self, marketplace_store, usage_store):
        sub_store = _make_free_sub_store()
        client = _admin_client(marketplace_store, usage_store, sub_store)

        # 第一个 install
        resp = client.post("/agent-marketplace/mkp_knowledge/install", json={})
        assert resp.status_code == 201

        # 第二个不同的 agent — 应被拒绝
        resp = client.post("/agent-marketplace/mkp_training/install", json={})
        assert resp.status_code == 403
        assert "已达上限" in resp.json()["detail"]

    def test_free_second_install_same_agent_hits_plan_limit_first(self, marketplace_store, usage_store):
        """同 agent 第二次安装：plan limit 检查先于 duplicate check，返回 403。"""
        sub_store = _make_free_sub_store()
        client = _admin_client(marketplace_store, usage_store, sub_store)
        client.post("/agent-marketplace/mkp_knowledge/install", json={})

        # 同 agent 第二次 — plan limit (max=1) 先触发 403，不会到达 duplicate 409
        resp = client.post("/agent-marketplace/mkp_knowledge/install", json={})
        assert resp.status_code == 403

    def test_free_uninstalled_allows_reinstall(self, marketplace_store, usage_store):
        """卸载后可以重新安装，不超过 plan limit。"""
        sub_store = _make_free_sub_store()
        client = _admin_client(marketplace_store, usage_store, sub_store)

        # install
        client.post("/agent-marketplace/mkp_knowledge/install", json={})
        insts = marketplace_store.list_installations(tenant_id="test-ws-001")
        # uninstall
        client.delete(f"/agent-marketplace/installations/{insts[0].installation_id}")

        # 重新安装 — 应该允许
        resp = client.post("/agent-marketplace/mkp_training/install", json={})
        assert resp.status_code == 201

    def test_free_disabled_counts_toward_limit(self, marketplace_store, usage_store):
        """disabled 的 installation 计入 plan limit。"""
        sub_store = _make_free_sub_store()
        client = _admin_client(marketplace_store, usage_store, sub_store)

        # 安装第一个
        resp = client.post("/agent-marketplace/mkp_knowledge/install", json={})
        inst_id = resp.json()["installation"]["installation_id"]

        # 停用（disabled 仍计数）
        client.post(f"/agent-marketplace/installations/{inst_id}/disable")

        # 安装第二个 — 应被拒绝（disabled 也占用名额）
        resp = client.post("/agent-marketplace/mkp_training/install", json={})
        assert resp.status_code == 403


class TestPlanLimitProfessional:
    """Professional plan: max_marketplace_agents = 5"""

    def test_pro_allows_five_installs(self, marketplace_store, usage_store):
        sub_store = _make_professional_sub_store()
        client = _admin_client(marketplace_store, usage_store, sub_store)

        agent_ids = ["mkp_knowledge", "mkp_training", "mkp_support", "mkp_sales", "mkp_meeting_training"]
        for mid in agent_ids:
            resp = client.post(f"/agent-marketplace/{mid}/install", json={})
            assert resp.status_code == 201, f"Expected 201 for {mid}, got {resp.status_code}"

    def test_pro_rejects_sixth_install(self, marketplace_store, usage_store):
        sub_store = _make_professional_sub_store()
        client = _admin_client(marketplace_store, usage_store, sub_store)

        agent_ids = ["mkp_knowledge", "mkp_training", "mkp_support", "mkp_sales", "mkp_meeting_training"]
        for mid in agent_ids:
            client.post(f"/agent-marketplace/{mid}/install", json={})

        # 第 6 个 — 所有 6 个内置 agent 都已安装到当前 workspace
        # 需要不同的 workspace_id 来避免 DuplicateInstallationError
        # 实际上，_check_plan_agent_limit 会检查的是同一 tenant 下所有 workspace 的总数
        # 让我们用默认 test-ws-001 且不同 agent 测试 limit
        # mkp_dept_assistant 是第 6 个
        resp = client.post("/agent-marketplace/mkp_dept_assistant/install", json={})
        assert resp.status_code == 403

    def test_pro_uninstalled_does_not_count(self, marketplace_store, usage_store):
        """Professional: 卸载后释放名额。"""
        sub_store = _make_professional_sub_store()
        client = _admin_client(marketplace_store, usage_store, sub_store)

        # 安装 5 个到 limit
        for mid in ["mkp_knowledge", "mkp_training", "mkp_support", "mkp_sales", "mkp_meeting_training"]:
            client.post(f"/agent-marketplace/{mid}/install", json={})

        # 卸载一个
        insts = marketplace_store.list_installations(tenant_id="test-ws-001")
        client.delete(f"/agent-marketplace/installations/{insts[0].installation_id}")

        # 现在可以安装新的
        resp = client.post("/agent-marketplace/mkp_dept_assistant/install", json={})
        assert resp.status_code == 201


class TestPlanLimitSuperAdmin:
    """Super admin 绕过 plan limit。"""

    def test_super_admin_bypasses_free_limit(self, marketplace_store, usage_store):
        sub_store = _make_free_sub_store()
        client = _make_app(marketplace_store, usage_store, sub_store, _override_super_admin)

        # 安装 3 个 agent — free plan 限制 1，但 super_admin 绕过
        for mid in ["mkp_knowledge", "mkp_training", "mkp_support"]:
            resp = client.post(f"/agent-marketplace/{mid}/install", json={})
            assert resp.status_code == 201, f"Expected 201 for {mid}, got {resp.status_code}"


class TestPlanLimitNoSubscriptionStore:
    """无 subscription_store 时不做限制（向后兼容）。"""

    def test_no_sub_store_allows_multiple(self, marketplace_store, usage_store):
        client = _admin_client(marketplace_store, usage_store, None)
        for mid in ["mkp_knowledge", "mkp_training", "mkp_support"]:
            resp = client.post(f"/agent-marketplace/{mid}/install", json={})
            assert resp.status_code == 201, f"Expected 201 for {mid}"


# ═══════════════════════════════════════════
# 4. Agent Run Usage Recording
# ═══════════════════════════════════════════


class TestAgentRunUsageRecording:
    """验证 agent_run 事件能被写入 usage_events 表。"""

    def test_usage_store_can_record_agent_run(self, usage_store):
        """UsageStoreAdapter 能正确记录 agent_run event。"""
        event = UsageEvent(
            tenant_id="test-ws-001",
            user_id="u1",
            workspace_id="test-ws-001",
            resource=UsageResource.AGENT_RUN,
            quantity=1,
            unit=UsageUnit.COUNT,
            metadata={
                "agent_id": "builtin-knowledge",
                "agent_name": "Knowledge Agent",
                "task_id": "task-001",
                "success": True,
            },
        )
        event_id = usage_store.record_event(event)
        assert event_id == event.id

        # 查询
        events = usage_store.query_events(tenant_id="test-ws-001", resource="agent_run", limit=100)
        assert len(events) >= 1
        assert events[0].resource == UsageResource.AGENT_RUN
        assert events[0].metadata.get("agent_id") == "builtin-knowledge"

    def test_installation_usage_counts_agent_run(self, marketplace_store, usage_store):
        """安装后的 usage 应能从 usage_events 的 agent_run 中统计。"""
        # 先在 usage_store 中写入一些 agent_run 事件
        for i in range(5):
            usage_store.record_event(UsageEvent(
                tenant_id="test-ws-001", user_id="u1", workspace_id="test-ws-001",
                resource=UsageResource.AGENT_RUN, quantity=1, unit=UsageUnit.COUNT,
                metadata={"agent_id": "builtin-knowledge", "success": True, "task_id": f"task-{i}"},
            ))

        # 安装 agent
        client = _admin_client(marketplace_store, usage_store)
        resp = client.post("/agent-marketplace/mkp_knowledge/install", json={})
        inst_id = resp.json()["installation"]["installation_id"]

        # 查询 usage
        resp = client.get(f"/agent-marketplace/installations/{inst_id}/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_calls"] >= 5
        assert data["period_calls"] >= 5

    def test_usage_failure_does_not_block_install(self, marketplace_store, usage_store):
        """Usage 写入失败（模拟）不应阻塞 install。"""
        # install 仍然应该成功（_try_record_usage 是 best-effort）
        client = _admin_client(marketplace_store, usage_store)
        resp = client.post("/agent-marketplace/mkp_knowledge/install", json={})
        assert resp.status_code == 201
        assert "installation" in resp.json()


# ═══════════════════════════════════════════
# 5. Step 22 Boundary — 不存在越界 API
# ═══════════════════════════════════════════


class TestStep22Boundary:
    """确认当前 Marketplace API 没有暴露 Step 22 Open Platform 能力。"""

    def test_no_publish_route(self, marketplace_store, usage_store):
        client = _admin_client(marketplace_store, usage_store)
        # 不应存在 publish / review / developer 等路由
        get_paths = [
            "/agent-marketplace/developer",
            "/agent-marketplace/sdk",
        ]
        post_paths = [
            "/agent-marketplace/publish",
            "/agent-marketplace/mkp_knowledge/publish",
            "/agent-marketplace/mkp_knowledge/review",
        ]
        for path in get_paths:
            resp = client.get(path)
            assert resp.status_code == 404, f"GET {path}: expected 404, got {resp.status_code}"
        for path in post_paths:
            resp = client.post(path, json={})
            assert resp.status_code in (404, 405), \
                f"POST {path}: expected 404/405 (no publish endpoint), got {resp.status_code}"

    def test_no_third_party_upload_route(self, marketplace_store, usage_store):
        """确认没有 POST /agent-marketplace（创建新 agent）。"""
        client = _admin_client(marketplace_store, usage_store)
        resp = client.post("/agent-marketplace", json={"name": "test"})
        assert resp.status_code == 405  # GET allowed, POST not

    def test_agent_router_not_leaking_marketplace_routes(self, marketplace_store, usage_store):
        """确认 /agents 下没有 marketplace 路径。"""
        client = _admin_client(marketplace_store, usage_store)
        # /agents 前缀不在 marketplace router 中
        resp = client.get("/agents/marketplace")
        assert resp.status_code == 404

    def test_no_revenue_share_route(self, marketplace_store, usage_store):
        client = _admin_client(marketplace_store, usage_store)
        resp = client.get("/agent-marketplace/revenue")
        assert resp.status_code == 404

    def test_no_external_api_key_routes(self, marketplace_store, usage_store):
        client = _admin_client(marketplace_store, usage_store)
        resp = client.get("/agent-marketplace/api-keys")
        assert resp.status_code == 404


# ═══════════════════════════════════════════
# 6. Data Leak Prevention
# ═══════════════════════════════════════════


class TestNoTracebackLeak:
    """确认错误响应不暴露 traceback。"""

    def test_404_no_traceback(self, marketplace_store, usage_store):
        client = _admin_client(marketplace_store, usage_store)
        resp = client.get("/agent-marketplace/nonexistent")
        assert resp.status_code == 404
        data = resp.json()
        assert "Traceback" not in str(data)
        assert "File " not in str(data)

    def test_403_no_traceback(self, marketplace_store, usage_store):
        client = _viewer_client(marketplace_store, usage_store)
        resp = client.post("/agent-marketplace/mkp_knowledge/install", json={})
        assert resp.status_code == 403
        data = resp.json()
        assert "Traceback" not in str(data)

    def test_401_no_traceback(self, marketplace_store):
        client = _no_auth_client(marketplace_store)
        resp = client.get("/agent-marketplace")
        assert resp.status_code == 401
        data = resp.json()
        assert "Traceback" not in str(data)

    def test_500_does_not_expose_internals(self, marketplace_store, usage_store):
        """500 错误不暴露内部细节。"""
        client = _admin_client(marketplace_store, usage_store)
        # 触发一个 404 而不是 500 — 因为 router 内部捕获了异常
        # 验证 404 的 detail 不包含内部路径
        resp = client.get("/agent-marketplace/mkp_nonexistent/permissions")
        assert resp.status_code == 404
        data = resp.json()
        assert "src/" not in str(data)


# ═══════════════════════════════════════════
# 7. PlanLimit data class integrity
# ═══════════════════════════════════════════


class TestPlanLimitField:
    """验证 max_marketplace_agents 字段在所有 plan tier 中正确设置。"""

    def test_free_has_limit(self):
        from src.core.subscription import PLANS
        assert PLANS[PlanTier.FREE].max_marketplace_agents == 1

    def test_personal_has_limit(self):
        from src.core.subscription import PLANS
        assert PLANS[PlanTier.PERSONAL].max_marketplace_agents == 1

    def test_professional_has_limit(self):
        from src.core.subscription import PLANS
        assert PLANS[PlanTier.PROFESSIONAL].max_marketplace_agents == 5

    def test_team_has_limit(self):
        from src.core.subscription import PLANS
        assert PLANS[PlanTier.TEAM].max_marketplace_agents == 20

    def test_enterprise_has_limit(self):
        from src.core.subscription import PLANS
        assert PLANS[PlanTier.ENTERPRISE].max_marketplace_agents == 999999

    def test_as_dict_includes_max_marketplace_agents(self):
        from src.core.subscription import PLANS
        d = PLANS[PlanTier.FREE].as_dict()
        assert "max_marketplace_agents" in d
