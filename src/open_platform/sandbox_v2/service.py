"""Sandbox v2 Service Layer — 业务逻辑层。

负责：
1. submit_job — 提交 sandbox job（支持 enqueue 到队列）
2. evaluate_policy — 评估策略
3. create_execution_record — 创建执行记录
4. run_simulation — 模拟执行（不运行真实代码）
5. cancel_job — 取消 job（只更新状态，不杀进程）
6. get_job_status — 查询 job 状态
7. list_execution_records — 列出执行记录
8. enqueue_job / get_queue_status / cancel_queued_or_running_job — 队列管理
9. list_queue_items / list_worker_heartbeats / requeue_expired_jobs — 队列运维

安全约束：
- run_simulation 只做模拟，不执行真实代码、不启动进程、不访问网络、不写 artifact
- cancel_job 只更新状态，不假装杀进程
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.open_platform.sandbox_v2.models import (
    SandboxJob,
    SandboxV2ExecutionRecord,
    SandboxV2JobStatus,
    SandboxV2Mode,
    SandboxV2Decision,
    SandboxV2RiskLevel,
    SandboxPolicyV2,
    SandboxV2PolicyDecision,
    SandboxArtifact,
    SandboxArtifactManifest,
    SandboxArtifactMaterializationRequest,
    SandboxV2ArtifactStatus,
    SandboxV2ArtifactType,
    SandboxPackageRequest,
    SandboxPackageQuarantineRecord,
    SandboxPackageSBOM,
    SandboxPackageVulnerabilityScanResult,
    SandboxV2PackageRequestStatus,
    SandboxV2PackageQuarantineStatus,
    SandboxV2PackageManager,
    SandboxV2PackageSourceType,
    SandboxV2SignatureStatus,
    SandboxV2SBOMStatus,
    SandboxV2VulnerabilityStatus,
    SandboxExecutionPlan,
    SandboxIsolationDecision,
    SandboxIsolationCapability,
    SandboxV2IsolationProvider,
    SandboxV2ExecutionPlanStatus,
    SandboxContainerExecutionPlan,
    SandboxContainerExecutionResult,
    SandboxContainerRuntimeConfig,
    SandboxV2ContainerRuntime,
    SandboxV2ContainerExecutionStatus,
    SandboxV2KillTargetType,
    SandboxV2ArtifactType,
    SandboxV2ArtifactStatus,
    SandboxV2BenchmarkConfig,
    SandboxV2BenchmarkStatus,
    SandboxV2BenchmarkTarget,
    SandboxV2PerformanceProfile,
    MVP_ALLOWED_MODES,
)
from src.open_platform.sandbox_v2.policy_engine import evaluate_policy
from src.open_platform.sandbox_v2.artifact_policy import _guess_mime_from_name as _guess_mime
from src.open_platform.sandbox_v2.store import SandboxV2Store

logger = logging.getLogger(__name__)


class SandboxV2Service:
    """Sandbox v2 服务层。

    不执行代码、不启动进程、不访问网络、不写 artifact。
    """

    def __init__(self, store: SandboxV2Store, queue: Any = None, artifact_store: Any = None, package_store: Any = None, network_service: Any = None, execution_providers: Any = None, kill_switch: Any = None, iam_service: Any = None, observability_service: Any = None, load_tester: Any = None, slo_service: Any = None):
        self._store = store
        self._queue = queue
        self._artifact_store = artifact_store
        self._package_store = package_store
        self._network_service = network_service
        self._execution_providers = execution_providers or {}
        self._kill_switch = kill_switch
        self._iam_service = iam_service
        self._observability = observability_service
        self._load_tester = load_tester
        self._slo_service = slo_service

    @property
    def queue(self): return self._queue
    @property
    def artifact_store(self): return self._artifact_store
    @property
    def package_store(self): return self._package_store
    @property
    def network_service(self): return self._network_service
    @property
    def execution_providers(self): return self._execution_providers
    @property
    def kill_switch(self): return self._kill_switch
    @property
    def iam_service(self): return self._iam_service
    @property
    def observability_service(self): return self._observability
    @property
    def load_tester(self): return self._load_tester
    @property
    def slo_service(self): return self._slo_service

    # ═══════════════════════════════════════════
    # Job Management
    # ═══════════════════════════════════════════

    def submit_job(
        self,
        *,
        organization_id: str = "",
        workspace_id: str = "",
        agent_id: str = "",
        requested_by: str = "",
        mode: str = SandboxV2Mode.SIMULATION,
        requested_action: str = "",
        input_ref: str = "",
        metadata: dict | None = None,
        enqueue: bool = False,
        priority: int = 100,
        max_attempts: int = 3,
    ) -> dict:
        """提交 sandbox job。

        enqueue=True: 先策略检查，通过后加入任务队列。
        enqueue=False (默认): Step 1 行为 — 只策略检查和记录。
        """
        if mode not in MVP_ALLOWED_MODES:
            return {
                "job_id": None,
                "status": SandboxV2JobStatus.REJECTED,
                "decision": {
                    "allowed": False,
                    "action": SandboxV2Decision.DENY,
                    "reason": f"Mode '{mode}' is not allowed in MVP.",
                    "risk_level": SandboxV2RiskLevel.HIGH,
                    "required_approvals": ["security_admin"],
                    "matched_rules": ["mode_not_allowed"],
                    "fail_closed": True,
                    "policy_snapshot": {},
                },
            }

        job = SandboxJob(
            organization_id=organization_id,
            workspace_id=workspace_id,
            agent_id=agent_id,
            requested_by=requested_by,
            mode=mode,
            status=SandboxV2JobStatus.CREATED,
            requested_action=requested_action,
            input_ref=input_ref,
            metadata=metadata or {},
        )

        # Policy evaluation
        policy = SandboxPolicyV2()
        decision = evaluate_policy(
            job=job,
            policy=policy,
            requested_action=requested_action,
            requested_network=False,
            requested_filesystem_write=False,
            requested_package_download=False,
            requested_artifact_materialization=False,
        )

        if not decision.allowed:
            job.status = SandboxV2JobStatus.REJECTED
            job.risk_level = decision.risk_level
            job.policy_snapshot = decision.to_dict()
            job.updated_at = datetime.now(timezone.utc)
            self._store.create_job(job)
            return {
                "job_id": job.job_id,
                "status": job.status,
                "decision": decision.to_dict(),
            }

        # Policy passed
        job.risk_level = decision.risk_level
        job.policy_snapshot = decision.to_dict()
        job.updated_at = datetime.now(timezone.utc)

        if enqueue and self._queue is not None:
            # Enqueue to task queue
            job.status = SandboxV2JobStatus.POLICY_CHECKED
            self._store.create_job(job)

            queue_item = self._queue.enqueue(
                job_id=job.job_id,
                organization_id=organization_id,
                workspace_id=workspace_id,
                priority=priority,
                max_attempts=max_attempts,
            )
            # Update job to queued
            self._store.update_job_status(job.job_id, SandboxV2JobStatus.QUEUED)

            logger.info("sandbox_v2_job_enqueued",
                         extra={"job_id": job.job_id, "queue_id": queue_item.queue_id, "mode": mode})

            return {
                "job_id": job.job_id,
                "status": SandboxV2JobStatus.QUEUED,
                "queue_id": queue_item.queue_id,
                "decision": decision.to_dict(),
            }

        # enqueue=False — Step 1 behavior
        job.status = SandboxV2JobStatus.POLICY_CHECKED
        self._store.create_job(job)

        logger.info("sandbox_v2_job_submitted",
                     extra={"job_id": job.job_id, "mode": mode, "status": job.status})

        return {
            "job_id": job.job_id,
            "status": job.status,
            "decision": decision.to_dict(),
        }

    def evaluate_policy(
        self,
        job: SandboxJob,
        policy: SandboxPolicyV2 | None = None,
        requested_action: str = "",
    ) -> SandboxV2PolicyDecision:
        """评估 sandbox v2 策略，返回决策。"""
        return evaluate_policy(
            job=job,
            policy=policy or SandboxPolicyV2(),
            requested_action=requested_action,
        )

    def create_execution_record(
        self,
        job: SandboxJob,
        status: str,
        reason: str = "",
    ) -> SandboxV2ExecutionRecord:
        """为 job 创建一条执行记录。"""
        now = datetime.now(timezone.utc)
        record = SandboxV2ExecutionRecord(
            job_id=job.job_id,
            status=status,
            mode=job.mode,
            started_at=now,
            finished_at=None,
            duration_ms=0,
            decision=SandboxV2Decision.DENY if status == SandboxV2JobStatus.REJECTED else SandboxV2Decision.ALLOW,
            reason=reason,
            no_real_execution=True,
            metadata={"source": "sandbox_v2_service", "job_mode": job.mode},
        )
        self._store.create_execution_record(record)
        logger.info("sandbox_v2_execution_record_created",
                     extra={"record_id": record.record_id, "job_id": job.job_id, "status": status})
        return record

    def run_simulation(self, job_id: str) -> dict:
        """执行模拟 — 不运行真实代码。

        1. 获取 job
        2. 验证状态
        3. 生成模拟 execution record
        4. 更新 job 状态

        安全约束：
        - 不执行真实代码
        - 不启动进程
        - 不访问网络
        - 不写 artifact
        - 只生成 metadata execution record
        """
        job = self._store.get_job(job_id)
        if job is None:
            return {"error": f"Job '{job_id}' not found."}

        if job.is_terminal():
            return {
                "job_id": job_id,
                "status": job.status,
                "message": f"Job is already in terminal state '{job.status}'. Cannot run simulation.",
                "execution_record": None,
            }

        if job.mode not in (SandboxV2Mode.SIMULATION, SandboxV2Mode.METADATA_ONLY):
            return {
                "job_id": job_id,
                "status": job.status,
                "message": f"Job mode '{job.mode}' does not support simulation.",
                "execution_record": None,
            }

        # Update job status to running_simulation
        self._store.update_job_status(job_id, SandboxV2JobStatus.RUNNING_SIMULATION)

        start = datetime.now(timezone.utc)

        # Simulated execution — deterministic mock
        import time as _time
        _time.sleep(0.01)  # 模拟极短延迟，代表"元数据处理完成"

        finish = datetime.now(timezone.utc)
        duration_ms = int((finish - start).total_seconds() * 1000)

        # Create execution record
        reason = (
            f"Simulation completed successfully (mode={job.mode}). "
            f"No real code was executed. No network was used. No artifacts were written."
        )
        record = SandboxV2ExecutionRecord(
            job_id=job_id,
            status=SandboxV2JobStatus.COMPLETED,
            mode=job.mode,
            started_at=start,
            finished_at=finish,
            duration_ms=duration_ms,
            decision=SandboxV2Decision.ALLOW,
            reason=reason,
            stdout_ref=f"sim://{job_id}/stdout.mock",
            stderr_ref=f"sim://{job_id}/stderr.mock",
            artifact_refs=[],
            audit_refs=[f"audit://{job_id}/simulation"],
            no_real_execution=True,
            metadata={
                "source": "sandbox_v2_simulation",
                "job_mode": job.mode,
                "no_real_execution": True,
            },
        )
        self._store.create_execution_record(record)

        # Update job to completed
        self._store.update_job_status(job_id, SandboxV2JobStatus.COMPLETED)

        logger.info("sandbox_v2_simulation_completed",
                     extra={"job_id": job_id, "record_id": record.record_id, "duration_ms": duration_ms})

        return {
            "job_id": job_id,
            "status": SandboxV2JobStatus.COMPLETED,
            "message": reason,
            "execution_record": record.to_dict(),
        }

    def cancel_job(self, job_id: str) -> dict:
        """取消 job — 如果 kill_switch 可用则通过 kill policy，否则直接更新状态。"""
        # Use kill_switch if available
        if self._kill_switch is not None:
            result = self._kill_switch.request_kill(job_id=job_id, target_type="job")
            action = result.get("action_result", {})
            return {
                "job_id": job_id, "status": action.get("status_after", SandboxV2JobStatus.CANCELED),
                "message": action.get("message", "Canceled via kill switch."),
                "canceled": True, "kill_request_id": result["kill_request"]["kill_request_id"],
                "kill_record_id": action.get("kill_record_id", ""),
            }

        job = self._store.get_job(job_id)
        if job is None:
            return {"error": f"Job '{job_id}' not found."}

        if job.is_terminal():
            return {
                "job_id": job_id, "status": job.status,
                "message": f"Job is already in terminal state '{job.status}'. Cancel is not applicable. "
                           f"No process was killed (no real process existed).",
                "canceled": False,
            }

        if not job.is_cancellable():
            return {
                "job_id": job_id, "status": job.status,
                "message": f"Job in status '{job.status}' cannot be canceled.",
                "canceled": False,
            }

        self._store.update_job_status(job_id, SandboxV2JobStatus.CANCELED)

        # Create audit execution record for cancellation
        record = SandboxV2ExecutionRecord(
            job_id=job_id,
            status=SandboxV2JobStatus.CANCELED,
            mode=job.mode,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            duration_ms=0,
            decision=SandboxV2Decision.DENY,
            reason="Job canceled by user request. No real process was killed (metadata-only).",
            no_real_execution=True,
            metadata={"cancel_source": "user_request", "previous_status": job.status},
        )
        self._store.create_execution_record(record)

        logger.info("sandbox_v2_job_canceled",
                     extra={"job_id": job_id, "previous_status": job.status})

        return {
            "job_id": job_id,
            "status": SandboxV2JobStatus.CANCELED,
            "message": "Job canceled. No real process was killed (metadata-only cancel).",
            "canceled": True,
            "execution_record": record.to_dict(),
        }

    def get_job_status(self, job_id: str) -> dict | None:
        """查询 job 状态。"""
        job = self._store.get_job(job_id)
        if job is None:
            return None
        return job.to_dict()

    def list_execution_records(
        self,
        job_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """列出执行记录。"""
        records = self._store.list_execution_records(job_id=job_id, limit=limit)
        return [r.to_dict() for r in records]

    def get_job(self, job_id: str) -> SandboxJob | None:
        """获取 job 原始对象。"""
        return self._store.get_job(job_id)

    def list_jobs(
        self,
        organization_id: str | None = None,
        workspace_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """列出 jobs。"""
        jobs = self._store.list_jobs(
            organization_id=organization_id,
            workspace_id=workspace_id,
            limit=limit,
        )
        return [j.to_dict() for j in jobs]

    # ═══════════════════════════════════════════
    # Step 2 — Queue / Worker methods
    # ═══════════════════════════════════════════

    def enqueue_job(
        self,
        job_id: str,
        priority: int = 100,
        max_attempts: int = 3,
    ) -> dict:
        """将已存在的 job 加入队列。"""
        if self._queue is None:
            return {"error": "Queue is not configured."}

        job = self._store.get_job(job_id)
        if job is None:
            return {"error": f"Job '{job_id}' not found."}

        if job.is_terminal():
            return {"error": f"Job '{job_id}' is in terminal state '{job.status}'."}

        queue_item = self._queue.enqueue(
            job_id=job_id,
            organization_id=job.organization_id,
            workspace_id=job.workspace_id,
            priority=priority,
            max_attempts=max_attempts,
        )
        self._store.update_job_status(job_id, SandboxV2JobStatus.QUEUED)
        return {
            "job_id": job_id,
            "queue_id": queue_item.queue_id,
            "status": SandboxV2JobStatus.QUEUED,
        }

    def get_queue_status(self, job_id: str) -> dict:
        """查询 job 的队列状态。"""
        if self._queue is None:
            return {"error": "Queue is not configured."}

        queue_item = self._queue.get_queue_item_by_job_id(job_id)
        if queue_item is None:
            return {"job_id": job_id, "in_queue": False}

        return {
            "job_id": job_id,
            "in_queue": True,
            "queue_item": queue_item.to_dict(),
        }

    def cancel_queued_or_running_job(self, job_id: str) -> dict:
        """取消队列中或运行中的 job。同时更新 job 和 queue item。"""
        result = self.cancel_job(job_id)

        if self._queue is not None and result.get("canceled"):
            self._queue.cancel(job_id, "Canceled by user request.")

        return result

    def list_queue_items(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """列出队列项。"""
        if self._queue is None:
            return []
        items = self._queue.list_queue(status=status, limit=limit)
        return [i.to_dict() for i in items]

    def list_worker_heartbeats(self, limit: int = 50) -> list[dict]:
        """列出 worker 心跳记录。"""
        if self._queue is None:
            return []
        workers = self._queue.list_workers(limit=limit)
        return [w.to_dict() for w in workers]

    def requeue_expired_jobs(self) -> int:
        """回收过期 lease 的任务。"""
        if self._queue is None:
            return 0
        return self._queue.requeue_expired_leases()

    def list_dead_letter(self, limit: int = 50) -> list[dict]:
        """列出 dead letter 队列。"""
        if self._queue is None:
            return []
        items = self._queue.list_dead_letter(limit=limit)
        return [i.to_dict() for i in items]

    # ═══════════════════════════════════════════
    # Step 3 — Artifact methods
    # ═══════════════════════════════════════════

    def materialize_artifact(
        self,
        request: SandboxArtifactMaterializationRequest,
    ) -> dict:
        """物化 artifact — 经过 policy 检查后写入安全存储。

        返回 dict 包含 artifact metadata 和 policy decision。
        """
        if self._artifact_store is None:
            return {"error": "Artifact store is not configured."}

        from src.open_platform.sandbox_v2.artifact_policy import evaluate_artifact_policy

        # Policy check
        decision = evaluate_artifact_policy(request, force_read_only=True)
        if not decision.allowed:
            # Record rejected artifact in metadata only
            artifact = SandboxArtifact(
                job_id=request.job_id,
                organization_id=request.organization_id,
                workspace_id=request.workspace_id,
                record_id=request.record_id,
                artifact_type=request.artifact_type,
                name=request.artifact_name,
                status=SandboxV2ArtifactStatus.REJECTED,
                policy_decision_id=decision.reason[:64] if decision.reason else "",
                metadata={
                    "policy_decision": decision.to_dict(),
                    "source": "sandbox_v2_service_rejected",
                },
            )
            self._store.create_artifact(artifact)
            return {
                "artifact": artifact.to_dict(),
                "decision": decision.to_dict(),
                "materialized": False,
            }

        # Materialize
        try:
            artifact = self._artifact_store.create_artifact(
                job_id=request.job_id,
                organization_id=request.organization_id,
                workspace_id=request.workspace_id,
                record_id=request.record_id,
                artifact_type=request.artifact_type,
                name=request.artifact_name,
                original_filename=request.artifact_name,
                content=request.get_content(),
                mime_type=request.mime_type or _guess_mime(request.artifact_name),
                read_only=True,
                metadata={
                    **request.metadata,
                    "source": "sandbox_v2_service",
                    "policy_decision": decision.to_dict(),
                },
            )
        except Exception:
            logger.exception("artifact_materialization_failed")
            artifact = SandboxArtifact(
                job_id=request.job_id,
                record_id=request.record_id,
                artifact_type=request.artifact_type,
                name=request.artifact_name,
                status=SandboxV2ArtifactStatus.FAILED,
                metadata={"error": "materialization_failed"},
            )
            self._store.create_artifact(artifact)
            return {
                "artifact": artifact.to_dict(),
                "decision": decision.to_dict(),
                "materialized": False,
            }

        # Persist metadata
        self._store.create_artifact(artifact)
        return {
            "artifact": artifact.to_dict(),
            "decision": decision.to_dict(),
            "materialized": True,
        }

    def get_artifact(self, artifact_id: str) -> SandboxArtifact | None:
        """获取 artifact metadata。"""
        return self._store.get_artifact(artifact_id)

    def list_artifacts(
        self,
        job_id: str | None = None,
        record_id: str | None = None,
        organization_id: str | None = None,
        workspace_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """列出 artifacts。"""
        artifacts = self._store.list_artifacts(
            job_id=job_id, record_id=record_id,
            organization_id=organization_id, workspace_id=workspace_id,
            limit=limit,
        )
        return [a.to_dict() for a in artifacts]

    def get_artifact_content(self, artifact_id: str) -> dict:
        """读取 artifact 内容。"""
        artifact = self._store.get_artifact(artifact_id)
        if artifact is None:
            return {"error": f"Artifact '{artifact_id}' not found."}
        if self._artifact_store is None:
            return {"error": "Artifact store is not configured."}

        try:
            text = self._artifact_store.read_artifact_text(artifact.storage_key)
            return {
                "artifact_id": artifact_id,
                "content": text,
                "size_bytes": artifact.size_bytes,
                "mime_type": artifact.mime_type,
                "sha256": artifact.sha256,
            }
        except Exception as e:
            return {"error": str(e), "artifact_id": artifact_id}

    def create_artifact_manifest(
        self,
        job_id: str,
        record_id: str,
    ) -> dict:
        """为 job/record 创建 artifact manifest。"""
        if self._artifact_store is None:
            return {"error": "Artifact store is not configured."}

        artifacts = self._store.list_artifacts(job_id=job_id, record_id=record_id, limit=1000)
        manifest = self._artifact_store.create_manifest(job_id, record_id, artifacts)
        self._store.create_artifact_manifest(manifest)
        return {"manifest": manifest.to_dict()}

    def get_artifact_manifest(self, manifest_id: str) -> SandboxArtifactManifest | None:
        """获取 manifest。"""
        return self._store.get_artifact_manifest(manifest_id)

    def expire_artifacts(self, now: datetime | None = None) -> int:
        """标记过期的 artifact。返回过期数量。"""
        from datetime import timezone as _tz
        now = now or datetime.now(_tz)
        artifacts = self._store.list_artifacts(limit=1000)
        count = 0
        for a in artifacts:
            if a.is_expired(now) and a.status != SandboxV2ArtifactStatus.EXPIRED:
                self._store.mark_artifact_expired(a.artifact_id)
                count += 1
        return count

    def delete_artifact(self, artifact_id: str) -> dict:
        """删除 artifact（文件 + metadata）。"""
        artifact = self._store.get_artifact(artifact_id)
        if artifact is None:
            return {"error": f"Artifact '{artifact_id}' not found.", "deleted": False}

        # Delete file
        if self._artifact_store is not None and artifact.storage_key:
            self._artifact_store.delete_artifact_file(artifact.storage_key)

        # Mark metadata as deleted
        self._store.delete_artifact_metadata(artifact_id)
        return {"artifact_id": artifact_id, "deleted": True}

    def validate_artifact_request(self, request: SandboxArtifactMaterializationRequest) -> dict:
        """验证 artifact 物化请求，返回 policy decision。"""
        from src.open_platform.sandbox_v2.artifact_policy import evaluate_artifact_policy
        decision = evaluate_artifact_policy(request, force_read_only=True)
        return decision.to_dict()

    # ═══════════════════════════════════════════
    # Step 4 — Package / Supply Chain methods
    # ═══════════════════════════════════════════

    def request_package(self, **kw) -> dict:
        """创建 package request 并经过 policy 检查。"""
        from src.open_platform.sandbox_v2.package_policy import evaluate_package_policy

        request = SandboxPackageRequest(
            job_id=kw.get("job_id", ""),
            organization_id=kw.get("organization_id", ""),
            workspace_id=kw.get("workspace_id", ""),
            requested_by=kw.get("requested_by", ""),
            package_name=kw.get("package_name", ""),
            package_version=kw.get("package_version", ""),
            package_manager=kw.get("package_manager", SandboxV2PackageManager.UNKNOWN),
            source_url=kw.get("source_url", ""),
            source_type=kw.get("source_type", SandboxV2PackageSourceType.UNKNOWN),
            requested_action=kw.get("requested_action", ""),
            expected_sha256=kw.get("expected_sha256", ""),
            expected_signature=kw.get("expected_signature", ""),
            sbom_ref=kw.get("sbom_ref", ""),
            metadata=kw.get("metadata", {}),
        )

        decision = evaluate_package_policy(
            request, has_sha256=bool(request.expected_sha256),
            has_signature=bool(request.expected_signature),
            has_sbom=bool(request.sbom_ref),
            has_vulnerability_scan=False,
        )

        if not decision.allowed:
            request.status = SandboxV2PackageRequestStatus.REJECTED
            request.risk_level = decision.risk_level
            request.reason = decision.reason
            self._store.create_package_request(request)
            return {"package_request": request.to_dict(), "decision": decision.to_dict(), "accepted": False}

        request.status = SandboxV2PackageRequestStatus.POLICY_CHECKED
        request.risk_level = decision.risk_level
        request.reason = decision.reason
        self._store.create_package_request(request)
        return {"package_request": request.to_dict(), "decision": decision.to_dict(), "accepted": True}

    def evaluate_package_policy_for_request(self, request: SandboxPackageRequest) -> dict:
        """评估 package policy。"""
        from src.open_platform.sandbox_v2.package_policy import evaluate_package_policy
        d = evaluate_package_policy(
            request, has_sha256=bool(request.expected_sha256),
            has_signature=bool(request.expected_signature),
            has_sbom=bool(request.sbom_ref),
        )
        return d.to_dict()

    def quarantine_package(self, package_request_id: str, content_bytes: bytes = b"", content_text: str = "", original_filename: str = "") -> dict:
        """将包放入 quarantine。只接受离线内容。"""
        if self._package_store is None:
            return {"error": "Package quarantine store is not configured."}

        req = self._store.get_package_request(package_request_id)
        if req is None:
            return {"error": f"Package request '{package_request_id}' not found."}
        if req.status == SandboxV2PackageRequestStatus.REJECTED:
            return {"error": "Package request is rejected. Cannot quarantine."}

        content = content_bytes or (content_text.encode("utf-8") if content_text else b"")
        if not content:
            return {"error": "No content provided."}

        record, err = self._package_store.quarantine_package_bytes(
            content=content,
            original_filename=original_filename or f"{req.package_name}.tmp",
            package_request_id=package_request_id,
            job_id=req.job_id,
            organization_id=req.organization_id,
            workspace_id=req.workspace_id,
            package_name=req.package_name,
            package_version=req.package_version,
            package_manager=req.package_manager,
            expected_sha256=req.expected_sha256,
        )
        if record is None:
            return {"error": err, "quarantine_id": None}

        self._store.create_quarantine_record(record)
        self._store.update_package_request_status(package_request_id, SandboxV2PackageRequestStatus.QUARANTINED)
        return {"quarantine_record": record.to_dict(), "error": ""}

    def get_package_request(self, package_request_id: str) -> SandboxPackageRequest | None:
        return self._store.get_package_request(package_request_id)

    def list_package_requests(self, job_id: str | None = None, organization_id: str | None = None, workspace_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
        return [r.to_dict() for r in self._store.list_package_requests(job_id=job_id, organization_id=organization_id, workspace_id=workspace_id, status=status, limit=limit)]

    def get_quarantine_record(self, quarantine_id: str) -> SandboxPackageQuarantineRecord | None:
        return self._store.get_quarantine_record(quarantine_id)

    def list_quarantine_records(self, package_request_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
        return [r.to_dict() for r in self._store.list_quarantine_records(package_request_id=package_request_id, status=status, limit=limit)]

    def review_quarantine_record(self, quarantine_id: str, decision: str, reviewed_by: str = "", reason: str = "") -> dict:
        """审查 quarantine 记录。approved_metadata_only ≠ executable。"""
        from datetime import timezone as _tz
        record = self._store.get_quarantine_record(quarantine_id)
        if record is None:
            return {"error": f"Quarantine record '{quarantine_id}' not found."}

        if decision == "approved_metadata_only":
            new_status = SandboxV2PackageQuarantineStatus.APPROVED
        elif decision == "rejected":
            new_status = SandboxV2PackageQuarantineStatus.REJECTED
        else:
            return {"error": f"Invalid decision '{decision}'. Use 'approved_metadata_only' or 'rejected'."}

        updated = self._store.update_quarantine_status(quarantine_id, new_status, reason)
        if updated is None:
            return {"error": "Failed to update quarantine status."}

        return {
            "quarantine_id": quarantine_id,
            "decision": decision,
            "status": updated.status,
            "message": "Metadata approval recorded. This does NOT allow package execution or installation.",
        }

    def delete_quarantined_package(self, quarantine_id: str) -> dict:
        record = self._store.get_quarantine_record(quarantine_id)
        if record is None:
            return {"error": f"Quarantine record '{quarantine_id}' not found.", "deleted": False}
        if self._package_store is not None and record.storage_key:
            self._package_store.delete_quarantined_file(record.storage_key)
        self._store.update_quarantine_status(quarantine_id, SandboxV2PackageQuarantineStatus.DELETED)
        return {"quarantine_id": quarantine_id, "deleted": True}

    def submit_package_sbom(self, package_request_id: str, sbom_content: str, format: str = "unknown") -> dict:
        """提交并校验 SBOM。"""
        from src.open_platform.sandbox_v2.supply_chain import SBOMValidator
        validator = SBOMValidator()
        sbom, err = validator.validate_sbom(sbom_content, format)
        if sbom is None:
            return {"error": err}

        sbom.package_request_id = package_request_id

        # Try to get package name from request
        req = self._store.get_package_request(package_request_id)
        if req:
            sbom.package_name = req.package_name
            sbom.package_version = req.package_version

        self._store.create_package_sbom(sbom)

        # Update quarantine sbom_status if exists
        qrec = self._store.list_quarantine_records(package_request_id=package_request_id, limit=1)
        if qrec:
            self._store.update_quarantine_status(qrec[0].quarantine_id, qrec[0].status, f"SBOM submitted: {sbom.sbom_id}")

        return {"sbom": sbom.to_dict(), "validated": True}

    def validate_package_sbom(self, sbom_content: str, format: str = "unknown") -> dict:
        """校验 SBOM 格式。"""
        from src.open_platform.sandbox_v2.supply_chain import SBOMValidator
        validator = SBOMValidator()
        sbom, err = validator.validate_sbom(sbom_content, format)
        if sbom is None:
            return {"valid": False, "error": err}
        return {"valid": True, "sbom": sbom.to_dict()}

    def run_package_vulnerability_scan(self, package_request_id: str, sbom_id: str | None = None) -> dict:
        """运行漏洞扫描（fixture scanner，不联网）。"""
        from src.open_platform.sandbox_v2.supply_chain import VulnerabilityScanner
        scanner = VulnerabilityScanner()

        if sbom_id:
            sbom = self._store.get_package_sbom(sbom_id)
        else:
            sboms = self._store.list_package_sboms(package_request_id=package_request_id, limit=1)
            sbom = sboms[0] if sboms else None

        if sbom is None:
            # Create empty SBOM for scanning
            sbom = SandboxPackageSBOM(package_request_id=package_request_id, status=SandboxV2SBOMStatus.NOT_PROVIDED)

        req = self._store.get_package_request(package_request_id)
        pkg_name = req.package_name if req else ""
        pkg_ver = req.package_version if req else ""

        result = scanner.scan_sbom(sbom, package_name=pkg_name, package_version=pkg_ver, package_request_id=package_request_id)
        self._store.create_vulnerability_scan_result(result)
        return {"scan": result.to_dict()}

    def list_package_sboms(self, package_request_id: str | None = None, limit: int = 50) -> list[dict]:
        return [s.to_dict() for s in self._store.list_package_sboms(package_request_id=package_request_id, limit=limit)]

    def list_vulnerability_scan_results(self, package_request_id: str | None = None, limit: int = 50) -> list[dict]:
        return [r.to_dict() for r in self._store.list_vulnerability_scan_results(package_request_id=package_request_id, limit=limit)]

    # ═══════════════════════════════════════════
    # Step 5 — Network Egress methods
    # ═══════════════════════════════════════════

    def request_network_egress(self, **kw) -> dict:
        """创建网络出站请求。网络策略由 network_service 的 config 控制。"""
        if self._network_service is None:
            return {"error": "Network egress service is not configured.", "allowed": False}

        return self._network_service.create_egress_request(**kw)

    def evaluate_network_egress(self, **kw) -> dict:
        """即时网络预检，不持久化。"""
        if self._network_service is None:
            return {"allowed": False, "error": "Network egress service is not configured."}
        return self._network_service.evaluate_egress_policy(**kw)

    def list_network_egress_requests(self, job_id: str | None = None, organization_id: str | None = None, workspace_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
        if self._network_service is None: return []
        return self._network_service.list_egress_requests(job_id=job_id, organization_id=organization_id, workspace_id=workspace_id, status=status, limit=limit)

    def get_network_egress_request(self, egress_request_id: str) -> dict | None:
        if self._network_service is None: return None
        return self._network_service.get_egress_request(egress_request_id)

    def list_network_egress_audit_records(self, egress_request_id: str | None = None, job_id: str | None = None, limit: int = 50) -> list[dict]:
        if self._network_service is None: return []
        return self._network_service.list_audit_records(egress_request_id=egress_request_id, job_id=job_id, limit=limit)

    def get_network_egress_readiness(self) -> dict:
        if self._network_service is None:
            return {"network_egress_policy": False, "error": "Not configured."}
        return self._network_service.get_readiness()

    # ═══════════════════════════════════════════
    # Step 6A — Isolation / Execution methods
    # ═══════════════════════════════════════════

    def collect_isolation_capabilities(self) -> dict:
        from src.open_platform.sandbox_v2.isolation_capabilities import SandboxIsolationCapabilityProbe
        probe = SandboxIsolationCapabilityProbe()
        cap = probe.collect_capabilities()
        self._store.create_isolation_capability(cap)
        return probe.get_readiness_summary()

    def get_isolation_readiness(self) -> dict:
        return self.collect_isolation_capabilities()

    def create_execution_plan(self, **kw) -> dict:
        from src.open_platform.sandbox_v2.isolation_policy import evaluate_isolation_policy
        plan = SandboxExecutionPlan(
            job_id=kw.get("job_id", ""), organization_id=kw.get("organization_id", ""),
            workspace_id=kw.get("workspace_id", ""),
            provider=kw.get("provider", SandboxV2IsolationProvider.DISABLED),
            mode=kw.get("mode", SandboxV2Mode.SIMULATION),
            command_ref=kw.get("command_ref", ""), image_ref=kw.get("image_ref", ""),
            resource_limits=kw.get("resource_limits", {}),
            metadata=kw.get("metadata", {}),
        )
        decision = evaluate_isolation_policy(
            plan,
            resource_limits_provided=bool(plan.resource_limits),
            allow_network=kw.get("allow_network", False),
            allow_filesystem_write=kw.get("allow_filesystem_write", False),
            allow_package_install=kw.get("allow_package_install", False),
            allow_artifact_materialization_not_readonly=kw.get("allow_artifact_writable", False),
        )
        if not decision.allowed:
            plan.status = SandboxV2ExecutionPlanStatus.REJECTED
            plan.reason = decision.reason
        else:
            plan.status = SandboxV2ExecutionPlanStatus.CAPABILITY_CHECKED
            plan.reason = decision.reason
        self._store.create_execution_plan(plan)
        return {"execution_plan": plan.to_dict(), "decision": decision.to_dict()}

    def evaluate_isolation_policy(self, plan: SandboxExecutionPlan) -> dict:
        from src.open_platform.sandbox_v2.isolation_policy import evaluate_isolation_policy
        return evaluate_isolation_policy(plan).to_dict()

    def run_trusted_fixture_execution(self, execution_plan_id: str) -> dict:
        plan = self._store.get_execution_plan(execution_plan_id)
        if plan is None:
            return {"error": f"Execution plan '{execution_plan_id}' not found."}

        provider = self._execution_providers.get(plan.provider)
        if provider is None:
            return {"error": f"No provider found for '{plan.provider}'."}

        # Validate plan
        decision = provider.validate_execution_plan(plan)
        if not decision.allowed:
            self._store.update_execution_plan_status(execution_plan_id, SandboxV2ExecutionPlanStatus.REJECTED, decision.reason)
            return {"execution_plan": plan.to_dict(), "decision": decision.to_dict(), "executed": False}

        # Execute fixture
        result = provider.execute_trusted_fixture(plan)
        self._store.update_execution_plan_status(execution_plan_id, SandboxV2ExecutionPlanStatus.EXECUTED_FIXTURE, result.reason)

        # Create execution record
        record = SandboxV2ExecutionRecord(
            job_id=plan.job_id,
            status=SandboxV2JobStatus.COMPLETED,
            mode=plan.mode,
            started_at=result.started_at or datetime.now(timezone.utc),
            finished_at=result.finished_at or datetime.now(timezone.utc),
            duration_ms=result.duration_ms,
            decision=SandboxV2Decision.ALLOW,
            reason=result.reason,
            stdout_ref=f"fixture://{result.fixture_id}/stdout",
            stderr_ref=f"fixture://{result.fixture_id}/stderr",
            artifact_refs=result.artifact_refs,
            no_real_execution=True,
            metadata={"provider": plan.provider, "fixture_id": result.fixture_id},
        )
        self._store.create_execution_record(record)

        # Save stdout/stderr as artifacts if store available
        if self._artifact_store and result.stdout_text:
            art_stdout = SandboxArtifact(
                job_id=plan.job_id, record_id=record.record_id,
                artifact_type=SandboxV2ArtifactType.STDOUT,
                name="fixture_stdout.txt",
                safe_filename="fixture_stdout.txt",
                storage_key=f"fixture/{result.fixture_id}/stdout",
                size_bytes=len(result.stdout_text),
                mime_type="text/plain",
                sha256=__import__("hashlib").sha256(result.stdout_text.encode()).hexdigest(),
                status=SandboxV2ArtifactStatus.MATERIALIZED,
                read_only=True,
                metadata={"fixture_id": result.fixture_id, "provider": plan.provider},
            )
            self._store.create_artifact(art_stdout)
            result.artifact_refs.append(art_stdout.artifact_id)

        if self._artifact_store and result.stderr_text:
            art_stderr = SandboxArtifact(
                job_id=plan.job_id, record_id=record.record_id,
                artifact_type=SandboxV2ArtifactType.STDERR,
                name="fixture_stderr.txt",
                safe_filename="fixture_stderr.txt",
                storage_key=f"fixture/{result.fixture_id}/stderr",
                size_bytes=len(result.stderr_text),
                mime_type="text/plain",
                sha256=__import__("hashlib").sha256(result.stderr_text.encode()).hexdigest(),
                status=SandboxV2ArtifactStatus.MATERIALIZED,
                read_only=True,
                metadata={"fixture_id": result.fixture_id},
            )
            self._store.create_artifact(art_stderr)
            result.artifact_refs.append(art_stderr.artifact_id)

        self._store.update_execution_plan_status(execution_plan_id, SandboxV2ExecutionPlanStatus.COMPLETED, result.reason)
        return {
            "execution_plan": plan.to_dict(),
            "decision": decision.to_dict(),
            "executed": True,
            "fixture_result": result.to_dict(),
            "execution_record": record.to_dict(),
        }

    def get_execution_plan(self, execution_plan_id: str) -> SandboxExecutionPlan | None:
        return self._store.get_execution_plan(execution_plan_id)

    def list_execution_plans(self, job_id: str | None = None, organization_id: str | None = None, workspace_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
        return [p.to_dict() for p in self._store.list_execution_plans(job_id=job_id, organization_id=organization_id, workspace_id=workspace_id, status=status, limit=limit)]

    def cancel_execution_plan(self, execution_plan_id: str) -> dict:
        plan = self._store.get_execution_plan(execution_plan_id)
        if plan is None:
            return {"error": f"Execution plan '{execution_plan_id}' not found.", "canceled": False}
        provider = self._execution_providers.get(plan.provider)
        cancel_result = provider.cancel_execution(execution_plan_id) if provider else {"canceled": False, "message": "No provider found."}
        self._store.update_execution_plan_status(execution_plan_id, SandboxV2ExecutionPlanStatus.CANCELED, "Canceled. No real process was killed.")
        return {"execution_plan_id": execution_plan_id, "canceled": True, "message": "Execution plan canceled. No real process was killed.", "provider_result": cancel_result}

    # ═══════════════════════════════════════════
    # Step 6B — Container Execution methods
    # ═══════════════════════════════════════════

    def create_container_execution_plan(self, **kw) -> dict:
        plan = SandboxContainerExecutionPlan(
            job_id=kw.get("job_id", ""), execution_plan_id=kw.get("execution_plan_id", ""),
            provider=kw.get("provider", SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE),
            runtime=kw.get("runtime", SandboxV2ContainerRuntime.UNAVAILABLE),
            image=kw.get("image", ""), fixture_id=kw.get("fixture_id", ""),
            command=kw.get("command", []),
            resource_limits=kw.get("resource_limits", {}),
            timeout_seconds=kw.get("timeout_seconds", 30),
            status=SandboxV2ContainerExecutionStatus.CREATED,
            metadata=kw.get("metadata", {}),
        )
        self._store.create_container_execution_plan(plan)
        return {"container_plan": plan.to_dict()}

    def evaluate_container_execution_policy(self, container_plan_id: str) -> dict:
        plan = self._store.get_container_execution_plan(container_plan_id)
        if plan is None:
            return {"error": "Container plan not found.", "allowed": False}
        provider = self._execution_providers.get(plan.provider)
        if provider is None:
            return {"allowed": False, "reason": f"No provider for '{plan.provider}'."}
        sp = SandboxExecutionPlan(
            job_id=plan.job_id, provider=plan.provider,
            command_ref=plan.fixture_id, image_ref=plan.image,
        )
        d = provider.validate_execution_plan(sp)
        return d.to_dict()

    def run_container_trusted_fixture(self, container_plan_id: str) -> dict:
        plan = self._store.get_container_execution_plan(container_plan_id)
        if plan is None:
            return {"error": f"Container plan '{container_plan_id}' not found.", "executed": False}

        provider = self._execution_providers.get(plan.provider)
        if provider is None:
            self._store.update_container_execution_plan_status(container_plan_id, SandboxV2ContainerExecutionStatus.UNAVAILABLE, "No provider configured.")
            return {"container_plan": plan.to_dict(), "executed": False, "reason": "No provider configured."}

        sp = SandboxExecutionPlan(job_id=plan.job_id, provider=plan.provider, command_ref=plan.fixture_id, image_ref=plan.image)
        decision = provider.validate_execution_plan(sp)
        if not decision.allowed:
            self._store.update_container_execution_plan_status(container_plan_id, SandboxV2ContainerExecutionStatus.REJECTED, decision.reason)
            return {"container_plan": plan.to_dict(), "decision": decision.to_dict(), "executed": False}

        # Execute fixture
        self._store.update_container_execution_plan_status(container_plan_id, SandboxV2ContainerExecutionStatus.RUNNING)
        fixture_result = provider.execute_trusted_fixture(sp)

        # Persist result
        result = SandboxContainerExecutionResult(
            container_plan_id=container_plan_id, execution_plan_id=plan.execution_plan_id,
            job_id=plan.job_id, provider=plan.provider,
            runtime=plan.runtime, status=fixture_result.status,
            exit_code=fixture_result.exit_code,
            started_at=fixture_result.started_at, finished_at=fixture_result.finished_at,
            duration_ms=fixture_result.duration_ms,
            stdout_text=fixture_result.stdout_text, stderr_text=fixture_result.stderr_text,
            reason=fixture_result.reason,
            metadata={"fixture_id": plan.fixture_id, "image": plan.image},
        )
        self._store.create_container_execution_result(result)

        # Create execution record
        record = SandboxV2ExecutionRecord(
            job_id=plan.job_id, status=fixture_result.status,
            mode=SandboxV2Mode.SIMULATION,
            started_at=fixture_result.started_at, finished_at=fixture_result.finished_at,
            duration_ms=fixture_result.duration_ms,
            decision=fixture_result.decision, reason=fixture_result.reason,
            stdout_ref=f"container://{result.container_result_id}/stdout",
            stderr_ref=f"container://{result.container_result_id}/stderr",
            no_real_execution=False,  # container execution IS real execution (but only trusted fixtures)
            metadata={"provider": plan.provider, "runtime": plan.runtime, "container": True},
        )
        self._store.create_execution_record(record)

        final_status = SandboxV2ContainerExecutionStatus.COMPLETED if fixture_result.status == SandboxV2JobStatus.COMPLETED else SandboxV2ContainerExecutionStatus.FAILED
        self._store.update_container_execution_plan_status(container_plan_id, final_status, fixture_result.reason)

        return {"container_plan": plan.to_dict(), "executed": True,
                "fixture_result": fixture_result.to_dict(),
                "container_result": result.to_dict(),
                "execution_record": record.to_dict(),
                "note": "Trusted fixture only. No user code was executed."}

    def get_container_execution_plan(self, container_plan_id: str) -> SandboxContainerExecutionPlan | None:
        return self._store.get_container_execution_plan(container_plan_id)

    def list_container_execution_plans(self, job_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
        return [p.to_dict() for p in self._store.list_container_execution_plans(job_id=job_id, status=status, limit=limit)]

    def get_container_execution_result(self, container_result_id: str) -> SandboxContainerExecutionResult | None:
        return self._store.get_container_execution_result(container_result_id)

    def list_container_execution_results(self, job_id: str | None = None, container_plan_id: str | None = None, limit: int = 50) -> list[dict]:
        return [r.to_dict() for r in self._store.list_container_execution_results(job_id=job_id, container_plan_id=container_plan_id, limit=limit)]

    # ═══════════════════════════════════════════
    # Step 7 — Kill Switch methods
    # ═══════════════════════════════════════════

    # ═══════════════════════════════════════════
    # Step 6C — Real Container Fixture methods
    # ═══════════════════════════════════════════

    def get_container_runtime_preflight(self) -> dict:
        from src.open_platform.sandbox_v2.isolation_capabilities import SandboxIsolationCapabilityProbe
        from src.open_platform.sandbox_v2.models import DEFAULT_ALLOWED_IMAGES
        probe = SandboxIsolationCapabilityProbe()
        runtime = "docker" if __import__("shutil").which("docker") else ("podman" if __import__("shutil").which("podman") else "unavailable")
        image = sorted(DEFAULT_ALLOWED_IMAGES)[0]
        return probe.check_container_execution_preconditions(runtime, image)

    def run_real_container_trusted_fixture(self, container_plan_id: str) -> dict:
        plan = self._store.get_container_execution_plan(container_plan_id)
        if plan is None:
            return {"error": f"Container plan '{container_plan_id}' not found.", "executed": False}

        provider = self._execution_providers.get(plan.provider)
        if provider is None:
            return {"error": f"No provider for '{plan.provider}'.", "executed": False}

        result = provider.run_real_trusted_fixture(
            job_id=plan.job_id or container_plan_id,
            fixture_id=plan.fixture_id or "hello-container-fixture",
            image=plan.image or "",
            organization_id=getattr(plan, "organization_id", ""),
            workspace_id=getattr(plan, "workspace_id", ""),
        )

        if result.get("executed") and result.get("real_container_fixture"):
            # Persist container result
            cr = SandboxContainerExecutionResult(
                container_plan_id=container_plan_id, job_id=plan.job_id,
                provider=plan.provider, runtime=result.get("runtime", plan.runtime),
                status="completed" if result.get("status") == "completed" else "failed",
                exit_code=result.get("exit_code", -1),
                duration_ms=result.get("duration_ms", 0),
                stdout_text=result.get("stdout", ""), stderr_text=result.get("stderr", ""),
                reason=result.get("reason", ""),
                metadata={"real_container_fixture": True, "container_name": result.get("container_name", ""),
                          "image": result.get("image", ""), "fixture_id": result.get("fixture_id", "")},
            )
            self._store.create_container_execution_result(cr)
            result["container_result"] = cr.to_dict()

            # Create execution record
            record = SandboxV2ExecutionRecord(
                job_id=plan.job_id, status="completed" if result.get("status") == "completed" else "failed",
                mode=SandboxV2Mode.SIMULATION, duration_ms=result.get("duration_ms", 0),
                decision=SandboxV2Decision.ALLOW, reason=result.get("reason", ""),
                no_real_execution=False,
                metadata={"real_container_fixture": True, "container_name": result.get("container_name", ""),
                          "provider": plan.provider, "runtime": result.get("runtime", ""),
                          "fixture_id": result.get("fixture_id", ""), "image": result.get("image", "")},
            )
            self._store.create_execution_record(record)
            result["execution_record"] = record.to_dict()

            # Save stdout/stderr as read-only artifact
            if self._artifact_store and result.get("stdout"):
                art_out = SandboxArtifact(
                    job_id=plan.job_id, record_id=record.record_id,
                    artifact_type=SandboxV2ArtifactType.STDOUT, name="container_stdout.txt",
                    safe_filename="container_stdout.txt",
                    storage_key=f"container/{cr.container_result_id}/stdout",
                    size_bytes=len(result["stdout"]), mime_type="text/plain",
                    sha256=__import__("hashlib").sha256(result["stdout"].encode()).hexdigest(),
                    status=SandboxV2ArtifactStatus.MATERIALIZED, read_only=True,
                )
                self._store.create_artifact(art_out)
                result["stdout_artifact_id"] = art_out.artifact_id
            if self._artifact_store and result.get("stderr"):
                art_err = SandboxArtifact(
                    job_id=plan.job_id, record_id=record.record_id,
                    artifact_type=SandboxV2ArtifactType.STDERR, name="container_stderr.txt",
                    safe_filename="container_stderr.txt",
                    storage_key=f"container/{cr.container_result_id}/stderr",
                    size_bytes=len(result["stderr"]), mime_type="text/plain",
                    sha256=__import__("hashlib").sha256(result["stderr"].encode()).hexdigest(),
                    status=SandboxV2ArtifactStatus.MATERIALIZED, read_only=True,
                )
                self._store.create_artifact(art_err)
                result["stderr_artifact_id"] = art_err.artifact_id

        return result

    # ═══════════════════════════════════════════
    # Step 7 — Kill Switch methods
    # ═══════════════════════════════════════════

    def request_kill_job(self, job_id: str, **kw) -> dict:
        if self._kill_switch is None:
            return self.cancel_job(job_id)
        return self._kill_switch.request_kill(job_id=job_id, target_type=SandboxV2KillTargetType.JOB, **kw)

    def request_kill_execution_plan(self, execution_plan_id: str, **kw) -> dict:
        if self._kill_switch is None:
            plan = self._store.get_execution_plan(execution_plan_id)
            if plan is None: return {"error": "Not found."}
            return self._kill_switch.request_kill(job_id=plan.job_id, execution_plan_id=execution_plan_id, target_type=SandboxV2KillTargetType.EXECUTION_PLAN, target_id=execution_plan_id, **kw) if self._kill_switch else {}
        return self._kill_switch.request_kill(execution_plan_id=execution_plan_id, target_type=SandboxV2KillTargetType.EXECUTION_PLAN, target_id=execution_plan_id, **kw)

    def request_kill_container_plan(self, container_plan_id: str, **kw) -> dict:
        if self._kill_switch is None: return {"error": "Kill switch not configured."}
        return self._kill_switch.request_kill(container_plan_id=container_plan_id, target_type=SandboxV2KillTargetType.CONTAINER_PLAN, target_id=container_plan_id, **kw)

    def list_kill_requests(self, job_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
        if self._kill_switch is None: return []
        return self._kill_switch.list_kill_requests(job_id=job_id, status=status, limit=limit)

    def list_kill_records(self, job_id: str | None = None, kill_request_id: str | None = None, limit: int = 50) -> list[dict]:
        if self._kill_switch is None: return []
        return self._kill_switch.list_kill_records(job_id=job_id, kill_request_id=kill_request_id, limit=limit)

    def list_active_execution_handles(self, status: str | None = None, limit: int = 50) -> list[dict]:
        if self._kill_switch is None: return []
        return self._kill_switch.list_active_execution_handles(status=status, limit=limit)

    def request_handle_cancel(self, handle_id: str, reason: str = "") -> dict:
        if self._kill_switch is None: return {"error": "Kill switch not configured."}
        h = self._kill_switch.get_active_execution_handle(handle_id)
        if h is None: return {"error": "Handle not found."}
        self._store.mark_active_execution_cancel_requested(handle_id, reason)
        return {"handle_id": handle_id, "cancel_requested": True, "reason": reason}

    def register_execution_handle(self, **kw) -> dict:
        if self._kill_switch is None: return {"error": "Kill switch not configured."}
        return self._kill_switch.register_active_execution_handle(**kw)

    def mark_execution_handle_completed(self, handle_id: str) -> dict:
        if self._kill_switch is None: return {"error": "Kill switch not configured."}
        return self._kill_switch.mark_active_execution_completed(handle_id)

    def get_kill_readiness(self) -> dict:
        if self._kill_switch is None:
            return {"kill_switch": False, "error": "Kill switch not configured."}
        return self._kill_switch.get_kill_readiness()

    # ═══════════════════════════════════════════
    # Step 16 — Performance / Capacity
    # ═══════════════════════════════════════════

    def _performance_runner(self):
        from src.open_platform.sandbox_v2.config import load_sandbox_v2_settings
        from src.open_platform.sandbox_v2.performance import SandboxV2PerformanceBenchmark

        settings = load_sandbox_v2_settings()
        return SandboxV2PerformanceBenchmark(
            store=self._store,
            queue=self._queue,
            service=self,
            artifact_store=self._artifact_store,
            package_store=self._package_store,
            network_service=self._network_service,
            settings=settings,
        ), settings

    def _audit_performance_event(self, action: str, benchmark_id: str = "", decision: str = "allow", reason: str = "") -> None:
        try:
            from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService

            SandboxV2SecurityAuditService(store=self._store).create_audit_event(
                event_type="performance_benchmark",
                severity="info",
                principal_id="sandbox_v2_performance",
                resource_type="benchmark",
                resource_id=benchmark_id,
                action=action,
                decision=decision,
                reason=reason,
                metadata={"synthetic_fixture_only": True},
            )
        except Exception:
            logger.debug("sandbox_v2_performance_audit_skipped", extra={"action": action, "benchmark_id": benchmark_id})

    def create_performance_benchmark_config(self, **kw) -> dict[str, Any]:
        runner, _settings = self._performance_runner()
        config = runner.create_benchmark_config(**kw)
        self._audit_performance_event("create_config", config.benchmark_id, reason="benchmark config created")
        return config.to_dict()

    def list_performance_benchmark_configs(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = min(max(int(limit or 50), 1), 100)
        if not hasattr(self._store, "list_benchmark_configs"):
            return []
        return [c.to_dict() if hasattr(c, "to_dict") else c for c in self._store.list_benchmark_configs(limit=limit)]

    def run_performance_benchmark(self, benchmark_id: str) -> dict[str, Any]:
        runner, settings = self._performance_runner()
        config = self._store.get_benchmark_config(benchmark_id) if hasattr(self._store, "get_benchmark_config") else None
        if config is None:
            return {"benchmark_id": benchmark_id, "status": "not_found", "error": "Benchmark config not found."}

        if not settings.perf_tests_enabled:
            result = self._create_skipped_performance_result(
                config,
                reason="SANDBOX_V2_PERF_TESTS_ENABLED is false; benchmark run skipped.",
            )
            return {"benchmark_id": benchmark_id, "status": "disabled", "results": [result.to_dict()], "capacity_estimate": None}

        large_scale_profiles = {
            SandboxV2PerformanceProfile.MEDIUM,
            SandboxV2PerformanceProfile.LARGE,
            SandboxV2PerformanceProfile.CUSTOM,
        }
        if config.profile in large_scale_profiles and not settings.run_performance_benchmarks:
            result = self._create_skipped_performance_result(
                config,
                reason="SANDBOX_V2_RUN_PERFORMANCE_BENCHMARKS is false; medium/large/custom benchmark skipped.",
            )
            return {"benchmark_id": benchmark_id, "status": "skipped", "results": [result.to_dict()], "capacity_estimate": None}

        self._audit_performance_event("run_start", benchmark_id, reason="synthetic benchmark run started")
        result = runner.run_all(config)
        self._audit_performance_event("run_complete", benchmark_id, reason="synthetic benchmark run completed")
        return result

    def _create_skipped_performance_result(self, config: SandboxV2BenchmarkConfig, reason: str):
        from src.open_platform.sandbox_v2.models import SandboxV2BenchmarkResult

        now = datetime.now(timezone.utc)
        result = SandboxV2BenchmarkResult(
            benchmark_id=config.benchmark_id,
            target=SandboxV2BenchmarkTarget.END_TO_END,
            status=SandboxV2BenchmarkStatus.SKIPPED,
            started_at=now,
            finished_at=now,
            warnings=[reason],
            metadata={
                "synthetic_fixture_only": True,
                "disabled": True,
                "no_user_code": True,
                "no_external_network": True,
            },
        )
        if hasattr(self._store, "create_benchmark_result"):
            self._store.create_benchmark_result(result)
        self._audit_performance_event("run_skipped", config.benchmark_id, decision="deny", reason=reason)
        return result

    def list_performance_benchmark_results(
        self,
        benchmark_id: str | None = None,
        target: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = min(max(int(limit or 100), 1), 200)
        if not hasattr(self._store, "list_benchmark_results"):
            return []
        return [
            r.to_dict() if hasattr(r, "to_dict") else r
            for r in self._store.list_benchmark_results(benchmark_id=benchmark_id, target=target, limit=limit)
        ]

    def get_latest_capacity_estimate(self) -> dict[str, Any] | None:
        if not hasattr(self._store, "get_latest_capacity_estimate"):
            return None
        estimate = self._store.get_latest_capacity_estimate()
        return estimate.to_dict() if hasattr(estimate, "to_dict") else estimate

    def get_performance_report(self, benchmark_id: str, report_format: str = "markdown") -> dict[str, Any]:
        runner, _settings = self._performance_runner()
        config = self._store.get_benchmark_config(benchmark_id) if hasattr(self._store, "get_benchmark_config") else None
        if config is None:
            return {"benchmark_id": benchmark_id, "error": "Benchmark config not found."}
        results = self._store.list_benchmark_results(benchmark_id=benchmark_id, limit=100) if hasattr(self._store, "list_benchmark_results") else []
        capacity = self._store.get_latest_capacity_estimate() if hasattr(self._store, "get_latest_capacity_estimate") else None
        if report_format == "json":
            return {"benchmark_id": benchmark_id, "format": "json", "report": runner.export_report_json(config, results, capacity)}
        return {"benchmark_id": benchmark_id, "format": "markdown", "report": runner.export_report_markdown(config, results, capacity)}

    # ═══════════════════════════════════════════
    # Step 17 — IAM / SSO
    # ═══════════════════════════════════════════

    def create_iam_provider_config(self, **kwargs) -> Any:
        if not self._iam_service:
            raise RuntimeError("IAM service not configured")
        return self._iam_service.create_provider_config(**kwargs)

    def list_iam_provider_configs(self, **kwargs) -> list[Any]:
        if not self._iam_service:
            return []
        return self._iam_service.list_provider_configs(**kwargs)

    def get_iam_provider_config(self, provider_config_id: str) -> Any | None:
        if not self._iam_service:
            return None
        return self._iam_service.get_provider_config(provider_config_id)

    def create_iam_role_mapping(self, **kwargs) -> Any:
        if not self._iam_service:
            raise RuntimeError("IAM service not configured")
        return self._iam_service.create_role_mapping(**kwargs)

    def list_iam_role_mappings(self, **kwargs) -> list[Any]:
        if not self._iam_service:
            return []
        return self._iam_service.list_role_mappings(**kwargs)

    def simulate_sso_login(self, claims: dict[str, Any], provider_config_id: str,
                           organization_id: str = "", workspace_id: str = "") -> dict[str, Any]:
        if not self._iam_service:
            return {"allowed": False, "reason": "IAM service not configured"}
        return self._iam_service.simulate_sso_login(
            claims, provider_config_id, organization_id=organization_id, workspace_id=workspace_id,
        )

    def list_external_identities(self, **kwargs) -> list[Any]:
        if not self._iam_service:
            return []
        return self._iam_service.list_external_identities(**kwargs)

    def list_iam_mapping_decisions(self, **kwargs) -> list[Any]:
        if not self._iam_service:
            return []
        return self._iam_service.list_iam_mapping_decisions(**kwargs)

    def list_sso_simulation_results(self, **kwargs) -> list[Any]:
        if not self._iam_service:
            return []
        return self._iam_service.list_sso_simulation_results(**kwargs)

    def get_iam_readiness(self) -> dict[str, Any]:
        """IAM / SSO readiness."""
        if not self._iam_service:
            return {
                "iam_provider_config": True,
                "sso_config_model": True,
                "oidc_provider_skeleton": True,
                "saml_provider_skeleton": True,
                "mock_iam_provider": True,
                "claim_mapping": True,
                "role_scope_mapping": True,
                "jit_provisioning": False,
                "external_iam_enabled": False,
                "sso_enabled": False,
                "real_oidc_login": False,
                "real_saml_login": False,
                "token_storage": False,
                "token_introspection": False,
                "iam_safe_mode": True,
            }
        return self._iam_service.get_iam_readiness()

    # ═══════════════════════════════════════════
    # Step 18 — Observability / OTel
    # ═══════════════════════════════════════════

    def get_observability_readiness(self) -> dict[str, Any]:
        if not self._observability:
            return {"observability_config": True, "otel_adapter": True, "otel_real_export": False,
                    "observability_safe_mode": True, "blockers": [], "warnings": []}
        return self._observability.get_observability_readiness()

    def generate_grafana_dashboard(self, dashboard_type: str = "overview") -> dict[str, Any]:
        if not self._observability:
            return {"error": "Observability service not configured"}
        return self._observability.generate_grafana_dashboard(dashboard_type)

    def get_latest_grafana_dashboard(self) -> dict[str, Any] | None:
        if not self._observability:
            return None
        return self._observability.get_latest_grafana_dashboard()

    def generate_prometheus_scrape_config(self, **kwargs) -> dict[str, Any]:
        if not self._observability:
            return {}
        return self._observability.generate_prometheus_scrape_config(**kwargs)

    def generate_prometheus_alert_rules(self) -> dict[str, Any]:
        if not self._observability:
            return {}
        return self._observability.generate_prometheus_alert_rules()

    def create_trace_span(self, **kwargs) -> Any:
        if not self._observability:
            return None
        return self._observability.create_trace_span(**kwargs)

    def list_trace_spans(self, **kwargs) -> list[Any]:
        if not self._observability:
            return []
        return self._observability.list_trace_spans(**kwargs)

    def simulate_otel_export(self, **kwargs) -> dict[str, Any]:
        if not self._observability:
            return {"status": "disabled", "reason": "Observability service not configured"}
        return self._observability.simulate_otel_export(**kwargs)

    def list_telemetry_export_records(self, **kwargs) -> list[Any]:
        if not self._observability:
            return []
        return self._observability.list_telemetry_export_records(**kwargs)

    # ═══════════════════════════════════════════
    # Step 19 — Load Testing / SLO
    # ═══════════════════════════════════════════

    def get_load_testing_readiness(self) -> dict[str, Any]:
        from src.open_platform.sandbox_v2.config import load_sandbox_v2_settings
        s = load_sandbox_v2_settings()
        return {
            "load_testing_framework": True,
            "load_testing_enabled": s.load_testing_enabled,
            "staging_load_testing_enabled": s.run_staging_load_test,
            "local_dry_run_enabled": True,
            "production_load_testing_allowed": s.load_test_allow_production,
            "slo_definitions": True,
            "slo_evaluation": True,
            "capacity_planning": True,
            "external_load_testing": s.run_staging_load_test,
            "load_testing_safe_mode": not s.run_staging_load_test,
        }

    def create_load_test_config(self, **kwargs) -> Any:
        if self._load_tester:
            return self._load_tester.create_load_test_config(**kwargs)
        return None

    def run_load_test(self, load_test_id: str, mode: str = "local") -> dict[str, Any]:
        if not self._load_tester:
            return {"error": "Load tester not configured", "status": "blocked"}
        config = self._load_tester._get_config(load_test_id) if hasattr(self._load_tester, '_get_config') else None
        if not config:
            return {"error": f"Load test config not found: {load_test_id}", "status": "blocked"}
        if mode == "staging":
            from src.open_platform.sandbox_v2.config import load_sandbox_v2_settings
            s = load_sandbox_v2_settings()
            if not s.run_staging_load_test or not s.staging_base_url:
                return {"status": "skipped", "reason": "Staging load test not enabled"}
            return self._load_tester.run_staging_load_test(
                config, base_url=s.staging_base_url, token=s.staging_api_token,
            )
        return self._load_tester.run_local_dry_run(config)

    def list_load_test_results(self, **kwargs) -> list[Any]:
        if not self._store:
            return []
        try:
            return self._store.list_load_test_results(**kwargs)
        except Exception:
            return []

    def get_latest_capacity_plan(self) -> dict[str, Any] | None:
        if self._load_tester:
            plan = self._load_tester.generate_capacity_plan()
            return plan.to_dict() if plan else None
        return None

    def list_slo_definitions(self, **kwargs) -> list[Any]:
        if self._slo_service:
            return self._slo_service.list_slo_definitions(**kwargs)
        return []

    def list_slo_evaluations(self, **kwargs) -> list[Any]:
        if self._slo_service:
            return self._slo_service.list_slo_evaluations(**kwargs)
        return []

    def evaluate_slo_for_load_test(self, load_test_id: str) -> dict[str, Any]:
        if not self._slo_service or not self._store:
            return {"error": "SLO service not configured"}
        results = self._store.list_load_test_results(load_test_id=load_test_id, limit=100)
        slos = self._slo_service.list_slo_definitions(enabled=True)
        all_evals: list[Any] = []
        for r in results:
            evals = self._slo_service.evaluate_load_test_against_slo(r, slos)
            all_evals.extend(evals)
        return {
            "load_test_id": load_test_id,
            "evaluations": [e.to_dict() for e in all_evals],
            "summary": self._slo_service.generate_slo_summary(all_evals),
        }

    # ═══════════════════════════════════════════
    # Step 20 — Real OIDC / SAML
    # ═══════════════════════════════════════════

    def create_oidc_authorization_request(self, provider_config_id: str = "",
                                          organization_id: str = "", workspace_id: str = "",
                                          principal_hint: str = "") -> dict[str, Any]:
        if not self._iam_service: return {"status": "disabled", "reason": "IAM service not configured"}
        from src.open_platform.sandbox_v2.oidc_flow import SandboxV2OIDCFlowService
        oidc = SandboxV2OIDCFlowService(store=self._store, iam_service=self._iam_service,
                                         audit_service=getattr(self, '_audit', None), settings=getattr(self._iam_service, '_settings', None))
        pc = self._iam_service.get_provider_config(provider_config_id) if provider_config_id else None
        return oidc.create_authorization_request(pc, organization_id, workspace_id, principal_hint)

    def handle_oidc_callback(self, code: str = "", state: str = "", error: str = "",
                             provider_config_id: str = "", organization_id: str = "",
                             workspace_id: str = "") -> dict[str, Any]:
        if not self._iam_service: return {"status": "disabled", "reason": "IAM service not configured"}
        from src.open_platform.sandbox_v2.oidc_flow import SandboxV2OIDCFlowService
        oidc = SandboxV2OIDCFlowService(store=self._store, iam_service=self._iam_service,
                                         audit_service=getattr(self, '_audit', None), settings=getattr(self._iam_service, '_settings', None))
        return oidc.handle_callback(code, state, error, provider_config_id, organization_id, workspace_id)

    def create_saml_auth_request(self, provider_config_id: str = "",
                                 organization_id: str = "", workspace_id: str = "",
                                 principal_hint: str = "") -> dict[str, Any]:
        if not self._iam_service: return {"status": "disabled", "reason": "IAM service not configured"}
        from src.open_platform.sandbox_v2.saml_flow import SandboxV2SAMLFlowService
        saml = SandboxV2SAMLFlowService(store=self._store, iam_service=self._iam_service,
                                         audit_service=getattr(self, '_audit', None), settings=getattr(self._iam_service, '_settings', None))
        pc = self._iam_service.get_provider_config(provider_config_id) if provider_config_id else None
        return saml.create_authn_request(pc, organization_id, workspace_id, principal_hint)

    def handle_saml_acs(self, saml_response: str = "", relay_state: str = "",
                        provider_config_id: str = "", organization_id: str = "",
                        workspace_id: str = "") -> dict[str, Any]:
        if not self._iam_service: return {"status": "disabled", "reason": "IAM service not configured"}
        from src.open_platform.sandbox_v2.saml_flow import SandboxV2SAMLFlowService
        saml = SandboxV2SAMLFlowService(store=self._store, iam_service=self._iam_service,
                                         audit_service=getattr(self, '_audit', None), settings=getattr(self._iam_service, '_settings', None))
        return saml.handle_acs(saml_response, relay_state, provider_config_id, organization_id, workspace_id)

    def list_oidc_callback_results(self, **kwargs) -> list[Any]:
        if not self._store: return []
        try: return self._store.list_oidc_callback_results(**kwargs)
        except Exception: return []

    def list_saml_acs_results(self, **kwargs) -> list[Any]:
        if not self._store: return []
        try: return self._store.list_saml_acs_results(**kwargs)
        except Exception: return []

    def list_sso_sessions(self, **kwargs) -> list[Any]:
        if self._iam_service: return self._iam_service.list_sso_sessions(**kwargs)
        if not self._store: return []
        try: return self._store.list_sso_sessions(**kwargs)
        except Exception: return []

    def revoke_sso_session(self, session_id: str, reason: str = "") -> dict[str, Any]:
        if self._iam_service: return self._iam_service.revoke_sso_session(session_id, reason)
        return {"revoked": False, "reason": "IAM service not configured"}

    def get_real_sso_readiness(self) -> dict[str, Any]:
        if self._iam_service: return self._iam_service.get_real_sso_readiness()
        return {"real_oidc_login_enabled": False, "real_saml_login_enabled": False, "sso_safe_mode": True}

    def get_oidc_validation_readiness(self) -> dict[str, Any]:
        if self._iam_service: return self._iam_service.get_oidc_validation_readiness()
        # Fallback: build directly from settings so Runtime Admin still works without IAM
        from src.open_platform.sandbox_v2.oidc_step21_service import SandboxV2OIDCStep21Service
        return SandboxV2OIDCStep21Service(settings=getattr(self, '_settings', None)).get_oidc_validation_readiness()

    # ═══════════════════════════════════════════
    # Step 22 — Production-Grade SAML Signature Validation
    # ═══════════════════════════════════════════

    def get_saml_validation_readiness(self) -> dict[str, Any]:
        if self._iam_service and hasattr(self._iam_service, 'get_saml_validation_readiness'):
            return self._iam_service.get_saml_validation_readiness()
        from src.open_platform.sandbox_v2.saml_step22_service import SandboxV2SAMLStep22Service
        svc = SandboxV2SAMLStep22Service(
            settings=getattr(self, '_settings', None),
            store=self._store, iam_service=self._iam_service,
        )
        return svc.get_saml_validation_readiness()

    def validate_saml_assertion(
        self, assertion_xml: str = "", saml_response_xml: str = "",
        expected_issuer: str = "", expected_audience: str = "",
        expected_recipient: str = "", expected_destination: str = "",
        in_response_to_id: str = "", expected_cert_fingerprint: str = "",
        organization_id: str = "", workspace_id: str = "",
    ) -> dict[str, Any]:
        """Step 22 SAML assertion full validation pipeline. Default fail closed."""
        from src.open_platform.sandbox_v2.saml_step22_service import SandboxV2SAMLStep22Service
        svc = SandboxV2SAMLStep22Service(
            settings=getattr(self, '_settings', None),
            store=self._store, iam_service=self._iam_service,
            audit_service=getattr(self, '_audit', None),
        )
        return svc.validate_saml_assertion(
            assertion_xml=assertion_xml, saml_response_xml=saml_response_xml,
            expected_issuer=expected_issuer, expected_audience=expected_audience,
            expected_recipient=expected_recipient, expected_destination=expected_destination,
            in_response_to_id=in_response_to_id,
            expected_cert_fingerprint=expected_cert_fingerprint,
            organization_id=organization_id, workspace_id=workspace_id,
        )

    def validate_oidc_id_token(
        self, id_token: str = "", expected_issuer: str = "",
        expected_audience: str = "", expected_nonce: str = "",
    ) -> Any:
        """Step 21 id_token 验证。不存 token；默认 fail closed。"""
        import hashlib
        nonce_hash = ""
        if expected_nonce:
            nonce_hash = hashlib.sha256(expected_nonce.encode()).hexdigest()
        from src.open_platform.sandbox_v2.oidc_step21_service import SandboxV2OIDCStep21Service
        svc = SandboxV2OIDCStep21Service(settings=getattr(self._iam_service, '_settings', None) or getattr(self, '_settings', None))
        return svc.validate_id_token(
            id_token, expected_issuer=expected_issuer,
            expected_audience=expected_audience,
            expected_nonce_hash=nonce_hash, expected_nonce=expected_nonce,
        )

    def get_performance_readiness(self) -> dict[str, Any]:
        from src.open_platform.sandbox_v2.config import load_sandbox_v2_settings

        settings = load_sandbox_v2_settings()
        safe_profile = settings.perf_profile in {
            SandboxV2PerformanceProfile.SMOKE,
            SandboxV2PerformanceProfile.SMALL,
        }
        blockers: list[str] = []
        warnings: list[str] = []
        if not settings.perf_tests_enabled:
            warnings.append("Performance tests are disabled by default.")
        if settings.perf_profile == SandboxV2PerformanceProfile.LARGE and not settings.run_performance_benchmarks:
            blockers.append("large profile is disabled unless SANDBOX_V2_RUN_PERFORMANCE_BENCHMARKS=true")
        return {
            "performance_benchmarking": True,
            "performance_tests_enabled": settings.perf_tests_enabled,
            "performance_benchmarks_enabled": settings.run_performance_benchmarks,
            "performance_safe_profile": safe_profile,
            "default_profile": settings.perf_profile,
            "synthetic_fixture_only": True,
            "external_load_testing": False,
            "user_code_benchmarking": False,
            "container_benchmarking": False,
            "microvm_benchmarking": False,
            "capacity_estimation": True,
            "benchmark_cleanup_enabled": settings.perf_cleanup_after_run,
            "max_jobs": settings.perf_max_jobs,
            "max_queue_items": settings.perf_max_queue_items,
            "max_artifacts": settings.perf_max_artifacts,
            "max_concurrency": settings.perf_max_concurrency,
            "timeout_seconds": settings.perf_timeout_seconds,
            "allowed_profiles": ["smoke", "small"],
            "large_profile_enabled": settings.run_performance_benchmarks and settings.perf_profile == "large",
            "warnings": warnings,
            "blockers": blockers,
        }
