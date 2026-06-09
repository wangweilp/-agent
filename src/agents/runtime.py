from __future__ import annotations

"""Agent Runtime — 统一 Agent 协议与 PEOR 执行循环。

提供：
- AgentContext   — 执行上下文（记忆、知识图谱、工具，含租户/用户/权限）
- AgentTask      — 任务定义
- AgentResult    — 执行结果（含 trace、memory_refs、knowledge_refs、timeout）
- Agent          — 统一协议：Plan → Execute → Observe → Reflect
- Tool Calling / Memory Calling / Knowledge Graph Calling

安全约束：
- 所有 Agent 执行必须有 tenant_id/user_id（不可为空，开发模式默认放行）
- 不允许 Agent 绕过权限和租户隔离
- 不允许让 Agent 直接访问未经授权的数据
"""

DEFAULT_AGENT_TIMEOUT_SECONDS = 60  # Agent 执行超时默认值

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════


class AgentStatus(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    OBSERVING = "observing"
    REFLECTING = "reflecting"
    DONE = "done"
    FAILED = "failed"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ═══════════════════════════════════════════
# Tool Calling Protocol
# ═══════════════════════════════════════════


@dataclass
class ToolDefinition:
    """工具定义 — 与 OpenAI/DeepSeek function calling 兼容。"""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    handler: Callable[..., Any] | None = None

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolCallResult:
    tool_name: str
    success: bool
    content: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolProvider(Protocol):
    """工具提供者协议。"""
    def list_tools(self) -> list[ToolDefinition]: ...
    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolCallResult: ...


# ═══════════════════════════════════════════
# Memory Calling Protocol
# ═══════════════════════════════════════════


@dataclass
class MemoryResult:
    memory_id: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryProvider(Protocol):
    """记忆提供者协议。"""
    def search(self, query: str, top_k: int = 5) -> list[MemoryResult]: ...
    def remember(self, content: str, metadata: dict[str, Any] | None = None) -> str: ...


# ═══════════════════════════════════════════
# Knowledge Graph Calling Protocol
# ═══════════════════════════════════════════


@dataclass
class GraphEntity:
    id: str
    name: str
    entity_type: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphRelation:
    source: str
    target: str
    predicate: str
    weight: float = 1.0


class KnowledgeGraphProvider(Protocol):
    """知识图谱提供者协议。"""
    def query_entities(self, query: str, top_k: int = 10) -> list[GraphEntity]: ...
    def query_relations(self, entity_id: str) -> list[GraphRelation]: ...
    def traverse(self, start_id: str, depth: int = 2) -> dict[str, Any]: ...


# ═══════════════════════════════════════════
# AgentContext
# ═══════════════════════════════════════════


class PermissionChecker(Protocol):
    """权限检查器协议 — 在 Agent 执行前验证用户是否有权调用。"""

    def check(
        self,
        user_id: str,
        tenant_id: str,
        resource: str,
        action: str,
    ) -> bool:
        """返回 True 表示授权，False 表示拒绝。"""
        ...


@dataclass
class AgentContext:
    """Agent 执行上下文 — 注入所有外部能力。

    包含租户上下文、用户上下文和权限上下文，
    确保 Agent 执行不绕过多租户隔离和 RBAC 控制。
    """
    agent_id: str
    agent_name: str
    tools: ToolProvider | None = None
    memory: MemoryProvider | None = None
    knowledge_graph: KnowledgeGraphProvider | None = None
    config: dict[str, Any] = field(default_factory=dict)
    parent_execution_id: str | None = None

    # 租户与用户上下文
    tenant_id: str = ""
    user_id: str = ""
    workspace_id: str = ""
    user_roles: list[str] = field(default_factory=list)
    permission_checker: PermissionChecker | None = None

    # 运行时状态
    status: AgentStatus = AgentStatus.IDLE
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def record_metric(self, key: str, value: Any) -> None:
        self.metrics[key] = value

    def add_to_history(self, role: str, content: str) -> None:
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def check_permission(self, resource: str, action: str = "execute") -> bool:
        """验证当前用户是否对指定资源有操作权限。"""
        if self.permission_checker is None:
            return True  # 无检查器时默认放行（开发模式）
        return self.permission_checker.check(
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            resource=resource,
            action=action,
        )


# ═══════════════════════════════════════════
# AgentTask
# ═══════════════════════════════════════════


@dataclass
class AgentTask:
    """Agent 任务定义。"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    input_data: dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.MEDIUM
    deadline: datetime | None = None
    assigned_to: str = ""  # agent_id
    created_by: str = ""   # user_id or system
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════
# ExecutionTrace
# ═══════════════════════════════════════════


@dataclass
class ExecutionTraceStep:
    """执行链路中的单个步骤。"""
    phase: str  # plan | execute | observe | reflect | tool_call | memory_call | kg_call
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    detail: str = ""
    duration_ms: float = 0.0
    success: bool = True
    error: str | None = None


# ═══════════════════════════════════════════
# AgentResult
# ═══════════════════════════════════════════


@dataclass
class AgentResult:
    """Agent 执行结果。"""
    task_id: str
    agent_id: str
    agent_name: str
    success: bool
    output: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    # 执行指标
    plan: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    reflections: list[str] = field(default_factory=list)
    tool_calls_count: int = 0
    memory_calls_count: int = 0
    kg_calls_count: int = 0
    duration_ms: float = 0.0
    tokens_used: int = 0

    # 执行链路追踪
    trace: list[ExecutionTraceStep] = field(default_factory=list)
    memory_refs: list[str] = field(default_factory=list)  # 引用的 memory_id
    knowledge_refs: list[str] = field(default_factory=list)  # 引用的 entity_id
    tool_calls: list[str] = field(default_factory=list)  # 调用的 tool_name
    timeout_occurred: bool = False

    started_at: datetime | None = None
    finished_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "success": self.success,
            "output": self.output,
            "data": self.data,
            "error": self.error,
            "plan": self.plan,
            "observations": self.observations,
            "reflections": self.reflections,
            "tool_calls_count": self.tool_calls_count,
            "memory_calls_count": self.memory_calls_count,
            "kg_calls_count": self.kg_calls_count,
            "duration_ms": self.duration_ms,
            "tokens_used": self.tokens_used,
            "trace": [
                {
                    "phase": t.phase,
                    "timestamp": t.timestamp.isoformat(),
                    "detail": t.detail,
                    "duration_ms": t.duration_ms,
                    "success": t.success,
                    "error": t.error,
                }
                for t in self.trace
            ],
            "memory_refs": self.memory_refs,
            "knowledge_refs": self.knowledge_refs,
            "tool_calls": self.tool_calls,
            "timeout_occurred": self.timeout_occurred,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


# ═══════════════════════════════════════════
# Agent 统一协议
# ═══════════════════════════════════════════


class Agent(ABC):
    """企业 Agent 统一协议。

    每个 Agent 实现 PEOR 循环：
    - Plan    → 分析任务，制定执行计划
    - Execute → 执行计划（调用工具/记忆/知识图谱）
    - Observe → 观察执行结果，收集反馈
    - Reflect → 反思结果，决定是否继续或完成
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str = "",
        version: str = "1.0.0",
        tools: ToolProvider | None = None,
        memory: MemoryProvider | None = None,
        knowledge_graph: KnowledgeGraphProvider | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.version = version
        self._tools = tools
        self._memory = memory
        self._kg = knowledge_graph
        self._config = config or {}
        self._status = AgentStatus.IDLE
        self._metrics: dict[str, Any] = {}
        self._timeout_seconds = config.get("timeout_seconds", DEFAULT_AGENT_TIMEOUT_SECONDS) if config else DEFAULT_AGENT_TIMEOUT_SECONDS

    # ── PEOR 抽象方法 ──

    @abstractmethod
    def plan(self, context: AgentContext, task: AgentTask) -> list[str]:
        """分析任务，返回执行步骤列表。"""
        ...

    @abstractmethod
    def execute(self, context: AgentContext, task: AgentTask, plan: list[str]) -> str:
        """执行计划，返回主要输出。"""
        ...

    @abstractmethod
    def observe(self, context: AgentContext, output: str) -> list[str]:
        """观察输出，返回发现/反馈列表。"""
        ...

    @abstractmethod
    def reflect(self, context: AgentContext, observations: list[str], output: str) -> tuple[bool, str]:
        """反思结果。返回 (是否完成, 修正或确认信息)。"""
        ...

    # ── 公共方法 ──

    @property
    def timeout_seconds(self) -> int:
        return self._timeout_seconds

    def run(
        self,
        task: AgentTask,
        *,
        tenant_id: str = "",
        user_id: str = "",
        workspace_id: str = "",
        user_roles: list[str] | None = None,
        permission_checker: PermissionChecker | None = None,
    ) -> AgentResult:
        """完整 PEOR 循环。含超时控制、执行链路追踪、上下文验证。"""
        # ── 上下文验证 ──
        if not tenant_id:
            logger.warning("agent_run_no_tenant", extra={"agent": self.name, "task": task.title})
        if not user_id:
            logger.warning("agent_run_no_user", extra={"agent": self.name, "task": task.title})

        started_at = datetime.now(timezone.utc)
        t_start = time.monotonic()

        context = AgentContext(
            agent_id=self.agent_id,
            agent_name=self.name,
            tools=self._tools,
            memory=self._memory,
            knowledge_graph=self._kg,
            config=self._config,
            tenant_id=tenant_id,
            user_id=user_id,
            workspace_id=workspace_id,
            user_roles=user_roles or [],
            permission_checker=permission_checker,
        )

        result = AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            agent_name=self.name,
            success=False,
            started_at=started_at,
        )

        try:
            # P: Plan
            t0 = time.monotonic()
            self._status = AgentStatus.PLANNING
            context.status = AgentStatus.PLANNING
            logger.info("agent_plan_start", extra={"agent": self.name, "task": task.title})
            plan = self.plan(context, task)
            result.plan = plan
            result.trace.append(ExecutionTraceStep(
                phase="plan", detail=f"生成 {len(plan)} 步计划",
                duration_ms=(time.monotonic() - t0) * 1000,
            ))
            logger.info("agent_plan_done", extra={"agent": self.name, "steps": len(plan)})

            # E: Execute
            t0 = time.monotonic()
            # 超时检查
            elapsed = (time.monotonic() - t_start)
            if elapsed > self._timeout_seconds:
                result.timeout_occurred = True
                result.error = f"Agent 执行超时 (>{self._timeout_seconds}s)"
                self._status = AgentStatus.FAILED
                return result

            self._status = AgentStatus.EXECUTING
            context.status = AgentStatus.EXECUTING
            logger.info("agent_execute_start", extra={"agent": self.name})
            output = self.execute(context, task, plan)
            result.output = output
            result.trace.append(ExecutionTraceStep(
                phase="execute", detail=f"输出 {len(output)} 字符",
                duration_ms=(time.monotonic() - t0) * 1000,
            ))

            # O: Observe
            t0 = time.monotonic()
            self._status = AgentStatus.OBSERVING
            context.status = AgentStatus.OBSERVING
            observations = self.observe(context, output)
            result.observations = observations
            result.trace.append(ExecutionTraceStep(
                phase="observe", detail=f"{len(observations)} 条观察",
                duration_ms=(time.monotonic() - t0) * 1000,
            ))

            # R: Reflect
            t0 = time.monotonic()
            self._status = AgentStatus.REFLECTING
            context.status = AgentStatus.REFLECTING
            try:
                done, reflection = self.reflect(context, observations, output)
                result.reflections.append(reflection)
                result.trace.append(ExecutionTraceStep(
                    phase="reflect", detail=reflection[:200],
                    duration_ms=(time.monotonic() - t0) * 1000,
                    success=done,
                ))
            except Exception as reflect_err:
                result.trace.append(ExecutionTraceStep(
                    phase="reflect", detail="反思阶段异常",
                    duration_ms=(time.monotonic() - t0) * 1000,
                    success=False, error=str(reflect_err),
                ))
                done = False
                reflection = ""

            # 如果未完成，尝试一次修正
            if not done and reflection:
                logger.info("agent_reflect_retry", extra={"agent": self.name, "reflection": reflection[:100]})
                context.add_to_history("system", f"修正建议: {reflection}")
                revised_output = self.execute(context, task, plan)
                result.output = f"{output}\n\n[修正后]\n{revised_output}"
                output = revised_output
                result.trace.append(ExecutionTraceStep(
                    phase="retry", detail="执行修正",
                ))

            result.success = True
            self._status = AgentStatus.DONE
            context.status = AgentStatus.DONE

        except Exception as e:
            logger.exception("agent_run_failed", extra={"agent": self.name, "error": str(e)})
            result.trace.append(ExecutionTraceStep(
                phase="error", detail="执行异常",
                success=False, error=str(e)[:500],
            ))
            result.success = False
            result.error = str(e)
            self._status = AgentStatus.FAILED
            context.status = AgentStatus.FAILED

        finally:
            result.duration_ms = (time.monotonic() - t_start) * 1000
            result.finished_at = datetime.now(timezone.utc)
            self._update_metrics(result)

        logger.info(
            "agent_run_done",
            extra={
                "agent": self.name,
                "success": result.success,
                "duration_ms": round(result.duration_ms, 1),
            },
        )
        return result

    def _update_metrics(self, result: AgentResult) -> None:
        self._metrics["total_runs"] = self._metrics.get("total_runs", 0) + 1
        if result.success:
            self._metrics["successful_runs"] = self._metrics.get("successful_runs", 0) + 1
        else:
            self._metrics["failed_runs"] = self._metrics.get("failed_runs", 0) + 1
        durations = self._metrics.setdefault("durations_ms", [])
        durations.append(result.duration_ms)

    # ── 属性 ──

    @property
    def status(self) -> AgentStatus:
        return self._status

    @property
    def metrics(self) -> dict[str, Any]:
        return dict(self._metrics)

    def get_success_rate(self) -> float:
        total = self._metrics.get("total_runs", 0)
        if total == 0:
            return 1.0
        return self._metrics.get("successful_runs", 0) / total

    def get_avg_duration_ms(self) -> float:
        durations = self._metrics.get("durations_ms", [])
        if not durations:
            return 0.0
        return sum(durations) / len(durations)


