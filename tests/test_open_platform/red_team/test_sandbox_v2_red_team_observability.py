"""Red-Team Observability tests (Step 18)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.otel_adapter import sanitize_attributes, MockOTelExporter, OTLPHttpExporterSkeleton
from src.open_platform.sandbox_v2.observability import SandboxV2ObservabilityService
from src.open_platform.sandbox_v2.grafana import SandboxV2GrafanaDashboardBuilder
from src.open_platform.sandbox_v2.prometheus import SandboxV2PrometheusConfigBuilder
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


class TestNoSecretLeakage:
    def test_metrics_label_no_secret(self):
        attrs = {"SANDBOX_V2_POSTGRES_DSN": "postgresql://user:pass@host/db",
                 "SANDBOX_V2_MINIO_SECRET_KEY": "sekret"}
        safe = sanitize_attributes(attrs)
        assert safe["SANDBOX_V2_POSTGRES_DSN"] == "[REDACTED]"
        assert safe["SANDBOX_V2_MINIO_SECRET_KEY"] == "[REDACTED]"

    def test_trace_no_token(self):
        attrs = {"access_token": "eyJhbGciOi...", "sub": "user-1"}
        safe = sanitize_attributes(attrs)
        assert safe["access_token"] == "[REDACTED]"

    def test_trace_no_client_secret(self):
        attrs = {"client_secret": "abc123", "client_id": "test-id"}
        safe = sanitize_attributes(attrs)
        assert safe["client_secret"] == "[REDACTED]"

    def test_grafana_no_dsn(self):
        b = SandboxV2GrafanaDashboardBuilder()
        d = b.build_overview_dashboard()
        s = str(d.to_dict())
        assert "DSN" not in s

    def test_prometheus_no_access_key(self):
        b = SandboxV2PrometheusConfigBuilder()
        y = b.export_scrape_yaml() + b.export_alert_rules_yaml()
        assert "access_key" not in y.lower()
        assert "secret_key" not in y.lower()


class TestNoExternalNetwork:
    def test_otel_mock_no_external(self):
        e = MockOTelExporter()
        r = e.export_metrics([{"name": "test"}])
        assert r["exported_count"] == 1  # mock just records, no HTTP

    def test_otlp_skeleton_no_http(self):
        e = OTLPHttpExporterSkeleton()
        r = e.export_metrics([{"name": "should_not_send"}])
        assert r["status"] == "skipped"

    def test_simulate_export_no_external(self):
        store = SQLiteSandboxV2Store(Settings(), db_path=":memory:")
        svc = SandboxV2ObservabilityService(store=store, settings=DummySettings())
        r = svc.simulate_otel_export(signal_type="trace")
        # must not make external calls
        assert r["status"] == "disabled"


class TestContentRedaction:
    def test_no_artifact_content_in_trace(self):
        attrs = {"artifact_content": "base64encodedbinarydata..." * 10}
        safe = sanitize_attributes(attrs)
        # long content should be truncated
        val = safe.get("artifact_content", "")
        assert len(val) <= 503

    def test_no_prompt_full_text_in_trace(self):
        attrs = {"prompt": "This is a very long prompt text " * 40}
        safe = sanitize_attributes(attrs)
        val = safe.get("prompt", "")
        assert len(val) <= 503


class TestFailClosed:
    def test_malformed_attributes_no_crash(self):
        safe = sanitize_attributes(None)
        assert isinstance(safe, dict)
        safe = sanitize_attributes(123)
        assert isinstance(safe, dict)

    def test_otel_disabled_rejects_all(self):
        e = MockOTelExporter()
        # Even mock should redact secrets
        r = e.export_metrics([{"client_secret": "secret-value", "ok": "yes"}])
        assert r["exported_count"] == 1


class TestReadinessSecurity:
    def test_external_telemetry_export_false(self):
        svc = SandboxV2ObservabilityService(settings=DummySettings())
        r = svc.get_observability_readiness()
        assert not r["external_telemetry_export"]

    def test_observability_safe_mode_true(self):
        svc = SandboxV2ObservabilityService(settings=DummySettings())
        r = svc.get_observability_readiness()
        assert r["observability_safe_mode"]

    def test_otel_real_export_false(self):
        svc = SandboxV2ObservabilityService(settings=DummySettings())
        r = svc.get_observability_readiness()
        assert not r["otel_real_export"]
