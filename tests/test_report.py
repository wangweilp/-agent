"""Tests for Report Domain + ReportStore Adapter.

覆盖:
- Report 数据类
- compute_period_range 计算
- ReportStore CRUD
- CSV / JSON 导出
"""
import json
import os
import pytest
from datetime import datetime, timezone, timedelta

from src.core.report import (
    Report,
    ReportData,
    ReportFormat,
    ReportStatus,
    ReportType,
    compute_period_range,
)
from src.adapters.report_store import ReportStoreAdapter
from src.adapters.config import Settings


class TestReportDomain:
    """核心域：Report / ReportData / compute_period_range。"""

    def test_report_creation(self):
        data = ReportData(
            report_type=ReportType.MONTHLY,
            period_start="2026-06-01",
            period_end="2026-06-30",
            mrr_cents=1234000,
            arr_cents=14808000,
            total_tenants=45,
        )
        report = Report(
            tenant_id="tnt_001",
            report_type=ReportType.MONTHLY,
            period_start="2026-06-01",
            period_end="2026-06-30",
            format=ReportFormat.JSON,
            data=data,
        )
        assert report.id.startswith("rpt_")
        assert report.report_type == ReportType.MONTHLY
        assert report.status == ReportStatus.GENERATING
        assert report.data is not None
        assert report.data.mrr_cents == 1234000

        d = report.as_dict()
        assert d["data"]["mrr_cents"] == 1234000
        assert d["data"]["report_type"] == "monthly"

    def test_report_data_as_dict(self):
        data = ReportData(
            report_type=ReportType.WEEKLY,
            period_start="2026-06-01",
            period_end="2026-06-07",
            top_entities=[{"name": "AI", "entity_type": "topic", "mention_count": 42}],
            import_channels={"web": 10, "api": 5},
            daily_usage_trend=[{"date": "2026-06-01", "memory": 10}],
        )
        d = data.as_dict()
        assert d["report_type"] == "weekly"
        assert len(d["top_entities"]) == 1
        assert d["import_channels"]["web"] == 10
        assert len(d["daily_usage_trend"]) == 1

    def test_compute_period_range_weekly(self):
        # 使用固定日期测试
        monday = datetime(2026, 6, 1, tzinfo=timezone.utc)  # Monday
        start, end = compute_period_range(ReportType.WEEKLY, now=monday)
        assert start == "2026-06-01"
        assert end == "2026-06-07"

    def test_compute_period_range_monthly(self):
        june = datetime(2026, 6, 15, tzinfo=timezone.utc)
        start, end = compute_period_range(ReportType.MONTHLY, now=june)
        assert start == "2026-06-01"
        assert end == "2026-06-30"

    def test_compute_period_range_quarterly(self):
        q2 = datetime(2026, 5, 10, tzinfo=timezone.utc)
        start, end = compute_period_range(ReportType.QUARTERLY, now=q2)
        assert start == "2026-04-01"
        assert end == "2026-06-30"

    def test_compute_period_range_year_end(self):
        dec = datetime(2026, 12, 20, tzinfo=timezone.utc)
        start, end = compute_period_range(ReportType.MONTHLY, now=dec)
        assert start == "2026-12-01"
        assert end == "2026-12-31"


