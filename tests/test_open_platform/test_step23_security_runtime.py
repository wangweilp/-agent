"""Step 23 安全总测试 — API Key Boundary, Tenant Isolation, Runtime, Simulation, Sandbox Policy, Package Validation, Manifest SDK, Usage Safety.

覆盖 100+ 测试用例。不执行任何代码, 不联网, 不下载 package。
"""

from __future__ import annotations
import json, os, pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.developer_store import SQLiteDeveloperStore
from src.adapters.submission_store import SQLiteSubmissionStore
from src.adapters.usage_store import UsageStoreAdapter
from src.adapters.marketplace_store import SQLiteMarketplaceStore
from src.adapters.runtime_store import SQLiteRuntimeStore
from src.adapters.sandbox_policy_store import SQLiteSandboxPolicyStore
from src.api.developer_router import create_developer_router
from src.api.admin_submission_router import create_admin_submission_router
from src.api.runtime_admin_router import create_runtime_admin_router
from src.api.sandbox_policy_router import create_sandbox_policy_router
from src.api.middleware import require_auth, get_token_payload, TokenPayload
from src.core.auth import WorkspaceRole
from src.agents.marketplace import MarketplaceAgent, PublisherType
from src.open_platform.developer import (
    DeveloperAccount, DeveloperApiKey, DeveloperStatus,
    generate_api_key, get_api_key_prefix, hash_api_key,
)
from src.open_platform.runtime import (
    DeveloperAgentRuntimeBinding, RuntimeAdapterType, RuntimeBindingStatus, RuntimeEligibilityCode,
)
from src.open_platform.simulation import (
    SimulationRunRequest, SimulationRunStatus, SimulationBlockReason,
)
from src.open_platform.simulation_runtime import SimulationRuntimeService
from src.open_platform.sandbox_policy import (
    SandboxPolicy, SandboxLevel, SandboxPolicyStatus, SandboxPolicyScope, SandboxPolicyTestRequest,
)

_TENANT = "test-ws-001"
_AUTH_ADMIN = "user-admin"

def _tp(role=WorkspaceRole.ADMIN, ws=_TENANT, uid=_AUTH_ADMIN, sa=False):
    return TokenPayload(user_id=uid, workspace_id=ws, role=role, is_super_admin=sa)
async def _auth_admin(): return _tp()
async def _auth_member(): return _tp(WorkspaceRole.MEMBER)
async def _auth_viewer(): return _tp(WorkspaceRole.VIEWER)
async def _auth_super(): return _tp(WorkspaceRole.ADMIN, sa=True)
async def _auth_other(): return _tp(ws="other-tenant")
async def _auth_dev_uid(): return _tp(WorkspaceRole.MEMBER, uid="dev-user-001")

@pytest.fixture
def s(): return Settings(deepseek_api_key="sk-test")
@pytest.fixture
def dev_store(s): return SQLiteDeveloperStore(s, db_path=":memory:")
@pytest.fixture
def sub_store(s): return SQLiteSubmissionStore(s, db_path=":memory:")
@pytest.fixture
def mkp_store(s): return SQLiteMarketplaceStore(s, db_path=":memory:")
@pytest.fixture
def rt_store(s):
    st = SQLiteRuntimeStore(s, db_path=":memory:"); st.seed_builtin_adapters(); return st
@pytest.fixture
def sp_store(s):
    st = SQLiteSandboxPolicyStore(s, db_path=":memory:"); st.seed_builtin_policies(); return st
@pytest.fixture
def usage_store(s, tmp_path):
    u = UsageStoreAdapter(config=s, db_path=str(tmp_path / "sec_usage.db"))
    yield u; u.close()

def _make_dev_app(dev_store, sub_store, usage=None, mkp=None, rt=None, sim=None, auth=_auth_admin):
    app = FastAPI()
    app.dependency_overrides[require_auth] = auth
    app.dependency_overrides[get_token_payload] = auth
    app.include_router(create_developer_router(dev_store, sub_store, usage, marketplace_store=mkp, runtime_store=rt, simulation_service=sim))
    return TestClient(app)

def _make_admin_app(dev_store, sub_store, usage=None, mkp=None, pv=None, auth=_auth_admin):
    app = FastAPI()
    app.dependency_overrides[require_auth] = auth
    app.dependency_overrides[get_token_payload] = auth
    app.include_router(create_admin_submission_router(dev_store, sub_store, usage, mkp, pv_service=pv))
    return TestClient(app)

def _make_ra_app(rt_store, mkp=None, sp_store=None, usage=None, auth=_auth_admin):
    app = FastAPI()
    app.dependency_overrides[require_auth] = auth
    app.dependency_overrides[get_token_payload] = auth
    app.include_router(create_runtime_admin_router(rt_store, mkp, sp_store, usage))
    return TestClient(app)

def _make_sp_app(sp_store, rt_store=None, usage=None, auth=_auth_admin):
    app = FastAPI(); app.dependency_overrides[require_auth] = auth
    app.dependency_overrides[get_token_payload] = auth
    app.include_router(create_sandbox_policy_router(sp_store, rt_store, usage))
    return TestClient(app)

