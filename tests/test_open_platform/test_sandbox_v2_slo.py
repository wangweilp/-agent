"""SLO tests (Step 19)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.slo import SandboxV2SLOService
from src.open_platform.sandbox_v2.models import (
    SandboxV2SLODefinition, SandboxV2SLOEvaluation,
    SandboxV2LoadTestResult, SandboxV2SLOStatus,
)
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.config import Settings


@pytest.fixture
def store():
    return SQLiteSandboxV2Store(Settings(), db_path=":memory:")


class TestSLODefaults:
    def test_default_slos_exist(self):
        defs = SandboxV2SLOService.get_default_slo_definitions()
        assert len(defs) >= 5

    def test_create_slo(self, store):
        svc = SandboxV2SLOService(store=store)
        slo = svc.create_slo_definition(name="test-slo", target="readiness",
                                        p95_ms=100, p99_ms=200)
        assert slo.slo_id != ""

    def test_list_slos(self, store):
        svc = SandboxV2SLOService(store=store)
        svc.create_slo_definition(name="slo-1", target="readiness")
        items = svc.list_slo_definitions()
        assert len(items) >= 1


class TestSLOEvaluation:
    def test_passed(self, store):
        svc = SandboxV2SLOService(store=store)
        slo = svc.create_slo_definition(name="fast-slo", target="readiness",
                                        p95_ms=500, p99_ms=1000, error_rate_percent=5.0)
        result = SandboxV2LoadTestResult(
            load_test_id="lt-1", target="readiness",
            p95_ms=100.0, p99_ms=200.0, error_rate_percent=0.0,
            total_requests=100, success_count=100,
        )
        evals = svc.evaluate_load_test_against_slo(result, [slo])
        assert len(evals) == 1
        assert evals[0].status == SandboxV2SLOStatus.PASSED

    def test_failed_p95(self, store):
        svc = SandboxV2SLOService(store=store)
        slo = svc.create_slo_definition(name="strict", target="readiness",
                                        p95_ms=50, p99_ms=100)
        result = SandboxV2LoadTestResult(
            load_test_id="lt-2", target="readiness",
            p95_ms=200.0, p99_ms=300.0, error_rate_percent=0.0,
            total_requests=100, success_count=100,
        )
        evals = svc.evaluate_load_test_against_slo(result, [slo])
        assert evals[0].status == SandboxV2SLOStatus.FAILED

    def test_failed_error_rate(self, store):
        svc = SandboxV2SLOService(store=store)
        slo = svc.create_slo_definition(name="low-err", target="readiness",
                                        p95_ms=5000, p99_ms=5000, error_rate_percent=1.0)
        result = SandboxV2LoadTestResult(
            load_test_id="lt-3", target="readiness",
            p95_ms=10.0, p99_ms=20.0, error_rate_percent=10.0,
            total_requests=100, success_count=90,
        )
        evals = svc.evaluate_load_test_against_slo(result, [slo])
        assert evals[0].status == SandboxV2SLOStatus.FAILED

    def test_summary(self, store):
        svc = SandboxV2SLOService(store=store)
        eval1 = SandboxV2SLOEvaluation(status="passed")
        eval2 = SandboxV2SLOEvaluation(status="failed")
        s = svc.generate_slo_summary([eval1, eval2])
        assert s["passed"] == 1
        assert s["failed"] == 1

    def test_readiness(self, store):
        svc = SandboxV2SLOService(store=store)
        r = svc.get_slo_readiness()
        assert r["slo_evaluation"] is True
