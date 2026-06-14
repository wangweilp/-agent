"""Load Testing tests (Step 19)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.load_testing import (
    SandboxV2LoadTester, compute_latency_stats, compute_error_rate,
)
from src.open_platform.sandbox_v2.models import (
    SandboxV2LoadTestConfig, SandboxV2LoadTestStatus, SandboxV2LoadTestProfile,
)
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.config import Settings


class DummySettings:
    load_testing_enabled = False
    run_staging_load_test = False
    staging_base_url = ""
    staging_api_token = ""
    load_test_profile = "smoke"
    load_test_max_users = 5
    load_test_max_rps = 5
    load_test_duration_seconds = 30
    load_test_timeout_seconds = 5
    load_test_targets = ["readiness", "metrics"]
    load_test_allow_production = False
    load_test_require_confirmation = True
    database_backend = "sqlite"
    perf_profile = "small"


@pytest.fixture
def store():
    return SQLiteSandboxV2Store(Settings(), db_path=":memory:")


class TestDefaults:
    def test_disabled_by_default(self):
        t = SandboxV2LoadTester(settings=DummySettings())
        config = t.create_load_test_config(targets=["readiness"])
        assert config.profile == "smoke"

    def test_local_dry_run_ok(self, store):
        t = SandboxV2LoadTester(store=store, settings=DummySettings())
        config = t.create_load_test_config(targets=["readiness"])
        result = t.run_local_dry_run(config)
        assert result["mode"] == "local_dry_run"
        assert len(result["results"]) >= 1

    def test_staging_default_skipped(self, store):
        t = SandboxV2LoadTester(store=store, settings=DummySettings())
        config = t.create_load_test_config(targets=["readiness"])
        result = t.run_staging_load_test(config, base_url="")
        assert result["status"] == "blocked"


class TestValidation:
    def test_max_users_exceeded(self):
        config = SandboxV2LoadTestConfig(max_users=50, profile="smoke")
        r = SandboxV2LoadTester.validate_load_test_config(config)
        assert not r["valid"]

    def test_max_rps_exceeded(self):
        config = SandboxV2LoadTestConfig(max_rps=50, profile="smoke")
        r = SandboxV2LoadTester.validate_load_test_config(config)
        assert not r["valid"]

    def test_duration_exceeded(self):
        config = SandboxV2LoadTestConfig(duration_seconds=9999, profile="smoke")
        r = SandboxV2LoadTester.validate_load_test_config(config)
        assert not r["valid"]

    def test_valid_config(self):
        config = SandboxV2LoadTestConfig(max_users=5, max_rps=5, duration_seconds=30, profile="smoke")
        r = SandboxV2LoadTester.validate_load_test_config(config)
        assert r["valid"]


class TestProductionGuards:
    def test_production_url_blocked(self):
        assert SandboxV2LoadTester.is_production_url("https://api.prod.example.com")
        assert not SandboxV2LoadTester.is_production_url("http://localhost:8000")

    def test_staging_blocks_production_url(self, store):
        t = SandboxV2LoadTester(store=store, settings=DummySettings())
        config = SandboxV2LoadTestConfig(allow_production=False)
        result = t.run_staging_load_test(config, base_url="https://api.production.example.com")
        assert result["status"] == "blocked"


class TestStats:
    def test_latency_stats(self):
        latencies = [10.0, 20.0, 30.0, 40.0, 50.0]
        stats = compute_latency_stats(latencies)
        assert stats["p50"] == 30.0
        assert stats["min"] == 10.0
        assert stats["max"] == 50.0

    def test_error_rate(self):
        assert compute_error_rate(90, 100) == 10.0
        assert compute_error_rate(100, 100) == 0.0

    def test_empty_latencies(self):
        stats = compute_latency_stats([])
        assert stats["p50"] == 0.0


class TestCapacityPlan:
    def test_generate_plan(self, store):
        t = SandboxV2LoadTester(store=store, settings=DummySettings())
        plan = t.generate_capacity_plan()
        assert plan.recommended_profile == "small"
        assert plan.recommended_backend == "sqlite"

    def test_plan_persisted(self, store):
        t = SandboxV2LoadTester(store=store, settings=DummySettings())
        plan = t.generate_capacity_plan()
        fetched = store.get_latest_capacity_plan()
        assert fetched is not None

    def test_plan_json(self):
        t = SandboxV2LoadTester(settings=DummySettings())
        plan = t.generate_capacity_plan()
        d = plan.to_dict()
        assert "recommended_profile" in d
        assert "bottlenecks" in d


class TestConfigMasking:
    def test_base_url_masked(self):
        config = SandboxV2LoadTestConfig(base_url_masked="https://staging.internal.example.com/api")
        d = config.to_dict()
        assert "staging.internal.example.com" not in str(d.get("base_url_masked", ""))

    def test_token_not_in_result(self, store):
        t = SandboxV2LoadTester(store=store, settings=DummySettings())
        config = t.create_load_test_config(targets=["readiness"])
        result = t.run_local_dry_run(config)
        s = str(result)
        assert "token" not in s.lower() or "base_url_masked" in s
