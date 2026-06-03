"""Multi-Agent Coordinator Adapter — 实现 MultiAgentCoordinator 协议。

从 CollaborationService 获取团队上下文，从 WorkspaceContext 获取当前 workspace，
调用 MemoryRetrievalService 检索团队共享记忆，复用 Recall/Reflect/Remember 工具。

依赖链：
    DefaultMultiAgentCoordinator
        ├── CollaborationService  (团队数据 + 审计/通知)
        ├── SQLiteAuthStore       (成员信息)
        ├── MemoryRetrievalService (记忆检索)
        └── ToolRegistry          (recall/remember/reflect 工具)
"""
import logging
from datetime import datetime, timezone

from src.adapters.auth_store import SQLiteAuthStore
from src.adapters.collab_store import CollaborationService
from src.core.agent_collab import (
    AgentDelegation,
    MultiAgentCoordinator,
    ParticipantInsight,
    SharedContext,
    TeamReasoning,
)
from src.core.collaboration import ActivityEvent, AuditAction, AuditLog
from src.core.retrieval import MemoryRetrievalService
from src.core.types import Memory, ToolResult

logger = logging.getLogger(__name__)


class DefaultMultiAgentCoordinator:
    """MultiAgentCoordinator 协议的默认实现。

    协调跨成员的记忆检索、任务委托和联合推理。
    所有外部能力通过构造注入，不持有全局引用。
    """

    def __init__(
        self,
        collab_service: CollaborationService,
        auth_store: SQLiteAuthStore,
        retrieval_service: MemoryRetrievalService,
        tool_registry,
    ) -> None:
        self._collab = collab_service
        self._auth = auth_store
        self._retrieval = retrieval_service
        self._tools = tool_registry

    # ── Shared Context ──

    def get_shared_context(
        self,
        workspace_id: str,
        query: str = "",
        top_k: int = 10,
    ) -> SharedContext:
        """构建团队共享记忆上下文。

        1. 获取 workspace 所有成员
        2. 按成员检索各自的相关记忆
        3. 聚合为 SharedContext
        """
        members = self._auth.list_members(workspace_id)
        if not members:
            return SharedContext(
                workspace_id=workspace_id,
                query=query,
                member_count=0,
            )

        all_memories: list[Memory] = []
        member_memories: dict[str, list[Memory]] = {}

        for member in members:
            user_id = member.user_id
            member_mems = self._retrieve_for_user(
                user_id=user_id,
                query=query,
                top_k=max(top_k, 1),
            )
            if member_mems:
                member_memories[user_id] = member_mems
                all_memories.extend(member_mems)

        # 去重（同一记忆可能被多个成员共享）
        seen: set[str] = set()
        unique_memories: list[Memory] = []
        for mem in all_memories:
            if mem.id not in seen:
                seen.add(mem.id)
                unique_memories.append(mem)

        # 获取最近活动
        recent_activity: list[dict] = []
        try:
            recent_activity = self._collab.get_activity_log(workspace_id, limit=10)
        except Exception:
            logger.debug("get_shared_context:activity_log_failed", exc_info=True)

        ctx = SharedContext(
            workspace_id=workspace_id,
            query=query,
            team_memories=unique_memories,
            member_memories=member_memories,
            member_count=len(members),
            recent_activity=recent_activity,
        )

        logger.info(
            "shared_context_built",
            extra={
                "workspace_id": workspace_id,
                "member_count": ctx.member_count,
                "memory_count": ctx.total_memories,
            },
        )
        return ctx

    def _retrieve_for_user(
        self,
        user_id: str,
        query: str,
        top_k: int,
    ) -> list[Memory]:
        """检索特定用户的记忆。

        利用 MemoryRetrievalService 的语义搜索能力，
        但当前检索服务不按 user 过滤，因此返回全局结果后
        按 workspace 内成员上下文筛选。

        此处返回所有相关记忆（不做 user 级别过滤），
        因为共享上下文本就是"团队视角"。
        """
        if not query.strip():
            # 无查询时返回最近记忆
            try:
                return self._retrieval._memory_store.get_recent(limit=top_k)
            except Exception:
                return []

        return self._retrieval.retrieve(query, top_k=top_k)

    # ── Agent Delegation ──

    def delegate(
        self,
        workspace_id: str,
        query: str,
        agent_type: str,
        context: str = "",
        executor_user_id: str = "",
    ) -> AgentDelegation:
        """委托 Agent 执行任务。

        agent_type ∈ {"recall", "remember", "reflect"}。
        委托结果记录审计日志。
        """
        valid_types = {"recall", "remember", "reflect"}
        if agent_type not in valid_types:
            return AgentDelegation(
                workspace_id=workspace_id,
                query=query,
                agent_type=agent_type,
                context=context,
                result=ToolResult(
                    tool_name=agent_type,
                    success=False,
                    error=f"无效的 agent_type: {agent_type}，支持: {', '.join(sorted(valid_types))}",
                    user_message=f"不支持的操作类型: {agent_type}",
                ),
                executor_user_id=executor_user_id,
            )

        # 根据 agent_type 构造参数
        arguments = self._build_delegation_args(agent_type, query, context)

        try:
            result = self._tools.execute(agent_type, arguments)
        except Exception as e:
            logger.error(
                "agent_delegation_failed",
                extra={
                    "workspace_id": workspace_id,
                    "agent_type": agent_type,
                    "error": str(e)[:200],
                },
            )
            result = ToolResult(
                tool_name=agent_type,
                success=False,
                error=str(e),
                user_message="Agent 执行失败，请稍后重试。",
            )

        # 审计日志
        self._log_delegation(workspace_id, executor_user_id, agent_type, query, result)

        delegation = AgentDelegation(
            workspace_id=workspace_id,
            query=query,
            agent_type=agent_type,
            context=context,
            result=result,
            executor_user_id=executor_user_id,
            metadata={
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        logger.info(
            "agent_delegation_complete",
            extra={
                "workspace_id": workspace_id,
                "agent_type": agent_type,
                "success": delegation.success,
            },
        )
        return delegation

    def _build_delegation_args(
        self,
        agent_type: str,
        query: str,
        context: str,
    ) -> dict:
        """根据 agent_type 构造工具调用参数。"""
        if agent_type == "recall":
            return {"query": query, "top_k": 5}
        elif agent_type == "remember":
            content = f"{query}"
            if context:
                content = f"{context}\n\n{query}"
            return {"content": content, "entities": []}
        elif agent_type == "reflect":
            topic = query
            if context:
                topic = f"{query} (上下文: {context})"
            return {"topic": topic, "recent_n": 10}
        return {}

    def _log_delegation(
        self,
        workspace_id: str,
        executor_user_id: str,
        agent_type: str,
        query: str,
        result: ToolResult,
    ) -> None:
        """记录委托审计日志和活动事件。"""
        try:
            audit_action_map = {
                "recall": AuditAction.MEMORY_CREATE,
                "remember": AuditAction.MEMORY_CREATE,
                "reflect": AuditAction.MEMORY_CREATE,
            }
            action = audit_action_map.get(agent_type, AuditAction.MEMORY_CREATE)

            self._collab._store.log_audit(AuditLog(
                workspace_id=workspace_id,
                user_id=executor_user_id or "system",
                action=action,
                resource_type="agent_delegation",
                resource_id=agent_type,
                detail=f"Agent delegation: {agent_type} query='{query[:100]}' success={result.success}",
            ))
        except Exception:
            logger.debug("delegation_audit_failed", exc_info=True)

    # ── Team Reasoning ──

    def reason(
        self,
        workspace_id: str,
        question: str,
        participants: list[str],
    ) -> TeamReasoning:
        """多 Agent 联合推理。

        对每个参与者：
            1. 检索其与问题相关的记忆
            2. 基于记忆生成个体见解（摘要）
        综合所有见解形成共识/综合结论。
        """
        if not participants:
            return TeamReasoning(
                workspace_id=workspace_id,
                question=question,
                consensus="没有指定参与者，无法进行联合推理。",
            )

        reasoning = TeamReasoning(
            workspace_id=workspace_id,
            question=question,
            participants=list(participants),
        )

        # 收集每个参与者的见解
        all_insights_text: list[str] = []

        for user_id in participants:
            user_memories = self._retrieve_for_user(
                user_id=user_id,
                query=question,
                top_k=5,
            )

            insight_text = self._generate_insight(user_id, question, user_memories)
            if insight_text:
                all_insights_text.append(f"[{user_id[:8]}]: {insight_text}")

            reasoning.individual_insights.append(
                ParticipantInsight(
                    user_id=user_id,
                    insight=insight_text or "未找到相关记忆。",
                    relevant_memories=user_memories,
                )
            )

        # 综合：所有人见解的拼接 + 简单共识提取
        if all_insights_text:
            reasoning.synthesis = "\n\n".join(all_insights_text)
            reasoning.consensus = self._extract_consensus(
                question, reasoning.individual_insights
            )

        logger.info(
            "team_reasoning_complete",
            extra={
                "workspace_id": workspace_id,
                "participants": len(participants),
                "insight_count": len(all_insights_text),
            },
        )
        return reasoning

    def _generate_insight(
        self,
        user_id: str,
        question: str,
        memories: list[Memory],
    ) -> str:
        """基于用户记忆生成个体见解（摘要形式）。

        无 LLM 调用时，直接基于记忆内容生成结构化摘要。
        """
        if not memories:
            return ""

        insights_parts: list[str] = []
        for mem in memories[:5]:
            text = mem.summary or mem.content[:150]
            insights_parts.append(f"  - {text}")

        if insights_parts:
            return (
                f"基于 {len(memories)} 条相关记忆的观点：\n"
                + "\n".join(insights_parts)
            )
        return ""

    @staticmethod
    def _extract_consensus(
        question: str,
        insights: list[ParticipantInsight],
    ) -> str:
        """从个体见解中提取共识。

        基于规则的简单共识提取：
        - 如果只有 1 个参与者，返回其见解
        - 多个参与者时，统计共同主题
        """
        non_empty = [ins for ins in insights if ins.insight and ins.insight != "未找到相关记忆。"]
        if not non_empty:
            return f"对于问题「{question}」，团队成员暂无相关记忆可供综合判断。"

        if len(non_empty) == 1:
            return (
                f"对于问题「{question}」，单一参与者提供了以下见解：\n"
                f"{non_empty[0].insight[:500]}"
            )

        # 多参与者：汇总
        total_memories = sum(len(ins.relevant_memories) for ins in non_empty)
        lines = [
            f"对于问题「{question}」，{len(non_empty)} 位团队成员参与了联合推理。",
            f"共检索到 {total_memories} 条相关记忆。",
            "",
            "各参与者见解摘要：",
        ]
        for ins in non_empty:
            lines.append(f"\n--- {ins.user_id[:8]} ---")
            lines.append(ins.insight[:300])

        if total_memories >= 5:
            lines.append(
                f"\n综合判断：基于 {total_memories} 条关联记忆，"
                "建议团队就各自记忆中的共同线索进一步对齐。"
            )

        return "\n".join(lines)
