"""FastAPI 路由 — /chat 端点与 SSE 流式返回。"""
import asyncio
import logging
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
            )
        except Exception as e:
            logger.exception("chat stream error")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/health")
    async def health():
        return {"status": "ok"}

    return router


async def _stream_response(text: str) -> AsyncGenerator[str, None]:
    for i in range(0, len(text), 10):
        chunk = text[i:i + 10]
        yield f"data: {chunk}\n\n"
        await asyncio.sleep(0.02)
    yield "data: [DONE]\n\n"
