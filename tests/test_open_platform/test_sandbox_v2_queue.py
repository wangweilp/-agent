"""Test Sandbox v2 Queue — 队列单元测试。

覆盖：
1. enqueue 后 queue item 状态为 queued
2. lease_next 能租约一个任务
3. acknowledge 后任务 completed
4. fail 后未超过 max_attempts 会重新 queued
5. fail 超过 max_attempts 会进入 dead_letter
6. cancel queued job 后状态 canceled
7. expired lease 可以 requeue
"""
import pytest
import tempfile
import os
from datetime import datetime, timedelta, timezone

from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
from src.open_platform.sandbox_v2.models import (
    SandboxV2QueueStatus,
    SandboxV2WorkerStatus,
)


@pytest.fixture
def queue():
    """创建临时 SQLite queue。"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    settings = Settings()
    q = SQLiteSandboxV2Queue(settings, db_path=db_path)
    yield q
    try:
        os.unlink(db_path)
    except Exception:
        pass


class TestEnqueue:
    def test_enqueue_creates_queued_item(self, queue):
        """enqueue 后 queue item 状态为 queued。"""
        item = queue.enqueue(job_id="job-1")
        assert item is not None
        assert item.status == SandboxV2QueueStatus.QUEUED
        assert item.job_id == "job-1"

    def test_enqueue_idempotent(self, queue):
        """重复 enqueue 返回已有 item。"""
        item1 = queue.enqueue(job_id="job-2")
        item2 = queue.enqueue(job_id="job-2")
        assert item1.queue_id == item2.queue_id


class TestLeaseNext:
    def test_lease_next_gets_item(self, queue):
        """lease_next 能租约一个任务。"""
        queue.enqueue(job_id="job-lease")
        item = queue.lease_next(worker_id="worker-1")
        assert item is not None
        assert item.status == SandboxV2QueueStatus.LEASED
        assert item.leased_by == "worker-1"

    def test_lease_next_returns_none_when_empty(self, queue):
        """空队列返回 None。"""
        item = queue.lease_next(worker_id="worker-1")
        assert item is None

    def test_lease_next_skips_leased_items(self, queue):
        """已租约的 item 不会被重复租约。"""
        queue.enqueue(job_id="job-a")
        queue.enqueue(job_id="job-b")
        item1 = queue.lease_next(worker_id="worker-1")
        item2 = queue.lease_next(worker_id="worker-2")
        assert item1 is not None
        assert item2 is not None
        assert item1.job_id != item2.job_id


class TestAcknowledge:
    def test_acknowledge_completes_item(self, queue):
        """acknowledge 后任务 completed。"""
        queue.enqueue(job_id="job-ack")
        item = queue.lease_next(worker_id="worker-1")
        queue.acknowledge(item.queue_id)
        updated = queue.get_queue_item(item.queue_id)
        assert updated.status == SandboxV2QueueStatus.COMPLETED


class TestFail:
    def test_fail_retry_requeues(self, queue):
        """fail 后未超过 max_attempts 会重新 queued。"""
        queue.enqueue(job_id="job-retry", max_attempts=3)
        item = queue.lease_next(worker_id="worker-1")
        result = queue.fail(item.queue_id, reason="test retry", retry=True)
        assert result is not None
        assert result.status == SandboxV2QueueStatus.QUEUED
        assert result.attempts == 1

    def test_fail_exceeds_max_attempts_dead_letter(self, queue):
        """fail 超过 max_attempts 会进入 dead_letter。"""
        queue.enqueue(job_id="job-dl", max_attempts=1)
        item = queue.lease_next(worker_id="worker-1")
        result = queue.fail(item.queue_id, reason="fatal", retry=True)
        assert result is not None
        assert result.status == SandboxV2QueueStatus.DEAD_LETTER
        assert result.attempts == 1


class TestCancel:
    def test_cancel_queued_job(self, queue):
        """cancel queued job 后状态 canceled。"""
        queue.enqueue(job_id="job-cancel")
        result = queue.cancel(job_id="job-cancel", reason="test cancel")
        assert result is not None
        assert result.status == SandboxV2QueueStatus.CANCELED

    def test_cancel_already_completed_item_not_changed(self, queue):
        """已完成的 item 不会被重新取消。"""
        queue.enqueue(job_id="job-done")
        item = queue.lease_next(worker_id="worker-1")
        queue.acknowledge(item.queue_id)
        result = queue.cancel(job_id="job-done", reason="too late")
        assert result.status == SandboxV2QueueStatus.COMPLETED


class TestRequeueExpired:
    def test_expired_lease_requeue(self, queue):
        """expired lease 可以 requeue。"""
        queue.enqueue(job_id="job-expired")
        item = queue.lease_next(worker_id="worker-1", lease_seconds=1)
        assert item.status == SandboxV2QueueStatus.LEASED

        # 模拟 lease 过期
        future = datetime.now(timezone.utc) + timedelta(seconds=120)
        count = queue.requeue_expired_leases(now=future)
        assert count == 1

        updated = queue.get_queue_item(item.queue_id)
        assert updated.status == SandboxV2QueueStatus.QUEUED

    def test_expired_lease_exceed_max_attempts_dead_letter(self, queue):
        """过期 lease 超过 max_attempts 进入 dead_letter。"""
        queue.enqueue(job_id="job-expired-dl", max_attempts=1)
        item = queue.lease_next(worker_id="worker-1", lease_seconds=1)
        future = datetime.now(timezone.utc) + timedelta(seconds=120)
        count = queue.requeue_expired_leases(now=future)
        assert count == 1
        updated = queue.get_queue_item(item.queue_id)
        assert updated.status == SandboxV2QueueStatus.DEAD_LETTER


class TestHeartbeat:
    def test_heartbeat_creates_record(self, queue):
        """heartbeat 创建 worker 记录。"""
        hb = queue.heartbeat(worker_id="worker-hb")
        assert hb.worker_id == "worker-hb"
        assert hb.status == SandboxV2WorkerStatus.IDLE

    def test_heartbeat_updates_existing(self, queue):
        """heartbeat 更新已有记录。"""
        queue.heartbeat(worker_id="worker-upd", current_job_id="job-1")
        hb2 = queue.heartbeat(worker_id="worker-upd", current_job_id="job-2")
        assert hb2.current_job_id == "job-2"


class TestDeadLetter:
    def test_move_to_dead_letter(self, queue):
        """move_to_dead_letter 正确移入。"""
        queue.enqueue(job_id="job-mv-dl")
        item = queue.lease_next(worker_id="worker-1")
        result = queue.move_to_dead_letter(item.queue_id, reason="manual move")
        assert result.status == SandboxV2QueueStatus.DEAD_LETTER

    def test_list_dead_letter(self, queue):
        """list_dead_letter 正确返回。"""
        queue.enqueue(job_id="job-dl-list", max_attempts=1)
        item = queue.lease_next(worker_id="worker-1")
        queue.fail(item.queue_id, reason="fatal", retry=True)
        items = queue.list_dead_letter()
        assert len(items) >= 1


class TestListQueue:
    def test_list_queue_all(self, queue):
        """列出所有队列项。"""
        queue.enqueue(job_id="job-qa")
        queue.enqueue(job_id="job-qb")
        items = queue.list_queue()
        assert len(items) >= 2

    def test_list_queue_filter_status(self, queue):
        """按状态筛选队列项。"""
        queue.enqueue(job_id="job-qf")
        items = queue.list_queue(status=SandboxV2QueueStatus.QUEUED)
        assert all(i.status == SandboxV2QueueStatus.QUEUED for i in items)
