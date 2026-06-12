"""Marketplace Governance API。

端点:
  Reviews:
    POST   /api/marketplace/reviews         — 创建 Review
    GET    /api/marketplace/reviews         — 列表
    PATCH  /api/marketplace/reviews/{id}    — 更新
    DELETE /api/marketplace/reviews/{id}    — 删除
  Reports:
    POST   /api/marketplace/reports         — 创建 Report
    GET    /api/marketplace/reports         — 列表
    POST   /api/marketplace/reports/{id}/resolve  — 解决举报
  Trust & Risk:
    GET    /api/marketplace/trust/{agent_id} — TrustScore
    GET    /api/marketplace/risk/{agent_id}  — RiskLevel
    GET    /api/marketplace/governance/{agent_id} — Governance Timeline
  Analytics:
    GET    /api/marketplace/analytics        — 综合面板

约束: metadata_only，不执行 runtime/container。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.middleware import require_auth, TokenPayload

logger = logging.getLogger(__name__)


class CreateReviewRequest(BaseModel):
    agent_module_id: str = Field(..., min_length=1)
    rating: int = Field(..., ge=1, le=5)
    title: str = Field(..., min_length=1)
    content: str = ""


class UpdateReviewRequest(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    title: str | None = None
    content: str | None = None


class CreateReportRequest(BaseModel):
    agent_module_id: str = Field(..., min_length=1)
    report_type: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = ""


class ResolveReportRequest(BaseModel):
    status: str = Field(..., min_length=1)
    resolved_by: str = Field(..., min_length=1)
    resolution_note: str = ""


def create_marketplace_governance_router(gov_service) -> APIRouter:
    router = APIRouter(prefix="/api/marketplace", tags=["marketplace-governance"])

    # ─── Reviews ───

    @router.post("/reviews", status_code=201)
    async def create_review(body: CreateReviewRequest,
                            payload: TokenPayload = Depends(require_auth)):
        from src.open_platform.marketplace_governance import (
            ReviewAlreadyExistsError, ReviewValidationError)
        try:
            r = gov_service.create_review(
                workspace_id=payload.workspace_id,
                agent_module_id=body.agent_module_id, rating=body.rating,
                title=body.title, content=body.content, created_by=payload.user_id)
        except ReviewValidationError as e:
            raise HTTPException(422, detail={"message": str(e), "errors": e.errors})
        except ReviewAlreadyExistsError as e:
            raise HTTPException(409, detail=str(e))
        return {"review": r.to_dict()}

    @router.get("/reviews")
    async def list_reviews(
        agent_module_id: str = Query(default=""),
        workspace_id: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
        payload: TokenPayload = Depends(require_auth),
    ):
        reviews = gov_service.list_reviews(
            agent_module_id=agent_module_id, workspace_id=workspace_id,
            limit=limit, offset=offset)
        return {"reviews": [r.to_dict() for r in reviews], "total": len(reviews)}

    @router.patch("/reviews/{review_id}")
    async def update_review(review_id: str, body: UpdateReviewRequest,
                            payload: TokenPayload = Depends(require_auth)):
        from src.open_platform.marketplace_governance import (
            ReviewNotFoundError, ReviewValidationError)
        try:
            r = gov_service.update_review(
                review_id, rating=body.rating, title=body.title, content=body.content)
        except ReviewNotFoundError as e: raise HTTPException(404, detail=str(e))
        except ReviewValidationError as e:
            raise HTTPException(422, detail={"message": str(e), "errors": e.errors})
        return {"review": r.to_dict()}

    @router.delete("/reviews/{review_id}")
    async def delete_review(review_id: str, payload: TokenPayload = Depends(require_auth)):
        from src.open_platform.marketplace_governance import ReviewNotFoundError
        try: gov_service.delete_review(review_id)
        except ReviewNotFoundError as e: raise HTTPException(404, detail=str(e))
        return {"success": True, "review_id": review_id}

    # ─── Reports ───

    @router.post("/reports", status_code=201)
    async def create_report(body: CreateReportRequest,
                            payload: TokenPayload = Depends(require_auth)):
        from src.open_platform.marketplace_governance import ReportValidationError
        try:
            r = gov_service.create_report(
                workspace_id=payload.workspace_id, agent_module_id=body.agent_module_id,
                report_type=body.report_type, title=body.title,
                description=body.description, created_by=payload.user_id)
        except ReportValidationError as e:
            raise HTTPException(422, detail={"message": str(e), "errors": e.errors})
        return {"report": r.to_dict()}

    @router.get("/reports")
    async def list_reports(
        agent_module_id: str = Query(default=""), status: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
        payload: TokenPayload = Depends(require_auth),
    ):
        reports = gov_service.list_reports(
            agent_module_id=agent_module_id, status=status, limit=limit, offset=offset)
        return {"reports": [r.to_dict() for r in reports], "total": len(reports)}

    @router.post("/reports/{report_id}/resolve")
    async def resolve_report(report_id: str, body: ResolveReportRequest,
                             payload: TokenPayload = Depends(require_auth)):
        from src.open_platform.marketplace_governance import (
            ReportNotFoundError, ReportValidationError)
        try:
            r = gov_service.resolve_report(report_id, body.status, body.resolved_by,
                                           body.resolution_note)
        except ReportNotFoundError as e: raise HTTPException(404, detail=str(e))
        except ReportValidationError as e:
            raise HTTPException(422, detail={"message": str(e), "errors": e.errors})
        return {"report": r.to_dict()}

    # ─── Trust & Risk ───

    @router.get("/trust/{agent_id}")
    async def get_trust(agent_id: str, payload: TokenPayload = Depends(require_auth)):
        ts = gov_service.calculate_trust_score(agent_id)
        agg = gov_service.get_rating_aggregation(agent_id)
        return {"trust_score": ts.to_dict(), "rating_aggregation": agg}

    @router.get("/risk/{agent_id}")
    async def get_risk(agent_id: str, payload: TokenPayload = Depends(require_auth)):
        risk = gov_service.calculate_risk_level(agent_id)
        ts = gov_service.get_trust_score(agent_id)
        return {"agent_module_id": agent_id, "risk_level": risk,
                "trust_score": ts.to_dict() if ts else None}

    @router.get("/governance/{agent_id}")
    async def get_governance(agent_id: str, limit: int = Query(default=50, ge=1, le=200),
                             payload: TokenPayload = Depends(require_auth)):
        timeline = gov_service.get_governance_timeline(agent_id, limit=limit)
        ts = gov_service.get_trust_score(agent_id)
        risk = gov_service.calculate_risk_level(agent_id)
        return {"agent_module_id": agent_id, "timeline": timeline,
                "trust_score": ts.to_dict() if ts else None, "risk_level": risk}

    # ─── Analytics ───

    @router.get("/analytics")
    async def get_analytics(payload: TokenPayload = Depends(require_auth)):
        return gov_service.get_analytics_dashboard()

    return router
