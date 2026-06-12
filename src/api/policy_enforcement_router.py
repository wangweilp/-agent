"""Policy Enforcement API Router — metadata-only, all decisions = deny."""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from src.api.middleware import require_auth, TokenPayload
from src.core.usage import UsageEvent, UsageResource, UsageUnit

logger = logging.getLogger(__name__)


def create_policy_enforcement_router(service=None, usage_store=None) -> APIRouter:
    router = APIRouter(prefix="/api/runtime/policy-decisions", tags=["Policy Enforcement"])

    def _admin(payload: TokenPayload = Depends(require_auth)):
        if payload.is_super_admin: return payload
        if payload.role and payload.role.value in ("owner", "admin", "org_admin", "super_admin"): return payload
        raise HTTPException(status_code=403, detail="Admin required")

    def _try_usage(tenant_id, user_id, resource, metadata=None):
        if usage_store is None: return
        try:
            usage_store.record_event(UsageEvent(tenant_id=tenant_id, user_id=user_id, workspace_id=tenant_id,
                resource=resource, quantity=1, unit=UsageUnit.COUNT, metadata=metadata or {}))
        except Exception: logger.warning("penf_api_usage_failed", exc_info=True)

    @router.get("")
    async def list_decisions(request_type: str = Query(""),
                             payload: TokenPayload = Depends(_admin)):
        _try_usage(payload.tenant_id or "", payload.user_id, UsageResource.POLICY_ENFORCEMENT_DECISION,
                   metadata={"action": "list", "metadata_only": True})
        decisions = service.list_decisions(request_type=request_type)
        return {"decisions": [d.to_dict() for d in decisions], "total": len(decisions)}

    @router.get("/export")
    async def export_decisions(payload: TokenPayload = Depends(_admin)):
        _try_usage(payload.tenant_id or "", payload.user_id, UsageResource.POLICY_ENFORCEMENT_AUDIT,
                   metadata={"action": "export", "metadata_only": True})
        return service.export_decisions()

    @router.get("/audit")
    async def run_audit(payload: TokenPayload = Depends(_admin)):
        _try_usage(payload.tenant_id or "", payload.user_id, UsageResource.POLICY_ENFORCEMENT_AUDIT,
                   metadata={"action": "audit", "metadata_only": True})
        return service.run_audit()

    @router.get("/{decision_id}")
    async def get_decision(decision_id: str, payload: TokenPayload = Depends(_admin)):
        _try_usage(payload.tenant_id or "", payload.user_id, UsageResource.POLICY_ENFORCEMENT_DECISION,
                   metadata={"action": "get", "decision_id": decision_id, "metadata_only": True})
        return service.get_decision(decision_id).to_dict()

    return router
