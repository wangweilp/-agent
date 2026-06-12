"""Package Registry Store 单元测试。

覆盖: CRUD, 状态迁移, 审核流水线, 安全约束。
"""

from __future__ import annotations

import os, tempfile
import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.package_registry_store import SQLitePackageStore
from src.open_platform.package_registry import (
    Package, PackageNotFoundError, PackageStateError,
    PackageStatus, PackageValidationError,
)


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")

@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test_pkg.db")
    yield path
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def store(settings, tmp_db_path): return SQLitePackageStore(settings, db_path=tmp_db_path)


class TestCreate:
    def test_create_draft(self, store):
        p = store.create(Package(workspace_id="ws-1", name="Pkg"))
        assert p.id.startswith("pkg_")
        assert p.status == PackageStatus.DRAFT
        assert p.metadata_only is True

    def test_create_enforces_metadata_only(self, store):
        p = Package(workspace_id="ws-1", name="P")
        p.metadata_only = False
        created = store.create(p)
        assert created.metadata_only is True

    def test_create_requires_draft(self, store):
        with pytest.raises(PackageStateError):
            store.create(Package(workspace_id="ws-1", name="P", status=PackageStatus.APPROVED))

    def test_create_validation_error(self, store):
        with pytest.raises(PackageValidationError):
            store.create(Package())


class TestGet:
    def test_get_existing(self, store):
        p = store.create(Package(workspace_id="ws-1", name="P"))
        fetched = store.get(p.id)
        assert fetched is not None and fetched.id == p.id

    def test_get_nonexistent(self, store):
        assert store.get("pkg_nonexistent") is None


class TestList:
    def test_list_all(self, store):
        store.create(Package(workspace_id="ws-1", name="A"))
        store.create(Package(workspace_id="ws-1", name="B"))
        assert len(store.list()) == 2

    def test_list_filter_workspace(self, store):
        store.create(Package(workspace_id="ws-1", name="A"))
        store.create(Package(workspace_id="ws-2", name="B"))
        assert len(store.list(workspace_id="ws-1")) == 1

    def test_list_filter_status(self, store):
        p = store.create(Package(workspace_id="ws-1", name="A"))
        store.update_status(p.id, PackageStatus.REVIEW)
        assert len(store.list(status=PackageStatus.REVIEW)) == 1

    def test_list_pagination(self, store):
        for i in range(5):
            store.create(Package(workspace_id="ws-1", name=f"P{i}"))
        assert len(store.list(limit=2, offset=0)) == 2
        assert len(store.list(limit=5, offset=2)) == 3


class TestUpdate:
    def test_update_draft(self, store):
        p = store.create(Package(workspace_id="ws-1", name="Original"))
        p.name = "Updated"
        store.update(p)
        assert store.get(p.id).name == "Updated"

    def test_cannot_update_review(self, store):
        p = store.create(Package(workspace_id="ws-1", name="P"))
        store.update_status(p.id, PackageStatus.REVIEW)
        p.name = "New"
        with pytest.raises(PackageStateError, match="不允许编辑"):
            store.update(p)

    def test_cannot_update_approved(self, store):
        p = store.create(Package(workspace_id="ws-1", name="P"))
        store.update_status(p.id, PackageStatus.REVIEW)
        store.update_status(p.id, PackageStatus.APPROVED)
        with pytest.raises(PackageStateError):
            store.update(p)

    def test_cannot_update_published(self, store):
        p = store.create(Package(workspace_id="ws-1", name="P"))
        store.update_status(p.id, PackageStatus.REVIEW)
        store.update_status(p.id, PackageStatus.APPROVED)
        store.update_status(p.id, PackageStatus.PUBLISHED)
        with pytest.raises(PackageStateError):
            store.update(p)


