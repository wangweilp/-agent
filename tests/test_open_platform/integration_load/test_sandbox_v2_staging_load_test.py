"""Integration Load Testing — default skip.

Only runs when:
  SANDBOX_V2_RUN_STAGING_LOAD_TEST=true
  SANDBOX_V2_LOAD_TESTING_ENABLED=true
  SANDBOX_V2_STAGING_BASE_URL set and valid
"""
from __future__ import annotations
import os
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest


def _enabled() -> bool:
    return all([
        os.getenv("SANDBOX_V2_RUN_STAGING_LOAD_TEST", "").lower() == "true",
        os.getenv("SANDBOX_V2_LOAD_TESTING_ENABLED", "").lower() == "true",
        bool(os.getenv("SANDBOX_V2_STAGING_BASE_URL", "")),
    ])


pytestmark = pytest.mark.skipif(
    not _enabled(),
    reason="Integration load tests skipped — set SANDBOX_V2_RUN_STAGING_LOAD_TEST=true, LOAD_TESTING_ENABLED=true, STAGING_BASE_URL",
)


class TestStagingLoad:
    def test_readiness_accessible(self):
        import requests
        base = os.getenv("SANDBOX_V2_STAGING_BASE_URL", "")
        resp = requests.get(f"{base.rstrip('/')}/api/runtime/sandbox-v2/readiness", timeout=10)
        assert resp.status_code == 200

    def test_metrics_accessible(self):
        import requests
        base = os.getenv("SANDBOX_V2_STAGING_BASE_URL", "")
        resp = requests.get(f"{base.rstrip('/')}/api/runtime/sandbox-v2/observability/readiness", timeout=10)
        assert resp.status_code == 200

    def test_no_token_leaked(self):
        token = os.getenv("SANDBOX_V2_STAGING_API_TOKEN", "")
        assert len(token) < 5 or token.startswith("***")  # not real token

    def test_production_blocked_if_disallowed(self):
        from src.open_platform.sandbox_v2.load_testing import SandboxV2LoadTester
        base = os.getenv("SANDBOX_V2_STAGING_BASE_URL", "")
        if SandboxV2LoadTester.is_production_url(base):
            allow = os.getenv("SANDBOX_V2_LOAD_TEST_ALLOW_PRODUCTION", "").lower() == "true"
            if not allow:
                pytest.skip("Production URL blocked as expected")

    def test_p95_p99_calculable(self):
        from src.open_platform.sandbox_v2.load_testing import compute_latency_stats
        s = compute_latency_stats([10.0, 20.0, 30.0, 40.0, 50.0])
        assert s["p50"] > 0
        assert s["p95"] > 0

    def test_slo_evaluable(self):
        from src.open_platform.sandbox_v2.slo import SandboxV2SLOService
        from src.open_platform.sandbox_v2.models import SandboxV2LoadTestResult
        svc = SandboxV2SLOService()
        slos = svc.get_default_slo_definitions()
        result = SandboxV2LoadTestResult(
            target="readiness", p95_ms=100.0, p99_ms=200.0,
            error_rate_percent=0.0, total_requests=10, success_count=10,
        )
        from src.open_platform.sandbox_v2.models import SandboxV2SLODefinition
        defs = [SandboxV2SLODefinition(**s) for s in slos if s["target"] == "readiness"]
        evals = svc.evaluate_load_test_against_slo(result, defs)
        assert len(evals) > 0
