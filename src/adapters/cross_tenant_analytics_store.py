"""Cross-Tenant Analytics Store — 跨租户指标持久化。

metadata-only，不执行 runtime/container/microVM。
"""

from __future__ import annotations

import json, logging
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.cross_tenant_analytics import (
    CrossTenantMetrics, PlatformTrend, TenantUsageSummary, _safe_dt,
)

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ct_analytics_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_json TEXT NOT NULL DEFAULT '{}',
    calculated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ct_tenant_summaries (
    workspace_id TEXT NOT NULL,
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    summary_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (workspace_id, calculated_at)
);

CREATE TABLE IF NOT EXISTS ct_trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL DEFAULT 'daily',
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    metric_name TEXT NOT NULL DEFAULT '',
    value REAL NOT NULL DEFAULT 0.0,
    previous_value REAL NOT NULL DEFAULT 0.0,
    direction TEXT NOT NULL DEFAULT 'flat',
    change_percent REAL NOT NULL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_ct_trend_metric ON ct_trends(metric_name, timestamp);
"""


class CrossTenantAnalyticsStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="ct_analytics_init")

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

    def save_snapshot(self, metrics: CrossTenantMetrics) -> None:
        self._exec("INSERT INTO ct_analytics_snapshots (snapshot_json, calculated_at) VALUES (?,?)",
                   [json.dumps(metrics.to_dict(), ensure_ascii=False), metrics.calculated_at.isoformat()])

    def get_latest_snapshot(self) -> CrossTenantMetrics | None:
        row = next(self._exec(
            "SELECT * FROM ct_analytics_snapshots ORDER BY calculated_at DESC LIMIT 1"), None)
        if not row: return None
        d = json.loads(row["snapshot_json"])
        return CrossTenantMetrics(
            total_tenants=d.get("total_tenants", 0),
            active_tenants=d.get("active_tenants", 0),
            trial_tenants=d.get("trial_tenants", 0),
            paying_tenants=d.get("paying_tenants", 0),
            total_modules=d.get("total_modules", 0),
            total_artifacts=d.get("total_artifacts", 0),
            total_packages=d.get("total_packages", 0),
            total_workflows=d.get("total_workflows", 0),
            total_subscriptions=d.get("total_subscriptions", 0),
            total_reviews=d.get("total_reviews", 0),
            total_reports=d.get("total_reports", 0),
            total_llm_calls=d.get("total_llm_calls", 0),
            total_embedding_calls=d.get("total_embedding_calls", 0),
            conversion_rate=d.get("conversion_rate", 0),
            platform_trust_avg=d.get("platform_trust_avg", 0),
            platform_rating_avg=d.get("platform_rating_avg", 0),
            top_workspaces=d.get("top_workspaces", []),
            plan_distribution=d.get("plan_distribution", {}),
            category_distribution=d.get("category_distribution", {}),
            trends=d.get("trends", []),
            calculated_at=_safe_dt(d.get("calculated_at")),
        )

    def save_tenant_summary(self, summary: TenantUsageSummary) -> None:
        self._exec("""INSERT OR REPLACE INTO ct_tenant_summaries
            (workspace_id, calculated_at, summary_json) VALUES (?,?,?)""",
            [summary.workspace_id, datetime.now(timezone.utc).isoformat(),
             json.dumps(summary.to_dict(), ensure_ascii=False)])

    def get_tenant_summaries(self) -> list[TenantUsageSummary]:
        rows = self._exec("""SELECT DISTINCT workspace_id, summary_json
            FROM ct_tenant_summaries
            WHERE calculated_at = (SELECT MAX(calculated_at) FROM ct_tenant_summaries t2
            WHERE t2.workspace_id = ct_tenant_summaries.workspace_id)
            ORDER BY workspace_id""")
        return [self._row_tenant_summary(dict(r)) for r in rows]

    def save_trends(self, trends: list[PlatformTrend]) -> None:
        for t in trends:
            self._exec("""INSERT INTO ct_trends
                (period, timestamp, metric_name, value, previous_value, direction, change_percent)
                VALUES (?,?,?,?,?,?,?)""",
                [t.period, t.timestamp, t.metric_name, t.value,
                 t.previous_value, t.direction, t.change_percent])

    def get_trends(self, metric_name: str = "", period: str = "", limit: int = 50) -> list[PlatformTrend]:
        sql = "SELECT * FROM ct_trends WHERE 1=1"
        params: list[Any] = []
        if metric_name:
            sql += " AND metric_name=?"
            params.append(metric_name)
        if period:
            sql += " AND period=?"
            params.append(period)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(int(limit))
        return [self._row_trend(dict(r)) for r in self._exec(sql, params)]

    @staticmethod
    def _row_trend(row: dict) -> PlatformTrend:
        return PlatformTrend(
            period=row.get("period", "daily"), timestamp=row.get("timestamp", ""),
            metric_name=row.get("metric_name", ""),
            value=float(row.get("value", 0)), previous_value=float(row.get("previous_value", 0)),
            direction=row.get("direction", "flat"),
            change_percent=float(row.get("change_percent", 0)))

    @staticmethod
    def _row_tenant_summary(row: dict) -> TenantUsageSummary:
        d = json.loads(row.get("summary_json", "{}"))
        return TenantUsageSummary(
            workspace_id=row["workspace_id"],
            tenant_name=d.get("tenant_name", ""), plan_tier=d.get("plan_tier", "free"),
            total_modules=d.get("total_modules", 0),
            published_modules=d.get("published_modules", 0),
            total_artifacts=d.get("total_artifacts", 0),
            total_packages=d.get("total_packages", 0),
            total_workflows=d.get("total_workflows", 0),
            total_subscriptions=d.get("total_subscriptions", 0),
            total_reviews=d.get("total_reviews", 0), total_reports=d.get("total_reports", 0),
            llm_calls=d.get("llm_calls", 0), embedding_calls=d.get("embedding_calls", 0),
            storage_bytes=d.get("storage_bytes", 0),
            last_active=_safe_dt(d.get("last_active")),
        )
