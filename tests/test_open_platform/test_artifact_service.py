"""Artifact Service 单元测试。

覆盖:
- create_artifact
- submit_review
- approve
- reject
- publish
- get / list / delete
- 安全约束
"""

from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.artifact_store import SQLiteArtifactStore
from src.open_platform.artifact import (
    ArtifactNotFoundError,
    ArtifactStateError,
    ArtifactStatus,
    ArtifactType,
    ArtifactValidationError,
)
from src.open_platform.artifact_service import ArtifactService


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test_artifact_svc.db")
    yield path
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def store(settings, tmp_db_path):
    return SQLiteArtifactStore(settings, db_path=tmp_db_path)


@pytest.fixture
def service(store):
    return ArtifactService(store)


class TestCreateArtifact:
    def test_create(self, service):
        a = service.create_artifact(
            workspace_id="ws-1",
            agent_id="agent-1",
            artifact_type=ArtifactType.CODE,
            title="Test Artifact",
            description="desc",
            content="content",
            tags=["test"],
            metadata={"key": "val"},
        )
        assert a.id.startswith("art_")
        assert a.status == ArtifactStatus.DRAFT
        assert a.workspace_id == "ws-1"
        assert a.agent_id == "agent-1"
        assert a.execution_allowed is False
        assert a.runtime_enabled is False
        assert a.metadata_only is True

    def test_create_validation_fails(self, service):
        with pytest.raises(ArtifactValidationError):
            service.create_artifact(
                workspace_id="", agent_id="", artifact_type="invalid", title="",
            )

    def test_create_all_types(self, service):
        for at in ArtifactType:
            a = service.create_artifact(
                workspace_id="ws-1", agent_id="a1",
                artifact_type=at.value, title=f"Type {at.value}",
            )
            assert a.artifact_type == at.value


class TestReviewPipeline:
    """完整的审核流水线测试。"""

    def test_submit_review(self, service):
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.PROMPT, title="Prompt",
        )
        a = service.submit_review(a.id)
        assert a.status == ArtifactStatus.REVIEW

    def test_submit_review_wrong_status(self, service):
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.CODE, title="Test",
        )
        service.submit_review(a.id)
        # 已是 review，不能再提交
        with pytest.raises(ArtifactStateError):
            service.submit_review(a.id)

    def test_approve(self, service):
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.CODE, title="Test",
        )
        service.submit_review(a.id)
        a = service.approve(a.id, "reviewer-1", "Looks good")
        assert a.status == ArtifactStatus.APPROVED
        assert a.reviewed_by == "reviewer-1"
        assert a.review_comment == "Looks good"

    def test_approve_wrong_status(self, service):
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.CODE, title="Test",
        )
        with pytest.raises(ArtifactStateError):
            service.approve(a.id, "r1")

    def test_reject(self, service):
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.CODE, title="Test",
        )
        service.submit_review(a.id)
        a = service.reject(a.id, "reviewer-1", "Needs changes")
        assert a.status == ArtifactStatus.REJECTED
        assert a.review_comment == "Needs changes"

    def test_reject_wrong_status(self, service):
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.CODE, title="Test",
        )
        with pytest.raises(ArtifactStateError):
            service.reject(a.id, "r1")

    def test_publish(self, service):
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.CODE, title="Test",
        )
        service.submit_review(a.id)
        service.approve(a.id, "r1")
        a = service.publish(a.id, "pub-1")
        assert a.status == ArtifactStatus.PUBLISHED
        assert a.published_by == "pub-1"

    def test_publish_wrong_status(self, service):
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.CODE, title="Test",
        )
        with pytest.raises(ArtifactStateError):
            service.publish(a.id, "pub-1")

    def test_full_pipeline(self, service):
        """draft → review → approved → published。"""
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.TOOL_BUNDLE, title="Tool Bundle",
        )
        assert a.status == ArtifactStatus.DRAFT

        a = service.submit_review(a.id)
        assert a.status == ArtifactStatus.REVIEW

        a = service.approve(a.id, "r1", "LGTM")
        assert a.status == ArtifactStatus.APPROVED

        a = service.publish(a.id, "pub-1")
        assert a.status == ArtifactStatus.PUBLISHED

        # 确认安全约束
        assert a.execution_allowed is False
        assert a.runtime_enabled is False
        assert a.metadata_only is True

    def test_reject_and_resubmit_pipeline(self, service):
        """draft → review → rejected → draft → review → approved。"""
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.CODE, title="Test",
        )
        service.submit_review(a.id)
        a = service.reject(a.id, "r1", "Fix it")

        # 通过 store 回到 draft (service 暂不直接支持 resubmit 为独立方法)
        service._store.update_status(a.id, ArtifactStatus.DRAFT)
        service.submit_review(a.id)
        a = service.approve(a.id, "r1")
        assert a.status == ArtifactStatus.APPROVED

    def test_published_is_terminal(self, service):
        """published 后无法进一步迁移。"""
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.CODE, title="Test",
        )
        service.submit_review(a.id)
        service.approve(a.id, "r1")
        service.publish(a.id, "pub-1")
        # 不能再次 publish
        with pytest.raises(ArtifactStateError):
            service.publish(a.id, "pub-2")


class TestGetAndList:
    def test_get(self, service):
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.CODE, title="Test",
        )
        fetched = service.get(a.id)
        assert fetched is not None
        assert fetched.id == a.id

    def test_get_nonexistent(self, service):
        assert service.get("art_nonexistent") is None

    def test_list(self, service):
        service.create_artifact(workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.CODE, title="T1")
        service.create_artifact(workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.PROMPT, title="T2")
        results = service.list(workspace_id="ws-1")
        assert len(results) == 2

    def test_list_filter_status(self, service):
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.CODE, title="Test",
        )
        service.submit_review(a.id)
        results = service.list(workspace_id="ws-1", status=ArtifactStatus.REVIEW)
        assert len(results) == 1


class TestDelete:
    def test_delete_draft(self, service):
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.CODE, title="Test",
        )
        service.delete(a.id)
        assert service.get(a.id) is None

    def test_cannot_delete_active(self, service):
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.CODE, title="Test",
        )
        service.submit_review(a.id)
        with pytest.raises(ArtifactStateError):
            service.delete(a.id)


class TestSafetyConstraints:
    """服务层安全约束。"""

    def test_all_service_artifacts_safe(self, service):
        """通过 service 创建的所有 artifact 都应满足安全约束。"""
        for at in ArtifactType:
            a = service.create_artifact(
                workspace_id="ws", agent_id="a",
                artifact_type=at.value, title="Test",
            )
            assert a.execution_allowed is False
            assert a.runtime_enabled is False
            assert a.metadata_only is True
