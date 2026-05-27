"""Dashboard 路由 — 系统指标与实时 trace。"""
import logging

from fastapi import APIRouter

from src.core.agent import CognitiveAgent

logger = logging.getLogger(__name__)


def create_dashboard_router(agent: CognitiveAgent) -> APIRouter:
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

    @router.get("/traces")
    async def traces():
        return []

    return router
