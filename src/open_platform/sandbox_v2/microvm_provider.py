"""Sandbox v2 MicroVM / Firecracker Provider — Step 11 PoC.

MicroVMCommandBuilder: 构建 Firecracker 配置和命令参数（不执行）
FirecrackerMicroVMExecutionProvider: 实现 ExecutionProvider Protocol 的 MicroVM 扩展
  默认 disabled，需要 SANDBOX_V2_MICROVM_EXECUTION_ENABLED=true +
  SANDBOX_V2_RUN_MICROVM_INTEGRATION=true + Linux + KVM + Firecracker binary +
  kernel + rootfs 全部满足才允许真实运行。

安全约束：
- 不要执行用户代码/command
- 不要使用用户 kernel/rootfs
- 不要联网（默认 network disabled）
- 不要挂载宿主机目录
- 不要使用 shell=True
- 只允许内置 trusted MicroVM fixture
- 不做真实 Firecracker 启动（本步骤只做 policy + preflight + plan management）
"""

from __future__ import annotations

import json
import logging
import os
import platform as _platform
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.open_platform.sandbox_v2.models import (
    SandboxV2Decision,
    SandboxMicroVMRuntime,
    SandboxMicroVMExecutionStatus,
    SandboxMicroVMRuntimeConfig,
    SandboxMicroVMExecutionPlan,
    SandboxMicroVMExecutionResult,
    SandboxMicroVMPreflightResult,
    TRUSTED_MICROVM_FIXTURES,
)
from src.open_platform.sandbox_v2.microvm_policy import evaluate_microvm_policy

logger = logging.getLogger(__name__)

_ENV_EXEC_ENABLE = "SANDBOX_V2_MICROVM_EXECUTION_ENABLED"
_ENV_INTEGRATION_ENABLE = "SANDBOX_V2_RUN_MICROVM_INTEGRATION"


# ═══════════════════════════════════════════
# MicroVMCommandBuilder
# ═══════════════════════════════════════════

class MicroVMCommandBuilder:
    """构建 Firecracker 配置和命令参数。不执行命令。不使用 shell=True。

    所有命令使用参数数组。
    不接受用户自定义 command/kernel/rootfs/网络配置。
    """

    @staticmethod
    def build_firecracker_command(
        firecracker_bin: str, *,
        api_sock_path: str = "/tmp/firecracker.sock",
        config_file_path: str = "/tmp/firecracker-config.json",
        jailer_enabled: bool = False,
    ) -> list[str]:
        """构建 Firecracker 命令（参数数组，不使用 shell=True）。"""
        if jailer_enabled:
            return [
                "jailer", "--id", "sandbox-v2-microvm",
                "--exec-file", firecracker_bin,
                "--api-sock", api_sock_path,
                "--", "--config-file", config_file_path,
            ]
        return [firecracker_bin, "--api-sock", api_sock_path, "--config-file", config_file_path]

    @staticmethod
    def build_firecracker_config(
        *,
        kernel_path: str,
        rootfs_path: str,
        memory_mb: int = 128,
        vcpu_count: int = 1,
        network_enabled: bool = False,
        kernel_args: str = "console=ttyS0 reboot=k panic=1 pci=off",
    ) -> dict[str, Any]:
        """构建 Firecracker 配置字典。

        安全约束：
        - 网络默认禁用（network_interfaces 为空）
        - 不接受用户自定义 kernel_args
        - 不接受用户自定义 host mount
        - 不接受用户自定义 rootfs
        """
        config: dict[str, Any] = {
            "boot-source": {
                "kernel_image_path": kernel_path,
                "boot_args": kernel_args,
            },
            "drives": [{
                "drive_id": "rootfs",
                "path_on_host": rootfs_path,
                "is_root_device": True,
                "is_read_only": True,
            }],
            "machine-config": {
                "vcpu_count": vcpu_count,
                "mem_size_mib": memory_mb,
                "smt": False,
            },
            "network-interfaces": [],
        }
        if network_enabled:
            # 即使开启网络，也只允许最基础配置（不是用户可以自定义的）
            config["network-interfaces"] = [{
                "iface_id": "eth0",
                "guest_mac": "06:00:00:00:00:01",
                "host_dev_name": "tap-sandbox-v2",
            }]
        return config

    @staticmethod
    def build_firecracker_jailer_command(
        firecracker_bin: str, *,
        jailer_id: str = "sandbox-v2-microvm",
        api_sock_path: str = "/tmp/firecracker.sock",
        config_file_path: str = "/tmp/firecracker-config.json",
    ) -> list[str]:
        """构建 Firecracker jailer 命令（参数数组）。仅构建，不执行。"""
        return [
            "jailer", "--id", jailer_id,
            "--exec-file", firecracker_bin,
            "--api-sock", api_sock_path,
            "--chroot-base-dir", "/srv/jailer",
            "--", "--config-file", config_file_path,
        ]

    @staticmethod
    def validate_config(config: dict[str, Any]) -> tuple[bool, str]:
        """验证 Firecracker 配置。"""
        if not config.get("boot-source", {}).get("kernel_image_path"):
            return False, "Missing kernel_image_path in boot-source"
        if not config.get("drives"):
            return False, "Missing drives in config"
        if not config.get("machine-config", {}).get("vcpu_count"):
            return False, "Missing vcpu_count in machine-config"
        if not config.get("machine-config", {}).get("mem_size_mib"):
            return False, "Missing mem_size_mib in machine-config"
        # 安全检查
        network_ifs = config.get("network-interfaces", [])
        if len(network_ifs) > 1:
            return False, "Too many network interfaces"
        return True, "Config validated"


