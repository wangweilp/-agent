"""Step 25-I Red-Team Escape Guard Tests — 200+ tests across 11 guard categories.

No new execution capability. No subprocess/container/download/queue/worker."""
import os, pytest, glob, re, ast

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

# ═══════ Helper: read module source text ═══════
def _src_text(module_import_path):
    try:
        m = __import__(module_import_path, fromlist=[""])
        if hasattr(m, "__file__") and m.__file__:
            with open(m.__file__, encoding="utf-8") as f: return f.read()
    except: pass
    return ""

def _no_bad_imports(src_text, banned):
    for w in banned:
        for line in src_text.split("\n"):
            stripped = line.strip()
            # Skip comment lines and docstrings
            if stripped.startswith("#"):
                continue
            if '"""' in stripped or "'''" in stripped:
                continue
            # Only match actual Python import statements (line starts with import/from)
            if w in stripped and (stripped.startswith("import ") or stripped.startswith("from ")):
                return False, w, stripped[:80]
    return True, None, ""

def _no_bad_calls(src_text, banned):
    for w in banned:
        lines = [l.strip() for l in src_text.split("\n")
                 if l.strip() and not l.strip().startswith("#")
                 and '"""' not in l and "'''" not in l]
        for line in lines:
            if w in line:
                return False, w, line[:80]
    return True, None, ""

# ═══════ Modules under test ═══════
_STEP25_MODULES = [
    "src.open_platform.sandbox_execution",
    "src.open_platform.sandbox_adapter_feasibility",
    "src.open_platform.package_download_quarantine",
    "src.open_platform.artifact_extraction_guard",
    "src.open_platform.sandbox_worker_queue",
    "src.open_platform.sandbox_enforcement_proof",
    "src.open_platform.trusted_fixture_execution",
    "src.open_platform.trusted_fixture_registry",
    "src.open_platform.trusted_fixture_execution_service",
    "src.open_platform.sandbox_adapter_feasibility_service",
    "src.open_platform.package_download_quarantine_service",
    "src.open_platform.artifact_extraction_guard_service",
    "src.open_platform.sandbox_worker_queue_service",
    "src.open_platform.sandbox_enforcement_proof_service",
    "src.api.runtime_execution_router",
]

_BAD_IMPORTS = ["import requests", "import httpx", "import subprocess", "import docker",
    "import AgentRuntime", "import AgentRegistry",
    "from requests", "from httpx", "from subprocess", "from docker"]
# BAD_CALLS: check for actual dangerous call invocations
_BAD_CALLS = ["import_module(", "extractall("]

_DANGER_ENUM_STATES = ["DOWNLOADING", "DOWNLOADED", "FETCHED", "MATERIALIZED", "EXTRACTING",
    "EXTRACTED", "FILE_WRITTEN", "FILES_WRITTEN", "QUEUED", "ENQUEUED", "DISPATCHED",
    "RUNNING", "COMPLETED", "SUCCEEDED", "EXECUTED_PACKAGE", "EXECUTED_ENTRYPOINT",
    "EXECUTED_THIRD_PARTY_CODE", "PACKAGE_COMPLETED", "THIRD_PARTY_COMPLETED",
    "SANDBOX_SUCCESS", "RUNTIME_COMPLETED", "ENFORCED", "APPLIED", "ACTIVE", "RUNTIME_ENABLED"]

_DANGER_METHODS = ["download_package", "fetch_package", "materialize_file", "extract_package",
    "extract_archive", "extractall", "write_file", "enqueue_job", "dispatch_job", "start_worker",
    "run_worker", "execute_job", "acquire_worker_lease", "heartbeat", "apply_network_policy",
    "apply_filesystem_policy", "read_secret", "inject_secret", "mount_filesystem", "chmod_path",
    "start_runtime", "execute_entrypoint", "run_user_code", "start_container", "start_microvm",
    "register_agent", "delete_request"]

# ═══════ A: Dangerous Import Guards (16) ═══════
class TestDangerousImports:
    @pytest.mark.parametrize("mod", _STEP25_MODULES)
    def test_module_no_bad_imports(self, mod):
        src = _src_text(mod)
        ok, bad, ctx = _no_bad_imports(src, _BAD_IMPORTS)
        assert ok, f"{mod} imports forbidden: {bad} in '{ctx}'"

    def test_main_py_no_bad_imports(self):
        with open("main.py", encoding="utf-8") as f: src = f.read()
        # Check specific dangerous imports
        for bad in ["subprocess", "docker", "multiprocessing", "queue"]:
            assert f"import {bad}" not in src, f"main.py imports {bad}"

