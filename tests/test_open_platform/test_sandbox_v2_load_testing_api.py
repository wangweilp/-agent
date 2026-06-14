"""Load Testing API tests (Step 19)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from fastapi.testclient import TestClient
from src.api.sandbox_v2 import create_sandbox_v2_router
from src.open_platform.sandbox_v2.service import SandboxV2Service
from src.open_platform.sandbox_v2.load_testing import SandboxV2LoadTester
from src.open_platform.sandbox_v2.slo import SandboxV2SLOService
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.config import Settings

BASE = "/api/runtime/sandbox-v2"


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
def client():
    store = SQLiteSandboxV2Store(Settings(), db_path=":memory:")
    lt = SandboxV2LoadTester(store=store, settings=DummySettings())
    slo_svc = SandboxV2SLOService(store=store)
    svc = SandboxV2Service(store, load_tester=lt, slo_service=slo_svc)
    router = create_sandbox_v2_router(svc)
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestReadiness:
    def test_readiness(self, client):
        resp = client.get(f"{BASE}/load-testing/readiness")
        assert resp.status_code == 200
        d = resp.json()
        assert d["load_testing_framework"]
        assert not d["load_testing_enabled"]

    def test_in_main_readiness(self, client):
        resp = client.get(f"{BASE}/readiness")
        assert resp.status_code == 200
        d = resp.json()
        assert "load_testing_framework" in d


class TestConfigAPI:
    def test_create_config(self, client):
        resp = client.post(f"{BASE}/load-testing/configs", json={
            "targets": ["readiness", "metrics"], "max_users": 3, "max_rps": 3,
        })
        assert resp.status_code == 200

    def test_list_configs(self, client):
        resp = client.get(f"{BASE}/load-testing/configs")
        assert resp.status_code == 200

    def test_malformed_not_500(self, client):
        resp = client.post(f"{BASE}/load-testing/configs", json={"bad": "data"})
        assert resp.status_code != 500


class TestRunAPI:
    def test_local_dry_run(self, client):
        c = client.post(f"{BASE}/load-testing/configs", json={
            "targets": ["readiness"], "max_users": 3, "max_rps": 3,
        })
        lt_id = c.json()["load_test_config"]["load_test_id"]
        resp = client.post(f"{BASE}/load-testing/configs/{lt_id}/run?mode=local")
        assert resp.status_code == 200
        assert resp.json()["mode"] == "local_dry_run"

    def test_staging_skipped(self, client):
        c = client.post(f"{BASE}/load-testing/configs", json={
            "targets": ["readiness"], "max_users": 3, "max_rps": 3,
        })
        lt_id = c.json()["load_test_config"]["load_test_id"]
        resp = client.post(f"{BASE}/load-testing/configs/{lt_id}/run?mode=staging")
        assert resp.status_code == 200
        assert resp.json().get("status") == "skipped"


class TestResultsAPI:
    def test_list_results(self, client):
        resp = client.get(f"{BASE}/load-testing/results")
        assert resp.status_code == 200

    def test_report_json(self, client):
        c = client.post(f"{BASE}/load-testing/configs", json={
            "targets": ["readiness"], "max_users": 2, "max_rps": 2,
        })
        lt_id = c.json()["load_test_config"]["load_test_id"]
        client.post(f"{BASE}/load-testing/configs/{lt_id}/run?mode=local")
        resp = client.get(f"{BASE}/load-testing/report/{lt_id}")
        assert resp.status_code == 200


class TestSLOAPI:
    def test_definitions(self, client):
        resp = client.get(f"{BASE}/load-testing/slo/definitions")
        assert resp.status_code == 200

    def test_evaluations(self, client):
        resp = client.get(f"{BASE}/load-testing/slo/evaluations")
        assert resp.status_code == 200


class TestCapacityAPI:
    def test_latest_plan(self, client):
        resp = client.get(f"{BASE}/load-testing/capacity/latest")
        assert resp.status_code == 200
