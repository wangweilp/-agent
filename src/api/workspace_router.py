"""Workspace Team API — 成员管理 / 协作 / 任务 / 审计 / 通知。

端点:
    GET    /workspace/{id}/members
    POST   /workspace/{id}/members
    PATCH  /workspace/{id}/members/{user_id}
    DELETE /workspace/{id}/members/{user_id}
    POST   /workspace/{id}/memory/merge
    POST   /workspace/{id}/action-plan
    GET    /workspace/{id}/action-plans
    PATCH  /workspace/{id}/action-plans/{plan_id}
    POST   /workspace/{id}/action-plans/{plan_id}/complete
    DELETE /workspace/{id}/action-plans/{plan_id}
    GET    /workspace/{id}/dashboard
    GET    /workspace/{id}/activity-log
    GET    /notifications
    POST   /notifications/read-all
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.adapters.auth_store import SQLiteAuthStore, WorkspaceContext
from src.adapters.collab_store import CollaborationService
from src.api.middleware import (
    assert_workspace_access,
    assert_workspace_manage,
    require_auth,
)
from src.core.auth import TokenPayload, WorkspaceRole
from src.core.audit import NotificationPreferences
from src.core.collaboration import ActionPlan, ActionPriority, ActionStatus, AuditLog

logger = logging.getLogger(__name__)


# ── Schemas ──


class AddMemberRequest(BaseModel):
    email: str = Field(..., min_length=3)
    role: str = Field(default="member")


class UpdateRoleRequest(BaseModel):
    role: str = Field(...)


class MemoryMergeRequest(BaseModel):
    primary_id: str
    secondary_ids: list[str] = Field(min_length=1)


class ActionPlanRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    assigned_to: str | None = None
    priority: str = "medium"
    due_date: str | None = None
    related_memory_ids: list[str] = []


class ActionPlanUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    assigned_to: str | None = None
    priority: str | None = None
    status: str | None = None
    due_date: str | None = None


class NotificationPreferencesRequest(BaseModel):
    email_enabled: bool | None = None
    push_enabled: bool | None = None
    digest_frequency: str | None = None


# ── Router Factory ──


def create_workspace_router(
    collab_service: CollaborationService,
    auth_store: SQLiteAuthStore,
    agent=None,
) -> APIRouter:
    router = APIRouter(tags=["workspace"])

    # ── Helpers ──

    def _current_ws() -> str:
        return WorkspaceContext.workspace_id()

    def _check_role(payload: TokenPayload, required: WorkspaceRole):
        if WorkspaceRole.hierarchy()[payload.role.value] < WorkspaceRole.hierarchy()[required.value]:
            raise HTTPException(403, f"需要 {required.value} 或以上权限")

    # ── Members ──

    @router.get("/workspace/{id}/members")
    async def list_members(id: str, payload: TokenPayload = Depends(assert_workspace_access)):
        members = auth_store.list_members(id)
        result = []
        for m in members:
            user = auth_store.get_user_by_id(m.user_id)
            result.append({
                "user_id": m.user_id,
                "name": user.name if user else "",
                "email": user.email if user else "",
                "avatar_url": user.avatar_url if user else None,
                "role": m.role.value,
                "joined_at": m.joined_at.isoformat() if m.joined_at else "",
            })
        return result

    @router.post("/workspace/{id}/members")
    async def add_member(id: str, body: AddMemberRequest,
                         payload: TokenPayload = Depends(assert_workspace_manage)):
        _check_role(payload, WorkspaceRole.ADMIN)
        user = auth_store.get_by_email(body.email.lower())
        if user is None:
            raise HTTPException(404, "用户不存在，请先注册")
        try:
            role = WorkspaceRole(body.role)
        except ValueError:
            raise HTTPException(400, f"无效角色: {body.role}")

        existing = auth_store.get_membership(id, user.id)
        if existing:
            raise HTTPException(409, "该用户已在工作区中")

        m = auth_store.add_member(id, user.id, role)
        collab_service._store.log_activity(__import__("src.core.collaboration", fromlist=["ActivityEvent"]).ActivityEvent(
            workspace_id=id, user_id=payload.user_id, user_name=payload.email,
            event_type="member_added", message=f"添加了成员 {user.email}",
        ))
        return {"user_id": m.user_id, "role": m.role.value, "joined_at": m.joined_at.isoformat()}

    @router.patch("/workspace/{id}/members/{user_id}")
    async def update_member_role(id: str, user_id: str, body: UpdateRoleRequest,
                                  payload: TokenPayload = Depends(assert_workspace_manage)):
        _check_role(payload, WorkspaceRole.ADMIN)
        try:
            role = WorkspaceRole(body.role)
        except ValueError:
            raise HTTPException(400, f"无效角色: {body.role}")
        auth_store.update_role(id, user_id, role)
        return {"user_id": user_id, "role": role.value}

    @router.delete("/workspace/{id}/members/{user_id}")
    async def remove_member(id: str, user_id: str,
                            payload: TokenPayload = Depends(assert_workspace_manage)):
        _check_role(payload, WorkspaceRole.ADMIN)
        if user_id == payload.user_id:
            raise HTTPException(400, "不能移除自己")
        auth_store.remove_member(id, user_id)
        return {"status": "removed"}

    # ── Memory Merge ──

    @router.post("/workspace/{id}/memory/merge")
    async def merge_memory(id: str, body: MemoryMergeRequest,
                           payload: TokenPayload = Depends(assert_workspace_manage)):
        if agent is None:
            raise HTTPException(500, "Agent 未初始化")
        count = collab_service.merge_workspace_memories(
            workspace_id=id, primary_id=body.primary_id,
            secondary_ids=body.secondary_ids, user_id=payload.user_id,
            user_name=payload.email, memory_store=agent._memory_store,
        )
        return {"merged_count": count}

    # ── Action Plans ──

    @router.post("/workspace/{id}/action-plan")
    async def create_action_plan(id: str, body: ActionPlanRequest,
                                  payload: TokenPayload = Depends(assert_workspace_manage)):
        plan = ActionPlan(
            workspace_id=id, title=body.title, description=body.description,
            assigned_to=body.assigned_to, assigned_by=payload.user_id,
            priority=ActionPriority(body.priority),
            due_date=datetime.fromisoformat(body.due_date) if body.due_date else None,
            related_memory_ids=body.related_memory_ids,
        )
        result = collab_service.create_action(plan, payload.user_id, payload.email)
        return {
            "id": result.id, "title": result.title, "status": result.status.value,
            "assigned_to": result.assigned_to, "priority": result.priority.value,
            "created_at": result.created_at.isoformat(),
        }

    @router.get("/workspace/{id}/action-plans")
    async def list_action_plans(id: str, assignee: str = "",
                                 status: str = "", limit: int = Query(default=50, le=100),
                                 payload: TokenPayload = Depends(assert_workspace_access)):
        plans = collab_service._store.list_action_plans(id, assignee, status, limit)
        return [
            {
                "id": p.id, "title": p.title, "description": p.description,
                "assigned_to": p.assigned_to, "assigned_by": p.assigned_by,
                "priority": p.priority.value, "status": p.status.value,
                "due_date": p.due_date.isoformat() if p.due_date else None,
                "related_memory_ids": p.related_memory_ids,
                "created_at": p.created_at.isoformat(),
                "completed_at": p.completed_at.isoformat() if p.completed_at else None,
            }
            for p in plans
        ]

    @router.patch("/workspace/{id}/action-plans/{plan_id}")
    async def update_action_plan(id: str, plan_id: str, body: ActionPlanUpdateRequest,
                                  payload: TokenPayload = Depends(assert_workspace_manage)):
        plan = collab_service._store.get_action_plan(id, plan_id)
        if plan is None:
            raise HTTPException(404, "行动计划不存在")
        if body.title is not None:
            plan.title = body.title
        if body.description is not None:
            plan.description = body.description
        if body.assigned_to is not None:
            plan.assigned_to = body.assigned_to
        if body.priority is not None:
            plan.priority = ActionPriority(body.priority)
        if body.status is not None:
            plan.status = ActionStatus(body.status)
        if body.due_date is not None:
            plan.due_date = datetime.fromisoformat(body.due_date) if body.due_date else None
        collab_service._store.update_action_plan(plan)
        return {"id": plan.id, "status": plan.status.value}

    @router.post("/workspace/{id}/action-plans/{plan_id}/complete")
    async def complete_action_plan(id: str, plan_id: str,
                                    payload: TokenPayload = Depends(assert_workspace_manage)):
        plan = collab_service.complete_action(plan_id, id, payload.user_id, payload.email)
        if plan is None:
            raise HTTPException(404, "行动计划不存在")
        return {"id": plan.id, "status": "completed", "completed_at": plan.completed_at.isoformat() if plan.completed_at else ""}

    @router.delete("/workspace/{id}/action-plans/{plan_id}")
    async def delete_action_plan(id: str, plan_id: str,
                                  payload: TokenPayload = Depends(assert_workspace_manage)):
        plan = collab_service._store.get_action_plan(id, plan_id)
        if plan is None:
            raise HTTPException(404, "行动计划不存在")
        collab_service._store.delete_action_plan(id, plan_id)
        return {"status": "deleted"}

    # ── Dashboard ──

    @router.get("/workspace/{id}/dashboard")
    async def workspace_dashboard(id: str, payload: TokenPayload = Depends(assert_workspace_access)):
        if agent is None:
            raise HTTPException(500, "Agent 未初始化")
        stats = collab_service.get_dashboard(id, agent._memory_store)
        return {
            "total_members": stats.total_members,
            "total_memories": stats.total_memories,
            "total_actions": stats.total_actions,
            "completed_actions": stats.completed_actions,
            "member_contributions": stats.member_contributions,
            "recent_activity": stats.recent_activity,
        }

    # ── Activity / Audit ──

    @router.get("/workspace/{id}/activity-log")
    async def activity_log(id: str, limit: int = Query(default=30, le=100),
                           payload: TokenPayload = Depends(assert_workspace_access)):
        return collab_service.get_activity_log(id, limit)

    @router.get("/workspace/{id}/audit-log")
    async def audit_log(id: str, action: str = "", user_id: str = "",
                        limit: int = Query(default=50, le=100),
                        payload: TokenPayload = Depends(assert_workspace_manage)):
        logs = collab_service.get_audit_log(id, limit, action, user_id)
        return [
            {
                "id": l.id, "user_id": l.user_id, "action": l.action.value,
                "resource_type": l.resource_type, "resource_id": l.resource_id,
                "detail": l.detail, "timestamp": l.timestamp.isoformat(),
            }
            for l in logs
        ]

    # ── Notifications ──

    @router.get("/notifications")
    async def list_notifications(unread_only: bool = False, limit: int = Query(default=30, le=100),
                                  payload: TokenPayload = Depends(require_auth)):
        notifs = collab_service._store.list_notifications(
            payload.user_id, payload.workspace_id, unread_only, limit,
        )
        return [
            {"id": n.id, "title": n.title, "body": n.body, "read": n.read,
             "created_at": n.created_at.isoformat(), "link": n.link}
            for n in notifs
        ]

    @router.get("/notifications/unread-count")
    async def unread_count(payload: TokenPayload = Depends(require_auth)):
        count = collab_service._store.unread_count(payload.user_id, payload.workspace_id)
        return {"unread": count}

    @router.post("/notifications/read-all")
    async def read_all_notifications(payload: TokenPayload = Depends(require_auth)):
        collab_service._store.mark_all_read(payload.user_id, payload.workspace_id)
        return {"status": "ok"}

    # ── Audit Summary ──

    @router.get("/workspace/{id}/audit-summary")
    async def audit_summary(id: str, payload: TokenPayload = Depends(assert_workspace_manage)):
        summary = collab_service._store.get_audit_summary(id)
        return {
            "workspace_id": summary.workspace_id,
            "last_24h": summary.last_24h,
            "last_7d": summary.last_7d,
            "last_30d": summary.last_30d,
            "total": summary.total,
        }

    # ── User Activity Timeline ──

    @router.get("/workspace/{id}/user-activity")
    async def user_activity_timeline(id: str,
                                     days: int = Query(default=7, ge=1, le=90),
                                     payload: TokenPayload = Depends(assert_workspace_access)):
        activity = collab_service._store.get_user_activity_timeline(
            payload.user_id, id, days=days,
        )
        return {
            "user_id": activity.user_id,
            "workspace_id": activity.workspace_id,
            "daily_actions": activity.daily_actions,
            "top_actions": activity.top_actions,
            "total_actions": activity.total_actions,
        }

    # ── Notification Preferences ──

    @router.patch("/notifications/preferences")
    async def update_notification_preferences(
        body: NotificationPreferencesRequest,
        payload: TokenPayload = Depends(require_auth),
    ):
        current = collab_service._store.get_notification_preferences(
            payload.user_id, payload.workspace_id,
        )
        if body.email_enabled is not None:
            current.email_enabled = body.email_enabled
        if body.push_enabled is not None:
            current.push_enabled = body.push_enabled
        if body.digest_frequency is not None:
            if body.digest_frequency not in ("daily", "weekly", "none"):
                raise HTTPException(400, "digest_frequency 须为 daily / weekly / none")
            current.digest_frequency = body.digest_frequency
        collab_service._store.update_notification_preferences(current)
        return {
            "user_id": current.user_id,
            "workspace_id": current.workspace_id,
            "email_enabled": current.email_enabled,
            "push_enabled": current.push_enabled,
            "digest_frequency": current.digest_frequency,
        }

    @router.get("/notifications/preferences")
    async def get_notification_preferences(
        payload: TokenPayload = Depends(require_auth),
    ):
        prefs = collab_service._store.get_notification_preferences(
            payload.user_id, payload.workspace_id,
        )
        return {
            "user_id": prefs.user_id,
            "workspace_id": prefs.workspace_id,
            "email_enabled": prefs.email_enabled,
            "push_enabled": prefs.push_enabled,
            "digest_frequency": prefs.digest_frequency,
        }

    return router