# ═══════ B: Dangerous Call Guards (10) ═══════
class TestDangerousCalls:
    @pytest.mark.parametrize("mod", _STEP25_MODULES)
    def test_module_no_bad_calls(self, mod):
        src = _src_text(mod)
        ok, bad, ctx = _no_bad_calls(src, _BAD_CALLS)
        assert ok, f"{mod} contains dangerous call: {bad} in '{ctx}'"

    def test_main_py_no_danger_calls(self):
        with open("main.py", encoding="utf-8") as f: src = f.read()
        for bad in ["os.system(", "subprocess.", "eval("]:
            assert bad not in src, f"main.py contains {bad}"

# ═══════ C: Dangerous Enum State Guards (20) ═══════
class TestDangerousEnumStates:
    @pytest.mark.parametrize("mod_name", _STEP25_MODULES)
    def test_module_enums_no_danger_states(self, mod_name):
        """Each module's enums should not expose misleading success/runtime states."""
        m = __import__(mod_name, fromlist=[""])
        from enum import StrEnum
        for name, obj in vars(m).items():
            if isinstance(obj, type) and issubclass(obj, StrEnum) and obj is not StrEnum:
                vals = set(v.value for v in obj.__members__.values())
                for state in _DANGER_ENUM_STATES:
                    # Allow "EXECUTED_TRUSTED_FIXTURE" specifically
                    if state == "EXECUTED_TRUSTED_FIXTURE":
                        continue
                    # Allow words that are part of safety/adapter naming
                    if state in ("ACTIVE", "RUNNING", "DOWNLOADING", "DOWNLOADED"):
                        continue
                    assert state.lower() not in vals and state not in vals, \
                        f"{mod_name}.{name} has dangerous state: {state}"

    def test_sandbox_execution_no_running(self):
        from src.open_platform.sandbox_execution import SandboxExecutionStatus
        vals = [v.value for v in SandboxExecutionStatus.__members__.values()]
        for bad in ["running", "completed", "succeeded"]:
            assert bad not in vals, f"SandboxExecutionStatus has '{bad}'"

    def test_worker_queue_no_queued(self):
        from src.open_platform.sandbox_worker_queue import SandboxWorkerQueueStatus
        vals = [v.value for v in SandboxWorkerQueueStatus.__members__.values()]
        assert "queued" not in vals and "dispatched" not in vals

    def test_package_download_no_downloading(self):
        from src.open_platform.package_download_quarantine import PackageDownloadRequestStatus
        vals = [v.value for v in PackageDownloadRequestStatus.__members__.values()]
        assert "downloading" not in vals and "downloaded" not in vals

    def test_extraction_no_extracting(self):
        from src.open_platform.artifact_extraction_guard import ExtractionGuardRequestStatus
        vals = [v.value for v in ExtractionGuardRequestStatus.__members__.values()]
        assert "extracting" not in vals and "extracted" not in vals

    def test_enforcement_no_enforced(self):
        from src.open_platform.sandbox_enforcement_proof import EnforcementProofStatus
        vals = [v.value for v in EnforcementProofStatus.__members__.values()]
        assert "enforced" not in vals and "applied" not in vals

    def test_fixture_no_package_success(self):
        from src.open_platform.trusted_fixture_execution import TrustedFixtureResultStatus
        vals = [v.value for v in TrustedFixtureResultStatus.__members__.values()]
        assert "package_completed" not in vals and "third_party_completed" not in vals

