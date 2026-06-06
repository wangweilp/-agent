"""SyncConnector Protocol + BaseSyncConnector — unified interface for all sync sources.

Follows the same pattern as src/importers/base.py:
  - SyncConnector is a Protocol (like Importer)
  - BaseSyncConnector provides shared utilities (like the helpers in importers/base.py)

Each connector inherits from BaseSyncConnector for shared code and satisfies
SyncConnector for type checking.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from src.sync.models import SyncConnectionResult, SyncResource


# ── Protocol ──


@runtime_checkable
class SyncConnector(Protocol):
    """Protocol every sync connector must satisfy.

    Mirrors the Importer protocol in src/importers/base.py — stateless,
    receives config at construction time, and exposes four standard methods.
    """

    connector_type: str  # e.g. "feishu", "notion", "rss"

    def test_connection(self) -> SyncConnectionResult:
        """Verify credentials and connectivity to the source."""
        ...

    def list_resources(self) -> list[SyncResource]:
        """List all available resources (documents, notes, articles, ...)."""
        ...

    def fetch_changes(self, since: datetime | None) -> list:
        """Return raw change metadata since the given timestamp.

        Connectors may return lightweight change descriptors here;
        the ChangeDetector handles the heavy diff logic.
        """
        ...

    def fetch_content(self, resource_id: str) -> dict:
        """Fetch full content for a single resource.

        Returns:
            {"content": str, "content_type": str, "metadata": dict}
        """
        ...


# ── Base implementation ──


class BaseSyncConnector:
    """Shared base for all concrete connectors.

    Provides:
      - compute_hash() — deterministic content hashing for change detection
      - now_utc() — timezone-aware timestamp helper
      - config passthrough + logger setup
    """

    connector_type: str = "base"

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}
        self.logger = logging.getLogger(f"sync.connector.{self.connector_type}")

    def test_connection(self) -> SyncConnectionResult:
        raise NotImplementedError

    def list_resources(self) -> list[SyncResource]:
        raise NotImplementedError

    def fetch_changes(self, since: datetime | None) -> list:
        raise NotImplementedError

    def fetch_content(self, resource_id: str) -> dict:
        raise NotImplementedError

    # ── Shared utilities ──

    @staticmethod
    def compute_hash(content: str) -> str:
        """SHA-256 hex digest for deterministic content comparison."""
        return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(timezone.utc)
