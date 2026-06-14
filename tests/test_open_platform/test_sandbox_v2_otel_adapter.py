"""OTel Adapter tests (Step 18)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.otel_adapter import (
    DisabledOTelExporter, MockOTelExporter, OTLPHttpExporterSkeleton,
    get_otel_exporter, sanitize_attributes,
)
from src.open_platform.sandbox_v2.models import SandboxV2TelemetryExportStatus


class TestDisabledExporter:
    def test_all_exports_disabled(self):
        e = DisabledOTelExporter()
        assert e.get_name() == "disabled"
        r = e.export_metrics([], None)
        assert r["status"] == SandboxV2TelemetryExportStatus.DISABLED
        r = e.export_trace_spans([], None)
        assert r["status"] == SandboxV2TelemetryExportStatus.DISABLED

    def test_readiness(self):
        e = DisabledOTelExporter()
        r = e.get_readiness()
        assert not r["otel_real_export"]


class TestMockExporter:
    def test_no_external_network(self):
        e = MockOTelExporter()
        r = e.export_metrics([{"name": "test"}])
        assert r["status"] == SandboxV2TelemetryExportStatus.EXPORTED
        assert r["exported_count"] == 1

    def test_trace_export(self):
        e = MockOTelExporter()
        r = e.export_trace_spans([{"span_id": "1"}])
        assert r["exported_count"] == 1

    def test_log_export(self):
        e = MockOTelExporter()
        r = e.export_logs([{"message": "test"}])
        assert r["exported_count"] == 1

    def test_records_tracked(self):
        e = MockOTelExporter()
        e.export_metrics([{"n": "a"}])
        e.export_trace_spans([{"s": "b"}])
        assert len(e.exported_records) == 2


class TestOTLPSkeleton:
    def test_no_http_sent(self):
        e = OTLPHttpExporterSkeleton()
        r = e.export_metrics([{"metric": "test"}])
        assert r["status"] == SandboxV2TelemetryExportStatus.SKIPPED

    def test_config_validation(self):
        e = OTLPHttpExporterSkeleton()
        r = e.validate_config({"otel_endpoint": "http://localhost:4318"})
        assert r["valid"]

    def test_missing_endpoint_invalid(self):
        e = OTLPHttpExporterSkeleton()
        r = e.validate_config({"otel_endpoint": ""})
        assert not r["valid"]


class TestSanitizeAttributes:
    def test_secret_redacted(self):
        attrs = {"client_secret": "abc123", "api_key": "xyz", "user": "john"}
        safe = sanitize_attributes(attrs)
        assert safe["client_secret"] == "[REDACTED]"
        assert safe["api_key"] == "[REDACTED]"
        assert safe["user"] == "john"

    def test_allow_sensitive_bypass(self):
        attrs = {"token": "value"}
        safe = sanitize_attributes(attrs, allow_sensitive=True)
        assert safe["token"] == "value"

    def test_no_crash_on_none(self):
        safe = sanitize_attributes(None)
        assert isinstance(safe, dict)

    def test_truncate_long_values(self):
        attrs = {"description": "x" * 1000}
        safe = sanitize_attributes(attrs)
        assert len(safe["description"]) <= 503


class TestFactory:
    def test_default_disabled(self):
        e = get_otel_exporter("invalid")
        assert e.get_name() == "disabled"

    def test_mock_factory(self):
        e = get_otel_exporter("mock")
        assert e.get_name() == "mock"
