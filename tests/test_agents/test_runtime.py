"""Agent Runtime 单元测试 — PEOR 循环、协议、上下文、任务、结果。"""

import pytest
from datetime import datetime, timezone

from src.agents.runtime import (
    Agent,
    AgentContext,
    AgentResult,
    AgentStatus,
    AgentTask,
    BaseAgent,
    MemoryProvider,
    MemoryResult,
    KnowledgeGraphProvider,
    GraphEntity,
    GraphRelation,
    ToolDefinition,
    ToolCallResult,
    TaskPriority,
)


# ═══════════════════════════════════════════
# 测试用 Memory Provider
# ═══════════════════════════════════════════


class FakeMemoryProvider:
    def search(self, query: str, top_k: int = 5) -> list[MemoryResult]:
        return [
            MemoryResult(
                memory_id=f"mem-{i}",
                content=f"关于 {query} 的记忆 {i}",
                score=0.9 - i * 0.1,
            )
            for i in range(min(top_k, 3))
        ]

    def remember(self, content: str, metadata: dict | None = None) -> str:
        return f"mem-new-{hash(content) % 10000}"


class FakeKGProvider:
    def query_entities(self, query: str, top_k: int = 10) -> list[GraphEntity]:
        return [
            GraphEntity(id=f"e{i}", name=f"{query}_entity_{i}", entity_type="concept")
            for i in range(min(top_k, 3))
        ]

    def query_relations(self, entity_id: str) -> list[GraphRelation]:
        return [
            GraphRelation(source=entity_id, target="other", predicate="related_to"),
        ]

    def traverse(self, start_id: str, depth: int = 2) -> dict:
        return {"entities": ["a", "b"], "relations": [{"source": "a", "target": "b", "predicate": "linked"}]}


# ═══════════════════════════════════════════
# 测试用 Agent 实现
# ═══════════════════════════════════════════


class EchoAgent(BaseAgent):
    """最简 Agent — 直接返回输入。"""
    def __init__(self, **kwargs):
        super().__init__(
            agent_id="test-echo",
            name="Echo Agent",
            description="Echo test agent",
            **kwargs,
        )

    def execute(self, context, task, plan):
        return f"Echo: {task.description}"


class FailingAgent(BaseAgent):
    """会失败的 Agent。"""
    def __init__(self, **kwargs):
        super().__init__(
            agent_id="test-failing",
            name="Failing Agent",
            **kwargs,
        )

    def execute(self, context, task, plan):
        raise RuntimeError("模拟执行失败")


class CountingAgent(BaseAgent):
    """带计数的 Agent — 测试指标收集。"""
    def __init__(self, **kwargs):
        super().__init__(
            agent_id="test-counting",
            name="Counting Agent",
            **kwargs,
        )
        self._run_count = 0

    def execute(self, context, task, plan):
        self._run_count += 1
        return f"执行第 {self._run_count} 次"


class ReflectiveAgent(BaseAgent):
    """需要反思修正的 Agent — 首次输出不完整，反思后补充。"""
    def __init__(self, **kwargs):
        super().__init__(agent_id="test-reflective", name="Reflective Agent", **kwargs)
        self._attempt = 0

    def execute(self, context, task, plan):
        self._attempt += 1
        if self._attempt == 1:
            return "短"  # 太短，触发反思
        return f"这是完整的输出: {task.description}，包含{len(plan)}个步骤的详细分析。"

    def reflect(self, context, observations, output):
        if self._attempt == 1 and len(output) < 50:
            return False, "输出太短，请补充更多细节"
        return True, "完成"


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════


@pytest.fixture
def memory_provider():
    return FakeMemoryProvider()


@pytest.fixture
def kg_provider():
    return FakeKGProvider()


@pytest.fixture
def sample_task():
    return AgentTask(
        title="测试任务",
        description="这是一个测试任务",
        priority=TaskPriority.MEDIUM,
    )


@pytest.fixture
def context(memory_provider, kg_provider):
    return AgentContext(
        agent_id="test-agent",
        agent_name="Test Agent",
        tools=None,
        memory=memory_provider,
        knowledge_graph=kg_provider,
    )


