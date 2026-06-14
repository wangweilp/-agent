"""Sandbox v2 Access Policy Engine — Step 14 RBAC/Scope 权限策略。

默认 deny + fail closed。
Organization / Workspace 边界强制。
"""

from __future__ import annotations

import logging
from typing import Any

from src.open_platform.sandbox_v2.models import (
    SandboxV2PrincipalType, SandboxV2Role, SandboxV2ResourceType,
    SandboxV2PermissionAction, SandboxV2AccessDecisionAction,
    SandboxV2RiskLevel,
)

logger = logging.getLogger(__name__)

# ── Role → allowed actions ──
_ROLE_PERMISSIONS: dict[str, set[str]] = {
    SandboxV2Role.OWNER: {
        SandboxV2PermissionAction.CREATE, SandboxV2PermissionAction.READ,
        SandboxV2PermissionAction.LIST, SandboxV2PermissionAction.UPDATE,
        SandboxV2PermissionAction.DELETE, SandboxV2PermissionAction.EXECUTE,
        SandboxV2PermissionAction.CANCEL, SandboxV2PermissionAction.KILL,
        SandboxV2PermissionAction.REVIEW, SandboxV2PermissionAction.APPROVE,
        SandboxV2PermissionAction.REJECT, SandboxV2PermissionAction.EXPORT,
        SandboxV2PermissionAction.PREFLIGHT, SandboxV2PermissionAction.ADMINISTER,
    },
    SandboxV2Role.ADMIN: {
        SandboxV2PermissionAction.CREATE, SandboxV2PermissionAction.READ,
        SandboxV2PermissionAction.LIST, SandboxV2PermissionAction.UPDATE,
        SandboxV2PermissionAction.DELETE, SandboxV2PermissionAction.EXECUTE,
        SandboxV2PermissionAction.CANCEL, SandboxV2PermissionAction.KILL,
        SandboxV2PermissionAction.REVIEW, SandboxV2PermissionAction.APPROVE,
        SandboxV2PermissionAction.REJECT, SandboxV2PermissionAction.EXPORT,
        SandboxV2PermissionAction.PREFLIGHT, SandboxV2PermissionAction.ADMINISTER,
    },
    SandboxV2Role.DEVELOPER: {
        SandboxV2PermissionAction.CREATE, SandboxV2PermissionAction.READ,
        SandboxV2PermissionAction.LIST, SandboxV2PermissionAction.PREFLIGHT,
    },
    SandboxV2Role.OPERATOR: {
        SandboxV2PermissionAction.READ, SandboxV2PermissionAction.LIST,
        SandboxV2PermissionAction.CANCEL, SandboxV2PermissionAction.EXECUTE,
        SandboxV2PermissionAction.KILL, SandboxV2PermissionAction.PREFLIGHT,
    },
    SandboxV2Role.AUDITOR: {
        SandboxV2PermissionAction.READ, SandboxV2PermissionAction.LIST,
        SandboxV2PermissionAction.EXPORT,
    },
    SandboxV2Role.VIEWER: {
        SandboxV2PermissionAction.READ, SandboxV2PermissionAction.LIST,
    },
    SandboxV2Role.WORKER: {
        SandboxV2PermissionAction.READ, SandboxV2PermissionAction.UPDATE,
        SandboxV2PermissionAction.EXECUTE,
    },
    SandboxV2Role.SERVICE: {
        SandboxV2PermissionAction.CREATE, SandboxV2PermissionAction.READ,
        SandboxV2PermissionAction.LIST, SandboxV2PermissionAction.UPDATE,
        SandboxV2PermissionAction.EXECUTE,
    },
}


def get_role_permissions(role: str) -> set[str]:
    return _ROLE_PERMISSIONS.get(role, set())


