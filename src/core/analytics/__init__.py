"""Analytics 子包 — 团队分析数据模型 + Dashboard V2 统计仓库 + Analytics Pipeline。

兼容旧导入路径：
    from src.core.analytics import WorkspaceAnalytics, AnalyticsStore

新增子模块：
    from src.core.analytics.analytics_repository import AnalyticsRepository
    from src.core.analytics.analytics_store import AnalyticsStore as AnalyticsPipelineStore
"""
from src.core.analytics.analytics_repository import AnalyticsRepository
from src.core.analytics.analytics_store import AnalyticsStore as AnalyticsPipelineStore
from src.core.analytics.team_analytics import AnalyticsStore, WorkspaceAnalytics

__all__ = [
    "AnalyticsPipelineStore",
    "AnalyticsRepository",
    "AnalyticsStore",
    "WorkspaceAnalytics",
]
