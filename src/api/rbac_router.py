"""
RBAC router — roles, permissions, ABAC policies, assignments, access checks.
"""

import logging
from typing import Optional, Union

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.rbac import EnterpriseRole
from .middleware import require_auth, require_manage


# ── Pydantic models ──────────────────────────────────────────────────────────

from pydantic import BaseModel, Field


class CreateRoleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    permissions: list[str] = Field(default_factory=list)
    description: Optional[str] = Field(None, max_length=256)


class UpdateRoleRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    description: Optional[str] = Field(None, max_length=256)
    permissions: Optional[list[str]] = None


class AddPermissionRequest(BaseModel):
    permission_key: str = Field(..., min_length=1, max_length=128)


class CreatePolicyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    effect: str = Field(..., pattern=r"^(allow|deny)$")
    conditions: dict = Field(default_factory=dict)
    priority: int = Field(default=0, ge=0)
    description: Optional[str] = Field(None, max_length=512)


class UpdatePolicyRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    effect: Optional[str] = Field(None, pattern=r"^(allow|deny)$")
    conditions: Optional[dict] = None
    priority: Optional[int] = Field(None, ge=0)
    description: Optional[str] = Field(None, max_length=512)


class AssignRoleRequest(BaseModel):
    user_id: str
    role_id: str
    organization_id: str
    scope_type: str = Field(default="org", pattern=r"^(org|bu|department|project)$")
    scope_id: Optional[str] = None


class CheckAccessRequest(BaseModel):
    user_id: str
    organization_id: str
    resource: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    resource_id: Optional[str] = None


# ── Factory ──────────────────────────────────────────────────────────────────

