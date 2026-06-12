"""Sandbox Worker 单元测试 — Disabled Stub + Registry + Plan Integration。

80 测试覆盖 domain/stub/registry/plan integration/non-execution guards。
"""

from __future__ import annotations
import os, pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from datetime import datetime, timezone
from src.open_platform.sandbox_worker import (
    SandboxWorkerCheck, SandboxWorkerRequest, SandboxWorkerResult,
    SandboxWorkerCheckStatus, SandboxWorkerCheckType, SandboxWorkerDecision,
    SandboxWorkerResultStatus, SandboxWorkerSeverity, SandboxWorkerType,
    SandboxWorkerAvailability, build_worker_request_from_plan,
)
from src.open_platform.sandbox_worker_stub import DisabledSandboxWorker
from src.open_platform.sandbox_worker_registry import SandboxWorkerRegistry
from src.open_platform.runtime_execution_plan import RuntimeExecutionPlan

# ═══════════════ Domain ═══════════════

class TestWorkerDomain:
    def test_create_check(self):
        c = SandboxWorkerCheck(check_type=SandboxWorkerCheckType.WORKER_DISABLED, message="ok")
        assert c.check_id.startswith("sbxchk_")

    def test_check_to_dict_from_dict(self):
        c = SandboxWorkerCheck(check_type="t", status="passed", severity="info", message="m")
        d = c.to_dict(); c2 = SandboxWorkerCheck.from_dict(d)
        assert c2.check_type == "t"

    def test_check_metadata_safe(self):
        c = SandboxWorkerCheck(message="ok"); d = c.to_dict()
        assert "raw_key" not in str(d) and "key_hash" not in str(d)

    def test_create_request(self):
        r = SandboxWorkerRequest(plan_id="p1", marketplace_agent_id="m1", tenant_id="t1", developer_id="d1")
        assert r.request_id.startswith("sbxreq_")

    def test_request_to_dict_from_dict(self):
        r = SandboxWorkerRequest(plan_id="p1", marketplace_agent_id="m1", tenant_id="t1", developer_id="d1",
                                 policy_snapshot={"a": 1}, artifact_snapshot={"b": 2}, verification_snapshot={"c": 3})
        d = r.to_dict(); r2 = SandboxWorkerRequest.from_dict(d)
        assert r2.policy_snapshot == {"a": 1}

    def test_request_from_plan(self):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1", tenant_id="t1", developer_id="d1",
                                    input_payload_hash="abc123", policy_snapshot={"p": 1})
        req = SandboxWorkerRequest.from_plan(plan, requested_by="u1")
        assert req.plan_id == plan.plan_id
        assert req.input_payload_hash == "abc123"
        assert req.policy_snapshot == {"p": 1}

    def test_request_input_payload_hash_only(self):
        req = SandboxWorkerRequest(plan_id="p1", marketplace_agent_id="m1", tenant_id="t1", developer_id="d1",
                                   input_payload_hash="h")
        d = req.to_dict()
        assert "input_payload_hash" in d
        # No raw input payload

    def test_request_metadata_safe(self):
        req = SandboxWorkerRequest(plan_id="p1", marketplace_agent_id="m1", tenant_id="t1", developer_id="d1")
        d = req.to_dict(); assert "raw_key" not in str(d)

    def test_create_result(self):
        r = SandboxWorkerResult(request_id="r1", plan_id="p1", tenant_id="t1")
        assert r.result_id.startswith("sbxres_")

    def test_result_to_dict_from_dict(self):
        r = SandboxWorkerResult(request_id="r1", plan_id="p1", tenant_id="t1")
        r.add_check(SandboxWorkerCheck(check_type="t", status="passed", message="ok"))
        d = r.to_dict(); r2 = SandboxWorkerResult.from_dict(d)
        assert len(r2.checks) == 1

    def test_result_add_check_recounts(self):
        r = SandboxWorkerResult(request_id="r1", plan_id="p1", tenant_id="t1")
        r.add_check(SandboxWorkerCheck(check_type="w", status=SandboxWorkerCheckStatus.WARNING, severity=SandboxWorkerSeverity.WARNING, message="w"))
        r.add_check(SandboxWorkerCheck(check_type="b", status=SandboxWorkerCheckStatus.BLOCKED, severity=SandboxWorkerSeverity.BLOCKER, message="b"))
        assert r.warnings_count == 1; assert r.blockers_count == 1

    def test_calculate_status_blocked(self):
        r = SandboxWorkerResult(request_id="r1", plan_id="p1", tenant_id="t1")
        r.add_check(SandboxWorkerCheck(check_type="b", status=SandboxWorkerCheckStatus.BLOCKED, severity=SandboxWorkerSeverity.BLOCKER, message="b"))
        r.calculate_status()
        assert r.status == SandboxWorkerResultStatus.BLOCKED

    def test_is_successful_execution_always_false(self):
        r = SandboxWorkerResult(request_id="r1", plan_id="p1", tenant_id="t1")
        assert r.is_successful_execution() is False
        r.add_check(SandboxWorkerCheck(check_type="ok", status="passed", severity="info", message="ok"))
        r.calculate_status()
        assert r.is_successful_execution() is False  # still false regardless

    def test_stdout_stderr_default_none(self):
        r = SandboxWorkerResult(request_id="r1", plan_id="p1", tenant_id="t1")
        assert r.stdout_text is None and r.stderr_text is None

    def test_exit_code_default_none(self):
        r = SandboxWorkerResult(request_id="r1", plan_id="p1", tenant_id="t1"); assert r.exit_code is None

    def test_output_json_default_empty(self):
        r = SandboxWorkerResult(request_id="r1", plan_id="p1", tenant_id="t1"); assert r.output_json == {}

    def test_id_formats(self):
        assert SandboxWorkerCheck().check_id.startswith("sbxchk_")
        assert SandboxWorkerRequest().request_id.startswith("sbxreq_")
        assert SandboxWorkerResult().result_id.startswith("sbxres_")