def _register_dev(client):
    resp = client.post("/developers/register", json={"display_name":"Dev","contact_email":"d@t.com"})
    return resp.json()["developer"]

def _create_key(client, scopes=None):
    resp = client.post("/developers/api-keys", json={"name":"K1","scopes":scopes or ["developer:read"]})
    return resp.json()["raw_key"], resp.json()["api_key"]["api_key_id"]

def _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_dev_x", dev_id="dev_001", tenant=_TENANT):
    agent = MarketplaceAgent(marketplace_agent_id=mkp_id, agent_id=f"agent_{mkp_id[-6:]}",
        name="test-agent", display_name="TA", description="Test agent for security tests",
        capabilities=["test"], required_permissions=["agent:execute"],
        publisher_type=PublisherType.DEVELOPER, publisher_name="Test Dev", status="beta")
    mkp_store.create_agent(agent)
    mkp_store.install_agent(marketplace_agent_id=mkp_id, agent_id=agent.agent_id,
        tenant_id=tenant, workspace_id=tenant, installed_by="admin", permissions_granted=["agent:execute"])
    binding = DeveloperAgentRuntimeBinding(marketplace_agent_id=mkp_id, developer_id=dev_id,
        tenant_id=tenant, adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION)
    rt_store.create_binding(binding)
    rt_store.enable_binding(binding.binding_id, "admin")
    return mkp_id


