"""Package Verification Domain Model — checksum/signature verification pipeline.

Step 24-C:
- VerificationCheck — 单个验证检查
- PackageVerificationRun — 验证运行记录
- SignatureVerificationMode — 签名验证模式
- PackageVerificationStore Protocol — 存储层抽象

安全边界：
- 不下载 package / 不执行 package / 不联网
- checksum verification: 只对受控 bytes/local fixture
- signature verification: metadata/trust-policy 层，非真实 cryptographic verification
- 不调用 cosign/gpg/minisign 外部命令
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


# ═══════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════


class VerificationRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    PASSED_WITH_WARNINGS = "passed_with_warnings"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class VerificationCheckType(StrEnum):
    CHECKSUM_FORMAT = "checksum_format"
    CHECKSUM_MATCH = "checksum_match"
    SIGNATURE_FORMAT = "signature_format"
    SIGNATURE_METADATA = "signature_metadata"
    SIGNATURE_TRUST_POLICY = "signature_trust_policy"
    ARTIFACT_INPUT_AVAILABLE = "artifact_input_available"
    LOCAL_PATH_ALLOWED = "local_path_allowed"
    NO_NETWORK_USED = "no_network_used"
    NO_EXECUTION_USED = "no_execution_used"


class VerificationCheckStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class VerificationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


class SignatureVerificationMode(StrEnum):
    METADATA_ONLY = "metadata_only"
    LOCAL_DETACHED_SIGNATURE = "local_detached_signature"
    EXTERNAL_TOOL_RESERVED = "external_tool_reserved"


# ═══════════════════════════════════════════
# VerificationCheck
# ═══════════════════════════════════════════


@dataclass
class VerificationCheck:
    """单次验证检查。expected/actual 不存 package contents。metadata 不含 secrets。"""

    check_id: str = field(default_factory=lambda: f"verchk_{uuid4().hex[:16]}")
    check_type: str = ""
    status: str = VerificationCheckStatus.PASSED
    severity: str = VerificationSeverity.INFO
    message: str = ""
    expected: str | None = None
    actual: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id, "check_type": self.check_type,
            "status": self.status, "severity": self.severity,
            "message": self.message, "expected": self.expected,
            "actual": self.actual, "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "VerificationCheck":
        return cls(
            check_id=str(d.get("check_id", "")), check_type=str(d.get("check_type", "")),
            status=str(d.get("status", VerificationCheckStatus.PASSED)),
            severity=str(d.get("severity", VerificationSeverity.INFO)),
            message=str(d.get("message", "")), expected=d.get("expected"),
            actual=d.get("actual"), metadata=dict(d.get("metadata", {})),
        )


# ═══════════════════════════════════════════
# PackageVerificationRun
# ═══════════════════════════════════════════


@dataclass
class PackageVerificationRun:
    """Package 验证运行记录。包含 checksum + signature 的所有检查结果。"""

    verification_id: str = field(default_factory=lambda: f"pkgver_{uuid4().hex[:16]}")
    artifact_id: str = ""
    submission_id: str = ""
    tenant_id: str = ""
    developer_id: str = ""
    requested_by: str | None = None
    run_status: str = VerificationRunStatus.PENDING
    checksum_algorithm: str | None = None
    expected_checksum: str | None = None
    actual_checksum: str | None = None
    signature_algorithm: str | None = None
    signature_value_present: bool = False
    signature_verified: bool = False
    signature_mode: str = SignatureVerificationMode.METADATA_ONLY
    checks: list[VerificationCheck] = field(default_factory=list)
    warnings_count: int = 0
    errors_count: int = 0
    blockers_count: int = 0
    no_network_used: bool = True
    no_execution_used: bool = True
    no_download_used: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be dict")

    def add_check(self, check: VerificationCheck) -> None:
        self.checks.append(check)
        if check.status == VerificationCheckStatus.WARNING:
            self.warnings_count += 1
        elif check.status == VerificationCheckStatus.FAILED:
            if check.severity == VerificationSeverity.BLOCKER:
                self.blockers_count += 1
            else:
                self.errors_count += 1
        elif check.status == VerificationCheckStatus.BLOCKED:
            self.blockers_count += 1

    def calculate_status(self) -> None:
        self._recount()
        if not self.checks:
            self.run_status = VerificationRunStatus.PENDING; return
        if self.blockers_count > 0:
            self.run_status = VerificationRunStatus.BLOCKED
        elif self.errors_count > 0:
            self.run_status = VerificationRunStatus.FAILED
        elif self.warnings_count > 0:
            self.run_status = VerificationRunStatus.PASSED_WITH_WARNINGS
        else:
            all_ok = all(c.status in (VerificationCheckStatus.PASSED, VerificationCheckStatus.SKIPPED) for c in self.checks)
            self.run_status = VerificationRunStatus.PASSED if all_ok else VerificationRunStatus.PASSED_WITH_WARNINGS

    def _recount(self) -> None:
        """从 checks 重新计算计数（兼容 extend 直接添加的检查）。"""
        self.warnings_count = 0
        self.errors_count = 0
        self.blockers_count = 0
        for c in self.checks:
            if c.status == VerificationCheckStatus.WARNING:
                self.warnings_count += 1
            elif c.status == VerificationCheckStatus.FAILED:
                if c.severity == VerificationSeverity.BLOCKER:
                    self.blockers_count += 1
                else:
                    self.errors_count += 1
            elif c.status == VerificationCheckStatus.BLOCKED:
                self.blockers_count += 1

    def is_passed(self) -> bool:
        return self.run_status in (VerificationRunStatus.PASSED, VerificationRunStatus.PASSED_WITH_WARNINGS)

    def is_blocked(self) -> bool:
        return self.run_status == VerificationRunStatus.BLOCKED

    def to_dict(self) -> dict[str, Any]:
        return {
            "verification_id": self.verification_id, "artifact_id": self.artifact_id,
            "submission_id": self.submission_id, "tenant_id": self.tenant_id,
            "developer_id": self.developer_id, "requested_by": self.requested_by,
            "run_status": self.run_status, "checksum_algorithm": self.checksum_algorithm,
            "expected_checksum": self.expected_checksum, "actual_checksum": self.actual_checksum,
            "signature_algorithm": self.signature_algorithm,
            "signature_value_present": self.signature_value_present,
            "signature_verified": self.signature_verified, "signature_mode": self.signature_mode,
            "checks": [c.to_dict() for c in self.checks],
            "warnings_count": self.warnings_count, "errors_count": self.errors_count,
            "blockers_count": self.blockers_count,
            "no_network_used": self.no_network_used, "no_execution_used": self.no_execution_used,
            "no_download_used": self.no_download_used,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PackageVerificationRun":
        checks = [VerificationCheck.from_dict(c) for c in d.get("checks", [])]
        return cls(
            verification_id=str(d.get("verification_id", "")),
            artifact_id=str(d.get("artifact_id", "")), submission_id=str(d.get("submission_id", "")),
            tenant_id=str(d.get("tenant_id", "")), developer_id=str(d.get("developer_id", "")),
            requested_by=d.get("requested_by"),
            run_status=str(d.get("run_status", VerificationRunStatus.PENDING)),
            checksum_algorithm=d.get("checksum_algorithm"), expected_checksum=d.get("expected_checksum"),
            actual_checksum=d.get("actual_checksum"), signature_algorithm=d.get("signature_algorithm"),
            signature_value_present=bool(d.get("signature_value_present", False)),
            signature_verified=bool(d.get("signature_verified", False)),
            signature_mode=str(d.get("signature_mode", SignatureVerificationMode.METADATA_ONLY)),
            checks=checks, warnings_count=int(d.get("warnings_count", 0)),
            errors_count=int(d.get("errors_count", 0)), blockers_count=int(d.get("blockers_count", 0)),
            no_network_used=bool(d.get("no_network_used", True)),
            no_execution_used=bool(d.get("no_execution_used", True)),
            no_download_used=bool(d.get("no_download_used", True)),
            created_at=_safe_dt(d.get("created_at")), completed_at=_safe_dt(d.get("completed_at"), none_ok=True),
            metadata=dict(d.get("metadata", {})),
        )


# ═══════════════════════════════════════════
# Error Classes
# ═══════════════════════════════════════════


class PackageVerificationError(Exception):
    pass


class PackageVerificationNotFoundError(PackageVerificationError):
    pass


class PackageVerificationStateError(PackageVerificationError):
    pass


class ArtifactInputNotAvailableError(PackageVerificationError):
    pass


class ArtifactPathNotAllowedError(PackageVerificationError):
    pass


# ═══════════════════════════════════════════
# Store Protocol
# ═══════════════════════════════════════════


@runtime_checkable
class PackageVerificationStore(Protocol):
    """Package Verification 存储协议。禁止：下载/执行/联网。"""

    def create_run(self, run: PackageVerificationRun) -> PackageVerificationRun: ...
    def get_run(self, verification_id: str) -> PackageVerificationRun | None: ...
    def get_latest_run_for_artifact(self, artifact_id: str) -> PackageVerificationRun | None: ...
    def list_runs(self, *, tenant_id: str = "", artifact_id: str = "", status: str = "") -> list[PackageVerificationRun]: ...
    def update_run(self, run: PackageVerificationRun) -> PackageVerificationRun: ...
    def count_runs(self, *, tenant_id: str = "", status: str = "") -> int: ...


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════


def _safe_dt(raw: str | None, none_ok: bool = False) -> datetime | None:
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError): return None if none_ok else datetime.now(timezone.utc)
