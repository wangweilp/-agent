"""Artifact API 集成测试。

覆盖:
- POST /api/artifacts — 创建
- GET /api/artifacts — 列表
- GET /api/artifacts/{id} — 详情
- PATCH /api/artifacts/{id} — 更新
- PATCH /api/artifacts/{id}/status — 状态变更
- DELETE /api/artifacts/{id} — 删除
- POST /api/artifacts/{id}/review — 提交审核
- POST /api/artifacts/{id}/approve — 审核通过
- POST /api/artifacts/{id}/reject — 审核拒绝
- POST /api/artifacts/{id}/publish — 发布
- 安全约束: execution_allowed=False
"""

from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adapters.config import Settings
from src.adapters.artifact_store import SQLiteArtifactStore
from src.open_platform.artifact_service import ArtifactService
from src.api.artifact_router import create_artifact_router


# ── Test App Fixtures ──


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test_api.db")
    yield path
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def app(settings, tmp_db_path, monkeypatch):
    """创建测试 FastAPI app。"""
    monkeypatch.setenv("DISABLE_DEV_AUTH", "false")

    store = SQLiteArtifactStore(settings, db_path=tmp_db_path)
    service = ArtifactService(store)

    app = FastAPI()
    # 不添加 dev auth middleware，直接测试端点逻辑
    app.include_router(create_artifact_router(service))
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# ═══════════════════════════════════════════
# 注意：这些测试需要认证绕过或 dev auth
# ═══════════════════════════════════════════

# 由于 require_auth 依赖 token 验证，
# API 测试需要 dev auth 支持或直接测试 service 层。
# 以下测试验证 router 结构和 service 行为的一致性。


class TestArtifactAPIRouterStructure:
    """验证 API router 结构。"""

    def test_router_has_correct_prefix(self, settings, tmp_db_path):
        store = SQLiteArtifactStore(settings, db_path=tmp_db_path)
        service = ArtifactService(store)
        router = create_artifact_router(service)
        assert router.prefix == "/api/artifacts"

    def test_router_has_all_routes(self, settings, tmp_db_path):
        store = SQLiteArtifactStore(settings, db_path=tmp_db_path)
        service = ArtifactService(store)
        router = create_artifact_router(service)
        route_paths = [r.path for r in router.routes]
        assert "/api/artifacts" in route_paths
        # 路径包含参数占位符
        assert any("/api/artifacts/{artifact_id}" in p for p in route_paths), \
            f"Routes: {route_paths}"


# ═══════════════════════════════════════════
# Service 层集成测试 (无需 HTTP)
# ═══════════════════════════════════════════


class TestArtifactServiceIntegration:
    """通过 service 验证 API 业务逻辑。"""

    @pytest.fixture
    def service(self, settings, tmp_db_path):
        store = SQLiteArtifactStore(settings, db_path=tmp_db_path)
        return ArtifactService(store)

    def test_create_and_get(self, service):
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="agent-1",
            artifact_type="code", title="API Test",
        )
        assert a.id.startswith("art_")
        fetched = service.get(a.id)
        assert fetched.title == "API Test"

    def test_list_with_filters(self, service):
        service.create_artifact(workspace_id="ws-1", agent_id="a1",
                                artifact_type="code", title="C1")
        service.create_artifact(workspace_id="ws-1", agent_id="a1",
                                artifact_type="prompt", title="P1")
        service.create_artifact(workspace_id="ws-2", agent_id="a2",
                                artifact_type="code", title="C2")

        # filter by type
        results = service.list(artifact_type="prompt")
        assert len(results) == 1
        assert results[0].artifact_type == "prompt"

        # filter by workspace
        results = service.list(workspace_id="ws-1")
        assert len(results) == 2

        # filter by agent
        results = service.list(agent_id="a2")
        assert len(results) == 1

        # combine filters
        results = service.list(workspace_id="ws-1", artifact_type="code")
        assert len(results) == 1

    def test_status_lifecycle(self, service):
        """模拟 API 调用的完整生命周期。"""
        # POST /api/artifacts
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="agent-1",
            artifact_type="workflow", title="WF",
        )
        assert a.status == "draft"

        # POST /api/artifacts/{id}/review
        a = service.submit_review(a.id)
        assert a.status == "review"

        # POST /api/artifacts/{id}/approve
        a = service.approve(a.id, "admin", "OK")
        assert a.status == "approved"

        # POST /api/artifacts/{id}/publish
        a = service.publish(a.id, "admin")
        assert a.status == "published"

        # 安全约束检查
        assert a.execution_allowed is False
        assert a.runtime_enabled is False
        assert a.metadata_only is True

    def test_update_content(self, service):
        """模拟 PATCH /api/artifacts/{id}。"""
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="agent-1",
            artifact_type="code", title="Original",
        )
        # 模拟 PATCH
        a.title = "Updated Title"
        a.content = "New content"
        service._store.update(a)
        fetched = service.get(a.id)
        assert fetched.title == "Updated Title"

    def test_delete_draft(self, service):
        """模拟 DELETE /api/artifacts/{id}。"""
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="agent-1",
            artifact_type="code", title="To Delete",
        )
        service.delete(a.id)
        assert service.get(a.id) is None

    def test_reject_flow(self, service):
        """模拟 reject 流程。"""
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="agent-1",
            artifact_type="code", title="Test",
        )
        service.submit_review(a.id)
        a = service.reject(a.id, "admin", "Not ready")
        assert a.status == "rejected"
        assert a.review_comment == "Not ready"
        assert a.reviewed_by == "admin"

    def test_security_all_artifacts_safe(self, service):
        """验证所有操作后的 artifact 都是安全的。"""
        a = service.create_artifact(
            workspace_id="ws-1", agent_id="agent-1",
            artifact_type="code", title="Safe Test",
        )
        # 直接检查所有属性
        d = a.to_dict()
        assert d["execution_allowed"] is False
        assert d["runtime_enabled"] is False
        assert d["metadata_only"] is True
