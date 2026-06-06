"""Agent Registry — 企业 Agent 注册中心。

管理 Agent 的注册、发现、启用/停用、配置、版本管理。
内置 6 个 Agent：Knowledge / Meeting / Research / Sales / Support / Training
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.agents.runtime import (
    Agent,
    AgentContext,
    AgentResult,
    AgentStatus,
    AgentTask,
    KnowledgeGraphProvider,
    MemoryProvider,
    ToolProvider,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentRegistration:
    """Agent 注册信息。"""
    agent_id: str
    name: str
    description: str
    version: str = "1.0.0"
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    usage_count: int = 0
    success_count: int = 0
    avg_duration_ms: float = 0.0

    def record_usage(self, result: AgentResult) -> None:
        self.usage_count += 1
        if result.success:
            self.success_count += 1
        # 指数移动平均
        alpha = 0.1
        self.avg_duration_ms = (
            alpha * result.duration_ms + (1 - alpha) * self.avg_duration_ms
            if self.avg_duration_ms > 0
            else result.duration_ms
        )

    @property
    def success_rate(self) -> float:
        if self.usage_count == 0:
            return 1.0
        return self.success_count / self.usage_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "enabled": self.enabled,
            "config": self.config,
            "tags": self.tags,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "success_rate": round(self.success_rate, 4),
            "avg_duration_ms": round(self.avg_duration_ms, 1),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class AgentRegistry:
    """Agent 注册中心。

    管理所有已注册 Agent 的生命周期：
    - 注册 / 注销
    - 启用 / 停用
    - 配置更新
    - 版本管理
    - 按名称/tag 查询
    """

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._registrations: dict[str, AgentRegistration] = {}
        self._tools: ToolProvider | None = None
        self._memory: MemoryProvider | None = None
        self._kg: KnowledgeGraphProvider | None = None

    # ── 依赖注入 ──

    def set_providers(
        self,
        tools: ToolProvider | None = None,
        memory: MemoryProvider | None = None,
        kg: KnowledgeGraphProvider | None = None,
    ) -> None:
        self._tools = tools
        self._memory = memory
        self._kg = kg

    # ── 注册 / 注销 ──

    def register(self, agent: Agent, enabled: bool = True, config: dict[str, Any] | None = None) -> None:
        if agent.agent_id in self._agents:
            logger.warning("agent_already_registered", extra={"agent_id": agent.agent_id})
            return

        self._agents[agent.agent_id] = agent
        self._registrations[agent.agent_id] = AgentRegistration(
            agent_id=agent.agent_id,
            name=agent.name,
            description=agent.description,
            version=agent.version,
            enabled=enabled,
            config=config or {},
        )
        logger.info("agent_registered", extra={"agent_id": agent.agent_id, "agent_name": agent.name})

    def unregister(self, agent_id: str) -> bool:
        if agent_id not in self._agents:
            return False
        del self._agents[agent_id]
        del self._registrations[agent_id]
        logger.info("agent_unregistered", extra={"agent_id": agent_id})
        return True

    # ── 启用 / 停用 ──

    def enable(self, agent_id: str) -> bool:
        reg = self._registrations.get(agent_id)
        if reg is None:
            return False
        reg.enabled = True
        reg.updated_at = datetime.now(timezone.utc)
        return True

    def disable(self, agent_id: str) -> bool:
        reg = self._registrations.get(agent_id)
        if reg is None:
            return False
        reg.enabled = False
        reg.updated_at = datetime.now(timezone.utc)
        return True

    # ── 配置管理 ──

    def update_config(self, agent_id: str, config: dict[str, Any]) -> bool:
        reg = self._registrations.get(agent_id)
        if reg is None:
            return False
        reg.config.update(config)
        reg.updated_at = datetime.now(timezone.utc)
        return True

    def get_config(self, agent_id: str) -> dict[str, Any] | None:
        reg = self._registrations.get(agent_id)
        return dict(reg.config) if reg else None

    # ── 版本管理 ──

    def upgrade(self, agent_id: str, new_agent: Agent) -> bool:
        """升级 Agent 版本：替换实例但保留注册信息和统计数据。"""
        old_reg = self._registrations.get(agent_id)
        if old_reg is None:
            return False
        old_reg.version = new_agent.version
        old_reg.updated_at = datetime.now(timezone.utc)
        self._agents[agent_id] = new_agent
        logger.info("agent_upgraded", extra={"agent_id": agent_id, "version": new_agent.version})
        return True

    # ── 查询 ──

    def get(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def get_registration(self, agent_id: str) -> AgentRegistration | None:
        return self._registrations.get(agent_id)

    def list_all(self) -> list[AgentRegistration]:
        return list(self._registrations.values())

    def list_enabled(self) -> list[AgentRegistration]:
        return [r for r in self._registrations.values() if r.enabled]

    def list_by_tag(self, tag: str) -> list[AgentRegistration]:
        return [r for r in self._registrations.values() if tag in r.tags]

    def list_by_name(self, name: str) -> list[AgentRegistration]:
        name_lower = name.lower()
        return [r for r in self._registrations.values() if name_lower in r.name.lower()]

    # ── 执行 ──

    def run(self, agent_id: str, task: AgentTask) -> AgentResult | None:
        agent = self._agents.get(agent_id)
        reg = self._registrations.get(agent_id)
        if agent is None or reg is None:
            logger.warning("agent_not_found", extra={"agent_id": agent_id})
            return None
        if not reg.enabled:
            logger.warning("agent_disabled", extra={"agent_id": agent_id})
            return None

        result = agent.run(task)
        reg.record_usage(result)
        return result

    # ── 统计 ──

    def get_stats(self) -> dict[str, Any]:
        total = len(self._registrations)
        enabled_count = sum(1 for r in self._registrations.values() if r.enabled)
        total_usage = sum(r.usage_count for r in self._registrations.values())
        return {
            "total_agents": total,
            "enabled_agents": enabled_count,
            "disabled_agents": total - enabled_count,
            "total_usage": total_usage,
            "total_success": sum(r.success_count for r in self._registrations.values()),
            "agents": [r.to_dict() for r in self._registrations.values()],
        }

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._agents
