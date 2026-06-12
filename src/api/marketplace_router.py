"""Agent Marketplace API — /agent-marketplace 端点。

端点：
- GET    /agent-marketplace                           — 浏览 Marketplace Agent
- GET    /agent-marketplace/categories                — 分类列表
- GET    /agent-marketplace/departments               — 部门列表
- GET    /agent-marketplace/installations              — 安装列表
- GET    /agent-marketplace/installations/{id}         — 安装详情
- POST   /agent-marketplace/installations/{id}/enable  — 启用
- POST   /agent-marketplace/installations/{id}/disable — 停用
- PATCH  /agent-marketplace/installations/{id}/config  — 更新配置
- DELETE /agent-marketplace/installations/{id}         — 软卸载
- GET    /agent-marketplace/installations/{id}/usage   — 安装用量
- GET    /agent-marketplace/{id}                       — Agent 详情
- GET    /agent-marketplace/{id}/permissions           — 权限需求
- POST   /agent-marketplace/{id}/install               — 安装 Agent

权限模型：
- 浏览类接口: require_auth（所有已认证用户）
- 管理类接口: require_auth + admin/owner/super_admin
- tenant/workspace 隔离: 所有安装操作按 tenant_id + workspace_id 隔离

注意：固定路径（/categories, /departments, /installations）必须在参数化路径（/{id}）之前注册。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.adapters.marketplace_store import SQLiteMarketplaceStore, DuplicateInstallationError
from src.adapters.usage_store import UsageStoreAdapter
from src.api.middleware import require_auth, TokenPayload
from src.core.usage import UsageEvent, UsageResource, UsageUnit

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 请求模型
# ═══════════════════════════════════════════


class InstallAgentRequest(BaseModel):
    workspace_id: str = Field(default="", description="目标工作区 ID，缺省使用当前工作区")
    config: dict[str, Any] = Field(default_factory=dict, description="安装配置")
    permissions_granted: list[str] = Field(default_factory=list, description="已授予的权限")
    usage_limit_override: dict[str, Any] = Field(default_factory=dict, description="用量限制覆盖")
    version_pinned: str | None = Field(default=None, description="锁定版本，None=跟随最新")


class UpdateInstallationConfigRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict, description="配置键值对（合并更新）")
    permissions_granted: list[str] = Field(default_factory=list, description="已授予的权限")
    usage_limit_override: dict[str, Any] = Field(default_factory=dict, description="用量限制覆盖")
    version_pinned: str | None = Field(default=None, description="锁定版本")


# ═══════════════════════════════════════════
# 内部 Helper
# ═══════════════════════════════════════════


def _is_admin(payload: TokenPayload) -> bool:
    """判断当前用户是否为 admin 或以上。"""
    if payload.is_super_admin:
        return True
    if payload.role and payload.role.value in ("owner", "admin", "org_admin", "super_admin"):
        return True
    return False


def _require_admin(payload: TokenPayload = Depends(require_auth)) -> TokenPayload:
    """强制要求 admin/owner 角色 — 非管理员返回 403。"""
    if not _is_admin(payload):
        raise HTTPException(status_code=403, detail="权限不足: 需要 admin 或以上角色")
    return payload


def _resolve_workspace_id(payload: TokenPayload, request_ws: str) -> str:
    """解析 workspace_id: request 为空时使用 payload.workspace_id。"""
    return request_ws if request_ws else payload.workspace_id


def _check_tenant_access(payload: TokenPayload, target_tenant_id: str) -> None:
    """验证跨 tenant 访问: 非 super_admin 不能访问其他 tenant 的 installation。"""
    if payload.is_super_admin:
        return
    if target_tenant_id != payload.workspace_id:
        raise HTTPException(status_code=404, detail="安装记录不存在")


def _try_record_usage(
    usage_store: UsageStoreAdapter | None,
    tenant_id: str,
    user_id: str,
    workspace_id: str,
    resource: UsageResource,
    quantity: int = 1,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Best-effort 记录用量事件 — 失败仅 warning，不影响主流程。"""
    if usage_store is None:
        return
    try:
        event = UsageEvent(
            tenant_id=tenant_id,
            user_id=user_id,
            workspace_id=workspace_id,
            resource=resource,
            quantity=quantity,
            unit=UsageUnit.COUNT,
            metadata=metadata or {},
        )
        usage_store.record_event(event)
    except Exception:
        logger.warning("marketplace_usage_record_failed", exc_info=True,
                       extra={"tenant_id": tenant_id, "resource": resource.value})


