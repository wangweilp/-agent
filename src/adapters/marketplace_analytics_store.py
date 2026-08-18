"""SQLite Marketplace Analytics Store — recommendations/rankings/analytics_events。

纯 metadata 操作，不执行 runtime/container/microVM。
"""

from __future__ import annotations

import json, logging
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.marketplace_analytics import (
    RecommendedAgent, AgentRank, AnalyticsMetrics, AnalyticsEvent, _safe_dt,
)

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analytics_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    agent_module_id TEXT NOT NULL,
    agent_name TEXT NOT NULL DEFAULT '',
    score REAL NOT NULL DEFAULT 0.0,
    reason TEXT NOT NULL DEFAULT 'popular',
    sub_reasons_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_arec_ws ON analytics_recommendations(workspace_id);

CREATE TABLE IF NOT EXISTS analytics_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_module_id TEXT NOT NULL,
    agent_name TEXT NOT NULL DEFAULT '',
    rank INTEGER NOT NULL DEFAULT 0,
    category TEXT NOT NULL DEFAULT 'top_rated',
    score REAL NOT NULL DEFAULT 0.0,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_arank_cat ON analytics_rankings(category);

CREATE TABLE IF NOT EXISTS analytics_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    total_modules INTEGER NOT NULL DEFAULT 0,
    published_modules INTEGER NOT NULL DEFAULT 0,
    total_reviews INTEGER NOT NULL DEFAULT 0,
    average_rating REAL NOT NULL DEFAULT 0.0,
    average_trust REAL NOT NULL DEFAULT 0.0,
    total_subscriptions INTEGER NOT NULL DEFAULT 0,
    active_workspaces INTEGER NOT NULL DEFAULT 0,
    risk_distribution_json TEXT NOT NULL DEFAULT '{}',
    top_categories_json TEXT NOT NULL DEFAULT '[]',
    trending_tags_json TEXT NOT NULL DEFAULT '[]',
    recent_growth_rate REAL NOT NULL DEFAULT 0.0,
    calculated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS analytics_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL DEFAULT '',
    dimension TEXT NOT NULL DEFAULT '',
    agent_module_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_aevt_module ON analytics_events(agent_module_id);
