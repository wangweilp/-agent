"""Test Step 6B — Container Provider 测试。"""
import pytest, os, platform
from src.open_platform.sandbox_v2.container_provider import (
    ContainerCommandBuilder, RootlessContainerExecutionProvider,
)
from src.open_platform.sandbox_v2.models import (
    SandboxContainerRuntimeConfig, SandboxContainerExecutionPlan,
    SandboxExecutionPlan, SandboxV2IsolationProvider,
    SandboxV2ContainerRuntime, SandboxV2ContainerExecutionStatus,
    TRUSTED_CONTAINER_FIXTURES, DEFAULT_ALLOWED_IMAGES,
)


class TestCommandBuilder:
    def test_docker_has_network_none(self):
        cmd = ContainerCommandBuilder.build_docker_command("alpine", ["echo", "hi"])
        assert "--network=none" in cmd

    def test_docker_has_read_only(self):
        cmd = ContainerCommandBuilder.build_docker_command("alpine", ["echo", "hi"])
        assert "--read-only" in cmd

    def test_docker_has_cap_drop_all(self):
        cmd = ContainerCommandBuilder.build_docker_command("alpine", ["echo", "hi"])
        assert "--cap-drop=ALL" in cmd

    def test_docker_has_no_new_privileges(self):
        cmd = ContainerCommandBuilder.build_docker_command("alpine", ["echo", "hi"])
        assert "--security-opt=no-new-privileges" in cmd

    def test_docker_has_non_root_user(self):
        cmd = ContainerCommandBuilder.build_docker_command("alpine", ["echo", "hi"])
        assert "--user=65532:65532" in cmd

    def test_docker_has_pids_limit(self):
        cmd = ContainerCommandBuilder.build_docker_command("alpine", ["echo", "hi"])
        assert any("pids-limit" in c for c in cmd)

    def test_docker_has_memory_limit(self):
        cmd = ContainerCommandBuilder.build_docker_command("alpine", ["echo", "hi"])
        assert any("memory" in c for c in cmd)

    def test_docker_has_cpu_limit(self):
        cmd = ContainerCommandBuilder.build_docker_command("alpine", ["echo", "hi"])
        assert any("cpus" in c for c in cmd)

    def test_docker_has_tmpfs(self):
        cmd = ContainerCommandBuilder.build_docker_command("alpine", ["echo", "hi"])
        assert any("tmpfs" in c for c in cmd)

    def test_podman_has_network_none(self):
        cmd = ContainerCommandBuilder.build_podman_command("alpine", ["echo", "hi"])
        assert "--network=none" in cmd

    def test_no_privileged(self):
        for c in [ContainerCommandBuilder.build_docker_command("x", ["y"]), ContainerCommandBuilder.build_podman_command("x", ["y"])]:
            assert "--privileged" not in c

    def test_no_network_host(self):
        for c in [ContainerCommandBuilder.build_docker_command("x", ["y"]), ContainerCommandBuilder.build_podman_command("x", ["y"])]:
            assert "--network=host" not in c, f"Found host network in {c}"

    def test_no_docker_socket_mount(self):
        for c in [ContainerCommandBuilder.build_docker_command("x", ["y"]), ContainerCommandBuilder.build_podman_command("x", ["y"])]:
            joined = " ".join(c)
            assert "docker.sock" not in joined


class TestRootlessProvider:
    def test_default_disabled(self):
        p = RootlessContainerExecutionProvider()
        assert p._enabled() is False

    def test_validate_plan_disabled_rejects(self):
        p = RootlessContainerExecutionProvider()
        d = p.validate_execution_plan(SandboxExecutionPlan(provider="docker_rootless_future", command_ref="hello-container-fixture"))
        assert d.allowed is False

    def test_validate_plan_rejects_user_command(self):
        p = RootlessContainerExecutionProvider()
        d = p.validate_execution_plan(SandboxExecutionPlan(provider="docker_rootless_future", command_ref="rm -rf /"))
        assert d.allowed is False

    def test_validate_plan_rejects_unknown_fixture(self):
        p = RootlessContainerExecutionProvider()
        d = p.validate_execution_plan(SandboxExecutionPlan(provider="docker_rootless_future", command_ref="random-script"))
        assert d.allowed is False

    def test_validate_plan_rejects_non_allowed_image(self):
        p = RootlessContainerExecutionProvider()
        d = p.validate_execution_plan(SandboxExecutionPlan(provider="docker_rootless_future", command_ref="hello-container-fixture", image_ref="evil:latest"))
        assert d.allowed is False

    def test_execute_disabled_returns_rejected(self):
        p = RootlessContainerExecutionProvider()
        result = p.execute_trusted_fixture(SandboxExecutionPlan(job_id="j1"))
        assert result.status in ("rejected", "unavailable")

    def test_provider_cancel_no_active_process(self):
        p = RootlessContainerExecutionProvider()
        r = p.cancel_execution("x")
        assert r["canceled"] is False
