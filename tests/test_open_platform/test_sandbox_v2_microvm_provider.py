"""Tests for MicroVM Provider (Step 11).

验证:
1. Command builder 不使用 shell=True
2. Firecracker config 默认无 network interfaces
3. Firecracker config 包含 memory/vcpu limits
4. Firecracker config 验证
5. Provider 默认不可运行
6. Windows 环境返回 unavailable
7. 用户 command 被拒绝
8. 未知 fixture 被拒绝
9. Preflight 返回正确状态
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.open_platform.sandbox_v2.models import (
    SandboxMicroVMRuntimeConfig,
    SandboxMicroVMExecutionPlan,
    SandboxExecutionPlan,
)
from src.open_platform.sandbox_v2.microvm_provider import (
    MicroVMCommandBuilder,
    FirecrackerMicroVMExecutionProvider,
)


class TestMicroVMCommandBuilder:
    """MicroVMCommandBuilder 安全验证。"""

    def test_build_firecracker_command_is_array(self):
        cmd = MicroVMCommandBuilder.build_firecracker_command("/usr/bin/firecracker")
        assert isinstance(cmd, list)
        assert "shell" not in str(cmd).lower()

    def test_build_firecracker_config_no_network_by_default(self):
        config = MicroVMCommandBuilder.build_firecracker_config(
            kernel_path="/path/to/vmlinux", rootfs_path="/path/to/rootfs.ext4",
        )
        assert config["network-interfaces"] == []

    def test_build_firecracker_config_has_memory_vcpu_limits(self):
        config = MicroVMCommandBuilder.build_firecracker_config(
            kernel_path="/path/to/vmlinux", rootfs_path="/path/to/rootfs.ext4",
            memory_mb=256, vcpu_count=1,
        )
        assert config["machine-config"]["mem_size_mib"] == 256
        assert config["machine-config"]["vcpu_count"] == 1

    def test_build_firecracker_config_has_boot_source(self):
        config = MicroVMCommandBuilder.build_firecracker_config(
            kernel_path="/path/to/vmlinux", rootfs_path="/path/to/rootfs.ext4",
        )
        assert config["boot-source"]["kernel_image_path"] == "/path/to/vmlinux"
        assert "console=ttyS0" in config["boot-source"]["boot_args"]

    def test_validate_config_valid(self):
        config = MicroVMCommandBuilder.build_firecracker_config(
            kernel_path="/path/to/vmlinux", rootfs_path="/path/to/rootfs.ext4",
        )
        ok, msg = MicroVMCommandBuilder.validate_config(config)
        assert ok, msg

    def test_validate_config_missing_kernel(self):
        config = MicroVMCommandBuilder.build_firecracker_config(
            kernel_path="", rootfs_path="/path/to/rootfs.ext4",
        )
        ok, msg = MicroVMCommandBuilder.validate_config(config)
        assert not ok

    def test_validate_config_missing_drives(self):
        config = {"boot-source": {"kernel_image_path": "/k"}}
        ok, msg = MicroVMCommandBuilder.validate_config(config)
        assert not ok

    def test_build_jailer_command(self):
        cmd = MicroVMCommandBuilder.build_firecracker_jailer_command("/bin/firecracker")
        assert isinstance(cmd, list)
        assert "jailer" in cmd[0]


class TestMicroVMProviderDefaultState:
    """Provider 默认不可运行。"""

    def test_provider_default_disabled(self):
        provider = FirecrackerMicroVMExecutionProvider()
        caps = provider.get_capabilities()
        assert caps["enabled"] is False

    def test_provider_validate_disabled(self):
        provider = FirecrackerMicroVMExecutionProvider()
        r = provider.validate_execution_plan(SandboxExecutionPlan(command_ref="test"))
        assert not r["allowed"]

    def test_run_trusted_fixture_disabled(self):
        provider = FirecrackerMicroVMExecutionProvider()
        r = provider.run_trusted_fixture(SandboxExecutionPlan(command_ref="hello-microvm-fixture"))
        assert not r["executed"]
        assert r["status"] in ("disabled", "unavailable")

    def test_preflight_on_windows(self):
        provider = FirecrackerMicroVMExecutionProvider()
        pf = provider.get_preflight()
        assert pf.is_windows or not pf.runnable


class TestMicroVMProviderRejections:
    """危险操作被拒绝。"""

    def test_unknown_fixture_rejected(self):
        provider = FirecrackerMicroVMExecutionProvider()
        r = provider.run_trusted_fixture(
            SandboxExecutionPlan(command_ref="unknown-fixture"))
        assert not r["executed"]

    def test_user_command_not_supported(self):
        """通过 fixture_id 字段传递非 trusted fixture → rejected。"""
        provider = FirecrackerMicroVMExecutionProvider()
        r = provider.run_trusted_fixture(
            SandboxExecutionPlan(command_ref="rm -rf /"))
        assert not r["executed"]
        assert r["status"] in ("disabled", "unavailable", "rejected")


class TestMicroVMConfigBuilder:
    """Config 验证。"""

    def test_build_config_network_enabled(self):
        """即使 network_enabled=True，也只允许基础配置。"""
        config = MicroVMCommandBuilder.build_firecracker_config(
            kernel_path="/k", rootfs_path="/r", network_enabled=True,
        )
        assert len(config["network-interfaces"]) == 1
        assert config["network-interfaces"][0]["host_dev_name"] == "tap-sandbox-v2"

    def test_readonly_rootfs(self):
        config = MicroVMCommandBuilder.build_firecracker_config(
            kernel_path="/k", rootfs_path="/r",
        )
        assert config["drives"][0]["is_read_only"] is True
