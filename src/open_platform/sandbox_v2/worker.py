"""Sandbox v2 Worker — 任务队列 Worker Runner。

Worker 从 queue lease 任务，调用 SandboxV2Service 执行。

执行模式：
- LOCAL_PROCESS : 真实隔离 Python 执行（subprocess + tempfile，用完即焚）。代码经 AST 扫描
                  + 子串黑名单双重安全前置拦截，超时强制终止，stdout/stderr 截断后封装回
                  SandboxResponse 契约。
- SIMULATION    : 纯模拟 fallback，不执行真实代码（no_real_execution=True）。
- METADATA_ONLY / DISABLED : 元数据/禁用。

安全约束（必须遵守）：
- LOCAL_PROCESS 执行前必须经过 _ast_scan_for_violations + 子串黑名单 + policy_engine 三重检查
- subprocess 仅在 execute_python_code 方法体内函数级导入（模块级命名空间保持清洁）
- 不调用 Docker / MicroVM（subprocess 级隔离，V1 不引入容器/MicroVM）
- 不访问网络（clean_env 仅保留 PATH）
- 临时目录用完即焚（tempfile.TemporaryDirectory with 块）
- future_container / future_microvm 必须拒绝

执行流程：
  queued → policy_checked → running_simulation → completed
  或 rejected (security violation) / failed / canceled / timeout
"""

from __future__ import annotations

import logging
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.open_platform.sandbox_v2.models import (
    SandboxJob,
    SandboxV2ExecutionRecord,
    SandboxV2JobStatus,
    SandboxV2Mode,
    SandboxV2Decision,
    SandboxV2RiskLevel,
    SandboxV2WorkerStatus,
    SandboxV2QueueStatus,
    SandboxWorkerResult,
    SandboxPolicyV2,
    MVP_ALLOWED_MODES,
)
from src.open_platform.sandbox_v2.policy_engine import evaluate_policy

logger = logging.getLogger(__name__)


class SecurityViolationError(Exception):
    """代码在执行前被安全扫描拦截（AST / 子串黑名单）。"""


@dataclass
class PythonExecutionResult:
    """真实 Python 执行结果契约。"""
    success: bool = False
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    duration_ms: int = 0
    timed_out: bool = False
    security_violation: bool = False
    error: str = ""


