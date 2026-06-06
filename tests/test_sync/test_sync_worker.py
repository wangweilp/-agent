"""SyncWorker unit tests.

Covers: enqueue/dequeue, status transitions, stats counters,
dead-letter queue on failure, graceful shutdown, connector resolution,
alert thresholds, history tracking.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import (
    SyncConnectorConfig,
    SyncExecution,
    SyncJob,
    SyncPipelineResult,
)
from src.sync.sync_pipeline import SyncPipeline
from src.sync.sync_store import SyncStore
from src.sync.sync_worker import SyncWorker


# ── helpers ────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_job(
    *,
    job_id: str | None = None,
    connector_config_id: str = "",
    rule_id: str = "",
    name: str = "Test Job",
    status: str = "pending",
) -> SyncJob:
    return SyncJob(
        id=job_id or _new_id(),
        connector_config_id=connector_config_id,
        rule_id=rule_id,
        name=name,
        status=status,
    )


def _make_execution(
    *,
    execution_id: str | None = None,
    job_id: str = "",
    status: str = "pending",
) -> SyncExecution:
    return SyncExecution(
        id=execution_id or _new_id(),
        job_id=job_id,
        status=status,
    )


def _make_connector_config(
    *,
    connector_id: str = "",
    connector_type: str = "fake",
) -> SyncConnectorConfig:
    return SyncConnectorConfig(
        id=connector_id or _new_id(),
        name="Test Connector",
        connector_type=connector_type,
        credentials={"key": "val"},
    )


def _make_pipeline_result(**overrides) -> SyncPipelineResult:
    defaults: dict = {
        "execution_id": _new_id(),
        "status": "completed",
        "items_fetched": 10,
        "items_new": 3,
        "items_updated": 2,
        "items_deleted": 0,
        "items_renamed": 1,
        "memories_created": 5,
        "errors_count": 0,
        "error": None,
        "processing_time_ms": 250,
    }
    defaults.update(overrides)
    return SyncPipelineResult(**defaults)


# ── Mock connector ─────────────────────────────────────────────────────────

class _FakeConnector(BaseSyncConnector):
    connector_type = "fake"


# ── fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def mock_store() -> MagicMock:
    """Fully-mocked SyncStore."""
    return MagicMock(spec=SyncStore)


@pytest.fixture
def mock_pipeline() -> MagicMock:
    """Fully-mocked SyncPipeline that returns success by default."""
    pipeline = MagicMock(spec=SyncPipeline)
    pipeline.run.return_value = _make_pipeline_result()
    return pipeline


@pytest.fixture
def worker(mock_store, mock_pipeline, tmp_path) -> SyncWorker:
    """SyncWorker with mocked deps, connector factory, and temp DLQ dir."""
    dlq_dir = tmp_path / "dead_letter"

    def _factory(connector_type: str, credentials: dict) -> _FakeConnector:
        return _FakeConnector(credentials)

    return SyncWorker(
        sync_store=mock_store,
        sync_pipeline=mock_pipeline,
        connector_factory=_factory,
        dead_letter_dir=str(dlq_dir),
    )


# ── Enqueue / Dequeue ──────────────────────────────────────────────────────

class TestEnqueueDequeue:

    def test_enqueue_increments_pending_count(self, worker):
        """Enqueue one item increments pending by 1."""
        assert worker.pending == 0
        job = _make_job()
        execution = _make_execution(job_id=job.id)
        worker.enqueue(job, execution)
        assert worker.pending == 1

    def test_enqueue_multiple_increments_pending(self, worker):
        """Enqueue N items increments pending to N."""
        for i in range(5):
            job = _make_job(name=f"Job {i}")
            execution = _make_execution(job_id=job.id)
            worker.enqueue(job, execution)
        assert worker.pending == 5

    def test_enqueue_none_shuts_down_worker(self, worker):
        """Shutdown sentinel (None) via shutdown() method is handled."""
        worker.enqueue(_make_job(), _make_execution())
        worker.enqueue(_make_job(), _make_execution())
        # Thread not started yet, so pending is 2
        assert worker.pending == 2
        worker.shutdown(timeout=0.1)
        # Sentinel inserted, worker not running so join returns immediately
        assert worker.pending >= 2  # sentinel + pending items still in queue

    def test_pending_is_zero_after_thread_processes_and_shuts_down(
        self, worker, mock_store, mock_pipeline
    ):
        """After starting the thread, enqueued items are consumed."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config

        job = _make_job(connector_config_id=connector_config.id)
        execution = _make_execution(job_id=job.id)
        worker.enqueue(job, execution)

        worker.start()
        time.sleep(0.3)  # allow thread to pick up and process the item
        worker.shutdown(timeout=5.0)
        assert worker.pending == 0


