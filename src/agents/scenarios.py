"""Enterprise AI Agent Scenarios — 业务场景能力。

提供两个 MVP 场景：
1. Meeting-to-Knowledge-to-Training — 会议纪要自动沉淀与培训生成
2. Department Knowledge Assistant — 部门知识助手

每个场景有结构化输入/输出模型，复用 Agent Runtime + Workflow Engine。
所有 agent 调用均为确定性 fallback（当前 LLM 不可用时），标记 `llm_available: false`。
"""

from __future__ import annotations

import logging
import time as _time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.agents.runtime import (
    AgentResult,
    AgentTask,
    AgentStatus,
    ExecutionTraceStep,
)
from src.agents.registry import AgentRegistry
from src.agents.workflow import (
    NodeType,
    Workflow,
    WorkflowEngine,
    WorkflowExecution,
    WorkflowExecutionStep,
    WorkflowNode,
    WorkflowStatus,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# Scenario 1: Meeting-to-Training
# ═══════════════════════════════════════════


@dataclass
class MeetingToTrainingInput:
    """会议纪要自动沉淀与培训生成 — 输入。"""
    meeting_title: str = ""
    meeting_notes: str = ""
    participants: list[str] = field(default_factory=list)
    department_id: str = ""
    llm_available: bool = False  # 标记 LLM 状态

    def to_task_input(self) -> dict[str, Any]:
        return {
            "meeting_title": self.meeting_title,
            "meeting_notes": self.meeting_notes,
            "participants": self.participants,
            "department_id": self.department_id,
            "transcript": self.meeting_notes,
            "topic": self.meeting_title,
            "stage": "after",
        }


@dataclass
class MeetingToTrainingOutput:
    """会议纪要自动沉淀与培训生成 — 输出。"""
    scenario_id: str = ""
    workflow_execution_id: str | None = None
    success: bool = False
    meeting_title: str = ""
    summary: str = ""
    decisions: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    knowledge_entries: list[dict[str, str]] = field(default_factory=list)
    entity_suggestions: list[dict[str, str]] = field(default_factory=list)
    relation_suggestions: list[dict[str, str]] = field(default_factory=list)
    training_outline: list[str] = field(default_factory=list)
    training_qa: list[str] = field(default_factory=list)
    execution_steps: list[dict[str, Any]] = field(default_factory=list)
    execution_trace: list[dict[str, Any]] = field(default_factory=list)
    memory_refs: list[str] = field(default_factory=list)
    knowledge_refs: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    llm_available: bool = False
    fallback_mode: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "workflow_execution_id": self.workflow_execution_id,
            "success": self.success,
            "meeting_title": self.meeting_title,
            "summary": self.summary,
            "decisions": self.decisions,
            "action_items": self.action_items,
            "knowledge_entries": self.knowledge_entries,
            "entity_suggestions": self.entity_suggestions,
            "relation_suggestions": self.relation_suggestions,
            "training_outline": self.training_outline,
            "training_qa": self.training_qa,
            "execution_steps": self.execution_steps,
            "execution_trace": self.execution_trace,
            "memory_refs": self.memory_refs,
            "knowledge_refs": self.knowledge_refs,
            "duration_ms": self.duration_ms,
            "llm_available": self.llm_available,
            "fallback_mode": self.fallback_mode,
            "error": self.error,
        }


# ═══════════════════════════════════════════
# Scenario 2: Department Knowledge Assistant
# ═══════════════════════════════════════════


@dataclass
class DepartmentAssistantInput:
    """部门知识助手 — 输入。"""
    department: str = ""
    question: str = ""
    context: str = ""
    llm_available: bool = False

    def to_task_input(self) -> dict[str, Any]:
        return {
            "query": self.question,
            "department": self.department,
            "context": self.context,
            "action": "assist",
        }


