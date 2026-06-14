"""Sandbox v2 performance benchmark tests (Step 16)."""
import os
import tempfile

import pytest

from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.open_platform.sandbox_v2.config import SandboxV2Settings
from src.open_platform.sandbox_v2.network import SandboxNetworkEgressService
from src.open_platform.sandbox_v2.performance import SandboxV2PerformanceBenchmark
from src.open_platform.sandbox_v2.service import SandboxV2Service


@pytest.fixture
def perf_stack():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
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
        settings=SandboxV2Settings(),
    )
    yield runner, store
    try:
        os.unlink(db_path)
    except OSError:
        pass


class TestPerformanceConfig:
    def test_perf_tests_default_disabled(self):
        settings = SandboxV2Settings()
        assert settings.perf_tests_enabled is False
        assert settings.run_performance_benchmarks is False

    def test_smoke_config_can_be_created(self, perf_stack):
        runner, store = perf_stack
        cfg = runner.create_benchmark_config(profile="smoke", targets=["jobs"], max_jobs=3)
        assert cfg.profile == "smoke"
        assert cfg.metadata["synthetic_fixture_only"] is True
        assert store.get_benchmark_config(cfg.benchmark_id) is not None

    def test_large_profile_default_rejected(self, perf_stack):
        runner, _ = perf_stack
        with pytest.raises(ValueError):
            runner.create_benchmark_config(profile="large", targets=["jobs"])

    def test_max_jobs_over_limit_rejected(self, perf_stack):
        runner, _ = perf_stack
        with pytest.raises(ValueError):
            runner.create_benchmark_config(profile="small", targets=["jobs"], max_jobs=101)

    def test_max_concurrency_over_limit_rejected(self, perf_stack):
        runner, _ = perf_stack
        with pytest.raises(ValueError):
            runner.create_benchmark_config(profile="small", targets=["jobs"], max_concurrency=5)

    def test_user_command_metadata_rejected(self, perf_stack):
        runner, _ = perf_stack
        with pytest.raises(ValueError):
            runner.create_benchmark_config(profile="smoke", targets=["jobs"], metadata={"command": "whoami"})


class TestBenchmarkSafety:
    def test_benchmark_uses_synthetic_fixture(self, perf_stack):
        runner, _ = perf_stack
        cfg = runner.create_benchmark_config(profile="smoke", targets=["jobs"], max_jobs=2)
        result = runner.run_jobs_benchmark(cfg)
        assert result.metadata["synthetic_fixture_only"] is True
        assert result.metadata["no_user_code"] is True

    def test_network_benchmark_preflight_only(self, perf_stack):
        runner, _ = perf_stack
        cfg = runner.create_benchmark_config(profile="smoke", targets=["network"], max_jobs=2)
        result = runner.run_network_preflight_benchmark(cfg)
        assert result.status == "completed"
        assert any("preflight only" in w for w in result.warnings)

    def test_package_benchmark_does_not_download_package(self, perf_stack):
        runner, store = perf_stack
        cfg = runner.create_benchmark_config(profile="smoke", targets=["packages"], max_jobs=2)
        result = runner.run_package_benchmark(cfg)
        assert result.status == "completed"
        requests = store.list_package_requests(limit=10)
        assert requests
        assert all(r.source_url.startswith("offline://") for r in requests)

    def test_kill_benchmark_does_not_kill_system_process(self, perf_stack):
        runner, _ = perf_stack
        cfg = runner.create_benchmark_config(profile="smoke", targets=["kill_switch"], max_jobs=1)
        result = runner.run_kill_switch_benchmark(cfg)
        assert result.status == "completed"
        assert any("no PID" in w for w in result.warnings)


class TestLatencyStats:
    def test_latency_stats_p50_p95_p99(self, perf_stack):
        runner, _ = perf_stack
        stats = runner.compute_latency_stats([1, 2, 3, 4, 5, 100])
        assert stats["p50_ms"] == 3
        assert stats["p95_ms"] == 100
        assert stats["p99_ms"] == 100

    def test_ops_per_second_calculated(self, perf_stack):
        runner, _ = perf_stack
        cfg = runner.create_benchmark_config(profile="smoke", targets=["jobs"], max_jobs=2)
        result = runner.run_jobs_benchmark(cfg)
        assert result.total_operations == 2
        assert result.ops_per_second > 0

    def test_sqlite_persists_benchmark_result(self, perf_stack):
        runner, store = perf_stack
        cfg = runner.create_benchmark_config(profile="smoke", targets=["jobs"], max_jobs=1)
        result = runner.run_jobs_benchmark(cfg)
        store.create_benchmark_result(result)
        rows = store.list_benchmark_results(benchmark_id=cfg.benchmark_id)
        assert len(rows) == 1