def create_rbac_router(rbac_store, org_store=None, auth_store=None) -> APIRouter:
    router = APIRouter(prefix="/api/rbac", tags=["RBAC"])

    # ── Users ─────────────────────────────────────────────────────────────

    @router.get("/users")
    async def list_users(
        token=Depends(require_auth),
    ):
        """List all registered users with their organizations and roles."""
        result: list[dict] = []
        if auth_store is None:
            return result

        try:
            # 从 users 表查询所有用户
            rows = auth_store._db.execute(
                "SELECT * FROM users ORDER BY created_at DESC"
            ).fetchall()

            for row in rows:
                user = dict(row)
                user_id = user["id"]

                # 获取用户所属组织
                orgs = []
                if org_store is not None:
                    try:
                        org_list = org_store.list_organizations(user_id=user_id)
                        orgs = [
                            {"id": o.id, "name": o.name}
                            for o in org_list
                        ]
                    except Exception:
                        pass

                # 获取用户角色（从 memberships 表或 role_assignments 表）
                roles: list[str] = []
                try:
                    # 先尝试从 role_assignments 获取
                    role_rows = rbac_store._db.execute(
                        """SELECT r.name FROM roles r
                           JOIN role_assignments ra ON r.id = ra.role_id
                           WHERE ra.user_id = ?""",
                        (user_id,),
                    ).fetchall()
                    if role_rows:
                        roles = [r["name"] for r in role_rows]
                except Exception:
                    pass

                # 如果 RBAC 没有角色，从 memberships 获取
                if not roles:
                    try:
                        member_rows = auth_store._db.execute(
                            "SELECT role FROM memberships WHERE user_id = ?",
                            (user_id,),
                        ).fetchall()
                        roles = [r["role"] for r in member_rows]
                    except Exception:
                        pass

                # 超级管理员标记
                if user.get("is_super_admin"):
                    if "SuperAdmin" not in roles:
                        roles.insert(0, "SuperAdmin")

                result.append({
                    "id": user_id,
                    "name": user.get("name", ""),
                    "email": user.get("email", ""),
                    "roles": roles,
                    "org_id": orgs[0]["id"] if orgs else None,
                    "org_name": orgs[0]["name"] if orgs else None,
                    "department": None,
                    "created_at": user.get("created_at"),
                })
        except Exception:
            logger.warning("rbac:list_users_failed", exc_info=True)
            return []

        return result

    # ── Roles ─────────────────────────────────────────────────────────────

    @router.get("/roles")
    async def list_roles(
        org_id: Optional[str] = Query(None, description="Filter by organization"),
        token=Depends(require_auth),
    ):
        """List all roles, optionally filtered by organization."""
        roles = rbac_store.list_roles(organization_id=org_id)
        return roles

    @router.post("/roles", status_code=201)
    async def create_role(
        body: CreateRoleRequest,
        token=Depends(require_manage),
    ):
        """Create a custom role (admin+)."""
        try:
            role = rbac_store.create_role(
                name=body.name,
                permissions=body.permissions,
                description=body.description,
                is_system=False,
            )
            return role
        except ValueError as e:
            raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create role: {str(e)}")

    @router.get("/roles/{role_id}")
    async def get_role(
        role_id: str,
        token=Depends(require_auth),
    ):
        """Get a role by ID."""
        role = rbac_store.get_role(role_id)
        if role is None:
            raise HTTPException(status_code=404, detail="Role not found")
        return role

    @router.put("/roles/{role_id}")
    async def update_role(
        role_id: str,
        body: UpdateRoleRequest,
        token=Depends(require_manage),
    ):
        """Update a role (admin+)."""
        role = rbac_store.get_role(role_id)
        if role is None:
            raise HTTPException(status_code=404, detail="Role not found")
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        try:
            updated = rbac_store.update_role(role_id, **updates)
            return updated
        except ValueError as e:
            raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update role: {str(e)}")

    @router.delete("/roles/{role_id}", status_code=200)
    async def delete_role(
        role_id: str,
        token=Depends(require_manage),
    ):
        """Delete a role. System roles cannot be deleted."""
        role = rbac_store.get_role(role_id)
        if role is None:
            raise HTTPException(status_code=404, detail="Role not found")
        if getattr(role, "is_system", False):
            raise HTTPException(status_code=403, detail="Cannot delete a system role")
        success = rbac_store.delete_role(role_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete role")
        return {"detail": "Role deleted"}

    # ── Permissions ───────────────────────────────────────────────────────

    @router.post("/roles/{role_id}/permissions", status_code=200)
    async def add_permission_to_role(
        role_id: str,
        body: AddPermissionRequest,
        token=Depends(require_manage),
    ):
        """Add a permission to a role."""
        role = rbac_store.get_role(role_id)
        if role is None:
            raise HTTPException(status_code=404, detail="Role not found")
        try:
            rbac_store.add_permission(role_id, body.permission_key)
            return {"detail": f"Permission '{body.permission_key}' added to role"}
        except ValueError as e:
            raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to add permission: {str(e)}")

    @router.delete("/roles/{role_id}/permissions/{permission_key}", status_code=200)
    async def remove_permission_from_role(
        role_id: str,
        permission_key: str,
        token=Depends(require_manage),
    ):
        """Remove a permission from a role."""
        role = rbac_store.get_role(role_id)
        if role is None:
            raise HTTPException(status_code=404, detail="Role not found")
        success = rbac_store.remove_permission(role_id, permission_key)
        if not success:
            raise HTTPException(status_code=404, detail="Permission not found on this role")
        return {"detail": f"Permission '{permission_key}' removed from role"}

    @router.get("/permissions")
    async def list_permissions(
        org_id: Optional[str] = Query(None, description="Filter by organization"),
        token=Depends(require_auth),
    ):
        """List all available permissions, optionally filtered by organization."""
        perms = rbac_store.list_permissions(organization_id=org_id)
        return perms

    # ── ABAC Policies ─────────────────────────────────────────────────────

    @router.get("/policies")
    async def list_policies(
        org_id: Optional[str] = Query(None, description="Filter by organization"),
        token=Depends(require_auth),
    ):
        """List ABAC policies, optionally filtered by organization."""
        policies = rbac_store.list_policies(organization_id=org_id)
        return policies

    @router.post("/policies", status_code=201)
    async def create_policy(
        body: CreatePolicyRequest,
        token=Depends(require_manage),
    ):
        """Create an ABAC policy (admin+)."""
        try:
            policy = rbac_store.create_policy(
                name=body.name,
                effect=body.effect,
                conditions=body.conditions,
                priority=body.priority,
                description=body.description,
            )
            return policy
        except ValueError as e:
            raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create policy: {str(e)}")

    @router.put("/policies/{policy_id}")
    async def update_policy(
        policy_id: str,
        body: UpdatePolicyRequest,
        token=Depends(require_manage),
    ):
        """Update an ABAC policy."""
        policy = rbac_store.get_policy(policy_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="Policy not found")
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        try:
            updated = rbac_store.update_policy(policy_id, **updates)
            return updated
        except ValueError as e:
            raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update policy: {str(e)}")

    @router.delete("/policies/{policy_id}", status_code=200)
    async def delete_policy(
        policy_id: str,
        token=Depends(require_manage),
    ):
        """Delete an ABAC policy."""
        policy = rbac_store.get_policy(policy_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="Policy not found")
        success = rbac_store.delete_policy(policy_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete policy")
        return {"detail": "Policy deleted"}

    # ── Assignments ───────────────────────────────────────────────────────

    @router.post("/assign", status_code=201)
    async def assign_role(
        body: AssignRoleRequest,
        token=Depends(require_manage),
    ):
        """Assign a role to a user within a scope."""
        role = rbac_store.get_role(body.role_id)
        if role is None:
            raise HTTPException(status_code=404, detail="Role not found")
        try:
            assignment = rbac_store.assign_role(
                user_id=body.user_id,
                role_id=body.role_id,
                organization_id=body.organization_id,
                scope_type=body.scope_type,
                scope_id=body.scope_id,
            )
            return assignment
        except ValueError as e:
            raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to assign role: {str(e)}")

    @router.get("/users/{user_id}/roles")
    async def get_user_roles(
        user_id: str,
        org_id: Optional[str] = Query(None, description="Filter by organization"),
        token=Depends(require_auth),
    ):
        """Get all roles assigned to a user."""
        roles = rbac_store.get_user_roles(user_id=user_id, organization_id=org_id)
        return roles

    @router.delete("/assignments/{assignment_id}", status_code=200)
    async def remove_assignment(
        assignment_id: str,
        token=Depends(require_manage),
    ):
        """Remove a role assignment."""
        assignment = rbac_store.get_assignment(assignment_id)
        if assignment is None:
            raise HTTPException(status_code=404, detail="Assignment not found")
        success = rbac_store.remove_assignment(assignment_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to remove assignment")
        return {"detail": "Assignment removed"}

    # ── Access Check ──────────────────────────────────────────────────────

    @router.post("/check")
    async def check_access(
        body: CheckAccessRequest,
        token=Depends(require_auth),
    ):
        """Check whether a user has permission for a given resource and action."""
        try:
            decision = rbac_store.check_access(
                user_id=body.user_id,
                organization_id=body.organization_id,
                resource=body.resource,
                action=body.action,
                resource_id=body.resource_id,
            )
            return decision
        except ValueError as e:
            raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Access check failed: {str(e)}")

    return router
