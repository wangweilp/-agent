"""Import 路由 — 文件批量导入 + 分块解析 + 异步记忆写入 + 实时告警。

流程:
    POST /imports              — 提交导入作业 (multipart file upload)
      → 校验 + 保存到 data/imports/
      → 构建 ImportJob + 入队 ImportWorker
      → 返回 job 状态 + Worker 告警

    GET  /imports              — 列出所有导入作业
    GET  /imports/{id}         — 获取作业详情 + 进度
    POST /imports/{id}/retry   — 重试失败作业
    DELETE /imports/{id}       — 删除作业 + 可选清除关联记忆
"""
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile

from src.adapters.config import Settings
from src.core.agent import CognitiveAgent
from src.core.memory import ChatModel
from src.core.memory_queue import MemoryWriteWorker
from src.core.import_worker import ImportWorker, ImportJob

logger = logging.getLogger(__name__)

# ── 支持的文件类型 ──
_ALLOWED_EXTENSIONS: set[str] = {
    ".md", ".markdown", ".txt", ".text",
    ".pdf", ".html", ".htm", ".json",
    ".csv", ".xml", ".rst",
}
_MAX_BATCH_FILES = 20


def create_import_router(
    settings: Settings,
    llm: ChatModel,
    writer: MemoryWriteWorker,
    import_worker: ImportWorker,
    agent: CognitiveAgent | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/imports", tags=["imports"])

    # ── POST /imports — 提交导入作业 ──

    @router.post("")
    async def submit_import(files: list[UploadFile]):
        """批量上传文件，构建 ImportJob 并异步入队。

        接受多个文件（form field 名: files），校验后构建 ImportJob 交给 ImportWorker。
        """
        if not files:
            raise HTTPException(400, "至少需要一个文件")

        if len(files) > _MAX_BATCH_FILES:
            raise HTTPException(400, f"一次最多导入 {_MAX_BATCH_FILES} 个文件")

        t0 = time.monotonic()

        # ── Phase 1: 校验 + 保存 ──
        saved: list[dict[str, Any]] = []
        import_dir = Path("./data/imports")
        import_dir.mkdir(parents=True, exist_ok=True)

        for f in files:
            if not f.filename:
                raise HTTPException(400, "文件名为空")

            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in _ALLOWED_EXTENSIONS:
                raise HTTPException(400, f"不支持的文件类型: {ext}，支持: {sorted(_ALLOWED_EXTENSIONS)}")

            content_bytes = await f.read()
            size_bytes = len(content_bytes)

            if size_bytes > settings.upload_max_size_mb * 1024 * 1024 * 2:
                raise HTTPException(413, f"文件过大: {f.filename} {size_bytes / 1024 / 1024:.1f}MB (上限 {settings.upload_max_size_mb * 2}MB)")

            file_id = str(uuid.uuid4())
            saved_name = f"{file_id}{ext}"
            file_path = import_dir / saved_name
            file_path.write_bytes(content_bytes)

            saved.append({
                "file_id": file_id,
                "filename": f.filename,
                "saved_name": saved_name,
                "ext": ext,
                "size_bytes": size_bytes,
                "path": str(file_path),
            })
            logger.info("import:file_saved", extra={"file_id": file_id, "filename": f.filename, "ext": ext})

        # ── Phase 2: 构建 ImportJob ──
        sources = [s["path"] for s in saved]
        file_types = list({s["ext"].lstrip(".") for s in saved})
        file_type = file_types[0] if len(file_types) == 1 else "batch"

        title = saved[0]["filename"] if len(saved) == 1 else f"批量导入 {len(saved)} 个文件"

        job = ImportJob(
            source=",".join(sources),
            title=title,
            file_type=file_type,
        )

        # ── Phase 3: 入队 ImportWorker ──
        import_worker.enqueue(job)

        t_total_ms = int((time.monotonic() - t0) * 1000)

        return {
            "status": "accepted",
            "job_id": job.id,
            "title": job.title,
            "file_type": job.file_type,
            "total_files": len(saved),
            "total_time_ms": t_total_ms,
            "queue_depth": import_worker.pending,
            "files": [
                {
                    "file_id": s["file_id"],
                    "filename": s["filename"],
                    "ext": s["ext"],
                    "size_bytes": s["size_bytes"],
                }
                for s in saved
            ],
            "worker": {
                "alive": import_worker.stats["worker"]["alive"],
                "jobs_completed": import_worker.stats["jobs"]["completed"],
                "jobs_failed": import_worker.stats["jobs"]["failed"],
                "dlq_count": import_worker.stats["dead_letter"]["count"],
            },
            "alerts": import_worker.alerts,
        }

    # ── GET /imports — 列出导入作业 ──

    @router.get("")
    async def list_imports(
        status: str = "",
        limit: int = 50,
    ):
        """列出所有导入作业，支持按状态过滤。"""
        jobs = import_worker._history.list_jobs()

        if status:
            jobs = [j for j in jobs if j.get("status") == status]

        result = [
            _job_to_response(j)
            for j in jobs[:limit]
        ]

        return {
            "jobs": result,
            "total": len(result),
            "worker": {
                "alive": import_worker.stats["worker"]["alive"],
                "completed": import_worker.stats["jobs"]["completed"],
                "failed": import_worker.stats["jobs"]["failed"],
                "in_progress": import_worker.stats["jobs"]["in_progress"],
                "pending": import_worker.stats["jobs"]["pending"],
            },
        }

    # ── GET /imports/{id} — 作业详情 ──

    @router.get("/{job_id}")
    async def get_import(job_id: str):
        """获取作业详情 + 进度。"""
        job_data = import_worker._history.get_job(job_id)
        if job_data is None:
            raise HTTPException(404, f"导入作业 {job_id} 不存在")

        # 实时进度
        progress = import_worker._progress.get(job_id)
        resume_from = progress if progress is not None else 0

        return {
            **_job_to_response(job_data),
            "resume_from_chunk": resume_from,
        }

    # ── POST /imports/{id}/retry — 重试失败作业 ──

    @router.post("/{job_id}/retry")
    async def retry_import(job_id: str):
        """重试失败的作业。已成功写入的 chunk 会被跳过（断点续传）。"""
        job_data = import_worker._history.get_job(job_id)
        if job_data is None:
            raise HTTPException(404, f"导入作业 {job_id} 不存在")

        if job_data.get("status") not in ("failed", "cancelled"):
            raise HTTPException(409, f"只有失败或取消的作业才能重试，当前状态: {job_data.get('status')}")

        # 重建 ImportJob 并重新入队
        job = ImportJob(
            id=job_data["id"],
            source=job_data.get("source", ""),
            title=job_data.get("title", ""),
            file_type=job_data.get("file_type", "batch"),
        )
        # 重新开始进度
        import_worker._progress.pop(job.id, None)

        import_worker.enqueue(job)

        return {
            "status": "retrying",
            "job_id": job.id,
            "title": job.title,
            "previous_status": job_data.get("status"),
            "previous_processed_chunks": job_data.get("processed_chunks", 0),
        }

    # ── DELETE /imports/{id} — 删除作业 ──

    @router.delete("/{job_id}")
    async def delete_import(job_id: str, delete_memories: bool = False):
        """删除导入作业记录。可选删除关联记忆。

        Args:
            delete_memories: 若为 True，同时软删除该作业产生的所有记忆。
        """
        job_data = import_worker._history.get_job(job_id)
        if job_data is None:
            raise HTTPException(404, f"导入作业 {job_id} 不存在")

        # 如果作业正在处理中，先取消
        if job_data.get("status") == "processing":
            import_worker._progress.pop(job_id, None)

        if delete_memories and agent is not None:
            try:
                source_marker = f"import:{job_id}"
                deleted_count = _soft_delete_imported_memories(agent, source_marker)
            except Exception:
                logger.exception("import_delete_memories_failed", extra={"job_id": job_id})
                deleted_count = 0
        else:
            deleted_count = 0

        deleted = import_worker._history.delete_job(job_id)

        return {
            "job_id": job_id,
            "deleted": deleted,
            "memories_deleted": deleted_count,
        }

    return router


# ── Helpers ──


def _job_to_response(job_data: dict[str, Any]) -> dict[str, Any]:
    """将内部 job dict 转为 API 响应格式。"""
    total = job_data.get("total_chunks", 0)
    processed = job_data.get("processed_chunks", 0)
    progress_pct = (processed / total * 100) if total > 0 else 0.0

    return {
        "job_id": job_data.get("id", ""),
        "title": job_data.get("title", ""),
        "file_type": job_data.get("file_type", ""),
        "status": job_data.get("status", "pending"),
        "total_chunks": total,
        "processed_chunks": processed,
        "memories_created": job_data.get("memories_created", 0),
        "progress_pct": round(progress_pct, 1),
        "started_at": job_data.get("started_at"),
        "completed_at": job_data.get("completed_at"),
        "error": job_data.get("error"),
    }


def _soft_delete_imported_memories(agent: CognitiveAgent, source_marker: str) -> int:
    """软删除所有 source 匹配 import:xxx 的记忆。"""
    store = agent._memory_store
    try:
        rows = store._db.execute(
            "SELECT id FROM notes WHERE source LIKE ?",
            (f"%{source_marker}%",),
        ).fetchall()
        count = 0
        for row in rows:
            store.update_status(row["id"], "deleted")
            count += 1
        logger.info("import_memories_bulk_deleted", extra={"source": source_marker, "count": count})
        return count
    except Exception:
        logger.exception("import_memories_bulk_delete_failed")
        return 0
