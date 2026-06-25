"""Runtime Orchestrator — aggregates adapter lifecycle + system readiness.

P5: Lightweight orchestration layer over ConfigDispatch. Does NOT replace
SQLite/thread/memory; only provides unified readiness aggregation and
ordered initialization for the metadata-only readiness adapters.

P7: Integrated EventBus for non-blocking lifecycle hooks. Events are emitted
at key points (initialize_all, register_adapter, readiness change) without
changing existing logic.

Design principles:
- Delegates to ConfigDispatch (does not duplicate registry state)
- No new framework, no complex dependency graph
- Linear initialization order (database → cache → queue)
- SystemReadinessReport classifies overall system state
- Event hooks are optional + fail-safe (never block or crash main flow)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable

from src.adapters.config import Settings
from src.adapters.postgres_adapter import PostgresAdapter
from src.adapters.redis_cache import RedisCacheAdapter
from src.adapters.task_queue_adapter import TaskQueueAdapter
from src.bootstrap.config_dispatch import ConfigDispatch
from src.bootstrap.event_bus import (
    EVENT_ADAPTER_REGISTERED,
    EVENT_READINESS_UPDATED,
    EVENT_RUNTIME_INITIALIZED,
    EventBus,
)

logger = logging.getLogger(__name__)


class OverallStatus(StrEnum):
    """Aggregated system readiness classification."""

    HEALTHY = "healthy"          # all components OK (connection_active)
    SIMULATION = "simulation"    # all metadata-only, no real connections
    DEGRADED = "degraded"        # at least one component failed or partial
    UNKNOWN = "unknown"          # no adapters registered (default config)


@dataclass
class SystemReadinessReport:
    """Aggregated readiness report across all registered adapters.

    Classification rules:
    - HEALTHY: all registered adapters have connection_active=True
    - SIMULATION: all registered adapters are metadata_only=True
    - DEGRADED: at least one adapter has execution_allowed=False but not metadata_only
    - UNKNOWN: no adapters registered (default SQLite/memory/inline config)
    """

    database_status: dict[str, Any] = field(default_factory=dict)
    cache_status: dict[str, Any] = field(default_factory=dict)
    queue_status: dict[str, Any] = field(default_factory=dict)
    overall_status: str = OverallStatus.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_status": self.database_status,
            "cache_status": self.cache_status,
            "queue_status": self.queue_status,
            "overall_status": self.overall_status,
        }


class RuntimeOrchestrator:
    """Lightweight runtime orchestrator for readiness-adapter lifecycle.

    Wraps ConfigDispatch to provide:
    - Ordered initialization (initialize_all)
    - Per-adapter status query (get_adapter_status)
    - Aggregated system readiness (get_system_readiness)

    Does NOT manage SQLiteStoreAdapter or worker threads — those remain
    directly wired in main.py with their existing lifecycle.
    """

    def __init__(self, settings: Settings, dispatch: ConfigDispatch | None = None):
        self._settings = settings
        self._dispatch = dispatch if dispatch is not None else ConfigDispatch()
        self._initialized = False
        # P7: EventBus for non-blocking lifecycle hooks
        self._event_bus = EventBus()
        self._last_readiness_status: str | None = None

    @property
    def dispatch(self) -> ConfigDispatch:
        """Access the underlying ConfigDispatch registry."""
        return self._dispatch

    @property
    def event_bus(self) -> EventBus:
        """Access the EventBus for subscribing lifecycle hooks."""
        return self._event_bus

    def register_adapter(self, name: str, adapter: Any) -> None:
        """Register a readiness adapter by slot name.

        Delegates to ConfigDispatch.register() which validates the slot name.
        Emits adapter.registered event (non-blocking).
        """
        self._dispatch.register(name, adapter)
        # P7: emit event (non-blocking, fail-safe)
        self._event_bus.emit(
            EVENT_ADAPTER_REGISTERED,
            {"slot": name, "adapter_type": type(adapter).__name__},
        )

    def initialize_all(self) -> ConfigDispatch:
        """Run config dispatch initialization in linear order.

        Order: database → cache → queue (deterministic).
        Idempotent: safe to call multiple times (subsequent calls are no-ops).
        Emits runtime.initialized event on first initialization (non-blocking).

        P11: if _initialize_adapters() raises, _initialized stays False so the
        caller can retry. Logs the failure with the adapter slot that failed.
        """
        if self._initialized:
            logger.debug("orchestrator_already_initialized")
            return self._dispatch
        # P8: instantiate adapters in runtime layer (correct dependency direction).
        # Previously this lived in config_dispatch.py (config layer importing
        # runtime adapters) — moved here to enforce single-direction dependency.
        try:
            self._initialize_adapters()
        except Exception:
            logger.exception(
                "orchestrator_init_adapters_failed",
                extra={"event": "orchestrator_init_adapters_failed"},
            )
            raise  # re-raise: _initialized stays False, caller can retry
        self._initialized = True
        overall = self._compute_overall_status()
        logger.info(
            "orchestrator_initialized",
            extra={"event": "orchestrator_initialized", "overall": overall},
        )
        # P7: emit runtime.initialized + readiness.updated (non-blocking)
        self._event_bus.emit(
            EVENT_RUNTIME_INITIALIZED,
            {"overall_status": overall},
        )
        self._emit_readiness_if_changed(overall)
        return self._dispatch

    # ── P7: Lifecycle hooks (optional, non-blocking, fail-safe) ──

    def on_start(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Hook for runtime.initialized. Non-blocking; never blocks init flow."""
        self._event_bus.subscribe(EVENT_RUNTIME_INITIALIZED, handler)

    def on_adapter_ready(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Hook for adapter.registered. Non-blocking; never blocks register flow."""
        self._event_bus.subscribe(EVENT_ADAPTER_REGISTERED, handler)

    def on_system_degraded(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Hook invoked when overall status transitions to DEGRADED."""
        def _wrapper(payload: dict[str, Any]) -> None:
            if payload.get("overall_status") == OverallStatus.DEGRADED:
                handler(payload)
        self._event_bus.subscribe(EVENT_READINESS_UPDATED, _wrapper)

    def on_system_healthy(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Hook invoked when overall status transitions to HEALTHY."""
        def _wrapper(payload: dict[str, Any]) -> None:
            if payload.get("overall_status") == OverallStatus.HEALTHY:
                handler(payload)
        self._event_bus.subscribe(EVENT_READINESS_UPDATED, _wrapper)

    def _emit_readiness_if_changed(self, current_status: str) -> None:
        """Emit readiness.updated only when overall status changes. Non-blocking."""
        previous = self._last_readiness_status
        if current_status != previous:
            self._last_readiness_status = current_status
            self._event_bus.emit(
                EVENT_READINESS_UPDATED,
                {"overall_status": current_status, "previous_status": previous},
            )

    def _initialize_adapters(self) -> None:
        """Instantiate metadata-only adapters based on config (runtime layer).

        P8: Moved from config_dispatch.initialize_config_dispatch() to fix
        dependency direction — config layer must not import runtime adapters.
        Behavior is identical: registers adapters on the config_dispatch singleton.
        Does NOT replace SQLite; adapters are readiness-assessment stubs only.
        """
        settings = self._settings
        if settings.database_backend == "postgres":
            self._dispatch.register("database_backend", PostgresAdapter(settings))
            logger.warning(
                "database_backend=postgres: PostgresAdapter instantiated as metadata-only. "
                "SQLite remains the active store. No real PG connection.",
                extra={"event": "config_dispatch_database_postgres_metadata_only"},
            )
        if settings.cache_backend == "redis":
            self._dispatch.register("cache_backend", RedisCacheAdapter(settings))
            logger.warning(
                "cache_backend=redis: RedisCacheAdapter instantiated as metadata-only. "
                "In-memory cache remains active. No real Redis connection.",
                extra={"event": "config_dispatch_cache_redis_metadata_only"},
            )
        if settings.queue_backend in ("redis", "celery", "rq"):
            self._dispatch.register("queue_backend", TaskQueueAdapter(settings))
            logger.warning(
                "queue_backend=%s: TaskQueueAdapter instantiated as metadata-only. "
                "Inline thread workers remain active. No real queue enqueue/dispatch.",
                settings.queue_backend,
                extra={"event": "config_dispatch_queue_metadata_only"},
            )

    def get_adapter_status(self, name: str) -> dict[str, Any]:
        """Query a single adapter's readiness status by slot name.

        Returns {"instantiated": False} if not registered.
        P9: delegates to ConfigDispatch.get_readiness_summary() (single source
        of truth). get() call preserves ValueError on invalid slot names.
        """
        self._dispatch.get(name)  # validates slot name (raises ValueError if invalid)
        return self._dispatch.get_readiness_summary().get(name, {"instantiated": False})

    def get_system_readiness(self) -> SystemReadinessReport:
        """Aggregate readiness across all registered adapters.

        Returns SystemReadinessReport with per-component status + overall classification.
        P10: fetches summary once and passes it to _compute_overall_status() to
        eliminate redundant get_readiness_summary() call (was called twice).
        """
        summary = self._dispatch.get_readiness_summary()
        return SystemReadinessReport(
            database_status=summary.get("database_backend", {"instantiated": False}),
            cache_status=summary.get("cache_backend", {"instantiated": False}),
            queue_status=summary.get("queue_backend", {"instantiated": False}),
            overall_status=self._compute_overall_status(summary),
        )

    def _compute_overall_status(self, summary: dict[str, Any] | None = None) -> str:
        """Classify overall system state based on registered adapters.

        - UNKNOWN: no adapters registered (default config)
        - SIMULATION: all registered adapters are metadata_only
        - HEALTHY: all registered adapters have connection_active=True
        - DEGRADED: mixed state or partial failure

        P10: accepts optional summary to avoid redundant get_readiness_summary()
        call when caller already has the summary.
        """
        if summary is None:
            summary = self._dispatch.get_readiness_summary()
        registered = [v for v in summary.values() if v.get("instantiated")]
        if not registered:
            return OverallStatus.UNKNOWN
        all_metadata_only = all(v.get("metadata_only", True) for v in registered)
        all_connected = all(v.get("connection_active", False) for v in registered)
        if all_connected:
            return OverallStatus.HEALTHY
        if all_metadata_only:
            return OverallStatus.SIMULATION
        return OverallStatus.DEGRADED
