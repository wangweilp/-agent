"""AgentModule Store 单元测试。CRUD + 状态迁移 + 审核流水线 + 订阅。"""

from __future__ import annotations

import os, tempfile
import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.agent_module_store import SQLiteAgentModuleStore
from src.open_platform.agent_module import (
    AgentModule, AgentModuleNotFoundError, AgentModuleStateError,
    AgentModuleStatus, AgentModuleValidationError,
    Subscription, SubscriptionAlreadyExistsError, SubscriptionNotFoundError,
)


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")

@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp(); path = os.path.join(d, "test_am.db"); yield path
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def store(settings, tmp_db_path): return SQLiteAgentModuleStore(settings, db_path=tmp_db_path)


class TestCreate:
    def test_create(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="M"))
        assert m.id.startswith("agent_") and m.metadata_only

    def test_create_enforces_metadata_only(self, store):
        m = AgentModule(workspace_id="ws-1", name="M"); m.metadata_only = False
        assert store.create(m).metadata_only is True

    def test_create_requires_draft(self, store):
        with pytest.raises(AgentModuleStateError):
            store.create(AgentModule(workspace_id="ws-1", name="M", status="approved"))

    def test_validation_error(self, store):
        with pytest.raises(AgentModuleValidationError): store.create(AgentModule())


class TestGet:
    def test_get(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="M"))
        assert store.get(m.id).name == "M"
    def test_nonexistent(self, store): assert store.get("agent_none") is None


class TestList:
    def test_list_all(self, store):
        store.create(AgentModule(workspace_id="ws-1", name="A"))
        store.create(AgentModule(workspace_id="ws-1", name="B"))
        assert len(store.list()) == 2

    def test_filter_workspace(self, store):
        store.create(AgentModule(workspace_id="ws-1", name="A"))
        store.create(AgentModule(workspace_id="ws-2", name="B"))
        assert len(store.list(workspace_id="ws-1")) == 1

    def test_filter_status(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="A"))
        store.update_status(m.id, "review")
        assert len(store.list(status="review")) == 1

    def test_filter_category(self, store):
        store.create(AgentModule(workspace_id="ws-1", name="A", category="chat"))
        store.create(AgentModule(workspace_id="ws-1", name="B", category="code"))
        assert len(store.list(category="chat")) == 1


class TestSearch:
    def test_search_name(self, store):
        _publish(store, AgentModule(workspace_id="ws-1", name="ChatBot"))
        _publish(store, AgentModule(workspace_id="ws-1", name="CodeGen"))
        results = store.search("Chat")
        assert len(results) == 1 and results[0].name == "ChatBot"

    def test_search_description(self, store):
        _publish(store, AgentModule(workspace_id="ws-1", name="A", description="helpful assistant"))
        assert len(store.search("assistant")) == 1

    def test_search_tag(self, store):
        _publish(store, AgentModule(workspace_id="ws-1", name="A", tags=["python"]))
        assert len(store.search("python")) == 1

    def test_search_only_published(self, store):
        store.create(AgentModule(workspace_id="ws-1", name="DraftOnly"))
        assert len(store.search("Draft")) == 0

    def test_search_category_filter(self, store):
        _publish(store, AgentModule(workspace_id="ws-1", name="A", category="chat"))
        _publish(store, AgentModule(workspace_id="ws-1", name="B", category="code"))
        assert len(store.search("", category="chat")) == 1


class TestUpdate:
    def test_update_draft(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="Orig"))
        m.name = "New"; store.update(m)
        assert store.get(m.id).name == "New"

    def test_cannot_update_review(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="M"))
        store.update_status(m.id, "review")
        with pytest.raises(AgentModuleStateError): store.update(m)

    def test_cannot_update_approved(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="M"))
        _migrate(store, m.id, "review", "approved")
        with pytest.raises(AgentModuleStateError): store.update(m)

    def test_cannot_update_published(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="M"))
        _migrate(store, m.id, "review", "approved", "published")
        with pytest.raises(AgentModuleStateError): store.update(m)