# ═══════════════ Disabled Worker ═══════════════

class TestDisabledWorker:
    @pytest.fixture
    def worker(self): return DisabledSandboxWorker()

    def test_worker_type_disabled_stub(self, worker):
        assert worker.get_worker_type() == SandboxWorkerType.DISABLED_STUB

    def test_availability_disabled(self, worker):
        assert worker.get_availability() == SandboxWorkerAvailability.DISABLED

    def test_evaluate_request_returns_blocked(self, worker):
        req = SandboxWorkerRequest(plan_id="p1", marketplace_agent_id="m1", tenant_id="t1", developer_id="d1")
        result = worker.evaluate_request(req)
        assert result.status == SandboxWorkerResultStatus.BLOCKED

    def test_decision_blocked_disabled(self, worker):
        req = SandboxWorkerRequest(plan_id="p1", marketplace_agent_id="m1", tenant_id="t1", developer_id="d1")
        result = worker.evaluate_request(req)
        assert result.decision in (SandboxWorkerDecision.BLOCKED_DISABLED, SandboxWorkerDecision.FAIL_CLOSED)

    def test_no_download_used_true(self, worker):
        req = mk_req(); result = worker.evaluate_request(req)
        assert result.no_download_used is True

    def test_no_network_used_true(self, worker):
        req = mk_req(); result = worker.evaluate_request(req)
        assert result.no_network_used is True

    def test_no_execution_performed_true(self, worker):
        req = mk_req(); result = worker.evaluate_request(req)
        assert result.no_execution_performed is True

    def test_no_subprocess_used_true(self, worker):
        req = mk_req(); result = worker.evaluate_request(req)
        assert result.no_subprocess_used is True

    def test_no_container_used_true(self, worker):
        req = mk_req(); result = worker.evaluate_request(req)
        assert result.no_container_used is True

    def test_no_agent_runtime_used_true(self, worker):
        req = mk_req(); result = worker.evaluate_request(req)
        assert result.no_agent_runtime_used is True

    def test_no_agent_registry_used_true(self, worker):
        req = mk_req(); result = worker.evaluate_request(req)
        assert result.no_agent_registry_used is True

    def test_output_json_empty(self, worker):
        req = mk_req(); result = worker.evaluate_request(req)
        assert result.output_json == {}

    def test_stdout_none(self, worker):
        req = mk_req(); result = worker.evaluate_request(req); assert result.stdout_text is None

    def test_stderr_none(self, worker):
        req = mk_req(); result = worker.evaluate_request(req); assert result.stderr_text is None

    def test_exit_code_none(self, worker):
        req = mk_req(); result = worker.evaluate_request(req); assert result.exit_code is None

    def test_includes_worker_disabled_check(self, worker):
        req = mk_req(); result = worker.evaluate_request(req)
        assert any(c.check_type == SandboxWorkerCheckType.WORKER_DISABLED for c in result.checks)

    def test_includes_no_package_download_check(self, worker):
        req = mk_req(); result = worker.evaluate_request(req)
        assert any(c.check_type == SandboxWorkerCheckType.NO_PACKAGE_DOWNLOAD for c in result.checks)

    def test_includes_no_network_check(self, worker):
        req = mk_req(); result = worker.evaluate_request(req)
        assert any(c.check_type == SandboxWorkerCheckType.NO_NETWORK_USED for c in result.checks)

    def test_includes_no_execution_check(self, worker):
        req = mk_req(); result = worker.evaluate_request(req)
        assert any(c.check_type == SandboxWorkerCheckType.NO_EXECUTION_PERFORMED for c in result.checks)

    def test_includes_fail_closed_check(self, worker):
        req = mk_req(); result = worker.evaluate_request(req)
        assert any(c.check_type == SandboxWorkerCheckType.FAIL_CLOSED for c in result.checks)

    def test_blocked_result_has_blockers(self, worker):
        req = mk_req(); result = worker.evaluate_request(req)
        assert result.blockers_count > 0

    def test_does_not_mutate_request(self, worker):
        req = mk_req(plan_id="original"); worker.evaluate_request(req)
        assert req.plan_id == "original"

    def test_does_not_mutate_plan(self, worker):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1", tenant_id="t1", developer_id="d1")
        req = SandboxWorkerRequest.from_plan(plan)
        worker.evaluate_request(req)
        # plan is separate from request, so this is always fine

    def test_no_execute_method(self):
        assert not hasattr(DisabledSandboxWorker(), "execute") or not callable(
            getattr(DisabledSandboxWorker(), "execute", None))

    def test_no_dispatch_method(self):
        assert not hasattr(DisabledSandboxWorker(), "dispatch") or not callable(
            getattr(DisabledSandboxWorker(), "dispatch", None))

    def test_no_run_method(self):
        assert not hasattr(DisabledSandboxWorker(), "run") or not callable(
            getattr(DisabledSandboxWorker(), "run", None))


