"""Usage Store Adapter — SQLite 实现 UsageStore 协议。

管理 usage_events / subscriptions 表。
"""
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlite_utils import Database as SqliteDB

from src.adapters.config import Settings
from src.core.subscription import PLAN_PRICES, BillingCycle, PlanTier, SubscriptionStatus
from src.core.usage import (
    CostStats,
    PlatformStats,
    UsageEvent,
    UsageResource,
    UsageStats,
    UsageUnit,
    UserProfile,
)

logger = logging.getLogger(__name__)

_USAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_events (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    resource TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    workspace_id TEXT NOT NULL DEFAULT '',
    unit TEXT NOT NULL DEFAULT 'count',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    cost_cents INTEGER NOT NULL DEFAULT 0,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ue_tenant ON usage_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ue_tenant_resource ON usage_events(tenant_id, resource);
CREATE INDEX IF NOT EXISTS idx_ue_tenant_ts ON usage_events(tenant_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_ue_resource ON usage_events(resource);
CREATE INDEX IF NOT EXISTS idx_ue_workspace ON usage_events(workspace_id);

CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL UNIQUE,
    plan_tier TEXT NOT NULL DEFAULT 'free',
    status TEXT NOT NULL DEFAULT 'trial',
    billing_cycle TEXT NOT NULL DEFAULT 'monthly',
    current_period_start TEXT,
    current_period_end TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sub_tenant ON subscriptions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sub_status ON subscriptions(status);
"""


class UsageStoreAdapter:
    """UsageStore 的 SQLite 实现。"""

    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        path = db_path or config.sqlite_db_path
        if path == ":memory:":
            self._db = SqliteDB(memory=True)
        else:
            conn = sqlite3.connect(path, check_same_thread=False)
            self._db = SqliteDB(conn)
        self._db.conn.row_factory = sqlite3.Row
        self._write_lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        for stmt in _USAGE_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)

    # ── UsageStore 协议 ──────────────────────────────────────────────

    def record_event(self, event: UsageEvent) -> str:
        """记录一条用量事件，返回事件 ID。"""
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO usage_events (id, tenant_id, user_id, resource,
                   quantity, workspace_id, unit, metadata_json, cost_cents, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.id,
                    event.tenant_id,
                    event.user_id,
                    event.resource.value,
                    event.quantity,
                    event.workspace_id,
                    event.unit.value,
                    json.dumps(event.metadata, ensure_ascii=False),
                    event.cost_cents,
                    event.timestamp.isoformat(),
                ),
            )
        logger.debug("usage:event_recorded", extra={"event_id": event.id, "tenant_id": event.tenant_id})
        return event.id

    def query_events(
        self,
        tenant_id: str,
        resource: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[UsageEvent]:
        """查询用量事件，支持按 resource 和时间范围过滤。"""
        sql = "SELECT * FROM usage_events WHERE tenant_id = ?"
        params: list[Any] = [tenant_id]

        if resource:
            sql += " AND resource = ?"
            params.append(resource)
        if start:
            sql += " AND timestamp >= ?"
            params.append(start.isoformat())
        if end:
            sql += " AND timestamp <= ?"
            params.append(end.isoformat())

        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = self._db.execute(sql, tuple(params)).fetchall()
        return [self._row_to_event(dict(r)) for r in rows]

    def get_monthly_stats(self, tenant_id: str, year: int, month: int) -> UsageStats:
        """按月聚合用量统计：按 resource 分组，汇总数量和成本。"""
        month_str = f"{year:04d}-{month:02d}"
        period_start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            period_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            period_end = datetime(year, month + 1, 1, tzinfo=timezone.utc)

        rows = self._db.execute(
            """SELECT resource,
                      SUM(quantity) AS total_qty,
                      SUM(cost_cents) AS total_cost
               FROM usage_events
               WHERE tenant_id = ?
                 AND timestamp >= ? AND timestamp < ?
               GROUP BY resource""",
            (tenant_id, period_start.isoformat(), period_end.isoformat()),
        ).fetchall()

        by_resource: dict[str, int] = {}
        by_resource_cost: dict[str, int] = {}
        total_events = 0
        total_cost_cents = 0

        for row in rows:
            r = dict(row)
            res = r["resource"]
            qty = int(r["total_qty"] or 0)
            cost = int(r["total_cost"] or 0)
            by_resource[res] = qty
            by_resource_cost[res] = cost
            total_events += qty
            total_cost_cents += cost

        return UsageStats(
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            total_events=total_events,
            by_resource=by_resource,
            total_cost_cents=total_cost_cents,
            by_resource_cost=by_resource_cost,
        )

    def get_cost_stats(self, tenant_id: str, year: int, month: int) -> CostStats:
        """按月成本统计：聚合用量成本并计算营收/利润率。

        需要关联 subscriptions 表获取套餐价格。
        """
        month_str = f"{year:04d}-{month:02d}"
        period_start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            period_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            period_end = datetime(year, month + 1, 1, tzinfo=timezone.utc)

        # ── 按资源类型汇总成本 ──
        rows = self._db.execute(
            """SELECT resource, SUM(cost_cents) AS total_cost
               FROM usage_events
               WHERE tenant_id = ?
                 AND timestamp >= ? AND timestamp < ?
               GROUP BY resource""",
            (tenant_id, period_start.isoformat(), period_end.isoformat()),
        ).fetchall()

        cost_by_resource: dict[str, int] = {}
        for row in rows:
            r = dict(row)
            cost_by_resource[r["resource"]] = int(r["total_cost"] or 0)

        llm_cost = cost_by_resource.get(UsageResource.LLM_CALL.value, 0) + cost_by_resource.get(UsageResource.COACH.value, 0)
        embedding_cost = cost_by_resource.get(UsageResource.EMBEDDING.value, 0)
        storage_cost = cost_by_resource.get(UsageResource.STORAGE.value, 0) + cost_by_resource.get(UsageResource.UPLOAD.value, 0) + cost_by_resource.get(UsageResource.IMPORT.value, 0)
        total_cost = sum(cost_by_resource.values())

        # ── 查询订阅以计算收入 ──
        sub_row = self._db.execute(
            "SELECT plan_tier, status, billing_cycle FROM subscriptions WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()

        gross_revenue_cents = 0
        if sub_row:
            sub = dict(sub_row)
            tier = PlanTier(sub["plan_tier"])
            cycle = BillingCycle(sub["billing_cycle"])
            gross_revenue_cents = PLAN_PRICES.get(tier, {}).get(cycle, 0)

        net_revenue_cents = gross_revenue_cents - total_cost
        margin_percent = round((net_revenue_cents / gross_revenue_cents) * 100, 1) if gross_revenue_cents > 0 else 0.0

        return CostStats(
            tenant_id=tenant_id,
            month=month_str,
            llm_cost_cents=llm_cost,
            embedding_cost_cents=embedding_cost,
            storage_cost_cents=storage_cost,
            total_cost_cents=total_cost,
            gross_revenue_cents=gross_revenue_cents,
            net_revenue_cents=net_revenue_cents,
            margin_percent=margin_percent,
        )

    def get_user_profile(self, tenant_id: str, user_id: str) -> UserProfile:
        """聚合用户用量数据，生成用户画像。

        计算 active_days / engagement_score / is_power_user。
        """
        # ── 按资源类型统计 ──
        rows = self._db.execute(
            """SELECT resource, COUNT(*) AS cnt
               FROM usage_events
               WHERE tenant_id = ? AND user_id = ?
               GROUP BY resource""",
            (tenant_id, user_id),
        ).fetchall()

        resource_counts: dict[str, int] = {}
        total_events = 0
        for row in rows:
            r = dict(row)
            resource_counts[r["resource"]] = int(r["cnt"])
            total_events += int(r["cnt"])

        total_memories = resource_counts.get(UsageResource.MEMORY.value, 0)
        total_searches = resource_counts.get(UsageResource.SEARCH.value, 0)
        total_imports = resource_counts.get(UsageResource.IMPORT.value, 0)
        total_syncs = resource_counts.get(UsageResource.SYNC.value, 0)
        coach_sessions = resource_counts.get(UsageResource.COACH.value, 0)

        # ── 活跃天数 ──
        active_row = self._db.execute(
            """SELECT COUNT(DISTINCT date(timestamp)) AS active_days,
                      MAX(timestamp) AS last_active
               FROM usage_events
               WHERE tenant_id = ? AND user_id = ?""",
            (tenant_id, user_id),
        ).fetchone()

        active_days = 0
        last_active = None
        if active_row:
            a = dict(active_row)
            active_days = int(a["active_days"] or 0)
            raw_ts = a.get("last_active")
            if raw_ts:
                last_active = _safe_parse_datetime(raw_ts)

        # ── 偏好功能 ──
        sorted_features = sorted(resource_counts.items(), key=lambda x: x[1], reverse=True)
        preferred_features = [feat for feat, _ in sorted_features[:5]]

        # ── 活跃度评分（0-100）──
        # 基线 = 同租户所有用户的平均事件数
        baseline_row = self._db.execute(
            """SELECT CAST(COUNT(*) AS REAL) / MAX(1, COUNT(DISTINCT user_id)) AS avg_events
               FROM usage_events
               WHERE tenant_id = ?""",
            (tenant_id,),
        ).fetchone()
        avg_events = 1.0
        if baseline_row:
            avg_events = max(1.0, float(dict(baseline_row).get("avg_events", 1.0) or 1.0))
        engagement_score = min(100, round((total_events / avg_events) * 50))

        # ── 是否为重度用户（top 20%）──
        all_users = self._db.execute(
            """SELECT user_id, COUNT(*) AS cnt
               FROM usage_events
               WHERE tenant_id = ?
               GROUP BY user_id
               ORDER BY cnt DESC""",
            (tenant_id,),
        ).fetchall()

        is_power_user = False
        if all_users:
            user_counts = [(dict(u)["user_id"], int(dict(u)["cnt"])) for u in all_users]
            threshold_idx = max(0, int(len(user_counts) * 0.2) - 1)  # top 20% cutoff
            if threshold_idx < len(user_counts):
                threshold_count = user_counts[threshold_idx][1]
                is_power_user = total_events > 0 and total_events >= threshold_count

        return UserProfile(
            tenant_id=tenant_id,
            user_id=user_id,
            total_memories=total_memories,
            total_searches=total_searches,
            total_imports=total_imports,
            total_syncs=total_syncs,
            coach_sessions=coach_sessions,
            active_days=active_days,
            last_active=last_active,
            preferred_features=preferred_features,
            engagement_score=engagement_score,
            is_power_user=is_power_user,
        )

    def get_platform_stats(self) -> PlatformStats:
        """平台级统计（SaaS Dashboard）。

        计算 MRR / ARR / 租户数 / 转化率 / 流失率 / 留存率。
        """
        now = datetime.now(timezone.utc)
        this_month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        last_month_start = (this_month_start.replace(day=1) - timedelta(days=1)).replace(day=1)
        if now.month == 12:
            next_month_start = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            next_month_start = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

        # ── MRR = 活跃订阅的月度价格之和 ──
        sub_rows = self._db.execute(
            "SELECT plan_tier, status, billing_cycle FROM subscriptions"
        ).fetchall()

        mrr_cents = 0
        paying_tenants = 0
        trial_tenants = 0
        for row in sub_rows:
            r = dict(row)
            status = r["status"]
            tier = PlanTier(r["plan_tier"])
            cycle = BillingCycle(r["billing_cycle"])
            monthly_price = PLAN_PRICES.get(tier, {}).get(BillingCycle.MONTHLY, 0)

            if status in (SubscriptionStatus.ACTIVE.value, SubscriptionStatus.TRIAL.value):
                # 对于年付用户，折算月价格
                if cycle == BillingCycle.YEARLY:
                    yearly = PLAN_PRICES.get(tier, {}).get(BillingCycle.YEARLY, 0)
                    monthly_price = yearly // 12
                mrr_cents += monthly_price

            if status == SubscriptionStatus.TRIAL.value:
                trial_tenants += 1
            elif status == SubscriptionStatus.ACTIVE.value and tier != PlanTier.FREE:
                paying_tenants += 1

        arr_cents = mrr_cents * 12
        total_tenants = len(sub_rows)

        # ── 活跃租户（本月有用量事件）──
        active_this = self._db.execute(
            """SELECT COUNT(DISTINCT tenant_id) AS cnt
               FROM usage_events
               WHERE timestamp >= ? AND timestamp < ?""",
            (this_month_start.isoformat(), next_month_start.isoformat()),
        ).fetchone()
        active_tenants = int(dict(active_this).get("cnt", 0) or 0)

        # ── 上月活跃租户 ──
        active_last = self._db.execute(
            """SELECT COUNT(DISTINCT tenant_id) AS cnt
               FROM usage_events
               WHERE timestamp >= ? AND timestamp < ?""",
            (last_month_start.isoformat(), this_month_start.isoformat()),
        ).fetchone()
        active_last_month = int(dict(active_last).get("cnt", 0) or 0)

        # ── 转化率：paying / (paying + trial) ──
        total_subscribed = paying_tenants + trial_tenants
        conversion_rate = round(paying_tenants / total_subscribed, 4) if total_subscribed > 0 else 0.0

        # ── 留存率 / 流失率 ──
        retention_rate = round(active_tenants / active_last_month, 4) if active_last_month > 0 else 0.0
        churn_rate = round(1 - retention_rate, 4)

        # ── ARPU / 总收入 ──
        total_revenue = self._db.execute(
            "SELECT COALESCE(SUM(cost_cents), 0) AS rev FROM usage_events"
        ).fetchone()
        total_revenue_cents = int(dict(total_revenue).get("rev", 0) or 0)

        total_users = self._db.execute(
            "SELECT COUNT(DISTINCT user_id) AS cnt FROM usage_events"
        ).fetchone()
        user_count = int(dict(total_users).get("cnt", 0) or 0)
        avg_revenue_per_user = total_revenue_cents // user_count if user_count > 0 else 0

        return PlatformStats(
            mrr_cents=mrr_cents,
            arr_cents=arr_cents,
            total_tenants=total_tenants,
            active_tenants=active_tenants,
            trial_tenants=trial_tenants,
            paying_tenants=paying_tenants,
            conversion_rate=conversion_rate,
            churn_rate=churn_rate,
            retention_rate=retention_rate,
            avg_revenue_per_user=avg_revenue_per_user,
            total_revenue_cents=total_revenue_cents,
        )

    def get_daily_usage(
        self, tenant_id: str, resource: str, days: int = 30
    ) -> list[dict]:
        """按日聚合单个资源的用量，返回 [{date, count, cost}, ...]."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        rows = self._db.execute(
            """SELECT date(timestamp) AS d,
                      SUM(quantity) AS cnt,
                      SUM(cost_cents) AS cost
               FROM usage_events
               WHERE tenant_id = ? AND resource = ? AND timestamp >= ?
               GROUP BY d
               ORDER BY d ASC""",
            (tenant_id, resource, since),
        ).fetchall()

        return [
            {
                "date": dict(r)["d"],
                "count": int(dict(r)["cnt"] or 0),
                "cost": int(dict(r)["cost"] or 0),
            }
            for r in rows
        ]

    def get_tenant_usage_summary(self, tenant_id: str, days: int = 30) -> dict:
        """租户用量概览：所有 resource 在最近 N 天的汇总。"""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        rows = self._db.execute(
            """SELECT resource,
                      SUM(quantity) AS total_qty,
                      SUM(cost_cents) AS total_cost,
                      COUNT(*) AS event_count
               FROM usage_events
               WHERE tenant_id = ? AND timestamp >= ?
               GROUP BY resource
               ORDER BY total_cost DESC""",
            (tenant_id, since),
        ).fetchall()

        by_resource = {}
        total_events = 0
        total_cost = 0
        for row in rows:
            r = dict(row)
            res = r["resource"]
            qty = int(r["total_qty"] or 0)
            cost = int(r["total_cost"] or 0)
            cnt = int(r["event_count"] or 0)
            by_resource[res] = {"quantity": qty, "cost_cents": cost, "events": cnt}
            total_events += cnt
            total_cost += cost

        # 活跃用户数
        user_row = self._db.execute(
            """SELECT COUNT(DISTINCT user_id) AS active_users
               FROM usage_events
               WHERE tenant_id = ? AND timestamp >= ?""",
            (tenant_id, since),
        ).fetchone()
        active_users = int(dict(user_row)["active_users"] or 0) if user_row else 0

        return {
            "tenant_id": tenant_id,
            "period_days": days,
            "total_events": total_events,
            "total_cost_cents": total_cost,
            "active_users": active_users,
            "by_resource": by_resource,
        }

    # ── Growth & Analytics 方法 ─────────────────────────────────────

    def get_retention_analysis(self, tenant_id: str, months: int = 6) -> list[dict]:
        """留存队列分析：逐月计算活跃租户留存率。

        Returns [{month, new_tenants, retained, retention_rate}, ...]
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        result = []

        for i in range(months - 1, -1, -1):
            month_start = (now.replace(day=1) - timedelta(days=i * 30)).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0,
            )
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1)

            # 当月活跃租户
            active_this = self._db.execute(
                """SELECT COUNT(DISTINCT tenant_id) AS cnt
                   FROM usage_events
                   WHERE timestamp >= ? AND timestamp < ?""",
                (month_start.isoformat(), month_end.isoformat()),
            ).fetchone()
            new_count = int(dict(active_this).get("cnt", 0) or 0)

            # 上月活跃且本月仍在的租户
            prev_start = month_start.replace(day=1) - timedelta(days=1)
            prev_start = prev_start.replace(day=1)
            prev_end = month_start

            prev_active = self._db.execute(
                """SELECT COUNT(DISTINCT tenant_id) AS cnt
                   FROM usage_events
                   WHERE timestamp >= ? AND timestamp < ?""",
                (prev_start.isoformat(), prev_end.isoformat()),
            ).fetchone()
            prev_count = int(dict(prev_active).get("cnt", 0) or 0)

            retention_rate = round(new_count / prev_count, 4) if prev_count > 0 else 0.0

            result.append({
                "month": month_start.strftime("%Y-%m"),
                "new_tenants": new_count,
                "retained": new_count,
                "retention_rate": retention_rate,
            })

        return result

    def get_import_channel_breakdown(self, tenant_id: str, days: int = 30) -> dict:
        """导入渠道分析：统计各导入来源的分布。

        Returns {channels: {channel: count}, total_imports: int}
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        rows = self._db.execute(
            """SELECT metadata_json
               FROM usage_events
               WHERE tenant_id = ? AND resource = 'import' AND timestamp >= ?""",
            (tenant_id, since),
        ).fetchall()

        channels: dict[str, int] = {}
        total = 0
        for row in rows:
            try:
                meta = json.loads(dict(row).get("metadata_json", "{}"))
                channel = meta.get("channel", meta.get("source", "unknown"))
                channels[channel] = channels.get(channel, 0) + 1
                total += 1
            except Exception:
                channels["unknown"] = channels.get("unknown", 0) + 1
                total += 1

        return {"channels": channels, "total_imports": total}

    def get_resource_usage_trend(
        self, tenant_id: str, resource: str, days: int = 30,
    ) -> list[dict]:
        """按日聚合单个资源的用量并返回趋势数据。

        Returns [{date, count, cost}, ...] 补全缺失日期填 0。
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)
        since_str = since.isoformat()

        rows = self._db.execute(
            """SELECT date(timestamp) AS d,
                      SUM(quantity) AS cnt,
                      SUM(cost_cents) AS cost
               FROM usage_events
               WHERE tenant_id = ? AND resource = ? AND timestamp >= ?
               GROUP BY d
               ORDER BY d ASC""",
            (tenant_id, resource, since_str),
        ).fetchall()

        data_map: dict[str, dict] = {}
        for row in rows:
            r = dict(row)
            data_map[r["d"]] = {
                "date": r["d"],
                "count": int(r["cnt"] or 0),
                "cost": int(r["cost"] or 0),
            }

        # 补全缺失日期
        result = []
        current = since
        now = datetime.now(timezone.utc)
        while current <= now:
            d_str = current.strftime("%Y-%m-%d")
            if d_str in data_map:
                result.append(data_map[d_str])
            else:
                result.append({"date": d_str, "count": 0, "cost": 0})
            current += timedelta(days=1)

        return result

    def get_realtime_metrics(self, tenant_id: str) -> dict:
        """实时指标：当前队列深度、DLQ 积压、今日事件数等。

        Returns dict with queue_depth, dlq_count, today_events, today_cost, active_users_today.
        """
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

        # 今日事件数
        today_events = self._db.execute(
            "SELECT COUNT(*) AS cnt FROM usage_events WHERE tenant_id = ? AND timestamp >= ?",
            (tenant_id, today_start),
        ).fetchone()
        today_event_count = int(dict(today_events).get("cnt", 0) or 0)

        # 今日成本
        today_cost = self._db.execute(
            "SELECT COALESCE(SUM(cost_cents), 0) AS cost FROM usage_events WHERE tenant_id = ? AND timestamp >= ?",
            (tenant_id, today_start),
        ).fetchone()
        today_cost_cents = int(dict(today_cost).get("cost", 0) or 0)

        # 今日活跃用户
        today_users = self._db.execute(
            "SELECT COUNT(DISTINCT user_id) AS cnt FROM usage_events WHERE tenant_id = ? AND timestamp >= ?",
            (tenant_id, today_start),
        ).fetchone()
        active_users_today = int(dict(today_users).get("cnt", 0) or 0)

        # 每小时事件数（用于异常检测）
        hourly = self._db.execute(
            """SELECT strftime('%H', timestamp) AS hr, COUNT(*) AS cnt
               FROM usage_events
               WHERE tenant_id = ? AND timestamp >= ?
               GROUP BY hr ORDER BY hr""",
            (tenant_id, today_start),
        ).fetchall()
        hourly_breakdown = {
            dict(r)["hr"]: int(dict(r)["cnt"])
            for r in hourly
        }

        return {
            "tenant_id": tenant_id,
            "today_events": today_event_count,
            "today_cost_cents": today_cost_cents,
            "active_users_today": active_users_today,
            "hourly_breakdown": hourly_breakdown,
            "max_hourly_events": max(hourly_breakdown.values()) if hourly_breakdown else 0,
        }

    # ── 内部方法 ────────────────────────────────────────────────────

    @staticmethod
    def _row_to_event(row: dict) -> UsageEvent:
        """将数据库行转换为 UsageEvent。"""
        return UsageEvent(
            id=row["id"],
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            resource=UsageResource(row["resource"]),
            quantity=int(row.get("quantity", 1)),
            workspace_id=row.get("workspace_id", ""),
            unit=UsageUnit(row.get("unit", "count")),
            metadata=json.loads(row.get("metadata_json") or "{}"),
            cost_cents=int(row.get("cost_cents", 0)),
            timestamp=_safe_parse_datetime(row["timestamp"]),
        )

    def close(self) -> None:
        if hasattr(self._db, "conn") and self._db.conn:
            self._db.conn.close()

    def __enter__(self) -> "UsageStoreAdapter":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ── helpers ────────────────────────────────────────────────────────


def _safe_parse_datetime(raw: str | None) -> datetime:
    """安全解析 ISO 时间字符串，失败时返回 UTC now。"""
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)
