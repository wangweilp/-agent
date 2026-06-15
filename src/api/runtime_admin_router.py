"""Runtime Admin API — /admin/runtime 端点。

Step 23-G MVP:
- Runtime Adapter 列表
- Runtime Binding CRUD + enable/disable/suspend
- Sandbox Policy assignment to binding
- Runtime Eligibility 查询
- 权限: require_auth + admin/owner/super_admin
- API Key 禁止
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.middleware import require_auth, TokenPayload
from src.core.usage import UsageEvent, UsageResource, UsageUnit
from src.open_platform.runtime_governance_summary import build_runtime_governance_summary

logger = logging.getLogger(__name__)


def _is_admin(payload: TokenPayload) -> bool:
    if payload.is_super_admin: return True
    if payload.role and payload.role.value in ("owner", "admin", "org_admin", "super_admin"): return True
    return False

def _require_admin(payload: TokenPayload = Depends(require_auth)) -> TokenPayload:
    if not _is_admin(payload):
        raise HTTPException(status_code=403, detail="需要 admin 或以上角色")
    return payload


class CreateBindingRequest(BaseModel):
    marketplace_agent_id: str = Field(..., min_length=1)
    adapter_id: str = Field(default="rtadp_simulation")
    sandbox_policy_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class AssignPolicyRequest(BaseModel):
    sandbox_policy_id: str = Field(..., min_length=1)


def _try_usage(usage_store, tenant_id, user_id, resource, metadata=None):
    if usage_store is None: return
    try:
        usage_store.record_event(UsageEvent(tenant_id=tenant_id, user_id=user_id, workspace_id=tenant_id,
                                             resource=resource, quantity=1, unit=UsageUnit.COUNT,
                                             metadata=metadata or {}))
    except Exception:
        logger.warning("runtime_admin_usage_failed", exc_info=True, extra={"resource": resource.value})


def create_runtime_admin_router(
    runtime_store,
    marketplace_store=None,
    sandbox_policy_store=None,
    usage_store=None,
    runtime_safety_store=None,
    package_download_worker_store=None,
    artifact_materialization_store=None,
    sandbox_execution_store=None,
    production_sandbox_gate_store=None,
) -> APIRouter:
    router = APIRouter(prefix="/admin/runtime", tags=["admin-runtime"])

    # ── Adapters ──

    @router.get("/adapters")
    async def list_adapters(
        status: str = Query(default=""),
        adapter_type: str = Query(default=""),
        mvp_only: bool = Query(default=False),
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        adapters = runtime_store.list_adapters(status=status, mvp_only=mvp_only)
        if adapter_type:
            adapters = [a for a in adapters if a.adapter_type == adapter_type]
        return {"adapters": [a.to_dict() for a in adapters], "total": len(adapters)}

    # ── Bindings list ──

    @router.get("/bindings")
    async def list_bindings(
        tenant_id: str = Query(default=""),
        developer_id: str = Query(default=""),
        marketplace_agent_id: str = Query(default=""),
        runtime_status: str = Query(default=""),
        adapter_type: str = Query(default=""),
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        tn = tenant_id if tenant_id and payload.is_super_admin else (payload.workspace_id or "")
        bindings = runtime_store.list_bindings(
            tenant_id=tn, developer_id=developer_id, runtime_status=runtime_status,
            adapter_type=adapter_type)
        if marketplace_agent_id:
            bindings = [b for b in bindings if b.marketplace_agent_id == marketplace_agent_id]
        return {"bindings": [b.to_dict() for b in bindings], "total": len(bindings)}

    # ── Create binding ──

    @router.post("/bindings", status_code=201)
    async def create_binding(
        body: CreateBindingRequest,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        from src.agents.marketplace import PublisherType
        from src.open_platform.runtime import (
            DeveloperAgentRuntimeBinding, RuntimeBindingStatus,
            RuntimeAdapterNotFoundError, RuntimeBindingAlreadyExistsError,
            RuntimeAdapterNotAllowedError,
        )

        # verify marketplace agent exists and is developer
        if marketplace_store:
            agent = marketplace_store.get_agent(body.marketplace_agent_id)
            if agent is None:
                raise HTTPException(status_code=404, detail="Marketplace Agent 不存在")
            if getattr(agent, "publisher_type", "") != PublisherType.DEVELOPER:
                raise HTTPException(status_code=400, detail="只能为 developer agent 创建 runtime binding")

        tenant_id = payload.workspace_id

        binding = DeveloperAgentRuntimeBinding(
            marketplace_agent_id=body.marketplace_agent_id,
            developer_id=agent.metadata.get("developer_id", "") if marketplace_store and (agent := marketplace_store.get_agent(body.marketplace_agent_id)) else "",
            tenant_id=tenant_id,
            adapter_id=body.adapter_id,
            adapter_type="simulation" if "simulation" in body.adapter_id else "manifest_only",
            runtime_status=RuntimeBindingStatus.PENDING,
            sandbox_policy_id=body.sandbox_policy_id,
            metadata=body.metadata,
        )
        # Fix adapter_type from actual adapter
        adapter = runtime_store.get_adapter(body.adapter_id)
        if adapter:
            binding.adapter_type = adapter.adapter_type
        else:
            raise HTTPException(status_code=404, detail="Runtime Adapter 不存在")

        try:
            created = runtime_store.create_binding(binding)
        except RuntimeBindingAlreadyExistsError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except RuntimeAdapterNotAllowedError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except RuntimeAdapterNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

        _try_usage(usage_store, tenant_id, payload.user_id, UsageResource.AGENT_SUBMISSION_REVIEW,
                    {"binding_id": created.binding_id, "action": "create"})
        logger.info("runtime_binding_created", extra={"binding_id": created.binding_id, "tenant_id": tenant_id})
        return {"binding": created.to_dict(), "message": "Binding created (pending). Does NOT enable execution."}

    # ── Get binding detail ──

    @router.get("/bindings/{binding_id}")
    async def get_binding_detail(
        binding_id: str,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        binding = runtime_store.get_binding(binding_id)
        if binding is None:
            raise HTTPException(status_code=404, detail="Runtime Binding 不存在")
        if not payload.is_super_admin and binding.tenant_id != payload.workspace_id:
            raise HTTPException(status_code=404, detail="Runtime Binding 不存在")

        eligibility = runtime_store.get_runtime_eligibility(binding.marketplace_agent_id, binding.tenant_id)
        adapter_dict = None
        adapter = runtime_store.get_adapter(binding.adapter_id)
        if adapter:
            adapter_dict = adapter.to_dict()

        return {
            "binding": binding.to_dict(),
            "adapter": adapter_dict,
            "eligibility": eligibility.to_dict(),
        }

    # ── Enable ──

    @router.post("/bindings/{binding_id}/enable")
    async def enable_binding(
        binding_id: str,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        from src.open_platform.runtime import (
            RuntimeBindingNotFoundError, RuntimeAdapterNotAllowedError, RuntimeStateError,
        )
        binding = runtime_store.get_binding(binding_id)
        if binding is None:
            raise HTTPException(status_code=404, detail="Runtime Binding 不存在")
        if not payload.is_super_admin and binding.tenant_id != payload.workspace_id:
            raise HTTPException(status_code=404, detail="Runtime Binding 不存在")

        try:
            runtime_store.enable_binding(binding_id, payload.user_id)
        except RuntimeBindingNotFoundError:
            raise HTTPException(status_code=404, detail="Runtime Binding 不存在")
        except RuntimeAdapterNotAllowedError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except RuntimeStateError as e:
            raise HTTPException(status_code=409, detail=str(e))

        updated = runtime_store.get_binding(binding_id)
        _try_usage(usage_store, binding.tenant_id, payload.user_id, UsageResource.AGENT_SUBMISSION_REVIEW,
                    {"binding_id": binding_id, "action": "enable"})
        return {"binding": updated.to_dict() if updated else None, "message": "Binding enabled. Does NOT execute code."}

    # ── Disable ──

    @router.post("/bindings/{binding_id}/disable")
    async def disable_binding(
        binding_id: str,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        binding = runtime_store.get_binding(binding_id)
        if binding is None:
            raise HTTPException(status_code=404, detail="Runtime Binding 不存在")
        if not payload.is_super_admin and binding.tenant_id != payload.workspace_id:
            raise HTTPException(status_code=404, detail="Runtime Binding 不存在")

        runtime_store.disable_binding(binding_id, payload.user_id)
        updated = runtime_store.get_binding(binding_id)
        return {"binding": updated.to_dict() if updated else None}

    # ── Suspend ──

    @router.post("/bindings/{binding_id}/suspend")
    async def suspend_binding(
        binding_id: str,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        binding = runtime_store.get_binding(binding_id)
        if binding is None:
            raise HTTPException(status_code=404, detail="Runtime Binding 不存在")
        if not payload.is_super_admin and binding.tenant_id != payload.workspace_id:
            raise HTTPException(status_code=404, detail="Runtime Binding 不存在")

        runtime_store.suspend_binding(binding_id, payload.user_id)
        updated = runtime_store.get_binding(binding_id)
        return {"binding": updated.to_dict() if updated else None}

    # ── Assign sandbox policy to binding ──

    @router.post("/bindings/{binding_id}/sandbox-policy")
    async def assign_sandbox_policy(
        binding_id: str,
        body: AssignPolicyRequest,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        binding = runtime_store.get_binding(binding_id)
        if binding is None:
            raise HTTPException(status_code=404, detail="Runtime Binding 不存在")
        if not payload.is_super_admin and binding.tenant_id != payload.workspace_id:
            raise HTTPException(status_code=404, detail="Runtime Binding 不存在")

        if sandbox_policy_store:
            policy = sandbox_policy_store.get_policy(body.sandbox_policy_id)
            if policy is None:
                raise HTTPException(status_code=404, detail="Sandbox Policy 不存在")
            if not payload.is_super_admin and policy.scope == "tenant" and policy.tenant_id != payload.workspace_id:
                raise HTTPException(status_code=404, detail="Sandbox Policy 不存在")

        runtime_store.set_binding_sandbox_policy(binding_id, body.sandbox_policy_id)
        updated = runtime_store.get_binding(binding_id)
        _try_usage(usage_store, binding.tenant_id, payload.user_id, UsageResource.SANDBOX_POLICY_ASSIGN,
                    {"binding_id": binding_id, "sandbox_policy_id": body.sandbox_policy_id})
        return {"binding": updated.to_dict() if updated else None, "message": "Policy assigned. Does NOT enable execution."}

    # ── Eligibility ──

    @router.get("/developer-agents/{marketplace_agent_id}/eligibility")
    async def get_eligibility(
        marketplace_agent_id: str,
        tenant_id: str = Query(default=""),
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        tn = tenant_id if tenant_id and payload.is_super_admin else payload.workspace_id
        result = runtime_store.get_runtime_eligibility(marketplace_agent_id, tn)
        return result.to_dict()

    @router.get("/governance/summary")
    async def get_governance_summary(
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        return build_runtime_governance_summary(
            runtime_store=runtime_store,
            sandbox_policy_store=sandbox_policy_store,
            runtime_safety_store=runtime_safety_store,
            package_download_worker_store=package_download_worker_store,
            artifact_materialization_store=artifact_materialization_store,
            sandbox_execution_store=sandbox_execution_store,
            production_sandbox_gate_store=production_sandbox_gate_store,
        )

    # ═══════════════════════════════════════════
    # Step 21 — OIDC Validation Readiness (Runtime Admin)
    # ═══════════════════════════════════════════

    @router.get("/oidc-validation/readiness")
    async def oidc_validation_readiness(
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        """Runtime Admin 可视化 — Step 21 OIDC Validation Readiness。

        展示子能力状态：enabled / disabled / ready / not_ready。
        所有能力默认 disabled；signature_validation 仅在
        ``OIDC_SIGNATURE_VALIDATION_ENABLED=true`` 后显示 enabled。
        """
        from src.open_platform.sandbox_v2.config import load_sandbox_v2_settings
        from src.open_platform.sandbox_v2.oidc_step21_service import (
            SandboxV2OIDCStep21Service,
        )
        settings = load_sandbox_v2_settings()
        svc = SandboxV2OIDCStep21Service(settings=settings)
        return svc.get_oidc_validation_readiness()

    # ═══════════════════════════════════════════
    # Step 22 — SAML Validation Readiness (Runtime Admin)
    # ═══════════════════════════════════════════

    @router.get("/saml-validation/readiness")
    async def saml_validation_readiness(
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        """Runtime Admin 可视化 — Step 22 SAML Validation Readiness。

        展示子能力状态：enabled / disabled / ready / not_ready。
        所有能力默认 disabled。

        面板展示：
        - Metadata Import
        - Signature Validation
        - Certificate Validation
        - Certificate Pinning
        - Replay Protection
        - Identity Mapping
        """
        from src.open_platform.sandbox_v2.config import load_sandbox_v2_settings
        from src.open_platform.sandbox_v2.saml_step22_service import (
            SandboxV2SAMLStep22Service,
        )
        settings = load_sandbox_v2_settings()
        svc = SandboxV2SAMLStep22Service(settings=settings)
        return svc.get_saml_validation_readiness()

    # ═══════════════════════════════════════════
    # Step 23 — Observability Readiness (Runtime Admin)
    # ═══════════════════════════════════════════

    @router.get("/observability/readiness")
    async def observability_readiness(
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        """Runtime Admin 可视化 — Step 23 Observability Readiness。

        展示：
        - Prometheus: enabled/disabled + metrics count
        - OTel: enabled/disabled + exporter + config_valid
        - Tracing: enabled/disabled + spans recorded
        - Dashboards: enabled/disabled + available list
        - Metrics Domains: OIDC/SAML/Governance/Audit
        """
        from src.observability.service import ObservabilityService
        from src.open_platform.sandbox_v2.config import load_sandbox_v2_settings
        settings = load_sandbox_v2_settings()
        svc = ObservabilityService(settings=settings)
        return svc.get_readiness()

    return router
