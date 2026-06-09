"""Agent Metrics 单元测试。"""
import pytest
from datetime import datetime, timezone

from src.agents.metrics import (
    AgentUsageEvent,
    InMemoryAgentMetricsStore,
    get_agent_metrics_store,
)


class TestAgentUsageEvent:
    def test_event_creation(self):
        event = AgentUsageEvent(
            agent_id="agent-1",
            agent_name="Test Agent",
            tenant_id="t1",
            user_id="u1",
            success=True,
            duration_ms=100.5,
            tool_calls=2,
            memory_calls=3,
            kg_calls=1,
            tokens_used=500,
            department="研发部",
        )
        assert event.agent_id == "agent-1"
        assert event.success is True
        assert event.duration_ms == 100.5

    def test_event_default_values(self):
        event = AgentUsageEvent(agent_id="a1", agent_name="test")
        assert event.tenant_id == ""
        assert event.user_id == ""
        assert event.success is False
        assert event.duration_ms == 0.0


class TestInMemoryAgentMetricsStore:
    def test_record_and_get_stats(self):
        store = InMemoryAgentMetricsStore()
        store.record_event(AgentUsageEvent(
            agent_id="a1", agent_name="Agent One",
            success=True, duration_ms=100, department="研发",
        ))
        store.record_event(AgentUsageEvent(
            agent_id="a1", agent_name="Agent One",
            success=False, duration_ms=200, department="研发",
        ))
        store.record_event(AgentUsageEvent(
            agent_id="a2", agent_name="Agent Two",
            success=True, duration_ms=50, department="销售",
        ))

        stats = store.get_agent_stats(days=30)
        assert stats["total_events"] == 3
        assert stats["total_calls"] == 3
        assert len(stats["agents"]) == 2
        a1 = next(a for a in stats["agents"] if a["agent_id"] == "a1")
        assert a1["total_calls"] == 2
        assert a1["success_count"] == 1
        assert a1["failure_count"] == 1
        assert a1["success_rate"] == 0.5
        assert a1["avg_duration_ms"] == 150.0

    def test_get_department_distribution(self):
        store = InMemoryAgentMetricsStore()
        store.record_event(AgentUsageEvent(agent_id="a1", agent_name="A", department="研发"))
        store.record_event(AgentUsageEvent(agent_id="a2", agent_name="B", department="研发"))
        store.record_event(AgentUsageEvent(agent_id="a3", agent_name="C", department="销售"))

        dist = store.get_department_distribution()
        assert dist["研发"] == 2
        assert dist["销售"] == 1

    def test_get_tenant_distribution(self):
        store = InMemoryAgentMetricsStore()
        store.record_event(AgentUsageEvent(agent_id="a1", agent_name="A", tenant_id="t1"))
        store.record_event(AgentUsageEvent(agent_id="a2", agent_name="B", tenant_id="t1"))
        store.record_event(AgentUsageEvent(agent_id="a3", agent_name="C", tenant_id="t2"))

        dist = store.get_tenant_distribution()
        assert dist["t1"] == 2
        assert dist["t2"] == 1

    def test_tenant_filtering(self):
        store = InMemoryAgentMetricsStore()
        store.record_event(AgentUsageEvent(agent_id="a1", agent_name="A", tenant_id="t1"))
        store.record_event(AgentUsageEvent(agent_id="a2", agent_name="B", tenant_id="t2"))

        stats_t1 = store.get_agent_stats(tenant_id="t1")
        assert stats_t1["total_events"] == 1

    def test_recent_executions(self):
        store = InMemoryAgentMetricsStore()
        store.record_event(AgentUsageEvent(agent_id="a1", agent_name="A", task_id="task-1"))
        store.record_event(AgentUsageEvent(agent_id="a2", agent_name="B", task_id="task-2"))

        recent = store.get_recent_executions(limit=5)
        assert len(recent) == 2
        assert recent[0]["task_id"] == "task-2"  # 最新在前

    def test_reset(self):
        store = InMemoryAgentMetricsStore()
        store.record_event(AgentUsageEvent(agent_id="a1", agent_name="A"))
        assert store.get_agent_stats()["total_events"] == 1
        store.reset()
        assert store.get_agent_stats()["total_events"] == 0

    def test_days_cutoff(self):
        """超过 days 的事件不计入。"""
        store = InMemoryAgentMetricsStore()
        # 直接操作内部列表，设置旧时间戳
        old_event = AgentUsageEvent(
            agent_id="a1", agent_name="A",
            timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        store._events.append(old_event)
        stats = store.get_agent_stats(days=30)
        assert stats["total_events"] == 0  # 过期事件不计入


class TestGlobalMetricsStore:
    def test_singleton_pattern(self):
        store1 = get_agent_metrics_store()
        store2 = get_agent_metrics_store()
        assert store1 is store2
