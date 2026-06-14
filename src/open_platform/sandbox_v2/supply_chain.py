"""Sandbox v2 Supply Chain — 签名校验、SBOM 验证、漏洞扫描接口。

轻量默认实现 — 不做真实签名/扫描，只做接口和 trusted fixture。

安全约束：
- 不联网
- 不调用外部扫描器
- 不执行包
- 不做真实密码学验证（仅 trusted fixture）
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from src.open_platform.sandbox_v2.models import (
    SandboxV2SignatureStatus,
    SandboxV2SBOMStatus,
    SandboxV2VulnerabilityStatus,
    SandboxPackageSBOM,
    SandboxPackageVulnerabilityScanResult,
    SandboxV2RiskLevel,
)

logger = logging.getLogger(__name__)

TRUSTED_FIXTURE_SIGNATURE = "trusted-fixture-signature"


class SignatureVerifier:
    """签名校验器 — 接口 + trusted fixture 实现。

    不做真实复杂签名体系。只做接口和可测试的 fixture。
    """

    def verify_signature(
        self,
        package_ref: str,
        signature: str,
        public_key_ref: str | None = None,
    ) -> tuple[str, str]:
        """验证包签名。

        Returns: (status, reason)
        """
        if not signature or not signature.strip():
            return SandboxV2SignatureStatus.NOT_PROVIDED, "No signature provided."

        if signature == TRUSTED_FIXTURE_SIGNATURE:
            return SandboxV2SignatureStatus.VERIFIED, "Trusted fixture signature verified."

        if signature.startswith("fixture-") and len(signature) > 8:
            return SandboxV2SignatureStatus.VERIFIED, f"Fixture signature '{signature}' accepted."

        return SandboxV2SignatureStatus.FAILED, "Signature verification failed — unsupported signature format."


class SBOMValidator:
    """SBOM 校验器 — 支持 cyclonedx-json 和 spdx-json。

    只做基本 JSON 解析和字段校验，不执行包。
    """

    SUPPORTED_FORMATS = {"cyclonedx-json", "spdx-json"}

    def validate_sbom(
        self,
        sbom_content: str,
        format: str = "unknown",
    ) -> tuple[SandboxPackageSBOM | None, str]:
        """校验 SBOM 内容。

        Returns: (sbom_record | None, error_reason)
        """
        if format not in self.SUPPORTED_FORMATS and format != "unknown":
            return None, f"Unsupported SBOM format '{format}'. Supported: {sorted(self.SUPPORTED_FORMATS)}."

        # Parse JSON
        try:
            data = json.loads(sbom_content)
        except json.JSONDecodeError as e:
            return None, f"SBOM JSON parse error: {e}"

        if not isinstance(data, dict):
            return None, "SBOM root must be a JSON object."

        # Detect format from content
        detected_format = format
        if format == "unknown":
            detected_format = self._detect_format(data)
            if detected_format == "unknown":
                return None, "Could not detect SBOM format. Expects cyclonedx-json or spdx-json."

        # Validate based on format
        if detected_format == "cyclonedx-json":
            component_count = self._validate_cyclonedx(data)
        elif detected_format == "spdx-json":
            component_count = self._validate_spdx(data)
        else:
            return None, f"Could not validate format '{detected_format}'."

        sha256 = hashlib.sha256(sbom_content.encode("utf-8")).hexdigest()

        sbom = SandboxPackageSBOM(
            format=detected_format,
            content_sha256=sha256,
            component_count=component_count,
            created_at=datetime.now(timezone.utc),
            status=SandboxV2SBOMStatus.VERIFIED,
            metadata={"validation_method": "basic_structural"},
        )
        return sbom, ""

    def _detect_format(self, data: dict) -> str:
        if "bomFormat" in data and data.get("bomFormat") == "CycloneDX":
            return "cyclonedx-json"
        if "spdxVersion" in data or "SPDXID" in data:
            return "spdx-json"
        return "unknown"

    def _validate_cyclonedx(self, data: dict) -> int:
        components = data.get("components", [])
        if not isinstance(components, list):
            return 0
        return len(components)

    def _validate_spdx(self, data: dict) -> int:
        packages = data.get("packages", [])
        if not isinstance(packages, list):
            return 0
        return len(packages)

    def validate_sbom_dict(
        self,
        sbom_data: dict,
        format_hint: str = "unknown",
    ) -> tuple[SandboxPackageSBOM | None, str]:
        """直接校验 dict 格式的 SBOM。"""
        return self.validate_sbom(json.dumps(sbom_data), format_hint)


class VulnerabilityScanner:
    """漏洞扫描器 — 接口 + test fixture 实现。

    不联网，不调用外部扫描器。
    使用测试 fixture 返回 clean / findings_low / findings_high。
    """

    def scan_sbom(
        self,
        sbom: SandboxPackageSBOM,
        package_name: str = "",
        package_version: str = "",
        package_request_id: str = "",
    ) -> SandboxPackageVulnerabilityScanResult:
        """扫描 SBOM 返回漏洞结果。不联网。"""
        now = datetime.now(timezone.utc)

        # Fixture-based logic: check component count and name/version patterns
        if sbom.component_count == 0:
            status = SandboxV2VulnerabilityStatus.CLEAN
            findings: list[dict] = []
            summary = "No components to scan."
        elif "fixture-critical" in package_name.lower():
            status = SandboxV2VulnerabilityStatus.FINDINGS_CRITICAL
            findings = [{"id": "CVE-FIXTURE-001", "severity": "critical", "component": package_name, "description": "Test fixture critical finding."}]
            summary = "1 critical finding (fixture)."
        elif "fixture-high" in package_name.lower():
            status = SandboxV2VulnerabilityStatus.FINDINGS_HIGH
            findings = [{"id": "CVE-FIXTURE-002", "severity": "high", "component": package_name, "description": "Test fixture high finding."}]
            summary = "1 high finding (fixture)."
        elif sbom.component_count > 50:
            status = SandboxV2VulnerabilityStatus.FINDINGS_LOW
            findings = [{"id": "CVE-FIXTURE-LOW-1", "severity": "low", "component": "large-dependency-tree", "description": "Large component tree, low risk finding (fixture)."}]
            summary = "1 low finding (large component fixture)."
        else:
            status = SandboxV2VulnerabilityStatus.CLEAN
            findings = []
            summary = f"No vulnerability findings for {sbom.component_count} components (fixture scan)."

        result = SandboxPackageVulnerabilityScanResult(
            scan_id=f"sbxvuln_{uuid4().hex[:16]}",
            package_request_id=package_request_id,
            package_name=package_name,
            package_version=package_version,
            scanner="sbom_fixture_scanner",
            status=status,
            severity_summary=summary,
            critical_count=sum(1 for f in findings if f.get("severity") == "critical"),
            high_count=sum(1 for f in findings if f.get("severity") == "high"),
            medium_count=sum(1 for f in findings if f.get("severity") == "medium"),
            low_count=sum(1 for f in findings if f.get("severity") == "low"),
            findings=findings,
            created_at=now,
            metadata={"source": "fixture_scanner", "scanner_available": True},
        )
        return result
