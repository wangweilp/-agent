#!/usr/bin/env python
"""Sandbox v2 Load Test Smoke Script — Step 19.

Default: local dry-run only. No external network.
Use --staging to request staging load test (requires env).

Usage:
    python scripts/run_sandbox_v2_load_test_smoke.py --dry-run --json
    python scripts/run_sandbox_v2_load_test_smoke.py --staging --json
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _env_bool(n: str, d: bool = False) -> bool:
    v = os.getenv(n, "").strip().lower()
    return v in ("true", "1", "yes") if v else d


def run(dry_run: bool = True, staging: bool = False, profile: str = "smoke",
        output_dir: str = ".sandbox_v2_load_reports") -> dict:
    from src.open_platform.sandbox_v2.load_testing import SandboxV2LoadTester
    from src.open_platform.sandbox_v2.config import load_sandbox_v2_settings
    from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
    from src.adapters.config import Settings

    settings = load_sandbox_v2_settings()
    store = SQLiteSandboxV2Store(Settings(), db_path=":memory:")
    tester = SandboxV2LoadTester(store=store, settings=settings)

    targets = settings.load_test_targets or ["readiness", "metrics", "network_preflight"]
    config = tester.create_load_test_config(
        profile=profile, targets=targets,
        max_users=min(settings.load_test_max_users, 5),
        max_rps=min(settings.load_test_max_rps, 5),
        duration_seconds=min(settings.load_test_duration_seconds, 30),
        timeout_seconds=settings.load_test_timeout_seconds,
        allow_production=settings.load_test_allow_production,
        require_confirmation=settings.load_test_require_confirmation,
    )

    if staging:
        if not settings.run_staging_load_test or not settings.staging_base_url:
            return {"status": "skipped", "reason": "Staging load test not enabled. Set SANDBOX_V2_RUN_STAGING_LOAD_TEST=true and SANDBOX_V2_STAGING_BASE_URL."}
        result = tester.run_staging_load_test(
            config, base_url=settings.staging_base_url, token=settings.staging_api_token,
        )
        result["mode"] = "staging"
    else:
        result = tester.run_local_dry_run(config)
        result["mode"] = "local_dry_run"

    # Write report
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, f"load_test_{config.load_test_id}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)

    result["report_path"] = report_path
    return result


def main():
    p = argparse.ArgumentParser(description="Sandbox v2 Load Test Smoke")
    p.add_argument("--dry-run", action="store_true", default=True, help="Local dry-run (default)")
    p.add_argument("--staging", action="store_true", help="Staging load test (requires env)")
    p.add_argument("--profile", default="smoke", choices=["smoke", "staging_small", "custom"])
    p.add_argument("--json", action="store_true", default=True, help="JSON output")
    p.add_argument("--output-dir", default=".sandbox_v2_load_reports")
    args = p.parse_args()

    dry = not args.staging
    result = run(dry_run=dry, staging=args.staging, profile=args.profile,
                 output_dir=args.output_dir)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    if result.get("status") == "skipped":
        print("\n[Skipped] Staging load test not enabled. Default is safe.")
    elif result.get("summary", {}).get("failure_count", 0) == 0:
        print("\n[OK] All targets completed.")
    else:
        print("\n[WARN] Some targets had failures.")


if __name__ == "__main__":
    main()
