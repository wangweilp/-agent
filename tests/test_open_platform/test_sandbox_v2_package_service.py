"""Test Sandbox v2 Package Service — 包服务层测试。"""
import pytest
import tempfile
import os
import shutil
from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
from src.open_platform.sandbox_v2.service import SandboxV2Service
from src.open_platform.sandbox_v2.artifacts import LocalSandboxArtifactStore
from src.open_platform.sandbox_v2.packages import LocalSandboxPackageQuarantineStore
from src.open_platform.sandbox_v2.models import (
    SandboxV2PackageRequestStatus, SandboxV2PackageQuarantineStatus,
    SandboxV2PackageManager, SandboxV2PackageSourceType,
    SandboxV2SignatureStatus, SandboxV2SBOMStatus,
)


@pytest.fixture
def service():
    db_fd, db_path = tempfile.mkstemp(suffix=".db"); art_root = tempfile.mkdtemp(); pkg_root = tempfile.mkdtemp()
    os.close(db_fd)
    settings = Settings()
    store = SQLiteSandboxV2Store(settings, db_path=db_path)
    queue = SQLiteSandboxV2Queue(settings, db_path=db_path)
    art_store = LocalSandboxArtifactStore(artifact_root=art_root)
    pkg_store = LocalSandboxPackageQuarantineStore(quarantine_root=pkg_root)
    svc = SandboxV2Service(store=store, queue=queue, artifact_store=art_store, package_store=pkg_store)
    yield svc
    try: os.unlink(db_path)
    except: pass
    for d in [art_root, pkg_root]:
        try: shutil.rmtree(d)
        except: pass


class TestPackageRequest:
    def test_offline_request_accepted(self, service):
        result = service.request_package(
            package_name="test-pkg", package_version="1.0",
            package_manager=SandboxV2PackageManager.PIP,
            source_type=SandboxV2PackageSourceType.OFFLINE_UPLOAD,
            source_url="offline://test",
        )
        assert result["accepted"] is True

    def test_external_request_rejected(self, service):
        result = service.request_package(
            package_name="ext-pkg",
            source_type=SandboxV2PackageSourceType.EXTERNAL_URL,
            source_url="https://pypi.org",
        )
        assert result["accepted"] is False

    def test_get_package_request(self, service):
        r = service.request_package(package_name="my-pkg", source_type=SandboxV2PackageSourceType.OFFLINE_UPLOAD, source_url="offline://x")
        req_id = r["package_request"]["package_request_id"]
        req = service.get_package_request(req_id)
        assert req is not None
        assert req.package_name == "my-pkg"


class TestQuarantine:
    def test_quarantine_success(self, service):
        r = service.request_package(package_name="q-pkg", source_type=SandboxV2PackageSourceType.OFFLINE_UPLOAD, source_url="offline://q")
        req_id = r["package_request"]["package_request_id"]
        result = service.quarantine_package(req_id, content_text="pkg content", original_filename="q.pkg")
        assert "error" not in result or not result["error"]
        assert result.get("quarantine_record") is not None

    def test_review_approved_metadata_only(self, service):
        r = service.request_package(package_name="rev-pkg", source_type=SandboxV2PackageSourceType.OFFLINE_UPLOAD, source_url="offline://rev")
        req_id = r["package_request"]["package_request_id"]
        qr = service.quarantine_package(req_id, content_text="x", original_filename="rev.pkg")
        qid = qr["quarantine_record"]["quarantine_id"]
        rev = service.review_quarantine_record(qid, "approved_metadata_only", "admin")
        assert "error" not in rev
        assert "not allow" in rev["message"].lower()

    def test_delete_quarantine(self, service):
        r = service.request_package(package_name="del-pkg", source_type=SandboxV2PackageSourceType.OFFLINE_UPLOAD, source_url="offline://del")
        req_id = r["package_request"]["package_request_id"]
        qr = service.quarantine_package(req_id, content_text="del", original_filename="del.pkg")
        qid = qr["quarantine_record"]["quarantine_id"]
        result = service.delete_quarantined_package(qid)
        assert result["deleted"] is True


class TestSBOMAndScan:
    def test_submit_sbom(self, service):
        r = service.request_package(package_name="sbom-pkg", source_type=SandboxV2PackageSourceType.OFFLINE_UPLOAD, source_url="offline://sbom")
        req_id = r["package_request"]["package_request_id"]
        sbom = '{"bomFormat":"CycloneDX","components":[{"name":"dep1"}]}'
        result = service.submit_package_sbom(req_id, sbom, "cyclonedx-json")
        assert "error" not in result
        assert result["validated"] is True

    def test_run_scan(self, service):
        r = service.request_package(package_name="scan-pkg", source_type=SandboxV2PackageSourceType.OFFLINE_UPLOAD, source_url="offline://scan")
        req_id = r["package_request"]["package_request_id"]
        result = service.run_package_vulnerability_scan(req_id)
        assert "scan" in result
