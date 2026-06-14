"""Sandbox v2 performance API tests (Step 16)."""
import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.api.sandbox_v2 import create_sandbox_v2_router
from src.open_platform.sandbox_v2.network import SandboxNetworkEgressService
from src.open_platform.sandbox_v2.service import SandboxV2Service


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("SANDBOX_V2_PERF_TESTS_ENABLED", raising=False)
    monkeypatch.delenv("SANDBOX_V2_RUN_PERFORMANCE_BENCHMARKS", raising=False)
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    app_settings = Settings()
    store = SQLiteSandboxV2Store(app_settings, db_path=db_path)
    queue = SQLiteSandboxV2Queue(app_settings, db_path=db_path)
    network = SandboxNetworkEgressService(store=store)
    service = SandboxV2Service(store=store, queue=queue, network_service=network)
    app = FastAPI()
    app.include_router(create_sandbox_v2_router(service))
    yield TestClient(app)
    try:
        os.unlink(db_path)
    except OSError:
        pass


def test_performance_readiness_fields(client):
    res = client.get("/api/runtime/sandbox-v2/performance/readiness")
    assert res.status_code == 200
    data = res.json()
    assert data["performance_benchmarking"] is True
    assert data["performance_tests_enabled"] is False
    assert data["synthetic_fixture_only"] is True
    assert data["external_load_testing"] is False
    assert data["user_code_benchmarking"] is False


def test_total_readiness_includes_performance_fields(client):
    res = client.get("/api/runtime/sandbox-v2/readiness")
    assert res.status_code == 200
    data = res.json()
    assert data["performance_benchmarking"] is True
    assert data["capacity_estimation"] is True


def test_create_smoke_benchmark_config(client):
    res = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
        "profile": "smoke",
        "targets": ["jobs", "metrics"],
        "max_jobs": 3,
    })
    assert res.status_code == 200
    assert res.json()["benchmark"]["profile"] == "smoke"


def test_api_disabled_does_not_run_benchmark(client):
    create = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
        "profile": "smoke",
        "targets": ["jobs"],
        "max_jobs": 3,
    })
    benchmark_id = create.json()["benchmark"]["benchmark_id"]
    run = client.post(f"/api/runtime/sandbox-v2/performance/benchmarks/{benchmark_id}/run")
    assert run.status_code == 200
    data = run.json()
    assert data["status"] == "disabled"
    assert data["results"][0]["status"] == "skipped"


def test_large_profile_default_rejected(client):
    res = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
        "profile": "large",
        "targets": ["jobs"],
    })
    assert res.status_code == 400


def test_max_jobs_over_limit_rejected(client):
    res = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
        "profile": "small",
        "targets": ["jobs"],
        "max_jobs": 101,
    })
    assert res.status_code == 400


def test_max_concurrency_over_limit_rejected(client):
    res = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
        "profile": "small",
        "targets": ["jobs"],
        "max_concurrency": 5,
    })
    assert res.status_code == 400


def test_malformed_request_does_not_return_500(client):
    res = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
        "profile": "smoke",
        "targets": ["jobs"],
        "max_jobs": "not-a-number",
    })
    assert res.status_code != 500


def test_metadata_external_url_rejected(client):
    res = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
        "profile": "smoke",
        "targets": ["jobs"],
        "metadata": {"external_url": "https://example.com/load"},
    })
    assert res.status_code == 400
