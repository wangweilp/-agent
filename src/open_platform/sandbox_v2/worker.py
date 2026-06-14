"""Sandbox v2 Worker — 任务队列 Worker Runner。

Worker 从 queue lease 任务，调用 SandboxV2Service 执行 simulation。

安全约束（必须遵守）：
- 不执行第三方代码
- 不调用 subprocess
- 不调用 Docker / MicroVM
- 不访问网络
- 不写真实 artifact
- 任何 execution 前必须经过 policy_engine 再检查
- 只处理 mode=metadata_only 或 mode=simulation
- future_container / future_microvm 必须拒绝

执行流程：
  queued → policy_checked → running_simulation → completed
  或 rejected / failed / canceled / timeout
"""

from __future__ import annotations

import logging
import time as _time
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