# ═══════════════════════════════════════════
# FirecrackerMicroVMExecutionProvider
# ═══════════════════════════════════════════

class MicroVMProcessRunner:
    """MicroVM 进程运行器 — 默认 fake/skip。真实运行仅在 Linux + 所有条件满足时。

    真实运行时：
    - shell=False
    - timeout 必须设置
    - stdout/stderr 捕获
    - 不接受用户输入
    """

    def run(self, command: list[str], timeout_seconds: int = 10) -> dict[str, Any]:
        """运行命令（参数数组）。默认不执行。

        返回字典包含 status, stdout, stderr, exit_code 等。
        """
        return {
            "executed": False, "status": "skipped",
            "reason": "Real MicroVM execution is disabled by default. Enable via env vars on Linux+KVM.",
            "stdout": "", "stderr": "", "exit_code": -1,
        }


class FirecrackerMicroVMExecutionProvider:
    """Firecracker MicroVM Execution Provider — 默认 disabled。

    只有以下全部条件满足时才允许真实运行：
    1. SANDBOX_V2_MICROVM_EXECUTION_ENABLED=true
    2. SANDBOX_V2_RUN_MICROVM_INTEGRATION=true
    3. Linux platform
    4. KVM available (/dev/kvm)
    5. Firecracker binary exists
    6. Kernel image exists
    7. Rootfs image exists
    8. Network disabled
    9. Only trusted fixture
    10. No user kernel/rootfs/command/mounts
    """

    def __init__(self, config: SandboxMicroVMRuntimeConfig | None = None):
        self._config = config or SandboxMicroVMRuntimeConfig()
        self._runner = MicroVMProcessRunner()

    def get_provider_name(self) -> str:
        return "firecracker_microvm"

    def get_capabilities(self) -> dict:
        return {
            "provider": self.get_provider_name(),
            "runtime": self._config.runtime,
            "enabled": self._enabled(),
            "integration_enabled": self._integration_enabled(),
            "platform": _platform.system(),
            "network_disabled": not self._config.network_enabled,
            "no_user_kernel": True, "no_user_rootfs": True,
            "no_user_command": True, "no_host_mounts": True,
            "no_network": True, "trusted_fixture_only": True,
        }

    def validate_execution_plan(self, plan: Any) -> dict:
        """校验 MicroVM 执行计划。"""
        policy_result = evaluate_microvm_policy(
            SandboxMicroVMExecutionPlan(
                fixture_id=getattr(plan, "command_ref", "") or getattr(plan, "fixture_id", ""),
                network_enabled=getattr(plan, "network_enabled", False),
            ),
            microvm_execution_enabled=self._enabled(),
            run_microvm_integration=self._integration_enabled(),
            is_linux=_platform.system() == "Linux",
            has_kvm=self._check_kvm(),
            firecracker_binary_present=self._check_firecracker_binary(),
            kernel_present=self._check_kernel(),
            rootfs_present=self._check_rootfs(),
            network_enabled=self._config.network_enabled,
        )
        return policy_result

    def run_trusted_fixture(self, plan: Any) -> dict:
        """运行/预检 MicroVM trusted fixture。

        环境不满足时返回 disabled/unavailable/rejected。
        不真实启动 Firecracker。
        """
        start = datetime.now(timezone.utc)

        # 构建 MicroVM execution plan
        fixture_id = getattr(plan, "command_ref", "") or getattr(plan, "fixture_id", "")
        microvm_plan = SandboxMicroVMExecutionPlan(
            fixture_id=fixture_id,
            network_enabled=getattr(plan, "network_enabled", False),
            memory_mb=self._config.memory_mb,
            vcpu_count=self._config.vcpu_count,
            timeout_seconds=self._config.timeout_seconds,
        )

        # Policy evaluation
        policy = evaluate_microvm_policy(
            microvm_plan,
            microvm_execution_enabled=self._enabled(),
            run_microvm_integration=self._integration_enabled(),
            is_linux=_platform.system() == "Linux",
            has_kvm=self._check_kvm(),
            firecracker_binary_present=self._check_firecracker_binary(),
            kernel_present=self._check_kernel(),
            rootfs_present=self._check_rootfs(),
            network_enabled=self._config.network_enabled,
        )

        if not policy["allowed"]:
            return {
                "executed": False, "status": policy["status"],
                "reason": policy["reason"],
                "microvm_plan_id": microvm_plan.microvm_plan_id,
                "fixture_id": fixture_id,
                "preflight": self.get_preflight(),
                "matched_rules": policy.get("matched_rules", []),
            }

        # Preflight passed but don't actually run Firecracker
        finish = datetime.now(timezone.utc)
        return {
            "executed": False,  # 不真实执行
            "status": SandboxMicroVMExecutionStatus.PREFLIGHT_PASSED,
            "reason": "MicroVM preflight passed. Real Firecracker execution is not implemented in this PoC.",
            "microvm_plan_id": microvm_plan.microvm_plan_id,
            "fixture_id": fixture_id,
            "duration_ms": int((finish - start).total_seconds() * 1000),
            "preflight": self.get_preflight(),
            "matched_rules": policy.get("matched_rules", []),
        }

    def get_preflight(self) -> SandboxMicroVMPreflightResult:
        """获取 MicroVM 前置条件检查结果。不启动 Firecracker。"""
        is_linux = _platform.system() == "Linux"
        has_kvm = self._check_kvm()
        has_fb = self._check_firecracker_binary()
        has_ker = self._check_kernel()
        has_rfs = self._check_rootfs()
        exec_enabled = self._enabled()
        integ_enabled = self._integration_enabled()
        net_off = not self._config.network_enabled

        runnable = all([
            is_linux, has_kvm, has_fb, has_ker, has_rfs,
            exec_enabled, integ_enabled, net_off,
        ])

        blockers: list[str] = []
        warnings: list[str] = []
        if not is_linux:
            blockers.append("Platform is not Linux")
        if not has_kvm:
            blockers.append("/dev/kvm not available")
        if not has_fb:
            blockers.append("Firecracker binary not found")
        if not has_ker:
            blockers.append("MicroVM kernel not found")
        if not has_rfs:
            blockers.append("MicroVM rootfs not found")
        if not exec_enabled:
            blockers.append("SANDBOX_V2_MICROVM_EXECUTION_ENABLED not true")
        if not integ_enabled:
            blockers.append("SANDBOX_V2_RUN_MICROVM_INTEGRATION not true")
        if not net_off:
            warnings.append("MicroVM network is enabled — should be disabled for production")

        reason = "; ".join(blockers) if blockers else "All MicroVM preconditions satisfied."
        if not blockers and not runnable:
            reason = "Preconditions partially met."

        return SandboxMicroVMPreflightResult(
            platform=_platform.system(),
            is_linux=is_linux, is_windows=not is_linux,
            has_kvm=has_kvm,
            firecracker_binary_present=has_fb,
            kernel_present=has_ker, rootfs_present=has_rfs,
            execution_env_enabled=exec_enabled,
            integration_env_enabled=integ_enabled,
            network_disabled=net_off,
            runnable=runnable,
            reason=reason,
            warnings=warnings, blockers=[b for b in blockers if b],
        )

    def cancel_execution(self, execution_id: str) -> dict:
        if not self._enabled():
            return {"execution_id": execution_id, "canceled": False,
                    "message": "MicroVM execution not enabled."}
        if _platform.system() != "Linux":
            return {"execution_id": execution_id, "canceled": False,
                    "message": "MicroVM kill unavailable on non-Linux platform."}
        return {"execution_id": execution_id, "canceled": False,
                "message": "MicroVM cancel not implemented in PoC. No real Firecracker process."}

    def cleanup(self, execution_id: str) -> bool:
        return True

    # ── Internal checks ──

    def _enabled(self) -> bool:
        return os.environ.get(_ENV_EXEC_ENABLE, "").lower() in ("true", "1", "yes")

    def _integration_enabled(self) -> bool:
        return os.environ.get(_ENV_INTEGRATION_ENABLE, "").lower() in ("true", "1", "yes")

    def _check_kvm(self) -> bool:
        """检查 /dev/kvm 是否存在且可访问。Windows 直接返回 False。"""
        if _platform.system() != "Linux":
            return False
        return os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)

    def _check_firecracker_binary(self) -> bool:
        """检查 Firecracker binary 是否存在。不执行。"""
        import shutil
        path = self._config.firecracker_bin_path
        if path:
            return os.path.isfile(path) and os.access(path, os.X_OK)
        return shutil.which("firecracker") is not None

    def _check_kernel(self) -> bool:
        """检查 MicroVM kernel 文件是否存在。"""
        path = self._config.kernel_path
        if path:
            return os.path.isfile(path)
        return False

    def _check_rootfs(self) -> bool:
        """检查 MicroVM rootfs 文件是否存在。"""
        path = self._config.rootfs_path
        if path:
            return os.path.isfile(path)
        return False
