"""AgentModule Domain 单元测试。"""

from __future__ import annotations

import pytest
from src.open_platform.agent_module import (
    AgentModule, AgentModuleStatus, Subscription,
    is_valid_transition, is_immutable,
)


class TestAgentModuleCreation:
    def test_defaults(self):
        m = AgentModule()
        assert m.id.startswith("agent_")
        assert m.workflow_ids == []
        assert m.version == "0.1.0"
        assert m.status == AgentModuleStatus.DRAFT
        assert m.metadata_only is True

    def test_with_values(self):
        m = AgentModule(
            workspace_id="ws-1", name="My Agent", description="desc",
            workflow_ids=["wf_1", "wf_2"], version="2.0.0",
            author="dev-1", category="chat", icon_url="/icon.png",
            tags=["ai", "chat"], metadata={"key": "val"},
        )
        assert m.workspace_id == "ws-1"
        assert m.workflow_ids == ["wf_1", "wf_2"]
        assert m.category == "chat"
        assert m.author == "dev-1"
        assert m.metadata_only is True

    def test_metadata_only_always_true(self):
        m = AgentModule()
        m.metadata_only = False
        errors = m.validate()
        assert any("metadata_only 必须为 True" in e for e in errors)


class TestAgentModuleValidation:
    def test_valid(self):
        m = AgentModule(workspace_id="ws-1", name="Test")
        assert m.is_valid()

    def test_missing_workspace_id(self):
        assert any("workspace_id 必填" in e for e in AgentModule(name="T").validate())

    def test_missing_name(self):
        assert any("name 必填" in e for e in AgentModule(workspace_id="ws-1").validate())

    def test_invalid_status(self):
        m = AgentModule(workspace_id="ws", name="T", status="bad")
        assert any("status 无效" in e for e in m.validate())


class TestTransitions:
    def test_draft_to_review(self): assert is_valid_transition("draft", "review")
    def test_review_to_approved(self): assert is_valid_transition("review", "approved")
    def test_review_to_rejected(self): assert is_valid_transition("review", "rejected")
    def test_approved_to_published(self): assert is_valid_transition("approved", "published")
    def test_rejected_to_draft(self): assert is_valid_transition("rejected", "draft")
    def test_invalid_draft_to_approved(self): assert not is_valid_transition("draft", "approved")
    def test_invalid_draft_to_published(self): assert not is_valid_transition("draft", "published")
    def test_published_terminal(self):
        for s in AgentModuleStatus:
            assert not is_valid_transition(AgentModuleStatus.PUBLISHED, s)

    def test_can_transition_to(self):
        m = AgentModule(workspace_id="ws", name="T")
        assert m.can_transition_to("review")
        assert not m.can_transition_to("approved")

    def test_is_editable(self):
        m = AgentModule(workspace_id="ws", name="T")
        assert m.is_editable()
        m.status = AgentModuleStatus.REVIEW
        assert not m.is_editable()

    def test_is_published(self):
        m = AgentModule(workspace_id="ws", name="T")
        assert not m.is_published()
        m.status = AgentModuleStatus.PUBLISHED
        assert m.is_published()


class TestSerialization:
    def test_to_dict(self):
        m = AgentModule(workspace_id="ws-1", name="A", workflow_ids=["wf_1"],
                        version="3.0.0", author="dev", category="chat",
                        tags=["t1"], metadata={"k": "v"})
        d = m.to_dict()
        assert d["id"].startswith("agent_")
        assert d["workflow_ids"] == ["wf_1"]
        assert d["category"] == "chat"
        assert d["metadata_only"] is True

    def test_from_dict_roundtrip(self):
        m = AgentModule(workspace_id="ws-1", name="A", workflow_ids=["wf_1"])
        m2 = AgentModule.from_dict(m.to_dict())
        assert m2.id == m.id
        assert m2.workflow_ids == m.workflow_ids
        assert m2.metadata_only is True

    def test_from_dict_always_metadata_only(self):
        m = AgentModule.from_dict({"workspace_id": "ws", "name": "A", "metadata_only": False})
        assert m.metadata_only is True


class TestSubscription:
    def test_defaults(self):
        s = Subscription()
        assert s.id.startswith("sub_")
        assert s.active is True

    def test_to_dict(self):
        s = Subscription(workspace_id="ws-1", agent_module_id="agent_abc")
        d = s.to_dict()
        assert d["workspace_id"] == "ws-1"
        assert d["agent_module_id"] == "agent_abc"
        assert d["active"] is True

    def test_from_dict(self):
        s = Subscription.from_dict({"workspace_id": "ws-1", "agent_module_id": "agent_abc"})
        assert s.workspace_id == "ws-1"
        assert s.active is True
