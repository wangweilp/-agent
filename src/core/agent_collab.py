"""Multi-Agent Collaboration Core — SharedContext / AgentDelegation / TeamReasoning.

六边形架构核心层：只定义数据类和 Protocol，不引用任何外部库或适配器。
"""
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from src.core.types import Memory, ToolResult


# ── Shared Context ──


@dataclass
class SharedContext:
    """团队成员共享的记忆上下文。

    聚合 workspace 内所有成员的相关记忆，按成员分组，
    供 Agent 协作时理解团队知识全貌。
    """
    workspace_id: str
    query: str = ""
    team_memories: list[Memory] = field(default_factory=list)
    member_memories: dict[str, list[Memory]] = field(default_factory=dict)
    member_count: int = 0
    recent_activity: list[dict] = field(default_factory=list)

    @property
    def total_memories(self) -> int:
        return len(self.team_memories)

    def summary(self) -> str:
        parts = [
            f"Workspace {self.workspace_id}: {self.member_count} members, "
            f"{self.total_memories} shared memories."
        ]
        for user_id, mems in self.member_memories.items():
            parts.append(f"  - {user_id[:8]}: {len(mems)} memories")
        return "\n".join(parts)


# ── Agent Delegation ──


@dataclass
class AgentDelegation:
    """任务委托模型 — 委托 Agent 执行 recall/remember/reflect。

    agent_type 决定调用哪个底层工具：
        recall   → MemoryRetrievalService.retrieve
        remember → RememberTool.execute
        reflect  → ReflectTool.execute
    """
    workspace_id: str
    query: str
    agent_type: str            # "recall" | "remember" | "reflect"
    context: str = ""
    result: ToolResult | None = None
    executor_user_id: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.result is not None and self.result.success


# ── Team Reasoning ──


@dataclass
class ParticipantInsight:
    """单个参与者在联合推理中的贡献。"""
    user_id: str
    insight: str
    relevant_memories: list[Memory] = field(default_factory=list)


@dataclass
class TeamReasoning:
    """联合推理结果 — consensus (共识) / synthesis (综合)。"""
    workspace_id: str
    question: str
    participants: list[str] = field(default_factory=list)
    individual_insights: list[ParticipantInsight] = field(default_factory=list)
    consensus: str = ""
    synthesis: str = ""
    conflicts: list[str] = field(default_factory=list)

    @property
    def participant_count(self) -> int:
        return len(self.participants)


# ── Multi-Agent Coordinator Protocol ──


@runtime_checkable
class MultiAgentCoordinator(Protocol):
    """多 Agent 协作协调器协议。

    职责：
        1. 构建团队共享上下文 (SharedContext)
        2. 委托 Agent 执行任务 (AgentDelegation)
        3. 多 Agent 联合推理 (TeamReasoning)

    所有实现方只需满足此协议，即可被 workspace_router 或
    任何上层消费者注入使用。
    """

    def get_shared_context(
        self,
        workspace_id: str,
        query: str = "",
        top_k: int = 10,
    ) -> SharedContext:
        """为 workspace 构建团队共享记忆上下文。

        Args:
            workspace_id: 目标工作区。
            query: 可选的检索查询，用于过滤相关记忆。
            top_k: 每个成员最多返回的记忆数。

        Returns:
            SharedContext 包含聚合后的团队记忆、成员分布、最近活动。
        """
        ...

    def delegate(
        self,
        workspace_id: str,
        query: str,
        agent_type: str,
        context: str = "",
        executor_user_id: str = "",
    ) -> AgentDelegation:
        """委托 Agent 执行指定类型的任务。

        agent_type ∈ {"recall", "remember", "reflect"}。

        Args:
            workspace_id: 目标工作区。
            query: 任务查询/内容。
            agent_type: 委托的 Agent 类型。
            context: 额外的上下文信息。
            executor_user_id: 执行此委托的用户 ID（用于审计）。

        Returns:
            AgentDelegation 包含执行结果。
        """
        ...

    def reason(
        self,
        workspace_id: str,
        question: str,
        participants: list[str],
    ) -> TeamReasoning:
        """多 Agent 联合推理 — 收集各参与者视角，综合形成共识。

        Args:
            workspace_id: 目标工作区。
            question: 推理问题。
            participants: 参与推理的用户 ID 列表。

        Returns:
            TeamReasoning 包含共识、个体见解、冲突点。
        """
        ...