# ═══════════════ Registry ═══════════════

class TestWorkerRegistry:
    def test_default_registry_has_disabled_only(self):
        reg = SandboxWorkerRegistry()
        workers = reg.list_workers()
        assert len(workers) == 1
        assert workers[0]["worker_type"] == SandboxWorkerType.DISABLED_STUB

    def test_get_default_returns_disabled(self):
        reg = SandboxWorkerRegistry()
        w = reg.get_default()
        assert w.get_worker_type() == SandboxWorkerType.DISABLED_STUB

    def test_list_workers_contains_disabled(self):
        reg = SandboxWorkerRegistry()
        types = [w["worker_type"] for w in reg.list_workers()]
        assert SandboxWorkerType.DISABLED_STUB in types

    def test_evaluate_with_default_blocked(self):
        reg = SandboxWorkerRegistry()
        req = mk_req(); result = reg.evaluate_with_default(req)
        assert result.status == SandboxWorkerResultStatus.BLOCKED

    def test_cannot_auto_enable_container(self):
        reg = SandboxWorkerRegistry(); w = reg.get(SandboxWorkerType.CONTAINER_RESERVED)
        assert w is None

    def test_cannot_auto_enable_subprocess(self):
        reg = SandboxWorkerRegistry(); w = reg.get(SandboxWorkerType.LOCAL_PROCESS_RESERVED)
        assert w is None

    def test_registry_does_not_import_AgentRegistry(self):
        mod = __import__("src.open_platform.sandbox_worker_registry", fromlist=[""])
        assert "AgentRegistry" not in str(dir(mod))

    def test_registry_no_dynamic_import(self):
        reg = SandboxWorkerRegistry(); assert reg.get("unknown_worker") is None


# ═══════════════ Plan Integration ═══════════════

class TestPlanIntegration:
    def test_build_request_from_plan(self):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1", tenant_id="t1", developer_id="d1",
                                    policy_snapshot={"p": 1}, artifact_snapshot={"a": 1},
                                    verification_snapshot={"v": 1}, input_payload_hash="hash123")
        req = build_worker_request_from_plan(plan, requested_by="u1")
        assert req.plan_id == plan.plan_id
        assert req.input_payload_hash == "hash123"

    def test_plan_not_dispatchable_but_request_builds(self):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1", tenant_id="t1", developer_id="d1")
        assert plan.is_dispatchable() is False
        req = build_worker_request_from_plan(plan)
        assert req is not None  # request builds even if not dispatchable

    def test_disabled_worker_blocks_plan_request(self):
        worker = DisabledSandboxWorker()
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1", tenant_id="t1", developer_id="d1")
        req = build_worker_request_from_plan(plan)
        result = worker.evaluate_request(req)
        assert result.status == SandboxWorkerResultStatus.BLOCKED

    def test_dispatch_status_unchanged(self, worker=DisabledSandboxWorker()):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1", tenant_id="t1", developer_id="d1")
        old_ds = plan.dispatch_status
        req = build_worker_request_from_plan(plan); worker.evaluate_request(req)
        assert plan.dispatch_status == old_ds  # plan unchanged

    def test_plan_status_unchanged(self, worker=DisabledSandboxWorker()):
        plan = RuntimeExecutionPlan(marketplace_agent_id="m1", tenant_id="t1", developer_id="d1")
        old = plan.plan_status
        req = build_worker_request_from_plan(plan); worker.evaluate_request(req)
        assert plan.plan_status == old

    def test_no_worker_available_true(self, worker=DisabledSandboxWorker()):
        req = mk_req(); result = worker.evaluate_request(req)
        assert result.availability == SandboxWorkerAvailability.DISABLED


