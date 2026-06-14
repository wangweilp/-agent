"""Sandbox v2 Execution Provider — 可插拔执行 Provider 抽象。

本步骤实现两个 Provider：
1. DisabledExecutionProvider — 永远拒绝真实执行
2. TrustedFixtureExecutionProvider — 只运行内置 trusted fixture

不调用 subprocess、不调用 Docker/Podman/MicroVM、不执行用户代码。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from src.open_platform.sandbox_v2.models import (
    SandboxV2JobStatus,
    SandboxV2Mode,
    SandboxV2Decision,
    SandboxV2IsolationProvider,
    SandboxV2ExecutionPlanStatus,
    SandboxExecutionPlan,
    SandboxIsolationDecision,
    SandboxTrustedFixtureExecutionResult,
    SandboxV2ExecutionRecord,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# Provider Protocol
# ═══════════════════════════════════════════


@runtime_checkable
class ExecutionProvider(Protocol):
    """可插拔执行 Provider 接口。"""

    def get_provider_name(self) -> str:
        """返回 provider 名称。"""
        ...

    def get_capabilities(self) -> dict[str, Any]:
        """返回当前 provider 的能力描述。"""
        ...

    def validate_execution_plan(self, plan: SandboxExecutionPlan) -> SandboxIsolationDecision:
        """校验执行计划是否可在此 provider 执行。"""
        ...

    def execute_trusted_fixture(self, plan: SandboxExecutionPlan) -> SandboxTrustedFixtureExecutionResult:
        """执行内置 trusted fixture。不接受用户 command。"""
        ...

    def cancel_execution(self, execution_id: str) -> dict:
        """取消正在执行的作业。当前不杀进程。"""
        ...

    def cleanup(self, execution_id: str) -> bool:
        """清理执行资源。"""
        ...


# ═══════════════════════════════════════════
# DisabledExecutionProvider
# ═══════════════════════════════════════════


class DisabledExecutionProvider:
    """永远拒绝真实执行。"""

    def get_provider_name(self) -> str:
        return SandboxV2IsolationProvider.DISABLED

    def get_capabilities(self) -> dict:
        return {
            "provider": self.get_provider_name(),
            "execution_allowed": False,
            "reason": "Execution provider is DISABLED. No sandbox execution available.",
            "supported_modes": [],
        }

    def validate_execution_plan(self, plan: SandboxExecutionPlan) -> SandboxIsolationDecision:
        return SandboxIsolationDecision(
            allowed=False,
            provider=self.get_provider_name(),
            reason="Execution provider is DISABLED.",
            risk_level="low",
            matched_rules=["provider_disabled"],
            fail_closed=True,
        )

    def execute_trusted_fixture(self, plan: SandboxExecutionPlan) -> SandboxTrustedFixtureExecutionResult:
        now = datetime.now(timezone.utc)
        return SandboxTrustedFixtureExecutionResult(
            job_id=plan.job_id,
            provider=self.get_provider_name(),
            status=SandboxV2JobStatus.FAILED,
            started_at=now, finished_at=now, duration_ms=0,
            reason="Execution provider is DISABLED. Cannot execute.",
            stderr_text="Provider disabled. No execution.",
        )

    def cancel_execution(self, execution_id: str) -> dict:
        return {"execution_id": execution_id, "canceled": False, "message": "No active process. Provider is disabled."}

    def cleanup(self, execution_id: str) -> bool:
        return True


# ═══════════════════════════════════════════
# TrustedFixtureExecutionProvider
# ═══════════════════════════════════════════


class TrustedFixtureExecutionProvider:
    """只允许执行内置 trusted fixture。

    - 不接受用户传入 command
    - 不接受用户传入脚本
    - 不访问网络
    - 不安装包
    - 不写任意文件
    - 只返回固定 stdout/stderr fixture 文本
    """

    TRUSTED_FIXTURES: frozenset[str] = frozenset({
        "echo_hello",
        "env_dump",
        "cpu_info",
        "memory_check",
        "filesystem_check",
        "network_check_fail",
    })

    def get_provider_name(self) -> str:
        return SandboxV2IsolationProvider.TRUSTED_FIXTURE

    def get_capabilities(self) -> dict:
        return {
            "provider": self.get_provider_name(),
            "execution_allowed": True,
            "reason": "Trusted fixture execution only. No user code or arbitrary commands.",
            "supported_fixtures": sorted(self.TRUSTED_FIXTURES),
            "no_subprocess": True,
            "no_network": True,
            "no_user_command": True,
        }

    def validate_execution_plan(self, plan: SandboxExecutionPlan) -> SandboxIsolationDecision:
        # Reject if command_ref is provided by user
        if plan.command_ref and not self._is_trusted_fixture_ref(plan.command_ref):
            return SandboxIsolationDecision(
                allowed=False,
                provider=self.get_provider_name(),
                reason=f"Command '{plan.command_ref}' is not a trusted fixture. Only built-in fixtures allowed.",
                risk_level="high",
                matched_rules=["untrusted_command_rejected"],
                fail_closed=True,
            )
        # Reject if image_ref is non-empty (not needed for fixture)
        if plan.image_ref:
            return SandboxIsolationDecision(
                allowed=False,
                provider=self.get_provider_name(),
                reason="Image references are not supported in trusted fixture mode.",
                risk_level="high",
                matched_rules=["image_not_supported"],
                fail_closed=True,
            )
        return SandboxIsolationDecision(
            allowed=True,
            provider=self.get_provider_name(),
            action="execute_trusted_fixture",
            reason="Trusted fixture execution plan validated.",
            risk_level="low",
            execution_allowed=True,
            matched_rules=["trusted_fixture_valid"],
            fail_closed=False,
        )

    def execute_trusted_fixture(self, plan: SandboxExecutionPlan) -> SandboxTrustedFixtureExecutionResult:
        fixture_name = plan.command_ref or "echo_hello"
        if not self._is_trusted_fixture_ref(fixture_name):
            fixture_name = "echo_hello"

        start = datetime.now(timezone.utc)

        stdout, stderr, exit_code = self._execute_fixture(fixture_name, plan)

        finish = datetime.now(timezone.utc)
        duration_ms = int((finish - start).total_seconds() * 1000)

        return SandboxTrustedFixtureExecutionResult(
            fixture_id=f"sbxfix_{uuid4().hex[:16]}",
            job_id=plan.job_id,
            provider=self.get_provider_name(),
            status=SandboxV2JobStatus.COMPLETED,
            started_at=start, finished_at=finish, duration_ms=duration_ms,
            stdout_text=stdout, stderr_text=stderr, exit_code=exit_code,
            decision=SandboxV2Decision.ALLOW,
            reason=f"Trusted fixture '{fixture_name}' executed successfully. No user code ran.",
            metadata={"fixture_name": fixture_name, "platform": plan.metadata.get("platform", "fixture")},
        )

    def _execute_fixture(self, fixture_name: str, plan: SandboxExecutionPlan) -> tuple[str, str, int]:
        """执行内置 fixture — 不调用 subprocess，直接返回 fixture 文本。"""
        fixtures = {
            "echo_hello": ("hello from sandbox v2 trusted fixture\n", "", 0),
            "env_dump": ("PATH=/usr/local/sandbox/bin:/usr/bin\nHOME=/sandbox\nUSER=sandbox\n", "", 0),
            "cpu_info": ("model: Sandbox vCPU (fixture)\ncores: 2\narch: x86_64\n", "", 0),
            "memory_check": ("total: 256MB (fixture limit)\navailable: 200MB\n", "", 0),
            "filesystem_check": ("/sandbox (read-only)\n/tmp (tmpfs)\n/output (read-only artifact)\n", "", 0),
            "network_check_fail": (
                "Network check result: FAILED (expected)\n",
                "curl: (6) Could not resolve host: example.com\nThis is expected — network is blocked in sandbox.\n",
                6,
            ),
        }
        return fixtures.get(fixture_name, (f"Fixture '{fixture_name}' output.\n", "", 0))

    def _is_trusted_fixture_ref(self, ref: str) -> bool:
        if not ref:
            return True  # empty → default fixture
        if ref in self.TRUSTED_FIXTURES:
            return True
        if ref.startswith("fixture:"):
            name = ref.split(":", 1)[1] if ":" in ref else ref
            return name in self.TRUSTED_FIXTURES
        return False

    def cancel_execution(self, execution_id: str) -> dict:
        return {"execution_id": execution_id, "canceled": False, "message": "No active process. Fixture execution is synchronous."}

    def cleanup(self, execution_id: str) -> bool:
        return True


# ═══════════════════════════════════════════
# Provider Registry
# ═══════════════════════════════════════════


def create_default_provider_registry() -> dict[str, ExecutionProvider]:
    """创建默认 provider 注册表。只有 disabled 和 trusted_fixture。"""
    return {
        SandboxV2IsolationProvider.DISABLED: DisabledExecutionProvider(),
        SandboxV2IsolationProvider.TRUSTED_FIXTURE: TrustedFixtureExecutionProvider(),
    }