# ── Status transitions ─────────────────────────────────────────────────────

class TestStatusTransitions:

    def test_process_success_transitions_job_and_execution_to_completed(
        self, worker, mock_store, mock_pipeline
    ):
        """On pipeline success, job + execution status become 'completed'."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config
        mock_pipeline.run.return_value = _make_pipeline_result(status="completed")

        job = _make_job(connector_config_id=connector_config.id, status="pending")
        execution = _make_execution(job_id=job.id, status="pending")

        worker._process(job, execution)

        # Job updated to completed
        assert job.status == "completed"
        # Execution saved with completed status
        saved_execution = mock_store.save_execution.call_args_list[-1][0][0]
        assert saved_execution.status == "completed"

    def test_process_failure_transitions_job_and_execution_to_failed(
        self, worker, mock_store, mock_pipeline
    ):
        """On pipeline exception, job + execution status become 'failed'."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config
        mock_pipeline.run.side_effect = RuntimeError("pipeline crash")

        job = _make_job(connector_config_id=connector_config.id, status="pending")
        execution = _make_execution(job_id=job.id, status="pending")

        worker._process(job, execution)

        assert job.status == "failed"
        saved_execution = mock_store.save_execution.call_args_list[-1][0][0]
        assert saved_execution.status == "failed"
        assert "Sync execution crashed" in (saved_execution.error or "")

    def test_process_updates_job_to_running_before_pipeline(
        self, worker, mock_store, mock_pipeline
    ):
        """Job status is set to 'running' before pipeline.run is called."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config

        # Track order: when pipeline.run is called, job.status should be "running"
        captured_statuses: list[str] = []

        def _capture(*args, **kwargs):
            captured_statuses.append(job.status)
            return _make_pipeline_result()

        mock_pipeline.run.side_effect = _capture

        job = _make_job(connector_config_id=connector_config.id, status="pending")
        execution = _make_execution(job_id=job.id)

        worker._process(job, execution)

        assert captured_statuses == ["running"]
        assert job.status == "completed"

    def test_process_partial_result_maps_to_partial_job_status(
        self, worker, mock_store, mock_pipeline
    ):
        """When pipeline returns 'partial', job status becomes 'partial'."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config
        mock_pipeline.run.return_value = _make_pipeline_result(
            status="partial", errors_count=2, error="some items failed"
        )

        job = _make_job(connector_config_id=connector_config.id, status="pending")
        execution = _make_execution(job_id=job.id)

        worker._process(job, execution)

        assert job.status == "partial"

    def test_process_preserves_pipeline_result_fields_on_execution(
        self, worker, mock_store, mock_pipeline
    ):
        """Execution object receives all counter fields from pipeline result."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config
        mock_pipeline.run.return_value = _make_pipeline_result(
            items_fetched=42,
            items_new=7,
            items_updated=3,
            items_deleted=1,
            items_renamed=2,
            memories_created=10,
            errors_count=5,
            error=None,
            processing_time_ms=999,
        )

        job = _make_job(connector_config_id=connector_config.id)
        execution = _make_execution(job_id=job.id)

        worker._process(job, execution)

        saved = mock_store.save_execution.call_args_list[-1][0][0]
        assert saved.items_fetched == 42
        assert saved.items_new == 7
        assert saved.items_updated == 3
        assert saved.items_deleted == 1
        assert saved.items_renamed == 2
        assert saved.memories_created == 10
        assert saved.errors_count == 5
        assert saved.elapsed_ms == 999


# ── Stats counters ─────────────────────────────────────────────────────────

class TestStatsCounters:

    def test_stats_initial_state_is_zero(self, worker):
        """Before any processing, all stats are zero."""
        s = worker.stats
        assert s["jobs"]["completed"] == 0
        assert s["jobs"]["failed"] == 0
        assert s["jobs"]["in_progress"] == 0
        assert s["jobs"]["pending"] == 0

    def test_completed_count_increments_after_success(
        self, worker, mock_store, mock_pipeline
    ):
        """After a successful process, completed_count is 1."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config

        job = _make_job(connector_config_id=connector_config.id)
        execution = _make_execution(job_id=job.id)
        worker._process(job, execution)

        assert worker.stats["jobs"]["completed"] == 1
        assert worker.stats["jobs"]["failed"] == 0
        assert worker.stats["jobs"]["in_progress"] == 0

    def test_failed_count_increments_after_failure(
        self, worker, mock_store, mock_pipeline
    ):
        """After a failed process, failed_count is 1."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config
        mock_pipeline.run.side_effect = RuntimeError("crash")

        job = _make_job(connector_config_id=connector_config.id)
        execution = _make_execution(job_id=job.id)
        worker._process(job, execution)

        assert worker.stats["jobs"]["completed"] == 0
        assert worker.stats["jobs"]["failed"] == 1
        assert worker.stats["jobs"]["in_progress"] == 0

    def test_stats_reflects_mixed_results_correctly(
        self, worker, mock_store, mock_pipeline
    ):
        """After 2 successes and 1 failure, counters are (2, 1, 0)."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config

        # Two successes
        mock_pipeline.run.return_value = _make_pipeline_result()
        worker._process(_make_job(connector_config_id=connector_config.id), _make_execution())
        worker._process(_make_job(connector_config_id=connector_config.id), _make_execution())

        # One failure
        mock_pipeline.run.side_effect = RuntimeError("crash")
        worker._process(_make_job(connector_config_id=connector_config.id), _make_execution())

        assert worker.stats["jobs"]["completed"] == 2
        assert worker.stats["jobs"]["failed"] == 1
        assert worker.stats["jobs"]["in_progress"] == 0

    def test_in_progress_count_during_processing(
        self, worker, mock_store, mock_pipeline
    ):
        """During _process, in_progress_count is temporarily 1."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config

        captured_in_progress: list[int] = []

        def _capture(*args, **kwargs):
            # Read stats while pipeline is "running"
            captured_in_progress.append(worker.stats["jobs"]["in_progress"])
            return _make_pipeline_result()

        mock_pipeline.run.side_effect = _capture

        job = _make_job(connector_config_id=connector_config.id)
        execution = _make_execution(job_id=job.id)
        worker._process(job, execution)

        assert captured_in_progress == [1]
        assert worker.stats["jobs"]["in_progress"] == 0


# ── Dead Letter Queue ──────────────────────────────────────────────────────

class TestDeadLetterQueue:

    def test_dlq_file_written_on_failure(self, worker, mock_store, mock_pipeline, tmp_path):
        """Pipeline failure writes a JSON dead-letter file."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config
        mock_pipeline.run.side_effect = RuntimeError("sync crash")

        job = _make_job(connector_config_id=connector_config.id)
        execution = _make_execution(job_id=job.id)
        worker._process(job, execution)

        dlq_dir = tmp_path / "dead_letter"
        json_files = list(dlq_dir.glob("sync_*.json"))
        assert len(json_files) == 1

        content = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert content["execution_id"] == execution.id
        assert content["job_id"] == job.id
        assert content["status"] == "failed"
        assert "Sync execution crashed" in content["error"]

    def test_dlq_file_not_written_on_success(self, worker, mock_store, mock_pipeline, tmp_path):
        """Successful execution does NOT write a dead-letter file."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config

        job = _make_job(connector_config_id=connector_config.id)
        execution = _make_execution(job_id=job.id)
        worker._process(job, execution)

        dlq_dir = tmp_path / "dead_letter"
        json_files = list(dlq_dir.glob("sync_*.json"))
        assert len(json_files) == 0

    def test_connector_config_not_found_triggers_failure_and_dlq(
        self, worker, mock_store, mock_pipeline, tmp_path
    ):
        """When get_connector returns None, the execution fails with DLQ."""
        mock_store.get_connector.return_value = None

        job = _make_job(connector_config_id="missing-connector-id")
        execution = _make_execution(job_id=job.id)
        worker._process(job, execution)

        assert job.status == "failed"
        assert execution.status == "failed"
        assert "not found" in (execution.error or "")

        dlq_dir = tmp_path / "dead_letter"
        json_files = list(dlq_dir.glob("sync_*.json"))
        assert len(json_files) == 1

    def test_connector_build_returns_none_triggers_failure_and_dlq(
        self, worker, mock_store, mock_pipeline, tmp_path
    ):
        """When _build_connector returns None, execution fails with DLQ."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config

        # factory returns None -> connector cannot be built
        worker._connector_factory = lambda ct, creds: None

        job = _make_job(connector_config_id=connector_config.id)
        execution = _make_execution(job_id=job.id)
        worker._process(job, execution)

        assert job.status == "failed"
        assert "No connector for type" in (execution.error or "")

        dlq_dir = tmp_path / "dead_letter"
        json_files = list(dlq_dir.glob("sync_*.json"))
        assert len(json_files) == 1

    def test_dlq_writes_are_idempotent_across_multiple_failures(
        self, worker, mock_store, mock_pipeline, tmp_path
    ):
        """Each failure produces a separate DLQ file."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config
        mock_pipeline.run.side_effect = RuntimeError("fail")

        for i in range(3):
            job = _make_job(connector_config_id=connector_config.id, name=f"Job {i}")
            execution = _make_execution(job_id=job.id)
            worker._process(job, execution)

        dlq_dir = tmp_path / "dead_letter"
        json_files = list(dlq_dir.glob("sync_*.json"))
        assert len(json_files) == 3

    def test_dlq_stats_count_reflects_failed_executions(
        self, worker, mock_store, mock_pipeline, tmp_path
    ):
        """stats['dead_letter']['count'] matches the number of DLQ files."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config
        mock_pipeline.run.side_effect = RuntimeError("fail")

        for i in range(4):
            job = _make_job(connector_config_id=connector_config.id)
            execution = _make_execution(job_id=job.id)
            worker._process(job, execution)

        assert worker.stats["dead_letter"]["count"] == 4
        assert worker.stats["dead_letter"]["dir"] == str(tmp_path / "dead_letter")


