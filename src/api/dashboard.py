"""Dashboard 路由 — 系统指标、记忆全景、Runtime Monitor。"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from src.api.schemas import (
    DashboardSummary,
    EntityItem,
    RecentMemoryItem,
    RecentReflectionItem,
    TopicItem,
    WeeklyReportPlaceholder,
)
from src.core.agent import CognitiveAgent
from src.core.memory_queue import MemoryWriteWorker
from src.core.types import Memory

logger = logging.getLogger(__name__)


def create_dashboard_router(
    agent: CognitiveAgent, writer: MemoryWriteWorker | None = None
) -> APIRouter:
    router = APIRouter(prefix="/dashboard", tags=["dashboard"])

    # ── 辅助函数 ──────────────────────────────────────────────────────

    def _db():
        """获取原始 sqlite_utils Database 对象，用于聚合查询。"""
        return agent._memory_store._db

    # ── 现有端点 ──────────────────────────────────────────────────────

    @router.get("/metrics")
    async def metrics():
        memory_store = agent._memory_store
        try:
            recent = memory_store.get_recent(limit=1000)
            memory_count = len(recent)
            reflection_count = sum(1 for m in recent if m.source == "reflect")
        except Exception:
            memory_count = 0
            reflection_count = 0

        return {
            "memory_count": memory_count,
            "memory_growth": 0,
            "recall_success_rate": 95,
            "reflection_count": reflection_count,
            "tool_calls_today": 0,
            "avg_latency_ms": 0,
            "token_usage": 0,
            "active_sessions": 1,
        }

    @router.get("/runtime")
    async def runtime():
        """Runtime Monitor — MemoryWriteWorker 实时状态、任务历史、DLQ。"""
        if writer is None:
            return {"status": "unavailable", "reason": "MemoryWriteWorker 未配置"}
        return writer.stats

    @router.get("/traces")
    async def traces():
        return []

    # ── 新增端点 ──────────────────────────────────────────────────────

    @router.get("/summary", response_model=DashboardSummary)
    async def summary():
        """记忆全景摘要 — 各状态/类型数量 + 队列深度 + DLQ。"""
        try:
            rows = _db().execute(
                """SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) as active,
                    SUM(CASE WHEN status='archived' THEN 1 ELSE 0 END) as archived,
                    SUM(CASE WHEN status='merged' THEN 1 ELSE 0 END) as merged,
                    SUM(CASE WHEN status='deleted' THEN 1 ELSE 0 END) as deleted,
                    SUM(CASE WHEN memory_type='episodic' THEN 1 ELSE 0 END) as episodic,
                    SUM(CASE WHEN memory_type='semantic' THEN 1 ELSE 0 END) as semantic,
                    SUM(CASE WHEN source='reflect' THEN 1 ELSE 0 END) as reflect
                FROM notes"""
            ).fetchone()

            # 本周新增
            week_row = _db().execute(
                """SELECT COUNT(*) as cnt FROM notes
                   WHERE timestamp >= datetime('now', '-7 days', 'localtime')"""
            ).fetchone()
            weekly_growth = week_row["cnt"] if week_row else 0

            # Writer stats
            queue_depth = writer.pending if writer else 0
            dlq_count = (
                writer.stats.get("dead_letter", {}).get("count", 0) if writer else 0
            )

            return DashboardSummary(
                total_memories=rows["total"] or 0,
                active_memories=rows["active"] or 0,
                archived_memories=rows["archived"] or 0,
                merged_memories=rows["merged"] or 0,
                deleted_memories=rows["deleted"] or 0,
                episodic_count=rows["episodic"] or 0,
                semantic_count=rows["semantic"] or 0,
                reflect_count=rows["reflect"] or 0,
                weekly_growth=weekly_growth,
                queue_depth=queue_depth,
                dlq_count=dlq_count,
            )
        except Exception:
            logger.warning("dashboard_summary_failed", exc_info=True)
            return DashboardSummary()

    @router.get("/topics", response_model=list[TopicItem])
    async def topics(limit: int = Query(default=10, ge=1, le=100)):
        """Top Topics — 按 mention_count 降序排列的实体。"""
        try:
            rows = _db().execute(
                """SELECT e.name, e.mention_count, COUNT(me.memory_id) as memory_count
                   FROM entities e
                   LEFT JOIN memory_entities me ON e.id = me.entity_id
                   GROUP BY e.id
                   ORDER BY e.mention_count DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            return [
                TopicItem(
                    name=r["name"],
                    mention_count=r["mention_count"],
                    memory_count=r["memory_count"],
                )
                for r in rows
            ]
        except Exception:
            logger.warning("dashboard_topics_failed", exc_info=True)
            return []

    @router.get("/entities", response_model=list[EntityItem])
    async def entities(limit: int = Query(default=20, ge=1, le=100)):
        """Top Entities — 按 mention_count 降序排列的实体排行榜。"""
        try:
            rows = _db().execute(
                """SELECT name, entity_type, mention_count, first_seen
                   FROM entities
                   ORDER BY mention_count DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            return [
                EntityItem(
                    name=r["name"],
                    entity_type=r["entity_type"] or "",
                    mention_count=r["mention_count"],
                    first_seen=r["first_seen"],
                )
                for r in rows
            ]
        except Exception:
            logger.warning("dashboard_entities_failed", exc_info=True)
            return []

    @router.get("/recent", response_model=list[RecentMemoryItem])
    async def recent(limit: int = Query(default=20, ge=1, le=200)):
        """最近记忆流 — 按 timestamp 降序排列的最新 N 条记忆。"""
        try:
            memories = agent._memory_store.get_recent(limit=limit)
            return [
                RecentMemoryItem(
                    id=m.id,
                    content_preview=(m.summary or m.content)[:120],
                    source=m.source,
                    timestamp=m.timestamp.isoformat(),
                    importance=m.importance,
                    memory_type=m.memory_type,
                    status=m.status,
                    entities=m.entities,
                )
                for m in memories
            ]
        except Exception:
            logger.warning("dashboard_recent_failed", exc_info=True)
            return []

    @router.get("/reflections", response_model=list[RecentReflectionItem])
    async def reflections(limit: int = Query(default=10, ge=1, le=100)):
        """最近反思 — 来源为 reflect 的最近记忆。"""
        try:
            recent = agent._memory_store.get_recent(limit=200)
            reflect_memories = [
                m for m in recent if m.source == "reflect"
            ][:limit]
            return [
                RecentReflectionItem(
                    id=m.id,
                    topic=(m.entities[0] if m.entities else "未分类"),
                    finding=(m.summary or m.content)[:200],
                    importance=m.importance,
                    timestamp=m.timestamp.isoformat(),
                    entities=m.entities,
                )
                for m in reflect_memories
            ]
        except Exception:
            logger.warning("dashboard_reflections_failed", exc_info=True)
            return []

    @router.get("/weekly-report", response_model=WeeklyReportPlaceholder)
    async def weekly_report():
        """最近周报 — v0.4 实现完整周报，当前返回基本统计。"""
        try:
            # 本周新增记忆
            week_new = _db().execute(
                """SELECT COUNT(*) as cnt FROM notes
                   WHERE timestamp >= datetime('now', '-7 days', 'localtime')"""
            ).fetchone()

            # 本周反思数
            week_reflect = _db().execute(
                """SELECT COUNT(*) as cnt FROM notes
                   WHERE source='reflect'
                   AND timestamp >= datetime('now', '-7 days', 'localtime')"""
            ).fetchone()

            # Top 3 实体
            top_entities = _db().execute(
                """SELECT name FROM entities
                   ORDER BY mention_count DESC LIMIT 3"""
            ).fetchall()

            return WeeklyReportPlaceholder(
                status="not_implemented",
                message="周报功能计划在 v0.4 实现",
                stats={
                    "week_new_memories": week_new["cnt"] if week_new else 0,
                    "week_reflections": week_reflect["cnt"] if week_reflect else 0,
                    "week_top_entities": [r["name"] for r in top_entities],
                },
            )
        except Exception:
            logger.warning("dashboard_weekly_report_failed", exc_info=True)
            return WeeklyReportPlaceholder()

    return router
