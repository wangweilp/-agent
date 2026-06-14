"""Sandbox v2 Package Policy — 包下载与供应链安全策略。

安全策略（必须遵守）：
1. 默认 deny
2. fail closed
3. external_url / public_registry 默认拒绝
4. offline_upload / internal_registry 可以进入 quarantine
5. 未知 package_manager / source_type 拒绝
6. 缺 sha256 → 不能 release
7. 缺签名 → 不能 release
8. 缺 SBOM → 不能 release
9. 漏洞扫描未完成 → 不能 release
10. 包名必须 sanitize，禁止路径穿越
11. source_url 不允许 file:// / metadata service
12. 所有 package request 默认 quarantine_required=true

不执行代码，不联网下载，不安装包。
"""

from __future__ import annotations

import logging
import re

from src.open_platform.sandbox_v2.models import (
    SandboxV2RiskLevel,
    SandboxV2PackageManager,
    SandboxV2PackageSourceType,
    SandboxPackageRequest,
    SandboxPackagePolicyDecision,
    BLOCKED_SOURCE_URL_PREFIXES,
    SAFE_SOURCE_URL_PREFIXES,
)

logger = logging.getLogger(__name__)

# 危险包名模式
_DANGEROUS_PACKAGE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\.\./"),
    re.compile(r"\.\.\\"),
    re.compile(r"^[A-Za-z]:\\"),
    re.compile(r"^/"),
    re.compile(r"^\\\\"),
]

# 安全版本号正则
_SAFE_VERSION_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\.\-\_\+]{0,99}$")


def evaluate_package_policy(
    request: SandboxPackageRequest,
    *,
    has_sha256: bool = False,
    has_signature: bool = False,
    has_sbom: bool = False,
    has_vulnerability_scan: bool = False,
) -> SandboxPackagePolicyDecision:
    """评估 package 请求策略，返回决策。"""
    try:
        return _evaluate_impl(
            request=request,
            has_sha256=has_sha256,
            has_signature=has_signature,
            has_sbom=has_sbom,
            has_vulnerability_scan=has_vulnerability_scan,
        )
    except Exception:
        logger.exception("package_policy_evaluation_failed")
        return SandboxPackagePolicyDecision(
            allowed=False,
            action="deny",
            reason="Package policy evaluation raised an exception — fail closed.",
            risk_level=SandboxV2RiskLevel.CRITICAL,
            matched_rules=["exception_fail_closed"],
            fail_closed=True,
        )


