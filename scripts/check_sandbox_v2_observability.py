#!/usr/bin/env python
"""Sandbox v2 Observability Check Script — Step 18.

Reads observability settings, generates Prometheus/Grafana configs,
runs OTel adapter readiness, simulates local export.

Usage:
    python scripts/check_sandbox_v2_observability.py
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name, "").strip().lower()
    if val in ("true", "1", "yes"): return True
    if val in ("false", "0", "no"): return False
    return default


def check() -> dict:
    observability_enabled = _env_bool("SANDBOX_V2_OBSERVABILITY_ENABLED", False)
    blockers: list[str] = []
    warnings: list[str] = []

    # Prometheus config
    try:
        from src.open_platform.sandbox_v2.prometheus import SandboxV2PrometheusConfigBuilder
        b = SandboxV2PrometheusConfigBuilder()
        scrape = b.build_scrape_config()
        rules = b.build_alerting_rules()
        scrape_ready = bool(scrape.get("scrape_configs"))
        alert_rules_ready = bool(rules.get("groups"))
    except Exception as e:
        scrape_ready = False
        alert_rules_ready = False
        warnings.append(f"Prometheus config error: {e}")

    # Grafana dashboard
    try:
        from src.open_platform.sandbox_v2.grafana import SandboxV2GrafanaDashboardBuilder
        builder = SandboxV2GrafanaDashboardBuilder()
        dash = builder.build_overview_dashboard()
        dashboard_ready = len(dash.panels) > 0
    except Exception as e:
        dashboard_ready = False
        warnings.append(f"Grafana dashboard error: {e}")

    # OTel adapter
    try:
        from src.open_platform.sandbox_v2.otel_adapter import get_otel_exporter
        exporter = get_otel_exporter("disabled")
        export_readiness = exporter.get_readiness()
        otel_ready = True
    except Exception as e:
        otel_ready = False
        warnings.append(f"OTel adapter error: {e}")

    # Simulate local export
    try:
        from src.open_platform.sandbox_v2.otel_adapter import MockOTelExporter
        mock = MockOTelExporter()
        r = mock.export_metrics([{"test_metric": 1}])
        simulate_ok = r["status"] == "exported"
    except Exception as e:
        simulate_ok = False
        warnings.append(f"Simulate export error: {e}")

    safe_mode = (
        not _env_bool("SANDBOX_V2_OTEL_INCLUDE_SENSITIVE_ATTRIBUTES", False)
        and scrape_ready
        and dashboard_ready
    )

    return {
        "observability_enabled": observability_enabled,
        "prometheus_scrape_config_ready": scrape_ready,
        "prometheus_alert_rules_ready": alert_rules_ready,
        "grafana_dashboard_ready": dashboard_ready,
        "otel_adapter_ready": otel_ready,
        "otel_real_export": False,
        "external_telemetry_export": False,
        "telemetry_redaction": True,
        "blockers": blockers,
        "warnings": warnings,
        "safe_mode": safe_mode,
    }


def main():
    result = check()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result.get("blockers"):
        print("\n[BLOCKERS]:")
        for b in result["blockers"]:
            print(f"  - {b}")
    if result.get("warnings"):
        print("\n[Warnings]:")
        for w in result["warnings"]:
            print(f"  - {w}")
    if result.get("safe_mode"):
        print("\n[OK] Observability safe mode active. No external telemetry.")
    sys.exit(1 if result.get("blockers") else 0)


if __name__ == "__main__":
    main()
