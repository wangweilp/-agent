"""Rate limiter — per-IP sliding-window request throttle.

Plugs in as ASGI middleware (Starlette-compatible). In-memory only (single-process);
for multi-replica deployments use Redis-based rate limiting behind a reverse proxy.

Usage in main.py::

    app.add_middleware(RateLimitMiddleware, max_requests=30, window_seconds=60.0)
"""

from __future__ import annotations

import json as _json
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)

_UPLOAD_PREFIXES: tuple[str, ...] = (
    "/upload", "/audio/upload", "/video/upload",
    "/imports", "/sync/connectors", "/sync/jobs",
)


class RateLimitMiddleware:
    """Per-IP sliding-window rate limiter (Starlette ASGI middleware).

    Only enforces limits on upload/mutating endpoints listed in ``_UPLOAD_PREFIXES``.
    All other paths pass through without counting.
    """

    def __init__(
        self,
        app,
        max_requests: int = 30,
        window_seconds: float = 60.0,
        enabled: bool = True,
    ) -> None:
        self._app = app
        self._max = max_requests
        self._window = window_seconds
        self._enabled = enabled
        # { ip: [monotonic_timestamp, ...] }
        self._hits: dict[str, list[float]] = defaultdict(list)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        if not self._enabled:
            await self._app(scope, receive, send)
            return

        path: str = scope.get("path", "/")
        if not path.startswith(_UPLOAD_PREFIXES):
            await self._app(scope, receive, send)
            return

        # Resolve client IP
        headers: dict[bytes, bytes] = dict(scope.get("headers", []))
        forwarded = headers.get(b"x-forwarded-for", b"").decode("latin-1")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            raw = scope.get("client")
            ip = raw[0] if raw else "127.0.0.1"

        now = time.monotonic()
        cutoff = now - self._window

        timestamps = self._hits[ip]
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

        if len(timestamps) >= self._max:
            retry_after = int(timestamps[0] + self._window - now + 1)
            body = _json.dumps({
                "detail": "请求过于频繁，请稍后重试",
                "retry_after_seconds": max(retry_after, 1),
            }).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"retry-after", str(max(retry_after, 1)).encode("ascii")),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            logger.warning(
                "rate_limit_hit",
                extra={"ip": ip, "path": path, "window_count": len(timestamps)},
            )
            return

        timestamps.append(now)
        await self._app(scope, receive, send)

    def stats(self) -> dict:
        """Return current limiter stats for monitoring."""
        now = time.monotonic()
        cutoff = now - self._window
        active_ips = 0
        blocked_ips = 0
        for ts in self._hits.values():
            while ts and ts[0] < cutoff:
                ts.pop(0)
            if ts:
                active_ips += 1
                if len(ts) >= self._max:
                    blocked_ips += 1
        return {
            "active_ips": active_ips,
            "blocked_ips": blocked_ips,
            "window_seconds": self._window,
            "max_requests_per_window": self._max,
        }
