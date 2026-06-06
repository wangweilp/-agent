"""SyncStore SQLite CRUD unit tests.

Covers: connectors, rules, jobs, executions, changes,
foreign-key cascade, filtering, pagination, and edge cases.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.adapters.config import Settings
from src.sync.models import (
    ChangeRecord,
    SyncConnectorConfig,
    SyncExecution,
    SyncJob,
    SyncRule,
)
from src.sync.sync_store import SyncStore


# ── helpers ────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


def _make_connector(
    *,
    connector_id: str | None = None,
    name: str = "Test Feishu",
    connector_type: str = "feishu",
    credentials: dict | None = None,
    enabled: bool = True,
) -> SyncConnectorConfig:
    return SyncConnectorConfig(
        id=connector_id or _new_id(),
        name=name,
        connector_type=connector_type,
        credentials=credentials or {"app_id": "cli_xxx", "app_secret": "yyy"},
        enabled=enabled,
    )


def _make_rule(
    *,
    rule_id: str | None = None,
    rule_type: str = "cron",
    cron_expression: str = "0 */6 * * *",
    enabled: bool = True,
    webhook_url: str = "",
    webhook_secret: str = "",
) -> SyncRule:
    return SyncRule(
        id=rule_id or _new_id(),
        rule_type=rule_type,
        cron_expression=cron_expression,
        enabled=enabled,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    )


def _make_job(
    *,
    job_id: str | None = None,
    connector_config_id: str = "",
    rule_id: str = "",
    name: str = "Test Job",
    status: str = "pending",
    enabled: bool = True,
) -> SyncJob:
    return SyncJob(
        id=job_id or _new_id(),
        connector_config_id=connector_config_id,
        rule_id=rule_id,
        name=name,
        status=status,
        enabled=enabled,
    )


def _make_execution(
    *,
    execution_id: str | None = None,
    job_id: str = "",
    status: str = "completed",
    items_fetched: int = 10,
    items_new: int = 3,
    items_updated: int = 2,
    items_deleted: int = 0,
    items_renamed: int = 0,
    memories_created: int = 5,
    errors_count: int = 0,
) -> SyncExecution:
    now = _utcnow()
    return SyncExecution(
        id=execution_id or _new_id(),
        job_id=job_id,
        status=status,
        started_at=now,
        completed_at=now,
        items_fetched=items_fetched,
        items_new=items_new,
        items_updated=items_updated,
        items_deleted=items_deleted,
        items_renamed=items_renamed,
        memories_created=memories_created,
        errors_count=errors_count,
    )


def _make_change(
    *,
    change_id: str | None = None,
    execution_id: str = "",
    connector_type: str = "feishu",
    resource_id: str = "doc_001",
    change_type: str = "new",
    content: str = "Hello world",
    processed: bool = False,
) -> ChangeRecord:
    return ChangeRecord(
        id=change_id or _new_id(),
        execution_id=execution_id,
        connector_type=connector_type,
        resource_id=resource_id,
        change_type=change_type,
        content=content,
        processed=processed,
    )


# ── fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path: Path) -> SyncStore:
    """Create a SyncStore whose database lives in a temp directory."""
    db_dir = tmp_path / "test_sync_data"
    db_dir.mkdir()
    s = Settings(deepseek_api_key="sk-test", sqlite_db_path=str(db_dir))
    store_instance = SyncStore(s)
    yield store_instance
    store_instance.close()


@pytest.fixture
def saved_connector(store: SyncStore) -> SyncConnectorConfig:
    return store.save_connector(_make_connector())


@pytest.fixture
def saved_rule(store: SyncStore) -> SyncRule:
    return store.save_rule(_make_rule())


@pytest.fixture
def saved_job(
    store: SyncStore,
    saved_connector: SyncConnectorConfig,
    saved_rule: SyncRule,
) -> SyncJob:
    return store.save_job(
        _make_job(
            connector_config_id=saved_connector.id,
            rule_id=saved_rule.id,
        )
    )


@pytest.fixture
def saved_execution(
    store: SyncStore, saved_job: SyncJob
) -> SyncExecution:
    return store.save_execution(_make_execution(job_id=saved_job.id))


# ── connector CRUD ─────────────────────────────────────────────────────────

class TestConnectorCRUD:

    def test_save_and_get_connector_roundtrip(
        self, store: SyncStore
    ) -> None:
        c = _make_connector(name="My RSS", connector_type="rss")
        saved = store.save_connector(c)
        assert saved.id == c.id

        got = store.get_connector(c.id)
        assert got is not None
        assert got.name == "My RSS"
        assert got.connector_type == "rss"
        assert got.credentials == {"app_id": "cli_xxx", "app_secret": "yyy"}
        assert got.enabled is True
        assert got.last_sync_status == "never"

    def test_save_connector_upserts_existing(
        self, store: SyncStore, saved_connector: SyncConnectorConfig
    ) -> None:
        saved_connector.name = "Renamed Connector"
        saved_connector.enabled = False
        store.save_connector(saved_connector)

        got = store.get_connector(saved_connector.id)
        assert got is not None
        assert got.name == "Renamed Connector"
        assert got.enabled is False

    def test_get_connector_nonexistent_returns_none(
        self, store: SyncStore
    ) -> None:
        assert store.get_connector("does-not-exist") is None

    def test_list_connectors_returns_all(
        self, store: SyncStore
    ) -> None:
        store.save_connector(_make_connector(name="A"))
        store.save_connector(_make_connector(name="B"))

        results = store.list_connectors()
        assert len(results) >= 2
        names = {c.name for c in results}
        assert "A" in names
        assert "B" in names

    def test_delete_connector_removes_it(
        self, store: SyncStore, saved_connector: SyncConnectorConfig
    ) -> None:
        assert store.delete_connector(saved_connector.id) is True
        assert store.get_connector(saved_connector.id) is None

    def test_delete_nonexistent_connector_returns_false(
        self, store: SyncStore
    ) -> None:
        assert store.delete_connector("does-not-exist") is False

    def test_update_connector_is_save_alias(
        self, store: SyncStore, saved_connector: SyncConnectorConfig
    ) -> None:
        saved_connector.name = "Via Update"
        store.update_connector(saved_connector)

        got = store.get_connector(saved_connector.id)
        assert got is not None
        assert got.name == "Via Update"

    def test_connector_credentials_roundtrip_complex_json(
        self, store: SyncStore
    ) -> None:
        creds = {"token": "abc", "scopes": ["read", "write"], "nested": {"a": 1}}
        c = _make_connector(name="Complex", credentials=creds)
        store.save_connector(c)

        got = store.get_connector(c.id)
        assert got is not None
        assert got.credentials == creds

    def test_connector_etag_hash_version_maps_roundtrip(
        self, store: SyncStore
    ) -> None:
        c = _make_connector(name="Maps")
        c.etag_map = {"res1": "etag_abc"}
        c.hash_map = {"res1": "deadbeef"}
        c.version_map = {"res1": "v2.0"}
        store.save_connector(c)

        got = store.get_connector(c.id)
        assert got is not None
        assert got.etag_map == {"res1": "etag_abc"}
        assert got.hash_map == {"res1": "deadbeef"}
        assert got.version_map == {"res1": "v2.0"}

    def test_connector_disabled_state_persisted(
        self, store: SyncStore
    ) -> None:
        c = _make_connector(name="Off", enabled=False)
        store.save_connector(c)

        got = store.get_connector(c.id)
        assert got is not None
        assert got.enabled is False

        results = store.list_connectors()
        assert any(not cc.enabled and cc.name == "Off" for cc in results)

    def test_connector_last_sync_time_roundtrip(
        self, store: SyncStore
    ) -> None:
        ts = datetime(2025, 6, 1, 14, 30, 0, tzinfo=timezone.utc)
        c = _make_connector(name="Timed")
        c.last_sync_time = ts
        c.last_sync_status = "success"
        store.save_connector(c)

        got = store.get_connector(c.id)
        assert got is not None
        assert got.last_sync_time == ts
        assert got.last_sync_status == "success"


# ── rule CRUD ──────────────────────────────────────────────────────────────

class TestRuleCRUD:

    def test_save_and_get_rule_roundtrip(self, store: SyncStore) -> None:
        r = _make_rule(rule_type="manual", cron_expression="")
        saved = store.save_rule(r)
        assert saved.id == r.id

        got = store.get_rule(r.id)
        assert got is not None
        assert got.rule_type == "manual"
        assert got.cron_expression == ""
        assert got.enabled is True

    def test_save_rule_upserts(self, store: SyncStore) -> None:
        r = _make_rule(cron_expression="0 0 * * *")
        store.save_rule(r)

        r.cron_expression = "*/30 * * * *"
        r.enabled = False
        store.save_rule(r)

        got = store.get_rule(r.id)
        assert got is not None
        assert got.cron_expression == "*/30 * * * *"
        assert got.enabled is False

    def test_get_rule_nonexistent_returns_none(
        self, store: SyncStore
    ) -> None:
        assert store.get_rule("no-rule") is None

    def test_delete_rule_removes_it(
        self, store: SyncStore, saved_rule: SyncRule
    ) -> None:
        assert store.delete_rule(saved_rule.id) is True
        assert store.get_rule(saved_rule.id) is None

    def test_delete_nonexistent_rule_returns_false(
        self, store: SyncStore
    ) -> None:
        assert store.delete_rule("no-rule") is False

    def test_rule_webhook_fields_roundtrip(self, store: SyncStore) -> None:
        r = _make_rule(
            rule_type="realtime",
            cron_expression="",
            webhook_url="https://example.com/hook",
            webhook_secret="shh-secret-123",
        )
        store.save_rule(r)

        got = store.get_rule(r.id)
        assert got is not None
        assert got.webhook_url == "https://example.com/hook"
        assert got.webhook_secret == "shh-secret-123"

    def test_get_rule_for_job_returns_correct_rule(
        self, store: SyncStore, saved_job: SyncJob, saved_rule: SyncRule
    ) -> None:
        rule = store.get_rule_for_job(saved_job.id)
        assert rule is not None
        assert rule.id == saved_rule.id
        assert rule.rule_type == saved_rule.rule_type

    def test_get_rule_for_nonexistent_job_returns_none(
        self, store: SyncStore
    ) -> None:
        assert store.get_rule_for_job("no-job") is None


# ── job CRUD ───────────────────────────────────────────────────────────────

class TestJobCRUD:

    def test_save_and_get_job_roundtrip(
        self,
        store: SyncStore,
        saved_connector: SyncConnectorConfig,
        saved_rule: SyncRule,
    ) -> None:
        j = _make_job(
            connector_config_id=saved_connector.id,
            rule_id=saved_rule.id,
            name="My Sync",
        )
        saved = store.save_job(j)
        assert saved.id == j.id

        got = store.get_job(j.id)
        assert got is not None
        assert got.name == "My Sync"
        assert got.connector_config_id == saved_connector.id
        assert got.rule_id == saved_rule.id
        assert got.status == "pending"
        assert got.enabled is True

    def test_save_job_upserts(self, store: SyncStore, saved_job: SyncJob) -> None:
        saved_job.status = "running"
        saved_job.name = "Updated Name"
        store.save_job(saved_job)

        got = store.get_job(saved_job.id)
        assert got is not None
        assert got.status == "running"
        assert got.name == "Updated Name"

    def test_get_job_nonexistent_returns_none(
        self, store: SyncStore
    ) -> None:
        assert store.get_job("no-job") is None

    def test_delete_job_removes_it(
        self, store: SyncStore, saved_job: SyncJob
    ) -> None:
        assert store.delete_job(saved_job.id) is True
        assert store.get_job(saved_job.id) is None

    def test_delete_nonexistent_job_returns_false(
        self, store: SyncStore
    ) -> None:
        assert store.delete_job("no-job") is False

    def test_list_jobs_pagination_and_filtering(
        self,
        store: SyncStore,
        saved_connector: SyncConnectorConfig,
        saved_rule: SyncRule,
    ) -> None:
        # Create 5 jobs, some disabled
        for i in range(3):
            j = _make_job(
                connector_config_id=saved_connector.id,
                rule_id=saved_rule.id,
                name=f"Job {i}",
                enabled=(i != 2),  # third one disabled
            )
            store.save_job(j)

        all_jobs = store.list_jobs()
        assert len(all_jobs) >= 3

        enabled = store.list_jobs(enabled_only=True)
        for ej in enabled:
            assert ej.enabled is True

    def test_list_jobs_enabled_only_excludes_cancelled(
        self,
        store: SyncStore,
        saved_connector: SyncConnectorConfig,
        saved_rule: SyncRule,
    ) -> None:
        j = _make_job(
            connector_config_id=saved_connector.id,
            rule_id=saved_rule.id,
            name="Cancelled",
            status="cancelled",
            enabled=True,
        )
        store.save_job(j)

        enabled = store.list_jobs(enabled_only=True)
        assert not any(ej.id == j.id for ej in enabled)

    def test_update_job_is_save_alias(
        self, store: SyncStore, saved_job: SyncJob
    ) -> None:
        saved_job.name = "Via Update"
        store.update_job(saved_job)

        got = store.get_job(saved_job.id)
        assert got is not None
        assert got.name == "Via Update"


# ── execution CRUD ─────────────────────────────────────────────────────────

class TestExecutionCRUD:

    def test_save_and_get_execution_roundtrip(
        self, store: SyncStore, saved_job: SyncJob
    ) -> None:
        started = datetime(2025, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
        completed = datetime(2025, 6, 1, 8, 0, 5, tzinfo=timezone.utc)
        e = SyncExecution(
            id=_new_id(),
            job_id=saved_job.id,
            status="completed",
            started_at=started,
            completed_at=completed,
            items_fetched=100,
            items_new=40,
            items_updated=20,
            items_deleted=5,
            items_renamed=3,
            memories_created=60,
            errors_count=0,
            elapsed_ms=5200,
        )
        store.save_execution(e)

        got = store.get_execution(e.id)
        assert got is not None
        assert got.job_id == saved_job.id
        assert got.status == "completed"
        assert got.items_fetched == 100
        assert got.items_new == 40
        assert got.items_updated == 20
        assert got.items_deleted == 5
        assert got.items_renamed == 3
        assert got.memories_created == 60
        assert got.errors_count == 0
        assert got.elapsed_ms == 5200
        assert got.started_at == started
        assert got.completed_at == completed

    def test_save_execution_upserts(
        self, store: SyncStore, saved_execution: SyncExecution
    ) -> None:
        saved_execution.status = "failed"
        saved_execution.errors_count = 1
        saved_execution.error = "network timeout"
        store.save_execution(saved_execution)

        got = store.get_execution(saved_execution.id)
        assert got is not None
        assert got.status == "failed"
        assert got.errors_count == 1
        assert got.error == "network timeout"

    def test_get_execution_nonexistent_returns_none(
        self, store: SyncStore
    ) -> None:
        assert store.get_execution("no-exec") is None

    def test_list_executions_by_job_id(
        self, store: SyncStore, saved_execution: SyncExecution
    ) -> None:
        results = store.list_executions(
            job_id=saved_execution.job_id, limit=10
        )
        assert len(results) >= 1
        assert any(e.id == saved_execution.id for e in results)

    def test_list_executions_by_job_id_empty_for_unknown_job(
        self, store: SyncStore
    ) -> None:
        assert store.list_executions(job_id="no-job") == []

    def test_list_executions_by_connector_id(
        self,
        store: SyncStore,
        saved_connector: SyncConnectorConfig,
        saved_execution: SyncExecution,
    ) -> None:
        results = store.list_executions(
            connector_id=saved_connector.id, limit=10
        )
        assert len(results) >= 1
        assert any(e.id == saved_execution.id for e in results)

    def test_list_executions_by_connector_id_empty_for_unknown(
        self, store: SyncStore
    ) -> None:
        assert store.list_executions(connector_id="unknown-connector") == []

    def test_list_executions_limit_respected(
        self, store: SyncStore, saved_job: SyncJob
    ) -> None:
        for i in range(5):
            store.save_execution(_make_execution(job_id=saved_job.id))

        assert len(store.list_executions(job_id=saved_job.id, limit=3)) == 3

    def test_list_executions_default_limit(
        self, store: SyncStore
    ) -> None:
        results = store.list_executions()
        assert len(results) <= 50

    def test_execution_nullable_fields_handled(
        self, store: SyncStore, saved_job: SyncJob
    ) -> None:
        e = SyncExecution(
            id=_new_id(),
            job_id=saved_job.id,
            status="pending",
            started_at=None,
            completed_at=None,
            items_fetched=0,
            items_new=0,
            items_updated=0,
            items_deleted=0,
            items_renamed=0,
            memories_created=0,
            errors_count=0,
            error=None,
            elapsed_ms=0,
        )
        store.save_execution(e)

        got = store.get_execution(e.id)
        assert got is not None
        assert got.started_at is None
        assert got.completed_at is None
        assert got.error is None
        assert got.items_fetched == 0


# ── change CRUD ────────────────────────────────────────────────────────────

class TestChangeCRUD:

    def test_save_and_list_changes(
        self, store: SyncStore, saved_execution: SyncExecution
    ) -> None:
        ch = _make_change(execution_id=saved_execution.id, change_type="new")
        store.save_change(ch)

        results = store.list_changes(saved_execution.id)
        assert len(results) == 1
        assert results[0].id == ch.id
        assert results[0].change_type == "new"
        assert results[0].resource_id == "doc_001"
        assert results[0].content == "Hello world"

    def test_save_change_upserts(
        self, store: SyncStore, saved_execution: SyncExecution
    ) -> None:
        ch = _make_change(execution_id=saved_execution.id, processed=False)
        store.save_change(ch)

        ch.processed = True
        ch.process_error = None
        store.save_change(ch)

        results = store.list_changes(saved_execution.id)
        assert len(results) == 1
        assert results[0].processed is True

    def test_list_changes_empty_for_unknown_execution(
        self, store: SyncStore
    ) -> None:
        assert store.list_changes("no-exec") == []

    def test_list_changes_returns_multiple_ordered_by_detected_at(
        self, store: SyncStore, saved_execution: SyncExecution
    ) -> None:
        ch1 = _make_change(
            execution_id=saved_execution.id,
            resource_id="doc_a",
            change_type="new",
        )
        ch2 = _make_change(
            execution_id=saved_execution.id,
            resource_id="doc_b",
            change_type="updated",
        )
        store.save_change(ch1)
        store.save_change(ch2)

        results = store.list_changes(saved_execution.id)
        assert len(results) == 2
        ids = [r.id for r in results]
        assert ch1.id in ids
        assert ch2.id in ids

    def test_change_metadata_json_roundtrip(
        self, store: SyncStore, saved_execution: SyncExecution
    ) -> None:
        ch = _make_change(execution_id=saved_execution.id)
        ch.metadata = {"size": 1024, "tags": ["a", "b"]}
        store.save_change(ch)

        results = store.list_changes(saved_execution.id)
        assert len(results) == 1
        assert results[0].metadata == {"size": 1024, "tags": ["a", "b"]}

    def test_change_content_long_truncated_to_preview(
        self, store: SyncStore, saved_execution: SyncExecution
    ) -> None:
        long_content = "x" * 600
        ch = _make_change(
            execution_id=saved_execution.id,
            content=long_content,
        )
        store.save_change(ch)

        results = store.list_changes(saved_execution.id)
        assert len(results) == 1
        # Preview is truncated to 500 characters
        assert len(results[0].content) == 500
        assert results[0].content == long_content[:500]

    def test_change_processed_and_error_fields(
        self, store: SyncStore, saved_execution: SyncExecution
    ) -> None:
        ch = _make_change(execution_id=saved_execution.id)
        ch.processed = True
        ch.process_error = "encoding error"
        store.save_change(ch)

        results = store.list_changes(saved_execution.id)
        assert len(results) == 1
        assert results[0].processed is True
        assert results[0].process_error == "encoding error"

    def test_change_content_hash_fields(
        self, store: SyncStore, saved_execution: SyncExecution
    ) -> None:
        ch = _make_change(execution_id=saved_execution.id)
        ch.content_hash = "abc123"
        ch.previous_hash = "def456"
        store.save_change(ch)

        results = store.list_changes(saved_execution.id)
        assert len(results) == 1
        assert results[0].content_hash == "abc123"
        assert results[0].previous_hash == "def456"

    def test_multiple_executions_changes_isolated(
        self,
        store: SyncStore,
        saved_job: SyncJob,
    ) -> None:
        e1 = store.save_execution(_make_execution(job_id=saved_job.id))
        e2 = store.save_execution(_make_execution(job_id=saved_job.id))

        store.save_change(_make_change(execution_id=e1.id, resource_id="r1"))
        store.save_change(_make_change(execution_id=e2.id, resource_id="r2"))

        assert len(store.list_changes(e1.id)) == 1
        assert len(store.list_changes(e2.id)) == 1
        assert store.list_changes(e1.id)[0].resource_id == "r1"
        assert store.list_changes(e2.id)[0].resource_id == "r2"


# ── foreign-key cascade ────────────────────────────────────────────────────

class TestForeignKeyCascade:

    def test_delete_connector_cascades_to_jobs(
        self,
        store: SyncStore,
        saved_connector: SyncConnectorConfig,
        saved_rule: SyncRule,
    ) -> None:
        j = store.save_job(
            _make_job(
                connector_config_id=saved_connector.id,
                rule_id=saved_rule.id,
            )
        )
        assert store.get_job(j.id) is not None

        store.delete_connector(saved_connector.id)
        # Job referencing deleted connector should be gone
        assert store.get_job(j.id) is None

    def test_delete_connector_cascades_to_jobs_then_executions_then_changes(
        self,
        store: SyncStore,
        saved_connector: SyncConnectorConfig,
        saved_rule: SyncRule,
    ) -> None:
        j = store.save_job(
            _make_job(
                connector_config_id=saved_connector.id,
                rule_id=saved_rule.id,
            )
        )
        e = store.save_execution(_make_execution(job_id=j.id))
        ch = store.save_change(_make_change(execution_id=e.id))

        store.delete_connector(saved_connector.id)

        assert store.get_job(j.id) is None
        assert store.get_execution(e.id) is None
        assert store.list_changes(e.id) == []

    def test_delete_rule_cascades_to_jobs(
        self,
        store: SyncStore,
        saved_connector: SyncConnectorConfig,
        saved_rule: SyncRule,
    ) -> None:
        j = store.save_job(
            _make_job(
                connector_config_id=saved_connector.id,
                rule_id=saved_rule.id,
            )
        )
        assert store.get_job(j.id) is not None

        store.delete_rule(saved_rule.id)
        assert store.get_job(j.id) is None

    def test_delete_job_cascades_to_executions(
        self, store: SyncStore, saved_job: SyncJob
    ) -> None:
        e = store.save_execution(_make_execution(job_id=saved_job.id))
        assert store.get_execution(e.id) is not None

        store.delete_job(saved_job.id)
        assert store.get_execution(e.id) is None

    def test_delete_job_cascades_to_executions_then_changes(
        self, store: SyncStore, saved_job: SyncJob
    ) -> None:
        e = store.save_execution(_make_execution(job_id=saved_job.id))
        ch = store.save_change(_make_change(execution_id=e.id))

        store.delete_job(saved_job.id)

        assert store.get_execution(e.id) is None
        assert store.list_changes(e.id) == []

    def test_delete_execution_cascades_to_changes(
        self, store: SyncStore, saved_execution: SyncExecution
    ) -> None:
        ch = store.save_change(
            _make_change(execution_id=saved_execution.id)
        )
        assert len(store.list_changes(saved_execution.id)) == 1

        # Execution delete via direct SQL since there's no delete_execution method
        with store._lock:
            conn = store._get_conn()
            conn.execute(
                "DELETE FROM sync_executions WHERE id = ?",
                (saved_execution.id,),
            )
            conn.commit()

        assert store.get_execution(saved_execution.id) is None
        assert store.list_changes(saved_execution.id) == []

    def test_delete_connector_does_not_affect_other_connectors(
        self,
        store: SyncStore,
        saved_connector: SyncConnectorConfig,
        saved_rule: SyncRule,
    ) -> None:
        c2 = store.save_connector(_make_connector(name="Other"))
        j2 = store.save_job(
            _make_job(
                connector_config_id=c2.id,
                rule_id=saved_rule.id,
                name="Other Job",
            )
        )

        store.delete_connector(saved_connector.id)

        # c2 and its job should survive
        assert store.get_connector(c2.id) is not None
        assert store.get_job(j2.id) is not None


# ── edge cases ─────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_empty_store_lists_return_empty(self, store: SyncStore) -> None:
        assert store.list_connectors() == []
        # No list_rules method on SyncStore
        assert store.list_jobs() == []
        assert store.list_executions() == []

    def test_many_connectors_list_all(self, store: SyncStore) -> None:
        for i in range(20):
            store.save_connector(_make_connector(name=f"Connector {i}"))
        assert len(store.list_connectors()) == 20

    def test_connector_idempotent_save(self, store: SyncStore) -> None:
        c = _make_connector(name="Stable")
        s1 = store.save_connector(c)
        s2 = store.save_connector(c)
        assert s1.id == s2.id
        assert len(store.list_connectors()) == 1

    def test_job_with_different_statuses(
        self,
        store: SyncStore,
        saved_connector: SyncConnectorConfig,
        saved_rule: SyncRule,
    ) -> None:
        for status in ("pending", "running", "completed", "failed", "cancelled"):
            j = _make_job(
                connector_config_id=saved_connector.id,
                rule_id=saved_rule.id,
                name=f"Job {status}",
                status=status,
            )
            store.save_job(j)
            got = store.get_job(j.id)
            assert got is not None
            assert got.status == status

    def test_execution_partial_status(
        self, store: SyncStore, saved_job: SyncJob
    ) -> None:
        e = _make_execution(job_id=saved_job.id, status="partial")
        store.save_execution(e)

        got = store.get_execution(e.id)
        assert got is not None
        assert got.status == "partial"

    def test_change_all_types(
        self, store: SyncStore, saved_execution: SyncExecution
    ) -> None:
        for ct in ("new", "updated", "deleted", "renamed"):
            ch = _make_change(
                execution_id=saved_execution.id,
                resource_id=f"res_{ct}",
                change_type=ct,
            )
            store.save_change(ch)

        results = store.list_changes(saved_execution.id)
        assert len(results) == 4
        types = {r.change_type for r in results}
        assert types == {"new", "updated", "deleted", "renamed"}

    def test_close_called_twice_does_not_raise(
        self, store: SyncStore
    ) -> None:
        store.close()
        store.close()  # should be safe

    def test_thread_safety_basic(self, store: SyncStore) -> None:
        """Bulk insert from thread — verifies the lock does not deadlock."""
        import threading

        def worker(start: int) -> None:
            for i in range(start, start + 10):
                store.save_connector(_make_connector(name=f"T{i}"))

        threads = [
            threading.Thread(target=worker, args=(base,))
            for base in (0, 10, 20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        connectors = store.list_connectors()
        assert len(connectors) == 30
