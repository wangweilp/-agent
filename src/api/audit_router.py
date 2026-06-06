"""
Audit router — audit logs, summaries, user activity timelines, export.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .middleware import require_auth, require_manage


# ── Pydantic models (matching core domain objects) ──


class AuditLogOut(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    action: str
    resource_type: str
    resource_id: str
    detail: str = ""
    timestamp: str

    class Config:
        from_attributes = True


class AuditSummaryOut(BaseModel):
    workspace_id: str
    last_24h: dict[str, int]
    last_7d: dict[str, int]
    last_30d: dict[str, int]
    total: int

    class Config:
        from_attributes = True


class UserActivityOut(BaseModel):
    user_id: str
    workspace_id: str
    daily_actions: list[dict]
    top_actions: list[dict]
    total_actions: int

    class Config:
        from_attributes = True


# ── Factory ──

def create_audit_router(collab_store) -> APIRouter:
    router = APIRouter(prefix="/api/audit", tags=["Audit"])

    def _log_to_dict(log) -> dict:
        """Convert AuditLog to dict matching AuditLogOut."""
        return {
            "id": log.id,
            "workspace_id": log.workspace_id,
            "user_id": log.user_id,
            "action": log.action.value if hasattr(log.action, "value") else str(log.action),
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "detail": log.detail,
            "timestamp": log.timestamp.isoformat(),
        }

    @router.get("")
    async def list_audit_logs(
        workspace_id: str = Query(..., description="Workspace ID"),
        limit: int = Query(50, ge=1, le=500),
        action: str = Query(""),
        user_id: str = Query(""),
        token=Depends(require_manage),
    ):
        """List audit logs for a workspace (admin+)."""
        try:
            logs = collab_store.list_audit_logs(
                workspace_id=workspace_id, limit=limit,
                action=action, user_id=user_id,
            )
            return [_log_to_dict(l) for l in logs]
        except Exception as e:
            raise HTTPException(status_code=500, detail="服务内部错误，请稍后重试")

    @router.get("/summary")
    async def get_audit_summary(
        workspace_id: str = Query(..., description="Workspace ID"),
        token=Depends(require_manage),
    ):
        """Get audit summary including counts by time window (admin+)."""
        try:
            summary = collab_store.get_audit_summary(workspace_id)
            return {
                "workspace_id": summary.workspace_id,
                "last_24h": summary.last_24h,
                "last_7d": summary.last_7d,
                "last_30d": summary.last_30d,
                "total": summary.total,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail="服务内部错误，请稍后重试")

    @router.get("/user/{user_id}")
    async def get_user_activity(
        user_id: str,
        workspace_id: str = Query(..., description="Workspace ID"),
        days: int = Query(7, ge=1, le=90),
        token=Depends(require_auth),
    ):
        """Get activity timeline for a specific user."""
        try:
            activity = collab_store.get_user_activity_timeline(
                user_id=user_id, workspace_id=workspace_id, days=days,
            )
            return {
                "user_id": activity.user_id,
                "workspace_id": activity.workspace_id,
                "daily_actions": activity.daily_actions,
                "top_actions": activity.top_actions,
                "total_actions": activity.total_actions,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail="服务内部错误，请稍后重试")

    @router.get("/export")
    async def export_audit_logs(
        workspace_id: str = Query(..., description="Workspace ID"),
        fmt: str = Query("json", alias="format"),
        token=Depends(require_manage),
    ):
        """Export audit logs as a downloadable JSON file (admin+)."""
        if fmt != "json":
            raise HTTPException(status_code=400, detail="Only 'json' format is supported")

        try:
            logs = collab_store.list_audit_logs(
                workspace_id=workspace_id, limit=10_000,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail="服务内部错误，请稍后重试")

        from datetime import datetime, timezone

        result = {
            "format": fmt,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_records": len(logs),
            "logs": [_log_to_dict(l) for l in logs],
        }

        return JSONResponse(
            content=result,
            headers={
                "Content-Disposition": f'attachment; filename="audit-export-{workspace_id}.json"',
                "Content-Type": "application/json",
            },
        )

    return router
