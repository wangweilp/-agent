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
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.api.errors import safe_error, MSG_INTERNAL_ERROR
from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    MemoryMergeRequest,
    MemoryUpdateRequest,
)
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


def _memory_to_dict(m, vs=None) -> dict:
    """Memory → dict 标准化序列化。"""
    return {
        "id": m.id,
        "content": m.content,
        "summary": m.summary,
        "source": m.source,
        "timestamp": m.timestamp.isoformat(),
        "importance": m.importance,
        "entities": m.entities,
        "relations": m.relations if hasattr(m, "relations") else [],
        "memory_type": m.memory_type,
        "access_count": m.access_count,
        "last_accessed": m.last_accessed.isoformat() if m.last_accessed else None,
        "status": getattr(m, "status", "active"),
        "archived_at": m.archived_at.isoformat() if getattr(m, "archived_at", None) else None,
        "embedding_status": "vectorized" if (vs and _check_vectorized(vs, m.id)) else "missing",
    }


def create_router(agent: CognitiveAgent) -> APIRouter:
    router = APIRouter()

    @router.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse:
        try:
            reply = await asyncio.to_thread(agent.run, request.content)
            return ChatResponse(reply=reply)
        except Exception as e:
            logger.exception("chat endpoint error")
            logger.exception("chat_endpoint_error")
            raise HTTPException(status_code=500, detail=MSG_INTERNAL_ERROR)

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
        return [_memory_to_dict(m, vs) for m in memories]

    # ── Memory Search (MUST be before /memory/{memory_id}) ──

    @router.get("/memory/search")
    async def search_memories(
        q: str = "",
        type: str = "",
        status: str = "",
        date_from: str = "",
        date_to: str = "",
        semantic: bool = False,
        limit: int = Query(default=50, ge=1, le=200),
    ):
        """统一记忆搜索。
        支持语义搜索(semantic=true)、关键词搜索、实体匹配，
        按 type/status/日期范围 过滤，结果合并去重。
        """
        store = agent._memory_store
        vs = agent._vector_store
        emb = agent._embedding

        results_by_id: dict[str, dict] = {}

        # 1. 语义搜索
        if semantic and q.strip():
            try:
                from src.core.retrieval import MemoryRetrievalService
                service = MemoryRetrievalService(store, vs, emb)
                memories = service.retrieve(
                    q, top_k=limit * 2, include_archived=(status == "archived"),
                )
                for mem in memories:
                    results_by_id[mem.id] = _memory_to_dict(mem, vs)
            except Exception:
                logger.warning("memory_search_semantic_failed", exc_info=True)

        # 2. 关键词搜索 (SQL LIKE)
        if q.strip() and not semantic:
            try:
                keyword_rows = store._db.execute(
                    """SELECT * FROM notes
                       WHERE (content LIKE ? OR summary LIKE ? OR entities_json LIKE ?)
                       ORDER BY timestamp DESC LIMIT ?""",
                    (f"%{q}%", f"%{q}%", f"%{q}%", limit * 2),
                ).fetchall()
                for row in keyword_rows:
                    mem = store._row_to_memory(dict(row))
                    if mem.id not in results_by_id:
                        results_by_id[mem.id] = _memory_to_dict(mem, vs)
            except Exception:
                logger.warning("memory_search_keyword_failed", exc_info=True)

        # 3. 实体匹配
        if q.strip():
            try:
                entity_mems = store.search_by_entity(q)
                for mem in entity_mems:
                    if mem.id not in results_by_id:
                        results_by_id[mem.id] = _memory_to_dict(mem, vs)
            except Exception:
                logger.warning("memory_search_entity_failed", exc_info=True)

        # 4. 无查询词 → 返回最近记忆
        if not q.strip() and not results_by_id:
            try:
                recent = store.get_recent(limit=limit * 2)
                for mem in recent:
                    results_by_id[mem.id] = _memory_to_dict(mem, vs)
            except Exception:
                logger.warning("memory_search_recent_failed", exc_info=True)

        # 5. 过滤
        results = list(results_by_id.values())

        if type:
            results = [r for r in results if r["memory_type"] == type]
        if status:
            results = [r for r in results if r["status"] == status]
        else:
            # 默认排除 deleted 和 merged
            results = [r for r in results if r["status"] not in ("deleted", "merged")]
        if date_from:
            results = [r for r in results if r["timestamp"] >= date_from]
        if date_to:
            results = [r for r in results if r["timestamp"] <= date_to]

        # 6. 排序：按 timestamp 降序
        results.sort(key=lambda r: r["timestamp"], reverse=True)

        return results[:limit]

    @router.get("/memory/{memory_id}")
    async def get_memory(memory_id: str):
        store = agent._memory_store
        m = store.get_by_id(memory_id)
        if m is None:
            raise HTTPException(status_code=404, detail="记忆不存在")
        vs = agent._vector_store
        return _memory_to_dict(m, vs)

    # ── Memory CRUD ──

    @router.patch("/memory/{memory_id}")
    async def update_memory(memory_id: str, body: MemoryUpdateRequest):
        store = agent._memory_store
        m = store.get_by_id(memory_id)
        if m is None:
            raise HTTPException(status_code=404, detail="记忆不存在")

        if body.content is not None:
            m.content = body.content
        if body.summary is not None:
            m.summary = body.summary
        if body.importance is not None:
            m.importance = body.importance
        if body.entities is not None:
            m.entities = body.entities
        if body.memory_type is not None:
            m.memory_type = body.memory_type

        try:
            store.store(m)
        except Exception:
            raise HTTPException(status_code=500, detail="保存失败")

        vs = agent._vector_store
        return _memory_to_dict(m, vs)

    @router.delete("/memory/{memory_id}")
    async def delete_memory(memory_id: str):
        """软删除 — 设置 status="deleted"，不物理删除。"""
        store = agent._memory_store
        m = store.get_by_id(memory_id)
        if m is None:
            raise HTTPException(status_code=404, detail="记忆不存在")

        try:
            store.update_status(memory_id, "deleted")
        except Exception:
            raise HTTPException(status_code=500, detail="删除失败")

        return {"id": memory_id, "status": "deleted"}

    @router.post("/memory/merge")
    async def merge_memories(body: MemoryMergeRequest):
        """手动合并记忆 — primary 吸收所有 secondary。"""
        store = agent._memory_store
        primary = store.get_by_id(body.primary_id)
        if primary is None:
            raise HTTPException(status_code=404, detail=f"主记忆 {body.primary_id} 不存在")

        merged_ids: list[str] = []
        for sid in body.secondary_ids:
            secondary = store.get_by_id(sid)
            if secondary is None:
                continue
            # 合并到 primary
            primary.content = f"{primary.content}\n[合并自 {sid[:8]}] {secondary.content}"
            primary.entities = list(set(primary.entities + secondary.entities))
            primary.access_count += secondary.access_count
            primary.importance = max(primary.importance, secondary.importance)
            # 标记 secondary 为 merged
            secondary.status = "merged"
            try:
                store.store(secondary)
                merged_ids.append(sid)
            except Exception:
                logger.warning("merge_secondary_failed", extra={"id": sid}, exc_info=True)

        if not merged_ids:
            raise HTTPException(status_code=400, detail="没有可合并的记忆")

        try:
            store.store(primary)
        except Exception:
            raise HTTPException(status_code=500, detail="保存主记忆失败")

        return {
            "primary_id": primary.id,
            "merged_ids": merged_ids,
            "merged_count": len(merged_ids),
        }

    @router.post("/memory/{memory_id}/archive")
    async def archive_memory(memory_id: str):
        """归档单条记忆。"""
        store = agent._memory_store
        m = store.get_by_id(memory_id)
        if m is None:
            raise HTTPException(status_code=404, detail="记忆不存在")

        now = datetime.now(timezone.utc)
        m.status = "archived"
        m.archived_at = now
        try:
            store.store(m)
        except Exception:
            raise HTTPException(status_code=500, detail="归档失败")

        return {
            "id": memory_id,
            "status": "archived",
            "archived_at": now.isoformat(),
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