CREATE INDEX IF NOT EXISTS idx_aevt_ws ON analytics_events(workspace_id);
CREATE INDEX IF NOT EXISTS idx_aevt_type ON analytics_events(event_type);
"""


class SQLiteMarketplaceAnalyticsStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="analytics_init")

    def _init_schema(self):
        for stmt in _SCHEMA.strip().split(";"):
            if stmt.strip(): self._db.execute(stmt.strip())
        try: self._db.conn.commit()
        except Exception: pass

    def flush(self):
        try:
            if hasattr(self._db, "conn") and self._db.conn: self._db.conn.commit()
        except Exception: pass

    def _exec(self, sql, params=None): return self._db.execute(sql, params or [])

    # ── Recommendations ──

    def save_recommendations(self, workspace_id: str, recs: list[RecommendedAgent]) -> None:
        # 先清理旧推荐
        self._exec("DELETE FROM analytics_recommendations WHERE workspace_id=?", [workspace_id])
        now = datetime.now(timezone.utc).isoformat()
        for r in recs:
            self._exec("""INSERT INTO analytics_recommendations
                (workspace_id, agent_module_id, agent_name, score, reason, sub_reasons_json, confidence, created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                [workspace_id, r.agent_module_id, r.agent_name, r.score, r.reason,
                 json.dumps(r.sub_reasons, ensure_ascii=False), r.confidence, now])

    def get_recommendations(self, workspace_id: str, limit: int = 20) -> list[RecommendedAgent]:
        rows = self._exec(
            "SELECT * FROM analytics_recommendations WHERE workspace_id=? ORDER BY score DESC LIMIT ?",
            [workspace_id, int(limit)])
        return [self._row_recommendation(dict(r)) for r in rows]

    # ── Rankings ──

    def save_rankings(self, category: str, ranks: list[AgentRank]) -> None:
        self._exec("DELETE FROM analytics_rankings WHERE category=?", [category])
        now = datetime.now(timezone.utc).isoformat()
        for r in ranks:
            self._exec("""INSERT INTO analytics_rankings
                (agent_module_id, agent_name, rank, category, score, metrics_json, created_at)
                VALUES (?,?,?,?,?,?,?)""",
                [r.agent_module_id, r.agent_name, r.rank, category, r.score,
                 json.dumps(r.metrics, ensure_ascii=False), now])

    def get_rankings(self, category: str, limit: int = 20) -> list[AgentRank]:
        rows = self._exec(
            "SELECT * FROM analytics_rankings WHERE category=? ORDER BY rank ASC LIMIT ?",
            [category, int(limit)])
        return [self._row_rank(dict(r)) for r in rows]

    # ── Analytics Metrics ──

    def save_analytics_metrics(self, m: AnalyticsMetrics) -> None:
        self._exec("""INSERT INTO analytics_metrics
            (total_modules, published_modules, total_reviews, average_rating,
             average_trust, total_subscriptions, active_workspaces,
             risk_distribution_json, top_categories_json, trending_tags_json,
             recent_growth_rate, calculated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            [m.total_modules, m.published_modules, m.total_reviews,
             m.average_platform_rating, m.average_platform_trust,
             m.total_subscriptions, m.active_workspaces,
             json.dumps(m.risk_distribution, ensure_ascii=False),
             json.dumps(m.top_categories, ensure_ascii=False),
             json.dumps(m.trending_tags, ensure_ascii=False),
             m.recent_growth_rate, m.calculated_at.isoformat()])

    def get_latest_metrics(self) -> AnalyticsMetrics | None:
        row = next(self._exec(
            # calculated_at 相同（同一微秒）时按 rowid 取最新，保证确定性
            "SELECT * FROM analytics_metrics ORDER BY calculated_at DESC, rowid DESC LIMIT 1"), None)
        return self._row_metrics(dict(row)) if row else None

    def get_metrics_history(self, limit: int = 10) -> list[AnalyticsMetrics]:
        rows = self._exec(
            "SELECT * FROM analytics_metrics ORDER BY calculated_at DESC, rowid DESC LIMIT ?", [int(limit)])
        return [self._row_metrics(dict(r)) for r in rows]

    # ── Events ──

    def record_event(self, evt: AnalyticsEvent) -> None:
        self._exec("""INSERT INTO analytics_events
            (id, event_type, dimension, agent_module_id, workspace_id, payload_json)
            VALUES (?,?,?,?,?,?)""",
            [evt.id, evt.event_type, evt.dimension, evt.agent_module_id,
             evt.workspace_id, json.dumps(evt.payload, ensure_ascii=False)])

    def get_events(self, agent_module_id: str = "", limit: int = 50) -> list[AnalyticsEvent]:
        sql = "SELECT * FROM analytics_events"
        params: list[Any] = []
        if agent_module_id:
            sql += " WHERE agent_module_id=?"
            params.append(agent_module_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(int(limit))
        return [self._row_event(dict(r)) for r in self._exec(sql, params)]

    # ── Row mappers ──

    @staticmethod
    def _row_recommendation(row: dict) -> RecommendedAgent:
        return RecommendedAgent(
            agent_module_id=row["agent_module_id"], agent_name=row.get("agent_name", ""),
            score=float(row.get("score", 0)), reason=row.get("reason", "popular"),
            sub_reasons=json.loads(row.get("sub_reasons_json", "[]")),
            confidence=float(row.get("confidence", 0)))

    @staticmethod
    def _row_rank(row: dict) -> AgentRank:
        return AgentRank(
            agent_module_id=row["agent_module_id"], agent_name=row.get("agent_name", ""),
            rank=int(row.get("rank", 0)), category=row.get("category", "top_rated"),
            score=float(row.get("score", 0)),
            metrics=json.loads(row.get("metrics_json", "{}")))

    @staticmethod
    def _row_metrics(row: dict) -> AnalyticsMetrics:
        return AnalyticsMetrics(
            total_modules=int(row.get("total_modules", 0)),
            published_modules=int(row.get("published_modules", 0)),
            total_reviews=int(row.get("total_reviews", 0)),
            average_platform_rating=float(row.get("average_rating", 0)),
            average_platform_trust=float(row.get("average_trust", 0)),
            total_subscriptions=int(row.get("total_subscriptions", 0)),
            active_workspaces=int(row.get("active_workspaces", 0)),
            risk_distribution=json.loads(row.get("risk_distribution_json", "{}")),
            top_categories=json.loads(row.get("top_categories_json", "[]")),
            trending_tags=json.loads(row.get("trending_tags_json", "[]")),
            recent_growth_rate=float(row.get("recent_growth_rate", 0)),
            calculated_at=_safe_dt(row.get("calculated_at")))

    @staticmethod
    def _row_event(row: dict) -> AnalyticsEvent:
        return AnalyticsEvent(
            id=row["id"], event_type=row.get("event_type", ""),
            dimension=row.get("dimension", ""),
            agent_module_id=row.get("agent_module_id", ""),
            workspace_id=row.get("workspace_id", ""),
            payload=json.loads(row.get("payload_json", "{}")),
            created_at=_safe_dt(row.get("created_at")))
