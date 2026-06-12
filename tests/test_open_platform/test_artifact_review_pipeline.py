"""Artifact Review Pipeline 端到端测试。

覆盖完整审核流水线:
1. Draft → Review → Approved → Published
2. Draft → Review → Rejected → Draft → Review → Approved
3. 各种非法状态迁移
4. published 终态验证
5. 安全约束不变
"""

from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.artifact_store import SQLiteArtifactStore
from src.open_platform.artifact_service import ArtifactService
from src.open_platform.artifact import (
    Artifact,
    ArtifactNotFoundError,
    ArtifactStateError,
    ArtifactStatus,
    ArtifactType,
    is_valid_transition,
)


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test_pipeline.db")
    yield path
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def store(settings, tmp_db_path):
    return SQLiteArtifactStore(settings, db_path=tmp_db_path)


@pytest.fixture
def service(store):
    return ArtifactService(store)


# ═══════════════════════════════════════════
# Pipeline: Happy Path
# ═══════════════════════════════════════════


class TestHappyPath:
    """标准审核流水线。"""

    def test_draft_to_published(self, service):
        """draft → review → approved → published。"""
        # Step 1: Agent 创建 artifact
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="agent-1",
            artifact_type=ArtifactType.CODE,
            title="My Artifact",
            description="A useful artifact",
            content="print('hello')",
        )
        assert a.status == ArtifactStatus.DRAFT
        assert a.is_editable()
        assert a.execution_allowed is False

        # Step 2: 提交审核
        a = service.submit_review(a.id)
        assert a.status == ArtifactStatus.REVIEW
        assert not a.is_editable()

        # Step 3: 审核通过
        a = service.approve(a.id, "admin-1", "Reviewed and approved")
        assert a.status == ArtifactStatus.APPROVED
        assert a.reviewed_by == "admin-1"
        assert a.review_comment == "Reviewed and approved"
        assert a.reviewed_at is not None

        # Step 4: 发布
        a = service.publish(a.id, "publisher-1")
        assert a.status == ArtifactStatus.PUBLISHED
        assert a.published_by == "publisher-1"
        assert a.published_at is not None

        # 终态检查
        assert a.is_terminal()
        assert not a.is_editable()
        # 安全约束始终不变
        assert a.execution_allowed is False
        assert a.runtime_enabled is False
        assert a.metadata_only is True

    def test_multiple_artifacts_pipeline(self, service):
        """多个 artifact 各自独立走流水线。"""
        ids = []
        for i in range(3):
            a = service.create_artifact(
                workspace_id="ws-1", agent_id=f"agent-{i}",
                artifact_type=ArtifactType.PROMPT, title=f"Prompt {i}",
            )
            service.submit_review(a.id)
            service.approve(a.id, f"reviewer-{i}")
            service.publish(a.id, f"pub-{i}")
            ids.append(a.id)

        for aid in ids:
            a = service.get(aid)
            assert a.status == ArtifactStatus.PUBLISHED
            assert a.execution_allowed is False


# ═══════════════════════════════════════════
# Pipeline: Reject & Resubmit
# ═══════════════════════════════════════════


class TestRejectPath:
    """拒绝与重新提交流水线。"""

    def test_reject_flow(self, service):
        """draft → review → rejected → draft → review → approved。"""
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="agent-1",
            artifact_type=ArtifactType.WORKFLOW, title="Workflow",
        )
        service.submit_review(a.id)

        # 拒绝
        a = service.reject(a.id, "admin-1", "Incomplete implementation")
        assert a.status == ArtifactStatus.REJECTED
        assert a.reviewed_by == "admin-1"
        assert a.review_comment == "Incomplete implementation"

        # 被拒绝后可编辑
        assert a.is_editable()

        # 重新提交（回到 draft）
        service._store.update_status(a.id, ArtifactStatus.DRAFT)
        a = service.submit_review(a.id)
        assert a.status == ArtifactStatus.REVIEW

        # 通过
        a = service.approve(a.id, "admin-1", "Fixed now")
        assert a.status == ArtifactStatus.APPROVED

    def test_reject_cannot_go_directly_to_approved(self, service):
        """rejected → approved 非法。"""
        assert is_valid_transition(ArtifactStatus.REJECTED, ArtifactStatus.APPROVED) is False


# ═══════════════════════════════════════════
# Pipeline: Invalid Transitions
# ═══════════════════════════════════════════


class TestInvalidTransitions:
    """非法状态迁移。"""

    @pytest.mark.parametrize("from_status, to_status", [
        (ArtifactStatus.DRAFT, ArtifactStatus.APPROVED),
        (ArtifactStatus.DRAFT, ArtifactStatus.PUBLISHED),
        (ArtifactStatus.REVIEW, ArtifactStatus.DRAFT),
        (ArtifactStatus.APPROVED, ArtifactStatus.DRAFT),
        (ArtifactStatus.APPROVED, ArtifactStatus.REVIEW),
        (ArtifactStatus.APPROVED, ArtifactStatus.REJECTED),
        (ArtifactStatus.PUBLISHED, ArtifactStatus.DRAFT),
        (ArtifactStatus.PUBLISHED, ArtifactStatus.REVIEW),
        (ArtifactStatus.PUBLISHED, ArtifactStatus.APPROVED),
        (ArtifactStatus.PUBLISHED, ArtifactStatus.REJECTED),
    ])
    def test_invalid_transitions(self, service, from_status, to_status):
        assert is_valid_transition(from_status, to_status) is False, \
            f"{from_status} → {to_status} 应该是非法迁移"


# ═══════════════════════════════════════════
# Pipeline: Safety Throughout
# ═══════════════════════════════════════════


class TestSafetyThroughPipeline:
    """流水线全过程安全约束不变。"""

    def test_execution_always_false_through_pipeline(self, service):
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="a1",
            artifact_type=ArtifactType.CODE, title="Test",
        )
        assert a.execution_allowed is False
        assert a.runtime_enabled is False

        a = service.submit_review(a.id)
        assert a.execution_allowed is False

        a = service.approve(a.id, "r1")
        assert a.execution_allowed is False

        a = service.publish(a.id, "pub-1")
        assert a.execution_allowed is False
        assert a.runtime_enabled is False
        assert a.metadata_only is True

        # 即使从 store 直接读也是安全的
        raw = service._store.get(a.id)
        assert raw.execution_allowed is False
        assert raw.runtime_enabled is False
        assert raw.metadata_only is True

    def test_all_types_stay_safe(self, service):
        """所有类型在所有状态下都是安全的。"""
        for at in ArtifactType:
            a = service.create_artifact(
                workspace_id="ws", agent_id="a",
                artifact_type=at.value, title=f"Type {at.value}",
            )
            service.submit_review(a.id)
            service.approve(a.id, "r1")
            service.publish(a.id, "pub-1")
            final = service.get(a.id)
            assert final.execution_allowed is False
            assert final.runtime_enabled is False
            assert final.metadata_only is True
