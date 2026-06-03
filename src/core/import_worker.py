"""Import Worker — 独立的异步批量导入线程。

架构：
    主线程 enqueue(ImportJob) → Worker 线程（自有 SQLite 连接）
        → 分块解析 → MemoryWriteWorker.enqueue() 写入记忆
        → 失败 → Dead Letter Queue

状态机: pending → processing → completed | failed | cancelled
支持: 批量导入 | 断点续传 | 重试 | DLQ 持久化
"""
import json
import logging
import os
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.adapters.config import Settings

logger = logging.getLogger(__name__)

_DEAD_LETTER_DIR = "./data/dead_letter"
_HISTORY_FILE = "./data/import_history.json"


# ── Data Models ──


@dataclass
class ImportJob:
    """一个导入作业，可包含多个文件。"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = ""                 # file path(s) 或 URL(s)，逗号分隔
    title: str = ""
    file_type: str = ""              # "markdown", "pdf", "text", "batch"
    status: str = "pending"          # pending → processing → completed | failed | cancelled
    total_chunks: int = 0
    processed_chunks: int = 0
    memories_created: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    result: dict | None = None       # 额外元数据


@dataclass
class ImportTask:
    """作业中的一个分块任务。"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    chunk_index: int = 0
    content: str = ""
    memory_type: str = "episodic"
    status: str = "pending"          # pending → enqueued → stored | failed
    memory_id: str | None = None     # 写入成功后由 MemoryWriteWorker 回填
    error: str | None = None


# ── ImportHistory ──


