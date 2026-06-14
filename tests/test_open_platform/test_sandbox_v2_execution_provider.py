"""Test Step 6A — Execution Provider 测试。"""
import pytest
from src.open_platform.sandbox_v2.models import (
    SandboxExecutionPlan, SandboxV2IsolationProvider,
)
from src.open_platform.sandbox_v2.execution_provider import (
    DisabledExecutionProvider, TrustedFixtureExecutionProvider,
    create_default_provider_registry,
)


class TestDisabledProvider:
    def test_always_denies(self):
        p = DisabledExecutionProvider()
        assert p.get_provider_name() == "disabled"
        plan = SandboxExecutionPlan(provider="disabled")
        d = p.validate_execution_plan(plan)
        assert d.allowed is False

    def test_execute_fails(self):
        p = DisabledExecutionProvider()
        result = p.execute_trusted_fixture(SandboxExecutionPlan(job_id="j1"))
        assert result.status == "failed"
        assert "disabled" in result.stderr_text.lower()

    def test_cancel_no_process(self):
        p = DisabledExecutionProvider()
        r = p.cancel_execution("x")
        assert r["canceled"] is False


class TestTrustedFixtureProvider:
    def test_accepts_echo_hello(self):
        p = TrustedFixtureExecutionProvider()
        plan = SandboxExecutionPlan(provider="trusted_fixture", command_ref="echo_hello")
        d = p.validate_execution_plan(plan)
        assert d.allowed is True

    def test_rejects_user_command(self):
        p = TrustedFixtureExecutionProvider()
        plan = SandboxExecutionPlan(provider="trusted_fixture", command_ref="rm -rf /")
        d = p.validate_execution_plan(plan)
        assert d.allowed is False
        assert "untrusted_command_rejected" in d.matched_rules

    def test_rejects_image_ref(self):
        p = TrustedFixtureExecutionProvider()
        plan = SandboxExecutionPlan(provider="trusted_fixture", image_ref="ubuntu:latest")
        d = p.validate_execution_plan(plan)
        assert d.allowed is False

    def test_execute_echo_hello(self):
        p = TrustedFixtureExecutionProvider()
        result = p.execute_trusted_fixture(SandboxExecutionPlan(job_id="j1", command_ref="echo_hello"))
        assert result.status == "completed"
        assert "hello" in result.stdout_text.lower()
        assert result.exit_code == 0

    def test_execute_env_dump(self):
        p = TrustedFixtureExecutionProvider()
        result = p.execute_trusted_fixture(SandboxExecutionPlan(job_id="j2", command_ref="env_dump"))
        assert result.status == "completed"
        assert "PATH" in result.stdout_text

    def test_execute_network_check_fail(self):
        p = TrustedFixtureExecutionProvider()
        result = p.execute_trusted_fixture(SandboxExecutionPlan(job_id="j3", command_ref="network_check_fail"))
        assert result.status == "completed"
        assert result.exit_code == 6
        assert "FAILED" in result.stdout_text

    def test_no_subprocess_module(self):
        """验证不导入 subprocess 模块。"""
        import src.open_platform.sandbox_v2.execution_provider as ep
        assert "subprocess" not in ep.__dict__
        assert "subprocess" not in dir(ep)

    def test_no_network_module(self):
        import src.open_platform.sandbox_v2.execution_provider as ep
        for bad in ("urllib", "requests", "socket", "http.client"):
            assert bad not in ep.__dict__

    def test_cancel_no_real_process(self):
        p = TrustedFixtureExecutionProvider()
        r = p.cancel_execution("x")
        assert r["canceled"] is False
        assert "no active process" in r["message"].lower()


class TestProviderRegistry:
    def test_contains_disabled_and_fixture(self):
        reg = create_default_provider_registry()
        assert "disabled" in reg
        assert "trusted_fixture" in reg
        assert "docker_rootless_future" not in reg
