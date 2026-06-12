"""Multi-Tenant Isolation 集成测试 — 跨所有子系统验证 workspace 隔离。

验证：
- 每个子系统的 store 都按 workspace_id 隔离
- 不同 workspace 的资源完全不可见
- 跨 workspace 访问被守卫机制拒绝
"""

from __future__ import annotations

import os, tempfile
import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.artifact_store import SQLiteArtifactStore
from src.adapters.package_registry_store import SQLitePackageStore
from src.adapters.workflow_registry_store import SQLiteWorkflowStore
from src.adapters.agent_module_store import SQLiteAgentModuleStore
from src.open_platform.artifact import Artifact, ArtifactStatus
from src.open_platform.package_registry import Package, PackageStatus
from src.open_platform.workflow_registry import Workflow, WorkflowStatus
from src.open_platform.agent_module import AgentModule, AgentModuleStatus
from src.open_platform.saas_integration import require_workspace_match, WorkspaceIsolationError


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")

@pytest.fixture
def db():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test_isolation.db")
    yield path
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def a_store(settings, db): return SQLiteArtifactStore(settings, db_path=db)
@pytest.fixture
def p_store(settings, db): return SQLitePackageStore(settings, db_path=db)
@pytest.fixture
def w_store(settings, db): return SQLiteWorkflowStore(settings, db_path=db)
@pytest.fixture
def m_store(settings, db): return SQLiteAgentModuleStore(settings, db_path=db)


class TestArtifactIsolation:
    def test_workspace_a_cannot_see_workspace_b(self, a_store):
        a_store.create(Artifact(workspace_id="tenant-A", agent_id="a1", title="A-Secret"))
        a_store.create(Artifact(workspace_id="tenant-B", agent_id="b1", title="B-Secret"))
        tenant_a = a_store.list(workspace_id="tenant-A")
        tenant_b = a_store.list(workspace_id="tenant-B")
        assert all(a.workspace_id == "tenant-A" for a in tenant_a)
        assert all(a.workspace_id == "tenant-B" for a in tenant_b)
        assert len(tenant_a) == 1 and len(tenant_b) == 1

    def test_artifact_get_returns_right_workspace(self, a_store):
        a = a_store.create(Artifact(workspace_id="tenant-A", agent_id="a1", title="A"))
        b = a_store.create(Artifact(workspace_id="tenant-B", agent_id="b1", title="B"))
        assert a_store.get(a.id).workspace_id == "tenant-A"
        assert a_store.get(b.id).workspace_id == "tenant-B"

    def test_cross_workspace_guard_rejects(self):
        with pytest.raises(WorkspaceIsolationError):
            require_workspace_match("tenant-A", "tenant-B")

    def test_same_workspace_guard_passes(self):
        require_workspace_match("tenant-A", "tenant-A")


class TestPackageIsolation:
    def test_packages_isolated(self, p_store):
        p_store.create(Package(workspace_id="org-X", name="XPkg"))
        p_store.create(Package(workspace_id="org-Y", name="YPkg"))
        assert len(p_store.list(workspace_id="org-X")) == 1
        assert len(p_store.list(workspace_id="org-Y")) == 1

    def test_package_get_isolated(self, p_store):
        x = p_store.create(Package(workspace_id="org-X", name="X"))
        y = p_store.create(Package(workspace_id="org-Y", name="Y"))
        assert p_store.get(x.id).workspace_id == "org-X"
        assert p_store.get(y.id).workspace_id == "org-Y"


class TestWorkflowIsolation:
    def test_workflows_isolated(self, w_store):
        w_store.create(Workflow(workspace_id="dept-1", name="W1"))
        w_store.create(Workflow(workspace_id="dept-2", name="W2"))
        assert len(w_store.list(workspace_id="dept-1")) == 1
        assert len(w_store.list(workspace_id="dept-2")) == 1

    def test_workflow_get_isolated(self, w_store):
        w1 = w_store.create(Workflow(workspace_id="dept-1", name="W1"))
        w2 = w_store.create(Workflow(workspace_id="dept-2", name="W2"))
        assert w_store.get(w1.id).workspace_id == "dept-1"
        assert w_store.get(w2.id).workspace_id == "dept-2"


class TestAgentModuleIsolation:
    def test_modules_isolated(self, m_store):
        m_store.create(AgentModule(workspace_id="co-A", name="MA"))
        m_store.create(AgentModule(workspace_id="co-B", name="MB"))
        assert len(m_store.list(workspace_id="co-A")) == 1
        assert len(m_store.list(workspace_id="co-B")) == 1

    def test_module_get_isolated(self, m_store):
        ma = m_store.create(AgentModule(workspace_id="co-A", name="MA"))
        mb = m_store.create(AgentModule(workspace_id="co-B", name="MB"))
        assert m_store.get(ma.id).workspace_id == "co-A"
        assert m_store.get(mb.id).workspace_id == "co-B"


class TestFullPipelineIsolation:
    """完整流水线 — 每个 workspace 独立的审核流水线。"""

    def test_independent_pipelines(self, a_store):
        """两个 workspace 各自跑完审核流水线，互不干扰。"""
        # workspace-1
        a1 = a_store.create(Artifact(workspace_id="ws-1", agent_id="a1", title="A1"))
        a_store.update_status(a1.id, ArtifactStatus.REVIEW)
        a_store.update_status(a1.id, ArtifactStatus.APPROVED)
        a_store.update_status(a1.id, ArtifactStatus.PUBLISHED)

        # workspace-2: independent
        a2 = a_store.create(Artifact(workspace_id="ws-2", agent_id="a2", title="A2"))
        a_store.update_status(a2.id, ArtifactStatus.REVIEW)
        a_store.update_status(a2.id, ArtifactStatus.APPROVED)

        # 验证隔离
        ws1_items = a_store.list(workspace_id="ws-1")
        ws2_items = a_store.list(workspace_id="ws-2")
        assert len(ws1_items) == 1
        assert len(ws2_items) == 1
        assert ws1_items[0].status == ArtifactStatus.PUBLISHED
        assert ws2_items[0].status == ArtifactStatus.APPROVED
