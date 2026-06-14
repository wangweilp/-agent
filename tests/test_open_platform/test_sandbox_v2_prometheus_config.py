"""Prometheus Config tests (Step 18)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.prometheus import SandboxV2PrometheusConfigBuilder


class TestPrometheusConfig:
    def test_scrape_config(self):
        b = SandboxV2PrometheusConfigBuilder()
        cfg = b.build_scrape_config()
        assert "scrape_configs" in cfg
        sc = cfg["scrape_configs"][0]
        assert sc["job_name"] == "sandbox-v2"

    def test_alert_rules(self):
        b = SandboxV2PrometheusConfigBuilder()
        rules = b.build_alerting_rules()
        assert "groups" in rules
        group = rules["groups"][0]
        assert group["name"] == "sandbox-v2-alerts"
        rule_names = [r["alert"] for r in group["rules"]]
        assert "SandboxV2AuditChainFailure" in rule_names
        assert "SandboxV2CrossTenantDenied" in rule_names

    def test_yaml_export(self):
        b = SandboxV2PrometheusConfigBuilder()
        yaml_str = b.export_scrape_yaml()
        assert "sandbox-v2" in yaml_str
        assert "scrape_configs" in yaml_str or "job_name" in yaml_str

    def test_alert_rules_yaml(self):
        b = SandboxV2PrometheusConfigBuilder()
        yaml_str = b.export_alert_rules_yaml()
        assert "SandboxV2" in yaml_str or "groups" in yaml_str

    def test_no_secret(self):
        b = SandboxV2PrometheusConfigBuilder()
        yaml_str = b.export_scrape_yaml()
        assert "secret" not in yaml_str.lower() or "redacted" in yaml_str.lower()

    def test_no_absolute_path(self):
        b = SandboxV2PrometheusConfigBuilder()
        yaml_str = b.export_scrape_yaml() + b.export_alert_rules_yaml()
        assert "C:\\" not in yaml_str
        assert "/home/" not in yaml_str

    def test_custom_job_name(self):
        b = SandboxV2PrometheusConfigBuilder(job_name="my-sandbox")
        cfg = b.build_scrape_config()
        assert cfg["scrape_configs"][0]["job_name"] == "my-sandbox"

    def test_covers_all_default_alerts(self):
        b = SandboxV2PrometheusConfigBuilder()
        rules = b.build_alerting_rules()
        group = rules["groups"][0]
        alerts = [r["alert"] for r in group["rules"]]
        expected = [
            "SandboxV2AuditChainFailure", "SandboxV2DeadLetter",
            "SandboxV2CrossTenantDenied", "SandboxV2MetadataServiceBlocked",
            "SandboxV2WorkerNoHeartbeat", "SandboxV2BackendBlocker",
            "SandboxV2RedTeamFailed", "SandboxV2QueueDepthHigh",
            "SandboxV2NetworkDeniedSpike",
        ]
        for a in expected:
            assert a in alerts, f"Missing alert: {a}"
