"""Video 路由 — 视频上传 + 管理 CRUD。

流程：
    POST /video/upload (multipart)
      → 校验 + 保存到 data/video_uploads/
      → VideoAnalyzer.analyze() 关键帧+OCR+ASR+LLM综合分析
      → 构建 5 层 MemoryTask
      → MemoryWriteWorker.enqueue() 异步写入
      → 返回分析结果 + 任务状态

管理端点：
    GET  /video/{file_id}    — 查看视频分析详情
    GET  /video              — 列出视频记忆列表（支持搜索）
    PATCH  /video/{file_id}  — 编辑视频记忆
    DELETE /video/{file_id}  — 软删除
    POST /video/{file_id}/archive — 归档
"""
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, UploadFile

from src.adapters.config import Settings
from src.core.agent import CognitiveAgent
from src.core.video_analyzer import VideoAnalyzer
from src.core.memory import ChatModel
from src.core.memory_queue import MemoryWriteWorker, MemoryWriteTask
from src.api.schemas import MemoryUpdateRequest

logger = logging.getLogger(__name__)


def create_video_router(
    settings: Settings,
    llm: ChatModel,
    writer: MemoryWriteWorker,
    agent: CognitiveAgent | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/video", tags=["video"])
    analyzer = VideoAnalyzer(llm, settings)

    # ── helper ──

    def _video_to_memory_dict(m) -> dict:
        return {
            "id": m.id,
            "content": m.content,
            "summary": m.summary,
            "source": m.source,
            "timestamp": m.timestamp.isoformat(),
            "importance": m.importance,
            "entities": m.entities,
            "memory_type": m.memory_type,
            "access_count": m.access_count,
            "last_accessed": m.last_accessed.isoformat() if m.last_accessed else None,
            "status": m.status,
            "archived_at": m.archived_at.isoformat() if getattr(m, "archived_at", None) else None,
        }

    # ── POST /video/upload ──

    @router.post("/upload")
    async def upload_video(files: list[UploadFile]):
        """上传视频文件，分析并异步入队。"""
        if not files:
            raise HTTPException(400, "至少需要一个视频文件")

        t0 = time.monotonic()
        video_dir = Path(settings.video_upload_dir)
        video_dir.mkdir(parents=True, exist_ok=True)
        max_bytes = settings.video_max_size_mb * 1024 * 1024

        saved: list[dict[str, Any]] = []
        file_paths: list[str] = []
        filenames: list[str] = []

        for f in files:
            if not f.filename:
                raise HTTPException(400, "文件名为空")

            content = await f.read()
            size_bytes = len(content)
            if size_bytes > max_bytes:
                raise HTTPException(413,
                    f"文件过大: {f.filename} {size_bytes / 1024 / 1024:.1f}MB "
                    f"(上限 {settings.video_max_size_mb}MB)")

            ext = os.path.splitext(f.filename)[1] or ".mp4"
            supported = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv", ".wmv"}
            if ext.lower() not in supported:
                raise HTTPException(400, f"不支持的视频格式: {ext}")

            file_id = str(uuid.uuid4())
            saved_name = f"{file_id}{ext}"
            file_path = video_dir / saved_name
            file_path.write_bytes(content)

            saved.append({
                "file_id": file_id,
                "filename": f.filename,
                "saved_name": saved_name,
                "size_bytes": size_bytes,
            })
            file_paths.append(str(file_path))
            filenames.append(f.filename)
            logger.info("video:saved", extra={"file_id": file_id, "filename": f.filename})

        # ── 分析 ──
        t_analysis_start = time.monotonic()
        results = analyzer.analyze_batch(file_paths, filenames)
        t_analysis_ms = int((time.monotonic() - t_analysis_start) * 1000)

        # ── 构建 MemoryTask + 入队 ──
        items: list[dict[str, Any]] = []
        total_tasks = 0

        for meta, result in zip(saved, results):
            all_entities = list(dict.fromkeys(result.entities))
            all_concepts = result.concepts

            tasks = _build_video_memory_tasks(
                result=result,
                file_id=meta["file_id"],
                filename=meta["filename"],
                entities=all_entities + all_concepts,
            )

            for t in tasks:
                writer.enqueue(MemoryWriteTask(
                    arguments={
                        "content": t["content"],
                        "entities": t["entities"],
                        "importance_override": t["importance"],
                    },
                    call_id=f"video:{meta['file_id']}",
                ))
                total_tasks += 1

            items.append({
                "file_id": meta["file_id"],
                "filename": meta["filename"],
                "size_bytes": meta["size_bytes"],
                "analysis": {
                    "summary": result.summary,
                    "topic": result.topic,
                    "key_points": result.key_points,
                    "entities": all_entities,
                    "concepts": all_concepts,
                    "ocr_text_preview": result.ocr_text[:300] if result.ocr_text else "",
                    "transcription_preview": result.transcription[:300] if result.transcription else "",
                    "duration_seconds": result.duration_seconds,
                    "keyframe_count": result.keyframe_count,
                    "importance_hint": result.importance_hint,
                },
                "tasks": [
                    {"task_id": t["task_id"], "memory_type": t["memory_type"],
                     "status": t["status"], "importance": t["importance"]}
                    for t in tasks
                ],
                "task_count": len(tasks),
            })

        t_total_ms = int((time.monotonic() - t0) * 1000)
        worker_stats = writer.stats

        return {
            "status": "accepted",
            "files_count": len(files),
            "total_tasks_enqueued": total_tasks,
            "analysis_time_ms": t_analysis_ms,
            "total_time_ms": t_total_ms,
            "queue_depth": writer.pending,
            "items": items,
            "worker": {
                "alive": worker_stats["worker"]["alive"],
                "total_stored": worker_stats["queue"]["total_stored"],
                "total_failed": worker_stats["queue"]["total_failed"],
                "dlq_count": worker_stats["dead_letter"]["count"],
            },
            "alerts": writer.alerts,
        }

    # ── GET /video ──

    @router.get("")
    async def list_video_memories(
        q: str = "",
        limit: int = Query(default=50, ge=1, le=200),
    ):
        """列出视频相关记忆。通过 content 含 "[视频" 前缀筛选。"""
        store = agent._memory_store if agent else None
        if store is None:
            return []

        try:
            recent = store.get_recent(limit=500)
            video_mems = [
                m for m in recent
                if "[视频" in m.content or "video" in m.memory_type.lower()
            ]
            if q:
                q_lower = q.lower()
                video_mems = [
                    m for m in video_mems
                    if q_lower in m.content.lower()
                    or any(q_lower in e.lower() for e in m.entities)
                ]
            return [_video_to_memory_dict(m) for m in video_mems[:limit]]
        except Exception:
            logger.warning("video_list_failed", exc_info=True)
            return []

    # ── GET /video/{file_id} ──

    @router.get("/{file_id}")
    async def get_video_memory(file_id: str):
        store = agent._memory_store if agent else None
        if store is None:
            raise HTTPException(500, "记忆存储未初始化")

        m = store.get_by_id(file_id)
        if m is None:
            raise HTTPException(404, "视频记忆不存在")
        return _video_to_memory_dict(m)

    # ── PATCH /video/{file_id} ──

    @router.patch("/{file_id}")
    async def update_video_memory(file_id: str, body: MemoryUpdateRequest):
        store = agent._memory_store if agent else None
        if store is None:
            raise HTTPException(500, "记忆存储未初始化")

        m = store.get_by_id(file_id)
        if m is None:
            raise HTTPException(404, "视频记忆不存在")

        if body.content is not None:
            m.content = body.content
        if body.summary is not None:
            m.summary = body.summary
        if body.importance is not None:
            m.importance = body.importance
        if body.entities is not None:
            m.entities = body.entities

        try:
            store.store(m)
        except Exception:
            raise HTTPException(500, "保存失败")
        return _video_to_memory_dict(m)

    # ── DELETE /video/{file_id} ──

    @router.delete("/{file_id}")
    async def delete_video_memory(file_id: str):
        store = agent._memory_store if agent else None
        if store is None:
            raise HTTPException(500, "记忆存储未初始化")

        m = store.get_by_id(file_id)
        if m is None:
            raise HTTPException(404, "视频记忆不存在")

        try:
            store.update_status(file_id, "deleted")
        except Exception:
            raise HTTPException(500, "删除失败")
        return {"id": file_id, "status": "deleted"}

    # ── POST /video/{file_id}/archive ──

    @router.post("/{file_id}/archive")
    async def archive_video_memory(file_id: str):
        store = agent._memory_store if agent else None
        if store is None:
            raise HTTPException(500, "记忆存储未初始化")

        m = store.get_by_id(file_id)
        if m is None:
            raise HTTPException(404, "视频记忆不存在")

        now = datetime.now(timezone.utc)
        m.status = "archived"
        m.archived_at = now
        try:
            store.store(m)
        except Exception:
            raise HTTPException(500, "归档失败")
        return {"id": file_id, "status": "archived", "archived_at": now.isoformat()}

    return router


# ── Memory Task 构建 ──


def _build_video_memory_tasks(
    result: Any,
    file_id: str,
    filename: str,
    entities: list[str],
) -> list[dict[str, Any]]:
    """构建 5 层记忆任务（视频版）。"""
    now_ts = datetime.now(timezone.utc).isoformat()
    imp = min(result.importance_hint, 10)

    kp_text = "\n".join(f"- {p}" for p in result.key_points) if result.key_points else ""

    return [
        {
            "task_id": f"mem_{file_id}_working",
            "memory_type": "working",
            "content": (
                f"[视频记忆·工作区] {filename}\n"
                f"主题: {result.topic}\n"
                f"摘要: {result.summary}\n"
                f"时长: {result.duration_seconds:.0f}s | 关键帧: {result.keyframe_count}\n\n"
                f"OCR: {result.ocr_text[:500] if result.ocr_text else '无'}\n"
                f"转录: {result.transcription[:500] if result.transcription else '无'}"
            ),
            "entities": entities,
            "importance": min(imp + 2, 10),
            "status": "pending",
        },
        {
            "task_id": f"mem_{file_id}_episodic",
            "memory_type": "episodic",
            "content": (
                f"[视频记忆·情景] 用户于 {now_ts} 上传视频「{filename}」\n"
                f"主题: {result.topic} | 时长: {result.duration_seconds:.0f}s\n"
                f"摘要: {result.summary}"
            ),
            "entities": entities,
            "importance": min(imp + 1, 10),
            "status": "pending",
        },
        {
            "task_id": f"mem_{file_id}_semantic",
            "memory_type": "semantic",
            "content": (
                f"[视频记忆·语义] {result.summary}\n"
                f"话题: {result.topic}\n"
                f"关键点:\n{kp_text}\n"
                f"概念: {', '.join(result.concepts) if result.concepts else '无'}\n"
                f"OCR 文字:\n{result.ocr_text[:1500] if result.ocr_text else '无'}\n"
                f"转录: {result.transcription[:1500] if result.transcription else '无'}"
            ),
            "entities": entities,
            "importance": imp,
            "status": "pending",
        },
        {
            "task_id": f"mem_{file_id}_conceptual",
            "memory_type": "semantic",
            "content": (
                f"[视频记忆·概念] 主题={result.topic} | "
                f"实体={json.dumps(entities[:10], ensure_ascii=False)} | "
                f"概念={json.dumps(result.concepts[:10], ensure_ascii=False) if result.concepts else '[]'} | "
                f"用途={result.suggested_use}"
            ),
            "entities": entities,
            "importance": max(imp - 1, 3),
            "status": "pending",
        },
        {
            "task_id": f"mem_{file_id}_reflective",
            "memory_type": "reflect",
            "content": (
                f"[视频记忆·反思] 用户上传视频「{filename}」(时长 {result.duration_seconds:.0f}s)。"
                f"内容: {result.summary}。"
                f"关键发现:\n{kp_text}\n"
                f"建议关联: {result.suggested_use}。"
                f"实体 {', '.join(entities[:5]) if entities else '暂无'} 值得后续关注。"
            ),
            "entities": entities,
            "importance": max(imp - 2, 2),
            "status": "pending",
        },
    ]
