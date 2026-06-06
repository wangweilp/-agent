"""Report Store Adapter — SQLite 实现 ReportStore 协议。

管理 reports 表，支持 JSON/CSV 导出。
"""
import csv
import io
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from sqlite_utils import Database as SqliteDB

from src.adapters.config import Settings
from src.core.report import (
    Report,
    ReportData,
    ReportFormat,
    ReportStatus,
    ReportStore,
    ReportType,
)

logger = logging.getLogger(__name__)

_REPORT_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    report_type TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    format TEXT NOT NULL DEFAULT 'json',
    status TEXT NOT NULL DEFAULT 'generating',
    data_json TEXT,
    file_path TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rp_tenant ON reports(tenant_id);
CREATE INDEX IF NOT EXISTS idx_rp_type ON reports(tenant_id, report_type);
CREATE INDEX IF NOT EXISTS idx_rp_created ON reports(created_at);
"""


class ReportStoreAdapter:
    """ReportStore 的 SQLite 实现。"""

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
        # 报告导出目录
        self._export_dir = os.path.join(
            os.path.dirname(path) if path != ":memory:" else "data",
            "reports",
        )
        os.makedirs(self._export_dir, exist_ok=True)

    def _init_schema(self) -> None:
        for stmt in _REPORT_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)

    # ── ReportStore 协议 ──────────────────────────────────────────────

    def create_report(self, report: Report) -> str:
        data_json_str = None
        if report.data:
            data_json_str = json.dumps(report.data.as_dict(), ensure_ascii=False)

        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO reports (id, tenant_id, report_type, period_start,
                   period_end, format, status, data_json, file_path, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    report.id,
                    report.tenant_id,
                    report.report_type.value,
                    report.period_start,
                    report.period_end,
                    report.format.value,
                    report.status.value,
                    data_json_str,
                    report.file_path,
                    report.created_at.isoformat(),
                ),
            )
        logger.info("report:created", extra={
            "report_id": report.id, "type": report.report_type.value,
            "tenant_id": report.tenant_id,
        })
        return report.id

    def get_report(self, tenant_id: str, report_id: str) -> Report | None:
        row = self._db.execute(
            "SELECT * FROM reports WHERE id = ? AND tenant_id = ?",
            (report_id, tenant_id),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_report(dict(row))

    def list_reports(self, tenant_id: str, report_type: str | None = None,
                     limit: int = 20) -> list[Report]:
        sql = "SELECT * FROM reports WHERE tenant_id = ?"
        params: list[Any] = [tenant_id]
        if report_type:
            sql += " AND report_type = ?"
            params.append(report_type)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._db.execute(sql, tuple(params)).fetchall()
        return [self._row_to_report(dict(r)) for r in rows]

    def update_report(self, tenant_id: str, report_id: str,
                      updates: dict) -> Report | None:
        existing = self.get_report(tenant_id, report_id)
        if existing is None:
            return None

        allowed = {"status", "data_json", "file_path", "format"}
        filtered = {k: v for k, v in updates.items() if k in allowed}

        if not filtered:
            return existing

        set_clause = ", ".join(f"{k} = ?" for k in filtered)
        values = list(filtered.values()) + [report_id, tenant_id]

        with self._write_lock, self._db.conn:
            self._db.execute(
                f"UPDATE reports SET {set_clause} WHERE id = ? AND tenant_id = ?",
                tuple(values),
            )

        return self.get_report(tenant_id, report_id)

    def delete_report(self, tenant_id: str, report_id: str) -> bool:
        report = self.get_report(tenant_id, report_id)
        if report and report.file_path and os.path.exists(report.file_path):
            try:
                os.remove(report.file_path)
            except OSError:
                pass

        with self._write_lock, self._db.conn:
            cursor = self._db.execute(
                "DELETE FROM reports WHERE id = ? AND tenant_id = ?",
                (report_id, tenant_id),
            )
            return cursor.rowcount > 0

    def export_csv(self, report: Report) -> str:
        """将报告数据导出为 CSV 文件，返回文件路径。"""
        if report.data is None:
            raise ValueError("Report has no data to export")

        data = report.data
        filename = (
            f"{report.report_type.value}_{report.period_start}_{report.period_end}"
            f"_{report.tenant_id}.csv"
        )
        filepath = os.path.join(self._export_dir, filename)

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # 报告元信息
            writer.writerow(["Metric", "Value"])
            writer.writerow(["Report Type", data.report_type.value])
            writer.writerow(["Period", f"{data.period_start} to {data.period_end}"])
            writer.writerow([])

            # SaaS 指标
            writer.writerow(["=== SaaS Metrics ===", ""])
            writer.writerow(["MRR (cents)", data.mrr_cents])
            writer.writerow(["ARR (cents)", data.arr_cents])
            writer.writerow(["Total Tenants", data.total_tenants])
            writer.writerow(["Active Tenants", data.active_tenants])
            writer.writerow(["Paying Tenants", data.paying_tenants])
            writer.writerow(["Trial Tenants", data.trial_tenants])
            writer.writerow(["Conversion Rate", f"{data.conversion_rate:.2%}"])
            writer.writerow(["Churn Rate", f"{data.churn_rate:.2%}"])
            writer.writerow(["Retention Rate", f"{data.retention_rate:.2%}"])
            writer.writerow([])

            # 用量指标
            writer.writerow(["=== Usage Metrics ===", ""])
            writer.writerow(["Memories Created", data.total_memories_created])
            writer.writerow(["LLM Calls", data.total_llm_calls])
            writer.writerow(["Embedding Calls", data.total_embedding_calls])
            writer.writerow(["Searches", data.total_searches])
            writer.writerow(["Imports", data.total_imports])
            writer.writerow(["Syncs", data.total_syncs])
            writer.writerow(["Coach Sessions", data.total_coach_sessions])
            writer.writerow([])

            # 成本与收入
            writer.writerow(["=== Cost & Revenue ===", ""])
            writer.writerow(["Total Cost (cents)", data.total_cost_cents])
            writer.writerow(["Total Revenue (cents)", data.total_revenue_cents])
            writer.writerow(["Net Revenue (cents)", data.net_revenue_cents])
            writer.writerow(["Margin %", f"{data.margin_percent:.1f}%"])
            writer.writerow([])

            # 用户行为
            writer.writerow(["=== User Engagement ===", ""])
            writer.writerow(["Active Users", data.active_users])
            writer.writerow(["New Users", data.new_users])
            writer.writerow([])

            # 导入渠道
            if data.import_channels:
                writer.writerow(["=== Import Channels ===", ""])
                writer.writerow(["Channel", "Count"])
                for ch, cnt in data.import_channels.items():
                    writer.writerow([ch, cnt])
                writer.writerow([])

            # Top Entities
            if data.top_entities:
                writer.writerow(["=== Top Entities ===", ""])
                writer.writerow(["Name", "Type", "Mentions"])
                for ent in data.top_entities[:10]:
                    writer.writerow([
                        ent.get("name", ""),
                        ent.get("entity_type", ""),
                        ent.get("mention_count", 0),
                    ])
                writer.writerow([])

            # Daily Trend
            if data.daily_usage_trend:
                writer.writerow(["=== Daily Usage Trend ===", ""])
                if data.daily_usage_trend:
                    headers = ["Date"] + list(data.daily_usage_trend[0].keys())[1:]
                    writer.writerow(headers)
                    for day in data.daily_usage_trend:
                        writer.writerow([day.get(h, "") for h in headers])

        logger.info("report:csv_exported", extra={"filepath": filepath})
        return filepath

    def export_json(self, report: Report) -> str:
        """将报告数据导出为 JSON 文件，返回文件路径。"""
        if report.data is None:
            raise ValueError("Report has no data to export")

        filename = (
            f"{report.report_type.value}_{report.period_start}_{report.period_end}"
            f"_{report.tenant_id}.json"
        )
        filepath = os.path.join(self._export_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report.data.as_dict(), f, ensure_ascii=False, indent=2)

        logger.info("report:json_exported", extra={"filepath": filepath})
        return filepath

    # ── 内部方法 ────────────────────────────────────────────────────

    @staticmethod
    def _row_to_report(row: dict) -> Report:
        data = None
        data_json_str = row.get("data_json")
        if data_json_str:
            try:
                raw = json.loads(data_json_str)
                data = ReportData(
                    report_type=ReportType(raw.get("report_type", "weekly")),
                    period_start=raw.get("period_start", ""),
                    period_end=raw.get("period_end", ""),
                    mrr_cents=raw.get("mrr_cents", 0),
                    arr_cents=raw.get("arr_cents", 0),
                    total_tenants=raw.get("total_tenants", 0),
                    active_tenants=raw.get("active_tenants", 0),
                    paying_tenants=raw.get("paying_tenants", 0),
                    trial_tenants=raw.get("trial_tenants", 0),
                    conversion_rate=raw.get("conversion_rate", 0.0),
                    churn_rate=raw.get("churn_rate", 0.0),
                    retention_rate=raw.get("retention_rate", 0.0),
                    total_memories_created=raw.get("total_memories_created", 0),
                    total_llm_calls=raw.get("total_llm_calls", 0),
                    total_embedding_calls=raw.get("total_embedding_calls", 0),
                    total_searches=raw.get("total_searches", 0),
                    total_imports=raw.get("total_imports", 0),
                    total_syncs=raw.get("total_syncs", 0),
                    total_coach_sessions=raw.get("total_coach_sessions", 0),
                    total_cost_cents=raw.get("total_cost_cents", 0),
                    total_revenue_cents=raw.get("total_revenue_cents", 0),
                    net_revenue_cents=raw.get("net_revenue_cents", 0),
                    margin_percent=raw.get("margin_percent", 0.0),
                    active_users=raw.get("active_users", 0),
                    new_users=raw.get("new_users", 0),
                    top_entities=raw.get("top_entities", []),
                    top_contributors=raw.get("top_contributors", []),
                    import_channels=raw.get("import_channels", {}),
                    daily_usage_trend=raw.get("daily_usage_trend", []),
                    memory_growth_trend=raw.get("memory_growth_trend", []),
                )
            except Exception:
                pass

        return Report(
            id=row["id"],
            tenant_id=row["tenant_id"],
            report_type=ReportType(row["report_type"]),
            period_start=row["period_start"],
            period_end=row["period_end"],
            format=ReportFormat(row.get("format", "json")),
            status=ReportStatus(row.get("status", "generating")),
            data=data,
            file_path=row.get("file_path"),
            created_at=_safe_parse_datetime(row.get("created_at")),
        )

    def close(self) -> None:
        if hasattr(self._db, "conn") and self._db.conn:
            self._db.conn.close()

    def __enter__(self) -> "ReportStoreAdapter":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def _safe_parse_datetime(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)
