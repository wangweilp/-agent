"""API endpoint tests for /sync routes using FastAPI TestClient."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adapters.auth_store import SQLiteAuthStore
from src.api.middleware import JWTTokenService, init_auth
from src.api.sync_router import create_sync_router
from src.core.auth import User, WorkspaceRole
from src.sync.models import (
    SyncConnectorConfig,
    SyncExecution,
    SyncJob,
    SyncRule,
)
from src.sync.sync_store import SyncStore
from src.sync.sync_worker import SyncWorker
from src.sync.scheduler import SyncScheduler
from src.sync.sync_pipeline import SyncPipeline


# ── Auth helpers ──


def _make_auth_headers(token_service: JWTTokenService) -> dict:
    """Create Bearer auth headers with admin role for sync management access."""
    user = User(id="admin-1", email="admin@sync.test", name="Sync Admin")
    tokens = token_service.create_tokens(user, "ws-sync", WorkspaceRole.ADMIN)
    return {"Authorization": f"Bearer {tokens.access_token}"}


# ── Fixtures ──


@pytest.fixture
def settings():
    from src.adapters.config import Settings
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def auth_store(settings):
    store = SQLiteAuthStore(settings, db_path=":memory:")
    yield store
    store.close()


@pytest.fixture
def token_service():
    return JWTTokenService()


@pytest.fixture
def auth_headers(token_service):
    return _make_auth_headers(token_service)


@pytest.fixture
def mock_store(sync_store):
    """Use the real SyncStore from conftest."""
    return sync_store


@pytest.fixture
def mock_pipeline():
    """Mock SyncPipeline."""
    pipeline = MagicMock(spec=SyncPipeline)
    return pipeline


@pytest.fixture
def mock_worker(mock_store, mock_pipeline):
    """SyncWorker with mock pipeline."""
    worker = SyncWorker(mock_store, mock_pipeline)
    return worker


@pytest.fixture
def mock_scheduler(mock_store, mock_worker):
    """Mock SyncScheduler."""
    scheduler = MagicMock(spec=SyncScheduler)
    return scheduler


@pytest.fixture
def client(mock_store, mock_worker, mock_scheduler, token_service, auth_store):
    """FastAPI TestClient with sync router and auth initialized."""
    init_auth(token_service, auth_store)
    router = create_sync_router(mock_store, mock_worker, mock_scheduler)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ── Connector Tests ──


class TestConnectorEndpoints:
    """POST/GET/DELETE /sync/connectors endpoints."""

    def test_create_connector(self, client, mock_store, auth_headers):
        """POST /sync/connectors creates and returns connector."""
        resp = client.post("/sync/connectors", json={
            "name": "My Feishu",
            "connector_type": "feishu",
            "credentials": {"app_id": "test", "app_secret": "secret"},
        }, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert data["connector"]["name"] == "My Feishu"
        assert data["connector"]["connector_type"] == "feishu"
        assert "id" in data["connector"]

    def test_create_connector_default_credentials(self, client, auth_headers):
        """Credentials default to empty dict."""
        resp = client.post("/sync/connectors", json={
            "name": "Minimal",
            "connector_type": "rss",
        }, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"

    def test_list_connectors_empty(self, client, auth_headers):
        """GET /sync/connectors returns empty list with no connectors."""
        resp = client.get("/sync/connectors", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["connectors"] == []

    def test_list_connectors_with_data(self, client, mock_store, auth_headers):
        """GET /sync/connectors returns all connectors."""
        cfg = SyncConnectorConfig(name="C1", connector_type="feishu", credentials={})
        mock_store.save_connector(cfg)
        cfg2 = SyncConnectorConfig(name="C2", connector_type="notion", credentials={})
        mock_store.save_connector(cfg2)

        resp = client.get("/sync/connectors", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["connectors"]) == 2

    def test_delete_connector(self, client, mock_store, auth_headers):
        """DELETE /sync/connectors/{id} removes connector."""
        cfg = SyncConnectorConfig(name="ToDelete", connector_type="local_folder", credentials={})
        mock_store.save_connector(cfg)

        resp = client.delete(f"/sync/connectors/{cfg.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        assert mock_store.get_connector(cfg.id) is None

    def test_delete_nonexistent_connector(self, client, mock_store, auth_headers):
        """DELETE returns 404 for nonexistent connector."""
        resp = client.delete("/sync/connectors/nonexistent-id", headers=auth_headers)
        assert resp.status_code == 404

    def test_create_connector_returns_correct_fields(self, client, auth_headers):
        """Created connector response includes all expected fields (credentials redacted)."""
        resp = client.post("/sync/connectors", json={
            "name": "Test",
            "connector_type": "obsidian",
            "credentials": {"vault_path": "/tmp/vault", "api_key": "secret123"},
        }, headers=auth_headers)
        data = resp.json()
        c = data["connector"]
        assert "id" in c
        assert "name" in c
        assert "connector_type" in c
        assert c["enabled"] is True
        assert c["last_sync_status"] == "never"
        # Verify connector response never includes credentials
        assert "credentials" not in c, "credentials must not leak in API response"


# ── Job Tests ──


class TestJobEndpoints:
    """POST/GET/DELETE /sync/jobs endpoints."""

    @pytest.fixture
    def _connector(self, mock_store):
        cfg = SyncConnectorConfig(name="Test", connector_type="feishu", credentials={})
        mock_store.save_connector(cfg)
        return cfg

    def test_create_job_manual(self, client, mock_store, _connector, auth_headers):
        """POST /sync/jobs creates a manual sync job."""
        resp = client.post("/sync/jobs", json={
            "connector_config_id": _connector.id,
            "name": "My Manual Sync",
            "rule_type": "manual",
        }, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        job = data["job"]
        assert job["name"] == "My Manual Sync"
        assert job["rule_type"] == "manual"

    def test_create_job_cron(self, client, mock_store, _connector, auth_headers):
        """POST /sync/jobs with cron expression."""
        resp = client.post("/sync/jobs", json={
            "connector_config_id": _connector.id,
            "name": "Hourly Sync",
            "rule_type": "cron",
            "cron_expression": "0 * * * *",
        }, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["job"]["rule_type"] == "cron"
        assert data["job"]["cron_expression"] == "0 * * * *"

    def test_create_job_default_rule_type(self, client, mock_store, _connector, auth_headers):
        """Default rule_type is 'manual'."""
        resp = client.post("/sync/jobs", json={
            "connector_config_id": _connector.id,
            "name": "Default Rule",
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["job"]["rule_type"] == "manual"

    def test_list_jobs_empty(self, client, auth_headers):
        """GET /sync/jobs returns empty list."""
        resp = client.get("/sync/jobs", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["jobs"] == []

    def test_list_jobs_with_data(self, client, mock_store, _connector, auth_headers):
        """GET /sync/jobs returns all jobs with rules."""
        rule = SyncRule(rule_type="manual")
        mock_store.save_rule(rule)
        job = SyncJob(connector_config_id=_connector.id, rule_id=rule.id, name="J1")
        mock_store.save_job(job)

        resp = client.get("/sync/jobs", headers=auth_headers)
        assert resp.status_code == 200
        jobs = resp.json()["jobs"]
        assert len(jobs) == 1
        assert jobs[0]["name"] == "J1"

    def test_get_job_detail(self, client, mock_store, _connector, auth_headers):
        """GET /sync/jobs/{id} returns job with executions."""
        rule = SyncRule(rule_type="manual")
        mock_store.save_rule(rule)
        job = SyncJob(connector_config_id=_connector.id, rule_id=rule.id, name="Detail")
        mock_store.save_job(job)

        execution = SyncExecution(job_id=job.id, status="completed", items_new=5)
        mock_store.save_execution(execution)

        resp = client.get(f"/sync/jobs/{job.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["job"]["name"] == "Detail"
        assert len(data["recent_executions"]) == 1

    def test_get_job_not_found(self, client, auth_headers):
        """GET /sync/jobs/{id} with nonexistent ID returns 404."""
        resp = client.get("/sync/jobs/nonexistent", headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_job(self, client, mock_store, _connector, auth_headers):
        """DELETE /sync/jobs/{id} removes job."""
        rule = SyncRule(rule_type="manual")
        mock_store.save_rule(rule)
        job = SyncJob(connector_config_id=_connector.id, rule_id=rule.id, name="ToDelete")
        mock_store.save_job(job)

        resp = client.delete(f"/sync/jobs/{job.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_job_not_found(self, client, auth_headers):
        """DELETE nonexistent job returns 404."""
        resp = client.delete("/sync/jobs/nonexistent", headers=auth_headers)
        assert resp.status_code == 404


# ── Run / Retry Tests ──


class TestRunRetryEndpoints:
    """POST /sync/jobs/{id}/run and POST /sync/jobs/{id}/retry."""

    @pytest.fixture
    def _job_with_connector(self, mock_store, mock_worker, mock_pipeline):
        cfg = SyncConnectorConfig(name="Test", connector_type="local_folder", credentials={"folder_path": "/tmp"})
        mock_store.save_connector(cfg)
        rule = SyncRule(rule_type="manual")
        mock_store.save_rule(rule)
        job = SyncJob(connector_config_id=cfg.id, rule_id=rule.id, name="Test Job")
        mock_store.save_job(job)
        return job

    def test_run_job(self, client, mock_store, _job_with_connector, mock_pipeline, auth_headers):
        """POST /sync/jobs/{id}/run enqueues to worker."""
        resp = client.post(f"/sync/jobs/{_job_with_connector.id}/run", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert "execution_id" in data

    def test_run_job_not_found(self, client, auth_headers):
        """POST /sync/jobs/{id}/run with nonexistent ID returns 404."""
        resp = client.post("/sync/jobs/nonexistent/run", headers=auth_headers)
        assert resp.status_code == 404

    def test_retry_job(self, client, mock_store, _job_with_connector, auth_headers):
        """POST /sync/jobs/{id}/retry creates new execution."""
        failed_exec = SyncExecution(job_id=_job_with_connector.id, status="failed",
                                     error="test error")
        mock_store.save_execution(failed_exec)

        resp = client.post(f"/sync/jobs/{_job_with_connector.id}/retry", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "retrying"
        assert "execution_id" in data

    def test_retry_job_not_found(self, client, auth_headers):
        """POST /sync/jobs/{id}/retry with nonexistent ID returns 404."""
        resp = client.post("/sync/jobs/nonexistent/retry", headers=auth_headers)
        assert resp.status_code == 404

    def test_retry_with_execution_id(self, client, mock_store, _job_with_connector, auth_headers):
        """Retry with specific execution_id."""
        execution = SyncExecution(job_id=_job_with_connector.id, status="failed")
        mock_store.save_execution(execution)

        resp = client.post(
            f"/sync/jobs/{_job_with_connector.id}/retry",
            json={"execution_id": execution.id},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_run_job_creates_execution_in_store(self, client, mock_store, _job_with_connector, auth_headers):
        """Running a job creates an execution record."""
        resp = client.post(f"/sync/jobs/{_job_with_connector.id}/run", headers=auth_headers)
        execution_id = resp.json()["execution_id"]
        execution = mock_store.get_execution(execution_id)
        assert execution is not None
        assert execution.job_id == _job_with_connector.id


# ── History Tests ──


class TestHistoryEndpoint:
    """GET /sync/history."""

    def test_history_empty(self, client, auth_headers):
        """No executions returns empty list."""
        resp = client.get("/sync/history", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["executions"] == []

    def test_history_with_data(self, client, mock_store, auth_headers):
        """History returns recent executions."""
        cfg = SyncConnectorConfig(name="Test", connector_type="feishu", credentials={})
        mock_store.save_connector(cfg)
        rule = SyncRule(rule_type="manual")
        mock_store.save_rule(rule)
        job = SyncJob(connector_config_id=cfg.id, rule_id=rule.id, name="J")
        mock_store.save_job(job)

        for i in range(3):
            execution = SyncExecution(job_id=job.id, status="completed", items_new=5 + i)
            mock_store.save_execution(execution)

        resp = client.get("/sync/history", headers=auth_headers)
        assert resp.status_code == 200
        executions = resp.json()["executions"]
        assert len(executions) == 3

    def test_history_filter_by_connector(self, client, mock_store, auth_headers):
        """History filtered by connector_id."""
        cfg = SyncConnectorConfig(name="C", connector_type="notion", credentials={})
        mock_store.save_connector(cfg)
        rule = SyncRule(rule_type="manual")
        mock_store.save_rule(rule)
        job = SyncJob(connector_config_id=cfg.id, rule_id=rule.id, name="J")
        mock_store.save_job(job)
        execution = SyncExecution(job_id=job.id, status="completed")
        mock_store.save_execution(execution)

        resp = client.get(f"/sync/history?connector_id={cfg.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["executions"]) == 1

    def test_history_limit(self, client, mock_store, auth_headers):
        """History respects limit parameter."""
        cfg = SyncConnectorConfig(name="C", connector_type="rss", credentials={})
        mock_store.save_connector(cfg)
        rule = SyncRule(rule_type="manual")
        mock_store.save_rule(rule)
        job = SyncJob(connector_config_id=cfg.id, rule_id=rule.id, name="J")
        mock_store.save_job(job)

        for i in range(10):
            execution = SyncExecution(job_id=job.id, status="completed")
            mock_store.save_execution(execution)

        resp = client.get("/sync/history?limit=3", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["executions"]) == 3


# ── Stats Tests ──


class TestStatsEndpoint:
    """GET /sync/stats."""

    def test_stats_empty(self, client, auth_headers):
        """Stats with no data returns zeros."""
        resp = client.get("/sync/stats", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_connectors"] == 0
        assert data["enabled_connectors"] == 0
        assert data["active_jobs"] == 0

    def test_stats_with_data(self, client, mock_store, mock_worker, auth_headers):
        """Stats reflects stored data."""
        cfg = SyncConnectorConfig(name="A", connector_type="feishu", credentials={}, enabled=True)
        mock_store.save_connector(cfg)
        cfg2 = SyncConnectorConfig(name="B", connector_type="notion", credentials={}, enabled=False)
        mock_store.save_connector(cfg2)

        resp = client.get("/sync/stats", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_connectors"] == 2
        assert data["enabled_connectors"] == 1
        assert "connectors" in data

    def test_stats_includes_queue_depth(self, client, mock_store, mock_worker, auth_headers):
        """Stats includes queue_depth."""
        resp = client.get("/sync/stats", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "queue_depth" in data
        assert isinstance(data["queue_depth"], int)


# ── Test Connection Endpoint ──


class TestConnectionEndpoint:
    """POST /sync/connectors/{id}/test."""

    def test_test_connection_not_found(self, client, auth_headers):
        """Test connection for nonexistent connector returns 404."""
        resp = client.post("/sync/connectors/nonexistent/test", headers=auth_headers)
        assert resp.status_code == 404

    def test_test_connection_connector_not_registered(self, client, mock_store, auth_headers):
        """Test connection for an unregistered connector type returns 400."""
        cfg = SyncConnectorConfig(name="Bad", connector_type="nonexistent_type_xyz", credentials={})
        mock_store.save_connector(cfg)

        resp = client.post(f"/sync/connectors/{cfg.id}/test", headers=auth_headers)
        assert resp.status_code >= 400


# ═══════════════════════════════════════════
# Security Tests — auth + credential redaction + allowlist
# ═══════════════════════════════════════════


class TestSyncSecurityUnauthenticated:
    """所有 sync 端点无认证时应返回 401。"""

    READ_ENDPOINTS = [
        ("GET", "/sync/connectors"),
        ("GET", "/sync/jobs"),
        ("GET", "/sync/history"),
        ("GET", "/sync/stats"),
    ]
    WRITE_ENDPOINTS = [
        ("POST", "/sync/connectors"),
        ("DELETE", "/sync/connectors/fake-id"),
        ("POST", "/sync/connectors/fake-id/test"),
        ("POST", "/sync/jobs"),
        ("DELETE", "/sync/jobs/fake-id"),
        ("POST", "/sync/jobs/fake-id/run"),
        ("POST", "/sync/jobs/fake-id/retry"),
    ]

    @pytest.mark.parametrize("method,path", READ_ENDPOINTS + WRITE_ENDPOINTS)
    def test_sync_endpoint_401_without_auth(self, client, method, path):
        """无 token 访问任意 sync 端点应返回 401。"""
        r = client.request(method, path)
        assert r.status_code == 401, (
            f"{method} {path}: expected 401, got {r.status_code}: {r.text[:200]}"
        )

    @pytest.mark.parametrize("method,path", READ_ENDPOINTS + WRITE_ENDPOINTS)
    def test_sync_endpoint_200_with_auth(self, client, auth_headers, method, path):
        """有 admin token 访问 sync 端点应返回 200（非 401/403）。"""
        r = client.request(method, path, headers=auth_headers)
        assert r.status_code not in (401, 403), (
            f"{method} {path}: expected pass, got {r.status_code}: {r.text[:200]}"
        )


class TestCredentialRedaction:
    """敏感 credentials 不能泄露在 API 响应中。"""

    def test_connector_response_excludes_credentials(self, client, auth_headers, mock_store):
        """创建 connector 后列表响应不包含 credentials 字段。"""
        client.post("/sync/connectors", json={
            "name": "Secret Conn",
            "connector_type": "feishu",
            "credentials": {
                "app_id": "my_app",
                "app_secret": "super_secret_123",
                "private_key": "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----",
                "folder_path": "/data/docs",
            },
        }, headers=auth_headers)

        # 列表端点不应暴露 credentials
        r = client.get("/sync/connectors", headers=auth_headers)
        assert r.status_code == 200
        for conn in r.json()["connectors"]:
            assert "credentials" not in conn, (
                f"credentials leaked in connector list: {list(conn.keys())}"
            )
            assert "app_secret" not in str(conn), "secret value leaked"

    def test_redact_helper_strips_sensitive_keys(self):
        """_redact_credentials 应遮蔽已知敏感字段。"""
        from src.api.sync_router import _redact_credentials

        input_creds = {
            "app_id": "my_app",
            "app_secret": "should_be_hidden",
            "api_key": "secret_key_123",
            "access_token": "token_value",
            "bearer_token": "bearer_value",
            "client_secret": "cs_value",
            "password": "p4ssw0rd",
            "private_key": "pk_value",
            "signing_secret": "sign_secret",
            "connection_string": "conn_str",
            "folder_path": "/data/docs",    # not sensitive
            "host": "localhost",            # not sensitive
            "port": 8080,                   # not sensitive
            "nested": {
                "api_key": "nested_key",
                "name": "visible_name",
            },
        }

        redacted = _redact_credentials(input_creds)

        # 敏感字段应被遮蔽
        assert redacted["app_secret"] == "********"
        assert redacted["api_key"] == "********"
        assert redacted["access_token"] == "********"
        assert redacted["password"] == "********"
        assert redacted["client_secret"] == "********"
        assert redacted["private_key"] == "********"
        assert redacted["connection_string"] == "********"

        # 非敏感字段应保留
        assert redacted["folder_path"] == "/data/docs"
        assert redacted["host"] == "localhost"
        assert redacted["port"] == 8080

        # 嵌套字典应递归遮蔽
        assert redacted["nested"]["api_key"] == "********"
        assert redacted["nested"]["name"] == "visible_name"
