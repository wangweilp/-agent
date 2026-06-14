"""Test Sandbox v2 API — API 端点集成测试。

覆盖：
1. readiness 正确返回未完成项
2. API 不返回 500
"""
import os
import pytest
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.open_platform.sandbox_v2.service import SandboxV2Service
from src.api.sandbox_v2 import create_sandbox_v2_router


@pytest.fixture
def client():
    """创建带有 sandbox v2 路由的 TestClient。"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    settings = Settings()
    store = SQLiteSandboxV2Store(settings, db_path=db_path)
    service = SandboxV2Service(store=store)
    app = FastAPI()
    app.include_router(create_sandbox_v2_router(service))
    yield TestClient(app)
    try:
        os.unlink(db_path)
    except Exception:
        pass


class TestReadiness:
    def test_readiness_returns_200(self, client):
        """readiness API 返回 200。"""
        res = client.get("/api/runtime/sandbox-v2/readiness")
        assert res.status_code == 200

    def test_readiness_shows_capabilities_correctly(self, client):
        """readiness 正确返回未完成项。"""
        res = client.get("/api/runtime/sandbox-v2/readiness")
        data = res.json()
        assert data["sandbox_v2_core_contract"] is True
        # Step 2: real_task_queue is now True (SQLite queue exists)
        assert data["execution_isolation"] is False
        assert data["process_kill"] is False
        assert data["network_isolation"] is False
        assert data["filesystem_isolation"] is False
        assert "metadata_only" in data["allowed_modes"]
        assert "simulation" in data["allowed_modes"]

    def test_readiness_boundary_statement_present(self, client):
        """readiness 包含边界声明。"""
        res = client.get("/api/runtime/sandbox-v2/readiness")
        data = res.json()
        assert len(data["boundary_statement"]) > 0
        assert "boundary_statement" in data


class TestSubmitJob:
    def test_submit_job_returns_200(self, client):
        """submit job 返回 200。"""
        res = client.post("/api/runtime/sandbox-v2/jobs", json={
            "mode": "simulation",
            "requested_action": "dry_run",
        })
        assert res.status_code == 200

    def test_submit_job_returns_job_id(self, client):
        """submit job 返回 job_id。"""
        res = client.post("/api/runtime/sandbox-v2/jobs", json={
            "mode": "simulation",
            "requested_action": "dry_run",
        })
        data = res.json()
        assert "job_id" in data
        assert "decision" in data
        assert data["decision"]["allowed"] is False

    def test_submit_invalid_mode_returns_400(self, client):
        """非法 mode 返回 400。"""
        res = client.post("/api/runtime/sandbox-v2/jobs", json={
            "mode": "future_container",
        })
        assert res.status_code == 400


class TestListJobs:
    def test_list_jobs_returns_200(self, client):
        """list jobs API 返回 200。"""
        res = client.get("/api/runtime/sandbox-v2/jobs")
        assert res.status_code == 200
        data = res.json()
        assert "jobs" in data
        assert "total" in data


class TestGetJob:
    def test_get_nonexistent_job_returns_404(self, client):
        """不存在的 job 返回 404。"""
        res = client.get("/api/runtime/sandbox-v2/jobs/nonexistent")
        assert res.status_code == 404


class TestCancelJob:
    def test_cancel_nonexistent_job_returns_404(self, client):
        """cancel 不存在的 job 返回 404。"""
        res = client.post("/api/runtime/sandbox-v2/jobs/nonexistent/cancel")
        assert res.status_code == 404


class TestExecutionRecords:
    def test_list_execution_records_returns_200(self, client):
        """list execution records API 返回 200。"""
        res = client.get("/api/runtime/sandbox-v2/execution-records")
        assert res.status_code == 200
        data = res.json()
        assert "execution_records" in data
        assert "total" in data


class TestNo500:
    def test_all_endpoints_no_500(self, client):
        """所有端点不返回 500。"""
        endpoints = [
            ("GET", "/api/runtime/sandbox-v2/readiness"),
            ("GET", "/api/runtime/sandbox-v2/jobs"),
            ("GET", "/api/runtime/sandbox-v2/execution-records"),
        ]
        for method, path in endpoints:
            if method == "GET":
                res = client.get(path)
            assert res.status_code != 500, f"Endpoint {method} {path} returned 500: {res.text}"

    def test_submit_valid_job_no_500(self, client):
        """submit job 不返回 500。"""
        res = client.post("/api/runtime/sandbox-v2/jobs", json={
            "mode": "simulation",
        })
        assert res.status_code != 500
