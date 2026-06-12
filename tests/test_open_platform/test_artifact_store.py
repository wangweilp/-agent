"""Artifact Store 单元测试。

覆盖:
- CRUD: create, get, list, update, update_status, delete
- 状态迁移: draft→review→approved→published
- 安全硬约束: execution_allowed/runtime_enabled 强制 False
- 错误处理: NotFound, StateError, ValidationError
- 过滤查询: workspace_id, agent_id, artifact_type, status
- SQLite 稳定性: schema init, flush
"""

from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.artifact_store import SQLiteArtifactStore
from src.open_platform.artifact import (
    Artifact,
    ArtifactNotFoundError,
    ArtifactStateError,
    ArtifactStatus,
    ArtifactType,
    ArtifactValidationError,
)


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test_artifact.db")
    yield path
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def store(settings, tmp_db_path):
    return SQLiteArtifactStore(settings, db_path=tmp_db_path)


# ═══════════════════════════════════════════
# Create
# ═══════════════════════════════════════════

class TestCreate:
    def test_create_draft_artifact(self, store):
        a = Artifact(
            workspace_id="ws-1",
            agent_id="agent-1",
            title="Test Artifact",
            artifact_type=ArtifactType.CODE,
        )
        created = store.create(a)
        assert created.id.startswith("art_")
        assert created.status == ArtifactStatus.DRAFT
        assert created.execution_allowed is False
        assert created.runtime_enabled is False
        assert created.metadata_only is True

    def test_create_enforces_safety_constraints(self, store):
        """store.create 强制安全约束。"""
        a = Artifact(
            workspace_id="ws-1",
            agent_id="agent-1",
            title="Test",
        )
        # 尝试绕过约束
        a.execution_allowed = True
        a.runtime_enabled = True
        a.metadata_only = False
        created = store.create(a)
        # 创建后强制回安全值
        assert created.execution_allowed is False
        assert created.runtime_enabled is False
        assert created.metadata_only is True

    def test_create_requires_draft_status(self, store):
        """创建 artifact 状态必须为 draft。"""
        a = Artifact(
            workspace_id="ws-1",
            agent_id="agent-1",
            title="Test",
            status=ArtifactStatus.APPROVED,
        )
        with pytest.raises(ArtifactStateError, match="draft"):
            store.create(a)

    def test_create_validation_error(self, store):
        """缺少必填字段应抛出 ArtifactValidationError。"""
        a = Artifact()  # 缺少 workspace_id, agent_id, title
        with pytest.raises(ArtifactValidationError):
            store.create(a)

    def test_create_all_artifact_types(self, store):
        """所有 artifact_type 都可以创建。"""
        for at in ArtifactType:
            a = Artifact(
                workspace_id="ws-1",
                agent_id="agent-1",
                title=f"Test {at.value}",
                artifact_type=at.value,
            )
            created = store.create(a)
            assert created.artifact_type == at.value


# ═══════════════════════════════════════════
# Get
# ═══════════════════════════════════════════

class TestGet:
    def test_get_existing(self, store):
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="agent-1", title="Test",
        ))
        fetched = store.get(a.id)
        assert fetched is not None
        assert fetched.id == a.id
        assert fetched.title == "Test"

    def test_get_nonexistent(self, store):
        assert store.get("art_nonexistent") is None


# ═══════════════════════════════════════════
# List
# ═══════════════════════════════════════════

class TestList:
    def test_list_all(self, store):
        store.create(Artifact(workspace_id="ws-1", agent_id="a1", title="T1"))
        store.create(Artifact(workspace_id="ws-1", agent_id="a2", title="T2"))
        results = store.list()
        assert len(results) == 2

    def test_list_filter_workspace(self, store):
        store.create(Artifact(workspace_id="ws-1", agent_id="a1", title="T1"))
        store.create(Artifact(workspace_id="ws-2", agent_id="a2", title="T2"))
        results = store.list(workspace_id="ws-1")
        assert len(results) == 1
        assert results[0].workspace_id == "ws-1"

    def test_list_filter_agent(self, store):
        store.create(Artifact(workspace_id="ws-1", agent_id="a1", title="T1"))
        store.create(Artifact(workspace_id="ws-1", agent_id="a2", title="T2"))
        results = store.list(agent_id="a1")
        assert len(results) == 1
        assert results[0].agent_id == "a1"

    def test_list_filter_type(self, store):
        store.create(Artifact(workspace_id="ws-1", agent_id="a1", title="T1",
            artifact_type=ArtifactType.CODE))
        store.create(Artifact(workspace_id="ws-1", agent_id="a2", title="T2",
            artifact_type=ArtifactType.PROMPT))
        results = store.list(artifact_type=ArtifactType.PROMPT)
        assert len(results) == 1
        assert results[0].artifact_type == ArtifactType.PROMPT

    def test_list_filter_status(self, store):
        a = store.create(Artifact(workspace_id="ws-1", agent_id="a1", title="T1"))
        store.update_status(a.id, ArtifactStatus.REVIEW)
        results = store.list(status=ArtifactStatus.REVIEW)
        assert len(results) == 1
        assert results[0].status == ArtifactStatus.REVIEW

    def test_list_pagination(self, store):
        for i in range(5):
            store.create(Artifact(workspace_id="ws-1", agent_id="a1", title=f"T{i}"))
        results = store.list(limit=2, offset=0)
        assert len(results) == 2
        results2 = store.list(limit=5, offset=2)
        assert len(results2) == 3


