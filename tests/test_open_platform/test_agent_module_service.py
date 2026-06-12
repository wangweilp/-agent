"""AgentModule Service + Marketplace Service 单元测试。"""

from __future__ import annotations

import os, tempfile
import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.agent_module_store import SQLiteAgentModuleStore
from src.open_platform.agent_module_service import AgentModuleService, MarketplaceService
from src.open_platform.agent_module import (
    AgentModuleNotFoundError, AgentModuleStateError,
    AgentModuleStatus, AgentModuleValidationError,
    SubscriptionAlreadyExistsError,
)


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")

@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp(); path = os.path.join(d, "test_amsvc.db"); yield path
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def store(settings, tmp_db_path): return SQLiteAgentModuleStore(settings, db_path=tmp_db_path)

@pytest.fixture
def svc(store): return AgentModuleService(store)

@pytest.fixture
def mkt(store): return MarketplaceService(store)


class TestAgentModuleService:
    def test_create(self, svc):
        m = svc.create_module(workspace_id="ws-1", name="MyAgent",
                               description="desc", workflow_ids=["wf_1"], version="1.0.0",
                               author="dev", category="chat", tags=["ai"], metadata={"k":"v"})
        assert m.id.startswith("agent_") and m.metadata_only

    def test_create_validation_fails(self, svc):
        with pytest.raises(AgentModuleValidationError):
            svc.create_module(workspace_id="", name="")

    def test_full_pipeline(self, svc):
        m = svc.create_module(workspace_id="ws-1", name="Full")
        m = svc.submit_review(m.id); assert m.status == "review"
        m = svc.approve(m.id, "r1", "LGTM"); assert m.status == "approved" and m.reviewed_by == "r1"
        m = svc.publish(m.id, "pub-1"); assert m.status == "published" and m.published_by == "pub-1"
        assert m.metadata_only is True

    def test_reject(self, svc):
        m = svc.create_module(workspace_id="ws-1", name="R")
        svc.submit_review(m.id)
        m = svc.reject(m.id, "r1", "bad"); assert m.status == "rejected"

    def test_publish_wrong_status(self, svc):
        with pytest.raises(AgentModuleStateError): svc.publish(svc.create_module(workspace_id="ws-1", name="P").id, "pub-1")

    def test_approve_wrong_status(self, svc):
        with pytest.raises(AgentModuleStateError): svc.approve(svc.create_module(workspace_id="ws-1", name="P").id, "r1")

    def test_get_and_list(self, svc):
        svc.create_module(workspace_id="ws-1", name="A")
        svc.create_module(workspace_id="ws-1", name="B")
        assert len(svc.list(workspace_id="ws-1")) == 2

    def test_delete(self, svc):
        m = svc.create_module(workspace_id="ws-1", name="D")
        svc.delete(m.id); assert svc.get(m.id) is None

    def test_cannot_delete_review(self, svc):
        m = svc.create_module(workspace_id="ws-1", name="R")
        svc.submit_review(m.id)
        with pytest.raises(AgentModuleStateError): svc.delete(m.id)


class TestMarketplaceService:
    def _publish(self, svc, **kw):
        m = svc.create_module(workspace_id="ws-1", name=kw.get("name","A"),
                              category=kw.get("category",""), tags=kw.get("tags",[]),
                              description=kw.get("description",""))
        svc.submit_review(m.id); svc.approve(m.id, "r1"); svc.publish(m.id, "pub-1")
        return svc.get(m.id)

    def test_search(self, svc, mkt):
        self._publish(svc, name="ChatBot"); self._publish(svc, name="CodeGen")
        results = mkt.search("Chat")
        assert len(results) == 1 and results[0].name == "ChatBot"

    def test_search_no_results(self, svc, mkt):
        assert mkt.search("nonexistent") == []

    def test_list_published(self, svc, mkt):
        self._publish(svc, name="A"); self._publish(svc, name="B")
        results = mkt.list_published()
        assert len(results) == 2

    def test_list_published_excludes_draft(self, svc, mkt):
        svc.create_module(workspace_id="ws-1", name="Draft")
        results = mkt.list_published()
        assert len(results) == 0

    def test_subscribe(self, svc, mkt):
        m = self._publish(svc, name="Pub")
        s = mkt.subscribe("ws-2", m.id)
        assert s.id.startswith("sub_") and s.active

    def test_subscribe_non_published(self, svc, mkt):
        m = svc.create_module(workspace_id="ws-1", name="Draft")
        with pytest.raises(AgentModuleStateError, match="published"):
            mkt.subscribe("ws-2", m.id)

    def test_subscribe_nonexistent(self, svc, mkt):
        with pytest.raises(AgentModuleNotFoundError):
            mkt.subscribe("ws-2", "agent_nonexistent")

    def test_subscribe_duplicate(self, svc, mkt):
        m = self._publish(svc, name="Pub")
        mkt.subscribe("ws-2", m.id)
        with pytest.raises(SubscriptionAlreadyExistsError):
            mkt.subscribe("ws-2", m.id)

    def test_unsubscribe(self, svc, mkt):
        m = self._publish(svc, name="Pub")
        mkt.subscribe("ws-2", m.id)
        mkt.unsubscribe("ws-2", m.id)
        assert mkt.get_subscription("ws-2", m.id) is None

    def test_list_subscriptions(self, svc, mkt):
        m1 = self._publish(svc, name="A"); m2 = self._publish(svc, name="B")
        mkt.subscribe("ws-2", m1.id); mkt.subscribe("ws-2", m2.id)
        assert len(mkt.list_subscriptions("ws-2")) == 2

    def test_category_filter(self, svc, mkt):
        self._publish(svc, name="A", category="chat")
        self._publish(svc, name="B", category="code")
        assert len(mkt.list_published(category="chat")) == 1


class TestSafety:
    def test_all_metadata_only(self, svc):
        m = svc.create_module(workspace_id="ws-1", name="Safe")
        svc.submit_review(m.id); svc.approve(m.id, "r1"); svc.publish(m.id, "pub-1")
        final = svc.get(m.id)
        assert final.metadata_only is True
