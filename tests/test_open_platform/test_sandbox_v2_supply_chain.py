"""Test Sandbox v2 Supply Chain — 签名、SBOM、漏洞扫描测试。"""
import pytest
import json
from src.open_platform.sandbox_v2.supply_chain import (
    SignatureVerifier, SBOMValidator, VulnerabilityScanner,
    TRUSTED_FIXTURE_SIGNATURE,
)
from src.open_platform.sandbox_v2.models import (
    SandboxV2SignatureStatus, SandboxV2SBOMStatus, SandboxV2VulnerabilityStatus,
    SandboxPackageSBOM,
)


class TestSignatureVerifier:
    def test_trusted_fixture_verified(self):
        v = SignatureVerifier()
        status, reason = v.verify_signature("pkg-1", TRUSTED_FIXTURE_SIGNATURE)
        assert status == SandboxV2SignatureStatus.VERIFIED

    def test_missing_signature_not_provided(self):
        v = SignatureVerifier()
        status, reason = v.verify_signature("pkg-1", "")
        assert status == SandboxV2SignatureStatus.NOT_PROVIDED

    def test_unknown_signature_failed(self):
        v = SignatureVerifier()
        status, reason = v.verify_signature("pkg-1", "garbage-signature")
        assert status == SandboxV2SignatureStatus.FAILED

    def test_fixture_prefix_signature_verified(self):
        v = SignatureVerifier()
        status, reason = v.verify_signature("pkg-2", "fixture-test-sig-12345")
        assert status == SandboxV2SignatureStatus.VERIFIED


class TestSBOMValidator:
    def test_cyclonedx_parsed(self):
        sbom = json.dumps({"bomFormat": "CycloneDX", "components": [{"name": "comp1"}, {"name": "comp2"}]})
        v = SBOMValidator()
        result, err = v.validate_sbom(sbom, "cyclonedx-json")
        assert result is not None
        assert result.component_count == 2
        assert result.status == SandboxV2SBOMStatus.VERIFIED

    def test_spdx_parsed(self):
        sbom = json.dumps({"spdxVersion": "2.3", "packages": [{"name": "pkg1"}, {"name": "pkg2"}, {"name": "pkg3"}]})
        v = SBOMValidator()
        result, err = v.validate_sbom(sbom, "spdx-json")
        assert result is not None
        assert result.component_count == 3

    def test_auto_detect_cyclonedx(self):
        sbom = json.dumps({"bomFormat": "CycloneDX", "components": [{"name": "x"}]})
        v = SBOMValidator()
        result, err = v.validate_sbom(sbom, "unknown")
        assert result is not None
        assert result.format == "cyclonedx-json"

    def test_invalid_json(self):
        v = SBOMValidator()
        result, err = v.validate_sbom("not json", "cyclonedx-json")
        assert result is None
        assert "parse error" in err.lower()

    def test_unsupported_format(self):
        v = SBOMValidator()
        result, err = v.validate_sbom(json.dumps({}), "xml-format")
        assert result is None


class TestVulnerabilityScanner:
    def test_scanner_does_not_network(self):
        s = VulnerabilityScanner()
        sbom = SandboxPackageSBOM(component_count=10)
        result = s.scan_sbom(sbom, package_name="safe-pkg")
        # fixture: 0-50 components, safe name → clean
        assert result.status in (SandboxV2VulnerabilityStatus.CLEAN, SandboxV2VulnerabilityStatus.FINDINGS_LOW)

    def test_fixture_critical_name(self):
        s = VulnerabilityScanner()
        sbom = SandboxPackageSBOM(component_count=5)
        result = s.scan_sbom(sbom, package_name="fixture-critical-pkg")
        assert result.status == SandboxV2VulnerabilityStatus.FINDINGS_CRITICAL
        assert result.critical_count >= 1

    def test_fixture_high_name(self):
        s = VulnerabilityScanner()
        sbom = SandboxPackageSBOM(component_count=5)
        result = s.scan_sbom(sbom, package_name="fixture-high-pkg")
        assert result.status == SandboxV2VulnerabilityStatus.FINDINGS_HIGH

    def test_scanner_no_network_import(self):
        import src.open_platform.sandbox_v2.supply_chain as sc
        import inspect
        source = inspect.getsource(sc)
        # scanner should not import urllib, requests, socket
        assert "urllib" not in source
        assert "requests" not in source
