"""Sandbox v2 Rootless Container Provider — Docker/Podman 最小 PoC。

ContainerCommandBuilder: 构建安全容器命令（不执行）
RootlessContainerExecutionProvider: 实现 ExecutionProvider Protocol
  默认 disabled，需要 SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=true 才能执行
  只允许 trusted fixture，不允许用户 command/image

安全约束：
- 不要执行用户代码/command/script
- 不要使用用户 image
- 不要联网（--network=none）
- 不要使用 root 用户
- 不要挂载宿主机目录
- 不要 privileged
- 不要使用 shell=True
- 只允许 trusted fixture
"""

from __future__ import annotations

import logging
import os
import shutil
import platform as _platform
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.open_platform.sandbox_v2.models import (
    SandboxV2JobStatus, SandboxV2Decision,
    SandboxV2IsolationProvider, SandboxV2ContainerRuntime,
    SandboxV2ContainerExecutionStatus,
    SandboxContainerRuntimeConfig, SandboxContainerExecutionPlan,
    SandboxContainerExecutionResult,
    SandboxExecutionPlan, SandboxIsolationDecision,
    SandboxTrustedFixtureExecutionResult,
    TRUSTED_CONTAINER_FIXTURES, DEFAULT_ALLOWED_IMAGES,
)

logger = logging.getLogger(__name__)

_ENV_ENABLE = "SANDBOX_V2_CONTAINER_EXECUTION_ENABLED"
_NON_ROOT_USER = "65532:65532"
_DEFAULT_IMAGE = "python:3.11-alpine"


class ContainerCommandBuilder:
    """构建 Docker/Podman 安全命令参数。不执行命令。不使用 shell=True。"""

    @staticmethod
    def build_docker_command(
        image: str, command: list[str], *,
        network_mode: str = "none", readonly_rootfs: bool = True,
        user: str = _NON_ROOT_USER, memory_limit_mb: int = 256,
        cpu_limit: float = 0.5, pids_limit: int = 64,
        tmpfs_enabled: bool = True,
    ) -> list[str]:
        parts = ["docker", "run", "--rm",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--pids-limit={pids_limit}",
            f"--memory={memory_limit_mb}m",
            f"--cpus={cpu_limit}",
            f"--user={user}",
        ]
        if tmpfs_enabled:
            parts.append("--tmpfs=/tmp:rw,noexec,nosuid,size=16m")
        parts.append(image)
        parts.extend(command)
        return parts

    @staticmethod
    def build_podman_command(
        image: str, command: list[str], *,
        network_mode: str = "none", readonly_rootfs: bool = True,
        user: str = _NON_ROOT_USER, memory_limit_mb: int = 256,
        cpu_limit: float = 0.5, pids_limit: int = 64,
        tmpfs_enabled: bool = True,
    ) -> list[str]:
        parts = ["podman", "run", "--rm",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--pids-limit={pids_limit}",
            f"--memory={memory_limit_mb}m",
            f"--cpus={cpu_limit}",
            f"--user={user}",
        ]
        if tmpfs_enabled:
            parts.append("--tmpfs=/tmp:rw,noexec,nosuid,size=16m")
        parts.append(image)
        parts.extend(command)
        return parts

    @staticmethod
    def build_kill_command(runtime: str, container_id: str) -> list[str]:
        """构建容器 kill 命令（参数数组，不使用 shell=True）。"""
        if runtime == SandboxV2ContainerRuntime.PODMAN:
            return ["podman", "kill", container_id]
        return ["docker", "kill", container_id]

    @staticmethod
    def build(
        runtime: str, image: str, command: list[str],
        **kw,
    ) -> list[str]:
        if runtime == SandboxV2ContainerRuntime.PODMAN:
            return ContainerCommandBuilder.build_podman_command(image, command, **kw)
        return ContainerCommandBuilder.build_docker_command(image, command, **kw)


