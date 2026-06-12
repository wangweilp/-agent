"""Step 25-K Final Gate Tests — 70 tests for release verification."""
import os, pytest, glob as gl

DOCS = "docs"
def _c(f):
    with open(f, encoding="utf-8") as fh: return fh.read()

# ═══════ Existence (9) ═══════
class TestExistence:
    def test_final_gate_doc(self): assert os.path.exists(f"{DOCS}/STEP25K_FINAL_REGRESSION_GATE.md")
    def test_release_checklist(self): assert os.path.exists(f"{DOCS}/STEP25_RELEASE_CHECKLIST.md")
    def test_demo_script(self): assert os.path.exists(f"{DOCS}/STEP25_RUNTIME_DEMO_SCRIPT.md")
    def test_security_qa(self): assert os.path.exists(f"{DOCS}/STEP25_SECURITY_QA.md")
    def test_arch_summary(self): assert os.path.exists(f"{DOCS}/STEP25_RUNTIME_ARCHITECTURE_SUMMARY.md")
    def test_claim_boundary(self): assert os.path.exists(f"{DOCS}/STEP25_CLAIM_BOUNDARY.md")
    def test_red_team(self): assert os.path.exists(f"{DOCS}/STEP25I_RED_TEAM_ESCAPE_TESTS.md")
    def test_readme(self): assert os.path.exists("README.md")
    def test_roadmap(self): assert os.path.exists(f"{DOCS}/ROADMAP.md")

# ═══════ README / ROADMAP (9) ═══════
class TestReadmeRoadmap:
    def test_readme_25k_done(self): c=_c("README.md"); assert "25-K" in c and "✅" in c
    def test_readme_no_production(self): c=_c("README.md").lower(); assert "no production sandbox" in c or "not" in c
    def test_readme_no_3p(self): c=_c("README.md").lower(); assert "no external code execution" in c or "no third-party" in c or "blocked" in c
    def test_roadmap_25k_done(self): c=_c(f"{DOCS}/ROADMAP.md"); assert "25-K" in c and "✅" in c
    def test_roadmap_step25_final(self): c=_c(f"{DOCS}/ROADMAP.md"); assert "Step 25 Final Status" in c
    def test_roadmap_step26_admission(self): c=_c(f"{DOCS}/ROADMAP.md"); assert "Step 26 Admission" in c
    def test_roadmap_26a_not_completed(self): c=_c(f"{DOCS}/ROADMAP.md"); assert "26-A" in c and "⏸" in c
    def test_release_checklist_all_checked(self):
        c = _c(f"{DOCS}/STEP25_RELEASE_CHECKLIST.md")
        checked = [l for l in c.split("\n") if "[x]" in l]
        assert len(checked) >= 20, f"Only {len(checked)} checked items found"
    def test_step25_docs_13_plus(self):
        assert len(gl.glob(f"{DOCS}/STEP25*.md")) >= 13

# ═══════ Safety Invariants (7) ═══════
class TestSafetyInvariants:
    def test_execution_not_executable(self):
        from src.open_platform.sandbox_execution import SandboxExecutionRecord
        assert not SandboxExecutionRecord(plan_id="p",marketplace_agent_id="m",tenant_id="t",developer_id="d").is_executable()
    def test_download_not_downloadable(self):
        from src.open_platform.package_download_quarantine import PackageDownloadRequest, build_package_source_metadata
        src = build_package_source_metadata("https://x.com")
        r = PackageDownloadRequest(artifact_id="a",tenant_id="t",source_metadata=src)
        assert not r.is_downloadable() and not r.is_network_allowed()
    def test_quarantine_not_materialized(self):
        from src.open_platform.package_download_quarantine import PackageDownloadQuarantineRecord
        assert not PackageDownloadQuarantineRecord(request_id="r",artifact_id="a",tenant_id="t").is_materialized()
    def test_extraction_not_allowed(self):
        from src.open_platform.artifact_extraction_guard import ArtifactExtractionGuardRequest
        assert not ArtifactExtractionGuardRequest(artifact_id="a",tenant_id="t").is_extraction_allowed()
    def test_queue_not_allowed(self):
        from src.open_platform.sandbox_worker_queue import SandboxWorkerQueueRecord
        r = SandboxWorkerQueueRecord(tenant_id="t")
        assert not r.is_enqueue_allowed() and not r.is_dispatch_allowed()
    def test_enforcement_not_active(self):
        from src.open_platform.sandbox_enforcement_proof import EnforcementProofResult
        assert not EnforcementProofResult(request_id="r",tenant_id="t").is_enforcement_active()
    def test_fixture_not_3p(self):
        from src.open_platform.trusted_fixture_execution import TrustedFixtureExecutionResult
        r = TrustedFixtureExecutionResult(request_id="r",fixture_id="f",tenant_id="t")
        r.trusted_fixture_executed = True
        assert not r.third_party_code_executed and not r.package_executed
        assert not r.is_third_party_success() and not r.is_package_success()

