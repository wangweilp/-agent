"""Memory Write Queue — 独立的异步记忆写入线程。

架构：
    主线程 enqueue → Worker 线程（自有 SQLite 连接）→ SQLite + ChromaDB
                                                    └→ 失败 → Dead Letter Queue

与 _fire_and_forget_remember 的关键区别：
    1. Worker 不共享主线程的 SQLite connection，彻底消除跨线程错误
    2. 所有向量/结构化写入串行化，ChromaDB 无并发冲突
    3. 失败写入 Dead Letter Queue（JSON 文件），可重试
    4. Tool Response 用"已接受"而非"已存储"，不伪造成功状态
"""
import json
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.adapters.config import Settings
from src.core.types import ToolResult

logger = logging.getLogger(__name__)

_DEAD_LETTER_DIR = "./data/dead_letter"


@dataclass
class MemoryWriteTask:
    arguments: dict[str, Any]
    call_id: str = ""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    submitted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    retry_count: int = 0
    status: str = "pending"  # pending → processing → stored / failed


class MemoryWriteWorker(threading.Thread):
    """独立写入线程，拥有自己的 SQLite 连接。

    单线程串行写入 = 无锁 = 无跨线程错误。
    """

    def __init__(
        self,
        settings: Settings,
        *,
        embedding_provider: object | None = None,
        dead_letter_dir: str = _DEAD_LETTER_DIR,
    ) -> None:
        super().__init__(daemon=True, name="memory-writer")
        self._queue: queue.Queue[MemoryWriteTask | None] = queue.Queue()
        self._settings = settings
        self._shared_embedding = embedding_provider
        self._dead_letter_dir = Path(dead_letter_dir)
        self._running = False
        # Runtime stats
        self._started_at: str = ""
        self._lock = threading.Lock()
        self._failed_count: int = 0
        self._stored_count: int = 0
        self._history: list[dict[str, Any]] = []  # 最近 50 条任务记录
        self._max_history = 50

    # ── 公共 API ──

    def enqueue(self, task: MemoryWriteTask) -> None:
        self._queue.put(task)

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def shutdown(self, timeout: float = 5.0) -> None:
        self._queue.put(None)  # sentinel
        self.join(timeout=timeout)
        logger.info("memory_worker_shutdown", extra={"pending": self.pending})

    # ── 线程主循环 ──

    def run(self) -> None:
        self._running = True
        self._dead_letter_dir.mkdir(parents=True, exist_ok=True)

        # 在 Worker 线程内创建自己的连接，不与主线程共享
        # embedding 复用主线程实例（SentenceTransformer 推理线程安全）
        from src.adapters.embedding import LocalEmbeddingProvider
        from src.adapters.sqlite_store import SQLiteStoreAdapter
        from src.adapters.vector_store import ChromaDBAdapter

        try:
            sqlite = SQLiteStoreAdapter(self._settings)
            chroma = ChromaDBAdapter(self._settings)
            embedding = (
                self._shared_embedding
                if self._shared_embedding is not None
                else LocalEmbeddingProvider(self._settings)
            )
        except Exception:
            logger.exception("memory_worker_init_failed")
            return

        logger.info("memory_worker_started")
        self._started_at = datetime.now(timezone.utc).isoformat()

        while self._running:
            try:
                item = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if item is None:  # shutdown sentinel
                break

            self._process(item, sqlite, chroma, embedding)

        # 关闭自己的连接
        try:
            sqlite.close()
            chroma.close()
            embedding.close()
        except Exception:
            logger.debug("memory_worker_cleanup_error", exc_info=True)

    # ── 内部 ──

    def _process(
        self,
        task: MemoryWriteTask,
        sqlite: Any,
        chroma: Any,
        embedding: Any,
    ) -> None:
        from src.tools.remember import RememberTool

        task.status = "processing"
        t0 = time.monotonic()

        tool = RememberTool(sqlite, chroma, embedding)
        try:
            result = tool.execute(task.arguments)
        except Exception:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            task.status = "failed"
            with self._lock:
                self._failed_count += 1
            logger.exception(
                "memory_write_crashed",
                extra={
                    "task_id": task.task_id,
                    "call_id": task.call_id,
                    "elapsed_ms": elapsed_ms,
                    "queue_depth": self.pending,
                },
            )
            self._write_dead_letter(task)
            self._record_history(task, elapsed_ms)
            return

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if not result.success:
            task.status = "failed"
            with self._lock:
                self._failed_count += 1
            logger.warning(
                "memory_write_returned_failure",
                extra={
                    "task_id": task.task_id,
                    "call_id": task.call_id,
                    "error": result.error,
                    "elapsed_ms": elapsed_ms,
                },
            )
            self._write_dead_letter(task)
            self._record_history(task, elapsed_ms)
            return

        task.status = "stored"
        with self._lock:
            self._stored_count += 1
        logger.info(
            "memory_write_ok",
            extra={
                "task_id": task.task_id,
                "call_id": task.call_id,
                "memory_id": result.metadata.get("memory_id", ""),
                "elapsed_ms": elapsed_ms,
                "queue_depth": self.pending,
            },
        )
        self._record_history(task, elapsed_ms)

    def _write_dead_letter(self, task: MemoryWriteTask) -> None:
        task.retry_count += 1
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = f"memory_{ts}_r{task.retry_count}.json"
        path = self._dead_letter_dir / filename
        try:
            path.write_text(
                json.dumps(
                    {
                        "task_id": task.task_id,
                        "call_id": task.call_id,
                        "status": task.status,
                        "arguments": task.arguments,
                        "submitted_at": task.submitted_at,
                        "failed_at": datetime.now(timezone.utc).isoformat(),
                        "retry_count": task.retry_count,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            logger.info("dead_letter_written", extra={"path": str(path)})
        except Exception:
            logger.exception("dead_letter_write_failed")

    def _record_history(self, task: MemoryWriteTask, elapsed_ms: int) -> None:
        entry = {
            "task_id": task.task_id,
            "call_id": task.call_id,
            "status": task.status,
            "content_preview": task.arguments.get("content", "")[:80],
            "elapsed_ms": elapsed_ms,
            "submitted_at": task.submitted_at,
        }
        with self._lock:
            self._history.append(entry)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

    # ── Runtime Stats ──

    @property
    def stats(self) -> dict[str, Any]:
        dlq_count = 0
        try:
            if self._dead_letter_dir.exists():
                dlq_count = len(list(self._dead_letter_dir.glob("memory_*.json")))
        except Exception:
            pass

        with self._lock:
            return {
                "worker": {
                    "alive": self.is_alive(),
                    "started_at": self._started_at,
                    "uptime_seconds": (
                        int((datetime.now(timezone.utc) - datetime.fromisoformat(self._started_at)).total_seconds())
                        if self._started_at else 0
                    ),
                },
                "queue": {
                    "pending": self.pending,
                    "total_stored": self._stored_count,
                    "total_failed": self._failed_count,
                },
                "dead_letter": {
                    "count": dlq_count,
                    "dir": str(self._dead_letter_dir),
                },
                "recent_tasks": list(self._history[-20:]),
            }

    @property
    def alerts(self) -> list[dict[str, Any]]:
        """生成实时告警 JSON。

        检查阈值：
          - DLQ 累积 >= 5 条
          - 队列积压 >= 10 条
          - 最近 10 条任务失败率 >= 30%
        """
        dlq_count = 0
        try:
            if self._dead_letter_dir.exists():
                dlq_count = len(list(self._dead_letter_dir.glob("memory_*.json")))
        except Exception:
            pass

        result: list[dict[str, Any]] = []

        if dlq_count >= 5:
            result.append({
                "level": "warning",
                "type": "dlq_accumulation",
                "message": f"Dead Letter Queue 积压 {dlq_count} 条，请检查 Worker 日志",
                "threshold": 5,
                "current": dlq_count,
            })

        if self.pending >= 10:
            result.append({
                "level": "warning",
                "type": "queue_congestion",
                "message": f"写入队列积压 {self.pending} 条，可能影响响应延迟",
                "threshold": 10,
                "current": self.pending,
            })

        with self._lock:
            recent = list(self._history[-10:])
        if recent:
            failed_in_window = sum(1 for t in recent if t["status"] == "failed")
            fail_rate = failed_in_window / len(recent)
            if fail_rate >= 0.3:
                result.append({
                    "level": "critical",
                    "type": "high_failure_rate",
                    "message": f"最近 {len(recent)} 条任务失败率 {fail_rate:.0%}，需立即排查",
                    "threshold": 0.3,
                    "current": round(fail_rate, 2),
                    "failed_count": failed_in_window,
                    "window_size": len(recent),
                })

        return result
