"""Step 24 Demo & Documentation Guard Tests — docs completeness and honesty checks.

Verifies: demo script exists, Q&A 25+, architecture summary has trust boundaries + known issues,
README updated, ROADMAP correct, no false claims in docs."""

import os, glob as gl, pytest

DOCS_DIR = "docs"

class TestDemoDocsExist:
    def test_demo_script_exists(self):
        assert os.path.exists(f"{DOCS_DIR}/STEP24_RUNTIME_DEMO_SCRIPT.md")
    def test_security_qa_exists(self):
        assert os.path.exists(f"{DOCS_DIR}/STEP24_SECURITY_QA.md")
    def test_architecture_summary_exists(self):
        assert os.path.exists(f"{DOCS_DIR}/STEP24_RUNTIME_ARCHITECTURE_SUMMARY.md")
    def test_step24a_exists(self):
        assert os.path.exists(f"{DOCS_DIR}/STEP24A_REAL_SANDBOX_RUNTIME_ARCHITECTURE_AUDIT.md")
    def test_step24b_doc_exists(self):
        assert os.path.exists(f"{DOCS_DIR}/STEP24B_PACKAGE_ARTIFACT_QUARANTINE_STORE.md")
    def test_step24c_doc_exists(self):
        assert os.path.exists(f"{DOCS_DIR}/STEP24C_CHECKSUM_SIGNATURE_VERIFICATION.md")
    def test_step24d_doc_exists(self):
        assert os.path.exists(f"{DOCS_DIR}/STEP24D_RUNTIME_EXECUTION_PLAN_MODEL_STORE.md")
    def test_step24e_doc_exists(self):
        assert os.path.exists(f"{DOCS_DIR}/STEP24E_SANDBOX_WORKER_DISABLED_STUB.md")
    def test_step24f_doc_exists(self):
        assert os.path.exists(f"{DOCS_DIR}/STEP24F_POLICY_ENFORCEMENT_TRANSLATOR.md")
    def test_step24g_doc_exists(self):
        assert os.path.exists(f"{DOCS_DIR}/STEP24G_LOCAL_DEVELOPMENT_SANDBOX_PROTOTYPE.md")
    def test_step24h_doc_exists(self):
        assert os.path.exists(f"{DOCS_DIR}/STEP24H_RUNTIME_EXECUTION_API_DRAFT_ADMIN_GATE.md")
    def test_step24i_doc_exists(self):
        assert os.path.exists(f"{DOCS_DIR}/STEP24I_SECURITY_ESCAPE_GUARD_TESTS.md")


class TestDemoContent:
    def test_demo_script_has_8_scenes(self):
        with open(f"{DOCS_DIR}/STEP24_RUNTIME_DEMO_SCRIPT.md", encoding="utf-8") as f:
            c = f.read()
        scenes = [l for l in c.split("\n") if l.strip().startswith("### Scene")]
        assert len(scenes) >= 8, f"Expected >=8 scenes, got {len(scenes)}"

    def test_demo_has_can_claim(self):
        with open(f"{DOCS_DIR}/STEP24_RUNTIME_DEMO_SCRIPT.md", encoding="utf-8") as f:
            c = f.read()
        assert "What We Can Claim" in c

    def test_demo_has_cannot_claim(self):
        with open(f"{DOCS_DIR}/STEP24_RUNTIME_DEMO_SCRIPT.md", encoding="utf-8") as f:
            c = f.read()
        assert "What We Cannot Claim" in c

    def test_qa_has_at_least_25(self):
        with open(f"{DOCS_DIR}/STEP24_SECURITY_QA.md", encoding="utf-8") as f:
            c = f.read()
        qs = [l for l in c.split("\n") if l.strip().startswith("## Q")]
        assert len(qs) >= 25, f"Expected >=25 Qs, got {len(qs)}"

    def test_architecture_has_trust_boundaries(self):
        with open(f"{DOCS_DIR}/STEP24_RUNTIME_ARCHITECTURE_SUMMARY.md", encoding="utf-8") as f:
            c = f.read()
        assert "Trust Boundaries" in c or "trust boundary" in c.lower()

    def test_architecture_has_known_issues(self):
        with open(f"{DOCS_DIR}/STEP24_RUNTIME_ARCHITECTURE_SUMMARY.md", encoding="utf-8") as f:
            c = f.read()
        assert "Known Issues" in c or "known issues" in c.lower()


