"""SaaS Integration Service — 配额强制执行 + 用量记录 + 租户隔离。

职责：
1. 配额检查：操作前对比 PlanLimit 与当前用量
2. 已接入 PlanLimit.max_marketplace_agents + platform 默认配额
3. 用量记录：操作后写入 UsageEvent
4. workspace 隔离：所有查询按 workspace_id 过滤
5. 租户 Dashboard 聚合

不执行任何 runtime/container/microVM 代码。
"""

from __future__ import annotations

import logging
from typing import Any

from src.open_platform.saas_integration import (
    QuotaCheckResult,
    QuotaExceededError,
    QuotaResource,
    TenantDashboard,
    require_workspace_match,
    _DEFAULT_QUOTAS,
)

logger = logging.getLogger(__name__)


class SaaSIntegrationService:
    """将所有 open_platform 子系统接入 SaaS 多租户体系。"""

    def __init__(self, *, artifact_store=None, package_store=None,
                 workflow_store=None, agent_module_store=None,
                 subscription_store=None, usage_store=None):
        self._artifact_store = artifact_store
        self._package_store = package_store
        self._workflow_store = workflow_store
        self._agent_module_store = agent_module_store
        self._subscription_store = subscription_store
        self._usage_store = usage_store

    # ═══════════════════════════════
    # Quota Enforcement
    # ═══════════════════════════════

    def check_quota(self, workspace_id: str, resource: str) -> QuotaCheckResult:
        """检查 workspace 在指定资源的配额。返回 QuotaCheckResult。"""
        current = self._count_by_resource(workspace_id, resource)
        limit = self._get_quota_limit(workspace_id, resource)
        allowed = current < limit
        remaining = max(0, limit - current)
        message = "" if allowed else f"配额超限: {resource} ({current}/{limit})"
        return QuotaCheckResult(
            allowed=allowed, resource=resource, workspace_id=workspace_id,
            current_count=current, quota_limit=limit, remaining=remaining,
            message=message,
        )

    def enforce_quota(self, workspace_id: str, resource: str) -> QuotaCheckResult:
        """检查配额；超限则 raise QuotaExceededError。"""
        result = self.check_quota(workspace_id, resource)
        if not result.allowed:
            raise QuotaExceededError(resource, result.current_count, result.quota_limit)
        return result

    def _count_by_resource(self, workspace_id: str, resource: str) -> int:
        """按资源类型查询 workspace 当前已用量。"""
        if resource == QuotaResource.ARTIFACT and self._artifact_store:
            return len(self._artifact_store.list(workspace_id=workspace_id))
        if resource == QuotaResource.PACKAGE and self._package_store:
            return len(self._package_store.list(workspace_id=workspace_id))
        if resource == QuotaResource.WORKFLOW and self._workflow_store:
            return len(self._workflow_store.list(workspace_id=workspace_id))
        if resource == QuotaResource.AGENT_MODULE and self._agent_module_store:
            return len(self._agent_module_store.list(workspace_id=workspace_id))
        if resource == QuotaResource.MARKETPLACE_SUBSCRIPTION and self._agent_module_store:
            return len(self._agent_module_store.list_subscriptions(workspace_id))
        return 0

    def _get_quota_limit(self, workspace_id: str, resource: str) -> int:
        """获取配额上限：优先 PlanLimit，其次默认配额。"""
        # 从 subscription 读取 PlanLimit
        if self._subscription_store:
            try:
                sub = self._subscription_store.get_subscription(workspace_id)
                if sub and sub.is_active():
                    limits = sub.plan_limit()
                    if resource == QuotaResource.MARKETPLACE_SUBSCRIPTION:
                        return limits.max_marketplace_agents
                    if resource == QuotaResource.AGENT_MODULE:
                        return limits.max_marketplace_agents
                    if resource == QuotaResource.WORKFLOW:
                        return limits.max_marketplace_agents
                    if resource == QuotaResource.PACKAGE:
                        return limits.max_marketplace_agents * 2
                    if resource == QuotaResource.ARTIFACT:
                        return limits.max_marketplace_agents * 10
            except Exception:
                pass
        return _DEFAULT_QUOTAS.get(resource, 100)

    def get_all_quotas(self, workspace_id: str) -> dict[str, QuotaCheckResult]:
        """一次性获取所有资源类型的配额状态。"""
        return {
            r.value: self.check_quota(workspace_id, r.value)
            for r in QuotaResource
        }

    # ═══════════════════════════════
    # Usage Recording
    # ═══════════════════════════════

    def record_usage(self, workspace_id: str, user_id: str, resource: str,
                     quantity: int = 1, metadata: dict | None = None) -> None:
        """记录用量事件。静默失败 — 不计入核心路径。"""
        if not self._usage_store:
            return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            # 尝试匹配 resource 名到 UsageResource 枚举
            event_resource = _map_to_usage_resource(resource)
            event = UsageEvent(
                tenant_id=workspace_id, user_id=user_id,
                workspace_id=workspace_id, resource=event_resource,
                quantity=quantity, unit=UsageUnit.COUNT,
                metadata=metadata or {},
            )
            self._usage_store.record_event(event)
        except Exception:
            logger.debug("record_usage_silent_fail", exc_info=True,
                         extra={"workspace_id": workspace_id, "resource": resource})

    # ═══════════════════════════════
    # Dashboard
    # ═══════════════════════════════

    def get_dashboard(self, workspace_id: str) -> TenantDashboard:
        """构建租户 Dashboard。"""
        dashboard = TenantDashboard(workspace_id=workspace_id)

        if self._artifact_store:
            artifacts = self._artifact_store.list(workspace_id=workspace_id, limit=1000)
            for a in artifacts:
                dashboard.artifacts[a.status] = dashboard.artifacts.get(a.status, 0) + 1

        if self._package_store:
            pkgs = self._package_store.list(workspace_id=workspace_id, limit=1000)
            for p in pkgs:
                dashboard.packages[p.status] = dashboard.packages.get(p.status, 0) + 1

        if self._workflow_store:
            wfs = self._workflow_store.list(workspace_id=workspace_id, limit=1000)
            for w in wfs:
                dashboard.workflows[w.status] = dashboard.workflows.get(w.status, 0) + 1

        if self._agent_module_store:
            modules = self._agent_module_store.list(workspace_id=workspace_id, limit=1000)
            for m in modules:
                dashboard.agent_modules[m.status] = dashboard.agent_modules.get(m.status, 0) + 1
            dashboard.marketplace_subscriptions = len(
                self._agent_module_store.list_subscriptions(workspace_id))

        dashboard.quotas = self.get_all_quotas(workspace_id)
        return dashboard

    # ═══════════════════════════════
    # Cross-workspace Guard
    # ═══════════════════════════════

    def guard_workspace_access(self, request_workspace_id: str,
                               resource_workspace_id: str) -> None:
        """跨 workspace 访问守卫。"""
        require_workspace_match(request_workspace_id, resource_workspace_id)


# ═══════════════════════════════
# Helpers
# ═══════════════════════════════

def _map_to_usage_resource(resource: str):
    """将配额资源名映射到 UsageResource 枚举。"""
    from src.core.usage import UsageResource
    mapping = {
        QuotaResource.ARTIFACT: UsageResource.STORAGE,
        QuotaResource.PACKAGE: UsageResource.AGENT_SUBMISSION_CREATE,
        QuotaResource.WORKFLOW: UsageResource.WORKFLOW_RUN,
        QuotaResource.AGENT_MODULE: UsageResource.AGENT_SUBMISSION_PUBLISH,
        QuotaResource.MARKETPLACE_SUBSCRIPTION: UsageResource.AGENT_INSTALL,
    }
    return mapping.get(resource, UsageResource.STORAGE)
