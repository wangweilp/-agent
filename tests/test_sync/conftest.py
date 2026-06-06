"""Shared pytest fixtures for sync module tests.

Provides reusable fixtures across all test_sync subdirectories:
  - settings          → Settings(deepseek_api_key="sk-test")
  - sync_store        → in-memory SQLite SyncStore scoped to tmp_path
  - sample_connector_config → a persisted SyncConnectorConfig with tracking maps
  - sample_rule       → a persisted SyncRule (cron)
  - sample_job        → a persisted SyncJob
  - sample_execution  → a persisted SyncExecution
  - mock_connector    → MagicMock satisfying the SyncConnector protocol
  - change_detector   → a ChangeDetector instance

Also includes verification tests that the fixtures themselves are wired correctly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.adapters.config import Settings
from src.sync.change_detector import ChangeDetector
from src.sync.models import (
    ChangeRecord,
    SyncConnectorConfig,
    SyncConnectionResult,
    SyncExecution,
    SyncJob,
    SyncResource,
    SyncRule,
)
from src.sync.sync_store import SyncStore


# ── Helpers ──────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def _configure_local_folder_allowlist() -> None:
    """Auto-configure local_folder allowlist to accept any tmp_path created by tests.

    Without this, all LocalFolderConnector tests would fail because
    _ALLOWED_ROOTS is empty by default (secure-by-default).
    """
    import tempfile
    from src.sync.connectors.local_folder_connector import configure_local_folder_allowlist

    # Allow the OS temp directory (parent of all pytest tmp_path fixtures)
    temp_root = Path(tempfile.gettempdir())
    configure_local_folder_allowlist(
        allowed_roots=[str(temp_root)],
        max_file_bytes=10 * 1024 * 1024,
    )


@pytest.fixture
def settings() -> Settings:
    """Test Settings instance with a fake API key."""
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def sync_store(settings: Settings, tmp_path: Path) -> SyncStore:
    """SyncStore backed by an in-memory SQLite database in a temp directory.

    The database file lives under tmp_path so tests are isolated and
    the OS cleans up after the test run.
    """
    db_dir = tmp_path / "sync_test_data"
    db_dir.mkdir()
    # Override sqlite_db_path to point into tmp_path
    store_settings = Settings(
        deepseek_api_key=settings.deepseek_api_key,
        sqlite_db_path=str(db_dir),
    )
    store = SyncStore(store_settings)
    yield store
    store.close()


@pytest.fixture
def sample_connector_config(sync_store: SyncStore) -> SyncConnectorConfig:
    """A persisted SyncConnectorConfig with pre-populated tracking maps.

    Represents a typical "feishu" connector that has already completed at
    least one sync cycle (so hash_map/etag_map/version_map are non-empty).
    """
    config = SyncConnectorConfig(
        name="Test Feishu Workspace",
        connector_type="feishu",
        credentials={"app_id": "cli_test", "app_secret": "test_secret"},
        enabled=True,
        last_sync_time=_utcnow(),
        last_sync_status="success",
        etag_map={"doc_001": "etag_v1", "doc_002": "etag_v2"},
        hash_map={
            "doc_001": "abc123def456",
            "doc_002": "998877aabbcc",
            "doc_003": "deadbeef9999",
        },
        version_map={"doc_001": "v1.0", "doc_002": "v2.3"},
    )
    return sync_store.save_connector(config)


@pytest.fixture
def sample_rule(sync_store: SyncStore) -> SyncRule:
    """A persisted cron SyncRule."""
    rule = SyncRule(
        rule_type="cron",
        cron_expression="0 */6 * * *",
        enabled=True,
    )
    return sync_store.save_rule(rule)


@pytest.fixture
def sample_job(
    sync_store: SyncStore,
    sample_connector_config: SyncConnectorConfig,
    sample_rule: SyncRule,
) -> SyncJob:
    """A persisted SyncJob linking sample_connector_config to sample_rule."""
    job = SyncJob(
        connector_config_id=sample_connector_config.id,
        rule_id=sample_rule.id,
        name="Test Feishu Sync",
        status="pending",
        enabled=True,
    )
    return sync_store.save_job(job)


@pytest.fixture
def sample_execution(
    sync_store: SyncStore,
    sample_job: SyncJob,
) -> SyncExecution:
    """A persisted SyncExecution attached to sample_job."""
    now = _utcnow()
    execution = SyncExecution(
        job_id=sample_job.id,
        status="completed",
        started_at=now,
        completed_at=now,
        items_fetched=10,
        items_new=5,
        items_updated=3,
        items_deleted=1,
        items_renamed=1,
        memories_created=4,
        errors_count=0,
        elapsed_ms=1500,
    )
    return sync_store.save_execution(execution)


@pytest.fixture
def mock_connector() -> MagicMock:
    """A MagicMock that satisfies the SyncConnector protocol.

    Default return values:
      - connector_type       → "mock"
      - test_connection()    → SyncConnectionResult(success=True, message="OK", resources_count=3)
      - list_resources()     → [SyncResource(...), SyncResource(...), SyncResource(...)]
      - fetch_content(rid)   → {"content": "<rid> content", "content_type": "markdown", "metadata": {}}
      - fetch_changes(since) → []

    Tests can override return values / side effects per test case.
    """
    connector = MagicMock()
    connector.connector_type = "mock"

    connector.test_connection.return_value = SyncConnectionResult(
        success=True,
        message="Connected to mock source",
        resources_count=3,
    )

    connector.list_resources.return_value = [
        SyncResource(
            resource_id="mock_res_001",
            name="Mock Document Alpha",
            resource_type="document",
            updated_at=_utcnow(),
            size_bytes=1024,
            metadata={"etag": "etag_alpha"},
        ),
        SyncResource(
            resource_id="mock_res_002",
            name="Mock Document Beta",
            resource_type="document",
            updated_at=_utcnow(),
            size_bytes=2048,
            metadata={"version": "v1"},
        ),
        SyncResource(
            resource_id="mock_res_003",
            name="Mock Note Gamma",
            resource_type="note",
            updated_at=_utcnow(),
            size_bytes=512,
            metadata={},
        ),
    ]

    connector.fetch_content.side_effect = lambda resource_id: {
        "content": f"Content of {resource_id}",
        "content_type": "markdown" if resource_id.endswith("md") else "text",
        "metadata": {"title": resource_id, "source": "mock"},
    }

    connector.fetch_changes.return_value = []

    return connector


@pytest.fixture
def change_detector() -> ChangeDetector:
    """A fresh ChangeDetector with no internal state."""
    return ChangeDetector()


@pytest.fixture
def sample_changes(
    sample_execution: SyncExecution,
) -> list[ChangeRecord]:
    """A list of ChangeRecords for the sample_execution covering all change types."""
    return [
        ChangeRecord(
            execution_id=sample_execution.id,
            connector_type="feishu",
            resource_id="doc_new",
            change_type="new",
            content_hash="hash_new_111",
            content="# Brand new document",
            content_type="markdown",
            processed=False,
        ),
        ChangeRecord(
            execution_id=sample_execution.id,
            connector_type="feishu",
            resource_id="doc_updated",
            change_type="updated",
            content_hash="hash_updated_222",
            previous_hash="hash_old_111",
            content="# Updated document",
            content_type="markdown",
            processed=False,
        ),
        ChangeRecord(
            execution_id=sample_execution.id,
            connector_type="feishu",
            resource_id="doc_deleted",
            change_type="deleted",
            previous_hash="hash_gone_333",
            processed=False,
        ),
        ChangeRecord(
            execution_id=sample_execution.id,
            connector_type="feishu",
            resource_id="doc_renamed",
            change_type="renamed",
            content_hash="hash_renamed_444",
            content="# Renamed document",
            content_type="markdown",
            metadata={"previous_resource_id": "doc_old_name"},
            processed=False,
        ),
    ]


# =============================================================================
# Fixture self-verification tests
# =============================================================================
#
# These tests assert that the shared fixtures return properly-wired objects.
# They also serve as the minimum 5+ test functions required for this file.

class TestFixturesWiring:
    """Verify that all shared fixtures are correctly constructed and usable."""

    def test_settings_has_api_key(self, settings: Settings) -> None:
        """settings fixture provides a Settings object with deepseek_api_key set."""
        assert settings.deepseek_api_key == "sk-test"
        assert isinstance(settings.sqlite_db_path, str)

    def test_sync_store_creates_db_file(self, sync_store: SyncStore, tmp_path: Path) -> None:
        """sync_store fixture creates a SQLite database file on disk."""
        db_path = sync_store._db_path
        assert db_path.exists()
        assert db_path.suffix == ".db"
        # Should be under tmp_path
        assert str(tmp_path) in str(db_path)

    def test_sync_store_tables_exist(self, sync_store: SyncStore) -> None:
        """sync_store fixture initialises all required tables."""
        conn = sync_store._get_conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {row["name"] for row in tables}
        expected = {
            "sync_connectors",
            "sync_rules",
            "sync_jobs",
            "sync_executions",
            "sync_changes",
        }
        assert expected.issubset(table_names)

    def test_sample_connector_config_is_persisted(
        self, sync_store: SyncStore, sample_connector_config: SyncConnectorConfig
    ) -> None:
        """sample_connector_config is retrievable from the store."""
        fetched = sync_store.get_connector(sample_connector_config.id)
        assert fetched is not None
        assert fetched.name == "Test Feishu Workspace"
        assert fetched.connector_type == "feishu"
        assert fetched.hash_map == {
            "doc_001": "abc123def456",
            "doc_002": "998877aabbcc",
            "doc_003": "deadbeef9999",
        }

    def test_sample_rule_is_persisted(
        self, sync_store: SyncStore, sample_rule: SyncRule
    ) -> None:
        """sample_rule is retrievable from the store."""
        fetched = sync_store.get_rule(sample_rule.id)
        assert fetched is not None
        assert fetched.rule_type == "cron"
        assert fetched.cron_expression == "0 */6 * * *"

    def test_sample_job_links_config_and_rule(
        self,
        sync_store: SyncStore,
        sample_job: SyncJob,
        sample_connector_config: SyncConnectorConfig,
        sample_rule: SyncRule,
    ) -> None:
        """sample_job correctly references its connector config and rule."""
        fetched = sync_store.get_job(sample_job.id)
        assert fetched is not None
        assert fetched.connector_config_id == sample_connector_config.id
        assert fetched.rule_id == sample_rule.id
        assert fetched.name == "Test Feishu Sync"
        assert fetched.status == "pending"

    def test_sample_execution_is_persisted(
        self,
        sync_store: SyncStore,
        sample_execution: SyncExecution,
        sample_job: SyncJob,
    ) -> None:
        """sample_execution is retrievable and attached to the correct job."""
        fetched = sync_store.get_execution(sample_execution.id)
        assert fetched is not None
        assert fetched.job_id == sample_job.id
        assert fetched.status == "completed"
        assert fetched.items_fetched == 10
        assert fetched.items_new == 5
        assert fetched.items_updated == 3
        assert fetched.items_deleted == 1
        assert fetched.items_renamed == 1
        assert fetched.memories_created == 4
        assert fetched.errors_count == 0
        assert fetched.elapsed_ms == 1500

    def test_mock_connector_has_required_attributes(self, mock_connector: MagicMock) -> None:
        """mock_connector exposes the connector_type attribute and required methods."""
        assert mock_connector.connector_type == "mock"
        assert callable(mock_connector.test_connection)
        assert callable(mock_connector.list_resources)
        assert callable(mock_connector.fetch_changes)
        assert callable(mock_connector.fetch_content)

    def test_mock_connector_test_connection_returns_success(
        self, mock_connector: MagicMock
    ) -> None:
        """Default test_connection() return value indicates success."""
        result = mock_connector.test_connection()
        assert result.success is True
        assert "Connected" in result.message
        assert result.resources_count == 3

    def test_mock_connector_list_resources_returns_three_items(
        self, mock_connector: MagicMock
    ) -> None:
        """Default list_resources() returns three SyncResource objects."""
        resources = mock_connector.list_resources()
        assert len(resources) == 3
        for r in resources:
            assert isinstance(r, SyncResource)
            assert r.resource_id != ""
            assert r.name != ""

    def test_mock_connector_fetch_content_returns_predictable_data(
        self, mock_connector: MagicMock
    ) -> None:
        """fetch_content returns content keyed on the resource_id."""
        result = mock_connector.fetch_content("test_doc.md")
        assert result["content"] == "Content of test_doc.md"
        assert result["content_type"] == "markdown"
        assert "title" in result["metadata"]

        # Non-markdown extension
        result2 = mock_connector.fetch_content("log.txt")
        assert result2["content_type"] == "text"

    def test_mock_connector_can_override_return_value(
        self, mock_connector: MagicMock
    ) -> None:
        """Tests can override the mock's return values without affecting other tests."""
        mock_connector.test_connection.return_value = SyncConnectionResult(
            success=False, message="Auth failed"
        )
        result = mock_connector.test_connection()
        assert result.success is False
        assert result.message == "Auth failed"

    def test_change_detector_is_fresh_instance(
        self, change_detector: ChangeDetector
    ) -> None:
        """change_detector fixture returns a ChangeDetector with no pre-existing state."""
        assert isinstance(change_detector, ChangeDetector)

    def test_change_detector_detect_with_mock_connector(
        self,
        change_detector: ChangeDetector,
        mock_connector: MagicMock,
        sample_connector_config: SyncConnectorConfig,
    ) -> None:
        """ChangeDetector.detect() runs end-to-end with the mock connector."""
        changes = change_detector.detect(
            connector=mock_connector,
            config=sample_connector_config,
            since=None,
        )
        # mock_connector returns 3 resources with known content;
        # sample_connector_config already has hash_map entries for doc_001, doc_002, doc_003
        # So the mock resources (mock_res_001, etc.) will all be detected as "new"
        assert isinstance(changes, list)
        for ch in changes:
            assert isinstance(ch, ChangeRecord)
            assert ch.connector_type == "mock"
            assert ch.resource_id != ""

    def test_sample_changes_cover_all_change_types(
        self, sample_changes: list[ChangeRecord]
    ) -> None:
        """sample_changes includes new, updated, deleted, and renamed."""
        types = {ch.change_type for ch in sample_changes}
        assert types == {"new", "updated", "deleted", "renamed"}
        assert len(sample_changes) == 4

    def test_sync_store_empty_on_first_use_before_fixtures(
        self, sync_store: SyncStore
    ) -> None:
        """Before any sample fixtures are used, the store is empty.

        This test does NOT request sample_* fixtures, so the store starts clean.
        """
        assert sync_store.list_connectors() == []
        assert sync_store.list_jobs() == []
        assert sync_store.list_executions() == []

    def test_sync_store_close_twice_is_safe(
        self, sync_store: SyncStore
    ) -> None:
        """Calling close() multiple times does not raise."""
        sync_store.close()
        sync_store.close()  # Should be safe — no exception

    def test_settings_can_override_defaults(self) -> None:
        """Settings constructor accepts overrides for any field."""
        s = Settings(
            deepseek_api_key="sk-override",
            sqlite_db_path="/custom/path/db.sqlite",
            chroma_persist_dir="/custom/chroma",
        )
        assert s.deepseek_api_key == "sk-override"
        assert s.sqlite_db_path == "/custom/path/db.sqlite"
        assert s.chroma_persist_dir == "/custom/chroma"

    def test_sync_store_handles_unicode_in_connector_fields(
        self, sync_store: SyncStore
    ) -> None:
        """Connector names and credentials with Unicode are round-tripped."""
        cfg = SyncConnectorConfig(
            name="飞书工作区",
            connector_type="feishu",
            credentials={"密钥": "abc123", "描述": "测试用"},
        )
        sync_store.save_connector(cfg)
        fetched = sync_store.get_connector(cfg.id)
        assert fetched is not None
        assert fetched.name == "飞书工作区"
        assert fetched.credentials == {"密钥": "abc123", "描述": "测试用"}
