"""Package Registry Domain 单元测试。

覆盖:
- Package 创建与默认值
- 校验: 必填字段, metadata_only 硬约束
- 状态迁移规则
- 序列化/反序列化
"""

from __future__ import annotations

import pytest

from src.open_platform.package_registry import (
    Package,
    PackageStatus,
    PackageValidationError,
    is_valid_transition,
    is_immutable,
)


class TestPackageCreation:
    def test_default_values(self):
        p = Package()
        assert p.id.startswith("pkg_")
        assert p.workspace_id == ""
        assert p.name == ""
        assert p.artifact_ids == []
        assert p.version == "0.1.0"
        assert p.status == PackageStatus.DRAFT
        assert p.metadata_only is True
        assert p.tags == []

    def test_create_with_values(self):
        p = Package(
            workspace_id="ws-1", name="My Package",
            description="A test package", artifact_ids=["art_abc", "art_def"],
            version="1.0.0", tags=["ml", "nlp"],
            metadata={"author": "agent-1"},
        )
        assert p.workspace_id == "ws-1"
        assert p.name == "My Package"
        assert p.artifact_ids == ["art_abc", "art_def"]
        assert p.version == "1.0.0"
        assert p.metadata_only is True

    def test_metadata_only_always_true(self):
        p = Package()
        p.metadata_only = False
        errors = p.validate()
        assert any("metadata_only 必须为 True" in e for e in errors)


class TestPackageValidation:
    def test_valid(self):
        p = Package(workspace_id="ws-1", name="Test")
        assert p.is_valid()

    def test_missing_workspace_id(self):
        p = Package(name="Test")
        errors = p.validate()
        assert any("workspace_id 必填" in e for e in errors)

    def test_missing_name(self):
        p = Package(workspace_id="ws-1")
        errors = p.validate()
        assert any("name 必填" in e for e in errors)

    def test_invalid_status(self):
        p = Package(workspace_id="ws-1", name="T", status="invalid")
        errors = p.validate()
        assert any("status 无效" in e for e in errors)


class TestPackageTransitions:
    def test_valid_draft_to_review(self):
        assert is_valid_transition(PackageStatus.DRAFT, PackageStatus.REVIEW)

    def test_valid_review_to_approved(self):
        assert is_valid_transition(PackageStatus.REVIEW, PackageStatus.APPROVED)

    def test_valid_review_to_rejected(self):
        assert is_valid_transition(PackageStatus.REVIEW, PackageStatus.REJECTED)

    def test_valid_approved_to_published(self):
        assert is_valid_transition(PackageStatus.APPROVED, PackageStatus.PUBLISHED)

    def test_valid_rejected_to_draft(self):
        assert is_valid_transition(PackageStatus.REJECTED, PackageStatus.DRAFT)

    def test_invalid_draft_to_approved(self):
        assert not is_valid_transition(PackageStatus.DRAFT, PackageStatus.APPROVED)

    def test_invalid_draft_to_published(self):
        assert not is_valid_transition(PackageStatus.DRAFT, PackageStatus.PUBLISHED)

    def test_published_is_terminal(self):
        for s in PackageStatus:
            assert not is_valid_transition(PackageStatus.PUBLISHED, s)

    def test_can_transition_to(self):
        p = Package(workspace_id="ws-1", name="T")
        assert p.can_transition_to(PackageStatus.REVIEW)
        assert not p.can_transition_to(PackageStatus.APPROVED)

    def test_is_editable(self):
        p = Package(workspace_id="ws-1", name="T")
        assert p.is_editable()
        p.status = PackageStatus.REVIEW
        assert not p.is_editable()

    def test_is_terminal(self):
        p = Package(workspace_id="ws-1", name="T")
        assert not p.is_terminal()
        p.status = PackageStatus.PUBLISHED
        assert p.is_terminal()
        p.status = PackageStatus.REJECTED
        assert p.is_terminal()


class TestPackageSerialization:
    def test_to_dict(self):
        p = Package(workspace_id="ws-1", name="Pkg", artifact_ids=["art_1"],
                    version="2.0.0", tags=["t1"], metadata={"k": "v"})
        d = p.to_dict()
        assert d["id"].startswith("pkg_")
        assert d["workspace_id"] == "ws-1"
        assert d["artifact_ids"] == ["art_1"]
        assert d["version"] == "2.0.0"
        assert d["metadata_only"] is True

    def test_from_dict_roundtrip(self):
        p = Package(workspace_id="ws-1", name="Pkg", artifact_ids=["art_1"])
        d = p.to_dict()
        p2 = Package.from_dict(d)
        assert p2.id == p.id
        assert p2.name == p.name
        assert p2.artifact_ids == p.artifact_ids
        assert p2.metadata_only is True

    def test_from_dict_always_metadata_only(self):
        d = {"workspace_id": "ws", "name": "P", "metadata_only": False}
        p = Package.from_dict(d)
        assert p.metadata_only is True