# ═══════════════════════════════════════════
# BaseAgent — 带默认实现的便利基类
# ═══════════════════════════════════════════


class BaseAgent(Agent):
    """提供 PEOR 默认实现的便利基类。

    子类只需覆盖 execute()，其他阶段有合理默认值。
    """

    def plan(self, context: AgentContext, task: AgentTask) -> list[str]:
        """默认计划：拆分为分析→检索→生成→验证四步。"""
        return [
            f"分析任务: {task.title}",
            "检索相关知识",
            "生成结果",
            "验证输出质量",
        ]

    def observe(self, context: AgentContext, output: str) -> list[str]:
        """默认观察：检查输出是否非空、是否包含关键信息。"""
        observations = []
        if not output.strip():
            observations.append("输出为空")
        else:
            observations.append(f"输出长度: {len(output)} 字符")
        if self._memory:
            try:
                memories = self._memory.search(output[:200], top_k=3)
                if memories:
                    observations.append(f"找到 {len(memories)} 条相关记忆")
            except Exception:
                pass
        return observations

    def reflect(self, context: AgentContext, observations: list[str], output: str) -> tuple[bool, str]:
        """默认反思：有输出且无错误即完成。"""
        done = bool(output and output.strip())
        return done, "任务完成" if done else "输出为空，需要重新执行"
