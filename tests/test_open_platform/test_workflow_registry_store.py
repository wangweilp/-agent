"""Workflow Registry Store 单元测试。覆盖: CRUD, 状态迁移, 审核流水线。"""

from __future__ import annotations

import os, tempfile
import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.workflow_registry_store import SQLiteWorkflowStore
from src.open_platform.workflow_registry import (
    Workflow, WorkflowNotFoundError, WorkflowStateError,
    WorkflowStatus, WorkflowValidationError,
)


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")

@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test_wf.db")
    yield path
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def store(settings, tmp_db_path): return SQLiteWorkflowStore(settings, db_path=tmp_db_path)


class TestCreate:
    def test_create_draft(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="WF"))
        assert w.id.startswith("wf_")
        assert w.status == WorkflowStatus.DRAFT
        assert w.metadata_only is True

    def test_create_enforces_metadata_only(self, store):
        w = Workflow(workspace_id="ws-1", name="W")
        w.metadata_only = False
        created = store.create(w)
        assert created.metadata_only is True

    def test_create_requires_draft(self, store):
        with pytest.raises(WorkflowStateError):
            store.create(Workflow(workspace_id="ws-1", name="W", status=WorkflowStatus.APPROVED))

    def test_create_validation_error(self, store):
        with pytest.raises(WorkflowValidationError):
            store.create(Workflow())


class TestGet:
    def test_get_existing(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="W"))
        fetched = store.get(w.id)
        assert fetched is not None and fetched.id == w.id

    def test_get_nonexistent(self, store):
        assert store.get("wf_nonexistent") is None


class TestList:
    def test_list_all(self, store):
        store.create(Workflow(workspace_id="ws-1", name="A"))
        store.create(Workflow(workspace_id="ws-1", name="B"))
        assert len(store.list()) == 2

    def test_list_filter_workspace(self, store):
        store.create(Workflow(workspace_id="ws-1", name="A"))
        store.create(Workflow(workspace_id="ws-2", name="B"))
        assert len(store.list(workspace_id="ws-1")) == 1

    def test_list_filter_status(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="A"))
        store.update_status(w.id, WorkflowStatus.REVIEW)
        assert len(store.list(status=WorkflowStatus.REVIEW)) == 1

    def test_list_pagination(self, store):
        for i in range(5):
            store.create(Workflow(workspace_id="ws-1", name=f"W{i}"))
        assert len(store.list(limit=2)) == 2
        assert len(store.list(limit=5, offset=2)) == 3


class TestUpdate:
    def test_update_draft(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="Original"))
        w.name = "Updated"
        store.update(w)
        assert store.get(w.id).name == "Updated"

    def test_cannot_update_review(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="W"))
        store.update_status(w.id, WorkflowStatus.REVIEW)
        with pytest.raises(WorkflowStateError):
            store.update(w)

    def test_cannot_update_approved(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="W"))
        store.update_status(w.id, WorkflowStatus.REVIEW)
        store.update_status(w.id, WorkflowStatus.APPROVED)
        with pytest.raises(WorkflowStateError):
            store.update(w)

    def test_cannot_update_published(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="W"))
        store.update_status(w.id, WorkflowStatus.REVIEW)
        store.update_status(w.id, WorkflowStatus.APPROVED)
        store.update_status(w.id, WorkflowStatus.PUBLISHED)
        with pytest.raises(WorkflowStateError):
            store.update(w)


class TestUpdateStatus:
    def test_draft_to_review(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="W"))
        store.update_status(w.id, WorkflowStatus.REVIEW)
        assert store.get(w.id).status == WorkflowStatus.REVIEW

    def test_review_to_approved(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="W"))
        store.update_status(w.id, WorkflowStatus.REVIEW)
        store.update_status(w.id, WorkflowStatus.APPROVED, reviewed_by="r1", review_comment="OK")
        f = store.get(w.id)
        assert f.status == WorkflowStatus.APPROVED and f.reviewed_by == "r1"

    def test_review_to_rejected(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="W"))
        store.update_status(w.id, WorkflowStatus.REVIEW)
        store.update_status(w.id, WorkflowStatus.REJECTED, reviewed_by="r1")
        assert store.get(w.id).status == WorkflowStatus.REJECTED

    def test_approved_to_published(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="W"))
        store.update_status(w.id, WorkflowStatus.REVIEW)
        store.update_status(w.id, WorkflowStatus.APPROVED)
        store.update_status(w.id, WorkflowStatus.PUBLISHED, published_by="pub-1")
        f = store.get(w.id)
        assert f.status == WorkflowStatus.PUBLISHED and f.published_by == "pub-1"

    def test_rejected_to_draft(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="W"))
        store.update_status(w.id, WorkflowStatus.REVIEW)
        store.update_status(w.id, WorkflowStatus.REJECTED)
        store.update_status(w.id, WorkflowStatus.DRAFT)
        assert store.get(w.id).status == WorkflowStatus.DRAFT

    def test_invalid_transition(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="W"))
        with pytest.raises(WorkflowStateError):
            store.update_status(w.id, WorkflowStatus.PUBLISHED)


class TestDelete:
    def test_delete_draft(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="W"))
        store.delete(w.id)
        assert store.get(w.id) is None

    def test_delete_rejected(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="W"))
        store.update_status(w.id, WorkflowStatus.REVIEW)
        store.update_status(w.id, WorkflowStatus.REJECTED)
        store.delete(w.id)
        assert store.get(w.id) is None

    def test_cannot_delete_review(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="W"))
        store.update_status(w.id, WorkflowStatus.REVIEW)
        with pytest.raises(WorkflowStateError):
            store.delete(w.id)

    def test_cannot_delete_published(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="W"))
        store.update_status(w.id, WorkflowStatus.REVIEW)
        store.update_status(w.id, WorkflowStatus.APPROVED)
        store.update_status(w.id, WorkflowStatus.PUBLISHED)
        with pytest.raises(WorkflowStateError):
            store.delete(w.id)


class TestReviewPipeline:
    def test_full_pipeline(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="Pipeline"))
        store.update_status(w.id, WorkflowStatus.REVIEW)
        store.update_status(w.id, WorkflowStatus.APPROVED, reviewed_by="r1")
        store.update_status(w.id, WorkflowStatus.PUBLISHED, published_by="pub-1")
        final = store.get(w.id)
        assert final.status == WorkflowStatus.PUBLISHED and final.metadata_only is True

    def test_reject_and_resubmit(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="R"))
        store.update_status(w.id, WorkflowStatus.REVIEW)
        store.update_status(w.id, WorkflowStatus.REJECTED)
        store.update_status(w.id, WorkflowStatus.DRAFT)
        store.update_status(w.id, WorkflowStatus.REVIEW)
        store.update_status(w.id, WorkflowStatus.APPROVED)
        assert store.get(w.id).status == WorkflowStatus.APPROVED

    def test_published_terminal(self, store):
        w = store.create(Workflow(workspace_id="ws-1", name="T"))
        store.update_status(w.id, WorkflowStatus.REVIEW)
        store.update_status(w.id, WorkflowStatus.APPROVED)
        store.update_status(w.id, WorkflowStatus.PUBLISHED)
        with pytest.raises(WorkflowStateError):
            store.update_status(w.id, WorkflowStatus.DRAFT)