# ═══════════════════════════════════════════
# AgentContext 测试
# ═══════════════════════════════════════════


class TestAgentContext:
    def test_creation(self):
        ctx = AgentContext(agent_id="a1", agent_name="Test")
        assert ctx.agent_id == "a1"
        assert ctx.agent_name == "Test"
        assert ctx.status == AgentStatus.IDLE
        assert ctx.conversation_history == []

    def test_record_metric(self):
        ctx = AgentContext(agent_id="a1", agent_name="Test")
        ctx.record_metric("key1", 100)
        assert ctx.metrics["key1"] == 100

    def test_add_to_history(self):
        ctx = AgentContext(agent_id="a1", agent_name="Test")
        ctx.add_to_history("user", "hello")
        assert len(ctx.conversation_history) == 1
        assert ctx.conversation_history[0]["role"] == "user"
        assert ctx.conversation_history[0]["content"] == "hello"

    def test_created_at_is_utc(self):
        ctx = AgentContext(agent_id="a1", agent_name="Test")
        assert ctx.created_at.tzinfo is not None


# ═══════════════════════════════════════════
# AgentTask 测试
# ═══════════════════════════════════════════


class TestAgentTask:
    def test_default_values(self):
        task = AgentTask()
        assert task.task_id != ""
        assert task.priority == TaskPriority.MEDIUM

    def test_custom_values(self):
        task = AgentTask(
            title="紧急任务",
            description="需要立即处理",
            priority=TaskPriority.CRITICAL,
            tags=["urgent", "production"],
        )
        assert task.title == "紧急任务"
        assert task.priority == TaskPriority.CRITICAL
        assert "urgent" in task.tags


# ═══════════════════════════════════════════
# AgentResult 测试
# ═══════════════════════════════════════════


class TestAgentResult:
    def test_success_result(self):
        result = AgentResult(
            task_id="t1",
            agent_id="a1",
            agent_name="Test",
            success=True,
            output="Hello",
            duration_ms=150.0,
        )
        assert result.success
        assert result.output == "Hello"

    def test_to_dict(self):
        result = AgentResult(
            task_id="t1",
            agent_id="a1",
            agent_name="Test",
            success=True,
            output="Hello",
            plan=["step1", "step2"],
            observations=["obs1"],
            reflections=["ref1"],
            tool_calls_count=3,
            memory_calls_count=2,
            kg_calls_count=1,
            duration_ms=150.0,
        )
        d = result.to_dict()
        assert d["task_id"] == "t1"
        assert d["success"] is True
        assert d["plan"] == ["step1", "step2"]
        assert d["tool_calls_count"] == 3

    def test_failure_result(self):
        result = AgentResult(
            task_id="t1",
            agent_id="a1",
            agent_name="Test",
            success=False,
            error="Something went wrong",
        )
        assert not result.success
        assert result.error == "Something went wrong"


# ═══════════════════════════════════════════
# Agent PEOR 循环测试
# ═══════════════════════════════════════════


