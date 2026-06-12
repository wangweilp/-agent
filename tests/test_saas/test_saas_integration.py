"""SaaS Integration 单元测试 — 配额 + 隔离 + Dashboard + 用量。"""

from __future__ import annotations

import os, tempfile
import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.artifact_store import SQLiteArtifactStore
from src.adapters.package_registry_store import SQLitePackageStore
from src.adapters.workflow_registry_store import SQLiteWorkflowStore
from src.adapters.agent_module_store import SQLiteAgentModuleStore
from src.open_platform.artifact_service import ArtifactService
from src.open_platform.package_registry_service import PackageService
from src.open_platform.workflow_registry_service import WorkflowService
from src.open_platform.agent_module_service import AgentModuleService
from src.open_platform.saas_integration_service import SaaSIntegrationService
from src.open_platform.saas_integration import (
    QuotaExceededError, WorkspaceIsolationError, QuotaResource,
)


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")

@pytest.fixture
def db():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test_saas.db")
    yield path
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def artifact_store(settings, db): return SQLiteArtifactStore(settings, db_path=db)
@pytest.fixture
def package_store(settings, db): return SQLitePackageStore(settings, db_path=db)
@pytest.fixture
def workflow_store(settings, db): return SQLiteWorkflowStore(settings, db_path=db)
@pytest.fixture
def agent_module_store(settings, db): return SQLiteAgentModuleStore(settings, db_path=db)

@pytest.fixture
def saas(artifact_store, package_store, workflow_store, agent_module_store):
    return SaaSIntegrationService(
        artifact_store=artifact_store, package_store=package_store,
        workflow_store=workflow_store, agent_module_store=agent_module_store,
    )


# ═══════════════════════════════
# Quota Enforcement
# ═══════════════════════════════

class TestQuotaEnforcement:
    def test_check_quota_artifact(self, saas):
        result = saas.check_quota("ws-1", QuotaResource.ARTIFACT)
        assert result.allowed is True
        assert result.current_count == 0
        assert result.quota_limit > 0

    def test_check_quota_package(self, saas):
        result = saas.check_quota("ws-1", QuotaResource.PACKAGE)
        assert result.allowed is True

    def test_check_quota_workflow(self, saas):
        result = saas.check_quota("ws-1", QuotaResource.WORKFLOW)
        assert result.allowed is True

    def test_check_quota_agent_module(self, saas):
        result = saas.check_quota("ws-1", QuotaResource.AGENT_MODULE)
        assert result.allowed is True

    def test_enforce_quota_allows_when_under_limit(self, saas):
        result = saas.enforce_quota("ws-1", QuotaResource.ARTIFACT)
        assert result.allowed is True

    def test_get_all_quotas(self, saas):
        quotas = saas.get_all_quotas("ws-1")
        assert len(quotas) == len(QuotaResource)
        for r in QuotaResource:
            assert r.value in quotas
            assert quotas[r.value].allowed is True

    def test_quota_per_workspace(self, saas, artifact_store):
        """不同 workspace 的配额是独立的。"""
        # 在 ws-1 创建 artifact
        from src.open_platform.artifact import Artifact
        artifact_store.create(Artifact(workspace_id="ws-1", agent_id="a1", title="T1"))
        result_1 = saas.check_quota("ws-1", QuotaResource.ARTIFACT)
        result_2 = saas.check_quota("ws-2", QuotaResource.ARTIFACT)
        assert result_1.current_count == 1
        assert result_2.current_count == 0


# ═══════════════════════════════
# Workspace Isolation
# ═══════════════════════════════

