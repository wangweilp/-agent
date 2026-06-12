"""Admin Review API — /admin/agent-submissions 端点。

端点：
- GET  /admin/agent-submissions                              — 审核队列
- GET  /admin/agent-submissions/{id}                         — Submission 详情（含 developer / validation / review record）
- GET  /admin/agent-submissions/{id}/reviews                 — 审核记录
- POST /admin/agent-submissions/{id}/start-review            — 开始审核
- POST /admin/agent-submissions/{id}/approve                 — 通过
- POST /admin/agent-submissions/{id}/reject                  — 拒绝
- POST /admin/agent-submissions/{id}/request-changes         — 要求修改

权限模型：require_auth + admin/owner/super_admin
安全边界：
- member / viewer / normal developer → 403
- 跨 tenant → 404（super_admin 不受限）
- reviewer 不能自审 → 403
- invalid manifest 不能 approve → 422
- 不存在 publish endpoint
- 不创建 MarketplaceAgent
- package_url 不执行
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.adapters.developer_store import SQLiteDeveloperStore
from src.adapters.submission_store import SQLiteSubmissionStore
from src.adapters.usage_store import UsageStoreAdapter
from src.api.middleware import require_auth, TokenPayload
from src.core.usage import UsageEvent, UsageResource, UsageUnit
from src.open_platform.publish import build_marketplace_agent_from_submission
from src.open_platform.submission import (
    SubmissionNotFoundError,
    SubmissionStateError,
    SubmissionStatus,
    ManifestValidationError,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# Request Models
# ═══════════════════════════════════════════


class ReviewDecisionRequest(BaseModel):
    notes: str = Field(default="", description="审核备注")
    checklist: dict[str, Any] = Field(default_factory=dict, description="checklist")


class RejectRequest(BaseModel):
    notes: str = Field(..., min_length=1, description="拒绝理由（必填）")
    checklist: dict[str, Any] = Field(default_factory=dict)


class RequestChangesRequest(BaseModel):
    notes: str = Field(..., min_length=1, description="修改建议（必填）")
    checklist: dict[str, Any] = Field(default_factory=dict)


class ValidatePackageRequest(BaseModel):
    validation_options: dict[str, Any] | None = None


# ═══════════════════════════════════════════
# Internal Helpers
# ═══════════════════════════════════════════


def _is_admin(payload: TokenPayload) -> bool:
    if payload.is_super_admin:
        return True
    if payload.role and payload.role.value in ("owner", "admin", "org_admin", "super_admin"):
        return True
    return False


def _require_admin(payload: TokenPayload = Depends(require_auth)) -> TokenPayload:
    if not _is_admin(payload):
        raise HTTPException(status_code=403, detail="权限不足: 需要 admin 或以上角色")
    return payload


def _check_tenant(sub, payload: TokenPayload) -> None:
    """跨 tenant 检查。super_admin 放行。"""
    if payload.is_super_admin:
        return
    if sub.tenant_id != payload.workspace_id:
        raise HTTPException(status_code=404, detail="提交不存在")


def _get_submission_or_404(submission_store, submission_id: str, payload: TokenPayload):
    sub = submission_store.get_submission(submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="提交不存在")
    _check_tenant(sub, payload)
    return sub


def _check_not_self_review(sub, payload: TokenPayload, developer_store) -> None:
    """reviewer 不能审核自己的 submission。"""
    dev = developer_store.get_developer(sub.developer_id)
    if dev and dev.user_id == payload.user_id:
        raise HTTPException(status_code=403, detail="不能审核自己提交的 Agent")


def _record_usage(usage_store, tenant_id: str, user_id: str, ws: str,
                  resource: UsageResource, metadata: dict[str, Any] | None = None):
    if usage_store is None:
        return
    try:
        usage_store.record_event(UsageEvent(
            tenant_id=tenant_id, user_id=user_id, workspace_id=ws,
            resource=resource, quantity=1, unit=UsageUnit.COUNT,
            metadata=metadata or {},
        ))
    except Exception:
        logger.warning("admin_review_usage_record_failed", exc_info=True,
                       extra={"resource": resource.value})


# ═══════════════════════════════════════════
# Router Factory
# ═══════════════════════════════════════════


def create_admin_submission_router(
    developer_store: SQLiteDeveloperStore,
    submission_store: SQLiteSubmissionStore,
    usage_store: UsageStoreAdapter | None = None,
    marketplace_store: Any = None,
    pv_service: Any = None,
) -> APIRouter:
    router = APIRouter(prefix="/admin/agent-submissions", tags=["admin-agent-submissions"])

    # ═══════════════════════════════════════════
    # List queue
    # ═══════════════════════════════════════════

    @router.get("")
    async def list_submissions(
        status: str = Query(default=""),
        tenant_id: str = Query(default=""),
        developer_id: str = Query(default=""),
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        """审核队列。super_admin 可跨 tenant。"""
        effective_tenant = tenant_id if tenant_id and payload.is_super_admin else payload.workspace_id

        subs = submission_store.list_submissions(
            tenant_id=effective_tenant,
            status=status,
            developer_id=developer_id,
        )
        return {"submissions": [s.to_dict() for s in subs], "total": len(subs)}

    # ═══════════════════════════════════════════
    # Detail
    # ═══════════════════════════════════════════

    @router.get("/{submission_id}")
    async def get_submission_detail(
        submission_id: str,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        sub = _get_submission_or_404(submission_store, submission_id, payload)

        # Validation
        validation = {"valid": True, "errors": [], "warnings": []}
        if sub.agent_manifest:
            result = sub.agent_manifest.validate()
            validation = {"valid": result.valid, "errors": result.errors, "warnings": result.warnings}

        # Developer profile
        developer = None
        dev = developer_store.get_developer(sub.developer_id)
        if dev:
            developer = dev.to_dict()

        # Latest review record
        latest_review = submission_store.get_latest_review_record(submission_id)

        return {
            "submission": sub.to_dict(),
            "developer": developer,
            "validation": validation,
            "latest_review_record": latest_review.to_dict() if latest_review else None,
        }

    # ═══════════════════════════════════════════
    # Review records
    # ═══════════════════════════════════════════

    @router.get("/{submission_id}/reviews")
    async def list_reviews(
        submission_id: str,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        sub = _get_submission_or_404(submission_store, submission_id, payload)
        records = submission_store.list_review_records(submission_id)
        return {"reviews": [r.to_dict() for r in records], "total": len(records)}

    # ═══════════════════════════════════════════
    # Start review
    # ═══════════════════════════════════════════

    @router.post("/{submission_id}/start-review")
    async def start_review(
        submission_id: str,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        sub = _get_submission_or_404(submission_store, submission_id, payload)
        try:
            submission_store.start_review(submission_id, payload.user_id)
        except SubmissionStateError as e:
            raise HTTPException(status_code=409, detail=str(e))

        _record_usage(usage_store, sub.tenant_id, payload.user_id, payload.workspace_id,
                       UsageResource.AGENT_SUBMISSION_REVIEW,
                       {"submission_id": submission_id, "developer_id": sub.developer_id,
                        "reviewer_id": payload.user_id, "decision": "start_review",
                        "previous_status": SubmissionStatus.SUBMITTED if sub.status == SubmissionStatus.SUBMITTED else sub.status})

        updated = submission_store.get_submission(submission_id)
        return {"submission": updated.to_dict() if updated else None}

    # ═══════════════════════════════════════════
    # Approve
    # ═══════════════════════════════════════════

    @router.post("/{submission_id}/approve")
    async def approve_submission(
        submission_id: str,
        body: ReviewDecisionRequest = ReviewDecisionRequest(),
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        sub = _get_submission_or_404(submission_store, submission_id, payload)
        _check_not_self_review(sub, payload, developer_store)

        # Manifest must be valid
        if sub.agent_manifest:
            result = sub.agent_manifest.validate()
            if not result.valid:
                raise HTTPException(
                    status_code=422,
                    detail={"message": "Manifest 校验失败，不能通过审核", "errors": result.errors},
                )
            if result.warnings:
                raise HTTPException(
                    status_code=422,
                    detail={"message": "存在安全警告，不能通过审核", "warnings": result.warnings},
                )

        try:
            submission_store.approve_submission(
                submission_id, payload.user_id, body.notes, body.checklist,
            )
        except SubmissionStateError as e:
            raise HTTPException(status_code=409, detail=str(e))

        _record_usage(usage_store, sub.tenant_id, payload.user_id, payload.workspace_id,
                       UsageResource.AGENT_SUBMISSION_REVIEW,
                       {"submission_id": submission_id, "developer_id": sub.developer_id,
                        "reviewer_id": payload.user_id, "decision": "approve"})

        logger.info("agent_submission_approved", extra={
            "submission_id": submission_id, "reviewer_id": payload.user_id,
            "developer_id": sub.developer_id,
        })
        updated = submission_store.get_submission(submission_id)
        return {"submission": updated.to_dict() if updated else None}

    # ═══════════════════════════════════════════
    # Reject
    # ═══════════════════════════════════════════

    @router.post("/{submission_id}/reject")
    async def reject_submission(
        submission_id: str,
        body: RejectRequest,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        sub = _get_submission_or_404(submission_store, submission_id, payload)
        _check_not_self_review(sub, payload, developer_store)

        try:
            submission_store.reject_submission(
                submission_id, payload.user_id, body.notes, body.checklist,
            )
        except SubmissionStateError as e:
            raise HTTPException(status_code=409, detail=str(e))

        _record_usage(usage_store, sub.tenant_id, payload.user_id, payload.workspace_id,
                       UsageResource.AGENT_SUBMISSION_REVIEW,
                       {"submission_id": submission_id, "developer_id": sub.developer_id,
                        "reviewer_id": payload.user_id, "decision": "reject"})

        logger.info("agent_submission_rejected", extra={
            "submission_id": submission_id, "reviewer_id": payload.user_id,
        })
        updated = submission_store.get_submission(submission_id)
        return {"submission": updated.to_dict() if updated else None}

    # ═══════════════════════════════════════════
    # Request changes
    # ═══════════════════════════════════════════

    @router.post("/{submission_id}/request-changes")
    async def request_changes(
        submission_id: str,
        body: RequestChangesRequest,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        sub = _get_submission_or_404(submission_store, submission_id, payload)
        _check_not_self_review(sub, payload, developer_store)

        try:
            submission_store.request_changes(
                submission_id, payload.user_id, body.notes, body.checklist,
            )
        except SubmissionStateError as e:
            raise HTTPException(status_code=409, detail=str(e))

        _record_usage(usage_store, sub.tenant_id, payload.user_id, payload.workspace_id,
                       UsageResource.AGENT_SUBMISSION_REVIEW,
                       {"submission_id": submission_id, "developer_id": sub.developer_id,
                        "reviewer_id": payload.user_id, "decision": "request_changes"})

        logger.info("agent_submission_changes_requested", extra={
            "submission_id": submission_id, "reviewer_id": payload.user_id,
        })
        updated = submission_store.get_submission(submission_id)
        return {"submission": updated.to_dict() if updated else None}

    # ═══════════════════════════════════════════
    # Publish
    # ═══════════════════════════════════════════

    @router.post("/{submission_id}/publish")
    async def publish_submission(
        submission_id: str,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        """将 approved submission 发布到 Agent Marketplace。

        - 创建 MarketplaceAgent (publisher_type=developer)
        - 更新 submission status=published
        - 不执行 package_url / 不注册 Runtime / 不创建 Installation
        """
        sub = _get_submission_or_404(submission_store, submission_id, payload)
        _check_not_self_review(sub, payload, developer_store)

        if sub.status != SubmissionStatus.APPROVED:
            raise HTTPException(status_code=409, detail="只有 approved 状态的提交可以发布")

        if sub.agent_manifest is None:
            raise HTTPException(status_code=422, detail="Manifest 不能为空")

        result = sub.agent_manifest.validate()
        if not result.valid:
            raise HTTPException(
                status_code=422,
                detail={"message": "Manifest 校验失败，无法发布", "errors": result.errors},
            )
        if result.warnings:
            raise HTTPException(
                status_code=422,
                detail={"message": "存在安全警告，无法发布", "warnings": result.warnings},
            )

        # Check already published (idempotent check)
        if sub.marketplace_agent_id and sub.status == SubmissionStatus.PUBLISHED:
            raise HTTPException(status_code=409, detail="该提交已发布")

        # Build MarketplaceAgent
        dev = developer_store.get_developer(sub.developer_id)
        try:
            marketplace_agent = build_marketplace_agent_from_submission(sub, dev)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        # Create MarketplaceAgent via marketplace_store
        created_agent = None
        if marketplace_store is not None:
            try:
                existing = marketplace_store.get_agent(marketplace_agent.marketplace_agent_id)
                if existing is not None:
                    raise HTTPException(status_code=409, detail=f"MarketplaceAgent {marketplace_agent.marketplace_agent_id} 已存在")
                created_agent = marketplace_store.create_agent(marketplace_agent)
            except Exception as e:
                if "409" in str(e) or "已存在" in str(e):
                    raise HTTPException(status_code=409, detail=str(e))
                logger.exception("marketplace_agent_create_failed")
                raise HTTPException(status_code=500, detail="创建 MarketplaceAgent 失败")

        # Update submission
        mkp_id = created_agent.marketplace_agent_id if created_agent else marketplace_agent.marketplace_agent_id
        submission_store.publish_submission(submission_id, mkp_id)

        _record_usage(usage_store, sub.tenant_id, payload.user_id, payload.workspace_id,
                       UsageResource.AGENT_SUBMISSION_PUBLISH,
                       {"submission_id": submission_id, "developer_id": sub.developer_id,
                        "marketplace_agent_id": mkp_id,
                        "publisher_user_id": payload.user_id,
                        "manifest_name": sub.agent_manifest.name,
                        "manifest_version": sub.agent_manifest.version,
                        "publisher_type": "developer"})

        logger.info("agent_submission_published", extra={
            "submission_id": submission_id,
            "marketplace_agent_id": mkp_id,
            "publisher_user_id": payload.user_id,
        })

        updated = submission_store.get_submission(submission_id)
        return {
            "success": True,
            "submission": updated.to_dict() if updated else None,
            "marketplace_agent": created_agent.to_dict() if created_agent else None,
            "message": "Submission published to Marketplace as developer agent.",
        }

    # ═══════════════════════════════════════════
    # Package Validation (Step 23-F)
    # ═══════════════════════════════════════════

    @router.post("/{submission_id}/validate-package")
    async def validate_submission_package(
        submission_id: str,
        body: ValidatePackageRequest = ValidatePackageRequest(),
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        sub = _get_submission_or_404(submission_store, submission_id, payload)
        if pv_service is None:
            raise HTTPException(status_code=501, detail="Package validation not available")
        try:
            result = pv_service.validate_submission_package(
                submission_id, payload.user_id, sub.tenant_id,
                options=body.validation_options,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return result.to_dict()

    @router.get("/{submission_id}/package-validation")
    async def get_latest_package_validation(
        submission_id: str,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        sub = _get_submission_or_404(submission_store, submission_id, payload)
        if pv_service is None:
            return {"validation": None}
        latest = pv_service.get_latest_validation(submission_id)
        return {"validation": latest.to_dict() if latest else None}

    return router
