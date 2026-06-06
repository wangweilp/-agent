"""Workflow Engine — 多 Agent 协同工作流。

支持：
- Agent → Agent（自动流转）
- Agent → Human（人工确认节点）
- Human → Agent（人工触发）
- 条件分支、并行执行、错误处理

示例工作流：会议记录 → Meeting Agent → Knowledge Agent → KG → Training Agent
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from src.agents.runtime import AgentContext, AgentResult, AgentTask, TaskPriority
from src.agents.registry import AgentRegistry

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════


class NodeType(str, Enum):
    AGENT = "agent"          # Agent 执行节点
    HUMAN = "human"          # 人工节点（审批/确认）
    CONDITION = "condition"  # 条件分支
    PARALLEL = "parallel"    # 并行执行
    START = "start"
    END = "end"


class WorkflowStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"       # 等待人工
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ═══════════════════════════════════════════
# WorkflowNode
# ═══════════════════════════════════════════


@dataclass
class WorkflowNode:
    """工作流节点。"""
    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    node_type: NodeType = NodeType.AGENT
    agent_id: str = ""           # NodeType.AGENT 时指定
    description: str = ""
    config: dict[str, Any] = field(default_factory=dict)

    # 连接
    next_nodes: list[str] = field(default_factory=list)          # 默认下一节点
    condition_map: dict[str, str] = field(default_factory=dict)   # condition → node_id

    # 人工节点
    human_prompt: str = ""      # 人工确认提示
    human_input: str = ""       # 人工输入（运行时填充）

    # 执行状态
    status: str = "pending"
    result: AgentResult | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "node_type": self.node_type.value,
            "agent_id": self.agent_id,
            "description": self.description,
            "next_nodes": self.next_nodes,
            "human_prompt": self.human_prompt,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


# ═══════════════════════════════════════════
# Workflow
# ═══════════════════════════════════════════


@dataclass
class Workflow:
    """工作流定义。"""
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    nodes: dict[str, WorkflowNode] = field(default_factory=dict)
    start_node_id: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_node(self, node: WorkflowNode) -> WorkflowNode:
        self.nodes[node.node_id] = node
        return node

    def connect(self, from_id: str, to_id: str) -> None:
        if from_id in self.nodes:
            self.nodes[from_id].next_nodes.append(to_id)

    def set_start(self, node_id: str) -> None:
        self.start_node_id = node_id

    def get_start_node(self) -> WorkflowNode | None:
        return self.nodes.get(self.start_node_id)

    def validate(self) -> list[str]:
        """验证工作流完整性。"""
        errors = []
        if not self.start_node_id:
            errors.append("未设置起始节点")
        if self.start_node_id and self.start_node_id not in self.nodes:
            errors.append(f"起始节点 {self.start_node_id} 不存在")
        for node in self.nodes.values():
            if node.node_type == NodeType.AGENT and not node.agent_id:
                errors.append(f"Agent 节点 {node.name} 未指定 agent_id")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "start_node_id": self.start_node_id,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# ═══════════════════════════════════════════
# WorkflowExecution
# ═══════════════════════════════════════════


@dataclass
class WorkflowExecution:
    """工作流执行实例。"""
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    workflow_name: str = ""
    status: WorkflowStatus = WorkflowStatus.DRAFT
    node_results: dict[str, AgentResult] = field(default_factory=dict)
    node_statuses: dict[str, str] = field(default_factory=dict)  # node_id → status
    current_node_id: str = ""
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float = 0.0

    def record_node_result(self, node_id: str, result: AgentResult) -> None:
        self.node_results[node_id] = result
        self.node_statuses[node_id] = "completed" if result.success else "failed"

    def get_next_nodes(self, node: WorkflowNode, result: AgentResult | None = None) -> list[str]:
        """根据条件和结果决定下一节点。"""
        if node.node_type == NodeType.CONDITION and result:
            condition_key = result.data.get("condition", result.output[:50] if result.output else "")
            for key, next_id in node.condition_map.items():
                if key in condition_key:
                    return [next_id]
        return list(node.next_nodes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "status": self.status.value,
            "node_statuses": self.node_statuses,
            "current_node_id": self.current_node_id,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


# ═══════════════════════════════════════════
# WorkflowEngine
# ═══════════════════════════════════════════


class WorkflowEngine:
    """工作流执行引擎。"""

    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry
        self._workflows: dict[str, Workflow] = {}
        self._executions: dict[str, WorkflowExecution] = {}

    # ── 工作流管理 ──

    def register_workflow(self, workflow: Workflow) -> None:
        errors = workflow.validate()
        if errors:
            raise ValueError(f"工作流验证失败: {'; '.join(errors)}")
        self._workflows[workflow.workflow_id] = workflow
        logger.info("workflow_registered", extra={"id": workflow.workflow_id, "workflow_name": workflow.name})

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> list[Workflow]:
        return list(self._workflows.values())

    def delete_workflow(self, workflow_id: str) -> bool:
        if workflow_id in self._workflows:
            del self._workflows[workflow_id]
            return True
        return False

    # ── 执行 ──

    def execute(self, workflow_id: str, input_data: dict[str, Any] | None = None) -> WorkflowExecution:
        workflow = self._workflows.get(workflow_id)
        if workflow is None:
            raise ValueError(f"工作流 {workflow_id} 不存在")

        execution = WorkflowExecution(
            workflow_id=workflow_id,
            workflow_name=workflow.name,
            status=WorkflowStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        t_start = time.monotonic()

        try:
            current_id = workflow.start_node_id
            visited: set[str] = set()
            max_steps = 100  # 防止无限循环

            for _ in range(max_steps):
                if not current_id:
                    break

                node = workflow.nodes.get(current_id)
                if node is None:
                    execution.error = f"节点 {current_id} 不存在"
                    execution.status = WorkflowStatus.FAILED
                    break

                # 防止循环
                if current_id in visited:
                    logger.warning("workflow_cycle_detected", extra={"node": current_id})
                visited.add(current_id)

                execution.current_node_id = current_id
                node.status = "running"
                node.started_at = datetime.now(timezone.utc)

                if node.node_type == NodeType.AGENT:
                    result = self._execute_agent_node(node, input_data or {})
                    execution.record_node_result(node.node_id, result)
                    node.result = result
                    node.finished_at = datetime.now(timezone.utc)

                    if not result.success:
                        # 检查是否配置了错误处理
                        if node.config.get("continue_on_error"):
                            logger.warning("agent_node_failed_continue", extra={"node": node.name})
                        else:
                            execution.status = WorkflowStatus.FAILED
                            execution.error = result.error
                            break

                    next_nodes = execution.get_next_nodes(node, result)

                elif node.node_type == NodeType.CONDITION:
                    last_result = execution.node_results.get(
                        list(execution.node_results.keys())[-1] if execution.node_results else ""
                    )
                    next_nodes = node.next_nodes  # 默认路径
                    if last_result and node.condition_map:
                        for key, next_id in node.condition_map.items():
                            if key in (last_result.output or ""):
                                next_nodes = [next_id]
                                break

                elif node.node_type == NodeType.HUMAN:
                    # 等待人工输入
                    if not node.human_input:
                        execution.status = WorkflowStatus.PAUSED
                        execution.current_node_id = current_id
                        node.status = "waiting_human"
                        logger.info("workflow_paused_for_human", extra={"node": node.name})
                        return execution
                    else:
                        # 人工已输入，继续
                        fake_result = AgentResult(
                            task_id=str(uuid.uuid4()),
                            agent_id="human",
                            agent_name="Human",
                            success=True,
                            output=node.human_input,
                        )
                        execution.record_node_result(node.node_id, fake_result)
                        node.result = fake_result
                        node.finished_at = datetime.now(timezone.utc)
                        next_nodes = node.next_nodes

                elif node.node_type == NodeType.END:
                    execution.status = WorkflowStatus.COMPLETED
                    node.status = "completed"
                    break

                else:
                    next_nodes = node.next_nodes

                # 移动
                if next_nodes:
                    current_id = next_nodes[0]
                else:
                    execution.status = WorkflowStatus.COMPLETED
                    break

            else:
                execution.error = "超过最大执行步骤"
                execution.status = WorkflowStatus.FAILED

        except Exception as e:
            logger.exception("workflow_execution_failed")
            execution.status = WorkflowStatus.FAILED
            execution.error = str(e)

        finally:
            execution.duration_ms = (time.monotonic() - t_start) * 1000
            execution.finished_at = datetime.now(timezone.utc)

        self._executions[execution.execution_id] = execution
        return execution

    def resume(self, execution_id: str, human_inputs: dict[str, str]) -> WorkflowExecution:
        """恢复暂停的工作流（提供人工输入）。"""
        execution = self._executions.get(execution_id)
        if execution is None:
            raise ValueError(f"执行实例 {execution_id} 不存在")
        if execution.status != WorkflowStatus.PAUSED:
            raise ValueError("只能恢复暂停的工作流")

        workflow = self._workflows.get(execution.workflow_id)
        if workflow is None:
            raise ValueError("关联工作流已删除")

        # 填入人工输入
        current_node = workflow.nodes.get(execution.current_node_id)
        if current_node and current_node.node_type == NodeType.HUMAN:
            current_node.human_input = human_inputs.get(current_node.node_id, "")

        # 继续执行
        execution.status = WorkflowStatus.RUNNING
        # 从当前节点继续（简化：重新执行，已完成的跳过）
        return self.execute(workflow.workflow_id)

    def get_execution(self, execution_id: str) -> WorkflowExecution | None:
        return self._executions.get(execution_id)

    def list_executions(self, workflow_id: str | None = None) -> list[WorkflowExecution]:
        if workflow_id:
            return [e for e in self._executions.values() if e.workflow_id == workflow_id]
        return list(self._executions.values())

    # ── 内部 ──

    def _execute_agent_node(self, node: WorkflowNode, input_data: dict[str, Any]) -> AgentResult:
        task = AgentTask(
            title=node.name,
            description=node.description,
            input_data={**input_data, **node.config},
            priority=TaskPriority.MEDIUM,
        )

        result = self._registry.run(node.agent_id, task)
        if result is None:
            return AgentResult(
                task_id=task.task_id,
                agent_id=node.agent_id,
                agent_name="unknown",
                success=False,
                error=f"Agent {node.agent_id} 未找到或已停用",
            )
        return result


# ═══════════════════════════════════════════
# 预置工作流
# ═══════════════════════════════════════════


def create_meeting_to_training_workflow() -> Workflow:
    """示例工作流：会议记录 → Meeting Agent → Knowledge Agent → KG → Training Agent"""
    wf = Workflow(
        name="会议知识沉淀工作流",
        description="会议记录 → Meeting Agent 提取要点 → Knowledge Agent 入库 → Training Agent 生成培训材料",
        tags=["meeting", "knowledge", "training"],
    )

    start = WorkflowNode(name="开始", node_type=NodeType.START)
    wf.add_node(start)

    meeting = WorkflowNode(
        name="会议要点提取",
        node_type=NodeType.AGENT,
        agent_id="builtin-meeting",
        description="从会议记录中提取要点和行动项",
    )
    wf.add_node(meeting)

    knowledge = WorkflowNode(
        name="知识入库",
        node_type=NodeType.AGENT,
        agent_id="builtin-knowledge",
        description="将会议要点写入知识库和图谱",
        config={"action": "ingest"},
    )
    wf.add_node(knowledge)

    training = WorkflowNode(
        name="生成培训材料",
        node_type=NodeType.AGENT,
        agent_id="builtin-training",
        description="基于新入库知识生成培训内容",
        config={"action": "generate"},
    )
    wf.add_node(training)

    end = WorkflowNode(name="结束", node_type=NodeType.END)
    wf.add_node(end)

    wf.set_start(start.node_id)
    wf.connect(start.node_id, meeting.node_id)
    wf.connect(meeting.node_id, knowledge.node_id)
    wf.connect(knowledge.node_id, training.node_id)
    wf.connect(training.node_id, end.node_id)

    return wf


def create_research_to_report_workflow() -> Workflow:
    """研究 → 报告工作流"""
    wf = Workflow(
        name="深度研究到报告工作流",
        description="Research Agent 研究 → Knowledge Agent 整理 → 生成最终报告",
        tags=["research", "report"],
    )

    start = WorkflowNode(name="开始", node_type=NodeType.START)
    wf.add_node(start)

    research = WorkflowNode(
        name="深度研究",
        node_type=NodeType.AGENT,
        agent_id="builtin-research",
        description="对主题进行深度研究",
    )
    wf.add_node(research)

    knowledge = WorkflowNode(
        name="知识整理",
        node_type=NodeType.AGENT,
        agent_id="builtin-knowledge",
        description="整理和结构化研究成果",
        config={"action": "organize"},
    )
    wf.add_node(knowledge)

    end = WorkflowNode(name="结束", node_type=NodeType.END)
    wf.add_node(end)

    wf.set_start(start.node_id)
    wf.connect(start.node_id, research.node_id)
    wf.connect(research.node_id, knowledge.node_id)
    wf.connect(knowledge.node_id, end.node_id)

    return wf
