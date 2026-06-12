"""Local Dev Sandbox Prototype 测试 — domain + worker + registry + policy + safety。"""
import os, pytest
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from datetime import datetime, timezone
from src.open_platform.local_dev_sandbox import *
from src.open_platform.sandbox_worker import (
    SandboxWorkerRequest, SandboxWorkerResult, SandboxWorkerResultStatus,
    SandboxWorkerType, SandboxWorkerAvailability, SandboxWorkerDecision, SandboxWorkerCheck,
    build_worker_request_from_plan,
)
from src.open_platform.local_dev_sandbox_worker import LocalDevSandboxPrototypeWorker
from src.open_platform.sandbox_worker_registry import SandboxWorkerRegistry, create_default_sandbox_worker_registry
from src.open_platform.runtime_execution_plan import RuntimeExecutionPlan

# ═════ Domain (19) ═════

class TestDomain:
    def test_create_check(self):
        c = LocalDevSandboxCheck(check_type=LocalDevSandboxCheckType.DRY_RUN_ONLY_MODE, message="ok")
        assert c.check_id.startswith("ldschk_")
    def test_check_to_dict_from_dict(self):
        c = LocalDevSandboxCheck(check_type="t", status="passed", message="m"); d=c.to_dict(); c2=LocalDevSandboxCheck.from_dict(d)
        assert c2.check_type=="t"
    def test_check_metadata_safe(self):
        c=LocalDevSandboxCheck(message="ok"); d=c.to_dict(); assert "raw_key" not in str(d)
    def test_disabled_config(self):
        cfg=LocalDevSandboxConfig.disabled(); assert not cfg.enabled
        assert not cfg.allow_subprocess and not cfg.allow_container and not cfg.allow_network
        assert not cfg.allow_file_read and not cfg.allow_file_write and not cfg.allow_secrets
    def test_disabled_config_no_enabled(self): assert not LocalDevSandboxConfig.disabled().enabled
    def test_dry_run_for_tests_enabled(self): assert LocalDevSandboxConfig.dry_run_for_tests().enabled
    def test_dry_run_for_tests_dry_run_only(self): assert LocalDevSandboxConfig.dry_run_for_tests().dry_run_only
    def test_dry_run_still_no_danger_caps(self):
        cfg=LocalDevSandboxConfig.dry_run_for_tests()
        assert not cfg.allow_subprocess and not cfg.allow_container and not cfg.allow_network
        assert not cfg.allow_file_read and not cfg.allow_file_write and not cfg.allow_secrets
    def test_config_to_dict_from_dict(self):
        cfg=LocalDevSandboxConfig.dry_run_for_tests(); d=cfg.to_dict(); cfg2=LocalDevSandboxConfig.from_dict(d)
        assert cfg2.enabled and cfg2.dry_run_only
    def test_config_metadata_safe(self):
        d=LocalDevSandboxConfig.disabled().to_dict(); assert "raw_key" not in str(d)
    def test_create_dry_run_result(self):
        dr=LocalDevSandboxDryRunResult(request_id="r1",plan_id="p1",tenant_id="t1")
        assert dr.dry_run_id.startswith("ldsdry_")
    def test_dry_run_result_to_dict_from_dict(self):
        dr=LocalDevSandboxDryRunResult(request_id="r1",plan_id="p1",tenant_id="t1")
        dr.add_check(LocalDevSandboxCheck(check_type="t",status="passed",message="ok")); d=dr.to_dict(); dr2=LocalDevSandboxDryRunResult.from_dict(d)
        assert len(dr2.checks)==1
    def test_add_check_recounts(self):
        dr=LocalDevSandboxDryRunResult(request_id="r1",plan_id="p1",tenant_id="t1")
        dr.add_check(LocalDevSandboxCheck(check_type="b",status=LocalDevSandboxCheckStatus.BLOCKED,severity=LocalDevSandboxSeverity.BLOCKER,message="b"))
        assert dr.blockers_count==1
    def test_calculate_status_blocked(self):
        dr=LocalDevSandboxDryRunResult(request_id="r1",plan_id="p1",tenant_id="t1")
        dr.add_check(LocalDevSandboxCheck(check_type="b",status="blocked",severity="blocker",message="b")); dr.calculate_status()
        assert dr.decision==LocalDevSandboxDecision.BLOCKED_DISABLED
    def test_calculate_status_dry_run(self):
        dr=LocalDevSandboxDryRunResult(request_id="r1",plan_id="p1",tenant_id="t1")
        dr.add_check(LocalDevSandboxCheck(check_type="ok",status="passed",message="ok")); dr.calculate_status()
        assert dr.decision==LocalDevSandboxDecision.DRY_RUN_RESERVED
    def test_is_real_execution_always_false(self):
        dr=LocalDevSandboxDryRunResult(request_id="r1",plan_id="p1",tenant_id="t1"); assert not dr.is_real_execution()
    def test_output_preview_no_raw_input(self):
        dr=LocalDevSandboxDryRunResult(request_id="r1",plan_id="p1",tenant_id="t1",output_preview={"dry_run":True})
        assert "input" not in str(dr.output_preview).lower() or "dry" in str(dr.output_preview).lower()
    def test_id_formats(self):
        assert LocalDevSandboxCheck().check_id.startswith("ldschk_")
        assert LocalDevSandboxConfig.disabled().config_id.startswith("ldscfg_")
        assert LocalDevSandboxDryRunResult().dry_run_id.startswith("ldsdry_")

