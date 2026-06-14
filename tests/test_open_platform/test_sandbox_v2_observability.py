"""Observability Service tests (Step 18)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.observability import SandboxV2ObservabilityService
from src.open_platform.sandbox_v2.otel_adapter import sanitize_attributes, get_otel_exporter, MockOTelExporter, DisabledOTelExporter
from src.open_platform.sandbox_v2.models import SandboxV2TelemetryExportStatus
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.config import Settings


class DummySettings:
    observability_enabled = False
    prometheus_export_enabled = True
    prometheus_scrape_path = "/api/metrics"
    grafana_dashboard_enabled = False
    otel_enabled = False
    otel_exporter = "disabled"
    otel_endpoint = ""
    otel_service_name = "sandbox-v2"
    otel_traces_enabled = False
    otel_metrics_enabled = False
    otel_logs_enabled = False
    otel_include_sensitive_attributes = False
    observability_safe_mode = True


@pytest.fixture
def store():
    return SQLiteSandboxV2Store(Settings(), db_path=":memory:")


class TestObservabilityDefaults:
    def test_disabled_by_default(self):
        svc = SandboxV2ObservabilityService(settings=DummySettings())
        r = svc.get_observability_readiness()
        assert not r["observability_enabled"]
        assert not r["otel_enabled"]
        assert r["observability_safe_mode"]

    def test_readiness_fields(self):
        svc = SandboxV2ObservabilityService(settings=DummySettings())
        r = svc.get_observability_readiness()
        assert r["observability_config"]
        assert r["prometheus_scrape_config"]
        assert r["grafana_dashboard_spec"]
        assert not r["otel_real_export"]


class TestPrometheusConfig:
    def test_scrape_config_generated(self):
        svc = SandboxV2ObservabilityService(settings=DummySettings())
        cfg = svc.generate_prometheus_scrape_config()
        assert "scrape_configs" in cfg
        assert len(cfg["scrape_configs"]) > 0

    def test_alert_rules_generated(self):
        svc = SandboxV2ObservabilityService(settings=DummySettings())
        rules = svc.generate_prometheus_alert_rules()
        assert "groups" in rules
        group = rules["groups"][0]
        assert len(group["rules"]) >= 5

    def test_no_secret_in_scrape_config(self):
        svc = SandboxV2ObservabilityService(settings=DummySettings())
        cfg = svc.generate_prometheus_scrape_config()
        s = str(cfg)
        assert "secret" not in s.lower() or "redacted" in s.lower()


class TestGrafanaDashboard:
    def test_overview_dashboard_generated(self):
        svc = SandboxV2ObservabilityService(settings=DummySettings())
        dash = svc.generate_grafana_dashboard("overview")
        assert dash["title"]
        assert len(dash["panels"]) > 0

    def test_security_dashboard(self):
        svc = SandboxV2ObservabilityService(settings=DummySettings())
        dash = svc.generate_grafana_dashboard("security")
        assert "Security" in dash["title"]

    def test_datasource_placeholder(self):
        svc = SandboxV2ObservabilityService(settings=DummySettings())
        dash = svc.generate_grafana_dashboard()
        assert "${DS_PROMETHEUS}" in dash.get("datasource", "")

    def test_no_secret_in_dashboard(self):
        svc = SandboxV2ObservabilityService(settings=DummySettings())
        dash = svc.generate_grafana_dashboard()
        s = str(dash)
        assert "password" not in s.lower()
        assert "secret" not in s.lower() or "redacted" in s.lower()
        assert "dsn" not in s.lower()


class TestTraceSpans:
    def test_create_span(self, store):
        svc = SandboxV2ObservabilityService(store=store, settings=DummySettings())
        span = svc.create_trace_span(span_name="test_operation", resource_type="job", organization_id="org-1")
        assert span.span_id != ""
        assert span.span_name == "test_operation"

    def test_list_spans(self, store):
        svc = SandboxV2ObservabilityService(store=store, settings=DummySettings())
        svc.create_trace_span(span_name="op1", organization_id="org-1")
        svc.create_trace_span(span_name="op2", organization_id="org-1")
        spans = svc.list_trace_spans(organization_id="org-1")
        assert len(spans) >= 2

    def test_sensitive_attributes_redacted(self, store):
        svc = SandboxV2ObservabilityService(store=store, settings=DummySettings())
        span = svc.create_trace_span(span_name="test", attributes={"secret": "my-secret", "key": "value"})
        d = span.to_dict()
        attrs = d.get("attributes_redacted", {})
        assert attrs.get("secret") == "[REDACTED]"

    def test_overlong_attributes_truncated(self):
        attrs = sanitize_attributes({"long": "x" * 1000}, allow_sensitive=False)
        assert len(attrs["long"]) <= 503


class TestTelemetryExport:
    def test_simulate_export_disabled(self, store):
        svc = SandboxV2ObservabilityService(store=store, settings=DummySettings())
        result = svc.simulate_otel_export(signal_type="metric", items=[{"name": "test", "value": 1}])
        assert result["status"] == "disabled"

    def test_simulate_no_external_request(self, store):
        svc = SandboxV2ObservabilityService(store=store, settings=DummySettings())
        result = svc.simulate_otel_export()
        assert result.get("exported_count", -1) == 0

    def test_export_record_persisted(self, store):
        svc = SandboxV2ObservabilityService(store=store, settings=DummySettings())
        svc.simulate_otel_export(signal_type="metric", organization_id="org-1")
        records = svc.list_telemetry_export_records()
        assert len(records) >= 1

    def test_list_records(self, store):
        svc = SandboxV2ObservabilityService(store=store, settings=DummySettings())
        svc.create_telemetry_export_record(provider="mock", signal_type="trace", status="exported")
        svc.create_telemetry_export_record(provider="mock", signal_type="metric", status="skipped")
        all_records = svc.list_telemetry_export_records()
        assert len(all_records) >= 2
        traces = svc.list_telemetry_export_records(signal_type="trace")
        assert len(traces) >= 1
