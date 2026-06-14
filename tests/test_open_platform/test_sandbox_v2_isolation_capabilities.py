"""Test Step 6A — Isolation Capability Probe 测试。"""
import pytest
from src.open_platform.sandbox_v2.isolation_capabilities import SandboxIsolationCapabilityProbe


class TestCapabilityProbe:
    def test_probe_no_500(self):
        probe = SandboxIsolationCapabilityProbe()
        cap = probe.collect_capabilities()
        assert cap is not None
        assert cap.checked_at is not None

    def test_windows_namespace_false(self):
        probe = SandboxIsolationCapabilityProbe()
        cap = probe.collect_capabilities()
        if cap.is_windows:
            assert cap.has_user_namespace is False
            assert cap.has_seccomp is False
            assert cap.has_cgroup is False

    def test_docker_check_no_500(self):
        probe = SandboxIsolationCapabilityProbe()
        has, msg = probe.check_docker_available()
        assert isinstance(has, bool)
        assert len(msg) > 0

    def test_podman_check_no_500(self):
        probe = SandboxIsolationCapabilityProbe()
        has, msg = probe.check_podman_available()
        assert isinstance(has, bool)

    def test_firecracker_check_no_500(self):
        probe = SandboxIsolationCapabilityProbe()
        has, msg = probe.check_firecracker_available()
        assert isinstance(has, bool)

    def test_gvisor_check_no_500(self):
        probe = SandboxIsolationCapabilityProbe()
        has, msg = probe.check_gvisor_available()
        assert isinstance(has, bool)

    def test_readiness_summary(self):
        probe = SandboxIsolationCapabilityProbe()
        rs = probe.get_readiness_summary()
        assert rs["isolation_capability_probe"] is True
        assert rs["execution_provider_abstraction"] is True
        assert rs["trusted_fixture_provider"] is True
        assert rs["untrusted_code_execution"] is False
        assert rs["local_process_execution"] is False
        assert rs["docker_execution"] is False
        assert rs["podman_execution"] is False
        assert rs["microvm_execution"] is False

    def test_probe_no_global_network_import(self):
        """顶层模块不导入 urllib/requests；subprocess 只在函数内做只读检查。"""
        import src.open_platform.sandbox_v2.isolation_capabilities as ic
        assert "requests" not in ic.__dict__
        assert "urllib" not in ic.__dict__
