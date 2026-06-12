"""RBAC Service — 权限矩阵检查与角色管理。

metadata-only，不执行 runtime/container/microVM。
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class RBACResource(StrEnum):
    ARTIFACT = "artifact"
    PACKAGE = "package"
    WORKFLOW = "workflow"
    AGENT_MODULE = "agent_module"
    MARKETPLACE = "marketplace"
    REVIEW = "review"
    REPORT = "report"
    GOVERNANCE = "governance"
    BILLING = "billing"
    SUBSCRIPTION = "subscription"
    ANALYTICS = "analytics"
    TENANT = "tenant"


class RBACAction(StrEnum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    REVIEW = "review"
    APPROVE = "approve"
    PUBLISH = "publish"
    MANAGE = "manage"
    SUBSCRIBE = "subscribe"


_DEFAULT_PERMISSIONS: dict[str, dict[str, set[str]]] = {
    "owner": {
        RBACResource.ARTIFACT: {
            RBACAction.CREATE, RBACAction.READ, RBACAction.UPDATE, RBACAction.DELETE,
            RBACAction.REVIEW, RBACAction.APPROVE, RBACAction.PUBLISH},
        RBACResource.PACKAGE: {
            RBACAction.CREATE, RBACAction.READ, RBACAction.UPDATE, RBACAction.DELETE,
            RBACAction.REVIEW, RBACAction.APPROVE, RBACAction.PUBLISH},
        RBACResource.WORKFLOW: {
            RBACAction.CREATE, RBACAction.READ, RBACAction.UPDATE, RBACAction.DELETE,
            RBACAction.REVIEW, RBACAction.APPROVE, RBACAction.PUBLISH},
        RBACResource.AGENT_MODULE: {
            RBACAction.CREATE, RBACAction.READ, RBACAction.UPDATE, RBACAction.DELETE,
            RBACAction.REVIEW, RBACAction.APPROVE, RBACAction.PUBLISH},
        RBACResource.MARKETPLACE: {RBACAction.READ, RBACAction.SUBSCRIBE},
        RBACResource.REVIEW: {RBACAction.CREATE, RBACAction.READ, RBACAction.UPDATE, RBACAction.DELETE},
        RBACResource.REPORT: {RBACAction.CREATE, RBACAction.READ},
        RBACResource.GOVERNANCE: {RBACAction.READ, RBACAction.MANAGE},
        RBACResource.BILLING: {RBACAction.READ, RBACAction.MANAGE},
        RBACResource.SUBSCRIPTION: {RBACAction.READ, RBACAction.MANAGE},
        RBACResource.ANALYTICS: {RBACAction.READ},
        RBACResource.TENANT: {RBACAction.READ, RBACAction.UPDATE, RBACAction.MANAGE},
    },
    "admin": {
        RBACResource.ARTIFACT: {
            RBACAction.CREATE, RBACAction.READ, RBACAction.UPDATE, RBACAction.REVIEW,
            RBACAction.APPROVE, RBACAction.PUBLISH},
        RBACResource.PACKAGE: {
            RBACAction.CREATE, RBACAction.READ, RBACAction.UPDATE, RBACAction.REVIEW,
            RBACAction.APPROVE, RBACAction.PUBLISH},
        RBACResource.WORKFLOW: {
            RBACAction.CREATE, RBACAction.READ, RBACAction.UPDATE, RBACAction.REVIEW,
            RBACAction.APPROVE, RBACAction.PUBLISH},
        RBACResource.AGENT_MODULE: {
            RBACAction.CREATE, RBACAction.READ, RBACAction.UPDATE, RBACAction.REVIEW,
            RBACAction.APPROVE, RBACAction.PUBLISH},
        RBACResource.MARKETPLACE: {RBACAction.READ, RBACAction.SUBSCRIBE},
        RBACResource.REVIEW: {RBACAction.CREATE, RBACAction.READ, RBACAction.UPDATE, RBACAction.DELETE},
        RBACResource.REPORT: {RBACAction.CREATE, RBACAction.READ},
        RBACResource.GOVERNANCE: {RBACAction.READ},
        RBACResource.BILLING: {RBACAction.READ},
        RBACResource.SUBSCRIPTION: {RBACAction.READ},
        RBACResource.ANALYTICS: {RBACAction.READ},
        RBACResource.TENANT: {RBACAction.READ, RBACAction.UPDATE},
    },
    "member": {
        RBACResource.ARTIFACT: {RBACAction.CREATE, RBACAction.READ, RBACAction.UPDATE},
        RBACResource.PACKAGE: {RBACAction.CREATE, RBACAction.READ, RBACAction.UPDATE},
        RBACResource.WORKFLOW: {RBACAction.CREATE, RBACAction.READ, RBACAction.UPDATE},
        RBACResource.AGENT_MODULE: {RBACAction.CREATE, RBACAction.READ, RBACAction.UPDATE},
        RBACResource.MARKETPLACE: {RBACAction.READ, RBACAction.SUBSCRIBE},
        RBACResource.REVIEW: {RBACAction.CREATE, RBACAction.READ, RBACAction.UPDATE},
        RBACResource.REPORT: {RBACAction.CREATE, RBACAction.READ},
        RBACResource.GOVERNANCE: {RBACAction.READ},
        RBACResource.ANALYTICS: {RBACAction.READ},
        RBACResource.TENANT: {RBACAction.READ},
    },
    "viewer": {
        RBACResource.ARTIFACT: {RBACAction.READ},
        RBACResource.PACKAGE: {RBACAction.READ},
        RBACResource.WORKFLOW: {RBACAction.READ},
        RBACResource.AGENT_MODULE: {RBACAction.READ},
        RBACResource.MARKETPLACE: {RBACAction.READ},
        RBACResource.REVIEW: {RBACAction.READ},
        RBACResource.REPORT: {RBACAction.READ},
        RBACResource.GOVERNANCE: {RBACAction.READ},
        RBACResource.ANALYTICS: {RBACAction.READ},
        RBACResource.TENANT: {RBACAction.READ},
    },
}


class RBACService:
    """RBAC 权限服务 — 基于 metadata 的角色-权限矩阵。"""

    def __init__(self, rbac_store=None):
        self._store = rbac_store

    def check_permission(self, role: str, resource: str, action: str) -> bool:
        """检查角色是否有资源/操作的权限。"""
        if role not in _DEFAULT_PERMISSIONS:
            return False
        perms = _DEFAULT_PERMISSIONS[role]
        if resource not in perms:
            return False
        return action in perms[resource]

    def get_role_permissions(self, role: str) -> dict[str, list[str]]:
        """获取角色的所有权限。"""
        if role not in _DEFAULT_PERMISSIONS:
            return {}
        return {
            resource: sorted(list(actions))
            for resource, actions in _DEFAULT_PERMISSIONS[role].items()
        }

    def assign_role(self, user_id: str, workspace_id: str, role: str) -> dict:
        """为用户分配角色。"""
        if role not in _DEFAULT_PERMISSIONS:
            return {"error": f"invalid role: {role}"}
        if self._store:
            try:
                self._store.assign_role(user_id, role, workspace_id)
            except Exception as e:
                logger.warning("assign_role_failed", exc_info=True)
        logger.info("role_assigned", extra={"user_id": user_id, "role": role, "ws": workspace_id})
        return {"user_id": user_id, "workspace_id": workspace_id, "role": role, "assigned": True}

    def revoke_role(self, user_id: str, workspace_id: str) -> dict:
        if self._store:
            try:
                self._store.remove_assignment(f"{user_id}_{workspace_id}")
            except Exception:
                logger.debug("revoke_failed", exc_info=True)
        logger.info("role_revoked", extra={"user_id": user_id, "ws": workspace_id})
        return {"user_id": user_id, "workspace_id": workspace_id, "revoked": True}

    def get_user_role(self, user_id: str, workspace_id: str) -> str:
        if self._store:
            try:
                assignments = self._store.get_user_roles(user_id, workspace_id)
                if assignments:
                    return assignments[0].get("role", "member") if isinstance(assignments[0], dict) else "member"
            except Exception:
                pass
        return "member"

    def get_permission_matrix(self) -> dict:
        """返回完整的权限矩阵。"""
        return {
            role: {
                resource: sorted(list(actions))
                for resource, actions in perms.items()
            }
            for role, perms in _DEFAULT_PERMISSIONS.items()
        }

    def list_roles(self) -> list[str]:
        return list(_DEFAULT_PERMISSIONS.keys())

    def list_resources(self) -> list[str]:
        return [r.value for r in RBACResource]

    def list_actions(self) -> list[str]:
        return [a.value for a in RBACAction]
