"""Admin Sandbox Policy API — /admin/sandbox-policies 端点。

端点:
- GET    /admin/sandbox-policies              — 浏览 policies
- GET    /admin/sandbox-policies/{id}          — Policy 详情
- POST   /admin/sandbox-policies              — 创建 policy
- PATCH  /admin/sandbox-policies/{id}          — 更新 policy
- POST   /admin/sandbox-policies/{id}/test     — 测试 policy（静态）
- POST   /admin/sandbox-policies/{id}/enable   — 启用
- POST   /admin/sandbox-policies/{id}/disable  — 停用
- POST   /admin/runtime-bindings/{id}/sandbox-policy — 绑定 policy 到 binding

权限: require_auth + admin/owner/super_admin
API Key 禁止。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.middleware import require_auth, TokenPayload
from src.core.usage import UsageEvent, UsageResource, UsageUnit

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# Permission helpers
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


# ═══════════════════════════════════════════
# Request Models
# ═══════════════════════════════════════════

class CreatePolicyRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    sandbox_level: str = "no_execution"
    allow_network: bool = False
    allowed_domains: list[str] = Field(default_factory=list)
    allow_filesystem_read: bool = False
    allow_filesystem_write: bool = False
    allowed_paths: list[str] = Field(default_factory=list)
    allow_secrets: bool = False
    allowed_secret_names: list[str] = Field(default_factory=list)
    max_timeout_ms: int = 0
    max_memory_mb: int = 0
    max_cpu_percent: int = 0
    max_output_bytes: int = 0
    max_requests_per_minute: int = 0
    data_access_scope: list[str] = Field(default_factory=list)
    audit_enabled: bool = True
    kill_switch_enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdatePolicyRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    allow_network: bool | None = None
    allowed_domains: list[str] | None = None
    allow_filesystem_read: bool | None = None
    allow_filesystem_write: bool | None = None
    allowed_paths: list[str] | None = None
    allow_secrets: bool | None = None
    allowed_secret_names: list[str] | None = None
    max_timeout_ms: int | None = None
    max_memory_mb: int | None = None
    max_cpu_percent: int | None = None
    max_output_bytes: int | None = None
    max_requests_per_minute: int | None = None
    data_access_scope: list[str] | None = None
    audit_enabled: bool | None = None
    kill_switch_enabled: bool | None = None
    metadata: dict[str, Any] | None = None


class PolicyTestRequest(BaseModel):
    sandbox_level: str = "no_execution"
    requested_network: bool = False
    requested_domains: list[str] = Field(default_factory=list)
    requested_filesystem_read: bool = False
    requested_filesystem_write: bool = False
    requested_secret_names: list[str] = Field(default_factory=list)
    requested_timeout_ms: int = 0
    requested_memory_mb: int = 0
    requested_data_access_scope: list[str] = Field(default_factory=list)


class AssignPolicyRequest(BaseModel):
    sandbox_policy_id: str = Field(..., min_length=1)


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════

def _check_tenant_access(policy, payload: TokenPayload) -> None:
    """验证 admin 能访问该 policy。super_admin 放行。"""
    if payload.is_super_admin:
        return
    if policy.scope == "system":
        return  # admin can read system policies
    if policy.tenant_id != payload.workspace_id:
        raise HTTPException(status_code=404, detail="Policy 不存在")


def _check_tenant_write(policy, payload: TokenPayload) -> None:
    """验证 admin 能修改该 policy。"""
    if payload.is_super_admin:
        return
    if policy.scope == "system":
        raise HTTPException(status_code=403, detail="不能修改 system policy")
    if policy.tenant_id != payload.workspace_id:
        raise HTTPException(status_code=404, detail="Policy 不存在")


def _try_record_usage(usage_store, tenant_id, user_id, ws, resource, metadata=None):
    if usage_store is None:
        return
    try:
        usage_store.record_event(UsageEvent(
            tenant_id=tenant_id, user_id=user_id, workspace_id=ws,
            resource=resource, quantity=1, unit=UsageUnit.COUNT,
            metadata=metadata or {},
        ))
    except Exception:
        logger.warning("sp_usage_record_failed", exc_info=True, extra={"resource": resource.value})


# ═══════════════════════════════════════════
# Router Factory
# ═══════════════════════════════════════════

def create_sandbox_policy_router(
    sandbox_policy_store,
    runtime_store=None,
    usage_store=None,
) -> APIRouter:
    router = APIRouter(prefix="/admin/sandbox-policies", tags=["admin-sandbox-policies"])

    # ── List ──

    @router.get("")
    async def list_policies(
        status: str = Query(default=""),
        scope: str = Query(default=""),
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        tn = "" if payload.is_super_admin else payload.workspace_id
        policies = sandbox_policy_store.list_policies(
            tenant_id=tn, scope=scope, status=status, include_system=True,
        )
        return {"policies": [p.to_dict() for p in policies], "total": len(policies)}

    # ── Detail ──

    @router.get("/{policy_id}")
    async def get_policy(
        policy_id: str,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        policy = sandbox_policy_store.get_policy(policy_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="Policy 不存在")
        _check_tenant_access(policy, payload)
        return {"policy": policy.to_dict()}

    # ── Create ──

    @router.post("", status_code=201)
    async def create_policy(
        body: CreatePolicyRequest,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        from src.open_platform.sandbox_policy import (
            SandboxPolicy, SandboxPolicyScope, SandboxPolicyValidationError,
            SandboxPolicyAlreadyExistsError,
        )

        is_super = payload.is_super_admin
        scope = SandboxPolicyScope.TENANT
        tenant_id = payload.workspace_id
        system_managed = False
        if is_super and tenant_id == payload.workspace_id:
            # super_admin can optionally create system scope
            pass

        policy = SandboxPolicy(
            name=body.name,
            description=body.description,
            scope=scope,
            tenant_id=tenant_id,
            sandbox_level=body.sandbox_level,
            allow_network=body.allow_network,
            allowed_domains=list(body.allowed_domains),
            allow_filesystem_read=body.allow_filesystem_read,
            allow_filesystem_write=body.allow_filesystem_write,
            allowed_paths=list(body.allowed_paths),
            allow_secrets=body.allow_secrets,
            allowed_secret_names=list(body.allowed_secret_names),
            max_timeout_ms=body.max_timeout_ms,
            max_memory_mb=body.max_memory_mb,
            max_cpu_percent=body.max_cpu_percent,
            max_output_bytes=body.max_output_bytes,
            max_requests_per_minute=body.max_requests_per_minute,
            data_access_scope=list(body.data_access_scope),
            audit_enabled=body.audit_enabled,
            kill_switch_enabled=body.kill_switch_enabled,
            system_managed=system_managed,
            created_by=payload.user_id,
            metadata=body.metadata or {},
        )
        try:
            created = sandbox_policy_store.create_policy(policy)
        except SandboxPolicyValidationError as e:
            raise HTTPException(status_code=422, detail={"message": str(e), "errors": e.errors})
        except SandboxPolicyAlreadyExistsError as e:
            raise HTTPException(status_code=409, detail=str(e))

        _try_record_usage(usage_store, payload.workspace_id, payload.user_id, payload.workspace_id,
                          UsageResource.SANDBOX_POLICY_CREATE,
                          {"policy_id": created.policy_id, "scope": scope, "sandbox_level": body.sandbox_level})
        logger.info("sp_created", extra={"policy_id": created.policy_id})
        return {"policy": created.to_dict()}

    # ── Update ──

    @router.patch("/{policy_id}")
    async def update_policy(
        policy_id: str,
        body: UpdatePolicyRequest,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        from src.open_platform.sandbox_policy import (
            SandboxPolicyValidationError, SandboxPolicyNotFoundError,
        )

        policy = sandbox_policy_store.get_policy(policy_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="Policy 不存在")
        _check_tenant_write(policy, payload)

        if body.name is not None: policy.name = body.name
        if body.description is not None: policy.description = body.description
        if body.allow_network is not None: policy.allow_network = body.allow_network
        if body.allowed_domains is not None: policy.allowed_domains = body.allowed_domains
        if body.allow_filesystem_read is not None: policy.allow_filesystem_read = body.allow_filesystem_read
        if body.allow_filesystem_write is not None: policy.allow_filesystem_write = body.allow_filesystem_write
        if body.allowed_paths is not None: policy.allowed_paths = body.allowed_paths
        if body.allow_secrets is not None: policy.allow_secrets = body.allow_secrets
        if body.allowed_secret_names is not None: policy.allowed_secret_names = body.allowed_secret_names
        if body.max_timeout_ms is not None: policy.max_timeout_ms = body.max_timeout_ms
        if body.max_memory_mb is not None: policy.max_memory_mb = body.max_memory_mb
        if body.max_cpu_percent is not None: policy.max_cpu_percent = body.max_cpu_percent
        if body.max_output_bytes is not None: policy.max_output_bytes = body.max_output_bytes
        if body.max_requests_per_minute is not None: policy.max_requests_per_minute = body.max_requests_per_minute
        if body.data_access_scope is not None: policy.data_access_scope = body.data_access_scope
        if body.audit_enabled is not None: policy.audit_enabled = body.audit_enabled
        if body.kill_switch_enabled is not None: policy.kill_switch_enabled = body.kill_switch_enabled
        if body.metadata is not None: policy.metadata = {**policy.metadata, **body.metadata}
        policy.updated_by = payload.user_id

        try:
            sandbox_policy_store.update_policy(policy)
        except SandboxPolicyValidationError as e:
            raise HTTPException(status_code=422, detail={"message": str(e), "errors": e.errors})
        except SandboxPolicyNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

        updated = sandbox_policy_store.get_policy(policy_id)
        _try_record_usage(usage_store, payload.workspace_id, payload.user_id, payload.workspace_id,
                          UsageResource.SANDBOX_POLICY_UPDATE,
                          {"policy_id": policy_id})
        return {"policy": updated.to_dict() if updated else None}

    # ── Test ──

    @router.post("/{policy_id}/test")
    async def test_policy(
        policy_id: str,
        body: PolicyTestRequest,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        policy = sandbox_policy_store.get_policy(policy_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="Policy 不存在")
        _check_tenant_access(policy, payload)

        from src.open_platform.sandbox_policy import SandboxPolicyTestRequest
        req = SandboxPolicyTestRequest(
            sandbox_level=body.sandbox_level,
            requested_network=body.requested_network,
            requested_domains=list(body.requested_domains),
            requested_filesystem_read=body.requested_filesystem_read,
            requested_filesystem_write=body.requested_filesystem_write,
            requested_secret_names=list(body.requested_secret_names),
            requested_timeout_ms=body.requested_timeout_ms,
            requested_memory_mb=body.requested_memory_mb,
            requested_data_access_scope=list(body.requested_data_access_scope),
        )
        result = sandbox_policy_store.test_policy(policy_id, req)

        _try_record_usage(usage_store, payload.workspace_id, payload.user_id, payload.workspace_id,
                          UsageResource.SANDBOX_POLICY_TEST,
                          {"policy_id": policy_id, "decision": result.decision})
        return result.to_dict()

    # ── Enable / Disable ──

    @router.post("/{policy_id}/enable")
    async def enable_policy(
        policy_id: str,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        from src.open_platform.sandbox_policy import SandboxPolicyStatus, SandboxPolicyPermissionError
        policy = sandbox_policy_store.get_policy(policy_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="Policy 不存在")
        _check_tenant_write(policy, payload)
        if policy.system_managed:
            raise SandboxPolicyPermissionError("system_managed policy 不允许 enable/disable")
        ok = sandbox_policy_store.set_policy_status(policy_id, SandboxPolicyStatus.ACTIVE, payload.user_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Policy 不存在")
        return {"success": True}

    @router.post("/{policy_id}/disable")
    async def disable_policy(
        policy_id: str,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        from src.open_platform.sandbox_policy import SandboxPolicyStatus, SandboxPolicyPermissionError
        policy = sandbox_policy_store.get_policy(policy_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="Policy 不存在")
        _check_tenant_write(policy, payload)
        if policy.system_managed:
            raise HTTPException(status_code=403, detail="system_managed policy 不允许 disable")
        ok = sandbox_policy_store.set_policy_status(policy_id, SandboxPolicyStatus.DISABLED, payload.user_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Policy 不存在")
        return {"success": True}

    # ── Runtime Binding Policy Assignment ──

    @router.post("/bindings/{binding_id}/assign")
    async def assign_policy_to_binding(
        binding_id: str,
        body: AssignPolicyRequest,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        if runtime_store is None:
            raise HTTPException(status_code=501, detail="Runtime store not available")

        from src.open_platform.runtime import RuntimeBindingNotFoundError
        binding = runtime_store.get_binding(binding_id)
        if binding is None:
            raise HTTPException(status_code=404, detail="Runtime Binding 不存在")

        # tenant check: admin can only assign to own tenant binding
        if not payload.is_super_admin and binding.tenant_id != payload.workspace_id:
            raise HTTPException(status_code=404, detail="Runtime Binding 不存在")

        # policy must exist
        policy = sandbox_policy_store.get_policy(body.sandbox_policy_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="Sandbox Policy 不存在")

        # policy scope check
        if not payload.is_super_admin:
            if policy.scope == "tenant" and policy.tenant_id != payload.workspace_id:
                raise HTTPException(status_code=404, detail="Sandbox Policy 不存在")

        # assign
        try:
            runtime_store.set_binding_sandbox_policy(binding_id, body.sandbox_policy_id)
        except RuntimeBindingNotFoundError:
            raise HTTPException(status_code=404, detail="Runtime Binding 不存在")

        # Does NOT enable binding — assignment != execution
        updated = runtime_store.get_binding(binding_id)
        _try_record_usage(usage_store, payload.workspace_id, payload.user_id, payload.workspace_id,
                          UsageResource.SANDBOX_POLICY_ASSIGN,
                          {"binding_id": binding_id, "sandbox_policy_id": body.sandbox_policy_id})

        logger.info("sp_assigned", extra={"binding_id": binding_id, "policy_id": body.sandbox_policy_id})
        return {
            "success": True,
            "binding": updated.to_dict() if updated else None,
            "message": "Policy assigned. Does NOT enable runtime binding.",
        }

    return router
