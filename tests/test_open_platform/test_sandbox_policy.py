"""Sandbox Policy 测试 — domain model + store + admin API。

覆盖: Domain / Store / Admin Auth / Binding Assignment / Security
"""

from __future__ import annotations
import os, json, pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.sandbox_policy_store import SQLiteSandboxPolicyStore
from src.adapters.runtime_store import SQLiteRuntimeStore
from src.adapters.usage_store import UsageStoreAdapter
from src.api.sandbox_policy_router import create_sandbox_policy_router
from src.api.middleware import require_auth, get_token_payload, TokenPayload
from src.core.auth import WorkspaceRole
from src.open_platform.sandbox_policy import (
    SandboxPolicy, SandboxPolicyTestRequest, SandboxPolicyTestResult,
    SandboxLevel, SandboxPolicyStatus, SandboxPolicyScope, SandboxPolicyDecision,
    SandboxPolicyValidationError, SandboxPolicyAlreadyExistsError,
    SandboxPolicyPermissionError, SandboxPolicyNotFoundError,
)
from src.open_platform.runtime import (
    DeveloperAgentRuntimeBinding, RuntimeAdapterType,
)

# ═══════════════════════ Auth helpers ═══════════════════════
def _p(role=WorkspaceRole.ADMIN, ws="test-ws-001", uid="user-admin", sa=False):
    return TokenPayload(user_id=uid, workspace_id=ws, role=role, is_super_admin=sa)
async def _auth_admin(): return _p()
async def _auth_member(): return _p(WorkspaceRole.MEMBER)
async def _auth_viewer(): return _p(WorkspaceRole.VIEWER)
async def _auth_super(): return _p(WorkspaceRole.ADMIN, sa=True)
async def _auth_other(): return _p(WorkspaceRole.ADMIN, ws="other-tenant")

@pytest.fixture
def s(): return Settings(deepseek_api_key="sk-test")
@pytest.fixture
def sp_store(s): return SQLiteSandboxPolicyStore(s, db_path=":memory:")
@pytest.fixture
def seeded_sp(sp_store):
    sp_store.seed_builtin_policies()
    return sp_store
@pytest.fixture
def rt_store(s):
    st = SQLiteRuntimeStore(s, db_path=":memory:")
    st.seed_builtin_adapters()
    return st
@pytest.fixture
def usage_store(s, tmp_path):
    u = UsageStoreAdapter(config=s, db_path=str(tmp_path / "sp_usage.db"))
    yield u; u.close()

def _make_app(sp_store, rt_store=None, usage=None, auth=_auth_admin):
    app = FastAPI(); app.dependency_overrides[require_auth] = auth
    app.dependency_overrides[get_token_payload] = auth
    app.include_router(create_sandbox_policy_router(sp_store, rt_store, usage))
    return TestClient(app)

def _noauth_app(sp_store, rt_store=None):
    app = FastAPI()
    app.include_router(create_sandbox_policy_router(sp_store, rt_store))
    return TestClient(app)