class TestAgentPEOR:
    def test_echo_agent_run(self, sample_task):
        agent = EchoAgent()
        result = agent.run(sample_task)
        assert result.success
        assert "Echo:" in result.output
        assert result.agent_id == "test-echo"
        assert result.duration_ms >= 0
        assert len(result.plan) == 4  # BaseAgent default plan

    def test_agent_status_transitions(self, sample_task):
        agent = EchoAgent()
        assert agent.status == AgentStatus.IDLE
        agent.run(sample_task)
        assert agent.status == AgentStatus.DONE

    def test_failing_agent(self, sample_task):
        agent = FailingAgent()
        result = agent.run(sample_task)
        assert not result.success
        assert result.error is not None
        assert "模拟执行失败" in result.error

    def test_counting_agent_metrics(self, sample_task):
        agent = CountingAgent()
        agent.run(sample_task)
        agent.run(sample_task)
        agent.run(sample_task)
        metrics = agent.metrics
        assert metrics["total_runs"] == 3
        assert metrics["successful_runs"] == 3
        assert agent.get_success_rate() == 1.0
        assert agent.get_avg_duration_ms() > 0

    def test_reflective_agent_retry(self, sample_task):
        agent = ReflectiveAgent()
        result = agent.run(sample_task)
        # 首次输出短，触发反思后再执行一次
        assert result.success
        assert agent._attempt >= 1

    def test_agent_with_providers(self, sample_task):
        agent = EchoAgent(
            memory=FakeMemoryProvider(),
            knowledge_graph=FakeKGProvider(),
        )
        result = agent.run(sample_task)
        assert result.success

    def test_base_agent_default_plan(self, sample_task):
        agent = EchoAgent()
        result = agent.run(sample_task)
        assert len(result.plan) == 4
        assert any("分析任务" in p for p in result.plan)

    def test_base_agent_observe(self, context, sample_task):
        agent = EchoAgent(memory=FakeMemoryProvider())
        observations = agent.observe(context, "some output")
        assert len(observations) >= 1
        assert any("输出长度" in o for o in observations)

    def test_base_agent_reflect_done(self, context):
        agent = EchoAgent()
        done, msg = agent.reflect(context, [], "valid output")
        assert done is True
        assert "完成" in msg

    def test_base_agent_reflect_empty(self, context):
        agent = EchoAgent()
        done, msg = agent.reflect(context, [], "")
        assert done is False
        assert "空" in msg


# ═══════════════════════════════════════════
# Tool Calling 测试
# ═══════════════════════════════════════════


class TestToolDefinition:
    def test_to_openai_tool(self):
        td = ToolDefinition(
            name="search",
            description="搜索文档",
            parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        )
        tool = td.to_openai_tool()
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "search"
        assert "properties" in tool["function"]["parameters"]


class TestToolCallResult:
    def test_success(self):
        r = ToolCallResult(tool_name="test", success=True, content="OK")
        assert r.success
        assert r.content == "OK"

    def test_failure(self):
        r = ToolCallResult(tool_name="test", success=False, error="fail", content="")
        assert not r.success
        assert r.error == "fail"


# ═══════════════════════════════════════════
# Memory Calling 测试
# ═══════════════════════════════════════════


class TestMemoryProvider:
    def test_fake_search(self, memory_provider):
        results = memory_provider.search("test", top_k=3)
        assert len(results) == 3
        assert all(isinstance(r, MemoryResult) for r in results)
        assert results[0].score > results[-1].score

    def test_fake_remember(self, memory_provider):
        mid = memory_provider.remember("important info")
        assert mid.startswith("mem-new-")


# ═══════════════════════════════════════════
# KG Calling 测试
# ═══════════════════════════════════════════


class TestKGProvider:
    def test_fake_query_entities(self, kg_provider):
        entities = kg_provider.query_entities("AI")
        assert len(entities) == 3
        assert all(isinstance(e, GraphEntity) for e in entities)

    def test_fake_query_relations(self, kg_provider):
        rels = kg_provider.query_relations("e1")
        assert len(rels) == 1
        assert rels[0].predicate == "related_to"

    def test_fake_traverse(self, kg_provider):
        result = kg_provider.traverse("start")
        assert "entities" in result
        assert "relations" in result


# ═══════════════════════════════════════════
# AgentStatus 枚举测试
# ═══════════════════════════════════════════


class TestAgentStatus:
    def test_all_statuses(self):
        assert AgentStatus.IDLE.value == "idle"
        assert AgentStatus.PLANNING.value == "planning"
        assert AgentStatus.EXECUTING.value == "executing"
        assert AgentStatus.OBSERVING.value == "observing"
        assert AgentStatus.REFLECTING.value == "reflecting"
        assert AgentStatus.DONE.value == "done"
        assert AgentStatus.FAILED.value == "failed"

    def test_task_priorities(self):
        assert TaskPriority.LOW.value == "low"
        assert TaskPriority.CRITICAL.value == "critical"
