"""Test Sandbox v2 Package Policy — 包策略测试。"""
import pytest
from src.open_platform.sandbox_v2.models import (
    SandboxPackageRequest,
    SandboxV2PackageManager,
    SandboxV2PackageSourceType,
)
from src.open_platform.sandbox_v2.package_policy import (
    evaluate_package_policy,
    can_release_from_quarantine,
)


def _req(**kw):
    return SandboxPackageRequest(
        package_name=kw.get("package_name", "test-pkg"),
        package_version=kw.get("package_version", "1.0.0"),
        package_manager=kw.get("package_manager", SandboxV2PackageManager.PIP),
        source_type=kw.get("source_type", SandboxV2PackageSourceType.OFFLINE_UPLOAD),
        source_url=kw.get("source_url", "offline://test"),
        **{k: v for k, v in kw.items() if k not in ("package_name", "package_version", "package_manager", "source_type", "source_url")},
    )


class TestPackagePolicy:
    def test_external_url_denied(self):
        d = evaluate_package_policy(_req(source_type=SandboxV2PackageSourceType.EXTERNAL_URL, source_url="https://pypi.org/simple/pkg"))
        assert d.allowed is False
        assert "external_source_denied" in d.matched_rules

    def test_public_registry_denied(self):
        d = evaluate_package_policy(_req(source_type=SandboxV2PackageSourceType.PUBLIC_REGISTRY))
        assert d.allowed is False

    def test_offline_upload_allowed_quarantine(self):
        d = evaluate_package_policy(_req())
        assert d.allowed is True
        assert d.action == "quarantine"
        assert d.quarantine_required is True
        assert d.network_download_allowed is False

    def test_unknown_package_manager_denied(self):
        d = evaluate_package_policy(_req(package_manager="foobar"))
        assert d.allowed is False
        assert "package_manager_unknown" in d.matched_rules

    def test_unknown_source_type_denied(self):
        d = evaluate_package_policy(_req(source_type="marketplace"))
        assert d.allowed is False

    def test_path_traversal_name_denied(self):
        d = evaluate_package_policy(_req(package_name="../etc/passwd"))
        assert d.allowed is False

    def test_windows_drive_name_denied(self):
        d = evaluate_package_policy(_req(package_name="C:\\Windows\\test"))
        assert d.allowed is False

    def test_dangerous_source_url_denied(self):
        d = evaluate_package_policy(_req(source_url="file:///etc/passwd", source_type=SandboxV2PackageSourceType.OFFLINE_UPLOAD))
        assert d.allowed is False

    def test_metadata_service_url_denied(self):
        d = evaluate_package_policy(_req(source_url="http://169.254.169.254/latest/meta-data", source_type=SandboxV2PackageSourceType.OFFLINE_UPLOAD))
        assert d.allowed is False

    def test_exception_fail_closed(self):
        d = evaluate_package_policy(None)  # type: ignore
        assert d.allowed is False
        assert d.fail_closed is True

    def test_unsafe_version_denied(self):
        d = evaluate_package_policy(_req(package_version="../../etc"))
        assert d.allowed is False
        assert "package_version_unsafe" in d.matched_rules


class TestCanRelease:
    def test_missing_sha256_cannot_release(self):
        ok, msg = can_release_from_quarantine(sha256_provided=False)
        assert ok is False

    def test_missing_signature_cannot_release(self):
        ok, msg = can_release_from_quarantine(sha256_provided=True, signature_status="not_provided")
        assert ok is False

    def test_missing_sbom_cannot_release(self):
        ok, msg = can_release_from_quarantine(sha256_provided=True, signature_status="verified", sbom_status="not_provided")
        assert ok is False

    def test_high_vulnerability_cannot_release(self):
        ok, msg = can_release_from_quarantine(sha256_provided=True, signature_status="verified", sbom_status="verified", vulnerability_status="findings_high")
        assert ok is False

    def test_clean_allows_release(self):
        ok, msg = can_release_from_quarantine(sha256_provided=True, signature_status="verified", sbom_status="verified", vulnerability_status="clean")
        assert ok is True
