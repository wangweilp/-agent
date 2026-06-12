"""Sync Hub — metadata-only sync center. No real sync. No network.

Step 27: Sync readiness for Memory/Timeline/Usage incremental sync.
No real sync operations. sync_active=False.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


class SyncStatus(StrEnum):
    NOT_STARTED = "not_started"
    CONFIGURED = "configured"
    SYNC_READY = "sync_ready"
    SYNC_ACTIVE = "sync_active"
    DELTA_SYNC_ACTIVE = "delta_sync_active"
    FAIL_CLOSED = "fail_closed"


class SyncEntityType(StrEnum):
    MEMORY = "memory"
    TIMELINE = "timeline"
    USAGE = "usage"
    POLICY = "policy"
    INCIDENT = "incident"
    CAPABILITY = "capability"


class SyncMode(StrEnum):
    FULL = "full"
    INCREMENTAL = "incremental"
    DELTA = "delta"


@dataclass
class SyncEntity:
    entity_id: str = field(default_factory=lambda: f"syncent_{uuid4().hex[:16]}")
    entity_type: str = ""
    sync_mode: str = SyncMode.INCREMENTAL
    last_synced_at: datetime | None = None
    sync_allowed: bool = False
    network_allowed: bool = False
    metadata_only: bool = True
    delta_count: int = 0
    warnings: list[str] = field(default_factory=list)

    def is_sync_allowed(self) -> bool: return False

    def to_dict(self):
        return {
            "entity_id": self.entity_id, "entity_type": self.entity_type,
            "sync_mode": self.sync_mode,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "sync_allowed": self.sync_allowed, "network_allowed": self.network_allowed,
            "metadata_only": self.metadata_only, "delta_count": self.delta_count,
            "warnings": self.warnings,
        }


@dataclass
class SyncHubReport:
    report_id: str = field(default_factory=lambda: f"synrep_{uuid4().hex[:16]}")
    status: str = SyncStatus.NOT_STARTED
    sync_active: bool = False
    sync_allowed: bool = False
    entities_configured: int = 0
    entities: list[dict] = field(default_factory=list)
    last_full_sync: datetime | None = None
    warnings: list[str] = field(default_factory=list)
    execution_allowed: bool = False
    runtime_enabled: bool = False
    metadata_only: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "report_id": self.report_id, "status": self.status,
            "sync_active": self.sync_active, "sync_allowed": self.sync_allowed,
            "entities_configured": self.entities_configured,
            "entities": self.entities,
            "last_full_sync": self.last_full_sync.isoformat() if self.last_full_sync else None,
            "warnings": self.warnings,
            "execution_allowed": self.execution_allowed,
            "runtime_enabled": self.runtime_enabled,
            "metadata_only": self.metadata_only,
            "created_at": self.created_at.isoformat(),
        }


SYNC_ENTITIES = {
    SyncEntityType.MEMORY: SyncEntity(
        entity_type=SyncEntityType.MEMORY, sync_mode=SyncMode.INCREMENTAL,
        sync_allowed=False, warnings=["Memory sync disabled - no real sync"]),
    SyncEntityType.TIMELINE: SyncEntity(
        entity_type=SyncEntityType.TIMELINE, sync_mode=SyncMode.INCREMENTAL,
        sync_allowed=False, warnings=["Timeline sync disabled - no real sync"]),
    SyncEntityType.USAGE: SyncEntity(
        entity_type=SyncEntityType.USAGE, sync_mode=SyncMode.DELTA,
        sync_allowed=False, warnings=["Usage sync disabled - no real sync"]),
    SyncEntityType.POLICY: SyncEntity(
        entity_type=SyncEntityType.POLICY, sync_mode=SyncMode.FULL,
        sync_allowed=False, warnings=["Policy sync disabled - no real sync"]),
    SyncEntityType.INCIDENT: SyncEntity(
        entity_type=SyncEntityType.INCIDENT, sync_mode=SyncMode.FULL,
        sync_allowed=False, warnings=["Incident sync disabled - no real sync"]),
    SyncEntityType.CAPABILITY: SyncEntity(
        entity_type=SyncEntityType.CAPABILITY, sync_mode=SyncMode.FULL,
        sync_allowed=False, warnings=["Capability sync disabled - no real sync"]),
}


class SyncHub:
    """Sync Hub — metadata-only. No real sync operations."""

    def __init__(self):
        self._sync_active = False

    def assess_readiness(self) -> SyncHubReport:
        entities = [e.to_dict() for e in SYNC_ENTITIES.values()]
        return SyncHubReport(
            status=SyncStatus.CONFIGURED,
            sync_active=False, sync_allowed=False,
            entities_configured=len(SYNC_ENTITIES),
            entities=entities,
            warnings=["Sync Hub is metadata-configured only",
                       "No sync operations are active",
                       "All sync_allowed=False",
                       "No network access for sync"],
            execution_allowed=False, runtime_enabled=False, metadata_only=True,
        )

    def get_sync_entities(self) -> dict[str, dict]:
        return {k.value: v.to_dict() for k, v in SYNC_ENTITIES.items()}
