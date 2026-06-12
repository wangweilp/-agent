"""Developer API — /developers 端点。

端点：
- POST /developers/register              — 注册 Developer Account (JWT only)
- GET  /developers/me                    — 获取当前开发者信息
- PATCH /developers/me                   — 更新开发者信息 (JWT only)
- POST /developers/me/verify-request     — 邮箱验证请求（MVP）(JWT only)
- POST /developers/api-keys              — 创建 API Key (JWT only)
- GET  /developers/api-keys              — 列出 API Keys
- DELETE /developers/api-keys/{id}       — 撤销 API Key (JWT only)
- POST /developers/agents                — 创建 Agent Submission
- GET  /developers/agents                — 列出自己的 Submissions
- GET  /developers/agents/{id}           — 查看 Submission 详情
- PATCH /developers/agents/{id}          — 编辑 draft manifest
- POST /developers/agents/{id}/validate  — 校验 manifest
- POST /developers/agents/{id}/submit    — 提交审核
- POST /developers/agents/{id}/withdraw  — 撤回提交

权限模型：
- JWT only: register, create/revoke API key, patch profile, verify-request
- JWT or API Key: get-me, list-api-keys, get-submissions, create-submission, etc.
- API Key scopes 必须在创建时校验（allowlist + 禁止 forbidden）
- API Key 不能调用 admin API
- API Key 不能 publish

安全边界：
- raw_key 只在创建时返回一次
- key_hash 不出现在任何 API response
- developer 只能操作自己的 key / submission
- package_url 不执行
- developer API 不能 publish
- API Key 不能绕过 tenant isolation
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.adapters.developer_store import SQLiteDeveloperStore
from src.adapters.submission_store import SQLiteSubmissionStore
from src.adapters.usage_store import UsageStoreAdapter
from src.api.middleware import require_auth, get_token_payload, TokenPayload
from src.core.usage import UsageEvent, UsageResource, UsageUnit
from src.open_platform.api_auth import DeveloperApiPrincipal
from src.open_platform.developer import (
    ApiKeyScopeError,
    DeveloperAccount,
    DeveloperAlreadyExistsError,
    DeveloperApiKey,
    DeveloperStatus,
    DuplicateApiKeyError,
    generate_api_key,
    get_api_key_prefix,
    hash_api_key,
    validate_api_key_scopes,
    has_required_scopes,
)
from src.open_platform.simulation import SimulationRunRequest
from src.open_platform.submission import (
    AgentManifest,
    AgentSubmission,
    ManifestValidationError,
    SecurityProfile,
    SubmissionNotFoundError,
    SubmissionPermissionError,
    SubmissionStateError,
    SubmissionStatus,
    SubmissionSourceType,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# Request Models
# ═══════════════════════════════════════════


class DeveloperRegisterRequest(BaseModel):
    display_name: str = Field(default="", description="开发者展示名")
    organization_name: str | None = None
    website: str | None = None
    contact_email: str = Field(default="", description="联系邮箱")
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeveloperUpdateRequest(BaseModel):
    display_name: str | None = None
    organization_name: str | None = None
    website: str | None = None
    contact_email: str | None = None
    metadata: dict[str, Any] | None = None


class CreateApiKeyRequest(BaseModel):
    name: str = Field(default="", description="Key 名称")
    scopes: list[str] = Field(default_factory=list, description="权限范围")
    expires_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateSubmissionRequest(BaseModel):
    agent_manifest: dict[str, Any] = Field(default_factory=dict, description="Agent Manifest JSON")
    package_url: str | None = None
    source_type: str = "manifest"
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateSubmissionRequest(BaseModel):
    agent_manifest: dict[str, Any] | None = None
    package_url: str | None = None
    source_type: str | None = None
    metadata: dict[str, Any] | None = None


class SimulationRequest(BaseModel):
    input_text: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] | None = None


class ManifestValidateRequest(BaseModel):
    manifest: dict[str, Any] | None = None
    strict: bool = True


# ═══════════════════════════════════════════
# Internal Helpers
# ═══════════════════════════════════════════


def _get_dev(developer_store, payload: TokenPayload) -> DeveloperAccount:
    """获取当前用户的 developer account，未注册返回 None → 404。"""
    dev = developer_store.get_developer_by_user(payload.user_id, payload.workspace_id)
    if dev is None:
        raise HTTPException(status_code=404, detail="Developer account not found")
    if dev.status == DeveloperStatus.SUSPENDED:
        raise HTTPException(status_code=403, detail="Developer account is suspended")
    return dev


def _get_active_dev(developer_store, payload: TokenPayload) -> DeveloperAccount:
    """获取 active developer，否则 404/403。"""
    dev = _get_dev(developer_store, payload)
    if dev.status != DeveloperStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Developer account is not active")
    return dev


def _record_usage(
    usage_store, tenant_id: str, user_id: str, workspace_id: str,
    resource: UsageResource, metadata: dict[str, Any] | None = None,
) -> None:
    if usage_store is None:
        return
    try:
        event = UsageEvent(
            tenant_id=tenant_id,
            user_id=user_id,
            workspace_id=workspace_id,
            resource=resource,
            quantity=1,
            unit=UsageUnit.COUNT,
            metadata=metadata or {},
        )
        usage_store.record_event(event)
    except Exception:
        logger.warning("developer_api_usage_record_failed", exc_info=True,
                       extra={"resource": resource.value})


def _record_api_key_usage(
    usage_store, dev: DeveloperAccount, resource: UsageResource,
    metadata: dict[str, Any] | None = None,
) -> None:
    """API Key 路径的 usage 记录 — user_id 用 developer 关联的 user_id。"""
    _record_usage(usage_store, dev.tenant_id, dev.user_id, dev.tenant_id, resource, metadata)


def _manifest_from_dict(d: dict[str, Any]) -> AgentManifest:
    """从请求 dict 构建 AgentManifest，处理 security_profile 嵌套。"""
    sp = d.get("security_profile")
    security_profile = SecurityProfile.from_dict(sp) if isinstance(sp, dict) else None
    return AgentManifest(
        name=str(d.get("name", "")),
        display_name=str(d.get("display_name", "")),
        description=str(d.get("description", "")),
        version=str(d.get("version", "0.1.0")),
        capabilities=list(d.get("capabilities", [])),
        required_permissions=list(d.get("required_permissions", [])),
        supported_workflows=list(d.get("supported_workflows", [])),
        runtime_type=str(d.get("runtime_type", "manifest_only")),
        entrypoint=d.get("entrypoint"),
        config_schema=dict(d.get("config_schema", {})),
        usage_limits=dict(d.get("usage_limits", {})),
        security_profile=security_profile,
        metadata=dict(d.get("metadata", {})),
    )


# ═══════════════════════════════════════════
# Router Factory
# ═══════════════════════════════════════════


def create_developer_router(
    developer_store: SQLiteDeveloperStore,
    submission_store: SQLiteSubmissionStore,
    usage_store: UsageStoreAdapter | None = None,
    marketplace_store: Any = None,
    runtime_store: Any = None,
    simulation_service: Any = None,
) -> APIRouter:
    router = APIRouter(prefix="/developers", tags=["developers"])

    # ── API Key auth helper (closure over developer_store, usage_store) ──

    async def _try_api_key_auth(
        request: Request,
        required_scopes: list[str] | None = None,
    ) -> DeveloperApiPrincipal | None:
        """Try to authenticate via X-Cognitive-API-Key header.

        Returns None if header is absent or key is invalid.
        Raises 403 if developer suspended.
        Uses closure: developer_store, usage_store.
        """
        raw_key = request.headers.get("X-Cognitive-API-Key", "").strip()
        if not raw_key:
            return None

        # verify raw_key → lookup + hash + status/expire
        api_key = developer_store.verify_and_lookup_api_key(raw_key)
        if api_key is None:
            return None  # 不暴露 key 不存在/无效

        # lookup developer
        dev = developer_store.get_developer(api_key.developer_id)
        if dev is None:
            return None

        # developer must be active
        if dev.status != DeveloperStatus.ACTIVE:
            raise HTTPException(status_code=403, detail="Developer account is not active")

        # check scopes
        if required_scopes:
            if not has_required_scopes(api_key.scopes, required_scopes):
                raise HTTPException(
                    status_code=403,
                    detail={
                        "message": "Insufficient API key scope",
                        "required_scopes": required_scopes,
                    },
                )

        # record usage (best-effort, no raw_key in metadata)
        _safe_usage_dev_key(dev.tenant_id, dev.user_id, dev.tenant_id,
                            api_key.api_key_id, api_key.key_prefix,
                            request.url.path, request.method)

        logger.info("api_key_auth_success", extra={
            "developer_id": dev.developer_id,
            "api_key_id": api_key.api_key_id,
        })

        return DeveloperApiPrincipal(
            developer_id=dev.developer_id,
            user_id=dev.user_id,
            tenant_id=dev.tenant_id,
            api_key_id=api_key.api_key_id,
            key_prefix=api_key.key_prefix,
            scopes=list(api_key.scopes),
        )

    def _safe_usage_dev_key(
        tenant_id: str, user_id: str, ws: str,
        api_key_id: str, key_prefix: str, endpoint: str, method: str,
    ) -> None:
        if usage_store is None:
            return
        try:
            usage_store.record_event(UsageEvent(
                tenant_id=tenant_id, user_id=user_id, workspace_id=ws,
                resource=UsageResource.DEVELOPER_API_KEY_AUTH,
                quantity=1, unit=UsageUnit.COUNT,
                metadata={
                    "developer_id": tenant_id or "",
                    "api_key_id": api_key_id,
                    "key_prefix": key_prefix,
                    "auth_type": "developer_api_key",
                    "endpoint": str(endpoint),
                    "method": method,
                },
            ))
        except Exception:
            logger.warning("dev_api_key_usage_failed", exc_info=True)

    # ═══════════════════════════════════════════
    # Developer Account (JWT only)
    # ═══════════════════════════════════════════

    @router.post("/register", status_code=201)
    async def register_developer(
        body: DeveloperRegisterRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """注册为 Developer。JWT only。"""
        tenant_id = payload.workspace_id
        account = DeveloperAccount(
            user_id=payload.user_id,
            tenant_id=tenant_id,
            display_name=body.display_name,
            organization_name=body.organization_name,
            website=body.website,
            contact_email=body.contact_email,
            metadata=body.metadata,
        )
        try:
            created = developer_store.create_developer(account)
        except DeveloperAlreadyExistsError as e:
            raise HTTPException(status_code=409, detail=str(e))

        _record_usage(usage_store, tenant_id, payload.user_id, payload.workspace_id,
                       UsageResource.DEVELOPER_REGISTER,
                       {"developer_id": created.developer_id})

        logger.info("developer_registered", extra={"developer_id": created.developer_id, "user_id": payload.user_id})
        return {"developer": created.to_dict()}

    @router.get("/me")
    async def get_my_developer(
        request: Request,
        payload: TokenPayload | None = Depends(get_token_payload),
    ) -> dict[str, Any]:
        """获取当前用户的 Developer Profile。支持 JWT 或 API Key。"""
        # Try API Key first
        principal = await _try_api_key_auth(request, required_scopes=["developer:read"])
        if principal is not None:
            dev = developer_store.get_developer(principal.developer_id)
            if dev is None:
                raise HTTPException(status_code=404, detail="Developer account not found")
            return {"developer": dev.to_dict()}

        # Fallback to JWT
        if payload is None:
            raise HTTPException(status_code=401, detail="需要登录")
        dev = developer_store.get_developer_by_user(payload.user_id, payload.workspace_id)
        if dev is None:
            raise HTTPException(status_code=404, detail="Developer account not found")
        return {"developer": dev.to_dict()}

    @router.patch("/me")
    async def update_my_developer(
        body: DeveloperUpdateRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """更新自己的 Developer Profile（不能改 status/user_id/tenant_id/verified）。JWT only。"""
        dev = developer_store.get_developer_by_user(payload.user_id, payload.workspace_id)
        if dev is None:
            raise HTTPException(status_code=404, detail="Developer account not found")

        if body.display_name is not None:
            dev.display_name = body.display_name
        if body.organization_name is not None:
            dev.organization_name = body.organization_name
        if body.website is not None:
            dev.website = body.website
        if body.contact_email is not None:
            dev.contact_email = body.contact_email
        if body.metadata is not None:
            dev.metadata = {**dev.metadata, **body.metadata}

        developer_store.update_developer(dev)
        updated = developer_store.get_developer(dev.developer_id)
        return {"developer": updated.to_dict() if updated else None}

    @router.post("/me/verify-request")
    async def request_verification(
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """请求邮箱验证（MVP — 不发真实邮件）。JWT only。"""
        dev = developer_store.get_developer_by_user(payload.user_id, payload.workspace_id)
        if dev is None:
            raise HTTPException(status_code=404, detail="Developer account not found")
        return {
            "success": True,
            "message": "Verification request recorded. Email delivery is not implemented in MVP.",
        }

    # ═══════════════════════════════════════════
    # API Keys
    # ═══════════════════════════════════════════

    @router.post("/api-keys", status_code=201)
    async def create_api_key(
        body: CreateApiKeyRequest,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """创建 API Key — raw_key 仅此一次返回。JWT only。"""
        dev = _get_active_dev(developer_store, payload)

        if not body.scopes:
            raise HTTPException(status_code=422, detail="scopes 不能为空")

        # Validate scopes against allowlist/forbidden list
        validate_api_key_scopes(body.scopes)

        raw_key = generate_api_key()
        key_prefix = get_api_key_prefix(raw_key)
        key_hash = hash_api_key(raw_key)

        expires_at = None
        if body.expires_at:
            try:
                expires_at = datetime.fromisoformat(body.expires_at)
            except (ValueError, TypeError):
                raise HTTPException(status_code=422, detail="expires_at 格式无效，请使用 ISO 8601")

        api_key = DeveloperApiKey(
            developer_id=dev.developer_id,
            key_prefix=key_prefix,
            key_hash=key_hash,
            name=body.name,
            scopes=body.scopes,
            expires_at=expires_at,
            metadata=body.metadata,
        )

        try:
            created = developer_store.create_api_key(api_key)
        except ApiKeyScopeError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except DuplicateApiKeyError as e:
            raise HTTPException(status_code=500, detail="API Key 生成冲突，请重试")

        _record_usage(usage_store, dev.tenant_id, payload.user_id, payload.workspace_id,
                       UsageResource.DEVELOPER_API_KEY_CREATE,
                       {"api_key_id": created.api_key_id, "developer_id": dev.developer_id,
                        "name": body.name})

        # raw_key 只在本次响应返回，不写日志
        logger.info("api_key_created", extra={"api_key_id": created.api_key_id, "developer_id": dev.developer_id})
        return {
            "api_key": created.to_dict(),
            "raw_key": raw_key,
        }

    @router.get("/api-keys")
    async def list_api_keys(
        include_revoked: bool = Query(default=False),
        request: Request = None,  # type: ignore — FastAPI injects
        payload: TokenPayload | None = Depends(get_token_payload),
    ) -> dict[str, Any]:
        """列出 API Keys。支持 JWT 或 API Key。"""
        # Try API Key first
        principal = await _try_api_key_auth(request, required_scopes=["api_keys:read"])
        if principal is not None:
            keys = developer_store.list_api_keys(principal.developer_id, include_revoked=include_revoked)
            return {"api_keys": [k.to_dict() for k in keys], "total": len(keys)}

        # Fallback to JWT
        if payload is None:
            raise HTTPException(status_code=401, detail="需要登录")
        dev = _get_dev(developer_store, payload)
        keys = developer_store.list_api_keys(dev.developer_id, include_revoked=include_revoked)
        return {
            "api_keys": [k.to_dict() for k in keys],
            "total": len(keys),
        }

    @router.delete("/api-keys/{api_key_id}")
    async def revoke_api_key(
        api_key_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """撤销 API Key。JWT only。"""
        dev = _get_dev(developer_store, payload)
        ok = developer_store.revoke_api_key(api_key_id, dev.developer_id)
        if not ok:
            raise HTTPException(status_code=404, detail="API Key 不存在或不属于当前开发者")

        _record_usage(usage_store, dev.tenant_id, payload.user_id, payload.workspace_id,
                       UsageResource.DEVELOPER_API_KEY_REVOKE,
                       {"api_key_id": api_key_id, "developer_id": dev.developer_id})

        logger.info("api_key_revoked", extra={"api_key_id": api_key_id})
        return {"success": True}

    # ═══════════════════════════════════════════
    # Agent Submissions (JWT or API Key)
    # ═══════════════════════════════════════════

    @router.post("/agents", status_code=201)
    async def create_agent_submission(
        body: CreateSubmissionRequest,
        request: Request,
        payload: TokenPayload | None = Depends(get_token_payload),
    ) -> dict[str, Any]:
        """创建 Agent Submission。支持 JWT 或 API Key (submissions:write)。"""
        dev = await _resolve_dev_for_write(request, payload, ["submissions:write"])
        manifest = _manifest_from_dict(body.agent_manifest)
        result = manifest.validate()
        if not result.valid:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Manifest 校验失败",
                    "errors": result.errors,
                    "warnings": result.warnings,
                },
            )

        sub = AgentSubmission(
            developer_id=dev.developer_id,
            tenant_id=dev.tenant_id,
            agent_manifest=manifest,
            package_url=body.package_url,
            source_type=body.source_type,
            status=SubmissionStatus.DRAFT,
            metadata=body.metadata,
        )
        created = submission_store.create_submission(sub)

        _record_api_key_usage(usage_store, dev, UsageResource.AGENT_SUBMISSION_CREATE,
                              {"submission_id": created.submission_id, "developer_id": dev.developer_id})

        logger.info("agent_submission_created", extra={"submission_id": created.submission_id})
        return {"submission": created.to_dict()}

    @router.get("/agents")
    async def list_submissions(
        status: str = Query(default=""),
        include_withdrawn: bool = Query(default=False),
        request: Request = None,  # type: ignore
        payload: TokenPayload | None = Depends(get_token_payload),
    ) -> dict[str, Any]:
        """列出自己的 Submissions。支持 JWT 或 API Key (submissions:read)。"""
        dev = await _resolve_dev_for_read(request, payload, ["submissions:read"])
        subs = submission_store.list_submissions(developer_id=dev.developer_id, status=status)
        if not include_withdrawn:
            subs = [s for s in subs if s.status != SubmissionStatus.WITHDRAWN]
        return {"submissions": [s.to_dict() for s in subs], "total": len(subs)}

    @router.get("/agents/{submission_id}")
    async def get_submission(
        submission_id: str,
        request: Request,
        payload: TokenPayload | None = Depends(get_token_payload),
    ) -> dict[str, Any]:
        """查看 Submission 详情。支持 JWT 或 API Key (submissions:read)。"""
        dev = await _resolve_dev_for_read(request, payload, ["submissions:read"])
        sub = submission_store.get_submission(submission_id)
        if sub is None or sub.developer_id != dev.developer_id:
            raise HTTPException(status_code=404, detail="提交不存在")
        return {"submission": sub.to_dict()}

    @router.patch("/agents/{submission_id}")
    async def update_submission(
        submission_id: str,
        body: UpdateSubmissionRequest,
        request: Request,
        payload: TokenPayload | None = Depends(get_token_payload),
    ) -> dict[str, Any]:
        """编辑 draft manifest。支持 JWT 或 API Key (submissions:write)。"""
        dev = await _resolve_dev_for_write(request, payload, ["submissions:write"])
        sub = submission_store.get_submission(submission_id)
        if sub is None or sub.developer_id != dev.developer_id:
            raise HTTPException(status_code=404, detail="提交不存在")

        if sub.status != SubmissionStatus.DRAFT:
            raise HTTPException(status_code=409, detail="只有 draft 状态的提交可以编辑")

        if body.agent_manifest is not None:
            manifest = _manifest_from_dict(body.agent_manifest)
            result = manifest.validate()
            if not result.valid:
                raise HTTPException(
                    status_code=422,
                    detail={"message": "Manifest 校验失败", "errors": result.errors, "warnings": result.warnings},
                )
            sub.agent_manifest = manifest

        if body.package_url is not None:
            sub.package_url = body.package_url
        if body.source_type is not None:
            sub.source_type = body.source_type
        if body.metadata is not None:
            sub.metadata = {**sub.metadata, **body.metadata}

        submission_store.update_submission(sub)
        updated = submission_store.get_submission(submission_id)
        return {"submission": updated.to_dict() if updated else None}

    @router.post("/agents/{submission_id}/validate")
    async def validate_submission(
        submission_id: str,
        request: Request,
        payload: TokenPayload | None = Depends(get_token_payload),
    ) -> dict[str, Any]:
        """校验 manifest。支持 JWT 或 API Key (submissions:read)。"""
        dev = await _resolve_dev_for_read(request, payload, ["submissions:read"])
        sub = submission_store.get_submission(submission_id)
        if sub is None or sub.developer_id != dev.developer_id:
            raise HTTPException(status_code=404, detail="提交不存在")

        if sub.agent_manifest is None:
            return {"valid": False, "errors": ["Manifest 不能为空"], "warnings": []}

        result = sub.agent_manifest.validate()
        return {"valid": result.valid, "errors": result.errors, "warnings": result.warnings}

    @router.post("/agents/{submission_id}/submit")
    async def submit_submission(
        submission_id: str,
        request: Request,
        payload: TokenPayload | None = Depends(get_token_payload),
    ) -> dict[str, Any]:
        """提交审核。支持 JWT 或 API Key (submissions:submit)。"""
        dev = await _resolve_dev_for_write(request, payload, ["submissions:submit"])
        try:
            submission_store.submit_submission(submission_id, dev.developer_id)
        except SubmissionNotFoundError:
            raise HTTPException(status_code=404, detail="提交不存在")
        except SubmissionPermissionError:
            raise HTTPException(status_code=404, detail="提交不存在")
        except SubmissionStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except ManifestValidationError as e:
            raise HTTPException(status_code=422, detail={"message": str(e), "errors": e.validation_errors})

        _record_api_key_usage(usage_store, dev, UsageResource.AGENT_SUBMISSION_SUBMIT,
                              {"submission_id": submission_id, "developer_id": dev.developer_id})

        updated = submission_store.get_submission(submission_id)
        return {"submission": updated.to_dict() if updated else None}

    @router.post("/agents/{submission_id}/withdraw")
    async def withdraw_submission(
        submission_id: str,
        request: Request,
        payload: TokenPayload | None = Depends(get_token_payload),
    ) -> dict[str, Any]:
        """撤回提交。支持 JWT 或 API Key (submissions:write)。"""
        dev = await _resolve_dev_for_write(request, payload, ["submissions:write"])
        try:
            submission_store.withdraw_submission(submission_id, dev.developer_id)
        except SubmissionNotFoundError:
            raise HTTPException(status_code=404, detail="提交不存在")
        except SubmissionPermissionError:
            raise HTTPException(status_code=404, detail="提交不存在")
        except SubmissionStateError as e:
            raise HTTPException(status_code=409, detail=str(e))

        updated = submission_store.get_submission(submission_id)
        return {"submission": updated.to_dict() if updated else None}

    # ═══════════════════════════════════════════
    # Simulation Runtime (Step 23-D)
    # ═══════════════════════════════════════════

    @router.post("/marketplace-agents/{marketplace_agent_id}/simulate")
    async def simulate_developer_agent(
        marketplace_agent_id: str,
        body: SimulationRequest = SimulationRequest(),
        request: Request = None,  # type: ignore
        payload: TokenPayload | None = Depends(get_token_payload),
    ) -> dict[str, Any]:
        """运行 Developer Agent 安全仿真。

        支持 JWT 或 API Key (agent:simulate)。
        不执行第三方代码、不联网、不读写真实企业数据。
        返回 SimulationRunResult。
        """
        if simulation_service is None:
            raise HTTPException(status_code=501, detail="Simulation runtime not available")

        # Resolve auth: try API Key first with simulation scopes (either is sufficient)
        principal = await _try_api_key_auth(request)  # no required_scopes here
        if principal is not None:
            # Check simulation scope — either agent:simulate OR agent:execute:simulation
            sim_scopes = {"agent:simulate", "agent:execute:simulation"}
            if not (set(principal.scopes) & sim_scopes):
                raise HTTPException(
                    status_code=403,
                    detail={
                        "message": "Insufficient API key scope",
                        "required_scopes": ["agent:simulate"],
                    },
                )

        if principal is not None:
            # API Key path
            dev = developer_store.get_developer(principal.developer_id)
            if dev is None:
                raise HTTPException(status_code=401, detail="Invalid API Key")
            sim_req = SimulationRunRequest(
                marketplace_agent_id=marketplace_agent_id,
                tenant_id=dev.tenant_id,
                user_id=dev.user_id,
                developer_id=dev.developer_id,
                input_text=body.input_text,
                input_payload=body.input_payload,
                api_key_scopes=list(principal.scopes),
                auth_type="developer_api_key",
                metadata=body.metadata or {},
            )
        elif payload is not None:
            # JWT path
            dev = developer_store.get_developer_by_user(payload.user_id, payload.workspace_id)
            if dev is None:
                raise HTTPException(status_code=403, detail="Developer account not found")
            sim_req = SimulationRunRequest(
                marketplace_agent_id=marketplace_agent_id,
                tenant_id=dev.tenant_id,
                user_id=payload.user_id,
                developer_id=dev.developer_id,
                input_text=body.input_text,
                input_payload=body.input_payload,
                auth_type="jwt",
                metadata=body.metadata or {},
            )
        else:
            raise HTTPException(status_code=401, detail="需要登录")

        # Run simulation
        result = simulation_service.simulate_agent(sim_req, principal)
        return result.to_dict()

    # ═══════════════════════════════════════════
    # Manifest Schema & Validation (Step 23-H)
    # ═══════════════════════════════════════════

    @router.get("/agent-manifest/schema")
    async def get_manifest_schema(
        request: Request,
        payload: TokenPayload | None = Depends(get_token_payload),
    ) -> dict[str, Any]:
        """获取 Agent Manifest JSON Schema。支持 JWT 或 API Key (developer:read)。"""
        principal = await _try_api_key_auth(request, required_scopes=["developer:read"])
        if principal is None and payload is None:
            raise HTTPException(status_code=401, detail="需要登录")

        import json, os
        schema_path = os.path.join(os.path.dirname(__file__), "..", "..", "schemas", "cognitive-agent.schema.json")
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            schema = {"error": "Schema file not found"}

        return {
            "schema": schema,
            "version": "v1",
            "non_execution_guarantees": [
                "No package URL is downloaded. No entrypoint is executed.",
                "No network calls are made. Static metadata validation only.",
                "Runtime execution requires admin review + runtime binding + sandbox policy.",
                "Step 23 MVP supports manifest_only runtime type and simulation adapter only.",
            ],
        }

    @router.post("/agent-manifest/validate")
    async def validate_manifest(
        body: ManifestValidateRequest,
        request: Request,
        payload: TokenPayload | None = Depends(get_token_payload),
    ) -> dict[str, Any]:
        """静态校验 Agent Manifest。不创建 submission，不下载 package，不执行代码。支持 JWT 或 API Key (submissions:read)。"""
        from src.open_platform.manifest_validator import validate_manifest_dict as vm_validate

        principal = await _try_api_key_auth(request, required_scopes=["submissions:read"])
        if principal is None and payload is None:
            raise HTTPException(status_code=401, detail="需要登录")

        manifest = body.manifest or {}
        strict = body.strict if body.strict is not None else True
        result = vm_validate(manifest, strict)
        return result.to_dict()

    # ── Dual-auth resovers ──

    async def _resolve_dev_for_read(
        request: Request,
        payload: TokenPayload | None,
        scopes: list[str],
    ) -> DeveloperAccount:
        """Resolve DeveloperAccount for read endpoints. API Key or JWT."""
        principal = await _try_api_key_auth(request, required_scopes=scopes)
        if principal is not None:
            return _get_dev_by_id(developer_store, principal.developer_id)

        if payload is None:
            raise HTTPException(status_code=401, detail="需要登录")
        return _get_dev(developer_store, payload)

    async def _resolve_dev_for_write(
        request: Request,
        payload: TokenPayload | None,
        scopes: list[str],
    ) -> DeveloperAccount:
        """Resolve active DeveloperAccount for write endpoints. API Key or JWT."""
        principal = await _try_api_key_auth(request, required_scopes=scopes)
        if principal is not None:
            return _get_active_dev_by_id(developer_store, principal.developer_id)

        if payload is None:
            raise HTTPException(status_code=401, detail="需要登录")
        return _get_active_dev(developer_store, payload)

    return router


def _get_dev_by_id(developer_store, developer_id: str) -> DeveloperAccount:
    dev = developer_store.get_developer(developer_id)
    if dev is None:
        raise HTTPException(status_code=404, detail="Developer account not found")
    if dev.status == DeveloperStatus.SUSPENDED:
        raise HTTPException(status_code=403, detail="Developer account is suspended")
    return dev


def _get_active_dev_by_id(developer_store, developer_id: str) -> DeveloperAccount:
    dev = _get_dev_by_id(developer_store, developer_id)
    if dev.status != DeveloperStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Developer account is not active")
    return dev