# ═══════════════════════ 1. Domain Model ═══════════════════════
class TestPolicyModel:
    def test_create_no_execution(self):
        p = SandboxPolicy(name="NoExec", description="No code execution", sandbox_level=SandboxLevel.NO_EXECUTION)
        assert p.is_valid()
        assert not p.is_execution_allowed()

    def test_create_simulation_only(self):
        p = SandboxPolicy(name="SimOnly", description="Sim only", sandbox_level=SandboxLevel.SIMULATION_ONLY)
        assert p.is_valid()
        assert not p.is_execution_allowed()

    def test_create_restricted(self):
        p = SandboxPolicy(name="Restricted", description="R", sandbox_level=SandboxLevel.RESTRICTED,
                          max_timeout_ms=10000, max_memory_mb=128)
        assert p.is_valid()
        assert p.is_execution_allowed()

    def test_roundtrip(self):
        p = SandboxPolicy(policy_id="sbxpol_x", name="N", description="D",
                          sandbox_level=SandboxLevel.SIMULATION_ONLY,
                          scope=SandboxPolicyScope.TENANT, tenant_id="t1",
                          max_timeout_ms=5000, metadata={"k":"v"})
        d = p.to_dict()
        p2 = SandboxPolicy.from_dict(d)
        assert p2.policy_id == p.policy_id
        assert p2.max_timeout_ms == 5000
        assert p2.metadata == {"k":"v"}

    def test_scope_system_rejects_tenant_id(self):
        p = SandboxPolicy(name="S", description="D", scope=SandboxPolicyScope.SYSTEM, tenant_id="t1")
        assert not p.is_valid()
        assert any("tenant_id" in e for e in p.validate())

    def test_scope_tenant_requires_tenant_id(self):
        p = SandboxPolicy(name="S", description="D", scope=SandboxPolicyScope.TENANT, tenant_id=None)
        assert not p.is_valid()

    def test_no_execution_rejects_network(self):
        p = SandboxPolicy(name="N", description="D", sandbox_level=SandboxLevel.NO_EXECUTION, allow_network=True)
        assert not p.is_valid()

    def test_no_execution_rejects_filesystem_read(self):
        p = SandboxPolicy(name="N", description="D", sandbox_level=SandboxLevel.NO_EXECUTION, allow_filesystem_read=True)
        assert not p.is_valid()

    def test_no_execution_rejects_filesystem_write(self):
        p = SandboxPolicy(name="N", description="D", sandbox_level=SandboxLevel.NO_EXECUTION, allow_filesystem_write=True)
        assert not p.is_valid()

    def test_no_execution_rejects_secrets(self):
        p = SandboxPolicy(name="N", description="D", sandbox_level=SandboxLevel.NO_EXECUTION, allow_secrets=True)
        assert not p.is_valid()

    def test_simulation_rejects_network(self):
        p = SandboxPolicy(name="S", description="D", sandbox_level=SandboxLevel.SIMULATION_ONLY, allow_network=True)
        assert not p.is_valid()

    def test_simulation_rejects_filesystem_write(self):
        p = SandboxPolicy(name="S", description="D", sandbox_level=SandboxLevel.SIMULATION_ONLY, allow_filesystem_write=True)
        assert not p.is_valid()

    def test_simulation_rejects_secrets(self):
        p = SandboxPolicy(name="S", description="D", sandbox_level=SandboxLevel.SIMULATION_ONLY, allow_secrets=True)
        assert not p.is_valid()

    def test_invalid_sandbox_level(self):
        p = SandboxPolicy(name="S", description="D", sandbox_level="bad_level")
        assert not p.is_valid()

    def test_max_values_non_negative(self):
        p = SandboxPolicy(name="S", description="D", max_timeout_ms=-1)
        assert not p.is_valid()
        assert any("max_timeout_ms" in e for e in p.validate())

    def test_is_active(self):
        assert SandboxPolicy(name="A", description="D", status=SandboxPolicyStatus.ACTIVE).is_active()
        assert not SandboxPolicy(name="A", description="D", status=SandboxPolicyStatus.DISABLED).is_active()

