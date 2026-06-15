"""Step 23 — OpenTelemetry Tracing Infrastructure.

Provides span creation, context propagation, and trace export.
Default: disabled (OTEL_ENABLED=false).

Covers:
- OIDC Flow tracing
- SAML Flow tracing
- Identity Mapping tracing
- Runtime Governance tracing
- Sandbox Execution tracing
- Audit Pipeline tracing
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class TraceSpan:
    """A single trace span in a distributed trace."""

    def __init__(self, name: str, trace_id: str = "", parent_id: str = "",
                 service: str = "sandbox-v2", attributes: dict[str, Any] | None = None):
        import uuid
        self.name = name
        self.span_id = uuid.uuid4().hex[:16]
        self.trace_id = trace_id or uuid.uuid4().hex[:32]
        self.parent_id = parent_id
        self.service = service
        self.start_time = time.time()
        self.end_time: float | None = None
        self.status: str = "unset"  # unset | ok | error
        self.attributes: dict[str, Any] = dict(attributes or {})
        self.events: list[dict[str, Any]] = []

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = str(value)[:500]

    def add_event(self, name: str, attrs: dict[str, Any] | None = None) -> None:
        self.events.append({"name": name, "timestamp": time.time(), "attributes": attrs or {}})

    def set_status(self, status: str) -> None:
        self.status = status

    def finish(self) -> None:
        self.end_time = time.time()

    @property
    def duration_seconds(self) -> float:
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "span_id": self.span_id, "trace_id": self.trace_id,
            "parent_id": self.parent_id, "service": self.service,
            "start_time": self.start_time, "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "status": self.status, "attributes": self.attributes,
            "events": self.events,
        }


class Tracer:
    """Thread-local tracer for creating spans within a trace context."""

    def __init__(self, service: str = "sandbox-v2", enabled: bool = False):
        self.service = service
        self.enabled = enabled
        self._spans: list[TraceSpan] = []
        self._span_stack: list[TraceSpan] = []  # active span stack
        self._lock = threading.Lock()

    def start_span(self, name: str, attributes: dict[str, Any] | None = None,
                   parent_id: str = "") -> TraceSpan:
        if not self.enabled:
            return TraceSpan(name, service=self.service, attributes=attributes)

        trace_id = ""
        p_id = parent_id
        with self._lock:
            if self._span_stack:
                active = self._span_stack[-1]
                trace_id = active.trace_id
                p_id = p_id or active.span_id

        span = TraceSpan(name, trace_id=trace_id, parent_id=p_id,
                         service=self.service, attributes=attributes)
        if self.enabled:
            with self._lock:
                self._span_stack.append(span)
        return span

    def end_span(self, span: TraceSpan, status: str = "ok") -> None:
        if span.end_time is not None:
            return  # Already finished, skip duplicate
        span.set_status(status)
        span.finish()
        if self.enabled:
            with self._lock:
                if self._span_stack and self._span_stack[-1].span_id == span.span_id:
                    self._span_stack.pop()
                self._spans.append(span)

    def span_context(self, name: str, attributes: dict[str, Any] | None = None):
        """Context manager for automatic span lifecycle."""
        return _SpanContext(self, name, attributes)

    def list_spans(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self._spans]

    def span_count(self) -> int:
        return len(self._spans)

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()
            self._span_stack.clear()

    def get_readiness(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "ready": self.enabled,
            "status": "ready" if self.enabled else "disabled",
            "reason": "" if self.enabled else "OTEL_ENABLED=false",
            "spans_recorded": len(self._spans),
            "active_spans": len(self._span_stack),
        }


class _SpanContext:
    def __init__(self, tracer: Tracer, name: str, attributes: dict[str, Any] | None = None):
        self.tracer = tracer
        self.name = name
        self.attributes = attributes
        self.span: TraceSpan | None = None

    def __enter__(self) -> TraceSpan:
        self.span = self.tracer.start_span(self.name, self.attributes)
        return self.span

    def __exit__(self, *args) -> None:
        if self.span:
            status = "error" if args[0] else "ok"
            self.tracer.end_span(self.span, status)


# ── Global Tracer ──

_tracer: Tracer | None = None
_tracer_lock = threading.Lock()


def get_tracer(settings: Any = None) -> Tracer:
    global _tracer
    if _tracer is None:
        with _tracer_lock:
            if _tracer is None:
                otel_enabled = bool(getattr(settings, 'otel_enabled', False)) if settings else False
                _tracer = Tracer(enabled=otel_enabled)
    return _tracer


def reset_tracer() -> None:
    global _tracer
    _tracer = None
