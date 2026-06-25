"""Event Bridge — backend structured event emitter + SSE stream.

L2 Replay Engine: bridges Python EventBus events to the frontend CausalKernel
via Server-Sent Events (SSE). Emits structured events compatible with the
frontend SystemEvent schema.

Design:
- StructuredEventEmitter wraps EventBus, subscribes to lifecycle events
  and re-emits them as structured SystemEvent dicts (with trace_id, causal).
- SSE endpoint streams these structured events to frontend.
- Frontend EventBridge client ingests them into CausalKernel with origin="backend".

Constraints:
- Does NOT modify existing EventBus or route definitions.
- Additive only: new module + new router.
- Fail-safe: bridge failures never crash the main system.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from threading import Lock, Thread
from typing import Any, Callable

from src.bootstrap.event_bus import (
    EVENT_ADAPTER_REGISTERED,
    EVENT_CONFIG_CHANGED,
    EVENT_READINESS_UPDATED,
    EVENT_RUNTIME_INITIALIZED,
    EventBus,
)

logger = logging.getLogger(__name__)

# ── Backend event type → frontend SystemEvent mapping ──

_BACKEND_EVENT_MAP: dict[str, dict[str, Any]] = {
    EVENT_RUNTIME_INITIALIZED: {
        "source": "governance",
        "type": "governance.policy.evaluated",
        "severity": "info",
        "cause_type": "system_event",
    },
    EVENT_ADAPTER_REGISTERED: {
        "source": "runtime",
        "type": "runtime.sandbox.terminated",
        "severity": "info",
        "cause_type": "system_event",
    },
    EVENT_CONFIG_CHANGED: {
        "source": "governance",
        "type": "governance.policy.evaluated",
        "severity": "warn",
        "cause_type": "system_policy",
    },
    EVENT_READINESS_UPDATED: {
        "source": "observability",
        "type": "observability.metric.recorded",
        "severity": "info",
        "cause_type": "system_event",
    },
}


class StructuredEventEmitter:
    """Wraps EventBus, emits structured SystemEvent dicts for SSE streaming.

    - Subscribes to backend EventBus lifecycle events.
    - Transforms them into frontend-compatible SystemEvent dicts.
    - Buffers recent events in a ring buffer for late SSE subscribers.
    - Notifies SSE subscribers via asyncio queue (thread-safe bridge).
    """

    def __init__(self, event_bus: EventBus, buffer_size: int = 1000) -> None:
        self._event_bus = event_bus
        self._buffer: deque[dict[str, Any]] = deque(maxlen=buffer_size)
        self._lock = Lock()
        self._sse_subscribers: list[asyncio.Queue] = []
        self._subscribed = False
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_to_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Attach the asyncio loop for thread-safe queue notification."""
        self._loop = loop

    def start(self) -> None:
        """Subscribe to backend EventBus lifecycle events."""
        if self._subscribed:
            return
        for event_type in _BACKEND_EVENT_MAP:
            self._event_bus.subscribe(event_type, self._make_handler(event_type))
        self._subscribed = True
        logger.info("structured_event_emitter_started")

    def _make_handler(self, event_type: str) -> Callable[[dict[str, Any]], None]:
        """Create a handler that transforms backend events to structured SystemEvent."""

        def handler(payload: dict[str, Any]) -> None:
            structured = self._transform(event_type, payload)
            self._emit_structured(structured)

        return handler

    def _transform(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Transform backend EventBus event → frontend SystemEvent dict."""
        mapping = _BACKEND_EVENT_MAP.get(event_type, {
            "source": "observability",
            "type": "observability.metric.recorded",
            "severity": "info",
            "cause_type": "system_event",
        })

        trace_id = payload.get("trace_id", f"backend_{int(time.time() * 1000)}")
        parent_event_id = payload.get("parent_event_id")

        return {
            "event_id": str(uuid.uuid4()),
            "timestamp": _iso_now(),
            "source": mapping["source"],
            "type": mapping["type"],
            "severity": mapping["severity"],
            "trace_id": trace_id,
            "payload": self._build_payload(mapping["type"], event_type, payload),
            "causal": {
                "parent_event_id": parent_event_id,
                "cause_type": mapping["cause_type"],
                "cause_metadata": {"backend_event_type": event_type},
            },
            "origin": "backend",
        }

    def _build_payload(self, frontend_type: str, backend_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Build structured payload matching frontend EventPayload union."""
        overall = payload.get("overall_status", "unknown")
        slot = payload.get("slot", "system")
        adapter_type = payload.get("adapter_type", "unknown")

        if frontend_type == "governance.policy.evaluated":
            return {
                "policy_id": f"backend-{backend_type}",
                "policy_name": backend_type,
                "decision": "allowed" if overall != "degraded" else "denied",
                "evaluated_rules": [backend_type],
                "violations": [] if overall != "degraded" else [f"{overall}_status"],
                "warnings": [],
            }
        if frontend_type == "runtime.sandbox.terminated":
            return {
                "handle_id": slot,
                "reason": f"adapter_registered:{adapter_type}",
                "cleanup_actions": [],
            }
        if frontend_type == "observability.metric.recorded":
            return {
                "metric_name": backend_type,
                "value": 1,
                "unit": "event",
                "tags": {"overall_status": overall, "slot": slot},
            }
        return {"metric_name": backend_type, "value": 1, "unit": "event", "tags": payload}

    def _emit_structured(self, event: dict[str, Any]) -> None:
        """Buffer event + notify SSE subscribers (thread-safe)."""
        with self._lock:
            self._buffer.append(event)
            subscribers = list(self._sse_subscribers)

        for queue in subscribers:
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(queue.put(event), self._loop)
            else:
                logger.debug("sse_no_loop_attached_dropping_event")

    def get_recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent buffered events (for late SSE subscribers)."""
        with self._lock:
            buf_list = list(self._buffer)
        return buf_list[-limit:]

    def subscribe_sse(self) -> asyncio.Queue:
        """Subscribe to SSE stream. Returns a queue that receives structured events."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        with self._lock:
            self._sse_subscribers.append(queue)
        return queue

    def unsubscribe_sse(self, queue: asyncio.Queue) -> None:
        """Unsubscribe from SSE stream."""
        with self._lock:
            if queue in self._sse_subscribers:
                self._sse_subscribers.remove(queue)


def _iso_now() -> str:
    """ISO 8601 timestamp with timezone."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ── Module-level singleton (initialized by main.py) ──

_emitter: StructuredEventEmitter | None = None


def init_event_emitter(event_bus: EventBus) -> StructuredEventEmitter:
    """Initialize the structured event emitter singleton."""
    global _emitter
    if _emitter is None:
        _emitter = StructuredEventEmitter(event_bus)
        _emitter.start()
        logger.info("event_emitter_initialized")
    return _emitter


def get_event_emitter() -> StructuredEventEmitter | None:
    """Get the structured event emitter singleton (None if not initialized)."""
    return _emitter