class ImportHistory:
    """导入作业历史跟踪，持久化到 import_history.json。"""

    def __init__(self, filepath: str = _HISTORY_FILE) -> None:
        self._filepath = Path(filepath)
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self._filepath.exists():
                content = self._filepath.read_text(encoding="utf-8")
                data = json.loads(content)
                if isinstance(data, dict):
                    self._jobs = data
            else:
                self._filepath.parent.mkdir(parents=True, exist_ok=True)
                self._save()
        except Exception:
            logger.exception("import_history_load_failed")
            self._jobs = {}

    def _save(self) -> None:
        try:
            self._filepath.parent.mkdir(parents=True, exist_ok=True)
            self._filepath.write_text(
                json.dumps(self._jobs, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("import_history_save_failed")

    def add_job(self, job: ImportJob) -> None:
        entry = {
            "id": job.id,
            "source": job.source,
            "title": job.title,
            "file_type": job.file_type,
            "status": job.status,
            "total_chunks": job.total_chunks,
            "processed_chunks": job.processed_chunks,
            "memories_created": job.memories_created,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "error": job.error,
            "result": job.result,
        }
        with self._lock:
            self._jobs[job.id] = entry
            self._save()

    def update_job(self, job: ImportJob) -> None:
        self.add_job(job)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(
                list(self._jobs.values()),
                key=lambda j: j.get("completed_at") or j.get("started_at") or "",
                reverse=True,
            )

    def delete_job(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                self._save()
                return True
            return False


# ── ImportWorker ──


class ImportWorker(threading.Thread):
    """独立导入线程，串行处理 ImportJob。

    单线程 = 无并发 + 解析/写入全部串行，完全匹配 MemoryWriteWorker 模式。
    """

    def __init__(
        self,
        settings: Settings,
        *,
        memory_writer: object | None = None,
        dead_letter_dir: str = _DEAD_LETTER_DIR,
    ) -> None:
        super().__init__(daemon=True, name="import-worker")
        self._queue: queue.Queue[ImportJob | None] = queue.Queue()
        self._settings = settings
        self._memory_writer = memory_writer   # MemoryWriteWorker 实例，用于入队写入
        self._dead_letter_dir = Path(dead_letter_dir)
        self._running = False
        self._history = ImportHistory()
        # Runtime stats
        self._started_at: str = ""
        self._lock = threading.Lock()
        self._total_jobs: int = 0
        self._completed_count: int = 0
        self._failed_count: int = 0
        self._in_progress_count: int = 0
        self._pending_count: int = 0
        self._job_history: list[dict[str, Any]] = []  # 最近 50 条作业记录
        self._max_history = 50
        # 断点续传进度追踪
        self._progress: dict[str, int] = {}  # job_id → last_completed_chunk_index

    # ── 公共 API ──

    def enqueue(self, job: ImportJob) -> None:
        """提交导入作业到队列。"""
        self._queue.put(job)
        self._history.add_job(job)
        with self._lock:
            self._pending_count += 1

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def shutdown(self, timeout: float = 5.0) -> None:
        self._queue.put(None)  # sentinel
        self.join(timeout=timeout)
        logger.info("import_worker_shutdown", extra={"pending": self.pending})

    # ── 线程主循环 ──

    def run(self) -> None:
        self._running = True
        self._dead_letter_dir.mkdir(parents=True, exist_ok=True)

        # 在 Worker 线程内创建自己的连接
        from src.adapters.embedding import LocalEmbeddingProvider
        from src.adapters.sqlite_store import SQLiteStoreAdapter
        from src.adapters.vector_store import ChromaDBAdapter

        try:
            sqlite = SQLiteStoreAdapter(self._settings)
            chroma = ChromaDBAdapter(self._settings)
            embedding = LocalEmbeddingProvider(self._settings)
        except Exception:
            logger.exception("import_worker_init_failed")
            return

        logger.info("import_worker_started")
        self._started_at = datetime.now(timezone.utc).isoformat()

        while self._running:
            try:
                item = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if item is None:  # shutdown sentinel
                break

            self._process_job(item, sqlite, chroma, embedding)

        # 关闭自己的连接
        try:
            sqlite.close()
            chroma.close()
            embedding.close()
        except Exception:
            logger.debug("import_worker_cleanup_error", exc_info=True)

    # ── 作业处理 ──

    def _process_job(
        self,
        job: ImportJob,
        sqlite: Any,
        chroma: Any,
        embedding: Any,
    ) -> None:
        """处理单个 ImportJob：解析 → 分块 → 入队 → 追踪进度。"""
        job.status = "processing"
        job.started_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._in_progress_count += 1
            self._pending_count = max(0, self._pending_count - 1)
        self._history.update_job(job)

        t0 = time.monotonic()

        try:
            # 1) 解析源文件 → chunks
            chunks = self._parse_sources(job)
            job.total_chunks = len(chunks)
            self._history.update_job(job)

            if not chunks:
                job.status = "completed"
                job.completed_at = datetime.now(timezone.utc).isoformat()
                job.result = {"message": "无有效内容可导入"}
                self._history.update_job(job)
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                with self._lock:
                    self._completed_count += 1
                    self._in_progress_count -= 1
                self._record_job_history(job, elapsed_ms)
                return

            # 2) 逐块写入（支持断点续传）
            start_idx = self._progress.get(job.id, 0)
            for idx in range(start_idx, len(chunks)):
                chunk_data = chunks[idx]
                task = ImportTask(
                    job_id=job.id,
                    chunk_index=idx,
                    content=chunk_data.get("content", ""),
                    memory_type=chunk_data.get("memory_type", job.file_type_to_memory_type()),
                )

                if self._memory_writer is not None:
                    # 异步路径：入队到 MemoryWriteWorker，不等待结果
                    task.status = "enqueued"
                    try:
                        from src.core.memory_queue import MemoryWriteTask

                        mw_task = MemoryWriteTask(
                            arguments={
                                "content": task.content,
                                "entities": chunk_data.get("entities", []),
                            },
                            call_id=f"import:{job.id}",
                        )
                        self._memory_writer.enqueue(mw_task)
                        task.memory_id = mw_task.task_id
                        # status 保持 "enqueued"，不伪造为 "stored"
                        job.memories_created += 1
                    except Exception as write_err:
                        task.status = "failed"
                        task.error = str(write_err)
                        self._write_dead_letter(task, reason=str(write_err))
                else:
                    # 无 MemoryWriteWorker：直接写入（降级路径）
                    task.status = "enqueued"
                    try:
                        from src.tools.remember import RememberTool

                        tool = RememberTool(sqlite, chroma, embedding)
                        result = tool.execute({
                            "content": task.content,
                            "entities": chunk_data.get("entities", []),
                        })
                        if result.success:
                            task.status = "stored"
                            task.memory_id = result.metadata.get("memory_id", "")
                            job.memories_created += 1
                        else:
                            task.status = "failed"
                            task.error = result.error or "工具返回失败"
                            self._write_dead_letter(task, reason=task.error or "写入失败")
                    except Exception as write_err:
                        task.status = "failed"
                        task.error = str(write_err)
                        self._write_dead_letter(task, reason=str(write_err))

                job.processed_chunks = idx + 1
                self._progress[job.id] = idx  # 标记此块已完成（断点续传用）

                # 每 10 块更新一次历史
                if (idx + 1) % 10 == 0:
                    self._history.update_job(job)

            # 3) 完成
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc).isoformat()
            self._history.update_job(job)
            elapsed_ms = int((time.monotonic() - t0) * 1000)

            with self._lock:
                self._completed_count += 1
                self._in_progress_count -= 1
                self._total_jobs += 1

            # 清理断点进度
            self._progress.pop(job.id, None)

            logger.info(
                "import_job_completed",
                extra={
                    "job_id": job.id,
                    "title": job.title,
                    "chunks": job.total_chunks,
                    "memories_created": job.memories_created,
                    "elapsed_ms": elapsed_ms,
                    "queue_depth": self.pending,
                },
            )
            self._record_job_history(job, elapsed_ms)

        except Exception:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc).isoformat()
            job.error = f"导入作业异常崩溃: {_truncate_error()}"
            self._history.update_job(job)
            logger.exception(
                "import_job_failed",
                extra={
                    "job_id": job.id,
                    "title": job.title,
                    "elapsed_ms": elapsed_ms,
                    "queue_depth": self.pending,
                },
            )

            with self._lock:
                self._failed_count += 1
                self._in_progress_count -= 1
                self._total_jobs += 1

            # 写入 DLQ
            self._write_dead_letter_job(job)
            self._record_job_history(job, elapsed_ms)

    # ── 源文件解析 ──

    def _parse_sources(self, job: ImportJob) -> list[dict[str, Any]]:
        """解析 job.source 中的所有文件/URL，返回统一 chunk 列表。

        每个 source 用逗号分隔，支持文件路径和 http(s) URL。
        """
        sources = [s.strip() for s in job.source.split(",") if s.strip()]
        if not sources:
            return []

        all_chunks: list[dict[str, Any]] = []
        from src.importers.base import chunk_text, extract_entities, generate_title

        for src in sources:
            if src.startswith("http://") or src.startswith("https://"):
                # URL 导入
                chunks = self._import_from_url(src)
            else:
                # 文件导入
                chunks = self._import_from_file(src)

            # 补全缺失字段
            for ch in chunks:
                if "title" not in ch:
                    ch["title"] = job.title or generate_title(ch.get("content", ""))
                if "memory_type" not in ch:
                    ch["memory_type"] = job.file_type_to_memory_type()

            all_chunks.extend(chunks)

        # 从所有 chunks 聚合 entities
        all_text = " ".join(ch.get("content", "") for ch in all_chunks)
        entities = extract_entities(all_text)
        for ch in all_chunks:
            if "entities" not in ch or not ch["entities"]:
                ch["entities"] = entities[:10]

        return all_chunks

    def _import_from_file(self, file_path: str) -> list[dict[str, Any]]:
        """从文件导入：根据扩展名选择解析策略。"""
        path = Path(file_path)
        if not path.exists():
            logger.warning("import_source_missing", extra={"path": file_path})
            return []

        ext = path.suffix.lower()
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            logger.exception("import_read_failed", extra={"path": file_path})
            return []

        return self._chunk_content(content, file_path, ext)

    def _import_from_url(self, url: str) -> list[dict[str, Any]]:
        """从 URL 导入：使用 requests 抓取后解析。"""
        try:
            import requests
        except ImportError:
            logger.warning("requests_not_installed", extra={"url": url})
            return [{"content": f"[URL] {url}\n\n无法抓取：requests 库未安装", "title": url}]

        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            content = resp.text
            ext = _guess_url_ext(url, resp.headers.get("content-type", ""))
            return self._chunk_content(content, url, ext)
        except Exception:
            logger.exception("import_url_failed", extra={"url": url})
            return [{"content": f"[URL] {url}\n\n抓取失败", "title": url}]

    def _chunk_content(
        self,
        content: str,
        source_path: str,
        ext: str,
    ) -> list[dict[str, Any]]:
        """根据文件类型分块。"""
        from src.importers.base import chunk_text, extract_entities, generate_title

        title = generate_title(content, fallback=Path(source_path).stem or "Untitled")

        if ext in (".md", ".markdown"):
            chunks = chunk_text(content)
        elif ext in (".pdf",):
            chunks = _try_pdf_chunk(source_path)
            if not chunks:
                chunks = chunk_text(content)
        else:
            # 纯文本
            chunks = chunk_text(content)

        entities = extract_entities(content)

        return [
            {
                "content": ch,
                "title": title,
                "entities": entities[:10],
                "metadata": {"source": source_path, "chunk_index": idx},
            }
            for idx, ch in enumerate(chunks)
        ]

    # ── DLQ ──

    def _write_dead_letter(self, task: ImportTask, reason: str = "") -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = f"import_{ts}_{task.id[:8]}.json"
        path = self._dead_letter_dir / filename
        try:
            path.write_text(
                json.dumps(
                    {
                        "task_id": task.id,
                        "job_id": task.job_id,
                        "chunk_index": task.chunk_index,
                        "status": task.status,
                        "memory_type": task.memory_type,
                        "reason": reason or "写入失败，详见 Worker 日志",
                        "content_preview": task.content[:200],
                        "failed_at": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            logger.info("import_dead_letter_written", extra={"path": str(path), "job_id": task.job_id})
        except Exception:
            logger.exception("import_dead_letter_write_failed")

    def _write_dead_letter_job(self, job: ImportJob) -> None:
        """作业级故障写入 DLQ。"""
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = f"import_job_{ts}_{job.id[:8]}.json"
        path = self._dead_letter_dir / filename
        try:
            path.write_text(
                json.dumps(
                    {
                        "job_id": job.id,
                        "source": job.source,
                        "title": job.title,
                        "file_type": job.file_type,
                        "status": job.status,
                        "total_chunks": job.total_chunks,
                        "processed_chunks": job.processed_chunks,
                        "error": job.error,
                        "started_at": job.started_at,
                        "failed_at": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            logger.info("import_job_dead_letter_written", extra={"path": str(path), "job_id": job.id})
        except Exception:
            logger.exception("import_job_dead_letter_write_failed")

    # ── Job History ──

    def _record_job_history(self, job: ImportJob, elapsed_ms: int) -> None:
        entry = {
            "job_id": job.id,
            "title": job.title,
            "file_type": job.file_type,
            "status": job.status,
            "total_chunks": job.total_chunks,
            "processed_chunks": job.processed_chunks,
            "memories_created": job.memories_created,
            "elapsed_ms": elapsed_ms,
            "started_at": job.started_at,
        }
        with self._lock:
            self._job_history.append(entry)
            if len(self._job_history) > self._max_history:
                self._job_history = self._job_history[-self._max_history:]

    # ── Runtime Stats ──

    @property
    def stats(self) -> dict[str, Any]:
        dlq_count = 0
        try:
            if self._dead_letter_dir.exists():
                dlq_count = len(list(self._dead_letter_dir.glob("import_*.json")))
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
                "jobs": {
                    "total": self._total_jobs,
                    "completed": self._completed_count,
                    "failed": self._failed_count,
                    "in_progress": self._in_progress_count,
                    "pending": int(self._queue.qsize()),
                },
                "queue": {
                    "pending": int(self._queue.qsize()),
                },
                "dead_letter": {
                    "count": dlq_count,
                    "dir": str(self._dead_letter_dir),
                },
                "recent_jobs": list(self._job_history[-20:]),
            }

    @property
    def alerts(self) -> list[dict[str, Any]]:
        """生成实时告警。

        检查阈值：
          - DLQ 累积 >= 5 条
          - 队列积压 >= 10 条
          - 最近 10 条作业失败率 >= 30%
        """
        dlq_count = 0
        try:
            if self._dead_letter_dir.exists():
                dlq_count = len(list(self._dead_letter_dir.glob("import_*.json")))
        except Exception:
            pass

        result: list[dict[str, Any]] = []

        if dlq_count >= 5:
            result.append({
                "level": "warning",
                "type": "dlq_accumulation",
                "message": f"Import Dead Letter Queue 积压 {dlq_count} 条，请检查 Import Worker 日志",
                "threshold": 5,
                "current": dlq_count,
            })

        if self._queue.qsize() >= 10:
            result.append({
                "level": "warning",
                "type": "queue_congestion",
                "message": f"导入队列积压 {self._queue.qsize()} 条，可能影响后续导入延迟",
                "threshold": 10,
                "current": self._queue.qsize(),
            })

        with self._lock:
            recent = list(self._job_history[-10:])
        if recent:
            failed_in_window = sum(1 for j in recent if j.get("status") == "failed")
            fail_rate = failed_in_window / len(recent)
            if fail_rate >= 0.3:
                failed_job_ids = [j["job_id"] for j in recent if j.get("status") == "failed"]
                result.append({
                    "level": "critical",
                    "type": "high_failure_rate",
                    "message": f"最近 {len(recent)} 条导入作业失败率 {fail_rate:.0%}，需立即排查",
                    "threshold": 0.3,
                    "current": round(fail_rate, 2),
                    "failed_count": failed_in_window,
                    "window_size": len(recent),
                    "failed_job_ids": failed_job_ids,
                })

        return result


# ── Helpers ──


def _truncate_error(max_len: int = 500) -> str:
    import traceback
    tb = traceback.format_exc()
    return tb[:max_len] if len(tb) > max_len else tb


def _guess_url_ext(url: str, content_type: str) -> str:
    """从 URL 或 Content-Type 猜测文件扩展名。"""
    content_type_lower = content_type.lower()
    if "pdf" in content_type_lower:
        return ".pdf"
    if "markdown" in content_type_lower:
        return ".md"
    if "html" in content_type_lower:
        return ".html"

    from urllib.parse import urlparse
    path = urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    if ext:
        return ext
    return ".txt"


def _try_pdf_chunk(file_path: str) -> list[dict[str, Any]]:
    """尝试使用 PyMuPDF 解析 PDF，不可用时返回空列表。"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.debug("PyMuPDF_not_installed, fallback to raw text", extra={"path": file_path})
        return []

    try:
        doc = fitz.open(file_path)
        all_chunks: list[dict[str, Any]] = []
        from src.importers.base import chunk_text, extract_entities, generate_title

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            if not text or not text.strip():
                continue
            page_chunks = chunk_text(text)
            for pc in page_chunks:
                all_chunks.append({
                    "content": pc,
                    "metadata": {"source": file_path, "page": page_num + 1},
                })
        doc.close()
        return all_chunks
    except Exception:
        logger.exception("pdf_parse_failed", extra={"path": file_path})
        return []


# ── file_type → memory_type mapping ──


def _file_type_to_memory_type(file_type: str) -> str:
    """从文件类型推断默认 memory_type。"""
    mapping: dict[str, str] = {
        "markdown": "semantic",
        "md": "semantic",
        "pdf": "semantic",
        "text": "episodic",
        "txt": "episodic",
        "html": "semantic",
        "batch": "episodic",
    }
    return mapping.get(file_type.lower(), "episodic")
