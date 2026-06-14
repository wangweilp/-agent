"""Test Step 6A — Isolation Policy 测试。"""
import pytest
from src.open_platform.sandbox_v2.models import (
    SandboxExecutionPlan, SandboxV2IsolationProvider, SandboxV2Mode,
)
from src.open_platform.sandbox_v2.isolation_policy import evaluate_isolation_policy


class TestIsolationPolicy:
    def _plan(self, **kw):
        return SandboxExecutionPlan(
            provider=kw.get("provider", SandboxV2IsolationProvider.TRUSTED_FIXTURE),
            mode=kw.get("mode", SandboxV2Mode.SIMULATION),
            **{k: v for k, v in kw.items() if k not in ("provider", "mode")},
        )

    def test_default_deny_empty_provider(self):
        d = evaluate_isolation_policy(SandboxExecutionPlan(provider=""))
        assert d.allowed is False

    def test_docker_rootless_allowed_strict(self):
        """docker_rootless_future is now allowed under strict conditions (Step 6B)."""
        d = evaluate_isolation_policy(self._plan(provider=SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE, resource_limits={"max_mb": 256}))
        assert d.allowed is True

    def test_microvm_now_allowed_for_plan(self):
        """Step 11: microvm_future allowed by isolation policy. Execution blocked by microvm_policy."""
        d = evaluate_isolation_policy(self._plan(provider=SandboxV2IsolationProvider.MICROVM_FUTURE))
        assert d.allowed is True
        assert d.execution_allowed is False

    def test_gvisor_future_rejected(self):
        d = evaluate_isolation_policy(self._plan(provider=SandboxV2IsolationProvider.GVISOR_FUTURE))
        assert d.allowed is False

    def test_kata_future_rejected(self):
        d = evaluate_isolation_policy(self._plan(provider=SandboxV2IsolationProvider.KATA_FUTURE))
        assert d.allowed is False

    def test_firecracker_now_allowed_for_plan(self):
        """Step 11: firecracker_future allowed by isolation policy. Execution blocked by microvm_policy."""
        d = evaluate_isolation_policy(self._plan(provider=SandboxV2IsolationProvider.FIRECRACKER_FUTURE))
        assert d.allowed is True
        assert d.execution_allowed is False

    def test_local_process_disabled_rejected(self):
        d = evaluate_isolation_policy(self._plan(provider=SandboxV2IsolationProvider.LOCAL_PROCESS_DISABLED))
        assert d.allowed is False

    def test_disabled_provider_denies(self):
        d = evaluate_isolation_policy(self._plan(provider=SandboxV2IsolationProvider.DISABLED))
        assert d.allowed is False

    def test_trusted_fixture_allowed(self):
        d = evaluate_isolation_policy(self._plan(provider=SandboxV2IsolationProvider.TRUSTED_FIXTURE, resource_limits={"max_mb": 256}))
        assert d.allowed is True
        assert d.execution_allowed is True

    def test_simulation_allowed(self):
        d = evaluate_isolation_policy(self._plan(provider=SandboxV2IsolationProvider.SIMULATION))
        assert d.allowed is True

    def test_missing_resource_limits_rejected(self):
        d = evaluate_isolation_policy(self._plan(provider=SandboxV2IsolationProvider.TRUSTED_FIXTURE), resource_limits_provided=False)
        assert d.allowed is False
        assert "missing_resource_limits" in d.matched_rules

    def test_allow_network_rejected(self):
        d = evaluate_isolation_policy(self._plan(provider=SandboxV2IsolationProvider.TRUSTED_FIXTURE, resource_limits={"mb": 256}), allow_network=True)
        assert d.allowed is False
        assert "network_not_allowed" in d.matched_rules

    def test_allow_filesystem_write_rejected(self):
        d = evaluate_isolation_policy(self._plan(provider=SandboxV2IsolationProvider.TRUSTED_FIXTURE, resource_limits={"mb": 256}), allow_filesystem_write=True)
        assert d.allowed is False

    def test_allow_package_install_rejected(self):
        d = evaluate_isolation_policy(self._plan(provider=SandboxV2IsolationProvider.TRUSTED_FIXTURE, resource_limits={"mb": 256}), allow_package_install=True)
        assert d.allowed is False

    def test_future_container_mode_rejected(self):
        d = evaluate_isolation_policy(self._plan(provider=SandboxV2IsolationProvider.TRUSTED_FIXTURE, mode=SandboxV2Mode.FUTURE_CONTAINER, resource_limits={"mb": 256}))
        assert d.allowed is False
        assert "future_mode_rejected" in d.matched_rules

    def test_future_microvm_mode_rejected(self):
        d = evaluate_isolation_policy(self._plan(provider=SandboxV2IsolationProvider.TRUSTED_FIXTURE, mode=SandboxV2Mode.FUTURE_MICROVM, resource_limits={"mb": 256}))
        assert d.allowed is False

    def test_exception_fail_closed(self):
        d = evaluate_isolation_policy(None)  # type: ignore
        assert d.allowed is False
        assert d.fail_closed is True