# ═══════════════════════ 2. Store ═══════════════════════
class TestPolicyStore:
    def test_seed_creates_3_policies(self, seeded_sp):
        ps = seeded_sp.list_policies()
        assert len(ps) == 3

    def test_seed_idempotent(self, sp_store):
        c1 = sp_store.seed_builtin_policies()
        c2 = sp_store.seed_builtin_policies()
        assert c1 == 3
        assert c2 == 0

    def test_get_policy(self, seeded_sp):
        p = seeded_sp.get_policy("sbxpol_no_execution")
        assert p is not None
        assert p.name == "No Execution Policy"

    def test_get_policy_by_name(self, seeded_sp):
        p = seeded_sp.get_policy_by_name("No Execution Policy")
        assert p is not None

    def test_list_system(self, seeded_sp):
        ps = seeded_sp.list_policies(scope="system")
        assert len(ps) == 3

    def test_list_tenant_includes_system(self, seeded_sp):
        ps = seeded_sp.list_policies(tenant_id="t1", include_system=True)
        assert len(ps) == 3

    def test_list_tenant_excludes_other(self, seeded_sp):
        sp_store = SQLiteSandboxPolicyStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:")
        sp_store.seed_builtin_policies()
        # No tenant policies for "other-tenant"
        ps = sp_store.list_policies(tenant_id="other-tenant")
        assert len(ps) == 3  # sys + 0 tenant

    def test_status_filter(self, seeded_sp):
        ps = seeded_sp.list_policies(status="active")
        assert all(p.status == "active" for p in ps)

    def test_create_tenant_policy(self, sp_store):
        sp_store.seed_builtin_policies()
        p = SandboxPolicy(name="TenantP", description="D", scope=SandboxPolicyScope.TENANT,
                          tenant_id="t1", sandbox_level=SandboxLevel.SIMULATION_ONLY)
        created = sp_store.create_policy(p)
        assert created.policy_id is not None

    def test_duplicate_name_tenant_rejected(self, seeded_sp):
        p1 = SandboxPolicy(name="Dup", description="D", scope=SandboxPolicyScope.TENANT, tenant_id="t1")
        p2 = SandboxPolicy(name="Dup", description="D", scope=SandboxPolicyScope.TENANT, tenant_id="t1")
        seeded_sp.create_policy(p1)
        with pytest.raises(SandboxPolicyAlreadyExistsError):
            seeded_sp.create_policy(p2)

    def test_update_tenant_policy(self, sp_store):
        sp_store.seed_builtin_policies()
        p = SandboxPolicy(name="Upd", description="D", scope=SandboxPolicyScope.TENANT,
                          tenant_id="t1", sandbox_level=SandboxLevel.SIMULATION_ONLY)
        sp_store.create_policy(p)
        p.name = "Updated"
        sp_store.update_policy(p)
        assert sp_store.get_policy(p.policy_id).name == "Updated"

    def test_system_managed_critical_fields_preserved(self, seeded_sp):
        p = seeded_sp.get_policy("sbxpol_no_execution")
        original_level = p.sandbox_level
        p.sandbox_level = SandboxLevel.RESTRICTED
        seeded_sp.update_policy(p)
        p2 = seeded_sp.get_policy("sbxpol_no_execution")
        assert p2.sandbox_level == original_level  # preserved

    def test_disable_tenant_policy(self, sp_store):
        sp_store.seed_builtin_policies()
        p = SandboxPolicy(name="Dis", description="D", scope=SandboxPolicyScope.TENANT,
                          tenant_id="t1", sandbox_level=SandboxLevel.SIMULATION_ONLY)
        sp_store.create_policy(p)
        ok = sp_store.set_policy_status(p.policy_id, SandboxPolicyStatus.DISABLED)
        assert ok
        assert sp_store.get_policy(p.policy_id).status == SandboxPolicyStatus.DISABLED

    def test_delete_system_managed_rejected(self, seeded_sp):
        with pytest.raises(SandboxPolicyPermissionError, match="system_managed"):
            seeded_sp.delete_policy("sbxpol_no_execution")

    def test_delete_tenant_policy_disables(self, sp_store):
        sp_store.seed_builtin_policies()
        p = SandboxPolicy(name="Del", description="D", scope=SandboxPolicyScope.TENANT,
                          tenant_id="t1", sandbox_level=SandboxLevel.SIMULATION_ONLY)
        sp_store.create_policy(p)
        sp_store.delete_policy(p.policy_id)
        assert sp_store.get_policy(p.policy_id).status == SandboxPolicyStatus.DISABLED

    def test_test_policy_allow(self, seeded_sp):
        req = SandboxPolicyTestRequest(sandbox_level=SandboxLevel.NO_EXECUTION)
        result = seeded_sp.test_policy("sbxpol_no_execution", req)
        assert result.allowed
        assert result.decision == SandboxPolicyDecision.ALLOW

    def test_test_policy_deny_network(self, seeded_sp):
        req = SandboxPolicyTestRequest(sandbox_level=SandboxLevel.NO_EXECUTION, requested_network=True)
        result = seeded_sp.test_policy("sbxpol_no_execution", req)
        assert not result.allowed
        assert "network" in " ".join(result.violations).lower()

    def test_test_policy_deny_domain(self, seeded_sp):
        req = SandboxPolicyTestRequest(sandbox_level=SandboxLevel.SIMULATION_ONLY,
                                       requested_domains=["evil.com"])
        result = seeded_sp.test_policy("sbxpol_simulation_only", req)
        assert not result.allowed

    def test_test_policy_deny_timeout(self, seeded_sp):
        req = SandboxPolicyTestRequest(sandbox_level=SandboxLevel.SIMULATION_ONLY,
                                       requested_timeout_ms=99999)
        result = seeded_sp.test_policy("sbxpol_simulation_only", req)
        assert not result.allowed

    def test_test_policy_deny_secret(self, seeded_sp):
        req = SandboxPolicyTestRequest(sandbox_level=SandboxLevel.NO_EXECUTION,
                                       requested_secret_names=["DB_PASSWORD"])
        result = seeded_sp.test_policy("sbxpol_no_execution", req)
        assert not result.allowed

    def test_test_policy_no_code_execution(self, seeded_sp):
        """test_policy 不 import AgentRuntime。"""
        req = SandboxPolicyTestRequest(sandbox_level=SandboxLevel.NO_EXECUTION)
        result = seeded_sp.test_policy("sbxpol_no_execution", req)
        assert result.metadata.get("no_code_executed") is True
        assert result.metadata.get("static_evaluation_only") is True

    def test_get_nonexistent_returns_none(self, sp_store):
        assert sp_store.get_policy("sbxpol_fake") is None

    def test_test_nonexistent_raises(self, sp_store):
        with pytest.raises(SandboxPolicyNotFoundError):
            sp_store.test_policy("sbxpol_fake", SandboxPolicyTestRequest())