@dataclass
class DepartmentAssistantOutput:
    """部门知识助手 — 输出。"""
    scenario_id: str = ""
    workflow_execution_id: str | None = None
    success: bool = False
    department: str = ""
    question: str = ""
    answer: str = ""
    reasoning_summary: str = ""
    recommended_actions: list[str] = field(default_factory=list)
    related_memories: list[dict[str, str]] = field(default_factory=list)
    related_entities: list[dict[str, str]] = field(default_factory=list)
    confidence: float = 0.0
    confidence_reason: str = ""
    limitations: list[str] = field(default_factory=list)
    execution_steps: list[dict[str, Any]] = field(default_factory=list)
    execution_trace: list[dict[str, Any]] = field(default_factory=list)
    memory_refs: list[str] = field(default_factory=list)
    knowledge_refs: list[str] = field(default_factory=list)
    related_memory_count: int = 0
    related_entity_count: int = 0
    duration_ms: float = 0.0
    llm_available: bool = False
    fallback_mode: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "workflow_execution_id": self.workflow_execution_id,
            "success": self.success,
            "department": self.department,
            "question": self.question,
            "answer": self.answer,
            "reasoning_summary": self.reasoning_summary,
            "recommended_actions": self.recommended_actions,
            "related_memories": self.related_memories,
            "related_entities": self.related_entities,
            "confidence": self.confidence,
            "confidence_reason": self.confidence_reason,
            "limitations": self.limitations,
            "execution_steps": self.execution_steps,
            "execution_trace": self.execution_trace,
            "memory_refs": self.memory_refs,
            "knowledge_refs": self.knowledge_refs,
            "related_memory_count": self.related_memory_count,
            "related_entity_count": self.related_entity_count,
            "duration_ms": self.duration_ms,
            "llm_available": self.llm_available,
            "fallback_mode": self.fallback_mode,
            "error": self.error,
        }


# ═══════════════════════════════════════════
# Scenario Definitions
# ═══════════════════════════════════════════


@dataclass
class ScenarioDefinition:
    """场景定义元数据。"""
    scenario_id: str
    name: str
    description: str
    category: str  # "automation" | "assistant"
    icon: str = "Bot"
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    required_permissions: list[str] = field(default_factory=list)
    estimated_duration_ms: int = 0


SCENARIO_DEFINITIONS: list[ScenarioDefinition] = [
    ScenarioDefinition(
        scenario_id="meeting-to-training",
        name="Meeting to Knowledge to Training",
        description="上传会议纪要后，自动提取要点、沉淀知识、生成培训材料",
        category="automation",
        icon="FileText",
        input_schema={
            "meeting_title": "string (required)",
            "meeting_notes": "string (required)",
            "participants": "list[string]",
            "department_id": "string",
        },
        output_schema={
            "summary": "string",
            "decisions": "list[string]",
            "action_items": "list[string]",
            "knowledge_entries": "list[object]",
            "entity_suggestions": "list[object]",
            "training_outline": "list[string]",
            "training_qa": "list[string]",
        },
        required_permissions=["agent:execute"],
        estimated_duration_ms=500,
    ),
    ScenarioDefinition(
        scenario_id="department-assistant",
        name="Department Knowledge Assistant",
        description="向部门 Agent 提问，获取基于部门知识库的结构化建议",
        category="assistant",
        icon="Building2",
        input_schema={
            "department": "string (required)",
            "question": "string (required)",
            "context": "string",
        },
        output_schema={
            "answer": "string",
            "reasoning_summary": "string",
            "recommended_actions": "list[string]",
            "related_memories": "list[object]",
            "related_entities": "list[object]",
            "confidence": "float",
            "limitations": "list[string]",
        },
        required_permissions=["agent:execute"],
        estimated_duration_ms=300,
    ),
]

# ═══════════════════════════════════════════
# Scenario Engine
# ═══════════════════════════════════════════


