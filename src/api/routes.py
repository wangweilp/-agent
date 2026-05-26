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
import time
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
        try:
            reply = await asyncio.to_thread(agent.run, request.content)
            return StreamingResponse(
                _stream_response(reply),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        except Exception as e:
            logger.exception("chat stream error")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/health")
    async def health():
        return {"status": "ok"}

    return router


async def _stream_response(text: str) -> AsyncGenerator[str, None]:
    """SSE 流式返回，统一事件类型。"""
    for i in range(0, len(text), 10):
        chunk = text[i:i + 10]
        yield f"event: token\ndata: {json.dumps({'text': chunk})}\n\n"
        await asyncio.sleep(0.02)
    yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"
