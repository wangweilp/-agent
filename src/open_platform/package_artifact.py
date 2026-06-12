"""Package Artifact Domain Model — Developer Agent 包制品生命周期管理。

Step 24-B MVP:
- PackageArtifact — 包制品元数据 + 状态机
- PackageQuarantineRecord — 隔离记录
- PackageArtifactAuditEvent — 审计事件
- PackageArtifactStore Protocol — 存储层抽象

安全边界：
- 不下载 package
- 不解压 package
- 不执行 package_url / entrypoint
- 不联网
- 不计算真实 checksum（checksum_value 只存声明值）
- 不验证真实 signature（signature_value 只存声明值）
- VERIFIED 只表示 metadata state machine 状态
- is_verified_for_execution() 在 Step 24-B 始终返回 False
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


class ArtifactSourceType(StrEnum):
    PACKAGE_URL = "package_url"
    REPOSITORY = "repository"
    INLINE_METADATA = "inline_metadata"
    UNKNOWN = "unknown"


class ArtifactStatus(StrEnum):
    DECLARED = "declared"
    QUARANTINED = "quarantined"
    METADATA_VALIDATED = "metadata_validated"
    VERIFICATION_PENDING = "verification_pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    DISABLED = "disabled"


class QuarantineStatus(StrEnum):
    NOT_QUARANTINED = "not_quarantined"
    QUARANTINED = "quarantined"
    REVIEW_REQUIRED = "review_required"
    RELEASED = "released"
    REJECTED = "rejected"
    EXPIRED = "expired"


class VerificationStatus(StrEnum):
    NOT_VERIFIED = "not_verified"
    METADATA_ONLY = "metadata_only"
    CHECKSUM_PENDING = "checksum_pending"
    CHECKSUM_VERIFIED = "checksum_verified"
    SIGNATURE_PENDING = "signature_pending"
    SIGNATURE_VERIFIED = "signature_verified"
    FAILED = "failed"


class ArtifactRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class ArtifactAuditEventType(StrEnum):
    CREATED = "created"
    METADATA_UPDATED = "metadata_updated"
    QUARANTINED = "quarantined"
    RELEASED = "released"
    REJECTED = "rejected"
    DISABLED = "disabled"
    VERIFICATION_STATUS_CHANGED = "verification_status_changed"
    RISK_LEVEL_CHANGED = "risk_level_changed"


# ═══════════════════════════════════════════
# PackageArtifact
# ═══════════════════════════════════════════


@dataclass
class PackageArtifact:
    """包制品 — 从 submission manifest metadata 声明的包元数据。

    安全约束：
    - 不包含下载方法
    - 不包含执行方法
    - 不包含 file path 读取方法
    - 不包含 network 访问方法
    - checksum_value 只存声明值，不计算
    - signature_value 只存声明值，不验证
    - is_verified_for_execution() 在 Step 24-B 始终返回 False
    """

    artifact_id: str = field(default_factory=lambda: f"art_{uuid4().hex[:16]}")
    submission_id: str = ""
    developer_id: str = ""
    tenant_id: str = ""
    marketplace_agent_id: str | None = None
    source_type: str = ArtifactSourceType.UNKNOWN
    package_url: str | None = None
    repository_url: str | None = None
    package_name: str | None = None
    package_version: str | None = None
    checksum_algorithm: str | None = None
    checksum_value: str | None = None
    signature_algorithm: str | None = None
    signature_value: str | None = None
    signing_key_id: str | None = None
    declared_size_bytes: int | None = None
    content_type: str | None = None
    artifact_status: str = ArtifactStatus.DECLARED
    verification_status: str = VerificationStatus.METADATA_ONLY
    risk_level: str = ArtifactRiskLevel.UNKNOWN
    quarantine_status: str = QuarantineStatus.NOT_QUARANTINED
    package_metadata: dict[str, Any] = field(default_factory=dict)
    validation_id: str | None = None
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.package_metadata, dict):
            raise ValueError("package_metadata must be dict")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be dict")
        if self.declared_size_bytes is not None and self.declared_size_bytes < 0:
            raise ValueError("declared_size_bytes must be None or >= 0")

    def is_quarantined(self) -> bool:
        return self.quarantine_status == QuarantineStatus.QUARANTINED

    def is_verified_for_execution(self) -> bool:
        """Step 24-B: 始终返回 False。

        真实 execution 需要:
        - checksum verified (Step 24-C)
        - signature verified (Step 24-C)
        - dependency scanned (Step 24-C+)
        - policy enforced (Step 24-F)
        - worker available (Step 24-E)
        这些条件在 Step 24-B 都未满足。
        """
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "submission_id": self.submission_id,
            "developer_id": self.developer_id,
            "tenant_id": self.tenant_id,
            "marketplace_agent_id": self.marketplace_agent_id,
            "source_type": self.source_type,
            "package_url": self.package_url,
            "repository_url": self.repository_url,
            "package_name": self.package_name,
            "package_version": self.package_version,
            "checksum_algorithm": self.checksum_algorithm,
            "checksum_value": self.checksum_value,
            "signature_algorithm": self.signature_algorithm,
            "signature_value": self.signature_value,
            "signing_key_id": self.signing_key_id,
            "declared_size_bytes": self.declared_size_bytes,
            "content_type": self.content_type,
            "artifact_status": self.artifact_status,
            "verification_status": self.verification_status,
            "risk_level": self.risk_level,
            "quarantine_status": self.quarantine_status,
            "package_metadata": dict(self.package_metadata),
            "validation_id": self.validation_id,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PackageArtifact":
        ca = _safe_dt(d.get("created_at"))
        ua = _safe_dt(d.get("updated_at"))
        return cls(
            artifact_id=str(d.get("artifact_id", "")),
            submission_id=str(d.get("submission_id", "")),
            developer_id=str(d.get("developer_id", "")),
            tenant_id=str(d.get("tenant_id", "")),
            marketplace_agent_id=d.get("marketplace_agent_id"),
            source_type=str(d.get("source_type", ArtifactSourceType.UNKNOWN)),
            package_url=d.get("package_url"),
            repository_url=d.get("repository_url"),
            package_name=d.get("package_name"),
            package_version=d.get("package_version"),
            checksum_algorithm=d.get("checksum_algorithm"),
            checksum_value=d.get("checksum_value"),
            signature_algorithm=d.get("signature_algorithm"),
            signature_value=d.get("signature_value"),
            signing_key_id=d.get("signing_key_id"),
            declared_size_bytes=d.get("declared_size_bytes"),
            content_type=d.get("content_type"),
            artifact_status=str(d.get("artifact_status", ArtifactStatus.DECLARED)),
            verification_status=str(d.get("verification_status", VerificationStatus.METADATA_ONLY)),
            risk_level=str(d.get("risk_level", ArtifactRiskLevel.UNKNOWN)),
            quarantine_status=str(d.get("quarantine_status", QuarantineStatus.NOT_QUARANTINED)),
            package_metadata=dict(d.get("package_metadata", {})),
            validation_id=d.get("validation_id"),
            created_by=d.get("created_by"),
            updated_by=d.get("updated_by"),
            created_at=ca,
            updated_at=ua,
            metadata=dict(d.get("metadata", {})),
        )


# ═══════════════════════════════════════════
# PackageQuarantineRecord
# ═══════════════════════════════════════════


@dataclass
class PackageQuarantineRecord:
    """隔离记录 — artifact 的隔离状态追踪。

    安全约束：
    - 不包含 package content
    - 不包含 file path
    - 不访问网络
    - release / reject 只改变状态，不表示可执行
    """

    quarantine_id: str = field(default_factory=lambda: f"quar_{uuid4().hex[:16]}")
    artifact_id: str = ""
    tenant_id: str = ""
    submission_id: str = ""
    status: str = QuarantineStatus.QUARANTINED
    reason: str = ""
    risk_level: str = ArtifactRiskLevel.UNKNOWN
    policy_snapshot: dict[str, Any] = field(default_factory=dict)
    validation_summary: dict[str, Any] = field(default_factory=dict)
    created_by: str | None = None
    released_by: str | None = None
    rejected_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    released_at: datetime | None = None
    rejected_at: datetime | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.policy_snapshot, dict):
            raise ValueError("policy_snapshot must be dict")
        if not isinstance(self.validation_summary, dict):
            raise ValueError("validation_summary must be dict")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "quarantine_id": self.quarantine_id,
            "artifact_id": self.artifact_id,
            "tenant_id": self.tenant_id,
            "submission_id": self.submission_id,
            "status": self.status,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "policy_snapshot": dict(self.policy_snapshot),
            "validation_summary": dict(self.validation_summary),
            "created_by": self.created_by,
            "released_by": self.released_by,
            "rejected_by": self.rejected_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "released_at": self.released_at.isoformat() if self.released_at else None,
            "rejected_at": self.rejected_at.isoformat() if self.rejected_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PackageQuarantineRecord":
        return cls(
            quarantine_id=str(d.get("quarantine_id", "")),
            artifact_id=str(d.get("artifact_id", "")),
            tenant_id=str(d.get("tenant_id", "")),
            submission_id=str(d.get("submission_id", "")),
            status=str(d.get("status", QuarantineStatus.QUARANTINED)),
            reason=str(d.get("reason", "")),
            risk_level=str(d.get("risk_level", ArtifactRiskLevel.UNKNOWN)),
            policy_snapshot=dict(d.get("policy_snapshot", {})),
            validation_summary=dict(d.get("validation_summary", {})),
            created_by=d.get("created_by"),
            released_by=d.get("released_by"),
            rejected_by=d.get("rejected_by"),
            created_at=_safe_dt(d.get("created_at")),
            updated_at=_safe_dt(d.get("updated_at")),
            released_at=_safe_dt(d.get("released_at"), none_ok=True),
            rejected_at=_safe_dt(d.get("rejected_at"), none_ok=True),
            expires_at=_safe_dt(d.get("expires_at"), none_ok=True),
            metadata=dict(d.get("metadata", {})),
        )


# ═══════════════════════════════════════════
# PackageArtifactAuditEvent
# ═══════════════════════════════════════════


@dataclass
class PackageArtifactAuditEvent:
    """审计事件 — artifact 生命周期变更记录。

    安全约束：
    - metadata 不包含 package contents
    - metadata 不包含 secrets
    - metadata 不包含 raw_key / key_hash
    """

    event_id: str = field(default_factory=lambda: f"artevt_{uuid4().hex[:16]}")
    artifact_id: str = ""
    tenant_id: str = ""
    event_type: str = ""
    actor_id: str | None = None
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "artifact_id": self.artifact_id,
            "tenant_id": self.tenant_id,
            "event_type": self.event_type,
            "actor_id": self.actor_id,
            "message": self.message,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PackageArtifactAuditEvent":
        return cls(
            event_id=str(d.get("event_id", "")),
            artifact_id=str(d.get("artifact_id", "")),
            tenant_id=str(d.get("tenant_id", "")),
            event_type=str(d.get("event_type", "")),
            actor_id=d.get("actor_id"),
            message=str(d.get("message", "")),
            metadata=dict(d.get("metadata", {})),
            created_at=_safe_dt(d.get("created_at")),
        )


# ═══════════════════════════════════════════
# Error Classes
# ═══════════════════════════════════════════


class PackageArtifactError(Exception):
    def __init__(self, message: str = "Package artifact error"):
        super().__init__(message)


class PackageArtifactNotFoundError(PackageArtifactError):
    def __init__(self, message: str = "Package artifact not found"):
        super().__init__(message)


class PackageArtifactAlreadyExistsError(PackageArtifactError):
    def __init__(self, message: str = "Package artifact already exists"):
        super().__init__(message)


class PackageArtifactStateError(PackageArtifactError):
    def __init__(self, message: str = "Invalid state transition"):
        super().__init__(message)


class PackageQuarantineNotFoundError(PackageArtifactError):
    def __init__(self, message: str = "Quarantine record not found"):
        super().__init__(message)


# ═══════════════════════════════════════════
# Store Protocol
# ═══════════════════════════════════════════


@runtime_checkable
class PackageArtifactStore(Protocol):
    """Package Artifact 存储协议。

    禁止：
    - 下载 package
    - 执行 package
    - 联网
    - 状态变更必须产生 audit event
    """

    # ── Artifact ──

    def create_artifact(self, artifact: PackageArtifact) -> PackageArtifact: ...
    def get_artifact(self, artifact_id: str) -> PackageArtifact | None: ...
    def get_artifact_by_submission(self, submission_id: str) -> PackageArtifact | None: ...
    def list_artifacts(
        self, *,
        tenant_id: str = "", developer_id: str = "",
        submission_id: str = "", status: str = "",
        verification_status: str = "", quarantine_status: str = "",
    ) -> list[PackageArtifact]: ...
    def update_artifact(self, artifact: PackageArtifact) -> PackageArtifact: ...
    def set_artifact_status(
        self, artifact_id: str, status: str,
        actor_id: str | None = None, reason: str | None = None,
    ) -> PackageArtifact: ...
    def set_verification_status(
        self, artifact_id: str, verification_status: str,
        actor_id: str | None = None, reason: str | None = None,
    ) -> PackageArtifact: ...
    def set_risk_level(
        self, artifact_id: str, risk_level: str,
        actor_id: str | None = None, reason: str | None = None,
    ) -> PackageArtifact: ...

    # ── Quarantine ──

    def create_quarantine_record(self, record: PackageQuarantineRecord) -> PackageQuarantineRecord: ...
    def get_quarantine_record(self, quarantine_id: str) -> PackageQuarantineRecord | None: ...
    def get_latest_quarantine_for_artifact(self, artifact_id: str) -> PackageQuarantineRecord | None: ...
    def list_quarantine_records(
        self, *, tenant_id: str = "", artifact_id: str = "",
        status: str = "",
    ) -> list[PackageQuarantineRecord]: ...
    def set_quarantine_status(
        self, quarantine_id: str, status: str,
        actor_id: str | None = None, reason: str | None = None,
    ) -> PackageQuarantineRecord: ...

    # ── Audit ──

    def add_audit_event(self, event: PackageArtifactAuditEvent) -> PackageArtifactAuditEvent: ...
    def list_audit_events(self, artifact_id: str) -> list[PackageArtifactAuditEvent]: ...

    # ── Counts ──

    def count_artifacts(
        self, *, tenant_id: str = "", status: str = "",
        quarantine_status: str = "",
    ) -> int: ...


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════


def _safe_dt(raw: str | None, none_ok: bool = False) -> datetime | None:
    if not raw:
        return None if none_ok else datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None if none_ok else datetime.now(timezone.utc)
