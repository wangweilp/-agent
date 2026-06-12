"""Workflow Registry Domain 单元测试。"""

from __future__ import annotations

import pytest

from src.open_platform.workflow_registry import (
    Workflow, WorkflowStatus, is_valid_transition, is_immutable,
)


class TestWorkflowCreation:
    def test_default_values(self):
        w = Workflow()
        assert w.id.startswith("wf_")
        assert w.package_ids == []
        assert w.version == "0.1.0"
        assert w.status == WorkflowStatus.DRAFT
        assert w.metadata_only is True

    def test_create_with_values(self):
        w = Workflow(
            workspace_id="ws-1", name="My WF",
            description="A workflow", package_ids=["pkg_1", "pkg_2"],
            version="2.0.0", tags=["prod"], metadata={"key": "v"},
        )
        assert w.workspace_id == "ws-1"
        assert w.package_ids == ["pkg_1", "pkg_2"]
        assert w.version == "2.0.0"
        assert w.metadata_only is True

    def test_metadata_only_always_true(self):
        w = Workflow()
        w.metadata_only = False
        errors = w.validate()
        assert any("metadata_only 必须为 True" in e for e in errors)


class TestWorkflowValidation:
    def test_valid(self):
        w = Workflow(workspace_id="ws-1", name="W")
        assert w.is_valid()

    def test_missing_workspace_id(self):
        w = Workflow(name="W")
        errors = w.validate()
        assert any("workspace_id 必填" in e for e in errors)

    def test_missing_name(self):
        w = Workflow(workspace_id="ws-1")
        errors = w.validate()
        assert any("name 必填" in e for e in errors)

    def test_invalid_status(self):
        w = Workflow(workspace_id="ws-1", name="W", status="bad")
        errors = w.validate()
        assert any("status 无效" in e for e in errors)


class TestWorkflowTransitions:
    def test_valid_draft_to_review(self):
        assert is_valid_transition(WorkflowStatus.DRAFT, WorkflowStatus.REVIEW)

    def test_valid_review_to_approved(self):
        assert is_valid_transition(WorkflowStatus.REVIEW, WorkflowStatus.APPROVED)

    def test_valid_review_to_rejected(self):
        assert is_valid_transition(WorkflowStatus.REVIEW, WorkflowStatus.REJECTED)

    def test_valid_approved_to_published(self):
        assert is_valid_transition(WorkflowStatus.APPROVED, WorkflowStatus.PUBLISHED)

    def test_valid_rejected_to_draft(self):
        assert is_valid_transition(WorkflowStatus.REJECTED, WorkflowStatus.DRAFT)

    def test_invalid_draft_to_approved(self):
        assert not is_valid_transition(WorkflowStatus.DRAFT, WorkflowStatus.APPROVED)

    def test_invalid_draft_to_published(self):
        assert not is_valid_transition(WorkflowStatus.DRAFT, WorkflowStatus.PUBLISHED)

    def test_published_is_terminal(self):
        for s in WorkflowStatus:
            assert not is_valid_transition(WorkflowStatus.PUBLISHED, s)

    def test_can_transition_to(self):
        w = Workflow(workspace_id="ws-1", name="W")
        assert w.can_transition_to(WorkflowStatus.REVIEW)
        assert not w.can_transition_to(WorkflowStatus.APPROVED)

    def test_is_editable(self):
        w = Workflow(workspace_id="ws-1", name="W")
        assert w.is_editable()
        w.status = WorkflowStatus.REVIEW
        assert not w.is_editable()

    def test_is_terminal(self):
        w = Workflow(workspace_id="ws-1", name="W")
        assert not w.is_terminal()
        w.status = WorkflowStatus.PUBLISHED
        assert w.is_terminal()


class TestWorkflowSerialization:
    def test_to_dict(self):
        w = Workflow(workspace_id="ws-1", name="WF", package_ids=["pkg_1"],
                     version="3.0.0", tags=["t1"], metadata={"k": "v"})
        d = w.to_dict()
        assert d["id"].startswith("wf_")
        assert d["package_ids"] == ["pkg_1"]
        assert d["version"] == "3.0.0"
        assert d["metadata_only"] is True

    def test_from_dict_roundtrip(self):
        w = Workflow(workspace_id="ws-1", name="WF", package_ids=["pkg_1"])
        d = w.to_dict()
        w2 = Workflow.from_dict(d)
        assert w2.id == w.id
        assert w2.package_ids == w.package_ids
        assert w2.metadata_only is True

    def test_from_dict_always_metadata_only(self):
        d = {"workspace_id": "ws", "name": "W", "metadata_only": False}
        w = Workflow.from_dict(d)
        assert w.metadata_only is True