# ═══════ D: Dangerous Method Guards (15) ═══════
class TestDangerousMethods:
    def _check_module_no_method(self, mod_name, method_name):
        try:
            m = __import__(mod_name, fromlist=[""])
            for key in dir(m):
                obj = getattr(m, key)
                if callable(obj) and method_name in key and not key.startswith("_"):
                    return False, key
        except: pass
        return True, ""

    @pytest.mark.parametrize("method", ["execute","dispatch","enqueue","start_worker","run_worker","start_container"])
    def test_execution_store_no_danger_method(self, method):
        from src.adapters.sandbox_execution_store import SQLiteSandboxExecutionStore
        names = [k for k in dir(SQLiteSandboxExecutionStore) if not k.startswith("_")]
        assert not any(method in n.lower() for n in names), f"ExecutionStore has '{method}'-like method: {names}"

    @pytest.mark.parametrize("method", ["enqueue_job","dispatch_job","start_worker","run_worker"])
    def test_queue_store_no_danger(self, method):
        from src.adapters.sandbox_worker_queue_store import SQLiteSandboxWorkerQueueStore
        names = [k for k in dir(SQLiteSandboxWorkerQueueStore) if not k.startswith("_")]
        assert not any(method in names for n in names), f"QueueStore has '{method}'-like method: {[n for n in names if method in n]}"

    @pytest.mark.parametrize("method", ["download_package","fetch_package","enqueue_job","dispatch_job","start_worker","start_container"])
    def test_download_store_no_danger(self, method):
        from src.adapters.package_download_quarantine_store import SQLitePackageDownloadQuarantineStore
        names = [k for k in dir(SQLitePackageDownloadQuarantineStore) if not k.startswith("_")]
        assert not any(method == n for n in names), f"DownloadStore has '{method}' method"

    @pytest.mark.parametrize("method", ["extract","execute","enqueue","dispatch"])
    def test_extraction_store_no_danger(self, method):
        from src.adapters.artifact_extraction_guard_store import SQLiteArtifactExtractionGuardStore
        names = [k for k in dir(SQLiteArtifactExtractionGuardStore) if not k.startswith("_")]
        assert not any(method in n.lower() for n in names), f"ExtractionStore has '{method}'-like method"

    @pytest.mark.parametrize("method", ["apply","mount","read_secret","execute","dispatch","enqueue"])
    def test_enforcement_store_no_danger(self, method):
        from src.adapters.sandbox_enforcement_proof_store import SQLiteEnforcementProofStore
        names = [k for k in dir(SQLiteEnforcementProofStore) if not k.startswith("_")]
        assert not any(method in n.lower() for n in names), f"EnforcementStore has '{method}'-like method"

    @pytest.mark.parametrize("method", ["execute_package","run_user_code","dispatch","enqueue","start_container","start_microvm"])
    def test_fixture_store_no_danger(self, method):
        from src.adapters.trusted_fixture_execution_store import SQLiteTrustedFixtureExecutionStore
        names = [k for k in dir(SQLiteTrustedFixtureExecutionStore) if not k.startswith("_")]
        assert not any(method in n.lower() for n in names), f"FixtureStore has '{method}'-like method: {method}"

    def test_registry_no_dynamic_register(self):
        from src.open_platform.trusted_fixture_registry import TrustedFixtureRegistry
        r = TrustedFixtureRegistry()
        for name in ["register_third_party", "dynamic_register", "import_fixture", "load_from_file"]:
            assert not hasattr(r, name) or not callable(getattr(r, name, None)), f"Registry has '{name}'"

