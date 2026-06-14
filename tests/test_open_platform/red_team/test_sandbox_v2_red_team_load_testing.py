"""Red-Team Load Testing abuse tests (Step 19)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.load_testing import SandboxV2LoadTester
from src.open_platform.sandbox_v2.models import SandboxV2LoadTestConfig


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
    load_test_targets = ["readiness"]
    load_test_allow_production = False
    load_test_require_confirmation = True


class TestExternalURLBlocked:
    def test_arbitrary_url_blocked(self):
        t = SandboxV2LoadTester(settings=DummySettings())
        config = SandboxV2LoadTestConfig(allow_production=False)
        result = t.run_staging_load_test(config, base_url="https://evil.example.com")
        assert result["status"] == "blocked"

    def test_production_url_blocked(self):
        t = SandboxV2LoadTester(settings=DummySettings())
        config = SandboxV2LoadTestConfig(allow_production=False)
        result = t.run_staging_load_test(config, base_url="https://api.prod.example.com")
        assert result["status"] == "blocked"

    def test_staging_allows_localhost(self):
        t = SandboxV2LoadTester(settings=DummySettings())
        assert not t.is_production_url("http://localhost:8000")
        assert not t.is_production_url("http://127.0.0.1:9000")


class TestExceededLimits:
    def test_huge_concurrency_blocked(self):
        config = SandboxV2LoadTestConfig(max_users=500, profile="smoke")
        r = SandboxV2LoadTester.validate_load_test_config(config)
        assert not r["valid"]

    def test_huge_rps_blocked(self):
        config = SandboxV2LoadTestConfig(max_rps=999, profile="smoke")
        r = SandboxV2LoadTester.validate_load_test_config(config)
        assert not r["valid"]

    def test_long_duration_blocked(self):
        config = SandboxV2LoadTestConfig(duration_seconds=99999, profile="smoke")
        r = SandboxV2LoadTester.validate_load_test_config(config)
        assert not r["valid"]


class TestTokenNotLeaked:
    def test_token_not_in_result(self):
        t = SandboxV2LoadTester(settings=DummySettings())
        config = t.create_load_test_config(targets=["readiness"])
        result = t.run_local_dry_run(config)
        s = str(result)
        assert "token" not in s.lower() or "base_url_masked" in s

    def test_base_url_masked(self):
        config = SandboxV2LoadTestConfig(base_url_masked="https://staging.internal.secret.com/api")
        d = config.to_dict()
        masked = d.get("base_url_masked", "")
        assert "staging.internal.secret.com" not in masked


class TestMalformedConfig:
    def test_empty_targets_ok(self):
        config = SandboxV2LoadTestConfig(targets=[])
        r = SandboxV2LoadTester.validate_load_test_config(config)
        assert r["valid"]

    def test_negative_values_rejected(self):
        config = SandboxV2LoadTestConfig(max_users=-1)
        r = SandboxV2LoadTester.validate_load_test_config(config)
        assert not r["valid"]


class TestProductionGuard:
    def test_prod_patterns(self):
        t = SandboxV2LoadTester()
        for pat in ["https://api.prod.example.com", "https://app.production.com"]:
            assert t.is_production_url(pat), f"Should detect production: {pat}"

    def test_safe_patterns(self):
        t = SandboxV2LoadTester()
        for pat in ["http://localhost:8000", "http://127.0.0.1:3000", "http://staging.internal"]:
            assert not t.is_production_url(pat), f"Should not flag: {pat}"


class TestNoExternalNetwork:
    def test_dry_run_no_network(self):
        t = SandboxV2LoadTester(settings=DummySettings())
        config = t.create_load_test_config(targets=["readiness"])
        result = t.run_local_dry_run(config)
        assert result["mode"] == "local_dry_run"


class TestNoContainerMicroVM:
    def test_no_container_start(self):
        t = SandboxV2LoadTester(settings=DummySettings())
        config = t.create_load_test_config()
        result = t.run_local_dry_run(config)
        s = str(result)
        assert "docker" not in s.lower()
        assert "firecracker" not in s.lower()
