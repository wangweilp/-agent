"""Team Analytics Domain Models — WorkspaceAnalytics + AnalyticsStore protocol.

六边形架构核心层：只定义数据类和协议。
"""
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class WorkspaceAnalytics:
    """工作区分析数据 — 团队面板核心指标。"""
    member_count: int = 0
    memory_by_type: dict[str, int] = field(default_factory=dict)
    memory_growth: list[dict] = field(default_factory=list)
    top_entities: list[dict] = field(default_factory=list)
    top_contributors: list[dict] = field(default_factory=list)
    action_completion_rate: float = 0.0
    media_breakdown: dict[str, int] = field(default_factory=dict)
    weekly_active_users: int = 0


@runtime_checkable
class AnalyticsStore(Protocol):
    """分析存储协议。"""

    def get_workspace_analytics(self, workspace_id: str, memory_store) -> WorkspaceAnalytics: ...
    def get_memory_by_type(self, workspace_id: str, memory_store) -> dict[str, int]: ...
    def get_growth_trend(self, workspace_id: str, memory_store, days: int = 30) -> list[dict]: ...
    def get_top_contributors(self, workspace_id: str, days: int = 30) -> list[dict]: ...
    def get_media_breakdown(self, workspace_id: str, memory_store) -> dict[str, int]: ...
