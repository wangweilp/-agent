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
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from src.api.schemas import ChatRequest, ChatResponse
from src.core.agent import CognitiveAgent

logger = logging.getLogger(__name__)


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

    return router


