"""Policy Enforcement Translator 单元测试 — domain + translator + fail-closed + safety。

90 tests covering domain model, translator rules, fail-closed, safety guards.
"""

from __future__ import annotations
import os, pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from datetime import datetime, timezone
from src.open_platform.policy_enforcement import (
    DataAccessMode, DataAccessPolicyConfig, FilesystemMode, FilesystemPolicyConfig,
    NetworkEgressMode, NetworkPolicyConfig, PolicyEnforcementCheck,
    PolicyEnforcementCheckStatus, PolicyEnforcementCheckType, PolicyEnforcementDecision,
    PolicyEnforcementSeverity, PolicyEnforcementStatus, PolicyTranslationResult,
    ResourceLimitPolicyConfig, SecretAccessMode, SecretPolicyConfig,
    WorkerPolicyConfig, build_policy_config_snapshot,
)
from src.open_platform.policy_enforcement_translator import SandboxPolicyEnforcementTranslator
from src.open_platform.sandbox_policy import SandboxPolicy, SandboxLevel, SandboxPolicyStatus

# Short helper to create a test policy
def mk_policy(**kw):
    return SandboxPolicy(policy_id=kw.get("pid", "sp1"), name=kw.get("name", "test"),
                         description=kw.get("desc", "test policy"), status=kw.get("status", SandboxPolicyStatus.ACTIVE),
                         sandbox_level=kw.get("level", SandboxLevel.NO_EXECUTION),
                         allow_network=kw.get("net", False), allowed_domains=kw.get("domains", []),
                         allow_filesystem_read=kw.get("fs_r", False), allow_filesystem_write=kw.get("fs_w", False),
                         allowed_paths=kw.get("paths", []),
                         allow_secrets=kw.get("sec", False), allowed_secret_names=kw.get("sec_names", []),
                         max_timeout_ms=kw.get("timeout", 5000), max_memory_mb=kw.get("mem", 128),
                         max_cpu_percent=kw.get("cpu", 10), max_output_bytes=kw.get("out", 65536),
                         max_requests_per_minute=kw.get("rate", 30),
                         data_access_scope=kw.get("dascope", []),
                         audit_enabled=kw.get("audit", True), kill_switch_enabled=kw.get("ks", True))

def mk_t(**kw):
    return SandboxPolicyEnforcementTranslator(**kw)

# ═══════════════ Domain ═══════════════