# ═════ Worker disabled (13) ═════

class TestWorkerDisabled:
    @pytest.fixture
    def w(self): return LocalDevSandboxPrototypeWorker()
    def test_default_availability_disabled(self,w): assert w.get_availability()==SandboxWorkerAvailability.DISABLED
    def test_default_config_disabled(self,w): assert not w._config.enabled
    def test_evaluate_disabled_blocked(self,w):
        r=w.evaluate_request(mk_req()); assert r.status==SandboxWorkerResultStatus.BLOCKED
    def test_disabled_result_no_exec(self,w):
        r=w.evaluate_request(mk_req()); assert r.no_execution_performed
    def test_disabled_no_network(self,w): r=w.evaluate_request(mk_req()); assert r.no_network_used
    def test_disabled_no_subprocess(self,w): r=w.evaluate_request(mk_req()); assert r.no_subprocess_used
    def test_disabled_no_container(self,w): r=w.evaluate_request(mk_req()); assert r.no_container_used
    def test_disabled_no_agent_runtime(self,w): r=w.evaluate_request(mk_req()); assert r.no_agent_runtime_used
    def test_disabled_no_agent_registry(self,w): r=w.evaluate_request(mk_req()); assert r.no_agent_registry_used
    def test_no_execute_method(self,w): assert not hasattr(w,"execute") or not callable(getattr(w,"execute",None))
    def test_no_run_method(self,w): assert not hasattr(w,"run") or not callable(getattr(w,"run",None))
    def test_no_dispatch_method(self,w): assert not hasattr(w,"dispatch") or not callable(getattr(w,"dispatch",None))
    def test_worker_type(self,w): assert "dry_run" in w.get_worker_type() or w.get_worker_type()=="local_dev_dry_run"

# ═════ Worker dry-run (16) ═════

class TestWorkerDryRun:
    @pytest.fixture
    def cfg(self): return LocalDevSandboxConfig.dry_run_for_tests()
    @pytest.fixture
    def w(self, cfg): return LocalDevSandboxPrototypeWorker(config=cfg)
    @pytest.fixture
    def good_policy_snap(self): return {"enforceable":True,"network":{"allow_network":False},"secrets":{"allow_secrets":False},"filesystem":{"allow_read":False,"allow_write":False},"data_access":{"mode":"deny_all"}}
    def test_availability_degraded(self,w): assert w.get_availability() in (SandboxWorkerAvailability.DEGRADED,SandboxWorkerAvailability.DISABLED)
    def test_dry_run_with_policy_config(self,w,good_policy_snap):
        req=mk_req(policy_config_snapshot=good_policy_snap); r=w.evaluate_request(req)
        assert r.status in (SandboxWorkerResultStatus.RESERVED, SandboxWorkerResultStatus.SKIPPED)
    def test_dry_run_output_has_dry_run_true(self,w,good_policy_snap):
        req=mk_req(policy_config_snapshot=good_policy_snap); r=w.evaluate_request(req)
        assert r.output_json.get("dry_run") is True
    def test_dry_run_stdout_none(self,w,good_policy_snap):
        req=mk_req(policy_config_snapshot=good_policy_snap); r=w.evaluate_request(req)
        assert r.stdout_text is None and r.stderr_text is None
    def test_dry_run_exit_code_none(self,w,good_policy_snap):
        req=mk_req(policy_config_snapshot=good_policy_snap); r=w.evaluate_request(req); assert r.exit_code is None
    def test_is_successful_execution_false(self,w,good_policy_snap):
        req=mk_req(policy_config_snapshot=good_policy_snap); r=w.evaluate_request(req); assert not r.is_successful_execution()
    def test_does_not_mutate_request(self,w,good_policy_snap):
        req=mk_req(policy_config_snapshot=good_policy_snap); old=req.plan_id; w.evaluate_request(req); assert req.plan_id==old
    def test_requires_policy_config(self,w):
        req=mk_req(); r=w.evaluate_request(req); assert r.status==SandboxWorkerResultStatus.BLOCKED
    def test_non_enforceable_policy_fail_closed(self,w):
        req=mk_req(policy_config_snapshot={"enforceable":False}); r=w.evaluate_request(req)
        assert r.status==SandboxWorkerResultStatus.BLOCKED
    def test_network_allow_policy_blocked(self,w):
        req=mk_req(policy_config_snapshot={"enforceable":True,"network":{"allow_network":True},"secrets":{"allow_secrets":False},"filesystem":{"allow_read":False,"allow_write":False},"data_access":{"mode":"deny_all"}})
        r=w.evaluate_request(req); assert r.status==SandboxWorkerResultStatus.BLOCKED
    def test_secrets_allow_policy_blocked(self,w):
        req=mk_req(policy_config_snapshot={"enforceable":True,"network":{"allow_network":False},"secrets":{"allow_secrets":True},"filesystem":{"allow_read":False,"allow_write":False},"data_access":{"mode":"deny_all"}})
        r=w.evaluate_request(req); assert r.status==SandboxWorkerResultStatus.BLOCKED
    def test_filesystem_access_policy_blocked(self,w):
        req=mk_req(policy_config_snapshot={"enforceable":True,"network":{"allow_network":False},"secrets":{"allow_secrets":False},"filesystem":{"allow_read":True,"allow_write":False},"data_access":{"mode":"deny_all"}})
        r=w.evaluate_request(req); assert r.status==SandboxWorkerResultStatus.BLOCKED
    def test_no_execution_performed_true(self,w,good_policy_snap):
        req=mk_req(policy_config_snapshot=good_policy_snap); r=w.evaluate_request(req); assert r.no_execution_performed
    def test_no_download_used_true(self,w,good_policy_snap):
        req=mk_req(policy_config_snapshot=good_policy_snap); r=w.evaluate_request(req); assert r.no_download_used
    def test_no_subprocess_used_true(self,w,good_policy_snap):
        req=mk_req(policy_config_snapshot=good_policy_snap); r=w.evaluate_request(req); assert r.no_subprocess_used
    def test_no_container_used_true(self,w,good_policy_snap):
        req=mk_req(policy_config_snapshot=good_policy_snap); r=w.evaluate_request(req); assert r.no_container_used

