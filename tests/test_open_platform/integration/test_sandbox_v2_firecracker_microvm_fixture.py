"""Integration test: Firecracker MicroVM Trusted Fixture (Step 11).

默认 skip — 只在所有条件满足时才运行：
- SANDBOX_V2_MICROVM_EXECUTION_ENABLED=true
- SANDBOX_V2_RUN_MICROVM_INTEGRATION=true
- Linux platform
- KVM available
- Firecracker binary exists
- Kernel + rootfs files exist

如果条件不满足，所有测试 skip（不 fail）。
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _is_microvm_ready() -> bool:
    """检查 MicroVM 所有前置条件。"""
    env_exec = os.environ.get("SANDBOX_V2_MICROVM_EXECUTION_ENABLED", "").lower() in ("true", "1", "yes")
    env_integ = os.environ.get("SANDBOX_V2_RUN_MICROVM_INTEGRATION", "").lower() in ("true", "1", "yes")
    is_linux = platform.system() == "Linux"
    has_kvm = is_linux and os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)

    fb_path = os.environ.get("SANDBOX_V2_FIRECRACKER_BIN_PATH", "")
    import shutil
    has_fb = bool(fb_path and os.path.isfile(fb_path) and os.access(fb_path, os.X_OK)) or shutil.which("firecracker") is not None

    ker_path = os.environ.get("SANDBOX_V2_FIRECRACKER_KERNEL_PATH", "")
    has_ker = bool(ker_path and os.path.isfile(ker_path))

    rfs_path = os.environ.get("SANDBOX_V2_FIRECRACKER_ROOTFS_PATH", "")
    has_rfs = bool(rfs_path and os.path.isfile(rfs_path))

    return all([env_exec, env_integ, is_linux, has_kvm, has_fb, has_ker, has_rfs])


# Skip reason string
_SKIP_REASON = (
    "MicroVM integration test requires: "
    "SANDBOX_V2_MICROVM_EXECUTION_ENABLED=true + "
    "SANDBOX_V2_RUN_MICROVM_INTEGRATION=true + "
    "Linux + KVM + Firecracker binary + kernel + rootfs"
)

# Apply skip at module level
if not _is_microvm_ready():
    pytestmark = pytest.mark.skip(reason=_SKIP_REASON)


class TestFirecrackerMicroVMFixture:
    """真实 Firecracker MicroVM fixture 集成测试。

    仅在所有前置条件满足时运行（通过 env vars 显式 opt-in）。
    """

    def test_preflight_runnable(self):
        """Preflight 返回 runnable=true。"""
        from src.open_platform.sandbox_v2.isolation_capabilities import SandboxIsolationCapabilityProbe
        probe = SandboxIsolationCapabilityProbe()
        pc = probe.check_microvm_preconditions()
        assert pc["runnable"], f"Preflight not runnable: {pc}"

    def test_provider_preflight_runnable(self):
        """Provider preflight 返回 runnable。"""
        from src.open_platform.sandbox_v2.microvm_provider import FirecrackerMicroVMExecutionProvider
        from src.open_platform.sandbox_v2.models import SandboxMicroVMRuntimeConfig
        config = SandboxMicroVMRuntimeConfig(
            runtime="firecracker",
            firecracker_bin_path=os.environ.get("SANDBOX_V2_FIRECRACKER_BIN_PATH", ""),
            kernel_path=os.environ.get("SANDBOX_V2_FIRECRACKER_KERNEL_PATH", ""),
            rootfs_path=os.environ.get("SANDBOX_V2_FIRECRACKER_ROOTFS_PATH", ""),
        )
        provider = FirecrackerMicroVMExecutionProvider(config=config)
        pf = provider.get_preflight()
        assert pf.runnable, f"Provider preflight not runnable: {pf.reason}"

    def test_trusted_fixture_not_rejected(self):
        """Trusted fixture 不被拒绝（至少 preflight_passed）。"""
        from src.open_platform.sandbox_v2.microvm_provider import FirecrackerMicroVMExecutionProvider
        from src.open_platform.sandbox_v2.models import SandboxMicroVMRuntimeConfig, SandboxExecutionPlan
        config = SandboxMicroVMRuntimeConfig(
            runtime="firecracker",
            firecracker_bin_path=os.environ.get("SANDBOX_V2_FIRECRACKER_BIN_PATH", ""),
            kernel_path=os.environ.get("SANDBOX_V2_FIRECRACKER_KERNEL_PATH", ""),
            rootfs_path=os.environ.get("SANDBOX_V2_FIRECRACKER_ROOTFS_PATH", ""),
        )
        provider = FirecrackerMicroVMExecutionProvider(config=config)
        # 真实运行时可能返回 preflight_passed 或实际执行结果
        result = provider.run_trusted_fixture(
            SandboxExecutionPlan(command_ref="hello-microvm-fixture"))
        assert result["status"] != "rejected", f"Trusted fixture rejected: {result}"

    def test_unknown_fixture_rejected(self):
        """非 trusted fixture 必须被拒绝。"""
        from src.open_platform.sandbox_v2.microvm_provider import FirecrackerMicroVMExecutionProvider
        from src.open_platform.sandbox_v2.models import SandboxMicroVMRuntimeConfig, SandboxExecutionPlan
        config = SandboxMicroVMRuntimeConfig(
            runtime="firecracker",
            firecracker_bin_path=os.environ.get("SANDBOX_V2_FIRECRACKER_BIN_PATH", ""),
            kernel_path=os.environ.get("SANDBOX_V2_FIRECRACKER_KERNEL_PATH", ""),
            rootfs_path=os.environ.get("SANDBOX_V2_FIRECRACKER_ROOTFS_PATH", ""),
        )
        provider = FirecrackerMicroVMExecutionProvider(config=config)
        result = provider.run_trusted_fixture(
            SandboxExecutionPlan(command_ref="evil-fixture"))
        assert not result.get("executed", False)
        assert result["status"] in ("disabled", "unavailable", "rejected")

    def test_network_not_enabled(self):
        """MicroVM 网络默认不启用。"""
        env_net = os.environ.get("SANDBOX_V2_MICROVM_NETWORK_ENABLED", "").lower()
        assert env_net not in ("true", "1", "yes"), (
            "SANDBOX_V2_MICROVM_NETWORK_ENABLED must be false for production"
        )

    def test_user_kernel_not_allowed(self):
        """用户 kernel 必须不启用。"""
        env = os.environ.get("SANDBOX_V2_MICROVM_ALLOW_USER_KERNEL", "").lower()
        assert env not in ("true", "1", "yes")

    def test_user_rootfs_not_allowed(self):
        """用户 rootfs 必须不启用。"""
        env = os.environ.get("SANDBOX_V2_MICROVM_ALLOW_USER_ROOTFS", "").lower()
        assert env not in ("true", "1", "yes")
