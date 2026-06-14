"""Metrics Collector tests (Step 15)."""
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest, json
from src.open_platform.sandbox_v2.metrics import SandboxV2MetricsCollector

class TestMetricsCollectorBasic:
    def test_collect_all_returns_data(self):
        from src.adapters.config import Settings; from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        store = SQLiteSandboxV2Store(config=Settings()); mc = SandboxV2MetricsCollector(store=store)
        data = mc.collect_all()
        assert "samples" in data; assert len(data["samples"]) > 0
    def test_create_snapshot(self):
        from src.adapters.config import Settings; from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        store = SQLiteSandboxV2Store(config=Settings()); mc = SandboxV2MetricsCollector(store=store)
        snap = mc.create_snapshot()
        assert snap.snapshot_id != ""
    def test_collector_no_store(self):
        mc = SandboxV2MetricsCollector()
        data = mc.collect_all()
        assert "samples" in data
    def test_export_json(self):
        from src.adapters.config import Settings; from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        store = SQLiteSandboxV2Store(config=Settings()); mc = SandboxV2MetricsCollector(store=store)
        j = mc.export_json()
        assert "snapshot_id" in j

class TestMetricsNoSecrets:
    def test_prometheus_export_no_secret(self):
        from src.adapters.config import Settings; from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        store = SQLiteSandboxV2Store(config=Settings()); mc = SandboxV2MetricsCollector(store=store)
        text = mc.export_prometheus_text()
        assert "DSN" not in text; assert "ACCESS_KEY" not in text; assert "SECRET" not in text
    def test_json_export_no_secret(self):
        mc = SandboxV2MetricsCollector()
        j = mc.export_json()
        json_str = json.dumps(j)
        assert "postgresql://" not in json_str

class TestPrometheusExport:
    def test_format_has_help_type(self):
        from src.adapters.config import Settings; from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        store = SQLiteSandboxV2Store(config=Settings()); mc = SandboxV2MetricsCollector(store=store)
        text = mc.export_prometheus_text()
        assert "# HELP" in text; assert "# TYPE" in text
    def test_format_has_sandbox_v2_prefix(self):
        mc = SandboxV2MetricsCollector()
        text = mc.export_prometheus_text()
        assert "sandbox_v2_" in text

class TestMetricsSnapshotPersist:
    def test_persist_snapshot(self):
        from src.adapters.config import Settings; from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        store = SQLiteSandboxV2Store(config=Settings()); mc = SandboxV2MetricsCollector(store=store)
        snap = mc.create_snapshot()
        fetched = store.get_latest_metrics_snapshot()
        assert fetched is not None
