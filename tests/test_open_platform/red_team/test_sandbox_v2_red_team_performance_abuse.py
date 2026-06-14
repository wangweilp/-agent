"""Red-team tests for Sandbox v2 performance benchmark abuse (Step 16)."""
import json
import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.api.sandbox_v2 import create_sandbox_v2_router
from src.open_platform.sandbox_v2.config import SandboxV2Settings
from src.open_platform.sandbox_v2.network import SandboxNetworkEgressService
from src.open_platform.sandbox_v2.performance import SandboxV2PerformanceBenchmark
from src.open_platform.sandbox_v2.service import SandboxV2Service


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SANDBOX_V2_PERF_TESTS_ENABLED", "false")
    monkeypatch.setenv("SANDBOX_V2_RUN_PERFORMANCE_BENCHMARKS", "false")
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


def test_user_huge_max_jobs_rejected(client):
    res = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
        "profile": "small", "targets": ["jobs"], "max_jobs": 999999,
    })
    assert res.status_code != 200
    assert res.status_code != 500


def test_user_huge_concurrency_rejected(client):
    res = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
        "profile": "small", "targets": ["jobs"], "max_concurrency": 999999,
    })
    assert res.status_code != 200
    assert res.status_code != 500


def test_large_profile_rejected_by_default(client):
    res = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
        "profile": "large", "targets": ["jobs"],
    })
    assert res.status_code == 400


def test_performance_api_rejects_external_url(client):
    res = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
        "profile": "smoke", "targets": ["jobs"], "metadata": {"external_url": "https://evil.example/load"},
    })
    assert res.status_code == 400


def test_benchmark_rejects_user_command(client):
    res = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
        "profile": "smoke", "targets": ["jobs"], "metadata": {"command": "curl https://evil.example"},
    })
    assert res.status_code == 400


def test_benchmark_rejects_user_artifact_path(client):
    res = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
        "profile": "smoke", "targets": ["artifacts"], "metadata": {"artifact_path": "C:\\Users\\secret.txt"},
    })
    assert res.status_code == 400


def test_benchmark_rejects_container_or_microvm_input(client):
    for metadata in ({"container": "docker run alpine"}, {"microvm": "firecracker"}):
        res = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
            "profile": "smoke", "targets": ["jobs"], "metadata": metadata,
        })
        assert res.status_code == 400


def test_network_target_does_not_send_external_request(monkeypatch):
    def fail_socket(*args, **kwargs):
        raise AssertionError("socket must not be used")

    monkeypatch.setattr("socket.socket", fail_socket)
    runner = SandboxV2PerformanceBenchmark(store=_temp_store(), settings=SandboxV2Settings())
    cfg = runner.create_benchmark_config(profile="smoke", targets=["network"], max_jobs=1)
    result = runner.run_network_preflight_benchmark(cfg)
    assert result.status == "completed"


def test_benchmark_does_not_generate_unbounded_alerts():
    store = _temp_store()
    runner = SandboxV2PerformanceBenchmark(store=store, settings=SandboxV2Settings())
    cfg = runner.create_benchmark_config(profile="smoke", targets=["alerts"], max_jobs=3)
    result = runner.run_alert_evaluation_benchmark(cfg)
    assert result.status == "completed"
    assert len(store.list_alerts(limit=100)) <= 10


def test_benchmark_report_no_secret_or_local_absolute_path(client):
    create = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
        "profile": "smoke", "targets": ["jobs"], "max_jobs": 1,
    })
    benchmark_id = create.json()["benchmark"]["benchmark_id"]
    report = client.get(f"/api/runtime/sandbox-v2/performance/report/{benchmark_id}")
    assert report.status_code == 200
    text = json.dumps(report.json())
    assert "SECRET" not in text.upper()
    assert "ACCESS_KEY" not in text
    assert "C:\\Users\\" not in text
    assert "D:\\dma\\" not in text


def test_malformed_benchmark_request_fail_closed(client):
    res = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
        "profile": "smoke", "targets": {"not": "a-list"},
    })
    assert res.status_code != 500
    assert res.status_code in (400, 422)


def test_repeated_disabled_benchmark_has_warning(client):
    create = client.post("/api/runtime/sandbox-v2/performance/benchmarks", json={
        "profile": "smoke", "targets": ["jobs"], "max_jobs": 1,
    })
    benchmark_id = create.json()["benchmark"]["benchmark_id"]
    first = client.post(f"/api/runtime/sandbox-v2/performance/benchmarks/{benchmark_id}/run")
    second = client.post(f"/api/runtime/sandbox-v2/performance/benchmarks/{benchmark_id}/run")
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["results"][0]["warnings"]


def _temp_store():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return SQLiteSandboxV2Store(Settings(), db_path=db_path)