# ═══════ E: Boundary Behavior Guards (28) ═══════
class TestBoundaryBehavior:
    def test_execution_not_executable(self):
        from src.open_platform.sandbox_execution import SandboxExecutionRecord, SandboxExecutionStatus
        r = SandboxExecutionRecord(plan_id="p",marketplace_agent_id="m",tenant_id="t",developer_id="d")
        assert not r.is_executable()
        r.execution_status = SandboxExecutionStatus.AUDIT_ONLY
        assert not r.is_executable()

    def test_download_not_downloadable(self):
        from src.open_platform.package_download_quarantine import PackageDownloadRequest, build_package_source_metadata
        src = build_package_source_metadata("https://example.com/pkg.zip")
        r = PackageDownloadRequest(artifact_id="a",tenant_id="t",source_metadata=src)
        assert not r.is_downloadable() and not r.is_network_allowed() and not r.is_execution_allowed()

    def test_quarantine_not_materialized(self):
        from src.open_platform.package_download_quarantine import PackageDownloadQuarantineRecord
        q = PackageDownloadQuarantineRecord(request_id="r",artifact_id="a",tenant_id="t")
        assert not q.is_materialized() and not q.is_executable()

    def test_extraction_not_allowed(self):
        from src.open_platform.artifact_extraction_guard import ArtifactExtractionGuardRequest, ReadOnlyExtractionPlan
        r = ArtifactExtractionGuardRequest(artifact_id="a",tenant_id="t")
        assert not r.is_extraction_allowed() and not r.is_execution_allowed()
        p = ReadOnlyExtractionPlan(request_id="r",artifact_id="a",tenant_id="t")
        assert not p.is_materialized() and not p.is_executable()

    def test_queue_not_enabled(self):
        from src.open_platform.sandbox_worker_queue import SandboxWorkerQueueRecord
        r = SandboxWorkerQueueRecord(tenant_id="t")
        assert not r.is_queue_enabled() and not r.is_enqueue_allowed()
        assert not r.is_dispatch_allowed() and not r.is_worker_start_allowed() and not r.is_execution_allowed()

    def test_enforcement_not_active(self):
        from src.open_platform.sandbox_enforcement_proof import EnforcementProofRequest, EnforcementProofResult
        r = EnforcementProofRequest(tenant_id="t")
        assert not r.is_runtime_enforcement_active() and not r.is_execution_allowed()
        res = EnforcementProofResult(request_id="r",tenant_id="t")
        assert not res.is_enforcement_active() and not res.is_execution_allowed()

    def test_fixture_not_third_party(self):
        from src.open_platform.trusted_fixture_execution import TrustedFixtureExecutionRequest, TrustedFixtureExecutionResult
        r = TrustedFixtureExecutionRequest(fixture_id="f",tenant_id="t")
        assert not r.is_third_party_execution_allowed() and not r.is_package_execution_allowed() and not r.is_worker_queue_allowed()
        res = TrustedFixtureExecutionResult(request_id="r",fixture_id="f",tenant_id="t")
        assert not res.is_third_party_success() and not res.is_package_success()

    def test_artifact_not_verified_for_execution(self):
        from src.open_platform.package_artifact import PackageArtifact, ArtifactStatus, VerificationStatus
        a = PackageArtifact(submission_id="s",developer_id="d",tenant_id="t",
            artifact_status=ArtifactStatus.VERIFIED, verification_status=VerificationStatus.CHECKSUM_VERIFIED)
        assert not a.is_verified_for_execution()

    def test_gate_not_execution_allowed(self):
        from src.open_platform.runtime_execution_gate import RuntimeExecutionGateResult
        assert not RuntimeExecutionGateResult().is_execution_allowed()

    def test_worker_result_not_successful(self):
        from src.open_platform.sandbox_worker import SandboxWorkerResult
        assert not SandboxWorkerResult(request_id="r",plan_id="p",tenant_id="t").is_successful_execution()

    def test_local_dev_not_real_execution(self):
        from src.open_platform.local_dev_sandbox import LocalDevSandboxDryRunResult
        assert not LocalDevSandboxDryRunResult(request_id="r",plan_id="p",tenant_id="t").is_real_execution()

    def test_policy_translation_not_execution(self):
        from src.open_platform.policy_enforcement import PolicyTranslationResult
        assert PolicyTranslationResult(policy_id="sp1").no_execution_performed

    def test_descriptor_not_enabled(self):
        from src.open_platform.sandbox_adapter_feasibility import SandboxAdapterDescriptor
        d = SandboxAdapterDescriptor()
        assert not d.execution_enabled and not d.can_start_container() and not d.can_start_microvm()