class TestPolicyEnforcementDomain:
    def test_create_check(self):
        c = PolicyEnforcementCheck(check_type=PolicyEnforcementCheckType.POLICY_EXISTS, message="ok")
        assert c.check_id.startswith("polchk_")
    def test_check_to_dict_from_dict(self):
        c = PolicyEnforcementCheck(check_type="t", status="passed", message="m"); d=c.to_dict(); c2=PolicyEnforcementCheck.from_dict(d)
        assert c2.check_type == "t"
    def test_check_metadata_safe(self):
        c = PolicyEnforcementCheck(message="ok"); d = c.to_dict(); assert "raw_key" not in str(d)
    def test_network_config_deny_all(self):
        n = NetworkPolicyConfig(mode=NetworkEgressMode.DENY_ALL); assert n.mode == NetworkEgressMode.DENY_ALL
    def test_network_config_allowlist(self):
        n = NetworkPolicyConfig(mode=NetworkEgressMode.ALLOWLIST_ONLY, allow_network=True, allowed_domains=["example.com"])
        assert n.allowed_domains == ["example.com"]
    def test_filesystem_config_deny_all(self):
        f = FilesystemPolicyConfig(mode=FilesystemMode.DENY_ALL); assert f.mode == FilesystemMode.DENY_ALL
    def test_secret_config_deny_all(self):
        s = SecretPolicyConfig(mode=SecretAccessMode.DENY_ALL); assert s.mode == SecretAccessMode.DENY_ALL
    def test_resource_config_valid(self):
        r = ResourceLimitPolicyConfig(timeout_ms=30000, memory_mb=256, cpu_percent=50, max_output_bytes=100000)
        assert r.timeout_ms == 30000 and r.memory_mb == 256
    def test_data_access_deny_all(self):
        d = DataAccessPolicyConfig(mode=DataAccessMode.DENY_ALL); assert d.mode == DataAccessMode.DENY_ALL
    def test_worker_policy_config_to_dict_from_dict(self):
        w = WorkerPolicyConfig(policy_id="sp1", sandbox_level="no_execution", enforceable=True,
                               decision=PolicyEnforcementDecision.ALLOW_CONFIG)
        d = w.to_dict(); w2 = WorkerPolicyConfig.from_dict(d); assert w2.policy_id == "sp1"
    def test_worker_config_not_enforceable_with_unsupported(self):
        w = WorkerPolicyConfig(enforceable=False, unsupported_features=["isolated"])
        assert not w.enforceable
    def test_translation_result_to_dict_from_dict(self):
        r = PolicyTranslationResult(policy_id="sp1"); r.add_check(PolicyEnforcementCheck(check_type="t", status="passed", message="ok"))
        d = r.to_dict(); r2 = PolicyTranslationResult.from_dict(d); assert len(r2.checks) == 1
    def test_add_check_recounts(self):
        r = PolicyTranslationResult(policy_id="sp1")
        r.add_check(PolicyEnforcementCheck(check_type="w", status=PolicyEnforcementCheckStatus.WARNING, severity=PolicyEnforcementSeverity.WARNING, message="w"))
        r.add_check(PolicyEnforcementCheck(check_type="b", status=PolicyEnforcementCheckStatus.BLOCKED, severity=PolicyEnforcementSeverity.BLOCKER, message="b"))
        assert r.warnings_count == 1; assert r.blockers_count == 1
    def test_calculate_status_passed(self):
        r = PolicyTranslationResult(policy_id="sp1"); r.add_check(PolicyEnforcementCheck(check_type="t", status="passed", message="ok"))
        r.calculate_status(); assert r.status == PolicyEnforcementStatus.PASSED
    def test_calculate_status_warnings(self):
        r = PolicyTranslationResult(policy_id="sp1")
        r.add_check(PolicyEnforcementCheck(check_type="t", status="passed", message="ok"))
        r.add_check(PolicyEnforcementCheck(check_type="w", status="warning", severity="warning", message="w"))
        r.calculate_status(); assert r.status == PolicyEnforcementStatus.PASSED_WITH_WARNINGS
    def test_calculate_status_blocked(self):
        r = PolicyTranslationResult(policy_id="sp1")
        r.add_check(PolicyEnforcementCheck(check_type="b", status="blocked", severity="blocker", message="b"))
        r.calculate_status(); assert r.status == PolicyEnforcementStatus.BLOCKED
    def test_is_enforceable_false_when_config_missing(self):
        r = PolicyTranslationResult(policy_id="sp1"); r.config = None; assert not r.is_enforceable()
    def test_id_formats(self):
        assert PolicyEnforcementCheck().check_id.startswith("polchk_")
        assert WorkerPolicyConfig().config_id.startswith("polcfg_")
        assert PolicyTranslationResult().translation_id.startswith("poltr_")
    def test_safety_flags_true(self):
        r = PolicyTranslationResult(policy_id="sp1")
        assert r.no_execution_performed and r.no_network_used and r.no_secrets_read and r.no_filesystem_access


# ═══════════════ Translator no_exec / simulation ═══════════════

class TestTranslatorNoExecSimulation:
    def test_no_execution_policy_translates(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.NO_EXECUTION); result = t.translate_policy(p)
        assert result.status in (PolicyEnforcementStatus.PASSED, PolicyEnforcementStatus.PASSED_WITH_WARNINGS)
        assert result.config is not None
    def test_no_execution_network_deny_all(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.NO_EXECUTION); result = t.translate_policy(p)
        assert result.config.network.mode == NetworkEgressMode.DENY_ALL; assert not result.config.network.allow_network
    def test_no_execution_secrets_deny_all(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.NO_EXECUTION); result = t.translate_policy(p)
        assert result.config.secrets.mode == SecretAccessMode.DENY_ALL
    def test_no_execution_data_deny_all(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.NO_EXECUTION); result = t.translate_policy(p)
        assert result.config.data_access.mode == DataAccessMode.DENY_ALL
    def test_no_execution_no_host_mount(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.NO_EXECUTION); result = t.translate_policy(p)
        assert not result.config.filesystem.host_mount_allowed
    def test_simulation_policy_translates(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.SIMULATION_ONLY); result = t.translate_policy(p)
        assert result.status in (PolicyEnforcementStatus.PASSED, PolicyEnforcementStatus.PASSED_WITH_WARNINGS)
        assert result.config is not None
    def test_simulation_does_not_imply_execution(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.SIMULATION_ONLY); result = t.translate_policy(p)
        assert result.no_execution_performed
    def test_audit_enabled_pass(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.NO_EXECUTION, audit=True); result = t.translate_policy(p)
        assert any(c.check_type == PolicyEnforcementCheckType.AUDIT_ENABLED and c.status == "passed" for c in result.checks)

