"""Analytics Pipeline 集成层 — 将现有 Runtime 接入 AnalyticsStore。

设计原则：
- 不修改 Agent / Memory / Chat 的核心逻辑，仅在外部包装调用
- 提供 async helper 函数，供 Router / Worker 调用
- 失败降级：任何 AnalyticsStore 写入失败不影响主业务

接入点：
1. Agent Worker — AgentRegistry.run() 后调用 record_agent_run_from_result()
2. Memory Service — SQLiteStoreAdapter.store()/delete()/get_by_id() 后调用 record_memory_event_*()
3. Chat Runtime — /chat 端点结束后调用 record_chat_activity()
"""
import asyncio
import logging
from datetime import datetime, timezone

from src.core.analytics.analytics_store import AnalyticsStore

logger = logging.getLogger(__name__)


class AnalyticsPipeline:
    """Analytics Pipeline 集成层 — 包装 AnalyticsStore，提供业务友好的接入方法。

    所有方法为 async，失败时仅记录日志。
    """

    def __init__(self, store: AnalyticsStore) -> None:
        self._store = store

    # ── Agent Worker 接入 ────────────────────────────────

    async def record_agent_run_from_result(
        self,
        result,
        tenant_id: str = "",
        workspace_id: str = "",
    ) -> None:
        """从 AgentResult 记录 Agent 运行到 Analytics Pipeline。

        Args:
            result: AgentResult dataclass（含 success, duration_ms, tokens_used, agent_name）
        """
        try:
            status = "success" if result.success else "failed"
            # tokens_used 拆分为 prompt/completion（P0 阶段简化，全部计入 prompt）
            prompt_tokens = getattr(result, "tokens_used", 0) or 0
            await self._store.record_agent_run(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                agent_name=getattr(result, "agent_name", "") or "",
                status=status,
                duration_ms=getattr(result, "duration_ms", 0.0) or 0.0,
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                cost_usd=0.0,
            )
        except Exception:
            logger.warning("analytics_record_agent_run_failed", exc_info=True)

    # ── Memory Service 接入 ──────────────────────────────

    async def record_memory_insert(
        self,
        tenant_id: str,
        workspace_id: str,
        memory_type: str = "episodic",
    ) -> None:
        """记录 Memory INSERT 事件。"""
        try:
            await self._store.record_memory_event(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                memory_type=memory_type,
                event_type="INSERT",
                hit=False,
            )
        except Exception:
            logger.warning("analytics_record_memory_insert_failed", exc_info=True)

    async def record_memory_update(
        self,
        tenant_id: str,
        workspace_id: str,
        memory_type: str = "episodic",
    ) -> None:
        """记录 Memory UPDATE 事件。"""
        try:
            await self._store.record_memory_event(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                memory_type=memory_type,
                event_type="UPDATE",
                hit=False,
            )
        except Exception:
            logger.warning("analytics_record_memory_update_failed", exc_info=True)

    async def record_memory_delete(
        self,
        tenant_id: str,
        workspace_id: str,
        memory_type: str = "episodic",
    ) -> None:
        """记录 Memory DELETE 事件。"""
        try:
            await self._store.record_memory_event(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                memory_type=memory_type,
                event_type="DELETE",
                hit=False,
            )
        except Exception:
            logger.warning("analytics_record_memory_delete_failed", exc_info=True)

    async def record_memory_hit(
        self,
        tenant_id: str,
        workspace_id: str,
        memory_type: str = "episodic",
    ) -> None:
        """记录 Memory HIT 事件（检索命中）。"""
        try:
            await self._store.record_memory_event(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                memory_type=memory_type,
                event_type="HIT",
                hit=True,
            )
        except Exception:
            logger.warning("analytics_record_memory_hit_failed", exc_info=True)

    # ── Chat Runtime 接入 ─────────────────────────────────

    async def record_chat_activity(
        self,
        tenant_id: str,
        workspace_id: str,
        user_id: str,
        messages: int = 1,
        active_minutes: int = 1,
    ) -> None:
        """记录 Chat 消息结束后的用户活动。

        同时触发 user_activity 和 token_usage 记录。
        """
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            await self._store.record_user_activity(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                user_id=user_id,
                event_date=today,
                sessions=1,
                messages=messages,
                active_minutes=active_minutes,
            )
        except Exception:
            logger.warning("analytics_record_chat_activity_failed", exc_info=True)

    async def record_chat_token_usage(
        self,
        tenant_id: str,
        workspace_id: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """记录 Chat 消息的 Token 消耗。"""
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            await self._store.record_token_usage(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                event_date=today,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
            )
        except Exception:
            logger.warning("analytics_record_chat_token_usage_failed", exc_info=True)

    # ── 综合接入：Agent 运行后同时记录 user_activity + token_usage ──

    async def record_agent_run_full(
        self,
        result,
        tenant_id: str = "",
        workspace_id: str = "",
        user_id: str = "",
    ) -> None:
        """Agent 运行结束后综合记录：agent_run + user_activity + token_usage。"""
        await self.record_agent_run_from_result(result, tenant_id, workspace_id)
        if user_id:
            await self.record_chat_activity(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                user_id=user_id,
                messages=1,
                active_minutes=1,
            )
        tokens = getattr(result, "tokens_used", 0) or 0
        if tokens > 0:
            await self.record_chat_token_usage(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                prompt_tokens=tokens,
                completion_tokens=0,
                cost_usd=0.0,
            )
