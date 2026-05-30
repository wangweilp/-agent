"""Upload 路由 — 批量图片上传 + LLM Vision 解析 + 5 层记忆管道 + 实时告警。

流程：
    POST /upload (multipart, 支持多文件)
      → 校验 + 保存到 data/uploads/
      → ImageAnalyzer.analyze_batch() 批量分析（跨图上下文关联）
      → 每张图构建 5 层 MemoryTask
      → 主动记忆触发：基于 scene_type 自动关联
      → MemoryWriteWorker.enqueue() 异步写入
      → 返回每张图的分析 + task 状态 + Worker 告警
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
from src.core.image_analyzer import ImageAnalyzer
from src.core.memory import ChatModel
from src.core.memory_queue import MemoryWriteWorker, MemoryWriteTask

logger = logging.getLogger(__name__)

# 场景 → 主动触发策略
_SCENE_TRIGGERS: dict[str, dict[str, Any]] = {
    "白板": {"extra_importance": 2, "auto_reflect": True, "reason": "白板内容通常包含架构/规划，值得深度反思"},
    "图表": {"extra_importance": 2, "auto_reflect": True, "reason": "图表蕴含结构化知识"},
    "代码": {"extra_importance": 1, "auto_reflect": False, "reason": "代码片段作为参考记忆"},
    "文档": {"extra_importance": 1, "auto_reflect": False, "reason": "文档截图提取文字并索引"},
    "截图": {"extra_importance": 0, "auto_reflect": False, "reason": "截图作为情景证据保存"},
    "人像": {"extra_importance": 1, "auto_reflect": False, "reason": "人像记录关联用户社交知识"},
    "风景": {"extra_importance": 0, "auto_reflect": False, "reason": "风景作为情景记忆存储"},
}


def create_upload_router(
    settings: Settings,
    llm: ChatModel,
    writer: MemoryWriteWorker,
) -> APIRouter:
    router = APIRouter(prefix="/upload", tags=["upload"])
    analyzer = ImageAnalyzer(llm)

    @router.post("")
    async def upload(files: list[UploadFile]):
        """批量上传图片，解析并异步入队。

        接受多个文件（form field 名: files），每张图独立分析、
        批量做跨图上下文关联，统一返回。
        """
        if not files:
            raise HTTPException(400, "至少需要一个文件")

        t0 = time.monotonic()
        saved: list[dict[str, Any]] = []
        file_paths: list[str] = []

        # ── Phase 1: 校验 + 保存 ──
        for f in files:
            if not f.filename:
                raise HTTPException(400, "文件名为空")
            if not f.content_type or not f.content_type.startswith("image/"):
                raise HTTPException(400, f"仅支持图片文件，{f.filename}: {f.content_type}")

            content = await f.read()
            size_bytes = len(content)
            max_bytes = settings.upload_max_size_mb * 1024 * 1024
            if size_bytes > max_bytes:
                raise HTTPException(413, f"文件过大: {f.filename} {size_bytes / 1024 / 1024:.1f}MB")

            upload_dir = Path(settings.upload_dir)
            upload_dir.mkdir(parents=True, exist_ok=True)

            ext = os.path.splitext(f.filename)[1] or ".png"
            file_id = str(uuid.uuid4())
            filename = f"{file_id}{ext}"
            file_path = upload_dir / filename
            file_path.write_bytes(content)

            saved.append({
                "file_id": file_id,
                "filename": f.filename,
                "saved_name": filename,
                "size_bytes": size_bytes,
                "content_type": f.content_type,
            })
            file_paths.append(str(file_path))
            logger.info("upload:saved", extra={"file_id": file_id, "filename": f.filename})

        # ── Phase 2: 批量分析 ──
        t_analysis_start = time.monotonic()
        try:
            results = analyzer.analyze_batch(file_paths)
        except Exception:
            logger.exception("upload:batch_analysis_failed")
            raise HTTPException(500, "图片分析失败，请重试")

        t_analysis_ms = int((time.monotonic() - t_analysis_start) * 1000)

        # ── Phase 3: 构建任务 + 入队 ──
        items: list[dict[str, Any]] = []
        total_tasks = 0

        for i, (meta, result) in enumerate(zip(saved, results)):
            if not result.summary:
                items.append({
                    **meta,
                    "analysis": {"summary": "无法识别", "structured_json": None},
                    "tasks": [],
                    "error": "图片清晰度不足或内容无法识别",
                })
                continue

            all_entities = list(dict.fromkeys(result.entities + result.objects))

            # 主动记忆触发
            trigger = _match_trigger(result.scene_type)
            trigger_tasks = _build_trigger_tasks(
                result=result,
                file_id=meta["file_id"],
                filename=meta["filename"],
                entities=all_entities,
                trigger=trigger,
            )

            # 5 层 MemoryTask
            memory_tasks = _build_memory_tasks(
                result=result,
                file_id=meta["file_id"],
                filename=meta["filename"],
                entities=all_entities,
                trigger=trigger,
            )

            all_tasks = memory_tasks + trigger_tasks

            # 入队
            for t in all_tasks:
                writer.enqueue(MemoryWriteTask(
                    arguments={
                        "content": t["content"],
                        "entities": t["entities"],
                        "importance_override": t["importance"],
                    },
                    call_id=f"upload:{meta['file_id']}",
                ))
                total_tasks += 1

            # 结构化输出
            sj = None
            if result.structured_json:
                sj = {
                    "text_in_image": result.structured_json.text_in_image,
                    "entities": result.structured_json.entities,
                    "scene_type": result.structured_json.scene_type,
                    "object_list": result.structured_json.object_list,
                }

            items.append({
                "file_id": meta["file_id"],
                "filename": meta["filename"],
                "size_bytes": meta["size_bytes"],
                "analysis": {
                    "summary": result.summary,
                    "scene_type": result.scene_type,
                    "text_in_image": result.text_in_image,
                    "entities": all_entities,
                    "structured_json": sj,
                    "trigger": {
                        "matched": trigger is not None,
                        "reason": trigger.get("reason", "") if trigger else "",
                    },
                },
                "tasks": [
                    {
                        "task_id": t["task_id"],
                        "memory_type": t["memory_type"],
                        "status": t["status"],
                        "importance": t["importance"],
                    }
                    for t in all_tasks
                ],
                "task_count": len(all_tasks),
            })

        # ── Phase 4: Worker 实时状态 + 告警 ──
        worker_stats = writer.stats
        worker_alerts = writer.alerts

        t_total_ms = int((time.monotonic() - t0) * 1000)

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
            "alerts": worker_alerts,
        }

    return router


# ── Memory Task 构建 ──


def _build_memory_tasks(
    result: Any,
    file_id: str,
    filename: str,
    entities: list[str],
    trigger: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """构建标准 5 层记忆 task。"""
    now_ts = datetime.now(timezone.utc).isoformat()
    bonus = trigger.get("extra_importance", 0) if trigger else 0

    sj = None
    if result.structured_json:
        sj = json.dumps({
            "text_in_image": result.structured_json.text_in_image,
            "entities": result.structured_json.entities,
            "scene_type": result.structured_json.scene_type,
            "object_list": result.structured_json.object_list,
        }, ensure_ascii=False)

    return [
        {
            "task_id": f"mem_{file_id}_working",
            "memory_type": "working",
            "content": f"[图片记忆·工作区] {filename}\n{result.summary}\n\n{result.detailed_description}",
            "entities": entities,
            "importance": min(8 + bonus, 10),
            "status": "pending",
        },
        {
            "task_id": f"mem_{file_id}_episodic",
            "memory_type": "episodic",
            "content": f"[图片记忆·情景] 用户于 {now_ts} 上传「{filename}」\n场景: {result.scene_type}\n摘要: {result.summary}",
            "entities": entities,
            "importance": min(6 + bonus, 10),
            "status": "pending",
        },
        {
            "task_id": f"mem_{file_id}_semantic",
            "memory_type": "semantic",
            "content": f"[图片记忆·语义] {result.summary}\n{result.detailed_description}\n{sj or ''}",
            "entities": entities,
            "importance": min(7 + bonus, 10),
            "status": "pending",
        },
        {
            "task_id": f"mem_{file_id}_conceptual",
            "memory_type": "semantic",
            "content": f"[图片记忆·概念] 场景={result.scene_type} | 实体={json.dumps(entities, ensure_ascii=False)} | 用途={result.suggested_use}",
            "entities": entities,
            "importance": min(5 + bonus, 10),
            "status": "pending",
        },
        {
            "task_id": f"mem_{file_id}_reflective",
            "memory_type": "reflect",
            "content": f"[图片记忆·反思] 用户上传「{filename}」(场景: {result.scene_type})。"
                       f"内容: {result.summary}。"
                       f"建议关联: {result.suggested_use}。"
                       f"实体 {', '.join(entities[:5]) if entities else '暂无'} 值得后续关注。",
            "entities": entities,
            "importance": min(4 + bonus, 10),
            "status": "pending",
        },
    ]


def _match_trigger(scene_type: str) -> dict[str, Any] | None:
    """根据场景类型匹配主动触发策略。"""
    for key, cfg in _SCENE_TRIGGERS.items():
        if key in scene_type:
            return cfg
    return None


def _build_trigger_tasks(
    result: Any,
    file_id: str,
    filename: str,
    entities: list[str],
    trigger: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """主动记忆触发：白板/图表等场景自动生成额外记忆。"""
    if not trigger:
        return []

    tasks: list[dict[str, Any]] = []

    # 触发 Reflective Memory 更新
    if trigger.get("auto_reflect"):
        tasks.append({
            "task_id": f"mem_{file_id}_trigger_reflect",
            "memory_type": "reflect",
            "content": f"[自动反思触发] 场景「{result.scene_type}」触发深度反思。\n"
                       f"原因: {trigger['reason']}\n"
                       f"图片: {filename}\n"
                       f"摘要: {result.summary}\n"
                       f"识别的实体: {', '.join(entities[:10]) if entities else '暂无'}\n"
                       f"建议: 将图内容与已有知识体系关联，寻找矛盾或补充。",
            "entities": entities,
            "importance": 8,
            "status": "pending",
        })

    return tasks
