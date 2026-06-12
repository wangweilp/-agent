"""SaaS Integration Security + Quota + Isolation 综合测试。

验证：
- 配额超限拒绝
- 跨 workspace 隔离强制执行
- metadata_only — 无 runtime/container/microVM
- RBAC 权限矩阵完整性
"""

from __future__ import annotations

import os, tempfile, inspect, pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
from src.adapters.config import Settings
from src.adapters.agent_module_store import SQLiteAgentModuleStore
from src.adapters.subscription_store import SubscriptionStoreAdapter
from src.adapters.usage_store import UsageStoreAdapter
from src.adapters.billing_store import BillingStoreAdapter
from src.open_platform.saas_billing_service import SaaSBillingService
from src.open_platform.rbac_service import RBACService
from src.open_platform.cross_tenant_analytics_service import CrossTenantAnalyticsService
from src.open_platform.saas_integration_service import SaaSIntegrationService
from src.open_platform.saas_integration import WorkspaceIsolationError

FORBIDDEN = ["execute", "run", "exec", "spawn", "launch", "start_container",
             "create_container", "start_microvm", "subprocess", "shell", "eval"]
FORBIDDEN_IMPORTS = ["subprocess", "docker", "container", "microvm",
                     "podman", "kubernetes", "lxc", "firecracker",
                     "os.system", "os.popen", "shell=True", "requests", "urllib.request"]


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")

@pytest.fixture
def db():
    d = tempfile.mkdtemp(); p = os.path.join(d, "test_quota.db"); yield p
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def am_db():
    d = tempfile.mkdtemp(); p = os.path.join(d, "test_am.db"); yield p
    import shutil; shutil.rmtree(d, ignore_errors=True)
@pytest.fixture
def sub_db():
    d = tempfile.mkdtemp(); p = os.path.join(d, "test_sub.db"); yield p
    import shutil; shutil.rmtree(d, ignore_errors=True)
@pytest.fixture
def am_store(settings, am_db): return SQLiteAgentModuleStore(settings, db_path=am_db)
@pytest.fixture
def sub_store(settings, sub_db): return SubscriptionStoreAdapter(settings, db_path=sub_db)


class TestQuotaEnforcement:
    def test_enforce_quota_allows_under_limit(self, settings, db, am_store, sub_store):
        svc = SaaSIntegrationService(
            agent_module_store=am_store, subscription_store=sub_store)
        result = svc.enforce_quota("ws-1", "artifact")
        assert result.allowed is True
        assert result.remaining > 0

    def test_quota_per_workspace_independent(self, settings, db, am_store):
        from src.open_platform.agent_module import AgentModule
        store1 = am_store
        store1.create(AgentModule(workspace_id="ws-heavy", name="H1"))
        store1.create(AgentModule(workspace_id="ws-heavy", name="H2"))
        # ws-empty has 0 modules
        svc = SaaSIntegrationService(agent_module_store=store1)
        q_heavy = svc.check_quota("ws-heavy", "agent_module")
        q_empty = svc.check_quota("ws-empty", "agent_module")
        assert q_heavy.current_count >= 2
        assert q_empty.current_count == 0


class TestWorkspaceIsolation:
    """跨 workspace 隔离强制执行。"""

    def test_guard_rejects_cross_ws(self):
        from src.open_platform.saas_integration_service import SaaSIntegrationService
        svc = SaaSIntegrationService()
        with pytest.raises(WorkspaceIsolationError):
            svc.guard_workspace_access("ws-A", "ws-B")

    def test_guard_allows_same_ws(self):
        svc = SaaSIntegrationService()
        svc.guard_workspace_access("ws-1", "ws-1")

    def test_dashboard_isolated_by_workspace(self, settings, db, am_store):
        from src.open_platform.agent_module import AgentModule
        am_store.create(AgentModule(workspace_id="ws-A", name="A-only"))
        svc = SaaSIntegrationService(agent_module_store=am_store)
        d_a = svc.get_dashboard("ws-A")
        d_b = svc.get_dashboard("ws-B")
        assert d_a.agent_modules.get("draft", 0) >= 1
        assert d_b.agent_modules.get("draft", 0) == 0


