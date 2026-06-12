"""Simulation Runtime Domain Model — Developer Agent 安全仿真。

Step 23-D MVP:
- 不执行 package_url
- 不执行 entrypoint
- 不联网
- 不读取真实企业数据
- 不调用 AgentRuntime
- 不注册 AgentRegistry
- simulation output 是 deterministic mock

安全元数据（每个 SimulationRunResult 强制写入）:
- no_remote_code_execution: True
- simulation_only: True
- no_network: True
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


class SimulationRunStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"


class SimulationBlockReason(StrEnum):
    MARKETPLACE_AGENT_NOT_FOUND = "marketplace_agent_not_found"
    NOT_DEVELOPER_AGENT = "not_developer_agent"
    INSTALLATION_REQUIRED = "installation_required"
    PERMISSIONS_REQUIRED = "permissions_required"
    RUNTIME_BINDING_REQUIRED = "runtime_binding_required"
    RUNTIME_BINDING_DISABLED = "runtime_binding_disabled"
    ADAPTER_NOT_SIMULATION = "adapter_not_simulation"
    ADAPTER_NOT_AVAILABLE = "adapter_not_available"
    INSUFFICIENT_API_KEY_SCOPE = "insufficient_api_key_scope"
    TENANT_MISMATCH = "tenant_mismatch"
    UNSAFE_RUNTIME_TYPE = "unsafe_runtime_type"
    PACKAGE_EXECUTION_FORBIDDEN = "package_execution_forbidden"


# ═══════════════════════════════════════════
# SimulationRunRequest
# ═══════════════════════════════════════════


@dataclass
class SimulationRunRequest:
    """仿真运行请求 — 只描述"想模拟什么"，不包含可执行代码。

    安全约束:
    - 不接受 package_url
    - 不接受 entrypoint
    - 不接受 arbitrary code
    - to_dict 不包含 raw_key/key_hash
    """

    marketplace_agent_id: str = ""
    tenant_id: str = ""
    user_id: str | None = None
    developer_id: str | None = None
    input_text: str | None = None
    input_payload: dict[str, Any] = field(default_factory=dict)
    requested_permissions: list[str] = field(default_factory=list)
    api_key_scopes: list[str] = field(default_factory=list)
    auth_type: str = "jwt"  # jwt | developer_api_key
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "marketplace_agent_id": self.marketplace_agent_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "developer_id": self.developer_id,
            "input_text": self.input_text,
            "input_payload": self.input_payload,
            "requested_permissions": list(self.requested_permissions),
            "auth_type": self.auth_type,
            # 不暴露 api_key_scopes 完整列表
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════
# SimulationStep
# ═══════════════════════════════════════════


@dataclass
class SimulationStep:
    """仿真执行中的单个验证/执行步骤。"""

    step_id: str = field(default_factory=lambda: f"simstep_{uuid4().hex[:8]}")
    name: str = ""
    status: str = "pending"  # pending | passed | blocked | skipped
    message: str = ""
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════
# SimulationRunResult
# ═══════════════════════════════════════════


@dataclass
class SimulationRunResult:
    """仿真运行结果 — 不包含任何可执行代码或敏感信息。

    强制安全元数据:
    - metadata.no_remote_code_execution = True
    - metadata.simulation_only = True
    - metadata.no_network = True
    """

    run_id: str = field(default_factory=lambda: f"simrun_{uuid4().hex[:12]}")
    status: str = SimulationRunStatus.BLOCKED
    blocked_reason: str | None = None
    message: str = ""
    marketplace_agent_id: str = ""
    tenant_id: str = ""
    developer_id: str | None = None
    adapter_id: str | None = None
    binding_id: str | None = None
    simulated_output: dict[str, Any] = field(default_factory=dict)
    steps: list[SimulationStep] = field(default_factory=list)
    usage_recorded: bool = False
    metrics_recorded: bool = False
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # 强制写入安全元数据
        self.metadata["no_remote_code_execution"] = True
        self.metadata["simulation_only"] = True
        self.metadata["no_network"] = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "blocked_reason": self.blocked_reason,
            "message": self.message,
            "marketplace_agent_id": self.marketplace_agent_id,
            "tenant_id": self.tenant_id,
            "developer_id": self.developer_id,
            "adapter_id": self.adapter_id,
            "binding_id": self.binding_id,
            "simulated_output": self.simulated_output,
            "steps": [s.to_dict() for s in self.steps],
            "usage_recorded": self.usage_recorded,
            "metrics_recorded": self.metrics_recorded,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SimulationRunResult":
        steps = []
        for s in d.get("steps", []):
            steps.append(SimulationStep(
                step_id=s.get("step_id", ""),
                name=s.get("name", ""),
                status=s.get("status", "pending"),
                message=s.get("message", ""),
                duration_ms=s.get("duration_ms", 0.0),
                metadata=s.get("metadata", {}),
            ))
        sa = _safe_parse_datetime(d.get("started_at"))
        ca = _safe_parse_datetime(d.get("completed_at"))
        return cls(
            run_id=str(d.get("run_id", "")),
            status=str(d.get("status", SimulationRunStatus.BLOCKED)),
            blocked_reason=d.get("blocked_reason"),
            message=str(d.get("message", "")),
            marketplace_agent_id=str(d.get("marketplace_agent_id", "")),
            tenant_id=str(d.get("tenant_id", "")),
            developer_id=d.get("developer_id"),
            adapter_id=d.get("adapter_id"),
            binding_id=d.get("binding_id"),
            simulated_output=dict(d.get("simulated_output", {})),
            steps=steps,
            usage_recorded=bool(d.get("usage_recorded", False)),
            metrics_recorded=bool(d.get("metrics_recorded", False)),
            started_at=sa,
            completed_at=ca,
            duration_ms=float(d.get("duration_ms", 0.0)),
            metadata=dict(d.get("metadata", {})),
        )


def _safe_parse_datetime(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)