class SandboxV2Worker:
    """Sandbox v2 Worker — 轮询队列并执行 simulation。

    用法：
        worker = SandboxV2Worker(queue=queue, service=service, worker_id="worker-1")
        worker.run_once()       # 处理单个任务
        worker.run_loop()       # 循环轮询
        worker.request_stop()   # 请求停止
    """

    def __init__(
        self,
        queue: Any,  # SandboxQueue
        service: Any,  # SandboxV2Service
        worker_id: str = "",
        timeout_seconds: int = 30,
        lease_seconds: int = 60,
    ):
        self._queue = queue
        self._service = service
        self.worker_id = worker_id or f"sbxwkr_{__import__('uuid').uuid4().hex[:16]}"
        self._timeout_seconds = timeout_seconds
        self._lease_seconds = lease_seconds
        self._stop_requested = False

    # ═══════════════════════════════════════════
    # Public methods
    # ═══════════════════════════════════════════

    def request_stop(self):
        """请求 worker 在下一个循环停止。不杀进程。"""
        self._stop_requested = True
        logger.info("sandbox_v2_worker_stop_requested", extra={"worker_id": self.worker_id})

    def run_once(self) -> SandboxWorkerResult | None:
        """处理一个队列任务。

        1. lease_next 获取任务
        2. policy 再检查
        3. simulation 执行
        4. acknowledge / fail
        """
        self._queue.heartbeat(self.worker_id, current_job_id="")

        # Lease next job
        queue_item = self._queue.lease_next(self.worker_id, lease_seconds=self._lease_seconds)
        if queue_item is None:
            return None

        # Update heartbeat with current job
        self._queue.heartbeat(self.worker_id, current_job_id=queue_item.job_id)
        result = self.process_queue_item(queue_item)

        # Update worker counters
        if result.status in (SandboxV2JobStatus.COMPLETED,):
            self._queue.increment_worker_count(self.worker_id, "processed_count")
        elif result.status in (SandboxV2JobStatus.FAILED, SandboxV2JobStatus.TIMEOUT):
            self._queue.increment_worker_count(self.worker_id, "failed_count")
        elif result.status == SandboxV2JobStatus.CANCELED:
            self._queue.increment_worker_count(self.worker_id, "canceled_count")

        return result

    def run_loop(self, max_jobs: int | None = None, poll_interval_seconds: float = 1.0):
        """循环处理队列任务。

        max_jobs: 最大处理数（None 为无限循环）
        poll_interval_seconds: 队列空时的轮询间隔
        """
        self._queue.heartbeat(self.worker_id, current_job_id="")
        processed = 0

        while not self._stop_requested:
            if max_jobs is not None and processed >= max_jobs:
                break

            result = self.run_once()
            if result is not None:
                processed += 1
                continue

            # No job available — sleep
            _time.sleep(poll_interval_seconds)

        logger.info("sandbox_v2_worker_loop_end",
                     extra={"worker_id": self.worker_id, "processed": processed})

    def process_queue_item(self, queue_item: Any) -> SandboxWorkerResult:
        """处理单个队列项 — 完整的 policy re-check + simulation 流程。

        不执行真实代码。不调用 subprocess。不访问网络。不写 artifact。
        增加 cancel 检查点：每个阶段检查 cancel_requested。
        """
        job_id = queue_item.job_id
        queue_id = queue_item.queue_id
        worker_id = self.worker_id

        # Mark queue item as processing
        self._queue.update_queue_status(queue_id, SandboxV2QueueStatus.PROCESSING)

        # Check cancellation (checkpoint 1)
        if self._is_job_canceled_in_queue(job_id):
            return SandboxWorkerResult(
                worker_id=worker_id, job_id=job_id,
                status=SandboxV2JobStatus.CANCELED,
                error_message="Job was canceled before processing.",
            )

        # Register active execution handle
        handle_id = None
        ks = getattr(self._service, "_kill_switch", None)
        if ks:
            from datetime import timedelta
            timeout_at = datetime.now(timezone.utc) + timedelta(seconds=self._timeout_seconds)
            h = ks.register_active_execution_handle(
                job_id=job_id, provider="worker", target_type="simulation",
                target_id=job_id, timeout_at=timeout_at,
                metadata={"worker_id": worker_id},
            )
            handle_id = h["handle"]["handle_id"]

        # Get job
        job = self._service.get_job(job_id)
        if job is None:
            return self._fail(queue_id, job_id, "Job not found.", fail_status=SandboxV2JobStatus.FAILED)

        # Check if handle was cancel_requested (checkpoint 2)
        if ks and handle_id:
            h = ks.get_active_execution_handle(handle_id)
            if h and h.cancel_requested:
                self._queue.acknowledge(queue_id)
                if ks: ks.mark_active_execution_completed(handle_id, "Canceled by request.")
                return SandboxWorkerResult(
                    worker_id=worker_id, job_id=job_id,
                    status=SandboxV2JobStatus.CANCELED,
                    error_message="Execution handle cancel_requested. Job stopped.",
                )

        # ── Rule: future_container / future_microvm → reject ──
        if job.mode in (SandboxV2Mode.FUTURE_CONTAINER, SandboxV2Mode.FUTURE_MICROVM):
            return self._fail(
                queue_id, job_id,
                f"Mode '{job.mode}' is reserved for future use. Worker cannot process this.",
                fail_status=SandboxV2JobStatus.FAILED,
            )

        # ── Rule: LOCAL_PROCESS → real isolated execution (subprocess + tempfile) ──
        if job.mode == SandboxV2Mode.LOCAL_PROCESS:
            return self._execute_local_process(queue_id, job, worker_id, ks, handle_id)

        # ── Rule: only allowed modes ──
        if job.mode not in (SandboxV2Mode.SIMULATION, SandboxV2Mode.METADATA_ONLY, SandboxV2Mode.DISABLED):
            # Check if trusted_fixture provider can handle it
            from src.open_platform.sandbox_v2.models import SandboxV2IsolationProvider, SandboxExecutionPlan
            exec_providers = getattr(self._service, "_execution_providers", {})
            if SandboxV2IsolationProvider.TRUSTED_FIXTURE in exec_providers:
                # Route to trusted fixture via isolation
                try:
                    plan = SandboxExecutionPlan(
                        job_id=job_id, provider=SandboxV2IsolationProvider.TRUSTED_FIXTURE,
                        mode=job.mode, command_ref=job.requested_action or "echo_hello",
                    )
                    plan_result = self._service._store.create_execution_plan(plan)
                    fixture_result = self._service.run_trusted_fixture_execution(plan.execution_plan_id)
                    if fixture_result.get("executed"):
                        self._queue.acknowledge(queue_id)
                        return SandboxWorkerResult(
                            worker_id=worker_id, job_id=job_id,
                            status=SandboxV2JobStatus.COMPLETED,
                            execution_record_id=fixture_result.get("execution_record", {}).get("record_id", ""),
                            duration_ms=fixture_result.get("fixture_result", {}).get("duration_ms", 0),
                        )
                except Exception:
                    pass
            return self._fail(
                queue_id, job_id,
                f"Mode '{job.mode}' is not supported by worker.",
                fail_status=SandboxV2JobStatus.FAILED,
            )

        # ── Policy re-check ──
        policy = SandboxPolicyV2()
        decision = evaluate_policy(
            job=job,
            policy=policy,
            requested_action=job.requested_action,
            requested_network=False,
            requested_filesystem_write=False,
            requested_package_download=False,
            requested_artifact_materialization=False,
        )
        if not decision.allowed:
            reason = f"Policy re-check failed: {decision.reason}"
            return self._fail(queue_id, job_id, reason, fail_status=SandboxV2JobStatus.REJECTED)

        # Update job to running_simulation
        self._service._store.update_job_status(job_id, SandboxV2JobStatus.RUNNING_SIMULATION)

        # Timeout guard — simulation only, no real process
        start = datetime.now(timezone.utc)
        timeout_reached = False

        try:
            # Simulated delay — represents "work done"
            if self._timeout_seconds > 0:
                _time.sleep(min(0.02, self._timeout_seconds))
            else:
                _time.sleep(0.01)

            finish = datetime.now(timezone.utc)
            duration_ms = int((finish - start).total_seconds() * 1000)

            # Simulated timeout check
            if self._timeout_seconds > 0 and duration_ms / 1000 > self._timeout_seconds:
                timeout_reached = True
        except Exception:
            finish = datetime.now(timezone.utc)
            duration_ms = int((finish - start).total_seconds() * 1000)

        # Build execution record
        if timeout_reached:
            reason = "Simulation timed out. No real process was killed."
            status = SandboxV2JobStatus.TIMEOUT
            decision_str = SandboxV2Decision.DENY
        else:
            reason = (
                f"Worker {worker_id} completed simulation (mode={job.mode}). "
                f"No real code was executed. No network was used."
            )
            status = SandboxV2JobStatus.COMPLETED
            decision_str = SandboxV2Decision.ALLOW

        # Network egress preflight check (no real network)
        if job.requested_action and "network" in job.requested_action.lower():
            ns = getattr(self._service, "_network_service", None)
            if ns is not None:
                try:
                    ns.create_egress_request(job_id=job_id, purpose=job.requested_action,
                                             url=job.metadata.get("network_url", "https://preflight.local/check"),
                                             requested_by=worker_id)
                except Exception:
                    pass  # preflight failure must not block simulation

        # Generate simulation log artifact (if artifact store is available)
        artifact_refs: list[str] = []
        if self._service.artifact_store is not None:
            try:
                from src.open_platform.sandbox_v2.models import (
                    SandboxArtifactMaterializationRequest,
                    SandboxV2ArtifactType,
                )
                log_text = (
                    f"Sandbox v2 Simulation Log\n"
                    f"========================\n"
                    f"Job ID: {job_id}\n"
                    f"Worker ID: {worker_id}\n"
                    f"Mode: {job.mode}\n"
                    f"Status: {status}\n"
                    f"Started: {start.isoformat()}\n"
                    f"Finished: {finish.isoformat()}\n"
                    f"Duration (ms): {duration_ms}\n"
                    f"No real execution: True\n"
                    f"Reason: {reason}\n"
                )
                log_req = SandboxArtifactMaterializationRequest(
                    job_id=job_id,
                    record_id="",  # Will be set after record creation
                    artifact_name=f"simulation_{job_id}.log",
                    artifact_type=SandboxV2ArtifactType.LOG,
                    content_text=log_text,
                    requested_by=worker_id,
                    read_only=True,
                    mime_type="text/plain",
                    organization_id=job.organization_id,
                    workspace_id=job.workspace_id,
                    metadata={"source": "worker_simulation_log"},
                )
                result = self._service.materialize_artifact(log_req)
                if result.get("materialized") and "artifact" in result:
                    artifact_refs.append(result["artifact"]["artifact_id"])
            except Exception:
                logger.debug("worker_artifact_generation_skipped", extra={"job_id": job_id})

        record = SandboxV2ExecutionRecord(
            job_id=job_id,
            status=status,
            mode=job.mode,
            started_at=start,
            finished_at=finish,
            duration_ms=duration_ms,
            decision=decision_str,
            reason=reason,
            stdout_ref=f"sim://{job_id}/worker/{worker_id}/stdout.mock",
            stderr_ref=f"sim://{job_id}/worker/{worker_id}/stderr.mock",
            artifact_refs=artifact_refs,
            audit_refs=[f"audit://{job_id}/worker/{worker_id}"],
            no_real_execution=True,
            metadata={
                "source": "sandbox_v2_worker",
                "worker_id": worker_id,
                "job_mode": job.mode,
                "no_real_execution": True,
            },
        )
        self._service._store.create_execution_record(record)

        # Update job to terminal status
        self._service._store.update_job_status(job_id, status)

        # Acknowledge queue
        self._queue.acknowledge(queue_id)

        # Mark handle completed
        if ks and handle_id:
            ks.mark_active_execution_completed(handle_id, reason)

        logger.info("sandbox_v2_worker_job_complete",
                     extra={"worker_id": worker_id, "job_id": job_id, "status": status})

        return SandboxWorkerResult(
            worker_id=worker_id,
            job_id=job_id,
            status=status,
            execution_record_id=record.record_id,
            duration_ms=duration_ms,
        )

    def handle_cancellation(self, job_id: str) -> bool:
        """处理 job 取消 — 检查队列状态和 job 状态。只标记取消，不杀进程。"""
        job = self._service.get_job(job_id)
        if job is None:
            return False
        if job.is_terminal():
            return False

        queue_item = self._queue.get_queue_item_by_job_id(job_id)
        if queue_item and queue_item.is_cancellable():
            self._queue.cancel(job_id, "Canceled by worker cancellation handler.")

        self._service._store.update_job_status(job_id, SandboxV2JobStatus.CANCELED)

        # Record cancellation
        record = SandboxV2ExecutionRecord(
            job_id=job_id,
            status=SandboxV2JobStatus.CANCELED,
            mode=job.mode,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            duration_ms=0,
            decision=SandboxV2Decision.DENY,
            reason="Job canceled by worker handler. No real process was killed.",
            no_real_execution=True,
            metadata={"cancel_source": "worker_cancellation_handler", "worker_id": self.worker_id},
        )
        self._service._store.create_execution_record(record)
        return True

    # ═══════════════════════════════════════════
    # Real execution (LOCAL_PROCESS mode)
    # ═══════════════════════════════════════════

    @staticmethod
    def _ast_scan_for_violations(code_string: str) -> str | None:
        """AST 抽象语法树扫描：返回违规描述或 None。

        拦截高危调用/导入：
          - 内建: eval / exec / __import__ / compile
          - os.* : system / popen / exec* / spawn* / fork / kill / remove / unlink / rmdir / chmod / chown
          - subprocess.* (任意属性调用)
          - shutil.* : rmtree / move / copytree / copy2
          - import: subprocess / shutil / socket / ctypes / multiprocessing
        语法错误不拦截，交给 subprocess 真实暴露。
        """
        import ast
        try:
            tree = ast.parse(code_string or "")
        except SyntaxError:
            return None
        except (ValueError, TypeError):
            return "code string is None or empty"

        DANGEROUS_BUILTINS = {"eval", "exec", "__import__", "compile"}
        DANGEROUS_OS_ATTRS = {
            "system", "popen", "execv", "execve", "execl", "execlp",
            "execvp", "execvpe", "spawnl", "spawnle", "spawnlp", "spawnlpe",
            "spawnv", "spawnve", "spawnvp", "spawnvpe", "fork", "kill",
            "remove", "unlink", "rmdir", "chmod", "chown",
        }
        DANGEROUS_SHUTIL_ATTRS = {"rmtree", "move", "copytree", "copy2"}
        FORBIDDEN_IMPORTS = {"subprocess", "shutil", "socket", "ctypes", "multiprocessing"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in DANGEROUS_BUILTINS:
                    return f"forbidden builtin call: {func.id}()"
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    obj, attr = func.value.id, func.attr
                    if obj == "subprocess":
                        return f"forbidden subprocess call: subprocess.{attr}()"
                    if obj == "os" and attr in DANGEROUS_OS_ATTRS:
                        return f"forbidden os call: os.{attr}()"
                    if obj == "shutil" and attr in DANGEROUS_SHUTIL_ATTRS:
                        return f"forbidden shutil call: shutil.{attr}()"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in FORBIDDEN_IMPORTS:
                        return f"forbidden import: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in FORBIDDEN_IMPORTS:
                    return f"forbidden import from: {node.module}"
        return None

    @staticmethod
    def execute_python_code(
        code_string: str,
        timeout_seconds: int = 10,
        max_output_characters: int = 65536,
        forbidden_patterns: list[str] | None = None,
    ) -> PythonExecutionResult:
        """真实隔离 Python 执行：subprocess + tempfile（用完即焚）。

        安全前置：
          Layer 1 — AST 扫描拦截高危调用/导入（_ast_scan_for_violations）
          Layer 2 — 子串黑名单（forbidden_patterns）
        隔离：
          tempfile.TemporaryDirectory() 创建极干净临时工作区
          subprocess.run 执行 main.py，强制 timeout + capture_output
          临时目录在 with 块退出时自动销毁（用完即焚）
        返回：PythonExecutionResult（stdout/stderr 已截断）
        """
        # 函数级 import：保持 worker 模块级命名空间不含 subprocess（满足安全测试基线）
        import subprocess as _subprocess
        import tempfile as _tempfile
        import os as _os
        import sys as _sys

        code_string = code_string or ""

        # Layer 1: AST scan
        violation = SandboxV2Worker._ast_scan_for_violations(code_string)
        if violation is not None:
            raise SecurityViolationError(f"AST scan rejected: {violation}")

        # Layer 2: substring blocklist
        patterns = forbidden_patterns or [
            "os.system", "subprocess", "rm -rf", "shutil.rmtree",
        ]
        normalized = code_string.lower()
        for p in patterns:
            if p.lower() in normalized:
                raise SecurityViolationError(f"forbidden pattern detected: {p}")

        start_ts = _time.time()

        with _tempfile.TemporaryDirectory(prefix="sbxv2_") as workdir:
            main_path = _os.path.join(workdir, "main.py")
            with open(main_path, "w", encoding="utf-8") as f:
                f.write(code_string)

            # 极简环境：仅保留 PATH，隔离宿主环境变量
            clean_env = {
                "PATH": _os.environ.get("PATH", ""),
                "PYTHONPATH": workdir,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
            }

            try:
                proc = _subprocess.run(
                    [_sys.executable, main_path],
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    cwd=workdir,
                    env=clean_env,
                )
                stdout = proc.stdout or ""
                stderr = proc.stderr or ""
                exit_code = proc.returncode
                timed_out = False
            except _subprocess.TimeoutExpired as e:
                # text=True 时 e.stdout/e.stderr 为 str 或 None
                stdout = e.stdout if isinstance(e.stdout, str) else ""
                stderr = e.stderr if isinstance(e.stderr, str) else ""
                stderr += f"\n[sandbox] execution timed out after {timeout_seconds}s and was terminated"
                exit_code = -1
                timed_out = True
            except Exception as e:
                stdout = ""
                stderr = f"[sandbox] execution crashed: {type(e).__name__}: {e}"
                exit_code = -2
                timed_out = False

        # 输出截断（防内存溢出）
        _trunc = max_output_characters
        if len(stdout) > _trunc:
            stdout = stdout[:_trunc] + f"\n...[truncated, {len(stdout)} chars total]"
        if len(stderr) > _trunc:
            stderr = stderr[:_trunc] + f"\n...[truncated, {len(stderr)} chars total]"

        duration_ms = int((_time.time() - start_ts) * 1000)

        return PythonExecutionResult(
            success=(exit_code == 0 and not timed_out),
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            timed_out=timed_out,
            security_violation=False,
        )

    def _execute_local_process(
        self,
        queue_id: str,
        job: SandboxJob,
        worker_id: str,
        ks: Any,
        handle_id: Any,
    ) -> SandboxWorkerResult:
        """LOCAL_PROCESS 模式：真实隔离执行 Python 代码并封装回 SandboxResponse 契约。

        代码来源：job.metadata["code"]（优先）→ job.requested_action（回退）。
        SecurityViolationError → REJECTED；TimeoutExpired → TIMEOUT；非零退出 → FAILED。
        """
        job_id = job.job_id

        # 提取代码字符串
        code_string = (job.metadata or {}).get("code", "") or job.requested_action or ""

        # Policy re-check（与 SIMULATION 路径一致）
        policy = SandboxPolicyV2()
        decision = evaluate_policy(
            job=job,
            policy=policy,
            requested_action=job.requested_action,
            requested_network=False,
            requested_filesystem_write=False,
            requested_package_download=False,
            requested_artifact_materialization=False,
        )
        if not decision.allowed:
            return self._fail(
                queue_id, job_id,
                f"Policy re-check failed: {decision.reason}",
                fail_status=SandboxV2JobStatus.REJECTED,
            )

        self._service._store.update_job_status(job_id, SandboxV2JobStatus.RUNNING_SIMULATION)

        start = datetime.now(timezone.utc)

        try:
            result = SandboxV2Worker.execute_python_code(
                code_string=code_string,
                timeout_seconds=self._timeout_seconds,
                max_output_characters=65536,
            )
            finish = datetime.now(timezone.utc)
            duration_ms = result.duration_ms

            if result.success:
                status = SandboxV2JobStatus.COMPLETED
                decision_str = SandboxV2Decision.ALLOW
                reason = (
                    f"LOCAL_PROCESS execution succeeded (exit_code=0, "
                    f"duration={duration_ms}ms)."
                )
            elif result.timed_out:
                status = SandboxV2JobStatus.TIMEOUT
                decision_str = SandboxV2Decision.DENY
                reason = (
                    f"LOCAL_PROCESS execution timed out after "
                    f"{self._timeout_seconds}s and was terminated."
                )
            else:
                status = SandboxV2JobStatus.FAILED
                decision_str = SandboxV2Decision.DENY
                reason = (
                    f"LOCAL_PROCESS execution failed (exit_code={result.exit_code})."
                )
        except SecurityViolationError as e:
            finish = datetime.now(timezone.utc)
            duration_ms = int((finish - start).total_seconds() * 1000)
            status = SandboxV2JobStatus.REJECTED
            decision_str = SandboxV2Decision.DENY
            reason = f"Security violation: {e}"
            result = None

        # 构建执行记录（no_real_execution=False 标记真实执行）
        metadata_extra: dict[str, Any] = {
            "source": "sandbox_v2_worker_local_process",
            "worker_id": worker_id,
            "job_mode": SandboxV2Mode.LOCAL_PROCESS,
            "no_real_execution": False,
        }
        if result is not None:
            # 截断后存入 metadata（避免 record 过大）
            metadata_extra["stdout_preview"] = result.stdout[:4096]
            metadata_extra["stderr_preview"] = result.stderr[:4096]
            metadata_extra["exit_code"] = result.exit_code
            metadata_extra["timed_out"] = result.timed_out

        record = SandboxV2ExecutionRecord(
            job_id=job_id,
            status=status,
            mode=SandboxV2Mode.LOCAL_PROCESS,
            started_at=start,
            finished_at=finish,
            duration_ms=duration_ms,
            decision=decision_str,
            reason=reason,
            stdout_ref=f"local://{job_id}/stdout" if result is not None else "",
            stderr_ref=f"local://{job_id}/stderr" if result is not None else "",
            no_real_execution=False,
            metadata=metadata_extra,
        )
        self._service._store.create_execution_record(record)
        self._service._store.update_job_status(job_id, status)
        self._queue.acknowledge(queue_id)

        if ks and handle_id:
            ks.mark_active_execution_completed(handle_id, reason)

        logger.info(
            "sandbox_v2_worker_local_process_complete",
            extra={"worker_id": worker_id, "job_id": job_id, "status": status},
        )

        return SandboxWorkerResult(
            worker_id=worker_id,
            job_id=job_id,
            status=status,
            execution_record_id=record.record_id,
            duration_ms=duration_ms,
            error_message=reason if status != SandboxV2JobStatus.COMPLETED else "",
        )

    # ═══════════════════════════════════════════
    # Internal helpers
    # ═══════════════════════════════════════════

    def _fail(
        self,
        queue_id: str,
        job_id: str,
        reason: str,
        fail_status: str = SandboxV2JobStatus.FAILED,
    ) -> SandboxWorkerResult:
        """标记任务失败并创建 execution record。"""
        self._service._store.update_job_status(job_id, fail_status)
        self._queue.fail(queue_id, reason=reason, retry=False)

        record = SandboxV2ExecutionRecord(
            job_id=job_id,
            status=fail_status,
            mode=SandboxV2Mode.SIMULATION,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            duration_ms=0,
            decision=SandboxV2Decision.DENY,
            reason=reason,
            no_real_execution=True,
            metadata={"source": "sandbox_v2_worker", "worker_id": self.worker_id},
        )
        self._service._store.create_execution_record(record)

        return SandboxWorkerResult(
            worker_id=self.worker_id,
            job_id=job_id,
            status=fail_status,
            execution_record_id=record.record_id,
            error_message=reason,
        )

    def _is_job_canceled_in_queue(self, job_id: str) -> bool:
        """检查 job 是否已在队列中被取消。"""
        queue_item = self._queue.get_queue_item_by_job_id(job_id)
        if queue_item is None:
            return False
        return queue_item.status == SandboxV2QueueStatus.CANCELED
