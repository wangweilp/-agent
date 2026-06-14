"""Monitoring API tests (Step 15)."""
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest

class TestMonitoringReadinessFields:
    def test_readiness_has_monitoring_fields(self):
        from src.api.sandbox_v2 import ReadinessResponse
        resp = ReadinessResponse(); data = resp.model_dump()
        fields = ["metrics_collector","health_checks","alert_engine","internal_alert_records","prometheus_export","external_notifications","monitoring_dashboard","audit_signal_aggregation","alert_rules_present","monitoring_safe_mode"]
        for f in fields: assert f in data, f"Missing: {f}"
    def test_default_monitoring_values(self):
        from src.api.sandbox_v2 import ReadinessResponse
        resp = ReadinessResponse()
        assert resp.metrics_collector is True; assert resp.health_checks is True
        assert resp.alert_engine is True; assert resp.external_notifications is False
        assert resp.monitoring_safe_mode is True

class TestMonitoringAPIIntegrity:
    def test_metrics_snapshot_no_500(self):
        from src.open_platform.sandbox_v2.metrics import SandboxV2MetricsCollector
        mc = SandboxV2MetricsCollector()
        data = mc.collect_all()
        assert "samples" in data
    def test_health_no_500(self):
        from src.open_platform.sandbox_v2.health import SandboxV2HealthService
        hs = SandboxV2HealthService(); results = hs.run_all()
        assert len(results) > 0
    def test_alerts_evaluate_no_500(self):
        from src.open_platform.sandbox_v2.alerts import SandboxV2AlertEngine
        engine = SandboxV2AlertEngine(); alerts = engine.evaluate_all({"queue_depth": 5})
        assert isinstance(alerts, list)
    def test_prometheus_text_no_error(self):
        from src.open_platform.sandbox_v2.metrics import SandboxV2MetricsCollector
        mc = SandboxV2MetricsCollector(); text = mc.export_prometheus_text()
        assert len(text) > 0; assert "Error" not in text

class TestStorePersistence:
    def test_alert_crud(self):
        from src.adapters.config import Settings; from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        from src.open_platform.sandbox_v2.models import SandboxV2Alert
        store = SQLiteSandboxV2Store(config=Settings())
        alert = SandboxV2Alert(name="crud-test", severity="warning")
        store.create_alert(alert); fetched = store.get_alert(alert.alert_id); assert fetched is not None
        store.update_alert_status(alert.alert_id, "acknowledged", actor="tester")
        fetched2 = store.get_alert(alert.alert_id); assert fetched2["status"] == "acknowledged"
    def test_health_check_persist(self):
        from src.adapters.config import Settings; from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        from src.open_platform.sandbox_v2.models import SandboxV2HealthCheckResult
        store = SQLiteSandboxV2Store(config=Settings())
        hc = SandboxV2HealthCheckResult(component="test", status="healthy", ready=True)
        store.create_health_check_result(hc); results = store.list_health_check_results(component="test")
        assert len(results) >= 1