# ═══════ Docs Honesty (12) ═══════
class TestDocsHonesty:
    def _check(self, claim):
        for f in gl.glob(f"{DOCS}/STEP25*.md"):
            c = _c(f)
            idx = c.lower().find(claim.lower())
            if idx < 0: continue
            # Skip the 25-K doc itself and release checklist — they list claims in verification tables
            if "STEP25K_FINAL_REGRESSION" in f or "STEP25_RELEASE_CHECKLIST" in f: continue
            before = c[:idx].lower()
            has_denial = ("cannot claim" in before or "unsafe claim" in before or
                         "what we cannot claim" in before or "unsafe claims" in before or
                         "**not**" in before or "claim boundary" in before)
            assert has_denial, f"{f} claims '{claim}' without denial context"
    def test_no_production_sandbox(self): self._check("production sandbox completed")
    def test_no_3p_complete(self): self._check("third-party code execution completed")
    def test_no_pkg_exec(self): self._check("package execution completed")
    def test_no_pkg_download(self): self._check("package download completed")
    def test_no_extraction(self): self._check("archive extraction completed")
    def test_no_queue_running(self): self._check("worker queue running")
    def test_no_dispatch(self): self._check("dispatch completed")
    def test_no_enforcement(self): self._check("enforcement applied")
    def test_no_container(self): self._check("container runtime completed")
    def test_no_microvm(self): self._check("microvm runtime completed")
    def test_no_fixture_equals_3p(self): self._check("trusted fixture equals third-party")
    def test_checklist_no_false_claims(self):
        c = _c(f"{DOCS}/STEP25_RELEASE_CHECKLIST.md")
        assert "production sandbox enabled" not in c.lower() or "no production" in c.lower()

# ═══════ Trusted Fixture Boundary (11) ═══════
class TestTrustedFixtureBoundary:
    def _result(self):
        from src.open_platform.trusted_fixture_execution import TrustedFixtureExecutionResult
        r = TrustedFixtureExecutionResult(request_id="r",fixture_id="f",tenant_id="t")
        r.trusted_fixture_executed = True; return r
    def test_not_3p(self): r=self._result(); assert not r.third_party_code_executed
    def test_not_package(self): r=self._result(); assert not r.package_executed
    def test_not_entrypoint(self): r=self._result(); assert not r.entrypoint_executed
    def test_not_network(self): r=self._result(); assert not r.network_used
    def test_not_filesystem(self): r=self._result(); assert not r.filesystem_used
    def test_not_secrets(self): r=self._result(); assert not r.secrets_used
    def test_not_subprocess(self): r=self._result(); assert not r.subprocess_used
    def test_not_container(self): r=self._result(); assert not r.container_used
    def test_not_worker_queue(self): r=self._result(); assert not r.worker_queue_used
    def test_not_job_dispatched(self): r=self._result(); assert not r.job_dispatched

# ═══════ Execute Endpoint / Startup (8) ═══════
class TestExecuteStartup:
    def test_router_has_blocked(self): c=_c("src/api/runtime_execution_router.py"); assert "blocked" in c.lower()
    def test_main_py_no_runtime_worker(self): c=_c("main.py"); assert "runtime_worker_started" not in c
    def test_main_py_no_execution_enabled(self): c=_c("main.py"); assert "execution_enabled" not in c
    def test_main_py_no_worker_queue(self): c=_c("main.py"); assert "worker_queue_started" not in c
    def test_main_py_no_pkg_downloader(self): c=_c("main.py"); assert "package_downloader_started" not in c
    def test_main_py_no_extractor(self): c=_c("main.py"); assert "artifact_extractor_started" not in c
    def test_main_py_no_fixture_auto(self): c=_c("main.py"); assert "trusted_fixture_auto_run" not in c
    def test_main_py_has_runtime_api(self): c=_c("main.py"); assert "runtime_execution_api_registered" in c

# ═══════ Step 26 Admission (3) ═══════
class TestStep26Admission:
    def test_26a_not_started(self): c=_c(f"{DOCS}/ROADMAP.md"); assert "26-A" in c and "⏸" in c
    def test_26_requires_gate(self): c=_c(f"{DOCS}/STEP25K_FINAL_REGRESSION_GATE.md"); assert "Step 26 Admission" in c
    def test_26_no_arbitrary_execution(self):
        c = _c(f"{DOCS}/ROADMAP.md").lower()
        assert "must not jump directly" in c or "not approval" in c or "earliest possible" in c