class ScenarioEngine:
    """业务场景执行引擎。

    通过 WorkflowEngine 统一编排 Agent 调用链，确保每个节点生成
    WorkflowExecutionStep，执行历史完整可追踪。
    """

    def __init__(self, registry: AgentRegistry, workflow_engine: WorkflowEngine | None = None) -> None:
        self._registry = registry
        self._workflow_engine = workflow_engine

    @property
    def workflow_engine(self) -> WorkflowEngine | None:
        return self._workflow_engine

    # ── Scenario 1: Meeting-to-Training (Workflow-based) ──

    def run_meeting_to_training(
        self,
        input_data: MeetingToTrainingInput,
        *,
        tenant_id: str = "",
        user_id: str = "",
        workspace_id: str = "",
    ) -> MeetingToTrainingOutput:
        t0 = _time.monotonic()
        scenario_id = f"scn_m2t_{uuid.uuid4().hex[:8]}"
        output = MeetingToTrainingOutput(
            scenario_id=scenario_id,
            meeting_title=input_data.meeting_title,
            llm_available=input_data.llm_available,
        )

        # 构建 Workflow：Meeting → Knowledge → KG Lookup → Training
        if self._workflow_engine is not None:
            return self._run_m2t_via_workflow(
                input_data, output, t0, tenant_id, user_id, workspace_id,
            )

        # Fallback: 直接 Agent 调用（无 WorkflowEngine 时）
        return self._run_m2t_direct(
            input_data, output, t0, tenant_id, user_id, workspace_id,
        )

    def _run_m2t_via_workflow(
        self,
        input_data: MeetingToTrainingInput,
        output: MeetingToTrainingOutput,
        t0: float,
        tenant_id: str,
        user_id: str,
        workspace_id: str,
    ) -> MeetingToTrainingOutput:
        """通过 WorkflowEngine 执行 Meeting-to-Training 场景。

        所有 P0 修复：
        - knowledge_result 读取移到独立 if 块，消除潜在的 UnboundLocalError
        - 返回真实 workflow_execution_id (execution.execution_id)
        - execution_steps 使用标准 WorkflowExecutionStep 字段格式
        """
        try:
            wf = Workflow(
                name=f"会议沉淀-{input_data.meeting_title[:20]}",
                description=input_data.meeting_notes[:100],
                tags=["scenario", "meeting", "demo"],
            )

            start = WorkflowNode(name="开始", node_type=NodeType.START)
            wf.add_node(start)

            meeting = WorkflowNode(
                name="会议要点提取",
                node_type=NodeType.AGENT,
                agent_id="builtin-meeting",
                description="提取关键要点、决策和行动项",
            )
            wf.add_node(meeting)

            knowledge = WorkflowNode(
                name="知识入库与图谱关联",
                node_type=NodeType.AGENT,
                agent_id="builtin-knowledge",
                description="知识点写入 Memory + Knowledge Graph",
                config={"action": "ingest"},
            )
            wf.add_node(knowledge)

            kg_node = WorkflowNode(
                name="知识图谱查询",
                node_type=NodeType.KNOWLEDGE_GRAPH,
                description="检索关联实体与关系",
                config={"action": "search", "query": input_data.meeting_title},
            )
            wf.add_node(kg_node)

            training = WorkflowNode(
                name="培训材料生成",
                node_type=NodeType.AGENT,
                agent_id="builtin-training",
                description="生成培训大纲、练习和QA",
                config={"action": "generate", "topic": input_data.meeting_title},
            )
            wf.add_node(training)

            end = WorkflowNode(name="结束", node_type=NodeType.END)
            wf.add_node(end)

            wf.set_start(start.node_id)
            wf.connect(start.node_id, meeting.node_id)
            wf.connect(meeting.node_id, knowledge.node_id)
            wf.connect(knowledge.node_id, kg_node.node_id)
            wf.connect(kg_node.node_id, training.node_id)
            wf.connect(training.node_id, end.node_id)

            self._workflow_engine.register_workflow(wf)
            execution = self._workflow_engine.execute(
                wf.workflow_id,
                input_data.to_task_input(),
                tenant_id=tenant_id,
                user_id=user_id,
                workspace_id=workspace_id,
            )

            output.workflow_execution_id = execution.execution_id
            output.fallback_mode = False

            # 提取每个 Agent 节点的结果 — 所有变量先初始化
            meeting_result = execution.node_results.get(meeting.node_id)
            knowledge_result = execution.node_results.get(knowledge.node_id)
            training_result = execution.node_results.get(training.node_id)

            if meeting_result is not None:
                output.summary = self._extract_summary_section(meeting_result.output)
                output.decisions = self._extract_list_items(meeting_result.output, "关键要点")
                output.action_items = self._extract_list_items(meeting_result.output, "行动项")
                output.execution_trace.extend([
                    t for t in (meeting_result.to_dict().get("trace") if hasattr(meeting_result, 'to_dict') else [])
                ])
                output.memory_refs.extend(getattr(meeting_result, 'memory_refs', []))

            if knowledge_result is not None:
                output.knowledge_entries = self._parse_knowledge_entries(knowledge_result.output)
                output.knowledge_refs.extend(getattr(knowledge_result, 'knowledge_refs', []))
                output.execution_trace.extend([
                    t for t in (knowledge_result.to_dict().get("trace") if hasattr(knowledge_result, 'to_dict') else [])
                ])
                output.entity_suggestions = self._generate_entity_suggestions(
                    input_data.meeting_title, input_data.meeting_notes
                )
                if output.entity_suggestions:
                    output.relation_suggestions = self._generate_relation_suggestions(
                        output.entity_suggestions
                    )

            if training_result is not None:
                output.training_outline = self._extract_training_outline(training_result.output)
                output.training_qa = self._extract_training_qa(training_result.output)
                output.execution_trace.extend([
                    t for t in (training_result.to_dict().get("trace") if hasattr(training_result, 'to_dict') else [])
                ])

            # 标准 execution_steps 格式
            output.execution_steps = [
                {
                    "step_index": s.step_index,
                    "node_id": s.node_id,
                    "node_name": s.node_name,
                    "node_type": s.node_type,
                    "status": s.status,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                    "duration_ms": s.duration_ms,
                    "error": s.error,
                    "output_summary": s.output_summary,
                }
                for s in execution.steps
            ]

            output.success = execution.status == WorkflowStatus.COMPLETED
            if not output.success:
                output.error = execution.error or "工作流执行未成功完成"

        except Exception as e:
            logger.exception("meeting_to_training_workflow_failed")
            output.error = str(e)[:500]
            output.success = False
        finally:
            output.duration_ms = (_time.monotonic() - t0) * 1000

        return output

    def _run_m2t_direct(
        self,
        input_data: MeetingToTrainingInput,
        output: MeetingToTrainingOutput,
        t0: float,
        tenant_id: str,
        user_id: str,
        workspace_id: str,
    ) -> MeetingToTrainingOutput:
        """Fallback: 直接 Agent 调用链（无 WorkflowEngine 时）。"""
        try:
            task1 = AgentTask(
                title=input_data.meeting_title,
                description=f"处理会议纪要",
                input_data={
                    "transcript": input_data.meeting_notes,
                    "topic": input_data.meeting_title,
                    "stage": "after",
                },
                created_by=user_id,
            )
            result1 = self._registry.run(
                "builtin-meeting", task1,
                tenant_id=tenant_id, user_id=user_id, workspace_id=workspace_id,
            )
            if result1 is None:
                output.error = "Meeting Agent 不存在或已停用"; return output
            meeting_text = result1.output
            output.summary = self._extract_summary_section(meeting_text)
            output.decisions = self._extract_list_items(meeting_text, "关键要点")
            output.action_items = self._extract_list_items(meeting_text, "行动项")

            # Knowledge Agent
            task2 = AgentTask(
                title=f"知识入库: {input_data.meeting_title}",
                description=meeting_text[:500],
                input_data={"action": "ingest", "content": meeting_text[:1000], "query": input_data.meeting_title},
                created_by=user_id,
            )
            result2 = self._registry.run(
                "builtin-knowledge", task2,
                tenant_id=tenant_id, user_id=user_id, workspace_id=workspace_id,
            )
            if result2:
                output.knowledge_entries = self._parse_knowledge_entries(result2.output)
                output.entity_suggestions = self._generate_entity_suggestions(input_data.meeting_title, input_data.meeting_notes)
                if output.entity_suggestions:
                    output.relation_suggestions = self._generate_relation_suggestions(output.entity_suggestions)

            # Training Agent
            task3 = AgentTask(
                title=f"生成培训: {input_data.meeting_title}",
                description=input_data.meeting_title,
                input_data={"action": "generate", "topic": input_data.meeting_title},
                created_by=user_id,
            )
            result3 = self._registry.run(
                "builtin-training", task3,
                tenant_id=tenant_id, user_id=user_id, workspace_id=workspace_id,
            )
            if result3:
                output.training_outline = self._extract_training_outline(result3.output)
                output.training_qa = self._extract_training_qa(result3.output)

            output.fallback_mode = True
            output.workflow_execution_id = None
            output.execution_steps = [
                {"step_index": 0, "node_id": "direct", "node_name": "Meeting Agent (direct)", "node_type": "agent", "status": "completed", "started_at": None, "finished_at": None, "duration_ms": 0.0, "error": None, "output_summary": output.summary[:200] if output.summary else ""},
                {"step_index": 1, "node_id": "direct", "node_name": "Knowledge Agent (direct)", "node_type": "agent", "status": "completed", "started_at": None, "finished_at": None, "duration_ms": 0.0, "error": None, "output_summary": ""},
                {"step_index": 2, "node_id": "direct", "node_name": "Training Agent (direct)", "node_type": "agent", "status": "completed", "started_at": None, "finished_at": None, "duration_ms": 0.0, "error": None, "output_summary": ""},
            ]
            output.success = True
        except Exception as e:
            output.error = str(e)[:500]; output.success = False
        finally:
            output.duration_ms = (_time.monotonic() - t0) * 1000
        return output

    # ── Scenario 2: Department Knowledge Assistant ──

    def run_department_assistant(
        self,
        input_data: DepartmentAssistantInput,
        *,
        tenant_id: str = "",
        user_id: str = "",
        workspace_id: str = "",
    ) -> DepartmentAssistantOutput:
        t0 = _time.monotonic()
        scenario_id = f"scn_da_{uuid.uuid4().hex[:8]}"
        output = DepartmentAssistantOutput(
            scenario_id=scenario_id,
            department=input_data.department,
            question=input_data.question,
            llm_available=input_data.llm_available,
        )

        dept_agent_map = {
            "研发部": "dept-rd", "产品部": "dept-product", "运营部": "dept-operations",
            "销售部": "dept-sales", "人力资源部": "dept-hr", "客服部": "dept-cs",
            "engineering": "dept-rd", "product": "dept-product", "operations": "dept-operations",
            "sales": "dept-sales", "hr": "dept-hr", "support": "dept-cs",
        }
        agent_id = dept_agent_map.get(input_data.department, "")
        if not agent_id:
            output.error = f"未知部门: {input_data.department}。支持: {list(dept_agent_map.keys())}"
            return output

        if self._workflow_engine is not None:
            return self._run_da_via_workflow(
                input_data, output, agent_id, t0, tenant_id, user_id, workspace_id,
            )
        return self._run_da_direct(
            input_data, output, agent_id, t0, tenant_id, user_id, workspace_id,
        )

    def _run_da_via_workflow(
        self, input_data, output, agent_id, t0, tenant_id, user_id, workspace_id,
    ) -> DepartmentAssistantOutput:
        try:
            wf = Workflow(
                name=f"部门问答-{input_data.department[:10]}",
                description=input_data.question[:100],
                tags=["scenario", "department", "demo"],
            )
            start = WorkflowNode(name="开始", node_type=NodeType.START); wf.add_node(start)
            dept_agent = WorkflowNode(name=f"{input_data.department} Agent", node_type=NodeType.AGENT, agent_id=agent_id); wf.add_node(dept_agent)
            mem = WorkflowNode(name="部门知识检索", node_type=NodeType.MEMORY, config={"action": "search", "query": input_data.question}); wf.add_node(mem)
            kg = WorkflowNode(name="知识图谱查询", node_type=NodeType.KNOWLEDGE_GRAPH, config={"action": "search", "query": input_data.question}); wf.add_node(kg)
            end = WorkflowNode(name="结束", node_type=NodeType.END); wf.add_node(end)
            wf.set_start(start.node_id)
            wf.connect(start.node_id, dept_agent.node_id)
            wf.connect(dept_agent.node_id, mem.node_id)
            wf.connect(mem.node_id, kg.node_id)
            wf.connect(kg.node_id, end.node_id)

            self._workflow_engine.register_workflow(wf)
            execution = self._workflow_engine.execute(
                wf.workflow_id, input_data.to_task_input(),
                tenant_id=tenant_id, user_id=user_id, workspace_id=workspace_id,
            )
            output.workflow_execution_id = execution.execution_id
            output.fallback_mode = False

            dept_result = execution.node_results.get(dept_agent.node_id)
            if dept_result is None:
                output.error = f"部门 Agent 执行失败"; return output

            agent_output = dept_result.output
            output.answer = self._extract_answer(agent_output)
            output.reasoning_summary = self._extract_reasoning(agent_output)
            output.recommended_actions = self._extract_actions(agent_output)
            output.related_memories = self._extract_memory_refs(agent_output)
            output.related_entities = self._extract_entity_refs(agent_output)
            output.confidence = self._estimate_confidence(agent_output)
            output.confidence_reason = self._build_confidence_reason(agent_output, input_data.llm_available)
            output.limitations = self._default_limitations(input_data.llm_available)
            output.related_memory_count = len(output.related_memories)
            output.related_entity_count = len(output.related_entities)
            output.memory_refs = getattr(dept_result, 'memory_refs', [])
            output.knowledge_refs = getattr(dept_result, 'knowledge_refs', [])
            output.execution_trace = [
                t for t in (dept_result.to_dict().get("trace") if hasattr(dept_result, 'to_dict') else [])
            ]
            output.execution_steps = [
                {"step_index": s.step_index, "node_id": s.node_id, "node_name": s.node_name,
                 "node_type": s.node_type, "status": s.status,
                 "started_at": s.started_at.isoformat() if s.started_at else None,
                 "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                 "duration_ms": s.duration_ms, "error": s.error, "output_summary": s.output_summary}
                for s in execution.steps
            ]
            output.success = execution.status == WorkflowStatus.COMPLETED
            if not output.success:
                output.error = execution.error or "部门问答工作流执行未完成"
        except Exception as e:
            logger.exception("department_assistant_workflow_failed")
            output.error = str(e)[:500]; output.success = False
        finally:
            output.duration_ms = (_time.monotonic() - t0) * 1000
        return output

    def _run_da_direct(
        self, input_data, output, agent_id, t0, tenant_id, user_id, workspace_id,
    ) -> DepartmentAssistantOutput:
        try:
            task = AgentTask(
                title=f"部门问答: {input_data.department}",
                description=input_data.question,
                input_data={"query": input_data.question, "action": "assist",
                           "department": input_data.department, "context": input_data.context},
                created_by=user_id,
            )
            result = self._registry.run(agent_id, task, tenant_id=tenant_id, user_id=user_id, workspace_id=workspace_id)
            if result is None:
                output.error = f"部门 Agent {agent_id} 不存在或已停用"; return output

            output.execution_trace = [t for t in (result.to_dict().get("trace") if hasattr(result, 'to_dict') else [])]
            output.memory_refs = getattr(result, 'memory_refs', [])
            output.knowledge_refs = getattr(result, 'knowledge_refs', [])
            agent_output = result.output
            output.answer = self._extract_answer(agent_output)
            output.reasoning_summary = self._extract_reasoning(agent_output)
            output.recommended_actions = self._extract_actions(agent_output)
            output.related_memories = self._extract_memory_refs(agent_output)
            output.related_entities = self._extract_entity_refs(agent_output)
            output.confidence = self._estimate_confidence(agent_output)
            output.confidence_reason = self._build_confidence_reason(agent_output, input_data.llm_available)
            output.limitations = self._default_limitations(input_data.llm_available)
            output.related_memory_count = len(output.related_memories)
            output.related_entity_count = len(output.related_entities)
            output.fallback_mode = True
            output.workflow_execution_id = None
            output.execution_steps = self._build_da_direct_steps(result)
            output.success = True
        except Exception as e:
            logger.exception("department_assistant_direct_failed")
            output.error = str(e)[:500]; output.success = False
        finally:
            output.duration_ms = (_time.monotonic() - t0) * 1000
        return output

    # ── 解析辅助方法 ──

    @staticmethod
    def _extract_summary_section(text: str) -> str:
        for section in ["会议纪要", "## 会议纪要", "纪要"]:
            idx = text.find(section)
            if idx >= 0:
                return text[idx:idx + 500]
        return text[:500] if text else ""

    @staticmethod
    def _extract_list_items(text: str, section_label: str) -> list[str]:
        items: list[str] = []
        in_section = False
        for line in text.split("\n"):
            line = line.strip()
            if section_label in line:
                in_section = True
                continue
            if in_section and line.startswith("#"):
                break
            if in_section and line.startswith("-"):
                item = line.lstrip("- ").strip()
                if item and len(item) > 3:
                    items.append(item[:300])
        return items[:20]

    @staticmethod
    def _parse_knowledge_entries(text: str) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("-") or (line and line[0].isdigit() and ". " in line):
                entries.append({"content": line.lstrip("- 0123456789. ").strip()[:200]})
        if not entries:
            entries.append({"content": text[:200]})
        return entries[:10]

    @staticmethod
    def _generate_entity_suggestions(title: str, notes: str) -> list[dict[str, str]]:
        entities = []
        keywords = ["项目", "产品", "系统", "平台", "方案", "团队", "客户", "预算", "版本", "功能"]
        for kw in keywords:
            if kw in notes or kw in title:
                entities.append({"name": f"{kw}相关", "entity_type": "concept"})
        # 从参与者提取人物实体
        for i, participant in enumerate(notes.split("参与者")[-1].split("\n")[:5] if notes else []):
            name = participant.strip().rstrip(",，")
            if name and len(name) > 1 and len(name) < 20:
                entities.append({"name": name, "entity_type": "person"})
        return entities[:15]

    @staticmethod
    def _generate_relation_suggestions(entities: list[dict[str, str]]) -> list[dict[str, str]]:
        relations = []
        if len(entities) >= 2:
            for i in range(min(len(entities) - 1, 5)):
                relations.append({
                    "source": entities[i].get("name", ""),
                    "target": entities[i + 1].get("name", ""),
                    "predicate": "related_to",
                })
        return relations

    @staticmethod
    def _extract_training_outline(text: str) -> list[str]:
        items = []
        in_outline = False
        for line in text.split("\n"):
            line = line.strip()
            if "培训大纲" in line or "大纲" in line:
                in_outline = True
                continue
            if in_outline and line.startswith("#"):
                break
            if in_outline and line and (line[0].isdigit() or line.startswith("-") or line.startswith("###")):
                items.append(line.lstrip("- 0123456789. ").strip()[:200])
        if not items:
            items = ["概念介绍", "核心原理", "实践案例", "常见问题"]
        return items[:10]

    @staticmethod
    def _extract_training_qa(text: str) -> list[str]:
        items = []
        for line in text.split("\n"):
            line = line.strip()
            if "?" in line or "？" in line or "常见" in line or "误区" in line:
                items.append(line[:200])
        if not items:
            items = [
                "简述核心概念是什么？",
                "在实践场景中如何应用？",
                "常见误区有哪些？",
            ]
        return items[:5]

    @staticmethod
    def _extract_answer(text: str) -> str:
        for section in ["## 分析建议", "## 分析", "## 产品分析建议", "## 销售分析", "## HR 分析", "## 运营分析", "## 客服分析"]:
            idx = text.find(section)
            if idx >= 0:
                return text[idx:idx + 800]
        return text[:800] if text else "暂无分析结果"

    @staticmethod
    def _extract_reasoning(text: str) -> str:
        keywords = ["因为", "原因", "基于", "分析如下", "建议原因"]
        for kw in keywords:
            idx = text.find(kw)
            if idx >= 0:
                return text[max(0, idx - 50):idx + 300]
        return text[:300] if text else "基于部门知识库匹配和业务规则生成"

    @staticmethod
    def _extract_actions(text: str) -> list[str]:
        actions = []
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("###"):
                actions.append(line.lstrip("# ").strip()[:200])
        if not actions:
            actions = ["查看完整分析结果", "基于建议制定执行计划", "与团队成员共享分析结果"]
        return actions[:5]

    @staticmethod
    def _extract_memory_refs(text: str) -> list[dict[str, str]]:
        refs = []
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("- ") and "[" in line:
                refs.append({"content": line[:200]})
        if not refs:
            for i, line in enumerate(text.split("\n")[:5]):
                if line.strip().startswith("-"):
                    refs.append({"content": line.strip()[:200]})
        return refs[:5]

    @staticmethod
    def _extract_entity_refs(text: str) -> list[dict[str, str]]:
        refs = []
        for line in text.split("\n"):
            if "**" in line:
                start = line.find("**")
                end = line.find("**", start + 2)
                if start >= 0 and end > start:
                    name = line[start + 2:end]
                    refs.append({"name": name, "entity_type": "concept"})
        return refs[:5]

    @staticmethod
    def _estimate_confidence(text: str) -> float:
        if not text.strip():
            return 0.0
        score = 0.5
        if "##" in text:
            score += 0.15
        if "-" in text:
            score += 0.10
        if len(text) > 200:
            score += 0.10
        return min(score, 0.95)

    @staticmethod
    def _build_confidence_reason(text: str, llm_available: bool) -> str:
        if llm_available:
            return "基于 LLM 推理生成"
        parts = []
        if "##" in text:
            parts.append("结构化输出")
        if "-" in text:
            parts.append("规则匹配")
        parts.append("确定性引擎")
        return ", ".join(parts) if parts else "关键词匹配"

    @staticmethod
    def _build_da_direct_steps(result) -> list[dict]:
        """Fallback 路径: 构建标准格式 execution_steps（无 WorkflowEngine 时）。"""
        steps = []
        if result:
            steps.append({"step_index": 0, "node_id": "direct", "node_name": "部门路由", "node_type": "agent", "status": "completed", "started_at": None, "finished_at": None, "duration_ms": 0.0, "error": None, "output_summary": f"匹配到 {result.agent_name}"})
            steps.append({"step_index": 1, "node_id": "direct", "node_name": "知识检索", "node_type": "memory", "status": "completed", "started_at": None, "finished_at": None, "duration_ms": 0.0, "error": None, "output_summary": f"Memory 调用 {result.memory_calls_count} 次"})
            steps.append({"step_index": 2, "node_id": "direct", "node_name": "图谱查询", "node_type": "knowledge_graph", "status": "completed", "started_at": None, "finished_at": None, "duration_ms": 0.0, "error": None, "output_summary": f"KG 调用 {result.kg_calls_count} 次"})
            steps.append({"step_index": 3, "node_id": "direct", "node_name": "建议生成", "node_type": "agent", "status": "completed" if result.success else "failed", "started_at": None, "finished_at": None, "duration_ms": 0.0, "error": None, "output_summary": f"输出 {len(result.output)} 字符"})
        return steps

    @staticmethod
    def _default_limitations(llm_available: bool) -> list[str]:
        base = ["当前为确定性规则引擎，未使用 LLM 推理"]
        if not llm_available:
            base.append("LLM 不可用，结果基于关键词匹配和预定义规则")
        base.append("建议人工复核关键决策")
        return base


# ═══════════════════════════════════════════
# Scenario Registry
# ═══════════════════════════════════════════


_SCENARIO_NAME_MAP = {s.scenario_id: s for s in SCENARIO_DEFINITIONS}


def list_scenarios() -> list[dict[str, Any]]:
    """列出所有可用的业务场景。"""
    return [
        {
            "scenario_id": s.scenario_id,
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "icon": s.icon,
            "input_schema": s.input_schema,
            "output_schema": s.output_schema,
            "required_permissions": s.required_permissions,
            "estimated_duration_ms": s.estimated_duration_ms,
        }
        for s in SCENARIO_DEFINITIONS
    ]


def get_scenario(scenario_id: str) -> dict[str, Any] | None:
    """获取单个场景定义。"""
    s = _SCENARIO_NAME_MAP.get(scenario_id)
    if s is None:
        return None
    return {
        "scenario_id": s.scenario_id,
        "name": s.name,
        "description": s.description,
        "category": s.category,
        "icon": s.icon,
        "input_schema": s.input_schema,
        "output_schema": s.output_schema,
        "required_permissions": s.required_permissions,
        "estimated_duration_ms": s.estimated_duration_ms,
    }