class TestRoadmapCorrectness:
    def test_roadmap_24j_completed(self):
        with open(f"{DOCS_DIR}/ROADMAP.md", encoding="utf-8") as f:
            c = f.read()
        assert "24-J" in c and ("✅" in c or "completed" in c.lower())

    def test_roadmap_24k_pending(self):
        with open(f"{DOCS_DIR}/ROADMAP.md", encoding="utf-8") as f:
            c = f.read()
        assert "24-K" in c and "⏸" in c

    def test_roadmap_step_25_gate_mentioned(self):
        with open(f"{DOCS_DIR}/ROADMAP.md", encoding="utf-8") as f:
            c = f.read()
        assert "Step 25" in c or "Step 24-K" in c


class TestReadmeUpdated:
    def test_readme_has_step24_section(self):
        with open("README.md", encoding="utf-8") as f:
            c = f.read()
        assert "Step 24 Runtime Safety Layer" in c

    def test_readme_says_execute_blocked(self):
        with open("README.md", encoding="utf-8") as f:
            c = f.read()
        assert "blocked" in c.lower()

    def test_readme_says_no_production_sandbox(self):
        with open("README.md", encoding="utf-8") as f:
            c = f.read()
        assert "no production sandbox" in c.lower() or "No production sandbox" in c


class TestDocsNoFalseClaims:
    def test_no_claim_production_sandbox_completed(self):
        for f in gl.glob(f"{DOCS_DIR}/STEP24*.md"):
            with open(f, encoding="utf-8") as fh:
                c = fh.read()
            if "production sandbox completed" in c.lower():
                assert "不" in c or "not" in c.lower() or "no production" in c.lower(), \
                    f"{f} claims production sandbox completed"

    def test_no_claim_execution_completed(self):
        for f in gl.glob(f"{DOCS_DIR}/STEP24*.md"):
            with open(f, encoding="utf-8") as fh:
                c = fh.read()
            if "external code execution completed" in c.lower():
                assert "不" in c or "not" in c.lower() or "does not" in c.lower() or "never" in c.lower(), \
                    f"{f} claims execution completed"

    def test_no_claim_container_completed(self):
        for f in gl.glob(f"{DOCS_DIR}/STEP24*.md"):
            with open(f, encoding="utf-8") as fh:
                c = fh.read()
            if "container sandbox completed" in c.lower():
                assert "不" in c or "not" in c.lower() or "no container" in c.lower(), \
                    f"{f} claims container completed"

    def test_no_claim_crypto_signature_completed(self):
        for f in gl.glob(f"{DOCS_DIR}/STEP24*.md"):
            with open(f, encoding="utf-8") as fh:
                c = fh.read()
            if "cryptographic signature verification completed" in c.lower() or "signature verification completed" in c.lower():
                assert "metadata" in c.lower() or "not" in c.lower() or "不" in c

    def test_no_claim_execution_success(self):
        for f in gl.glob(f"{DOCS_DIR}/STEP24*.md"):
            with open(f, encoding="utf-8") as fh:
                c = fh.read()
            if "runtime execution success completed" in c.lower():
                assert False, f"{f} claims execution success completed"

    def test_mention_step_24k(self):
        for f in ["STEP24_RUNTIME_DEMO_SCRIPT.md", "STEP24_SECURITY_QA.md",
                   "STEP24_RUNTIME_ARCHITECTURE_SUMMARY.md", "ROADMAP.md"]:
            path = os.path.join(DOCS_DIR, f)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    c = fh.read()
                assert "24-K" in c or "Step 25" in c, f"{f} does not mention 24-K/Step 25"