def _check_plan_agent_limit(
    tenant_id: str,
    subscription_store: Any,
    marketplace_store: Any,
) -> tuple[bool, int, int]:
    """检查当前 plan 的 Agent 安装数量限制。

    Returns:
        (allowed, current_count, max_limit)
    """
    if subscription_store is None or marketplace_store is None:
        return True, 0, -1  # 无 subscription store 时不限制
    try:
        sub = subscription_store.get_subscription(tenant_id)
        if sub is None:
            return True, 0, -1
        plan_limit = sub.plan_limit()
        max_agents = getattr(plan_limit, "max_marketplace_agents", 999999)
    except Exception:
        return True, 0, -1  # 异常时不限制

    installations = marketplace_store.list_installations(tenant_id=tenant_id)
    # 只计数 active/disabled 的安装（不含 uninstalled 软删除）
    current = len([i for i in installations if i.status != "uninstalled"])

    return current < max_agents, current, max_agents


# ═══════════════════════════════════════════
# Router Factory
# ═══════════════════════════════════════════


def create_marketplace_router(
    marketplace_store: SQLiteMarketplaceStore,
    usage_store: UsageStoreAdapter | None = None,
    subscription_store: Any = None,
) -> APIRouter:
    """创建 Marketplace API 路由。

    Args:
        marketplace_store: SQLiteMarketplaceStore 实例。
        usage_store: 可选的 UsageStoreAdapter，用于记录用量事件。
        subscription_store: 可选的 SubscriptionStoreAdapter，用于检查 PlanLimit。

    Returns:
        配置好的 APIRouter。
    """
    router = APIRouter(prefix="/agent-marketplace", tags=["agent-marketplace"])

    # ═══════════════════════════════════════════
    # 固定路径路由（必须在参数化路径之前）
    # ═══════════════════════════════════════════

    # ── 1. 浏览 Marketplace ──

    @router.get("")
    async def browse_marketplace(
        category: str = Query(default="", description="按分类过滤"),
        department: str | None = Query(default=None, description="按部门过滤"),
        status: str = Query(default="", description="按状态过滤: active/beta/deprecated/disabled"),
        visibility: str = Query(default="", description="按可见性过滤: public/private/beta"),
        installed: bool | None = Query(default=None, description="仅已安装/未安装"),
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """浏览 Marketplace Agent 目录。

        每个 agent 附带当前租户/工作区的安装状态（is_installed + installation）。
        """
        tid = payload.workspace_id
        ws = payload.workspace_id

        agents = marketplace_store.list_agents(
            category=category,
            department=department,
            status=status,
            visibility=visibility,
        )

        if installed is not None:
            if installed:
                agents = [a for a in agents if marketplace_store.is_agent_installed(a.marketplace_agent_id, tid, ws)]
            else:
                agents = [a for a in agents if not marketplace_store.is_agent_installed(a.marketplace_agent_id, tid, ws)]

        all_agents = marketplace_store.list_agents()
        categories = sorted({a.category for a in all_agents if a.category})
        departments = sorted({a.department for a in all_agents if a.department})

        # 为每个 agent 附加安装状态（减少前端额外 API 调用）
        agent_dicts = []
        for a in agents:
            d = a.to_dict()
            inst = marketplace_store.get_installation_by_agent(a.marketplace_agent_id, tid, ws)
            d["is_installed"] = inst is not None
            d["installation"] = inst.to_dict() if inst else None
            agent_dicts.append(d)

        return {
            "agents": agent_dicts,
            "total": len(agent_dicts),
            "categories": categories,
            "departments": departments,
        }

    # ── 2. 分类列表 ──

    @router.get("/categories")
    async def list_categories(
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """返回所有已存在的分类。"""
        agents = marketplace_store.list_agents()
        categories = sorted({a.category for a in agents if a.category})
        return {"categories": categories}

    # ── 3. 部门列表 ──

    @router.get("/departments")
    async def list_departments(
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """返回所有已存在的部门。"""
        agents = marketplace_store.list_agents()
        departments = sorted({a.department for a in agents if a.department})
        return {"departments": departments}

    # ── 4. 安装列表 ──

    @router.get("/installations")
    async def list_installations(
        workspace_id: str = Query(default="", description="工作区 ID，缺省使用当前工作区"),
        include_disabled: bool = Query(default=True, description="是否包含已停用的安装"),
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """查看当前 tenant/workspace 的 Agent 安装列表。"""
        tenant_id = payload.workspace_id
        ws_id = _resolve_workspace_id(payload, workspace_id)

        installations = marketplace_store.list_installations(
            tenant_id=tenant_id,
            workspace_id=ws_id,
        )

        if not include_disabled:
            installations = [i for i in installations if i.status == "active"]

        return {
            "installations": [i.to_dict() for i in installations],
            "total": len(installations),
        }

    # ── 5. 安装详情 ──

    @router.get("/installations/{installation_id}")
    async def get_installation(
        installation_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """查看单个安装详情。只能查看当前 tenant 的 installation。"""
        installation = marketplace_store.get_installation(installation_id)
        if installation is None:
            raise HTTPException(status_code=404, detail="安装记录不存在")

        _check_tenant_access(payload, installation.tenant_id)

        agent = marketplace_store.get_agent(installation.marketplace_agent_id)

        return {
            "installation": installation.to_dict(),
            "agent": agent.to_dict() if agent else None,
        }

    # ── 6. 启用安装 ──

    @router.post("/installations/{installation_id}/enable")
    async def enable_installation(
        installation_id: str,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        """启用一个已停用的安装。"""
        installation = marketplace_store.get_installation(installation_id)
        if installation is None:
            raise HTTPException(status_code=404, detail="安装记录不存在")

        _check_tenant_access(payload, installation.tenant_id)

        ok = marketplace_store.enable_installation(
            installation_id, installation.tenant_id, installation.workspace_id,
        )
        if not ok:
            raise HTTPException(status_code=404, detail="安装记录不存在")

        updated = marketplace_store.get_installation(installation_id)
        return {"installation": updated.to_dict() if updated else None}

    # ── 7. 停用安装 ──

    @router.post("/installations/{installation_id}/disable")
    async def disable_installation(
        installation_id: str,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        """停用一个安装。"""
        installation = marketplace_store.get_installation(installation_id)
        if installation is None:
            raise HTTPException(status_code=404, detail="安装记录不存在")

        _check_tenant_access(payload, installation.tenant_id)

        ok = marketplace_store.disable_installation(
            installation_id, installation.tenant_id, installation.workspace_id,
        )
        if not ok:
            raise HTTPException(status_code=404, detail="安装记录不存在")

        updated = marketplace_store.get_installation(installation_id)
        return {"installation": updated.to_dict() if updated else None}

    # ── 8. 更新安装配置 ──

    @router.patch("/installations/{installation_id}/config")
    async def update_installation_config(
        installation_id: str,
        body: UpdateInstallationConfigRequest = UpdateInstallationConfigRequest(),
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        """更新安装配置（合并更新 config + 替换 permissions_granted/usage_limit_override/version_pinned）。"""
        installation = marketplace_store.get_installation(installation_id)
        if installation is None:
            raise HTTPException(status_code=404, detail="安装记录不存在")

        _check_tenant_access(payload, installation.tenant_id)

        tid = installation.tenant_id
        ws = installation.workspace_id

        # 更新 config（合并）
        if body.config:
            ok = marketplace_store.update_installation_config(installation_id, tid, ws, body.config)
            if not ok:
                raise HTTPException(status_code=404, detail="安装记录不存在")

        # 更新 permissions_granted / usage_limit_override / version_pinned
        now_ts = datetime.now(timezone.utc).isoformat()
        if body.permissions_granted:
            marketplace_store._exec(
                "UPDATE tenant_agent_installations SET permissions_granted_json=?, updated_at=? "
                "WHERE installation_id=? AND tenant_id=? AND workspace_id=?",
                [json.dumps(body.permissions_granted, ensure_ascii=False), now_ts,
                 installation_id, tid, ws],
            )
        if body.usage_limit_override:
            marketplace_store._exec(
                "UPDATE tenant_agent_installations SET usage_limit_override_json=?, updated_at=? "
                "WHERE installation_id=? AND tenant_id=? AND workspace_id=?",
                [json.dumps(body.usage_limit_override, ensure_ascii=False), now_ts,
                 installation_id, tid, ws],
            )
        if body.version_pinned is not None:
            marketplace_store._exec(
                "UPDATE tenant_agent_installations SET version_pinned=?, updated_at=? "
                "WHERE installation_id=? AND tenant_id=? AND workspace_id=?",
                [body.version_pinned, now_ts, installation_id, tid, ws],
            )

        updated = marketplace_store.get_installation(installation_id)
        return {"installation": updated.to_dict() if updated else None}

    # ── 9. 软卸载 ──

    @router.delete("/installations/{installation_id}")
    async def uninstall_agent(
        installation_id: str,
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        """软卸载 Agent（status=uninstalled, enabled=False）。"""
        installation = marketplace_store.get_installation(installation_id)
        if installation is None:
            raise HTTPException(status_code=404, detail="安装记录不存在")

        _check_tenant_access(payload, installation.tenant_id)

        ok = marketplace_store.uninstall_agent(
            installation_id, installation.tenant_id, installation.workspace_id,
        )
        if not ok:
            raise HTTPException(status_code=404, detail="安装记录不存在")

        logger.info("marketplace_agent_uninstalled", extra={
            "installation_id": installation_id,
            "marketplace_agent_id": installation.marketplace_agent_id,
            "tenant_id": installation.tenant_id,
        })

        return {"success": True}

    # ── 10. 安装用量 ──

    @router.get("/installations/{installation_id}/usage")
    async def get_installation_usage(
        installation_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """获取安装的用量概览。

        从 UsageStore 查询 agent_run / agent_install 事件，按 30 天 period 聚合。
        不实现真实扣费。
        """
        installation = marketplace_store.get_installation(installation_id)
        if installation is None:
            raise HTTPException(status_code=404, detail="安装记录不存在")

        _check_tenant_access(payload, installation.tenant_id)

        total_calls = 0
        period_calls = 0
        install_events = 0
        last_used_at: str | None = None

        if usage_store is not None:
            try:
                # 查询 agent_run 事件（过去 30 天）
                now = datetime.now(timezone.utc)
                thirty_days_ago = now - timedelta(days=30)

                run_events = usage_store.query_events(
                    tenant_id=installation.tenant_id,
                    resource="agent_run",
                    start=thirty_days_ago,
                    limit=10000,
                )
                agent_run_events = [
                    e for e in run_events
                    if e.metadata.get("agent_id") == installation.agent_id
                ]
                total_calls = len(agent_run_events)
                period_calls = total_calls

                if agent_run_events:
                    latest = max(agent_run_events, key=lambda e: e.timestamp if e.timestamp else datetime.min)
                    if latest.timestamp:
                        last_used_at = latest.timestamp.isoformat()

                # 查询 agent_install 事件
                install_evs = usage_store.query_events(
                    tenant_id=installation.tenant_id,
                    resource="agent_install",
                    limit=10000,
                )
                install_events = len([
                    e for e in install_evs
                    if e.metadata.get("installation_id") == installation_id
                ])
            except Exception:
                logger.warning("installation_usage_query_failed", exc_info=True,
                               extra={"installation_id": installation_id})

        # limit / remaining 逻辑
        limit = (
            installation.usage_limit_override.get("max_calls")
            if installation.usage_limit_override and "max_calls" in installation.usage_limit_override
            else None
        )
        # 如果 usage_limit_override 没有设置，则从 plan limit 推导
        if limit is None and subscription_store is not None:
            try:
                sub = subscription_store.get_subscription(installation.tenant_id)
                if sub:
                    plan_limit = sub.plan_limit()
                    limit = plan_limit.llm_calls_per_day
            except Exception:
                pass

        remaining = max(0, limit - period_calls) if limit is not None and isinstance(limit, (int, float)) else None

        return {
            "installation_id": installation_id,
            "agent_id": installation.agent_id,
            "marketplace_agent_id": installation.marketplace_agent_id,
            "total_calls": total_calls,
            "period_calls": period_calls,
            "install_events": install_events,
            "last_used_at": last_used_at,
            "limit": limit,
            "remaining": remaining,
            "billing_note": "MVP usage only; no real payment charge.",
        }

    # ── A. Marketplace Analytics Summary ──

    @router.get("/analytics/summary")
    async def marketplace_analytics_summary(
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """Marketplace Analytics MVP — 返回当前 tenant 的 marketplace 使用概况。

        统计来源：MarketplaceStore + UsageStore。
        不跨 tenant，不接入真实支付。
        """
        tid = payload.workspace_id
        ws = payload.workspace_id

        # Marketplace Agent 总数
        all_agents = marketplace_store.list_agents()
        total_marketplace_agents = len(all_agents)

        # 当前 tenant/workspace 安装统计
        installations = marketplace_store.list_installations(tenant_id=tid, workspace_id=ws)
        installed_count = len(installations)
        enabled_count = len([i for i in installations if i.status == "active" and i.enabled])
        disabled_count = len([i for i in installations if i.status == "disabled" or not i.enabled])

        # Usage events 统计
        install_events = 0
        agent_runs = 0
        top_categories: dict[str, int] = {}
        top_agents: dict[str, int] = {}

        if usage_store is not None:
            try:
                evs = usage_store.query_events(
                    tenant_id=tid,
                    resource="agent_install",
                    limit=10000,
                )
                install_events = len(evs)

                run_evs = usage_store.query_events(
                    tenant_id=tid,
                    resource="agent_run",
                    limit=10000,
                )
                agent_runs = len(run_evs)

                for e in run_evs:
                    aid = e.metadata.get("agent_id", "unknown")
                    top_agents[aid] = top_agents.get(aid, 0) + 1
                    cat = e.metadata.get("department", "") or "未分类"
                    top_categories[cat] = top_categories.get(cat, 0) + 1
            except Exception:
                logger.warning("marketplace_analytics_query_failed", exc_info=True,
                               extra={"tenant_id": tid})

        return {
            "total_marketplace_agents": total_marketplace_agents,
            "installed_agents": installed_count,
            "enabled_installations": enabled_count,
            "disabled_installations": disabled_count,
            "install_events": install_events,
            "agent_runs": agent_runs,
            "top_categories": dict(sorted(top_categories.items(), key=lambda x: -x[1])[:5]),
            "top_agents": dict(sorted(top_agents.items(), key=lambda x: -x[1])[:5]),
            "billing_note": "MVP analytics; no real payment charge.",
        }

    # ═══════════════════════════════════════════
    # 参数化路径路由（带 {marketplace_agent_id}，必须在固定路径之后）
    # ═══════════════════════════════════════════

    # ── 11. Agent 详情 ──

    @router.get("/{marketplace_agent_id}")
    async def get_marketplace_agent(
        marketplace_agent_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """获取 Marketplace Agent 详情，含当前用户的安装状态。"""
        agent = marketplace_store.get_agent(marketplace_agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent {marketplace_agent_id} 不存在")

        tenant_id = payload.workspace_id
        ws_id = payload.workspace_id
        installation = marketplace_store.get_installation_by_agent(
            marketplace_agent_id, tenant_id, ws_id,
        )

        return {
            "agent": agent.to_dict(),
            "is_installed": installation is not None,
            "installation": installation.to_dict() if installation else None,
        }

    # ── 12. 安装 Agent ──

    @router.post("/{marketplace_agent_id}/install", status_code=201)
    async def install_agent(
        marketplace_agent_id: str,
        body: InstallAgentRequest = InstallAgentRequest(),
        payload: TokenPayload = Depends(_require_admin),
    ) -> dict[str, Any]:
        """安装 Agent 到指定 tenant/workspace。

        要求 admin/owner 角色。重复安装返回 409。Agent 不存在返回 404。
        """
        agent = marketplace_store.get_agent(marketplace_agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent {marketplace_agent_id} 不存在")

        tenant_id = payload.workspace_id
        ws_id = _resolve_workspace_id(payload, body.workspace_id)

        # 检查 plan limit（super_admin 绕过）
        if not payload.is_super_admin:
            allowed, current, max_count = _check_plan_agent_limit(
                tenant_id, subscription_store, marketplace_store,
            )
            if not allowed:
                raise HTTPException(
                    status_code=403,
                    detail=f"Agent 安装数量已达上限。当前: {current}/{max_count}。"
                           f"如需安装更多 Agent，请升级套餐或卸载不需要的 Agent。",
                )

        try:
            installation = marketplace_store.install_agent(
                marketplace_agent_id=marketplace_agent_id,
                agent_id=agent.agent_id,
                tenant_id=tenant_id,
                workspace_id=ws_id,
                installed_by=payload.user_id,
                config=body.config,
                permissions_granted=body.permissions_granted,
            )
        except DuplicateInstallationError:
            raise HTTPException(status_code=409, detail="该 Agent 已安装到此工作区")

        # 持久化 usage_limit_override 和 version_pinned
        if body.usage_limit_override or body.version_pinned is not None:
            now_ts = datetime.now(timezone.utc).isoformat()
            if body.usage_limit_override:
                marketplace_store._exec(
                    "UPDATE tenant_agent_installations SET usage_limit_override_json=?, updated_at=? "
                    "WHERE installation_id=? AND tenant_id=? AND workspace_id=?",
                    [json.dumps(body.usage_limit_override, ensure_ascii=False), now_ts,
                     installation.installation_id, tenant_id, ws_id],
                )
            if body.version_pinned is not None:
                marketplace_store._exec(
                    "UPDATE tenant_agent_installations SET version_pinned=?, updated_at=? "
                    "WHERE installation_id=? AND tenant_id=? AND workspace_id=?",
                    [body.version_pinned, now_ts, installation.installation_id, tenant_id, ws_id],
                )
            # 重新读取以获取更新后的 installation
            installation = marketplace_store.get_installation(installation.installation_id)

        _try_record_usage(
            usage_store,
            tenant_id=tenant_id,
            user_id=payload.user_id,
            workspace_id=ws_id,
            resource=UsageResource.AGENT_INSTALL,
            metadata={
                "marketplace_agent_id": marketplace_agent_id,
                "agent_id": agent.agent_id,
                "installation_id": installation.installation_id,
            },
        )

        logger.info("marketplace_agent_installed", extra={
            "installation_id": installation.installation_id,
            "marketplace_agent_id": marketplace_agent_id,
            "tenant_id": tenant_id,
            "workspace_id": ws_id,
            "installed_by": payload.user_id,
        })

        return {
            "installation": installation.to_dict(),
            "agent": agent.to_dict(),
        }

    # ── 13. 权限需求 ──

    @router.get("/{marketplace_agent_id}/permissions")
    async def get_agent_permissions(
        marketplace_agent_id: str,
        payload: TokenPayload = Depends(require_auth),
    ) -> dict[str, Any]:
        """查看 Agent 的权限需求及当前安装的授权状态。"""
        agent = marketplace_store.get_agent(marketplace_agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent {marketplace_agent_id} 不存在")

        required = agent.required_permissions

        tenant_id = payload.workspace_id
        ws_id = payload.workspace_id
        installation = marketplace_store.get_installation_by_agent(
            marketplace_agent_id, tenant_id, ws_id,
        )

        granted = installation.permissions_granted if installation else []
        missing = [p for p in required if p not in granted]

        return {
            "required": required,
            "granted": granted,
            "missing": missing,
        }

    return router
