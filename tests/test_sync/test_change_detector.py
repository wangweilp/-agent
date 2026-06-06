"""Test suite for ChangeDetector — incremental sync change detection.

Covers every strategy and edge case:
  - No changes when hashes match (no false positives)
  - New resource detection
  - Updated resource detection (hash mismatch)
  - Deleted resource detection
  - Renamed resource detection (same hash, different resource_id)
  - Empty source returns all tracked resources as deleted
  - Timestamp pre-filtering (since=)
  - ETag-based skip (strategy 1)
  - Version-based skip (strategy 1)
  - Mixed changes (new + updated + deleted + renamed) in one call
  - update_config_state correctly mutates hash/etag/version maps
  - Edge cases: empty config state, fetch_content failure, no-resource source
    with empty hash_map, multiple renames in one pass
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.sync.change_detector import ChangeDetector
from src.sync.connector_base import BaseSyncConnector
from src.sync.models import ChangeRecord, SyncConnectorConfig, SyncResource


# ── helpers ──────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(content: str) -> str:
    return BaseSyncConnector.compute_hash(content)


def _cfg(
    *,
    connector_type: str = "mock",
    hash_map: dict[str, str] | None = None,
    etag_map: dict[str, str] | None = None,
    version_map: dict[str, str] | None = None,
) -> SyncConnectorConfig:
    return SyncConnectorConfig(
        id=str(uuid.uuid4()),
        name="test-connector",
        connector_type=connector_type,
        hash_map=hash_map or {},
        etag_map=etag_map or {},
        version_map=version_map or {},
    )


def _resource(
    resource_id: str,
    name: str = "",
    resource_type: str = "document",
    updated_at: datetime | None = None,
    metadata: dict | None = None,
) -> SyncResource:
    return SyncResource(
        resource_id=resource_id,
        name=name or resource_id,
        resource_type=resource_type,
        updated_at=updated_at,
        metadata=metadata or {},
    )


def _build_mock_connector(
    connector_type: str = "mock",
    resources: list[SyncResource] | None = None,
    fetch_content_map: dict[str, dict] | None = None,
    list_resources_side_effect: Exception | None = None,
) -> MagicMock:
    """Create a mock connector with list_resources() and fetch_content().

    * resources: returned by list_resources()
    * fetch_content_map: resource_id -> {"content": ..., "content_type": ..., "metadata": ...}
    * list_resources_side_effect: if set, list_resources() raises this exception
    """
    connector = MagicMock()
    connector.connector_type = connector_type

    if list_resources_side_effect:
        connector.list_resources.side_effect = list_resources_side_effect
    else:
        connector.list_resources.return_value = resources or []

    if fetch_content_map is None:
        fetch_content_map = {}

    def _fetch_content(resource_id: str) -> dict:
        if resource_id in fetch_content_map:
            return fetch_content_map[resource_id]
        return {"content": f"content of {resource_id}", "content_type": "text/plain", "metadata": {}}

    connector.fetch_content.side_effect = _fetch_content
    return connector


def _pluck(records: list[ChangeRecord], change_type: str) -> list[ChangeRecord]:
    return [r for r in records if r.change_type == change_type]


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def detector() -> ChangeDetector:
    return ChangeDetector()


# ── 1. No changes when hashes match ──────────────────────────────────────────

class TestNoChangesWhenHashesMatch:
    """When all resources have matching content hashes, detect returns []."""

    def test_no_changes_returns_empty_list(self, detector: ChangeDetector) -> None:
        content_a = "alpha"
        content_b = "beta"
        config = _cfg(hash_map={"r1": _hash(content_a), "r2": _hash(content_b)})
        connector = _build_mock_connector(
            resources=[_resource("r1"), _resource("r2")],
            fetch_content_map={
                "r1": {"content": content_a, "content_type": "text/plain", "metadata": {}},
                "r2": {"content": content_b, "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        assert changes == []

    def test_hash_match_skips_fetch_when_etag_matches(
        self, detector: ChangeDetector,
    ) -> None:
        """ETag match short-circuits before fetch_content is called."""
        content = "shared content"
        config = _cfg(
            hash_map={"r1": _hash(content)},
            etag_map={"r1": "etag-v1"},
        )
        connector = _build_mock_connector(
            resources=[_resource("r1", metadata={"etag": "etag-v1"})],
            fetch_content_map={
                "r1": {"content": content, "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        assert changes == []
        # fetch_content should NOT have been called — etag skip
        connector.fetch_content.assert_not_called()

    def test_hash_match_skips_fetch_when_version_matches(
        self, detector: ChangeDetector,
    ) -> None:
        """Version match short-circuits before fetch_content is called."""
        content = "shared content"
        config = _cfg(
            hash_map={"r1": _hash(content)},
            version_map={"r1": "v3"},
        )
        connector = _build_mock_connector(
            resources=[_resource("r1", metadata={"version": "v3"})],
            fetch_content_map={
                "r1": {"content": content, "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        assert changes == []
        connector.fetch_content.assert_not_called()

    def test_etag_map_updated_even_when_hash_matches(
        self, detector: ChangeDetector,
    ) -> None:
        """When hash matches but etag was absent, the etag_map is updated
        so next sync can skip via strategy 1."""
        content = "persistent content"
        config = _cfg(hash_map={"r1": _hash(content)})
        connector = _build_mock_connector(
            resources=[_resource("r1", metadata={"etag": "new-etag"})],
            fetch_content_map={
                "r1": {"content": content, "content_type": "text/plain", "metadata": {}},
            },
        )

        detector.detect(connector, config)

        assert config.etag_map.get("r1") == "new-etag"

    def test_version_map_updated_even_when_hash_matches(
        self, detector: ChangeDetector,
    ) -> None:
        """When hash matches but version was absent, the version_map is updated."""
        content = "persistent content"
        config = _cfg(hash_map={"r1": _hash(content)})
        connector = _build_mock_connector(
            resources=[_resource("r1", metadata={"version": "v9"})],
            fetch_content_map={
                "r1": {"content": content, "content_type": "text/plain", "metadata": {}},
            },
        )

        detector.detect(connector, config)

        assert config.version_map.get("r1") == "v9"


# ── 2. Detects new resources ─────────────────────────────────────────────────

class TestDetectsNewResources:
    """When a resource_id never seen before appears, change_type is 'new'."""

    def test_single_new_resource(self, detector: ChangeDetector) -> None:
        config = _cfg()  # empty hash_map = no prior state
        content = "fresh content"
        connector = _build_mock_connector(
            resources=[_resource("new-1")],
            fetch_content_map={
                "new-1": {"content": content, "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        assert len(changes) == 1
        ch = changes[0]
        assert ch.change_type == "new"
        assert ch.resource_id == "new-1"
        assert ch.content_hash == _hash(content)
        assert ch.previous_hash == ""
        assert ch.content == content

    def test_multiple_new_resources(self, detector: ChangeDetector) -> None:
        config = _cfg()
        connector = _build_mock_connector(
            resources=[_resource("a"), _resource("b"), _resource("c")],
            fetch_content_map={
                rid: {"content": f"body-{rid}", "content_type": "text/plain", "metadata": {}}
                for rid in ("a", "b", "c")
            },
        )

        changes = detector.detect(connector, config)

        assert len(changes) == 3
        assert all(c.change_type == "new" for c in changes)
        assert {c.resource_id for c in changes} == {"a", "b", "c"}


# ── 3. Detects updated resources ─────────────────────────────────────────────

class TestDetectsUpdatedResources:
    """When content hash differs from stored hash, change_type is 'updated'."""

    def test_single_update_content_changed(self, detector: ChangeDetector) -> None:
        old_content = "v1 content"
        new_content = "v2 content — revised"
        config = _cfg(hash_map={"doc-1": _hash(old_content)})
        connector = _build_mock_connector(
            resources=[_resource("doc-1")],
            fetch_content_map={
                "doc-1": {"content": new_content, "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        assert len(changes) == 1
        ch = changes[0]
        assert ch.change_type == "updated"
        assert ch.resource_id == "doc-1"
        assert ch.content_hash == _hash(new_content)
        assert ch.previous_hash == _hash(old_content)

    def test_updated_resource_no_stored_hash_treated_as_new(
        self, detector: ChangeDetector,
    ) -> None:
        """Without stored hash, a resource is 'new' regardless of content."""
        config = _cfg()  # empty
        connector = _build_mock_connector(
            resources=[_resource("doc-x")],
            fetch_content_map={
                "doc-x": {"content": "anything", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        assert len(changes) == 1
        assert changes[0].change_type == "new"

    def test_fetch_content_failure_treated_as_updated_if_known(
        self, detector: ChangeDetector,
    ) -> None:
        """If fetch_content fails for a known resource, it is flagged 'updated'."""
        config = _cfg(hash_map={"fail-res": _hash("old")})
        connector = _build_mock_connector(
            resources=[_resource("fail-res")],
        )
        connector.fetch_content.side_effect = lambda rid: (_ for _ in ()).throw(
            RuntimeError("network down")
        )

        changes = detector.detect(connector, config)

        assert len(changes) == 1
        ch = changes[0]
        assert ch.change_type == "updated"
        assert ch.resource_id == "fail-res"
        assert ch.metadata.get("fetch_error") is True

    def test_fetch_content_failure_for_unknown_treated_as_new(
        self, detector: ChangeDetector,
    ) -> None:
        """If fetch_content fails for an unknown resource, it is flagged 'new'."""
        config = _cfg()
        connector = _build_mock_connector(resources=[_resource("fresh-fail")])
        connector.fetch_content.side_effect = RuntimeError("boom")

        changes = detector.detect(connector, config)

        assert len(changes) == 1
        assert changes[0].change_type == "new"


# ── 4. Detects deleted resources ─────────────────────────────────────────────

class TestDetectsDeletedResources:
    """When a resource tracked in hash_map is absent from listing, it is 'deleted'."""

    def test_single_deletion(self, detector: ChangeDetector) -> None:
        config = _cfg(hash_map={"gone-1": _hash("removed")})
        connector = _build_mock_connector(resources=[])  # source lists nothing

        changes = detector.detect(connector, config)

        assert len(changes) == 1
        ch = changes[0]
        assert ch.change_type == "deleted"
        assert ch.resource_id == "gone-1"
        assert ch.previous_hash == _hash("removed")

    def test_multiple_deletions(self, detector: ChangeDetector) -> None:
        config = _cfg(hash_map={
            "r1": _hash("a"),
            "r2": _hash("b"),
            "r3": _hash("c"),
        })
        connector = _build_mock_connector(resources=[_resource("r1")])

        changes = detector.detect(connector, config)

        deleted = _pluck(changes, "deleted")
        assert len(deleted) == 2
        assert {d.resource_id for d in deleted} == {"r2", "r3"}

    def test_no_deletions_when_all_still_present(self, detector: ChangeDetector) -> None:
        config = _cfg(hash_map={
            "r1": _hash("a"),
            "r2": _hash("b"),
        })
        connector = _build_mock_connector(
            resources=[_resource("r1"), _resource("r2")],
            fetch_content_map={
                "r1": {"content": "a", "content_type": "text/plain", "metadata": {}},
                "r2": {"content": "b", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        deleted = _pluck(changes, "deleted")
        assert len(deleted) == 0

    def test_empty_hash_map_produces_no_delete(self, detector: ChangeDetector) -> None:
        """If hash_map is empty, there is nothing to delete even if listing is empty."""
        config = _cfg(hash_map={})
        connector = _build_mock_connector(resources=[])

        changes = detector.detect(connector, config)

        assert changes == []


# ── 5. Detects renamed resources ─────────────────────────────────────────────

class TestDetectsRenamedResources:
    """A resource with same content hash but a new resource_id is a rename."""

    def test_simple_rename(self, detector: ChangeDetector) -> None:
        content = "renamed document content v1"
        config = _cfg(hash_map={"old-id": _hash(content)})
        connector = _build_mock_connector(
            resources=[_resource("new-id")],
            fetch_content_map={
                "new-id": {"content": content, "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        renamed = _pluck(changes, "renamed")
        assert len(renamed) == 1
        ch = renamed[0]
        assert ch.resource_id == "new-id"
        assert ch.content_hash == _hash(content)
        assert ch.metadata.get("previous_resource_id") == "old-id"

    def test_rename_with_deletion_of_old_id(self, detector: ChangeDetector) -> None:
        """When a rename is detected, the old resource_id should be in deleted set."""
        content = "rename me"
        config = _cfg(hash_map={"alpha": _hash(content)})
        connector = _build_mock_connector(
            resources=[_resource("beta")],
            fetch_content_map={
                "beta": {"content": content, "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        # The old ID appears as deleted, new ID as renamed
        by_type = {ch.resource_id: ch.change_type for ch in changes}
        assert by_type.get("alpha") == "deleted"
        assert by_type.get("beta") == "renamed"

    def test_rename_only_when_old_id_differs_from_new_id(
        self, detector: ChangeDetector,
    ) -> None:
        """A 'new' with same ID as tracked should NOT become renamed."""
        content = "same id"
        config = _cfg(hash_map={"r1": _hash(content)}, etag_map={}, version_map={})
        connector = _build_mock_connector(
            resources=[_resource("r1")],
            fetch_content_map={
                "r1": {"content": content, "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        renamed = _pluck(changes, "renamed")
        assert len(renamed) == 0

    def test_no_hash_collision_mistaken_for_rename(
        self, detector: ChangeDetector,
    ) -> None:
        """Different content with a different resource_id is NOT a rename."""
        config = _cfg(hash_map={"old": _hash("alpha content")})
        connector = _build_mock_connector(
            resources=[_resource("new")],
            fetch_content_map={
                "new": {"content": "beta content — different", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        renamed = _pluck(changes, "renamed")
        assert len(renamed) == 0
        # "new" is genuinely new
        assert any(c.resource_id == "new" and c.change_type == "new" for c in changes)


# ── 6. Empty source returns all deleted ──────────────────────────────────────

class TestEmptySourceDeletesAll:
    """When list_resources() returns [], all tracked resources are deleted."""

    def test_non_empty_hash_map_all_deleted(self, detector: ChangeDetector) -> None:
        tracked = {f"res-{i}": _hash(f"body-{i}") for i in range(5)}
        config = _cfg(hash_map=tracked)
        connector = _build_mock_connector(resources=[])

        changes = detector.detect(connector, config)

        assert len(changes) == 5
        assert all(c.change_type == "deleted" for c in changes)
        assert {c.resource_id for c in changes} == set(tracked.keys())
        for c in changes:
            assert c.previous_hash == tracked[c.resource_id]

    def test_empty_hash_map_empty_source_no_changes(
        self, detector: ChangeDetector,
    ) -> None:
        """Empty hash_map + empty source = no changes at all."""
        config = _cfg(hash_map={})
        connector = _build_mock_connector(resources=[])

        changes = detector.detect(connector, config)

        assert changes == []


# ── 7. Timestamp pre-filtering ───────────────────────────────────────────────

class TestTimestampPreFiltering:
    """When `since` is set, resources updated before `since` are skipped."""

    def test_skips_resource_updated_before_since(self, detector: ChangeDetector) -> None:
        old_time = _now() - timedelta(days=30)
        since = _now() - timedelta(days=1)
        config = _cfg()
        connector = _build_mock_connector(
            resources=[_resource("stale", updated_at=old_time)],
            fetch_content_map={
                "stale": {"content": "stale body", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config, since=since)

        assert changes == []

    def test_includes_resource_updated_after_since(self, detector: ChangeDetector) -> None:
        recent_time = _now()
        since = _now() - timedelta(days=1)
        config = _cfg()
        connector = _build_mock_connector(
            resources=[_resource("fresh", updated_at=recent_time)],
            fetch_content_map={
                "fresh": {"content": "fresh body", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config, since=since)

        assert len(changes) == 1
        assert changes[0].resource_id == "fresh"

    def test_resource_without_updated_at_not_filtered(self, detector: ChangeDetector) -> None:
        """Resource with updated_at=None is never timestamp-filtered."""
        since = _now() - timedelta(days=1)
        config = _cfg()
        connector = _build_mock_connector(
            resources=[_resource("no-ts", updated_at=None)],
            fetch_content_map={
                "no-ts": {"content": "body", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config, since=since)

        assert len(changes) == 1
        assert changes[0].resource_id == "no-ts"

    def test_since_none_processes_all(self, detector: ChangeDetector) -> None:
        """since=None means no filtering at all."""
        very_old = _now() - timedelta(days=365)
        config = _cfg()
        connector = _build_mock_connector(
            resources=[_resource("ancient", updated_at=very_old)],
            fetch_content_map={
                "ancient": {"content": "old body", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config, since=None)

        assert len(changes) == 1


# ── 8. ETag-based skip ───────────────────────────────────────────────────────

class TestEtagBasedSkip:
    """Strategy 1: matching etags skip content fetch entirely."""

    def test_etag_match_skips_content_fetch(self, detector: ChangeDetector) -> None:
        config = _cfg(etag_map={"doc": "etag-abc"})
        connector = _build_mock_connector(
            resources=[_resource("doc", metadata={"etag": "etag-abc"})],
            fetch_content_map={
                "doc": {"content": "body", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        assert changes == []
        connector.fetch_content.assert_not_called()

    def test_etag_mismatch_proceeds_to_hash(self, detector: ChangeDetector) -> None:
        config = _cfg(etag_map={"doc": "etag-old"})
        connector = _build_mock_connector(
            resources=[_resource("doc", metadata={"etag": "etag-new"})],
            fetch_content_map={
                "doc": {"content": "body", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        # fetch_content IS called because etags differ
        connector.fetch_content.assert_called_once_with("doc")
        assert len(changes) == 1
        assert changes[0].change_type == "new"

    def test_etag_present_but_no_stored_etag_proceeds(self, detector: ChangeDetector) -> None:
        """If resource sends etag but store has none, etag skip is not applied."""
        config = _cfg(etag_map={})
        connector = _build_mock_connector(
            resources=[_resource("doc", metadata={"etag": "etag-1"})],
            fetch_content_map={
                "doc": {"content": "body", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        assert len(changes) == 1
        connector.fetch_content.assert_called_once_with("doc")

    def test_no_etag_on_resource_proceeds_to_hash(self, detector: ChangeDetector) -> None:
        """No etag from source = cannot skip, must hash."""
        config = _cfg(etag_map={"doc": "etag-old"})
        connector = _build_mock_connector(
            resources=[_resource("doc", metadata={})],  # no etag in metadata
            fetch_content_map={
                "doc": {"content": "body", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        connector.fetch_content.assert_called_once_with("doc")
        assert len(changes) == 1


# ── 9. Version-based skip ────────────────────────────────────────────────────

class TestVersionBasedSkip:
    """Strategy 1: matching versions skip content fetch entirely."""

    def test_version_match_skips_content_fetch(self, detector: ChangeDetector) -> None:
        config = _cfg(version_map={"note": "v5"})
        connector = _build_mock_connector(
            resources=[_resource("note", metadata={"version": "v5"})],
            fetch_content_map={
                "note": {"content": "body", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        assert changes == []
        connector.fetch_content.assert_not_called()

    def test_version_mismatch_proceeds_to_hash(self, detector: ChangeDetector) -> None:
        config = _cfg(version_map={"note": "v4"})
        connector = _build_mock_connector(
            resources=[_resource("note", metadata={"version": "v6"})],
            fetch_content_map={
                "note": {"content": "body", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        connector.fetch_content.assert_called_once_with("note")
        assert len(changes) == 1

    def test_version_present_but_no_stored_version_proceeds(self, detector: ChangeDetector) -> None:
        config = _cfg(version_map={})
        connector = _build_mock_connector(
            resources=[_resource("note", metadata={"version": "v1"})],
            fetch_content_map={
                "note": {"content": "body", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        assert len(changes) == 1
        connector.fetch_content.assert_called_once_with("note")

    def test_etag_match_short_circuits_before_version_check(
        self, detector: ChangeDetector,
    ) -> None:
        """If etag matches, we never reach version or hash checks."""
        config = _cfg(
            etag_map={"doc": "etag-match"},
            version_map={"doc": "old-version"},
        )
        connector = _build_mock_connector(
            resources=[_resource("doc", metadata={"etag": "etag-match", "version": "new-version"})],
            fetch_content_map={
                "doc": {"content": "changed body", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        assert changes == []
        connector.fetch_content.assert_not_called()


# ── 10. Mixed changes ────────────────────────────────────────────────────────

class TestMixedChanges:
    """A single detect() call can produce new + updated + deleted + renamed."""

    def test_all_four_types_in_one_run(self, detector: ChangeDetector) -> None:
        shared_content = "shared content for rename detection"
        config = _cfg(
            hash_map={
                "keep": _hash("unchanged"),
                "update": _hash("v1"),
                "gone": _hash("bye"),
                "name-v1": _hash(shared_content),
            }
        )
        connector = _build_mock_connector(
            resources=[
                _resource("keep"),
                _resource("update"),
                _resource("new-kid"),
                _resource("name-v2"),
            ],
            fetch_content_map={
                "keep": {"content": "unchanged", "content_type": "text/plain", "metadata": {}},
                "update": {"content": "v2 revised", "content_type": "text/plain", "metadata": {}},
                "new-kid": {"content": "brand new", "content_type": "text/plain", "metadata": {}},
                "name-v2": {"content": shared_content, "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        # 5 changes: updated, new, deleted (gone), deleted (name-v1), renamed (name-v2)
        assert len(changes) == 5
        by_type = {c.resource_id: c.change_type for c in changes}
        # "keep" is not in changes (unchanged)
        assert by_type["update"] == "updated"
        assert by_type["new-kid"] == "new"
        assert by_type["gone"] == "deleted"
        assert by_type["name-v1"] == "deleted"  # old name not in listing
        assert by_type["name-v2"] == "renamed"

    def test_new_with_same_content_as_existing_old_resource(
        self, detector: ChangeDetector,
    ) -> None:
        """When a new resource has the same content hash as an old tracked
        resource that is still present, the rename detector classifies the
        new one as 'renamed' anyway (it only checks hash-to-id mapping,
        not whether the old id is still active in the listing)."""
        content = "duplicate content"
        config = _cfg(hash_map={"alpha": _hash(content)})
        connector = _build_mock_connector(
            resources=[_resource("alpha"), _resource("beta")],
            fetch_content_map={
                "alpha": {"content": content, "content_type": "text/plain", "metadata": {}},
                "beta": {"content": content, "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        by_type = {c.resource_id: c.change_type for c in changes}
        # alpha is unchanged (hash matches)
        assert by_type.get("alpha") is None  # not in changes
        # beta has same hash as alpha → classified as renamed by _detect_renames
        assert by_type["beta"] == "renamed"


# ── 11. update_config_state ──────────────────────────────────────────────────

class TestUpdateConfigState:
    """update_config_state mutates hash_map, etag_map, version_map, last_sync_time."""

    def test_new_resources_added_to_maps(self) -> None:
        config = _cfg(hash_map={}, etag_map={}, version_map={})
        changes = [
            ChangeRecord(
                resource_id="r1",
                change_type="new",
                content_hash=_hash("hello"),
                metadata={"etag": "e1", "version": "v1"},
            ),
        ]

        ChangeDetector.update_config_state(config, changes)

        assert config.hash_map == {"r1": _hash("hello")}
        assert config.etag_map == {"r1": "e1"}
        assert config.version_map == {"r1": "v1"}
        assert config.last_sync_time is not None

    def test_updated_resources_refresh_maps(self) -> None:
        config = _cfg(
            hash_map={"r1": _hash("old")},
            etag_map={"r1": "old-etag"},
            version_map={"r1": "old-ver"},
        )
        changes = [
            ChangeRecord(
                resource_id="r1",
                change_type="updated",
                content_hash=_hash("new content"),
                metadata={"etag": "new-etag", "version": "v2"},
            ),
        ]

        ChangeDetector.update_config_state(config, changes)

        assert config.hash_map["r1"] == _hash("new content")
        assert config.etag_map["r1"] == "new-etag"
        assert config.version_map["r1"] == "v2"

    def test_deleted_resources_removed_from_all_maps(self) -> None:
        config = _cfg(
            hash_map={"d1": _hash("dead"), "keep": _hash("alive")},
            etag_map={"d1": "etag-dead", "keep": "etag-alive"},
            version_map={"d1": "v-dead", "keep": "v-alive"},
        )
        changes = [
            ChangeRecord(
                resource_id="d1",
                change_type="deleted",
                previous_hash=_hash("dead"),
            ),
        ]

        ChangeDetector.update_config_state(config, changes)

        assert "d1" not in config.hash_map
        assert "d1" not in config.etag_map
        assert "d1" not in config.version_map
        assert config.hash_map["keep"] == _hash("alive")

    def test_renamed_resources_swap_old_for_new(self) -> None:
        config = _cfg(
            hash_map={"old-name": _hash("shared")},
            etag_map={"old-name": "e-old"},
            version_map={"old-name": "v-old"},
        )
        changes = [
            ChangeRecord(
                resource_id="new-name",
                change_type="renamed",
                content_hash=_hash("shared"),
                metadata={"previous_resource_id": "old-name"},
            ),
        ]

        ChangeDetector.update_config_state(config, changes)

        assert "old-name" not in config.hash_map
        assert "old-name" not in config.etag_map
        assert "old-name" not in config.version_map
        assert config.hash_map["new-name"] == _hash("shared")

    def test_renamed_without_previous_id_does_not_clear_old(self) -> None:
        """If previous_resource_id is missing (edge case), only new mapping is added."""
        config = _cfg(hash_map={"x": _hash("x-content")})
        changes = [
            ChangeRecord(
                resource_id="y",
                change_type="renamed",
                content_hash=_hash("x-content"),
                metadata={},  # no previous_resource_id
            ),
        ]

        ChangeDetector.update_config_state(config, changes)

        assert "x" in config.hash_map  # not cleared
        assert config.hash_map["y"] == _hash("x-content")

    def test_last_sync_time_is_set(self) -> None:
        config = _cfg()
        assert config.last_sync_time is None

        ChangeDetector.update_config_state(config, [])

        assert config.last_sync_time is not None
        assert config.last_sync_time.tzinfo == timezone.utc

    def test_mixed_changes_all_handled(self) -> None:
        config = _cfg(
            hash_map={"u": _hash("old-u"), "d": _hash("old-d"), "rn": _hash("shared")},
            etag_map={"u": "e-u", "d": "e-d", "rn": "e-rn"},
            version_map={"u": "v-u", "d": "v-d", "rn": "v-rn"},
        )
        changes = [
            ChangeRecord(
                resource_id="n",
                change_type="new",
                content_hash=_hash("new-n"),
                metadata={"etag": "e-n"},
            ),
            ChangeRecord(
                resource_id="u",
                change_type="updated",
                content_hash=_hash("new-u"),
                metadata={"etag": "e-u2"},
            ),
            ChangeRecord(
                resource_id="d",
                change_type="deleted",
                previous_hash=_hash("old-d"),
            ),
            ChangeRecord(
                resource_id="rn-new",
                change_type="renamed",
                content_hash=_hash("shared"),
                metadata={"previous_resource_id": "rn"},
            ),
        ]

        ChangeDetector.update_config_state(config, changes)

        assert config.hash_map == {
            "n": _hash("new-n"),
            "u": _hash("new-u"),
            "rn-new": _hash("shared"),
        }
        assert config.etag_map == {"u": "e-u2", "n": "e-n"}
        assert config.version_map == {"u": "v-u"}  # n had no version, rn/new had none
        assert config.last_sync_time is not None


# ── 12. Edge cases ───────────────────────────────────────────────────────────

class TestEdgeCases:
    """Various edge conditions that should not crash or produce wrong results."""

    def test_list_resources_exception_returns_empty(self, detector: ChangeDetector) -> None:
        """When connector.list_resources() raises, return [] gracefully."""
        config = _cfg(hash_map={"r1": _hash("content")})
        connector = _build_mock_connector(
            list_resources_side_effect=ConnectionError("timeout"),
        )

        changes = detector.detect(connector, config)

        assert changes == []

    def test_zero_resources_with_empty_hash_map_is_noop(
        self, detector: ChangeDetector,
    ) -> None:
        config = _cfg(hash_map={})
        connector = _build_mock_connector(resources=[])

        changes = detector.detect(connector, config)

        assert changes == []

    def test_resource_with_all_change_markers_new(
        self, detector: ChangeDetector,
    ) -> None:
        """A truly new resource with etag, version, and content is classified 'new'."""
        config = _cfg()
        connector = _build_mock_connector(
            resources=[_resource("novel", metadata={"etag": "abc", "version": "1"})],
            fetch_content_map={
                "novel": {"content": "new post", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        assert len(changes) == 1
        assert changes[0].change_type == "new"

    def test_content_type_preserved_in_change_record(
        self, detector: ChangeDetector,
    ) -> None:
        config = _cfg()
        connector = _build_mock_connector(
            resources=[_resource("md-doc")],
            fetch_content_map={
                "md-doc": {"content": "# Title", "content_type": "text/markdown", "metadata": {"author": "test"}},
            },
        )

        changes = detector.detect(connector, config)

        assert changes[0].content_type == "text/markdown"
        assert changes[0].metadata.get("author") == "test"

    def test_content_metadata_merged_with_resource_metadata(
        self, detector: ChangeDetector,
    ) -> None:
        config = _cfg()
        connector = _build_mock_connector(
            resources=[_resource("doc", metadata={"source_tag": "api", "etag": "e1"})],
            fetch_content_map={
                "doc": {"content": "body", "content_type": "text/plain", "metadata": {"nested": True}},
            },
        )

        changes = detector.detect(connector, config)

        ch = changes[0]
        assert ch.metadata.get("source_tag") == "api"  # from SyncResource
        assert ch.metadata.get("etag") == "e1"  # from SyncResource
        assert ch.metadata.get("nested") is True  # from fetch_content

    def test_multiple_renames_in_one_pass(self, detector: ChangeDetector) -> None:
        shared_content = "content for multiple renames"
        config = _cfg(
            hash_map={
                "keep": _hash("static"),
                "a": _hash(shared_content),
                "c": _hash("something else"),
            }
        )
        connector = _build_mock_connector(
            resources=[
                _resource("keep"),
                _resource("b"),   # was "a" — renamed
                _resource("d"),   # was "c" — renamed
            ],
            fetch_content_map={
                "keep": {"content": "static", "content_type": "text/plain", "metadata": {}},
                "b": {"content": shared_content, "content_type": "text/plain", "metadata": {}},
                "d": {"content": "something else", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        renamed = {c.resource_id: c.metadata.get("previous_resource_id") for c in _pluck(changes, "renamed")}
        assert renamed == {"b": "a", "d": "c"}

    def test_etag_updated_in_config_during_hash_match_detection(
        self, detector: ChangeDetector,
    ) -> None:
        """Confirm that when hash matches and etag is present, config.etag_map is mutated."""
        content = "etag update test"
        config = _cfg(hash_map={"r1": _hash(content)}, etag_map={})
        connector = _build_mock_connector(
            resources=[_resource("r1", metadata={"etag": "brand-new-etag"})],
            fetch_content_map={
                "r1": {"content": content, "content_type": "text/plain", "metadata": {}},
            },
        )

        detector.detect(connector, config)

        assert config.etag_map["r1"] == "brand-new-etag"

    def test_skip_both_etag_and_version_present_but_only_etag_matches(
        self, detector: ChangeDetector,
    ) -> None:
        """If etag matches but version mismatches, etag wins — no fetch."""
        config = _cfg(
            etag_map={"r1": "matching-etag"},
            version_map={"r1": "old-version"},
        )
        connector = _build_mock_connector(
            resources=[_resource("r1", metadata={"etag": "matching-etag", "version": "new-version"})],
            fetch_content_map={
                "r1": {"content": "whatever", "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        assert changes == []
        connector.fetch_content.assert_not_called()

    def test_deleted_but_also_listed_as_new_is_rename(
        self, detector: ChangeDetector,
    ) -> None:
        """If a resource is deleted from hash_map and a 'new' resource has same hash,
        the 'new' is promoted to 'renamed'."""
        content = "same old content"
        config = _cfg(hash_map={"deleteme": _hash(content)})
        connector = _build_mock_connector(
            resources=[_resource("replacement")],
            fetch_content_map={
                "replacement": {"content": content, "content_type": "text/plain", "metadata": {}},
            },
        )

        changes = detector.detect(connector, config)

        # There will be a deleted and a renamed (not new + deleted mismatch)
        types = {ch.resource_id: ch.change_type for ch in changes}
        assert types["deleteme"] == "deleted"
        assert types["replacement"] == "renamed"


# ── 13. Metadata propagation ─────────────────────────────────────────────────

class TestMetadataPropagation:
    """Verify that metadata fields survive the full detect() pipeline."""

    def test_resource_metadata_flows_to_change_record(self, detector: ChangeDetector) -> None:
        config = _cfg()
        connector = _build_mock_connector(
            resources=[_resource(
                "m1",
                metadata={"color": "blue", "priority": 1},
            )],
            fetch_content_map={
                "m1": {"content": "body", "content_type": "text/plain", "metadata": {"extra": "value"}},
            },
        )

        changes = detector.detect(connector, config)

        ch = changes[0]
        assert ch.metadata["color"] == "blue"
        assert ch.metadata["priority"] == 1
        assert ch.metadata["extra"] == "value"

    def test_fetch_error_metadata_present(self, detector: ChangeDetector) -> None:
        config = _cfg(hash_map={"f1": _hash("old")})
        connector = _build_mock_connector(resources=[_resource("f1")])
        connector.fetch_content.side_effect = OSError("disk full")

        changes = detector.detect(connector, config)

        assert changes[0].metadata.get("fetch_error") is True


# ── 14. Large-scale correctness ──────────────────────────────────────────────

class TestLargeScale:
    """Smoke tests with many resources to ensure no O(N^2) scaling issues."""

    def test_hundred_unchanged_resources_produce_no_changes(
        self, detector: ChangeDetector,
    ) -> None:
        n = 100
        hash_map = {f"r{i}": _hash(f"content-{i}") for i in range(n)}
        config = _cfg(hash_map=hash_map)
        connector = _build_mock_connector(
            resources=[_resource(f"r{i}") for i in range(n)],
            fetch_content_map={
                f"r{i}": {"content": f"content-{i}", "content_type": "text/plain", "metadata": {}}
                for i in range(n)
            },
        )

        changes = detector.detect(connector, config)

        assert changes == []

    def test_hundred_new_resources_all_detected(self, detector: ChangeDetector) -> None:
        n = 100
        config = _cfg()
        connector = _build_mock_connector(
            resources=[_resource(f"r{i}") for i in range(n)],
            fetch_content_map={
                f"r{i}": {"content": f"new-{i}", "content_type": "text/plain", "metadata": {}}
                for i in range(n)
            },
        )

        changes = detector.detect(connector, config)

        assert len(changes) == n
        assert all(c.change_type == "new" for c in changes)
