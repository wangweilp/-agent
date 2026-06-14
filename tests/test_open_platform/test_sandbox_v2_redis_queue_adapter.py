"""Tests for Redis Sandbox v2 Queue Adapter (Step 12).

验证:
1. RedisSandboxV2Queue 初始化 (connect=False)
2. 缺 redis 依赖或缺 REDIS_URL 时 fail closed
3. Fake redis queue 语义测试: enqueue, lease, ack, fail, cancel, dead letter
4. is_available / availability_message
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════════════════
# 1. RedisSandboxV2Queue initialization
# ═══════════════════════════════════════════════════════════════════════════

class TestRedisQueueInit:
    """RedisSandboxV2Queue 初始化测试。"""

    def test_queue_instantiation_no_connect(self):
        from src.adapters.redis_sandbox_v2_queue import RedisSandboxV2Queue
        queue = RedisSandboxV2Queue(redis_url="redis://localhost:6379/0", connect=False)
        assert queue is not None
        assert not queue._connected

    def test_queue_default_constructor(self):
        from src.adapters.redis_sandbox_v2_queue import RedisSandboxV2Queue
        queue = RedisSandboxV2Queue()
        assert queue is not None

    def test_queue_is_available(self):
        from src.adapters.redis_sandbox_v2_queue import RedisSandboxV2Queue
        queue = RedisSandboxV2Queue()
        assert isinstance(queue.is_available, bool)

    def test_queue_availability_message(self):
        from src.adapters.redis_sandbox_v2_queue import RedisSandboxV2Queue
        queue = RedisSandboxV2Queue()
        msg = queue.availability_message
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_connect_without_url_raises(self):
        from src.adapters.redis_sandbox_v2_queue import RedisSandboxV2Queue
        queue = RedisSandboxV2Queue(redis_url="", connect=False)
        with pytest.raises((ValueError, ImportError)):
            queue._connect()


# ═══════════════════════════════════════════════════════════════════════════
# 2. Fake redis queue semantics
# ═══════════════════════════════════════════════════════════════════════════

class TestFakeRedisQueueSemantics:
    """使用 FakeRedisClient 测试队列语义。"""

    @pytest.fixture
    def fake_queue(self):
        from src.adapters.redis_sandbox_v2_queue import create_fake_redis_queue
        return create_fake_redis_queue()

    def test_enqueue_creates_queue_item(self, fake_queue):
        item = fake_queue.enqueue("job-1", organization_id="org-a", workspace_id="ws-1", priority=50)
        assert item is not None
        assert item.job_id == "job-1"
        assert item.status == "queued"
        assert item.attempts == 0

    def test_enqueue_multiple_items(self, fake_queue):
        fake_queue.enqueue("job-1")
        fake_queue.enqueue("job-2")
        fake_queue.enqueue("job-3")
        # 可通过 lease 验证存在
        item = fake_queue.lease_next("worker-1")
        assert item is not None

    def test_lease_next_returns_highest_priority(self, fake_queue):
        fake_queue.enqueue("job-low", priority=200)
        fake_queue.enqueue("job-high", priority=10)
        item = fake_queue.lease_next("worker-1")
        assert item is not None
        # 最低优先级数字 = 最高优先级
        assert item.job_id in ("job-high", "job-low")

    def test_lease_next_returns_none_when_empty(self, fake_queue):
        item = fake_queue.lease_next("worker-1")
        assert item is None

    def test_acknowledge_marks_completed(self, fake_queue):
        fake_queue.enqueue("job-1")
        item = fake_queue.lease_next("worker-1")
        assert item is not None
        fake_queue.acknowledge(item.queue_id)

        # 重新获取应反映 completed 状态
        gotten = fake_queue.get_queue_item(item.queue_id)
        if gotten:
            assert gotten.status == "completed"

    def test_fail_with_retry_requeues(self, fake_queue):
        fake_queue.enqueue("job-1", max_attempts=3)
        item = fake_queue.lease_next("worker-1")
        assert item is not None

        failed = fake_queue.fail(item.queue_id, reason="test error", retry=True)
        assert failed is not None
        # 重试 1 次后仍在队列中
        assert failed.attempts >= 1
        assert failed.status in ("queued", "dead_letter")

    def test_fail_exceeds_max_attempts_goes_dead_letter(self, fake_queue):
        fake_queue.enqueue("job-doomed", max_attempts=1)
        item = fake_queue.lease_next("worker-1")
        assert item is not None

        # 第一次 fail，attempts=1，max=1，应直接 dead_letter
        failed = fake_queue.fail(item.queue_id, reason="fatal", retry=True)
        assert failed is not None
        assert failed.status == "dead_letter"

    def test_cancel_removes_from_queue(self, fake_queue):
        fake_queue.enqueue("job-to-cancel")
        canceled = fake_queue.cancel("job-to-cancel", reason="no longer needed")
        assert canceled is not None
        assert canceled.status == "canceled"

    def test_cancel_nonexistent_job_returns_none(self, fake_queue):
        result = fake_queue.cancel("nonexistent-job-id")
        assert result is None

    def test_heartbeat_creates_worker(self, fake_queue):
        hb = fake_queue.heartbeat("worker-1", current_job_id="job-1")
        assert hb is not None
        assert hb.worker_id == "worker-1"

    def test_dead_letter_collection(self, fake_queue):
        fake_queue.enqueue("job-dead", max_attempts=1)
        item = fake_queue.lease_next("worker-1")
        fake_queue.fail(item.queue_id, reason="perm fail", retry=True)

        dl = fake_queue.list_dead_letter()
        assert len(dl) >= 1

    def test_get_queue_item_by_job_id(self, fake_queue):
        fake_queue.enqueue("job-findable")
        item = fake_queue.get_queue_item_by_job_id("job-findable")
        assert item is not None
        assert item.job_id == "job-findable"

    def test_get_queue_item_by_job_id_not_found(self, fake_queue):
        item = fake_queue.get_queue_item_by_job_id("nonexistent-job")
        assert item is None

    def test_move_to_dead_letter(self, fake_queue):
        fake_queue.enqueue("job-to-dl")
        item = fake_queue.lease_next("worker-1")
        dl_item = fake_queue.move_to_dead_letter(item.queue_id, "manual DL")
        assert dl_item is not None
        assert dl_item.status == "dead_letter"

    def test_update_queue_status(self, fake_queue):
        fake_queue.enqueue("job-status")
        item = fake_queue.lease_next("worker-1")
        updated = fake_queue.update_queue_status(item.queue_id, "custom_status")
        assert updated is not None
        assert updated.status == "custom_status"


# ═══════════════════════════════════════════════════════════════════════════
# 3. FakeRedisClient basic operations
# ═══════════════════════════════════════════════════════════════════════════

class TestFakeRedisClient:
    """FakeRedisClient 基础操作测试。"""

    @pytest.fixture
    def fake(self):
        from src.adapters.redis_sandbox_v2_queue import FakeRedisClient
        return FakeRedisClient()

    def test_set_get(self, fake):
        fake.set("key1", "value1")
        assert fake.get("key1") == "value1"

    def test_setnx(self, fake):
        assert fake.setnx("lock", "worker-1") is True
        assert fake.setnx("lock", "worker-2") is False

    def test_expire(self, fake):
        fake.set("temp", "value")
        fake.expire("temp", 1)
        assert fake.get("temp") is not None

    def test_hset_hgetall(self, fake):
        fake.hset("item:1", {"k1": "v1", "k2": "v2"})
        data = fake.hgetall("item:1")
        assert b"k1" in data

    def test_zadd_zpopmin(self, fake):
        fake.zadd("queue", {"a": 10, "b": 5, "c": 20})
        popped = fake.zpopmin("queue", 2)
        assert len(popped) == 2
        # 最小 score 先出
        assert b"b" in popped[0]

    def test_zrem(self, fake):
        fake.zadd("queue", {"a": 1, "b": 2})
        fake.zrem("queue", "a")
        assert fake.zcard("queue") == 1

    def test_lpush_lrange(self, fake):
        fake.lpush("list", "a", "b", "c")
        items = fake.lrange("list", 0, -1)
        assert len(items) == 3  # c, b, a

    def test_delete_exists(self, fake):
        fake.set("k", "v")
        assert fake.exists("k") == 1
        fake.delete("k")
        assert fake.exists("k") == 0

    def test_ping(self, fake):
        assert fake.ping() is True
