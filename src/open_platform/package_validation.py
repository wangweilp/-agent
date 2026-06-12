"""Package Validation Domain Model — 静态 package metadata 验证。

Step 23-F MVP:
- 不下载 package
- 不解压 package
- 不执行 package_url
- 不执行 entrypoint
- 不联网
- 只是静态 metadata validation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


class PackageSourceType(StrEnum):
    NONE = "none"
    PACKAGE_URL = "package_url"
    REPOSITORY = "repository"
    INLINE_METADATA = "inline_metadata"


class PackageValidationStatus(StrEnum):
    NOT_VALIDATED = "not_validated"
    PASSED = "passed"
    PASSED_WITH_WARNINGS = "passed_with_warnings"
    FAILED = "failed"
    BLOCKED = "blocked"


class PackageValidationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


class PackageValidationCheckCode(StrEnum):
    URL_PRESENT = "url_present"
    URL_FORMAT_VALID = "url_format_valid"
    HTTPS_REQUIRED = "https_required"
    DOMAIN_ALLOWED = "domain_allowed"
    DOMAIN_BLOCKED = "domain_blocked"
    CHECKSUM_DECLARED = "checksum_declared"
    SIGNATURE_DECLARED = "signature_declared"
    PACKAGE_NAME_MATCH = "package_name_match"
    PACKAGE_VERSION_MATCH = "package_version_match"
    RUNTIME_TYPE_SUPPORTED = "runtime_type_supported"
    SOURCE_TYPE_SUPPORTED = "source_type_supported"
    DEPENDENCIES_DECLARED = "dependencies_declared"
    LICENSE_DECLARED = "license_declared"
    SECURITY_CONTACT_DECLARED = "security_contact_declared"
    SANDBOX_REQUIREMENTS_DECLARED = "sandbox_requirements_declared"
    NETWORK_REQUIREMENTS_DECLARED = "network_requirements_declared"
    USER_DATA_ACCESS_DECLARED = "user_data_access_declared"
    PACKAGE_NOT_DOWNLOADED = "package_not_downloaded"
    PACKAGE_NOT_EXECUTED = "package_not_executed"


@dataclass
class PackageValidationCheck:
    check_id: str = field(default_factory=lambda: f"pvchk_{uuid4().hex[:8]}")
    code: str = ""
    severity: str = PackageValidationSeverity.INFO
    passed: bool = True
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id, "code": self.code,
            "severity": self.severity, "passed": self.passed,
            "message": self.message, "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PackageValidationCheck":
        return cls(
            check_id=d.get("check_id", ""), code=d.get("code", ""),
            severity=d.get("severity", "info"), passed=d.get("passed", True),
            message=d.get("message", ""), metadata=d.get("metadata", {}),
        )


@dataclass
class PackageValidationRequest:
    submission_id: str = ""
    requested_by: str = ""
    tenant_id: str = ""
    package_url: str | None = None
    repository_url: str | None = None
    source_type: str = "manifest"
    manifest_name: str = ""
    manifest_version: str = ""
    manifest_runtime_type: str = "manifest_only"
    manifest_metadata: dict[str, Any] = field(default_factory=dict)
    validation_options: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PackageValidationResult:
    validation_id: str = field(default_factory=lambda: f"pval_{uuid4().hex[:12]}")
    submission_id: str = ""
    tenant_id: str = ""
    requested_by: str = ""
    status: str = PackageValidationStatus.NOT_VALIDATED
    source_type: str = PackageSourceType.NONE
    package_url: str | None = None
    repository_url: str | None = None
    manifest_name: str = ""
    manifest_version: str = ""
    checks: list[PackageValidationCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    package_metadata: dict[str, Any] = field(default_factory=dict)
    review_recommendation: str = ""
    no_download_performed: bool = True
    no_execution_performed: bool = True
    no_network_performed: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_blockers(self) -> bool: return len(self.blockers) > 0
    def is_passed(self) -> bool: return self.status in (PackageValidationStatus.PASSED, PackageValidationStatus.PASSED_WITH_WARNINGS)

    def summary_counts(self) -> dict[str, int]:
        p = sum(1 for c in self.checks if c.passed)
        return {"total": len(self.checks), "passed": p, "failed": len(self.checks) - p,
                "warnings": len(self.warnings), "errors": len(self.errors), "blockers": len(self.blockers)}

    def to_dict(self) -> dict[str, Any]:
        return {
            "validation_id": self.validation_id, "submission_id": self.submission_id,
            "tenant_id": self.tenant_id, "requested_by": self.requested_by,
            "status": self.status, "source_type": self.source_type,
            "package_url": self.package_url, "repository_url": self.repository_url,
            "manifest_name": self.manifest_name, "manifest_version": self.manifest_version,
            "checks": [c.to_dict() for c in self.checks],
            "warnings": self.warnings, "errors": self.errors, "blockers": self.blockers,
            "package_metadata": self.package_metadata,
            "review_recommendation": self.review_recommendation,
            "no_download_performed": self.no_download_performed,
            "no_execution_performed": self.no_execution_performed,
            "no_network_performed": self.no_network_performed,
            "summary": self.summary_counts(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PackageValidationResult":
        checks = [PackageValidationCheck.from_dict(c) for c in d.get("checks", [])]
        return cls(
            validation_id=d.get("validation_id", ""), submission_id=d.get("submission_id", ""),
            tenant_id=d.get("tenant_id", ""), requested_by=d.get("requested_by", ""),
            status=d.get("status", ""), source_type=d.get("source_type", ""),
            package_url=d.get("package_url"), repository_url=d.get("repository_url"),
            manifest_name=d.get("manifest_name", ""), manifest_version=d.get("manifest_version", ""),
            checks=checks,
            warnings=list(d.get("warnings", [])), errors=list(d.get("errors", [])),
            blockers=list(d.get("blockers", [])),
            package_metadata=dict(d.get("package_metadata", {})),
            review_recommendation=d.get("review_recommendation", ""),
            no_download_performed=bool(d.get("no_download_performed", True)),
            no_execution_performed=bool(d.get("no_execution_performed", True)),
            no_network_performed=bool(d.get("no_network_performed", True)),
            created_at=_safe_dt(d.get("created_at")), completed_at=_safe_dt(d.get("completed_at"), none_ok=True),
            metadata=dict(d.get("metadata", {})),
        )


# ═══════════════════════════════════════════
# Store Protocol
# ═══════════════════════════════════════════

@runtime_checkable
class PackageValidationStore(Protocol):
    def create_result(self, result: PackageValidationResult) -> PackageValidationResult: ...
    def get_result(self, validation_id: str) -> PackageValidationResult | None: ...
    def get_latest_by_submission(self, submission_id: str) -> PackageValidationResult | None: ...
    def list_results(self, *, submission_id: str = "", tenant_id: str = "", status: str = "") -> list[PackageValidationResult]: ...
    def count_results(self, *, submission_id: str = "", tenant_id: str = "", status: str = "") -> int: ...


class PackageValidationError(Exception):
    def __init__(self, message: str = "Package validation error"): super().__init__(message)

class PackageValidationNotFoundError(Exception):
    def __init__(self, message: str = "Validation result not found"): super().__init__(message)

class PackageValidationStateError(Exception):
    def __init__(self, message: str = "Invalid state for package validation"): super().__init__(message)


def _safe_dt(raw: str | None, none_ok: bool = False) -> datetime | None:
    if not raw:
        return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError): return None if none_ok else datetime.now(timezone.utc)