class TestUpdateStatus:
    def test_draft_to_review(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="M"))
        store.update_status(m.id, "review")
        assert store.get(m.id).status == "review"

    def test_review_to_approved(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="M"))
        store.update_status(m.id, "review")
        store.update_status(m.id, "approved", reviewed_by="r1", review_comment="OK")
        f = store.get(m.id)
        assert f.status == "approved" and f.reviewed_by == "r1"

    def test_review_to_rejected(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="M"))
        store.update_status(m.id, "review")
        store.update_status(m.id, "rejected", reviewed_by="r1")
        assert store.get(m.id).status == "rejected"

    def test_approved_to_published(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="M"))
        _migrate(store, m.id, "review", "approved")
        store.update_status(m.id, "published", published_by="pub-1")
        f = store.get(m.id)
        assert f.status == "published" and f.published_by == "pub-1"

    def test_rejected_to_draft(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="M"))
        _migrate(store, m.id, "review", "rejected")
        store.update_status(m.id, "draft")
        assert store.get(m.id).status == "draft"

    def test_invalid_transition(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="M"))
        with pytest.raises(AgentModuleStateError): store.update_status(m.id, "published")


class TestDelete:
    def test_delete_draft(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="D"))
        store.delete(m.id); assert store.get(m.id) is None

    def test_delete_rejected(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="R"))
        _migrate(store, m.id, "review", "rejected")
        store.delete(m.id); assert store.get(m.id) is None

    def test_cannot_delete_review(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="R"))
        store.update_status(m.id, "review")
        with pytest.raises(AgentModuleStateError): store.delete(m.id)

    def test_cannot_delete_published(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="P"))
        _migrate(store, m.id, "review", "approved", "published")
        with pytest.raises(AgentModuleStateError): store.delete(m.id)


class TestReviewPipeline:
    def test_full_pipeline(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="Pipeline"))
        _migrate(store, m.id, "review", "approved", "published")
        final = store.get(m.id)
        assert final.status == "published" and final.metadata_only is True

    def test_reject_and_resubmit(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="R"))
        _migrate(store, m.id, "review", "rejected")
        store.update_status(m.id, "draft")
        _migrate(store, m.id, "review", "approved")
        assert store.get(m.id).status == "approved"

    def test_published_terminal(self, store):
        m = store.create(AgentModule(workspace_id="ws-1", name="T"))
        _migrate(store, m.id, "review", "approved", "published")
        with pytest.raises(AgentModuleStateError): store.update_status(m.id, "draft")


class TestSubscription:
    @pytest.fixture
    def pub_store(self, store):
        """Store with a published module ready for subscription."""
        m = store.create(AgentModule(workspace_id="ws-1", name="Pub"))
        _migrate(store, m.id, "review", "approved", "published")
        return store

    def test_subscribe(self, pub_store):
        m = pub_store.list(status="published")[0]
        s = pub_store.subscribe(Subscription(workspace_id="ws-2", agent_module_id=m.id))
        assert s.id.startswith("sub_") and s.active

    def test_subscribe_duplicate(self, pub_store):
        m = pub_store.list(status="published")[0]
        pub_store.subscribe(Subscription(workspace_id="ws-2", agent_module_id=m.id))
        with pytest.raises(SubscriptionAlreadyExistsError):
            pub_store.subscribe(Subscription(workspace_id="ws-2", agent_module_id=m.id))

    def test_unsubscribe(self, pub_store):
        m = pub_store.list(status="published")[0]
        pub_store.subscribe(Subscription(workspace_id="ws-2", agent_module_id=m.id))
        pub_store.unsubscribe("ws-2", m.id)
        assert pub_store.get_subscription("ws-2", m.id) is None

    def test_unsubscribe_nonexistent(self, pub_store):
        with pytest.raises(SubscriptionNotFoundError):
            pub_store.unsubscribe("ws-x", "agent_nonexistent")

    def test_list_subscriptions(self, pub_store):
        m = pub_store.list(status="published")[0]
        pub_store.subscribe(Subscription(workspace_id="ws-2", agent_module_id=m.id))
        subs = pub_store.list_subscriptions("ws-2")
        assert len(subs) == 1 and subs[0].agent_module_id == m.id

    def test_get_subscription(self, pub_store):
        m = pub_store.list(status="published")[0]
        pub_store.subscribe(Subscription(workspace_id="ws-2", agent_module_id=m.id))
        s = pub_store.get_subscription("ws-2", m.id)
        assert s is not None and s.active


# ── Helpers ──

def _migrate(store, module_id: str, *statuses: str):
    for s in statuses:
        store.update_status(module_id, s)

def _publish(store, m: AgentModule) -> AgentModule:
    created = store.create(m)
    _migrate(store, created.id, "review", "approved", "published")
    return store.get(created.id)
