"""Simulation Runtime 测试 — Developer Agent 安全仿真。

覆盖:
- Domain Model: request/result/step/blocked, no raw_key/key_hash, safety metadata
- Service Blocked: not_found, not_developer, no_installation, no_permissions,
    no_binding, binding_disabled, adapter_not_simulation, no_scope
- Service Success: simulation succeeds, output deterministic, usage recorded
- Non-execution: no AgentRuntime, no AgentRegistry, no package_url, no network
- API Endpoint: JWT dev simulates, API Key simulates, scope enforcement, denial
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.developer_store import SQLiteDeveloperStore
from src.adapters.submission_store import SQLiteSubmissionStore
from src.adapters.usage_store import UsageStoreAdapter
from src.adapters.marketplace_store import SQLiteMarketplaceStore
from src.adapters.runtime_store import SQLiteRuntimeStore
from src.api.developer_router import create_developer_router
from src.api.middleware import require_auth, get_token_payload, TokenPayload
from src.core.auth import WorkspaceRole
from src.core.usage import UsageResource
from src.agents.marketplace import MarketplaceAgent, PublisherType
from src.open_platform.api_auth import DeveloperApiPrincipal
from src.open_platform.developer import (
    DeveloperAccount, DeveloperApiKey, DeveloperStatus,
    generate_api_key, get_api_key_prefix, hash_api_key,
)
from src.open_platform.runtime import (
    DeveloperAgentRuntimeBinding,
    RuntimeAdapterType,
    RuntimeBindingStatus,
    RuntimeEligibilityCode,
)
from src.open_platform.simulation import (
    SimulationRunRequest,
    SimulationRunResult,
    SimulationRunStatus,
    SimulationStep,
    SimulationBlockReason,
)
from src.open_platform.simulation_runtime import SimulationRuntimeService


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════

def _payload(role=WorkspaceRole.ADMIN, ws="test-ws-001", uid="user-001", sa=False):
    return TokenPayload(user_id=uid, workspace_id=ws, role=role, is_super_admin=sa)

async def _auth_admin(): return _payload()
async def _auth_user2(): return _payload(uid="user-002")

@pytest.fixture
def settings(): return Settings(deepseek_api_key="sk-test")

@pytest.fixture
def dev_store(settings): return SQLiteDeveloperStore(settings, db_path=":memory:")

@pytest.fixture
def sub_store(settings): return SQLiteSubmissionStore(settings, db_path=":memory:")

@pytest.fixture
def mkp_store(settings): return SQLiteMarketplaceStore(settings, db_path=":memory:")

@pytest.fixture
def rt_store(settings):
    s = SQLiteRuntimeStore(settings, db_path=":memory:")
    s.seed_builtin_adapters()
    return s

@pytest.fixture
def usage_store(settings, tmp_path):
    s = UsageStoreAdapter(config=settings, db_path=str(tmp_path / "sim_usage.db"))
    yield s; s.close()

@pytest.fixture
def svc(mkp_store, rt_store, usage_store):
    return SimulationRuntimeService(mkp_store, rt_store, usage_store)


def _make_dev_app(dev_store, sub_store, usage=None, mkp=None, rt=None, sim=None):
    app = FastAPI()
    app.dependency_overrides[require_auth] = _auth_admin
    app.dependency_overrides[get_token_payload] = _auth_admin
    app.include_router(create_developer_router(
        dev_store, sub_store, usage, marketplace_store=mkp,
        runtime_store=rt, simulation_service=sim,
    ))
    return TestClient(app)


def _create_dev_key(client, dev_id, scopes=None):
    """Create API Key via low-level store (bypasses JWT requirement for test setup)."""
    raw_key = generate_api_key()
    kp = get_api_key_prefix(raw_key)
    kh = hash_api_key(raw_key)
    from src.open_platform.developer import DeveloperApiKey as DAK
    client.app.dependency_overrides  # just to avoid unused arg
    return raw_key, DAK(
        developer_id=dev_id, key_prefix=kp, key_hash=kh,
        name="SimKey", scopes=scopes or ["agent:simulate"],
    )


# ═══════════════════════════════════════════
# 1. Domain Model
# ═══════════════════════════════════════════

class TestDomainModel:
    def test_create_request(self):
        r = SimulationRunRequest(marketplace_agent_id="mkp_x", tenant_id="t1")
        assert r.marketplace_agent_id == "mkp_x"

    def test_request_to_dict_no_package_url(self):
        r = SimulationRunRequest(marketplace_agent_id="mkp_x", tenant_id="t1")
        d = r.to_dict()
        assert "package_url" not in d
        assert "entrypoint" not in d

    def test_create_step(self):
        s = SimulationStep(name="test", status="passed", message="OK")
        d = s.to_dict()
        assert d["name"] == "test"
        assert d["status"] == "passed"

    def test_success_result(self):
        r = SimulationRunResult(status=SimulationRunStatus.SUCCESS, message="OK")
        assert r.status == SimulationRunStatus.SUCCESS
        assert r.blocked_reason is None

    def test_blocked_result(self):
        r = SimulationRunResult(
            status=SimulationRunStatus.BLOCKED,
            blocked_reason=SimulationBlockReason.MARKETPLACE_AGENT_NOT_FOUND,
            message="Not found",
        )
        assert not r.status == SimulationRunStatus.SUCCESS
        assert r.blocked_reason is not None

    def test_result_to_dict_no_raw_key(self):
        r = SimulationRunResult(status=SimulationRunStatus.SUCCESS)
        d = r.to_dict()
        assert "raw_key" not in d
        assert "key_hash" not in d

    def test_result_metadata_has_safety_flags(self):
        r = SimulationRunResult()
        assert r.metadata.get("no_remote_code_execution") is True
        assert r.metadata.get("simulation_only") is True
        assert r.metadata.get("no_network") is True

    def test_result_roundtrip(self):
        r = SimulationRunResult(
            run_id="simrun_001",
            status=SimulationRunStatus.SUCCESS,
            message="OK",
            marketplace_agent_id="mkp_x",
            tenant_id="t1",
            developer_id="dev_1",
            adapter_id="rtadp_simulation",
            binding_id="rtbind_1",
            simulated_output={"mode": "simulation"},
            steps=[SimulationStep(name="s1", status="passed", message="p")],
            usage_recorded=True,
        )
        d = r.to_dict()
        r2 = SimulationRunResult.from_dict(d)
        assert r2.run_id == r.run_id
        assert r2.status == r.status
        assert r2.simulated_output == r.simulated_output


# ═══════════════════════════════════════════
# 2. Service Blocked Cases
# ═══════════════════════════════════════════

def _setup_dev_agent(mkp_store, rt_store, dev_id="dev_001", tenant="t1",
                     mkp_id="mkp_dev_x", scope_present=True):
    """Setup: developer agent in marketplace + installation + simulation binding."""
    # Create MarketplaceAgent
    agent = MarketplaceAgent(
        marketplace_agent_id=mkp_id,
        agent_id=f"developer_sub_{mkp_id[-8:]}",
        name="test-sim-agent",
        display_name="Test Sim Agent",
        description="For simulation testing",
        capabilities=["test"],
        required_permissions=["agent:execute"],
        publisher_type=PublisherType.DEVELOPER,
        publisher_name="Test Dev",
        status="beta",
    )
    mkp_store.create_agent(agent)

    # Create installation
    mkp_store.install_agent(
        marketplace_agent_id=mkp_id,
        agent_id=agent.agent_id,
        tenant_id=tenant,
        workspace_id=tenant,
        installed_by="admin-001",
        permissions_granted=["agent:execute"],
    )

    # Create and enable simulation binding
    binding = DeveloperAgentRuntimeBinding(
        marketplace_agent_id=mkp_id,
        developer_id=dev_id,
        tenant_id=tenant,
        adapter_id="rtadp_simulation",
        adapter_type=RuntimeAdapterType.SIMULATION,
    )
    rt_store.create_binding(binding)
    rt_store.enable_binding(binding.binding_id, "admin-001")


class TestServiceBlocked:
    def test_marketplace_agent_not_found(self, svc):
        req = SimulationRunRequest(marketplace_agent_id="mkp_nonexistent", tenant_id="t1")
        result = svc.simulate_agent(req)
        assert result.status == SimulationRunStatus.BLOCKED
        assert result.blocked_reason == SimulationBlockReason.MARKETPLACE_AGENT_NOT_FOUND

    def test_builtin_not_developer_agent(self, svc, mkp_store):
        mkp_store.create_agent(MarketplaceAgent(
            marketplace_agent_id="mkp_builtin",
            agent_id="builtin-test",
            name="builtin-test",
            display_name="Builtin Test",
            description="Test",
            capabilities=["test"],
            publisher_type=PublisherType.BUILTIN,
        ))
        req = SimulationRunRequest(marketplace_agent_id="mkp_builtin", tenant_id="t1")
        result = svc.simulate_agent(req)
        assert result.status == SimulationRunStatus.BLOCKED
        assert result.blocked_reason == SimulationBlockReason.NOT_DEVELOPER_AGENT

    def test_no_installation(self, svc, mkp_store):
        mkp_store.create_agent(MarketplaceAgent(
            marketplace_agent_id="mkp_no_inst",
            agent_id="dev-no-inst",
            name="no-inst",
            display_name="No Install",
            description="Test",
            capabilities=["test"],
            publisher_type=PublisherType.DEVELOPER,
        ))
        req = SimulationRunRequest(marketplace_agent_id="mkp_no_inst", tenant_id="t1")
        result = svc.simulate_agent(req)
        assert result.status == SimulationRunStatus.BLOCKED
        assert result.blocked_reason == SimulationBlockReason.INSTALLATION_REQUIRED

    def test_missing_permission(self, svc, mkp_store, rt_store):
        agent = MarketplaceAgent(
            marketplace_agent_id="mkp_no_perm",
            agent_id="dev-no-perm",
            name="no-perm",
            display_name="No Perm",
            description="Test",
            capabilities=["test"],
            required_permissions=["agent:execute", "memory:read"],
            publisher_type=PublisherType.DEVELOPER,
        )
        mkp_store.create_agent(agent)
        mkp_store.install_agent(
            marketplace_agent_id="mkp_no_perm",
            agent_id=agent.agent_id,
            tenant_id="t1", workspace_id="t1",
            installed_by="admin-001",
            permissions_granted=["agent:execute"],  # missing memory:read
        )
        binding = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_no_perm",
            developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_simulation",
            adapter_type=RuntimeAdapterType.SIMULATION,
        )
        rt_store.create_binding(binding)
        rt_store.enable_binding(binding.binding_id, "admin-001")
        req = SimulationRunRequest(marketplace_agent_id="mkp_no_perm", tenant_id="t1")
        result = svc.simulate_agent(req)
        assert result.status == SimulationRunStatus.BLOCKED
        assert result.blocked_reason == SimulationBlockReason.PERMISSIONS_REQUIRED

    def test_no_runtime_binding(self, svc, mkp_store):
        mkp_store.create_agent(MarketplaceAgent(
            marketplace_agent_id="mkp_no_bind",
            agent_id="dev-no-bind",
            name="no-bind",
            display_name="No Bind",
            description="Test",
            capabilities=["test"],
            publisher_type=PublisherType.DEVELOPER,
        ))
        mkp_store.install_agent(
            marketplace_agent_id="mkp_no_bind",
            agent_id="dev-no-bind",
            tenant_id="t1", workspace_id="t1",
            installed_by="admin-001",
            permissions_granted=["agent:execute"],
        )
        req = SimulationRunRequest(marketplace_agent_id="mkp_no_bind", tenant_id="t1")
        result = svc.simulate_agent(req)
        assert result.status == SimulationRunStatus.BLOCKED
        assert result.blocked_reason == SimulationBlockReason.RUNTIME_BINDING_REQUIRED

    def test_pending_binding(self, svc, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_pend")
        # Disable the binding
        binding = rt_store.get_binding_by_marketplace_agent("mkp_pend", "t1")
        rt_store.disable_binding(binding.binding_id, "admin-002")
        req = SimulationRunRequest(marketplace_agent_id="mkp_pend", tenant_id="t1")
        result = svc.simulate_agent(req)
        assert result.status == SimulationRunStatus.BLOCKED
        assert result.blocked_reason == SimulationBlockReason.RUNTIME_BINDING_DISABLED

    def test_manifest_only_binding_not_simulation(self, svc, mkp_store, rt_store):
        mkp_store.create_agent(MarketplaceAgent(
            marketplace_agent_id="mkp_mo",
            agent_id="dev-mo",
            name="mo",
            display_name="MO", description="T",
            capabilities=["t"], required_permissions=["agent:execute"],
            publisher_type=PublisherType.DEVELOPER,
        ))
        mkp_store.install_agent(
            marketplace_agent_id="mkp_mo", agent_id="dev-mo",
            tenant_id="t1", workspace_id="t1",
            installed_by="admin-001", permissions_granted=["agent:execute"],
        )
        binding = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_mo", developer_id="dev_1", tenant_id="t1",
            adapter_id="rtadp_manifest_only",
            adapter_type=RuntimeAdapterType.MANIFEST_ONLY,
        )
        rt_store.create_binding(binding)
        rt_store.enable_binding(binding.binding_id, "admin-001")
        req = SimulationRunRequest(marketplace_agent_id="mkp_mo", tenant_id="t1")
        result = svc.simulate_agent(req)
        assert result.status == SimulationRunStatus.BLOCKED
        assert result.blocked_reason == SimulationBlockReason.ADAPTER_NOT_SIMULATION

    def test_api_key_without_sim_scope(self, svc, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_noscope")
        req = SimulationRunRequest(
            marketplace_agent_id="mkp_noscope", tenant_id="t1",
            auth_type="developer_api_key",
            api_key_scopes=["developer:read"],  # no simulation scope
        )
        result = svc.simulate_agent(req)
        assert result.status == SimulationRunStatus.BLOCKED
        assert result.blocked_reason == SimulationBlockReason.INSUFFICIENT_API_KEY_SCOPE

    def test_package_url_present_does_not_execute(self, svc, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_pkg")
        # Add package_url metadata
        agent = mkp_store.get_agent("mkp_pkg")
        agent.metadata["package_url_present"] = True
        mkp_store.update_agent(agent)
        req = SimulationRunRequest(marketplace_agent_id="mkp_pkg", tenant_id="t1")
        result = svc.simulate_agent(req)
        # Should still succeed — package_url is NOT executed
        assert result.status == SimulationRunStatus.SUCCESS
        # package_url warning should be in metadata
        has_pkg_warning = False
        for s in result.steps:
            if "package_url_warning" in s.metadata:
                has_pkg_warning = True
        assert has_pkg_warning


# ═══════════════════════════════════════════
# 3. Service Success Cases
# ═══════════════════════════════════════════

class TestServiceSuccess:
    def test_simulation_success(self, svc, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_ok")
        req = SimulationRunRequest(marketplace_agent_id="mkp_ok", tenant_id="t1")
        result = svc.simulate_agent(req)
        assert result.status == SimulationRunStatus.SUCCESS
        assert result.blocked_reason is None

    def test_simulated_output_deterministic(self, svc, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_det")
        req = SimulationRunRequest(marketplace_agent_id="mkp_det", tenant_id="t1",
                                    input_text="Hello")
        r1 = svc.simulate_agent(req)
        r2 = svc.simulate_agent(req)
        assert r1.simulated_output == r2.simulated_output

    def test_capabilities_in_output(self, svc, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_caps")
        req = SimulationRunRequest(marketplace_agent_id="mkp_caps", tenant_id="t1")
        result = svc.simulate_agent(req)
        assert "capabilities_checked" in result.simulated_output
        assert "test" in result.simulated_output["capabilities_checked"]

    def test_permissions_in_output(self, svc, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_perms_out")
        req = SimulationRunRequest(marketplace_agent_id="mkp_perms_out", tenant_id="t1")
        result = svc.simulate_agent(req)
        assert "permissions_checked" in result.simulated_output
        assert "agent:execute" in result.simulated_output["permissions_checked"]

    def test_usage_recorded(self, svc, mkp_store, rt_store, usage_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_usage")
        req = SimulationRunRequest(marketplace_agent_id="mkp_usage", tenant_id="t1",
                                    developer_id="dev_001")
        result = svc.simulate_agent(req)
        assert result.usage_recorded

    def test_usage_metadata_no_raw_key(self, svc, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_safe")
        req = SimulationRunRequest(marketplace_agent_id="mkp_safe", tenant_id="t1")
        result = svc.simulate_agent(req)
        d = result.to_dict()
        assert "raw_key" not in json.dumps(d)
        assert "key_hash" not in json.dumps(d)

    def test_no_agent_runtime_imported(self):
        """Verify simulation_runtime module does not load AgentRuntime."""
        from src.open_platform import simulation_runtime as sim_mod
        assert "AgentRuntime" not in sim_mod.__dict__

    def test_no_agent_registry_imported(self):
        """Verify simulation_runtime module does not load AgentRegistry."""
        from src.open_platform import simulation_runtime as sim_mod
        assert "AgentRegistry" not in sim_mod.__dict__

    def test_safety_metadata_in_result(self, svc, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_meta")
        req = SimulationRunRequest(marketplace_agent_id="mkp_meta", tenant_id="t1")
        result = svc.simulate_agent(req)
        assert result.metadata["no_remote_code_execution"] is True
        assert result.metadata["simulation_only"] is True
        assert result.metadata["no_network"] is True

    def test_jwt_auth_simulation_allowed(self, svc, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_jwt")
        req = SimulationRunRequest(
            marketplace_agent_id="mkp_jwt", tenant_id="t1",
            auth_type="jwt", developer_id="dev_001",
        )
        result = svc.simulate_agent(req)
        assert result.status == SimulationRunStatus.SUCCESS

    def test_api_key_with_agent_simulate_scope(self, svc, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_scope1")
        req = SimulationRunRequest(
            marketplace_agent_id="mkp_scope1", tenant_id="t1",
            auth_type="developer_api_key",
            api_key_scopes=["agent:simulate"],
        )
        result = svc.simulate_agent(req)
        assert result.status == SimulationRunStatus.SUCCESS

    def test_api_key_with_execute_simulation_scope(self, svc, mkp_store, rt_store):
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_scope2")
        req = SimulationRunRequest(
            marketplace_agent_id="mkp_scope2", tenant_id="t1",
            auth_type="developer_api_key",
            api_key_scopes=["agent:execute:simulation"],
        )
        result = svc.simulate_agent(req)
        assert result.status == SimulationRunStatus.SUCCESS


# ═══════════════════════════════════════════
# 4. API Endpoint
# ═══════════════════════════════════════════

class TestSimulationEndpoint:
    T = "test-ws-001"  # matches JWT payload workspace_id

    @pytest.fixture
    def app_client(self, dev_store, sub_store, usage_store, mkp_store, rt_store):
        svc = SimulationRuntimeService(mkp_store, rt_store, usage_store)
        return _make_dev_app(dev_store, sub_store, usage_store, mkp_store, rt_store, svc)

    def _register(self, client):
        return client.post("/developers/register",
            json={"display_name": "Dev", "contact_email": "d@t.com"}).json()["developer"]

    def test_jwt_dev_simulates_own_published_agent(self, app_client, mkp_store, rt_store):
        dev_info = self._register(app_client)
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_api1",
                         dev_id=dev_info["developer_id"], tenant=self.T)
        resp = app_client.post("/developers/marketplace-agents/mkp_api1/simulate",
                               json={"input_text": "hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_api_key_with_agent_simulate_can_simulate(self, app_client, mkp_store, rt_store,
                                                        dev_store):
        dev_info = self._register(app_client)
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_ak",
                         dev_id=dev_info["developer_id"], tenant=self.T)
        raw_key, _ = self._create_api_key(dev_store, dev_info, ["agent:simulate"])
        resp = app_client.post("/developers/marketplace-agents/mkp_ak/simulate",
                               json={"input_text": "hi"},
                               headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_api_key_without_scope_gets_403(self, app_client, mkp_store, rt_store, dev_store):
        dev_info = self._register(app_client)
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_403",
                         dev_id=dev_info["developer_id"], tenant=self.T)
        raw_key, _ = self._create_api_key(dev_store, dev_info, ["developer:read"])
        resp = app_client.post("/developers/marketplace-agents/mkp_403/simulate",
                               json={"input_text": "hi"},
                               headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code == 403
        resp = app_client.post("/developers/marketplace-agents/mkp_403/simulate",
                               json={"input_text": "hi"},
                               headers={"X-Cognitive-API-Key": raw_key})
        assert resp.status_code == 403

    def test_api_key_cannot_simulate_builtin(self, app_client, mkp_store):
        self._register(app_client)
        mkp_store.create_agent(MarketplaceAgent(
            marketplace_agent_id="mkp_builtin2",
            agent_id="builtin-2", name="b2", display_name="B2",
            description="T", capabilities=["t"],
            publisher_type=PublisherType.BUILTIN,
        ))
        resp = app_client.post("/developers/marketplace-agents/mkp_builtin2/simulate",
                               json={"input_text": "hi"})
        data = resp.json()
        assert data["status"] == "blocked"
        assert data["blocked_reason"] == SimulationBlockReason.NOT_DEVELOPER_AGENT

    def test_no_binding_returns_blocked(self, app_client, mkp_store):
        dev_info = self._register(app_client)
        mkp_store.create_agent(MarketplaceAgent(
            marketplace_agent_id="mkp_nb", agent_id="dev-nb",
            name="nb", display_name="NB", description="T",
            capabilities=["t"], publisher_type=PublisherType.DEVELOPER,
        ))
        resp = app_client.post("/developers/marketplace-agents/mkp_nb/simulate",
                               json={"input_text": "hi"})
        data = resp.json()
        assert data["status"] == "blocked"

    def test_no_installation_returns_blocked(self, app_client, mkp_store, rt_store):
        dev_info = self._register(app_client)
        mkp_store.create_agent(MarketplaceAgent(
            marketplace_agent_id="mkp_ni", agent_id="dev-ni",
            name="ni", display_name="NI", description="T",
            capabilities=["t"], publisher_type=PublisherType.DEVELOPER,
        ))
        binding = DeveloperAgentRuntimeBinding(
            marketplace_agent_id="mkp_ni",
            developer_id=dev_info["developer_id"],
            tenant_id=self.T,
            adapter_id="rtadp_simulation",
            adapter_type=RuntimeAdapterType.SIMULATION,
        )
        rt_store.create_binding(binding)
        rt_store.enable_binding(binding.binding_id, "admin-001")
        resp = app_client.post("/developers/marketplace-agents/mkp_ni/simulate",
                               json={"input_text": "hi"})
        data = resp.json()
        assert data["status"] == "blocked"
        assert data["blocked_reason"] == SimulationBlockReason.INSTALLATION_REQUIRED

    def test_raw_key_not_in_response(self, app_client, mkp_store, rt_store):
        dev_info = self._register(app_client)
        _setup_dev_agent(mkp_store, rt_store, mkp_id="mkp_noleak",
                         dev_id=dev_info["developer_id"], tenant=self.T)
        resp = app_client.post("/developers/marketplace-agents/mkp_noleak/simulate",
                               json={"input_text": "hi"})
        assert "raw_key" not in json.dumps(resp.json())
        assert "key_hash" not in json.dumps(resp.json())

    def test_no_traceback_in_error(self):
        app = FastAPI()
        app.include_router(create_developer_router(
            SQLiteDeveloperStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:"),
            SQLiteSubmissionStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:"),
            None,
        ))
        c = TestClient(app)
        resp = c.post("/developers/marketplace-agents/mkp_x/simulate", json={})
        assert resp.status_code == 501
        body = resp.json()
        assert "Traceback" not in str(body)

    def _create_api_key(self, dev_store, dev_info, scopes):
        """Create API Key via store directly."""
        raw_key = generate_api_key()
        kp = get_api_key_prefix(raw_key)
        kh = hash_api_key(raw_key)
        dev_store.create_api_key(DeveloperApiKey(
            developer_id=dev_info["developer_id"],
            key_prefix=kp, key_hash=kh, name="K", scopes=scopes,
        ))
        return raw_key, None

    def test_401_without_auth(self):
        app = FastAPI()
        app.include_router(create_developer_router(
            SQLiteDeveloperStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:"),
            SQLiteSubmissionStore(Settings(deepseek_api_key="sk-test"), db_path=":memory:"),
        ))
        c = TestClient(app)
        resp = c.post("/developers/marketplace-agents/mkp_x/simulate", json={})
        assert resp.status_code in (401, 501)