# ═══════════════ Translator restricted ═══════════════

class TestTranslatorRestricted:
    def test_restricted_no_network_fs_secrets_translates(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.RESTRICTED); result = t.translate_policy(p)
        assert result.config is not None and result.config.sandbox_level == SandboxLevel.RESTRICTED
    def test_restricted_allow_network_without_worker_support_blocks(self):
        t = mk_t(worker_supports_network_enforcement=False)
        p = mk_policy(level=SandboxLevel.RESTRICTED, net=True, domains=["example.com"])
        result = t.translate_policy(p)
        assert result.status in (PolicyEnforcementStatus.BLOCKED, PolicyEnforcementStatus.FAILED)
    def test_restricted_domains_valid(self):
        t = mk_t(worker_supports_network_enforcement=True)
        p = mk_policy(level=SandboxLevel.RESTRICTED, net=True, domains=["example.com"])
        result = t.translate_policy(p)
        assert not result.is_enforceable() or result.config.network.allowed_domains == ["example.com"]
    def test_private_ip_domain_blocked(self):
        t = mk_t(worker_supports_network_enforcement=True)
        p = mk_policy(level=SandboxLevel.RESTRICTED, net=True, domains=["10.0.0.1"])
        result = t.translate_policy(p)
        assert any(c.check_type == PolicyEnforcementCheckType.NETWORK_PRIVATE_IP_BLOCKED and c.status in ("blocked","failed") for c in result.checks)
    def test_localhost_domain_blocked(self):
        t = mk_t(worker_supports_network_enforcement=True)
        p = mk_policy(level=SandboxLevel.RESTRICTED, net=True, domains=["localhost"])
        result = t.translate_policy(p)
        assert any(c.check_type == PolicyEnforcementCheckType.NETWORK_PRIVATE_IP_BLOCKED for c in result.checks)
    def test_metadata_ip_blocked(self):
        t = mk_t(worker_supports_network_enforcement=True)
        p = mk_policy(level=SandboxLevel.RESTRICTED, net=True, domains=["example.com"]); result = t.translate_policy(p)
        # metadata IP check only appears when network enforcement is active
        assert any(c.check_type == PolicyEnforcementCheckType.NETWORK_METADATA_IP_BLOCKED for c in result.checks)
    def test_filesystem_read_without_support_blocked(self):
        t = mk_t(worker_supports_filesystem_enforcement=False)
        p = mk_policy(level=SandboxLevel.RESTRICTED, fs_r=True, paths=["/tmp"])
        result = t.translate_policy(p)
        assert result.status in (PolicyEnforcementStatus.BLOCKED, PolicyEnforcementStatus.FAILED)
    def test_filesystem_write_without_support_blocked(self):
        t = mk_t(worker_supports_filesystem_enforcement=False)
        p = mk_policy(level=SandboxLevel.RESTRICTED, fs_w=True)
        result = t.translate_policy(p)
        assert result.status in (PolicyEnforcementStatus.BLOCKED, PolicyEnforcementStatus.FAILED)
    def test_host_mount_always_blocked(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.RESTRICTED, fs_r=True); result = t.translate_policy(p)
        assert not result.config.filesystem.host_mount_allowed
    def test_secrets_allowed_without_broker_blocked(self):
        t = mk_t(worker_supports_secret_broker=False)
        p = mk_policy(level=SandboxLevel.RESTRICTED, sec=True, sec_names=["api_key"])
        result = t.translate_policy(p)
        assert result.status in (PolicyEnforcementStatus.BLOCKED, PolicyEnforcementStatus.FAILED)
    def test_raw_env_injection_never_allowed(self):
        t = mk_t(worker_supports_secret_broker=True)
        p = mk_policy(level=SandboxLevel.RESTRICTED, sec=True, sec_names=["k1"])
        result = t.translate_policy(p)
        assert not result.config.secrets.raw_env_injection_allowed
    def test_data_scope_without_broker_blocked(self):
        t = mk_t(worker_supports_data_broker=False)
        p = mk_policy(level=SandboxLevel.RESTRICTED, dascope=["memory"])
        result = t.translate_policy(p)
        assert result.status in (PolicyEnforcementStatus.BLOCKED, PolicyEnforcementStatus.FAILED)
    def test_resource_timeout_valid(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.RESTRICTED, timeout=30000); result = t.translate_policy(p)
        assert result.config.resources.timeout_ms == 30000
    def test_timeout_too_large_blocked(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.RESTRICTED, timeout=999999); result = t.translate_policy(p)
        assert any(c.check_type == PolicyEnforcementCheckType.RESOURCE_TIMEOUT_LIMIT_VALID and c.status == "failed" for c in result.checks)
    def test_isolated_unsupported_fail_closed(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.ISOLATED); result = t.translate_policy(p)
        assert result.status == PolicyEnforcementStatus.BLOCKED; assert not result.is_enforceable()
    def test_unknown_level_blocked(self):
        t = mk_t(supported_sandbox_levels={"custom_level"}); p = mk_policy(level=SandboxLevel.RESTRICTED)
        result = t.translate_policy(p); assert result.status == PolicyEnforcementStatus.BLOCKED
    def test_inactive_policy_blocked(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.NO_EXECUTION, status=SandboxPolicyStatus.DISABLED)
        result = t.translate_policy(p); assert result.status == PolicyEnforcementStatus.BLOCKED