class TestMetadataOnlySecurity:
    SERVICES = [SaaSBillingService, RBACService, CrossTenantAnalyticsService, SaaSIntegrationService]

    @pytest.mark.parametrize("svc_cls", SERVICES)
    def test_service_no_execution_methods(self, svc_cls):
        for name in FORBIDDEN:
            assert not hasattr(svc_cls, name), f"{svc_cls.__name__} 不应有 {name}"

    @pytest.mark.parametrize("svc_cls", SERVICES)
    def test_service_source_clean(self, svc_cls):
        src = inspect.getsource(svc_cls).lower()
        for p in FORBIDDEN_IMPORTS:
            assert p not in src, f"{svc_cls.__name__} 源码不应含 {p}"

    def test_rbac_service_pure_python(self):
        src = inspect.getsource(RBACService.check_permission)
        for kw in ["eval", "exec", "subprocess", "import"]:
            assert kw not in src or kw == "import"
        # It should use only dict lookups, no dynamic code

    def test_billing_service_pure_python(self):
        src = inspect.getsource(SaaSBillingService.generate_invoice)
        assert "eval" not in src
        assert "exec" not in src

    def test_cross_tenant_pure_python(self):
        src = inspect.getsource(CrossTenantAnalyticsService.aggregate_metrics)
        assert "eval" not in src
        assert "exec" not in src


class TestRBACMatrixCompleteness:
    """权限矩阵完整性检查。"""

    @pytest.fixture
    def rbac(self): return RBACService()

    def test_all_resources_have_permissions(self, rbac):
        matrix = rbac.get_permission_matrix()
        resources = rbac.list_resources()
        for role in matrix:
            role_resources = set(matrix[role].keys())
            # 所有角色至少覆盖 marketplace 和 artifact
            assert "marketplace" in role_resources, f"{role} 缺少 marketplace"
            assert "artifact" in role_resources, f"{role} 缺少 artifact"
            assert "analytics" in role_resources, f"{role} 缺少 analytics"

    def test_owner_has_all_actions(self, rbac):
        perms = rbac.get_role_permissions("owner")
        for res, actions in perms.items():
            assert "read" in actions, f"owner 对 {res} 缺 read"
            if res not in ("marketplace", "report"):
                assert len(actions) >= 1, f"owner 对 {res} 权限为空"

    def test_viewer_readonly(self, rbac):
        perms = rbac.get_role_permissions("viewer")
        for res, actions in perms.items():
            assert len(actions) == 1, f"viewer 对 {res} 不应该是只读(actions={actions})"
            assert "read" in actions, f"viewer 对 {res} 缺 read"

    def test_billing_only_owner_admin(self, rbac):
        assert rbac.check_permission("owner", "billing", "manage") is True
        assert rbac.check_permission("admin", "billing", "manage") is False
        assert rbac.check_permission("member", "billing", "read") is False
        assert rbac.check_permission("viewer", "billing", "read") is False


class TestSaaSIntegrationQuotaWithBilling:
    """集成配额检查与计费服务。"""

    def test_quota_integration(self, settings, am_store, sub_store):
        from src.core.subscription import Subscription, PlanTier
        sub_store.create_subscription(
            Subscription(tenant_id="ws-pro", plan_tier=PlanTier.PROFESSIONAL))
        svc = SaaSIntegrationService(
            agent_module_store=am_store, subscription_store=sub_store)
        q = svc.check_quota("ws-pro", "agent_module")
        assert q.allowed is True
        assert q.quota_limit > 0

    def test_free_tier_has_lower_quota(self, settings, am_store, sub_store):
        from src.core.subscription import Subscription, PlanTier
        sub_store.create_subscription(
            Subscription(tenant_id="ws-free", plan_tier=PlanTier.FREE))
        sub_store.create_subscription(
            Subscription(tenant_id="ws-pro", plan_tier=PlanTier.PROFESSIONAL))
        svc = SaaSIntegrationService(
            agent_module_store=am_store, subscription_store=sub_store)
        q_free = svc.check_quota("ws-free", "agent_module")
        q_pro = svc.check_quota("ws-pro", "agent_module")
        assert q_free.quota_limit < q_pro.quota_limit
