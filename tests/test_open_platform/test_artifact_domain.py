"""Artifact Domain Model 单元测试。

覆盖:
- Artifact 创建与默认值
- 校验: 必填字段、execution_allowed/runtime_enabled 硬约束
- 状态迁移规则
- 序列化/反序列化
- Store Protocol 接口检查
"""

from __future__ import annotations

import pytest

from src.open_platform.artifact import (
    Artifact,
    ArtifactStatus,
    ArtifactType,
    ArtifactValidationError,
    is_valid_transition,
    is_immutable,
    _VALID_TRANSITIONS,
)


# ═══════════════════════════════════════════
# Artifact 创建与默认值
# ═══════════════════════════════════════════

class TestArtifactCreation:
    """Artifact 创建。"""

    def test_default_values(self):
        a = Artifact()
        assert a.id.startswith("art_")
        assert a.workspace_id == ""
        assert a.agent_id == ""
        assert a.artifact_type == ArtifactType.CODE
        assert a.status == ArtifactStatus.DRAFT
        assert a.execution_allowed is False
        assert a.runtime_enabled is False
        assert a.metadata_only is True
        assert a.tags == []
        assert a.metadata == {}
        assert a.content == ""

    def test_create_with_values(self):
        a = Artifact(
            workspace_id="ws-1",
            agent_id="agent-1",
            artifact_type=ArtifactType.PROMPT,
            title="Test Prompt",
            description="A test prompt artifact",
            content="You are a helpful assistant.",
        )
        assert a.workspace_id == "ws-1"
        assert a.agent_id == "agent-1"
        assert a.artifact_type == ArtifactType.PROMPT
        assert a.title == "Test Prompt"
        assert a.execution_allowed is False
        assert a.runtime_enabled is False
        assert a.metadata_only is True

    def test_execution_allowed_always_false(self):
        """execution_allowed 永远是 False — 硬约束。"""
        a = Artifact()
        assert a.execution_allowed is False
        # 即使尝试修改，validate 也会报错
        # 注意：dataclass 允许直接赋值，但 store/create 会强制重置
        a.execution_allowed = True  # 绕过构造
        errors = a.validate()
        assert any("execution_allowed 必须为 False" in e for e in errors)

    def test_runtime_enabled_always_false(self):
        """runtime_enabled 永远是 False — 硬约束。"""
        a = Artifact()
        a.runtime_enabled = True
        errors = a.validate()
        assert any("runtime_enabled 必须为 False" in e for e in errors)

    def test_metadata_only_always_true(self):
        """metadata_only 永远是 True — 硬约束。"""
        a = Artifact()
        a.metadata_only = False
        errors = a.validate()
        assert any("metadata_only 必须为 True" in e for e in errors)


# ═══════════════════════════════════════════
# 校验
# ═══════════════════════════════════════════

class TestArtifactValidation:
    """Artifact 校验。"""

    def test_valid_artifact(self):
        a = Artifact(
            workspace_id="ws-1",
            agent_id="agent-1",
            title="Valid Artifact",
            artifact_type=ArtifactType.CODE,
        )
        assert a.is_valid()
        assert a.validate() == []

    def test_missing_workspace_id(self):
        a = Artifact(agent_id="agent-1", title="Test")
        errors = a.validate()
        assert any("workspace_id 必填" in e for e in errors)

    def test_missing_agent_id(self):
        a = Artifact(workspace_id="ws-1", title="Test")
        errors = a.validate()
        assert any("agent_id 必填" in e for e in errors)

    def test_missing_title(self):
        a = Artifact(workspace_id="ws-1", agent_id="agent-1")
        errors = a.validate()
        assert any("title 必填" in e for e in errors)

    def test_invalid_artifact_type(self):
        a = Artifact(
            workspace_id="ws-1",
            agent_id="agent-1",
            title="Test",
            artifact_type="invalid_type",
        )
        errors = a.validate()
        assert any("artifact_type 无效" in e for e in errors)

    def test_invalid_status(self):
        a = Artifact(
            workspace_id="ws-1",
            agent_id="agent-1",
            title="Test",
            status="invalid_status",
        )
        errors = a.validate()
        assert any("status 无效" in e for e in errors)

    def test_valid_artifact_types(self):
        """所有 ArtifactType 值都应通过验证。"""
        for at in ArtifactType:
            a = Artifact(
                workspace_id="ws-1",
                agent_id="agent-1",
                title="Test",
                artifact_type=at.value,
            )
            assert a.is_valid(), f"ArtifactType.{at.name} should be valid"


# ═══════════════════════════════════════════
# 状态迁移
# ═══════════════════════════════════════════

