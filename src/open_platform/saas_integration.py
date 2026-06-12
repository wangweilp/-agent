"""SaaS Integration Domain — 连接 open_platform 与 multi-tenant SaaS 基础设施。

职责：
- 配额检查：在创建/订阅/发布操作前验证 PlanLimit
-  workspace 隔离：所有查询按 workspace_id (= tenant_id) 过滤
- 用量记录：所有操作后记录 UsageEvent

安全约束：
- metadata_only — 不做执行
- 不访问 secrets/network/filesystem
- 不运行 runtime/container/microVM
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


# ═══════════════════════════════════════════
# Quota Resource Types
# ═══════════════════════════════════════════


class QuotaResource(StrEnum):
    ARTIFACT = "artifact"
    PACKAGE = "package"
    WORKFLOW = "workflow"
    AGENT_MODULE = "agent_module"
    MARKETPLACE_SUBSCRIPTION = "marketplace_subscription"


_DEFAULT_QUOTAS: dict[str, int] = {
    QuotaResource.ARTIFACT: 100,
    QuotaResource.PACKAGE: 50,
    QuotaResource.WORKFLOW: 20,
    QuotaResource.AGENT_MODULE: 10,
    QuotaResource.MARKETPLACE_SUBSCRIPTION: 5,
}


# ═══════════════════════════════════════════
# Quota Check Result
# ═══════════════════════════════════════════


@dataclass
class QuotaCheckResult:
    """配额检查结果。"""
    allowed: bool
    resource: str
    workspace_id: str
    current_count: int = 0
    quota_limit: int = 0
    remaining: int = 0
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "resource": self.resource,
            "workspace_id": self.workspace_id,
            "current_count": self.current_count,
            "quota_limit": self.quota_limit,
            "remaining": self.remaining,
            "message": self.message,
        }


# ═══════════════════════════════════════════
# Tenant Dashboard
# ═══════════════════════════════════════════


@dataclass
class TenantDashboard:
    """租户总览面板。"""
    workspace_id: str
    artifacts: dict[str, int] = field(default_factory=dict)    # {status: count}
    packages: dict[str, int] = field(default_factory=dict)
    workflows: dict[str, int] = field(default_factory=dict)
    agent_modules: dict[str, int] = field(default_factory=dict)
    marketplace_subscriptions: int = 0
    quotas: dict[str, QuotaCheckResult] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "artifacts": self.artifacts,
            "packages": self.packages,
            "workflows": self.workflows,
            "agent_modules": self.agent_modules,
            "marketplace_subscriptions": self.marketplace_subscriptions,
            "quotas": {k: v.to_dict() for k, v in self.quotas.items()},
        }


# ═══════════════════════════════════════════
# Workspace Enforcement
# ═══════════════════════════════════════════


def require_workspace_match(workspace_id: str, resource_workspace_id: str) -> None:
    """跨 workspace 访问守卫 — 凡不匹配直接 raise。"""
    if workspace_id != resource_workspace_id:
        raise WorkspaceIsolationError(
            f"跨 workspace 访问禁止: {workspace_id} → {resource_workspace_id}")


class WorkspaceIsolationError(Exception):
    def __init__(self, message: str = "跨 workspace 访问被拒绝"):
        super().__init__(message)
        self.message = message


class QuotaExceededError(Exception):
    def __init__(self, resource: str, current: int, limit: int):
        super().__init__(f"配额超限: {resource} (当前 {current}, 上限 {limit})")
        self.resource = resource
        self.current = current
        self.limit = limit
