"""Sandbox v2 Core Data Models — Step 1–6B 核心数据模型。

定义 SandboxJob, SandboxExecutionRecord, SandboxPolicy, SandboxPolicyDecision,
SandboxResourceLimits, SandboxNetworkPolicy, SandboxFilesystemPolicy,
SandboxArtifactPolicy, SandboxPackagePolicy 及状态/mode 枚举。

安全约束：
- 不执行代码
- 不连接 Docker/MicroVM
- 不发起网络请求
- 不写真实文件系统 artifact
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


# ═══════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════


class SandboxV2JobStatus(StrEnum):
    """Sandbox v2 Job 状态机。"""
    CREATED = "created"
    POLICY_CHECKED = "policy_checked"
    REJECTED = "rejected"
    QUEUED = "queued"
    RUNNING_SIMULATION = "running_simulation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    TIMEOUT = "timeout"


class SandboxV2Mode(StrEnum):
    """Sandbox v2 执行模式。

    future_container 和 future_microvm 只是预留枚举，不实现真实执行。
    """
    METADATA_ONLY = "metadata_only"
    SIMULATION = "simulation"
    DISABLED = "disabled"
    FUTURE_CONTAINER = "future_container"
    FUTURE_MICROVM = "future_microvm"


class SandboxV2RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class SandboxV2Decision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    FAIL_CLOSED = "fail_closed"


# MVP 允许的 mode（只允许 metadata_only 和 simulation）
MVP_ALLOWED_MODES: frozenset[str] = frozenset({
    SandboxV2Mode.METADATA_ONLY,
    SandboxV2Mode.SIMULATION,
    SandboxV2Mode.DISABLED,
})


# ═══════════════════════════════════════════
# Core Data Models
# ═══════════════════════════════════════════


@dataclass
class SandboxResourceLimits:
    """Sandbox v2 资源限制。"""
    max_runtime_seconds: int = 30
    max_memory_mb: int = 256
    max_cpu_percent: int = 50
    max_output_bytes: int = 1_048_576  # 1 MiB
    max_concurrent_jobs: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_memory_mb": self.max_memory_mb,
            "max_cpu_percent": self.max_cpu_percent,
            "max_output_bytes": self.max_output_bytes,
            "max_concurrent_jobs": self.max_concurrent_jobs,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxResourceLimits":
        return cls(
            max_runtime_seconds=d.get("max_runtime_seconds", 30),
            max_memory_mb=d.get("max_memory_mb", 256),
            max_cpu_percent=d.get("max_cpu_percent", 50),
            max_output_bytes=d.get("max_output_bytes", 1_048_576),
            max_concurrent_jobs=d.get("max_concurrent_jobs", 1),
        )


@dataclass
class SandboxNetworkPolicy:
    """Sandbox v2 网络策略。"""
    allow_network: bool = False
    allowed_domains: list[str] = field(default_factory=list)
    allowed_ips: list[str] = field(default_factory=list)
    blocked_ips: list[str] = field(default_factory=list)
    allow_dns: bool = False
    allow_egress_proxy: bool = False
    block_metadata_service: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_network": self.allow_network,
            "allowed_domains": self.allowed_domains,
            "allowed_ips": self.allowed_ips,
            "blocked_ips": self.blocked_ips,
            "allow_dns": self.allow_dns,
            "allow_egress_proxy": self.allow_egress_proxy,
            "block_metadata_service": self.block_metadata_service,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxNetworkPolicy":
        return cls(
            allow_network=d.get("allow_network", False),
            allowed_domains=d.get("allowed_domains", []),
            allowed_ips=d.get("allowed_ips", []),
            blocked_ips=d.get("blocked_ips", []),
            allow_dns=d.get("allow_dns", False),
            allow_egress_proxy=d.get("allow_egress_proxy", False),
            block_metadata_service=d.get("block_metadata_service", True),
        )


@dataclass
class SandboxFilesystemPolicy:
    """Sandbox v2 文件系统策略。"""
    allow_write_filesystem: bool = False
    allow_read_filesystem: bool = False
    allowed_paths: list[str] = field(default_factory=list)
    blocked_paths: list[str] = field(default_factory=list)
    read_only_rootfs: bool = True
    no_host_mount: bool = True
    temp_dir_isolated: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_write_filesystem": self.allow_write_filesystem,
            "allow_read_filesystem": self.allow_read_filesystem,
            "allowed_paths": self.allowed_paths,
            "blocked_paths": self.blocked_paths,
            "read_only_rootfs": self.read_only_rootfs,
            "no_host_mount": self.no_host_mount,
            "temp_dir_isolated": self.temp_dir_isolated,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxFilesystemPolicy":
        return cls(
            allow_write_filesystem=d.get("allow_write_filesystem", False),
            allow_read_filesystem=d.get("allow_read_filesystem", False),
            allowed_paths=d.get("allowed_paths", []),
            blocked_paths=d.get("blocked_paths", []),
            read_only_rootfs=d.get("read_only_rootfs", True),
            no_host_mount=d.get("no_host_mount", True),
            temp_dir_isolated=d.get("temp_dir_isolated", True),
        )


@dataclass
class SandboxArtifactPolicy:
    """Sandbox v2 Artifact 策略。"""
    allow_artifact_materialization: bool = False
    max_artifact_size_bytes: int = 1_048_576  # 1 MiB
    allowed_mime_types: list[str] = field(default_factory=list)
    blocked_mime_types: list[str] = field(default_factory=list)
    max_file_count: int = 10
    allow_extraction: bool = False
    artifact_retention_hours: int = 24

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_artifact_materialization": self.allow_artifact_materialization,
            "max_artifact_size_bytes": self.max_artifact_size_bytes,
            "allowed_mime_types": self.allowed_mime_types,
            "blocked_mime_types": self.blocked_mime_types,
            "max_file_count": self.max_file_count,
            "allow_extraction": self.allow_extraction,
            "artifact_retention_hours": self.artifact_retention_hours,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxArtifactPolicy":
        return cls(
            allow_artifact_materialization=d.get("allow_artifact_materialization", False),
            max_artifact_size_bytes=d.get("max_artifact_size_bytes", 1_048_576),
            allowed_mime_types=d.get("allowed_mime_types", []),
            blocked_mime_types=d.get("blocked_mime_types", []),
            max_file_count=d.get("max_file_count", 10),
            allow_extraction=d.get("allow_extraction", False),
            artifact_retention_hours=d.get("artifact_retention_hours", 24),
        )


@dataclass
class SandboxPackagePolicy:
    """Sandbox v2 包管理策略。"""
    allow_package_download: bool = False
    allowed_registries: list[str] = field(default_factory=list)
    allowed_packages: list[str] = field(default_factory=list)
    blocked_packages: list[str] = field(default_factory=list)
    require_hash_verification: bool = True
    require_signature_verification: bool = True
    require_sbom: bool = True
    quarantine_downloads: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_package_download": self.allow_package_download,
            "allowed_registries": self.allowed_registries,
            "allowed_packages": self.allowed_packages,
            "blocked_packages": self.blocked_packages,
            "require_hash_verification": self.require_hash_verification,
            "require_signature_verification": self.require_signature_verification,
            "require_sbom": self.require_sbom,
            "quarantine_downloads": self.quarantine_downloads,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxPackagePolicy":
        return cls(
            allow_package_download=d.get("allow_package_download", False),
            allowed_registries=d.get("allowed_registries", []),
            allowed_packages=d.get("allowed_packages", []),
            blocked_packages=d.get("blocked_packages", []),
            require_hash_verification=d.get("require_hash_verification", True),
            require_signature_verification=d.get("require_signature_verification", True),
            require_sbom=d.get("require_sbom", True),
            quarantine_downloads=d.get("quarantine_downloads", True),
        )


# ═══════════════════════════════════════════
# SandboxPolicy (v2)
# ═══════════════════════════════════════════


@dataclass
class SandboxPolicyV2:
    """Sandbox v2 安全策略 — 默认 deny all。

    所有能力默认关闭，需要显式 action 才能打开。
    """
    policy_id: str = field(default_factory=lambda: f"sbxpolv2_{uuid4().hex[:16]}")
    name: str = "default-deny-all"
    description: str = "Default deny-all sandbox policy"
    default_action: str = SandboxV2Decision.DENY
    allow_network: bool = False
    allow_write_filesystem: bool = False
    allow_package_download: bool = False
    allow_artifact_materialization: bool = False
    require_human_approval: bool = True
    resource_limits: SandboxResourceLimits = field(default_factory=SandboxResourceLimits)
    network_policy: SandboxNetworkPolicy = field(default_factory=SandboxNetworkPolicy)
    filesystem_policy: SandboxFilesystemPolicy = field(default_factory=SandboxFilesystemPolicy)
    artifact_policy: SandboxArtifactPolicy = field(default_factory=SandboxArtifactPolicy)
    package_policy: SandboxPackagePolicy = field(default_factory=SandboxPackagePolicy)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "description": self.description,
            "default_action": self.default_action,
            "allow_network": self.allow_network,
            "allow_write_filesystem": self.allow_write_filesystem,
            "allow_package_download": self.allow_package_download,
            "allow_artifact_materialization": self.allow_artifact_materialization,
            "require_human_approval": self.require_human_approval,
            "resource_limits": self.resource_limits.to_dict(),
            "network_policy": self.network_policy.to_dict(),
            "filesystem_policy": self.filesystem_policy.to_dict(),
            "artifact_policy": self.artifact_policy.to_dict(),
            "package_policy": self.package_policy.to_dict(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxPolicyV2":
        return cls(
            policy_id=d.get("policy_id", f"sbxpolv2_{uuid4().hex[:16]}"),
            name=d.get("name", "default-deny-all"),
            description=d.get("description", ""),
            default_action=d.get("default_action", SandboxV2Decision.DENY),
            allow_network=d.get("allow_network", False),
            allow_write_filesystem=d.get("allow_write_filesystem", False),
            allow_package_download=d.get("allow_package_download", False),
            allow_artifact_materialization=d.get("allow_artifact_materialization", False),
            require_human_approval=d.get("require_human_approval", True),
            resource_limits=SandboxResourceLimits.from_dict(d.get("resource_limits", {})),
            network_policy=SandboxNetworkPolicy.from_dict(d.get("network_policy", {})),
            filesystem_policy=SandboxFilesystemPolicy.from_dict(d.get("filesystem_policy", {})),
            artifact_policy=SandboxArtifactPolicy.from_dict(d.get("artifact_policy", {})),
            package_policy=SandboxPackagePolicy.from_dict(d.get("package_policy", {})),
            metadata=d.get("metadata", {}),
        )


# ═══════════════════════════════════════════
# SandboxPolicyDecision
# ═══════════════════════════════════════════


@dataclass
class SandboxV2PolicyDecision:
    """Sandbox v2 策略决策结果。

    fail_closed: 如果策略评估过程中出现任何缺失字段或异常，本字段为 True。
    """
    allowed: bool = False
    action: str = SandboxV2Decision.DENY
    reason: str = "Default deny — no policy evaluation performed."
    risk_level: str = SandboxV2RiskLevel.UNKNOWN
    required_approvals: list[str] = field(default_factory=list)
    matched_rules: list[str] = field(default_factory=list)
    fail_closed: bool = True
    policy_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "action": self.action,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "required_approvals": self.required_approvals,
            "matched_rules": self.matched_rules,
            "fail_closed": self.fail_closed,
            "policy_snapshot": self.policy_snapshot,
        }


# ═══════════════════════════════════════════
# SandboxJob
# ═══════════════════════════════════════════


@dataclass
class SandboxJob:
    """Sandbox v2 Job — 一次沙箱执行请求。

    安全约束：
    - mode 只允许 metadata_only / simulation / disabled
    - future_container / future_microvm 是预留枚举，不接受真实提交
    """
    job_id: str = field(default_factory=lambda: f"sbxjob_{uuid4().hex[:16]}")
    organization_id: str = ""
    workspace_id: str = ""
    agent_id: str = ""
    requested_by: str = ""
    mode: str = SandboxV2Mode.SIMULATION
    status: str = SandboxV2JobStatus.CREATED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    requested_action: str = ""
    input_ref: str = ""
    policy_snapshot: dict[str, Any] = field(default_factory=dict)
    risk_level: str = SandboxV2RiskLevel.UNKNOWN
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        for f_name in ("policy_snapshot", "metadata"):
            if not isinstance(getattr(self, f_name), dict):
                raise ValueError(f"{f_name} must be dict")

    def is_valid_mode(self) -> bool:
        return self.mode in MVP_ALLOWED_MODES

    def is_terminal(self) -> bool:
        return self.status in {
            SandboxV2JobStatus.REJECTED,
            SandboxV2JobStatus.COMPLETED,
            SandboxV2JobStatus.FAILED,
            SandboxV2JobStatus.CANCELED,
            SandboxV2JobStatus.TIMEOUT,
        }

    def is_cancellable(self) -> bool:
        return self.status in {
            SandboxV2JobStatus.CREATED,
            SandboxV2JobStatus.POLICY_CHECKED,
            SandboxV2JobStatus.QUEUED,
            SandboxV2JobStatus.RUNNING_SIMULATION,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "agent_id": self.agent_id,
            "requested_by": self.requested_by,
            "mode": self.mode,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "requested_action": self.requested_action,
            "input_ref": self.input_ref,
            "policy_snapshot": self.policy_snapshot,
            "risk_level": self.risk_level,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxJob":
        import json as _json

        def _parse_dt(v):
            if isinstance(v, datetime):
                return v
            if isinstance(v, str) and v:
                try:
                    return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)

        return cls(
            job_id=d.get("job_id", f"sbxjob_{uuid4().hex[:16]}"),
            organization_id=d.get("organization_id", ""),
            workspace_id=d.get("workspace_id", ""),
            agent_id=d.get("agent_id", ""),
            requested_by=d.get("requested_by", ""),
            mode=d.get("mode", SandboxV2Mode.SIMULATION),
            status=d.get("status", SandboxV2JobStatus.CREATED),
            created_at=_parse_dt(d.get("created_at")),
            updated_at=_parse_dt(d.get("updated_at")),
            requested_action=d.get("requested_action", ""),
            input_ref=d.get("input_ref", ""),
            policy_snapshot=d.get("policy_snapshot", {}),
            risk_level=d.get("risk_level", SandboxV2RiskLevel.UNKNOWN),
            metadata=d.get("metadata", {}),
        )


# ═══════════════════════════════════════════
# SandboxExecutionRecord (v2)
# ═══════════════════════════════════════════


@dataclass
class SandboxV2ExecutionRecord:
    """Sandbox v2 执行记录 — 每次模拟/元数据执行产生一条记录。

    安全约束：
    - 不记录真实 stdout/stderr 内容
    - artifact_refs 只保留引用，不物化
    - no_real_execution 始终为 True
    """
    record_id: str = field(default_factory=lambda: f"sbxrec_{uuid4().hex[:16]}")
    job_id: str = ""
    status: str = SandboxV2JobStatus.CREATED
    mode: str = SandboxV2Mode.SIMULATION
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int = 0
    decision: str = SandboxV2Decision.DENY
    reason: str = ""
    stdout_ref: str = ""
    stderr_ref: str = ""
    artifact_refs: list[str] = field(default_factory=list)
    audit_refs: list[str] = field(default_factory=list)
    error_code: str = ""
    error_message: str = ""
    no_real_execution: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        for f_name in ("artifact_refs", "audit_refs", "metadata"):
            v = getattr(self, f_name)
            if not isinstance(v, (list, dict)):
                raise ValueError(f"{f_name} must be list or dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "job_id": self.job_id,
            "status": self.status,
            "mode": self.mode,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": self.duration_ms,
            "decision": self.decision,
            "reason": self.reason,
            "stdout_ref": self.stdout_ref,
            "stderr_ref": self.stderr_ref,
            "artifact_refs": self.artifact_refs,
            "audit_refs": self.audit_refs,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "no_real_execution": self.no_real_execution,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2ExecutionRecord":
        def _parse_dt(v):
            if isinstance(v, datetime):
                return v
            if isinstance(v, str) and v:
                try:
                    return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    return None
            return None

        return cls(
            record_id=d.get("record_id", f"sbxrec_{uuid4().hex[:16]}"),
            job_id=d.get("job_id", ""),
            status=d.get("status", SandboxV2JobStatus.CREATED),
            mode=d.get("mode", SandboxV2Mode.SIMULATION),
            started_at=_parse_dt(d.get("started_at")),
            finished_at=_parse_dt(d.get("finished_at")),
            duration_ms=d.get("duration_ms", 0),
            decision=d.get("decision", SandboxV2Decision.DENY),
            reason=d.get("reason", ""),
            stdout_ref=d.get("stdout_ref", ""),
            stderr_ref=d.get("stderr_ref", ""),
            artifact_refs=d.get("artifact_refs", []),
            audit_refs=d.get("audit_refs", []),
            error_code=d.get("error_code", ""),
            error_message=d.get("error_message", ""),
            no_real_execution=d.get("no_real_execution", True),
            metadata=d.get("metadata", {}),
        )


# ═══════════════════════════════════════════
# Step 2 — Queue / Worker Enums
# ═══════════════════════════════════════════


class SandboxV2QueueStatus(StrEnum):
    """队列项状态。"""
    QUEUED = "queued"
    LEASED = "leased"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    TIMEOUT = "timeout"
    DEAD_LETTER = "dead_letter"


class SandboxV2WorkerStatus(StrEnum):
    """Worker 状态。"""
    IDLE = "idle"
    PROCESSING = "processing"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


# ═══════════════════════════════════════════
# Step 2 — SandboxQueueItem
# ═══════════════════════════════════════════


@dataclass
class SandboxQueueItem:
    """Sandbox v2 队列项 — 管理 job 的调度和租约。

    队列不执行 job，只负责调度。
    """
    queue_id: str = field(default_factory=lambda: f"sbxque_{uuid4().hex[:16]}")
    job_id: str = ""
    organization_id: str = ""
    workspace_id: str = ""
    priority: int = 100
    status: str = SandboxV2QueueStatus.QUEUED
    attempts: int = 0
    max_attempts: int = 3
    available_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    leased_by: str = ""
    leased_until: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_error: str = ""
    dead_letter_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be dict")

    def can_retry(self) -> bool:
        return self.attempts < self.max_attempts

    def is_lease_expired(self, now: datetime | None = None) -> bool:
        if self.leased_until is None:
            return False
        now = now or datetime.now(timezone.utc)
        return now > self.leased_until

    def is_cancellable(self) -> bool:
        return self.status in {
            SandboxV2QueueStatus.QUEUED,
            SandboxV2QueueStatus.LEASED,
            SandboxV2QueueStatus.PROCESSING,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "queue_id": self.queue_id,
            "job_id": self.job_id,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "priority": self.priority,
            "status": self.status,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "available_at": self.available_at.isoformat(),
            "leased_by": self.leased_by,
            "leased_until": self.leased_until.isoformat() if self.leased_until else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_error": self.last_error,
            "dead_letter_reason": self.dead_letter_reason,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxQueueItem":
        def _parse_dt(v):
            if isinstance(v, datetime):
                return v
            if isinstance(v, str) and v:
                try:
                    return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    return None
            return None

        return cls(
            queue_id=d.get("queue_id", f"sbxque_{uuid4().hex[:16]}"),
            job_id=d.get("job_id", ""),
            organization_id=d.get("organization_id", ""),
            workspace_id=d.get("workspace_id", ""),
            priority=d.get("priority", 100),
            status=d.get("status", SandboxV2QueueStatus.QUEUED),
            attempts=d.get("attempts", 0),
            max_attempts=d.get("max_attempts", 3),
            available_at=_parse_dt(d.get("available_at")) or datetime.now(timezone.utc),
            leased_by=d.get("leased_by", ""),
            leased_until=_parse_dt(d.get("leased_until")),
            created_at=_parse_dt(d.get("created_at")) or datetime.now(timezone.utc),
            updated_at=_parse_dt(d.get("updated_at")) or datetime.now(timezone.utc),
            last_error=d.get("last_error", ""),
            dead_letter_reason=d.get("dead_letter_reason", ""),
            metadata=d.get("metadata", {}),
        )


# ═══════════════════════════════════════════
# Step 2 — SandboxWorkerHeartbeat
# ═══════════════════════════════════════════


@dataclass
class SandboxWorkerHeartbeat:
    """Worker 心跳记录 — 追踪 worker 生命周期。"""
    worker_id: str = field(default_factory=lambda: f"sbxwkr_{uuid4().hex[:16]}")
    status: str = SandboxV2WorkerStatus.IDLE
    current_job_id: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_heartbeat_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    processed_count: int = 0
    failed_count: int = 0
    canceled_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "status": self.status,
            "current_job_id": self.current_job_id,
            "started_at": self.started_at.isoformat(),
            "last_heartbeat_at": self.last_heartbeat_at.isoformat(),
            "processed_count": self.processed_count,
            "failed_count": self.failed_count,
            "canceled_count": self.canceled_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxWorkerHeartbeat":
        def _parse_dt(v):
            if isinstance(v, datetime):
                return v
            if isinstance(v, str) and v:
                try:
                    return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)

        return cls(
            worker_id=d.get("worker_id", f"sbxwkr_{uuid4().hex[:16]}"),
            status=d.get("status", SandboxV2WorkerStatus.IDLE),
            current_job_id=d.get("current_job_id", ""),
            started_at=_parse_dt(d.get("started_at")),
            last_heartbeat_at=_parse_dt(d.get("last_heartbeat_at")),
            processed_count=d.get("processed_count", 0),
            failed_count=d.get("failed_count", 0),
            canceled_count=d.get("canceled_count", 0),
            metadata=d.get("metadata", {}),
        )


# ═══════════════════════════════════════════
# Step 2 — SandboxWorkerResult
# ═══════════════════════════════════════════


@dataclass
class SandboxWorkerResult:
    """Worker 处理结果。"""
    worker_id: str = ""
    job_id: str = ""
    status: str = SandboxV2JobStatus.CREATED
    execution_record_id: str = ""
    error_code: str = ""
    error_message: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "job_id": self.job_id,
            "status": self.status,
            "execution_record_id": self.execution_record_id,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
        }


# ═══════════════════════════════════════════
# Step 3 — Artifact Enums
# ═══════════════════════════════════════════


class SandboxV2ArtifactStatus(StrEnum):
    """Artifact 状态。"""
    PENDING = "pending"
    MATERIALIZED = "materialized"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"
    DELETED = "deleted"
    EXPIRED = "expired"
    FAILED = "failed"


class SandboxV2ArtifactType(StrEnum):
    """Artifact 类型。"""
    STDOUT = "stdout"
    STDERR = "stderr"
    LOG = "log"
    REPORT = "report"
    JSON = "json"
    TEXT = "text"
    INPUT = "input"
    OUTPUT = "output"
    DIAGNOSTIC = "diagnostic"
    UNKNOWN = "unknown"


# 危险文件扩展名 — 禁止物化
BLOCKED_FILE_EXTENSIONS: frozenset[str] = frozenset({
    ".exe", ".dll", ".bat", ".cmd", ".ps1", ".sh", ".bash",
    ".so", ".dylib", ".jar", ".pyc", ".pyo", ".msi", ".scr",
    ".com", ".vbs", ".vba", ".wsf", ".ws", ".reg", ".lnk",
})

# 允许的 MIME 类型白名单
ALLOWED_ARTIFACT_MIME_TYPES: frozenset[str] = frozenset({
    "text/plain",
    "application/json",
    "text/markdown",
    "text/csv",
    "text/html",
    "text/xml",
    "application/xml",
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/svg+xml",
    "application/octet-stream",  # 仅在明确允许时使用
})

# 默认 artifact 大小限制
DEFAULT_ARTIFACT_MAX_BYTES: int = 1_048_576  # 1 MiB
DEFAULT_JOB_TOTAL_ARTIFACT_BYTES: int = 10_485_760  # 10 MiB


# ═══════════════════════════════════════════
# Step 3 — SandboxArtifact
# ═══════════════════════════════════════════


@dataclass
class SandboxArtifact:
    """Sandbox v2 Artifact — 安全文件 artifact。

    安全约束：
    - 文件只存储在 artifact root 内
    - 默认只读
    - 路径经过 sanitize
    - 用户原始文件名不用于真实路径
    """
    artifact_id: str = field(default_factory=lambda: f"sbxart_{uuid4().hex[:16]}")
    job_id: str = ""
    organization_id: str = ""
    workspace_id: str = ""
    record_id: str = ""
    artifact_type: str = SandboxV2ArtifactType.UNKNOWN
    name: str = ""
    original_filename: str = ""
    safe_filename: str = ""
    storage_key: str = ""
    storage_backend: str = "local"
    size_bytes: int = 0
    mime_type: str = "text/plain"
    sha256: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    materialized_at: datetime | None = None
    read_only: bool = True
    status: str = SandboxV2ArtifactStatus.PENDING
    retention_until: datetime | None = None
    risk_level: str = SandboxV2RiskLevel.LOW
    policy_decision_id: str = ""
    audit_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        for f_name in ("audit_refs", "metadata"):
            v = getattr(self, f_name)
            if not isinstance(v, (list, dict)):
                raise ValueError(f"{f_name} must be list or dict")

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.retention_until is None:
            return False
        now = now or datetime.now(timezone.utc)
        return now > self.retention_until

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "job_id": self.job_id,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "record_id": self.record_id,
            "artifact_type": self.artifact_type,
            "name": self.name,
            "original_filename": self.original_filename,
            "safe_filename": self.safe_filename,
            "storage_key": self.storage_key,
            "storage_backend": self.storage_backend,
            "size_bytes": self.size_bytes,
            "mime_type": self.mime_type,
            "sha256": self.sha256,
            "created_at": self.created_at.isoformat(),
            "materialized_at": self.materialized_at.isoformat() if self.materialized_at else None,
            "read_only": self.read_only,
            "status": self.status,
            "retention_until": self.retention_until.isoformat() if self.retention_until else None,
            "risk_level": self.risk_level,
            "policy_decision_id": self.policy_decision_id,
            "audit_refs": self.audit_refs,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxArtifact":
        def _parse_dt(v):
            if isinstance(v, datetime):
                return v
            if isinstance(v, str) and v:
                try:
                    return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    return None
            return None

        return cls(
            artifact_id=d.get("artifact_id", f"sbxart_{uuid4().hex[:16]}"),
            job_id=d.get("job_id", ""),
            organization_id=d.get("organization_id", ""),
            workspace_id=d.get("workspace_id", ""),
            record_id=d.get("record_id", ""),
            artifact_type=d.get("artifact_type", SandboxV2ArtifactType.UNKNOWN),
            name=d.get("name", ""),
            original_filename=d.get("original_filename", ""),
            safe_filename=d.get("safe_filename", ""),
            storage_key=d.get("storage_key", ""),
            storage_backend=d.get("storage_backend", "local"),
            size_bytes=d.get("size_bytes", 0),
            mime_type=d.get("mime_type", "text/plain"),
            sha256=d.get("sha256", ""),
            created_at=_parse_dt(d.get("created_at")) or datetime.now(timezone.utc),
            materialized_at=_parse_dt(d.get("materialized_at")),
            read_only=d.get("read_only", True),
            status=d.get("status", SandboxV2ArtifactStatus.PENDING),
            retention_until=_parse_dt(d.get("retention_until")),
            risk_level=d.get("risk_level", SandboxV2RiskLevel.LOW),
            policy_decision_id=d.get("policy_decision_id", ""),
            audit_refs=d.get("audit_refs", []),
            metadata=d.get("metadata", {}),
        )


# ═══════════════════════════════════════════
# Step 3 — SandboxArtifactManifest
# ═══════════════════════════════════════════


@dataclass
class SandboxArtifactManifest:
    """Artifact manifest — 一个 job/record 的所有 artifact 清单。"""
    manifest_id: str = field(default_factory=lambda: f"sbxmft_{uuid4().hex[:16]}")
    job_id: str = ""
    record_id: str = ""
    artifact_ids: list[str] = field(default_factory=list)
    total_size_bytes: int = 0
    artifact_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sealed: bool = False
    sha256: str = ""

    def __post_init__(self):
        if not isinstance(self.artifact_ids, list):
            raise ValueError("artifact_ids must be list")

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "job_id": self.job_id,
            "record_id": self.record_id,
            "artifact_ids": self.artifact_ids,
            "total_size_bytes": self.total_size_bytes,
            "artifact_count": self.artifact_count,
            "created_at": self.created_at.isoformat(),
            "sealed": self.sealed,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxArtifactManifest":
        def _parse_dt(v):
            if isinstance(v, datetime):
                return v
            if isinstance(v, str) and v:
                try:
                    return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)

        return cls(
            manifest_id=d.get("manifest_id", f"sbxmft_{uuid4().hex[:16]}"),
            job_id=d.get("job_id", ""),
            record_id=d.get("record_id", ""),
            artifact_ids=d.get("artifact_ids", []),
            total_size_bytes=d.get("total_size_bytes", 0),
            artifact_count=d.get("artifact_count", 0),
            created_at=_parse_dt(d.get("created_at")),
            sealed=d.get("sealed", False),
            sha256=d.get("sha256", ""),
        )


# ═══════════════════════════════════════════
# Step 3 — SandboxArtifactMaterializationRequest
# ═══════════════════════════════════════════


@dataclass
class SandboxArtifactMaterializationRequest:
    """Artifact 物化请求。"""
    job_id: str = ""
    record_id: str = ""
    artifact_name: str = ""
    artifact_type: str = SandboxV2ArtifactType.UNKNOWN
    source_ref: str = ""
    content_bytes: bytes = field(default=b"")
    content_text: str = ""
    requested_by: str = ""
    read_only: bool = True
    mime_type: str = ""
    organization_id: str = ""
    workspace_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_content(self) -> bytes:
        if self.content_bytes:
            return self.content_bytes
        if self.content_text:
            return self.content_text.encode("utf-8")
        return b""

    def get_size(self) -> int:
        return len(self.get_content())

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "record_id": self.record_id,
            "artifact_name": self.artifact_name,
            "artifact_type": self.artifact_type,
            "source_ref": self.source_ref,
            "requested_by": self.requested_by,
            "read_only": self.read_only,
            "mime_type": self.mime_type,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════
# Step 3 — SandboxArtifactPolicyDecision
# ═══════════════════════════════════════════


@dataclass
class SandboxArtifactPolicyDecision:
    """Artifact 策略决策。"""
    allowed: bool = False
    reason: str = "Default deny — no artifact policy evaluation performed."
    risk_level: str = SandboxV2RiskLevel.MEDIUM
    max_size_bytes: int = DEFAULT_ARTIFACT_MAX_BYTES
    allowed_mime_types: list[str] = field(default_factory=list)
    read_only_required: bool = True
    fail_closed: bool = True
    matched_rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "max_size_bytes": self.max_size_bytes,
            "allowed_mime_types": self.allowed_mime_types,
            "read_only_required": self.read_only_required,
            "fail_closed": self.fail_closed,
            "matched_rules": self.matched_rules,
        }


# ═══════════════════════════════════════════
# Step 4 — Package / Supply Chain Enums
# ═══════════════════════════════════════════


class SandboxV2PackageManager(StrEnum):
    PIP = "pip"
    NPM = "npm"
    PNPM = "pnpm"
    YARN = "yarn"
    CARGO = "cargo"
    MAVEN = "maven"
    UNKNOWN = "unknown"


class SandboxV2PackageSourceType(StrEnum):
    OFFLINE_UPLOAD = "offline_upload"
    INTERNAL_REGISTRY = "internal_registry"
    EXTERNAL_URL = "external_url"
    PUBLIC_REGISTRY = "public_registry"
    UNKNOWN = "unknown"


class SandboxV2PackageRequestStatus(StrEnum):
    REQUESTED = "requested"
    POLICY_CHECKED = "policy_checked"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"
    PENDING_REVIEW = "pending_review"
    APPROVED_METADATA_ONLY = "approved_metadata_only"
    RELEASED = "released"
    FAILED = "failed"
    DELETED = "deleted"


class SandboxV2PackageQuarantineStatus(StrEnum):
    QUARANTINED = "quarantined"
    PENDING_SCAN = "pending_scan"
    SCAN_FAILED = "scan_failed"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    RELEASED_METADATA_ONLY = "released_metadata_only"
    DELETED = "deleted"


class SandboxV2SignatureStatus(StrEnum):
    NOT_PROVIDED = "not_provided"
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class SandboxV2SBOMStatus(StrEnum):
    NOT_PROVIDED = "not_provided"
    PROVIDED = "provided"
    VERIFIED = "verified"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class SandboxV2VulnerabilityStatus(StrEnum):
    NOT_SCANNED = "not_scanned"
    CLEAN = "clean"
    FINDINGS_LOW = "findings_low"
    FINDINGS_MEDIUM = "findings_medium"
    FINDINGS_HIGH = "findings_high"
    FINDINGS_CRITICAL = "findings_critical"
    SCANNER_UNAVAILABLE = "scanner_unavailable"
    FAILED = "failed"


# 默认包大小限制
DEFAULT_PACKAGE_MAX_BYTES: int = 10_485_760  # 10 MiB

# 禁止的 source_url 模式
BLOCKED_SOURCE_URL_PREFIXES: frozenset[str] = frozenset({
    "file://",
    "http://169.254.169.254",  # AWS metadata
    "http://metadata.google.internal",  # GCP metadata
    "http://100.100.100.200",  # Alibaba Cloud metadata
})

SAFE_SOURCE_URL_PREFIXES: frozenset[str] = frozenset({
    "offline://",  # 离线 fixture
    "internal://",  # 内部 registry placeholder
    "test://",  # 测试 fixture
})


# ═══════════════════════════════════════════
# Step 4 — SandboxPackageRequest
# ═══════════════════════════════════════════


@dataclass
class SandboxPackageRequest:
    package_request_id: str = field(default_factory=lambda: f"sbxpkg_{uuid4().hex[:16]}")
    job_id: str = ""
    organization_id: str = ""
    workspace_id: str = ""
    requested_by: str = ""
    package_name: str = ""
    package_version: str = ""
    package_manager: str = SandboxV2PackageManager.UNKNOWN
    source_url: str = ""
    source_type: str = SandboxV2PackageSourceType.UNKNOWN
    requested_action: str = ""
    expected_sha256: str = ""
    expected_signature: str = ""
    sbom_ref: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = SandboxV2PackageRequestStatus.REQUESTED
    risk_level: str = SandboxV2RiskLevel.UNKNOWN
    policy_decision_id: str = ""
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_request_id": self.package_request_id,
            "job_id": self.job_id,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "requested_by": self.requested_by,
            "package_name": self.package_name,
            "package_version": self.package_version,
            "package_manager": self.package_manager,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "requested_action": self.requested_action,
            "expected_sha256": self.expected_sha256,
            "expected_signature": self.expected_signature,
            "sbom_ref": self.sbom_ref,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "risk_level": self.risk_level,
            "policy_decision_id": self.policy_decision_id,
            "reason": self.reason,
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════
# Step 4 — SandboxPackagePolicyDecision
# ═══════════════════════════════════════════


@dataclass
class SandboxPackagePolicyDecision:
    allowed: bool = False
    action: str = "deny"
    reason: str = "Default deny — package policy not evaluated."
    risk_level: str = SandboxV2RiskLevel.MEDIUM
    require_hash: bool = True
    require_signature: bool = True
    require_sbom: bool = True
    require_vulnerability_scan: bool = True
    quarantine_required: bool = True
    network_download_allowed: bool = False
    matched_rules: list[str] = field(default_factory=list)
    fail_closed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "action": self.action,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "require_hash": self.require_hash,
            "require_signature": self.require_signature,
            "require_sbom": self.require_sbom,
            "require_vulnerability_scan": self.require_vulnerability_scan,
            "quarantine_required": self.quarantine_required,
            "network_download_allowed": self.network_download_allowed,
            "matched_rules": self.matched_rules,
            "fail_closed": self.fail_closed,
        }


# ═══════════════════════════════════════════
# Step 4 — SandboxPackageQuarantineRecord
# ═══════════════════════════════════════════


@dataclass
class SandboxPackageQuarantineRecord:
    quarantine_id: str = field(default_factory=lambda: f"sbxqrp_{uuid4().hex[:16]}")
    package_request_id: str = ""
    job_id: str = ""
    organization_id: str = ""
    workspace_id: str = ""
    package_name: str = ""
    package_version: str = ""
    package_manager: str = SandboxV2PackageManager.UNKNOWN
    storage_key: str = ""
    size_bytes: int = 0
    sha256: str = ""
    signature_status: str = SandboxV2SignatureStatus.NOT_PROVIDED
    sbom_status: str = SandboxV2SBOMStatus.NOT_PROVIDED
    vulnerability_status: str = SandboxV2VulnerabilityStatus.NOT_SCANNED
    status: str = SandboxV2PackageQuarantineStatus.QUARANTINED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: datetime | None = None
    reviewed_by: str = ""
    release_decision: str = ""
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "quarantine_id": self.quarantine_id,
            "package_request_id": self.package_request_id,
            "job_id": self.job_id,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "package_name": self.package_name,
            "package_version": self.package_version,
            "package_manager": self.package_manager,
            "storage_key": self.storage_key,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "signature_status": self.signature_status,
            "sbom_status": self.sbom_status,
            "vulnerability_status": self.vulnerability_status,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewed_by": self.reviewed_by,
            "release_decision": self.release_decision,
            "reason": self.reason,
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════
# Step 4 — SandboxPackageSBOM
# ═══════════════════════════════════════════


@dataclass
class SandboxPackageSBOM:
    sbom_id: str = field(default_factory=lambda: f"sbxsbom_{uuid4().hex[:16]}")
    package_request_id: str = ""
    package_name: str = ""
    package_version: str = ""
    format: str = "unknown"  # cyclonedx-json, spdx-json, unknown
    content_sha256: str = ""
    component_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    storage_key: str = ""
    status: str = SandboxV2SBOMStatus.PROVIDED
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "sbom_id": self.sbom_id,
            "package_request_id": self.package_request_id,
            "package_name": self.package_name,
            "package_version": self.package_version,
            "format": self.format,
            "content_sha256": self.content_sha256,
            "component_count": self.component_count,
            "created_at": self.created_at.isoformat(),
            "storage_key": self.storage_key,
            "status": self.status,
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════
# Step 4 — SandboxPackageVulnerabilityScanResult
# ═══════════════════════════════════════════


@dataclass
class SandboxPackageVulnerabilityScanResult:
    scan_id: str = field(default_factory=lambda: f"sbxvuln_{uuid4().hex[:16]}")
    package_request_id: str = ""
    package_name: str = ""
    package_version: str = ""
    scanner: str = "sbom_fixture_scanner"
    status: str = SandboxV2VulnerabilityStatus.NOT_SCANNED
    severity_summary: str = ""
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    findings: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.findings, list):
            raise ValueError("findings must be list")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "package_request_id": self.package_request_id,
            "package_name": self.package_name,
            "package_version": self.package_version,
            "scanner": self.scanner,
            "status": self.status,
            "severity_summary": self.severity_summary,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "findings": self.findings,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════
# Step 5 — Network Egress Enums
# ═══════════════════════════════════════════


class SandboxV2NetworkEgressStatus(StrEnum):
    REQUESTED = "requested"
    POLICY_CHECKED = "policy_checked"
    ALLOWED_PREFLIGHT = "allowed_preflight"
    REJECTED = "rejected"
    AUDITED = "audited"
    FAILED = "failed"


class SandboxV2NetworkEgressAction(StrEnum):
    DENY = "deny"
    ALLOW_PREFLIGHT_ONLY = "allow_preflight_only"
    ALLOW_VIA_FUTURE_PROXY = "allow_via_future_proxy"
    QUARANTINE = "quarantine"
    REQUIRE_REVIEW = "require_review"


# 危险 schemes
BLOCKED_NETWORK_SCHEMES: frozenset[str] = frozenset({
    "file", "ftp", "gopher", "dict", "ssh", "smb", "ldap", "ldaps",
    "telnet", "tftp", "data", "javascript", "vbscript",
})

# 允许的 schemes
ALLOWED_NETWORK_SCHEMES: frozenset[str] = frozenset({"http", "https"})

# 默认允许端口
DEFAULT_ALLOWED_PORTS: frozenset[int] = frozenset({80, 443})

# 私有网段 (CIDR)
PRIVATE_NETWORKS_V4: list[tuple[str, str]] = [
    ("10.0.0.0", "10.255.255.255"),
    ("172.16.0.0", "172.31.255.255"),
    ("192.168.0.0", "192.168.255.255"),
    ("127.0.0.0", "127.255.255.255"),
    ("169.254.0.0", "169.254.255.255"),
    ("0.0.0.0", "0.255.255.255"),
    ("224.0.0.0", "239.255.255.255"),
]


# ═══════════════════════════════════════════
# Step 5 — SandboxNetworkEgressRequest
# ═══════════════════════════════════════════


@dataclass
class SandboxNetworkEgressRequest:
    egress_request_id: str = field(default_factory=lambda: f"sbxegr_{uuid4().hex[:16]}")
    job_id: str = ""
    organization_id: str = ""
    workspace_id: str = ""
    requested_by: str = ""
    url: str = ""
    scheme: str = ""
    hostname: str = ""
    port: int = 443
    resolved_ips: list[str] = field(default_factory=list)
    method: str = "GET"
    purpose: str = ""
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = SandboxV2NetworkEgressStatus.REQUESTED
    risk_level: str = SandboxV2RiskLevel.MEDIUM
    policy_decision_id: str = ""
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "egress_request_id": self.egress_request_id,
            "job_id": self.job_id, "organization_id": self.organization_id,
            "workspace_id": self.workspace_id, "requested_by": self.requested_by,
            "url": self.url, "scheme": self.scheme, "hostname": self.hostname,
            "port": self.port, "resolved_ips": self.resolved_ips,
            "method": self.method, "purpose": self.purpose,
            "requested_at": self.requested_at.isoformat(),
            "status": self.status, "risk_level": self.risk_level,
            "policy_decision_id": self.policy_decision_id,
            "reason": self.reason, "metadata": self.metadata,
        }


# ═══════════════════════════════════════════
# Step 5 — SandboxNetworkEgressPolicyDecision
# ═══════════════════════════════════════════


@dataclass
class SandboxNetworkEgressPolicyDecision:
    allowed: bool = False
    action: str = SandboxV2NetworkEgressAction.DENY
    reason: str = "Default deny — network egress not evaluated."
    risk_level: str = SandboxV2RiskLevel.MEDIUM
    scheme_allowed: bool = False
    host_allowed: bool = False
    ip_allowed: bool = False
    port_allowed: bool = False
    dns_resolution_allowed: bool = False
    metadata_service_blocked: bool = True
    private_network_blocked: bool = True
    matched_rules: list[str] = field(default_factory=list)
    fail_closed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed, "action": self.action,
            "reason": self.reason, "risk_level": self.risk_level,
            "scheme_allowed": self.scheme_allowed, "host_allowed": self.host_allowed,
            "ip_allowed": self.ip_allowed, "port_allowed": self.port_allowed,
            "dns_resolution_allowed": self.dns_resolution_allowed,
            "metadata_service_blocked": self.metadata_service_blocked,
            "private_network_blocked": self.private_network_blocked,
            "matched_rules": self.matched_rules, "fail_closed": self.fail_closed,
        }


# ═══════════════════════════════════════════
# Step 5 — SandboxNetworkEgressAuditRecord
# ═══════════════════════════════════════════


@dataclass
class SandboxNetworkEgressAuditRecord:
    audit_id: str = field(default_factory=lambda: f"sbxaud_{uuid4().hex[:16]}")
    egress_request_id: str = ""
    job_id: str = ""
    organization_id: str = ""
    workspace_id: str = ""
    url: str = ""
    hostname: str = ""
    resolved_ips: list[str] = field(default_factory=list)
    decision: str = SandboxV2NetworkEgressAction.DENY
    reason: str = ""
    risk_level: str = SandboxV2RiskLevel.MEDIUM
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id, "egress_request_id": self.egress_request_id,
            "job_id": self.job_id, "organization_id": self.organization_id,
            "workspace_id": self.workspace_id, "url": self.url,
            "hostname": self.hostname, "resolved_ips": self.resolved_ips,
            "decision": self.decision, "reason": self.reason,
            "risk_level": self.risk_level, "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════
# Step 5 — SandboxNetworkPolicyConfig
# ═══════════════════════════════════════════


@dataclass
class SandboxNetworkPolicyConfig:
    allow_network: bool = False
    allowed_domains: list[str] = field(default_factory=list)
    denied_domains: list[str] = field(default_factory=list)
    allowed_ports: list[int] = field(default_factory=list)
    denied_ports: list[int] = field(default_factory=list)
    allowed_schemes: list[str] = field(default_factory=list)
    block_private_networks: bool = True
    block_loopback: bool = True
    block_link_local: bool = True
    block_metadata_service: bool = True
    require_dns_preflight: bool = True
    default_action: str = "deny"

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_network": self.allow_network, "allowed_domains": self.allowed_domains,
            "denied_domains": self.denied_domains, "allowed_ports": self.allowed_ports,
            "denied_ports": self.denied_ports, "allowed_schemes": self.allowed_schemes,
            "block_private_networks": self.block_private_networks,
            "block_loopback": self.block_loopback,
            "block_link_local": self.block_link_local,
            "block_metadata_service": self.block_metadata_service,
            "require_dns_preflight": self.require_dns_preflight,
            "default_action": self.default_action,
        }


# ═══════════════════════════════════════════
# Step 6A — Isolation / Execution Enums
# ═══════════════════════════════════════════


class SandboxV2IsolationProvider(StrEnum):
    DISABLED = "disabled"
    SIMULATION = "simulation"
    TRUSTED_FIXTURE = "trusted_fixture"
    LOCAL_PROCESS_DISABLED = "local_process_disabled"
    DOCKER_ROOTLESS_FUTURE = "docker_rootless_future"
    PODMAN_ROOTLESS_FUTURE = "podman_rootless_future"
    GVISOR_FUTURE = "gvisor_future"
    KATA_FUTURE = "kata_future"
    FIRECRACKER_FUTURE = "firecracker_future"
    MICROVM_FUTURE = "microvm_future"


class SandboxV2ExecutionPlanStatus(StrEnum):
    CREATED = "created"
    CAPABILITY_CHECKED = "capability_checked"
    REJECTED = "rejected"
    APPROVED_FOR_FIXTURE = "approved_for_fixture"
    EXECUTED_FIXTURE = "executed_fixture"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    UNAVAILABLE = "unavailable"


# 在本步骤中允许的 provider
STEP6A_ALLOWED_PROVIDERS: frozenset[str] = frozenset({
    SandboxV2IsolationProvider.SIMULATION,
    SandboxV2IsolationProvider.TRUSTED_FIXTURE,
    SandboxV2IsolationProvider.DISABLED,
    SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE,
    SandboxV2IsolationProvider.PODMAN_ROOTLESS_FUTURE,
    # Step 11 — MicroVM providers require strict conditions (see microvm_policy)
    SandboxV2IsolationProvider.FIRECRACKER_FUTURE,
    SandboxV2IsolationProvider.MICROVM_FUTURE,
})


# ═══════════════════════════════════════════
# Step 6A — SandboxIsolationCapability
# ═══════════════════════════════════════════


@dataclass
class SandboxIsolationCapability:
    capability_id: str = field(default_factory=lambda: f"sbxiso_{uuid4().hex[:16]}")
    provider: str = SandboxV2IsolationProvider.DISABLED
    available: bool = False
    enabled: bool = False
    reason: str = ""
    platform: str = ""
    os_name: str = ""
    is_windows: bool = False
    is_linux: bool = False
    has_docker: bool = False
    has_podman: bool = False
    has_firecracker: bool = False
    has_gvisor: bool = False
    has_kata: bool = False
    has_user_namespace: bool = False
    has_cgroup: bool = False
    has_seccomp: bool = False
    has_apparmor: bool = False
    has_selinux: bool = False
    has_network_namespace: bool = False
    has_mount_namespace: bool = False
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id, "provider": self.provider,
            "available": self.available, "enabled": self.enabled,
            "reason": self.reason, "platform": self.platform, "os_name": self.os_name,
            "is_windows": self.is_windows, "is_linux": self.is_linux,
            "has_docker": self.has_docker, "has_podman": self.has_podman,
            "has_firecracker": self.has_firecracker, "has_gvisor": self.has_gvisor,
            "has_kata": self.has_kata, "has_user_namespace": self.has_user_namespace,
            "has_cgroup": self.has_cgroup, "has_seccomp": self.has_seccomp,
            "has_apparmor": self.has_apparmor, "has_selinux": self.has_selinux,
            "has_network_namespace": self.has_network_namespace,
            "has_mount_namespace": self.has_mount_namespace,
            "checked_at": self.checked_at.isoformat(), "metadata": self.metadata,
        }


# ═══════════════════════════════════════════
# Step 6A — SandboxExecutionPlan
# ═══════════════════════════════════════════


@dataclass
class SandboxExecutionPlan:
    execution_plan_id: str = field(default_factory=lambda: f"sbxep_{uuid4().hex[:16]}")
    job_id: str = ""
    organization_id: str = ""
    workspace_id: str = ""
    provider: str = SandboxV2IsolationProvider.DISABLED
    mode: str = SandboxV2Mode.SIMULATION
    command_ref: str = ""
    image_ref: str = ""
    input_artifact_refs: list[str] = field(default_factory=list)
    output_artifact_policy: dict[str, Any] = field(default_factory=dict)
    network_policy_snapshot: dict[str, Any] = field(default_factory=dict)
    filesystem_policy_snapshot: dict[str, Any] = field(default_factory=dict)
    resource_limits: dict[str, Any] = field(default_factory=dict)
    environment_policy: dict[str, Any] = field(default_factory=dict)
    working_directory_policy: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = SandboxV2ExecutionPlanStatus.CREATED
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_plan_id": self.execution_plan_id, "job_id": self.job_id,
            "organization_id": self.organization_id, "workspace_id": self.workspace_id,
            "provider": self.provider, "mode": self.mode,
            "command_ref": self.command_ref, "image_ref": self.image_ref,
            "input_artifact_refs": self.input_artifact_refs,
            "output_artifact_policy": self.output_artifact_policy,
            "network_policy_snapshot": self.network_policy_snapshot,
            "filesystem_policy_snapshot": self.filesystem_policy_snapshot,
            "resource_limits": self.resource_limits,
            "environment_policy": self.environment_policy,
            "working_directory_policy": self.working_directory_policy,
            "created_at": self.created_at.isoformat(), "status": self.status,
            "reason": self.reason, "metadata": self.metadata,
        }


# ═══════════════════════════════════════════
# Step 6A — SandboxIsolationDecision
# ═══════════════════════════════════════════


@dataclass
class SandboxIsolationDecision:
    allowed: bool = False
    provider: str = SandboxV2IsolationProvider.DISABLED
    action: str = "deny"
    reason: str = "Default deny — isolation decision not evaluated."
    risk_level: str = SandboxV2RiskLevel.MEDIUM
    required_capabilities: list[str] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)
    fail_closed: bool = True
    execution_allowed: bool = False
    network_allowed: bool = False
    filesystem_write_allowed: bool = False
    package_install_allowed: bool = False
    matched_rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed, "provider": self.provider,
            "action": self.action, "reason": self.reason,
            "risk_level": self.risk_level,
            "required_capabilities": self.required_capabilities,
            "missing_capabilities": self.missing_capabilities,
            "fail_closed": self.fail_closed,
            "execution_allowed": self.execution_allowed,
            "network_allowed": self.network_allowed,
            "filesystem_write_allowed": self.filesystem_write_allowed,
            "package_install_allowed": self.package_install_allowed,
            "matched_rules": self.matched_rules,
        }


# ═══════════════════════════════════════════
# Step 6A — SandboxTrustedFixtureExecutionResult
# ═══════════════════════════════════════════


@dataclass
class SandboxTrustedFixtureExecutionResult:
    fixture_id: str = field(default_factory=lambda: f"sbxfix_{uuid4().hex[:16]}")
    job_id: str = ""
    provider: str = SandboxV2IsolationProvider.TRUSTED_FIXTURE
    status: str = SandboxV2JobStatus.CREATED
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int = 0
    stdout_text: str = ""
    stderr_text: str = ""
    exit_code: int = 0
    artifact_refs: list[str] = field(default_factory=list)
    decision: str = SandboxV2Decision.ALLOW
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id, "job_id": self.job_id,
            "provider": self.provider, "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": self.duration_ms, "stdout_text": self.stdout_text,
            "stderr_text": self.stderr_text, "exit_code": self.exit_code,
            "artifact_refs": self.artifact_refs, "decision": self.decision,
            "reason": self.reason, "metadata": self.metadata,
        }


# ═══════════════════════════════════════════
# Step 6B — Container Execution Enums + Models
# ═══════════════════════════════════════════


class SandboxV2ContainerRuntime(StrEnum):
    DOCKER = "docker"; PODMAN = "podman"; UNAVAILABLE = "unavailable"


class SandboxV2ContainerExecutionStatus(StrEnum):
    CREATED = "created"; REJECTED = "rejected"; DRY_RUN = "dry_run"
    RUNNING = "running"; COMPLETED = "completed"; FAILED = "failed"
    TIMEOUT = "timeout"; CANCELED = "canceled"; UNAVAILABLE = "unavailable"


TRUSTED_CONTAINER_FIXTURES: dict[str, list[str]] = {
    "hello-container-fixture": ["python", "-c", "print('sandbox-v2 trusted container fixture ok')"],
    "container-env-dump": ["python", "-c", "import os; print('\\n'.join(f'{k}={v}' for k,v in sorted(os.environ.items())))"],
    "container-id": ["whoami"],
    "container-fs": ["ls", "-la", "/"],
}
DEFAULT_ALLOWED_IMAGES: frozenset[str] = frozenset({"python:3.11-alpine", "busybox:latest"})


@dataclass
class SandboxContainerRuntimeConfig:
    provider: str = SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE
    runtime: str = SandboxV2ContainerRuntime.UNAVAILABLE
    enabled: bool = False; rootless_required: bool = True
    network_disabled: bool = True; readonly_rootfs: bool = True
    no_new_privileges: bool = True; drop_all_capabilities: bool = True
    run_as_non_root: bool = True; memory_limit_mb: int = 256; cpu_limit: float = 0.5
    pids_limit: int = 64; timeout_seconds: int = 30; tmpfs_enabled: bool = True
    allowed_images: list[str] = field(default_factory=lambda: sorted(DEFAULT_ALLOWED_IMAGES))
    allowed_fixture_ids: list[str] = field(default_factory=lambda: sorted(TRUSTED_CONTAINER_FIXTURES.keys()))
    artifact_output_mode: str = "read_only"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) if not isinstance(getattr(self, k), (datetime, list, dict)) else (getattr(self, k).isoformat() if isinstance(getattr(self, k), datetime) else getattr(self, k)) for k in ["provider","runtime","enabled","rootless_required","network_disabled","readonly_rootfs","no_new_privileges","drop_all_capabilities","run_as_non_root","memory_limit_mb","cpu_limit","pids_limit","timeout_seconds","tmpfs_enabled","allowed_images","allowed_fixture_ids","artifact_output_mode"]} | {"created_at": self.created_at.isoformat(), "metadata": self.metadata}


@dataclass
class SandboxContainerExecutionPlan:
    container_plan_id: str = field(default_factory=lambda: f"sbxcp_{uuid4().hex[:16]}")
    execution_plan_id: str = ""; job_id: str = ""
    provider: str = SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE
    runtime: str = SandboxV2ContainerRuntime.UNAVAILABLE
    image: str = ""; fixture_id: str = ""; command: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    network_mode: str = "none"; readonly_rootfs: bool = True; user: str = "65532:65532"
    resource_limits: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 30
    status: str = SandboxV2ContainerExecutionStatus.CREATED; reason: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"container_plan_id":self.container_plan_id,"execution_plan_id":self.execution_plan_id,"job_id":self.job_id,"provider":self.provider,"runtime":self.runtime,"image":self.image,"fixture_id":self.fixture_id,"command":self.command,"env":self.env,"network_mode":self.network_mode,"readonly_rootfs":self.readonly_rootfs,"user":self.user,"resource_limits":self.resource_limits,"timeout_seconds":self.timeout_seconds,"status":self.status,"reason":self.reason,"created_at":self.created_at.isoformat(),"metadata":self.metadata}


@dataclass
class SandboxContainerExecutionResult:
    container_result_id: str = field(default_factory=lambda: f"sbxcr_{uuid4().hex[:16]}")
    container_plan_id: str = ""; execution_plan_id: str = ""; job_id: str = ""
    provider: str = SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE
    runtime: str = SandboxV2ContainerRuntime.UNAVAILABLE
    status: str = SandboxV2ContainerExecutionStatus.CREATED
    exit_code: int = -1
    started_at: datetime | None = None; finished_at: datetime | None = None
    duration_ms: int = 0; stdout_text: str = ""; stderr_text: str = ""
    stdout_artifact_id: str = ""; stderr_artifact_id: str = ""
    timeout: bool = False; canceled: bool = False; reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"container_result_id":self.container_result_id,"container_plan_id":self.container_plan_id,"execution_plan_id":self.execution_plan_id,"job_id":self.job_id,"provider":self.provider,"runtime":self.runtime,"status":self.status,"exit_code":self.exit_code,"started_at":self.started_at.isoformat() if self.started_at else None,"finished_at":self.finished_at.isoformat() if self.finished_at else None,"duration_ms":self.duration_ms,"stdout_text":self.stdout_text,"stderr_text":self.stderr_text,"stdout_artifact_id":self.stdout_artifact_id,"stderr_artifact_id":self.stderr_artifact_id,"timeout":self.timeout,"canceled":self.canceled,"reason":self.reason,"metadata":self.metadata}


# ═══════════════════════════════════════════
# Step 11 — MicroVM / Firecracker Models
# ═══════════════════════════════════════════

class SandboxMicroVMRuntime(StrEnum):
    FIRECRACKER = "firecracker"
    CLOUD_HYPERVISOR_FUTURE = "cloud_hypervisor_future"
    QEMU_FUTURE = "qemu_future"
    UNAVAILABLE = "unavailable"


class SandboxMicroVMExecutionStatus(StrEnum):
    CREATED = "created"
    REJECTED = "rejected"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    PREFLIGHT_PASSED = "preflight_passed"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELED = "canceled"


@dataclass
class SandboxMicroVMRuntimeConfig:
    runtime: str = SandboxMicroVMRuntime.UNAVAILABLE
    enabled: bool = False
    integration_enabled: bool = False
    firecracker_bin_path: str = ""
    kernel_path: str = ""
    rootfs_path: str = ""
    jailer_enabled: bool = False
    network_enabled: bool = False
    memory_mb: int = 128
    vcpu_count: int = 1
    timeout_seconds: int = 10
    allow_user_kernel: bool = False
    allow_user_rootfs: bool = False
    allow_host_mounts: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """API 返回时 mask 敏感本地路径。"""
        return {
            "runtime": self.runtime,
            "enabled": self.enabled,
            "integration_enabled": self.integration_enabled,
            "firecracker_binary_present": bool(self.firecracker_bin_path),
            "kernel_present": bool(self.kernel_path),
            "rootfs_present": bool(self.rootfs_path),
            "jailer_enabled": self.jailer_enabled,
            "network_enabled": self.network_enabled,
            "memory_mb": self.memory_mb,
            "vcpu_count": self.vcpu_count,
            "timeout_seconds": self.timeout_seconds,
            "allow_user_kernel": self.allow_user_kernel,
            "allow_user_rootfs": self.allow_user_rootfs,
            "allow_host_mounts": self.allow_host_mounts,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class SandboxMicroVMExecutionPlan:
    microvm_plan_id: str = field(default_factory=lambda: f"sbxmv_{uuid4().hex[:16]}")
    execution_plan_id: str = ""
    job_id: str = ""
    organization_id: str = ""
    workspace_id: str = ""
    runtime: str = SandboxMicroVMRuntime.UNAVAILABLE
    fixture_id: str = ""
    kernel_ref: str = ""
    rootfs_ref: str = ""
    image_ref: str = ""
    network_enabled: bool = False
    memory_mb: int = 128
    vcpu_count: int = 1
    timeout_seconds: int = 10
    status: str = SandboxMicroVMExecutionStatus.CREATED
    reason: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "microvm_plan_id": self.microvm_plan_id,
            "execution_plan_id": self.execution_plan_id,
            "job_id": self.job_id,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "runtime": self.runtime,
            "fixture_id": self.fixture_id,
            "kernel_ref": self.kernel_ref,
            "rootfs_ref": self.rootfs_ref,
            "image_ref": self.image_ref,
            "network_enabled": self.network_enabled,
            "memory_mb": self.memory_mb,
            "vcpu_count": self.vcpu_count,
            "timeout_seconds": self.timeout_seconds,
            "status": self.status,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class SandboxMicroVMExecutionResult:
    microvm_result_id: str = field(default_factory=lambda: f"sbxmvres_{uuid4().hex[:16]}")
    microvm_plan_id: str = ""
    execution_plan_id: str = ""
    job_id: str = ""
    runtime: str = SandboxMicroVMRuntime.UNAVAILABLE
    status: str = SandboxMicroVMExecutionStatus.UNAVAILABLE
    exit_code: int = -1
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int = 0
    stdout_text: str = ""
    stderr_text: str = ""
    stdout_artifact_id: str = ""
    stderr_artifact_id: str = ""
    timeout: bool = False
    canceled: bool = False
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "microvm_result_id": self.microvm_result_id,
            "microvm_plan_id": self.microvm_plan_id,
            "execution_plan_id": self.execution_plan_id,
            "job_id": self.job_id,
            "runtime": self.runtime,
            "status": self.status,
            "exit_code": self.exit_code,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": self.duration_ms,
            "stdout_text": self.stdout_text,
            "stderr_text": self.stderr_text,
            "stdout_artifact_id": self.stdout_artifact_id,
            "stderr_artifact_id": self.stderr_artifact_id,
            "timeout": self.timeout,
            "canceled": self.canceled,
            "reason": self.reason,
            "metadata": self.metadata,
        }


@dataclass
class SandboxMicroVMPreflightResult:
    platform: str = ""
    is_linux: bool = False
    is_windows: bool = False
    has_kvm: bool = False
    firecracker_binary_present: bool = False
    kernel_present: bool = False
    rootfs_present: bool = False
    execution_env_enabled: bool = False
    integration_env_enabled: bool = False
    network_disabled: bool = True
    runnable: bool = False
    reason: str = ""
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform, "is_linux": self.is_linux, "is_windows": self.is_windows,
            "has_kvm": self.has_kvm,
            "firecracker_binary_present": self.firecracker_binary_present,
            "kernel_present": self.kernel_present, "rootfs_present": self.rootfs_present,
            "execution_env_enabled": self.execution_env_enabled,
            "integration_env_enabled": self.integration_env_enabled,
            "network_disabled": self.network_disabled,
            "runnable": self.runnable, "reason": self.reason,
            "warnings": self.warnings, "blockers": self.blockers,
        }


# Trusted MicroVM fixtures — only these are allowed
TRUSTED_MICROVM_FIXTURES: dict[str, str] = {
    "hello-microvm-fixture": "print('sandbox-v2 microvm trusted fixture ok')",
}


# ═══════════════════════════════════════════
# Step 14 — Security / Tenant / Audit Enums & Models
# ═══════════════════════════════════════════

class SandboxV2PrincipalType(StrEnum):
    USER = "user"; API_KEY = "api_key"; SERVICE_ACCOUNT = "service_account"
    WORKER = "worker"; ADMIN = "admin"; SYSTEM = "system"; ANONYMOUS = "anonymous"


class SandboxV2Role(StrEnum):
    OWNER = "owner"; ADMIN = "admin"; DEVELOPER = "developer"
    OPERATOR = "operator"; AUDITOR = "auditor"; VIEWER = "viewer"
    WORKER = "worker"; SERVICE = "service"; UNKNOWN = "unknown"


class SandboxV2ResourceType(StrEnum):
    JOB = "job"; QUEUE_ITEM = "queue_item"
    EXECUTION_RECORD = "execution_record"
    ARTIFACT = "artifact"; ARTIFACT_MANIFEST = "artifact_manifest"
    PACKAGE_REQUEST = "package_request"; PACKAGE_QUARANTINE = "package_quarantine"
    NETWORK_EGRESS_REQUEST = "network_egress_request"
    NETWORK_AUDIT_RECORD = "network_audit_record"
    EXECUTION_PLAN = "execution_plan"
    CONTAINER_PLAN = "container_plan"; MICROVM_PLAN = "microvm_plan"
    KILL_REQUEST = "kill_request"; KILL_RECORD = "kill_record"
    ACTIVE_HANDLE = "active_handle"
    BACKEND_READINESS = "backend_readiness"; RUNTIME_ADMIN = "runtime_admin"
    AUDIT_EVENT = "audit_event"; EVIDENCE_BUNDLE = "evidence_bundle"
    IAM_PROVIDER_CONFIG = "iam_provider_config"
    IAM_EXTERNAL_IDENTITY = "iam_external_identity"
    IAM_ROLE_MAPPING = "iam_role_mapping"
    IAM_MAPPING_DECISION = "iam_mapping_decision"
    IAM_SSO_SIMULATION = "iam_sso_simulation"


class SandboxV2PermissionAction(StrEnum):
    CREATE = "create"; READ = "read"; LIST = "list"
    UPDATE = "update"; DELETE = "delete"; EXECUTE = "execute"
    CANCEL = "cancel"; KILL = "kill"; REVIEW = "review"
    APPROVE = "approve"; REJECT = "reject"; EXPORT = "export"
    PREFLIGHT = "preflight"; ADMINISTER = "administer"


class SandboxV2AccessDecisionAction(StrEnum):
    ALLOW = "allow"; DENY = "deny"
    REQUIRE_REVIEW = "require_review"; AUDIT_ONLY = "audit_only"


class SandboxV2AuditEventType(StrEnum):
    ACCESS_ALLOWED = "access_allowed"; ACCESS_DENIED = "access_denied"
    CROSS_TENANT_DENIED = "cross_tenant_denied"
    RESOURCE_CREATED = "resource_created"; RESOURCE_UPDATED = "resource_updated"
    RESOURCE_DELETED = "resource_deleted"
    JOB_SUBMITTED = "job_submitted"; JOB_CANCELED = "job_canceled"
    ARTIFACT_ACCESSED = "artifact_accessed"; PACKAGE_REVIEWED = "package_reviewed"
    NETWORK_PREFLIGHT = "network_preflight"; KILL_REQUESTED = "kill_requested"
    PROVIDER_ACTION = "provider_action"; READINESS_CHECKED = "readiness_checked"
    EVIDENCE_BUNDLE_CREATED = "evidence_bundle_created"
    POLICY_ERROR = "policy_error"; SUSPICIOUS_INPUT = "suspicious_input"
    IAM_PROVIDER_CONFIG_CREATED = "iam_provider_config_created"
    IAM_PROVIDER_CONFIG_UPDATED = "iam_provider_config_updated"
    IAM_ROLE_MAPPING_CREATED = "iam_role_mapping_created"
    IAM_EXTERNAL_IDENTITY_LINKED = "iam_external_identity_linked"
    IAM_MAPPING_DECISION_MADE = "iam_mapping_decision_made"
    IAM_CLAIM_MAPPING_DENIED = "iam_claim_mapping_denied"
    IAM_SSO_SIMULATION_RUN = "iam_sso_simulation_run"
    IAM_CROSS_TENANT_DENIED = "iam_cross_tenant_denied"
    IAM_UNVERIFIED_EMAIL_DENIED = "iam_unverified_email_denied"
    IAM_UNAUTHORIZED_DOMAIN_DENIED = "iam_unauthorized_domain_denied"


class SandboxV2AuditSeverity(StrEnum):
    INFO = "info"; WARNING = "warning"; HIGH = "high"; CRITICAL = "critical"


@dataclass
class SandboxV2SecurityContext:
    principal_id: str = ""
    principal_type: str = SandboxV2PrincipalType.ANONYMOUS
    roles: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    organization_id: str = ""
    workspace_id: str = ""
    request_id: str = field(default_factory=lambda: f"req_{uuid4().hex[:16]}")
    source_ip: str = ""
    user_agent: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id, "principal_type": self.principal_type,
            "roles": self.roles, "scopes": self.scopes,
            "organization_id": self.organization_id, "workspace_id": self.workspace_id,
            "request_id": self.request_id,
        }


@dataclass
class SandboxV2ResourceRef:
    resource_type: str = ""
    resource_id: str = ""
    organization_id: str = ""
    workspace_id: str = ""
    owner_principal_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SandboxV2AccessRequest:
    access_request_id: str = field(default_factory=lambda: f"sbxacc_{uuid4().hex[:16]}")
    security_context: dict[str, Any] = field(default_factory=dict)
    resource_type: str = ""
    resource_id: str = ""
    action: str = ""
    organization_id: str = ""
    workspace_id: str = ""
    reason: str = ""
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SandboxV2AccessDecision:
    access_decision_id: str = field(default_factory=lambda: f"sbxad_{uuid4().hex[:16]}")
    allowed: bool = False
    action: str = SandboxV2AccessDecisionAction.DENY
    reason: str = "Default deny."
    risk_level: str = SandboxV2RiskLevel.MEDIUM
    principal_id: str = ""
    principal_type: str = ""
    resource_type: str = ""
    resource_id: str = ""
    permission_action: str = ""
    organization_match: bool = False
    workspace_match: bool = False
    role_allowed: bool = False
    scope_allowed: bool = False
    cross_tenant: bool = False
    fail_closed: bool = True
    matched_rules: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed, "action": self.action, "reason": self.reason,
            "risk_level": self.risk_level, "principal_id": self.principal_id,
            "principal_type": self.principal_type, "resource_type": self.resource_type,
            "resource_id": self.resource_id, "permission_action": self.permission_action,
            "organization_match": self.organization_match,
            "workspace_match": self.workspace_match, "role_allowed": self.role_allowed,
            "scope_allowed": self.scope_allowed, "cross_tenant": self.cross_tenant,
            "fail_closed": self.fail_closed, "matched_rules": self.matched_rules,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class SandboxV2AuditEvent:
    audit_event_id: str = field(default_factory=lambda: f"sbxaud_{uuid4().hex[:16]}")
    event_type: str = ""
    severity: str = SandboxV2AuditSeverity.INFO
    principal_id: str = ""
    principal_type: str = ""
    organization_id: str = ""
    workspace_id: str = ""
    resource_type: str = ""
    resource_id: str = ""
    action: str = ""
    decision: str = ""
    reason: str = ""
    request_id: str = ""
    previous_hash: str = ""
    event_hash: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_event_id": self.audit_event_id, "event_type": self.event_type,
            "severity": self.severity, "principal_id": self.principal_id,
            "principal_type": self.principal_type,
            "organization_id": self.organization_id, "workspace_id": self.workspace_id,
            "resource_type": self.resource_type, "resource_id": self.resource_id,
            "action": self.action, "decision": self.decision, "reason": self.reason,
            "request_id": self.request_id,
            "previous_hash": self.previous_hash, "event_hash": self.event_hash,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class SandboxV2EvidenceBundle:
    evidence_bundle_id: str = field(default_factory=lambda: f"sbxev_{uuid4().hex[:16]}")
    organization_id: str = ""
    workspace_id: str = ""
    created_by: str = ""
    title: str = ""
    description: str = ""
    resource_refs: list[dict[str, str]] = field(default_factory=list)
    audit_event_ids: list[str] = field(default_factory=list)
    job_ids: list[str] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    package_request_ids: list[str] = field(default_factory=list)
    network_request_ids: list[str] = field(default_factory=list)
    kill_request_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    bundle_hash: str = ""
    redacted: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_bundle_id": self.evidence_bundle_id,
            "organization_id": self.organization_id, "workspace_id": self.workspace_id,
            "created_by": self.created_by, "title": self.title,
            "description": self.description, "resource_refs": self.resource_refs,
            "audit_event_ids": self.audit_event_ids,
            "job_ids": self.job_ids, "artifact_ids": self.artifact_ids,
            "package_request_ids": self.package_request_ids,
            "network_request_ids": self.network_request_ids,
            "kill_request_ids": self.kill_request_ids,
            "created_at": self.created_at.isoformat(),
            "bundle_hash": self.bundle_hash, "redacted": self.redacted,
        }


# ═══════════════════════════════════════════
# Step 7 — Kill Switch Enums & Models
# ═══════════════════════════════════════════

class SandboxV2KillRequestStatus(StrEnum):
    REQUESTED="requested"; POLICY_CHECKED="policy_checked"; REJECTED="rejected"
    CANCEL_REQUESTED="cancel_requested"; PROVIDER_CANCEL_ATTEMPTED="provider_cancel_attempted"
    CANCELED="canceled"; FAILED="failed"
    NO_ACTIVE_EXECUTION="no_active_execution"; UNSUPPORTED="unsupported"

class SandboxV2KillTargetType(StrEnum):
    JOB="job"; QUEUE_ITEM="queue_item"; EXECUTION_PLAN="execution_plan"
    CONTAINER_PLAN="container_plan"; CONTAINER="container"
    MICROVM_PLAN="microvm_plan"; MICROVM="microvm"
    TRUSTED_FIXTURE="trusted_fixture"; SIMULATION="simulation"; UNKNOWN="unknown"

class SandboxV2KillAction(StrEnum):
    REJECT="reject"; MARK_CANCELED="mark_canceled"; CANCEL_QUEUE_ITEM="cancel_queue_item"
    REQUEST_WORKER_STOP="request_worker_stop"; PROVIDER_CANCEL="provider_cancel"
    CONTAINER_KILL_FUTURE="container_kill_future"; NO_ACTIVE_EXECUTION="no_active_execution"

class SandboxV2ActiveExecutionStatus(StrEnum):
    ACTIVE="active"; CANCEL_REQUESTED="cancel_requested"; CANCELED="canceled"
    COMPLETED="completed"; FAILED="failed"; TIMEOUT="timeout"; EXPIRED="expired"

@dataclass
class SandboxKillRequest:
    kill_request_id:str=field(default_factory=lambda:f"sbxkill_{uuid4().hex[:16]}")
    job_id:str=""; execution_plan_id:str=""; container_plan_id:str=""
    execution_record_id:str=""; queue_id:str=""
    organization_id:str=""; workspace_id:str=""; requested_by:str=""
    reason:str=""; scope:str="job"; target_type:str=SandboxV2KillTargetType.JOB
    target_id:str=""; force:bool=False
    requested_at:datetime=field(default_factory=lambda:datetime.now(timezone.utc))
    status:str=SandboxV2KillRequestStatus.REQUESTED
    policy_decision_id:str=""; metadata:dict[str,Any]=field(default_factory=dict)
    def to_dict(self)->dict[str,Any]:
        return {"kill_request_id":self.kill_request_id,"job_id":self.job_id,"execution_plan_id":self.execution_plan_id,"container_plan_id":self.container_plan_id,"execution_record_id":self.execution_record_id,"queue_id":self.queue_id,"organization_id":self.organization_id,"workspace_id":self.workspace_id,"requested_by":self.requested_by,"reason":self.reason,"scope":self.scope,"target_type":self.target_type,"target_id":self.target_id,"force":self.force,"requested_at":self.requested_at.isoformat(),"status":self.status,"policy_decision_id":self.policy_decision_id,"metadata":self.metadata}

@dataclass
class SandboxKillDecision:
    allowed:bool=False; action:str=SandboxV2KillAction.REJECT
    reason:str=""; risk_level:str=SandboxV2RiskLevel.MEDIUM
    target_owned_by_sandbox:bool=False; provider_cancel_supported:bool=False
    process_kill_allowed:bool=False; container_kill_allowed:bool=False
    queue_cancel_allowed:bool=False; job_state_cancel_allowed:bool=True
    fail_closed:bool=True; matched_rules:list[str]=field(default_factory=list)
    def to_dict(self)->dict[str,Any]:
        return {"allowed":self.allowed,"action":self.action,"reason":self.reason,"risk_level":self.risk_level,"target_owned_by_sandbox":self.target_owned_by_sandbox,"provider_cancel_supported":self.provider_cancel_supported,"process_kill_allowed":self.process_kill_allowed,"container_kill_allowed":self.container_kill_allowed,"queue_cancel_allowed":self.queue_cancel_allowed,"job_state_cancel_allowed":self.job_state_cancel_allowed,"fail_closed":self.fail_closed,"matched_rules":self.matched_rules}

@dataclass
class SandboxKillRecord:
    kill_record_id:str=field(default_factory=lambda:f"sbxkrec_{uuid4().hex[:16]}")
    kill_request_id:str=""; job_id:str=""; execution_plan_id:str=""
    container_plan_id:str=""; provider:str=""
    target_type:str=SandboxV2KillTargetType.UNKNOWN; target_id:str=""
    action_taken:str=SandboxV2KillAction.REJECT
    status_before:str=""; status_after:str=""
    provider_result:str=""; error_code:str=""; error_message:str=""
    created_at:datetime=field(default_factory=lambda:datetime.now(timezone.utc))
    metadata:dict[str,Any]=field(default_factory=dict)
    def to_dict(self)->dict[str,Any]:
        return {"kill_record_id":self.kill_record_id,"kill_request_id":self.kill_request_id,"job_id":self.job_id,"execution_plan_id":self.execution_plan_id,"container_plan_id":self.container_plan_id,"provider":self.provider,"target_type":self.target_type,"target_id":self.target_id,"action_taken":self.action_taken,"status_before":self.status_before,"status_after":self.status_after,"provider_result":self.provider_result,"error_code":self.error_code,"error_message":self.error_message,"created_at":self.created_at.isoformat(),"metadata":self.metadata}

@dataclass
class SandboxActiveExecutionHandle:
    handle_id:str=field(default_factory=lambda:f"sbxhandle_{uuid4().hex[:16]}")
    job_id:str=""; execution_plan_id:str=""; container_plan_id:str=""
    execution_record_id:str=""; provider:str=""
    target_type:str=SandboxV2KillTargetType.UNKNOWN; target_id:str=""
    status:str=SandboxV2ActiveExecutionStatus.ACTIVE
    started_at:datetime=field(default_factory=lambda:datetime.now(timezone.utc))
    last_seen_at:datetime=field(default_factory=lambda:datetime.now(timezone.utc))
    timeout_at:datetime|None=None
    cancel_requested:bool=False; cancel_reason:str=""
    metadata:dict[str,Any]=field(default_factory=dict)
    def to_dict(self)->dict[str,Any]:
        return {"handle_id":self.handle_id,"job_id":self.job_id,"execution_plan_id":self.execution_plan_id,"container_plan_id":self.container_plan_id,"execution_record_id":self.execution_record_id,"provider":self.provider,"target_type":self.target_type,"target_id":self.target_id,"status":self.status,"started_at":self.started_at.isoformat(),"last_seen_at":self.last_seen_at.isoformat(),"timeout_at":self.timeout_at.isoformat() if self.timeout_at else None,"cancel_requested":self.cancel_requested,"cancel_reason":self.cancel_reason,"metadata":self.metadata}


# ═══════════════════════════════════════════
# Step 15 — Monitoring / Metrics / Alerts / Health Check
# ═══════════════════════════════════════════

class SandboxV2MetricName(StrEnum):
    JOBS_CREATED = "jobs_created_total"; JOBS_COMPLETED = "jobs_completed_total"
    JOBS_FAILED = "jobs_failed_total"; JOBS_CANCELED = "jobs_canceled_total"
    QUEUE_DEPTH = "queue_depth"; QUEUE_DEAD_LETTER = "queue_dead_letter_total"
    WORKER_HEARTBEAT_AGE = "worker_heartbeat_age_seconds"; WORKER_FAILURES = "worker_failures_total"
    ARTIFACT_CREATED = "artifact_created_total"; ARTIFACT_REJECTED = "artifact_rejected_total"
    PACKAGE_REJECTED = "package_rejected_total"; PACKAGE_QUARANTINED = "package_quarantined_total"
    NETWORK_PREFLIGHT = "network_preflight_total"; NETWORK_DENIED = "network_denied_total"
    METADATA_BLOCKED = "metadata_service_blocked_total"
    KILL_REQUESTS = "kill_requests_total"; KILL_REJECTED = "kill_rejected_total"
    ACCESS_DENIED = "access_denied_total"; CROSS_TENANT_DENIED = "cross_tenant_denied_total"
    AUDIT_CHAIN_FAIL = "audit_chain_verify_failures_total"
    RED_TEAM_PASSED = "red_team_tests_passed"; RED_TEAM_FAILED = "red_team_tests_failed"
    BACKEND_BLOCKERS = "backend_blockers_total"
    MICROVM_UNAVAILABLE = "microvm_unavailable_total"
    CONTAINER_UNAVAILABLE = "container_unavailable_total"
    BENCHMARK_RESULTS = "benchmark_results_total"
    BENCHMARK_FAILURES = "benchmark_failures_total"
    CAPACITY_JOBS_PER_MINUTE = "capacity_jobs_per_minute"


class SandboxV2MetricType(StrEnum):
    COUNTER = "counter"; GAUGE = "gauge"; HISTOGRAM = "histogram"; SUMMARY = "summary"


class SandboxV2AlertSeverityStep15(StrEnum):
    INFO = "info"; WARNING = "warning"; HIGH = "high"; CRITICAL = "critical"


class SandboxV2AlertStatusStep15(StrEnum):
    OPEN = "open"; ACKNOWLEDGED = "acknowledged"; RESOLVED = "resolved"; MUTED = "muted"


class SandboxV2AlertRuleType(StrEnum):
    THRESHOLD = "threshold"; ABSENCE = "absence"; RATE = "rate"
    READINESS_BLOCKER = "readiness_blocker"; AUDIT_SIGNAL = "audit_signal"; SECURITY_EVENT = "security_event"


@dataclass
class SandboxV2MetricSample:
    metric_id: str = field(default_factory=lambda: f"sbxmet_{uuid4().hex[:16]}")
    name: str = ""
    metric_type: str = SandboxV2MetricType.GAUGE
    value: float = 0.0
    labels: dict[str, str] = field(default_factory=dict)
    organization_id: str = ""
    workspace_id: str = ""
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return {"metric_id": self.metric_id, "name": self.name, "metric_type": self.metric_type,
                "value": self.value, "labels": self.labels, "organization_id": self.organization_id,
                "workspace_id": self.workspace_id, "collected_at": self.collected_at.isoformat()}


@dataclass
class SandboxV2MetricsSnapshot:
    snapshot_id: str = field(default_factory=lambda: f"sbxsnap_{uuid4().hex[:16]}")
    organization_id: str = ""; workspace_id: str = ""
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    counters: dict[str, float] = field(default_factory=dict)
    gauges: dict[str, float] = field(default_factory=dict)
    health: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return {"snapshot_id": self.snapshot_id, "organization_id": self.organization_id,
                "workspace_id": self.workspace_id, "generated_at": self.generated_at.isoformat(),
                "counters": self.counters, "gauges": self.gauges, "health": self.health,
                "warnings": self.warnings, "blockers": self.blockers}


@dataclass
class SandboxV2AlertRule:
    alert_rule_id: str = field(default_factory=lambda: f"sbxrule_{uuid4().hex[:16]}")
    name: str = ""; description: str = ""
    rule_type: str = SandboxV2AlertRuleType.THRESHOLD
    metric_name: str = ""; threshold: float = 0.0
    comparison: str = "gt"  # gt, lt, gte, lte, eq
    severity: str = SandboxV2AlertSeverityStep15.WARNING
    enabled: bool = True
    organization_id: str = ""; workspace_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return {"alert_rule_id": self.alert_rule_id, "name": self.name, "description": self.description,
                "rule_type": self.rule_type, "metric_name": self.metric_name, "threshold": self.threshold,
                "comparison": self.comparison, "severity": self.severity, "enabled": self.enabled,
                "organization_id": self.organization_id, "workspace_id": self.workspace_id}


@dataclass
class SandboxV2Alert:
    alert_id: str = field(default_factory=lambda: f"sbxalert_{uuid4().hex[:16]}")
    alert_rule_id: str = ""; name: str = ""
    severity: str = SandboxV2AlertSeverityStep15.WARNING
    status: str = SandboxV2AlertStatusStep15.OPEN
    organization_id: str = ""; workspace_id: str = ""
    resource_type: str = ""; resource_id: str = ""
    reason: str = ""; observed_value: float = 0.0; threshold: float = 0.0
    first_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None; acknowledged_by: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return {"alert_id": self.alert_id, "alert_rule_id": self.alert_rule_id, "name": self.name,
                "severity": self.severity, "status": self.status, "organization_id": self.organization_id,
                "workspace_id": self.workspace_id, "resource_type": self.resource_type,
                "resource_id": self.resource_id, "reason": self.reason,
                "observed_value": self.observed_value, "threshold": self.threshold,
                "first_seen_at": self.first_seen_at.isoformat(),
                "last_seen_at": self.last_seen_at.isoformat(),
                "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
                "acknowledged_by": self.acknowledged_by}


@dataclass
class SandboxV2HealthCheckResult:
    health_check_id: str = field(default_factory=lambda: f"sbxhc_{uuid4().hex[:16]}")
    component: str = ""; status: str = "healthy"
    ready: bool = True; reason: str = ""; latency_ms: int = 0
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return {"health_check_id": self.health_check_id, "component": self.component,
                "status": self.status, "ready": self.ready, "reason": self.reason,
                "latency_ms": self.latency_ms, "checked_at": self.checked_at.isoformat(),
                "warnings": self.warnings, "blockers": self.blockers}


# ═══════════════════════════════════════════
# Step 16 — Performance / Capacity Benchmarks
# ═══════════════════════════════════════════

class SandboxV2PerformanceProfile(StrEnum):
    SMOKE = "smoke"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    CUSTOM = "custom"


class SandboxV2BenchmarkStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELED = "canceled"


class SandboxV2BenchmarkTarget(StrEnum):
    JOBS = "jobs"
    QUEUE = "queue"
    WORKER = "worker"
    ARTIFACTS = "artifacts"
    PACKAGES = "packages"
    NETWORK = "network"
    KILL_SWITCH = "kill_switch"
    SECURITY_AUDIT = "security_audit"
    METRICS = "metrics"
    ALERTS = "alerts"
    END_TO_END = "end_to_end"


@dataclass
class SandboxV2BenchmarkConfig:
    benchmark_id: str = field(default_factory=lambda: f"sbxbench_{uuid4().hex[:16]}")
    profile: str = SandboxV2PerformanceProfile.SMALL
    targets: list[str] = field(default_factory=lambda: [SandboxV2BenchmarkTarget.JOBS])
    max_jobs: int = 100
    max_queue_items: int = 100
    max_artifacts: int = 50
    max_concurrency: int = 4
    timeout_seconds: int = 60
    cleanup_after_run: bool = True
    organization_id: str = ""
    workspace_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "profile": self.profile,
            "targets": self.targets,
            "max_jobs": self.max_jobs,
            "max_queue_items": self.max_queue_items,
            "max_artifacts": self.max_artifacts,
            "max_concurrency": self.max_concurrency,
            "timeout_seconds": self.timeout_seconds,
            "cleanup_after_run": self.cleanup_after_run,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2BenchmarkConfig":
        return cls(
            benchmark_id=d.get("benchmark_id", ""),
            profile=d.get("profile", SandboxV2PerformanceProfile.SMALL),
            targets=list(d.get("targets", []) or []),
            max_jobs=int(d.get("max_jobs", 100) or 100),
            max_queue_items=int(d.get("max_queue_items", 100) or 100),
            max_artifacts=int(d.get("max_artifacts", 50) or 50),
            max_concurrency=int(d.get("max_concurrency", 4) or 4),
            timeout_seconds=int(d.get("timeout_seconds", 60) or 60),
            cleanup_after_run=bool(d.get("cleanup_after_run", True)),
            organization_id=d.get("organization_id", ""),
            workspace_id=d.get("workspace_id", ""),
            created_at=_parse_model_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}) or {}),
        )


@dataclass
class SandboxV2BenchmarkResult:
    benchmark_result_id: str = field(default_factory=lambda: f"sbxbres_{uuid4().hex[:16]}")
    benchmark_id: str = ""
    target: str = SandboxV2BenchmarkTarget.JOBS
    status: str = SandboxV2BenchmarkStatus.CREATED
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    duration_ms: int = 0
    total_operations: int = 0
    success_count: int = 0
    failure_count: int = 0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    ops_per_second: float = 0.0
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_result_id": self.benchmark_result_id,
            "benchmark_id": self.benchmark_id,
            "target": self.target,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": self.duration_ms,
            "total_operations": self.total_operations,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "ops_per_second": self.ops_per_second,
            "warnings": self.warnings,
            "blockers": self.blockers,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2BenchmarkResult":
        return cls(
            benchmark_result_id=d.get("benchmark_result_id", ""),
            benchmark_id=d.get("benchmark_id", ""),
            target=d.get("target", SandboxV2BenchmarkTarget.JOBS),
            status=d.get("status", SandboxV2BenchmarkStatus.CREATED),
            started_at=_parse_model_dt(d.get("started_at")),
            finished_at=_parse_model_dt(d.get("finished_at")) if d.get("finished_at") else None,
            duration_ms=int(d.get("duration_ms", 0) or 0),
            total_operations=int(d.get("total_operations", 0) or 0),
            success_count=int(d.get("success_count", 0) or 0),
            failure_count=int(d.get("failure_count", 0) or 0),
            p50_ms=float(d.get("p50_ms", 0.0) or 0.0),
            p95_ms=float(d.get("p95_ms", 0.0) or 0.0),
            p99_ms=float(d.get("p99_ms", 0.0) or 0.0),
            ops_per_second=float(d.get("ops_per_second", 0.0) or 0.0),
            warnings=list(d.get("warnings", []) or []),
            blockers=list(d.get("blockers", []) or []),
            metadata=dict(d.get("metadata", {}) or {}),
        )


@dataclass
class SandboxV2CapacityEstimate:
    capacity_id: str = field(default_factory=lambda: f"sbxcap_{uuid4().hex[:16]}")
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    profile: str = SandboxV2PerformanceProfile.SMALL
    estimated_jobs_per_minute: float = 0.0
    estimated_queue_items_per_minute: float = 0.0
    estimated_artifact_metadata_per_minute: float = 0.0
    estimated_network_preflight_per_minute: float = 0.0
    sqlite_recommended_limit: str = "local/single-node smoke or small benchmark only"
    postgres_recommended_threshold: str = "Use PostgreSQL before sustained multi-worker benchmarks"
    redis_recommended_threshold: str = "Use Redis before distributed queue workers"
    minio_recommended_threshold: str = "Use MinIO/S3 before large artifact metadata volumes"
    bottlenecks: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capacity_id": self.capacity_id,
            "generated_at": self.generated_at.isoformat(),
            "profile": self.profile,
            "estimated_jobs_per_minute": self.estimated_jobs_per_minute,
            "estimated_queue_items_per_minute": self.estimated_queue_items_per_minute,
            "estimated_artifact_metadata_per_minute": self.estimated_artifact_metadata_per_minute,
            "estimated_network_preflight_per_minute": self.estimated_network_preflight_per_minute,
            "sqlite_recommended_limit": self.sqlite_recommended_limit,
            "postgres_recommended_threshold": self.postgres_recommended_threshold,
            "redis_recommended_threshold": self.redis_recommended_threshold,
            "minio_recommended_threshold": self.minio_recommended_threshold,
            "bottlenecks": self.bottlenecks,
            "recommendations": self.recommendations,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2CapacityEstimate":
        return cls(
            capacity_id=d.get("capacity_id", ""),
            generated_at=_parse_model_dt(d.get("generated_at")),
            profile=d.get("profile", SandboxV2PerformanceProfile.SMALL),
            estimated_jobs_per_minute=float(d.get("estimated_jobs_per_minute", 0.0) or 0.0),
            estimated_queue_items_per_minute=float(d.get("estimated_queue_items_per_minute", 0.0) or 0.0),
            estimated_artifact_metadata_per_minute=float(d.get("estimated_artifact_metadata_per_minute", 0.0) or 0.0),
            estimated_network_preflight_per_minute=float(d.get("estimated_network_preflight_per_minute", 0.0) or 0.0),
            sqlite_recommended_limit=d.get("sqlite_recommended_limit", ""),
            postgres_recommended_threshold=d.get("postgres_recommended_threshold", ""),
            redis_recommended_threshold=d.get("redis_recommended_threshold", ""),
            minio_recommended_threshold=d.get("minio_recommended_threshold", ""),
            bottlenecks=list(d.get("bottlenecks", []) or []),
            recommendations=list(d.get("recommendations", []) or []),
            metadata=dict(d.get("metadata", {}) or {}),
        )




# ═══════════════════════════════════════════
# Step 17 — IAM / SSO Integration Models
# ═══════════════════════════════════════════

class SandboxV2IAMProviderType(StrEnum):
    DISABLED = "disabled"; OIDC = "oidc"; SAML = "saml"; MOCK = "mock"
    FUTURE_AZURE_AD = "future_azure_ad"; FUTURE_OKTA = "future_okta"
    FUTURE_AUTH0 = "future_auth0"; FUTURE_KEYCLOAK = "future_keycloak"


class SandboxV2SSOProtocol(StrEnum):
    OIDC = "oidc"; SAML = "saml"; MOCK = "mock"; DISABLED = "disabled"


class SandboxV2IdentityLinkStatus(StrEnum):
    ACTIVE = "active"; DISABLED = "disabled"; REVOKED = "revoked"; PENDING_REVIEW = "pending_review"


class SandboxV2IAMMappingStatus(StrEnum):
    MAPPED = "mapped"; REJECTED = "rejected"; REQUIRES_REVIEW = "requires_review"; FAILED = "failed"


class SandboxV2SSOLoginStatus(StrEnum):
    SIMULATED = "simulated"; MAPPED = "mapped"; REJECTED = "rejected"
    FAILED = "failed"; DISABLED = "disabled"


@dataclass
class SandboxV2IAMProviderConfig:
    provider_config_id: str = field(default_factory=lambda: f"sbxiamcfg_{uuid4().hex[:16]}")
    provider_type: str = SandboxV2IAMProviderType.DISABLED
    protocol: str = SandboxV2SSOProtocol.DISABLED
    enabled: bool = False
    issuer: str = ""
    client_id: str = ""
    client_secret_ref: str = ""          # NEVER stores plaintext secret
    jwks_uri: str = ""
    discovery_enabled: bool = False
    saml_entity_id: str = ""
    saml_metadata_ref: str = ""
    jit_provisioning: bool = False
    default_role: str = "viewer"
    allowed_domains: list[str] = field(default_factory=list)
    require_verified_email: bool = True
    external_group_mapping_enabled: bool = False
    organization_id: str = ""
    workspace_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_config_id": self.provider_config_id,
            "provider_type": self.provider_type,
            "protocol": self.protocol,
            "enabled": self.enabled,
            "issuer": self.issuer,
            "client_id": self._mask_id(self.client_id),
            "client_secret_ref": self.client_secret_ref,
            "jwks_uri": self.jwks_uri,
            "discovery_enabled": self.discovery_enabled,
            "saml_entity_id": self.saml_entity_id,
            "saml_metadata_ref": self.saml_metadata_ref,
            "jit_provisioning": self.jit_provisioning,
            "default_role": self.default_role,
            "allowed_domains": self.allowed_domains,
            "require_verified_email": self.require_verified_email,
            "external_group_mapping_enabled": self.external_group_mapping_enabled,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "created_at": self.created_at.isoformat(),
            "metadata": self._redact_metadata(self.metadata),
        }

    @staticmethod
    def _mask_id(value: str) -> str:
        if not value:
            return ""
        if len(value) <= 8:
            return value[:2] + "****"
        return value[:4] + "****" + value[-4:]

    @staticmethod
    def _redact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        sensitive = {"client_secret", "secret", "token", "key", "password", "credential"}
        return {k: ("***REDACTED***" if k.lower() in sensitive else v) for k, v in (metadata or {}).items()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2IAMProviderConfig":
        return cls(
            provider_config_id=d.get("provider_config_id", ""),
            provider_type=d.get("provider_type", SandboxV2IAMProviderType.DISABLED),
            protocol=d.get("protocol", SandboxV2SSOProtocol.DISABLED),
            enabled=bool(d.get("enabled", False)),
            issuer=d.get("issuer", ""),
            client_id=d.get("client_id", ""),
            client_secret_ref=d.get("client_secret_ref", ""),
            jwks_uri=d.get("jwks_uri", ""),
            discovery_enabled=bool(d.get("discovery_enabled", False)),
            saml_entity_id=d.get("saml_entity_id", ""),
            saml_metadata_ref=d.get("saml_metadata_ref", ""),
            jit_provisioning=bool(d.get("jit_provisioning", False)),
            default_role=d.get("default_role", "viewer"),
            allowed_domains=list(d.get("allowed_domains", []) or []),
            require_verified_email=bool(d.get("require_verified_email", True)),
            external_group_mapping_enabled=bool(d.get("external_group_mapping_enabled", False)),
            organization_id=d.get("organization_id", ""),
            workspace_id=d.get("workspace_id", ""),
            created_at=_parse_model_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}) or {}),
        )


@dataclass
class SandboxV2ExternalIdentity:
    external_identity_id: str = field(default_factory=lambda: f"sbxeid_{uuid4().hex[:16]}")
    provider_config_id: str = ""
    provider_type: str = SandboxV2IAMProviderType.DISABLED
    external_subject: str = ""
    external_email: str = ""
    email_verified: bool = False
    external_groups: list[str] = field(default_factory=list)
    display_name: str = ""
    organization_id: str = ""
    workspace_id: str = ""
    linked_principal_id: str = ""
    status: str = SandboxV2IdentityLinkStatus.PENDING_REVIEW
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "external_identity_id": self.external_identity_id,
            "provider_config_id": self.provider_config_id,
            "provider_type": self.provider_type,
            "external_subject": self.external_subject,
            "external_email": self.external_email,
            "email_verified": self.email_verified,
            "external_groups": self.external_groups,
            "display_name": self.display_name,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "linked_principal_id": self.linked_principal_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2ExternalIdentity":
        return cls(
            external_identity_id=d.get("external_identity_id", ""),
            provider_config_id=d.get("provider_config_id", ""),
            provider_type=d.get("provider_type", SandboxV2IAMProviderType.DISABLED),
            external_subject=d.get("external_subject", ""),
            external_email=d.get("external_email", ""),
            email_verified=bool(d.get("email_verified", False)),
            external_groups=list(d.get("external_groups", []) or []),
            display_name=d.get("display_name", ""),
            organization_id=d.get("organization_id", ""),
            workspace_id=d.get("workspace_id", ""),
            linked_principal_id=d.get("linked_principal_id", ""),
            status=d.get("status", SandboxV2IdentityLinkStatus.PENDING_REVIEW),
            created_at=_parse_model_dt(d.get("created_at")),
            last_seen_at=_parse_model_dt(d.get("last_seen_at")),
            metadata=dict(d.get("metadata", {}) or {}),
        )


@dataclass
class SandboxV2IAMClaimSet:
    issuer: str = ""
    subject: str = ""
    email: str = ""
    email_verified: bool = False
    name: str = ""
    groups: list[str] = field(default_factory=list)
    tenant: str = ""
    audience: str = ""
    issued_at: int = 0
    expires_at: int = 0
    raw_claims_redacted: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "issuer": self.issuer, "subject": self.subject,
            "email": self.email, "email_verified": self.email_verified,
            "name": self.name, "groups": self.groups,
            "tenant": self.tenant, "audience": self.audience,
            "issued_at": self.issued_at, "expires_at": self.expires_at,
            "raw_claims_redacted": self.raw_claims_redacted,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2IAMClaimSet":
        return cls(
            issuer=d.get("issuer", ""), subject=d.get("subject", ""),
            email=d.get("email", ""), email_verified=bool(d.get("email_verified", False)),
            name=d.get("name", ""),
            groups=list(d.get("groups", []) or []),
            tenant=d.get("tenant", ""), audience=d.get("audience", ""),
            issued_at=int(d.get("issued_at", 0) or 0),
            expires_at=int(d.get("expires_at", 0) or 0),
            raw_claims_redacted=dict(d.get("raw_claims_redacted", {}) or {}),
            metadata=dict(d.get("metadata", {}) or {}),
        )


@dataclass
class SandboxV2IAMRoleMapping:
    mapping_id: str = field(default_factory=lambda: f"sbxirm_{uuid4().hex[:16]}")
    provider_config_id: str = ""
    external_group: str = ""
    external_claim: str = ""
    sandbox_role: str = SandboxV2Role.VIEWER
    sandbox_scopes: list[str] = field(default_factory=list)
    organization_id: str = ""
    workspace_id: str = ""
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mapping_id": self.mapping_id, "provider_config_id": self.provider_config_id,
            "external_group": self.external_group, "external_claim": self.external_claim,
            "sandbox_role": self.sandbox_role, "sandbox_scopes": self.sandbox_scopes,
            "organization_id": self.organization_id, "workspace_id": self.workspace_id,
            "enabled": self.enabled, "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2IAMRoleMapping":
        return cls(
            mapping_id=d.get("mapping_id", ""), provider_config_id=d.get("provider_config_id", ""),
            external_group=d.get("external_group", ""), external_claim=d.get("external_claim", ""),
            sandbox_role=d.get("sandbox_role", SandboxV2Role.VIEWER),
            sandbox_scopes=list(d.get("sandbox_scopes", []) or []),
            organization_id=d.get("organization_id", ""), workspace_id=d.get("workspace_id", ""),
            enabled=bool(d.get("enabled", True)),
            created_at=_parse_model_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}) or {}),
        )


@dataclass
class SandboxV2IAMMappingDecision:
    decision_id: str = field(default_factory=lambda: f"sbximd_{uuid4().hex[:16]}")
    allowed: bool = False
    status: str = SandboxV2IAMMappingStatus.REJECTED
    reason: str = "Default deny."
    principal_id: str = ""
    principal_type: str = SandboxV2PrincipalType.ANONYMOUS
    mapped_roles: list[str] = field(default_factory=list)
    mapped_scopes: list[str] = field(default_factory=list)
    organization_id: str = ""
    workspace_id: str = ""
    email_domain_allowed: bool = False
    email_verified: bool = False
    tenant_match: bool = False
    group_mapping_applied: bool = False
    jit_provisioning_required: bool = False
    fail_closed: bool = True
    matched_rules: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id, "allowed": self.allowed,
            "status": self.status, "reason": self.reason,
            "principal_id": self.principal_id, "principal_type": self.principal_type,
            "mapped_roles": self.mapped_roles, "mapped_scopes": self.mapped_scopes,
            "organization_id": self.organization_id, "workspace_id": self.workspace_id,
            "email_domain_allowed": self.email_domain_allowed,
            "email_verified": self.email_verified, "tenant_match": self.tenant_match,
            "group_mapping_applied": self.group_mapping_applied,
            "jit_provisioning_required": self.jit_provisioning_required,
            "fail_closed": self.fail_closed,
            "matched_rules": self.matched_rules,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2IAMMappingDecision":
        return cls(
            decision_id=d.get("decision_id", ""), allowed=bool(d.get("allowed", False)),
            status=d.get("status", SandboxV2IAMMappingStatus.REJECTED),
            reason=d.get("reason", "Default deny."),
            principal_id=d.get("principal_id", ""),
            principal_type=d.get("principal_type", SandboxV2PrincipalType.ANONYMOUS),
            mapped_roles=list(d.get("mapped_roles", []) or []),
            mapped_scopes=list(d.get("mapped_scopes", []) or []),
            organization_id=d.get("organization_id", ""), workspace_id=d.get("workspace_id", ""),
            email_domain_allowed=bool(d.get("email_domain_allowed", False)),
            email_verified=bool(d.get("email_verified", False)),
            tenant_match=bool(d.get("tenant_match", False)),
            group_mapping_applied=bool(d.get("group_mapping_applied", False)),
            jit_provisioning_required=bool(d.get("jit_provisioning_required", False)),
            fail_closed=bool(d.get("fail_closed", True)),
            matched_rules=list(d.get("matched_rules", []) or []),
            created_at=_parse_model_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}) or {}),
        )


@dataclass
class SandboxV2SSOSimulationResult:
    simulation_id: str = field(default_factory=lambda: f"sbxsim_{uuid4().hex[:16]}")
    provider_config_id: str = ""
    protocol: str = SandboxV2SSOProtocol.MOCK
    login_status: str = SandboxV2SSOLoginStatus.DISABLED
    claim_set: dict[str, Any] = field(default_factory=dict)
    mapping_decision: dict[str, Any] = field(default_factory=dict)
    security_context: dict[str, Any] = field(default_factory=dict)
    audit_event_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "simulation_id": self.simulation_id, "provider_config_id": self.provider_config_id,
            "protocol": self.protocol, "login_status": self.login_status,
            "claim_set": self.claim_set, "mapping_decision": self.mapping_decision,
            "security_context": self.security_context, "audit_event_id": self.audit_event_id,
            "created_at": self.created_at.isoformat(), "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2SSOSimulationResult":
        return cls(
            simulation_id=d.get("simulation_id", ""),
            provider_config_id=d.get("provider_config_id", ""),
            protocol=d.get("protocol", SandboxV2SSOProtocol.MOCK),
            login_status=d.get("login_status", SandboxV2SSOLoginStatus.DISABLED),
            claim_set=dict(d.get("claim_set", {}) or {}),
            mapping_decision=dict(d.get("mapping_decision", {}) or {}),
            security_context=dict(d.get("security_context", {}) or {}),
            audit_event_id=d.get("audit_event_id", ""),
            created_at=_parse_model_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}) or {}),
        )


# ═══════════════════════════════════════════
# Step 18 — Observability / OpenTelemetry Models
# ═══════════════════════════════════════════

class SandboxV2ObservabilityProvider(StrEnum):
    DISABLED = "disabled"; PROMETHEUS = "prometheus"; GRAFANA = "grafana"
    OPENTELEMETRY = "opentelemetry"; MOCK = "mock"
    FUTURE_DATADOG = "future_datadog"; FUTURE_SENTRY = "future_sentry"


class SandboxV2TelemetrySignalType(StrEnum):
    METRIC = "metric"; TRACE = "trace"; LOG = "log"; EVENT = "event"


class SandboxV2TelemetryExportStatus(StrEnum):
    DISABLED = "disabled"; CONFIGURED = "configured"; SKIPPED = "skipped"
    EXPORTED = "exported"; FAILED = "failed"; REJECTED = "rejected"


class SandboxV2TraceSpanStatus(StrEnum):
    OK = "ok"; ERROR = "error"; SKIPPED = "skipped"; DISABLED = "disabled"


@dataclass
class SandboxV2ObservabilityConfig:
    observability_enabled: bool = False
    prometheus_export_enabled: bool = True
    prometheus_scrape_path: str = ""
    grafana_dashboard_enabled: bool = False
    otel_enabled: bool = False
    otel_exporter: str = "disabled"
    otel_endpoint_ref: str = ""
    otel_service_name: str = "sandbox-v2"
    otel_traces_enabled: bool = False
    otel_metrics_enabled: bool = False
    otel_logs_enabled: bool = False
    include_sensitive_attributes: bool = False
    safe_mode: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "observability_enabled": self.observability_enabled,
            "prometheus_export_enabled": self.prometheus_export_enabled,
            "prometheus_scrape_path": self.prometheus_scrape_path,
            "grafana_dashboard_enabled": self.grafana_dashboard_enabled,
            "otel_enabled": self.otel_enabled,
            "otel_exporter": self.otel_exporter,
            "otel_endpoint_ref": _mask_endpoint(self.otel_endpoint_ref),
            "otel_service_name": self.otel_service_name,
            "otel_traces_enabled": self.otel_traces_enabled,
            "otel_metrics_enabled": self.otel_metrics_enabled,
            "otel_logs_enabled": self.otel_logs_enabled,
            "include_sensitive_attributes": self.include_sensitive_attributes,
            "safe_mode": self.safe_mode,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class SandboxV2TelemetryExportRecord:
    export_record_id: str = field(default_factory=lambda: f"sbxtexp_{uuid4().hex[:16]}")
    provider: str = ""
    signal_type: str = SandboxV2TelemetrySignalType.METRIC
    status: str = SandboxV2TelemetryExportStatus.DISABLED
    organization_id: str = ""
    workspace_id: str = ""
    resource_type: str = ""
    resource_id: str = ""
    exported_count: int = 0
    rejected_count: int = 0
    reason: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "export_record_id": self.export_record_id, "provider": self.provider,
            "signal_type": self.signal_type, "status": self.status,
            "organization_id": self.organization_id, "workspace_id": self.workspace_id,
            "resource_type": self.resource_type, "resource_id": self.resource_id,
            "exported_count": self.exported_count, "rejected_count": self.rejected_count,
            "reason": self.reason, "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2TelemetryExportRecord":
        return cls(
            export_record_id=d.get("export_record_id", ""),
            provider=d.get("provider", ""),
            signal_type=d.get("signal_type", SandboxV2TelemetrySignalType.METRIC),
            status=d.get("status", SandboxV2TelemetryExportStatus.DISABLED),
            organization_id=d.get("organization_id", ""),
            workspace_id=d.get("workspace_id", ""),
            resource_type=d.get("resource_type", ""),
            resource_id=d.get("resource_id", ""),
            exported_count=int(d.get("exported_count", 0) or 0),
            rejected_count=int(d.get("rejected_count", 0) or 0),
            reason=d.get("reason", ""),
            created_at=_parse_model_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}) or {}),
        )


@dataclass
class SandboxV2TraceSpan:
    span_id: str = field(default_factory=lambda: f"sbxspan_{uuid4().hex[:16]}")
    trace_id: str = ""
    parent_span_id: str = ""
    span_name: str = ""
    status: str = SandboxV2TraceSpanStatus.OK
    organization_id: str = ""
    workspace_id: str = ""
    resource_type: str = ""
    resource_id: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    duration_ms: int = 0
    attributes_redacted: dict[str, Any] = field(default_factory=dict)
    events_redacted: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id, "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id, "span_name": self.span_name,
            "status": self.status, "organization_id": self.organization_id,
            "workspace_id": self.workspace_id, "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": self.duration_ms,
            "attributes_redacted": self.attributes_redacted,
            "events_redacted": self.events_redacted,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2TraceSpan":
        return cls(
            span_id=d.get("span_id", ""), trace_id=d.get("trace_id", ""),
            parent_span_id=d.get("parent_span_id", ""),
            span_name=d.get("span_name", ""),
            status=d.get("status", SandboxV2TraceSpanStatus.OK),
            organization_id=d.get("organization_id", ""),
            workspace_id=d.get("workspace_id", ""),
            resource_type=d.get("resource_type", ""),
            resource_id=d.get("resource_id", ""),
            started_at=_parse_model_dt(d.get("started_at")),
            finished_at=_parse_model_dt(d.get("finished_at")) if d.get("finished_at") else None,
            duration_ms=int(d.get("duration_ms", 0) or 0),
            attributes_redacted=dict(d.get("attributes_redacted", {}) or {}),
            events_redacted=list(d.get("events_redacted", []) or []),
            metadata=dict(d.get("metadata", {}) or {}),
        )


@dataclass
class SandboxV2GrafanaDashboardSpec:
    dashboard_id: str = field(default_factory=lambda: f"sbxgd_{uuid4().hex[:16]}")
    title: str = ""
    version: str = "1.0"
    panels: list[dict[str, Any]] = field(default_factory=list)
    datasource: str = "${DS_PROMETHEUS}"
    tags: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dashboard_id": self.dashboard_id, "title": self.title,
            "version": self.version, "panels": self.panels,
            "datasource": self.datasource, "tags": self.tags,
            "generated_at": self.generated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2GrafanaDashboardSpec":
        return cls(
            dashboard_id=d.get("dashboard_id", ""),
            title=d.get("title", ""),
            version=d.get("version", "1.0"),
            panels=list(d.get("panels", []) or []),
            datasource=d.get("datasource", "${DS_PROMETHEUS}"),
            tags=list(d.get("tags", []) or []),
            generated_at=_parse_model_dt(d.get("generated_at")),
            metadata=dict(d.get("metadata", {}) or {}),
        )


def _mask_endpoint(url: str) -> str:
    if not url:
        return ""
    if len(url) <= 12:
        return url[:3] + "****"
    return url[:8] + "****" + url[-4:]




# ═══════════════════════════════════════════
# Step 19 — Load Testing / SLO Models
# ═══════════════════════════════════════════

class SandboxV2LoadTestProfile(StrEnum):
    SMOKE = "smoke"; STAGING_SMALL = "staging_small"
    STAGING_MEDIUM = "staging_medium"; PRODUCTION_READONLY = "production_readonly"
    CUSTOM = "custom"

class SandboxV2LoadTestTarget(StrEnum):
    READINESS = "readiness"; METRICS = "metrics"; HEALTH = "health"
    ALERTS = "alerts"; JOBS = "jobs"; QUEUE = "queue"
    ARTIFACTS = "artifacts"; PACKAGES = "packages"
    NETWORK_PREFLIGHT = "network_preflight"; SECURITY_ACCESS = "security_access"
    OBSERVABILITY = "observability"; PERFORMANCE_REPORT = "performance_report"

class SandboxV2LoadTestStatus(StrEnum):
    CREATED = "created"; SKIPPED = "skipped"; RUNNING = "running"
    COMPLETED = "completed"; FAILED = "failed"; BLOCKED = "blocked"
    CANCELED = "canceled"

class SandboxV2SLOStatus(StrEnum):
    PASSED = "passed"; FAILED = "failed"; WARNING = "warning"; NOT_EVALUATED = "not_evaluated"


@dataclass
class SandboxV2LoadTestConfig:
    load_test_id: str = field(default_factory=lambda: f"sbxlt_{uuid4().hex[:16]}")
    profile: str = SandboxV2LoadTestProfile.SMOKE
    base_url_masked: str = ""
    targets: list[str] = field(default_factory=list)
    max_users: int = 5
    max_rps: int = 5
    duration_seconds: int = 30
    timeout_seconds: int = 5
    allow_production: bool = False
    require_confirmation: bool = True
    organization_id: str = ""
    workspace_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "load_test_id": self.load_test_id, "profile": self.profile,
            "base_url_masked": _mask_url(self.base_url_masked),
            "targets": self.targets, "max_users": self.max_users,
            "max_rps": self.max_rps, "duration_seconds": self.duration_seconds,
            "timeout_seconds": self.timeout_seconds,
            "allow_production": self.allow_production,
            "require_confirmation": self.require_confirmation,
            "organization_id": self.organization_id, "workspace_id": self.workspace_id,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2LoadTestConfig":
        return cls(
            load_test_id=d.get("load_test_id", ""), profile=d.get("profile", "smoke"),
            base_url_masked=d.get("base_url_masked", ""),
            targets=list(d.get("targets", []) or []),
            max_users=int(d.get("max_users", 5) or 5),
            max_rps=int(d.get("max_rps", 5) or 5),
            duration_seconds=int(d.get("duration_seconds", 30) or 30),
            timeout_seconds=int(d.get("timeout_seconds", 5) or 5),
            allow_production=bool(d.get("allow_production", False)),
            require_confirmation=bool(d.get("require_confirmation", True)),
            organization_id=d.get("organization_id", ""), workspace_id=d.get("workspace_id", ""),
            created_at=_parse_model_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}) or {}),
        )


@dataclass
class SandboxV2LoadTestResult:
    load_test_result_id: str = field(default_factory=lambda: f"sbxltr_{uuid4().hex[:16]}")
    load_test_id: str = ""
    target: str = ""
    status: str = SandboxV2LoadTestStatus.CREATED
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    duration_ms: int = 0
    total_requests: int = 0
    success_count: int = 0
    failure_count: int = 0
    timeout_count: int = 0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    requests_per_second: float = 0.0
    error_rate_percent: float = 0.0
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "load_test_result_id": self.load_test_result_id, "load_test_id": self.load_test_id,
            "target": self.target, "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": self.duration_ms, "total_requests": self.total_requests,
            "success_count": self.success_count, "failure_count": self.failure_count,
            "timeout_count": self.timeout_count,
            "p50_ms": self.p50_ms, "p95_ms": self.p95_ms, "p99_ms": self.p99_ms,
            "min_ms": self.min_ms, "max_ms": self.max_ms,
            "requests_per_second": self.requests_per_second,
            "error_rate_percent": self.error_rate_percent,
            "warnings": self.warnings, "blockers": self.blockers,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2LoadTestResult":
        return cls(
            load_test_result_id=d.get("load_test_result_id", ""),
            load_test_id=d.get("load_test_id", ""), target=d.get("target", ""),
            status=d.get("status", "created"),
            started_at=_parse_model_dt(d.get("started_at")),
            finished_at=_parse_model_dt(d.get("finished_at")) if d.get("finished_at") else None,
            duration_ms=int(d.get("duration_ms", 0) or 0),
            total_requests=int(d.get("total_requests", 0) or 0),
            success_count=int(d.get("success_count", 0) or 0),
            failure_count=int(d.get("failure_count", 0) or 0),
            timeout_count=int(d.get("timeout_count", 0) or 0),
            p50_ms=float(d.get("p50_ms", 0.0) or 0.0),
            p95_ms=float(d.get("p95_ms", 0.0) or 0.0),
            p99_ms=float(d.get("p99_ms", 0.0) or 0.0),
            min_ms=float(d.get("min_ms", 0.0) or 0.0),
            max_ms=float(d.get("max_ms", 0.0) or 0.0),
            requests_per_second=float(d.get("requests_per_second", 0.0) or 0.0),
            error_rate_percent=float(d.get("error_rate_percent", 0.0) or 0.0),
            warnings=list(d.get("warnings", []) or []),
            blockers=list(d.get("blockers", []) or []),
            metadata=dict(d.get("metadata", {}) or {}),
        )


@dataclass
class SandboxV2SLODefinition:
    slo_id: str = field(default_factory=lambda: f"sbxslo_{uuid4().hex[:16]}")
    name: str = ""
    description: str = ""
    target: str = ""
    p95_ms: int = 500
    p99_ms: int = 1500
    error_rate_percent: float = 1.0
    availability_percent: float = 99.0
    enabled: bool = True
    organization_id: str = ""
    workspace_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "slo_id": self.slo_id, "name": self.name,
            "description": self.description, "target": self.target,
            "p95_ms": self.p95_ms, "p99_ms": self.p99_ms,
            "error_rate_percent": self.error_rate_percent,
            "availability_percent": self.availability_percent,
            "enabled": self.enabled, "organization_id": self.organization_id,
            "workspace_id": self.workspace_id, "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2SLODefinition":
        return cls(
            slo_id=d.get("slo_id", ""), name=d.get("name", ""),
            description=d.get("description", ""), target=d.get("target", ""),
            p95_ms=int(d.get("p95_ms", 500) or 500),
            p99_ms=int(d.get("p99_ms", 1500) or 1500),
            error_rate_percent=float(d.get("error_rate_percent", 1.0) or 1.0),
            availability_percent=float(d.get("availability_percent", 99.0) or 99.0),
            enabled=bool(d.get("enabled", True)),
            organization_id=d.get("organization_id", ""), workspace_id=d.get("workspace_id", ""),
            created_at=_parse_model_dt(d.get("created_at")),
            metadata=dict(d.get("metadata", {}) or {}),
        )


@dataclass
class SandboxV2SLOEvaluation:
    slo_eval_id: str = field(default_factory=lambda: f"sbxslev_{uuid4().hex[:16]}")
    slo_id: str = ""
    load_test_id: str = ""
    status: str = SandboxV2SLOStatus.NOT_EVALUATED
    target: str = ""
    observed_p95_ms: float = 0.0
    observed_p99_ms: float = 0.0
    observed_error_rate_percent: float = 0.0
    observed_availability_percent: float = 0.0
    reason: str = ""
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "slo_eval_id": self.slo_eval_id, "slo_id": self.slo_id,
            "load_test_id": self.load_test_id, "status": self.status,
            "target": self.target,
            "observed_p95_ms": self.observed_p95_ms, "observed_p99_ms": self.observed_p99_ms,
            "observed_error_rate_percent": self.observed_error_rate_percent,
            "observed_availability_percent": self.observed_availability_percent,
            "reason": self.reason, "evaluated_at": self.evaluated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2SLOEvaluation":
        return cls(
            slo_eval_id=d.get("slo_eval_id", ""), slo_id=d.get("slo_id", ""),
            load_test_id=d.get("load_test_id", ""),
            status=d.get("status", "not_evaluated"), target=d.get("target", ""),
            observed_p95_ms=float(d.get("observed_p95_ms", 0.0) or 0.0),
            observed_p99_ms=float(d.get("observed_p99_ms", 0.0) or 0.0),
            observed_error_rate_percent=float(d.get("observed_error_rate_percent", 0.0) or 0.0),
            observed_availability_percent=float(d.get("observed_availability_percent", 0.0) or 0.0),
            reason=d.get("reason", ""),
            evaluated_at=_parse_model_dt(d.get("evaluated_at")),
            metadata=dict(d.get("metadata", {}) or {}),
        )


@dataclass
class SandboxV2CapacityPlan:
    capacity_plan_id: str = field(default_factory=lambda: f"sbxcap_{uuid4().hex[:16]}")
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    recommended_profile: str = "small"
    recommended_backend: str = "sqlite"
    recommended_workers: int = 2
    recommended_queue_backend: str = "sqlite"
    recommended_object_storage: str = "local"
    expected_daily_jobs: int = 1000
    expected_peak_rps: float = 5.0
    bottlenecks: list[str] = field(default_factory=list)
    scaling_recommendations: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capacity_plan_id": self.capacity_plan_id,
            "generated_at": self.generated_at.isoformat(),
            "recommended_profile": self.recommended_profile,
            "recommended_backend": self.recommended_backend,
            "recommended_workers": self.recommended_workers,
            "recommended_queue_backend": self.recommended_queue_backend,
            "recommended_object_storage": self.recommended_object_storage,
            "expected_daily_jobs": self.expected_daily_jobs,
            "expected_peak_rps": self.expected_peak_rps,
            "bottlenecks": self.bottlenecks,
            "scaling_recommendations": self.scaling_recommendations,
            "risk_notes": self.risk_notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxV2CapacityPlan":
        return cls(
            capacity_plan_id=d.get("capacity_plan_id", ""),
            generated_at=_parse_model_dt(d.get("generated_at")),
            recommended_profile=d.get("recommended_profile", "small"),
            recommended_backend=d.get("recommended_backend", "sqlite"),
            recommended_workers=int(d.get("recommended_workers", 2) or 2),
            recommended_queue_backend=d.get("recommended_queue_backend", "sqlite"),
            recommended_object_storage=d.get("recommended_object_storage", "local"),
            expected_daily_jobs=int(d.get("expected_daily_jobs", 1000) or 1000),
            expected_peak_rps=float(d.get("expected_peak_rps", 5.0) or 5.0),
            bottlenecks=list(d.get("bottlenecks", []) or []),
            scaling_recommendations=list(d.get("scaling_recommendations", []) or []),
            risk_notes=list(d.get("risk_notes", []) or []),
            metadata=dict(d.get("metadata", {}) or {}),
        )


def _mask_url(url: str) -> str:
    if not url:
        return ""
    # Mask credential portions
    for s in ("://",):
        if s in url:
            prefix, rest = url.split(s, 1)
            host_part = rest.split("@")[-1] if "@" in rest else rest
            return f"{prefix}{s}****@{host_part}" if "@" in rest else f"{prefix}{s}{host_part[:8]}****{host_part[-4:]}"
    return url[:5] + "****"


def _parse_model_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass
    return datetime.now(timezone.utc)