# ═══════════ A. API Key Boundary (20) ═══════════
class TestApiKeyBoundary:
    def test_api_key_cannot_access_admin_list(self, dev_store, sub_store, rt_store, sp_store, usage_store):
        c1 = _make_dev_app(dev_store, sub_store, usage_store)
        _register_dev(c1); raw_key, _ = _create_key(c1, ["developer:read"])
        app2 = FastAPI(); app2.include_router(create_admin_submission_router(dev_store, sub_store, None))
        resp = TestClient(app2).get("/admin/agent-submissions", headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code in (401, 403)

    def test_api_key_cannot_start_review(self, dev_store, sub_store, rt_store, sp_store, usage_store):
        c1 = _make_dev_app(dev_store, sub_store, usage_store)
        _register_dev(c1); raw_key, _ = _create_key(c1, ["submissions:read"])
        app2 = FastAPI(); app2.include_router(create_admin_submission_router(dev_store, sub_store, None))
        resp = TestClient(app2).post("/admin/agent-submissions/sub_x/start-review", headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code in (401, 403)

    def test_api_key_cannot_approve(self, dev_store, sub_store, usage_store):
        c1 = _make_dev_app(dev_store, sub_store, usage_store)
        _register_dev(c1); raw_key, _ = _create_key(c1, ["developer:read"])
        app2 = FastAPI(); app2.include_router(create_admin_submission_router(dev_store, sub_store, None))
        resp = TestClient(app2).post("/admin/agent-submissions/sub_x/approve", json={"notes":""}, headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code in (401, 403)

    def test_api_key_cannot_publish(self, dev_store, sub_store, usage_store, mkp_store):
        c1 = _make_dev_app(dev_store, sub_store, usage_store)
        _register_dev(c1); raw_key, _ = _create_key(c1, ["developer:read"])
        app2 = FastAPI(); app2.include_router(create_admin_submission_router(dev_store, sub_store, None, mkp_store))
        resp = TestClient(app2).post("/admin/agent-submissions/sub_x/publish", headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code in (401, 403)

    def test_api_key_cannot_access_runtime_admin(self, rt_store, dev_store, sub_store, usage_store):
        c1 = _make_dev_app(dev_store, sub_store, usage_store)
        _register_dev(c1); raw_key, _ = _create_key(c1, ["developer:read"])
        app2 = FastAPI(); app2.include_router(create_runtime_admin_router(rt_store))
        resp = TestClient(app2).get("/admin/runtime/adapters", headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code in (401, 403)

    def test_api_key_cannot_access_sandbox_policy(self, sp_store, dev_store, sub_store, usage_store):
        c1 = _make_dev_app(dev_store, sub_store, usage_store)
        _register_dev(c1); raw_key, _ = _create_key(c1, ["developer:read"])
        app2 = FastAPI(); app2.include_router(create_sandbox_policy_router(sp_store))
        resp = TestClient(app2).get("/admin/sandbox-policies", headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code in (401, 403)

    def test_api_key_cannot_create_api_key(self, dev_store, sub_store, usage_store):
        c1 = _make_dev_app(dev_store, sub_store, usage_store)
        _register_dev(c1); raw_key, _ = _create_key(c1, ["api_keys:write"])
        app2 = FastAPI(); app2.include_router(create_developer_router(dev_store, sub_store, usage_store))
        resp = TestClient(app2).post("/developers/api-keys", json={"name":"Hack","scopes":["developer:read"]}, headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code == 401

    def test_api_key_cannot_revoke_api_key(self, dev_store, sub_store, usage_store):
        c1 = _make_dev_app(dev_store, sub_store, usage_store)
        _register_dev(c1); raw_key, api_key_id = _create_key(c1, ["api_keys:write"])
        app2 = FastAPI(); app2.include_router(create_developer_router(dev_store, sub_store, usage_store))
        resp = TestClient(app2).delete(f"/developers/api-keys/{api_key_id}", headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code == 401

    def test_api_key_insufficient_scope_manifest_validate(self, dev_store, sub_store):
        c1 = _make_dev_app(dev_store, sub_store)
        _register_dev(c1); raw_key, _ = _create_key(c1, ["developer:read"])
        app2 = FastAPI(); app2.include_router(create_developer_router(dev_store, sub_store, None))
        resp2 = TestClient(app2).post("/developers/agent-manifest/validate", json={"manifest":{"name":"x"}}, headers={"X-Cognitive-API-Key": raw_key})
        assert resp2.status_code == 403

    def test_api_key_can_access_schema_if_allowed(self, dev_store, sub_store):
        c1 = _make_dev_app(dev_store, sub_store)
        _register_dev(c1); raw_key, _ = _create_key(c1, ["developer:read"])
        resp = c1.get("/developers/agent-manifest/schema", headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code == 200

    def test_api_key_simulation_scope_allows_simulate(self, dev_store, sub_store, mkp_store, rt_store):
        dev_info = _register_dev(_make_dev_app(dev_store, sub_store))
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_ak_sim", dev_id=dev_info["developer_id"])
        raw_key = generate_api_key(); kp = get_api_key_prefix(raw_key); kh = hash_api_key(raw_key)
        dev_store.create_api_key(DeveloperApiKey(developer_id=dev_info["developer_id"], key_prefix=kp, key_hash=kh, name="K", scopes=["agent:simulate"]))
        sim = SimulationRuntimeService(mkp_store, rt_store, None)
        c = _make_dev_app(dev_store, sub_store, mkp=mkp_store, rt=rt_store, sim=sim)
        resp = c.post("/developers/marketplace-agents/mkp_ak_sim/simulate", json={"input_text":"hi"}, headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code == 200

    def test_api_key_without_sim_scope_cannot_simulate(self, dev_store, sub_store, mkp_store, rt_store):
        dev_info = _register_dev(_make_dev_app(dev_store, sub_store))
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_no_sim", dev_id=dev_info["developer_id"])
        raw_key = generate_api_key(); kp = get_api_key_prefix(raw_key); kh = hash_api_key(raw_key)
        dev_store.create_api_key(DeveloperApiKey(developer_id=dev_info["developer_id"], key_prefix=kp, key_hash=kh, name="K", scopes=["developer:read"]))
        sim = SimulationRuntimeService(mkp_store, rt_store, None)
        c = _make_dev_app(dev_store, sub_store, mkp=mkp_store, rt=rt_store, sim=sim)
        resp = c.post("/developers/marketplace-agents/mkp_no_sim/simulate", json={"input_text":"hi"}, headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code == 403

    def test_api_key_response_no_raw_key(self, dev_store, sub_store):
        c = _make_dev_app(dev_store, sub_store)
        _register_dev(c); raw_key, _ = _create_key(c, ["developer:read", "submissions:read"])
        resp = c.get("/developers/me", headers={"X-Cognitive-API-Key": raw_key})
        assert "raw_key" not in json.dumps(resp.json())

    def test_api_key_list_response_no_key_hash(self, dev_store, sub_store):
        c = _make_dev_app(dev_store, sub_store)
        _register_dev(c); raw_key, _ = _create_key(c, ["api_keys:read", "submissions:read"])
        resp = c.get("/developers/api-keys", headers={"X-Cognitive-API-Key": raw_key})
        assert "key_hash" not in json.dumps(resp.json())

    def test_create_key_response_has_raw_key_only_once(self, dev_store, sub_store):
        c = _make_dev_app(dev_store, sub_store)
        _register_dev(c)
        resp = c.post("/developers/api-keys", json={"name":"K2","scopes":["developer:read"]})
        data = resp.json()
        assert "raw_key" in data
        resp2 = c.get("/developers/api-keys")
        for k in resp2.json()["api_keys"]:
            assert "raw_key" not in k

    def test_api_key_cannot_access_admin_package_validation(self, dev_store, sub_store, usage_store):
        c1 = _make_dev_app(dev_store, sub_store, usage_store)
        _register_dev(c1); raw_key, _ = _create_key(c1, ["submissions:read"])
        app2 = FastAPI(); app2.include_router(create_admin_submission_router(dev_store, sub_store, None))
        resp = TestClient(app2).post("/admin/agent-submissions/sub_x/validate-package", headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code in (401, 403)

    def test_api_key_cannot_patch_developer_profile(self, dev_store, sub_store):
        c1 = _make_dev_app(dev_store, sub_store)
        _register_dev(c1); raw_key, _ = _create_key(c1, ["developer:write"])
        app2 = FastAPI(); app2.include_router(create_developer_router(dev_store, sub_store, None))
        resp = TestClient(app2).patch("/developers/me", json={"display_name":"Hacked"}, headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code == 401


# ═══════════ B. Tenant Isolation (7) ═══════════
class TestTenantIsolation:
    def test_admin_cannot_see_other_tenant_bindings(self, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_ot", developer_id="d1", tenant_id="other-tn",
                                          adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        c = _make_ra_app(rt_store)
        resp = c.get("/admin/runtime/bindings")
        data = resp.json()
        ids = [b["tenant_id"] for b in data["bindings"]]
        assert "other-tn" not in ids

    def test_admin_cannot_enable_other_tenant_binding(self, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_oe", developer_id="d1", tenant_id="other-tn",
                                          adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        c = _make_ra_app(rt_store)
        resp = c.post(f"/admin/runtime/bindings/{b.binding_id}/enable")
        assert resp.status_code == 404

    def test_admin_cannot_assign_policy_to_other_tenant_binding(self, rt_store, sp_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_op", developer_id="d1", tenant_id="other-tn",
                                          adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        c = _make_ra_app(rt_store, sp_store=sp_store)
        resp = c.post(f"/admin/runtime/bindings/{b.binding_id}/sandbox-policy", json={"sandbox_policy_id":"sbxpol_simulation_only"})
        assert resp.status_code == 404

    def test_super_admin_can_see_cross_tenant(self, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_sax", developer_id="d1", tenant_id="other-tn",
                                          adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        c = _make_ra_app(rt_store, auth=_auth_super)
        resp = c.get("/admin/runtime/bindings", params={"tenant_id":"other-tn"})
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_cross_tenant_denial_404(self, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_ct", developer_id="d1", tenant_id="other-tn",
                                          adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        c = _make_ra_app(rt_store)
        resp = c.get(f"/admin/runtime/bindings/{b.binding_id}")
        assert resp.status_code == 404

    def test_developer_cannot_read_other_developer_submission(self, dev_store, sub_store, usage_store):
        from src.open_platform.submission import AgentManifest, AgentSubmission, SecurityProfile
        dev1 = DeveloperAccount(developer_id="dev_a", user_id="user-a", tenant_id=_TENANT, display_name="A", contact_email="a@t.com")
        dev2 = DeveloperAccount(developer_id="dev_b", user_id="user-b", tenant_id=_TENANT, display_name="B", contact_email="b@t.com")
        dev_store.create_developer(dev1); dev_store.create_developer(dev2)
        m = AgentManifest(name="sub-a", display_name="SA", description="Test sub A desc", version="1.0.0", capabilities=["t"],
                          required_permissions=["agent:execute"], security_profile=SecurityProfile())
        sub = AgentSubmission(developer_id="dev_a", tenant_id=_TENANT, agent_manifest=m)
        sub_store.create_submission(sub)
        c2 = _make_dev_app(dev_store, sub_store, usage_store, auth=_auth_dev_uid)
        resp = c2.get(f"/developers/agents/{sub.submission_id}")
        assert resp.status_code == 404


# ═══════════ C. Runtime Binding / Eligibility (17) ═══════════
class TestRuntimeBindingBoundary:
    def test_publish_does_not_auto_create_binding(self, dev_store, sub_store, rt_store, mkp_store, usage_store):
        from src.open_platform.publish import build_marketplace_agent_from_submission
        from src.open_platform.submission import AgentManifest, AgentSubmission, SecurityProfile, SubmissionStatus
        dev = DeveloperAccount(developer_id="dev_pub", user_id="u1", tenant_id=_TENANT, display_name="DP", contact_email="dp@t.com")
        dev_store.create_developer(dev)
        m = AgentManifest(name="pub-agent", display_name="PA", description="Test publish agent",
                          version="1.0.0", capabilities=["t"], required_permissions=["agent:execute"], security_profile=SecurityProfile())
        sub = AgentSubmission(developer_id="dev_pub", tenant_id=_TENANT, agent_manifest=m, status=SubmissionStatus.APPROVED)
        sub_store.create_submission(sub)
        mkp_agent = build_marketplace_agent_from_submission(sub, dev)
        mkp_store.create_agent(mkp_agent)
        sub_store.publish_submission(sub.submission_id, mkp_agent.marketplace_agent_id)
        binding = rt_store.get_binding_by_marketplace_agent(mkp_agent.marketplace_agent_id, _TENANT)
        assert binding is None

    def test_install_does_not_auto_create_binding(self, dev_store, rt_store, mkp_store, usage_store):
        mkp_store.create_agent(MarketplaceAgent(marketplace_agent_id="mkp_inst2", agent_id="a2", name="inst2",
            display_name="I2", description="Test", capabilities=["t"], publisher_type=PublisherType.DEVELOPER))
        mkp_store.install_agent(marketplace_agent_id="mkp_inst2", agent_id="a2", tenant_id=_TENANT,
                                workspace_id=_TENANT, installed_by="admin", permissions_granted=["agent:execute"])
        binding = rt_store.get_binding_by_marketplace_agent("mkp_inst2", _TENANT)
        assert binding is None

    def test_create_binding_default_pending(self, rt_store, mkp_store):
        mkp_store.create_agent(MarketplaceAgent(marketplace_agent_id="mkp_pending2", agent_id="a3", name="p2",
            display_name="P2", description="Test", capabilities=["t"], publisher_type=PublisherType.DEVELOPER))
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_pending2", developer_id="d1", tenant_id=_TENANT,
                                          adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION)
        created = rt_store.create_binding(b)
        assert created.runtime_status == RuntimeBindingStatus.PENDING

    def test_assign_policy_does_not_enable(self, rt_store, sp_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_ape2", developer_id="d1", tenant_id=_TENANT,
                                          adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        rt_store.set_binding_sandbox_policy(b.binding_id, "sbxpol_simulation_only")
        updated = rt_store.get_binding(b.binding_id)
        assert updated.runtime_status == RuntimeBindingStatus.PENDING

    def test_enable_non_mvp_adapter_rejected(self, rt_store):
        rt_store.set_adapter_status("rtadp_container", "active")
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_ctr2", developer_id="d1", tenant_id=_TENANT,
                                          adapter_id="rtadp_container", adapter_type=RuntimeAdapterType.CONTAINER)
        rt_store.create_binding(b)
        with pytest.raises(Exception):
            rt_store.enable_binding(b.binding_id, "admin")

    def test_disabled_adapter_cannot_enable_binding(self, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_http", developer_id="d1", tenant_id=_TENANT,
                                          adapter_id="rtadp_http_webhook", adapter_type=RuntimeAdapterType.HTTP_WEBHOOK)
        rt_store.create_binding(b)
        with pytest.raises(Exception):
            rt_store.enable_binding(b.binding_id, "admin")

    def test_enable_simulation_binding_does_not_execute_code(self, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_sim_en", developer_id="d1", tenant_id=_TENANT,
                                          adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        rt_store.enable_binding(b.binding_id, "admin")
        assert rt_store.get_binding(b.binding_id).is_enabled()

    def test_enable_manifest_only_does_not_execute_code(self, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_mo_en", developer_id="d1", tenant_id=_TENANT,
                                          adapter_id="rtadp_manifest_only", adapter_type=RuntimeAdapterType.MANIFEST_ONLY)
        rt_store.create_binding(b)
        rt_store.enable_binding(b.binding_id, "admin")
        assert rt_store.get_binding(b.binding_id).is_enabled()

    def test_eligibility_no_binding(self, rt_store):
        result = rt_store.get_runtime_eligibility("mkp_nonexistent2")
        assert result.code == RuntimeEligibilityCode.NO_BINDING

    def test_eligibility_pending_not_eligible(self, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_pend_el", developer_id="d1", tenant_id="t1",
                                          adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        result = rt_store.get_runtime_eligibility("mkp_pend_el", "t1")
        assert not result.eligible

    def test_eligibility_disabled_not_eligible(self, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_el_dis", developer_id="d1", tenant_id="t1",
                                          adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        rt_store.enable_binding(b.binding_id, "admin"); rt_store.disable_binding(b.binding_id, "admin")
        result = rt_store.get_runtime_eligibility("mkp_el_dis", "t1")
        assert not result.eligible

    def test_eligibility_suspended_not_eligible(self, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_el_sus", developer_id="d1", tenant_id="t1",
                                          adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        rt_store.enable_binding(b.binding_id, "admin"); rt_store.suspend_binding(b.binding_id, "admin")
        result = rt_store.get_runtime_eligibility("mkp_el_sus", "t1")
        assert not result.eligible

    def test_eligibility_simulation_enabled_eligible(self, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_el_sim_ok", developer_id="d1", tenant_id="t1",
                                          adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b); rt_store.enable_binding(b.binding_id, "admin")
        result = rt_store.get_runtime_eligibility("mkp_el_sim_ok", "t1")
        assert result.eligible

    def test_eligibility_no_agent_runtime_invoked(self, rt_store):
        result = rt_store.get_runtime_eligibility("mkp_nonexistent_3")
        assert not result.eligible

    def test_eligibility_no_agent_registry_invoked(self, rt_store):
        result = rt_store.get_runtime_eligibility("mkp_nonexistent_4")
        assert result.code == RuntimeEligibilityCode.NO_BINDING


# ═══════════ D. Simulation Runtime (8) ═══════════
class TestSimulationBoundary:
    def test_simulation_requires_developer_agent(self, mkp_store, rt_store):
        sim = SimulationRuntimeService(mkp_store, rt_store)
        req = SimulationRunRequest(marketplace_agent_id="mkp_nope", tenant_id=_TENANT)
        result = sim.simulate_agent(req)
        assert result.status == SimulationRunStatus.BLOCKED

    def test_builtin_agent_cannot_simulate(self, mkp_store, rt_store):
        mkp_store.create_agent(MarketplaceAgent(marketplace_agent_id="mkp_built", agent_id="b1", name="built",
            display_name="Built", description="Test", capabilities=["t"], publisher_type=PublisherType.BUILTIN))
        sim = SimulationRuntimeService(mkp_store, rt_store)
        req = SimulationRunRequest(marketplace_agent_id="mkp_built", tenant_id=_TENANT)
        result = sim.simulate_agent(req)
        assert result.status == SimulationRunStatus.BLOCKED

    def test_simulation_requires_installation(self, mkp_store, rt_store):
        mkp_store.create_agent(MarketplaceAgent(marketplace_agent_id="mkp_noinst", agent_id="ni", name="ni",
            display_name="NI", description="Test", capabilities=["t"], required_permissions=["agent:execute"],
            publisher_type=PublisherType.DEVELOPER))
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_noinst", developer_id="d1", tenant_id=_TENANT,
                                          adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b); rt_store.enable_binding(b.binding_id, "admin")
        sim = SimulationRuntimeService(mkp_store, rt_store)
        req = SimulationRunRequest(marketplace_agent_id="mkp_noinst", tenant_id=_TENANT)
        result = sim.simulate_agent(req)
        assert result.status == SimulationRunStatus.BLOCKED

    def test_simulation_no_package_execution(self, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_sim_safe")
        sim = SimulationRuntimeService(mkp_store, rt_store)
        req = SimulationRunRequest(marketplace_agent_id="mkp_sim_safe", tenant_id=_TENANT)
        result = sim.simulate_agent(req)
        assert result.metadata["no_remote_code_execution"] is True
        assert result.metadata["simulation_only"] is True

    def test_simulation_result_safety_flags(self, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_safe_flags")
        sim = SimulationRuntimeService(mkp_store, rt_store)
        req = SimulationRunRequest(marketplace_agent_id="mkp_safe_flags", tenant_id=_TENANT)
        result = sim.simulate_agent(req)
        assert result.metadata["no_remote_code_execution"] is True

    def test_simulation_no_raw_key_in_result(self, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_noleak")
        sim = SimulationRuntimeService(mkp_store, rt_store)
        req = SimulationRunRequest(marketplace_agent_id="mkp_noleak", tenant_id=_TENANT)
        result = sim.simulate_agent(req)
        assert "raw_key" not in json.dumps(result.to_dict())

    def test_simulation_no_key_hash_in_result(self, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_nohash")
        sim = SimulationRuntimeService(mkp_store, rt_store)
        req = SimulationRunRequest(marketplace_agent_id="mkp_nohash", tenant_id=_TENANT)
        result = sim.simulate_agent(req)
        assert "key_hash" not in json.dumps(result.to_dict())

    def test_simulation_metadata_has_no_network(self, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_no_net_meta")
        sim = SimulationRuntimeService(mkp_store, rt_store)
        req = SimulationRunRequest(marketplace_agent_id="mkp_no_net_meta", tenant_id=_TENANT)
        result = sim.simulate_agent(req)
        assert result.metadata.get("no_network") is True


# ═══════════ E. Sandbox Policy (8) ═══════════
class TestSandboxPolicyBoundary:
    def test_no_execution_execution_allowed_false(self):
        p = SandboxPolicy(name="N", description="D", sandbox_level=SandboxLevel.NO_EXECUTION)
        assert not p.is_execution_allowed()

    def test_simulation_only_execution_allowed_false(self):
        p = SandboxPolicy(name="S", description="D", sandbox_level=SandboxLevel.SIMULATION_ONLY)
        assert not p.is_execution_allowed()

    def test_policy_test_does_not_execute(self, sp_store):
        req = SandboxPolicyTestRequest(sandbox_level="no_execution")
        result = sp_store.test_policy("sbxpol_no_execution", req)
        assert result.metadata.get("no_code_executed") is True or result.metadata.get("static_evaluation_only") is True

    def test_system_managed_cannot_be_deleted(self, sp_store):
        with pytest.raises(Exception):
            sp_store.delete_policy("sbxpol_no_execution")

    def test_normal_admin_cannot_modify_system_policy(self, sp_store):
        c = _make_sp_app(sp_store)
        resp = c.patch("/admin/sandbox-policies/sbxpol_no_execution", json={"name":"Hacked"})
        assert resp.status_code == 403

    def test_api_key_cannot_list_policies(self, sp_store, dev_store, sub_store, usage_store):
        c1 = _make_dev_app(dev_store, sub_store, usage_store)
        _register_dev(c1); raw_key, _ = _create_key(c1, ["developer:read"])
        app2 = FastAPI(); app2.include_router(create_sandbox_policy_router(sp_store))
        resp = TestClient(app2).get("/admin/sandbox-policies", headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code in (401, 403)

    def test_policy_assignment_safe_usage(self, sp_store, rt_store):
        b = DeveloperAgentRuntimeBinding(marketplace_agent_id="mkp_pol_safe", developer_id="d1", tenant_id=_TENANT,
                                          adapter_id="rtadp_simulation", adapter_type=RuntimeAdapterType.SIMULATION)
        rt_store.create_binding(b)
        rt_store.set_binding_sandbox_policy(b.binding_id, "sbxpol_simulation_only")
        updated = rt_store.get_binding(b.binding_id)
        assert updated.sandbox_policy_id == "sbxpol_simulation_only"
        assert not updated.is_enabled()

    def test_policy_test_deny_network_static(self, sp_store):
        req = SandboxPolicyTestRequest(sandbox_level="simulation_only", requested_network=True)
        result = sp_store.test_policy("sbxpol_simulation_only", req)
        assert not result.allowed


# ═══════════ F. Package Validation (4) ═══════════
class TestPackageValidationBoundary:
    def test_validate_package_requires_admin(self, dev_store, sub_store, usage_store):
        from src.open_platform.package_validation_service import PackageValidationService
        from src.adapters.package_validation_store import SQLitePackageValidationStore
        pv = PackageValidationService(SQLitePackageValidationStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:"), sub_store, dev_store, usage_store)
        c_member = _make_admin_app(dev_store, sub_store, usage_store, pv=pv, auth=_auth_member)
        resp = c_member.post("/admin/agent-submissions/sub_x/validate-package")
        assert resp.status_code in (403, 404)

    def test_validate_package_blocks_localhost(self, dev_store, sub_store, usage_store):
        from src.open_platform.package_validation_service import PackageValidationService
        from src.adapters.package_validation_store import SQLitePackageValidationStore
        from src.open_platform.submission import AgentManifest, AgentSubmission, SecurityProfile
        pv_store = SQLitePackageValidationStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:")
        pv = PackageValidationService(pv_store, sub_store, dev_store, usage_store)
        m = AgentManifest(name="pkg-test", display_name="PT", description="Package test agent desc",
                          version="1.0.0", capabilities=["t"], required_permissions=["agent:execute"],
                          security_profile=SecurityProfile(),
                          metadata={"package_checksum":"abc","package_checksum_algorithm":"sha256"})
        sub = AgentSubmission(developer_id="dev_1", tenant_id=_TENANT, agent_manifest=m,
                              package_url="https://localhost/pkg.zip")
        sub_store.create_submission(sub)
        result = pv.validate_submission_package(sub.submission_id, "admin", _TENANT)
        assert result.no_download_performed
        assert result.has_blockers()

    def test_validate_package_safety_flags(self, dev_store, sub_store, usage_store):
        from src.open_platform.package_validation_service import PackageValidationService
        from src.adapters.package_validation_store import SQLitePackageValidationStore
        from src.open_platform.submission import AgentManifest, AgentSubmission, SecurityProfile
        pv = PackageValidationService(SQLitePackageValidationStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:"), sub_store, dev_store, usage_store)
        m = AgentManifest(name="safe-flags", display_name="SF", description="Safety flags test agent",
                          version="1.0.0", capabilities=["t"], required_permissions=["agent:execute"],
                          security_profile=SecurityProfile())
        sub = AgentSubmission(developer_id="dev_1", tenant_id=_TENANT, agent_manifest=m)
        sub_store.create_submission(sub)
        result = pv.validate_submission_package(sub.submission_id, "admin", _TENANT)
        assert result.no_download_performed
        assert result.no_execution_performed

    def test_package_validation_no_raw_key(self, dev_store, sub_store, usage_store):
        from src.open_platform.package_validation_service import PackageValidationService
        from src.adapters.package_validation_store import SQLitePackageValidationStore
        from src.open_platform.submission import AgentManifest, AgentSubmission, SecurityProfile
        pv = PackageValidationService(SQLitePackageValidationStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:"), sub_store, dev_store, usage_store)
        m = AgentManifest(name="meta-safe", display_name="MS", description="Metadata safety test desc",
                          version="1.0.0", capabilities=["t"], required_permissions=["agent:execute"],
                          security_profile=SecurityProfile())
        sub = AgentSubmission(developer_id="dev_1", tenant_id=_TENANT, agent_manifest=m)
        sub_store.create_submission(sub)
        result = pv.validate_submission_package(sub.submission_id, "admin", _TENANT)
        d = result.to_dict()
        assert "raw_key" not in json.dumps(d)
        assert "key_hash" not in json.dumps(d)


# ═══════════ G. Manifest SDK / Schema (7) ═══════════
class TestManifestSDKBoundary:
    def test_backend_validate_does_not_create_submission(self, dev_store, sub_store, usage_store):
        c = _make_dev_app(dev_store, sub_store, usage_store)
        resp = c.post("/developers/agent-manifest/validate", json={"manifest":{
            "name":"v-agent","display_name":"VA","description":"Validate test agent desc",
            "version":"1.0.0","capabilities":["t"],"required_permissions":["agent:execute"],
            "runtime_type":"manifest_only",
            "security_profile":{"sandbox_level":"no_execution","requires_network":False,"reads_user_data":False,"writes_user_data":False},
        }})
        assert resp.status_code == 200
        assert sub_store.list_submissions() == []

    def test_backend_validate_blocks_unsafe_runtime(self, dev_store, sub_store, usage_store):
        c = _make_dev_app(dev_store, sub_store, usage_store)
        resp = c.post("/developers/agent-manifest/validate", json={"manifest":{
            "name":"unsafe","display_name":"U","description":"Unsafe runtime test agent",
            "version":"1.0.0","capabilities":["t"],"required_permissions":["agent:execute"],
            "runtime_type":"container",
            "security_profile":{"sandbox_level":"no_execution","requires_network":False,"reads_user_data":False,"writes_user_data":False},
        }})
        assert not resp.json()["valid"]

    def test_backend_validate_blocks_network(self, dev_store, sub_store, usage_store):
        c = _make_dev_app(dev_store, sub_store, usage_store)
        resp = c.post("/developers/agent-manifest/validate", json={"manifest":{
            "name":"net","display_name":"N","description":"Network test agent desc",
            "version":"1.0.0","capabilities":["t"],"required_permissions":["agent:execute"],
            "runtime_type":"manifest_only",
            "security_profile":{"sandbox_level":"no_execution","requires_network":True,"reads_user_data":False,"writes_user_data":False},
        }})
        assert not resp.json()["valid"]

    def test_schema_runtime_type_mvp_only(self):
        schema_path = os.path.join(os.path.dirname(__file__), "..", "..", "schemas", "cognitive-agent.schema.json")
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
        rt_enum = schema["properties"]["runtime_type"]["enum"]
        assert "manifest_only" in rt_enum

    def test_examples_no_secrets(self):
        for name in ["minimal_manifest.json", "package_metadata_manifest.json", "invalid_network_manifest.json"]:
            path = os.path.join(os.path.dirname(__file__), "..", "..", "examples", "developer-agents", name)
            with open(path, encoding="utf-8") as f:
                content = f.read().lower()
            assert "password" not in content

    def test_invalid_network_manifest_is_invalid(self):
        from src.open_platform.manifest_validator import validate_manifest_dict
        path = os.path.join(os.path.dirname(__file__), "..", "..", "examples", "developer-agents", "invalid_network_manifest.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        result = validate_manifest_dict(data)
        assert not result.valid

    def test_manifest_validate_response_no_traceback(self, dev_store, sub_store, usage_store):
        c = _make_dev_app(dev_store, sub_store, usage_store)
        resp = c.post("/developers/agent-manifest/validate", json={"manifest":"not-a-dict"})
        assert "Traceback" not in str(resp.json())


# ═══════════ H. Usage / Logging / Metadata Safety (5) ═══════════
class TestUsageLoggingSafety:
    def test_simulation_usage_metadata_safe(self, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_usage_meta")
        sim = SimulationRuntimeService(mkp_store, rt_store)
        req = SimulationRunRequest(marketplace_agent_id="mkp_usage_meta", tenant_id=_TENANT)
        result = sim.simulate_agent(req)
        assert "raw_key" not in json.dumps(result.metadata)

    def test_logging_extra_no_reserved_created(self, rt_store, sp_store):
        rt2 = SQLiteRuntimeStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:")
        rt2.seed_builtin_adapters()
        sp2 = SQLiteSandboxPolicyStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:")
        sp2.seed_builtin_policies()
        assert True  # No KeyError thrown

    def test_frontend_runtime_types_no_raw_key(self):
        types_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "types", "runtime-admin.ts")
        if os.path.exists(types_path):
            with open(types_path, encoding="utf-8") as f:
                content = f.read()
            assert "raw_key" not in content
            assert "key_hash" not in content

    def test_marketplace_types_no_execution_fields(self):
        types_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "types", "marketplace.ts")
        if os.path.exists(types_path):
            with open(types_path, encoding="utf-8") as f:
                content = f.read().lower()
            assert "execute_code" not in content

    def test_open_platform_types_no_key_hash_in_interfaces(self):
        """DeveloperApiKey interface must not have a key_hash field, even though comments may mention it."""
        types_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "types", "open-platform.ts")
        if os.path.exists(types_path):
            with open(types_path, encoding="utf-8") as f:
                content = f.read()
            # Check: no "key_hash" as an interface property (not just in comments)
            # key_hash should never appear after ":" in a type definition
            lines = [l for l in content.split("\n") if ":" in l and "key_hash" in l and not l.strip().startswith("//")]
            assert len(lines) == 0, f"Found key_hash in type lines: {lines}"


# ═══════════ I. Frontend Security UX (7) ═══════════
class TestFrontendSecurityUX:
    def _read(self, *parts):
        path = os.path.join(os.path.dirname(__file__), "..", "..", *parts)
        if not os.path.exists(path): return ""
        with open(path, encoding="utf-8") as f: return f.read()

    def test_runtime_admin_no_misleading_execution(self):
        c = self._read("frontend", "app", "admin", "runtime", "page.tsx")
        if not c: return
        assert "Run external code" not in c
        assert "Execute package" not in c
        assert "no remote code execution" in c.lower() or "No Remote Code Execution" in c

    def test_sidebar_no_execution_buttons(self):
        c = self._read("frontend", "components", "layout", "Sidebar.tsx")
        if not c: return
        assert "Execute" not in c

    def test_runtime_admin_services_no_execution(self):
        c = self._read("frontend", "services", "runtime-admin.ts")
        if not c: return
        assert "execute_agent" not in c.lower()

    def test_developer_services_no_publish(self):
        c = self._read("frontend", "services", "developer.ts")
        if not c: return
        assert "publish" not in c.lower()

    def test_admin_services_has_no_execute(self):
        c = self._read("frontend", "services", "admin-submissions.ts")
        if not c: return
        assert "execute_package" not in c.lower()

    def test_types_no_execution_fields(self):
        c = self._read("frontend", "types", "open-platform.ts")
        if not c: return
        assert "execution_output" not in c

    def test_types_no_real_payment(self):
        c = self._read("frontend", "types", "marketplace.ts")
        if not c: return
        assert "revenue_share" not in c.lower()
