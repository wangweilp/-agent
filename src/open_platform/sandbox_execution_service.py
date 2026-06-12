"""SandboxExecutionRecordService — audit-only execution record builder。Step 25-B: no queue/dispatch/execute。"""
from __future__ import annotations
import logging, json
from datetime import datetime, timezone
from typing import Any
from src.open_platform.sandbox_execution import (
    SandboxExecutionRecord, SandboxExecutionStatus, SandboxExecutionDecision,
    SandboxExecutionQueueStatus, SandboxExecutionRiskLevel, SandboxExecutionAuditEventType,
)

logger = logging.getLogger(__name__)

class SandboxExecutionRecordService:
    def __init__(self, execution_store=None, plan_store=None, usage_store=None):
        self._execution_store = execution_store
        self._plan_store = plan_store
        self._usage_store = usage_store

    def create_audit_only_execution_from_plan(
        self, plan, *, gate_result=None, worker_request=None,
        policy_config_snapshot: dict | None = None, created_by: str | None = None,
    ) -> SandboxExecutionRecord:
        if self._execution_store is None: raise ValueError("execution_store not available")

        rec = SandboxExecutionRecord(
            plan_id=getattr(plan,"plan_id",""),
            gate_id=getattr(gate_result,"gate_id",None) if gate_result else None,
            marketplace_agent_id=getattr(plan,"marketplace_agent_id",""),
            tenant_id=getattr(plan,"tenant_id",""),
            user_id=getattr(plan,"user_id",None),
            developer_id=getattr(plan,"developer_id",""),
            submission_id=getattr(plan,"submission_id",None),
            artifact_id=getattr(plan,"artifact_id",None),
            verification_id=getattr(plan,"verification_id",None),
            sandbox_policy_id=getattr(plan,"sandbox_policy_id",None),
            runtime_binding_id=getattr(plan,"runtime_binding_id",None),
            worker_type=getattr(worker_request,"worker_type",None) if worker_request else None,
            execution_status=SandboxExecutionStatus.AUDIT_ONLY,
            decision=SandboxExecutionDecision.AUDIT_ONLY,
            queue_status=SandboxExecutionQueueStatus.QUEUE_DISABLED,
            risk_level=getattr(plan,"risk_level",SandboxExecutionRiskLevel.UNKNOWN),
            input_payload_hash=getattr(plan,"input_payload_hash",None),
            plan_snapshot=self._snap(plan),
            gate_snapshot=self._snap(gate_result),
            policy_config_snapshot=policy_config_snapshot or {},
            artifact_snapshot=self._snap_dict(getattr(plan,"artifact_snapshot",{})),
            verification_snapshot=self._snap_dict(getattr(plan,"verification_snapshot",{})),
            worker_request_snapshot=self._snap(worker_request),
            no_execution_performed=True, no_download_used=True, no_network_used=True,
            no_subprocess_used=True, no_container_used=True, no_queue_created=True,
            no_job_dispatched=True, no_agent_runtime_used=True, no_agent_registry_used=True,
            created_by=created_by,
        )
        created = self._execution_store.create_execution(rec)
        self._try_usage(created, created_by)
        logger.info("sandbox_execution_record_created", extra={"execution_id": created.execution_id})
        return created

    def _snap(self, obj) -> dict:
        if obj is None: return {}
        if isinstance(obj, dict): return dict(obj)
        if hasattr(obj,"to_dict") and callable(obj.to_dict): return obj.to_dict()
        return {}

    def _snap_dict(self, obj) -> dict:
        if obj is None: return {}
        if isinstance(obj, dict): return dict(obj)
        return {}

    def _try_usage(self, rec: SandboxExecutionRecord, actor_id: str | None):
        if self._usage_store is None: return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            self._usage_store.record_event(UsageEvent(
                tenant_id=rec.tenant_id, user_id=actor_id or "", workspace_id=rec.tenant_id,
                resource=UsageResource.SANDBOX_EXECUTION_RECORD_CREATE, quantity=1, unit=UsageUnit.COUNT,
                metadata={"execution_id":rec.execution_id,"plan_id":rec.plan_id,
                    "marketplace_agent_id":rec.marketplace_agent_id,"tenant_id":rec.tenant_id,
                    "developer_id":rec.developer_id,"execution_status":rec.execution_status,
                    "decision":rec.decision,"queue_status":rec.queue_status,
                    "risk_level":rec.risk_level,"no_execution_performed":True,
                    "no_download_used":True,"no_network_used":True,"no_queue_created":True,
                    "no_job_dispatched":True,"no_agent_runtime_used":True,"no_agent_registry_used":True}))
        except Exception: logger.warning("sbx_exec_usage_failed", exc_info=True)
