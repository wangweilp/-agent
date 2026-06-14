"""Sandbox v2 Queue Protocol — 任务队列抽象接口。

定义 SandboxQueue Protocol，便于后续替换为 Redis/Celery。
队列只负责调度，不执行 job。

安全约束：
- 队列不能执行 job，只负责调度
- 所有 job 执行必须经过 policy_engine
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from src.open_platform.sandbox_v2.models import (
    SandboxQueueItem,
    SandboxWorkerHeartbeat,
)


@runtime_checkable
class SandboxQueue(Protocol):
    """Sandbox v2 队列 Protocol。

    支持 lease 机制、retry、dead letter、expired lease 回收。
    当前默认实现：src/adapters/sqlite_sandbox_v2_queue.py
    """

    def enqueue(
        self,
        job_id: str,
        organization_id: str = "",
        workspace_id: str = "",
        priority: int = 100,
        max_attempts: int = 3,
    ) -> SandboxQueueItem:
        """入队一个 job。"""
        ...

    def lease_next(self, worker_id: str, lease_seconds: int = 60) -> SandboxQueueItem | None:
        """租约下一个可用的队列项，防止多 worker 竞争。"""
        ...

    def acknowledge(self, queue_id: str) -> None:
        """确认任务完成，标记为 completed。"""
        ...

    def fail(
        self,
        queue_id: str,
        reason: str = "",
        retry: bool = True,
    ) -> SandboxQueueItem | None:
        """标记任务失败。retry=True 且未超过 max_attempts 时重新入队。"""
        ...

    def cancel(self, job_id: str, reason: str = "") -> SandboxQueueItem | None:
        """取消队列中的任务。"""
        ...

    def heartbeat(
        self,
        worker_id: str,
        current_job_id: str = "",
    ) -> SandboxWorkerHeartbeat:
        """记录 worker 心跳。"""
        ...

    def list_queue(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[SandboxQueueItem]:
        """列出队列项。"""
        ...

    def get_queue_item(self, queue_id: str) -> SandboxQueueItem | None:
        """按 queue_id 查询队列项。"""
        ...

    def get_queue_item_by_job_id(self, job_id: str) -> SandboxQueueItem | None:
        """按 job_id 查询队列项。"""
        ...

    def requeue_expired_leases(self, now: datetime | None = None) -> int:
        """回收过期的 lease，返回回收数量。"""
        ...

    def move_to_dead_letter(self, queue_id: str, reason: str) -> SandboxQueueItem | None:
        """将任务移入 dead letter。"""
        ...

    def list_dead_letter(self, limit: int = 50) -> list[SandboxQueueItem]:
        """列出 dead letter 项。"""
        ...

    def list_workers(self, limit: int = 50) -> list[SandboxWorkerHeartbeat]:
        """列出 worker 心跳记录。"""
        ...

    def update_queue_status(self, queue_id: str, status: str) -> SandboxQueueItem | None:
        """更新队列项状态。"""
        ...
