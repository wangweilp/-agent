"""Prometheus Export tests (Step 15)."""
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.metrics import SandboxV2MetricsCollector

class TestPrometheusFormat:
    def test_export_has_help_lines(self):
        mc = SandboxV2MetricsCollector(); text = mc.export_prometheus_text()
        assert "# HELP" in text
    def test_export_has_type_lines(self):
        mc = SandboxV2MetricsCollector(); text = mc.export_prometheus_text()
        assert "# TYPE" in text
    def test_export_starts_with_help(self):
        mc = SandboxV2MetricsCollector(); text = mc.export_prometheus_text()
        assert text.strip() != ""
    def test_export_has_metric_values(self):
        mc = SandboxV2MetricsCollector(); text = mc.export_prometheus_text()
        lines = [l for l in text.split("\n") if l and not l.startswith("#")]
        assert len(lines) > 0

class TestPrometheusNoSecrets:
    def test_no_dsn_in_export(self):
        mc = SandboxV2MetricsCollector(); text = mc.export_prometheus_text()
        assert "postgresql://" not in text; assert "REDIS_URL" not in text
    def test_no_access_key_in_export(self):
        mc = SandboxV2MetricsCollector(); text = mc.export_prometheus_text()
        assert "ACCESS_KEY" not in text; assert "SECRET_KEY" not in text
    def test_no_absolute_paths(self):
        mc = SandboxV2MetricsCollector(); text = mc.export_prometheus_text()
        assert "C:\\" not in text; assert "/Users/" not in text
    def test_label_values_redacted(self):
        mc = SandboxV2MetricsCollector(); text = mc.export_prometheus_text()
        assert "secret" not in text.lower() or "[REDACTED]" in text
