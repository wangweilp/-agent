"""Signature Verifier — 签名声明的 metadata/trust-policy 层验证。

Step 24-C:
- METADATA_ONLY: 验证签名元数据格式/完整性，不做真实 cryptographic verification
- trusted_key_ids: 信任策略检查（key_id 是否在信任列表中）
- EXTERNAL_TOOL_RESERVED: 预留未来模式，当前返回 BLOCKED
- 不调用 cosign/gpg/minisign 外部命令
- 不启动 subprocess
- 不联网
- 不执行
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.open_platform.package_verification import (
    SignatureVerificationMode,
    VerificationCheck, VerificationCheckStatus, VerificationCheckType,
    VerificationSeverity, VerificationRunStatus,
)

_SUPPORTED_ALGOS = {"cosign", "minisign", "gpg"}


# ═══════════════════════════════════════════
# Models
# ═══════════════════════════════════════════


@dataclass
class SignatureVerificationRequest:
    artifact_id: str
    signature_algorithm: str | None = None
    signature_value: str | None = None
    signing_key_id: str | None = None
    mode: str = SignatureVerificationMode.METADATA_ONLY
    trusted_key_ids: list[str] = field(default_factory=list)


@dataclass
class SignatureVerificationResult:
    status: str = VerificationRunStatus.PENDING
    algorithm: str | None = None
    signature_value_present: bool = False
    signing_key_id_present: bool = False
    trusted_key_id: str | None = None
    signature_verified: bool = False
    mode: str = SignatureVerificationMode.METADATA_ONLY
    message: str = ""
    checks: list[VerificationCheck] = field(default_factory=list)
    no_network_used: bool = True
    no_execution_used: bool = True
    no_download_used: bool = True


# ═══════════════════════════════════════════
# Core Logic
# ═══════════════════════════════════════════


def verify_signature(request: SignatureVerificationRequest) -> SignatureVerificationResult:
    result = SignatureVerificationResult(
        algorithm=request.signature_algorithm, mode=request.mode,
    )

    # Step 0: EXTERNAL_TOOL_RESERVED — blocked
    if request.mode == SignatureVerificationMode.EXTERNAL_TOOL_RESERVED:
        result.checks.append(_chk(VerificationCheckType.SIGNATURE_METADATA, VerificationCheckStatus.BLOCKED,
                                  VerificationSeverity.BLOCKER,
                                  "EXTERNAL_TOOL_RESERVED mode: external signature tools not available in Step 24-C."))
        _finalize(result); return result

    # Check 1: Algorithm validation
    algo = (request.signature_algorithm or "").lower().strip()
    if not algo:
        result.checks.append(_chk(VerificationCheckType.SIGNATURE_FORMAT, VerificationCheckStatus.WARNING,
                                  VerificationSeverity.WARNING, "No signature_algorithm declared."))
    elif algo not in _SUPPORTED_ALGOS:
        result.checks.append(_chk(VerificationCheckType.SIGNATURE_FORMAT, VerificationCheckStatus.FAILED,
                                  VerificationSeverity.ERROR,
                                  f"Unsupported signature algorithm '{algo}'. Supported: {sorted(_SUPPORTED_ALGOS)}."))
    else:
        result.checks.append(_chk(VerificationCheckType.SIGNATURE_FORMAT, VerificationCheckStatus.PASSED,
                                  VerificationSeverity.INFO, f"Signature algorithm '{algo}' recognized."))

    # Check 2: Signature value presence
    sig_val = (request.signature_value or "").strip()
    result.signature_value_present = bool(sig_val)
    if not sig_val:
        result.checks.append(_chk(VerificationCheckType.SIGNATURE_METADATA, VerificationCheckStatus.WARNING,
                                  VerificationSeverity.WARNING, "No signature_value provided."))
    else:
        result.checks.append(_chk(VerificationCheckType.SIGNATURE_METADATA, VerificationCheckStatus.PASSED,
                                  VerificationSeverity.INFO, "Signature value present."))

    # Check 3: Signing key ID
    key_id = (request.signing_key_id or "").strip()
    result.signing_key_id_present = bool(key_id)
    if not key_id:
        result.checks.append(_chk(VerificationCheckType.SIGNATURE_METADATA, VerificationCheckStatus.WARNING,
                                  VerificationSeverity.WARNING, "No signing_key_id provided."))
    else:
        result.checks.append(_chk(VerificationCheckType.SIGNATURE_METADATA, VerificationCheckStatus.PASSED,
                                  VerificationSeverity.INFO, f"Signing key ID present: {key_id}"))

    # Check 4: Trust policy
    if key_id and request.trusted_key_ids:
        if key_id in request.trusted_key_ids:
            result.trusted_key_id = key_id
            result.checks.append(_chk(VerificationCheckType.SIGNATURE_TRUST_POLICY, VerificationCheckStatus.PASSED,
                                      VerificationSeverity.INFO,
                                      f"Signing key '{key_id}' is in trusted key list."))
        else:
            result.checks.append(_chk(VerificationCheckType.SIGNATURE_TRUST_POLICY, VerificationCheckStatus.WARNING,
                                      VerificationSeverity.WARNING,
                                      f"Signing key '{key_id}' not in trusted key list."))
    elif key_id:
        result.checks.append(_chk(VerificationCheckType.SIGNATURE_TRUST_POLICY, VerificationCheckStatus.SKIPPED,
                                  VerificationSeverity.INFO, "No trusted key list configured. Trust policy skipped."))

    # Check 5: Cryptographic verification status
    # Step 24-C: metadata-only — signature_verified 始终 False（METADATA_ONLY 模式）
    result.signature_verified = False
    result.checks.append(_chk(VerificationCheckType.SIGNATURE_METADATA, VerificationCheckStatus.PASSED,
                              VerificationSeverity.INFO,
                              "Signature verified=metadata_only. Real cryptographic verification not performed in Step 24-C."))

    _finalize(result)
    return result


def _chk(ct, status, sev, msg, expected=None, actual=None, meta=None) -> VerificationCheck:
    return VerificationCheck(check_type=ct, status=status, severity=sev, message=msg,
                            expected=expected, actual=actual, metadata=meta or {})


def _finalize(result: SignatureVerificationResult) -> None:
    passed = sum(1 for c in result.checks if c.status == VerificationCheckStatus.PASSED)
    blocked = sum(1 for c in result.checks if c.status == VerificationCheckStatus.BLOCKED)
    failed = sum(1 for c in result.checks if c.status == VerificationCheckStatus.FAILED)
    warnings = sum(1 for c in result.checks if c.status == VerificationCheckStatus.WARNING)
    if blocked > 0: result.status = VerificationRunStatus.BLOCKED
    elif failed > 0: result.status = VerificationRunStatus.FAILED
    elif warnings > 0: result.status = VerificationRunStatus.PASSED_WITH_WARNINGS
    elif passed == len(result.checks): result.status = VerificationRunStatus.PASSED
    else: result.status = VerificationRunStatus.PASSED_WITH_WARNINGS
