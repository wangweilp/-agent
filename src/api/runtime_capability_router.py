"""Runtime Capability API Router — metadata registry, no execution, no runtime."""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from src.api.middleware import require_auth, TokenPayload
from src.core.usage import UsageEvent, UsageResource, UsageUnit

logger = logging.getLogger(__name__)


class CapabilityUpdateRequest(BaseModel):
    status: str | None = None
    reason: str | None = None


def create_runtime_capability_router(capability_service=None, usage_store=None) -> APIRouter:
    router = APIRouter(prefix="/api/runtime/capabilities", tags=["Runtime Capabilities"])

    def _admin(payload: TokenPayload = Depends(require_auth)):
        if payload.is_super_admin: return payload
        if payload.role and payload.role.value in ("owner", "admin", "org_admin", "super_admin"): return payload
        raise HTTPException(status_code=403, detail="Admin required")

    def _try_usage(tenant_id, user_id, resource, metadata=None):
        if usage_store is None: return
        try:
            usage_store.record_event(UsageEvent(tenant_id=tenant_id, user_id=user_id, workspace_id=tenant_id,
                resource=resource, quantity=1, unit=UsageUnit.COUNT, metadata=metadata or {}))
        except Exception: logger.warning("rtcap_api_usage_failed", exc_info=True)

    @router.get("")
    async def list_capabilities(
        category: str = Query("", description="Filter by category"),
        status: str = Query("", description="Filter by status"),
        payload: TokenPayload = Depends(_admin)):
        _try_usage(payload.tenant_id or "", payload.user_id, UsageResource.RUNTIME_CAPABILITY_ACCESS,
                   metadata={"action": "list", "metadata_only": True})
        caps = capability_service.list_capabilities(category=category, status=status)
        return {"capabilities": [c.to_dict() for c in caps], "total": len(caps)}

    @router.get("/export")
    async def export_matrix(payload: TokenPayload = Depends(_admin)):
        _try_usage(payload.tenant_id or "", payload.user_id, UsageResource.RUNTIME_CAPABILITY_MATRIX_EXPORT,
                   metadata={"action": "export", "metadata_only": True})
        return capability_service.export_matrix()

    @router.get("/{capability_id}")
    async def get_capability(capability_id: str, payload: TokenPayload = Depends(_admin)):
        _try_usage(payload.tenant_id or "", payload.user_id, UsageResource.RUNTIME_CAPABILITY_ACCESS,
                   metadata={"action": "get", "capability_id": capability_id, "metadata_only": True})
        return capability_service.get_capability(capability_id).to_dict()

    @router.patch("/{capability_id}")
    async def update_capability(capability_id: str, body: CapabilityUpdateRequest,
                                payload: TokenPayload = Depends(_admin)):
        _try_usage(payload.tenant_id or "", payload.user_id, UsageResource.RUNTIME_CAPABILITY_ACCESS,
                   metadata={"action": "update", "capability_id": capability_id, "metadata_only": True})
        return capability_service.update_capability(capability_id, body.status, body.reason).to_dict()

    return router
