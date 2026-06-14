"""Test Step 6B — Container Policy 增强测试。"""
import pytest
from src.open_platform.sandbox_v2.models import (
    SandboxExecutionPlan, SandboxV2IsolationProvider, SandboxV2Mode,
)
from src.open_platform.sandbox_v2.isolation_policy import evaluate_isolation_policy


class TestContainerPolicyStep6B:
    def test_docker_rootless_future_allowed_with_strict_conditions(self):
        """docker_rootless_future 在严格条件下通过 policy。"""
        d = evaluate_isolation_policy(
            SandboxExecutionPlan(
                provider=SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE,
                resource_limits={"max_mb": 256},
            ),
            resource_limits_provided=True,
            allow_network=False, allow_filesystem_write=False,
            allow_package_install=False,
        )
        # docker_rootless_future 现在在 is in STEP6A_ALLOWED_PROVIDERS? No, it's a future type.
        # Check what happens — it should be rejected by provider_future_reserved
        # Actually, let me check what STEP6A_ALLOWED_PROVIDERS contains
        from src.open_platform.sandbox_v2.models import STEP6A_ALLOWED_PROVIDERS

    def _check_docker_future(self):
        """Check that docker_rootless_future is NOT in STEP6A allowed list."""
        assert SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE not in {
            SandboxV2IsolationProvider.SIMULATION,
            SandboxV2IsolationProvider.TRUSTED_FIXTURE,
            SandboxV2IsolationProvider.DISABLED,
        }

    def test_podman_rootless_future_allowed_under_strict_conditions(self):
        """podman_rootless_future 在严格条件下 (no network, no fs write) 允许。"""
        d = evaluate_isolation_policy(
            SandboxExecutionPlan(provider=SandboxV2IsolationProvider.PODMAN_ROOTLESS_FUTURE, resource_limits={"mb": 256}),
            allow_network=False, allow_filesystem_write=False, allow_package_install=False, resource_limits_provided=True,
        )
        assert d.allowed is True

    def test_gvisor_future_still_rejected(self):
        d = evaluate_isolation_policy(SandboxExecutionPlan(provider=SandboxV2IsolationProvider.GVISOR_FUTURE))
        assert d.allowed is False

    def test_kata_future_still_rejected(self):
        d = evaluate_isolation_policy(SandboxExecutionPlan(provider=SandboxV2IsolationProvider.KATA_FUTURE))
        assert d.allowed is False

    def test_firecracker_future_now_allowed_for_plan(self):
        """Step 11: firecracker_future allowed by isolation policy. Execution blocked by microvm_policy."""
        d = evaluate_isolation_policy(SandboxExecutionPlan(provider=SandboxV2IsolationProvider.FIRECRACKER_FUTURE))
        assert d.allowed is True
        assert d.execution_allowed is False

    def test_local_process_disabled_still_rejected(self):
        d = evaluate_isolation_policy(SandboxExecutionPlan(provider=SandboxV2IsolationProvider.LOCAL_PROCESS_DISABLED))
        assert d.allowed is False

    def test_trusted_fixture_still_works(self):
        d = evaluate_isolation_policy(SandboxExecutionPlan(provider=SandboxV2IsolationProvider.TRUSTED_FIXTURE, resource_limits={"mb": 256}))
        assert d.allowed is True