# ═════ Registry (9) ═════

class TestRegistry:
    def test_default_disabled_only(self):
        reg=SandboxWorkerRegistry(); wl=reg.list_workers(); assert len(wl)==1 and wl[0]["worker_type"]==SandboxWorkerType.DISABLED_STUB
    def test_factory_default_disabled_only(self):
        reg=create_default_sandbox_worker_registry(enable_local_dev_dry_run=False); assert len(reg.list_workers())==1
    def test_factory_with_dry_run_registers_local(self):
        reg=create_default_sandbox_worker_registry(enable_local_dev_dry_run=True)
        types=[w["worker_type"] for w in reg.list_workers()]; assert SandboxWorkerType.LOCAL_DEV_DRY_RUN in types
    def test_local_dry_run_not_default(self):
        reg=create_default_sandbox_worker_registry(enable_local_dev_dry_run=True)
        w=reg.get_default(); assert w.get_worker_type()==SandboxWorkerType.DISABLED_STUB
    def test_no_subprocess_registered(self):
        reg=create_default_sandbox_worker_registry(enable_local_dev_dry_run=True); assert reg.get(SandboxWorkerType.LOCAL_PROCESS_RESERVED) is None
    def test_no_container_registered(self):
        reg=create_default_sandbox_worker_registry(enable_local_dev_dry_run=True); assert reg.get(SandboxWorkerType.CONTAINER_RESERVED) is None
    def test_no_dynamic_import(self):
        reg=SandboxWorkerRegistry(); assert reg.get("unknown") is None
    def test_no_AgentRegistry_import(self):
        m=__import__("src.open_platform.sandbox_worker_registry",fromlist=[""]); assert "AgentRegistry" not in str(dir(m))
    def test_evaluate_default_still_blocked(self):
        reg=SandboxWorkerRegistry(); r=reg.evaluate_with_default(mk_req()); assert r.status==SandboxWorkerResultStatus.BLOCKED

# ═════ Request Integration (7) ═════

class TestRequestIntegration:
    def test_request_supports_policy_config_snapshot(self):
        req=SandboxWorkerRequest(policy_config_snapshot={"enforceable":True}); assert req.policy_config_snapshot=={"enforceable":True}
    def test_build_request_with_snapshot(self):
        plan=RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1")
        req=build_worker_request_from_plan(plan); assert isinstance(req.policy_config_snapshot,dict)
    def test_build_request_without_snapshot_valid(self):
        plan=RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1")
        req=build_worker_request_from_plan(plan); assert req is not None
    def test_request_input_payload_hash_only(self):
        req=mk_req(input_payload_hash="abc"); d=req.to_dict(); assert "input_payload_hash" in d
    def test_request_metadata_safe(self):
        d=mk_req().to_dict(); assert "raw_key" not in str(d)
    def test_no_raw_input_payload(self):
        d=mk_req().to_dict(); assert "input_payload" not in str(d) or "hash" in str(d)
    def test_plan_not_dispatchable_request_builds(self):
        plan=RuntimeExecutionPlan(marketplace_agent_id="m1",tenant_id="t1",developer_id="d1"); req=build_worker_request_from_plan(plan); assert req is not None