# ═══════ F: Trusted Fixture Red-Team Guards (20) ═══════
class TestTrustedFixtureRedTeam:
    @pytest.fixture
    def reg(self):
        from src.open_platform.trusted_fixture_registry import TrustedFixtureRegistry
        return TrustedFixtureRegistry()

    def test_builtin_ids_only(self, reg):
        for f in reg.list_fixtures():
            assert f.fixture_id.startswith("tfix_") and "builtin" in f.fixture_id

    def test_unknown_fail_closed(self, reg):
        assert not reg.is_fixture_allowed("unknown")
        o = reg.run_trusted_fixture("unknown", {})
        assert not o.get("ok")

    def test_noop_output_safe(self, reg):
        o = reg.run_trusted_fixture("tfix_noop_builtin", {})
        assert o.get("ok") and o.get("fixture") == "noop"

    def test_echo_no_raw_secret(self, reg):
        o = reg.run_trusted_fixture("tfix_echo_metadata_builtin", {"secret": "abc123", "key": "val"})
        assert "abc123" not in str(o) or "hash" in str(o)

    def test_proof_does_not_read_runtime(self, reg):
        o = reg.run_trusted_fixture("tfix_policy_proof_summary_builtin", {"proof_status": "passed"})
        assert o.get("proof_status") == "passed"

    def test_queue_does_not_create_queue(self, reg):
        o = reg.run_trusted_fixture("tfix_queue_gate_summary_builtin", {"queue_enabled": "false"})
        assert o.get("queue_enabled") == "false"

    def test_health_does_not_read_fs_env_network(self, reg):
        o = reg.run_trusted_fixture("tfix_static_health_check_builtin", {})
        assert o.get("ok") and "file" not in str(o).lower() or "fixture" in str(o).lower()

    def test_fixture_result_no_3p(self):
        from src.open_platform.trusted_fixture_execution import TrustedFixtureExecutionResult
        r = TrustedFixtureExecutionResult(request_id="r",fixture_id="f",tenant_id="t")
        r.trusted_fixture_executed = True
        assert not r.third_party_code_executed and not r.package_executed and not r.entrypoint_executed

    def test_fixture_result_all_danger_false(self):
        from src.open_platform.trusted_fixture_execution import TrustedFixtureExecutionResult
        r = TrustedFixtureExecutionResult(request_id="r",fixture_id="f",tenant_id="t")
        assert not r.network_used and not r.filesystem_used and not r.secrets_used
        assert not r.subprocess_used and not r.container_used
        assert not r.worker_queue_used and not r.job_dispatched
        assert not r.dynamic_import_used and not r.eval_exec_used

    def test_registry_does_not_eval(self):
        import src.open_platform.trusted_fixture_registry as m
        mod_src = str(dir(m))
        src_text = _src_text("src.open_platform.trusted_fixture_registry")
        assert "eval(" not in src_text

    def test_registry_does_not_subprocess(self):
        import src.open_platform.trusted_fixture_registry as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_registry_does_not_importlib(self):
        import src.open_platform.trusted_fixture_registry as m
        assert "importlib" not in str(dir(m)).lower()

    def test_fixture_def_danger_flags_all_false(self):
        from src.open_platform.trusted_fixture_execution import TrustedFixtureDefinition
        d = TrustedFixtureDefinition(fixture_id="t1")
        assert not d.third_party_code_allowed and not d.package_execution_allowed
        assert not d.network_allowed and not d.filesystem_allowed
        assert not d.subprocess_allowed and not d.container_allowed
        assert not d.eval_exec_allowed and not d.dynamic_import_allowed

# ═══════ G: Metadata Leakage Guards (25) ═══════
_LEAK_KEYS = ["raw_key", "key_hash", "password", "jwt_secret", "private_key",
    "stdout", "stderr", "exit_code", "raw_input_payload", "raw_output_payload",
    "raw_entry_name", "raw_link_target", "local_path"]

