#!/usr/bin/env python
"""Run a safe Sandbox v2 performance smoke benchmark.

Default behavior is skipped unless SANDBOX_V2_PERF_TESTS_ENABLED=true.
Use --force-smoke for a tiny synthetic self-check. This script never runs user
code, never opens network sockets, and never starts containers or MicroVMs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from statistics import median

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def run_performance_smoke(force_smoke: bool = False) -> dict:
    from src.open_platform.sandbox_v2.config import load_sandbox_v2_settings

    settings = load_sandbox_v2_settings()
    if not settings.perf_tests_enabled and not force_smoke:
        return {
            "benchmark_id": "",
            "profile": "smoke",
            "targets": ["jobs", "queue", "metrics", "alerts"],
            "status": "skipped",
            "total_operations": 0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "ops_per_second": 0.0,
            "capacity_estimate": None,
            "warnings": ["SANDBOX_V2_PERF_TESTS_ENABLED is false; smoke benchmark skipped."],
            "blockers": [],
            "synthetic_fixture_only": True,
            "external_network": False,
            "container_execution": False,
            "microvm_execution": False,
            "user_code_execution": False,
        }

    if settings.perf_profile not in {"smoke", "small"} and not force_smoke:
        return {
            "benchmark_id": "",
            "profile": settings.perf_profile,
            "targets": [],
            "status": "skipped",
            "total_operations": 0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "ops_per_second": 0.0,
            "capacity_estimate": None,
            "warnings": ["Smoke script only allows smoke/small profiles."],
            "blockers": [],
        }

    from src.adapters.config import Settings
    from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
    from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
    from src.open_platform.sandbox_v2.network import SandboxNetworkEgressService
    from src.open_platform.sandbox_v2.performance import SandboxV2PerformanceBenchmark
    from src.open_platform.sandbox_v2.service import SandboxV2Service

    fd, db_path = tempfile.mkstemp(prefix="sandbox_v2_perf_smoke_", suffix=".db")
    os.close(fd)
    try:
        app_settings = Settings()
        store = SQLiteSandboxV2Store(app_settings, db_path=db_path)
        queue = SQLiteSandboxV2Queue(app_settings, db_path=db_path)
        network = SandboxNetworkEgressService(store=store)
        service = SandboxV2Service(store=store, queue=queue, network_service=network)
        runner = SandboxV2PerformanceBenchmark(
            store=store,
            queue=queue,
            service=service,
            network_service=network,
            settings=settings,
        )
        config = runner.create_benchmark_config(
            profile="smoke" if force_smoke else settings.perf_profile,
            targets=["jobs", "queue", "metrics", "alerts"],
            max_jobs=3 if force_smoke else min(settings.perf_max_jobs, 3),
            max_queue_items=3 if force_smoke else min(settings.perf_max_queue_items, 3),
            max_artifacts=2,
            max_concurrency=1,
            timeout_seconds=10,
            cleanup_after_run=True,
            metadata={"script": "run_sandbox_v2_performance_smoke"},
        )
        result = runner.run_all(config)
        results = result.get("results", [])
        lat50 = [float(r.get("p50_ms", 0.0)) for r in results]
        lat95 = [float(r.get("p95_ms", 0.0)) for r in results]
        lat99 = [float(r.get("p99_ms", 0.0)) for r in results]
        summary = {
            "benchmark_id": config.benchmark_id,
            "profile": config.profile,
            "targets": config.targets,
            "status": "completed",
            "total_operations": sum(int(r.get("total_operations", 0)) for r in results),
            "p50_ms": round(median(lat50), 3) if lat50 else 0.0,
            "p95_ms": round(max(lat95), 3) if lat95 else 0.0,
            "p99_ms": round(max(lat99), 3) if lat99 else 0.0,
            "ops_per_second": round(sum(float(r.get("ops_per_second", 0.0)) for r in results), 3),
            "capacity_estimate": result.get("capacity_estimate"),
            "warnings": result.get("warnings", []),
            "blockers": result.get("blockers", []),
            "synthetic_fixture_only": True,
            "external_network": False,
            "container_execution": False,
            "microvm_execution": False,
            "user_code_execution": False,
        }
        _write_reports(settings.perf_output_dir, runner, config)
        return summary
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


def _write_reports(output_dir: str, runner, config) -> None:
    safe_dir = Path(output_dir or ".sandbox_v2_perf_reports")
    if safe_dir.is_absolute():
        safe_dir = Path(".sandbox_v2_perf_reports")
    safe_dir.mkdir(parents=True, exist_ok=True)
    json_report = runner.export_report_json(config)
    md_report = runner.export_report_markdown(config)
    (safe_dir / f"{config.benchmark_id}.json").write_text(
        json.dumps(json_report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (safe_dir / f"{config.benchmark_id}.md").write_text(md_report, encoding="utf-8")


def render_markdown(summary: dict) -> str:
    cap = summary.get("capacity_estimate") or {}
    lines = [
        "# Sandbox v2 Performance Smoke",
        "",
        f"- Status: `{summary.get('status', 'unknown')}`",
        f"- Profile: `{summary.get('profile', 'smoke')}`",
        f"- Benchmark ID: `{summary.get('benchmark_id', '')}`",
        f"- Total operations: {summary.get('total_operations', 0)}",
        f"- p50/p95/p99 ms: {summary.get('p50_ms', 0)} / {summary.get('p95_ms', 0)} / {summary.get('p99_ms', 0)}",
        f"- ops/s: {summary.get('ops_per_second', 0)}",
        "- Safety: synthetic fixture only; no user code, external network, containers, or MicroVMs",
    ]
    if cap:
        lines.extend([
            "",
            "## Capacity Estimate",
            f"- Jobs/min: {cap.get('estimated_jobs_per_minute', 0)}",
            f"- Queue/min: {cap.get('estimated_queue_items_per_minute', 0)}",
            f"- Artifact metadata/min: {cap.get('estimated_artifact_metadata_per_minute', 0)}",
            f"- Network preflight/min: {cap.get('estimated_network_preflight_per_minute', 0)}",
        ])
    if summary.get("warnings"):
        lines.extend(["", "## Warnings", *[f"- {w}" for w in summary["warnings"]]])
    if summary.get("blockers"):
        lines.extend(["", "## Blockers", *[f"- {b}" for b in summary["blockers"]]])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-smoke", action="store_true", help="Run a tiny smoke profile even when env is disabled.")
    parser.add_argument("--json", action="store_true", help="Print JSON only.")
    args = parser.parse_args()

    summary = run_performance_smoke(force_smoke=args.force_smoke)
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print("\n--- markdown summary ---")
        print(render_markdown(summary))
    return 1 if summary.get("blockers") else 0


if __name__ == "__main__":
    raise SystemExit(main())
