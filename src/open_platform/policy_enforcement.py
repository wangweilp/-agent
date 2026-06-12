"""Policy Enforcement Domain Model — SandboxPolicy → WorkerPolicyConfig 翻译层。

Step 24-F:
- WorkerPolicyConfig — 5 sub-configs (network/filesystem/secrets/resource/data)
- PolicyTranslationResult — 翻译结果 + fail-closed checks
- ALLOW_CONFIG 只表示可生成配置，不表示可执行
- enforceable=False when unsupported critical feature exists
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


# ═══════════════ Enums ═══════════════

class PolicyEnforcementDecision(StrEnum):
    ALLOW_CONFIG = "allow_config"
    BLOCK_CONFIG = "block_config"
    REVIEW_REQUIRED = "review_required"
    FAIL_CLOSED = "fail_closed"

class PolicyEnforcementStatus(StrEnum):
    PASSED = "passed"
    PASSED_WITH_WARNINGS = "passed_with_warnings"
    BLOCKED = "blocked"
    REVIEW_REQUIRED = "review_required"
    FAILED = "failed"

class PolicyEnforcementCheckType(StrEnum):
    POLICY_EXISTS = "policy_exists"
    POLICY_ACTIVE = "policy_active"
    SANDBOX_LEVEL_SUPPORTED = "sandbox_level_supported"
    NETWORK_DEFAULT_DENY = "network_default_deny"
    NETWORK_DOMAIN_ALLOWLIST_VALID = "network_domain_allowlist_valid"
    NETWORK_PRIVATE_IP_BLOCKED = "network_private_ip_blocked"
    NETWORK_METADATA_IP_BLOCKED = "network_metadata_ip_blocked"
    FILESYSTEM_DEFAULT_DENY = "filesystem_default_deny"
    FILESYSTEM_READ_PATHS_VALID = "filesystem_read_paths_valid"
    FILESYSTEM_WRITE_PATHS_VALID = "filesystem_write_paths_valid"
    FILESYSTEM_NO_HOST_MOUNT = "filesystem_no_host_mount"
    SECRETS_DEFAULT_DENY = "secrets_default_deny"
    SECRET_NAMES_SCOPED = "secret_names_scoped"
    RESOURCE_TIMEOUT_LIMIT_VALID = "resource_timeout_limit_valid"
    RESOURCE_MEMORY_LIMIT_VALID = "resource_memory_limit_valid"
    RESOURCE_CPU_LIMIT_VALID = "resource_cpu_limit_valid"
    OUTPUT_LIMIT_VALID = "output_limit_valid"
    DATA_ACCESS_SCOPE_VALID = "data_access_scope_valid"
    AUDIT_ENABLED = "audit_enabled"
    KILL_SWITCH_SUPPORTED_RESERVED = "kill_switch_supported_reserved"
    WORKER_CAN_ENFORCE_RESERVED = "worker_can_enforce_reserved"
    FAIL_CLOSED_ON_UNSUPPORTED = "fail_closed_on_unsupported"

class PolicyEnforcementCheckStatus(StrEnum):
    PASSED = "passed"; WARNING = "warning"; BLOCKED = "blocked"; FAILED = "failed"; SKIPPED = "skipped"

class PolicyEnforcementSeverity(StrEnum):
    INFO = "info"; WARNING = "warning"; ERROR = "error"; BLOCKER = "blocker"

class NetworkEgressMode(StrEnum):
    DENY_ALL = "deny_all"; ALLOWLIST_ONLY = "allowlist_only"; DISABLED_UNSUPPORTED = "disabled_unsupported"

class FilesystemMode(StrEnum):
    DENY_ALL = "deny_all"; EPHEMERAL_ONLY = "ephemeral_only"; READ_ONLY_PACKAGE_RESERVED = "read_only_package_reserved"; DISABLED_UNSUPPORTED = "disabled_unsupported"

class SecretAccessMode(StrEnum):
    DENY_ALL = "deny_all"; SCOPED_BROKER_RESERVED = "scoped_broker_reserved"; DISABLED_UNSUPPORTED = "disabled_unsupported"

class DataAccessMode(StrEnum):
    DENY_ALL = "deny_all"; BROKER_ONLY_RESERVED = "broker_only_reserved"; DISABLED_UNSUPPORTED = "disabled_unsupported"


# ═══════════════ PolicyEnforcementCheck ═══════════════

@dataclass
class PolicyEnforcementCheck:
    check_id: str = field(default_factory=lambda: f"polchk_{uuid4().hex[:16]}")
    check_type: str = ""
    status: str = PolicyEnforcementCheckStatus.PASSED
    severity: str = PolicyEnforcementSeverity.INFO
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {"check_id": self.check_id, "check_type": self.check_type, "status": self.status,
                "severity": self.severity, "message": self.message, "metadata": dict(self.metadata),
                "created_at": self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PolicyEnforcementCheck":
        return cls(check_id=str(d.get("check_id", "")), check_type=str(d.get("check_type", "")),
                   status=str(d.get("status", "passed")), severity=str(d.get("severity", "info")),
                   message=str(d.get("message", "")), metadata=dict(d.get("metadata", {})),
                   created_at=_safe_dt(d.get("created_at")))


# ═══════════════ Configs ═══════════════

@dataclass
class NetworkPolicyConfig:
    mode: str = NetworkEgressMode.DENY_ALL
    allow_network: bool = False
    allowed_domains: list[str] = field(default_factory=list)
    blocked_private_ranges: bool = True
    blocked_metadata_ip: bool = True
    blocked_localhost: bool = True
    dns_control_required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "allow_network": self.allow_network,
                "allowed_domains": list(self.allowed_domains),
                "blocked_private_ranges": self.blocked_private_ranges,
                "blocked_metadata_ip": self.blocked_metadata_ip,
                "blocked_localhost": self.blocked_localhost,
                "dns_control_required": self.dns_control_required, "metadata": dict(self.metadata)}
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "NetworkPolicyConfig":
        return cls(mode=str(d.get("mode", "deny_all")), allow_network=bool(d.get("allow_network", False)),
                   allowed_domains=list(d.get("allowed_domains", [])),
                   blocked_private_ranges=bool(d.get("blocked_private_ranges", True)),
                   blocked_metadata_ip=bool(d.get("blocked_metadata_ip", True)),
                   blocked_localhost=bool(d.get("blocked_localhost", True)),
                   dns_control_required=bool(d.get("dns_control_required", False)),
                   metadata=dict(d.get("metadata", {})))

@dataclass
class FilesystemPolicyConfig:
    mode: str = FilesystemMode.DENY_ALL
    allow_read: bool = False; allow_write: bool = False
    allowed_read_paths: list[str] = field(default_factory=list)
    allowed_write_paths: list[str] = field(default_factory=list)
    ephemeral_workspace: bool = True; host_mount_allowed: bool = False
    symlink_escape_blocked: bool = True; max_output_bytes: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "allow_read": self.allow_read, "allow_write": self.allow_write,
                "allowed_read_paths": list(self.allowed_read_paths),
                "allowed_write_paths": list(self.allowed_write_paths),
                "ephemeral_workspace": self.ephemeral_workspace,
                "host_mount_allowed": self.host_mount_allowed,
                "symlink_escape_blocked": self.symlink_escape_blocked,
                "max_output_bytes": self.max_output_bytes, "metadata": dict(self.metadata)}
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FilesystemPolicyConfig":
        return cls(mode=str(d.get("mode", "deny_all")), allow_read=bool(d.get("allow_read", False)),
                   allow_write=bool(d.get("allow_write", False)),
                   allowed_read_paths=list(d.get("allowed_read_paths", [])),
                   allowed_write_paths=list(d.get("allowed_write_paths", [])),
                   ephemeral_workspace=bool(d.get("ephemeral_workspace", True)),
                   host_mount_allowed=bool(d.get("host_mount_allowed", False)),
                   symlink_escape_blocked=bool(d.get("symlink_escape_blocked", True)),
                   max_output_bytes=d.get("max_output_bytes"), metadata=dict(d.get("metadata", {})))

@dataclass
class SecretPolicyConfig:
    mode: str = SecretAccessMode.DENY_ALL
    allow_secrets: bool = False; allowed_secret_names: list[str] = field(default_factory=list)
    broker_required: bool = False; raw_env_injection_allowed: bool = False
    audit_required: bool = True; metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "allow_secrets": self.allow_secrets,
                "allowed_secret_names": list(self.allowed_secret_names),
                "broker_required": self.broker_required,
                "raw_env_injection_allowed": self.raw_env_injection_allowed,
                "audit_required": self.audit_required, "metadata": dict(self.metadata)}
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SecretPolicyConfig":
        return cls(mode=str(d.get("mode", "deny_all")), allow_secrets=bool(d.get("allow_secrets", False)),
                   allowed_secret_names=list(d.get("allowed_secret_names", [])),
                   broker_required=bool(d.get("broker_required", False)),
                   raw_env_injection_allowed=bool(d.get("raw_env_injection_allowed", False)),
                   audit_required=bool(d.get("audit_required", True)), metadata=dict(d.get("metadata", {})))

@dataclass
class ResourceLimitPolicyConfig:
    timeout_ms: int = 0; memory_mb: int | None = None; cpu_percent: int | None = None
    max_output_bytes: int | None = None; max_requests_per_minute: int | None = None
    kill_on_timeout: bool = True; fail_closed_on_limit_missing: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"timeout_ms": self.timeout_ms, "memory_mb": self.memory_mb,
                "cpu_percent": self.cpu_percent, "max_output_bytes": self.max_output_bytes,
                "max_requests_per_minute": self.max_requests_per_minute,
                "kill_on_timeout": self.kill_on_timeout,
                "fail_closed_on_limit_missing": self.fail_closed_on_limit_missing,
                "metadata": dict(self.metadata)}
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ResourceLimitPolicyConfig":
        return cls(timeout_ms=int(d.get("timeout_ms", 0)), memory_mb=d.get("memory_mb"),
                   cpu_percent=d.get("cpu_percent"), max_output_bytes=d.get("max_output_bytes"),
                   max_requests_per_minute=d.get("max_requests_per_minute"),
                   kill_on_timeout=bool(d.get("kill_on_timeout", True)),
                   fail_closed_on_limit_missing=bool(d.get("fail_closed_on_limit_missing", True)),
                   metadata=dict(d.get("metadata", {})))

@dataclass
class DataAccessPolicyConfig:
    mode: str = DataAccessMode.DENY_ALL
    data_access_scope: list[str] = field(default_factory=list)
    broker_required: bool = False; direct_db_access_allowed: bool = False
    direct_file_access_allowed: bool = False; direct_vector_access_allowed: bool = False
    audit_required: bool = True; metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "data_access_scope": list(self.data_access_scope),
                "broker_required": self.broker_required,
                "direct_db_access_allowed": self.direct_db_access_allowed,
                "direct_file_access_allowed": self.direct_file_access_allowed,
                "direct_vector_access_allowed": self.direct_vector_access_allowed,
                "audit_required": self.audit_required, "metadata": dict(self.metadata)}
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DataAccessPolicyConfig":
        return cls(mode=str(d.get("mode", "deny_all")), data_access_scope=list(d.get("data_access_scope", [])),
                   broker_required=bool(d.get("broker_required", False)),
                   direct_db_access_allowed=bool(d.get("direct_db_access_allowed", False)),
                   direct_file_access_allowed=bool(d.get("direct_file_access_allowed", False)),
                   direct_vector_access_allowed=bool(d.get("direct_vector_access_allowed", False)),
                   audit_required=bool(d.get("audit_required", True)), metadata=dict(d.get("metadata", {})))


# ═══════════════ WorkerPolicyConfig ═══════════════

@dataclass
class WorkerPolicyConfig:
    config_id: str = field(default_factory=lambda: f"polcfg_{uuid4().hex[:16]}")
    policy_id: str = ""; tenant_id: str | None = None; sandbox_level: str = ""
    enforceable: bool = False
    decision: str = PolicyEnforcementDecision.FAIL_CLOSED
    network: NetworkPolicyConfig = field(default_factory=NetworkPolicyConfig)
    filesystem: FilesystemPolicyConfig = field(default_factory=FilesystemPolicyConfig)
    secrets: SecretPolicyConfig = field(default_factory=SecretPolicyConfig)
    resources: ResourceLimitPolicyConfig = field(default_factory=ResourceLimitPolicyConfig)
    data_access: DataAccessPolicyConfig = field(default_factory=DataAccessPolicyConfig)
    audit_enabled: bool = True; kill_switch_required: bool = True
    unsupported_features: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {"config_id": self.config_id, "policy_id": self.policy_id,
                "tenant_id": self.tenant_id, "sandbox_level": self.sandbox_level,
                "enforceable": self.enforceable, "decision": self.decision,
                "network": self.network.to_dict(), "filesystem": self.filesystem.to_dict(),
                "secrets": self.secrets.to_dict(), "resources": self.resources.to_dict(),
                "data_access": self.data_access.to_dict(),
                "audit_enabled": self.audit_enabled, "kill_switch_required": self.kill_switch_required,
                "unsupported_features": list(self.unsupported_features),
                "warnings": list(self.warnings), "metadata": dict(self.metadata),
                "created_at": self.created_at.isoformat() if self.created_at else None}
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WorkerPolicyConfig":
        return cls(config_id=str(d.get("config_id", "")), policy_id=str(d.get("policy_id", "")),
                   tenant_id=d.get("tenant_id"), sandbox_level=str(d.get("sandbox_level", "")),
                   enforceable=bool(d.get("enforceable", False)),
                   decision=str(d.get("decision", "fail_closed")),
                   network=NetworkPolicyConfig.from_dict(d.get("network", {})),
                   filesystem=FilesystemPolicyConfig.from_dict(d.get("filesystem", {})),
                   secrets=SecretPolicyConfig.from_dict(d.get("secrets", {})),
                   resources=ResourceLimitPolicyConfig.from_dict(d.get("resources", {})),
                   data_access=DataAccessPolicyConfig.from_dict(d.get("data_access", {})),
                   audit_enabled=bool(d.get("audit_enabled", True)),
                   kill_switch_required=bool(d.get("kill_switch_required", True)),
                   unsupported_features=list(d.get("unsupported_features", [])),
                   warnings=list(d.get("warnings", [])), metadata=dict(d.get("metadata", {})),
                   created_at=_safe_dt(d.get("created_at")))


# ═══════════════ PolicyTranslationResult ═══════════════

@dataclass
class PolicyTranslationResult:
    translation_id: str = field(default_factory=lambda: f"poltr_{uuid4().hex[:16]}")
    policy_id: str = ""; tenant_id: str | None = None
    status: str = PolicyEnforcementStatus.PASSED
    decision: str = PolicyEnforcementDecision.FAIL_CLOSED
    config: WorkerPolicyConfig | None = None
    checks: list[PolicyEnforcementCheck] = field(default_factory=list)
    warnings_count: int = 0; errors_count: int = 0; blockers_count: int = 0
    no_execution_performed: bool = True; no_network_used: bool = True
    no_secrets_read: bool = True; no_filesystem_access: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_check(self, c: PolicyEnforcementCheck) -> None: self.checks.append(c); self._recount()
    def _recount(self):
        self.warnings_count = sum(1 for c in self.checks if c.status == PolicyEnforcementCheckStatus.WARNING)
        self.errors_count = sum(1 for c in self.checks if c.status == PolicyEnforcementCheckStatus.FAILED)
        self.blockers_count = sum(1 for c in self.checks if c.status == PolicyEnforcementCheckStatus.BLOCKED)

    def calculate_status(self):
        self._recount()
        if self.blockers_count > 0: self.status = PolicyEnforcementStatus.BLOCKED; self.decision = PolicyEnforcementDecision.BLOCK_CONFIG
        elif self.errors_count > 0: self.status = PolicyEnforcementStatus.FAILED; self.decision = PolicyEnforcementDecision.BLOCK_CONFIG
        elif self.warnings_count > 0: self.status = PolicyEnforcementStatus.PASSED_WITH_WARNINGS; self.decision = PolicyEnforcementDecision.REVIEW_REQUIRED
        else: self.status = PolicyEnforcementStatus.PASSED; self.decision = PolicyEnforcementDecision.ALLOW_CONFIG

    def is_enforceable(self) -> bool:
        """只表示 config 可被未来 worker 消费，不表示可执行。"""
        return (self.config is not None and self.config.enforceable)

    def to_dict(self) -> dict[str, Any]:
        return {"translation_id": self.translation_id, "policy_id": self.policy_id,
                "tenant_id": self.tenant_id, "status": self.status, "decision": self.decision,
                "config": self.config.to_dict() if self.config else None,
                "checks": [c.to_dict() for c in self.checks],
                "warnings_count": self.warnings_count, "errors_count": self.errors_count,
                "blockers_count": self.blockers_count,
                "no_execution_performed": self.no_execution_performed,
                "no_network_used": self.no_network_used, "no_secrets_read": self.no_secrets_read,
                "no_filesystem_access": self.no_filesystem_access,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "metadata": dict(self.metadata)}
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PolicyTranslationResult":
        cfg = d.get("config"); cfg_obj = WorkerPolicyConfig.from_dict(cfg) if isinstance(cfg, dict) else None
        checks = [PolicyEnforcementCheck.from_dict(c) for c in d.get("checks", [])]
        return cls(translation_id=str(d.get("translation_id", "")), policy_id=str(d.get("policy_id", "")),
                   tenant_id=d.get("tenant_id"), status=str(d.get("status", "passed")),
                   decision=str(d.get("decision", "fail_closed")), config=cfg_obj, checks=checks,
                   warnings_count=int(d.get("warnings_count", 0)), errors_count=int(d.get("errors_count", 0)),
                   blockers_count=int(d.get("blockers_count", 0)),
                   no_execution_performed=bool(d.get("no_execution_performed", True)),
                   no_network_used=bool(d.get("no_network_used", True)),
                   no_secrets_read=bool(d.get("no_secrets_read", True)),
                   no_filesystem_access=bool(d.get("no_filesystem_access", True)),
                   created_at=_safe_dt(d.get("created_at")), metadata=dict(d.get("metadata", {})))


# ═══════════════ Errors ═══════════════

class PolicyEnforcementError(Exception): pass
class PolicyTranslationError(PolicyEnforcementError): pass
class PolicyUnsupportedFeatureError(PolicyEnforcementError): pass
class PolicyFailClosedError(PolicyEnforcementError): pass


# ═══════════════ Helpers ═══════════════

def build_policy_config_snapshot(result: PolicyTranslationResult) -> dict[str, Any]:
    """从 PolicyTranslationResult 生成安全的 policy_config_snapshot。不修改 worker request / plan。"""
    if result.config is not None: return result.config.to_dict()
    return {"policy_id": result.policy_id, "status": result.status, "decision": result.decision,
            "enforceable": False, "fail_closed": True, "no_config_generated": True}

# ═══════════════ Step 26-G: Unified Policy Decision Engine ═══════════════


class PolicyDecisionStatus(StrEnum):
    """Step 26-G: All decisions = Deny. allowed = always False."""
    DENIED = "denied"
    DENIED_BLOCKED = "denied_blocked"
    DENIED_PLANNED = "denied_planned"
    DENIED_UNSUPPORTED = "denied_unsupported"
    DENIED_BY_POLICY = "denied_by_policy"


class PermissionRequestType(StrEnum):
    NETWORK_EGRESS = "network_egress"
    NETWORK_INGRESS = "network_ingress"
    FILESYSTEM_WRITE = "filesystem_write"
    FILESYSTEM_READ = "filesystem_read"
    SECRETS_ACCESS = "secrets_access"
    SUBPROCESS_EXECUTION = "subprocess_execution"
    DYNAMIC_IMPORT = "dynamic_import"
    EVAL_EXEC = "eval_exec"
    PACKAGE_EXECUTION = "package_execution"
    THIRD_PARTY_EXECUTION = "third_party_execution"
    ENTRYPOINT_EXECUTION = "entrypoint_execution"
    CONTAINER_START = "container_start"
    MICROVM_START = "microvm_start"
    MEMORY_LIMIT = "memory_limit"
    CPU_LIMIT = "cpu_limit"
    ROOTLESS_CONTAINER = "rootless_container"
    ISOLATED_RUNTIME = "isolated_runtime"
    OS_ISOLATION = "os_isolation"
    IPC = "ipc"
    ENVIRONMENT_VARIABLES = "environment_variables"


class PolicyEnforcementAuditEventType(StrEnum):
    DECISION_CREATED = "decision_created"
    AUDIT_COMPLETED = "audit_completed"
    AUDIT_EXPORTED = "audit_exported"


@dataclass
class PermissionRequest:
    request_id: str = field(default_factory=lambda: f"pmreq_{uuid4().hex[:16]}")
    request_type: str = ""
    capability_name: str = ""
    tenant_id: str | None = None
    actor_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {"request_id": self.request_id, "request_type": self.request_type,
                "capability_name": self.capability_name, "tenant_id": self.tenant_id,
                "actor_id": self.actor_id, "metadata": dict(self.metadata),
                "requested_at": self.requested_at.isoformat()}


@dataclass
class PolicyDecision:
    decision_id: str = field(default_factory=lambda: f"poldec_{uuid4().hex[:16]}")
    request_id: str = ""
    request_type: str = ""
    capability_name: str = ""
    capability_status: str = "blocked"
    allowed: bool = False
    reason: str = ""
    source_policy: str = ""
    enforcement_type: str = "metadata_only"
    execution_allowed: bool = False
    runtime_enabled: bool = False
    metadata_only: bool = True
    tenant_id: str | None = None
    decided_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_allowed(self) -> bool: return False
    def is_execution_allowed(self) -> bool: return False
    def is_runtime_enabled(self) -> bool: return False

    def to_dict(self):
        return {"decision_id": self.decision_id, "request_id": self.request_id,
                "request_type": self.request_type, "capability_name": self.capability_name,
                "capability_status": self.capability_status, "allowed": self.allowed,
                "reason": self.reason, "source_policy": self.source_policy,
                "enforcement_type": self.enforcement_type,
                "execution_allowed": self.execution_allowed,
                "runtime_enabled": self.runtime_enabled, "metadata_only": self.metadata_only,
                "tenant_id": self.tenant_id, "decided_at": self.decided_at.isoformat(),
                "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, d):
        return cls(decision_id=str(d.get("decision_id", "")),
                   request_id=str(d.get("request_id", "")),
                   request_type=str(d.get("request_type", "")),
                   capability_name=str(d.get("capability_name", "")),
                   capability_status=str(d.get("capability_status", "blocked")),
                   allowed=bool(d.get("allowed", False)), reason=str(d.get("reason", "")),
                   source_policy=str(d.get("source_policy", "")),
                   enforcement_type=str(d.get("enforcement_type", "metadata_only")),
                   execution_allowed=bool(d.get("execution_allowed", False)),
                   runtime_enabled=bool(d.get("runtime_enabled", False)),
                   metadata_only=bool(d.get("metadata_only", True)),
                   tenant_id=d.get("tenant_id"), decided_at=_safe_dt(d.get("decided_at")),
                   metadata=dict(d.get("metadata", {})))


@dataclass
class PolicyEnforcementAuditEvent:
    event_id: str = field(default_factory=lambda: f"penfevt_{uuid4().hex[:16]}")
    decision_id: str = ""
    event_type: str = ""
    tenant_id: str | None = None
    message: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {"event_id": self.event_id, "decision_id": self.decision_id,
                "event_type": self.event_type, "tenant_id": self.tenant_id,
                "message": self.message, "created_at": self.created_at.isoformat(),
                "metadata": dict(self.metadata)}


class PolicyEnforcementEngine:
    """Unified policy engine. Step 26-G. All decisions = Deny. Metadata-only."""

    _POLICY_RULES: dict[str, tuple[str, str]] = {
        PermissionRequestType.NETWORK_EGRESS: ("blocked", "Step 26-F: network_enabled=False"),
        PermissionRequestType.NETWORK_INGRESS: ("blocked", "Step 26-F: network_enabled=False"),
        PermissionRequestType.FILESYSTEM_WRITE: ("blocked", "Step 26-F: filesystem_write_enabled=False"),
        PermissionRequestType.FILESYSTEM_READ: ("blocked", "Step 26-D: read-only refs only"),
        PermissionRequestType.SECRETS_ACCESS: ("blocked", "Step 26-F: secrets_enabled=False"),
        PermissionRequestType.SUBPROCESS_EXECUTION: ("blocked", "Step 26-F: subprocess_enabled=False"),
        PermissionRequestType.DYNAMIC_IMPORT: ("blocked", "Step 26-F: dynamic_import_enabled=False"),
        PermissionRequestType.EVAL_EXEC: ("blocked", "Step 26-F: eval_exec_enabled=False"),
        PermissionRequestType.PACKAGE_EXECUTION: ("blocked", "Step 26-F: package_execution_enabled=False"),
        PermissionRequestType.THIRD_PARTY_EXECUTION: ("blocked", "Step 26-F: third_party_execution_enabled=False"),
        PermissionRequestType.ENTRYPOINT_EXECUTION: ("blocked", "Step 26-F: entrypoint_execution_enabled=False"),
        PermissionRequestType.CONTAINER_START: ("blocked", "Step 26-F: container_start_enabled=False"),
        PermissionRequestType.MICROVM_START: ("blocked", "Step 26-F: microvm_start_enabled=False"),
        PermissionRequestType.MEMORY_LIMIT: ("planned", "Memory limit planned; cgroup missing (Step 26-E)"),
        PermissionRequestType.CPU_LIMIT: ("planned", "CPU limit planned; cgroup missing (Step 26-E)"),
        PermissionRequestType.ROOTLESS_CONTAINER: ("planned", "Rootless container planned; Step 27 required"),
        PermissionRequestType.ISOLATED_RUNTIME: ("planned", "Isolated runtime planned; Step 27 required"),
        PermissionRequestType.OS_ISOLATION: ("planned", "OS isolation planned; Step 27 required"),
        PermissionRequestType.IPC: ("unsupported", "IPC unsupported; no runtime processes"),
        PermissionRequestType.ENVIRONMENT_VARIABLES: ("blocked", "Step 26-F: secrets_enabled=False"),
    }

    def evaluate(self, request: PermissionRequest) -> PolicyDecision:
        rule = self._POLICY_RULES.get(request.request_type)
        if rule is None:
            return PolicyDecision(request_id=request.request_id, request_type=request.request_type,
                capability_name=request.capability_name, capability_status="blocked",
                allowed=False, reason=f"Unknown request type: {request.request_type}",
                source_policy="PolicyEnforcementEngine")
        expected_status, reason = rule
        return PolicyDecision(request_id=request.request_id, request_type=request.request_type,
            capability_name=request.capability_name, capability_status=expected_status,
            allowed=False, reason=reason, source_policy="Step 26-F: TrustedFixtureIsolationPolicy")

    def evaluate_all(self) -> list[PolicyDecision]:
        return [self.evaluate(PermissionRequest(request_type=t.value, capability_name=t.value))
                for t in PermissionRequestType]

    def export_audit_report(self) -> dict[str, Any]:
        decisions = self.evaluate_all()
        return {"total": len(decisions), "decisions": [d.to_dict() for d in decisions],
                "summary": {"allowed_any": any(d.allowed for d in decisions),
                             "execution_allowed_any": any(d.execution_allowed for d in decisions),
                             "runtime_enabled_any": any(d.runtime_enabled for d in decisions),
                             "all_denied": all(not d.allowed for d in decisions),
                             "metadata_only_all": all(d.metadata_only for d in decisions)},
                "generated_at": datetime.now(timezone.utc).isoformat()}


@runtime_checkable
class PolicyDecisionStore(Protocol):
    def create_decision(self, decision: PolicyDecision) -> PolicyDecision: ...
    def get_decision(self, decision_id: str) -> PolicyDecision | None: ...
    def list_decisions(self, *, request_type: str = "") -> list[PolicyDecision]: ...
    def export_decisions(self) -> dict[str, Any]: ...
    def add_audit_event(self, event: PolicyEnforcementAuditEvent) -> PolicyEnforcementAuditEvent: ...
    def list_audit_events(self) -> list[PolicyEnforcementAuditEvent]: ...


class PolicyEnforcementAuditSubAgent:
    """Audits all 20 capabilities. Metadata-only. No execution."""

    def __init__(self, metadata_only: bool = True):
        if not metadata_only: raise ValueError("metadata_only must be True")
        self.metadata_only = True

    def run_audit(self) -> dict[str, Any]:
        engine = PolicyEnforcementEngine()
        decisions = engine.evaluate_all()
        report = {
            "audit_id": f"polaudit_{uuid4().hex[:16]}",
            "total_capabilities": len(decisions),
            "all_denied": all(not d.allowed for d in decisions),
            "all_execution_blocked": all(not d.execution_allowed for d in decisions),
            "all_runtime_disabled": all(not d.runtime_enabled for d in decisions),
            "all_metadata_only": all(d.metadata_only for d in decisions),
            "blocked_count": sum(1 for d in decisions if d.capability_status == "blocked"),
            "planned_count": sum(1 for d in decisions if d.capability_status == "planned"),
            "unsupported_count": sum(1 for d in decisions if d.capability_status == "unsupported"),
            "enforcement_by_type": {t.value: next((d.to_dict() for d in decisions if d.request_type == t.value), None) for t in PermissionRequestType},
            "decisions": [d.to_dict() for d in decisions],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        return report


class PolicyDecisionNotFoundError(PolicyEnforcementError): pass


def run_policy_audit() -> dict[str, Any]:
    return PolicyEnforcementAuditSubAgent().run_audit()


def _safe_dt(raw, none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
