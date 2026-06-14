"""Observability API tests (Step 18)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from fastapi.testclient import TestClient
from src.api.sandbox_v2 import create_sandbox_v2_router
from src.open_platform.sandbox_v2.service import SandboxV2Service
from src.open_platform.sandbox_v2.observability import SandboxV2ObservabilityService
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.config import Settings

BASE = "/api/runtime/sandbox-v2"


class DummySettings:
    observability_enabled = False
    prometheus_export_enabled = True
    prometheus_scrape_path = "/api/metrics"
    grafana_dashboard_enabled = False
    otel_enabled = False
    otel_exporter = "disabled"
    otel_endpoint = ""
    otel_service_name = "sandbox-v2"
    otel_traces_enabled = False
    otel_metrics_enabled = False
    otel_logs_enabled = False
    otel_include_sensitive_attributes = False
    observability_safe_mode = True


@pytest.fixture
def client():
    store = SQLiteSandboxV2Store(Settings(), db_path=":memory:")
    obs = SandboxV2ObservabilityService(store=store, settings=DummySettings())
    svc = SandboxV2Service(store, observability_service=obs)
    router = create_sandbox_v2_router(svc)
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestObservabilityReadiness:
    def test_readiness_endpoint(self, client):
        resp = client.get(f"{BASE}/observability/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert not data["otel_real_export"]
        assert data["observability_safe_mode"]

    def test_in_main_readiness(self, client):
        resp = client.get(f"{BASE}/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert "observability_config" in data
        assert not data["otel_real_export"]


class TestPrometheusAPI:
    def test_scrape_config(self, client):
        resp = client.get(f"{BASE}/observability/prometheus/scrape-config")
        assert resp.status_code == 200
        data = resp.json()
        assert "scrape_configs" in data

    def test_alert_rules(self, client):
        resp = client.get(f"{BASE}/observability/prometheus/alert-rules")
        assert resp.status_code == 200
        data = resp.json()
        assert "groups" in data


class TestGrafanaAPI:
    def test_dashboard(self, client):
        resp = client.get(f"{BASE}/observability/grafana/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "dashboard" in data

    def test_generate_dashboard(self, client):
        resp = client.post(f"{BASE}/observability/grafana/dashboard/generate?dashboard_type=security")
        assert resp.status_code == 200


class TestTraceAPI:
    def test_list_empty(self, client):
        resp = client.get(f"{BASE}/observability/traces")
        assert resp.status_code == 200
        assert "traces" in resp.json()

    def test_create_span(self, client):
        resp = client.post(f"{BASE}/observability/traces", json={
            "span_name": "test_api_call", "resource_type": "job",
            "organization_id": "org-1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["trace_span"]["span_name"] == "test_api_call"

    def test_create_span_malformed_not_500(self, client):
        resp = client.post(f"{BASE}/observability/traces", json={"bad": "data"})
        assert resp.status_code != 500


class TestOTelAPI:
    def test_simulate_export(self, client):
        resp = client.post(f"{BASE}/observability/otel/simulate-export", json={
            "signal_type": "metric", "items": [{"name": "test"}],
        })
        assert resp.status_code == 200

    def test_simulate_export_not_500(self, client):
        resp = client.post(f"{BASE}/observability/otel/simulate-export", json={"bad": "data"})
        assert resp.status_code != 500

    def test_export_records(self, client):
        resp = client.get(f"{BASE}/observability/export-records")
        assert resp.status_code == 200
        assert "export_records" in resp.json()
