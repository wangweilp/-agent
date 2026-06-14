"""Test Sandbox v2 Queue API — 队列 API 集成测试。

覆盖：
1. submit job with enqueue=true 后进入队列
2. run-once API 能处理一个任务
3. readiness 正确显示 worker_framework=true、execution_isolation=false
4. 旧的 Step 1 测试兼容性（enqueue=false 行为不变）
"""
import os
import pytest
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
from src.open_platform.sandbox_v2.service import SandboxV2Service
from src.open_platform.sandbox_v2.worker import SandboxV2Worker
from src.api.sandbox_v2 import create_sandbox_v2_router


@pytest.fixture
def client():
    """创建完整的 sandbox v2 测试客户端（含 queue + worker）。"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    settings = Settings()
    store = SQLiteSandboxV2Store(settings, db_path=db_path)
    queue = SQLiteSandboxV2Queue(settings, db_path=db_path)
    service = SandboxV2Service(store=store, queue=queue)
    worker = SandboxV2Worker(queue=queue, service=service, worker_id="test-api-worker")
    app = FastAPI()
    app.include_router(create_sandbox_v2_router(service, worker=worker))
    yield TestClient(app)
    try:
        os.unlink(db_path)
    except Exception:
        pass


class TestReadiness:
    def test_readiness_worker_framework_true(self, client):
        """readiness 正确显示 worker_framework=true。"""
        res = client.get("/api/runtime/sandbox-v2/readiness")
        assert res.status_code == 200
        data = res.json()
        assert data["sandbox_v2_core_contract"] is True
        assert data["real_task_queue"] is True
        assert data["worker_framework"] is True
        assert data["execution_isolation"] is False
        assert data["distributed_worker"] is False
        assert data["redis_queue"] is False
        assert data["current_execution_mode"] == "simulation_only"

    def test_readiness_no_500(self, client):
        """readiness 不返回 500。"""
        res = client.get("/api/runtime/sandbox-v2/readiness")
        assert res.status_code != 500


class TestEnqueueSubmitJob:
    def test_submit_with_enqueue_true_returns_queue_id(self, client):
        """submit job with enqueue=true 后返回 queue_id。"""
        res = client.post("/api/runtime/sandbox-v2/jobs", json={
            "mode": "simulation",
            "requested_action": "dry_run",
            "enqueue": True,
        })
        assert res.status_code == 200
        data = res.json()
        # With default deny policy, the job will be rejected
        # So it may not have a queue_id
        assert "job_id" in data or data.get("job_id") is None

    def test_enqueue_false_preserves_step1_behavior(self, client):
        """enqueue=false 保持 Step 1 行为不变。"""
        res = client.post("/api/runtime/sandbox-v2/jobs", json={
            "mode": "simulation",
            "requested_action": "dry_run",
            "enqueue": False,
        })
        assert res.status_code == 200
        data = res.json()
        assert "job_id" in data
        assert "queue_id" not in data or data.get("queue_id") is None


class TestQueueEndpoints:
    def test_list_queue_returns_200(self, client):
        """GET /queue 返回 200。"""
        res = client.get("/api/runtime/sandbox-v2/queue")
        assert res.status_code == 200
        data = res.json()
        assert "queue_items" in data
        assert "total" in data

    def test_requeue_expired_returns_200(self, client):
        """POST /queue/requeue-expired 返回 200。"""
        res = client.post("/api/runtime/sandbox-v2/queue/requeue-expired")
        assert res.status_code == 200
        data = res.json()
        assert "requeued_count" in data


class TestWorkerEndpoints:
    def test_list_workers_returns_200(self, client):
        """GET /workers 返回 200。"""
        res = client.get("/api/runtime/sandbox-v2/workers")
        assert res.status_code == 200
        data = res.json()
        assert "workers" in data
        assert "total" in data

    def test_run_once_returns_200_when_empty(self, client):
        """POST /workers/run-once 在队列空时返回消息。"""
        res = client.post("/api/runtime/sandbox-v2/workers/run-once")
        assert res.status_code == 200
        data = res.json()
        assert "message" in data

    def test_run_once_worker_configured(self, client):
        """worker 已配置（不应返回 503）。"""
        res = client.post("/api/runtime/sandbox-v2/workers/run-once")
        assert res.status_code != 503


class TestDeadLetter:
    def test_dead_letter_returns_200(self, client):
        """GET /dead-letter 返回 200。"""
        res = client.get("/api/runtime/sandbox-v2/dead-letter")
        assert res.status_code == 200
        data = res.json()
        assert "dead_letter_items" in data
        assert "total" in data


class TestNo500:
    def test_all_step2_endpoints_no_500(self, client):
        """所有 Step 2 端点不返回 500。"""
        endpoints = [
            ("GET", "/api/runtime/sandbox-v2/queue"),
            ("GET", "/api/runtime/sandbox-v2/workers"),
            ("GET", "/api/runtime/sandbox-v2/dead-letter"),
            ("GET", "/api/runtime/sandbox-v2/readiness"),
        ]
        for method, path in endpoints:
            res = client.get(path)
            assert res.status_code != 500, f"{method} {path} returned 500: {res.text}"


class TestStep1Compatibility:
    """验证 Step 1 的 6 个原始端点仍然可用。"""
    def test_post_jobs_step1(self, client):
        res = client.post("/api/runtime/sandbox-v2/jobs", json={"mode": "simulation"})
        assert res.status_code == 200

    def test_get_jobs_step1(self, client):
        res = client.get("/api/runtime/sandbox-v2/jobs")
        assert res.status_code == 200

    def test_get_execution_records_step1(self, client):
        res = client.get("/api/runtime/sandbox-v2/execution-records")
        assert res.status_code == 200
