"""Sandbox v2 Tenant Isolation Service — Step 14 多租户隔离。

Organization / Workspace 边界校验。
Cross-tenant attempt detection + audit。
"""

from __future__ import annotations

import logging
from typing import Any

from src.open_platform.sandbox_v2.models import (
    SandboxV2AuditEventType, SandboxV2AuditSeverity,
    SandboxV2PrincipalType,
)

logger = logging.getLogger(__name__)


class SandboxV2TenantIsolationService:
    """多租户隔离服务。"""

    def __init__(self, store: Any = None, audit_service: Any = None):
        self._store = store
        self._audit = audit_service

    @staticmethod
    def validate_resource_ownership(
        resource_org: str, resource_ws: str,
        request_org: str, request_ws: str,
    ) -> tuple[bool, str]:
        """验证资源归属。返回 (valid, reason)。"""
        if resource_org and request_org and resource_org != request_org:
            return False, f"Organization mismatch: {resource_org} != {request_org}"
        if resource_ws and request_ws and resource_ws != request_ws:
            return False, f"Workspace mismatch: {resource_ws} != {request_ws}"
        return True, ""

    @staticmethod
    def assert_same_tenant(
        resource_org: str, resource_ws: str,
        request_org: str, request_ws: str,
    ) -> None:
        """断言资源与请求属于同一租户。跨租户抛出 ValueError。"""
        ok, reason = SandboxV2TenantIsolationService.validate_resource_ownership(
            resource_org, resource_ws, request_org, request_ws,
        )
        if not ok:
            raise ValueError(f"Cross-tenant access denied: {reason}")

    @staticmethod
    def filter_resources_for_context(
        resources: list[dict[str, Any]],
        organization_id: str, workspace_id: str,
    ) -> list[dict[str, Any]]:
        """过滤资源列表，只返回同 org/ws 的。"""
        result: list[dict[str, Any]] = []
        for r in resources:
            org = r.get("organization_id", "")
            ws = r.get("workspace_id", "")
            if org == organization_id and (not workspace_id or ws == workspace_id):
                result.append(r)
        return result

    def detect_cross_tenant_attempt(
        self, *, principal_id: str = "", principal_type: str = "",
        organization_id: str = "", workspace_id: str = "",
        resource_org: str = "", resource_ws: str = "",
        resource_type: str = "", resource_id: str = "",
        action: str = "", reason: str = "",
    ) -> bool:
        """检测并记录跨租户尝试。返回 True 表示跨租户。"""
        ok, detail = self.validate_resource_ownership(
            resource_org, resource_ws, organization_id, workspace_id,
        )
        cross = not ok  # cross-tenant if ownership validation fails
        if cross:
            if self._audit:
                self._audit.create_audit_event(
                    event_type=SandboxV2AuditEventType.CROSS_TENANT_DENIED,
                    severity=SandboxV2AuditSeverity.HIGH,
                    principal_id=principal_id, principal_type=principal_type,
                    organization_id=organization_id, workspace_id=workspace_id,
                    resource_type=resource_type, resource_id=resource_id,
                    action=action, decision="deny",
                    reason=f"Cross-tenant: {detail}",
                    metadata={"resource_org": resource_org, "resource_ws": resource_ws},
                )
            return True
        return False

    def get_tenant_isolation_readiness(self) -> dict[str, Any]:
        return {
            "tenant_isolation": True,
            "cross_tenant_deny": True,
            "resource_ownership_validation": True,
            "list_filtering": True,
            "cross_tenant_audit": self._audit is not None,
            "boundary": "All resources require matching organization_id. Cross-workspace access denied.",
        }