class SandboxV2AccessPolicyEngine:
    """权限策略引擎 — 默认 deny + fail closed。"""

    @staticmethod
    def evaluate_access(
        principal_type: str = SandboxV2PrincipalType.ANONYMOUS,
        roles: list[str] | None = None,
        scopes: list[str] | None = None,
        organization_id: str = "",
        workspace_id: str = "",
        resource_organization_id: str = "",
        resource_workspace_id: str = "",
        resource_type: str = "",
        resource_id: str = "",
        action: str = "",
    ) -> dict[str, Any]:
        """评估访问请求，返回 access decision dict。"""
        try:
            return _eval_impl(
                principal_type=principal_type, roles=roles or [], scopes=scopes or [],
                organization_id=organization_id, workspace_id=workspace_id,
                resource_organization_id=resource_organization_id,
                resource_workspace_id=resource_workspace_id,
                resource_type=resource_type, resource_id=resource_id, action=action,
            )
        except Exception as e:
            logger.exception("access_policy_eval_failed")
            return _deny("access_policy_exception", f"Policy evaluation failed: {e}", risk="critical", fail_closed=True)

    @staticmethod
    def evaluate_role_permission(role: str, action: str) -> bool:
        perms = _ROLE_PERMISSIONS.get(role, set())
        return action in perms

    @staticmethod
    def evaluate_scope_permission(scopes: list[str], resource_type: str, action: str) -> bool:
        if not scopes:
            return False
        scope_set = set(scopes)
        # admin:* scope allows everything
        if "admin:*" in scope_set:
            return True
        if "sandbox:*" in scope_set:
            subset = {SandboxV2PermissionAction.READ, SandboxV2PermissionAction.LIST,
                       SandboxV2PermissionAction.CREATE, SandboxV2PermissionAction.CANCEL}
            return action in subset
        if f"sandbox:{resource_type}" in scope_set:
            rw = {SandboxV2PermissionAction.READ, SandboxV2PermissionAction.LIST,
                  SandboxV2PermissionAction.CREATE, SandboxV2PermissionAction.UPDATE}
            return action in rw
        if f"sandbox:{resource_type}:read" in scope_set:
            return action in (SandboxV2PermissionAction.READ, SandboxV2PermissionAction.LIST)
        return False

    @staticmethod
    def evaluate_cross_tenant(
        principal_org: str, principal_ws: str,
        resource_org: str, resource_ws: str,
    ) -> tuple[bool, str]:
        """返回 (is_cross_tenant, reason)。"""
        if principal_org and resource_org and principal_org != resource_org:
            return True, f"Cross organization: principal_org={principal_org} != resource_org={resource_org}"
        if principal_ws and resource_ws and principal_ws != resource_ws:
            return True, f"Cross workspace: principal_ws={principal_ws} != resource_ws={resource_ws}"
        return False, ""


