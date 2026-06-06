"""Workflow Engine 单元测试。"""

import pytest
from datetime import datetime, timezone

from src.agents.registry import AgentRegistry
from src.agents.runtime import AgentTask
from src.agents.builtin.knowledge_agent import KnowledgeAgent
from src.agents.builtin.meeting_agent import MeetingAgent
from src.agents.builtin.research_agent import ResearchAgent
from src.agents.builtin.training_agent import TrainingAgent
from src.agents.workflow import (
    Workflow,
    WorkflowNode,
    WorkflowExecution,
    WorkflowEngine,
    WorkflowStatus,
    NodeType,
    create_meeting_to_training_workflow,
    create_research_to_report_workflow,
)
from tests.test_agents.test_runtime import FakeMemoryProvider, FakeKGProvider


@pytest.fixture
def registry():
    reg = AgentRegistry()
    mem = FakeMemoryProvider()
    kg = FakeKGProvider()
    reg.set_providers(memory=mem, kg=kg)
    for cls in [KnowledgeAgent, MeetingAgent, TrainingAgent, ResearchAgent]:
        reg.register(cls(memory=mem, knowledge_graph=kg))
    return reg


@pytest.fixture
def engine(registry):
    return WorkflowEngine(registry)


# ═══════════════════════════════════════════
# WorkflowNode 测试
# ═══════════════════════════════════════════


class TestWorkflowNode:
    def test_agent_node(self):
        node = WorkflowNode(
            name="知识搜索",
            node_type=NodeType.AGENT,
            agent_id="builtin-knowledge",
        )
        assert node.node_type == NodeType.AGENT
        assert node.agent_id == "builtin-knowledge"
        assert node.status == "pending"

    def test_human_node(self):
        node = WorkflowNode(
            name="审批",
            node_type=NodeType.HUMAN,
            human_prompt="请确认是否需要进一步分析?",
        )
        assert node.node_type == NodeType.HUMAN
        assert node.human_prompt != ""

    def test_condition_node(self):
        node = WorkflowNode(
            name="分支",
            node_type=NodeType.CONDITION,
            condition_map={"positive": "next_a", "negative": "next_b"},
        )
        assert node.node_type == NodeType.CONDITION
        assert node.condition_map["positive"] == "next_a"

    def test_to_dict(self):
        node = WorkflowNode(name="Test", node_type=NodeType.START)
        d = node.to_dict()
        assert d["name"] == "Test"
        assert d["node_type"] == "start"


# ═══════════════════════════════════════════
# Workflow 测试
# ═══════════════════════════════════════════


class TestWorkflow:
    def test_create_empty_workflow(self):
        wf = Workflow(name="Empty", description="empty")
        assert wf.workflow_id != ""
        assert wf.name == "Empty"

    def test_add_node(self):
        wf = Workflow(name="Test")
        node = wf.add_node(WorkflowNode(name="Step 1", node_type=NodeType.AGENT, agent_id="a1"))
        assert node.node_id in wf.nodes
        assert len(wf.nodes) == 1

    def test_connect_nodes(self):
        wf = Workflow(name="Test")
        n1 = wf.add_node(WorkflowNode(name="A", node_type=NodeType.START))
        n2 = wf.add_node(WorkflowNode(name="B", node_type=NodeType.END))
        wf.connect(n1.node_id, n2.node_id)
        assert n2.node_id in wf.nodes[n1.node_id].next_nodes

    def test_set_start(self):
        wf = Workflow(name="Test")
        n1 = wf.add_node(WorkflowNode(name="A", node_type=NodeType.START))
        wf.set_start(n1.node_id)
        assert wf.start_node_id == n1.node_id
        assert wf.get_start_node() is n1

    def test_validate_missing_start(self):
        wf = Workflow(name="Test")
        wf.add_node(WorkflowNode(name="A", node_type=NodeType.AGENT, agent_id="a1"))
        errors = wf.validate()
        assert any("起始节点" in e for e in errors)

    def test_validate_agent_without_id(self):
        wf = Workflow(name="Test")
        n = wf.add_node(WorkflowNode(name="A", node_type=NodeType.AGENT))
        wf.set_start(n.node_id)
        errors = wf.validate()
        assert any("agent_id" in e for e in errors)

    def test_to_dict(self):
        wf = Workflow(name="Test", tags=["test"])
        d = wf.to_dict()
        assert d["name"] == "Test"
        assert "test" in d["tags"]
        assert "nodes" in d


# ═══════════════════════════════════════════
# WorkflowExecution 测试
# ═══════════════════════════════════════════


