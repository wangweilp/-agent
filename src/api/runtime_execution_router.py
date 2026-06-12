"""Runtime Execution API Router — admin gated, execution disabled。
Step 24-H: create/list/cancel/expire plans, policy/worker preview, execute draft (blocked).
不执行/不dispatch/不worker/不queue。"""

from __future__ import annotations
import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.middleware import require_auth, TokenPayload
from src.core.usage import UsageEvent, UsageResource, UsageUnit

logger = logging.getLogger(__name__)

def _is_admin(payload: TokenPayload) -> bool:
    if payload.is_super_admin: return True
    if payload.role and payload.role.value in ("owner","admin","org_admin","super_admin"): return True
    return False

def _require_admin(payload: TokenPayload = Depends(require_auth)) -> TokenPayload:
    if not _is_admin(payload): raise HTTPException(status_code=403, detail="需要 admin 或以上角色")
    return payload

def _try_usage(usage_store, tenant_id, user_id, resource, metadata=None):
    if usage_store is None: return
    try: usage_store.record_event(UsageEvent(tenant_id=tenant_id, user_id=user_id, workspace_id=tenant_id,
        resource=resource, quantity=1, unit=UsageUnit.COUNT, metadata=metadata or {}))
    except Exception: logger.warning("runtime_exec_usage_failed", exc_info=True)

class CreatePlanRequest(BaseModel):
    marketplace_agent_id: str = Field(..., min_length=1)
    user_id: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    execution_mode: str = Field(default="sandbox_reserved")

NON_EXEC = ["no_package_download","no_package_execution","no_entrypoint_execution",
    "no_network_used","no_subprocess_used","no_container_used","no_queue_created",
    "no_job_dispatched","no_agent_runtime_used","no_agent_registry_used",
    "is_dispatchable_always_false","is_execution_allowed_always_false","step_24h_draft_api_only"]

