"""Agent Workflow Node Types — Tool, Memory, KnowledgeGraph 节点测试。"""
import pytest

from src.agents.workflow import (
    NodeType,
    Workflow,
    WorkflowEngine,
    WorkflowNode,
    WorkflowStatus,
)
from src.agents.registry import AgentRegistry
from src.agents.runtime import (
    AgentResult,
    MemoryResult,
    ToolCallResult,
)
from src.agents.builtin.knowledge_agent import KnowledgeAgent


# ═══════════════════════════════════════════
# Fake providers for node testing
# ═══════════════════════════════════════════


class FakeMemoryForWorkflow:
    def search(self, query, top_k=5):
        return [MemoryResult(memory_id="m1", content=f"Memory: {query}", score=0.95)]

    def remember(self, content, metadata=None):
        return f"mem-{hash(content) % 1000}"


class FakeKGForWorkflow:
    def query_entities(self, query, top_k=10):
        from src.agents.runtime import GraphEntity
        return [GraphEntity(id="e1", name=f"Entity: {query}", entity_type="concept")]

    def query_relations(self, entity_id):
        from src.agents.runtime import GraphRelation
        return [GraphRelation(source=entity_id, target="e2", predicate="related_to")]

    def traverse(self, start_id, depth=2):
        return {"entities": ["e1", "e2"], "relations": [{"source": "e1", "target": "e2", "predicate": "related_to"}]}


class FakeToolProvider:
    def list_tools(self):
        return []

    def execute(self, tool_name, arguments):
        return ToolCallResult(
            tool_name=tool_name,
            success=True,
            content=f"Tool {tool_name} executed with {arguments}",
            metadata={"args": arguments},
        )


# ═══════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════


class TestNodeTypes:
    """NodeType 枚举包含所有需要的类型。"""

    def test_all_node_types_exist(self):
        assert NodeType.AGENT == "agent"
        assert NodeType.HUMAN == "human"
        assert NodeType.CONDITION == "condition"
        assert NodeType.PARALLEL == "parallel"
        assert NodeType.TOOL == "tool"
        assert NodeType.MEMORY == "memory"
        assert NodeType.KNOWLEDGE_GRAPH == "knowledge_graph"
        assert NodeType.START == "start"
        assert NodeType.END == "end"


class TestToolNodeExecution:
    """工具节点执行测试。"""

    def test_tool_node_execution(self):
        registry = AgentRegistry()
        registry.set_providers(tools=FakeToolProvider())

        engine = WorkflowEngine(registry)
        wf = Workflow(name="Tool Test")
        start = WorkflowNode(name="start", node_type=NodeType.START)
        tool_node = WorkflowNode(
            name="call_tool",
            node_type=NodeType.TOOL,
            config={"tool_name": "test_tool", "tool_args": {"key": "val"}},
        )
        end = WorkflowNode(name="end", node_type=NodeType.END)
        wf.add_node(start)
        wf.add_node(tool_node)
        wf.add_node(end)
        wf.set_start(start.node_id)
        wf.connect(start.node_id, tool_node.node_id)
        wf.connect(tool_node.node_id, end.node_id)

        engine.register_workflow(wf)
        execution = engine.execute(wf.workflow_id)
        assert execution.status == WorkflowStatus.COMPLETED
        assert tool_node.node_id in execution.node_results
        result = execution.node_results[tool_node.node_id]
        assert result.success
        assert "test_tool" in result.output

    def test_tool_node_no_provider(self):
        registry = AgentRegistry()
        engine = WorkflowEngine(registry)
        wf = Workflow(name="Tool No Provider")
        start = WorkflowNode(name="start", node_type=NodeType.START)
        tool_node = WorkflowNode(name="call_tool", node_type=NodeType.TOOL, config={"tool_name": "missing"})
        end = WorkflowNode(name="end", node_type=NodeType.END)
        wf.add_node(start); wf.add_node(tool_node); wf.add_node(end)
        wf.set_start(start.node_id)
        wf.connect(start.node_id, tool_node.node_id)
        wf.connect(tool_node.node_id, end.node_id)

        engine.register_workflow(wf)
        execution = engine.execute(wf.workflow_id)
        assert execution.status == WorkflowStatus.FAILED