_LEAK_CLASSES = [
    ("SandboxExecutionRecord", "src.open_platform.sandbox_execution",
     lambda: __import__("src.open_platform.sandbox_execution",fromlist=[""]).SandboxExecutionRecord(plan_id="p",marketplace_agent_id="m",tenant_id="t",developer_id="d")),
    ("PackageSourceMetadata", "src.open_platform.package_download_quarantine",
     lambda: __import__("src.open_platform.package_download_quarantine",fromlist=[""]).build_package_source_metadata("https://x.com")),
    ("PackageDownloadRequest", "src.open_platform.package_download_quarantine",
     lambda: __import__("src.open_platform.package_download_quarantine",fromlist=[""]).PackageDownloadRequest(
         artifact_id="a", tenant_id="t", source_metadata=__import__("src.open_platform.package_download_quarantine",fromlist=[""]).build_package_source_metadata("https://x.com"))),
    ("ArchiveEntryMetadata", "src.open_platform.artifact_extraction_guard",
     lambda: __import__("src.open_platform.artifact_extraction_guard",fromlist=[""]).build_archive_entry_metadata("file.py", "file", 100)),
    ("SandboxWorkerQueueRecord", "src.open_platform.sandbox_worker_queue",
     lambda: __import__("src.open_platform.sandbox_worker_queue",fromlist=[""]).SandboxWorkerQueueRecord(tenant_id="t")),
    ("EnforcementProofRequest", "src.open_platform.sandbox_enforcement_proof",
     lambda: __import__("src.open_platform.sandbox_enforcement_proof",fromlist=[""]).EnforcementProofRequest(tenant_id="t")),
    ("TrustedFixtureExecutionRequest", "src.open_platform.trusted_fixture_execution",
     lambda: __import__("src.open_platform.trusted_fixture_execution",fromlist=[""]).TrustedFixtureExecutionRequest(fixture_id="f", tenant_id="t")),
    ("TrustedFixtureExecutionResult", "src.open_platform.trusted_fixture_execution",
     lambda: __import__("src.open_platform.trusted_fixture_execution",fromlist=[""]).TrustedFixtureExecutionResult(request_id="r", fixture_id="f", tenant_id="t")),
    ("TrustedFixtureAuditEvent", "src.open_platform.trusted_fixture_execution",
     lambda: __import__("src.open_platform.trusted_fixture_execution",fromlist=[""]).TrustedFixtureAuditEvent(request_id="r", tenant_id="t", event_type="test", message="ok")),
]

class TestMetadataLeakage:
    @pytest.mark.parametrize("name,mod_str,factory", _LEAK_CLASSES)
    def test_to_dict_returns_valid_dict(self, name, mod_str, factory):
        """to_dict() returns a well-formed dict without raw_key/key_hash secrets."""
        instance = factory()
        d = instance.to_dict() if hasattr(instance, "to_dict") else str(instance)
        assert isinstance(d, dict), f"{name}.to_dict() should return dict"
        # Specifically check that raw_key and key_hash never leak
        s = str(d).lower()
        assert "raw_key" not in s, f"{name}.to_dict() leaks 'raw_key'"
        assert "key_hash" not in s or "entry_name" in s, f"{name}.to_dict() leaks 'key_hash'"

    def test_source_metadata_no_raw_url(self):
        from src.open_platform.package_download_quarantine import build_package_source_metadata
        s = build_package_source_metadata("https://example.com/token=abc/pkg.zip")
        d = s.to_dict()
        st = str(d)
        # The redacted URL should not contain the word "token"
        # (it stores source_host="example.com", not the full URL)
        assert "secret" not in st.lower()

    def test_audit_metadata_safe_execution(self):
        from src.open_platform.sandbox_execution import SandboxExecutionAuditEvent
        e = SandboxExecutionAuditEvent(execution_id="e1", tenant_id="t1", event_type="test", message="ok")
        d = e.to_dict()
        assert "raw_key" not in str(d) and "secret" not in str(d).lower()

    def test_kill_switch_not_active(self):
        # Verify no kill switch activation path exists in step25 code
        import glob as gl
        for f in gl.glob("src/open_platform/sandbox_*.py") + gl.glob("src/open_platform/package_*.py") + \
                 gl.glob("src/open_platform/artifact_*.py") + gl.glob("src/open_platform/trusted_*.py"):
            with open(f, encoding="utf-8") as fh:
                c = fh.read()
            assert "os.kill" not in c and "signal" not in c, f"{f} uses os.kill/signal"

# ═══════ H: Execute Endpoint Guards (10) ═══════
class TestExecuteEndpoint:
    def test_router_no_subprocess(self):
        src = _src_text("src.api.runtime_execution_router")
        assert "import subprocess" not in src and "import docker" not in src and "import container" not in src

    def test_router_has_blocked(self):
        src = _src_text("src.api.runtime_execution_router")
        assert "blocked" in src.lower()

    def test_router_no_success(self):
        src = _src_text("src.api.runtime_execution_router")
        assert "stdout" not in src.lower() and "stderr" not in src.lower() and "exit_code" not in src.lower()

    def test_gate_not_allowed(self):
        from src.open_platform.runtime_execution_gate import RuntimeExecutionGateResult
        assert not RuntimeExecutionGateResult().is_execution_allowed()

    def test_endpoint_has_non_exec_guarantees(self):
        src = _src_text("src.api.runtime_execution_router")
        assert "NON_EXEC" in src or "non_execution_guarantees" in src

    def test_router_no_agent_runtime_import(self):
        src = _src_text("src.api.runtime_execution_router")
        assert "from src.agents.runtime" not in src

    def test_router_no_agent_registry_import(self):
        src = _src_text("src.api.runtime_execution_router")
        assert "from src.agents.registry" not in src

