"""
Organization router — org CRUD, business units, departments, positions, members.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.organization import Organization, BusinessUnit, Department, Position, OrgTreeNode
from src.core.rbac import EnterpriseRole
from .middleware import require_auth, require_write, require_manage


# ── Pydantic request models ──────────────────────────────────────────────────

from pydantic import BaseModel, Field


class CreateOrgRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    industry: Optional[str] = Field(None, max_length=64)


class UpdateOrgRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    industry: Optional[str] = Field(None, max_length=64)


class CreateBusinessUnitRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    parent_id: Optional[str] = None
    description: Optional[str] = Field(None, max_length=512)


class CreateDepartmentRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    business_unit_id: str
    parent_id: Optional[str] = None
    description: Optional[str] = Field(None, max_length=512)


class CreatePositionRequest(BaseModel):
    user_id: str
    department_id: str
    title: str = Field(..., min_length=1, max_length=128)
    is_manager: bool = False


# ── Factory ──────────────────────────────────────────────────────────────────

def create_org_router(org_store, auth_store, rbac_store=None) -> APIRouter:
    router = APIRouter(prefix="/api/org", tags=["Organization"])

    # ── Organization CRUD ────────────────────────────────────────────────

    @router.post("", response_model=Organization, status_code=201)
    async def create_organization(
        body: CreateOrgRequest,
        token=Depends(require_auth),
    ):
        """Create an organization. Auto-creates a default BU structure and RBAC roles."""
        try:
            org = org_store.create_organization(
                name=body.name,
                industry=body.industry,
                owner_id=token.user_id,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create organization: {str(e)}")

        # Auto-create default RBAC roles if rbac_store was provided
        if rbac_store is not None:
            try:
                rbac_store.create_default_roles(organization_id=org.id)
            except Exception:
                # Non-fatal — roles can be created later
                pass

        return org

    @router.get("", response_model=list[Organization])
    async def list_organizations(
        token=Depends(require_auth),
    ):
        """List organizations the current user belongs to."""
        orgs = org_store.list_organizations(user_id=token.user_id)
        return orgs

    @router.get("/{org_id}", response_model=Organization)
    async def get_organization(
        org_id: str,
        token=Depends(require_auth),
    ):
        """Get organization details."""
        org = org_store.get_organization(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        return org

    @router.put("/{org_id}", response_model=Organization)
    async def update_organization(
        org_id: str,
        body: UpdateOrgRequest,
        token=Depends(require_manage),
    ):
        """Update organization name or industry (admin+)."""
        org = org_store.get_organization(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        updated = org_store.update_organization(org_id, **updates)
        return updated

    @router.delete("/{org_id}", status_code=200)
    async def delete_organization(
        org_id: str,
        token=Depends(require_manage),
    ):
        """Delete an organization (owner only)."""
        org = org_store.get_organization(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        if org.owner_id != token.user_id:
            raise HTTPException(status_code=403, detail="Only the organization owner can delete it")
        success = org_store.delete_organization(org_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete organization")
        return {"detail": "Organization deleted"}

    @router.get("/{org_id}/tree", response_model=OrgTreeNode)
    async def get_org_tree(
        org_id: str,
        token=Depends(require_auth),
    ):
        """Get the full organization tree (BUs, departments, positions)."""
        org = org_store.get_organization(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        tree = org_store.get_org_tree(org_id)
        if tree is None:
            raise HTTPException(status_code=500, detail="Failed to build org tree")
        return tree

    # ── Business Units ────────────────────────────────────────────────────

    @router.get("/{org_id}/business-units", response_model=list[BusinessUnit])
    async def list_business_units(
        org_id: str,
        token=Depends(require_auth),
    ):
        """List business units in an organization."""
        org = org_store.get_organization(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        return org_store.list_business_units(org_id)

    @router.post("/{org_id}/business-units", response_model=BusinessUnit, status_code=201)
    async def create_business_unit(
        org_id: str,
        body: CreateBusinessUnitRequest,
        token=Depends(require_write),
    ):
        """Create a business unit within an organization."""
        org = org_store.get_organization(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        try:
            bu = org_store.create_business_unit(
                organization_id=org_id,
                name=body.name,
                parent_id=body.parent_id,
                description=body.description,
            )
            return bu
        except ValueError as e:
            raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create business unit: {str(e)}")

    @router.delete("/{org_id}/business-units/{bu_id}", status_code=200)
    async def delete_business_unit(
        org_id: str,
        bu_id: str,
        token=Depends(require_manage),
    ):
        """Delete a business unit."""
        org = org_store.get_organization(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        bu = org_store.get_business_unit(bu_id)
        if bu is None or bu.organization_id != org_id:
            raise HTTPException(status_code=404, detail="Business unit not found")
        success = org_store.delete_business_unit(bu_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete business unit")
        return {"detail": "Business unit deleted"}

    # ── Departments ───────────────────────────────────────────────────────

    @router.get("/{org_id}/departments", response_model=list[Department])
    async def list_departments(
        org_id: str,
        bu_id: Optional[str] = Query(None, description="Filter by business unit"),
        token=Depends(require_auth),
    ):
        """List departments, optionally filtered by business unit."""
        org = org_store.get_organization(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        return org_store.list_departments(organization_id=org_id, business_unit_id=bu_id)

    @router.post("/{org_id}/departments", response_model=Department, status_code=201)
    async def create_department(
        org_id: str,
        body: CreateDepartmentRequest,
        token=Depends(require_write),
    ):
        """Create a department."""
        org = org_store.get_organization(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        try:
            dept = org_store.create_department(
                organization_id=org_id,
                name=body.name,
                business_unit_id=body.business_unit_id,
                parent_id=body.parent_id,
                description=body.description,
            )
            return dept
        except ValueError as e:
            raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create department: {str(e)}")

    @router.delete("/{org_id}/departments/{dept_id}", status_code=200)
    async def delete_department(
        org_id: str,
        dept_id: str,
        token=Depends(require_manage),
    ):
        """Delete a department."""
        org = org_store.get_organization(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        dept = org_store.get_department(dept_id)
        if dept is None or dept.organization_id != org_id:
            raise HTTPException(status_code=404, detail="Department not found")
        success = org_store.delete_department(dept_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete department")
        return {"detail": "Department deleted"}

    # ── Positions ─────────────────────────────────────────────────────────

    @router.get("/{org_id}/positions", response_model=list[Position])
    async def list_positions(
        org_id: str,
        dept_id: Optional[str] = Query(None, description="Filter by department"),
        token=Depends(require_auth),
    ):
        """List positions, optionally filtered by department."""
        org = org_store.get_organization(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        return org_store.list_positions(organization_id=org_id, department_id=dept_id)

    @router.post("/{org_id}/positions", response_model=Position, status_code=201)
    async def create_position(
        org_id: str,
        body: CreatePositionRequest,
        token=Depends(require_write),
    ):
        """Create a position for a user in a department."""
        org = org_store.get_organization(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        try:
            position = org_store.create_position(
                organization_id=org_id,
                user_id=body.user_id,
                department_id=body.department_id,
                title=body.title,
                is_manager=body.is_manager,
            )
            return position
        except ValueError as e:
            raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create position: {str(e)}")

    @router.delete("/{org_id}/positions/{position_id}", status_code=200)
    async def delete_position(
        org_id: str,
        position_id: str,
        token=Depends(require_manage),
    ):
        """Delete a position."""
        org = org_store.get_organization(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        pos = org_store.get_position(position_id)
        if pos is None or pos.organization_id != org_id:
            raise HTTPException(status_code=404, detail="Position not found")
        success = org_store.delete_position(position_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete position")
        return {"detail": "Position deleted"}

    # ── Members ───────────────────────────────────────────────────────────

    @router.get("/{org_id}/members")
    async def list_members(
        org_id: str,
        token=Depends(require_auth),
    ):
        """List organization members with their positions."""
        org = org_store.get_organization(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        members = org_store.list_members_with_positions(org_id)
        return members

    return router