class TestWorkflowExecution:
    def test_create_execution(self):
        ex = WorkflowExecution(workflow_id="wf1", workflow_name="Test")
        assert ex.execution_id != ""
        assert ex.status == WorkflowStatus.DRAFT

    def test_record_node_result(self):
        from src.agents.runtime import AgentResult
        ex = WorkflowExecution(workflow_id="wf1", workflow_name="Test")
        result = AgentResult(task_id="t1", agent_id="a1", agent_name="A", success=True, output="ok")
        ex.record_node_result("node1", result)
        assert "node1" in ex.node_results
        assert ex.node_statuses["node1"] == "completed"

    def test_record_node_result_failed(self):
        from src.agents.runtime import AgentResult
        ex = WorkflowExecution(workflow_id="wf1", workflow_name="Test")
        result = AgentResult(task_id="t1", agent_id="a1", agent_name="A", success=False, error="err")
        ex.record_node_result("node1", result)
        assert ex.node_statuses["node1"] == "failed"

    def test_to_dict(self):
        ex = WorkflowExecution(workflow_id="wf1", workflow_name="Test")
        ex.error = "something"
        d = ex.to_dict()
        assert d["workflow_id"] == "wf1"
        assert d["error"] == "something"


# ═══════════════════════════════════════════
# WorkflowEngine 测试
# ═══════════════════════════════════════════


class TestWorkflowEngine:
    def test_register_workflow(self, engine):
        wf = Workflow(name="Test WF")
        n1 = wf.add_node(WorkflowNode(name="Start", node_type=NodeType.START))
        n2 = wf.add_node(WorkflowNode(name="Knowledge", node_type=NodeType.AGENT, agent_id="builtin-knowledge"))
        n3 = wf.add_node(WorkflowNode(name="End", node_type=NodeType.END))
        wf.set_start(n1.node_id)
        wf.connect(n1.node_id, n2.node_id)
        wf.connect(n2.node_id, n3.node_id)
        engine.register_workflow(wf)
        assert engine.get_workflow(wf.workflow_id) is wf

    def test_register_invalid_workflow_raises(self, engine):
        wf = Workflow(name="Invalid")
        # No start node, no valid nodes
        with pytest.raises(ValueError, match="起始节点"):
            engine.register_workflow(wf)

    def test_list_workflows(self, engine):
        wf1 = Workflow(name="WF1")
        n1 = wf1.add_node(WorkflowNode(name="S", node_type=NodeType.START))
        wf1.set_start(n1.node_id)
        wf1.add_node(WorkflowNode(name="E", node_type=NodeType.END))

        wf2 = Workflow(name="WF2")
        n1b = wf2.add_node(WorkflowNode(name="S", node_type=NodeType.START))
        wf2.set_start(n1b.node_id)
        wf2.add_node(WorkflowNode(name="E", node_type=NodeType.END))

        engine.register_workflow(wf1)
        engine.register_workflow(wf2)
        assert len(engine.list_workflows()) == 2

    def test_delete_workflow(self, engine):
        wf = Workflow(name="ToDelete")
        n1 = wf.add_node(WorkflowNode(name="S", node_type=NodeType.START))
        wf.set_start(n1.node_id)
        wf.add_node(WorkflowNode(name="E", node_type=NodeType.END))
        engine.register_workflow(wf)

        assert engine.delete_workflow(wf.workflow_id) is True
        assert engine.get_workflow(wf.workflow_id) is None

    def test_execute_simple_workflow(self, engine):
        """执行一个简单的开始→Agent→结束的工作流。"""
        wf = Workflow(name="Simple")
        start = wf.add_node(WorkflowNode(name="Start", node_type=NodeType.START))
        agent_node = wf.add_node(WorkflowNode(
            name="Search", node_type=NodeType.AGENT, agent_id="builtin-knowledge",
        ))
        end = wf.add_node(WorkflowNode(name="End", node_type=NodeType.END))
        wf.set_start(start.node_id)
        wf.connect(start.node_id, agent_node.node_id)
        wf.connect(agent_node.node_id, end.node_id)
        engine.register_workflow(wf)

        execution = engine.execute(wf.workflow_id, {"query": "test"})
        assert execution.status == WorkflowStatus.COMPLETED
        assert execution.duration_ms > 0
        assert len(execution.node_results) >= 1

    def test_execute_nonexistent_workflow(self, engine):
        with pytest.raises(ValueError, match="不存在"):
            engine.execute("nonexistent")

    def test_execute_paused_for_human(self, engine, registry):
        """测试人工节点的暂停。"""
        wf = Workflow(name="Human Approval")
        start = wf.add_node(WorkflowNode(name="Start", node_type=NodeType.START))
        human = wf.add_node(WorkflowNode(
            name="Approve",
            node_type=NodeType.HUMAN,
            human_prompt="请确认执行?",
        ))
        end = wf.add_node(WorkflowNode(name="End", node_type=NodeType.END))
        wf.set_start(start.node_id)
        wf.connect(start.node_id, human.node_id)
        wf.connect(human.node_id, end.node_id)
        engine.register_workflow(wf)

        execution = engine.execute(wf.workflow_id)
        assert execution.status == WorkflowStatus.PAUSED
        assert execution.current_node_id == human.node_id

    def test_list_executions(self, engine):
        wf = Workflow(name="Exec Test")
        start = wf.add_node(WorkflowNode(name="S", node_type=NodeType.START))
        end = wf.add_node(WorkflowNode(name="E", node_type=NodeType.END))
        wf.set_start(start.node_id)
        wf.connect(start.node_id, end.node_id)
        engine.register_workflow(wf)
        engine.execute(wf.workflow_id)

        executions = engine.list_executions()
        assert len(executions) == 1

    def test_list_executions_filter_by_workflow(self, engine):
        wf1 = Workflow(name="WF1")
        s1 = wf1.add_node(WorkflowNode(name="S", node_type=NodeType.START))
        e1 = wf1.add_node(WorkflowNode(name="E", node_type=NodeType.END))
        wf1.set_start(s1.node_id)
        wf1.connect(s1.node_id, e1.node_id)

        wf2 = Workflow(name="WF2")
        s2 = wf2.add_node(WorkflowNode(name="S", node_type=NodeType.START))
        e2 = wf2.add_node(WorkflowNode(name="E", node_type=NodeType.END))
        wf2.set_start(s2.node_id)
        wf2.connect(s2.node_id, e2.node_id)

        engine.register_workflow(wf1)
        engine.register_workflow(wf2)
        engine.execute(wf1.workflow_id)
        engine.execute(wf2.workflow_id)

        filtered = engine.list_executions(wf1.workflow_id)
        assert len(filtered) == 1