class TestWorkspaceIsolation:
    def test_artifacts_isolated_by_workspace(self, artifact_store):
        from src.open_platform.artifact import Artifact
        artifact_store.create(Artifact(workspace_id="ws-1", agent_id="a1", title="T1"))
        artifact_store.create(Artifact(workspace_id="ws-2", agent_id="a2", title="T2"))
        assert len(artifact_store.list(workspace_id="ws-1")) == 1
        assert len(artifact_store.list(workspace_id="ws-2")) == 1

    def test_packages_isolated_by_workspace(self, package_store):
        from src.open_platform.package_registry import Package
        package_store.create(Package(workspace_id="ws-1", name="P1"))
        package_store.create(Package(workspace_id="ws-2", name="P2"))
        assert len(package_store.list(workspace_id="ws-1")) == 1

    def test_workflows_isolated_by_workspace(self, workflow_store):
        from src.open_platform.workflow_registry import Workflow
        workflow_store.create(Workflow(workspace_id="ws-1", name="W1"))
        workflow_store.create(Workflow(workspace_id="ws-2", name="W2"))
        assert len(workflow_store.list(workspace_id="ws-1")) == 1

    def test_agent_modules_isolated_by_workspace(self, agent_module_store):
        from src.open_platform.agent_module import AgentModule
        agent_module_store.create(AgentModule(workspace_id="ws-1", name="A1"))
        agent_module_store.create(AgentModule(workspace_id="ws-2", name="A2"))
        assert len(agent_module_store.list(workspace_id="ws-1")) == 1

    def test_guard_workspace_access(self, saas):
        """同 workspace 允许，跨 workspace 拒绝。"""
        saas.guard_workspace_access("ws-1", "ws-1")  # no exception
        with pytest.raises(WorkspaceIsolationError):
            saas.guard_workspace_access("ws-1", "ws-2")

    def test_require_workspace_match_raises(self):
        from src.open_platform.saas_integration import require_workspace_match
        require_workspace_match("ws-1", "ws-1")
        with pytest.raises(WorkspaceIsolationError):
            require_workspace_match("ws-1", "ws-2")


# ═══════════════════════════════
# Dashboard
# ═══════════════════════════════

class TestDashboard:
    def test_empty_dashboard(self, saas):
        d = saas.get_dashboard("ws-1")
        assert d.workspace_id == "ws-1"
        assert d.artifacts == {}
        assert d.packages == {}
        assert d.workflows == {}
        assert d.agent_modules == {}

    def test_dashboard_with_artifacts(self, saas, artifact_store):
        from src.open_platform.artifact import Artifact, ArtifactStatus
        svc = ArtifactService(artifact_store)
        svc.create_artifact(workspace_id="ws-1", agent_id="a1",
                            artifact_type="code", title="T1")
        a2 = svc.create_artifact(workspace_id="ws-1", agent_id="a1",
                                 artifact_type="prompt", title="T2")
        svc.submit_review(a2.id)
        d = saas.get_dashboard("ws-1")
        assert d.artifacts.get("draft", 0) >= 1
        assert d.artifacts.get("review", 0) >= 1

    def test_dashboard_with_modules(self, saas, agent_module_store):
        svc = AgentModuleService(agent_module_store)
        svc.create_module(workspace_id="ws-1", name="M1")
        m2 = svc.create_module(workspace_id="ws-1", name="M2")
        svc.submit_review(m2.id); svc.approve(m2.id, "r1"); svc.publish(m2.id, "pub-1")
        d = saas.get_dashboard("ws-1")
        assert d.agent_modules.get("draft", 0) >= 1
        assert d.agent_modules.get("published", 0) >= 1

    def test_dashboard_quotas_included(self, saas):
        d = saas.get_dashboard("ws-1")
        assert len(d.quotas) == len(QuotaResource)

    def test_dashboard_workspace_isolated(self, saas, artifact_store):
        from src.open_platform.artifact import Artifact
        artifact_store.create(Artifact(workspace_id="ws-1", agent_id="a1", title="T1"))
        d_ws1 = saas.get_dashboard("ws-1")
        d_ws2 = saas.get_dashboard("ws-2")
        assert d_ws1.artifacts != d_ws2.artifacts or d_ws1.artifacts == d_ws2.artifacts


# ═══════════════════════════════
# Usage Recording (smoke test)
# ═══════════════════════════════

class TestUsageRecording:
    def test_record_usage_no_usage_store_does_not_crash(self, saas):
        """UsageStore 是 None 时 record_usage 不 crash。"""
        saas.record_usage("ws-1", "user-1", "artifact", 1)

    def test_record_usage_with_metadata(self, saas):
        saas.record_usage("ws-1", "user-1", "package", 1, {"key": "val"})
