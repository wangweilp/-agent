"""AnalyticsRepository — Dashboard V2 指标统计仓库（Phase 25 升级版）。

查询优先级：
1. analytics_* tables（analytics_user_activity_daily / analytics_agent_runs /
   analytics_memory_events / analytics_token_usage_daily）
2. fallback usage_events / notes / subscriptions（向后兼容）

如果 analytics 表为空或不存在，自动降级旧逻辑，不破坏 Dashboard V2 API。

新增：
- D30 留存
- 真实 P50/P95/P99 计算（Python statistics，非估算）
- analytics_agent_runs / analytics_memory_events / analytics_token_usage_daily 查询
"""
import json
import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class AnalyticsRepository:
    """Dashboard V2 指标统计仓库。

    接受一个 sqlite_utils.Database 对象（与 UsageStoreAdapter / SQLiteStoreAdapter /
    AnalyticsStore 共享同一 DB 文件）。
    """

    def __init__(self, db) -> None:
        self._db = db

    # ── 私有辅助 ──────────────────────────────────────────

    def _execute(self, sql: str, params: tuple = ()) -> list[dict]:
        """执行查询，返回 list[dict]。异常时返回空列表。"""
        try:
            cursor = self._db.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        except Exception:
            logger.warning("analytics_query_failed", exc_info=True, extra={"sql": sql[:120]})
            return []

    def _execute_one(self, sql: str, params: tuple = ()) -> dict:
        """执行查询，返回单行 dict。异常时返回空 dict。"""
        try:
            cursor = self._db.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else {}
        except Exception:
            logger.warning("analytics_query_one_failed", exc_info=True, extra={"sql": sql[:120]})
            return {}

    def _table_exists(self, table_name: str) -> bool:
        """检查表是否存在。"""
        try:
            row = self._execute_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            return bool(row)
        except Exception:
            return False

    def _table_has_data(self, table_name: str) -> bool:
        """检查表是否有数据。"""
        if not self._table_exists(table_name):
            return False
        row = self._execute_one(f"SELECT COUNT(*) AS cnt FROM {table_name}")
        return int(row.get("cnt", 0) or 0) > 0

    def _tenant_filter(self, tenant_id: str) -> tuple[str, tuple]:
        """生成 tenant_id 过滤子句。空或 default 时不过滤（平台全局视图）。"""
        if tenant_id and tenant_id != "default":
            return " AND tenant_id = ?", (tenant_id,)
        return "", ()

    # ── DAU / WAU / MAU ───────────────────────────────────

    def get_dau(self, tenant_id: str = "") -> int:
        """DAU — 今日活跃用户数。优先 analytics_user_activity_daily。"""
        if self._table_has_data("analytics_user_activity_daily"):
            clause, params = self._tenant_filter(tenant_id)
            row = self._execute_one(
                f"""SELECT COUNT(DISTINCT user_id) AS cnt
                    FROM analytics_user_activity_daily
                    WHERE event_date = date('now'){clause}""",
                params,
            )
            return int(row.get("cnt", 0) or 0)
        # fallback: usage_events
        clause, params = self._tenant_filter(tenant_id)
        row = self._execute_one(
            f"""SELECT COUNT(DISTINCT user_id) AS cnt
                FROM usage_events
                WHERE date(timestamp) = date('now'){clause}""",
            params,
        )
        return int(row.get("cnt", 0) or 0)

    def get_wau(self, tenant_id: str = "") -> int:
        """WAU — 近 7 天活跃用户数。"""
        if self._table_has_data("analytics_user_activity_daily"):
            clause, params = self._tenant_filter(tenant_id)
            row = self._execute_one(
                f"""SELECT COUNT(DISTINCT user_id) AS cnt
                    FROM analytics_user_activity_daily
                    WHERE event_date >= date('now', '-6 days'){clause}""",
                params,
            )
            return int(row.get("cnt", 0) or 0)
        clause, params = self._tenant_filter(tenant_id)
        row = self._execute_one(
            f"""SELECT COUNT(DISTINCT user_id) AS cnt
                FROM usage_events
                WHERE timestamp >= datetime('now', '-6 days'){clause}""",
            params,
        )
        return int(row.get("cnt", 0) or 0)

    def get_mau(self, tenant_id: str = "") -> int:
        """MAU — 近 30 天活跃用户数。"""
        if self._table_has_data("analytics_user_activity_daily"):
            clause, params = self._tenant_filter(tenant_id)
            row = self._execute_one(
                f"""SELECT COUNT(DISTINCT user_id) AS cnt
                    FROM analytics_user_activity_daily
                    WHERE event_date >= date('now', '-29 days'){clause}""",
                params,
            )
            return int(row.get("cnt", 0) or 0)
        clause, params = self._tenant_filter(tenant_id)
        row = self._execute_one(
            f"""SELECT COUNT(DISTINCT user_id) AS cnt
                FROM usage_events
                WHERE timestamp >= datetime('now', '-29 days'){clause}""",
            params,
        )
        return int(row.get("cnt", 0) or 0)

    def get_dau_series(self, tenant_id: str = "", days: int = 30) -> list[dict]:
        """DAU 时间序列。优先 analytics_user_activity_daily。"""
        if self._table_has_data("analytics_user_activity_daily"):
            clause, params = self._tenant_filter(tenant_id)
            rows = self._execute(
                f"""SELECT event_date AS d, COUNT(DISTINCT user_id) AS cnt
                    FROM analytics_user_activity_daily
                    WHERE event_date >= date('now', '-{int(days)} days'){clause}
                    GROUP BY d ORDER BY d ASC""",
                params,
            )
            return [{"date": r.get("d", ""), "value": int(r.get("cnt", 0) or 0)} for r in rows]
        clause, params = self._tenant_filter(tenant_id)
        rows = self._execute(
            f"""SELECT date(timestamp) AS d, COUNT(DISTINCT user_id) AS cnt
                FROM usage_events
                WHERE timestamp >= datetime('now', '-{int(days)} days'){clause}
                GROUP BY d ORDER BY d ASC""",
            params,
        )
        return [{"date": r.get("d", ""), "value": int(r.get("cnt", 0) or 0)} for r in rows]

    # ── 留存率 ────────────────────────────────────────────

    def get_retention_d1(self, tenant_id: str = "") -> float:
        """D1 留存率 — 昨日活跃用户中今日仍活跃的比例（百分比）。"""
        if self._table_has_data("analytics_user_activity_daily"):
            clause, params = self._tenant_filter(tenant_id)
            row = self._execute_one(
                f"""SELECT
                      (SELECT COUNT(DISTINCT user_id) FROM analytics_user_activity_daily
                       WHERE event_date = date('now', '-1 day'){clause}) AS base,
                      (SELECT COUNT(DISTINCT a.user_id) FROM analytics_user_activity_daily a
                       WHERE a.event_date = date('now', '-1 day'){clause}
                         AND a.user_id IN (
                           SELECT DISTINCT user_id FROM analytics_user_activity_daily
                           WHERE event_date = date('now'){clause}
                         )) AS retained""",
                params * 2,
            )
            base = int(row.get("base", 0) or 0)
            retained = int(row.get("retained", 0) or 0)
            if base == 0:
                return 0.0
            return round(retained / base * 100, 2)
        # fallback: usage_events
        clause, params = self._tenant_filter(tenant_id)
        row = self._execute_one(
            f"""SELECT
                  (SELECT COUNT(DISTINCT user_id) FROM usage_events
                   WHERE date(timestamp) = date('now', '-1 day'){clause}) AS base,
                  (SELECT COUNT(DISTINCT a.user_id) FROM usage_events a
                   WHERE date(a.timestamp) = date('now', '-1 day'){clause}
                     AND a.user_id IN (
                       SELECT DISTINCT user_id FROM usage_events
                       WHERE date(timestamp) = date('now'){clause}
                     )) AS retained""",
            params * 2,
        )
        base = int(row.get("base", 0) or 0)
        retained = int(row.get("retained", 0) or 0)
        if base == 0:
            return 0.0
        return round(retained / base * 100, 2)

    def get_retention_d7(self, tenant_id: str = "") -> float:
        """D7 留存率 — 7 天前活跃用户中今日仍活跃的比例（百分比）。"""
        if self._table_has_data("analytics_user_activity_daily"):
            clause, params = self._tenant_filter(tenant_id)
            row = self._execute_one(
                f"""SELECT
                      (SELECT COUNT(DISTINCT user_id) FROM analytics_user_activity_daily
                       WHERE event_date = date('now', '-7 days'){clause}) AS base,
                      (SELECT COUNT(DISTINCT a.user_id) FROM analytics_user_activity_daily a
                       WHERE a.event_date = date('now', '-7 days'){clause}
                         AND a.user_id IN (
                           SELECT DISTINCT user_id FROM analytics_user_activity_daily
                           WHERE event_date = date('now'){clause}
                         )) AS retained""",
                params * 2,
            )
            base = int(row.get("base", 0) or 0)
            retained = int(row.get("retained", 0) or 0)
            if base == 0:
                return 0.0
            return round(retained / base * 100, 2)
        clause, params = self._tenant_filter(tenant_id)
        row = self._execute_one(
            f"""SELECT
                  (SELECT COUNT(DISTINCT user_id) FROM usage_events
                   WHERE date(timestamp) = date('now', '-7 days'){clause}) AS base,
                  (SELECT COUNT(DISTINCT a.user_id) FROM usage_events a
                   WHERE date(a.timestamp) = date('now', '-7 days'){clause}
                     AND a.user_id IN (
                       SELECT DISTINCT user_id FROM usage_events
                       WHERE date(timestamp) = date('now'){clause}
                     )) AS retained""",
            params * 2,
        )
        base = int(row.get("base", 0) or 0)
        retained = int(row.get("retained", 0) or 0)
        if base == 0:
            return 0.0
        return round(retained / base * 100, 2)

    def get_retention_d30(self, tenant_id: str = "") -> float:
        """D30 留存率 — 30 天前活跃用户中今日仍活跃的比例（百分比）。"""
        if self._table_has_data("analytics_user_activity_daily"):
            clause, params = self._tenant_filter(tenant_id)
            row = self._execute_one(
                f"""SELECT
                      (SELECT COUNT(DISTINCT user_id) FROM analytics_user_activity_daily
                       WHERE event_date = date('now', '-30 days'){clause}) AS base,
                      (SELECT COUNT(DISTINCT a.user_id) FROM analytics_user_activity_daily a
                       WHERE a.event_date = date('now', '-30 days'){clause}
                         AND a.user_id IN (
                           SELECT DISTINCT user_id FROM analytics_user_activity_daily
                           WHERE event_date = date('now'){clause}
                         )) AS retained""",
                params * 2,
            )
            base = int(row.get("base", 0) or 0)
            retained = int(row.get("retained", 0) or 0)
            if base == 0:
                return 0.0
            return round(retained / base * 100, 2)
        return 0.0  # usage_events fallback 不支持 D30（数据量太大）

    def get_retention_cohort(self, tenant_id: str = "", weeks: int = 8) -> list[dict]:
        """留存队列矩阵 — 按注册周分组的 D1/D7 留存。"""
        table = "analytics_user_activity_daily" if self._table_has_data("analytics_user_activity_daily") else "usage_events"
        date_col = "event_date" if table == "analytics_user_activity_daily" else "date(timestamp)"
        clause, params = self._tenant_filter(tenant_id)
        rows = self._execute(
            f"""SELECT
                  {date_col} AS first_seen,
                  user_id
                FROM {table}
                WHERE 1=1{clause}
                GROUP BY user_id""",
            params,
        )
        if not rows:
            return []

        from collections import defaultdict
        cohorts: dict[str, list[str]] = defaultdict(list)
        for r in rows:
            first = r.get("first_seen", "")
            if first:
                cohorts[first].append(r.get("user_id", ""))

        result = []
        for cohort_date, users in sorted(cohorts.items(), reverse=True)[:weeks]:
            if not users:
                continue
            user_placeholders = ",".join("?" * len(users))
            d1_row = self._execute_one(
                f"""SELECT COUNT(DISTINCT user_id) AS cnt FROM {table}
                    WHERE {date_col} = date(?, '+1 day')
                      AND user_id IN ({user_placeholders})""",
                (cohort_date, *users),
            )
            d7_row = self._execute_one(
                f"""SELECT COUNT(DISTINCT user_id) AS cnt FROM {table}
                    WHERE {date_col} = date(?, '+7 days')
                      AND user_id IN ({user_placeholders})""",
                (cohort_date, *users),
            )
            size = len(users)
            d1 = round(int(d1_row.get("cnt", 0) or 0) / size * 100, 2) if size else 0.0
            d7 = round(int(d7_row.get("cnt", 0) or 0) / size * 100, 2) if size else 0.0
            result.append({
                "cohort_date": cohort_date,
                "cohort_size": size,
                "d1": d1,
                "d7": d7,
            })
        return result

    # ── Agent 指标 ────────────────────────────────────────

    def get_agent_success_rate(self, tenant_id: str = "", days: int = 7) -> float:
        """Agent 成功率。优先 analytics_agent_runs。"""
        if self._table_has_data("analytics_agent_runs"):
            clause, params = self._tenant_filter(tenant_id)
            row = self._execute_one(
                f"""SELECT
                      COUNT(*) AS total,
                      SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success
                    FROM analytics_agent_runs
                    WHERE created_at >= datetime('now', '-{int(days)} days'){clause}""",
                params,
            )
            total = int(row.get("total", 0) or 0)
            success = int(row.get("success", 0) or 0)
            if total == 0:
                return 0.0
            return round(success / total * 100, 2)
        # fallback: usage_events + metadata_json
        clause, params = self._tenant_filter(tenant_id)
        row = self._execute_one(
            f"""SELECT
                  COUNT(*) AS total,
                  SUM(CASE WHEN json_extract(metadata_json, '$.status') = 'failed' THEN 1 ELSE 0 END) AS failed
                FROM usage_events
                WHERE resource = 'agent_run'
                  AND timestamp >= datetime('now', '-{int(days)} days'){clause}""",
            params,
        )
        total = int(row.get("total", 0) or 0)
        failed = int(row.get("failed", 0) or 0)
        if total == 0:
            return 0.0
        return round((total - failed) / total * 100, 2)

    def get_latency_percentiles(self, tenant_id: str = "", days: int = 7) -> dict:
        """真实 P50/P95/P99 延迟（毫秒）。优先 analytics_agent_runs。

        使用 Python statistics 计算真实分位数，非估算。
        Returns: {"p50_ms": float, "p95_ms": float, "p99_ms": float}
        """
        if self._table_has_data("analytics_agent_runs"):
            clause, params = self._tenant_filter(tenant_id)
            rows = self._execute(
                f"""SELECT duration_ms FROM analytics_agent_runs
                    WHERE created_at >= datetime('now', '-{int(days)} days'){clause}
                      AND duration_ms > 0""",
                params,
            )
            durations = [float(r["duration_ms"]) for r in rows if r.get("duration_ms") is not None]
            if not durations:
                return {"p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0}
            return self._compute_percentiles(durations)
        # fallback: usage_events + metadata_json
        clause, params = self._tenant_filter(tenant_id)
        rows = self._execute(
            f"""SELECT json_extract(metadata_json, '$.duration_ms') AS dur
                FROM usage_events
                WHERE resource = 'agent_run'
                  AND timestamp >= datetime('now', '-{int(days)} days'){clause}
                  AND json_extract(metadata_json, '$.duration_ms') IS NOT NULL""",
            params,
        )
        durations = [float(r["dur"]) for r in rows if r.get("dur") is not None]
        if not durations:
            return {"p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0}
        return self._compute_percentiles(durations)

    def _compute_percentiles(self, data: list[float]) -> dict:
        """计算真实 P50/P95/P99（线性插值法，与 numpy.percentile 一致）。"""
        if not data:
            return {"p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0}
        sorted_data = sorted(data)
        n = len(sorted_data)

        def percentile(p: float) -> float:
            """线性插值法计算分位数。"""
            if n == 1:
                return sorted_data[0]
            rank = p / 100 * (n - 1)
            lower = int(rank)
            upper = lower + 1
            if upper >= n:
                return sorted_data[-1]
            weight = rank - lower
            return sorted_data[lower] * (1 - weight) + sorted_data[upper] * weight

        return {
            "p50_ms": round(percentile(50), 2),
            "p95_ms": round(percentile(95), 2),
            "p99_ms": round(percentile(99), 2),
        }

    def get_p95_latency_ms(self, tenant_id: str = "", days: int = 7) -> float:
        """P95 延迟（向后兼容）。"""
        return self.get_latency_percentiles(tenant_id, days)["p95_ms"]

    def get_agent_call_volume_series(self, tenant_id: str = "", days: int = 7) -> list[dict]:
        """Agent 调用量时间序列。优先 analytics_agent_runs。"""
        if self._table_has_data("analytics_agent_runs"):
            clause, params = self._tenant_filter(tenant_id)
            rows = self._execute(
                f"""SELECT date(created_at) AS d, COUNT(*) AS cnt
                    FROM analytics_agent_runs
                    WHERE created_at >= datetime('now', '-{int(days)} days'){clause}
                    GROUP BY d ORDER BY d ASC""",
                params,
            )
            return [{"date": r.get("d", ""), "value": int(r.get("cnt", 0) or 0)} for r in rows]
        clause, params = self._tenant_filter(tenant_id)
        rows = self._execute(
            f"""SELECT date(timestamp) AS d, COUNT(*) AS cnt
                FROM usage_events
                WHERE resource = 'agent_run'
                  AND timestamp >= datetime('now', '-{int(days)} days'){clause}
                GROUP BY d ORDER BY d ASC""",
            params,
        )
        return [{"date": r.get("d", ""), "value": int(r.get("cnt", 0) or 0)} for r in rows]

    def get_token_usage_series(self, tenant_id: str = "", days: int = 7) -> list[dict]:
        """Token 消耗时间序列。优先 analytics_token_usage_daily。"""
        if self._table_has_data("analytics_token_usage_daily"):
            clause, params = self._tenant_filter(tenant_id)
            rows = self._execute(
                f"""SELECT event_date AS d,
                           (prompt_tokens + completion_tokens) AS cnt
                    FROM analytics_token_usage_daily
                    WHERE event_date >= date('now', '-{int(days)} days'){clause}
                    GROUP BY d ORDER BY d ASC""",
                params,
            )
            return [{"date": r.get("d", ""), "value": int(r.get("cnt", 0) or 0)} for r in rows]
        clause, params = self._tenant_filter(tenant_id)
        rows = self._execute(
            f"""SELECT date(timestamp) AS d, SUM(quantity) AS cnt
                FROM usage_events
                WHERE resource IN ('llm_call', 'embedding')
                  AND timestamp >= datetime('now', '-{int(days)} days'){clause}
                GROUP BY d ORDER BY d ASC""",
            params,
        )
        return [{"date": r.get("d", ""), "value": int(r.get("cnt", 0) or 0)} for r in rows]

    # ── Token 成本 ────────────────────────────────────────

    def get_token_cost_cents(self, tenant_id: str = "", days: int = 1) -> int:
        """Token 成本（分）。优先 analytics_token_usage_daily。

        analytics 表存储 cost_usd，按 7.2 汇率转换为分（1 USD = 720 cents）。
        """
        if self._table_has_data("analytics_token_usage_daily"):
            clause, params = self._tenant_filter(tenant_id)
            row = self._execute_one(
                f"""SELECT COALESCE(SUM(cost_usd), 0) AS usd
                    FROM analytics_token_usage_daily
                    WHERE event_date >= date('now', '-{int(days)} days'){clause}""",
                params,
            )
            usd = float(row.get("usd", 0) or 0)
            return int(usd * 720)  # USD → CNY cents（汇率 7.2）
        clause, params = self._tenant_filter(tenant_id)
        row = self._execute_one(
            f"""SELECT COALESCE(SUM(cost_cents), 0) AS cnt
                FROM usage_events
                WHERE resource IN ('llm_call', 'embedding')
                  AND timestamp >= datetime('now', '-{int(days)} days'){clause}""",
            params,
        )
        return int(row.get("cnt", 0) or 0)

    def get_token_cost_usd(self, tenant_id: str = "", days: int = 1) -> float:
        """Token 成本（美元）。优先 analytics_token_usage_daily。"""
        if self._table_has_data("analytics_token_usage_daily"):
            clause, params = self._tenant_filter(tenant_id)
            row = self._execute_one(
                f"""SELECT COALESCE(SUM(cost_usd), 0) AS usd
                    FROM analytics_token_usage_daily
                    WHERE event_date >= date('now', '-{int(days)} days'){clause}""",
                params,
            )
            return round(float(row.get("usd", 0) or 0), 4)
        return round(self.get_token_cost_cents(tenant_id, days) / 720, 4)

    # ── Memory 指标 ───────────────────────────────────────

    def get_memory_hit_rate(self, tenant_id: str = "") -> float:
        """Memory 命中率。优先 analytics_memory_events。"""
        if self._table_has_data("analytics_memory_events"):
            clause, params = self._tenant_filter(tenant_id)
            row = self._execute_one(
                f"""SELECT
                      SUM(CASE WHEN event_type='HIT' THEN 1 ELSE 0 END) AS hits,
                      COUNT(*) AS total
                    FROM analytics_memory_events
                    WHERE event_type IN ('HIT', 'INSERT'){clause}""",
                params,
            )
            hits = int(row.get("hits", 0) or 0)
            total = int(row.get("total", 0) or 0)
            if total == 0:
                return 0.0
            return round(hits / total * 100, 2)
        # fallback: notes 表 access_count
        ws_clause = ""
        params: tuple = ()
        if tenant_id and tenant_id != "default":
            ws_clause = " WHERE workspace_id = ?"
            params = (tenant_id,)
        row = self._execute_one(
            f"""SELECT
                  COUNT(*) AS total,
                  SUM(CASE WHEN access_count > 0 THEN 1 ELSE 0 END) AS hit
                FROM notes
                WHERE status != 'deleted'{ws_clause}""",
            params,
        )
        total = int(row.get("total", 0) or 0)
        hit = int(row.get("hit", 0) or 0)
        if total == 0:
            return 0.0
        return round(hit / total * 100, 2)

    def get_total_memories(self, tenant_id: str = "") -> int:
        """总记忆数。"""
        ws_clause = ""
        params: tuple = ()
        if tenant_id and tenant_id != "default":
            ws_clause = " AND workspace_id = ?"
            params = (tenant_id,)
        row = self._execute_one(
            f"""SELECT COUNT(*) AS cnt FROM notes WHERE status != 'deleted'{ws_clause}""",
            params,
        )
        return int(row.get("cnt", 0) or 0)

    def get_active_memories(self, tenant_id: str = "") -> int:
        """活跃记忆数。"""
        ws_clause = ""
        params: tuple = ()
        if tenant_id and tenant_id != "default":
            ws_clause = " AND workspace_id = ?"
            params = (tenant_id,)
        row = self._execute_one(
            f"""SELECT COUNT(*) AS cnt FROM notes WHERE status = 'active'{ws_clause}""",
            params,
        )
        return int(row.get("cnt", 0) or 0)

    def get_net_memory_growth(self, tenant_id: str = "", days: int = 1) -> int:
        """净增记忆数。优先 analytics_memory_events。"""
        if self._table_has_data("analytics_memory_events"):
            clause, params = self._tenant_filter(tenant_id)
            row = self._execute_one(
                f"""SELECT
                      SUM(CASE WHEN event_type='INSERT' THEN 1 ELSE 0 END) AS inserted,
                      SUM(CASE WHEN event_type='DELETE' THEN 1 ELSE 0 END) AS deleted
                    FROM analytics_memory_events
                    WHERE created_at >= datetime('now', '-{int(days)} days'){clause}""",
                params,
            )
            inserted = int(row.get("inserted", 0) or 0)
            deleted = int(row.get("deleted", 0) or 0)
            return inserted - deleted
        # fallback: notes 表
        ws_clause = ""
        params: tuple = ()
        if tenant_id and tenant_id != "default":
            ws_clause = " AND workspace_id = ?"
            params = (tenant_id,)
        row = self._execute_one(
            f"""SELECT
                  SUM(CASE WHEN timestamp >= datetime('now', '-{int(days)} days') THEN 1 ELSE 0 END) AS new,
                  SUM(CASE WHEN status IN ('archived', 'merged', 'deleted')
                           AND COALESCE(archived_at, timestamp) >= datetime('now', '-{int(days)} days')
                           THEN 1 ELSE 0 END) AS removed
                FROM notes
                WHERE 1=1{ws_clause}""",
            params,
        )
        new_count = int(row.get("new", 0) or 0)
        removed = int(row.get("removed", 0) or 0)
        return new_count - removed

    def get_memory_type_distribution(self, tenant_id: str = "") -> list[dict]:
        """记忆类型分布。优先 analytics_memory_events。"""
        if self._table_has_data("analytics_memory_events"):
            clause, params = self._tenant_filter(tenant_id)
            rows = self._execute(
                f"""SELECT memory_type, COUNT(*) AS cnt
                    FROM analytics_memory_events
                    WHERE event_type = 'INSERT'{clause}
                    GROUP BY memory_type
                    ORDER BY cnt DESC""",
                params,
            )
            return [{"memory_type": r.get("memory_type", "unknown"), "count": int(r.get("cnt", 0) or 0)} for r in rows]
        ws_clause = ""
        params: tuple = ()
        if tenant_id and tenant_id != "default":
            ws_clause = " AND workspace_id = ?"
            params = (tenant_id,)
        rows = self._execute(
            f"""SELECT memory_type, COUNT(*) AS cnt
                FROM notes
                WHERE status != 'deleted'{ws_clause}
                GROUP BY memory_type
                ORDER BY cnt DESC""",
            params,
        )
        return [{"memory_type": r.get("memory_type", "unknown"), "count": int(r.get("cnt", 0) or 0)} for r in rows]

    def get_memory_growth_series(self, tenant_id: str = "", days: int = 30) -> list[dict]:
        """记忆增长时间序列。优先 analytics_memory_events。"""
        if self._table_has_data("analytics_memory_events"):
            clause, params = self._tenant_filter(tenant_id)
            rows = self._execute(
                f"""SELECT date(created_at) AS d,
                           SUM(CASE WHEN event_type='INSERT' THEN 1 ELSE 0 END) AS cnt
                    FROM analytics_memory_events
                    WHERE created_at >= datetime('now', '-{int(days)} days'){clause}
                    GROUP BY d ORDER BY d ASC""",
                params,
            )
            return [{"date": r.get("d", ""), "value": int(r.get("cnt", 0) or 0)} for r in rows]
        ws_clause = ""
        params: tuple = ()
        if tenant_id and tenant_id != "default":
            ws_clause = " AND workspace_id = ?"
            params = (tenant_id,)
        rows = self._execute(
            f"""SELECT date(timestamp) AS d, COUNT(*) AS cnt
                FROM notes
                WHERE timestamp >= datetime('now', '-{int(days)} days'){ws_clause}
                GROUP BY d ORDER BY d ASC""",
            params,
        )
        return [{"date": r.get("d", ""), "value": int(r.get("cnt", 0) or 0)} for r in rows]

    # ── 商业指标 ──────────────────────────────────────────

    def get_mrr_cents(self) -> int:
        """MRR — 活跃订阅的月度经常性收入（分）。"""
        try:
            from src.core.subscription import PLAN_PRICES, BillingCycle, PlanTier
        except ImportError:
            return 0
        rows = self._execute("SELECT plan_tier, status, billing_cycle FROM subscriptions")
        if not rows:
            return 0
        mrr = 0
        for r in rows:
            status = r.get("status", "")
            if status not in ("active", "trial"):
                continue
            try:
                tier = PlanTier(r.get("plan_tier", "free"))
                cycle = BillingCycle(r.get("billing_cycle", "monthly"))
                monthly = PLAN_PRICES.get(tier, {}).get(BillingCycle.MONTHLY, 0)
                if cycle == BillingCycle.YEARLY:
                    yearly = PLAN_PRICES.get(tier, {}).get(BillingCycle.YEARLY, 0)
                    monthly = yearly // 12
                mrr += monthly
            except (ValueError, KeyError):
                continue
        return mrr

    def get_arr_cents(self) -> int:
        """ARR — MRR × 12。"""
        return self.get_mrr_cents() * 12

    def get_paying_tenants(self) -> int:
        """付费租户数。"""
        row = self._execute_one(
            "SELECT COUNT(DISTINCT tenant_id) AS cnt FROM subscriptions WHERE status = 'active'"
        )
        return int(row.get("cnt", 0) or 0)

    def get_arpu_cents(self) -> int:
        """ARPU — MRR / 付费租户数。"""
        paying = self.get_paying_tenants()
        if paying == 0:
            return 0
        return self.get_mrr_cents() // paying

    def get_gross_margin_pct(self) -> float:
        """毛利率 — (MRR - AI成本) / MRR * 100。"""
        mrr = self.get_mrr_cents()
        if mrr == 0:
            return 0.0
        ai_cost = self.get_token_cost_cents(days=30)
        return round((mrr - ai_cost) / mrr * 100, 2)

    # ── 转化漏斗 ──────────────────────────────────────────

    def get_conversion_funnel(self, tenant_id: str = "", days: int = 30) -> list[dict]:
        """转化漏斗 — 注册 → 激活 → 试用 → 付费。"""
        clause, params = self._tenant_filter(tenant_id)
        interval = f"-{int(days)} days"
        reg_row = self._execute_one(
            f"""SELECT COUNT(DISTINCT user_id) AS cnt FROM usage_events
                WHERE timestamp >= datetime('now', '{interval}'){clause}""",
            params,
        )
        act_row = self._execute_one(
            f"""SELECT COUNT(DISTINCT user_id) AS cnt FROM usage_events
                WHERE resource = 'memory' AND timestamp >= datetime('now', '{interval}'){clause}""",
            params,
        )
        trial_row = self._execute_one(
            "SELECT COUNT(DISTINCT tenant_id) AS cnt FROM subscriptions WHERE status = 'trial'"
        )
        paid_row = self._execute_one(
            "SELECT COUNT(DISTINCT tenant_id) AS cnt FROM subscriptions WHERE status = 'active'"
        )
        return [
            {"stage": "registered", "count": int(reg_row.get("cnt", 0) or 0)},
            {"stage": "activated", "count": int(act_row.get("cnt", 0) or 0)},
            {"stage": "trial", "count": int(trial_row.get("cnt", 0) or 0)},
            {"stage": "paid", "count": int(paid_row.get("cnt", 0) or 0)},
        ]

    def get_activation_rate(self, tenant_id: str = "", days: int = 30) -> float:
        """激活率 — 有 memory 事件的用户 / 总注册用户 * 100。"""
        funnel = self.get_conversion_funnel(tenant_id, days)
        reg = funnel[0]["count"] if funnel else 0
        act = funnel[1]["count"] if len(funnel) > 1 else 0
        if reg == 0:
            return 0.0
        return round(act / reg * 100, 2)
