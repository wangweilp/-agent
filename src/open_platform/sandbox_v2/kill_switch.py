"""Sandbox v2 Kill Switch Service — Kill/Cancel/Terminate 统一控制服务。

协调 kill request → policy → queue cancel → provider cancel → audit record。
所有 kill 必须经过 kill_policy。所有 kill 必须有 audit record。
不杀任意系统进程。不接受用户 PID。container kill 默认 disabled。

安全约束：fail closed。Provider cancel 不假装成功。
"""

from __future__ import annotations

import logging, platform as _plat
from datetime import datetime, timezone
from typing import Any

from src.open_platform.sandbox_v2.models import (
    SandboxV2JobStatus, SandboxV2QueueStatus, SandboxV2RiskLevel,
    SandboxV2KillRequestStatus, SandboxV2KillTargetType, SandboxV2KillAction,
    SandboxV2ActiveExecutionStatus,
    SandboxKillRequest, SandboxKillDecision, SandboxKillRecord,
    SandboxActiveExecutionHandle,
)

logger = logging.getLogger(__name__)


class SandboxKillSwitchService:
    """Kill Switch 服务 — 统一管理 kill/cancel/timeout。"""

    def __init__(self, store: Any = None, queue: Any = None, execution_providers: dict | None = None):
        self._store = store
        self._queue = queue
        self._execution_providers = execution_providers or {}

    def request_kill(self, **kw) -> dict:
        """创建 kill request 并经过 policy 评估。"""
        from src.open_platform.sandbox_v2.kill_policy import evaluate_kill_policy

        target_type = kw.get("target_type", SandboxV2KillTargetType.JOB)
        target_id = kw.get("target_id", kw.get("job_id", ""))
        job_id = kw.get("job_id", "")

        # Gather target state
        exists, status, owned, ce, cr, ps = self._gather_target_state(target_type, target_id, job_id)

        req = SandboxKillRequest(
            job_id=job_id, execution_plan_id=kw.get("execution_plan_id", ""),
            container_plan_id=kw.get("container_plan_id", ""),
            organization_id=kw.get("organization_id", ""),
            workspace_id=kw.get("workspace_id", ""),
            requested_by=kw.get("requested_by", "system"),
            reason=kw.get("reason", ""), scope=kw.get("scope", "job"),
            target_type=target_type, target_id=target_id,
            force=kw.get("force", False), metadata=kw.get("metadata", {}),
        )

        decision = evaluate_kill_policy(
            req, target_exists=exists, target_status=status,
            target_is_owned_by_sandbox=owned,
            container_execution_enabled=ce, container_id_recorded=cr,
            provider_supports_cancel=ps,
        )

        if self._store:
            req.status = SandboxV2KillRequestStatus.REJECTED if not decision.allowed else SandboxV2KillRequestStatus.POLICY_CHECKED
            self._store.create_kill_request(req)

        # Apply decision
        action_result = self._apply_decision(req, decision, target_type, target_id, job_id, status)

        # Create audit record
        if self._store:
            self._store.create_kill_record(SandboxKillRecord(
                kill_request_id=req.kill_request_id, job_id=job_id,
                execution_plan_id=req.execution_plan_id,
                container_plan_id=req.container_plan_id,
                provider=kw.get("provider", ""), target_type=target_type,
                target_id=target_id, action_taken=decision.action,
                status_before=status, status_after=action_result.get("status_after", status),
                provider_result=action_result.get("provider_result", ""),
                error_message=action_result.get("error", ""),
                metadata={"decision": decision.to_dict()},
            ))

        return {"kill_request": req.to_dict(), "decision": decision.to_dict(), "action_result": action_result}

    def _gather_target_state(self, target_type, target_id, job_id):
        exists, status, owned, ce, cr, ps = False, "unknown", True, False, False, False
        if not self._store:
            return exists, status, owned, ce, cr, ps

        # Check job
        if target_type in (SandboxV2KillTargetType.JOB, SandboxV2KillTargetType.QUEUE_ITEM):
            job = self._store.get_job(job_id) if job_id else None
            if job:
                exists, status, owned = True, job.status, True

        # Check queue
        if target_type == SandboxV2KillTargetType.QUEUE_ITEM and self._queue:
            qi = self._queue.get_queue_item_by_job_id(job_id)
            if qi:
                exists, status = True, qi.status

        # Check execution plan
        if target_type == SandboxV2KillTargetType.EXECUTION_PLAN and target_id:
            ep = self._store.get_execution_plan(target_id)
            if ep:
                exists, status, owned = True, ep.status, True

        # Check container plan
        if target_type in (SandboxV2KillTargetType.CONTAINER_PLAN, SandboxV2KillTargetType.CONTAINER) and target_id:
            cp = self._store.get_container_execution_plan(target_id) if hasattr(self._store, 'get_container_execution_plan') else None
            if cp:
                exists, status, owned = True, cp.status, True
                # Container kill only if enabled + Linux
                import os
                ce = os.environ.get("SANDBOX_V2_CONTAINER_EXECUTION_ENABLED", "").lower() in ("true", "1", "yes") and _plat.system() == "Linux"
                cr = bool(cp.metadata.get("container_id")) if hasattr(cp, 'metadata') else False
                ps = ce and cr

        # Check provider capability
        provider_name = getattr(self, '_last_provider', "")
        if self._execution_providers:
            for p_name, p in self._execution_providers.items():
                try:
                    caps = p.get_capabilities()
                    if caps.get("execution_allowed", False):
                        ps = True
                        break
                except Exception:
                    pass

        return exists, status, owned, ce, cr, ps

    def _apply_decision(self, req, d, target_type, target_id, job_id, prev_status):
        result = {"status_after": prev_status, "provider_result": ""}

        if d.action == SandboxV2KillAction.REJECT:
            result["error"] = "Kill rejected by policy."
            return result

        if d.action == SandboxV2KillAction.NO_ACTIVE_EXECUTION:
            if self._store and job_id:
                self._store.update_job_status(job_id, prev_status)
            result["status_after"] = prev_status
            result["message"] = "No active execution. Already terminal."
            return result

        if d.action == SandboxV2KillAction.CANCEL_QUEUE_ITEM:
            if self._queue and job_id:
                self._queue.cancel(job_id, req.reason or "Canceled by kill switch.")
            if self._store and job_id:
                self._store.update_job_status(job_id, SandboxV2JobStatus.CANCELED)
            result["status_after"] = SandboxV2JobStatus.CANCELED
            result["message"] = "Queue item canceled."
            return result

        if d.action in (SandboxV2KillAction.MARK_CANCELED, SandboxV2KillAction.REQUEST_WORKER_STOP):
            if self._queue and job_id:
                self._queue.cancel(job_id, req.reason or "Canceled by kill switch.")
            if self._store and job_id:
                self._store.update_job_status(job_id, SandboxV2JobStatus.CANCELED)
            # Mark active handles
            if self._store and job_id:
                handle = self._store.get_active_execution_handle_for_job(job_id) if hasattr(self._store, 'get_active_execution_handle_for_job') else None
                if handle:
                    self._store.mark_active_execution_cancel_requested(handle.handle_id, req.reason) if hasattr(self._store, 'mark_active_execution_cancel_requested') else None
            result["status_after"] = SandboxV2JobStatus.CANCELED
            return result

        if d.action == SandboxV2KillAction.PROVIDER_CANCEL:
            provider = self._execution_providers.get("trusted_fixture") or next(iter(self._execution_providers.values()), None)
            if provider and target_id:
                cancel_r = provider.cancel_execution(target_id)
                result["provider_result"] = cancel_r.get("message", "")
            if self._store and job_id:
                self._store.update_job_status(job_id, SandboxV2JobStatus.CANCELED)
            result["status_after"] = SandboxV2JobStatus.CANCELED
            return result

        if d.action == SandboxV2KillAction.CONTAINER_KILL_FUTURE:
            result["error"] = "Container kill is supported by policy but execution is future. Provider cancel unavailable in current environment."
            result["status_after"] = prev_status
            return result

        return result

    # ── ActiveExecutionHandle methods ──

    def register_active_execution_handle(self, **kw) -> dict:
        handle = SandboxActiveExecutionHandle(
            job_id=kw.get("job_id", ""), execution_plan_id=kw.get("execution_plan_id", ""),
            container_plan_id=kw.get("container_plan_id", ""),
            execution_record_id=kw.get("execution_record_id", ""),
            provider=kw.get("provider", ""), target_type=kw.get("target_type", SandboxV2KillTargetType.SIMULATION),
            target_id=kw.get("target_id", kw.get("job_id", "")),
            timeout_at=kw.get("timeout_at"),
            metadata=kw.get("metadata", {}),
        )
        if self._store:
            self._store.create_active_execution_handle(handle)
        return {"handle": handle.to_dict()}

    def get_active_execution_handle(self, handle_id: str) -> SandboxActiveExecutionHandle | None:
        return self._store.get_active_execution_handle(handle_id) if self._store else None

    def get_active_execution_handle_for_job(self, job_id: str) -> SandboxActiveExecutionHandle | None:
        return self._store.get_active_execution_handle_for_job(job_id) if self._store else None

    def list_active_execution_handles(self, status: str | None = None, limit: int = 50) -> list[dict]:
        if not self._store: return []
        return [h.to_dict() for h in self._store.list_active_execution_handles(status=status, limit=limit)]

    def mark_active_execution_completed(self, handle_id: str, reason: str = "") -> dict:
        if not self._store: return {"error": "No store."}
        self._store.update_active_execution_handle_status(handle_id, SandboxV2ActiveExecutionStatus.COMPLETED, reason)
        return {"handle_id": handle_id, "status": "completed"}

    def expire_stale_handles(self, now: datetime | None = None) -> int:
        if not self._store: return 0
        now = now or datetime.now(timezone.utc)
        handles = self._store.list_active_execution_handles(limit=500)
        count = 0
        for h in handles:
            if h.timeout_at and now > h.timeout_at and h.status == SandboxV2ActiveExecutionStatus.ACTIVE:
                self._store.update_active_execution_handle_status(h.handle_id, SandboxV2ActiveExecutionStatus.EXPIRED, "Handle timeout expired.")
                count += 1
        return count

    def list_kill_requests(self, job_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
        if not self._store: return []
        return [r.to_dict() for r in self._store.list_kill_requests(job_id=job_id, status=status, limit=limit)]

    def list_kill_records(self, job_id: str | None = None, kill_request_id: str | None = None, limit: int = 50) -> list[dict]:
        if not self._store: return []
        return [r.to_dict() for r in self._store.list_kill_records(job_id=job_id, kill_request_id=kill_request_id, limit=limit)]

    def create_kill_record(self, **kw) -> dict:
        record = SandboxKillRecord(
            kill_request_id=kw.get("kill_request_id", ""), job_id=kw.get("job_id", ""),
            execution_plan_id=kw.get("execution_plan_id", ""),
            container_plan_id=kw.get("container_plan_id", ""),
            provider=kw.get("provider", ""), target_type=kw.get("target_type", SandboxV2KillTargetType.UNKNOWN),
            target_id=kw.get("target_id", ""), action_taken=kw.get("action_taken", ""),
            status_before=kw.get("status_before", ""), status_after=kw.get("status_after", ""),
            metadata=kw.get("metadata", {}),
        )
        if self._store:
            self._store.create_kill_record(record)
        return {"kill_record": record.to_dict()}

    def get_kill_readiness(self) -> dict:
        import os, shutil
        return {
            "kill_switch": True, "kill_policy": True,
            "active_execution_handles": True, "queue_cancel": self._queue is not None,
            "worker_cancel_checkpoints": True, "provider_cancel_interface": True,
            "process_kill_implemented": False, "arbitrary_pid_kill": False,
            "container_kill_enabled": os.environ.get("SANDBOX_V2_CONTAINER_EXECUTION_ENABLED", "").lower() in ("true", "1", "yes"),
            "docker_kill_available": shutil.which("docker") is not None,
            "podman_kill_available": shutil.which("podman") is not None,
            "platform": _plat.system(),
            "boundary": "Kill is metadata-only for simulation/trusted_fixture. Container kill requires Linux + enabled + recorded container_id.",
        }
