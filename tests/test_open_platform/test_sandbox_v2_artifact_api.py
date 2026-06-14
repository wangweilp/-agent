"""Test Sandbox v2 Artifact API — artifact API 集成测试。

覆盖：
1. POST /artifacts 创建 artifact
2. GET /artifacts 列出 artifacts
3. GET /artifacts/{id} 查看 metadata
4. GET /artifacts/{id}/content 读取内容
5. DELETE /artifacts/{id} 删除
6. readiness 显示 artifact_store=true
7. 旧 Step 1 / Step 2 端点仍可用
"""
import os
import pytest
import tempfile
import shutil

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
from src.open_platform.sandbox_v2.service import SandboxV2Service
from src.open_platform.sandbox_v2.worker import SandboxV2Worker
from src.open_platform.sandbox_v2.artifacts import LocalSandboxArtifactStore
from src.api.sandbox_v2 import create_sandbox_v2_router


@pytest.fixture
def client():
    """创建含 artifact store 的完整测试客户端。"""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    art_root = tempfile.mkdtemp(prefix="sbx_art_api_")
    os.close(db_fd)
    settings = Settings()
    store = SQLiteSandboxV2Store(settings, db_path=db_path)
    queue = SQLiteSandboxV2Queue(settings, db_path=db_path)
    art_store = LocalSandboxArtifactStore(artifact_root=art_root)
    service = SandboxV2Service(store=store, queue=queue, artifact_store=art_store)
    worker = SandboxV2Worker(queue=queue, service=service, worker_id="test-api-art-wkr")
    app = FastAPI()
    app.include_router(create_sandbox_v2_router(service, worker=worker))
    yield TestClient(app)
    try:
        os.unlink(db_path)
    except Exception:
        pass
    try:
        shutil.rmtree(art_root)
    except Exception:
        pass


class TestCreateArtifact:
    def test_create_valid_artifact(self, client):
        """POST /artifacts 正常创建。"""
        res = client.post("/api/runtime/sandbox-v2/artifacts", json={
            "artifact_name": "test.txt",
            "artifact_type": "text",
            "content_text": "api test content",
            "mime_type": "text/plain",
            "job_id": "api-job-1",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["materialized"] is True
        assert data["artifact"]["status"] == "materialized"

    def test_create_bad_extension_rejected(self, client):
        """危险扩展名被拒绝。"""
        res = client.post("/api/runtime/sandbox-v2/artifacts", json={
            "artifact_name": "malware.exe",
            "artifact_type": "text",
            "content_text": "bad",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["materialized"] is False
        assert data["artifact"]["status"] == "rejected"


class TestListArtifacts:
    def test_list_artifacts(self, client):
        """GET /artifacts 列出 artifacts。"""
        res = client.get("/api/runtime/sandbox-v2/artifacts")
        assert res.status_code == 200
        assert "artifacts" in res.json()

    def test_list_filter_by_job_id(self, client):
        """按 job_id 过滤。"""
        res = client.get("/api/runtime/sandbox-v2/artifacts?job_id=some-job")
        assert res.status_code == 200


class TestGetArtifact:
    def test_get_nonexistent_returns_404(self, client):
        """不存在的 artifact 返回 404。"""
        res = client.get("/api/runtime/sandbox-v2/artifacts/nonexistent")
        assert res.status_code == 404


class TestArtifactContent:
    def test_get_content(self, client):
        """GET /artifacts/{id}/content 返回内容。"""
        create_res = client.post("/api/runtime/sandbox-v2/artifacts", json={
            "artifact_name": "readme.txt",
            "artifact_type": "text",
            "content_text": "readable content here",
            "job_id": "api-readme",
        })
        art_id = create_res.json()["artifact"]["artifact_id"]

        content_res = client.get(f"/api/runtime/sandbox-v2/artifacts/{art_id}/content")
        assert content_res.status_code == 200
        assert "readable content here" in content_res.json()["content"]


class TestDeleteArtifact:
    def test_delete_artifact(self, client):
        """DELETE 成功删除。"""
        create_res = client.post("/api/runtime/sandbox-v2/artifacts", json={
            "artifact_name": "to_del.txt",
            "artifact_type": "text",
            "content_text": "tmp",
            "job_id": "api-del",
        })
        art_id = create_res.json()["artifact"]["artifact_id"]

        del_res = client.delete(f"/api/runtime/sandbox-v2/artifacts/{art_id}")
        assert del_res.status_code == 200
        assert del_res.json()["deleted"] is True


class TestManifest:
    def test_create_manifest(self, client):
        """POST /artifact-manifests 创建 manifest。"""
        # Create 2 artifacts first
        client.post("/api/runtime/sandbox-v2/artifacts", json={
            "artifact_name": "m1.txt", "artifact_type": "text",
            "content_text": "1", "job_id": "api-mft", "record_id": "rec-mft",
        })
        client.post("/api/runtime/sandbox-v2/artifacts", json={
            "artifact_name": "m2.json", "artifact_type": "json",
            "content_text": '{}', "job_id": "api-mft", "record_id": "rec-mft",
            "mime_type": "application/json",
        })

        res = client.post("/api/runtime/sandbox-v2/artifact-manifests", json={
            "job_id": "api-mft",
            "record_id": "rec-mft",
        })
        assert res.status_code == 200
        data = res.json()
        assert "manifest" in data
        assert data["manifest"]["artifact_count"] >= 2


class TestReadiness:
    def test_readiness_shows_artifact_flags(self, client):
        """readiness 显示 artifact_store=true。"""
        res = client.get("/api/runtime/sandbox-v2/readiness")
        data = res.json()
        assert data["artifact_store"] is True
        assert data["read_only_artifact_materialization"] is True
        assert data["path_traversal_protection"] is True
        assert data["artifact_size_limit"] is True
        assert data["artifact_hashing"] is True
        assert data["unsafe_archive_extraction"] is False
        assert data["arbitrary_filesystem_access"] is False
        assert data["execution_isolation"] is False
        assert data["network_isolation"] is False


class TestBackwardCompatibility:
    """验证 Step 1/2 端点仍可用。"""

    def test_jobs_endpoint(self, client):
        res = client.post("/api/runtime/sandbox-v2/jobs", json={"mode": "simulation"})
        assert res.status_code == 200

    def test_queue_endpoint(self, client):
        res = client.get("/api/runtime/sandbox-v2/queue")
        assert res.status_code == 200

    def test_workers_endpoint(self, client):
        res = client.get("/api/runtime/sandbox-v2/workers")
        assert res.status_code == 200

    def test_dead_letter_endpoint(self, client):
        res = client.get("/api/runtime/sandbox-v2/dead-letter")
        assert res.status_code == 200


class TestNo500:
    def test_all_artifact_endpoints_no_500(self, client):
        """所有 artifact 端点不返回 500。"""
        endpoints = [
            ("GET", "/api/runtime/sandbox-v2/artifacts"),
            ("GET", "/api/runtime/sandbox-v2/readiness"),
        ]
        for method, path in endpoints:
            res = client.get(path)
            assert res.status_code != 500, f"{method} {path} returned 500"
