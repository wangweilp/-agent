"""Integration tests for SyncPipeline — full pipeline with mock connector.

Covers:
  - Connection failure aborts early
  - Empty changes yield clean completion
  - New content flows through the full pipeline
  - Partial failure: individual resource error continues others
  - Deleted changes handled without import pipeline
  - Import pipeline failure results in partial status
  - Empty/whitespace-only content is skipped
  - Mixed change types (new, updated, deleted, renamed)
  - Pipeline crash (unexpected exception) returns failed
  - Edge cases: no content after fetch, all changes filtered out
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.core.import_pipeline import ImportMemoryPipeline, ImportPipelineResult
from src.sync.connector_base import BaseSyncConnector
from src.sync.models import (
    ChangeRecord,
    SyncConnectorConfig,
    SyncConnectionResult,
    SyncExecution,
    SyncPipelineResult,
)
from src.sync.sync_pipeline import SyncPipeline


# ── Helpers ──────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return str(uuid.uuid4())


def _make_config(**overrides) -> SyncConnectorConfig:
    kwargs = {
        "name": "test-connector",
        "connector_type": "mock",
        "credentials": {"token": "abc"},
        "last_sync_time": None,
    }
    kwargs.update(overrides)
    return SyncConnectorConfig(**kwargs)


def _make_execution(**overrides) -> SyncExecution:
    kwargs = {
        "job_id": _new_id(),
        "status": "pending",
    }
    kwargs.update(overrides)
    return SyncExecution(**kwargs)


def _make_change_record(**overrides) -> ChangeRecord:
    kwargs = {
        "connector_type": "mock",
        "resource_id": f"res-{_new_id()[:8]}",
        "change_type": "new",
        "content_hash": "abc123",
        "content": "Hello world content for testing.",
        "content_type": "text/plain",
        "metadata": {"title": "Test Resource", "file_size": 1024},
    }
    kwargs.update(overrides)
    return ChangeRecord(**kwargs)


def _make_success_connection(resources_count: int = 10) -> SyncConnectionResult:
    return SyncConnectionResult(
        success=True,
        message="OK",
        resources_count=resources_count,
    )


def _make_failed_connection(message: str = "auth error") -> SyncConnectionResult:
    return SyncConnectionResult(
        success=False,
        message=message,
        resources_count=0,
    )


def _make_import_result(
    source: str = "sync:mock:test-connector",
    title: str = "Sync: test-connector",
    chunks_count: int = 2,
    memories_created: int = 10,
    status: str = "completed",
) -> ImportPipelineResult:
    return ImportPipelineResult(
        source=source,
        title=title,
        chunks_count=chunks_count,
        memories_created=memories_created,
        tasks_enqueued=memories_created * 5,
        entities_found=["entity1", "entity2"],
        processing_time_ms=150,
        status=status,
    )


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_connector() -> Mock:
    """Base mock connector — tests configure behaviours per scenario."""
    connector = Mock(spec=BaseSyncConnector)
    connector.connector_type = "mock"
    connector.test_connection.return_value = _make_success_connection()
    connector.fetch_content.return_value = {
        "content": "Hello world content for testing.",
        "content_type": "text/plain",
        "metadata": {"title": "Test Resource"},
    }
    connector.list_resources.return_value = []
    connector.fetch_changes.return_value = []
    return connector


@pytest.fixture
def mock_import_pipeline() -> Mock:
    """Mock ImportMemoryPipeline — avoids needing real LLM/embedding/DB."""
    pipeline = Mock(spec=ImportMemoryPipeline)
    pipeline.process.return_value = _make_import_result()
    return pipeline


@pytest.fixture
def sync_pipeline(mock_import_pipeline: Mock) -> SyncPipeline:
    """SyncPipeline with mock import pipeline and mock change detector."""
    p = SyncPipeline(import_pipeline=mock_import_pipeline)
    # Replace the internal ChangeDetector with a mock
    mock_detector = Mock()
    mock_detector.detect.return_value = []
    p._change_detector = mock_detector
    return p


@pytest.fixture
def config() -> SyncConnectorConfig:
    return _make_config()


@pytest.fixture
def execution() -> SyncExecution:
    return _make_execution()


# ── Test: Connection failure ─────────────────────────────────────────────────


class TestConnectionFailure:
    """When test_connection() fails, the pipeline aborts early."""

    def test_connection_failure_aborts_early_and_returns_failed(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_failed_connection(
            "Authentication failed: invalid token"
        )

        result = sync_pipeline.run(mock_connector, config, execution)

        assert result.status == "failed"
        assert result.execution_id == execution.id
        assert result.error is not None
        assert "Authentication failed" in result.error
        assert result.items_fetched == 0
        assert result.items_new == 0
        assert result.memories_created == 0
        assert execution.status == "failed"
        assert execution.error is not None
        assert "Authentication failed" in (execution.error or "")

    def test_connection_failure_does_not_call_detect_or_import(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_failed_connection("boom")

        sync_pipeline.run(mock_connector, config, execution)

        # ChangeDetector.detect must NOT be called
        sync_pipeline._change_detector.detect.assert_not_called()
        # Import pipeline must NOT be called
        mock_import_pipeline.process.assert_not_called()


# ── Test: Empty changes ──────────────────────────────────────────────────────


class TestEmptyChanges:
    """When no changes are detected, the pipeline completes cleanly."""

    def test_empty_changes_yields_clean_completion(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(
            resources_count=25
        )
        sync_pipeline._change_detector.detect.return_value = []

        result = sync_pipeline.run(mock_connector, config, execution)

        assert result.status == "completed"
        assert result.execution_id == execution.id
        assert result.items_fetched == 25
        assert result.items_new == 0
        assert result.items_updated == 0
        assert result.items_deleted == 0
        assert result.items_renamed == 0
        assert result.memories_created == 0
        assert result.errors_count == 0
        assert result.error is None
        assert result.processing_time_ms >= 0

    def test_empty_changes_updates_last_sync_time(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        previous_time = config.last_sync_time
        assert previous_time is None  # never synced

        sync_pipeline._change_detector.detect.return_value = []

        sync_pipeline.run(mock_connector, config, execution)

        assert config.last_sync_time is not None
        assert config.last_sync_time != previous_time

    def test_empty_changes_sets_execution_fields_correctly(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        sync_pipeline._change_detector.detect.return_value = []

        sync_pipeline.run(mock_connector, config, execution)

        assert execution.status == "completed"
        assert execution.started_at is not None
        assert execution.completed_at is not None
        assert execution.items_fetched > 0
        assert execution.items_new == 0
        assert execution.elapsed_ms >= 0

    def test_empty_changes_does_not_call_import_pipeline(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        sync_pipeline._change_detector.detect.return_value = []

        sync_pipeline.run(mock_connector, config, execution)

        mock_import_pipeline.process.assert_not_called()


# ── Test: New content flows through pipeline ─────────────────────────────────


class TestNewContentFlow:
    """New changes trigger full pipeline: fetch → parse → import."""

    @pytest.fixture(autouse=True)
    def setup_detect(self, sync_pipeline: SyncPipeline, config: SyncConnectorConfig):
        """Configure detector to return new changes for these tests."""
        changes = [
            _make_change_record(
                resource_id="doc-001",
                change_type="new",
                content="",
                content_hash="h1",
                metadata={"title": "Document One"},
            ),
            _make_change_record(
                resource_id="doc-002",
                change_type="new",
                content="",
                content_hash="h2",
                metadata={"title": "Document Two"},
            ),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

    def test_new_content_flows_through_full_pipeline(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(50)

        def fetch_side_effect(resource_id: str) -> dict:
            return {
                "doc-001": {
                    "content": "Chapter 1: Introduction.\n\nThis is the first chapter.",
                    "content_type": "text/markdown",
                    "metadata": {"title": "Document One"},
                },
                "doc-002": {
                    "content": "Chapter 2: Advanced Topics.\n\nThis covers advanced material.",
                    "content_type": "text/markdown",
                    "metadata": {"title": "Document Two"},
                },
            }[resource_id]

        mock_connector.fetch_content.side_effect = fetch_side_effect

        with patch(
            "src.sync.sync_pipeline.chunk_text",
            side_effect=lambda text: [text[:200], text[200:]] if len(text) > 200 else [text],
        ):
            result = sync_pipeline.run(mock_connector, config, execution)

        assert result.status == "completed"
        assert result.execution_id == execution.id
        assert result.items_fetched == 50
        assert result.items_new == 2
        assert result.items_updated == 0
        assert result.items_deleted == 0
        assert result.items_renamed == 0
        assert result.memories_created == 10  # from mock import pipeline
        assert result.errors_count == 0
        assert result.error is None

    def test_new_content_calls_import_pipeline_with_correct_args(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        config.name = "my-feishu"
        mock_connector.connector_type = "feishu"
        mock_connector.test_connection.return_value = _make_success_connection(10)

        changes = [
            _make_change_record(
                connector_type="feishu",
                resource_id="doc-x",
                change_type="new",
                content="",
                content_hash="hx",
                metadata={"title": "Feishu Doc"},
            ),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        mock_connector.fetch_content.return_value = {
            "content": "Sample content.",
            "content_type": "text/plain",
            "metadata": {"title": "Feishu Doc"},
        }

        with patch("src.sync.sync_pipeline.chunk_text", return_value=["Sample content."]):
            sync_pipeline.run(mock_connector, config, execution)

        mock_import_pipeline.process.assert_called_once()
        call_kwargs = mock_import_pipeline.process.call_args.kwargs
        assert "source" in call_kwargs
        assert "feishu" in call_kwargs["source"]
        assert "my-feishu" in call_kwargs["source"]
        assert call_kwargs["title"] == "Sync: my-feishu"
        assert "feishu" in call_kwargs["tags"]
        assert "sync" in call_kwargs["tags"]
        assert "my-feishu" in call_kwargs["tags"]
        assert len(call_kwargs["chunks"]) == 1

    def test_execution_fields_populated_after_successful_run(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(99)

        changes = [
            _make_change_record(
                resource_id="r1",
                change_type="new",
                content="Short.",
                content_hash="aa",
            ),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        mock_connector.fetch_content.return_value = {
            "content": "Short.",
            "content_type": "text/plain",
            "metadata": {},
        }

        with patch("src.sync.sync_pipeline.chunk_text", return_value=["Short."]):
            sync_pipeline.run(mock_connector, config, execution)

        assert execution.status == "completed"
        assert execution.started_at is not None
        assert execution.completed_at is not None
        assert execution.items_fetched == 99
        assert execution.items_new == 1
        assert execution.items_updated == 0
        assert execution.items_deleted == 0
        assert execution.items_renamed == 0
        assert execution.memories_created == 10
        assert execution.errors_count == 0
        assert execution.error is None
        assert execution.elapsed_ms >= 0

    def test_last_sync_time_updated_after_changes_processed(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        changes = [
            _make_change_record(
                resource_id="r-last",
                change_type="new",
                content="Some content.",
                content_hash="hz",
            ),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        with patch("src.sync.sync_pipeline.chunk_text", return_value=["Some content."]):
            sync_pipeline.run(mock_connector, config, execution)

        assert config.last_sync_time is not None


# ── Test: Partial failure ────────────────────────────────────────────────────


class TestPartialFailure:
    """When some resources fail, the pipeline continues and reports partial."""

    def test_partial_failure_individual_resource_error_continues_others(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(30)

        changes = [
            _make_change_record(resource_id="good-1", change_type="new", content="", content_hash="g1"),
            _make_change_record(resource_id="bad-1", change_type="new", content="", content_hash="b1"),
            _make_change_record(resource_id="good-2", change_type="new", content="", content_hash="g2"),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        call_count = {"count": 0}

        def fetch_side_effect(resource_id: str) -> dict:
            call_count["count"] += 1
            if resource_id == "bad-1":
                raise RuntimeError("Network timeout for bad-1")
            return {
                "content": f"Content of {resource_id}.",
                "content_type": "text/plain",
                "metadata": {"title": resource_id},
            }

        mock_connector.fetch_content.side_effect = fetch_side_effect

        with patch("src.sync.sync_pipeline.chunk_text", return_value=["chunk"]):
            result = sync_pipeline.run(mock_connector, config, execution)

        assert result.status == "partial"
        assert result.errors_count == 1
        assert result.error is not None
        assert "bad-1" in (result.error or "")
        assert result.items_new == 3  # all three are "new" type changes
        assert result.memories_created == 10  # mock returns 10
        # Only 2 succeeded, so import pipeline got chunks from 2 resources
        assert mock_import_pipeline.process.call_count >= 1
        # 2 good resources * 1 chunk each = 2 chunks passed
        chunks_passed = mock_import_pipeline.process.call_args.kwargs.get("chunks", [])
        assert len(chunks_passed) == 2

    def test_multiple_resources_fail_each_recorded(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(5)

        changes = [
            _make_change_record(resource_id="fail-a", change_type="new", content="", content_hash="fa"),
            _make_change_record(resource_id="fail-b", change_type="updated", content="", content_hash="fb"),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        def fetch_side_effect(resource_id: str) -> dict:
            raise RuntimeError(f"Boom for {resource_id}")

        mock_connector.fetch_content.side_effect = fetch_side_effect

        # chunk_text won't even be called because fetching fails
        result = sync_pipeline.run(mock_connector, config, execution)

        assert result.status == "partial"  # fetch failures populate partial_failures, so status is partial
        assert result.errors_count == 2
        assert result.memories_created == 0
        # Each change gets its process_error set
        for ch in changes:
            assert ch.process_error is not None
            assert "Boom" in (ch.process_error or "")
        # partial_failures recorded in error
        assert result.error is not None
        assert "fail-a" in result.error
        assert "fail-b" in result.error

    def test_partial_failure_change_details_includes_errors(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(3)

        changes = [
            _make_change_record(resource_id="ok", change_type="new", content="", content_hash="ok1"),
            _make_change_record(resource_id="err", change_type="new", content="", content_hash="er1"),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        def fetch_side_effect(resource_id: str) -> dict:
            if resource_id == "err":
                raise RuntimeError("fetch error")
            return {"content": "OK", "content_type": "text/plain", "metadata": {}}

        mock_connector.fetch_content.side_effect = fetch_side_effect

        with patch("src.sync.sync_pipeline.chunk_text", return_value=["OK"]):
            result = sync_pipeline.run(mock_connector, config, execution)

        # Check change_details include both the failed and the successful entries
        assert len(result.change_details) >= 1  # at minimum one failed detail
        failed_details = [d for d in result.change_details if d.get("status") == "failed"]
        assert len(failed_details) >= 1
        assert any(d["resource_id"] == "err" for d in failed_details)


# ── Test: Deleted changes ────────────────────────────────────────────────────


class TestDeletedChanges:
    """Deleted changes are processed without going through the import pipeline."""

    def test_deleted_changes_are_handled_without_import_pipeline(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(20)

        changes = [
            _make_change_record(
                resource_id="del-001",
                change_type="deleted",
                content="",
                content_hash="",
                previous_hash="old-hash-del-001",
            ),
            _make_change_record(
                resource_id="del-002",
                change_type="deleted",
                content="",
                content_hash="",
                previous_hash="old-hash-del-002",
            ),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        result = sync_pipeline.run(mock_connector, config, execution)

        assert result.status == "completed"
        assert result.items_new == 0
        assert result.items_updated == 0
        assert result.items_deleted == 2
        assert result.items_renamed == 0
        assert result.memories_created == 0
        mock_import_pipeline.process.assert_not_called()
        assert execution.items_deleted == 2

    def test_deleted_changes_are_marked_processed(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(5)

        ch = _make_change_record(
            resource_id="del-only",
            change_type="deleted",
            content="",
            content_hash="",
        )
        sync_pipeline._change_detector.detect.return_value = [ch]

        sync_pipeline.run(mock_connector, config, execution)

        assert ch.processed is True

    def test_deleted_changes_appear_in_change_details(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(8)

        ch = _make_change_record(
            resource_id="del-detail",
            change_type="deleted",
            content="",
            content_hash="",
        )
        sync_pipeline._change_detector.detect.return_value = [ch]

        result = sync_pipeline.run(mock_connector, config, execution)

        assert len(result.change_details) >= 1
        del_detail = next(d for d in result.change_details if d.get("change_type") == "deleted")
        assert del_detail["resource_id"] == "del-detail"
        assert del_detail["status"] == "completed"


# ── Test: Import pipeline failure ────────────────────────────────────────────


class TestImportPipelineFailure:
    """When the import pipeline itself fails, the sync reports partial."""

    def test_import_pipeline_process_raises_results_in_partial_status(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(10)
        mock_import_pipeline.process.side_effect = RuntimeError("Memory store unavailable")

        changes = [
            _make_change_record(
                resource_id="crash-me",
                change_type="new",
                content="Valid content.",
                content_hash="c1",
            ),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        with patch("src.sync.sync_pipeline.chunk_text", return_value=["Valid content."]):
            result = sync_pipeline.run(mock_connector, config, execution)

        assert result.status == "partial"
        assert result.errors_count == 1
        assert result.error is not None
        assert "Memory pipeline failed" in (result.error or "")
        assert result.memories_created == 0

    def test_import_pipeline_failure_change_details_records_error(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(3)
        mock_import_pipeline.process.side_effect = RuntimeError("DB down")

        changes = [
            _make_change_record(resource_id="r1", change_type="new", content="x", content_hash="x1"),
            _make_change_record(resource_id="r2", change_type="new", content="y", content_hash="x2"),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        with patch("src.sync.sync_pipeline.chunk_text", return_value=["ch"]):
            result = sync_pipeline.run(mock_connector, config, execution)

        failed_details = [d for d in result.change_details if d.get("status") == "failed"]
        assert len(failed_details) == 2
        for d in failed_details:
            assert "DB down" in d.get("error", "")


# ── Test: Empty or whitespace content ────────────────────────────────────────


class TestEmptyContentSkipped:
    """Resources whose content is empty or whitespace-only are skipped."""

    def test_empty_content_is_skipped_and_not_passed_to_import_pipeline(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(3)

        changes = [
            _make_change_record(
                resource_id="empty-one",
                change_type="new",
                content="",
                content_hash="eh1",
            ),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        mock_connector.fetch_content.return_value = {
            "content": "",
            "content_type": "text/plain",
            "metadata": {},
        }

        result = sync_pipeline.run(mock_connector, config, execution)

        assert result.status == "completed"
        assert result.items_new == 1
        assert result.memories_created == 0
        mock_import_pipeline.process.assert_not_called()

    def test_whitespace_only_content_is_skipped(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(2)

        changes = [
            _make_change_record(
                resource_id="ws-only",
                change_type="new",
                content="",
                content_hash="ws1",
            ),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        mock_connector.fetch_content.return_value = {
            "content": "   \n  \t  \n   ",
            "content_type": "text/plain",
            "metadata": {},
        }

        result = sync_pipeline.run(mock_connector, config, execution)

        assert result.status == "completed"
        assert result.memories_created == 0
        mock_import_pipeline.process.assert_not_called()

    def test_one_empty_one_real_only_real_passed_to_pipeline(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(5)

        changes = [
            _make_change_record(resource_id="empty", change_type="new", content="", content_hash="e1"),
            _make_change_record(resource_id="real", change_type="new", content="", content_hash="r1"),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        def fetch_side_effect(resource_id: str) -> dict:
            if resource_id == "empty":
                return {"content": "", "content_type": "", "metadata": {}}
            return {"content": "Real content here.", "content_type": "text/plain", "metadata": {}}

        mock_connector.fetch_content.side_effect = fetch_side_effect

        with patch("src.sync.sync_pipeline.chunk_text", return_value=["Real content here."]):
            result = sync_pipeline.run(mock_connector, config, execution)

        mock_import_pipeline.process.assert_called_once()
        chunks = mock_import_pipeline.process.call_args.kwargs["chunks"]
        assert len(chunks) == 1
        assert chunks[0]["content"] == "Real content here."
        assert result.status == "completed"


# ── Test: Mixed change types ─────────────────────────────────────────────────


class TestMixedChanges:
    """All four change types (new, updated, deleted, renamed) in one run."""

    def test_mixed_changes_new_updated_deleted_renamed(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(100)

        changes = [
            _make_change_record(resource_id="n1", change_type="new", content="New doc.", content_hash="hn1"),
            _make_change_record(resource_id="u1", change_type="updated", content="Updated doc.", content_hash="hu1"),
            _make_change_record(resource_id="d1", change_type="deleted", content="", content_hash=""),
            _make_change_record(
                resource_id="r1",
                change_type="renamed",
                content="Renamed doc.",
                content_hash="hr1",
                metadata={"previous_resource_id": "old-r1"},
            ),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        def fetch_side_effect(resource_id: str) -> dict:
            if resource_id == "d1":
                return {"content": "", "content_type": "", "metadata": {}}
            return {"content": "Content here.", "content_type": "text/plain", "metadata": {}}

        mock_connector.fetch_content.side_effect = fetch_side_effect

        with patch("src.sync.sync_pipeline.chunk_text", return_value=["Content here."]):
            result = sync_pipeline.run(mock_connector, config, execution)

        assert result.status == "completed"
        assert result.items_new == 1
        assert result.items_updated == 1
        assert result.items_deleted == 1
        assert result.items_renamed == 1
        assert result.items_fetched == 100

    def test_mixed_changes_content_types_flow_to_import_pipeline(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(5)

        changes = [
            _make_change_record(resource_id="new1", change_type="new", content="", content_hash="n1"),
            _make_change_record(resource_id="upd1", change_type="updated", content="", content_hash="u1"),
            _make_change_record(resource_id="ren1", change_type="renamed", content="", content_hash="r1"),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        def fetch_side_effect(resource_id: str) -> dict:
            return {
                "content": f"Data from {resource_id}",
                "content_type": "text/markdown",
                "metadata": {"source": resource_id},
            }

        mock_connector.fetch_content.side_effect = fetch_side_effect

        with patch("src.sync.sync_pipeline.chunk_text", side_effect=lambda t: [t]):
            sync_pipeline.run(mock_connector, config, execution)

        mock_import_pipeline.process.assert_called_once()
        chunks = mock_import_pipeline.process.call_args.kwargs["chunks"]
        assert len(chunks) == 3
        for ch in chunks:
            assert ch["metadata"]["connector_type"] == "mock"
            assert "chunk_index" in ch["metadata"]
            assert "change_type" in ch["metadata"]


# ── Test: Pipeline crash (unexpected exception) ──────────────────────────────


class TestPipelineCrash:
    """When the pipeline itself encounters an unexpected exception."""

    def test_unexpected_exception_in_run_returns_failed(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.side_effect = AttributeError("Unexpected internal bug")

        result = sync_pipeline.run(mock_connector, config, execution)

        assert result.status == "failed"
        assert result.error is not None
        assert "Unexpected internal bug" in (result.error or "")
        assert execution.status == "failed"
        assert execution.error is not None

    def test_detect_method_crash_is_caught_and_reported(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        mock_connector.test_connection.return_value = _make_success_connection(1)
        sync_pipeline._change_detector.detect.side_effect = RuntimeError("Detector blew up")

        result = sync_pipeline.run(mock_connector, config, execution)

        assert result.status == "failed"
        assert "Detector blew up" in (result.error or "")


# ── Test: Edge Cases ─────────────────────────────────────────────────────────


class TestEdgeCases:
    """Boundary and edge-case scenarios."""

    def test_all_changes_are_empty_content_after_fetch(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        """When every fetched content is empty, import pipeline is never called."""
        mock_connector.test_connection.return_value = _make_success_connection(5)

        changes = [
            _make_change_record(resource_id="e1", change_type="new", content="", content_hash="e1"),
            _make_change_record(resource_id="e2", change_type="new", content="", content_hash="e2"),
            _make_change_record(resource_id="e3", change_type="new", content="", content_hash="e3"),
        ]
        sync_pipeline._change_detector.detect.return_value = changes
        mock_connector.fetch_content.return_value = {
            "content": "   ",
            "content_type": "",
            "metadata": {},
        }

        result = sync_pipeline.run(mock_connector, config, execution)

        assert result.status == "completed"
        assert result.items_new == 3
        assert result.memories_created == 0
        mock_import_pipeline.process.assert_not_called()

    def test_change_with_content_already_present_skips_fetch(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        """When ChangeRecord.content is already non-empty, fetch_content is skipped."""
        mock_connector.test_connection.return_value = _make_success_connection(5)

        changes = [
            _make_change_record(
                resource_id="prefilled",
                change_type="new",
                content="Already fetched content here.",
                content_hash="pf1",
            ),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        with patch("src.sync.sync_pipeline.chunk_text", return_value=["Already fetched content here."]):
            result = sync_pipeline.run(mock_connector, config, execution)

        mock_connector.fetch_content.assert_not_called()
        assert result.status == "completed"
        assert result.memories_created == 10

    def test_chunk_text_included_in_pipeline_chunks_with_correct_structure(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        """Verify each chunk dict passed to import pipeline has the right keys."""
        mock_connector.test_connection.return_value = _make_success_connection(2)

        changes = [
            _make_change_record(
                resource_id="struct1",
                change_type="new",
                content="",
                content_hash="s1",
                metadata={"title": "Structured Doc", "tags": ["a", "b"]},
            ),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        mock_connector.fetch_content.return_value = {
            "content": "Paragraph one.\n\nParagraph two.",
            "content_type": "text/markdown",
            "metadata": {"author": "test-user"},
        }

        def fake_chunk_text(text: str) -> list[str]:
            paragraphs = [p for p in text.split("\n\n") if p.strip()]
            return paragraphs  # ["Paragraph one.", "Paragraph two."]

        with patch("src.sync.sync_pipeline.chunk_text", side_effect=fake_chunk_text):
            sync_pipeline.run(mock_connector, config, execution)

        mock_import_pipeline.process.assert_called_once()
        chunks = mock_import_pipeline.process.call_args.kwargs["chunks"]
        assert len(chunks) == 2

        for i, chunk in enumerate(chunks):
            assert "content" in chunk
            assert "title" in chunk
            assert "entities" in chunk
            assert "metadata" in chunk
            assert chunk["metadata"]["connector_type"] == "mock"
            assert chunk["metadata"]["resource_id"] == "struct1"
            assert chunk["metadata"]["change_type"] == "new"
            assert chunk["metadata"]["chunk_index"] == i

    def test_title_fallback_to_resource_id_when_metadata_missing(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        """When metadata has no 'title' or 'name', resource_id is used as title."""
        mock_connector.test_connection.return_value = _make_success_connection(1)

        changes = [
            _make_change_record(
                resource_id="untitled-resource-xyz",
                change_type="new",
                content="",
                content_hash="nf1",
                metadata={},  # no title, no name
            ),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        mock_connector.fetch_content.return_value = {
            "content": "Some content.",
            "content_type": "text/plain",
            "metadata": {},  # also no title in fetch metadata
        }

        with patch("src.sync.sync_pipeline.chunk_text", return_value=["Some content."]):
            sync_pipeline.run(mock_connector, config, execution)

        chunks = mock_import_pipeline.process.call_args.kwargs["chunks"]
        assert chunks[0]["title"] == "untitled-resource-xyz"

    def test_update_config_state_called_after_pipeline(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        """Verify ChangeDetector.update_config_state is called with config + changes."""
        changes = [
            _make_change_record(resource_id="u1", change_type="updated", content="", content_hash="uh1"),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        with patch(
            "src.sync.sync_pipeline.ChangeDetector.update_config_state"
        ) as mock_update:
            sync_pipeline.run(mock_connector, config, execution)
            mock_update.assert_called_once_with(config, changes)

    def test_elapsed_time_is_reasonable(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        """Processing time should be a non-negative integer in milliseconds."""
        mock_connector.test_connection.return_value = _make_success_connection(1)
        sync_pipeline._change_detector.detect.return_value = []

        result = sync_pipeline.run(mock_connector, config, execution)

        assert isinstance(result.processing_time_ms, int)
        assert result.processing_time_ms >= 0
        assert execution.elapsed_ms >= 0

    def test_multiple_runs_with_same_pipeline_instance(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
    ):
        """The pipeline instance is reusable across multiple runs."""
        config = _make_config(name="run1")
        execution1 = _make_execution()
        sync_pipeline._change_detector.detect.return_value = []
        result1 = sync_pipeline.run(mock_connector, config, execution1)
        assert result1.status == "completed"

        config2 = _make_config(name="run2")
        execution2 = _make_execution()
        sync_pipeline._change_detector.detect.return_value = []
        result2 = sync_pipeline.run(mock_connector, config2, execution2)
        assert result2.status == "completed"
        assert result1.execution_id != result2.execution_id

    def test_updated_change_with_existing_hash_triggers_import(
        self,
        sync_pipeline: SyncPipeline,
        mock_connector: Mock,
        mock_import_pipeline: Mock,
        config: SyncConnectorConfig,
        execution: SyncExecution,
    ):
        """'updated' changes with previous_hash flow into the import pipeline."""
        mock_connector.test_connection.return_value = _make_success_connection(10)

        changes = [
            _make_change_record(
                resource_id="updated-doc",
                change_type="updated",
                content="",
                content_hash="new-hash",
                previous_hash="old-hash",
            ),
        ]
        sync_pipeline._change_detector.detect.return_value = changes

        mock_connector.fetch_content.return_value = {
            "content": "Revised content.",
            "content_type": "text/markdown",
            "metadata": {"title": "Updated Doc"},
        }

        with patch("src.sync.sync_pipeline.chunk_text", return_value=["Revised content."]):
            result = sync_pipeline.run(mock_connector, config, execution)

        assert result.items_updated == 1
        mock_import_pipeline.process.assert_called_once()
