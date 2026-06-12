"""Package Registry Service 单元测试。"""

from __future__ import annotations

import os, tempfile
import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.package_registry_store import SQLitePackageStore
from src.open_platform.package_registry_service import PackageService
from src.open_platform.package_registry import (
    PackageNotFoundError, PackageStateError, PackageStatus, PackageValidationError,
)


@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")

@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test_pkg_svc.db")
    yield path
    import shutil; shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def store(settings, tmp_db_path): return SQLitePackageStore(settings, db_path=tmp_db_path)

@pytest.fixture
def service(store): return PackageService(store)


class TestCreate:
    def test_create(self, service):
        p = service.create_package(
            workspace_id="ws-1", name="Pkg", description="desc",
            artifact_ids=["art_1", "art_2"], version="1.0.0",
            tags=["ml"], metadata={"a": "b"},
        )
        assert p.id.startswith("pkg_")
        assert p.status == PackageStatus.DRAFT
        assert p.artifact_ids == ["art_1", "art_2"]
        assert p.version == "1.0.0"
        assert p.metadata_only is True

    def test_create_validation_fails(self, service):
        with pytest.raises(PackageValidationError):
            service.create_package(workspace_id="", name="")


class TestReviewPipeline:
    def test_full_pipeline(self, service):
        p = service.create_package(workspace_id="ws-1", name="Full")
        assert p.status == PackageStatus.DRAFT

        p = service.submit_review(p.id)
        assert p.status == PackageStatus.REVIEW

        p = service.approve(p.id, "r1", "LGTM")
        assert p.status == PackageStatus.APPROVED
        assert p.reviewed_by == "r1"

        p = service.publish(p.id, "pub-1")
        assert p.status == PackageStatus.PUBLISHED
        assert p.published_by == "pub-1"
        assert p.metadata_only is True

    def test_reject(self, service):
        p = service.create_package(workspace_id="ws-1", name="R")
        service.submit_review(p.id)
        p = service.reject(p.id, "r1", "bad")
        assert p.status == PackageStatus.REJECTED
        assert p.review_comment == "bad"

    def test_publish_wrong_status(self, service):
        p = service.create_package(workspace_id="ws-1", name="P")
        with pytest.raises(PackageStateError):
            service.publish(p.id, "pub-1")

    def test_approve_wrong_status(self, service):
        p = service.create_package(workspace_id="ws-1", name="P")
        with pytest.raises(PackageStateError):
            service.approve(p.id, "r1")


class TestGetAndList:
    def test_get(self, service):
        p = service.create_package(workspace_id="ws-1", name="P")
        assert service.get(p.id).name == "P"

    def test_get_nonexistent(self, service):
        assert service.get("pkg_nonexistent") is None

    def test_list(self, service):
        service.create_package(workspace_id="ws-1", name="A")
        service.create_package(workspace_id="ws-1", name="B")
        assert len(service.list(workspace_id="ws-1")) == 2


class TestDelete:
    def test_delete_draft(self, service):
        p = service.create_package(workspace_id="ws-1", name="D")
        service.delete(p.id)
        assert service.get(p.id) is None

    def test_cannot_delete_review(self, service):
        p = service.create_package(workspace_id="ws-1", name="R")
        service.submit_review(p.id)
        with pytest.raises(PackageStateError):
            service.delete(p.id)


class TestSafety:
    def test_all_metadata_only(self, service):
        p = service.create_package(workspace_id="ws-1", name="Safe")
        service.submit_review(p.id)
        service.approve(p.id, "r1")
        service.publish(p.id, "pub-1")
        final = service.get(p.id)
        assert final.metadata_only is True
