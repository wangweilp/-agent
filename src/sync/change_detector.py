"""ChangeDetector — incremental sync change detection.

Strategies (in priority order):
  1. API-provided markers (etag / version) — trust the source
  2. Content hash (SHA-256) — compute and compare
  3. Timestamp-based — compare updated_at vs last_sync_time (fallback)

Output change types: "new" | "updated" | "deleted" | "renamed"

CRITICAL: This module exists to prevent full re-import. Every change that
passes through is incremental.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import ChangeRecord, SyncConnectorConfig, SyncResource

logger = logging.getLogger(__name__)


class ChangeDetector:
    """Performs incremental change detection using multiple strategies.

    The detector is separated from connectors — connectors provide raw data,
    the detector decides what changed. This allows:
      - Connectors to be simple data fetchers
      - Detection strategy to evolve independently
      - Easy testing with mock connectors
    """

    def detect(
        self,
        connector: BaseSyncConnector,
        config: SyncConnectorConfig,
        since: datetime | None = None,
    ) -> list[ChangeRecord]:
        """Fetch current state from connector and compute delta.

        Args:
            connector: The sync connector for the source.
            config: Persisted connector config (carries hash_map, etag_map, version_map).
            since: Only consider changes after this time. None = all changes.

        Returns:
            List of ChangeRecord, one per changed resource.
        """
        # Step 1: Fetch current resource list from source
        try:
            current_resources = connector.list_resources()
        except Exception:
            logger.exception("change_detector_list_failed", extra={"connector": connector.connector_type})
            return []

        if not current_resources:
            # All previously tracked resources are now deleted
            return self._detect_all_deleted(config)

        # Step 2: Build current state maps
        current_ids: set[str] = set()
        id_to_resource: dict[str, SyncResource] = {}
        for res in current_resources:
            current_ids.add(res.resource_id)
            id_to_resource[res.resource_id] = res

        changes: list[ChangeRecord] = []

        for res in current_resources:
            # Strategy 3: Timestamp-based pre-filter
            if since and res.updated_at and res.updated_at < since:
                continue

            # Strategy 1: API-provided change markers
            current_etag = res.metadata.get("etag", "")
            current_version = res.metadata.get("version", "")
            stored_etag = config.etag_map.get(res.resource_id, "")
            stored_version = config.version_map.get(res.resource_id, "")

            if current_etag and stored_etag and current_etag == stored_etag:
                continue  # No change per etag
            if current_version and stored_version and current_version == stored_version:
                continue  # No change per version

            # Need content to determine change type
            try:
                resource_data = connector.fetch_content(res.resource_id)
                content = resource_data.get("content", "")
                content_type = resource_data.get("content_type", "")
                extra_meta = resource_data.get("metadata", {})
            except Exception as fetch_err:
                logger.debug(
                    "change_detector_fetch_content_failed",
                    extra={"resource_id": res.resource_id, "error": str(fetch_err)},
                )
                # Can't fetch — treat as updated if previously known, else new
                change_type = "updated" if res.resource_id in config.hash_map else "new"
                changes.append(ChangeRecord(
                    connector_type=connector.connector_type,
                    resource_id=res.resource_id,
                    change_type=change_type,
                    metadata={**res.metadata, "fetch_error": True},
                ))
                continue

            # Strategy 2: Content hash
            current_hash = BaseSyncConnector.compute_hash(content)
            stored_hash = config.hash_map.get(res.resource_id, "")

            if stored_hash and current_hash == stored_hash:
                # Update etag/version maps even when hash matches
                # (so next time strategy 1 can short-circuit)
                if current_etag:
                    config.etag_map[res.resource_id] = current_etag
                if current_version:
                    config.version_map[res.resource_id] = current_version
                continue  # Content unchanged

            change_type = "new" if not stored_hash else "updated"
            changes.append(ChangeRecord(
                connector_type=connector.connector_type,
                resource_id=res.resource_id,
                change_type=change_type,
                content_hash=current_hash,
                previous_hash=stored_hash,
                content=content,
                content_type=content_type,
                metadata={**res.metadata, **extra_meta},
            ))

        # Step 3: Detect deletions
        deleted_ids = set(config.hash_map.keys()) - current_ids
        for rid in deleted_ids:
            changes.append(ChangeRecord(
                connector_type=connector.connector_type,
                resource_id=rid,
                change_type="deleted",
                previous_hash=config.hash_map.get(rid, ""),
            ))

        # Step 4: Detect renames (same hash, different resource_id)
        self._detect_renames(changes, config)

        logger.info(
            "change_detector_done",
            extra={
                "connector": connector.connector_type,
                "total_changes": len(changes),
                "new": sum(1 for c in changes if c.change_type == "new"),
                "updated": sum(1 for c in changes if c.change_type == "updated"),
                "deleted": sum(1 for c in changes if c.change_type == "deleted"),
                "renamed": sum(1 for c in changes if c.change_type == "renamed"),
            },
        )

        return changes

    # ── Internal helpers ──

    @staticmethod
    def _detect_all_deleted(config: SyncConnectorConfig) -> list[ChangeRecord]:
        """When the source returns no resources, all tracked items are deleted."""
        if not config.hash_map:
            return []
        return [
            ChangeRecord(
                connector_type=config.connector_type,
                resource_id=rid,
                change_type="deleted",
                previous_hash=h,
            )
            for rid, h in config.hash_map.items()
        ]

    @staticmethod
    def _detect_renames(changes: list[ChangeRecord], config: SyncConnectorConfig) -> None:
        """Detect renamed resources by matching content hashes.

        A "new" resource that has the same content_hash as a previously-known
        but now-missing resource is a rename, not a creation.
        """
        # Build reverse hash index from config
        hash_to_id: dict[str, str] = {}
        for rid, h in config.hash_map.items():
            if h:
                hash_to_id[h] = rid

        for ch in changes:
            if ch.change_type == "new" and ch.content_hash:
                old_id = hash_to_id.get(ch.content_hash)
                if old_id and old_id != ch.resource_id:
                    ch.change_type = "renamed"
                    ch.metadata["previous_resource_id"] = old_id

    # ── State update ──

    @staticmethod
    def update_config_state(config: SyncConnectorConfig, changes: list[ChangeRecord]) -> None:
        """Update the connector config's tracking maps after a sync cycle.

        After processing changes, update hash_map, etag_map, version_map,
        and last_sync_time so the next sync is incremental.
        """
        for ch in changes:
            if ch.change_type == "deleted":
                config.hash_map.pop(ch.resource_id, None)
                config.etag_map.pop(ch.resource_id, None)
                config.version_map.pop(ch.resource_id, None)
            elif ch.change_type in ("new", "updated"):
                config.hash_map[ch.resource_id] = ch.content_hash
                if "etag" in ch.metadata:
                    config.etag_map[ch.resource_id] = ch.metadata["etag"]
                if "version" in ch.metadata:
                    config.version_map[ch.resource_id] = ch.metadata["version"]
            elif ch.change_type == "renamed":
                old_id = ch.metadata.get("previous_resource_id", "")
                if old_id:
                    config.hash_map.pop(old_id, None)
                    config.etag_map.pop(old_id, None)
                    config.version_map.pop(old_id, None)
                config.hash_map[ch.resource_id] = ch.content_hash

        config.last_sync_time = datetime.now(timezone.utc)
