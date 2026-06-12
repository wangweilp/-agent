"""Package & Workflow Registry 安全测试。

验证：
- 所有 Package/Workflow metadata_only=True
- 不包含执行/网络/文件系统写入方法
- 不导入 runtime/container/microVM 相关模块
"""

from __future__ import annotations

import os, tempfile, inspect
import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.package_registry_store import SQLitePackageStore
from src.adapters.workflow_registry_store import SQLiteWorkflowStore
from src.open_platform.package_registry_service import PackageService
from src.open_platform.workflow_registry_service import WorkflowService
from src.open_platform.package_registry import Package, PackageStatus
from src.open_platform.workflow_registry import Workflow, WorkflowStatus


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")

@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test_sec.db")
    yield path
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def pkg_store(settings, tmp_db_path): return SQLitePackageStore(settings, db_path=tmp_db_path)
@pytest.fixture
def wf_store(settings, tmp_db_path): return SQLiteWorkflowStore(settings, db_path=tmp_db_path)
@pytest.fixture
def pkg_service(pkg_store): return PackageService(pkg_store)
@pytest.fixture
def wf_service(wf_store): return WorkflowService(wf_store)


# ═══════════════════════════════
# 禁止执行
# ═══════════════════════════════

class TestNoExecution:
    FORBIDDEN = ["execute", "run", "exec", "spawn", "launch",
                 "start_container", "create_container", "start_microvm",
                 "subprocess", "shell"]

    def test_package_domain_no_execution(self):
        for name in self.FORBIDDEN:
            assert not hasattr(Package, name), f"Package 不应有 {name}"

    def test_workflow_domain_no_execution(self):
        for name in self.FORBIDDEN:
            assert not hasattr(Workflow, name), f"Workflow 不应有 {name}"

    def test_package_service_no_execution(self):
        for name in self.FORBIDDEN:
            assert not hasattr(PackageService, name), f"PackageService 不应有 {name}"

    def test_workflow_service_no_execution(self):
        for name in self.FORBIDDEN:
            assert not hasattr(WorkflowService, name), f"WorkflowService 不应有 {name}"

    def test_package_store_no_execution(self):
        for name in self.FORBIDDEN:
            assert not hasattr(SQLitePackageStore, name), f"SQLitePackageStore 不应有 {name}"

    def test_workflow_store_no_execution(self):
        for name in self.FORBIDDEN:
            assert not hasattr(SQLiteWorkflowStore, name), f"SQLiteWorkflowStore 不应有 {name}"


# ═══════════════════════════════
# 源码审查 — 无敏感 import
# ═══════════════════════════════

class TestSourceNoForbiddenImports:
    FORBIDDEN = ["subprocess", "docker", "container", "microvm",
                 "podman", "kubernetes", "lxc", "firecracker",
                 "os.system", "os.popen", "shell=True"]

    STORES = [SQLitePackageStore, SQLiteWorkflowStore]
    SERVICES = [PackageService, WorkflowService]
    DOMAINS = [Package, Workflow]

    def test_package_source_clean(self):
        source = inspect.getsource(SQLitePackageStore)
        for pattern in self.FORBIDDEN:
            assert pattern not in source.lower(), f"SQLitePackageStore 不应含 {pattern}"

    def test_workflow_source_clean(self):
        source = inspect.getsource(SQLiteWorkflowStore)
        for pattern in self.FORBIDDEN:
            assert pattern not in source.lower(), f"SQLiteWorkflowStore 不应含 {pattern}"

    def test_package_service_clean(self):
        source = inspect.getsource(PackageService)
        for pattern in self.FORBIDDEN:
            assert pattern not in source.lower(), f"PackageService 不应含 {pattern}"

    def test_workflow_service_clean(self):
        source = inspect.getsource(WorkflowService)
        for pattern in self.FORBIDDEN:
            assert pattern not in source.lower(), f"WorkflowService 不应含 {pattern}"


# ═══════════════════════════════
# metadata_only 永远 True
# ═══════════════════════════════

class TestMetadataOnly:
    def test_package_always_metadata_only(self, pkg_store):
        p = Package(workspace_id="ws", name="P")
        p.metadata_only = False
        created = pkg_store.create(p)
        assert created.metadata_only is True
        for s in [PackageStatus.REVIEW, PackageStatus.APPROVED, PackageStatus.PUBLISHED]:
            if pkg_store.get(p.id).can_transition_to(s):
                pkg_store.update_status(p.id, s)
        final = pkg_store.get(p.id)
        assert final.metadata_only is True

    def test_workflow_always_metadata_only(self, wf_store):
        w = Workflow(workspace_id="ws", name="W")
        w.metadata_only = False
        created = wf_store.create(w)
        assert created.metadata_only is True
        for s in [WorkflowStatus.REVIEW, WorkflowStatus.APPROVED, WorkflowStatus.PUBLISHED]:
            if wf_store.get(w.id).can_transition_to(s):
                wf_store.update_status(w.id, s)
        final = wf_store.get(w.id)
        assert final.metadata_only is True

    def test_package_validate_enforces_metadata_only(self):
        p = Package(workspace_id="ws", name="P")
        p.metadata_only = False
        errors = p.validate()
        assert any("metadata_only 必须为 True" in e for e in errors)

    def test_workflow_validate_enforces_metadata_only(self):
        w = Workflow(workspace_id="ws", name="W")
        w.metadata_only = False
        errors = w.validate()
        assert any("metadata_only 必须为 True" in e for e in errors)

    def test_package_from_dict_always_metadata_only(self):
        d = {"workspace_id": "ws", "name": "P", "metadata_only": False}
        p = Package.from_dict(d)
        assert p.metadata_only is True

    def test_workflow_from_dict_always_metadata_only(self):
        d = {"workspace_id": "ws", "name": "W", "metadata_only": False}
        w = Workflow.from_dict(d)
        assert w.metadata_only is True

    def test_all_packages_safe_through_pipeline(self, pkg_service):
        p = pkg_service.create_package(workspace_id="ws", name="Safe")
        pkg_service.submit_review(p.id)
        pkg_service.approve(p.id, "r1")
        pkg_service.publish(p.id, "pub-1")
        final = pkg_service.get(p.id)
        assert final.metadata_only is True

    def test_all_workflows_safe_through_pipeline(self, wf_service):
        w = wf_service.create_workflow(workspace_id="ws", name="Safe")
        wf_service.submit_review(w.id)
        wf_service.approve(w.id, "r1")
        wf_service.publish(w.id, "pub-1")
        final = wf_service.get(w.id)
        assert final.metadata_only is True
