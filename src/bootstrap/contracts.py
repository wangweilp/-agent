"""Service Contracts — lightweight Protocol definitions for readiness adapters.

P4: Documents the EXISTING interface shared by PostgresAdapter, RedisCacheAdapter,
and TaskQueueAdapter. All three implement assess_readiness() → Report.

IMPORTANT: These contracts describe readiness-assessment adapters ONLY.
SQLiteStoreAdapter (the active store) has a DIFFERENT interface (store/delete/
update_status) and is NOT covered by these contracts. The two are not
interchangeable — SQLite is the runtime store; the others are metadata stubs.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ReadinessReport(Protocol):
    """Contract for readiness assessment reports returned by assess_readiness()."""

    metadata_only: bool
    connection_active: bool
    execution_allowed: bool
    status: str

    def to_dict(self) -> dict[str, Any]: ...


@runtime_checkable
class ReadinessAdapter(Protocol):
    """Contract for metadata-only readiness-assessment adapters.

    Implementations: PostgresAdapter, RedisCacheAdapter, TaskQueueAdapter.
    Does NOT include SQLiteStoreAdapter (different interface, active store).
    """

    def assess_readiness(self) -> ReadinessReport: ...
