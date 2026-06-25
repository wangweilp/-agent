"""System Entry Points — unified facade for system lifecycle.

P8: Consolidates scattered entry points into a single API surface.
P10: Inlined UnifiedSystemState (was a thin proxy layer). The 3 methods
get_config_state/get_runtime_state/get_unified_state now live directly
on SystemRuntime, eliminating one module + one proxy hop.

Entry points:
- initialize_system()  → unified init (orchestrator + adapters + events)
- get_system_status()   → unified status (config + runtime merged)
- shutdown_system()     → unified shutdown (event bus + future hooks)
"""
from __future__ import annotations

import logging
from typing import Any

from src.adapters.config import Settings
from src.bootstrap.config_dispatch import ConfigDispatch, config_dispatch
from src.bootstrap.orchestrator import RuntimeOrchestrator

logger = logging.getLogger(__name__)


class SystemRuntime:
    """Unified system entry point facade.

    P10: Inlined UnifiedSystemState — config/runtime/unified state methods
    live directly here. No separate observability proxy module needed.

    Boundary contract:
    - CONFIG LAYER:    Settings (read-only config expression)
    - RUNTIME LAYER:   RuntimeOrchestrator (adapter lifecycle + readiness)
    - CONTRACT LAYER:  ReadinessAdapter/ReadinessReport Protocol (validation)
    - OBSERVABILITY:   get_unified_state() on this facade (read-only projection)
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._orchestrator = RuntimeOrchestrator(settings, config_dispatch)
        self._initialized = False

    @property
    def orchestrator(self) -> RuntimeOrchestrator:
        """Access the underlying RuntimeOrchestrator (escape hatch)."""
        return self._orchestrator

    @property
    def dispatch(self) -> ConfigDispatch:
        """Access the config dispatch registry."""
        return self._orchestrator.dispatch

    @property
    def event_bus(self):
        """Access the EventBus for lifecycle hook subscription."""
        return self._orchestrator.event_bus

    def initialize_system(self) -> ConfigDispatch:
        """Unified initialization entry point.

        Idempotent: safe to call multiple times (subsequent calls are no-ops).
        Delegates to RuntimeOrchestrator.initialize_all() which:
        - instantiates metadata-only adapters based on config
        - emits runtime.initialized + readiness.updated events (non-blocking)
        """
        if self._initialized:
            logger.debug("system_runtime_already_initialized")
            return self._orchestrator.dispatch
        dispatch = self._orchestrator.initialize_all()
        self._initialized = True
        logger.info(
            "system_runtime_initialized",
            extra={"event": "system_runtime_initialized"},
        )
        return dispatch

    # ── P10: Inlined from UnifiedSystemState (eliminated proxy layer) ──

    def get_config_state(self) -> dict[str, Any]:
        """What was REQUESTED via config (env vars / Settings)."""
        return {
            "database_backend": self._settings.database_backend,
            "cache_backend": self._settings.cache_backend,
            "queue_backend": self._settings.queue_backend,
            "active_store": "sqlite",  # SQLite always remains the active store
        }

    def get_runtime_state(self) -> dict[str, Any]:
        """What ACTUALLY happened at runtime (authoritative)."""
        report = self._orchestrator.get_system_readiness()
        return report.to_dict()

    def get_unified_state(self) -> dict[str, Any]:
        """Single consistent view merging config + runtime.

        Runtime is authoritative: if config requests "postgres" but runtime
        shows no adapter registered, the unified view reports runtime reality.
        """
        config_state = self.get_config_state()
        runtime_state = self.get_runtime_state()
        return {
            "config": config_state,
            "runtime": runtime_state,
            "unified_status": runtime_state["overall_status"],
        }

    def get_system_status(self) -> dict[str, Any]:
        """Unified status query entry point (alias for get_unified_state)."""
        return self.get_unified_state()

    def get_runtime_readiness(self) -> dict[str, Any]:
        """Runtime-only readiness (without config projection)."""
        return self._orchestrator.get_system_readiness().to_dict()

    def shutdown_system(self) -> None:
        """Unified shutdown entry point.

        Currently shuts down the EventBus executor (non-blocking).
        Future shutdown hooks (adapter cleanup, etc.) should be added here.
        """
        self._orchestrator.event_bus.shutdown()
        logger.info(
            "system_runtime_shutdown_complete",
            extra={"event": "system_runtime_shutdown_complete"},
        )


# Module-level singleton (initialized by main.py via init_system_runtime)
_system_runtime: SystemRuntime | None = None


def init_system_runtime(settings: Settings) -> SystemRuntime:
    """Initialize the singleton SystemRuntime instance.

    Called once at application startup. Subsequent calls return the existing
    instance without re-initialization.
    """
    global _system_runtime
    if _system_runtime is None:
        _system_runtime = SystemRuntime(settings)
    return _system_runtime


def get_system_runtime() -> SystemRuntime:
    """Access the singleton SystemRuntime instance.

    Raises RuntimeError if not initialized — call init_system_runtime() first.
    """
    if _system_runtime is None:
        raise RuntimeError(
            "SystemRuntime not initialized. Call init_system_runtime(settings) first."
        )
    return _system_runtime
