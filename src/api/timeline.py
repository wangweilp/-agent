"""Timeline 路由 — 记忆时间轴。

所有事件从已有 notes 表派生，不维护独立事件存储。
事件类型映射：
  - memory_created          → 任何记忆的 timestamp 即为创建时间
  - memory_archived         → status="archived" AND archived_at IS NOT NULL
  - memory_merged           → status="merged"
  - memory_promoted         → memory_type="semantic" AND source="agent"
  - reflection_generated    → source="reflect"
  - image_uploaded          → content 中含 "[图片]" 或 memory_type="image"
  - weekly_report_generated → source="agent" AND content 中含 "周报"
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from src.api.schemas import TimelineDay, TimelineEvent, TimelineStats
from src.core.agent import CognitiveAgent

logger = logging.getLogger(__name__)

# 事件类型推断规则


def _event_type(memory: dict) -> str:
    source = memory.get("source", "")
    mtype = memory.get("memory_type", "")
    status = memory.get("status", "active")
    content = memory.get("content", "")
    archived_at = memory.get("archived_at")

    if status == "archived" and archived_at:
        return "memory_archived"
    if status == "merged":
        return "memory_merged"
    if source == "reflect":
        return "reflection_generated"
    if mtype == "image" or "[图片]" in content:
        return "image_uploaded"
    if source == "agent" and "周报" in content:
        return "weekly_report_generated"
    if mtype == "semantic" and source == "agent":
        return "memory_promoted"
    return "memory_created"


def _row_to_event(row: dict) -> TimelineEvent:
    import json

    entities = json.loads(row.get("entities_json") or "[]")
    return TimelineEvent(
        id=row["id"],
        type=_event_type(row),
        content_preview=(row.get("summary") or row["content"])[:150],
        memory_type=row.get("memory_type", "episodic"),
        importance=row.get("importance", 5),
        entities=entities,
        timestamp=row["timestamp"],
        status=row.get("status", "active"),
    )


def create_timeline_router(agent: CognitiveAgent) -> APIRouter:
    router = APIRouter(prefix="/timeline", tags=["timeline"])

    def _db():
        return agent._memory_store._db

    @router.get("", response_model=list[TimelineDay])
    async def list_timeline(
        start_date: str = "",
        end_date: str = "",
        memory_type: str = "",
        entity: str = "",
        page: int = Query(default=1, ge=1),
        limit: int = Query(default=30, ge=1, le=200),
    ):
        """按日期分页返回时间轴事件。每天一个 TimelineDay。"""
        try:
            where = ["1=1"]
            params: list = []

            if start_date:
                where.append("timestamp >= ?")
                params.append(start_date)
            if end_date:
                where.append("timestamp <= ?")
                params.append(f"{end_date}T23:59:59")
            if memory_type:
                where.append("memory_type = ?")
                params.append(memory_type)
            if entity:
                where.append("entities_json LIKE ?")
                params.append(f"%{entity}%")

            # Also include archived events (archived_at within range)
            # For archived events, use archived_at as the display time
            sql = f"""
                SELECT id, content, summary, source, timestamp, importance,
                       entities_json, memory_type, status, archived_at
                FROM notes
                WHERE {' AND '.join(where)}
                ORDER BY timestamp DESC
            """
            rows = _db().execute(sql, params).fetchall()

            # Group by date
            days: dict[str, list[dict]] = {}
            for row in rows:
                r = dict(row)
                ts_str = r["timestamp"]
                # Also generate archived event if applicable
                if r.get("archived_at") and r.get("status") == "archived":
                    archived_row = dict(r)
                    archived_row["_event_type"] = "memory_archived"
                    archived_row["timestamp"] = r["archived_at"]
                    arch_date = r["archived_at"][:10]
                    days.setdefault(arch_date, []).append(archived_row)

                date = ts_str[:10]
                days.setdefault(date, []).append(r)

            # Sort days descending, take page slice
            sorted_dates = sorted(days.keys(), reverse=True)
            total_dates = len(sorted_dates)
            start_idx = (page - 1) * limit
            page_dates = sorted_dates[start_idx:start_idx + limit]

            result = []
            for date in page_dates:
                events = [
                    _row_to_event(e)
                    for e in days[date]
                ]
                # Deduplicate by id+type
                seen = set()
                unique_events = []
                for evt in events:
                    key = (evt.id, evt.type)
                    if key not in seen:
                        seen.add(key)
                        unique_events.append(evt)

                result.append(TimelineDay(
                    date=date,
                    events=unique_events,
                    count=len(unique_events),
                ))

            return result

        except Exception:
            logger.warning("timeline_list_failed", exc_info=True)
            return []

    @router.get("/day/{date}", response_model=TimelineDay)
    async def day_detail(date: str):
        """返回某一天的完整事件列表。"""
        try:
            rows = _db().execute(
                """SELECT id, content, summary, source, timestamp, importance,
                          entities_json, memory_type, status, archived_at
                   FROM notes
                   WHERE timestamp >= ? AND timestamp < ?
                   ORDER BY timestamp DESC""",
                (f"{date}T00:00:00", f"{date}T23:59:59"),
            ).fetchall()

            if not rows:
                raise HTTPException(status_code=404, detail=f"日期 {date} 无事件")

            events = [_row_to_event(dict(r)) for r in rows]
            return TimelineDay(date=date, events=events, count=len(events))

        except HTTPException:
            raise
        except Exception:
            logger.warning("timeline_day_failed", exc_info=True)
            raise HTTPException(status_code=500, detail="查询失败")

    @router.get("/stats", response_model=TimelineStats)
    async def stats(
        start_date: str = "",
        end_date: str = "",
    ):
        """返回时间范围内的聚合统计。"""
        try:
            where = ["1=1"]
            params: list = []
            if start_date:
                where.append("timestamp >= ?")
                params.append(start_date)
            if end_date:
                where.append("timestamp <= ?")
                params.append(f"{end_date}T23:59:59")

            rows = _db().execute(
                f"""SELECT id, content, summary, source, timestamp, importance,
                           entities_json, memory_type, status, archived_at
                    FROM notes WHERE {' AND '.join(where)}""",
                params,
            ).fetchall()

            result = TimelineStats(total_events=len(rows))
            for r in rows:
                row = dict(r)
                et = _event_type(row)
                if et == "memory_created":
                    result.created_count += 1
                elif et == "memory_archived":
                    result.archived_count += 1
                elif et == "memory_merged":
                    result.merged_count += 1
                elif et == "reflection_generated":
                    result.reflection_count += 1
                elif et == "image_uploaded":
                    result.image_count += 1
                elif et == "memory_promoted":
                    result.promoted_count += 1
                elif et == "weekly_report_generated":
                    result.weekly_report_count += 1

            return result

        except Exception:
            logger.warning("timeline_stats_failed", exc_info=True)
            return TimelineStats()

    return router
