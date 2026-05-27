"""FastAPI 路由 — /chat 端点与 SSE 流式返回。

SSE 事件类型：
- event: token      → 逐块回复文本
- event: tool_call  → Agent 调用了工具
- event: tool_result → 工具执行结果
- event: done       → 对话结束
- event: error      → 异常
"""
import asyncio
import json
import logging
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from src.api.schemas import ChatRequest, ChatResponse
from src.core.agent import CognitiveAgent

logger = logging.getLogger(__name__)


def _check_vectorized(vs, memory_id: str) -> bool:
    """检查 memory 是否在向量存储中。

    使用 ChromaDB get 直接查询——不依赖 embedding 搜索。
    """
    try:
        result = vs._collection.get(ids=[memory_id], include=[])
        return bool(result and result.get("ids") and len(result["ids"]) > 0)
    except Exception:
        return False


def create_router(agent: CognitiveAgent) -> APIRouter:
    router = APIRouter()

    @router.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse:
        try:
            reply = await asyncio.to_thread(agent.run, request.content)
            return ChatResponse(reply=reply)
        except Exception as e:
            logger.exception("chat endpoint error")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/chat/stream")
    async def chat_stream(request: ChatRequest):
        async def generate():
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

            def _run():
                try:
                    for token in agent.run_stream(request.content):
                        loop.call_soon_threadsafe(queue.put_nowait, ("token", token))
                    loop.call_soon_threadsafe(queue.put_nowait, ("done", ""))
                except Exception as e:
                    logger.exception("chat stream error")
                    loop.call_soon_threadsafe(queue.put_nowait, ("error", str(e)))

            thread = threading.Thread(target=_run, daemon=True)
            thread.start()

            while True:
                event_type, data = await queue.get()
                if event_type == "done":
                    yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"
                    break
                elif event_type == "error":
                    yield f"event: error\ndata: {json.dumps({'message': data})}\n\n"
                    break
                else:
                    yield f"event: token\ndata: {json.dumps({'text': data})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/")
    async def root():
        return {
            "status": "ok",
            "service": "Agent Memory",
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/health",
        }

    @router.get("/health")
    async def health():
        return {
            "status": "healthy",
            "agent": {
                "short_term_size": agent.short_term_size,
                "trace_id": agent.trace_id,
            },
        }

    # ── Memory ──

    @router.get("/memory")
    async def list_memories(q: str = "", limit: int = 50):
        store = agent._memory_store
        vs = agent._vector_store
        try:
            memories = store.get_recent(limit=500)
        except Exception:
            memories = []
        if q:
            q_lower = q.lower()
            memories = [
                m for m in memories
                if q_lower in m.content.lower()
                or any(q_lower in e.lower() for e in m.entities)
            ]
        memories = memories[:limit]
        return [
            {
                "id": m.id,
                "content": m.content,
                "summary": m.summary,
                "source": m.source,
                "timestamp": m.timestamp.isoformat(),
                "importance": m.importance,
                "entities": m.entities,
                "memory_type": m.memory_type,
                "access_count": m.access_count,
                "last_accessed": m.last_accessed.isoformat() if m.last_accessed else None,
                "embedding_status": "vectorized" if _check_vectorized(vs, m.id) else "missing",
            }
            for m in memories
        ]

    @router.get("/memory/{memory_id}")
    async def get_memory(memory_id: str):
        store = agent._memory_store
        m = store.get_by_id(memory_id)
        if m is None:
            raise HTTPException(status_code=404, detail="记忆不存在")
        vs = agent._vector_store
        return {
            "id": m.id,
            "content": m.content,
            "summary": m.summary,
            "source": m.source,
            "timestamp": m.timestamp.isoformat(),
            "importance": m.importance,
            "entities": m.entities,
            "memory_type": m.memory_type,
            "access_count": m.access_count,
            "last_accessed": m.last_accessed.isoformat() if m.last_accessed else None,
            "embedding_status": "vectorized" if _check_vectorized(vs, m.id) else "missing",
        }

    # ── Reflection ──

    @router.get("/reflection")
    async def list_reflections():
        store = agent._memory_store
        try:
            recent = store.get_recent(limit=200)
        except Exception:
            recent = []
        reflections = [m for m in recent if m.source == "reflect"]
        return [
            {
                "id": m.id,
                "topic": (m.entities[0] if m.entities else ""),
                "finding": m.summary or m.content[:200],
                "confidence": m.importance / 10.0,
                "timestamp": m.timestamp.isoformat(),
                "related_memories": m.entities,
            }
            for m in reflections
        ]

    # ── Tools ──

    @router.get("/tools")
    async def list_tools():
        registry = agent._tool_executor
        result = []
        for name in registry.tool_names:
            tool = registry._tools.get(name)
            if tool is None:
                continue
            meta = getattr(tool, "metadata", {})
            result.append({
                "name": tool.name,
                "description": tool.description,
                "category": meta.get("category", "general"),
                "requires_confirmation": tool.requires_confirmation,
                "call_count": 0,
                "avg_duration_ms": 0,
                "success_rate": 100,
                "risk_level": "low",
                "enabled": True,
            })
        return result

    @router.patch("/tools/{tool_name}")
    async def toggle_tool(tool_name: str, body: dict = {}):
        enabled = body.get("enabled")
        if enabled is None:
            raise HTTPException(status_code=400, detail="缺少 enabled 字段")
        return {"name": tool_name, "enabled": enabled}

    # ── Debug: Retrieval Inspector ──

    @router.get("/debug/retrieve")
    async def debug_retrieve(q: str = "", top_k: int = 5):
        """Retrieval Inspector: 输入 query，返回分步 score 详情。"""
        from src.core.retrieval import MemoryRetrievalService

        service = MemoryRetrievalService(
            agent._memory_store, agent._vector_store, agent._embedding,
        )
        results = service.retrieve(q, top_k=top_k, with_breakdown=True)
        return [
            {
                "memory_id": r["memory"].id,
                "content": (r["memory"].summary or r["memory"].content)[:200],
                "source": r["memory"].source,
                "importance": r["memory"].importance,
                "rrf_score": r["rrf_score"],
                "time_factor": r["time_factor"],
                "importance_factor": r["importance_factor"],
                "access_bonus": r["access_bonus"],
                "final_score": r["final_score"],
                "timestamp": r["memory"].timestamp.isoformat(),
            }
            for r in results
        ]

    # ── Debug: Event Timeline ──

    @router.get("/debug/events")
    async def debug_events(limit: int = 100):
        """Event Timeline: 返回最近的系统事件流。"""
        from src.core.events import recent

        events = recent(limit)
        return [
            {
                "id": e.id,
                "type": e.type,
                "timestamp": e.timestamp,
                "data": e.data,
            }
            for e in events
        ]

    return router


