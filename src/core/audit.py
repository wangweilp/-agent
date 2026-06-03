"""审计和通知的领域扩展 — AuditSummary / UserActivity / NotificationPreferences。"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from src.core.collaboration import AuditLog


# ── Audit Summary ──


@dataclass
class AuditSummary:
    """审计摘要 — 最近 24h/7d/30d 各操作计数。"""
    workspace_id: str
    last_24h: dict[str, int] = field(default_factory=dict)   # action -> count
    last_7d: dict[str, int] = field(default_factory=dict)
    last_30d: dict[str, int] = field(default_factory=dict)
    total: int = 0


# ── User Activity ──


@dataclass
class UserActivity:
    """用户活动时间线。"""
    user_id: str
    workspace_id: str
    daily_actions: list[dict[str, Any]] = field(default_factory=list)   # [{date, count}]
    top_actions: list[dict[str, Any]] = field(default_factory=list)     # [{action, count}]
    total_actions: int = 0


# ── Notification Preferences ──


@dataclass
class NotificationPreferences:
    """通知偏好设置。"""
    user_id: str
    workspace_id: str
    email_enabled: bool = True
    push_enabled: bool = True
    digest_frequency: str = "daily"   # daily | weekly | none


# ── AuditStore Protocol ──


@runtime_checkable
class AuditStore(Protocol):
    """审计存储协议 — 扩展审计日志、摘要、时间线、修剪。"""

    def log(self, entry: AuditLog) -> None: ...
    def list_for_workspace(self, workspace_id: str, limit: int = 50, action: str = "") -> list[AuditLog]: ...
    def list_for_user(self, user_id: str, workspace_id: str, limit: int = 30) -> list[AuditLog]: ...
    def get_audit_summary(self, workspace_id: str) -> AuditSummary: ...
    def get_user_activity_timeline(self, user_id: str, workspace_id: str, days: int = 7) -> UserActivity: ...
    def prune_old_logs(self, workspace_id: str, days: int) -> int: ...
    def get_notification_preferences(self, user_id: str, workspace_id: str) -> NotificationPreferences: ...
    def update_notification_preferences(self, prefs: NotificationPreferences) -> None: ...
