"""
Compliance router — retention policies, data requests, sensitive-information scanning.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.compliance import detect_sensitive
from .middleware import require_auth, require_manage


# ── Pydantic models ──────────────────────────────────────────────────────────

from pydantic import BaseModel, Field


class CreateRetentionPolicyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    resource_type: str = Field(..., min_length=1, max_length=64)
    retention_period: int = Field(..., gt=0, description="Retention period in days")
    archive_action: str = Field(..., pattern=r"^(archive|delete|anonymize)$")
    description: Optional[str] = Field(None, max_length=512)
    organization_id: str


class UpdateRetentionPolicyRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    resource_type: Optional[str] = Field(None, min_length=1, max_length=64)
    retention_period: Optional[int] = Field(None, gt=0)
    archive_action: Optional[str] = Field(None, pattern=r"^(archive|delete|anonymize)$")
    description: Optional[str] = Field(None, max_length=512)


class DataRequestRequest(BaseModel):
    user_id: str
    organization_id: str
    request_type: str = Field(..., pattern=r"^(export|delete)$")


class ProcessDataRequestRequest(BaseModel):
    action: str = Field(default="approve", pattern=r"^(approve|deny)$")
    notes: Optional[str] = Field(None, max_length=1024)


class DetectSensitiveRequest(BaseModel):
    text: str = Field(..., min_length=1)
    entity_types: list[str] = Field(
        default_factory=lambda: ["pii", "credentials", "financial", "health", "legal"],
        description="Entity types to scan for",
    )


class SensitiveMatchResponse(BaseModel):
    text: str
    entity_type: str
    start: int
    end: int
    confidence: float


class ScanRequest(BaseModel):
    org_id: str = Query(..., description="Organization ID")
    entity_types: Optional[str] = Query(None, description="Comma-separated entity types")


# ── Factory ──────────────────────────────────────────────────────────────────

def create_compliance_router(compliance_store, org_store=None) -> APIRouter:
    router = APIRouter(prefix="/api/compliance", tags=["Compliance"])

    # ── Retention Policies ────────────────────────────────────────────────

    @router.get("/policies")
    async def list_retention_policies(
        org_id: Optional[str] = Query(None, description="Filter by organization"),
        token=Depends(require_auth),
    ):
        """List retention policies, optionally filtered by organization."""
        policies = compliance_store.list_retention_policies(organization_id=org_id)
        return policies

    @router.post("/policies", status_code=201)
    async def create_retention_policy(
        body: CreateRetentionPolicyRequest,
        token=Depends(require_manage),
    ):
        """Create a retention policy (admin+)."""
        if org_store is not None:
            org = org_store.get_organization(body.organization_id)
            if org is None:
                raise HTTPException(status_code=404, detail="Organization not found")

        try:
            policy = compliance_store.create_retention_policy(
                name=body.name,
                resource_type=body.resource_type,
                retention_period=body.retention_period,
                archive_action=body.archive_action,
                description=body.description,
                organization_id=body.organization_id,
            )
            return policy
        except ValueError as e:
            logger.exception("compliance_endpoint_error"); raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create policy: {str(e)}")

    @router.put("/policies/{policy_id}")
    async def update_retention_policy(
        policy_id: str,
        body: UpdateRetentionPolicyRequest,
        token=Depends(require_manage),
    ):
        """Update a retention policy."""
        policy = compliance_store.get_retention_policy(policy_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="Retention policy not found")
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        try:
            updated = compliance_store.update_retention_policy(policy_id, **updates)
            return updated
        except ValueError as e:
            logger.exception("compliance_endpoint_error"); raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update policy: {str(e)}")

    @router.delete("/policies/{policy_id}", status_code=200)
    async def delete_retention_policy(
        policy_id: str,
        token=Depends(require_manage),
    ):
        """Delete a retention policy."""
        policy = compliance_store.get_retention_policy(policy_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="Retention policy not found")
        success = compliance_store.delete_retention_policy(policy_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete policy")
        return {"detail": "Retention policy deleted"}

    # ── Enforcement ───────────────────────────────────────────────────────

    @router.post("/enforce/{org_id}")
    async def enforce_retention(
        org_id: str,
        token=Depends(require_manage),
    ):
        """Trigger retention policy enforcement for an organization (admin+)."""
        if org_store is not None:
            org = org_store.get_organization(org_id)
            if org is None:
                raise HTTPException(status_code=404, detail="Organization not found")

        try:
            result = compliance_store.enforce_retention(organization_id=org_id)
            return result
        except ValueError as e:
            logger.exception("compliance_endpoint_error"); raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Enforcement failed: {str(e)}")

    # ── Data Requests ─────────────────────────────────────────────────────

    @router.post("/data-request", status_code=201)
    async def submit_data_request(
        body: DataRequestRequest,
        token=Depends(require_auth),
    ):
        """Submit a data export or deletion request."""
        try:
            req = compliance_store.create_data_request(
                user_id=body.user_id,
                organization_id=body.organization_id,
                request_type=body.request_type,
            )
            return req
        except ValueError as e:
            logger.exception("compliance_endpoint_error"); raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to submit data request: {str(e)}")

    @router.get("/data-requests")
    async def list_data_requests(
        org_id: Optional[str] = Query(None, alias="org_id"),
        user_id: Optional[str] = Query(None, alias="user_id"),
        status: Optional[str] = Query(None, alias="status", pattern=r"^(pending|processing|completed|denied)$"),
        token=Depends(require_manage),
    ):
        """List data export/delete requests (admin+)."""
        requests = compliance_store.list_data_requests(
            organization_id=org_id,
            user_id=user_id,
            status=status,
        )
        return requests

    @router.post("/data-requests/{request_id}/process")
    async def process_data_request(
        request_id: str,
        body: ProcessDataRequestRequest,
        token=Depends(require_manage),
    ):
        """Approve or deny a pending data request (admin+)."""
        req = compliance_store.get_data_request(request_id)
        if req is None:
            raise HTTPException(status_code=404, detail="Data request not found")
        if getattr(req, "status", None) != "pending":
            raise HTTPException(status_code=400, detail="Only pending requests can be processed")

        try:
            result = compliance_store.process_data_request(
                request_id=request_id,
                action=body.action,
                notes=body.notes,
            )
            return result
        except ValueError as e:
            logger.exception("compliance_endpoint_error"); raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to process request: {str(e)}")

    # ── Sensitive Info Scanning ───────────────────────────────────────────

    @router.get("/scan", response_model=list[SensitiveMatchResponse])
    async def scan_for_sensitive_info(
        org_id: str = Query(..., description="Organization ID"),
        entity_types: Optional[str] = Query(None, description="Comma-separated entity types"),
        token=Depends(require_manage),
    ):
        """Scan an organization for sensitive information (admin+)."""
        types_list = (
            [t.strip() for t in entity_types.split(",") if t.strip()]
            if entity_types
            else None
        )

        try:
            matches = compliance_store.scan_sensitive(
                organization_id=org_id,
                entity_types=types_list,
            )
            return matches
        except ValueError as e:
            logger.exception("compliance_endpoint_error"); raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")

    @router.get("/report")
    async def generate_compliance_report(
        org_id: str = Query(..., description="Organization ID"),
        token=Depends(require_manage),
    ):
        """Generate a compliance report for an organization (admin+)."""
        try:
            report = compliance_store.generate_compliance_report(organization_id=org_id)
            if report is None:
                raise HTTPException(status_code=404, detail="No compliance data available")
            return report
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")

    @router.post("/detect", response_model=list[SensitiveMatchResponse])
    async def detect_sensitive_info(
        body: DetectSensitiveRequest,
        token=Depends(require_auth),
    ):
        """Detect sensitive information in a given text string."""
        try:
            matches = detect_sensitive(
                text=body.text,
                entity_types=body.entity_types,
            )
            return matches
        except ValueError as e:
            logger.exception("compliance_endpoint_error"); raise HTTPException(status_code=400, detail="请求参数无效")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Detection failed: {str(e)}")

    return router
