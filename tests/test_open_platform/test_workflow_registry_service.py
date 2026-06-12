"""Workflow Registry Service 单元测试。"""

from __future__ import annotations

import os, tempfile
import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.workflow_registry_store import SQLiteWorkflowStore
from src.open_platform.workflow_registry_service import WorkflowService
from src.open_platform.workflow_registry import (
    WorkflowNotFoundError, WorkflowStateError, WorkflowStatus, WorkflowValidationError,
)


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")

@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test_wf_svc.db")
    yield path
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def store(settings, tmp_db_path): return SQLiteWorkflowStore(settings, db_path=tmp_db_path)

@pytest.fixture
def service(store): return WorkflowService(store)


class TestCreate:
    def test_create(self, service):
        w = service.create_workflow(
            workspace_id="ws-1", name="WF", description="desc",
            package_ids=["pkg_1", "pkg_2"], version="1.0.0",
            tags=["prod"], metadata={"a": "b"},
        )
        assert w.id.startswith("wf_")
        assert w.status == WorkflowStatus.DRAFT
        assert w.package_ids == ["pkg_1", "pkg_2"]
        assert w.metadata_only is True

    def test_create_validation_fails(self, service):
        with pytest.raises(WorkflowValidationError):
            service.create_workflow(workspace_id="", name="")


class TestReviewPipeline:
    def test_full_pipeline(self, service):
        w = service.create_workflow(workspace_id="ws-1", name="Full")
        w = service.submit_review(w.id)
        assert w.status == WorkflowStatus.REVIEW
        w = service.approve(w.id, "r1", "LGTM")
        assert w.status == WorkflowStatus.APPROVED and w.reviewed_by == "r1"
        w = service.publish(w.id, "pub-1")
        assert w.status == WorkflowStatus.PUBLISHED and w.published_by == "pub-1"
        assert w.metadata_only is True

    def test_reject(self, service):
        w = service.create_workflow(workspace_id="ws-1", name="R")
        service.submit_review(w.id)
        w = service.reject(w.id, "r1", "bad")
        assert w.status == WorkflowStatus.REJECTED

    def test_publish_wrong_status(self, service):
        w = service.create_workflow(workspace_id="ws-1", name="P")
        with pytest.raises(WorkflowStateError):
            service.publish(w.id, "pub-1")

    def test_approve_wrong_status(self, service):
        w = service.create_workflow(workspace_id="ws-1", name="P")
        with pytest.raises(WorkflowStateError):
            service.approve(w.id, "r1")

    def test_published_terminal(self, service):
        w = service.create_workflow(workspace_id="ws-1", name="T")
        service.submit_review(w.id)
        service.approve(w.id, "r1")
        service.publish(w.id, "pub-1")
        with pytest.raises(WorkflowStateError):
            service.publish(w.id, "pub-2")


class TestGetAndList:
    def test_get(self, service):
        w = service.create_workflow(workspace_id="ws-1", name="W")
        assert service.get(w.id).name == "W"

    def test_list(self, service):
        service.create_workflow(workspace_id="ws-1", name="A")
        service.create_workflow(workspace_id="ws-1", name="B")
        assert len(service.list(workspace_id="ws-1")) == 2


class TestDelete:
    def test_delete_draft(self, service):
        w = service.create_workflow(workspace_id="ws-1", name="D")
        service.delete(w.id)
        assert service.get(w.id) is None

    def test_cannot_delete_review(self, service):
        w = service.create_workflow(workspace_id="ws-1", name="R")
        service.submit_review(w.id)
        with pytest.raises(WorkflowStateError):
            service.delete(w.id)


class TestSafety:
    def test_all_metadata_only(self, service):
        w = service.create_workflow(workspace_id="ws-1", name="Safe")
        service.submit_review(w.id)
        service.approve(w.id, "r1")
        service.publish(w.id, "pub-1")
        final = service.get(w.id)
        assert final.metadata_only is True
