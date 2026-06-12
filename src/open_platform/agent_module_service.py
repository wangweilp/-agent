"""Agent Module Service + Marketplace Service。

约束: metadata-only，审核流水线，不可执行。
"""

from __future__ import annotations

import logging
from typing import Any

from src.open_platform.agent_module import (
    AgentModule, AgentModuleNotFoundError, AgentModuleStateError,
    AgentModuleStatus, AgentModuleValidationError,
    Subscription, SubscriptionAlreadyExistsError, SubscriptionNotFoundError,
)

logger = logging.getLogger(__name__)


class AgentModuleService:
    """Agent 模块生命周期管理。"""

    def __init__(self, store) -> None:
        self._store = store

    def create_module(
        self, workspace_id: str, name: str,
        description: str = "", workflow_ids: list[str] | None = None,
        version: str = "0.1.0", author: str = "", category: str = "",
        icon_url: str = "", tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentModule:
        m = AgentModule(
            workspace_id=workspace_id, name=name, description=description,
            workflow_ids=workflow_ids or [], version=version,
            status=AgentModuleStatus.DRAFT, metadata_only=True,
            author=author, category=category, icon_url=icon_url,
            tags=tags or [], metadata=metadata or {},
        )
        errors = m.validate()
        if errors:
            raise AgentModuleValidationError(f"校验失败: {'; '.join(errors)}", errors)
        created = self._store.create(m)
        logger.info("agent_module_created", extra={"module_id": created.id, "name": name})
        return created

    def submit_review(self, module_id: str) -> AgentModule:
        m = self._store.get(module_id)
        if m is None:
            raise AgentModuleNotFoundError(f"AgentModule 不存在: {module_id}")
        if m.status != AgentModuleStatus.DRAFT:
            raise AgentModuleStateError(f"只有 draft 可提交审核，当前: {m.status}")
        self._store.update_status(module_id, AgentModuleStatus.REVIEW)
        return self._store.get(module_id)  # type: ignore[return-value]

    def approve(self, module_id: str, reviewer_id: str, comment: str = "") -> AgentModule:
        m = self._store.get(module_id)
        if m is None:
            raise AgentModuleNotFoundError(f"AgentModule 不存在: {module_id}")
        if m.status != AgentModuleStatus.REVIEW:
            raise AgentModuleStateError(f"只有 review 可 approve，当前: {m.status}")
        self._store.update_status(module_id, AgentModuleStatus.APPROVED,
                                  reviewed_by=reviewer_id, review_comment=comment)
        return self._store.get(module_id)  # type: ignore[return-value]

    def reject(self, module_id: str, reviewer_id: str, comment: str = "") -> AgentModule:
        m = self._store.get(module_id)
        if m is None:
            raise AgentModuleNotFoundError(f"AgentModule 不存在: {module_id}")
        if m.status != AgentModuleStatus.REVIEW:
            raise AgentModuleStateError(f"只有 review 可 reject，当前: {m.status}")
        self._store.update_status(module_id, AgentModuleStatus.REJECTED,
                                  reviewed_by=reviewer_id, review_comment=comment)
        return self._store.get(module_id)  # type: ignore[return-value]

    def publish(self, module_id: str, publisher_id: str) -> AgentModule:
        m = self._store.get(module_id)
        if m is None:
            raise AgentModuleNotFoundError(f"AgentModule 不存在: {module_id}")
        if m.status != AgentModuleStatus.APPROVED:
            raise AgentModuleStateError(f"只有 approved 可 publish，当前: {m.status}")
        self._store.update_status(module_id, AgentModuleStatus.PUBLISHED,
                                  published_by=publisher_id)
        return self._store.get(module_id)  # type: ignore[return-value]

    def get(self, module_id: str) -> AgentModule | None:
        return self._store.get(module_id)

    def list(self, *, workspace_id: str = "", status: str = "",
             category: str = "", limit: int = 50, offset: int = 0) -> list[AgentModule]:
        return self._store.list(workspace_id=workspace_id, status=status,
                                category=category, limit=limit, offset=offset)

    def delete(self, module_id: str) -> None:
        self._store.delete(module_id)


class MarketplaceService:
    """Agent 模块市场 — 搜索、浏览、订阅。"""

    def __init__(self, store) -> None:
        self._store = store

    def search(self, q: str = "", *, category: str = "",
               limit: int = 50) -> list[AgentModule]:
        return self._store.search(q, category=category, limit=limit)

    def list_published(self, *, category: str = "",
                       limit: int = 50, offset: int = 0) -> list[AgentModule]:
        return self._store.list(status=AgentModuleStatus.PUBLISHED,
                                category=category, limit=limit, offset=offset)

    def subscribe(self, workspace_id: str, agent_module_id: str) -> Subscription:
        m = self._store.get(agent_module_id)
        if m is None:
            raise AgentModuleNotFoundError(f"AgentModule 不存在: {agent_module_id}")
        if not m.is_published():
            raise AgentModuleStateError(f"只有 published 模块可订阅，当前: {m.status}")
        sub = Subscription(workspace_id=workspace_id, agent_module_id=agent_module_id)
        created = self._store.subscribe(sub)
        logger.info("subscribed", extra={"workspace_id": workspace_id, "module_id": agent_module_id})
        return created

    def unsubscribe(self, workspace_id: str, agent_module_id: str) -> None:
        self._store.unsubscribe(workspace_id, agent_module_id)
        logger.info("unsubscribed", extra={"workspace_id": workspace_id, "module_id": agent_module_id})

    def list_subscriptions(self, workspace_id: str) -> list[Subscription]:
        return self._store.list_subscriptions(workspace_id)

    def get_subscription(self, workspace_id: str, agent_module_id: str) -> Subscription | None:
        return self._store.get_subscription(workspace_id, agent_module_id)