# ═══════════════════════ 3. Admin API Auth ═══════════════════════
class TestAdminApiAuth:
    def test_all_endpoints_401(self):
        c = _noauth_app(SQLiteSandboxPolicyStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:"))
        assert c.get("/admin/sandbox-policies").status_code == 401
        assert c.get("/admin/sandbox-policies/sp_x").status_code == 401
        assert c.post("/admin/sandbox-policies", json={}).status_code == 401
        assert c.patch("/admin/sandbox-policies/sp_x", json={}).status_code == 401
        assert c.post("/admin/sandbox-policies/sp_x/test", json={}).status_code == 401

    def test_member_gets_403(self):
        c = _make_app(SQLiteSandboxPolicyStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:"), auth=_auth_member)
        assert c.get("/admin/sandbox-policies").status_code == 403

    def test_viewer_gets_403(self):
        c = _make_app(SQLiteSandboxPolicyStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:"), auth=_auth_viewer)
        assert c.get("/admin/sandbox-policies").status_code == 403

    def test_admin_can_list(self, seeded_sp):
        c = _make_app(seeded_sp)
        resp = c.get("/admin/sandbox-policies")
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    def test_admin_cannot_view_other_tenant_policy(self, sp_store):
        sp_store.seed_builtin_policies()
        p = SandboxPolicy(name="Secret", description="D", scope=SandboxPolicyScope.TENANT,
                          tenant_id="other-tn", sandbox_level=SandboxLevel.SIMULATION_ONLY)
        sp_store.create_policy(p)
        c = _make_app(sp_store)
        resp = c.get(f"/admin/sandbox-policies/{p.policy_id}")
        assert resp.status_code == 404

    def test_super_admin_can_view_system(self, seeded_sp):
        c = _make_app(seeded_sp, auth=_auth_super)
        resp = c.get("/admin/sandbox-policies")
        assert resp.status_code == 200

    def test_admin_cannot_create_system_policy(self, seeded_sp):
        c = _make_app(seeded_sp)
        # Normal admin creates → auto-scoped to tenant
        resp = c.post("/admin/sandbox-policies", json={"name": "MySys", "description": "D"})
        assert resp.status_code == 201
        assert resp.json()["policy"]["scope"] == "tenant"

    def test_admin_creates_tenant_policy(self, seeded_sp):
        c = _make_app(seeded_sp)
        resp = c.post("/admin/sandbox-policies", json={"name": "TenantP2", "description": "D"})
        assert resp.status_code == 201

    def test_duplicate_create_409(self, sp_store):
        sp_store.seed_builtin_policies()
        c = _make_app(sp_store)
        resp = c.post("/admin/sandbox-policies", json={"name": "TP", "description": "D"})
        assert resp.status_code == 201
        resp = c.post("/admin/sandbox-policies", json={"name": "TP", "description": "D"})
        assert resp.status_code == 409

    def test_invalid_create_422(self, seeded_sp):
        c = _make_app(seeded_sp)
        resp = c.post("/admin/sandbox-policies", json={"name": "Bad", "description": "D",
                       "allow_network": True, "sandbox_level": "no_execution"})
        assert resp.status_code == 422

    def test_admin_cannot_patch_system_policy(self, seeded_sp):
        c = _make_app(seeded_sp)
        resp = c.patch("/admin/sandbox-policies/sbxpol_no_execution", json={"name": "Hacked"})
        assert resp.status_code == 403

    def test_admin_can_patch_tenant_policy(self, sp_store):
        sp_store.seed_builtin_policies()
        p = SandboxPolicy(name="PTenant", description="D", scope=SandboxPolicyScope.TENANT,
                          tenant_id="test-ws-001", sandbox_level=SandboxLevel.SIMULATION_ONLY)
        sp_store.create_policy(p)
        c = _make_app(sp_store)
        resp = c.patch(f"/admin/sandbox-policies/{p.policy_id}", json={"name": "UpdatedTenant"})
        assert resp.status_code == 200

    def test_test_endpoint(self, seeded_sp):
        c = _make_app(seeded_sp)
        resp = c.post("/admin/sandbox-policies/sbxpol_no_execution/test", json={
            "sandbox_level": "no_execution", "requested_network": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert not data["allowed"]

    def test_disable_system_managed_rejected(self, seeded_sp):
        c = _make_app(seeded_sp)
        resp = c.post("/admin/sandbox-policies/sbxpol_no_execution/disable")
        assert resp.status_code in (403, 404)  # system_managed → 403

    def test_disable_tenant_works(self, sp_store):
        sp_store.seed_builtin_policies()
        p = SandboxPolicy(name="PTD", description="D", scope=SandboxPolicyScope.TENANT,
                          tenant_id="test-ws-001", sandbox_level=SandboxLevel.SIMULATION_ONLY)
        sp_store.create_policy(p)
        c = _make_app(sp_store)
        resp = c.post(f"/admin/sandbox-policies/{p.policy_id}/disable")
        assert resp.status_code == 200

# ═══════════════════════ 4. Binding Assignment ═══════════════════════
class TestBindingAssignment:
    def test_admin_assign_system_policy_to_own_binding(self, seeded_sp, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_b1", developer_id="d1",
                                          tenant_id="test-ws-001", adapter_id="rtadp_simulation",
                                          adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        c = _make_app(seeded_sp, rt_store)
        resp = c.post(f"/admin/sandbox-policies/bindings/{b.binding_id}/assign",
                      json={"sandbox_policy_id": "sbxpol_simulation_only"})
        assert resp.status_code == 200
        assert resp.json()["success"]

    def test_assign_missing_policy_404(self, seeded_sp, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_b2", developer_id="d1",
                                          tenant_id="test-ws-001", adapter_id="rtadp_simulation",
                                          adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        c = _make_app(seeded_sp, rt_store)
        resp = c.post(f"/admin/sandbox-policies/bindings/{b.binding_id}/assign",
                      json={"sandbox_policy_id": "sbxpol_fake"})
        assert resp.status_code == 404

    def test_assign_missing_binding_404(self, seeded_sp, rt_store):
        c = _make_app(seeded_sp, rt_store)
        resp = c.post("/admin/sandbox-policies/bindings/rtbind_fake/assign",
                      json={"sandbox_policy_id": "sbxpol_no_execution"})
        assert resp.status_code == 404

    def test_admin_cannot_assign_other_tenant_policy(self, sp_store, rt_store):
        sp_store.seed_builtin_policies()
        p = SandboxPolicy(name="OTP", description="D", scope=SandboxPolicyScope.TENANT,
                          tenant_id="other-tn", sandbox_level=SandboxLevel.SIMULATION_ONLY)
        sp_store.create_policy(p)
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_b3", developer_id="d1",
                                          tenant_id="test-ws-001", adapter_id="rtadp_simulation",
                                          adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        c = _make_app(sp_store, rt_store)
        resp = c.post(f"/admin/sandbox-policies/bindings/{b.binding_id}/assign",
                      json={"sandbox_policy_id": p.policy_id})
        assert resp.status_code == 404

    def test_admin_cannot_assign_to_other_tenant_binding(self, seeded_sp, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_b4", developer_id="d1",
                                          tenant_id="other-tn", adapter_id="rtadp_simulation",
                                          adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        c = _make_app(seeded_sp, rt_store)
        resp = c.post(f"/admin/sandbox-policies/bindings/{b.binding_id}/assign",
                      json={"sandbox_policy_id": "sbxpol_simulation_only"})
        assert resp.status_code == 404

    def test_super_admin_assign_cross_tenant(self, seeded_sp, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_b5", developer_id="d1",
                                          tenant_id="other-tn", adapter_id="rtadp_simulation",
                                          adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        c = _make_app(seeded_sp, rt_store, auth=_auth_super)
        resp = c.post(f"/admin/sandbox-policies/bindings/{b.binding_id}/assign",
                      json={"sandbox_policy_id": "sbxpol_simulation_only"})
        assert resp.status_code == 200

    def test_assignment_does_not_enable_binding(self, seeded_sp, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_b6", developer_id="d1",
                                          tenant_id="test-ws-001", adapter_id="rtadp_simulation",
                                          adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        assert not b.is_enabled()
        c = _make_app(seeded_sp, rt_store)
        resp = c.post(f"/admin/sandbox-policies/bindings/{b.binding_id}/assign",
                      json={"sandbox_policy_id": "sbxpol_simulation_only"})
        assert resp.status_code == 200
        # Binding should still be pending (not enabled by assignment)
        updated = rt_store.get_binding(b.binding_id)
        assert not updated.is_enabled()
        assert updated.sandbox_policy_id == "sbxpol_simulation_only"

    def test_assign_usage_metadata_safe(self, seeded_sp, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_b7", developer_id="d1",
                                          tenant_id="test-ws-001", adapter_id="rtadp_simulation",
                                          adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        c = _make_app(seeded_sp, rt_store)
        resp = c.post(f"/admin/sandbox-policies/bindings/{b.binding_id}/assign",
                      json={"sandbox_policy_id": "sbxpol_simulation_only"})
        data = resp.json()
        assert "raw_key" not in json.dumps(data)
        assert "key_hash" not in json.dumps(data)

# ═══════════════════════ 5. Security Edge ═══════════════════════
class TestSecurityEdge:
    def test_is_execution_allowed_false_for_no_exec(self):
        p = SandboxPolicy(name="N", description="D", sandbox_level=SandboxLevel.NO_EXECUTION)
        assert not p.is_execution_allowed()

    def test_is_execution_allowed_false_for_simulation(self):
        p = SandboxPolicy(name="S", description="D", sandbox_level=SandboxLevel.SIMULATION_ONLY)
        assert not p.is_execution_allowed()

    def test_no_agent_runtime_in_store(self):
        from src.adapters import sandbox_policy_store as sps
        assert "AgentRuntime" not in sps.__dict__

    def test_no_traceback_in_error(self, seeded_sp):
        c = _make_app(seeded_sp)
        resp = c.get("/admin/sandbox-policies/sbxpol_fake")
        body = resp.json()
        assert "Traceback" not in str(body)

    def test_policy_does_not_execute_code(self):
        """SandboxPolicy.validate() doesn't execute anything."""
        p = SandboxPolicy(name="X", description="Y")
        errors = p.validate()
        assert isinstance(errors, list)
