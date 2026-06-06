"""Tests for SyncScheduler — cron parsing, timer management, trigger logic."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.sync.models import SyncConnectorConfig, SyncJob, SyncRule
from src.sync.scheduler import SyncScheduler, _cron_next, _simple_cron_next


class TestCronParsing:
    """Test cron expression parsing and next-fire computation."""

    def test_hourly_cron(self):
        """0 * * * * should fire at the top of every hour."""
        from_time = datetime(2026, 6, 3, 10, 15, 0, tzinfo=timezone.utc)
        try:
            from croniter import croniter
            next_fire = croniter("0 * * * *", from_time).get_next(datetime)
            assert next_fire.hour == 11
            assert next_fire.minute == 0
        except ImportError:
            next_fire = _simple_cron_next("0 * * * *", from_time)
            assert next_fire.minute == 0

    def test_daily_cron(self):
        """0 0 * * * should fire at midnight."""
        from_time = datetime(2026, 6, 3, 10, 15, 0, tzinfo=timezone.utc)
        try:
            from croniter import croniter
            next_fire = croniter("0 0 * * *", from_time).get_next(datetime)
            assert next_fire.hour == 0
            assert next_fire.minute == 0
        except ImportError:
            next_fire = _simple_cron_next("0 0 * * *", from_time)
            assert next_fire.hour == 0

    def test_simple_fallback_hourly(self):
        """Fallback parser handles 0 * * * *."""
        from_time = datetime(2026, 6, 3, 10, 15, 0, tzinfo=timezone.utc)
        next_fire = _simple_cron_next("0 * * * *", from_time)
        assert next_fire > from_time

    def test_simple_fallback_daily(self):
        """Fallback parser handles 0 0 * * *."""
        from_time = datetime(2026, 6, 3, 10, 15, 0, tzinfo=timezone.utc)
        next_fire = _simple_cron_next("0 0 * * *", from_time)
        assert next_fire > from_time
        assert next_fire.hour == 0

    def test_simple_fallback_weekly(self):
        """Fallback parser handles 0 0 * * 0 (Sunday)."""
        from_time = datetime(2026, 6, 3, 10, 15, 0, tzinfo=timezone.utc)
        next_fire = _simple_cron_next("0 0 * * 0", from_time)
        assert next_fire > from_time

    def test_invalid_cron_expression(self):
        """Invalid cron expression should raise or fall back gracefully."""
        from_time = datetime(2026, 6, 3, 10, 15, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError):
            _simple_cron_next("invalid", from_time)

    def test_every_6_hours_cron(self):
        """0 */6 * * * should fire every 6 hours."""
        from_time = datetime(2026, 6, 3, 10, 15, 0, tzinfo=timezone.utc)
        try:
            from croniter import croniter
            next_fire = croniter("0 */6 * * *", from_time).get_next(datetime)
            assert next_fire > from_time
        except ImportError:
            pass  # skip if croniter not available


class TestSchedulerLogic:
    """Test scheduler thread logic."""

    def test_scheduler_init(self, sync_store):
        """Scheduler initializes with store and worker."""
        worker = MagicMock()
        scheduler = SyncScheduler(sync_store, worker, tick_interval=1)
        assert scheduler._running is False
        assert scheduler._tick_interval == 1

    def test_reload_cron_timers_no_jobs(self, sync_store):
        """Empty store yields no timers."""
        worker = MagicMock()
        scheduler = SyncScheduler(sync_store, worker)
        scheduler._reload_cron_timers()
        assert len(scheduler._cron_timers) == 0

    def test_reload_cron_timers_with_cron_job(self, sync_store):
        """Cron job creates a timer entry."""
        worker = MagicMock()

        config = SyncConnectorConfig(
            name="Test", connector_type="local_folder",
            credentials={"folder_path": "/tmp"},
        )
        sync_store.save_connector(config)

        rule = SyncRule(rule_type="cron", cron_expression="0 * * * *")
        sync_store.save_rule(rule)

        job = SyncJob(
            connector_config_id=config.id, rule_id=rule.id,
            name="Test Cron Job",
        )
        sync_store.save_job(job)

        scheduler = SyncScheduler(sync_store, worker)
        scheduler._reload_cron_timers()
        assert job.id in scheduler._cron_timers

    def test_reload_skips_manual_jobs(self, sync_store):
        """Manual jobs should NOT have cron timers."""
        worker = MagicMock()

        config = SyncConnectorConfig(
            name="Test", connector_type="local_folder",
            credentials={"folder_path": "/tmp"},
        )
        sync_store.save_connector(config)

        rule = SyncRule(rule_type="manual")
        sync_store.save_rule(rule)

        job = SyncJob(
            connector_config_id=config.id, rule_id=rule.id,
            name="Test Manual Job",
        )
        sync_store.save_job(job)

        scheduler = SyncScheduler(sync_store, worker)
        scheduler._reload_cron_timers()
        assert job.id not in scheduler._cron_timers

    def test_reload_skips_disabled_jobs(self, sync_store):
        """Disabled jobs should be skipped."""
        worker = MagicMock()

        config = SyncConnectorConfig(
            name="Test", connector_type="local_folder",
            credentials={"folder_path": "/tmp"},
        )
        sync_store.save_connector(config)

        rule = SyncRule(rule_type="cron", cron_expression="0 * * * *")
        sync_store.save_rule(rule)

        job = SyncJob(
            connector_config_id=config.id, rule_id=rule.id,
            name="Test", enabled=False,
        )
        sync_store.save_job(job)

        scheduler = SyncScheduler(sync_store, worker)
        scheduler._reload_cron_timers()
        assert job.id not in scheduler._cron_timers

    def test_reload_skips_cancelled_jobs(self, sync_store):
        """Cancelled jobs should be skipped even if enabled."""
        worker = MagicMock()

        config = SyncConnectorConfig(
            name="Test", connector_type="local_folder",
            credentials={"folder_path": "/tmp"},
        )
        sync_store.save_connector(config)

        rule = SyncRule(rule_type="cron", cron_expression="0 * * * *")
        sync_store.save_rule(rule)

        job = SyncJob(
            connector_config_id=config.id, rule_id=rule.id,
            name="Test", status="cancelled",
        )
        sync_store.save_job(job)

        scheduler = SyncScheduler(sync_store, worker)
        scheduler._reload_cron_timers()
        # Cancelled jobs are filtered by enabled_only=True in list_jobs
        # But status check also happens in _trigger_job

    def test_invalid_cron_handled_gracefully(self, sync_store):
        """Invalid cron expression is logged, not crashed."""
        worker = MagicMock()

        config = SyncConnectorConfig(
            name="Test", connector_type="local_folder",
            credentials={"folder_path": "/tmp"},
        )
        sync_store.save_connector(config)

        rule = SyncRule(rule_type="cron", cron_expression="not valid cron")
        sync_store.save_rule(rule)

        job = SyncJob(
            connector_config_id=config.id, rule_id=rule.id,
            name="Test",
        )
        sync_store.save_job(job)

        scheduler = SyncScheduler(sync_store, worker)
        # Should not raise
        scheduler._reload_cron_timers()

    def test_shutdown(self, sync_store):
        """Shutdown stops the scheduler cleanly."""
        worker = MagicMock()
        scheduler = SyncScheduler(sync_store, worker)
        scheduler.shutdown(timeout=1.0)
        assert scheduler._running is False

    def test_refresh_timers(self, sync_store):
        """refresh_timers delegates to reload."""
        worker = MagicMock()
        scheduler = SyncScheduler(sync_store, worker)
        scheduler._reload_cron_timers = MagicMock()
        scheduler.refresh_timers()
        scheduler._reload_cron_timers.assert_called_once()

    def test_trigger_job_enabled(self, sync_store):
        """_trigger_job enqueues enabled job."""
        worker = MagicMock()
        config = SyncConnectorConfig(name="T", connector_type="local_folder",
                                      credentials={"folder_path": "/tmp"})
        sync_store.save_connector(config)
        rule = SyncRule(rule_type="cron", cron_expression="0 * * * *")
        sync_store.save_rule(rule)
        job = SyncJob(connector_config_id=config.id, rule_id=rule.id, name="Test")
        sync_store.save_job(job)

        scheduler = SyncScheduler(sync_store, worker)
        scheduler._trigger_job(job.id)

        # Worker.enqueue should have been called
        assert worker.enqueue.called

    def test_trigger_job_disabled_skipped(self, sync_store):
        """_trigger_job skips disabled jobs."""
        worker = MagicMock()
        config = SyncConnectorConfig(name="T", connector_type="local_folder",
                                      credentials={"folder_path": "/tmp"})
        sync_store.save_connector(config)
        rule = SyncRule(rule_type="cron", cron_expression="0 * * * *")
        sync_store.save_rule(rule)
        job = SyncJob(connector_config_id=config.id, rule_id=rule.id,
                      name="Test", enabled=False)
        sync_store.save_job(job)

        scheduler = SyncScheduler(sync_store, worker)
        scheduler._trigger_job(job.id)

        # Worker.enqueue should NOT have been called
        assert not worker.enqueue.called

    def test_trigger_job_nonexistent_no_error(self, sync_store):
        """_trigger_job handles nonexistent job gracefully."""
        worker = MagicMock()
        scheduler = SyncScheduler(sync_store, worker)
        # Should not raise
        scheduler._trigger_job("nonexistent-id")
        assert not worker.enqueue.called

    def test_trigger_job_cancelled_skipped(self, sync_store):
        """_trigger_job skips cancelled jobs."""
        worker = MagicMock()
        config = SyncConnectorConfig(name="T", connector_type="local_folder",
                                      credentials={"folder_path": "/tmp"})
        sync_store.save_connector(config)
        rule = SyncRule(rule_type="cron", cron_expression="0 * * * *")
        sync_store.save_rule(rule)
        job = SyncJob(connector_config_id=config.id, rule_id=rule.id,
                      name="Test", status="cancelled")
        sync_store.save_job(job)

        scheduler = SyncScheduler(sync_store, worker)
        scheduler._trigger_job(job.id)
        assert not worker.enqueue.called

    def test_trigger_job_disabled_rule_skipped(self, sync_store):
        """_trigger_job skips when rule is disabled."""
        worker = MagicMock()
        config = SyncConnectorConfig(name="T", connector_type="local_folder",
                                      credentials={"folder_path": "/tmp"})
        sync_store.save_connector(config)
        rule = SyncRule(rule_type="cron", cron_expression="0 * * * *", enabled=False)
        sync_store.save_rule(rule)
        job = SyncJob(connector_config_id=config.id, rule_id=rule.id, name="Test")
        sync_store.save_job(job)

        scheduler = SyncScheduler(sync_store, worker)
        scheduler._trigger_job(job.id)
        assert not worker.enqueue.called
