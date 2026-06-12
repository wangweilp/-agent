"""Sandbox Worker Queue Service — disabled-by-default, metadata-only. No real queue. No enqueue/dispatch/worker."""
from __future__ import annotations
import logging
from typing import Any
from .sandbox_worker_queue import *

logger = logging.getLogger(__name__)

class SandboxWorkerQueueService:
    def __init__(self, store=None, execution_store=None, usage_store=None):
        self._store = store; self._execution_store = execution_store; self._usage_store = usage_store

    def create_disabled_queue_record(self, *, execution_record=None, plan=None, gate_result=None,
        extraction_plan=None, adapter_descriptor=None, policy_config_snapshot=None,
        worker_request_snapshot=None, requested_by=None, metadata=None) -> SandboxWorkerQueueRecord:
        if self._store is None: raise ValueError("store not available")
        rec = SandboxWorkerQueueRecord(
            execution_id=getattr(execution_record,"execution_id",None) if execution_record else None,
            plan_id=getattr(plan,"plan_id",None) if plan else None,
            gate_id=getattr(gate_result,"gate_id",None) if gate_result else None,
            artifact_id=getattr(plan,"artifact_id",None) if plan else None,
            extraction_plan_id=getattr(extraction_plan,"plan_id",None) if extraction_plan else None,
            marketplace_agent_id=getattr(plan,"marketplace_agent_id",None) if plan else None,
            tenant_id=getattr(plan,"tenant_id","") if plan else "",
            developer_id=getattr(plan,"developer_id",None) if plan else None,
            requested_by=requested_by,
            worker_type=getattr(adapter_descriptor,"technology",None) if adapter_descriptor else None,
            queue_mode=SandboxWorkerQueueMode.DISABLED,
            queue_status=SandboxWorkerQueueStatus.QUEUE_DISABLED,
            decision=SandboxWorkerQueueDecision.BLOCKED_DISABLED,
            lease_status=SandboxWorkerLeaseStatus.LEASE_DISABLED,
            dispatch_status=SandboxWorkerDispatchStatus.DISPATCH_DISABLED,
            execution_snapshot=self._snap(execution_record),
            plan_snapshot=self._snap(plan),
            gate_snapshot=self._snap(gate_result),
            extraction_plan_snapshot=self._snap(extraction_plan),
            adapter_descriptor_snapshot=self._snap(adapter_descriptor),
            policy_config_snapshot=policy_config_snapshot or {},
            worker_request_snapshot=worker_request_snapshot or {},
        )
        created = self._store.create_queue_record(rec)
        self._try_usage(created, requested_by)
        return created

    def evaluate_queue_gate(self, queue_record_id: str) -> SandboxWorkerQueueGateResult:
        if self._store is None: raise ValueError("store not available")
        rec = self._store.get_queue_record(queue_record_id)
        if rec is None: raise SandboxWorkerQueueRecordNotFoundError(f"Not found: {queue_record_id}")
        gate = SandboxWorkerQueueGateResult(queue_record_id=queue_record_id, tenant_id=rec.tenant_id,
            decision=SandboxWorkerQueueDecision.BLOCKED_DISABLED,
            queue_status=rec.queue_status, lease_status=rec.lease_status, dispatch_status=rec.dispatch_status,
            checks=[{"type":"queue_disabled_check","status":"passed_rejected","message":"Queue is DISABLED — no enqueue/dispatch allowed."},
                    {"type":"enqueue_check","status":"rejected","message":"Enqueue is DISABLED."},
                    {"type":"dispatch_check","status":"rejected","message":"Dispatch is DISABLED."},
                    {"type":"worker_check","status":"rejected","message":"Worker start is DISABLED."},
                    {"type":"execution_check","status":"rejected","message":"Execution is DISABLED."},
                    {"type":"no_queue_created","status":"passed","message":"No real queue was created."},
                    {"type":"no_job_enqueued","status":"passed","message":"No job was enqueued."},
                    {"type":"no_job_dispatched","status":"passed","message":"No job was dispatched."}])
        if self._store: self._store.create_gate_result(gate)
        return gate

    def cancel_queue_record(self, rid, actor=None): return self._store.cancel_queue_record(rid, actor) if self._store else None
    def expire_queue_record(self, rid, actor=None): return self._store.expire_queue_record(rid, actor) if self._store else None

    def _snap(self, obj):
        if obj is None: return {}
        if isinstance(obj, dict): return dict(obj)
        if hasattr(obj,"to_dict") and callable(obj.to_dict): return obj.to_dict()
        return {}

    def _try_usage(self, rec, actor_id):
        if self._usage_store is None: return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            self._usage_store.record_event(UsageEvent(tenant_id=rec.tenant_id, user_id=actor_id or "", workspace_id=rec.tenant_id,
                resource=UsageResource.SANDBOX_WORKER_QUEUE_RECORD_CREATE, quantity=1, unit=UsageUnit.COUNT,
                metadata={"queue_record_id":rec.queue_record_id,"execution_id":rec.execution_id,"plan_id":rec.plan_id,
                "tenant_id":rec.tenant_id,"queue_status":rec.queue_status,"decision":rec.decision,
                "lease_status":rec.lease_status,"dispatch_status":rec.dispatch_status,"queue_enabled":False,
                "enqueue_enabled":False,"dispatch_enabled":False,"worker_enabled":False,"no_queue_created":True,
                "no_job_enqueued":True,"no_job_dispatched":True,"no_worker_started":True,"no_execution_performed":True}))
        except Exception: logger.warning("swq_usage_failed", exc_info=True)
