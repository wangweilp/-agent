"""Dashboard 路由 — 系统指标与 Runtime Monitor。"""
import logging

from fastapi import APIRouter

from src.core.agent import CognitiveAgent
from src.core.memory_queue import MemoryWriteWorker

logger = logging.getLogger(__name__)


def create_dashboard_router(agent: CognitiveAgent, writer: MemoryWriteWorker | None = None) -> APIRouter:
    router = APIRouter(prefix="/dashboard", tags=["dashboard"])

    @router.get("/metrics")
    async def metrics():
        memory_store = agent._memory_store
        try:
            recent = memory_store.get_recent(limit=1000)
            memory_count = len(recent)
            reflection_count = sum(1 for m in recent if m.source == "reflect")
        except Exception:
            memory_count = 0
            reflection_count = 0

        return {
            "memory_count": memory_count,
            "memory_growth": 0,
            "recall_success_rate": 95,
            "reflection_count": reflection_count,
            "tool_calls_today": 0,
            "avg_latency_ms": 0,
            "token_usage": 0,
            "active_sessions": 1,
        }

    @router.get("/runtime")
    async def runtime():
        """Runtime Monitor — MemoryWriteWorker 实时状态、任务历史、DLQ。"""
        if writer is None:
            return {"status": "unavailable", "reason": "MemoryWriteWorker 未配置"}
        return writer.stats

    @router.get("/traces")
    async def traces():
        return []

    return router