def _eval_impl(**kw) -> dict[str, Any]:
    matched: list[str] = []
    principal_type = kw.get("principal_type", "anonymous")
    roles: list[str] = kw.get("roles", [])
    scopes: list[str] = kw.get("scopes", [])
    org_id = kw.get("organization_id", "")
    ws_id = kw.get("workspace_id", "")
    rsrc_org = kw.get("resource_organization_id", "")
    rsrc_ws = kw.get("resource_workspace_id", "")
    rsrc_type = kw.get("resource_type", "")
    action = kw.get("action", "")

    # Rule 1: Anonymous → deny
    if principal_type == SandboxV2PrincipalType.ANONYMOUS:
        return _deny("anonymous_denied", "Anonymous access denied.", matched=[*matched, "anonymous_denied"])
    matched.append("not_anonymous")

    # Rule 2: System → allow with audit
    if principal_type == SandboxV2PrincipalType.SYSTEM:
        return _allow("system_allowed", "System principal allowed.", action="allow", matched=[*matched, "system_allowed"])

    # Rule 3: Must have org/workspace
    if not org_id:
        return _deny("missing_organization", "Organization is required.", matched=[*matched, "missing_org"])
    matched.append("has_org")
    if not ws_id:
        return _deny("missing_workspace", "Workspace is required.", matched=[*matched, "missing_ws"])
    matched.append("has_ws")

    # Rule 4: Cross-tenant check
    cross, cross_reason = SandboxV2AccessPolicyEngine.evaluate_cross_tenant(org_id, ws_id, rsrc_org, rsrc_ws)
    if cross and principal_type not in (SandboxV2PrincipalType.ADMIN, SandboxV2PrincipalType.SYSTEM):
        return _deny("cross_tenant_denied", cross_reason,
                     risk="high", cross_tenant=True, matched=[*matched, "cross_tenant_denied"])
    if not cross and rsrc_org and rsrc_ws:
        matched.append("tenant_match")

    # Rule 5: Unknown role → deny
    unknown_roles = [r for r in roles if r not in _ROLE_PERMISSIONS]
    if unknown_roles:
        return _deny("unknown_role", f"Unknown roles: {unknown_roles}", matched=[*matched, "unknown_role"])
    matched.append("roles_known")

    # Rule 6: Unknown action → deny
    known_actions = set(SandboxV2PermissionAction)
    if action in known_actions:
        matched.append("action_known")
    else:
        return _deny("unknown_action", f"Unknown action: {action}", matched=[*matched, "unknown_action"])

    # Rule 7: Unknown resource → deny
    if rsrc_type in set(SandboxV2ResourceType) or not rsrc_type:
        matched.append("resource_known")
    else:
        return _deny("unknown_resource", f"Unknown resource: {rsrc_type}", matched=[*matched, "unknown_resource"])

    # Rule 8: Role permission check
    role_ok = any(SandboxV2AccessPolicyEngine.evaluate_role_permission(r, action) for r in roles)
    if not role_ok:
        return _deny("role_insufficient", f"Roles {roles} lack permission for {action}", matched=[*matched, "role_insufficient"])
    matched.append("role_allowed")

    # Rule 9: Scope permission check (if api_key or scopes provided)
    if principal_type in (SandboxV2PrincipalType.API_KEY, SandboxV2PrincipalType.SERVICE_ACCOUNT):
        if not scopes:
            return _deny("scope_required", "API key requires scopes.", matched=[*matched, "scope_required"])
        if rsrc_type:
            scope_ok = SandboxV2AccessPolicyEngine.evaluate_scope_permission(scopes, rsrc_type, action)
            if not scope_ok:
                return _deny("scope_insufficient", f"Scopes insufficient for {action} on {rsrc_type}", matched=[*matched, "scope_insufficient"])
        matched.append("scope_verified")

    return _allow("access_granted", f"Access granted to {principal_type} with roles={roles} for {action} on {rsrc_type}",
                  matched=matched)


def _deny(reason_code: str, reason: str, *, risk: str = "medium", cross_tenant: bool = False,
          matched: list[str] | None = None, fail_closed: bool = False) -> dict:
    return {
        "allowed": False, "action": SandboxV2AccessDecisionAction.DENY,
        "reason": f"[{reason_code}] {reason}", "risk_level": risk,
        "principal_id": "", "principal_type": "", "resource_type": "", "resource_id": "",
        "permission_action": "", "organization_match": not cross_tenant,
        "workspace_match": not cross_tenant, "role_allowed": False, "scope_allowed": False,
        "cross_tenant": cross_tenant, "fail_closed": fail_closed,
        "matched_rules": matched or [],
    }


def _allow(reason_code: str, reason: str, *, action: str = "allow",
           matched: list[str] | None = None) -> dict:
    return {
        "allowed": True, "action": action,
        "reason": f"[{reason_code}] {reason}", "risk_level": "low",
        "principal_id": "", "principal_type": "", "resource_type": "", "resource_id": "",
        "permission_action": "", "organization_match": True,
        "workspace_match": True, "role_allowed": True, "scope_allowed": True,
        "cross_tenant": False, "fail_closed": False,
        "matched_rules": matched or [],
    }
