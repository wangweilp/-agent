"""Agent Metrics — Agent 执行指标收集与分析。

对接现有 UsageStore 体系，记录 Agent 执行事件用于 Growth Analytics。
不重复造 Analytics 系统，复用现有 usage_events 表结构。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from src.agents.runtime import AgentResult

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# Metrics Event
# ═══════════════════════════════════════════


@dataclass
class AgentUsageEvent:
    """Agent 使用事件 — 映射到 usage_events 表。"""
    agent_id: str
    agent_name: str
    tenant_id: str = ""
    user_id: str = ""
    task_id: str = ""
    success: bool = False
    duration_ms: float = 0.0
    tool_calls: int = 0
    memory_calls: int = 0
    kg_calls: int = 0
    tokens_used: int = 0
    department: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════
# Metrics Collector Protocol
# ═══════════════════════════════════════════


class AgentMetricsStore(Protocol):
    """Agent 指标存储协议 — 对接现有 UsageStore。"""

    def record_event(self, event: AgentUsageEvent) -> None: ...

    def get_agent_stats(
        self,
        tenant_id: str = "",
        days: int = 30,
    ) -> dict[str, Any]: ...

    def get_department_distribution(self, tenant_id: str = "") -> dict[str, int]: ...

    def get_tenant_distribution(self) -> dict[str, int]: ...


# ═══════════════════════════════════════════
# In-Memory Metrics Store (standalone, no DB dependency)
# ═══════════════════════════════════════════


class InMemoryAgentMetricsStore:
    """内存 Agent 指标存储 — 轻量实现，可选对接 UsageStore。

    生产环境可注入 usage_store_adapter 实现持久化到 usage_events 表。
    """

    def __init__(self, usage_store: Any = None) -> None:
        self._events: list[AgentUsageEvent] = []
        self._usage_store = usage_store  # 可选的 UsageStoreAdapter

    def record_event(self, event: AgentUsageEvent) -> None:
        self._events.append(event)
        # 限制内存占用
        if len(self._events) > 100_000:
            self._events = self._events[-50_000:]

        # 持久化到 UsageStore（如果已注入）
        if self._usage_store is not None:
            try:
                self._usage_store.record_event(
                    tenant_id=event.tenant_id,
                    user_id=event.user_id,
                    resource="agent_run" if not event.task_id.startswith("wf_") else "workflow_run",
                    quantity=1,
                    metadata={
                        "agent_id": event.agent_id,
                        "agent_name": event.agent_name,
                        "task_id": event.task_id,
                        "success": event.success,
                        "duration_ms": event.duration_ms,
                        "tool_calls": event.tool_calls,
                        "memory_calls": event.memory_calls,
                        "kg_calls": event.kg_calls,
                        "tokens_used": event.tokens_used,
                        "department": event.department,
                    },
                )
            except Exception:
                pass  # 持久化失败不阻塞 Agent 执行

    def get_agent_stats(self, tenant_id: str = "", days: int = 30) -> dict[str, Any]:
        cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
        events = [
            e for e in self._events
            if e.timestamp.timestamp() >= cutoff
            and (not tenant_id or e.tenant_id == tenant_id)
        ]

        # 按 Agent 聚合
        agent_stats: dict[str, dict[str, Any]] = {}
        for e in events:
            if e.agent_id not in agent_stats:
                agent_stats[e.agent_id] = {
                    "agent_id": e.agent_id,
                    "agent_name": e.agent_name,
                    "total_calls": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "total_duration_ms": 0.0,
                    "total_tool_calls": 0,
                    "total_memory_calls": 0,
                    "total_kg_calls": 0,
                    "total_tokens": 0,
                }
            s = agent_stats[e.agent_id]
            s["total_calls"] += 1
            if e.success:
                s["success_count"] += 1
            else:
                s["failure_count"] += 1
            s["total_duration_ms"] += e.duration_ms
            s["total_tool_calls"] += e.tool_calls
            s["total_memory_calls"] += e.memory_calls
            s["total_kg_calls"] += e.kg_calls
            s["total_tokens"] += e.tokens_used

        result = []
        for agent_id, s in agent_stats.items():
            total = s["total_calls"]
            result.append({
                **s,
                "success_rate": round(s["success_count"] / max(total, 1), 4),
                "failure_rate": round(s["failure_count"] / max(total, 1), 4),
                "avg_duration_ms": round(s["total_duration_ms"] / max(total, 1), 1),
                "knowledge_utilization": round(
                    (s["total_memory_calls"] + s["total_kg_calls"]) / max(total, 1), 2
                ),
            })

        return {
            "total_events": len(events),
            "total_calls": sum(s["total_calls"] for s in agent_stats.values()),
            "agents": result,
        }

    def get_department_distribution(self, tenant_id: str = "") -> dict[str, int]:
        events = [e for e in self._events if not tenant_id or e.tenant_id == tenant_id]
        dist: dict[str, int] = {}
        for e in events:
            dept = e.department or "未分类"
            dist[dept] = dist.get(dept, 0) + 1
        return dict(sorted(dist.items(), key=lambda x: -x[1]))

    def get_tenant_distribution(self) -> dict[str, int]:
        dist: dict[str, int] = {}
        for e in self._events:
            tid = e.tenant_id or "未知租户"
            dist[tid] = dist.get(tid, 0) + 1
        return dict(sorted(dist.items(), key=lambda x: -x[1]))

    def get_recent_executions(self, limit: int = 20) -> list[dict[str, Any]]:
        recent = self._events[-limit:]
        return [
            {
                "task_id": e.task_id,
                "agent_id": e.agent_id,
                "agent_name": e.agent_name,
                "success": e.success,
                "duration_ms": e.duration_ms,
                "tenant_id": e.tenant_id,
                "user_id": e.user_id,
                "department": e.department,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in reversed(recent)
        ]

    def reset(self) -> None:
        self._events.clear()


# ═══════════════════════════════════════════
# Factory
# ═══════════════════════════════════════════


_global_metrics_store: InMemoryAgentMetricsStore | None = None


def get_agent_metrics_store() -> InMemoryAgentMetricsStore:
    global _global_metrics_store
    if _global_metrics_store is None:
        _global_metrics_store = InMemoryAgentMetricsStore()
    return _global_metrics_store
