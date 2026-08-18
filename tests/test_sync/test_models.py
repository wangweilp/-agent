"""Unit tests for sync dataclass models.

Tests all dataclasses for default_factory correctness, field types,
field defaults, immutability (where applicable), and serialization.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone

import pytest

from src.sync.models import (
    SyncConnectorConfig,
    SyncRule,
    SyncJob,
    SyncExecution,
    ChangeRecord,
    SyncResource,
    SyncConnectionResult,
    SyncPipelineResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _recent_utc(dt: datetime) -> bool:
    """Return True if *dt* is a tz-aware UTC datetime within the last 5 seconds."""
    now = datetime.now(timezone.utc)
    delta = abs((now - dt).total_seconds())
    return dt.tzinfo is not None and delta < 5.0


# ===================================================================
# SyncConnectorConfig
# ===================================================================


class TestSyncConnectorConfig:
    def test_default_factory_id_is_unique_uuid_string(self):
        c1 = SyncConnectorConfig()
        c2 = SyncConnectorConfig()
        assert isinstance(c1.id, str)
        assert isinstance(c2.id, str)
        assert len(c1.id) == 36  # standard UUID string length
        assert uuid.UUID(c1.id)   # does not raise
        assert c1.id != c2.id

    def test_defaults_are_correct(self):
        cfg = SyncConnectorConfig()
        assert cfg.name == ""
        assert cfg.connector_type == ""
        assert cfg.credentials == {}
        assert cfg.enabled is True
        assert cfg.last_sync_time is None
        assert cfg.last_sync_status == "never"
        assert cfg.etag_map == {}
        assert cfg.hash_map == {}
        assert cfg.version_map == {}
        assert cfg.enabled is True

    def test_created_at_and_updated_at_are_utc_datetimes(self):
        cfg = SyncConnectorConfig()
        assert isinstance(cfg.created_at, datetime)
        assert isinstance(cfg.updated_at, datetime)
        assert _recent_utc(cfg.created_at)
        assert _recent_utc(cfg.updated_at)

    def test_dict_fields_are_independent_copies(self):
        """Each instance must get its own mutable dict, not share one."""
        c1 = SyncConnectorConfig()
        c2 = SyncConnectorConfig()
        c1.credentials["key"] = "a"
        c1.etag_map["r1"] = "etag1"
        c1.hash_map["r2"] = "hash2"
        c1.version_map["r3"] = "v3"
        assert c2.credentials == {}
        assert c2.etag_map == {}
        assert c2.hash_map == {}
        assert c2.version_map == {}

    def test_custom_values_set_correctly(self):
        ts = datetime(2025, 1, 15, tzinfo=timezone.utc)
        cfg = SyncConnectorConfig(
            name="my-connector",
            connector_type="notion",
            credentials={"token": "abc"},
            enabled=False,
            last_sync_time=ts,
            last_sync_status="success",
            etag_map={"a": "e1"},
            hash_map={"b": "h2"},
            version_map={"c": "v3"},
        )
        assert cfg.name == "my-connector"
        assert cfg.connector_type == "notion"
        assert cfg.credentials == {"token": "abc"}
        assert cfg.enabled is False
        assert cfg.last_sync_time == ts
        assert cfg.last_sync_status == "success"
        assert cfg.etag_map == {"a": "e1"}
        assert cfg.hash_map == {"b": "h2"}
        assert cfg.version_map == {"c": "v3"}

    def test_serialization_returns_dict_with_all_fields(self):
        cfg = SyncConnectorConfig(name="test", connector_type="rss")
        d = asdict(cfg)
        expected_keys = {
            "id", "name", "connector_type", "credentials", "enabled",
            "last_sync_time", "last_sync_status", "etag_map", "hash_map",
            "version_map", "created_at", "updated_at", "workspace_id",
        }
        assert set(d.keys()) == expected_keys
        assert d["name"] == "test"
        assert d["connector_type"] == "rss"


# ===================================================================
# SyncRule
# ===================================================================


class TestSyncRule:
    def test_defaults(self):
        rule = SyncRule()
        assert rule.rule_type == "manual"
        assert rule.cron_expression == ""
        assert rule.enabled is True
        assert rule.webhook_url == ""
        assert rule.webhook_secret == ""

    def test_id_is_unique_uuid_per_instance(self):
        r1 = SyncRule()
        r2 = SyncRule()
        assert r1.id != r2.id
        assert uuid.UUID(r1.id)

    def test_cron_rule_with_custom_fields(self):
        rule = SyncRule(
            rule_type="cron",
            cron_expression="0 */6 * * *",
            enabled=False,
        )
        assert rule.rule_type == "cron"
        assert rule.cron_expression == "0 */6 * * *"
        assert rule.enabled is False

    def test_webhook_rule_fields(self):
        rule = SyncRule(
            rule_type="realtime",
            webhook_url="https://example.com/hook",
            webhook_secret="shhh",
        )
        assert rule.rule_type == "realtime"
        assert rule.webhook_url == "https://example.com/hook"
        assert rule.webhook_secret == "shhh"

    def test_serialization(self):
        rule = SyncRule(rule_type="cron", cron_expression="*/5 * * * *")
        d = asdict(rule)
        assert d["rule_type"] == "cron"
        assert d["cron_expression"] == "*/5 * * * *"


# ===================================================================
# SyncJob
# ===================================================================


class TestSyncJob:
    def test_defaults(self):
        job = SyncJob()
        assert job.connector_config_id == ""
        assert job.rule_id == ""
        assert job.name == ""
        assert job.status == "pending"
        assert job.enabled is True
        assert isinstance(job.created_at, datetime)
        assert _recent_utc(job.created_at)

    def test_id_is_unique(self):
        j1 = SyncJob()
        j2 = SyncJob()
        assert j1.id != j2.id

    def test_custom_values(self):
        job = SyncJob(
            connector_config_id="cfg-1",
            rule_id="rule-3",
            name="feishu-sync-daily",
            status="running",
            enabled=False,
        )
        assert job.connector_config_id == "cfg-1"
        assert job.rule_id == "rule-3"
        assert job.name == "feishu-sync-daily"
        assert job.status == "running"
        assert job.enabled is False

    def test_serialization(self):
        job = SyncJob(connector_config_id="cc", rule_id="rr", name="n")
        d = asdict(job)
        assert d["connector_config_id"] == "cc"
        assert d["rule_id"] == "rr"
        assert d["name"] == "n"
        assert d["status"] == "pending"


# ===================================================================
# SyncExecution
# ===================================================================


class TestSyncExecution:
    def test_defaults_and_id(self):
        ex = SyncExecution()
        assert uuid.UUID(ex.id)
        assert ex.job_id == ""
        assert ex.status == "pending"
        assert ex.started_at is None
        assert ex.completed_at is None
        assert ex.items_fetched == 0
        assert ex.items_new == 0
        assert ex.items_updated == 0
        assert ex.items_deleted == 0
        assert ex.items_renamed == 0
        assert ex.memories_created == 0
        assert ex.errors_count == 0
        assert ex.error is None
        assert ex.elapsed_ms == 0

    def test_full_lifecyle_values(self):
        start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc)
        ex = SyncExecution(
            job_id="job-42",
            status="completed",
            started_at=start,
            completed_at=end,
            items_fetched=100,
            items_new=10,
            items_updated=5,
            items_deleted=2,
            items_renamed=3,
            memories_created=8,
            errors_count=0,
            elapsed_ms=300_000,
        )
        assert ex.job_id == "job-42"
        assert ex.status == "completed"
        assert ex.started_at == start
        assert ex.completed_at == end
        assert ex.items_fetched == 100
        assert ex.items_new == 10
        assert ex.items_updated == 5
        assert ex.items_deleted == 2
        assert ex.items_renamed == 3
        assert ex.memories_created == 8
        assert ex.errors_count == 0
        assert ex.elapsed_ms == 300_000

    def test_error_field_supports_none_and_string(self):
        ex_ok = SyncExecution(status="completed")
        assert ex_ok.error is None

        ex_fail = SyncExecution(status="failed", error="timeout")
        assert ex_fail.error == "timeout"

    def test_serialization(self):
        ex = SyncExecution(
            job_id="j1",
            status="completed",
            items_fetched=50,
            errors_count=1,
            error="boom",
            elapsed_ms=1234,
        )
        d = asdict(ex)
        assert d["job_id"] == "j1"
        assert d["status"] == "completed"
        assert d["items_fetched"] == 50
        assert d["errors_count"] == 1
        assert d["error"] == "boom"
        assert d["elapsed_ms"] == 1234


# ===================================================================
# ChangeRecord
# ===================================================================


class TestChangeRecord:
    def test_defaults(self):
        cr = ChangeRecord()
        assert uuid.UUID(cr.id)
        assert cr.execution_id == ""
        assert cr.connector_type == ""
        assert cr.resource_id == ""
        assert cr.change_type == ""
        assert cr.content_hash == ""
        assert cr.previous_hash == ""
        assert cr.content == ""
        assert cr.content_type == ""
        assert cr.metadata == {}
        assert cr.processed is False
        assert cr.process_error is None
        assert isinstance(cr.detected_at, datetime)
        assert _recent_utc(cr.detected_at)

    def test_metadata_is_independent_per_instance(self):
        c1 = ChangeRecord()
        c2 = ChangeRecord()
        c1.metadata["source"] = "feishu"
        assert c2.metadata == {}

    def test_new_change_type(self):
        cr = ChangeRecord(
            execution_id="ex-1",
            connector_type="notion",
            resource_id="res-99",
            change_type="new",
            content_hash="abc123",
            content="# New page",
            content_type="markdown",
            processed=True,
        )
        assert cr.execution_id == "ex-1"
        assert cr.connector_type == "notion"
        assert cr.resource_id == "res-99"
        assert cr.change_type == "new"
        assert cr.content_hash == "abc123"
        assert cr.content == "# New page"
        assert cr.content_type == "markdown"
        assert cr.processed is True

    def test_updated_change_type_with_previous_hash(self):
        cr = ChangeRecord(
            change_type="updated",
            content_hash="newhash",
            previous_hash="oldhash",
        )
        assert cr.change_type == "updated"
        assert cr.content_hash == "newhash"
        assert cr.previous_hash == "oldhash"

    def test_deleted_change_type_with_empty_content(self):
        cr = ChangeRecord(
            change_type="deleted",
            content="",
        )
        assert cr.change_type == "deleted"
        assert cr.content == ""

    def test_renamed_change_type(self):
        cr = ChangeRecord(
            change_type="renamed",
            resource_id="res-x",
            metadata={"old_name": "foo.md", "new_name": "bar.md"},
        )
        assert cr.change_type == "renamed"
        assert cr.metadata["old_name"] == "foo.md"
        assert cr.metadata["new_name"] == "bar.md"

    def test_process_error_tracks_failure(self):
        cr = ChangeRecord(processed=False, process_error="encoding error")
        assert cr.processed is False
        assert cr.process_error == "encoding error"


# ===================================================================
# SyncResource
# ===================================================================


class TestSyncResource:
    def test_default_values(self):
        res = SyncResource()
        assert res.resource_id == ""
        assert res.name == ""
        assert res.resource_type == ""
        assert res.updated_at is None
        assert res.size_bytes == 0
        assert res.metadata == {}

    def test_metadata_independent_per_instance(self):
        r1 = SyncResource()
        r2 = SyncResource()
        r1.metadata["kind"] = "page"
        assert r2.metadata == {}

    def test_full_resource_populated(self):
        ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
        res = SyncResource(
            resource_id="res-001",
            name="Design Doc",
            resource_type="document",
            updated_at=ts,
            size_bytes=2048,
            metadata={"workspace": "eng", "lang": "en"},
        )
        assert res.resource_id == "res-001"
        assert res.name == "Design Doc"
        assert res.resource_type == "document"
        assert res.updated_at == ts
        assert res.size_bytes == 2048
        assert res.metadata == {"workspace": "eng", "lang": "en"}

    def test_serialization_handles_none_updated_at(self):
        res = SyncResource(resource_id="r1", name="test")
        d = asdict(res)
        assert d["updated_at"] is None


# ===================================================================
# SyncConnectionResult
# ===================================================================


class TestSyncConnectionResult:
    def test_defaults_mean_failed_connection(self):
        r = SyncConnectionResult()
        assert r.success is False
        assert r.message == ""
        assert r.resources_count == 0

    def test_successful_connection(self):
        r = SyncConnectionResult(
            success=True,
            message="OK",
            resources_count=42,
        )
        assert r.success is True
        assert r.message == "OK"
        assert r.resources_count == 42

    def test_failed_connection_with_error_message(self):
        r = SyncConnectionResult(
            success=False,
            message="Authentication failed: invalid token",
        )
        assert r.success is False
        assert r.message == "Authentication failed: invalid token"
        assert r.resources_count == 0


# ===================================================================
# SyncPipelineResult
# ===================================================================


class TestSyncPipelineResult:
    def test_defaults(self):
        pr = SyncPipelineResult()
        assert pr.execution_id == ""
        assert pr.status == ""
        assert pr.items_fetched == 0
        assert pr.items_new == 0
        assert pr.items_updated == 0
        assert pr.items_deleted == 0
        assert pr.items_renamed == 0
        assert pr.memories_created == 0
        assert pr.errors_count == 0
        assert pr.error is None
        assert pr.processing_time_ms == 0
        assert pr.change_details == []

    def test_change_details_is_independent_list(self):
        p1 = SyncPipelineResult()
        p2 = SyncPipelineResult()
        p1.change_details.append({"type": "new"})
        assert p2.change_details == []

    def test_successful_pipeline_result(self):
        pr = SyncPipelineResult(
            execution_id="ex-42",
            status="completed",
            items_fetched=200,
            items_new=15,
            items_updated=8,
            items_deleted=3,
            items_renamed=1,
            memories_created=12,
            errors_count=0,
            processing_time_ms=5_600,
            change_details=[
                {"resource_id": "a", "change": "new"},
                {"resource_id": "b", "change": "updated"},
            ],
        )
        assert pr.execution_id == "ex-42"
        assert pr.status == "completed"
        assert pr.items_fetched == 200
        assert pr.items_new == 15
        assert pr.items_updated == 8
        assert pr.items_deleted == 3
        assert pr.items_renamed == 1
        assert pr.memories_created == 12
        assert pr.errors_count == 0
        assert pr.error is None
        assert pr.processing_time_ms == 5_600
        assert len(pr.change_details) == 2
        assert pr.change_details[0]["resource_id"] == "a"

    def test_failed_pipeline_result_with_error(self):
        pr = SyncPipelineResult(
            execution_id="ex-fail",
            status="failed",
            errors_count=3,
            error="Connection timed out after 30s",
            processing_time_ms=30_000,
        )
        assert pr.status == "failed"
        assert pr.errors_count == 3
        assert pr.error == "Connection timed out after 30s"

    def test_partial_status_pipeline(self):
        pr = SyncPipelineResult(
            execution_id="ex-partial",
            status="partial",
            items_fetched=100,
            errors_count=1,
            error="One resource could not be fetched",
        )
        assert pr.status == "partial"
        assert pr.items_fetched == 100
        assert pr.errors_count == 1


# ===================================================================
# Cross-dataclass / integration-style tests
# ===================================================================


class TestModelIntegration:
    """Tests that span multiple models to verify they compose correctly."""

    def test_full_sync_lifecycle_composition(self):
        """Verify the full lifecycle: config -> rule -> job -> execution -> changes -> pipeline result."""
        config = SyncConnectorConfig(name="feishu-prod", connector_type="feishu")
        rule = SyncRule(rule_type="cron", cron_expression="0 */6 * * *")
        job = SyncJob(
            connector_config_id=config.id,
            rule_id=rule.id,
            name="feishu-6h",
        )
        ex = SyncExecution(
            job_id=job.id,
            status="completed",
            items_fetched=3,
            items_new=1,
            items_updated=1,
            items_deleted=1,
        )
        changes = [
            ChangeRecord(
                execution_id=ex.id,
                connector_type="feishu",
                resource_id="doc-1",
                change_type="new",
                content_hash="h1",
                content="New document",
            ),
            ChangeRecord(
                execution_id=ex.id,
                connector_type="feishu",
                resource_id="doc-2",
                change_type="updated",
                content_hash="h2",
                previous_hash="h1-old",
                content="Updated document",
            ),
            ChangeRecord(
                execution_id=ex.id,
                connector_type="feishu",
                resource_id="doc-3",
                change_type="deleted",
            ),
        ]
        result = SyncPipelineResult(
            execution_id=ex.id,
            status="completed",
            items_fetched=3,
            items_new=1,
            items_updated=1,
            items_deleted=1,
            processing_time_ms=1200,
            change_details=[asdict(c) for c in changes],
        )
        # pipeline result matches execution
        assert result.execution_id == ex.id
        assert result.items_fetched == ex.items_fetched
        assert result.items_new == ex.items_new
        assert result.items_updated == ex.items_updated
        assert result.items_deleted == ex.items_deleted
        assert len(result.change_details) == 3

    def test_all_models_are_dataclasses(self):
        models = [
            SyncConnectorConfig(),
            SyncRule(),
            SyncJob(),
            SyncExecution(),
            ChangeRecord(),
            SyncResource(),
            SyncConnectionResult(),
            SyncPipelineResult(),
        ]
        for m in models:
            assert is_dataclass(m), f"{type(m).__name__} is not a dataclass"