# ═══════════════════════════════════════════
# 预置工作流测试
# ═══════════════════════════════════════════


class TestPresetWorkflows:
    def test_meeting_to_training_workflow(self):
        wf = create_meeting_to_training_workflow()
        assert wf.name == "会议知识沉淀工作流"
        assert len(wf.nodes) == 5
        errors = wf.validate()
        assert errors == [], f"验证错误: {errors}"

    def test_meeting_to_training_flow_sequence(self):
        wf = create_meeting_to_training_workflow()
        start = wf.get_start_node()
        assert start is not None

        # 追踪路径
        current = start
        path = [current.name]
        while current.next_nodes:
            next_id = current.next_nodes[0]
            current = wf.nodes[next_id]
            path.append(current.name)
        assert path == ["开始", "会议要点提取", "知识入库", "生成培训材料", "结束"]

    def test_research_to_report_workflow(self):
        wf = create_research_to_report_workflow()
        assert wf.name == "深度研究到报告工作流"
        assert len(wf.nodes) == 4
        errors = wf.validate()
        assert errors == []


# ═══════════════════════════════════════════
# 执行预置工作流（集成测试）
# ═══════════════════════════════════════════


class TestExecutePresetWorkflows:
    def test_execute_meeting_to_training(self, engine):
        wf = create_meeting_to_training_workflow()
        engine.register_workflow(wf)

        execution = engine.execute(wf.workflow_id, {
            "transcript": "我们决定下周发布 v2.0。张三负责前端测试。",
            "topic": "产品发布讨论",
        })
        assert execution.status == WorkflowStatus.COMPLETED
        # 应该有至少 3 个节点的结果 (Meeting, Knowledge, Training)
        assert len(execution.node_results) == 3

    def test_execute_research_to_report(self, engine):
        wf = create_research_to_report_workflow()
        engine.register_workflow(wf)

        execution = engine.execute(wf.workflow_id, {
            "topic": "AI趋势2026",
            "depth": "standard",
        })
        assert execution.status == WorkflowStatus.COMPLETED
        assert len(execution.node_results) == 2


# ═══════════════════════════════════════════
# 高级工作流场景
# ═══════════════════════════════════════════