def create_runtime_execution_router(
    plan_store, planner_service, *, marketplace_store=None, runtime_store=None,
    sandbox_policy_store=None, artifact_store=None, verification_store=None,
    policy_translator=None, worker_registry=None, usage_store=None,
) -> APIRouter:
    from src.open_platform.runtime_execution_plan import RuntimeExecutionMode
    from src.open_platform.runtime_execution_gate import (
        RuntimeExecutionGateCheck, RuntimeExecutionGateCheckStatus,
        RuntimeExecutionGateCheckType, RuntimeExecutionGateSeverity,
        RuntimeExecutionGateResult, RuntimeExecutionGateStatus,
        RuntimeExecutionGateDecision, RuntimeExecutionApiMode,
    )
    from src.open_platform.sandbox_worker import (
        build_worker_request_from_plan, SandboxWorkerType,
    )

    def _sql_gate(mode, status, decision, mkp=None, tid=None, actor=None, plan_id=None):
        g = RuntimeExecutionGateResult(mode=mode, status=status, decision=decision,
            marketplace_agent_id=mkp, tenant_id=tid, actor_id=actor, plan_id=plan_id)
        for (ct, msg) in [
            (RuntimeExecutionGateCheckType.NO_PACKAGE_DOWNLOAD, "No package download."),
            (RuntimeExecutionGateCheckType.NO_PACKAGE_EXECUTION, "No package execution."),
            (RuntimeExecutionGateCheckType.NO_ENTRYPOINT_EXECUTION, "No entrypoint execution."),
            (RuntimeExecutionGateCheckType.NO_NETWORK_USED, "No network used."),
            (RuntimeExecutionGateCheckType.NO_SUBPROCESS_USED, "No subprocess."),
            (RuntimeExecutionGateCheckType.NO_CONTAINER_USED, "No container."),
            (RuntimeExecutionGateCheckType.NO_QUEUE_CREATED, "No queue created."),
            (RuntimeExecutionGateCheckType.NO_JOB_DISPATCHED, "No job dispatched."),
            (RuntimeExecutionGateCheckType.NO_AGENT_RUNTIME_USED, "AgentRuntime not called."),
            (RuntimeExecutionGateCheckType.NO_AGENT_REGISTRY_USED, "AgentRegistry not called."),
            (RuntimeExecutionGateCheckType.FAIL_CLOSED, "Fail-closed safety net active."),
        ]:
            g.add_check(RuntimeExecutionGateCheck(check_type=ct,
                status=RuntimeExecutionGateCheckStatus.PASSED, severity=RuntimeExecutionGateSeverity.INFO, message=msg))
        g.calculate_status(); return g

    admin_r = APIRouter(prefix="/admin/runtime/execution-plans", tags=["admin-runtime-execution"])

    @admin_r.post("")
    async def create_plan(body: CreatePlanRequest, payload: TokenPayload = Depends(_require_admin)) -> dict:
        tn = payload.workspace_id
        try:
            plan = planner_service.create_plan(marketplace_agent_id=body.marketplace_agent_id,
                tenant_id=tn, requested_by=payload.user_id, user_id=body.user_id,
                input_payload=body.input_payload if body.input_payload else None,
                execution_mode=body.execution_mode)
        except ValueError as e: raise HTTPException(status_code=400, detail=str(e))
        gate = _sql_gate(RuntimeExecutionApiMode.ADMIN_PLAN_ONLY, RuntimeExecutionGateStatus.PLAN_ONLY,
            RuntimeExecutionGateDecision.PLAN_CREATED, mkp=body.marketplace_agent_id, tid=tn,
            actor=payload.user_id, plan_id=plan.plan_id)
        gate.add_check(RuntimeExecutionGateCheck(check_type=RuntimeExecutionGateCheckType.PLAN_CREATED_ONLY,
            status=RuntimeExecutionGateCheckStatus.PASSED, severity=RuntimeExecutionGateSeverity.INFO,
            message=f"Plan {plan.plan_id} created. dispatch_status={plan.dispatch_status}"))
        gate.add_check(RuntimeExecutionGateCheck(check_type=RuntimeExecutionGateCheckType.PLAN_NOT_DISPATCHABLE,
            status=RuntimeExecutionGateCheckStatus.PASSED, severity=RuntimeExecutionGateSeverity.INFO,
            message=f"Plan not dispatchable.")); gate.calculate_status()
        _try_usage(usage_store, tn, payload.user_id, UsageResource.RUNTIME_EXECUTION_PLAN_API_CREATE,
            {"plan_id": plan.plan_id, "marketplace_agent_id": body.marketplace_agent_id, "no_execution_performed": True})
        logger.info("runtime_execution_plan_created", extra={"plan_id": plan.plan_id, "tenant_id": tn})
        return {"plan": plan.to_dict(), "gate": gate.to_dict(), "non_execution_guarantees": NON_EXEC}

    @admin_r.get("")
    async def list_plans(tenant_id: str = Query(default=""), marketplace_agent_id: str = Query(default=""),
                         developer_id: str = Query(default=""), status: str = Query(default=""),
                         decision: str = Query(default=""),
                         payload: TokenPayload = Depends(_require_admin)) -> dict:
        tn = tenant_id if tenant_id and payload.is_super_admin else payload.workspace_id
        plans = plan_store.list_plans(tenant_id=tn, marketplace_agent_id=marketplace_agent_id,
            developer_id=developer_id, status=status, decision=decision)
        return {"plans": [p.to_dict() for p in plans], "total": len(plans), "non_execution_guarantees": NON_EXEC}

    @admin_r.get("/{plan_id}")
    async def get_plan(plan_id: str, payload: TokenPayload = Depends(_require_admin)) -> dict:
        plan = plan_store.get_plan(plan_id)
        if plan is None: raise HTTPException(status_code=404, detail="Plan not found")
        if not payload.is_super_admin and plan.tenant_id != payload.workspace_id: raise HTTPException(status_code=404)
        audits = plan_store.list_audit_events(plan_id)
        return {"plan": plan.to_dict(), "audit_events": [a.to_dict() for a in audits], "non_execution_guarantees": NON_EXEC}

    @admin_r.post("/{plan_id}/cancel")
    async def cancel_plan(plan_id: str, payload: TokenPayload = Depends(_require_admin)) -> dict:
        plan = plan_store.get_plan(plan_id)
        if plan is None: raise HTTPException(status_code=404, detail="Plan not found")
        if not payload.is_super_admin and plan.tenant_id != payload.workspace_id: raise HTTPException(status_code=404)
        updated = plan_store.cancel_plan(plan_id, payload.user_id, "cancelled by admin")
        _try_usage(usage_store, plan.tenant_id, payload.user_id, UsageResource.RUNTIME_EXECUTION_PLAN_CANCEL, {"plan_id": plan_id})
        return {"plan": updated.to_dict(), "message": "Plan cancelled. No job dispatched.", "non_execution_guarantees": NON_EXEC}

    @admin_r.post("/{plan_id}/expire")
    async def expire_plan(plan_id: str, payload: TokenPayload = Depends(_require_admin)) -> dict:
        plan = plan_store.get_plan(plan_id)
        if plan is None: raise HTTPException(status_code=404, detail="Plan not found")
        if not payload.is_super_admin and plan.tenant_id != payload.workspace_id: raise HTTPException(status_code=404)
        updated = plan_store.expire_plan(plan_id, None, "expired by admin")
        return {"plan": updated.to_dict(), "message": "Plan expired. No job dispatched.", "non_execution_guarantees": NON_EXEC}

    @admin_r.post("/{plan_id}/policy-preview")
    async def policy_preview(plan_id: str, payload: TokenPayload = Depends(_require_admin)) -> dict:
        plan = plan_store.get_plan(plan_id)
        if plan is None: raise HTTPException(status_code=404, detail="Plan not found")
        if not payload.is_super_admin and plan.tenant_id != payload.workspace_id: raise HTTPException(status_code=404)
        if policy_translator is None: raise HTTPException(status_code=501, detail="Policy translator not available")
        if sandbox_policy_store is None or plan.sandbox_policy_id is None: raise HTTPException(status_code=400, detail="No sandbox policy")
        pol = sandbox_policy_store.get_policy(plan.sandbox_policy_id)
        if pol is None: raise HTTPException(status_code=404, detail="Sandbox policy not found")
        result = policy_translator.translate_policy(pol)
        _try_usage(usage_store, plan.tenant_id, payload.user_id, UsageResource.RUNTIME_EXECUTION_POLICY_PREVIEW, {"plan_id": plan_id})
        return {"translation": result.to_dict(), "non_execution_guarantees": NON_EXEC}

    class WorkerPreviewReq(BaseModel): mode: str = Field(default="disabled_only")

    @admin_r.post("/{plan_id}/worker-preview")
    async def worker_preview(plan_id: str, body: WorkerPreviewReq = WorkerPreviewReq(),
                             payload: TokenPayload = Depends(_require_admin)) -> dict:
        plan = plan_store.get_plan(plan_id)
        if plan is None: raise HTTPException(status_code=404, detail="Plan not found")
        if not payload.is_super_admin and plan.tenant_id != payload.workspace_id: raise HTTPException(status_code=404)
        if worker_registry is None: raise HTTPException(status_code=501, detail="Worker registry not available")
        wtype = SandboxWorkerType.LOCAL_DEV_DRY_RUN if body.mode == "local_dev_dry_run" else SandboxWorkerType.DISABLED_STUB
        req = build_worker_request_from_plan(plan, requested_by=payload.user_id, worker_type=wtype)
        if policy_translator and sandbox_policy_store and plan.sandbox_policy_id:
            pol = sandbox_policy_store.get_policy(plan.sandbox_policy_id)
            if pol:
                pr = policy_translator.translate_policy(pol)
                from src.open_platform.policy_enforcement import build_policy_config_snapshot
                req.policy_config_snapshot = build_policy_config_snapshot(pr)
        worker = worker_registry.get(req.worker_type) or worker_registry.get_default()
        result = worker.evaluate_request(req)
        gate = _sql_gate(RuntimeExecutionApiMode.ADMIN_PREVIEW_ONLY, RuntimeExecutionGateStatus.PLAN_ONLY,
            RuntimeExecutionGateDecision.PREVIEW_ONLY, mkp=plan.marketplace_agent_id, tid=plan.tenant_id,
            actor=payload.user_id, plan_id=plan_id)
        gate.add_check(RuntimeExecutionGateCheck(check_type=RuntimeExecutionGateCheckType.WORKER_DISABLED,
            status=RuntimeExecutionGateCheckStatus.PASSED if result.status=="blocked" else RuntimeExecutionGateCheckStatus.WARNING,
            severity=RuntimeExecutionGateSeverity.INFO, message=f"Worker={req.worker_type}, avail={result.availability}")); gate.calculate_status()
        _try_usage(usage_store, plan.tenant_id, payload.user_id, UsageResource.RUNTIME_EXECUTION_WORKER_PREVIEW, {"plan_id": plan_id})
        return {"worker_result": result.to_dict(), "gate": gate.to_dict(), "non_execution_guarantees": NON_EXEC}

    # ══════ Runtime execute draft — ALWAYS BLOCKED ══════

    public_r = APIRouter(prefix="/runtime/agents", tags=["runtime-execute-draft"])

    @public_r.post("/{marketplace_agent_id}/execute")
    async def runtime_execute_draft(marketplace_agent_id: str,
        payload: TokenPayload | None = Depends(require_auth)) -> dict:
        tn = payload.workspace_id if payload else ""
        gate = RuntimeExecutionGateResult(mode=RuntimeExecutionApiMode.USER_EXECUTE_DISABLED,
            status=RuntimeExecutionGateStatus.DISABLED, decision=RuntimeExecutionGateDecision.BLOCKED_DISABLED,
            marketplace_agent_id=marketplace_agent_id, tenant_id=tn, actor_id=payload.user_id if payload else None)
        gate.add_check(RuntimeExecutionGateCheck(check_type=RuntimeExecutionGateCheckType.USER_EXECUTE_DISABLED,
            status=RuntimeExecutionGateCheckStatus.BLOCKED, severity=RuntimeExecutionGateSeverity.BLOCKER,
            message="Runtime execution API is draft-only and disabled in Step 24-H."))
        for (ct, msg) in [
            (RuntimeExecutionGateCheckType.NO_PACKAGE_DOWNLOAD, "No package download."),
            (RuntimeExecutionGateCheckType.NO_PACKAGE_EXECUTION, "No package execution."),
            (RuntimeExecutionGateCheckType.NO_ENTRYPOINT_EXECUTION, "No entrypoint execution."),
            (RuntimeExecutionGateCheckType.NO_NETWORK_USED, "No network."),
            (RuntimeExecutionGateCheckType.NO_SUBPROCESS_USED, "No subprocess."),
            (RuntimeExecutionGateCheckType.NO_CONTAINER_USED, "No container."),
            (RuntimeExecutionGateCheckType.NO_AGENT_RUNTIME_USED, "AgentRuntime not called."),
            (RuntimeExecutionGateCheckType.NO_AGENT_REGISTRY_USED, "AgentRegistry not called."),
            (RuntimeExecutionGateCheckType.FAIL_CLOSED, "Fail-closed: execution refused."),
        ]:
            gate.add_check(RuntimeExecutionGateCheck(check_type=ct,
                status=RuntimeExecutionGateCheckStatus.PASSED, severity=RuntimeExecutionGateSeverity.INFO, message=msg))
        gate.calculate_status()
        _try_usage(usage_store, tn, payload.user_id if payload else "", UsageResource.RUNTIME_EXECUTION_DRAFT_BLOCKED, {"marketplace_agent_id": marketplace_agent_id})
        return {"status": "blocked", "message": "Runtime execution API is draft-only and disabled in Step 24-H.",
                "gate": gate.to_dict(), "non_execution_guarantees": NON_EXEC}

    # Merge routes
    router = APIRouter()
    for r in admin_r.routes: router.routes.append(r)
    for r in public_r.routes: router.routes.append(r)
    return router
