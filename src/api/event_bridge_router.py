"""Event Bridge Router — SSE endpoint for streaming backend events to frontend.

L2 Replay Engine: exposes /events/stream SSE endpoint that streams
structured SystemEvent dicts from the backend EventBus to the frontend
CausalKernel via Server-Sent Events.

Constraints:
- Additive only: new router, does NOT modify existing routes.
- Fail-safe: SSE connection errors never crash the system.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.bootstrap.event_bridge import get_event_emitter

logger = logging.getLogger(__name__)


def create_event_bridge_router() -> APIRouter:
    """Create the Event Bridge SSE router."""
    router = APIRouter(prefix="/events", tags=["Event Bridge"])

    @router.get("/stream")
    async def event_stream(request: Request):
        """SSE endpoint — streams structured backend events to frontend.

        Frontend connects via EventSource('/events/stream').
        Each event is a structured SystemEvent with origin="backend".
        """
        emitter = get_event_emitter()
        if emitter is None:
            async def _not_ready():
                yield 'data: {"error": "event_emitter_not_ready"}\n\n'
            return StreamingResponse(_not_ready(), media_type="text/event-stream")

        # Attach to current event loop for thread-safe queue notification
        loop = asyncio.get_event_loop()
        emitter.attach_to_loop(loop)

        queue = emitter.subscribe_sse()

        async def event_generator():
            try:
                # Send recent buffered events first (late subscriber catch-up)
                recent = emitter.get_recent_events(limit=50)
                for event in recent:
                    if await request.is_disconnected():
                        return
                    yield f"data: {json.dumps(event)}\n\n"

                # Stream live events
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                        yield f"data: {json.dumps(event)}\n\n"
                    except asyncio.TimeoutError:
                        # Send keepalive comment
                        yield ": keepalive\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                emitter.unsubscribe_sse(queue)
                logger.debug("sse_client_disconnected")

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/recent")
    async def recent_events(limit: int = 100):
        """Get recent buffered events (REST endpoint, non-streaming)."""
        emitter = get_event_emitter()
        if emitter is None:
            return {"events": [], "error": "event_emitter_not_ready"}
        return {"events": emitter.get_recent_events(limit)}

    return router
