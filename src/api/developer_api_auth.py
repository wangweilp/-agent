"""Developer API Key Auth — FastAPI dependencies。

提供：
- require_developer_api_key: 从 X-Cognitive-API-Key 认证
- require_dev_auth_with_scopes: 接受 JWT 或 API Key 的统一入口
- require_api_key_scopes: scope enforcement

Header: X-Cognitive-API-Key: cos_dev_<prefix>_<secret>
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, HTTPException, Request

from src.adapters.developer_store import SQLiteDeveloperStore
from src.adapters.usage_store import UsageStoreAdapter
from src.core.usage import UsageEvent, UsageResource, UsageUnit
from src.open_platform.api_auth import DeveloperApiPrincipal
from src.open_platform.developer import (
    DeveloperAccount,
    DeveloperStatus,
    has_required_scopes,
    get_api_key_prefix,
)

logger = logging.getLogger(__name__)


def _safe_record_usage(
    usage_store: UsageStoreAdapter | None,
    tenant_id: str,
    user_id: str,
    workspace_id: str,
    resource: UsageResource,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Best-effort 记录 usage，失败仅 warning。"""
    if usage_store is None:
        return
    try:
        usage_store.record_event(UsageEvent(
            tenant_id=tenant_id,
            user_id=user_id,
            workspace_id=workspace_id,
            resource=resource,
            quantity=1,
            unit=UsageUnit.COUNT,
            metadata=metadata or {},
        ))
    except Exception:
        logger.warning("dev_api_key_usage_record_failed", exc_info=True,
                       extra={"resource": resource.value})


def require_developer_api_key(
    developer_store: SQLiteDeveloperStore,
    usage_store: UsageStoreAdapter | None = None,
):
    """Factory: 创建 require_developer_api_key 依赖。

    从 X-Cognitive-API-Key header 提取并验证 API Key，返回 DeveloperApiPrincipal。
    header 缺失或 key 无效 → 401。
    developer suspended → 403。
    """

    async def _require(
        request: Request,
    ) -> DeveloperApiPrincipal:
        raw_key = request.headers.get("X-Cognitive-API-Key", "").strip()
        if not raw_key:
            raise HTTPException(status_code=401, detail="X-Cognitive-API-Key header required")

        # 1. verify_raw_key → lookup + hash check + status/expire check
        api_key = developer_store.verify_and_lookup_api_key(raw_key)
        if api_key is None:
            # 不记录失败 key（防 brute-force 枚举放大）
            raise HTTPException(status_code=401, detail="Invalid API Key")

        # 2. lookup developer
        dev = developer_store.get_developer(api_key.developer_id)
        if dev is None:
            raise HTTPException(status_code=401, detail="Invalid API Key")

        # 3. developer must be active
        if dev.status != DeveloperStatus.ACTIVE:
            raise HTTPException(status_code=403, detail="Developer account is not active")

        # 4. build principal
        principal = DeveloperApiPrincipal(
            developer_id=dev.developer_id,
            user_id=dev.user_id,
            tenant_id=dev.tenant_id,
            api_key_id=api_key.api_key_id,
            key_prefix=api_key.key_prefix,
            scopes=list(api_key.scopes),
        )

        # 5. record usage (best-effort, no raw_key in metadata)
        _safe_record_usage(
            usage_store,
            tenant_id=dev.tenant_id,
            user_id=dev.user_id,
            workspace_id=dev.tenant_id,  # API Key 用 tenant_id 作为 workspace
            resource=UsageResource.DEVELOPER_API_KEY_AUTH,
            metadata={
                "developer_id": dev.developer_id,
                "api_key_id": api_key.api_key_id,
                "key_prefix": api_key.key_prefix,
                "auth_type": "developer_api_key",
                "endpoint": str(request.url.path),
                "method": request.method,
            },
        )

        logger.info("api_key_auth_success", extra={
            "developer_id": dev.developer_id,
            "api_key_id": api_key.api_key_id,
        })
        return principal

    return _require


def require_api_key_scopes(*required_scopes: str):
    """Factory: 创建 scope enforcement 依赖。

    必须在 require_developer_api_key 之后调用。
    缺少 required scope → 403。
    """

    async def _check(
        principal: DeveloperApiPrincipal,
    ) -> DeveloperApiPrincipal:
        if not required_scopes:
            return principal
        if not has_required_scopes(principal.scopes, list(required_scopes)):
            raise HTTPException(
                status_code=403,
                detail={
                    "message": "Insufficient API key scope",
                    "required_scopes": list(required_scopes),
                },
            )
        return principal

    return _check
