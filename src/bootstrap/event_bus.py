"""Event Bus — lightweight in-process event dispatch (non-blocking, fail-safe).

P7: Provides event-driven lifecycle hooks WITHOUT introducing a message queue
framework. Uses a ThreadPoolExecutor for non-blocking dispatch.

Design principles:
- Non-blocking: emit() submits dispatch to a background thread, returns immediately
- Fail-safe: handler exceptions are caught + logged, never crash the caller
- No external dependencies (stdlib only)
- Thread-safe: subscriber registration is guarded by a Lock
"""
from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Standard event types emitted by the orchestrator
EVENT_CONFIG_CHANGED = "config.changed"
EVENT_ADAPTER_REGISTERED = "adapter.registered"
EVENT_RUNTIME_INITIALIZED = "runtime.initialized"
EVENT_READINESS_UPDATED = "readiness.updated"

Handler = Callable[[dict[str, Any]], None]


class EventBus:
    """Lightweight in-process event bus.

    - emit(event_type, payload) is non-blocking (dispatch runs in background thread)
    - subscribe(event_type, handler) is thread-safe
    - Handler failures are caught + logged, never propagated to caller
    """

    def __init__(self, max_workers: int = 2) -> None:
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="event-bus"
        )
        self._shutdown = False

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Register a handler for an event type. Thread-safe."""
        with self._lock:
            self._subscribers[event_type].append(handler)

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """Emit an event. Non-blocking: dispatch runs in background thread.

        If the bus is shut down, the event is dropped (logged at debug level).
        P11: wraps executor.submit() in try/except to handle the race window
        where _shutdown is False at check time but executor is already shut
        down (concurrent shutdown). Prevents RuntimeError propagation.
        """
        if self._shutdown:
            logger.debug("event_bus_shutdown_drop", extra={"event_type": event_type})
            return
        try:
            self._executor.submit(self._dispatch, event_type, payload or {})
        except RuntimeError:
            # Executor shut down between check and submit (race window)
            logger.debug(
                "event_bus_submit_after_shutdown",
                extra={"event_type": event_type},
            )

    def dispatch(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """Synchronous dispatch (for testing or when blocking is acceptable)."""
        self._dispatch(event_type, payload or {})

    def _dispatch(self, event_type: str, payload: dict[str, Any]) -> None:
        """Dispatch event to all subscribers. Fail-safe: catches all exceptions."""
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))
        for handler in handlers:
            try:
                handler(payload)
            except Exception:
                logger.exception(
                    "event_handler_failed",
                    extra={"event_type": event_type, "handler": getattr(handler, "__name__", repr(handler))},
                )

    def shutdown(self) -> None:
        """Shut down the executor. After this, emit() drops events.

        P11: idempotent — safe to call multiple times. Subsequent calls are
        no-ops (avoids RuntimeError on double shutdown).
        """
        if self._shutdown:
            return
        self._shutdown = True
        self._executor.shutdown(wait=False, cancel_futures=True)
        logger.debug("event_bus_shutdown_complete")
