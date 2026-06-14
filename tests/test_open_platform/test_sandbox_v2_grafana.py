"""Grafana Dashboard tests (Step 18)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.grafana import SandboxV2GrafanaDashboardBuilder


class TestGrafanaDashboard:
    def test_overview_has_panels(self):
        b = SandboxV2GrafanaDashboardBuilder()
        d = b.build_overview_dashboard()
        assert len(d.panels) > 0
        assert "Overview" in d.title

    def test_security_has_panels(self):
        b = SandboxV2GrafanaDashboardBuilder()
        d = b.build_security_dashboard()
        assert len(d.panels) > 0

    def test_runtime_has_panels(self):
        b = SandboxV2GrafanaDashboardBuilder()
        d = b.build_runtime_dashboard()
        assert len(d.panels) > 0

    def test_performance_has_panels(self):
        b = SandboxV2GrafanaDashboardBuilder()
        d = b.build_performance_dashboard()
        assert len(d.panels) > 0

    def test_datasource_placeholder(self):
        b = SandboxV2GrafanaDashboardBuilder()
        d = b.build_overview_dashboard()
        assert "${DS_PROMETHEUS}" in d.datasource

    def test_no_secret_in_json(self):
        b = SandboxV2GrafanaDashboardBuilder()
        d = b.build_overview_dashboard()
        s = str(d.to_dict())
        assert "password" not in s.lower()
        assert "secret" not in s.lower()
        assert "dsn" not in s.lower()

    def test_no_absolute_path(self):
        b = SandboxV2GrafanaDashboardBuilder()
        d = b.build_overview_dashboard()
        s = str(d.to_dict())
        # No hardcoded Windows or Unix paths
        assert "C:\\" not in s
        assert "/home/" not in s

    def test_export_all_dashboards(self):
        b = SandboxV2GrafanaDashboardBuilder()
        result = b.export_dashboard_json()
        assert "overview" in result
        assert "security" in result
        assert "runtime" in result
        assert "performance" in result

    def test_covers_key_metrics(self):
        b = SandboxV2GrafanaDashboardBuilder()
        d = b.build_overview_dashboard()
        s = str(d.to_dict())
        # Should cover key sandbox v2 metrics
        assert "jobs_created" in s
        assert "cross_tenant_denied" in s or "network_denied" in s
        assert "queue_depth" in s
