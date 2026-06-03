"""Multi-Agent Collaboration API — 委托 / 共享上下文 / 联合推理。

端点:
    POST   /workspace/{id}/agent/delegate — 委托 Agent 执行任务
    GET    /workspace/{id}/agent/context  — 获取团队共享上下文
    POST   /workspace/{id}/agent/reason   — 联合推理
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.adapters.collab_adapter import DefaultMultiAgentCoordinator
from src.adapters.auth_store import WorkspaceContext
from src.api.middleware import require_auth, require_write
from src.core.auth import TokenPayload

logger = logging.getLogger(__name__)


# ── Schemas ──


class DelegateRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="委托查询/内容")
    agent_type: str = Field(..., pattern=r"^(recall|remember|reflect)$", description="Agent 类型")
    context: str = Field(default="", max_length=5000, description="额外上下文")


class ReasonRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="推理问题")
    participants: list[str] = Field(..., min_length=1, max_length=20, description="参与者 user_id 列表")


# ── Router Factory ──


def create_agent_collab_router(
    coordinator: DefaultMultiAgentCoordinator,
) -> APIRouter:
    router = APIRouter(tags=["agent-collab"])

    def _get_ws_id(id: str) -> str:
        """URL 中的 workspace id 优先于 context 中的。"""
        return id

    # ── Agent Delegation ──

    @router.post("/workspace/{id}/agent/delegate")
    async def delegate_agent(
        id: str,
        body: DelegateRequest,
        payload: TokenPayload = Depends(require_write),
    ) -> dict[str, Any]:
        """委托 Agent 执行 recall/remember/reflect 任务。

        - recall: 检索与 query 相关的共享记忆
        - remember: 存储 query 内容为团队记忆
        - reflect: 对 query 主题进行反思

        Returns:
            Delegation result with success status and tool output.
        """
        delegation = coordinator.delegate(
            workspace_id=id,
            query=body.query,
            agent_type=body.agent_type,
            context=body.context,
            executor_user_id=payload.user_id,
        )

        return {
            "workspace_id": delegation.workspace_id,
            "agent_type": delegation.agent_type,
            "query": delegation.query,
            "success": delegation.success,
            "result": {
                "content": delegation.result.content if delegation.result else "",
                "user_message": delegation.result.user_message if delegation.result else "",
                "error": delegation.result.error if delegation.result else None,
                "metadata": delegation.result.metadata if delegation.result else {},
            },
            "executor_user_id": delegation.executor_user_id,
            "metadata": delegation.metadata,
        }

    # ── Shared Context ──

    @router.get("/workspace/{id}/agent/context")
    async def get_agent_context(
        id: str,
        query: str = Query(default="", max_length=500, description="检索查询"),
        top_k: int = Query(default=10, ge=1, le=50, description="返回记忆数量上限"),
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """获取团队共享上下文。

        聚合 workspace 内所有成员的记忆，按成员分组。

        Returns:
            SharedContext: team_memories, member_memories, member_count, recent_activity.
        """
        ctx = coordinator.get_shared_context(
            workspace_id=id,
            query=query,
            top_k=top_k,
        )

        return {
            "workspace_id": ctx.workspace_id,
            "query": ctx.query,
            "member_count": ctx.member_count,
            "total_memories": ctx.total_memories,
            "team_memories": [
                {
                    "id": m.id,
                    "content": m.content[:300],
                    "summary": m.summary,
                    "source": m.source,
                    "importance": m.importance,
                    "entities": m.entities,
                    "memory_type": m.memory_type,
                    "timestamp": m.timestamp.isoformat() if m.timestamp else "",
                    "status": m.status,
                }
                for m in ctx.team_memories[:top_k]
            ],
            "member_memories": {
                uid[:12]: len(mems) for uid, mems in ctx.member_memories.items()
            },
            "recent_activity": ctx.recent_activity[:10],
            "summary": ctx.summary(),
        }

    # ── Team Reasoning ──

    @router.post("/workspace/{id}/agent/reason")
    async def team_reason(
        id: str,
        body: ReasonRequest,
        payload: TokenPayload = Depends(require_write),
    ) -> dict[str, Any]:
        """多 Agent 联合推理。

        收集每个参与者的相关记忆，综合形成共识/综合结论。

        Returns:
            TeamReasoning: consensus, synthesis, individual_insights, participants.
        """
        reasoning = coordinator.reason(
            workspace_id=id,
            question=body.question,
            participants=body.participants,
        )

        return {
            "workspace_id": reasoning.workspace_id,
            "question": reasoning.question,
            "participants": reasoning.participants,
            "participant_count": reasoning.participant_count,
            "consensus": reasoning.consensus,
            "synthesis": reasoning.synthesis,
            "conflicts": reasoning.conflicts,
            "individual_insights": [
                {
                    "user_id": ins.user_id,
                    "insight": ins.insight[:500],
                    "memory_count": len(ins.relevant_memories),
                }
                for ins in reasoning.individual_insights
            ],
        }

    return router