class TestReportStoreAdapter:
    """ReportStoreAdapter 集成测试。"""

    @pytest.fixture
    def store(self):
        settings = Settings(sqlite_db_path=":memory:")
        s = ReportStoreAdapter(settings)
        yield s
        s.close()

    def test_create_and_get_report(self, store):
        data = ReportData(
            report_type=ReportType.WEEKLY,
            period_start="2026-06-01",
            period_end="2026-06-07",
            total_memories_created=100,
        )
        report = Report(
            tenant_id="tnt_001",
            report_type=ReportType.WEEKLY,
            period_start="2026-06-01",
            period_end="2026-06-07",
            format=ReportFormat.JSON,
            status=ReportStatus.READY,
            data=data,
        )
        rid = store.create_report(report)
        assert rid == report.id

        fetched = store.get_report("tnt_001", report.id)
        assert fetched is not None
        assert fetched.report_type == ReportType.WEEKLY
        assert fetched.data is not None
        assert fetched.data.total_memories_created == 100

    def test_list_reports(self, store):
        for i in range(3):
            report = Report(
                tenant_id="tnt_001",
                report_type=ReportType.MONTHLY,
                period_start=f"2026-0{i+1}-01",
                period_end=f"2026-0{i+1}-28",
                data=ReportData(report_type=ReportType.MONTHLY, period_start="", period_end=""),
            )
            store.create_report(report)

        reports = store.list_reports("tnt_001")
        assert len(reports) == 3

        # 按类型过滤
        weekly_reports = store.list_reports("tnt_001", report_type="weekly")
        assert len(weekly_reports) == 0

    def test_update_report(self, store):
        report = Report(
            tenant_id="tnt_001",
            report_type=ReportType.MONTHLY,
            period_start="2026-06-01",
            period_end="2026-06-30",
        )
        store.create_report(report)

        updated = store.update_report("tnt_001", report.id, {"status": "ready"})
        assert updated is not None
        assert updated.status == ReportStatus.READY

        assert store.update_report("tnt_001", "nonexistent", {}) is None

    def test_delete_report(self, store):
        report = Report(
            tenant_id="tnt_001",
            report_type=ReportType.MONTHLY,
            period_start="2026-06-01",
            period_end="2026-06-30",
        )
        store.create_report(report)
        assert store.delete_report("tnt_001", report.id) is True
        assert store.get_report("tnt_001", report.id) is None
        assert store.delete_report("tnt_001", "nonexistent") is False

    def test_export_json(self, store, tmp_path):
        """测试 JSON 导出。"""
        # 确保导出目录存在
        data = ReportData(
            report_type=ReportType.WEEKLY,
            period_start="2026-06-01",
            period_end="2026-06-07",
            mrr_cents=500000,
            active_users=25,
        )
        report = Report(
            tenant_id="tnt_001",
            report_type=ReportType.WEEKLY,
            period_start="2026-06-01",
            period_end="2026-06-07",
            data=data,
        )

        filepath = store.export_json(report)
        assert os.path.exists(filepath)
        assert filepath.endswith(".json")

        with open(filepath, "r", encoding="utf-8") as f:
            content = json.load(f)
        assert content["mrr_cents"] == 500000
        assert content["active_users"] == 25

        # Cleanup
        os.remove(filepath)

    def test_export_csv(self, store):
        """测试 CSV 导出。"""
        data = ReportData(
            report_type=ReportType.MONTHLY,
            period_start="2026-06-01",
            period_end="2026-06-30",
            mrr_cents=1234000,
            arr_cents=14808000,
            total_tenants=45,
            active_tenants=38,
            conversion_rate=0.35,
            import_channels={"web": 10, "api": 5, "cli": 3},
            daily_usage_trend=[{"date": "2026-06-01", "llm_call": 50, "memory": 100}],
        )
        report = Report(
            tenant_id="tnt_001",
            report_type=ReportType.MONTHLY,
            period_start="2026-06-01",
            period_end="2026-06-30",
            data=data,
        )

        filepath = store.export_csv(report)
        assert os.path.exists(filepath)
        assert filepath.endswith(".csv")

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        assert "MRR" in content
        assert "1234000" in content
        assert "web" in content

        # Cleanup
        os.remove(filepath)

    def test_export_without_data_raises(self, store):
        """无数据的报告导出时抛出 ValueError。"""
        report = Report(
            tenant_id="tnt_001",
            report_type=ReportType.MONTHLY,
            period_start="2026-06-01",
            period_end="2026-06-30",
            data=None,
        )
        with pytest.raises(ValueError):
            store.export_json(report)
        with pytest.raises(ValueError):
            store.export_csv(report)