class TestMemoryNodeExecution:
    """记忆节点执行测试。"""

    def test_memory_search_node(self):
        registry = AgentRegistry()
        registry.set_providers(memory=FakeMemoryForWorkflow())

        engine = WorkflowEngine(registry)
        wf = Workflow(name="Memory Search")
        start = WorkflowNode(name="start", node_type=NodeType.START)
        mem_node = WorkflowNode(
            name="search_memory",
            node_type=NodeType.MEMORY,
            config={"action": "search", "query": "test query"},
        )
        end = WorkflowNode(name="end", node_type=NodeType.END)
        for n in [start, mem_node, end]: wf.add_node(n)
        wf.set_start(start.node_id)
        wf.connect(start.node_id, mem_node.node_id)
        wf.connect(mem_node.node_id, end.node_id)

        engine.register_workflow(wf)
        execution = engine.execute(wf.workflow_id)
        assert execution.status == WorkflowStatus.COMPLETED
        assert mem_node.node_id in execution.node_results
        result = execution.node_results[mem_node.node_id]
        assert result.success
        assert "test query" in result.output

    def test_memory_write_node(self):
        registry = AgentRegistry()
        registry.set_providers(memory=FakeMemoryForWorkflow())

        engine = WorkflowEngine(registry)
        wf = Workflow(name="Memory Write")
        start = WorkflowNode(name="start", node_type=NodeType.START)
        mem_node = WorkflowNode(
            name="write_memory",
            node_type=NodeType.MEMORY,
            config={"action": "write", "content": "important info"},
        )
        end = WorkflowNode(name="end", node_type=NodeType.END)
        for n in [start, mem_node, end]: wf.add_node(n)
        wf.set_start(start.node_id)
        wf.connect(start.node_id, mem_node.node_id)
        wf.connect(mem_node.node_id, end.node_id)

        engine.register_workflow(wf)
        execution = engine.execute(wf.workflow_id)
        assert execution.status == WorkflowStatus.COMPLETED
        result = execution.node_results[mem_node.node_id]
        assert result.success
        assert "记忆已写入" in result.output


class TestKGNodeExecution:
    """知识图谱节点执行测试。"""

    def test_kg_search_node(self):
        registry = AgentRegistry()
        registry.set_providers(kg=FakeKGForWorkflow())

        engine = WorkflowEngine(registry)
        wf = Workflow(name="KG Search")
        start = WorkflowNode(name="start", node_type=NodeType.START)
        kg_node = WorkflowNode(
            name="search_kg",
            node_type=NodeType.KNOWLEDGE_GRAPH,
            config={"action": "search", "query": "test entity"},
        )
        end = WorkflowNode(name="end", node_type=NodeType.END)
        for n in [start, kg_node, end]: wf.add_node(n)
        wf.set_start(start.node_id)
        wf.connect(start.node_id, kg_node.node_id)
        wf.connect(kg_node.node_id, end.node_id)

        engine.register_workflow(wf)
        execution = engine.execute(wf.workflow_id)
        assert execution.status == WorkflowStatus.COMPLETED
        result = execution.node_results[kg_node.node_id]
        assert result.success
        assert "test entity" in result.output

    def test_kg_traverse_node(self):
        registry = AgentRegistry()
        registry.set_providers(kg=FakeKGForWorkflow())

        engine = WorkflowEngine(registry)
        wf = Workflow(name="KG Traverse")
        start = WorkflowNode(name="start", node_type=NodeType.START)
        kg_node = WorkflowNode(
            name="traverse_kg",
            node_type=NodeType.KNOWLEDGE_GRAPH,
            config={"action": "traverse", "start_id": "e1", "depth": 2},
        )
        end = WorkflowNode(name="end", node_type=NodeType.END)
        for n in [start, kg_node, end]: wf.add_node(n)
        wf.set_start(start.node_id)
        wf.connect(start.node_id, kg_node.node_id)
        wf.connect(kg_node.node_id, end.node_id)

        engine.register_workflow(wf)
        execution = engine.execute(wf.workflow_id)
        assert execution.status == WorkflowStatus.COMPLETED
        result = execution.node_results[kg_node.node_id]
        assert result.success
        assert "图谱遍历" in result.output


class TestMixedWorkflow:
    """混合节点类型工作流测试。"""

    def test_agent_then_memory_then_kg(self):
        registry = AgentRegistry()
        registry.set_providers(
            memory=FakeMemoryForWorkflow(),
            kg=FakeKGForWorkflow(),
        )
        registry.register(KnowledgeAgent(memory=FakeMemoryForWorkflow()))

        engine = WorkflowEngine(registry)
        wf = Workflow(name="Mixed Workflow")
        start = WorkflowNode(name="start", node_type=NodeType.START)
        agent_node = WorkflowNode(name="knowledge", node_type=NodeType.AGENT, agent_id="builtin-knowledge")
        mem_node = WorkflowNode(name="memory", node_type=NodeType.MEMORY, config={"action": "search", "query": "test"})
        kg_node = WorkflowNode(name="kg", node_type=NodeType.KNOWLEDGE_GRAPH, config={"action": "search", "query": "test"})
        end = WorkflowNode(name="end", node_type=NodeType.END)
        for n in [start, agent_node, mem_node, kg_node, end]: wf.add_node(n)
        wf.set_start(start.node_id)
        wf.connect(start.node_id, agent_node.node_id)
        wf.connect(agent_node.node_id, mem_node.node_id)
        wf.connect(mem_node.node_id, kg_node.node_id)
        wf.connect(kg_node.node_id, end.node_id)

        engine.register_workflow(wf)
        execution = engine.execute(wf.workflow_id, {"query": "knowledge management"})
        assert execution.status == WorkflowStatus.COMPLETED
        assert len(execution.node_results) == 3  # agent + memory + kg (start/end don't produce results)
