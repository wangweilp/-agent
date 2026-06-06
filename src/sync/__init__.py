"""Sync Hub — continuous multi-source data synchronization.

Public API:
  - SYNC_CONNECTOR_REGISTRY — maps connector_type strings to connector classes
  - SyncConnector / BaseSyncConnector — connector interface
  - SyncStore — SQLite persistence
  - SyncScheduler — cron-based job scheduler
  - SyncPipeline — full pipeline (reuses ImportMemoryPipeline)
  - SyncWorker — background execution thread
  - Models: SyncJob, SyncRule, SyncExecution, ChangeRecord, SyncConnectorConfig
"""

from src.sync.connector_base import BaseSyncConnector, SyncConnector
from src.sync.models import (
    ChangeRecord,
    SyncConnectionResult,
    SyncConnectorConfig,
    SyncExecution,
    SyncJob,
    SyncPipelineResult,
    SyncResource,
    SyncRule,
)
from src.sync.sync_store import SyncStore

# ── Connector Registry ──
# Populated lazily to avoid circular imports.
# Each connector registers itself by calling _register().

SYNC_CONNECTOR_REGISTRY: dict[str, type[BaseSyncConnector]] = {}


def _register(connector_type: str, cls: type[BaseSyncConnector]) -> None:
    """Register a connector class in the global registry."""
    SYNC_CONNECTOR_REGISTRY[connector_type] = cls


# Import connectors to trigger registration
from src.sync.connectors import (  # noqa: E402, F401
    bilibili_connector,
    dropbox_connector,
    feishu_connector,
    gdrive_connector,
    github_connector,
    local_folder_connector,
    logseq_connector,
    notion_connector,
    obsidian_connector,
    onedrive_connector,
    rss_connector,
    wechat_mp_connector,
    weixin_reader_connector,
    yuque_connector,
)

__all__ = [
    "SYNC_CONNECTOR_REGISTRY",
    "BaseSyncConnector",
    "SyncConnector",
    "SyncStore",
    "SyncJob",
    "SyncRule",
    "SyncExecution",
    "ChangeRecord",
    "SyncConnectorConfig",
    "SyncResource",
    "SyncConnectionResult",
    "SyncPipelineResult",
]
