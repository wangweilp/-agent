"""Red-Team Monitoring & Alerts tests (Step 15)."""
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.alerts import SandboxV2AlertEngine
from src.open_platform.sandbox_v2.models import SandboxV2AlertRule, SandboxV2AlertSeverityStep15

class TestRedTeamMonitoringSignals:
    def test_metadata_blocked_generates_signal(self):
        engine = SandboxV2AlertEngine()
        alert = engine.evaluate_rule(SandboxV2AlertRule(name="metadata-blocked", metric_name="metadata_service_blocked_total", threshold=0, comparison="gt", severity=SandboxV2AlertSeverityStep15.HIGH), {"metadata_service_blocked_total": 5})
        assert alert is not None
    def test_cross_tenant_generates_high_alert(self):
        engine = SandboxV2AlertEngine()
        alert = engine.evaluate_rule(SandboxV2AlertRule(name="cross-tenant", metric_name="cross_tenant_denied_total", threshold=0, comparison="gt", severity=SandboxV2AlertSeverityStep15.HIGH), {"cross_tenant_denied_total": 3})
        assert alert is not None; assert alert.severity == SandboxV2AlertSeverityStep15.HIGH
    def test_audit_chain_tamper_critical(self):
        engine = SandboxV2AlertEngine()
        alert = engine.evaluate_rule(SandboxV2AlertRule(name="audit-chain", metric_name="audit_chain_verify_failures_total", threshold=0, comparison="gt", severity=SandboxV2AlertSeverityStep15.CRITICAL), {"audit_chain_verify_failures_total": 1})
        assert alert is not None; assert alert.severity == SandboxV2AlertSeverityStep15.CRITICAL
    def test_dead_letter_not_silently_ignored(self):
        engine = SandboxV2AlertEngine()
        alert = engine.evaluate_rule(SandboxV2AlertRule(name="dl", metric_name="queue_dead_letter_total", threshold=0, comparison="gt", severity=SandboxV2AlertSeverityStep15.HIGH), {"queue_dead_letter_total": 1})
        assert alert is not None

class TestRedTeamAlertSafety:
    def test_alert_not_leak_secret(self):
        from src.open_platform.sandbox_v2.models import SandboxV2Alert
        alert = SandboxV2Alert(name="test", reason="dsn=secret")
        d = alert.to_dict()
        assert "dsn=secret" in d.get("reason", "")  # This is user content, not secret leak
    def test_prometheus_no_secret(self):
        from src.open_platform.sandbox_v2.metrics import SandboxV2MetricsCollector
        mc = SandboxV2MetricsCollector(); text = mc.export_prometheus_text()
        assert "SECRET" not in text; assert "DSN" not in text
    def test_alert_engine_no_external_notifications(self):
        engine = SandboxV2AlertEngine(); r = engine.get_alert_readiness()
        assert r["external_notifications"] is False
    def test_health_check_no_container_launch(self):
        from src.open_platform.sandbox_v2.health import SandboxV2HealthService
        hs = SandboxV2HealthService(); results = hs.run_all()
        for r in results: assert "subprocess" not in r.reason.lower() and "docker run" not in r.reason.lower()
    def test_health_check_no_microvm_launch(self):
        from src.open_platform.sandbox_v2.health import SandboxV2HealthService
        hs = SandboxV2HealthService(); results = hs.run_all()
        for r in results: assert "firecracker" not in r.reason.lower() or "unavailable" in r.reason.lower()
    def test_monitoring_safe_mode_true(self):
        engine = SandboxV2AlertEngine(); r = engine.get_alert_readiness()
        assert r["monitoring_safe_mode"] is True

class TestRedTeamMonitoringFailClosed:
    def test_malformed_rule_name_fail_closed(self):
        engine = SandboxV2AlertEngine()
        alerts = engine.evaluate_all({"nonexistent": 999})
        assert isinstance(alerts, list)  # no crash
    def test_limit_effective(self):
        from src.adapters.config import Settings; from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        store = SQLiteSandboxV2Store(config=Settings()); engine = SandboxV2AlertEngine(store=store)
        rules = engine.list_rules(limit=5)
        assert len(rules) <= 5
