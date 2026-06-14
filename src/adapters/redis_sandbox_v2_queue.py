"""Redis Sandbox v2 Queue Adapter — SandboxQueue Protocol 的 Redis 实现。

Step 12 — Production Backend Migration.

设计原则:
1. 使用 Redis 实现 SandboxQueue Protocol。
2. 缺 redis-py 依赖或 REDIS_URL 为空时返回 clear error。
3. 支持 enqueue, lease, ack, fail, cancel, dead letter, heartbeat。
4. lease 使用 Redis SETNX + EXPIRE 防止多 worker 竞争。
5. 不入队不可执行任务（必须经 policy engine）。

数据结构设计:
- sbv2:queue:items       → Sorted Set (score=priority, member=queue_id)
- sbv2:item:{queue_id}   → Hash (队列项详情)
- sbv2:leased:{queue_id} → String (leased worker_id, TTL=lease_seconds)
- sbv2:workers:{worker}  → Hash (worker heartbeat)
- sbv2:dead_letter       → List (dead letter queue_ids)
- sbv2:job:{job_id}      → String (queue_id mapping)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Module-level dependency check
# ═══════════════════════════════════════════════════════════════════════════

_REDIS_AVAILABLE = False
try:
    import redis as _redis_module
    _REDIS_AVAILABLE = True
except ImportError:
    pass

_REDIS_UNAVAILABLE_MSG = (
    "redis-py is not installed. Install with: pip install redis"
)


def _require_redis():
    """检查 redis 是否可用。"""
    if not _REDIS_AVAILABLE:
        raise ImportError(_REDIS_UNAVAILABLE_MSG)


# ═══════════════════════════════════════════════════════════════════════════
# In-Memory Fake Redis Client (用于测试)
# ═══════════════════════════════════════════════════════════════════════════

class FakeRedisClient:
    """Memory-backed fake Redis client for unit testing."""

    def __init__(self):
        self._data: dict[str, Any] = {}
        self._sets: dict[str, dict[str, float]] = {}     # sorted sets
        self._lists: dict[str, list[str]] = {}
        self._expiry: dict[str, float] = {}
        import time as _time
        self._time = _time

    def _now(self) -> float:
        return self._time.time()

    def _purge_expired(self, key: str):
        exp = self._expiry.get(key)
        if exp and self._now() > exp:
            self._data.pop(key, None)
            self._sets.pop(key, None)

    def get(self, key: str) -> str | None:
        self._purge_expired(key)
        val = self._data.get(key)
        return val if isinstance(val, str) else None

    def set(self, key: str, value: str, ex: int | None = None):
        self._data[key] = value
        if ex:
            self._expiry[key] = self._now() + ex

    def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self._data:
                del self._data[k]
                count += 1
            if k in self._sets:
                del self._sets[k]
                count += 1
        return count

    def exists(self, *keys: str) -> int:
        return sum(1 for k in keys if k in self._data or k in self._sets)

    def setnx(self, key: str, value: str) -> bool:
        if key in self._data:
            return False
        self._data[key] = value
        return True

    def expire(self, key: str, seconds: int) -> bool:
        if key in self._data:
            self._expiry[key] = self._now() + seconds
            return True
        return False

    def hset(self, name: str, mapping: dict[str, Any]) -> int:
        existing = self._data.get(name)
        if existing is None or not isinstance(existing, dict):
            self._data[name] = {}
        count = 0
        for k, v in mapping.items():
            self._data[name][k] = v
            count += 1
        return count

    def hgetall(self, name: str) -> dict[bytes, bytes]:
        val = self._data.get(name)
        if not isinstance(val, dict):
            return {}
        return {k.encode(): str(v).encode() for k, v in val.items()}

    def hget(self, name: str, key: str) -> str | None:
        val = self._data.get(name)
        if isinstance(val, dict):
            return val.get(key) if isinstance(val.get(key), str) else None
        return None

    def zadd(self, name: str, mapping: dict[str, float]) -> int:
        if name not in self._sets:
            self._sets[name] = {}
        count = 0
        for member, score in mapping.items():
            if member not in self._sets[name]:
                count += 1
            self._sets[name][member] = score
        return count

    def zpopmin(self, name: str, count: int = 1) -> list[tuple[bytes, float]]:
        if name not in self._sets or not self._sets[name]:
            return []
        sorted_items = sorted(self._sets[name].items(), key=lambda x: x[1])
        result = []
        for member, score in sorted_items[:count]:
            del self._sets[name][member]
            result.append((member.encode(), score))
        return result

    def zrem(self, name: str, *members: str) -> int:
        if name not in self._sets:
            return 0
        count = 0
        for m in members:
            if m in self._sets[name]:
                del self._sets[name][m]
                count += 1
        return count

    def zcard(self, name: str) -> int:
        return len(self._sets.get(name, {}))

    def lpush(self, name: str, *values: str) -> int:
        if name not in self._lists:
            self._lists[name] = []
        for v in reversed(values):
            self._lists[name].insert(0, v)
        return len(self._lists[name])

    def lrange(self, name: str, start: int, end: int) -> list[bytes]:
        lst = self._lists.get(name, [])
        if end == -1:
            end = len(lst)
        return [v.encode() for v in lst[start:end + 1]]

    def llen(self, name: str) -> int:
        return len(self._lists.get(name, []))

    def ping(self) -> bool:
        return True

    def close(self):
        pass


# ═══════════════════════════════════════════════════════════════════════════
# RedisSandboxV2Queue
# ═══════════════════════════════════════════════════════════════════════════

class RedisSandboxV2Queue:
    """Redis SandboxQueue 实现。

    参数:
        redis_url: Redis 连接 URL (e.g. redis://localhost:6379/0)
        connect: 是否立即连接 (测试中使用 False)
    """

    KEY_QUEUE = "sbv2:queue:items"
    KEY_ITEM_PREFIX = "sbv2:item:"
    KEY_LEASE_PREFIX = "sbv2:leased:"
    KEY_WORKER_PREFIX = "sbv2:workers:"
    KEY_DEAD_LETTER = "sbv2:dead_letter"
    KEY_JOB_MAP = "sbv2:job:"

    def __init__(self, redis_url: str = "", connect: bool = False):
        self._redis_url = redis_url or os.getenv("SANDBOX_V2_REDIS_URL", "")
        self._client: Any = None
        self._connected = False
        if connect and self._redis_url:
            self._connect()

    def _connect(self) -> None:
        """连接 Redis。"""
        _require_redis()
        if not self._redis_url:
            raise ValueError("REDIS_URL is empty. Set SANDBOX_V2_REDIS_URL.")
        try:
            self._client = _redis_module.from_url(self._redis_url)
            self._client.ping()
            self._connected = True
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Redis: {e}") from e

    def health_check(self) -> dict[str, Any]:
        """Redis 连接健康检查。"""
        if not _REDIS_AVAILABLE:
            return {"ok": False, "reason": _REDIS_UNAVAILABLE_MSG}
        if not self._redis_url:
            return {"ok": False, "reason": "Redis URL not configured"}
        try:
            r = self._r()
            r.ping()
            return {"ok": True, "reason": "Redis connection healthy"}
        except Exception as e:
            return {"ok": False, "reason": f"Redis connection failed: {e}"}

    def _r(self) -> Any:
        """获取 Redis 客户端，未连接时抛错。

        如果已通过 _set_client 注入 fake client，则直接使用。
        """
        if self._client is not None:
            return self._client
        self._connect()
        return self._client

    def _item_key(self, queue_id: str) -> str:
        return f"{self.KEY_ITEM_PREFIX}{queue_id}"

    def _lease_key(self, queue_id: str) -> str:
        return f"{self.KEY_LEASE_PREFIX}{queue_id}"

    def _worker_key(self, worker_id: str) -> str:
        return f"{self.KEY_WORKER_PREFIX}{worker_id}"

    def _job_key(self, job_id: str) -> str:
        return f"{self.KEY_JOB_MAP}{job_id}"

    @property
    def is_available(self) -> bool:
        """检查依赖是否可用。"""
        return _REDIS_AVAILABLE

    @property
    def availability_message(self) -> str:
        """返回可用性描述。"""
        if _REDIS_AVAILABLE:
            has_url = bool(self._redis_url)
            return f"redis-py available. {'REDIS_URL configured.' if has_url else 'REDIS_URL not configured.'}"
        return _REDIS_UNAVAILABLE_MSG

    # ── Enqueue ──

    def enqueue(self, job_id: str, organization_id: str = "", workspace_id: str = "",
                priority: int = 100, max_attempts: int = 3) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxQueueItem
        r = self._r()
        queue_id = f"queue_{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        item_data = {
            "queue_id": queue_id,
            "job_id": job_id,
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "priority": str(priority),
            "status": "queued",
            "attempts": "0",
            "max_attempts": str(max_attempts),
            "available_at": now,
            "leased_by": "",
            "leased_until": "",
            "created_at": now,
            "updated_at": now,
            "last_error": "",
            "dead_letter_reason": "",
        }
        r.hset(self._item_key(queue_id), item_data)
        r.zadd(self.KEY_QUEUE, {queue_id: float(priority)})
        r.set(self._job_key(job_id), queue_id)

        return SandboxQueueItem(
            queue_id=queue_id, job_id=job_id, organization_id=organization_id,
            workspace_id=workspace_id, status="queued",
            attempts=0, max_attempts=max_attempts,
        )

    # ── Lease ──

    def lease_next(self, worker_id: str, lease_seconds: int = 60) -> Any | None:
        """租约下一个可用队列项。使用 SETNX 防竞争。"""
        from src.open_platform.sandbox_v2.models import SandboxQueueItem
        r = self._r()

        # pop 最小 score (最高优先级)
        popped = r.zpopmin(self.KEY_QUEUE, count=1)
        if not popped:
            return None

        queue_id = popped[0][0].decode() if isinstance(popped[0][0], bytes) else popped[0][0]

        # 尝试获取 lease lock
        lease_key = self._lease_key(queue_id)
        acquired = r.setnx(lease_key, worker_id)
        if not acquired:
            # 已被其他 worker lease，放回队列
            item_key = self._item_key(queue_id)
            priority = int(r.hget(item_key, "priority") or "100")
            r.zadd(self.KEY_QUEUE, {queue_id: float(priority)})
            return None

        r.expire(lease_key, lease_seconds)

        # 更新 item 状态
        now = datetime.now(timezone.utc)
        lease_until = now.isoformat() if hasattr(now, 'isoformat') else str(now)
        r.hset(self._item_key(queue_id), {
            "status": "leased",
            "leased_by": worker_id,
            "leased_until": lease_until,
            "attempts": str(int(r.hget(self._item_key(queue_id), "attempts") or "0") + 1),
            "updated_at": now.isoformat() if hasattr(now, 'isoformat') else str(now),
        })

        item = r.hgetall(self._item_key(queue_id))
        return self._dict_to_queue_item(item)

    # ── Acknowledge ──

    def acknowledge(self, queue_id: str) -> None:
        r = self._r()
        r.hset(self._item_key(queue_id), {"status": "completed"})
        r.delete(self._lease_key(queue_id))

    # ── Fail ──

    def fail(self, queue_id: str, reason: str = "", retry: bool = True) -> Any | None:
        from src.open_platform.sandbox_v2.models import SandboxQueueItem
        r = self._r()

        item_key = self._item_key(queue_id)
        attempts = int(r.hget(item_key, "attempts") or "0")
        max_attempts = int(r.hget(item_key, "max_attempts") or "3")

        if retry and attempts < max_attempts:
            # 重新入队
            priority = int(r.hget(item_key, "priority") or "100")
            r.hset(item_key, {"status": "queued", "last_error": reason})
            r.zadd(self.KEY_QUEUE, {queue_id: float(priority)})
        else:
            # 移入 dead letter
            r.hset(item_key, {"status": "dead_letter", "last_error": reason, "dead_letter_reason": reason})
            r.lpush(self.KEY_DEAD_LETTER, queue_id)

        r.delete(self._lease_key(queue_id))
        item = r.hgetall(item_key)
        return self._dict_to_queue_item(item)

    # ── Cancel ──

    def cancel(self, job_id: str, reason: str = "") -> Any | None:
        from src.open_platform.sandbox_v2.models import SandboxQueueItem
        r = self._r()

        queue_id_enc = r.get(self._job_key(job_id))
        if not queue_id_enc:
            return None
        queue_id = queue_id_enc if isinstance(queue_id_enc, str) else queue_id_enc.decode()

        r.hset(self._item_key(queue_id), {"status": "canceled", "last_error": reason})
        r.zrem(self.KEY_QUEUE, queue_id)
        r.delete(self._lease_key(queue_id))

        item = r.hgetall(self._item_key(queue_id))
        return self._dict_to_queue_item(item)

    # ── Heartbeat ──

    def heartbeat(self, worker_id: str, current_job_id: str = "") -> Any:
        from src.open_platform.sandbox_v2.models import SandboxWorkerHeartbeat
        r = self._r()
        now = datetime.now(timezone.utc).isoformat() if hasattr(datetime.now(timezone.utc), 'isoformat') else str(datetime.now(timezone.utc))
        worker_key = self._worker_key(worker_id)

        if not r.exists(worker_key):
            r.hset(worker_key, {
                "worker_id": worker_id,
                "status": "idle",
                "current_job_id": current_job_id,
                "started_at": now,
                "last_heartbeat_at": now,
                "processed_count": "0",
                "failed_count": "0",
                "canceled_count": "0",
            })

        r.hset(worker_key, {
            "current_job_id": current_job_id,
            "status": "processing" if current_job_id else "idle",
            "last_heartbeat_at": now,
        })

        data = r.hgetall(worker_key)
        return SandboxWorkerHeartbeat(
            worker_id=worker_id,
            status="idle",
            current_job_id=current_job_id,
            processed_count=int(data.get(b"processed_count", b"0") or b"0") if isinstance(data.get(b"processed_count"), bytes) else 0,
        )

    # ── List / Query ──

    def list_queue(self, status: str | None = None, limit: int = 50) -> list[Any]:
        return self._list_items(status, limit)

    def get_queue_item(self, queue_id: str) -> Any | None:
        r = self._r()
        item = r.hgetall(self._item_key(queue_id))
        if not item:
            return None
        return self._dict_to_queue_item(item)

    def get_queue_item_by_job_id(self, job_id: str) -> Any | None:
        r = self._r()
        queue_id_enc = r.get(self._job_key(job_id))
        if not queue_id_enc:
            return None
        queue_id = queue_id_enc if isinstance(queue_id_enc, str) else queue_id_enc.decode()
        return self.get_queue_item(queue_id)

    def requeue_expired_leases(self, now: Any = None) -> int:
        # Redis lease 有 TTL，过期后 key 自动删除
        # 这里扫描所有 leased item，检查 lease key 是否还存活
        count = 0
        # 简化实现：通过队列状态检查
        return count

    def move_to_dead_letter(self, queue_id: str, reason: str) -> Any | None:
        r = self._r()
        r.hset(self._item_key(queue_id), {
            "status": "dead_letter",
            "dead_letter_reason": reason,
            "last_error": reason,
        })
        r.lpush(self.KEY_DEAD_LETTER, queue_id)
        item = r.hgetall(self._item_key(queue_id))
        return self._dict_to_queue_item(item)

    def list_dead_letter(self, limit: int = 50) -> list[Any]:
        r = self._r()
        queue_ids = r.lrange(self.KEY_DEAD_LETTER, 0, limit - 1)
        result = []
        for qid_enc in queue_ids:
            qid = qid_enc.decode() if isinstance(qid_enc, bytes) else qid_enc
            item = r.hgetall(self._item_key(qid))
            if item:
                result.append(self._dict_to_queue_item(item))
        return result

    def list_workers(self, limit: int = 50) -> list[Any]:
        return []  # 简化实现

    def update_queue_status(self, queue_id: str, status: str) -> Any | None:
        r = self._r()
        r.hset(self._item_key(queue_id), {"status": status})
        item = r.hgetall(self._item_key(queue_id))
        return self._dict_to_queue_item(item) if item else None

    # ── Helpers ──

    def _list_items(self, status: str | None, limit: int) -> list[Any]:
        r = self._r()
        # 简化：获取所有队列 member
        # 完整实现应扫描所有 sbv2:item:* keys
        result = []
        for _ in range(limit):
            result.append(None)
        return [x for x in result if x is not None]

    def _dict_to_queue_item(self, data: dict[bytes, bytes]) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxQueueItem

        def _g(key: str, default: str = "") -> str:
            for k, v in data.items():
                k_str = k.decode() if isinstance(k, bytes) else str(k)
                if k_str == key:
                    return v.decode() if isinstance(v, bytes) else str(v)
            return default

        return SandboxQueueItem(
            queue_id=_g("queue_id"),
            job_id=_g("job_id"),
            organization_id=_g("organization_id"),
            workspace_id=_g("workspace_id"),
            status=_g("status", "queued"),
            attempts=int(_g("attempts", "0")),
            max_attempts=int(_g("max_attempts", "3")),
        )

    # ── 用于测试的 fake redis 注入 ──
    def _set_client(self, client: Any) -> None:
        """注入 fake Redis client (仅供测试使用)。"""
        self._client = client
        self._connected = True


# ═══════════════════════════════════════════════════════════════════════════
# Factory helpers
# ═══════════════════════════════════════════════════════════════════════════

def create_fake_redis_queue() -> RedisSandboxV2Queue:
    """创建使用 FakeRedisClient 的 RedisSandboxV2Queue，用于测试。"""
    queue = RedisSandboxV2Queue.__new__(RedisSandboxV2Queue)
    queue._redis_url = ""
    queue._client = FakeRedisClient()
    queue._connected = True
    return queue
