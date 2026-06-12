"""Sandbox Policy Domain Model — Developer Agent 沙箱安全策略。

Step 23-E MVP:
- SandboxPolicy 是策略模型，不是容器沙箱
- 不执行代码
- 不联网
- 不读取真实企业数据
- 不读取 secrets

策略目标:
- 定义 developer agent 的运行时安全边界
- admin 可配置 policy 并绑定到 runtime binding
- test endpoint 只做静态规则评估
- no_execution / simulation_only 策略的 is_execution_allowed() 必须 False
- 真正 sandbox execution 需要 Step 24+ container/subprocess 基础设施
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


class SandboxLevel(StrEnum):
    NO_EXECUTION = "no_execution"
    SIMULATION_ONLY = "simulation_only"
    RESTRICTED = "restricted"
    ISOLATED = "isolated"


class SandboxPolicyStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class SandboxPolicyScope(StrEnum):
    SYSTEM = "system"
    TENANT = "tenant"


class SandboxPolicyDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    WARN = "warn"


# MVP 允许启用的 sandbox levels
MVP_ALLOWED_SANDBOX_LEVELS: frozenset[str] = frozenset({
    SandboxLevel.NO_EXECUTION,
    SandboxLevel.SIMULATION_ONLY,
    SandboxLevel.RESTRICTED,
})

# 这些 level 的 is_execution_allowed() 永远 False
NON_EXECUTABLE_SANDBOX_LEVELS: frozenset[str] = frozenset({
    SandboxLevel.NO_EXECUTION,
    SandboxLevel.SIMULATION_ONLY,
})


# ═══════════════════════════════════════════
# SandboxPolicy
# ═══════════════════════════════════════════


@dataclass
class SandboxPolicy:
    """沙箱安全策略 — 定义 developer agent 运行时的安全边界。

    安全约束：
    - 不包含执行函数
    - 不包含网络调用
    - 不包含文件访问
    - no_execution/simulation_only 的 is_execution_allowed() 必须 False
    - system_managed=True 的策略不允许普通 admin 修改关键限制字段
    """

    policy_id: str = field(default_factory=lambda: f"sbxpol_{uuid4().hex[:12]}")
    name: str = ""
    description: str = ""
    scope: str = SandboxPolicyScope.SYSTEM
    tenant_id: str | None = None
    sandbox_level: str = SandboxLevel.NO_EXECUTION
    allow_network: bool = False
    allowed_domains: list[str] = field(default_factory=list)
    allow_filesystem_read: bool = False
    allow_filesystem_write: bool = False
    allowed_paths: list[str] = field(default_factory=list)
    allow_secrets: bool = False
    allowed_secret_names: list[str] = field(default_factory=list)
    max_timeout_ms: int = 0
    max_memory_mb: int = 0
    max_cpu_percent: int = 0
    max_output_bytes: int = 0
    max_requests_per_minute: int = 0
    data_access_scope: list[str] = field(default_factory=list)
    audit_enabled: bool = True
    kill_switch_enabled: bool = True
    status: str = SandboxPolicyStatus.ACTIVE
    system_managed: bool = False
    created_by: str | None = None
    updated_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_active(self) -> bool:
        return self.status == SandboxPolicyStatus.ACTIVE

    def is_execution_allowed(self) -> bool:
        """no_execution 和 simulation_only 永远不返回 True。"""
        if self.sandbox_level in NON_EXECUTABLE_SANDBOX_LEVELS:
            return False
        if not self.is_active():
            return False
        return True

    def validate(self) -> list[str]:
        """校验 policy 合法性，返回 errors 列表。"""
        errors: list[str] = []

        if not self.name or not self.name.strip():
            errors.append("name 必填")
        if not self.description or not self.description.strip():
            errors.append("description 必填")

        # scope check
        if self.scope == SandboxPolicyScope.SYSTEM and self.tenant_id is not None:
            errors.append("scope=system 时 tenant_id 必须为 None")
        if self.scope == SandboxPolicyScope.TENANT and not self.tenant_id:
            errors.append("scope=tenant 时 tenant_id 必须有值")

        # sandbox_level check
        if self.sandbox_level not in [v.value for v in SandboxLevel]:
            errors.append(f"sandbox_level 无效: {self.sandbox_level}")

        # no_execution level restrictions
        if self.sandbox_level == SandboxLevel.NO_EXECUTION:
            if self.allow_network:
                errors.append("no_execution policy 不允许 allow_network=True")
            if self.allow_filesystem_read:
                errors.append("no_execution policy 不允许 allow_filesystem_read=True")
            if self.allow_filesystem_write:
                errors.append("no_execution policy 不允许 allow_filesystem_write=True")
            if self.allow_secrets:
                errors.append("no_execution policy 不允许 allow_secrets=True")

        # simulation_only restrictions
        if self.sandbox_level == SandboxLevel.SIMULATION_ONLY:
            if self.allow_network:
                errors.append("simulation_only policy 不允许 allow_network=True")
            if self.allow_filesystem_write:
                errors.append("simulation_only policy 不允许 allow_filesystem_write=True")
            if self.allow_secrets:
                errors.append("simulation_only policy 不允许 allow_secrets=True")

        # type checks
        for field_name in ("allowed_domains", "allowed_paths", "allowed_secret_names", "data_access_scope"):
            val = getattr(self, field_name)
            if not isinstance(val, list):
                errors.append(f"{field_name} 必须是 list")

        if not isinstance(self.metadata, dict):
            errors.append("metadata 必须是 dict")

        # numeric non-negative
        for field_name in ("max_timeout_ms", "max_memory_mb", "max_cpu_percent",
                           "max_output_bytes", "max_requests_per_minute"):
            val = getattr(self, field_name)
            if not isinstance(val, int) or val < 0:
                errors.append(f"{field_name} 必须是非负整数")

        return errors

    def is_valid(self) -> bool:
        return len(self.validate()) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "description": self.description,
            "scope": self.scope,
            "tenant_id": self.tenant_id,
            "sandbox_level": self.sandbox_level,
            "allow_network": self.allow_network,
            "allowed_domains": list(self.allowed_domains),
            "allow_filesystem_read": self.allow_filesystem_read,
            "allow_filesystem_write": self.allow_filesystem_write,
            "allowed_paths": list(self.allowed_paths),
            "allow_secrets": self.allow_secrets,
            "allowed_secret_names": list(self.allowed_secret_names),
            "max_timeout_ms": self.max_timeout_ms,
            "max_memory_mb": self.max_memory_mb,
            "max_cpu_percent": self.max_cpu_percent,
            "max_output_bytes": self.max_output_bytes,
            "max_requests_per_minute": self.max_requests_per_minute,
            "data_access_scope": list(self.data_access_scope),
            "audit_enabled": self.audit_enabled,
            "kill_switch_enabled": self.kill_switch_enabled,
            "status": self.status,
            "system_managed": self.system_managed,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SandboxPolicy":
        ca = _safe_parse_dt(d.get("created_at"))
        ua = _safe_parse_dt(d.get("updated_at"))
        return cls(
            policy_id=str(d.get("policy_id", "")),
            name=str(d.get("name", "")),
            description=str(d.get("description", "")),
            scope=str(d.get("scope", SandboxPolicyScope.SYSTEM)),
            tenant_id=d.get("tenant_id"),
            sandbox_level=str(d.get("sandbox_level", SandboxLevel.NO_EXECUTION)),
            allow_network=bool(d.get("allow_network", False)),
            allowed_domains=list(d.get("allowed_domains", [])),
            allow_filesystem_read=bool(d.get("allow_filesystem_read", False)),
            allow_filesystem_write=bool(d.get("allow_filesystem_write", False)),
            allowed_paths=list(d.get("allowed_paths", [])),
            allow_secrets=bool(d.get("allow_secrets", False)),
            allowed_secret_names=list(d.get("allowed_secret_names", [])),
            max_timeout_ms=int(d.get("max_timeout_ms", 0)),
            max_memory_mb=int(d.get("max_memory_mb", 0)),
            max_cpu_percent=int(d.get("max_cpu_percent", 0)),
            max_output_bytes=int(d.get("max_output_bytes", 0)),
            max_requests_per_minute=int(d.get("max_requests_per_minute", 0)),
            data_access_scope=list(d.get("data_access_scope", [])),
            audit_enabled=bool(d.get("audit_enabled", True)),
            kill_switch_enabled=bool(d.get("kill_switch_enabled", True)),
            status=str(d.get("status", SandboxPolicyStatus.ACTIVE)),
            system_managed=bool(d.get("system_managed", False)),
            created_by=d.get("created_by"),
            updated_by=d.get("updated_by"),
            metadata=dict(d.get("metadata", {})),
            created_at=ca,
            updated_at=ua,
        )


# ═══════════════════════════════════════════
# SandboxPolicyTestRequest
# ═══════════════════════════════════════════


@dataclass
class SandboxPolicyTestRequest:
    """针对政策的测试请求 — 只做静态规则评估。"""

    sandbox_level: str = SandboxLevel.NO_EXECUTION
    requested_network: bool = False
    requested_domains: list[str] = field(default_factory=list)
    requested_filesystem_read: bool = False
    requested_filesystem_write: bool = False
    requested_secret_names: list[str] = field(default_factory=list)
    requested_timeout_ms: int = 0
    requested_memory_mb: int = 0
    requested_data_access_scope: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════
# SandboxPolicyTestResult
# ═══════════════════════════════════════════


@dataclass
class SandboxPolicyTestResult:
    """政策测试结果 — 静态规则评估输出。"""

    policy_id: str = ""
    decision: str = SandboxPolicyDecision.DENY
    allowed: bool = False
    warnings: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    evaluated_rules: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "decision": self.decision,
            "allowed": self.allowed,
            "warnings": self.warnings,
            "violations": self.violations,
            "evaluated_rules": self.evaluated_rules,
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════
# SandboxPolicyStore Protocol
# ═══════════════════════════════════════════


@runtime_checkable
class SandboxPolicyStore(Protocol):
    """Sandbox Policy 存储协议。

    禁止：
    - 执行代码
    - 联网
    - 访问文件
    - 读取 secrets
    """

    def create_policy(self, policy: SandboxPolicy) -> SandboxPolicy: ...
    def get_policy(self, policy_id: str) -> SandboxPolicy | None: ...
    def get_policy_by_name(self, name: str, tenant_id: str | None = None) -> SandboxPolicy | None: ...
    def list_policies(
        self, *, tenant_id: str = "", scope: str = "",
        status: str = "", include_system: bool = True,
    ) -> list[SandboxPolicy]: ...
    def update_policy(self, policy: SandboxPolicy) -> None: ...
    def set_policy_status(self, policy_id: str, status: str, updated_by: str | None = None) -> bool: ...
    def delete_policy(self, policy_id: str) -> None: ...
    def seed_builtin_policies(self) -> int: ...
    def test_policy(self, policy_id: str, request: SandboxPolicyTestRequest) -> SandboxPolicyTestResult: ...


# ═══════════════════════════════════════════
# Error Classes
# ═══════════════════════════════════════════


class SandboxPolicyNotFoundError(Exception):
    def __init__(self, message: str = "Sandbox Policy 不存在"):
        super().__init__(message)


class SandboxPolicyAlreadyExistsError(Exception):
    def __init__(self, message: str = "Sandbox Policy 已存在"):
        super().__init__(message)


class SandboxPolicyValidationError(Exception):
    def __init__(self, message: str = "Sandbox Policy 校验失败", errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


class SandboxPolicyPermissionError(Exception):
    def __init__(self, message: str = "无权操作此 Sandbox Policy"):
        super().__init__(message)


class SandboxPolicyStateError(Exception):
    def __init__(self, message: str = "Sandbox Policy 状态不允许此操作"):
        super().__init__(message)


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════


def _safe_parse_dt(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)
