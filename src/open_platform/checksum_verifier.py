"""Checksum Verifier — 对受控 bytes/local fixture 计算 hash。

Step 24-C:
- 支持 sha256 / sha384 / sha512
- 拒绝 md5 / sha1 / crc32
- content_bytes 或 local_path (受 allowed_root 限制)
- 不下载 / 不联网 / 不解压 / 不执行
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass, field
from typing import Any

from src.open_platform.package_verification import (
    VerificationCheck, VerificationCheckStatus, VerificationCheckType,
    VerificationSeverity, VerificationRunStatus,
)

_ALLOWED_ALGOS = {"sha256", "sha384", "sha512"}
_HEX_LENGTHS = {"sha256": 64, "sha384": 96, "sha512": 128}
_DEFAULT_MAX_FILE_BYTES = 50_000_000  # 50MB


# ═══════════════════════════════════════════
# Models
# ═══════════════════════════════════════════


@dataclass
class ChecksumVerificationRequest:
    artifact_id: str
    algorithm: str | None = None
    expected_checksum: str | None = None
    local_path: str | None = None
    content_bytes: bytes | None = None
    allowed_root: str | None = None
    max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES


@dataclass
class ChecksumVerificationResult:
    status: str = VerificationRunStatus.PENDING
    algorithm: str | None = None
    expected_checksum: str | None = None
    actual_checksum: str | None = None
    matched: bool = False
    message: str = ""
    checks: list[VerificationCheck] = field(default_factory=list)
    no_network_used: bool = True
    no_execution_used: bool = True
    no_download_used: bool = True


# ═══════════════════════════════════════════
# Core Logic
# ═══════════════════════════════════════════


def verify_checksum(request: ChecksumVerificationRequest) -> ChecksumVerificationResult:
    result = ChecksumVerificationResult(
        algorithm=request.algorithm, expected_checksum=request.expected_checksum,
    )

    # Check 1: Algorithm validation
    algo = (request.algorithm or "").lower().strip()
    if not algo:
        result.checks.append(_chk(VerificationCheckType.CHECKSUM_FORMAT, VerificationCheckStatus.FAILED,
                                  VerificationSeverity.ERROR, "checksum_algorithm not provided."))
    elif algo not in _ALLOWED_ALGOS:
        result.checks.append(_chk(VerificationCheckType.CHECKSUM_FORMAT, VerificationCheckStatus.BLOCKED,
                                  VerificationSeverity.BLOCKER,
                                  f"Unsupported algorithm '{algo}'. Allowed: {sorted(_ALLOWED_ALGOS)}."))
    else:
        result.checks.append(_chk(VerificationCheckType.CHECKSUM_FORMAT, VerificationCheckStatus.PASSED,
                                  VerificationSeverity.INFO, f"Algorithm '{algo}' is supported."))

    # Check 2: Expected checksum format
    expected = (request.expected_checksum or "").strip().lower()
    if not expected:
        result.checks.append(_chk(VerificationCheckType.CHECKSUM_FORMAT, VerificationCheckStatus.WARNING,
                                  VerificationSeverity.WARNING, "No expected checksum declared."))
    elif algo in _HEX_LENGTHS:
        exp_len = _HEX_LENGTHS[algo]
        if len(expected) != exp_len or not all(c in "0123456789abcdef" for c in expected):
            result.checks.append(_chk(VerificationCheckType.CHECKSUM_FORMAT, VerificationCheckStatus.FAILED,
                                      VerificationSeverity.ERROR,
                                      f"Expected checksum not valid hex (len={len(expected)}, expected={exp_len})."))

    # Check 3: Input availability
    has_bytes = request.content_bytes is not None
    has_path = request.local_path is not None and request.local_path.strip() != ""
    if not has_bytes and not has_path:
        result.checks.append(_chk(VerificationCheckType.ARTIFACT_INPUT_AVAILABLE, VerificationCheckStatus.BLOCKED,
                                  VerificationSeverity.BLOCKER,
                                  "No content_bytes or local_path provided. Cannot compute checksum."))
        _finalize(result); return result

    # Check 4: Local path safety
    data: bytes | None = request.content_bytes
    if has_path and not has_bytes:
        path = request.local_path.strip()  # type: ignore[union-attr]
        root = request.allowed_root
        if not root:
            result.checks.append(_chk(VerificationCheckType.LOCAL_PATH_ALLOWED, VerificationCheckStatus.BLOCKED,
                                      VerificationSeverity.BLOCKER,
                                      "local_path provided but allowed_root is not set."))
            _finalize(result); return result
        try:
            resolved = os.path.realpath(path)
            resolved_root = os.path.realpath(root)
            if not _is_subpath(resolved, resolved_root):
                result.checks.append(_chk(VerificationCheckType.LOCAL_PATH_ALLOWED, VerificationCheckStatus.BLOCKED,
                                          VerificationSeverity.BLOCKER,
                                          f"Path '{path}' is outside allowed_root '{root}'."))
                _finalize(result); return result
            st = os.lstat(resolved)
            if stat.S_ISLNK(st.st_mode):
                result.checks.append(_chk(VerificationCheckType.LOCAL_PATH_ALLOWED, VerificationCheckStatus.BLOCKED,
                                          VerificationSeverity.BLOCKER, "Symlinks are not allowed."))
                _finalize(result); return result
            if stat.S_ISDIR(st.st_mode):
                result.checks.append(_chk(VerificationCheckType.LOCAL_PATH_ALLOWED, VerificationCheckStatus.BLOCKED,
                                          VerificationSeverity.BLOCKER, "Directories are not allowed."))
                _finalize(result); return result
            if st.st_size > request.max_file_bytes:
                result.checks.append(_chk(VerificationCheckType.LOCAL_PATH_ALLOWED, VerificationCheckStatus.BLOCKED,
                                          VerificationSeverity.BLOCKER,
                                          f"File too large ({st.st_size} > {request.max_file_bytes})."))
                _finalize(result); return result
            result.checks.append(_chk(VerificationCheckType.LOCAL_PATH_ALLOWED, VerificationCheckStatus.PASSED,
                                      VerificationSeverity.INFO, f"Local path allowed: {path}"))
        except OSError as e:
            result.checks.append(_chk(VerificationCheckType.ARTIFACT_INPUT_AVAILABLE, VerificationCheckStatus.BLOCKED,
                                      VerificationSeverity.BLOCKER, f"Cannot access path: {e}"))
            _finalize(result); return result
        try:
            with open(resolved, "rb") as f:
                data = f.read()
        except OSError as e:
            result.checks.append(_chk(VerificationCheckType.ARTIFACT_INPUT_AVAILABLE, VerificationCheckStatus.BLOCKED,
                                      VerificationSeverity.BLOCKER, f"Cannot read file: {e}"))
            _finalize(result); return result

    if data is None:
        result.checks.append(_chk(VerificationCheckType.ARTIFACT_INPUT_AVAILABLE, VerificationCheckStatus.BLOCKED,
                                  VerificationSeverity.BLOCKER, "No data to hash."))
        _finalize(result); return result

    # Check 5: Compute hash
    try:
        h = hashlib.new(algo, data)
        actual = h.hexdigest()
        result.actual_checksum = actual
        if expected and actual == expected:
            result.matched = True
            result.checks.append(_chk(VerificationCheckType.CHECKSUM_MATCH, VerificationCheckStatus.PASSED,
                                      VerificationSeverity.INFO, f"Checksum match ({algo}).",
                                      expected=expected, actual=actual))
        elif expected:
            result.checks.append(_chk(VerificationCheckType.CHECKSUM_MATCH, VerificationCheckStatus.FAILED,
                                      VerificationSeverity.ERROR,
                                      f"Checksum mismatch: expected={expected[:16]}..., actual={actual[:16]}...",
                                      expected=expected, actual=actual))
        else:
            result.checks.append(_chk(VerificationCheckType.CHECKSUM_MATCH, VerificationCheckStatus.PASSED,
                                      VerificationSeverity.INFO, f"Checksum computed ({algo}): {actual}",
                                      actual=actual))
    except Exception as e:
        result.checks.append(_chk(VerificationCheckType.CHECKSUM_MATCH, VerificationCheckStatus.FAILED,
                                  VerificationSeverity.ERROR, f"Hash computation failed: {e}"))

    _finalize(result)
    return result


def _chk(ct, status, sev, msg, expected=None, actual=None, meta=None) -> VerificationCheck:
    return VerificationCheck(check_type=ct, status=status, severity=sev, message=msg,
                            expected=expected, actual=actual, metadata=meta or {})


def _finalize(result: ChecksumVerificationResult) -> None:
    passed = sum(1 for c in result.checks if c.status == VerificationCheckStatus.PASSED)
    blocked = sum(1 for c in result.checks if c.status == VerificationCheckStatus.BLOCKED)
    failed = sum(1 for c in result.checks if c.status == VerificationCheckStatus.FAILED)
    if blocked > 0: result.status = VerificationRunStatus.BLOCKED
    elif failed > 0: result.status = VerificationRunStatus.FAILED
    elif passed == len(result.checks): result.status = VerificationRunStatus.PASSED
    else: result.status = VerificationRunStatus.PASSED_WITH_WARNINGS


def _is_subpath(child: str, parent: str) -> bool:
    parent = parent.rstrip(os.sep) + os.sep
    child_check = child.rstrip(os.sep) + os.sep
    return child_check.startswith(parent)