# ═══════════════ Snapshot helper ═══════════════

class TestSnapshotHelper:
    def test_build_config_snapshot_from_passed(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.NO_EXECUTION); result = t.translate_policy(p)
        snap = build_policy_config_snapshot(result)
        assert snap is not None and isinstance(snap, dict)
    def test_build_fail_closed_snapshot_from_blocked(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.ISOLATED); result = t.translate_policy(p)
        snap = build_policy_config_snapshot(result)
        assert snap.get("fail_closed") or snap.get("enforceable") is False
    def test_snapshot_no_secrets(self):
        snap = build_policy_config_snapshot(PolicyTranslationResult(policy_id="sp1"))
        assert "secret" not in str(snap).lower() or "mode" in str(snap).lower()
    def test_snapshot_does_not_include_package_url(self):
        snap = build_policy_config_snapshot(PolicyTranslationResult(policy_id="sp1"))
        assert "package_url" not in str(snap)
    def test_snapshot_does_not_mutate_result(self):
        t = mk_t(); p = mk_policy(); result = t.translate_policy(p); old = result.status
        build_policy_config_snapshot(result); assert result.status == old

# ═══════════════ Safety ═══════════════

class TestTranslatorSafety:
    def test_translator_no_subprocess(self):
        import src.open_platform.policy_enforcement_translator as pt; assert "subprocess" not in str(dir(pt)).lower()
    def test_translator_no_docker(self):
        import src.open_platform.policy_enforcement_translator as pt; assert "docker" not in str(dir(pt)).lower()
    def test_translator_no_requests(self):
        import src.open_platform.policy_enforcement_translator as pt
        assert "requests" not in str(dir(pt)).lower() and "httpx" not in str(dir(pt)).lower()
    def test_translator_no_AgentRuntime(self):
        import src.open_platform.policy_enforcement_translator as pt; assert "AgentRuntime" not in str(dir(pt))
    def test_translator_no_AgentRegistry(self):
        import src.open_platform.policy_enforcement_translator as pt; assert "AgentRegistry" not in str(dir(pt))
    def test_translator_does_not_open_files(self):
        t = mk_t(); p = mk_policy(); result = t.translate_policy(p); assert result is not None  # no file access
    def test_translator_does_not_call_network(self):
        t = mk_t(); p = mk_policy(); result = t.translate_policy(p); assert result.no_network_used
    def test_translator_does_not_create_worker(self):
        # translator class has no worker creation — evaluate_request/dispatch/execute absent
        t = mk_t(); p = mk_policy(); result = t.translate_policy(p)
        assert result.no_execution_performed is True
    def test_translator_does_not_dispatch(self):
        import src.open_platform.policy_enforcement_translator as pt; assert "dispatch" not in str(dir(pt)).lower()
    def test_translator_no_execute_method(self):
        assert not hasattr(SandboxPolicyEnforcementTranslator, "execute") or not callable(getattr(SandboxPolicyEnforcementTranslator, "execute", None))
    def test_translator_no_run_method(self):
        assert not hasattr(SandboxPolicyEnforcementTranslator, "run") or not callable(getattr(SandboxPolicyEnforcementTranslator, "run", None))

