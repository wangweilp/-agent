#!/usr/bin/env python
"""Sandbox v2 Monitoring Check Script — Step 15.

Collect metrics, run health checks, evaluate alerts.
No external notifications. No secrets leaked. Safe mode only.
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def main() -> int:
    try:
        from src.adapters.config import Settings; from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        store = SQLiteSandboxV2Store(config=Settings())
    except Exception as e:
        print(json.dumps({"error": str(e)})); return 1

    from src.open_platform.sandbox_v2.metrics import SandboxV2MetricsCollector
    from src.open_platform.sandbox_v2.health import SandboxV2HealthService
    from src.open_platform.sandbox_v2.alerts import SandboxV2AlertEngine

    # Metrics
    mc = SandboxV2MetricsCollector(store=store)
    data = mc.collect_all()
    snap = mc.create_snapshot()

    # Health
    hs = SandboxV2HealthService(store=store)
    hresults = hs.run_all()
    healthy = all(r.ready for r in hresults)

    # Alerts
    engine = SandboxV2AlertEngine(store=store)
    alerts = engine.evaluate_all(data.get("gauges", {}))
    critical = len([a for a in alerts if getattr(a, 'severity', '') == 'critical'])

    result = {
        "metrics_collected": len(data.get("samples", [])),
        "health_checks_passed": sum(1 for r in hresults if r.ready),
        "health_checks_total": len(hresults),
        "alerts_open": len(alerts),
        "critical_alerts": critical,
        "warnings": [],
        "blockers": [] if healthy else ["Health checks not all passing"],
        "safe_mode": True,
        "external_notifications": False,
    }

    if not healthy:
        result["warnings"].append("Some health checks not ready")

    if "--json" in sys.argv:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("=" * 60)
        print("  Sandbox v2 Monitoring Check")
        print("=" * 60)
        print(f"  Metrics collected: {result['metrics_collected']}")
        print(f"  Health checks: {result['health_checks_passed']}/{result['health_checks_total']} passed")
        print(f"  Alerts open: {result['alerts_open']}  Critical: {result['critical_alerts']}")
        print(f"  Safe mode: {result['safe_mode']}")
        print(f"  External notifications: {result['external_notifications']}")
        if result["blockers"]: print(f"  [BLOCKERS] {result['blockers']}")
        if result["warnings"]: print(f"  [WARN] {result['warnings']}")
        print("=" * 60)

    return 1 if result["blockers"] else 0

if __name__ == "__main__":
    sys.exit(main())