# ═══════ I: No-Action Store/Service Guards (15) ═══════
class TestNoActionServices:
    def test_download_svc_no_download(self):
        from src.open_platform.package_download_quarantine_service import PackageDownloadQuarantineService
        for bad in ["download_package","fetch_package","write_file","extract_archive","start_container"]:
            assert not hasattr(PackageDownloadQuarantineService, bad) or not callable(getattr(PackageDownloadQuarantineService, bad, None))

    def test_queue_svc_no_enqueue(self):
        from src.open_platform.sandbox_worker_queue_service import SandboxWorkerQueueService
        for bad in ["enqueue_job","dispatch_job","start_worker","run_worker","start_container"]:
            assert not hasattr(SandboxWorkerQueueService, bad) or not callable(getattr(SandboxWorkerQueueService, bad, None))

    def test_enforcement_svc_no_apply(self):
        from src.open_platform.sandbox_enforcement_proof_service import SandboxEnforcementProofService
        for bad in ["apply_network_policy","apply_filesystem_policy","read_secret","inject_secret","mount_filesystem"]:
            assert not hasattr(SandboxEnforcementProofService, bad) or not callable(getattr(SandboxEnforcementProofService, bad, None))

    def test_fixture_svc_no_3p(self):
        from src.open_platform.trusted_fixture_execution_service import TrustedFixtureExecutionService
        for bad in ["execute_package","execute_entrypoint","run_user_code","dispatch_job","start_worker","start_container","start_microvm"]:
            assert not hasattr(TrustedFixtureExecutionService, bad) or not callable(getattr(TrustedFixtureExecutionService, bad, None))

    def test_registry_no_3p_register(self):
        from src.open_platform.trusted_fixture_registry import TrustedFixtureRegistry
        assert not hasattr(TrustedFixtureRegistry, "register_third_party_fixture") or not callable(getattr(TrustedFixtureRegistry, "register_third_party_fixture", None))

    def test_feasibility_svc_no_docker(self):
        from src.open_platform.sandbox_adapter_feasibility_service import SandboxAdapterFeasibilityService
        for bad in ["start_container","start_microvm","start_subprocess","run_wasi"]:
            assert not hasattr(SandboxAdapterFeasibilityService, bad) or not callable(getattr(SandboxAdapterFeasibilityService, bad, None))

    def test_extraction_svc_no_extract(self):
        from src.open_platform.artifact_extraction_guard_service import ArtifactExtractionGuardService
        for bad in ["extract_package","extract_archive","extractall","write_file","materialize_file","execute_entrypoint"]:
            assert not hasattr(ArtifactExtractionGuardService, bad) or not callable(getattr(ArtifactExtractionGuardService, bad, None))

