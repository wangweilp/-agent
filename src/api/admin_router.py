"""Admin router for dashboard summary, growth, and config."""

from collections import Counter
from datetime import datetime, timedelta, timezone
import logging

from fastapi import APIRouter, Depends, Query

from src.adapters.production_backends import assess_production_backend_readiness

from .middleware import require_manage

logger = logging.getLogger(__name__)

_RISK_ACTION_KEYWORDS = (
    "delete",
    "remove",
    "revoke",
    "deny",
    "disable",
    "fail",
    "suspend",
    "terminate",
)


def _count_rows(db, sql: str, params: tuple = ()) -> int:
    row = db.execute(sql, params).fetchone()
    if row is None:
        return 0
    data = dict(row)
    return int(data.get("cnt", 0) or 0)


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _memory_growth_rate(memory_store) -> float:
    now = datetime.now(timezone.utc)
    this_week_start = (now.date() - timedelta(days=now.weekday()))
    last_week_start = this_week_start - timedelta(days=7)
    prev_week_start = this_week_start - timedelta(days=14)

    def _count_since(start: datetime.date, end: datetime.date) -> int:
        start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc)
        return _count_rows(
            memory_store._db,
            "SELECT COUNT(*) AS cnt FROM notes WHERE timestamp >= ? AND timestamp < ?",
            (start_dt.isoformat(), end_dt.isoformat()),
        )

    last_week = _count_since(last_week_start, this_week_start)
    prev_week = _count_since(prev_week_start, last_week_start)
    if prev_week == 0:
        return float(last_week * 100) if last_week > 0 else 0.0
    return round(((last_week - prev_week) / prev_week) * 100, 1)


def _weekly_growth_series(memory_store, weeks: int) -> list[dict[str, int | str]]:
    now = datetime.now(timezone.utc)
    current_week_start = now.date() - timedelta(days=now.weekday())
    first_week_start = current_week_start - timedelta(weeks=weeks - 1)
    buckets: Counter[str] = Counter()

    rows = memory_store._db.execute(
        "SELECT timestamp FROM notes WHERE timestamp >= ?",
        (datetime.combine(first_week_start, datetime.min.time(), tzinfo=timezone.utc).isoformat(),),
    ).fetchall()
    for row in rows:
        ts = _parse_timestamp(dict(row)["timestamp"])
        week_start = ts.date() - timedelta(days=ts.weekday())
        buckets[week_start.isoformat()] += 1

    series: list[dict[str, int | str]] = []
    for index in range(weeks):
        week_start = first_week_start + timedelta(weeks=index)
        key = week_start.isoformat()
        series.append({
            "week": week_start.strftime("%m/%d"),
            "count": buckets.get(key, 0),
        })
    return series


def create_admin_router(settings, org_store, auth_store, collab_store, memory_store) -> APIRouter:
    router = APIRouter(prefix="/api/admin", tags=["Admin"])

    @router.get("/summary")
    async def summary(payload=Depends(require_manage)):
        workspace_id = payload.workspace_id
        audit_summary = collab_store.get_audit_summary(workspace_id)

        total_orgs = _count_rows(org_store._db, "SELECT COUNT(*) AS cnt FROM organizations")
        total_users = _count_rows(auth_store._db, "SELECT COUNT(*) AS cnt FROM users")
        total_memories = _count_rows(memory_store._db, "SELECT COUNT(*) AS cnt FROM notes")
        audit_events_30d = sum(audit_summary.last_30d.values())
        risk_events = sum(
            count
            for action, count in audit_summary.last_30d.items()
            if any(keyword in action.lower() for keyword in _RISK_ACTION_KEYWORDS)
        )

        return {
            "total_orgs": total_orgs,
            "total_users": total_users,
            "total_memories": total_memories,
            "growth_rate_weekly": _memory_growth_rate(memory_store),
            "audit_events_30d": audit_events_30d,
            "risk_events": risk_events,
        }

    @router.get("/growth")
    async def growth(weeks: int = Query(12, ge=1, le=52), payload=Depends(require_manage)):
        return _weekly_growth_series(memory_store, weeks)

    @router.get("/config")
    async def config(payload=Depends(require_manage)):
        return {
            "db_type": "SQLite",
            "vector_store": "ChromaDB",
            "database_backend": settings.database_backend,
            "cache_backend": settings.cache_backend,
            "object_storage_backend": settings.object_storage_backend,
            "queue_backend": settings.queue_backend,
            "llm_provider": "DeepSeek",
            "embedding_model": settings.embedding_model,
            "auth_enabled": True,
            "cors_origins": settings.cors_allowed_origins,
            "log_level": settings.log_level,
            "environment": settings.environment,
        }

    @router.get("/production-backends")
    async def production_backends(payload=Depends(require_manage)):
        return assess_production_backend_readiness(settings)

    return router