class TestArtifactTransitions:
    """状态迁移规则。"""

    def test_valid_transition_draft_to_review(self):
        assert is_valid_transition(ArtifactStatus.DRAFT, ArtifactStatus.REVIEW) is True

    def test_valid_transition_review_to_approved(self):
        assert is_valid_transition(ArtifactStatus.REVIEW, ArtifactStatus.APPROVED) is True

    def test_valid_transition_review_to_rejected(self):
        assert is_valid_transition(ArtifactStatus.REVIEW, ArtifactStatus.REJECTED) is True

    def test_valid_transition_approved_to_published(self):
        assert is_valid_transition(ArtifactStatus.APPROVED, ArtifactStatus.PUBLISHED) is True

    def test_valid_transition_rejected_to_draft(self):
        assert is_valid_transition(ArtifactStatus.REJECTED, ArtifactStatus.DRAFT) is True

    def test_invalid_transition_draft_to_approved(self):
        """不允许跳过 review。"""
        assert is_valid_transition(ArtifactStatus.DRAFT, ArtifactStatus.APPROVED) is False

    def test_invalid_transition_draft_to_published(self):
        """不允许跳过 review 和 approved。"""
        assert is_valid_transition(ArtifactStatus.DRAFT, ArtifactStatus.PUBLISHED) is False

    def test_invalid_transition_published_to_anything(self):
        """published 是终态，不可迁移到任何状态。"""
        for status in ArtifactStatus:
            assert is_valid_transition(ArtifactStatus.PUBLISHED, status) is False

    def test_invalid_transition_review_to_draft(self):
        """review 不能直接回到 draft。"""
        assert is_valid_transition(ArtifactStatus.REVIEW, ArtifactStatus.DRAFT) is False

    def test_can_transition_to_method(self):
        a = Artifact(
            workspace_id="ws-1", agent_id="agent-1", title="Test",
            status=ArtifactStatus.DRAFT,
        )
        assert a.can_transition_to(ArtifactStatus.REVIEW) is True
        assert a.can_transition_to(ArtifactStatus.APPROVED) is False

    def test_is_editable(self):
        a = Artifact(
            workspace_id="ws-1", agent_id="agent-1", title="Test",
            status=ArtifactStatus.DRAFT,
        )
        assert a.is_editable() is True

        a.status = ArtifactStatus.REVIEW
        assert a.is_editable() is False

        a.status = ArtifactStatus.APPROVED
        assert a.is_editable() is False

        a.status = ArtifactStatus.PUBLISHED
        assert a.is_editable() is False

        a.status = ArtifactStatus.REJECTED
        assert a.is_editable() is True

    def test_is_terminal(self):
        a = Artifact(
            workspace_id="ws-1", agent_id="agent-1", title="Test",
        )
        a.status = ArtifactStatus.PUBLISHED
        assert a.is_terminal() is True

        a.status = ArtifactStatus.REJECTED
        assert a.is_terminal() is True

        a.status = ArtifactStatus.DRAFT
        assert a.is_terminal() is False

    def test_immutable_check(self):
        assert is_immutable(ArtifactStatus.REVIEW) is True
        assert is_immutable(ArtifactStatus.APPROVED) is True
        assert is_immutable(ArtifactStatus.PUBLISHED) is True
        assert is_immutable(ArtifactStatus.DRAFT) is False
        assert is_immutable(ArtifactStatus.REJECTED) is False


# ═══════════════════════════════════════════
# 序列化
# ═══════════════════════════════════════════

class TestArtifactSerialization:
    """to_dict / from_dict。"""

    def test_to_dict_contains_all_fields(self):
        a = Artifact(
            workspace_id="ws-1",
            agent_id="agent-1",
            artifact_type=ArtifactType.WORKFLOW,
            title="My Workflow",
            description="A workflow artifact",
            content="steps: []",
            tags=["tag1", "tag2"],
            metadata={"key": "value"},
        )
        d = a.to_dict()
        assert d["id"].startswith("art_")
        assert d["workspace_id"] == "ws-1"
        assert d["agent_id"] == "agent-1"
        assert d["artifact_type"] == ArtifactType.WORKFLOW
        assert d["status"] == ArtifactStatus.DRAFT
        assert d["execution_allowed"] is False
        assert d["runtime_enabled"] is False
        assert d["metadata_only"] is True
        assert d["tags"] == ["tag1", "tag2"]
        assert d["metadata"] == {"key": "value"}

    def test_from_dict_roundtrip(self):
        a = Artifact(
            workspace_id="ws-1",
            agent_id="agent-1",
            artifact_type=ArtifactType.KNOWLEDGE_PACK,
            title="Knowledge Pack",
            description="A pack of knowledge",
            content="knowledge content",
            tags=["test"],
            metadata={"source": "agent"},
        )
        d = a.to_dict()
        a2 = Artifact.from_dict(d)
        assert a2.id == a.id
        assert a2.workspace_id == a.workspace_id
        assert a2.agent_id == a.agent_id
        assert a2.artifact_type == a.artifact_type
        assert a2.title == a.title
        assert a2.execution_allowed is False
        assert a2.runtime_enabled is False
        assert a2.metadata_only is True
        assert a2.tags == a.tags

    def test_from_dict_always_sets_false_constraints(self):
        """即使 dict 中有 execution_allowed=True，from_dict 也强制为 False。"""
        d = {
            "workspace_id": "ws-1",
            "agent_id": "agent-1",
            "title": "Test",
            "execution_allowed": True,
            "runtime_enabled": True,
            "metadata_only": False,
        }
        a = Artifact.from_dict(d)
        assert a.execution_allowed is False
        assert a.runtime_enabled is False
        assert a.metadata_only is True


# ═══════════════════════════════════════════
# ArtifactType 枚举
# ═══════════════════════════════════════════

class TestArtifactType:
    """ArtifactType 枚举。"""

    def test_all_types_exist(self):
        types = [t.value for t in ArtifactType]
        assert "code" in types
        assert "workflow" in types
        assert "prompt" in types
        assert "knowledge_pack" in types
        assert "tool_bundle" in types