class TestUpdateStatus:
    def test_draft_to_review(self, store):
        p = store.create(Package(workspace_id="ws-1", name="P"))
        store.update_status(p.id, PackageStatus.REVIEW)
        assert store.get(p.id).status == PackageStatus.REVIEW

    def test_review_to_approved(self, store):
        p = store.create(Package(workspace_id="ws-1", name="P"))
        store.update_status(p.id, PackageStatus.REVIEW)
        store.update_status(p.id, PackageStatus.APPROVED, reviewed_by="r1", review_comment="OK")
        f = store.get(p.id)
        assert f.status == PackageStatus.APPROVED
        assert f.reviewed_by == "r1"

    def test_review_to_rejected(self, store):
        p = store.create(Package(workspace_id="ws-1", name="P"))
        store.update_status(p.id, PackageStatus.REVIEW)
        store.update_status(p.id, PackageStatus.REJECTED, reviewed_by="r1")
        assert store.get(p.id).status == PackageStatus.REJECTED

    def test_approved_to_published(self, store):
        p = store.create(Package(workspace_id="ws-1", name="P"))
        store.update_status(p.id, PackageStatus.REVIEW)
        store.update_status(p.id, PackageStatus.APPROVED)
        store.update_status(p.id, PackageStatus.PUBLISHED, published_by="pub-1")
        f = store.get(p.id)
        assert f.status == PackageStatus.PUBLISHED
        assert f.published_by == "pub-1"

    def test_rejected_to_draft(self, store):
        p = store.create(Package(workspace_id="ws-1", name="P"))
        store.update_status(p.id, PackageStatus.REVIEW)
        store.update_status(p.id, PackageStatus.REJECTED)
        store.update_status(p.id, PackageStatus.DRAFT)
        assert store.get(p.id).status == PackageStatus.DRAFT

    def test_invalid_transition(self, store):
        p = store.create(Package(workspace_id="ws-1", name="P"))
        with pytest.raises(PackageStateError):
            store.update_status(p.id, PackageStatus.PUBLISHED)


class TestDelete:
    def test_delete_draft(self, store):
        p = store.create(Package(workspace_id="ws-1", name="P"))
        store.delete(p.id)
        assert store.get(p.id) is None

    def test_delete_rejected(self, store):
        p = store.create(Package(workspace_id="ws-1", name="P"))
        store.update_status(p.id, PackageStatus.REVIEW)
        store.update_status(p.id, PackageStatus.REJECTED)
        store.delete(p.id)
        assert store.get(p.id) is None

    def test_cannot_delete_review(self, store):
        p = store.create(Package(workspace_id="ws-1", name="P"))
        store.update_status(p.id, PackageStatus.REVIEW)
        with pytest.raises(PackageStateError):
            store.delete(p.id)

    def test_cannot_delete_published(self, store):
        p = store.create(Package(workspace_id="ws-1", name="P"))
        store.update_status(p.id, PackageStatus.REVIEW)
        store.update_status(p.id, PackageStatus.APPROVED)
        store.update_status(p.id, PackageStatus.PUBLISHED)
        with pytest.raises(PackageStateError):
            store.delete(p.id)


class TestReviewPipeline:
    def test_full_pipeline(self, store):
        p = store.create(Package(workspace_id="ws-1", name="Pipeline"))
        store.update_status(p.id, PackageStatus.REVIEW)
        store.update_status(p.id, PackageStatus.APPROVED, reviewed_by="r1")
        store.update_status(p.id, PackageStatus.PUBLISHED, published_by="pub-1")
        final = store.get(p.id)
        assert final.status == PackageStatus.PUBLISHED
        assert final.metadata_only is True

    def test_reject_and_resubmit(self, store):
        p = store.create(Package(workspace_id="ws-1", name="R"))
        store.update_status(p.id, PackageStatus.REVIEW)
        store.update_status(p.id, PackageStatus.REJECTED)
        store.update_status(p.id, PackageStatus.DRAFT)
        store.update_status(p.id, PackageStatus.REVIEW)
        store.update_status(p.id, PackageStatus.APPROVED)
        assert store.get(p.id).status == PackageStatus.APPROVED

    def test_published_terminal(self, store):
        p = store.create(Package(workspace_id="ws-1", name="T"))
        store.update_status(p.id, PackageStatus.REVIEW)
        store.update_status(p.id, PackageStatus.APPROVED)
        store.update_status(p.id, PackageStatus.PUBLISHED)
        with pytest.raises(PackageStateError):
            store.update_status(p.id, PackageStatus.DRAFT)