class RootlessContainerExecutionProvider:
    """Rootless Container Execution Provider — 默认 disabled。

    只有 SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=true + Linux 环境才允许真实执行。
    只允许运行 TRUSTED_CONTAINER_FIXTURES 中的内置 fixture。
    """

    def __init__(self, config: SandboxContainerRuntimeConfig | None = None):
        self._config = config or SandboxContainerRuntimeConfig()

    def get_provider_name(self) -> str:
        return self._config.provider

    def get_capabilities(self) -> dict:
        return {
            "provider": self.get_provider_name(), "runtime": self._config.runtime,
            "enabled": self._enabled(), "platform": _platform.system(),
            "rootless_required": self._config.rootless_required,
            "network_disabled": self._config.network_disabled,
            "readonly_rootfs": self._config.readonly_rootfs,
            "allowed_images": self._config.allowed_images,
            "allowed_fixtures": self._config.allowed_fixture_ids,
            "no_user_command": True, "no_user_image": True,
            "no_network": True, "no_privileged": True,
        }

    def validate_execution_plan(self, plan: SandboxExecutionPlan) -> SandboxIsolationDecision:
        # Provider name must match
        if plan.provider != self.get_provider_name():
            return SandboxIsolationDecision(
                allowed=False, provider=self.get_provider_name(),
                reason=f"Provider mismatch: plan.provider={plan.provider} != {self.get_provider_name()}",
                risk_level="high", matched_rules=["provider_mismatch"], fail_closed=True,
            )

        if not self._enabled():
            return SandboxIsolationDecision(
                allowed=False, provider=self.get_provider_name(),
                reason=f"Container execution is not enabled. Set {_ENV_ENABLE}=true.",
                risk_level="low", matched_rules=["container_execution_disabled"],
            )

        # Must be Linux
        if _platform.system() != "Linux":
            return SandboxIsolationDecision(
                allowed=False, provider=self.get_provider_name(),
                reason="Container execution requires Linux platform.",
                risk_level="medium", matched_rules=["platform_not_linux"],
            )

        # Runtime binary must exist
        if not self._runtime_available():
            return SandboxIsolationDecision(
                allowed=False, provider=self.get_provider_name(),
                reason=f"Container runtime '{self._config.runtime}' binary not found.",
                risk_level="high", matched_rules=["runtime_unavailable"],
            )

        # Only trusted fixture
        if not self._is_trusted_fixture(plan.command_ref):
            return SandboxIsolationDecision(
                allowed=False, provider=self.get_provider_name(),
                reason=f"Command '{plan.command_ref}' is not a trusted container fixture.",
                risk_level="high", matched_rules=["untrusted_command_rejected"], fail_closed=True,
            )

        # No user image allowed
        if plan.image_ref and plan.image_ref not in set(self._config.allowed_images):
            return SandboxIsolationDecision(
                allowed=False, provider=self.get_provider_name(),
                reason=f"Image '{plan.image_ref}' is not in allowed images: {self._config.allowed_images}.",
                risk_level="high", matched_rules=["image_not_allowed"], fail_closed=True,
            )

        return SandboxIsolationDecision(
            allowed=True, provider=self.get_provider_name(), action="execute_trusted_fixture",
            reason="Container trusted fixture execution plan validated. No user code. No network. No privileged.",
            risk_level="low", execution_allowed=True,
            network_allowed=False, filesystem_write_allowed=False, package_install_allowed=False,
            matched_rules=["container_trusted_fixture_valid"], fail_closed=False,
        )

    def execute_trusted_fixture(self, plan: SandboxExecutionPlan) -> SandboxTrustedFixtureExecutionResult:
        """执行 trusted fixture。如果未启用或环境不满足，返回 unavailable/rejected fixture 结果。"""
        start = datetime.now(timezone.utc)

        if not self._enabled():
            return _fixture_result(plan, start, "rejected",
                stderr="Container execution not enabled. Set SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=true.",
                reason="Container execution disabled.")

        if _platform.system() != "Linux":
            return _fixture_result(plan, start, "unavailable",
                stderr="Container execution requires Linux. Current platform: " + _platform.system(),
                reason="Not Linux — container execution unavailable.")

        if not self._runtime_available():
            return _fixture_result(plan, start, "unavailable",
                stderr=f"Runtime '{self._config.runtime}' binary not found.",
                reason="Container runtime not available.")

        # Check image locally
        image = plan.image_ref or _DEFAULT_IMAGE
        if not self._image_exists_locally(image):
            return _fixture_result(plan, start, "unavailable",
                stderr=f"Image '{image}' not found locally. Auto-pull is disabled.",
                reason="Image not found locally.")

        # Build command
        fixture_id = plan.command_ref or "hello-container-fixture"
        if not self._is_trusted_fixture(fixture_id):
            return _fixture_result(plan, start, "rejected",
                stderr=f"Fixture '{fixture_id}' is not a trusted container fixture.",
                reason="Not a trusted fixture.")

        cmd_parts = TRUSTED_CONTAINER_FIXTURES[fixture_id]
        full_cmd = ContainerCommandBuilder.build(
            self._config.runtime, image, cmd_parts,
            memory_limit_mb=self._config.memory_limit_mb,
            cpu_limit=self._config.cpu_limit,
            pids_limit=self._config.pids_limit,
        )

        # Try real execution
        try:
            import subprocess
            result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=self._config.timeout_seconds)
            finish = datetime.now(timezone.utc)
            duration_ms = int((finish - start).total_seconds() * 1000)
            return SandboxTrustedFixtureExecutionResult(
                fixture_id=f"sbxfix_{uuid4().hex[:16]}", job_id=plan.job_id,
                provider=self.get_provider_name(),
                status=SandboxV2JobStatus.COMPLETED if result.returncode == 0 else SandboxV2JobStatus.FAILED,
                started_at=start, finished_at=finish, duration_ms=duration_ms,
                stdout_text=result.stdout, stderr_text=result.stderr,
                exit_code=result.returncode,
                decision=SandboxV2Decision.ALLOW,
                reason=f"Container fixture '{fixture_id}' completed. No user code executed.",
                metadata={"command": full_cmd, "runtime": self._config.runtime,
                          "image": image, "returncode": result.returncode},
            )
        except subprocess.TimeoutExpired:
            finish = datetime.now(timezone.utc)
            return _fixture_result(plan, start, "timeout",
                stderr="Container execution timed out.",
                reason="Container execution timed out.",
                timeout=True, duration_ms=int((finish - start).total_seconds() * 1000))
        except FileNotFoundError:
            return _fixture_result(plan, start, "unavailable",
                stderr=f"Container runtime '{self._config.runtime}' command not found.",
                reason="Container runtime command not found.")
        except Exception as e:
            return _fixture_result(plan, start, "failed",
                stderr=f"Container execution failed: {e}",
                reason=f"Container execution exception: {e}.")

    def cancel_execution(self, execution_id: str) -> dict:
        """Cancel container execution. Only works if enabled + Linux + container_id recorded."""
        if not self._enabled():
            return {"execution_id": execution_id, "canceled": False,
                    "message": "Container execution not enabled. No container process to kill."}
        if _platform.system() != "Linux":
            return {"execution_id": execution_id, "canceled": False,
                    "message": "Not Linux — container kill unavailable."}
        if not execution_id or execution_id.startswith("pid:") or not execution_id.startswith("sbx"):
            return {"execution_id": execution_id, "canceled": False,
                    "message": "Invalid container_id. Refusing to kill arbitrary container."}
        if not self._runtime_available():
            return {"execution_id": execution_id, "canceled": False,
                    "message": f"Runtime '{self._config.runtime}' not found."}
        # Build kill command but don't execute unless explicitly enabled
        kill_cmd = ContainerCommandBuilder.build_kill_command(self._config.runtime, execution_id)
        try:
            import subprocess
            r = subprocess.run(kill_cmd, capture_output=True, text=True, timeout=10)
            return {"execution_id": execution_id, "canceled": r.returncode == 0,
                    "message": f"Container kill result: exit={r.returncode}", "command": kill_cmd, "stdout": r.stdout, "stderr": r.stderr}
        except Exception as e:
            return {"execution_id": execution_id, "canceled": False,
                    "message": f"Container kill failed: {e}"}

    def cleanup(self, execution_id: str) -> bool:
        return True

    # ═══════════════════════════════════════════
    # Step 6C — Real Container Trusted Fixture
    # ═══════════════════════════════════════════

    def get_container_runtime_preflight(self) -> dict:
        """完整前置条件检查。不 pull，不启动容器。"""
        from src.open_platform.sandbox_v2.isolation_capabilities import SandboxIsolationCapabilityProbe
        probe = SandboxIsolationCapabilityProbe()
        image = self._config.allowed_images[0] if self._config.allowed_images else "python:3.11-alpine"
        return probe.check_container_execution_preconditions(self._config.runtime, image)

    def run_real_trusted_fixture(
        self, *, job_id: str = "", fixture_id: str = "", image: str = "",
        organization_id: str = "", workspace_id: str = "",
    ) -> dict:
        """真实容器 trusted fixture 运行（Step 6C opt-in）。

        所有条件必须满足：Linux/WSL2 + env vars + runtime binary + local image。
        不 pull 镜像，不联网，不安装包。
        如果任何条件不满足，返回 disabled/unavailable/image_not_found/rejected。
        """
        result = {"job_id": job_id, "executed": False, "preflight": self.get_container_runtime_preflight()}
        pf = result["preflight"]

        if not pf["runnable"]:
            result["reason"] = pf["reason"]
            result["status"] = "unavailable" if pf["is_linux"] else "unavailable"
            if not pf["env_enabled"]: result["status"] = "disabled"
            if not pf["image_present"]: result["status"] = "image_not_found"
            return result

        # Select image
        img = image or (self._config.allowed_images[0] if self._config.allowed_images else "python:3.11-alpine")
        if img not in set(self._config.allowed_images):
            return {**result, "executed": False, "status": "rejected", "reason": f"Image '{img}' not in allowed_images."}

        # Select fixture
        fix_id = fixture_id or "hello-container-fixture"
        if fix_id not in TRUSTED_CONTAINER_FIXTURES:
            return {**result, "executed": False, "status": "rejected", "reason": f"Fixture '{fix_id}' is not trusted."}

        # Build container name
        import random, string
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        container_name = f"sandboxv2-{job_id or 'fixture'}-{suffix}"[:64]

        # Build safe command
        cmd_parts = TRUSTED_CONTAINER_FIXTURES[fix_id]
        mem_mb = self._config.memory_limit_mb
        cpu = self._config.cpu_limit
        pids = self._config.pids_limit
        timeout_s = self._config.timeout_seconds
        runtime = self._config.runtime

        safe_args = [
            runtime, "run", "--rm",
            "--name", container_name,
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--pids-limit={pids}",
            f"--memory={mem_mb}m",
            f"--cpus={cpu}",
            f"--user=65532:65532",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=16m",
            img,
        ] + cmd_parts

        # Execute
        start = datetime.now(timezone.utc)
        try:
            import subprocess
            proc = subprocess.run(safe_args, capture_output=True, text=True, timeout=timeout_s)
            finish = datetime.now(timezone.utc)
            duration_ms = int((finish - start).total_seconds() * 1000)

            result["executed"] = True
            result["status"] = "completed" if proc.returncode == 0 else "failed"
            result["exit_code"] = proc.returncode
            result["stdout"] = proc.stdout
            result["stderr"] = proc.stderr
            result["duration_ms"] = duration_ms
            result["container_name"] = container_name
            result["image"] = img
            result["fixture_id"] = fix_id
            result["runtime"] = runtime
            result["command"] = safe_args
            result["real_container_fixture"] = True
            result["reason"] = f"Real container fixture '{fix_id}' completed. No user code executed."
            logger.info("real_container_fixture_completed",
                        extra={"job_id": job_id, "container_name": container_name, "exit_code": proc.returncode, "duration_ms": duration_ms})
        except subprocess.TimeoutExpired:
            finish = datetime.now(timezone.utc)
            result["executed"] = True
            result["status"] = "timeout"
            result["exit_code"] = -1
            result["duration_ms"] = int((finish - start).total_seconds() * 1000)
            result["container_name"] = container_name
            result["command"] = safe_args
            result["real_container_fixture"] = True
            result["reason"] = "Container fixture timed out."
            # Attempt controlled cancel
            self.cancel_execution(container_name)
        except FileNotFoundError:
            result["status"] = "unavailable"
            result["reason"] = f"Runtime '{runtime}' command not found."
        except Exception as e:
            result["status"] = "failed"
            result["reason"] = f"Container execution exception: {e}."

        return result

    # ═══════ helpers ═══════

    def _enabled(self) -> bool:
        return os.environ.get(_ENV_ENABLE, "").lower() in ("true", "1", "yes")

    def _integration_enabled(self) -> bool:
        return self._enabled() and os.environ.get("SANDBOX_V2_RUN_CONTAINER_INTEGRATION", "").lower() in ("true", "1", "yes")

    def _runtime_available(self) -> bool:
        return shutil.which(self._config.runtime) is not None

    def _is_trusted_fixture(self, command_ref: str) -> bool:
        if not command_ref:
            return False
        return command_ref in TRUSTED_CONTAINER_FIXTURES

    def _image_exists_locally(self, image: str) -> bool:
        """Check if image exists locally without pulling. Returns False if docker/podman not available."""
        rt = shutil.which(self._config.runtime)
        if not rt:
            return False
        try:
            import subprocess
            r = subprocess.run([rt, "image", "inspect", image], capture_output=True, text=True, timeout=10)
            return r.returncode == 0
        except Exception:
            return False


def _fixture_result(
    plan: SandboxExecutionPlan, start: datetime, status: str,
    stdout: str = "", stderr: str = "", reason: str = "",
    timeout: bool = False, duration_ms: int = 0,
) -> SandboxTrustedFixtureExecutionResult:
    finish = datetime.now(timezone.utc)
    if duration_ms == 0:
        duration_ms = int((finish - start).total_seconds() * 1000)
    return SandboxTrustedFixtureExecutionResult(
        fixture_id=f"sbxfix_{uuid4().hex[:16]}", job_id=plan.job_id,
        provider=plan.provider, status=status,
        started_at=start, finished_at=finish, duration_ms=duration_ms,
        stdout_text=stdout or f"Container fixture {status}: {reason}",
        stderr_text=stderr, exit_code=1,
        decision=SandboxV2Decision.DENY if status != "completed" else SandboxV2Decision.ALLOW,
        reason=reason,
        metadata={"timeout": timeout},
    )
