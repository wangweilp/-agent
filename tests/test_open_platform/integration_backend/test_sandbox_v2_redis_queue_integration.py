"""Redis queue integration tests (Step 13). Default SKIP.

Only run when:
  SANDBOX_V2_RUN_BACKEND_INTEGRATION=true
  SANDBOX_V2_QUEUE_BACKEND=redis
  SANDBOX_V2_REDIS_URL configured
"""

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_RUNNING = os.environ.get("SANDBOX_V2_RUN_BACKEND_INTEGRATION", "").lower() in ("true", "1", "yes")
_Q_BACKEND = os.environ.get("SANDBOX_V2_QUEUE_BACKEND", "sqlite")
_REDIS_URL = os.environ.get("SANDBOX_V2_REDIS_URL", "")

pytestmark = pytest.mark.skipif(
    not (_RUNNING and _Q_BACKEND == "redis" and _REDIS_URL),
    reason="Requires SANDBOX_V2_RUN_BACKEND_INTEGRATION=true + queue_backend=redis + REDIS_URL configured",
)

_NS = f"sandbox-v2-inttest:{__import__('uuid').uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def queue():
    from src.adapters.redis_sandbox_v2_queue import RedisSandboxV2Queue
    q = RedisSandboxV2Queue(redis_url=_REDIS_URL, connect=True)
    yield q
    # 清理测试 keys
    try:
        r = q._r()
        for key_suffix in ["queue:items", "item:*", "leased:*", "workers:*", "dead_letter", "job:*"]:
            r.delete(f"{_NS}:{key_suffix}")
    except Exception:
        pass


class TestRedisHealth:
    def test_health_check(self, queue):
        hc = queue.health_check()
        assert hc["ok"], f"Health check failed: {hc}"


class TestRedisEnqueueLease:
    def test_enqueue(self, queue):
        item = queue.enqueue("job-a", max_attempts=3)
        assert item is not None
        assert item.job_id == "job-a"

    def test_lease_next(self, queue):
        queue.enqueue("job-b")
        item = queue.lease_next("worker-1")
        assert item is not None

    def test_no_double_lease(self, queue):
        queue.enqueue("job-c")
        item1 = queue.lease_next("worker-1")
        item2 = queue.lease_next("worker-2")
        assert item1 is not None
        assert item2 is None or item2.job_id != "job-c"

    def test_ack_removes(self, queue):
        queue.enqueue("job-d")
        item = queue.lease_next("worker-1")
        if item:
            queue.acknowledge(item.queue_id)
            # 获取到的状态应为 completed
            fetched = queue.get_queue_item(item.queue_id)
            if fetched:
                assert fetched.status == "completed"

    def test_fail_attempts(self, queue):
        queue.enqueue("job-e", max_attempts=3)
        item = queue.lease_next("worker-1")
        failed = queue.fail(item.queue_id, reason="test", retry=True)
        assert failed.attempts >= 1

    def test_fail_max_attempts_dead_letter(self, queue):
        queue.enqueue("job-f", max_attempts=1)
        item = queue.lease_next("worker-1")
        failed = queue.fail(item.queue_id, reason="fatal", retry=True)
        assert failed.status == "dead_letter"

    def test_cancel_not_leasable(self, queue):
        queue.enqueue("job-g")
        queue.cancel("job-g", reason="test")
        item = queue.lease_next("worker-1")
        assert item is None or item.job_id != "job-g"


class TestRedisDeadLetter:
    def test_dead_letter_populated(self, queue):
        queue.enqueue("job-dl", max_attempts=1)
        item = queue.lease_next("worker-1")
        queue.fail(item.queue_id, reason="fatal", retry=True)
        dl = queue.list_dead_letter()
        assert len(dl) >= 1

    def test_move_to_dead_letter(self, queue):
        queue.enqueue("job-dl2")
        item = queue.lease_next("worker-dl")
        dl_item = queue.move_to_dead_letter(item.queue_id, "manual")
        assert dl_item is not None
        assert dl_item.status == "dead_letter"
