"""Red-Team Package Supply Chain Tests — 包供应链攻击测试。

验证：external URL/public registry 拒绝、file:// 拒绝、metadata URL 拒绝、路径穿越拒绝、
dangerous package manager/source 拒绝、缺 sha256/signature/SBOM/scan 不能 release。
"""

import pytest
from src.open_platform.sandbox_v2.models import (
    SandboxPackageRequest, SandboxV2PackageManager, SandboxV2PackageSourceType,
)
from src.open_platform.sandbox_v2.package_policy import (
    evaluate_package_policy, can_release_from_quarantine,
)


def _req(**kw):
    return SandboxPackageRequest(
        package_name=kw.get("package_name", "safe-pkg"),
        package_manager=kw.get("package_manager", SandboxV2PackageManager.PIP),
        source_type=kw.get("source_type", SandboxV2PackageSourceType.OFFLINE_UPLOAD),
        source_url=kw.get("source_url", "offline://test"),
        **{k: v for k, v in kw.items() if k not in ("package_name", "package_manager", "source_type", "source_url")},
    )


class TestExternalRejection:
    def test_external_url(self): assert not evaluate_package_policy(_req(source_type=SandboxV2PackageSourceType.EXTERNAL_URL)).allowed
    def test_public_registry(self): assert not evaluate_package_policy(_req(source_type=SandboxV2PackageSourceType.PUBLIC_REGISTRY)).allowed

class TestDangerousSourceURL:
    def test_file_url(self): assert not evaluate_package_policy(_req(source_url="file:///etc/passwd")).allowed
    def test_metadata_url(self): assert not evaluate_package_policy(_req(source_url="http://169.254.169.254")).allowed

class TestPackageNameAbuse:
    def test_dot_dot(self): assert not evaluate_package_policy(_req(package_name="../etc/passwd")).allowed
    def test_windows_drive(self): assert not evaluate_package_policy(_req(package_name="C:\\Windows\\System32")).allowed

class TestUnknownManagerSource:
    def test_unknown_manager(self): assert not evaluate_package_policy(_req(package_manager="foobar")).allowed
    def test_unknown_source_type(self): assert not evaluate_package_policy(_req(source_type="marketplace")).allowed


class TestReleaseRequirements:
    def test_no_sha256(self): assert not can_release_from_quarantine(sha256_provided=False)[0]
    def test_no_signature(self): assert not can_release_from_quarantine(sha256_provided=True, signature_status="not_provided")[0]
    def test_no_sbom(self): assert not can_release_from_quarantine(sha256_provided=True, signature_status="verified", sbom_status="not_provided")[0]
    def test_critical_findings(self): assert not can_release_from_quarantine(sha256_provided=True, signature_status="verified", sbom_status="verified", vulnerability_status="findings_critical")[0]
    def test_high_findings(self): assert not can_release_from_quarantine(sha256_provided=True, signature_status="verified", sbom_status="verified", vulnerability_status="findings_high")[0]

class TestFailClosed:
    def test_none_request(self):
        d = evaluate_package_policy(None)  # type: ignore
        assert not d.allowed
        assert d.fail_closed is True