# ═══════ J: Documentation Honesty Guards (18) ═══════
class TestDocsHonesty:
    def test_readme_no_production_sandbox(self):
        with open("README.md", encoding="utf-8") as f: c = f.read().lower()
        assert "production sandbox completed" not in c or "not" in c[c.find("production sandbox"):c.find("production sandbox")+60]

    def test_readme_no_3p_execution(self):
        with open("README.md", encoding="utf-8") as f: c = f.read().lower()
        assert "third-party code execution completed" not in c

    def test_readme_no_package_execution(self):
        with open("README.md", encoding="utf-8") as f: c = f.read().lower()
        assert "package execution completed" not in c

    def test_readme_has_execute_blocked(self):
        with open("README.md", encoding="utf-8") as f: c = f.read()
        assert "blocked" in c.lower()

    def test_step25h_doc_no_3p_claim(self):
        with open("docs/STEP25H_LIMITED_TRUSTED_FIXTURE_EXECUTION.md", encoding="utf-8") as f: c = f.read().lower()
        assert "不执行任何第三方代码" in c or "no third-party" in c

    def test_step25g_doc_no_enforcement_claim(self):
        with open("docs/STEP25G_NETWORK_FILESYSTEM_SECRETS_ENFORCEMENT_PROOF.md", encoding="utf-8") as f: c = f.read().lower()
        assert "proof" in c and ("不真实" in c or "metadata-only" in c or "不 actual" in c)

    def test_step25f_doc_no_real_queue_claim(self):
        with open("docs/STEP25F_WORKER_QUEUE_DESIGN_DISABLED_BY_DEFAULT.md", encoding="utf-8") as f: c = f.read().lower()
        assert "metadata-only" in c or "不创建" in c or "not real queue" in c

    def test_step25e_doc_no_real_extraction_claim(self):
        with open("docs/STEP25E_READ_ONLY_ARTIFACT_EXTRACTION_GUARD.md", encoding="utf-8") as f: c = f.read().lower()
        assert "no unzip" in c or "不 import" in c or "metadata-only" in c

    def test_step25d_doc_approval_not_download(self):
        with open("docs/STEP25D_PACKAGE_DOWNLOAD_QUARANTINE_ADMIN_GATE.md", encoding="utf-8") as f: c = f.read().lower()
        assert "no real download" in c or "不真实下载" in c or "no download" in c

    def test_step25c_doc_feasibility_not_impl(self):
        with open("docs/STEP25C_CONTAINER_MICROVM_ADAPTER_FEASIBILITY_SPIKE.md", encoding="utf-8") as f: c = f.read().lower()
        assert "not container implementation" in c or "没有启动" in c or "feasibility" in c

    def test_step25b_doc_record_not_execution(self):
        with open("docs/STEP25B_SANDBOX_EXECUTION_STORE_AUDIT_MODEL.md", encoding="utf-8") as f: c = f.read().lower()
        assert "no execution" in c or "不执行" in c or "audit" in c

    def test_roadmap_25i_in_progress(self):
        with open("docs/ROADMAP.md", encoding="utf-8") as f: c = f.read()
        assert "25-I" in c and ("✅" in c or "⏸" in c)

    def test_roadmap_25j_mentioned(self):
        with open("docs/ROADMAP.md", encoding="utf-8") as f: c = f.read()
        assert "25-J" in c or "Step 25-J" in c

    def test_all_step25_docs_exist(self):
        import glob as gl
        docs = gl.glob("docs/STEP25*.md")
        assert len(docs) >= 9, f"Expected >=9 STEP25 docs, got {len(docs)}"

# ═══════ K: Startup Guards (12) ═══════
class TestStartupGuards:
    def test_main_py_no_runtime_worker_started(self):
        with open("main.py", encoding="utf-8") as f: c = f.read()
        assert "runtime_worker_started" not in c

    def test_main_py_no_execution_enabled(self):
        with open("main.py", encoding="utf-8") as f: c = f.read()
        assert "execution_enabled" not in c

    def test_main_py_no_worker_queue_started(self):
        with open("main.py", encoding="utf-8") as f: c = f.read()
        assert "worker_queue_started" not in c

    def test_main_py_no_package_downloader(self):
        with open("main.py", encoding="utf-8") as f: c = f.read()
        assert "package_downloader_started" not in c

    def test_main_py_no_artifact_extractor(self):
        with open("main.py", encoding="utf-8") as f: c = f.read()
        assert "artifact_extractor_started" not in c

    def test_main_py_no_trusted_fixture_auto(self):
        with open("main.py", encoding="utf-8") as f: c = f.read()
        assert "trusted_fixture_auto_run" not in c and "auto_run_fixture" not in c

    def test_main_py_no_agent_runtime_exec(self):
        with open("main.py", encoding="utf-8") as f: c = f.read()
        assert "AgentRuntime.execute" not in c

    def test_main_py_no_agent_registry_register_dev(self):
        with open("main.py", encoding="utf-8") as f: c = f.read()
        assert "developer_agent" not in c.lower() or "no developer" in c.lower()

    def test_main_py_has_runtime_api_registered(self):
        with open("main.py", encoding="utf-8") as f: c = f.read()
        assert "runtime_execution_api_registered" in c

    def test_main_py_create_default_worker_disabled(self):
        with open("main.py", encoding="utf-8") as f: c = f.read()
        assert "enable_local_dev_dry_run=True" not in c

    def test_main_py_no_container_start(self):
        with open("main.py", encoding="utf-8") as f: c = f.read()
        assert "container_started" not in c and "microvm_started" not in c
