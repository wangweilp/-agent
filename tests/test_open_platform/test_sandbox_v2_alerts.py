"""Alert Engine tests (Step 15)."""
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.alerts import SandboxV2AlertEngine, _DEFAULT_RULES
from src.open_platform.sandbox_v2.models import SandboxV2AlertRule, SandboxV2AlertSeverityStep15

class TestAlertRules:
    def test_default_rules_exist(self):
        assert len(_DEFAULT_RULES) >= 5
    def test_rules_have_severity(self):
        for r in _DEFAULT_RULES:
            assert r.get("severity") in ("info","warning","high","critical")
    def test_dead_letter_rule_exists(self):
        names = [r["name"] for r in _DEFAULT_RULES]
        assert "queue-dead-letter" in names
    def test_audit_chain_rule_exists(self):
        names = [r["name"] for r in _DEFAULT_RULES]
        assert "audit-chain-failure" in names
    def test_cross_tenant_rule_exists(self):
        names = [r["name"] for r in _DEFAULT_RULES]
        assert "cross-tenant-denied" in names

class TestAlertEvaluation:
    def test_dead_letter_triggers_alert(self):
        rule = SandboxV2AlertRule(name="test-dl", metric_name="queue_dead_letter_total", threshold=0, comparison="gt", severity=SandboxV2AlertSeverityStep15.HIGH)
        engine = SandboxV2AlertEngine()
        alert = engine.evaluate_rule(rule, {"queue_dead_letter_total": 5})
        assert alert is not None; assert alert.severity == SandboxV2AlertSeverityStep15.HIGH
    def test_audit_chain_fail_triggers_critical(self):
        rule = SandboxV2AlertRule(name="test-ac", metric_name="audit_chain_verify_failures_total", threshold=0, comparison="gt", severity=SandboxV2AlertSeverityStep15.CRITICAL)
        engine = SandboxV2AlertEngine()
        alert = engine.evaluate_rule(rule, {"audit_chain_verify_failures_total": 1})
        assert alert is not None; assert alert.severity == SandboxV2AlertSeverityStep15.CRITICAL
    def test_cross_tenant_triggers_high(self):
        rule = SandboxV2AlertRule(name="test-ct", metric_name="cross_tenant_denied_total", threshold=0, comparison="gt", severity=SandboxV2AlertSeverityStep15.HIGH)
        engine = SandboxV2AlertEngine()
        alert = engine.evaluate_rule(rule, {"cross_tenant_denied_total": 1})
        assert alert is not None; assert alert.severity == SandboxV2AlertSeverityStep15.HIGH
    def test_below_threshold_no_alert(self):
        rule = SandboxV2AlertRule(name="test-ok", metric_name="queue_depth", threshold=100, comparison="gt", severity=SandboxV2AlertSeverityStep15.WARNING)
        engine = SandboxV2AlertEngine()
        alert = engine.evaluate_rule(rule, {"queue_depth": 5})
        assert alert is None

class TestAlertManagement:
    def test_acknowledge_persisted(self):
        from src.adapters.config import Settings; from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        from src.open_platform.sandbox_v2.models import SandboxV2Alert
        store = SQLiteSandboxV2Store(config=Settings())
        alert = SandboxV2Alert(name="test-ack", reason="test"); store.create_alert(alert)
        engine = SandboxV2AlertEngine(store=store); engine.acknowledge_alert(alert.alert_id, "tester")
        fetched = store.get_alert(alert.alert_id); assert fetched["status"] == "acknowledged"
    def test_resolve_persisted(self):
        from src.adapters.config import Settings; from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        from src.open_platform.sandbox_v2.models import SandboxV2Alert
        store = SQLiteSandboxV2Store(config=Settings())
        alert = SandboxV2Alert(name="test-resolve", reason="test"); store.create_alert(alert)
        engine = SandboxV2AlertEngine(store=store); engine.resolve_alert(alert.alert_id, "tester")
        fetched = store.get_alert(alert.alert_id); assert fetched["status"] == "resolved"
    def test_evaluate_all(self):
        from src.adapters.config import Settings; from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        store = SQLiteSandboxV2Store(config=Settings()); engine = SandboxV2AlertEngine(store=store)
        alerts = engine.evaluate_all({"queue_dead_letter_total": 10, "queue_depth": 5})
        assert len(alerts) >= 1

class TestAlertReadiness:
    def test_readiness(self):
        engine = SandboxV2AlertEngine(); r = engine.get_alert_readiness()
        assert r["alert_engine"] is True; assert r["external_notifications"] is False; assert r["monitoring_safe_mode"] is True
