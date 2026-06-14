"""Observability Integration tests — default skip.

Only runs when:
  SANDBOX_V2_RUN_OBSERVABILITY_INTEGRATION=true
  SANDBOX_V2_OBSERVABILITY_ENABLED=true

This step only does local preflight — no external Prometheus/Grafana/OTel.
"""
from __future__ import annotations
import os
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest


def _integration_enabled() -> bool:
    return all([
        os.getenv("SANDBOX_V2_RUN_OBSERVABILITY_INTEGRATION", "").lower() == "true",
        os.getenv("SANDBOX_V2_OBSERVABILITY_ENABLED", "").lower() == "true",
    ])


pytestmark = pytest.mark.skipif(
    not _integration_enabled(),
    reason="Observability integration tests skipped — set SANDBOX_V2_RUN_OBSERVABILITY_INTEGRATION=true and SANDBOX_V2_OBSERVABILITY_ENABLED=true",
)


class TestObservabilityIntegration:
    def test_readiness_preflight(self):
        from src.open_platform.sandbox_v2.observability import SandboxV2ObservabilityService
        svc = SandboxV2ObservabilityService()
        r = svc.get_observability_readiness()
        assert r["observability_config"]
        assert r["prometheus_scrape_config"]

    def test_prometheus_config_generated(self):
        from src.open_platform.sandbox_v2.prometheus import SandboxV2PrometheusConfigBuilder
        b = SandboxV2PrometheusConfigBuilder()
        cfg = b.build_scrape_config()
        assert "scrape_configs" in cfg

    def test_grafana_dashboard_generated(self):
        from src.open_platform.sandbox_v2.grafana import SandboxV2GrafanaDashboardBuilder
        b = SandboxV2GrafanaDashboardBuilder()
        d = b.build_overview_dashboard()
        assert len(d.panels) > 0

    def test_otel_skeleton_readiness(self):
        from src.open_platform.sandbox_v2.otel_adapter import get_otel_exporter
        e = get_otel_exporter("disabled")
        r = e.get_readiness()
        assert not r["otel_real_export"]

    def test_no_external_network(self):
        # Simulate export must not make network calls
        from src.open_platform.sandbox_v2.otel_adapter import OTLPHttpExporterSkeleton
        e = OTLPHttpExporterSkeleton()
        r = e.export_metrics([{"test": "value"}])
        assert r["exported_count"] == 0

    def test_no_secret_leak(self):
        from src.open_platform.sandbox_v2.otel_adapter import sanitize_attributes
        attrs = {"token": "secret123"}
        safe = sanitize_attributes(attrs)
        assert safe["token"] == "[REDACTED]"