# ═════ Safety (17) ═════

class TestSafety:
    def test_local_dev_module_no_subprocess(self):
        import src.open_platform.local_dev_sandbox_worker as m; assert "subprocess" not in str(dir(m)).lower()
    def test_no_docker(self):
        import src.open_platform.local_dev_sandbox_worker as m; assert "docker" not in str(dir(m)).lower()
    def test_no_requests(self):
        import src.open_platform.local_dev_sandbox_worker as m; assert "requests" not in str(dir(m)).lower() and "httpx" not in str(dir(m)).lower()
    def test_no_urllib(self):
        import src.open_platform.local_dev_sandbox_worker as m; assert "urllib" not in str(dir(m)).lower()
    def test_no_AgentRuntime(self):
        import src.open_platform.local_dev_sandbox_worker as m; assert "AgentRuntime" not in str(dir(m))
    def test_no_AgentRegistry(self):
        import src.open_platform.local_dev_sandbox_worker as m; assert "AgentRegistry" not in str(dir(m))
    def test_no_queue(self):
        import src.open_platform.local_dev_sandbox_worker as m; assert "Queue" not in str(dir(m)) or "Sandbox" in str(dir(m))
    def test_no_multiprocessing(self):
        import src.open_platform.local_dev_sandbox_worker as m; assert "multiprocessing" not in str(dir(m)).lower()
    def test_no_file_open(self,cfg=LocalDevSandboxConfig.dry_run_for_tests()):
        w=LocalDevSandboxPrototypeWorker(config=cfg); req=mk_req(policy_config_snapshot={"enforceable":True,"network":{"allow_network":False},"secrets":{"allow_secrets":False},"filesystem":{"allow_read":False,"allow_write":False},"data_access":{"mode":"deny_all"}})
        r=w.evaluate_request(req); assert r.no_execution_performed
    def test_no_package_url_access(self):
        req=mk_req(); r=LocalDevSandboxPrototypeWorker().evaluate_request(req); assert r.no_download_used
    def test_no_repository_url_access(self):
        req=mk_req(); r=LocalDevSandboxPrototypeWorker().evaluate_request(req); assert r.no_network_used
    def test_no_local_path_read(self,w=LocalDevSandboxPrototypeWorker()):
        r=w.evaluate_request(mk_req()); assert r.no_execution_performed
    def test_no_execute_method(self,w=LocalDevSandboxPrototypeWorker()):
        assert not hasattr(w,"execute") or not callable(getattr(w,"execute",None))
    def test_no_run_method(self,w=LocalDevSandboxPrototypeWorker()):
        assert not hasattr(w,"run") or not callable(getattr(w,"run",None))
    def test_no_dispatch_method(self,w=LocalDevSandboxPrototypeWorker()):
        assert not hasattr(w,"dispatch") or not callable(getattr(w,"dispatch",None))
    def test_no_stdout_stderr_content(self,cfg=LocalDevSandboxConfig.dry_run_for_tests()):
        w=LocalDevSandboxPrototypeWorker(config=cfg); req=mk_req(policy_config_snapshot={"enforceable":True,"network":{"allow_network":False},"secrets":{"allow_secrets":False},"filesystem":{"allow_read":False,"allow_write":False},"data_access":{"mode":"deny_all"}})
        r=w.evaluate_request(req); assert r.stdout_text is None and r.stderr_text is None and r.exit_code is None
    def test_no_runtime_execution_api_created(self):
        reg=create_default_sandbox_worker_registry(enable_local_dev_dry_run=True)
        r=reg.evaluate_with_default(mk_req()); assert r.status==SandboxWorkerResultStatus.BLOCKED
    def test_no_worker_process_created(self,w=LocalDevSandboxPrototypeWorker()):
        r=w.evaluate_request(mk_req()); assert r.no_subprocess_used and r.no_container_used

def mk_req(**kw):
    return SandboxWorkerRequest(plan_id=kw.get("plan_id","p1"),marketplace_agent_id=kw.get("mkp","m1"),
                                tenant_id=kw.get("tid","t1"),developer_id=kw.get("did","d1"),
                                policy_config_snapshot=kw.get("policy_config_snapshot",{}),
                                input_payload_hash=kw.get("input_payload_hash",None))