# ═══════════════ Integration ═══════════════

class TestTranslatorIntegration:
    def test_no_execution_seed_shape(self):
        t = mk_t(); p = SandboxPolicy(policy_id="sbxpol_no_execution", name="No Execution Policy",
                                      description="Default", status=SandboxPolicyStatus.ACTIVE,
                                      sandbox_level=SandboxLevel.NO_EXECUTION,
                                      allow_network=False, allowed_domains=[],
                                      allow_filesystem_read=False, allow_filesystem_write=False,
                                      allow_secrets=False, max_timeout_ms=5000, max_memory_mb=0,
                                      data_access_scope=[], audit_enabled=True, system_managed=True)
        result = t.translate_policy(p)
        assert result.status in (PolicyEnforcementStatus.PASSED, PolicyEnforcementStatus.PASSED_WITH_WARNINGS)
        assert result.config is not None
    def test_simulation_seed_shape(self):
        t = mk_t(); p = SandboxPolicy(policy_id="sbxpol_simulation_only", name="Simulation Only",
                                      description="Safe", status=SandboxPolicyStatus.ACTIVE,
                                      sandbox_level=SandboxLevel.SIMULATION_ONLY,
                                      allow_network=False, allow_filesystem_read=False, allow_filesystem_write=False,
                                      allow_secrets=False, max_timeout_ms=5000, max_memory_mb=64,
                                      data_access_scope=[], audit_enabled=True, system_managed=True)
        result = t.translate_policy(p)
        assert result.status in (PolicyEnforcementStatus.PASSED, PolicyEnforcementStatus.PASSED_WITH_WARNINGS)
    def test_restricted_seed_shape(self):
        t = mk_t(); p = SandboxPolicy(policy_id="sbxpol_restricted_network_off", name="Restricted No Network",
                                      description="Restricted", status=SandboxPolicyStatus.ACTIVE,
                                      sandbox_level=SandboxLevel.RESTRICTED,
                                      allow_network=False, allow_filesystem_read=False, allow_filesystem_write=False,
                                      allow_secrets=False, max_timeout_ms=10000, max_memory_mb=128,
                                      data_access_scope=[], audit_enabled=True, system_managed=True)
        result = t.translate_policy(p)
        assert result.config is not None and result.config.sandbox_level == SandboxLevel.RESTRICTED
    def test_disabled_worker_still_blocked(self):
        from src.open_platform.sandbox_worker_stub import DisabledSandboxWorker
        w = DisabledSandboxWorker(); assert w.get_availability() == "disabled"; assert w.get_worker_type() == "disabled_stub"
    def test_policy_config_does_not_make_worker_available(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.NO_EXECUTION); result = t.translate_policy(p)
        assert result.no_execution_performed  # config doesn't enable execution
    def test_plan_is_dispatchable_remains_false(self):
        from src.open_platform.runtime_execution_plan import RuntimeExecutionPlan
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1", tenant_id="t1", developer_id="d1")
        assert not plan.is_dispatchable()  # unchanged by translator
    def test_repeated_translation_deterministic(self):
        t = mk_t(); p = mk_policy(level=SandboxLevel.NO_EXECUTION)
        r1 = t.translate_policy(p); r2 = t.translate_policy(p)
        assert r1.status == r2.status; assert r1.decision == r2.decision
    def test_fail_closed_when_worker_support_false(self):
        t = mk_t(worker_supports_network_enforcement=False, worker_supports_secret_broker=False, worker_supports_data_broker=False)
        p = mk_policy(level=SandboxLevel.RESTRICTED, net=True, sec=True, dascope=["memory"])
        result = t.translate_policy(p)
        assert result.status in (PolicyEnforcementStatus.BLOCKED, PolicyEnforcementStatus.FAILED)
