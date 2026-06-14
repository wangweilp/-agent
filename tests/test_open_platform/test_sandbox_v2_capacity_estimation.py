"""Sandbox v2 capacity estimation tests (Step 16)."""
import os
import tempfile
from pathlib import Path

from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.open_platform.sandbox_v2.models import SandboxV2BenchmarkResult
from src.open_platform.sandbox_v2.performance import SandboxV2PerformanceBenchmark


def test_capacity_estimate_generated():
    runner = SandboxV2PerformanceBenchmark(store=None)
    results = [
        SandboxV2BenchmarkResult(target="jobs", status="completed", ops_per_second=10.0),
        SandboxV2BenchmarkResult(target="queue", status="completed", ops_per_second=5.0),
        SandboxV2BenchmarkResult(target="artifacts", status="completed", ops_per_second=2.0),
        SandboxV2BenchmarkResult(target="network", status="completed", ops_per_second=20.0),
    ]
    estimate = runner.estimate_capacity("smoke", results)
    assert estimate.estimated_jobs_per_minute == 600.0
    assert estimate.estimated_queue_items_per_minute == 300.0
    assert estimate.estimated_artifact_metadata_per_minute == 120.0
    assert estimate.estimated_network_preflight_per_minute == 1200.0
    assert estimate.recommendations


def test_capacity_estimate_persisted_in_sqlite():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        store = SQLiteSandboxV2Store(Settings(), db_path=db_path)
        runner = SandboxV2PerformanceBenchmark(store=store)
        estimate = runner.estimate_capacity("smoke", [
            SandboxV2BenchmarkResult(target="jobs", status="completed", ops_per_second=1.0),
        ])
        store.create_capacity_estimate(estimate)
        latest = store.get_latest_capacity_estimate()
        assert latest is not None
        assert latest.capacity_id == estimate.capacity_id
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_postgres_schema_contains_performance_tables():
    schema = Path("docs/sql/sandbox_v2_postgres_schema.sql").read_text(encoding="utf-8")
    assert "sandbox_v2_benchmark_configs" in schema
    assert "sandbox_v2_benchmark_results" in schema
    assert "sandbox_v2_capacity_estimates" in schema
