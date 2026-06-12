"""Runtime Adapter & Binding Domain Model — Developer Agent Runtime 管理层。

Step 23 MVP:
- manifest_only adapter (已有，Step 22)
- simulation adapter (新增，不执行代码)
- http_webhook / sandboxed_process / container 预留，默认 disabled

Execution 前置检查:
1. Marketplace installation
2. permissions_granted
3. runtime_binding enabled
4. adapter active + MVP allowed
5. sandbox policy (for sandbox adapters)

安全边界：
- 不执行 package_url
- 不执行 entrypoint
- 不调用 AgentRuntime
- 不注册 AgentRegistry
- 不联网
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


class RuntimeAdapterType(StrEnum):
    MANIFEST_ONLY = "manifest_only"
    SIMULATION = "simulation"
    HTTP_WEBHOOK = "http_webhook"
    SANDBOXED_PROCESS = "sandboxed_process"
    CONTAINER = "container"
    BUILTIN_BRIDGE = "builtin_bridge"


class RuntimeAdapterStatus(StrEnum):
    ACTIVE = "active"
    BETA = "beta"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class RuntimeBindingStatus(StrEnum):
    PENDING = "pending"
    ENABLED = "enabled"
    DISABLED = "disabled"
    SUSPENDED = "suspended"


class RuntimeEligibilityCode(StrEnum):
    ELIGIBLE = "eligible"
    NO_BINDING = "no_binding"
    BINDING_DISABLED = "binding_disabled"
    ADAPTER_DISABLED = "adapter_disabled"
    ADAPTER_NOT_ALLOWED = "adapter_not_allowed"
    SANDBOX_POLICY_REQUIRED = "sandbox_policy_required"
    INSTALLATION_REQUIRED = "installation_required"
    PERMISSIONS_REQUIRED = "permissions_required"
    RUNTIME_NOT_IMPLEMENTED = "runtime_not_implemented"


# ═══════════════════════════════════════════
# MVP Allowed Adapter Types
# ═══════════════════════════════════════════

MVP_ALLOWED_RUNTIME_ADAPTER_TYPES: frozenset[str] = frozenset({
    RuntimeAdapterType.MANIFEST_ONLY,
    RuntimeAdapterType.SIMULATION,
})


def is_mvp_allowed_adapter_type(adapter_type: str) -> bool:
    return adapter_type in MVP_ALLOWED_RUNTIME_ADAPTER_TYPES


# ═══════════════════════════════════════════
# RuntimeAdapter
# ═══════════════════════════════════════════


@dataclass
class RuntimeAdapter:
    """Runtime Adapter — 定义 Developer Agent 可用的执行适配器类型。

    安全约束：
    - 不包含执行函数
    - 不包含 package_url
    - 不包含 network 调用
    - simulation 不支持 network/user_data 读写
    - 非 MVP 类型默认 disabled
    """

    adapter_id: str = field(default_factory=lambda: f"rtadp_{uuid4().hex[:12]}")
    adapter_type: str = RuntimeAdapterType.MANIFEST_ONLY
    name: str = ""
    description: str = ""
    supports_network: bool = False
    supports_user_data_read: bool = False
    supports_user_data_write: bool = False
    sandbox_required: bool = False
    max_timeout_ms: int = 0
    max_memory_mb: int = 0
    status: str = RuntimeAdapterStatus.ACTIVE
    version: str = "1.0.0"
    config_schema: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_active(self) -> bool:
        return self.status in (RuntimeAdapterStatus.ACTIVE, RuntimeAdapterStatus.BETA)

    def is_mvp_allowed(self) -> bool:
        return is_mvp_allowed_adapter_type(self.adapter_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_type": self.adapter_type,
            "name": self.name,
            "description": self.description,
            "supports_network": self.supports_network,
            "supports_user_data_read": self.supports_user_data_read,
            "supports_user_data_write": self.supports_user_data_write,
            "sandbox_required": self.sandbox_required,
            "max_timeout_ms": self.max_timeout_ms,
            "max_memory_mb": self.max_memory_mb,
            "status": self.status,
            "version": self.version,
            "config_schema": self.config_schema,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RuntimeAdapter":
        ca = _safe_parse_datetime(d.get("created_at"))
        ua = _safe_parse_datetime(d.get("updated_at"))
        return cls(
            adapter_id=str(d.get("adapter_id", "")),
            adapter_type=str(d.get("adapter_type", RuntimeAdapterType.MANIFEST_ONLY)),
            name=str(d.get("name", "")),
            description=str(d.get("description", "")),
            supports_network=bool(d.get("supports_network", False)),
            supports_user_data_read=bool(d.get("supports_user_data_read", False)),
            supports_user_data_write=bool(d.get("supports_user_data_write", False)),
            sandbox_required=bool(d.get("sandbox_required", False)),
            max_timeout_ms=int(d.get("max_timeout_ms", 0)),
            max_memory_mb=int(d.get("max_memory_mb", 0)),
            status=str(d.get("status", RuntimeAdapterStatus.ACTIVE)),
            version=str(d.get("version", "1.0.0")),
            config_schema=dict(d.get("config_schema", {})),
            metadata=dict(d.get("metadata", {})),
            created_at=ca,
            updated_at=ua,
        )


# ═══════════════════════════════════════════
# DeveloperAgentRuntimeBinding
# ═══════════════════════════════════════════


@dataclass
class DeveloperAgentRuntimeBinding:
    """Developer Agent 的 Runtime 绑定 — 关联 MarketplaceAgent + Adapter。

    安全约束：
    - publish 不自动创建 binding
    - enable 必须 adapter active + mvp allowed
    - 一个 marketplace_agent_id + tenant_id 只有一个 binding
    - simulation binding 不执行代码
    - sandbox_required adapter 必须关联 sandbox_policy_id
    """

    binding_id: str = field(default_factory=lambda: f"rtbind_{uuid4().hex[:12]}")
    marketplace_agent_id: str = ""
    submission_id: str | None = None
    developer_id: str = ""
    tenant_id: str = ""
    adapter_id: str = ""
    adapter_type: str = RuntimeAdapterType.MANIFEST_ONLY
    runtime_status: str = RuntimeBindingStatus.PENDING
    sandbox_policy_id: str | None = None
    enabled_by: str | None = None
    disabled_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_enabled(self) -> bool:
        return self.runtime_status == RuntimeBindingStatus.ENABLED

    def is_eligible_status(self) -> bool:
        return self.runtime_status in (RuntimeBindingStatus.ENABLED,)

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "marketplace_agent_id": self.marketplace_agent_id,
            "submission_id": self.submission_id,
            "developer_id": self.developer_id,
            "tenant_id": self.tenant_id,
            "adapter_id": self.adapter_id,
            "adapter_type": self.adapter_type,
            "runtime_status": self.runtime_status,
            "sandbox_policy_id": self.sandbox_policy_id,
            "enabled_by": self.enabled_by,
            "disabled_by": self.disabled_by,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DeveloperAgentRuntimeBinding":
        ca = _safe_parse_datetime(d.get("created_at"))
        ua = _safe_parse_datetime(d.get("updated_at"))
        return cls(
            binding_id=str(d.get("binding_id", "")),
            marketplace_agent_id=str(d.get("marketplace_agent_id", "")),
            submission_id=d.get("submission_id"),
            developer_id=str(d.get("developer_id", "")),
            tenant_id=str(d.get("tenant_id", "")),
            adapter_id=str(d.get("adapter_id", "")),
            adapter_type=str(d.get("adapter_type", RuntimeAdapterType.MANIFEST_ONLY)),
            runtime_status=str(d.get("runtime_status", RuntimeBindingStatus.PENDING)),
            sandbox_policy_id=d.get("sandbox_policy_id"),
            enabled_by=d.get("enabled_by"),
            disabled_by=d.get("disabled_by"),
            metadata=dict(d.get("metadata", {})),
            created_at=ca,
            updated_at=ua,
        )


# ═══════════════════════════════════════════
# RuntimeEligibilityResult
# ═══════════════════════════════════════════


@dataclass
class RuntimeEligibilityResult:
    """Developer Agent 是否具备 Runtime 条件的评估结果。

    只做状态判断，不执行代码。
    """

    eligible: bool = False
    code: str = RuntimeEligibilityCode.NO_BINDING
    message: str = ""
    marketplace_agent_id: str = ""
    binding_id: str | None = None
    adapter_id: str | None = None
    adapter_type: str | None = None
    required_action: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "code": self.code,
            "message": self.message,
            "marketplace_agent_id": self.marketplace_agent_id,
            "binding_id": self.binding_id,
            "adapter_id": self.adapter_id,
            "adapter_type": self.adapter_type,
            "required_action": self.required_action,
            "metadata": self.metadata,
        }

    @classmethod
    def not_found(cls, mkp_id: str) -> "RuntimeEligibilityResult":
        return cls(
            eligible=False,
            code=RuntimeEligibilityCode.NO_BINDING,
            message="No runtime binding found for this developer agent.",
            marketplace_agent_id=mkp_id,
            required_action="Admin must create and enable a runtime binding.",
        )


# ═══════════════════════════════════════════
# RuntimeStore Protocol
# ═══════════════════════════════════════════


@runtime_checkable
class RuntimeStore(Protocol):
    """Runtime Adapter + Binding 存储协议。

    禁止：
    - 执行 package_url
    - 执行 entrypoint
    - 调用 AgentRuntime
    - 注册 AgentRegistry
    """

    # ── Adapter ──

    def create_adapter(self, adapter: RuntimeAdapter) -> RuntimeAdapter: ...
    def get_adapter(self, adapter_id: str) -> RuntimeAdapter | None: ...
    def get_adapter_by_type(self, adapter_type: str) -> RuntimeAdapter | None: ...
    def list_adapters(
        self, *, status: str = "", mvp_only: bool = False,
    ) -> list[RuntimeAdapter]: ...
    def update_adapter(self, adapter: RuntimeAdapter) -> None: ...
    def set_adapter_status(self, adapter_id: str, status: str) -> bool: ...
    def seed_builtin_adapters(self) -> int: ...

    # ── Binding ──

    def create_binding(self, binding: DeveloperAgentRuntimeBinding) -> DeveloperAgentRuntimeBinding: ...
    def get_binding(self, binding_id: str) -> DeveloperAgentRuntimeBinding | None: ...
    def get_binding_by_marketplace_agent(
        self, marketplace_agent_id: str, tenant_id: str | None = None,
    ) -> DeveloperAgentRuntimeBinding | None: ...
    def list_bindings(
        self, *, developer_id: str = "", tenant_id: str = "",
        runtime_status: str = "", adapter_type: str = "",
    ) -> list[DeveloperAgentRuntimeBinding]: ...
    def update_binding(self, binding: DeveloperAgentRuntimeBinding) -> None: ...
    def enable_binding(self, binding_id: str, enabled_by: str) -> None: ...
    def disable_binding(self, binding_id: str, disabled_by: str) -> None: ...
    def suspend_binding(self, binding_id: str, disabled_by: str) -> None: ...
    def set_binding_sandbox_policy(
        self, binding_id: str, sandbox_policy_id: str,
    ) -> None: ...

    # ── Eligibility ──

    def get_runtime_eligibility(
        self, marketplace_agent_id: str, tenant_id: str | None = None,
    ) -> RuntimeEligibilityResult: ...


# ═══════════════════════════════════════════
# Error Classes
# ═══════════════════════════════════════════


class RuntimeAdapterNotFoundError(Exception):
    def __init__(self, message: str = "Runtime Adapter 不存在"):
        super().__init__(message)


class RuntimeBindingNotFoundError(Exception):
    def __init__(self, message: str = "Runtime Binding 不存在"):
        super().__init__(message)


class RuntimeAdapterAlreadyExistsError(Exception):
    def __init__(self, message: str = "Runtime Adapter 已存在"):
        super().__init__(message)


class RuntimeBindingAlreadyExistsError(Exception):
    def __init__(self, message: str = "Runtime Binding 已存在"):
        super().__init__(message)


class RuntimeAdapterNotAllowedError(Exception):
    def __init__(self, message: str = "此 adapter 类型在 MVP 阶段不允许启用"):
        super().__init__(message)


class RuntimeStateError(Exception):
    def __init__(self, message: str = "Runtime 状态转换不允许"):
        super().__init__(message)


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════


def _safe_parse_datetime(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)
