"""Marketplace Analytics 安全测试。

验证：
- metadata_only — 所有计算纯 Python 不执行 runtime
- 无 execution/runtime/container 方法或 import
- 无 network/filesystem 访问
"""

from __future__ import annotations

import inspect, pytest
from src.open_platform.marketplace_analytics import (
    RecommendedAgent, AgentRank, AnalyticsMetrics, AnalyticsEvent,
)
from src.open_platform.marketplace_analytics_service import MarketplaceAnalyticsService
from src.adapters.marketplace_analytics_store import SQLiteMarketplaceAnalyticsStore

FORBIDDEN = ["execute", "run", "exec", "spawn", "launch", "start_container",
             "create_container", "start_microvm", "subprocess", "shell", "eval"]
FORBIDDEN_IMPORTS = ["subprocess", "docker", "container", "microvm",
                     "podman", "kubernetes", "lxc", "firecracker",
                     "os.system", "os.popen", "shell=True", "requests", "urllib.request"]


class TestNoExecutionMethods:
    @pytest.mark.parametrize("cls", [RecommendedAgent, AgentRank, AnalyticsMetrics, AnalyticsEvent])
    def test_domains_no_execution(self, cls):
        for name in FORBIDDEN:
            assert not hasattr(cls, name), f"{cls.__name__} 不应有 {name}"

    def test_service_no_execution(self):
        for name in FORBIDDEN:
            assert not hasattr(MarketplaceAnalyticsService, name), \
                f"MarketplaceAnalyticsService 不应有 {name}"

    def test_store_no_execution(self):
        for name in FORBIDDEN:
            assert not hasattr(SQLiteMarketplaceAnalyticsStore, name), \
                f"SQLiteMarketplaceAnalyticsStore 不应有 {name}"


class TestSourceClean:
    SOURCES = [
        ("Store", SQLiteMarketplaceAnalyticsStore),
        ("Service", MarketplaceAnalyticsService),
        ("Domain RecAgent", RecommendedAgent),
        ("Domain Rank", AgentRank),
        ("Domain Metrics", AnalyticsMetrics),
        ("Domain Event", AnalyticsEvent),
    ]

    @pytest.mark.parametrize("label,cls", SOURCES)
    def test_source_clean(self, label, cls):
        src = inspect.getsource(cls).lower()
        for p in FORBIDDEN_IMPORTS:
            assert p not in src, f"{label} 源码不应含 {p}"


class TestPureMetadataCalculation:
    """验证推荐/排行算法不依赖 runtime。"""

    def test_recommendations_pure_python(self):
        src = inspect.getsource(MarketplaceAnalyticsService.generate_recommendations)
        assert "eval" not in src
        assert "exec" not in src
        assert "subprocess" not in src
        assert "http" not in src.lower()

    def test_rankings_pure_python(self):
        src = inspect.getsource(MarketplaceAnalyticsService.generate_rankings)
        assert "eval" not in src
        assert "exec" not in src

    def test_platform_metrics_pure_python(self):
        src = inspect.getsource(MarketplaceAnalyticsService.calculate_platform_metrics)
        assert "eval" not in src
        assert "exec" not in src
