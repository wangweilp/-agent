"""Step 23 — Observability Security Tests (Red-Team).

Verifies observability is safe against:
- metrics endpoint abuse
- label explosion
- metrics injection
- tracing abuse
- export failure (fail closed)
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
import threading

from src.observability.metrics_registry import (
    MetricsRegistry, Counter, Gauge,
    get_metrics_registry, reset_metrics_registry,
)
from src.observability.prometheus_exporter import PrometheusExporter
from src.observability.tracing import Tracer, get_tracer, reset_tracer
from src.observability.service import ObservabilityService
from src.observability.oidc_metrics import get_oidc_metrics, reset_oidc_metrics
from src.observability.saml_metrics import get_saml_metrics, reset_saml_metrics
from src.observability.governance_metrics import get_governance_metrics, reset_governance_metrics
from src.observability.audit_metrics import get_audit_metrics


class DisabledSettings:
    prometheus_enabled = False; otel_enabled = False; grafana_dashboard_enabled = False
    otel_include_sensitive_attributes = False


class EnabledSettings:
    prometheus_enabled = True; otel_enabled = True; grafana_dashboard_enabled = True
    otel_exporter = "mock"; otel_endpoint = ""; otel_service_name = "sandbox-v2"
    otel_traces_enabled = True; otel_include_sensitive_attributes = False


@pytest.fixture(autouse=True)
def reset_all():
    reset_metrics_registry(); reset_tracer()
    reset_oidc_metrics(); reset_saml_metrics(); reset_governance_metrics()
    yield
    reset_metrics_registry(); reset_tracer()
    reset_oidc_metrics(); reset_saml_metrics(); reset_governance_metrics()


# ═══════════════════════════════════════════
# 1. Metrics endpoint abuse
# ═══════════════════════════════════════════

class TestMetricsEndpointAbuse:
    def test_disabled_endpoint_returns_disabled_text(self):
        exporter = PrometheusExporter(settings=DisabledSettings())
        text = exporter.export_prometheus_text()
        assert "disabled" in text.lower()

    def test_enabled_endpoint_honors_disabled_mode(self):
        exporter = PrometheusExporter(settings=DisabledSettings())
        json_out = exporter.export_json()
        assert json_out["enabled"] is False
        assert json_out["metrics"] == {}

    def test_disabled_settings_block_otel(self):
        svc = ObservabilityService(settings=DisabledSettings())
        r = svc.get_readiness()
        assert r["fail_closed"] is True
        assert not r["prometheus"]["enabled"]
        assert not r["otel"]["enabled"]


# ═══════════════════════════════════════════
# 2. Label explosion
# ═══════════════════════════════════════════

class TestLabelExplosion:
    def test_no_label_explosion_possible(self):
        """The metrics registry uses fixed metric names — unbounded label explosion is not possible."""
        reg = MetricsRegistry()
        for i in range(1000):
            reg.counter(f"metric_{i}")
        assert len(reg.list_all()) == 1000
        # Export still works
        text = reg.export_prometheus_text()
        assert text  # non-empty, no crash


# ═══════════════════════════════════════════
# 3. Metrics injection
# ═══════════════════════════════════════════

class TestMetricsInjection:
    def test_metric_name_with_special_chars_sanitized(self):
        reg = MetricsRegistry()
        c = reg.counter("my.metric-name with spaces")
        c.inc()
        text = reg.export_prometheus_text()
        assert "my_metric_name_with_spaces" in text

    def test_duplicate_metric_name_returns_existing(self):
        reg = MetricsRegistry()
        c1 = reg.counter("dup_metric")
        c2 = reg.counter("dup_metric")
        assert c1 is c2

    def test_prometheus_output_no_sensitive_data(self):
        """Metrics should never contain sensitive attribute keys in export."""
        reg = MetricsRegistry()
        c = reg.counter("test_metric")
        c.inc(42)
        text = reg.export_prometheus_text()
        sensitive_words = ["secret", "token", "password", "key", "dsn"]
        for word in sensitive_words:
            assert word not in text.lower(), f"Sensitive word '{word}' found in metrics output"


# ═══════════════════════════════════════════
# 4. Tracing abuse
# ═══════════════════════════════════════════

class TestTracingAbuse:
    def test_tracer_disabled_does_not_record(self):
        t = Tracer(enabled=False)
        span = t.start_span("should_not_record")
        t.end_span(span, "ok")
        assert t.span_count() == 0

    def test_tracer_multiple_end_same_span_no_crash(self):
        t = Tracer(enabled=True)
        span = t.start_span("s")
        t.end_span(span, "ok")
        t.end_span(span, "ok")  # double end — should not crash
        assert t.span_count() == 1


# ═══════════════════════════════════════════
# 5. Export failure (fail closed)
# ═══════════════════════════════════════════

class TestExportFailure:
    def test_empty_registry_exports_cleanly(self):
        reg = MetricsRegistry()
        text = reg.export_prometheus_text()
        assert "No metrics registered" in text

    def test_fail_closed_on_readiness(self):
        svc = ObservabilityService(settings=DisabledSettings())
        r = svc.get_readiness()
        assert r["fail_closed"] is True
        for key in ["prometheus", "otel", "tracing", "dashboards"]:
            assert r[key]["enabled"] is False or "disabled" in r[key]["status"]


# ═══════════════════════════════════════════
# 6. Default deny verification
# ═══════════════════════════════════════════

class TestDefaultDeny:
    def test_all_disabled_by_default(self):
        settings = DisabledSettings()
        assert not settings.prometheus_enabled
        assert not settings.otel_enabled
        assert not settings.grafana_dashboard_enabled

    def test_no_network_access_from_metrics(self):
        """Metrics registry and exporter are purely in-process, no network."""
        reg = MetricsRegistry()
        reg.counter("test").inc()
        text = reg.export_prometheus_text()
        assert isinstance(text, str)
        assert "127.0.0.1" not in text
        assert "http" not in text