# ═══════════════════════════════════════════
# Update
# ═══════════════════════════════════════════

class TestUpdate:
    def test_update_draft_content(self, store):
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Original",
        ))
        a.title = "Updated"
        a.content = "new content"
        store.update(a)
        fetched = store.get(a.id)
        assert fetched.title == "Updated"
        assert fetched.content == "new content"

    def test_update_enforces_safety(self, store):
        """update 也强制安全约束。"""
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Test",
        ))
        a.execution_allowed = True
        store.update(a)
        fetched = store.get(a.id)
        assert fetched.execution_allowed is False

    def test_cannot_update_review_artifact(self, store):
        """review 状态的 artifact 不可编辑。"""
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Test",
        ))
        store.update_status(a.id, ArtifactStatus.REVIEW)
        a.title = "New Title"
        with pytest.raises(ArtifactStateError, match="不允许编辑"):
            store.update(a)

    def test_cannot_update_approved_artifact(self, store):
        """approved 状态的 artifact 不可编辑。"""
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Test",
        ))
        store.update_status(a.id, ArtifactStatus.REVIEW)
        store.update_status(a.id, ArtifactStatus.APPROVED)
        a.title = "New Title"
        with pytest.raises(ArtifactStateError):
            store.update(a)

    def test_cannot_update_published_artifact(self, store):
        """published 状态的 artifact 不可编辑。"""
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Test",
        ))
        store.update_status(a.id, ArtifactStatus.REVIEW)
        store.update_status(a.id, ArtifactStatus.APPROVED)
        store.update_status(a.id, ArtifactStatus.PUBLISHED)
        a.title = "New Title"
        with pytest.raises(ArtifactStateError):
            store.update(a)

    def test_update_nonexistent(self, store):
        a = Artifact(
            id="art_nonexistent", workspace_id="ws-1",
            agent_id="a1", title="Test",
        )
        with pytest.raises(ArtifactNotFoundError):
            store.update(a)

    def test_update_preserves_status(self, store):
        """update 不能改 status。"""
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Test",
        ))
        a.status = ArtifactStatus.PUBLISHED  # 尝试改状态
        store.update(a)
        fetched = store.get(a.id)
        assert fetched.status == ArtifactStatus.DRAFT  # 状态不变


# ═══════════════════════════════════════════
# Update Status
# ═══════════════════════════════════════════

class TestUpdateStatus:
    def test_draft_to_review(self, store):
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Test",
        ))
        store.update_status(a.id, ArtifactStatus.REVIEW)
        fetched = store.get(a.id)
        assert fetched.status == ArtifactStatus.REVIEW

    def test_review_to_approved(self, store):
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Test",
        ))
        store.update_status(a.id, ArtifactStatus.REVIEW)
        store.update_status(
            a.id, ArtifactStatus.APPROVED,
            reviewed_by="reviewer-1", review_comment="Looks good",
        )
        fetched = store.get(a.id)
        assert fetched.status == ArtifactStatus.APPROVED
        assert fetched.reviewed_by == "reviewer-1"
        assert fetched.review_comment == "Looks good"
        assert fetched.reviewed_at is not None

    def test_review_to_rejected(self, store):
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Test",
        ))
        store.update_status(a.id, ArtifactStatus.REVIEW)
        store.update_status(
            a.id, ArtifactStatus.REJECTED,
            reviewed_by="reviewer-1", review_comment="Needs work",
        )
        fetched = store.get(a.id)
        assert fetched.status == ArtifactStatus.REJECTED

    def test_approved_to_published(self, store):
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Test",
        ))
        store.update_status(a.id, ArtifactStatus.REVIEW)
        store.update_status(a.id, ArtifactStatus.APPROVED)
        store.update_status(
            a.id, ArtifactStatus.PUBLISHED,
            published_by="pub-1",
        )
        fetched = store.get(a.id)
        assert fetched.status == ArtifactStatus.PUBLISHED
        assert fetched.published_by == "pub-1"
        assert fetched.published_at is not None

    def test_rejected_to_draft(self, store):
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Test",
        ))
        store.update_status(a.id, ArtifactStatus.REVIEW)
        store.update_status(a.id, ArtifactStatus.REJECTED)
        store.update_status(a.id, ArtifactStatus.DRAFT)
        fetched = store.get(a.id)
        assert fetched.status == ArtifactStatus.DRAFT

    def test_invalid_transition_raises_error(self, store):
        """非法状态迁移应抛出 ArtifactStateError。"""
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Test",
        ))
        with pytest.raises(ArtifactStateError, match="状态迁移非法"):
            store.update_status(a.id, ArtifactStatus.PUBLISHED)  # draft → published 不可

    def test_nonexistent_status_update(self, store):
        with pytest.raises(ArtifactNotFoundError):
            store.update_status("art_nonexistent", ArtifactStatus.REVIEW)