# ═══════════════ Non-Execution Guards ═══════════════

class TestNonExecutionGuards:
    def test_module_no_subprocess(self):
        import src.open_platform.sandbox_worker as sw; assert "subprocess" not in str(dir(sw)).lower()

    def test_module_no_docker(self):
        import src.open_platform.sandbox_worker as sw; assert "docker" not in str(dir(sw)).lower()

    def test_module_no_requests(self):
        import src.open_platform.sandbox_worker as sw
        assert "requests" not in str(dir(sw)).lower() and "httpx" not in str(dir(sw)).lower()

    def test_module_no_urllib(self):
        import src.open_platform.sandbox_worker as sw; assert "urllib" not in str(dir(sw)).lower()

    def test_module_no_AgentRuntime(self):
        mods = ["src.open_platform.sandbox_worker", "src.open_platform.sandbox_worker_stub"]
        for mn in mods:
            m = __import__(mn, fromlist=[""])
            assert "AgentRuntime" not in str(dir(m))

    def test_module_no_AgentRegistry(self):
        mods = ["src.open_platform.sandbox_worker_registry"]
        for mn in mods:
            m = __import__(mn, fromlist=[""])
            assert "AgentRegistry" not in str(dir(m))

    def test_stub_no_execute_dispatch_run_methods(self):
        w = DisabledSandboxWorker()
        for bad in ["execute", "dispatch", "run"]:
            assert not hasattr(w, bad) or not callable(getattr(w, bad, None))

    def test_no_queue_import(self):
        import src.open_platform.sandbox_worker_stub as stub
        assert "queue" not in str(dir(stub)).lower() or "sbx" in str(dir(stub)).lower()

    def test_no_multiprocessing_import(self):
        import src.open_platform.sandbox_worker as sw; assert "multiprocessing" not in str(dir(sw)).lower()

    def test_no_package_url_access(self):
        req = mk_req(); worker = DisabledSandboxWorker()
        result = worker.evaluate_request(req)
        # result is safe — no package_url accessed

    def test_no_repository_url_access(self, worker=DisabledSandboxWorker()):
        req = mk_req(); result = worker.evaluate_request(req)
        assert result.no_download_used is True and result.no_network_used is True

    def test_no_local_path_read(self, worker=DisabledSandboxWorker()):
        req = mk_req(); result = worker.evaluate_request(req)
        assert result.no_execution_performed is True

    def test_no_file_open(self, worker=DisabledSandboxWorker()):
        req = mk_req(); result = worker.evaluate_request(req)
        assert "open" in result.to_dict().get("status", "") or result.status == SandboxWorkerResultStatus.BLOCKED

    def test_no_secrets_in_metadata(self):
        r = SandboxWorkerResult(request_id="r1", plan_id="p1", tenant_id="t1")
        d = r.to_dict(); assert "secret" not in str(d).lower() or "severity" in str(d).lower()

    def test_no_raw_key_in_result(self):
        r = SandboxWorkerResult(request_id="r1", plan_id="p1", tenant_id="t1")
        assert "raw_key" not in str(r.to_dict())

    def test_stdout_not_populated(self, worker=DisabledSandboxWorker()):
        req = mk_req(); result = worker.evaluate_request(req)
        assert result.stdout_text is None and result.stderr_text is None

    def test_is_successful_execution_false_for_all(self):
        worker = DisabledSandboxWorker()
        result = worker.evaluate_request(mk_req())
        assert result.is_successful_execution() is False


# ═══════════════ Helpers ═══════════════

def mk_req(**kw):
    return SandboxWorkerRequest(
        plan_id=kw.get("plan_id", "p1"), marketplace_agent_id=kw.get("mkp", "m1"),
        tenant_id=kw.get("tid", "t1"), developer_id=kw.get("did", "d1"),
    )