# ── Shutdown ───────────────────────────────────────────────────────────────

class TestShutdown:

    def test_shutdown_stops_running_worker(self, worker, mock_store, mock_pipeline):
        """shutdown() sends sentinel and joins; worker stops."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config

        worker.enqueue(
            _make_job(connector_config_id=connector_config.id),
            _make_execution(),
        )

        worker.start()
        time.sleep(0.3)  # allow processing
        worker.shutdown(timeout=5.0)

        assert not worker.is_alive()

    def test_shutdown_before_start_does_not_raise(self, worker):
        """Shutdown on a never-started thread is safe."""
        worker.shutdown(timeout=0.5)
        # Should not raise; thread was never alive

    def test_shutdown_with_zero_timeout_returns_even_if_processing(
        self, worker, mock_store, mock_pipeline
    ):
        """A zero timeout returns quickly even if processing is ongoing."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config

        # Make pipeline slow
        def _slow(*args, **kwargs):
            time.sleep(1.0)
            return _make_pipeline_result()

        mock_pipeline.run.side_effect = _slow

        worker.enqueue(
            _make_job(connector_config_id=connector_config.id),
            _make_execution(),
        )

        worker.start()
        time.sleep(0.05)  # let thread pick up the item
        t0 = time.monotonic()
        worker.shutdown(timeout=0.1)
        elapsed = time.monotonic() - t0

        # Should return quickly (within the timeout window), even if thread still alive
        assert elapsed < 2.0  # generous bound; real timeout is 0.1s

    def test_shutdown_after_processing_all_queued_items(
        self, worker, mock_store, mock_pipeline
    ):
        """Worker processes all queued items before shutdown sentinel."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config

        num_items = 5
        jobs = []
        for i in range(num_items):
            job = _make_job(connector_config_id=connector_config.id, name=f"Job {i}")
            execution = _make_execution(job_id=job.id)
            worker.enqueue(job, execution)
            jobs.append(job)

        worker.start()
        time.sleep(0.5)  # allow processing of all items
        worker.shutdown(timeout=5.0)

        # All items should be processed, queue empty
        assert worker.pending == 0
        # All jobs should be status "completed"
        for job in jobs:
            assert job.status == "completed"

    def test_shutdown_logs_pending_count(self, worker):
        """Shutdown logs the pending count after sentinel inserted."""
        with patch("src.sync.sync_worker.logger") as mock_logger:
            worker.enqueue(_make_job(), _make_execution())
            worker.shutdown(timeout=0.1)
            mock_logger.info.assert_any_call(
                "sync_worker_shutdown", extra={"pending": worker.pending}
            )


# ── Alerts ─────────────────────────────────────────────────────────────────

class TestAlerts:

    def test_no_alerts_when_everything_is_healthy(self, worker):
        """Fresh worker with no activity has no alerts."""
        assert worker.alerts == []

    def test_dlq_accumulation_alert_at_threshold(
        self, worker, mock_store, mock_pipeline, tmp_path
    ):
        """When DLQ count >= 5, a warning alert fires."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config
        mock_pipeline.run.side_effect = RuntimeError("fail")

        for i in range(5):
            job = _make_job(connector_config_id=connector_config.id)
            execution = _make_execution(job_id=job.id)
            worker._process(job, execution)

        alerts = worker.alerts
        dlq_alerts = [a for a in alerts if a["type"] == "dlq_accumulation"]
        assert len(dlq_alerts) == 1
        assert dlq_alerts[0]["level"] == "warning"
        assert dlq_alerts[0]["current"] == 5

    def test_dlq_alert_not_fired_below_threshold(
        self, worker, mock_store, mock_pipeline, tmp_path
    ):
        """DLQ count < 5 does not trigger an alert."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config
        mock_pipeline.run.side_effect = RuntimeError("fail")

        for i in range(4):
            job = _make_job(connector_config_id=connector_config.id)
            execution = _make_execution(job_id=job.id)
            worker._process(job, execution)

        alerts = worker.alerts
        dlq_alerts = [a for a in alerts if a["type"] == "dlq_accumulation"]
        assert len(dlq_alerts) == 0

    def test_queue_congestion_alert_at_threshold(self, worker):
        """When pending queue >= 10, a warning alert fires."""
        for i in range(12):
            worker.enqueue(_make_job(name=f"Job {i}"), _make_execution())

        alerts = worker.alerts
        q_alerts = [a for a in alerts if a["type"] == "queue_congestion"]
        assert len(q_alerts) == 1
        assert q_alerts[0]["level"] == "warning"
        assert q_alerts[0]["current"] == 12

    def test_queue_congestion_alert_not_fired_below_threshold(self, worker):
        """Pending queue < 10 does not trigger congestion alert."""
        for i in range(9):
            worker.enqueue(_make_job(name=f"Job {i}"), _make_execution())

        alerts = worker.alerts
        q_alerts = [a for a in alerts if a["type"] == "queue_congestion"]
        assert len(q_alerts) == 0

    def test_high_failure_rate_alert_triggers(self, worker):
        """When recent failure rate >= 30%, a critical alert fires."""
        with worker._lock:
            # 10 entries, 4 failures = 40% failure rate
            for i in range(10):
                status = "failed" if i < 4 else "completed"
                worker._history.append({
                    "job_id": _new_id(),
                    "execution_id": _new_id(),
                    "name": f"Entry {i}",
                    "status": status,
                    "items_new": 0,
                    "items_updated": 0,
                    "items_deleted": 0,
                    "memories_created": 0,
                    "elapsed_ms": 100,
                    "started_at": _utcnow().isoformat(),
                })

        alerts = worker.alerts
        fail_alerts = [a for a in alerts if a["type"] == "high_failure_rate"]
        assert len(fail_alerts) == 1
        assert fail_alerts[0]["level"] == "critical"
        assert fail_alerts[0]["current"] == 0.4

    def test_high_failure_rate_alert_not_fired_below_threshold(self, worker):
        """When recent failure rate < 30%, no critical alert."""
        with worker._lock:
            for i in range(10):
                status = "failed" if i < 2 else "completed"  # 20%
                worker._history.append({
                    "job_id": _new_id(),
                    "execution_id": _new_id(),
                    "name": f"Entry {i}",
                    "status": status,
                    "items_new": 0,
                    "items_updated": 0,
                    "items_deleted": 0,
                    "memories_created": 0,
                    "elapsed_ms": 100,
                    "started_at": _utcnow().isoformat(),
                })

        alerts = worker.alerts
        fail_alerts = [a for a in alerts if a["type"] == "high_failure_rate"]
        assert len(fail_alerts) == 0

    def test_multiple_alerts_can_fire_simultaneously(
        self, worker, mock_store, mock_pipeline, tmp_path
    ):
        """Both DLQ and queue congestion alerts fire when thresholds met."""
        # Cause DLQ >= 5
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config
        mock_pipeline.run.side_effect = RuntimeError("fail")
        for i in range(5):
            job = _make_job(connector_config_id=connector_config.id)
            execution = _make_execution(job_id=job.id)
            worker._process(job, execution)

        # Cause queue congestion >= 10
        for i in range(10):
            worker.enqueue(_make_job(), _make_execution())

        alert_types = {a["type"] for a in worker.alerts}
        assert "dlq_accumulation" in alert_types
        assert "queue_congestion" in alert_types

    def test_alerts_empty_history_no_failure_rate_alert(self, worker):
        """No history entries means no failure rate alert."""
        assert worker.alerts == []


# ── Connector resolution ───────────────────────────────────────────────────

class TestConnectorResolution:

    def test_build_connector_uses_factory_when_provided(self, worker):
        """When connector_factory is set, it is used instead of the registry."""
        factory_calls: list[tuple] = []

        def _tracking_factory(connector_type: str, credentials: dict):
            factory_calls.append((connector_type, credentials))
            return _FakeConnector(credentials)

        worker._connector_factory = _tracking_factory
        config = _make_connector_config(connector_type="my_source")

        result = worker._build_connector(config)

        assert isinstance(result, _FakeConnector)
        assert len(factory_calls) == 1
        assert factory_calls[0] == ("my_source", {"key": "val"})

    def test_build_connector_returns_none_for_unknown_type_in_registry(self, worker):
        """When factory is None and type not in registry, returns None."""
        worker._connector_factory = None

        with patch.dict("src.sync.SYNC_CONNECTOR_REGISTRY", {}, clear=True):
            config = _make_connector_config(connector_type="nonexistent_type")
            result = worker._build_connector(config)
            assert result is None

    def test_build_connector_falls_back_to_registry_when_no_factory(self, worker):
        """Without a factory, _build_connector looks up SYNC_CONNECTOR_REGISTRY."""
        worker._connector_factory = None
        config = _make_connector_config(connector_type="fake")

        # Register our fake in the registry
        from src.sync import SYNC_CONNECTOR_REGISTRY as registry
        with patch.dict(registry, {"fake": _FakeConnector}, clear=True):
            result = worker._build_connector(config)
            assert isinstance(result, _FakeConnector)


# ── History tracking ───────────────────────────────────────────────────────

class TestHistoryTracking:

    def test_successful_execution_adds_to_history(
        self, worker, mock_store, mock_pipeline
    ):
        """A completed execution appears in recent_executions."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config

        job = _make_job(connector_config_id=connector_config.id, name="History Job")
        execution = _make_execution(job_id=job.id)
        worker._process(job, execution)

        recent = worker.stats["recent_executions"]
        assert len(recent) == 1
        assert recent[0]["job_id"] == job.id
        assert recent[0]["name"] == "History Job"
        assert recent[0]["status"] == "completed"

    def test_failed_execution_adds_to_history(self, worker, mock_store, mock_pipeline):
        """A failed execution appears in history with status 'failed'."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config
        mock_pipeline.run.side_effect = RuntimeError("crash")

        job = _make_job(connector_config_id=connector_config.id, name="Fail Job")
        execution = _make_execution(job_id=job.id)
        worker._process(job, execution)

        recent = worker.stats["recent_executions"]
        assert len(recent) == 1
        assert recent[0]["status"] == "failed"

    def test_history_capped_at_max_history(self, worker, mock_store, mock_pipeline):
        """When history exceeds _max_history (50), oldest entries are dropped."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config

        # Create 60 successful executions
        for i in range(60):
            job = _make_job(connector_config_id=connector_config.id, name=f"Job {i}")
            execution = _make_execution(job_id=job.id)
            worker._process(job, execution)

        # history list internally should have at most 50 entries
        with worker._lock:
            internal_len = len(worker._history)

        assert internal_len <= worker._max_history
        assert internal_len == 50

    def test_recent_executions_in_stats_is_last_20(self, worker, mock_store, mock_pipeline):
        """stats['recent_executions'] shows at most the last 20 entries."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config

        for i in range(40):
            job = _make_job(connector_config_id=connector_config.id, name=f"Job {i}")
            execution = _make_execution(job_id=job.id)
            worker._process(job, execution)

        recent = worker.stats["recent_executions"]
        assert len(recent) == 20


# ── Edge cases ─────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_worker_not_started_stats_shows_not_alive(self, worker):
        """Before start(), stats['worker']['alive'] is False."""
        assert worker.stats["worker"]["alive"] is False

    def test_worker_started_stats_shows_alive(self, worker, mock_store, mock_pipeline):
        """After start(), stats['worker']['alive'] is True."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config

        worker.start()
        try:
            assert worker.stats["worker"]["alive"] is True
        finally:
            worker.shutdown(timeout=5.0)

    def test_started_at_set_after_start(self, worker, mock_store, mock_pipeline):
        """After start(), _started_at is a non-empty ISO timestamp."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config

        worker.start()
        time.sleep(0.05)  # let run() reach _started_at assignment
        try:
            assert worker._started_at != ""
            # Should be valid ISO
            datetime.fromisoformat(worker._started_at)
        finally:
            worker.shutdown(timeout=5.0)

    def test_dead_letter_dir_created_on_run(self, worker, tmp_path):
        """DLQ directory is created when the worker starts."""
        dlq_dir = tmp_path / "dead_letter"
        assert not dlq_dir.exists()

        worker.start()
        time.sleep(0.1)
        worker.shutdown(timeout=5.0)

        assert dlq_dir.exists()
        assert dlq_dir.is_dir()

    def test_enqueue_same_job_multiple_executions(self, worker, mock_store, mock_pipeline):
        """The same job can be enqueued with different executions."""
        connector_config = _make_connector_config()
        mock_store.get_connector.return_value = connector_config

        job = _make_job(connector_config_id=connector_config.id)
        exec1 = _make_execution(job_id=job.id)
        exec2 = _make_execution(job_id=job.id)

        worker.enqueue(job, exec1)
        worker.enqueue(job, exec2)
        assert worker.pending == 2

        worker.start()
        time.sleep(0.4)
        worker.shutdown(timeout=5.0)
        assert worker.pending == 0

    def test_thread_name_is_sync_worker(self, worker):
        """Worker thread has the expected name."""
        assert worker.name == "sync-worker"

    def test_thread_is_daemon(self, worker):
        """Worker thread is a daemon thread."""
        assert worker.daemon is True