class TestAdvancedWorkflows:
    def test_workflow_with_condition_node(self, engine):
        """测试条件分支节点。"""
        wf = Workflow(name="Conditional")
        start = wf.add_node(WorkflowNode(name="S", node_type=NodeType.START))
        agent = wf.add_node(WorkflowNode(
            name="Search", node_type=NodeType.AGENT, agent_id="builtin-knowledge",
        ))
        condition = wf.add_node(WorkflowNode(
            name="Route",
            node_type=NodeType.CONDITION,
            condition_map={"记忆": ""},  # will be set after end nodes
        ))
        end_a = wf.add_node(WorkflowNode(name="EndA", node_type=NodeType.END))
        end_b = wf.add_node(WorkflowNode(name="EndB", node_type=NodeType.END))
        condition.condition_map["记忆"] = end_a.node_id
        condition.next_nodes.append(end_b.node_id)  # default
        wf.set_start(start.node_id)
        wf.connect(start.node_id, agent.node_id)
        wf.connect(agent.node_id, condition.node_id)
        engine.register_workflow(wf)
        execution = engine.execute(wf.workflow_id, {"query": "test"})
        assert execution.status == WorkflowStatus.COMPLETED

    def test_workflow_continue_on_error(self, engine):
        """测试 continue_on_error 配置。"""
        wf = Workflow(name="Resilient")
        start = wf.add_node(WorkflowNode(name="S", node_type=NodeType.START))
        # 用一个不存在的 agent_id 但配置 continue_on_error
        bad = wf.add_node(WorkflowNode(
            name="BadAgent",
            node_type=NodeType.AGENT,
            agent_id="nonexistent",
            config={"continue_on_error": True},
        ))
        end = wf.add_node(WorkflowNode(name="E", node_type=NodeType.END))
        wf.set_start(start.node_id)
        wf.connect(start.node_id, bad.node_id)
        wf.connect(bad.node_id, end.node_id)
        engine.register_workflow(wf)
        execution = engine.execute(wf.workflow_id)
        # should complete despite the failing node
        assert execution.status == WorkflowStatus.COMPLETED

    def test_workflow_failure_no_continue(self, engine):
        """测试默认行为：失败时不继续。"""
        wf = Workflow(name="Fragile")
        start = wf.add_node(WorkflowNode(name="S", node_type=NodeType.START))
        bad = wf.add_node(WorkflowNode(
            name="BadAgent",
            node_type=NodeType.AGENT,
            agent_id="nonexistent",
        ))
        end = wf.add_node(WorkflowNode(name="E", node_type=NodeType.END))
        wf.set_start(start.node_id)
        wf.connect(start.node_id, bad.node_id)
        wf.connect(bad.node_id, end.node_id)
        engine.register_workflow(wf)
        execution = engine.execute(wf.workflow_id)
        assert execution.status == WorkflowStatus.FAILED

    def test_execution_to_dict(self, engine):
        """测试 execution.to_dict() 完整输出。"""
        wf = Workflow(name="Dict")
        s = wf.add_node(WorkflowNode(name="S", node_type=NodeType.START))
        e = wf.add_node(WorkflowNode(name="E", node_type=NodeType.END))
        wf.set_start(s.node_id)
        wf.connect(s.node_id, e.node_id)
        engine.register_workflow(wf)
        execution = engine.execute(wf.workflow_id)
        d = execution.to_dict()
        assert d["status"] == "completed"
        assert "duration_ms" in d

    def test_get_execution(self, engine):
        wf = Workflow(name="GetEx")
        s = wf.add_node(WorkflowNode(name="S", node_type=NodeType.START))
        e = wf.add_node(WorkflowNode(name="E", node_type=NodeType.END))
        wf.set_start(s.node_id)
        wf.connect(s.node_id, e.node_id)
        engine.register_workflow(wf)
        execution = engine.execute(wf.workflow_id)
        retrieved = engine.get_execution(execution.execution_id)
        assert retrieved is not None
        assert retrieved.execution_id == execution.execution_id

    def test_get_nonexistent_execution(self, engine):
        assert engine.get_execution("nonexistent") is None

    def test_delete_nonexistent_workflow(self, engine):
        assert engine.delete_workflow("nope") is False

    def test_resume_errors(self, engine):
        """测试 resume 的各种错误路径。"""
        with pytest.raises(ValueError, match="不存在"):
            engine.resume("nonexistent", {})

        # 创建一个已完成的工作流，尝试 resume（不是 paused）
        wf = Workflow(name="ResumeTest")
        s = wf.add_node(WorkflowNode(name="S", node_type=NodeType.START))
        e = wf.add_node(WorkflowNode(name="E", node_type=NodeType.END))
        wf.set_start(s.node_id)
        wf.connect(s.node_id, e.node_id)
        engine.register_workflow(wf)
        execution = engine.execute(wf.workflow_id)
        with pytest.raises(ValueError, match="暂停"):
            engine.resume(execution.execution_id, {})
