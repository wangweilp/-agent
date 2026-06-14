from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.middleware import require_auth
from src.api.runtime_admin_router import create_runtime_admin_router
from src.core.auth import TokenPayload, WorkspaceRole
from src.open_platform.runtime_governance_summary import (
    BOUNDARY_STATEMENT,
    build_runtime_governance_summary,
)


def _admin_payload():
    return TokenPayload(
        user_id="admin-test",
        workspace_id="tenant-test",
        role=WorkspaceRole.ADMIN,
        email="admin@example.test",
        is_super_admin=True,
    )


def test_runtime_governance_summary_is_metadata_only_and_fail_closed():
    data = build_runtime_governance_summary()

    assert data["current_mode"] == "metadata-only / simulation"
    assert data["production_sandbox"] == "disabled"
    assert data["default_policy"] == "deny by default / fail closed"
    assert data["boundary_statement"] == BOUNDARY_STATEMENT
    gate = data["modules"]["production_sandbox_gate"]
    assert gate["enabled"] is False
    assert gate["gate_result"]["runtime_enabled"] is False
    assert gate["gate_result"]["third_party_execution_allowed"] is False
    assert data["modules"]["package_download_worker_gate"]["enabled"] is False
    assert data["modules"]["artifact_materialization_gate"]["enabled"] is False


def test_runtime_admin_governance_summary_endpoint_returns_read_only_payload():
    app = FastAPI()
    app.include_router(create_runtime_admin_router(runtime_store=None))
    app.dependency_overrides[require_auth] = _admin_payload

    res = TestClient(app).get("/admin/runtime/governance/summary")

    assert res.status_code == 200
    data = res.json()
    assert data["runtime_governance_status"] == "metadata_only_control_plane"
    assert data["modules"]["sandbox_execution_record"]["mode"] == "simulation / metadata-only"
    assert data["modules"]["production_sandbox_gate"]["status"] == "disabled"
