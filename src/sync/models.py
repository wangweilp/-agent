"""Sync data models — SyncJob, SyncRule, SyncExecution, ChangeRecord, SyncConnectorConfig.

Follows the dataclass pattern from src/core/types.py and src/core/import_worker.py.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SyncConnectorConfig:
    """Persisted connector credentials + tracking state.

    Tracks per-resource change markers (hash, etag, version) so incremental
    sync can skip unchanged resources.
    """

    id: str = field(default_factory=_new_id)
    name: str = ""
    connector_type: str = ""  # "feishu", "notion", "rss", ...
    credentials: dict = field(default_factory=dict)
    enabled: bool = True
    last_sync_time: datetime | None = None
    last_sync_status: str = "never"  # "never" | "success" | "failed"
    etag_map: dict[str, str] = field(default_factory=dict)
    hash_map: dict[str, str] = field(default_factory=dict)
    version_map: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass
class SyncRule:
    """Scheduling rule for a sync job."""

    id: str = field(default_factory=_new_id)
    rule_type: str = "manual"  # "manual" | "cron" | "realtime"
    cron_expression: str = ""  # e.g. "0 */6 * * *"
    enabled: bool = True
    webhook_url: str = ""
    webhook_secret: str = ""


@dataclass
class SyncJob:
    """A sync job binds a connector to a schedule."""

    id: str = field(default_factory=_new_id)
    connector_config_id: str = ""
    rule_id: str = ""
    name: str = ""
    status: str = "pending"  # pending | running | completed | failed | cancelled
    enabled: bool = True
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class SyncExecution:
    """One execution of a SyncJob."""

    id: str = field(default_factory=_new_id)
    job_id: str = ""
    status: str = "pending"  # pending | running | completed | failed | partial
    started_at: datetime | None = None
    completed_at: datetime | None = None
    items_fetched: int = 0
    items_new: int = 0
    items_updated: int = 0
    items_deleted: int = 0
    items_renamed: int = 0
    memories_created: int = 0
    errors_count: int = 0
    error: str | None = None
    elapsed_ms: int = 0


@dataclass
class ChangeRecord:
    """Per-resource delta detected during sync."""

    id: str = field(default_factory=_new_id)
    execution_id: str = ""
    connector_type: str = ""
    resource_id: str = ""
    change_type: str = ""  # "new" | "updated" | "deleted" | "renamed"
    content_hash: str = ""
    previous_hash: str = ""
    content: str = ""
    content_type: str = ""  # "text", "markdown", "html", "json", ...
    metadata: dict = field(default_factory=dict)
    processed: bool = False
    process_error: str | None = None
    detected_at: datetime = field(default_factory=_utcnow)


@dataclass
class SyncResource:
    """A resource discovered by listing a connector source."""

    resource_id: str = ""
    name: str = ""
    resource_type: str = ""  # "document", "folder", "article", "video", "note", ...
    updated_at: datetime | None = None
    size_bytes: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class SyncConnectionResult:
    """Result of a connector test_connection() call."""

    success: bool = False
    message: str = ""
    resources_count: int = 0


@dataclass
class SyncPipelineResult:
    """Result of one sync pipeline run."""

    execution_id: str = ""
    status: str = ""  # "completed" | "partial" | "failed"
    items_fetched: int = 0
    items_new: int = 0
    items_updated: int = 0
    items_deleted: int = 0
    items_renamed: int = 0
    memories_created: int = 0
    errors_count: int = 0
    error: str | None = None
    processing_time_ms: int = 0
    change_details: list[dict] = field(default_factory=list)
