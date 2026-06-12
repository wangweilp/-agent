"""Agent Module & Marketplace 安全测试。

验证: metadata_only, 无执行/网络/文件系统写入/container/runtime。
"""

from __future__ import annotations

import os, tempfile, inspect
import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.agent_module_store import SQLiteAgentModuleStore
from src.open_platform.agent_module_service import AgentModuleService, MarketplaceService
from src.open_platform.agent_module import AgentModule, AgentModuleStatus


FORBIDDEN_METHODS = ["execute", "run", "exec", "spawn", "launch",
                     "start_container", "create_container", "start_microvm",
                     "subprocess", "shell"]
FORBIDDEN_IMPORTS = ["subprocess", "docker", "container", "microvm",
                     "podman", "kubernetes", "lxc", "firecracker",
                     "os.system", "os.popen", "shell=True"]


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")

@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp(); path = os.path.join(d, "test_amsec.db"); yield path
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def store(settings, tmp_db_path): return SQLiteAgentModuleStore(settings, db_path=tmp_db_path)
@pytest.fixture
def svc(store): return AgentModuleService(store)


class TestNoExecution:
    def test_domain_no_execution(self):
        for name in FORBIDDEN_METHODS:
            assert not hasattr(AgentModule, name), f"AgentModule 不应有 {name}"

    def test_service_no_execution(self):
        for name in FORBIDDEN_METHODS:
            assert not hasattr(AgentModuleService, name), f"AgentModuleService 不应有 {name}"

    def test_marketplace_no_execution(self):
        for name in FORBIDDEN_METHODS:
            assert not hasattr(MarketplaceService, name), f"MarketplaceService 不应有 {name}"

    def test_store_no_execution(self):
        for name in FORBIDDEN_METHODS:
            assert not hasattr(SQLiteAgentModuleStore, name), f"SQLiteAgentModuleStore 不应有 {name}"


class TestSourceClean:
    def test_store_source_clean(self):
        src = inspect.getsource(SQLiteAgentModuleStore)
        for p in FORBIDDEN_IMPORTS:
            assert p not in src.lower(), f"Store 不应含 {p}"

    def test_service_source_clean(self):
        for cls in [AgentModuleService, MarketplaceService]:
            src = inspect.getsource(cls)
            for p in FORBIDDEN_IMPORTS:
                assert p not in src.lower(), f"{cls.__name__} 不应含 {p}"

    def test_domain_source_clean(self):
        src = inspect.getsource(AgentModule)
        for p in ["requests", "urllib", "http.client", "socket", "subprocess"]:
            assert f"import {p}" not in src, f"Domain 不应 import {p}"


class TestMetadataOnly:
    def test_always_metadata_only(self, store):
        m = AgentModule(workspace_id="ws", name="M"); m.metadata_only = False
        created = store.create(m)
        assert created.metadata_only is True
        _migrate(store, created.id, "review", "approved", "published")
        assert store.get(created.id).metadata_only is True

    def test_validate_enforces(self):
        m = AgentModule(workspace_id="ws", name="M"); m.metadata_only = False
        assert any("metadata_only 必须为 True" in e for e in m.validate())

    def test_from_dict_always(self):
        m = AgentModule.from_dict({"workspace_id": "ws", "name": "M", "metadata_only": False})
        assert m.metadata_only is True

    def test_through_pipeline(self, svc):
        m = svc.create_module(workspace_id="ws", name="Safe")
        svc.submit_review(m.id); svc.approve(m.id, "r1"); svc.publish(m.id, "pub-1")
        assert svc.get(m.id).metadata_only is True

    def test_marketplace_search_returns_safe(self, svc):
        m = svc.create_module(workspace_id="ws", name="M", category="chat")
        svc.submit_review(m.id); svc.approve(m.id, "r1"); svc.publish(m.id, "pub-1")
        mkt = MarketplaceService(svc._store)
        results = mkt.search("M")
        for r in results:
            assert r.metadata_only is True


def _migrate(store, mid, *statuses):
    for s in statuses:
        store.update_status(mid, s)