def _evaluate_impl(
    request: SandboxPackageRequest,
    has_sha256: bool,
    has_signature: bool,
    has_sbom: bool,
    has_vulnerability_scan: bool,
) -> SandboxPackagePolicyDecision:
    matched: list[str] = []

    # Rule 1: Validate package_name
    if not request.package_name or not request.package_name.strip():
        return SandboxPackagePolicyDecision(
            reason="Package name is missing — fail closed.",
            risk_level=SandboxV2RiskLevel.HIGH,
            matched_rules=["package_name_missing"],
            fail_closed=True,
        )

    if _has_dangerous_pattern(request.package_name):
        return SandboxPackagePolicyDecision(
            reason=f"Package name '{request.package_name}' contains dangerous patterns.",
            risk_level=SandboxV2RiskLevel.CRITICAL,
            matched_rules=["package_name_dangerous"],
            fail_closed=True,
        )

    sanitized = _sanitize_package_name(request.package_name)
    if sanitized != request.package_name:
        return SandboxPackagePolicyDecision(
            reason=f"Package name contains unsafe characters. Sanitized: '{sanitized}'.",
            risk_level=SandboxV2RiskLevel.HIGH,
            matched_rules=["package_name_unsafe"],
            fail_closed=True,
        )

    matched.append("package_name_valid")

    # Rule 2: Validate version
    if request.package_version and not _SAFE_VERSION_RE.match(request.package_version):
        return SandboxPackagePolicyDecision(
            reason=f"Package version '{request.package_version}' is unsafe.",
            risk_level=SandboxV2RiskLevel.MEDIUM,
            matched_rules=["package_version_unsafe"],
            fail_closed=True,
        )
    matched.append("version_valid")

    # Rule 3: Validate package_manager
    valid_managers = {e.value for e in SandboxV2PackageManager}
    if request.package_manager not in valid_managers:
        return SandboxPackagePolicyDecision(
            reason=f"Unknown package_manager '{request.package_manager}' — fail closed.",
            risk_level=SandboxV2RiskLevel.HIGH,
            matched_rules=["package_manager_unknown"],
            fail_closed=True,
        )
    matched.append("package_manager_valid")

    # Rule 4: Validate source_type
    valid_sources = {e.value for e in SandboxV2PackageSourceType}
    if request.source_type not in valid_sources:
        return SandboxPackagePolicyDecision(
            reason=f"Unknown source_type '{request.source_type}' — fail closed.",
            risk_level=SandboxV2RiskLevel.HIGH,
            matched_rules=["source_type_unknown"],
            fail_closed=True,
        )

    # Rule 5: external_url / public_registry → deny
    if request.source_type in (SandboxV2PackageSourceType.EXTERNAL_URL, SandboxV2PackageSourceType.PUBLIC_REGISTRY):
        return SandboxPackagePolicyDecision(
            reason=f"Source type '{request.source_type}' is not allowed — network download is disabled.",
            risk_level=SandboxV2RiskLevel.HIGH,
            matched_rules=[*matched, "external_source_denied"],
            fail_closed=True,
        )

    matched.append("source_type_valid")

    # Rule 6: Validate source_url
    if request.source_url:
        if _has_dangerous_source_url(request.source_url):
            return SandboxPackagePolicyDecision(
                reason=f"Source URL '{request.source_url}' is blocked (dangerous pattern).",
                risk_level=SandboxV2RiskLevel.CRITICAL,
                matched_rules=[*matched, "source_url_dangerous"],
                fail_closed=True,
            )
        # Must match safe prefixes or be empty
        if not _is_safe_source_url(request.source_url):
            return SandboxPackagePolicyDecision(
                reason=f"Source URL '{request.source_url}' is not in the safe prefix list.",
                risk_level=SandboxV2RiskLevel.HIGH,
                matched_rules=[*matched, "source_url_not_safe"],
                fail_closed=True,
            )
    matched.append("source_url_valid")

    # Rule 7: Only offline_upload and internal_registry can enter quarantine
    if request.source_type in (SandboxV2PackageSourceType.OFFLINE_UPLOAD, SandboxV2PackageSourceType.INTERNAL_REGISTRY):
        # Allowed to quarantined, but not directly released
        matched.append("quarantine_allowed")
        return SandboxPackagePolicyDecision(
            allowed=True,
            action="quarantine",
            reason="Package can enter quarantine for review. Release requires hash, signature, SBOM, and vulnerability scan.",
            risk_level=SandboxV2RiskLevel.MEDIUM,
            require_hash=not has_sha256,
            require_signature=not has_signature,
            require_sbom=not has_sbom,
            require_vulnerability_scan=not has_vulnerability_scan,
            quarantine_required=True,
            network_download_allowed=False,
            matched_rules=matched,
            fail_closed=False,
        )

    matched.append("all_checks_passed")
    return SandboxPackagePolicyDecision(
        allowed=True,
        action="quarantine",
        reason="All package policy checks passed.",
        risk_level=SandboxV2RiskLevel.LOW,
        require_hash=not has_sha256,
        require_signature=not has_signature,
        require_sbom=not has_sbom,
        require_vulnerability_scan=not has_vulnerability_scan,
        quarantine_required=True,
        network_download_allowed=False,
        matched_rules=matched,
        fail_closed=False,
    )


def can_release_from_quarantine(
    sha256_provided: bool = False,
    signature_status: str = "not_provided",
    sbom_status: str = "not_provided",
    vulnerability_status: str = "not_scanned",
) -> tuple[bool, str]:
    """判断是否可以 release。所有条件必须满足。"""
    from src.open_platform.sandbox_v2.models import (
        SandboxV2SignatureStatus,
        SandboxV2SBOMStatus,
        SandboxV2VulnerabilityStatus,
    )
    if not sha256_provided:
        return False, "SHA256 hash is required for release."
    if signature_status != SandboxV2SignatureStatus.VERIFIED:
        return False, f"Signature verification required for release. Current: {signature_status}."
    if sbom_status not in (SandboxV2SBOMStatus.VERIFIED, SandboxV2SBOMStatus.PROVIDED):
        return False, f"SBOM verification required for release. Current: {sbom_status}."
    if vulnerability_status not in (SandboxV2VulnerabilityStatus.CLEAN, SandboxV2VulnerabilityStatus.FINDINGS_LOW):
        return False, f"Vulnerability scan must be clean or low-risk. Current: {vulnerability_status}."
    return True, "All release requirements met."


# ═══════════ Helpers ═══════════


def _has_dangerous_pattern(name: str) -> bool:
    for p in _DANGEROUS_PACKAGE_PATTERNS:
        if p.search(name):
            return True
    return False


def _sanitize_package_name(name: str) -> str:
    cleaned = name.strip()
    cleaned = re.sub(r'[^\w\.\-]', '', cleaned)[:100]
    return cleaned


def _has_dangerous_source_url(url: str) -> bool:
    lower = url.lower()
    for prefix in BLOCKED_SOURCE_URL_PREFIXES:
        if lower.startswith(prefix):
            return True
    return False


def _is_safe_source_url(url: str) -> bool:
    if not url:
        return True
    lower = url.lower()
    for prefix in SAFE_SOURCE_URL_PREFIXES:
        if lower.startswith(prefix):
            return True
    return False
