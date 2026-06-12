"""Runtime Capability Enforcement Sub-Agent Tests — metadata-only, no execution."""
import os, json, pytest
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
from src.open_platform.runtime_capability import *
from src.open_platform.runtime_capability_subagent import *


class TestSubAgent:
    @pytest.fixture
    def capabilities(self):
        return build_default_capability_matrix()

    @pytest.fixture
    def subagent(self):
        return RuntimeCapabilityEnforcementSubAgent()

    # ── Constructor guards ──
    def test_constructor_blocks_execution(self):
        with pytest.raises(ValueError):
            RuntimeCapabilityEnforcementSubAgent(execution_allowed=True)
        with pytest.raises(ValueError):
            RuntimeCapabilityEnforcementSubAgent(runtime_enabled=True)

    def test_constructor_defaults(self):
        sa = RuntimeCapabilityEnforcementSubAgent()
        assert sa.metadata_only == True
        assert sa.execution_allowed == False
        assert sa.runtime_enabled == False

    # ── Enforcement run ──
    def test_run_simulation_returns_report(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        assert isinstance(report, EnforcementReport)
        assert report.total == 20
        assert report.metadata_only == True

    def test_all_checks_pass(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        assert report.passed == 20
        assert report.failed == 0

    def test_execution_not_allowed(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        assert report.execution_allowed == False
        assert report.runtime_enabled == False
        assert report.fixture_execution_allowed == False

    def test_ready_for_step26g(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        assert report.ready_for_step26g == True

    def test_ready_for_step26h(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        assert report.ready_for_step26h == True

    def test_execution_blockers_count(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        # At least 14 capabilities block execution (network×2, filesystem×2, secrets, memory, cpu, container×3, microvm, subprocess×3)
        assert report.execution_blockers >= 14

    def test_runtime_gates_count(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        assert report.runtime_gates_required >= 10

    def test_all_checks_have_expected_status(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        for chk in report.checks:
            assert chk["expected_status"] in {"blocked", "planned", "unsupported"}

    def test_no_check_has_execution_allowed(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        # Verify no capability in original set has execution_allowed
        for cap in capabilities:
            assert cap.execution_allowed == False

    def test_network_checks_are_blockers(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        net_checks = [c for c in report.checks if c["category"] == "network"]
        assert len(net_checks) == 2
        assert all(c["is_blocker_for_execution"] for c in net_checks)

    def test_filesystem_checks_are_blockers(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        fs_checks = [c for c in report.checks if c["category"] == "filesystem"]
        assert len(fs_checks) == 2
        assert all(c["is_blocker_for_execution"] for c in fs_checks)

    def test_third_party_execution_is_blocker(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        tpe = [c for c in report.checks if "Third-Party" in c["capability_name"]]
        assert len(tpe) == 1 and tpe[0]["is_blocker_for_execution"] == True

    def test_package_execution_is_blocker(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        pkg = [c for c in report.checks if c["capability_name"] == "Package Execution"]
        assert len(pkg) == 1 and pkg[0]["is_blocker_for_execution"] == True

    def test_ipc_not_blocker(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        ipc = [c for c in report.checks if c["category"] == "ipc"]
        assert len(ipc) >= 1 and not ipc[0]["is_blocker_for_execution"]

    def test_container_start_is_blocker(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        ct = [c for c in report.checks if c["capability_name"] == "Container Start"]
        assert len(ct) == 1 and ct[0]["is_blocker_for_execution"] == True

    def test_microvm_start_is_blocker(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        vm = [c for c in report.checks if c["capability_name"] == "MicroVM Start"]
        assert len(vm) == 1 and vm[0]["is_blocker_for_execution"] == True

    def test_report_to_dict(self, subagent, capabilities):
        report = subagent.run_simulation(capabilities)
        d = report.to_dict()
        assert "report_id" in d
        assert d["total"] == 20
        assert len(d["checks"]) == 20

    def test_convenience_function(self):
        caps = build_default_capability_matrix()
        report = run_capability_enforcement_report(caps)
        assert report.total == 20
        assert report.ready_for_step26g == True
        assert report.execution_allowed == False

    def test_enforcement_check_result_to_dict(self):
        r = EnforcementCheckResult(capability_name="test", category="network",
                                    current_status="blocked")
        d = r.to_dict()
        assert d["check_id"].startswith("enfchk_")
        assert d["capability_name"] == "test"

    def test_no_subprocess_import(self):
        import src.open_platform.runtime_capability_subagent as m
        assert "subprocess" not in str(dir(m)).lower()

    def test_no_docker_import(self):
        import src.open_platform.runtime_capability_subagent as m
        assert "docker" not in str(dir(m)).lower()

    def test_no_requests_import(self):
        import src.open_platform.runtime_capability_subagent as m
        assert "requests" not in str(dir(m)).lower()

    def test_no_AgentRuntime_import(self):
        import src.open_platform.runtime_capability_subagent as m
        assert "AgentRuntime" not in str(dir(m))
