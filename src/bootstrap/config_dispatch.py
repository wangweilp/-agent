"""Config Dispatch Layer — typed container for metadata-only readiness adapters.

P4: Upgraded from plain dict to ConfigDispatch dataclass with register/get API.
Does NOT replace SQLite/thread/memory; only honors config + logs warnings.

The ConfigDispatch serves as a lightweight service registry for readiness-
assessment adapters. SQLiteStoreAdapter (the active store) is NOT registered
here — it has a different interface and remains directly wired in main.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.adapters.config import Settings
from src.bootstrap.contracts import ReadinessAdapter

logger = logging.getLogger(__name__)

# Valid registry slots (prevents arbitrary key registration)
_VALID_SLOTS = frozenset({"database_backend", "cache_backend", "queue_backend"})


@dataclass
class ConfigDispatch:
    """Typed registry for metadata-only readiness adapters.

    NOT a service locator for the active store. SQLite remains the active
    database; these adapters only provide readiness assessment for operators.
    """

    database_backend: ReadinessAdapter | None = None
    cache_backend: ReadinessAdapter | None = None
    queue_backend: ReadinessAdapter | None = None

    def register(self, slot: str, adapter: ReadinessAdapter) -> None:
        """Register a readiness adapter in a named slot.

        Args:
            slot: One of "database_backend", "cache_backend", "queue_backend"
            adapter: ReadinessAdapter instance (must implement assess_readiness)
        """
        if slot not in _VALID_SLOTS:
            raise ValueError(f"Invalid dispatch slot: {slot!r}. Valid: {_VALID_SLOTS}")
        setattr(self, slot, adapter)

    def get(self, slot: str) -> ReadinessAdapter | None:
        """Retrieve a registered adapter by slot name. Returns None if not set."""
        if slot not in _VALID_SLOTS:
            raise ValueError(f"Invalid dispatch slot: {slot!r}. Valid: {_VALID_SLOTS}")
        return getattr(self, slot)

    def is_empty(self) -> bool:
        """True if no adapters are registered (default config state)."""
        return all(getattr(self, s) is None for s in _VALID_SLOTS)

    def get_readiness_summary(self) -> dict[str, dict[str, Any]]:
        """Build readiness summary dict for /health/config endpoint.

        Consolidates the report-extraction logic that was previously inline
        in the health route handler.

        P11: fail-safe — if adapter.assess_readiness() raises, the slot is
        reported as degraded with the error reason instead of propagating
        the exception (prevents /health/* from returning 500).
        """
        result: dict[str, dict[str, Any]] = {}
        for slot in _VALID_SLOTS:
            adapter = getattr(self, slot)
            if adapter is None:
                result[slot] = {"instantiated": False}
            else:
                try:
                    report = adapter.assess_readiness()
                    result[slot] = {
                        "instantiated": True,
                        "metadata_only": getattr(report, "metadata_only", True),
                        "connection_active": getattr(report, "connection_active", False),
                        "execution_allowed": getattr(report, "execution_allowed", False),
                        "status": str(getattr(report, "status", "unknown")),
                    }
                except Exception as exc:
                    logger.exception(
                        "adapter_assess_readiness_failed",
                        extra={"slot": slot, "adapter_type": type(adapter).__name__},
                    )
                    result[slot] = {
                        "instantiated": True,
                        "metadata_only": False,
                        "connection_active": False,
                        "execution_allowed": False,
                        "status": "error",
                        "error": str(exc),
                    }
        return result


# Module-level singleton registry (populated by RuntimeOrchestrator).
# P8: Adapter instantiation moved to orchestrator (runtime layer) to fix
# dependency direction — config layer must not import runtime adapters.
config_dispatch = ConfigDispatch()