# ═══════════════════════════════════════════
# Delete
# ═══════════════════════════════════════════

class TestDelete:
    def test_delete_draft(self, store):
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Test",
        ))
        store.delete(a.id)
        assert store.get(a.id) is None

    def test_delete_rejected(self, store):
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Test",
        ))
        store.update_status(a.id, ArtifactStatus.REVIEW)
        store.update_status(a.id, ArtifactStatus.REJECTED)
        store.delete(a.id)
        assert store.get(a.id) is None

    def test_cannot_delete_review_artifact(self, store):
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Test",
        ))
        store.update_status(a.id, ArtifactStatus.REVIEW)
        with pytest.raises(ArtifactStateError, match="不允许删除"):
            store.delete(a.id)

    def test_cannot_delete_approved_artifact(self, store):
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Test",
        ))
        store.update_status(a.id, ArtifactStatus.REVIEW)
        store.update_status(a.id, ArtifactStatus.APPROVED)
        with pytest.raises(ArtifactStateError):
            store.delete(a.id)

    def test_cannot_delete_published_artifact(self, store):
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="a1", title="Test",
        ))
        store.update_status(a.id, ArtifactStatus.REVIEW)
        store.update_status(a.id, ArtifactStatus.APPROVED)
        store.update_status(a.id, ArtifactStatus.PUBLISHED)
        with pytest.raises(ArtifactStateError):
            store.delete(a.id)

    def test_delete_nonexistent(self, store):
        with pytest.raises(ArtifactNotFoundError):
            store.delete("art_nonexistent")


# ═══════════════════════════════════════════
# Full Review Pipeline
# ═══════════════════════════════════════════

class TestReviewPipeline:
    """完整审核流水线测试。"""

    def test_full_pipeline(self, store):
        """draft → review → approved → published。"""
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="agent-1",
            title="Pipeline Test", artifact_type=ArtifactType.CODE,
        ))
        assert a.status == ArtifactStatus.DRAFT

        # submit review
        store.update_status(a.id, ArtifactStatus.REVIEW)
        a = store.get(a.id)
        assert a.status == ArtifactStatus.REVIEW

        # approve
        store.update_status(
            a.id, ArtifactStatus.APPROVED,
            reviewed_by="reviewer-1", review_comment="LGTM",
        )
        a = store.get(a.id)
        assert a.status == ArtifactStatus.APPROVED

        # publish
        store.update_status(a.id, ArtifactStatus.PUBLISHED, published_by="pub-1")
        a = store.get(a.id)
        assert a.status == ArtifactStatus.PUBLISHED

    def test_reject_and_resubmit(self, store):
        """draft → review → rejected → draft → review → approved。"""
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="agent-1",
            title="Reject Test",
        ))
        store.update_status(a.id, ArtifactStatus.REVIEW)
        store.update_status(a.id, ArtifactStatus.REJECTED)
        a = store.get(a.id)
        assert a.status == ArtifactStatus.REJECTED

        # resubmit
        store.update_status(a.id, ArtifactStatus.DRAFT)
        a = store.get(a.id)
        assert a.status == ArtifactStatus.DRAFT

        store.update_status(a.id, ArtifactStatus.REVIEW)
        store.update_status(a.id, ArtifactStatus.APPROVED)
        a = store.get(a.id)
        assert a.status == ArtifactStatus.APPROVED

    def test_published_is_terminal(self, store):
        """published 后任何迁移都非法。"""
        a = store.create(Artifact(
            workspace_id="ws-1", agent_id="agent-1", title="Terminal Test",
        ))
        store.update_status(a.id, ArtifactStatus.REVIEW)
        store.update_status(a.id, ArtifactStatus.APPROVED)
        store.update_status(a.id, ArtifactStatus.PUBLISHED)

        with pytest.raises(ArtifactStateError):
            store.update_status(a.id, ArtifactStatus.DRAFT)


# ═══════════════════════════════════════════
# Store Safety (execution/runtime 禁止)
# ═══════════════════════════════════════════

class TestStoreSafety:
    """安全测试：所有 artifact 都不可执行。"""

    def test_all_artifacts_have_execution_false(self, store):
        """所有从 store 取出的 artifact，execution_allowed 都为 False。"""
        for at in ArtifactType:
            a = store.create(Artifact(
                workspace_id="ws", agent_id="a", title=f"T{at.value}",
                artifact_type=at.value,
            ))
            store.update_status(a.id, ArtifactStatus.REVIEW)
            store.update_status(a.id, ArtifactStatus.APPROVED)
            store.update_status(a.id, ArtifactStatus.PUBLISHED)
            fetched = store.get(a.id)
            assert fetched.execution_allowed is False
            assert fetched.runtime_enabled is False
            assert fetched.metadata_only is True

    def test_no_execution_methods_on_store(self, store):
        """Store 不能有执行相关方法。"""
        forbidden = ["execute", "run", "launch", "start_container", "spawn"]
        for attr in forbidden:
            assert not hasattr(store, attr), f"store 不应有 {attr} 方法"
