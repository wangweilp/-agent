"""Marketplace Governance 安全测试。

验证：metadata_only=True，无 execution/runtime/container 方法或 import。
"""

from __future__ import annotations

import inspect, pytest
from src.open_platform.marketplace_governance import (
    Review, Report, TrustScore, GovernanceEvent,
)
from src.open_platform.marketplace_governance_service import MarketplaceGovernanceService
from src.adapters.marketplace_governance_store import SQLiteMarketplaceGovernanceStore

FORBIDDEN = ["execute", "run", "exec", "spawn", "launch", "start_container",
             "create_container", "start_microvm", "subprocess", "shell"]
FORBIDDEN_IMPORTS = ["subprocess", "docker", "container", "microvm",
                     "podman", "kubernetes", "lxc", "firecracker",
                     "os.system", "os.popen", "shell=True", "requests", "urllib.request"]


class TestNoExecutionMethods:
    @pytest.mark.parametrize("cls", [Review, Report, TrustScore, GovernanceEvent])
    def test_domains_no_execution(self, cls):
        for name in FORBIDDEN:
            assert not hasattr(cls, name), f"{cls.__name__} 不应有 {name}"

    def test_service_no_execution(self):
        for name in FORBIDDEN:
            assert not hasattr(MarketplaceGovernanceService, name), \
                f"MarketplaceGovernanceService 不应有 {name}"

    def test_store_no_execution(self):
        for name in FORBIDDEN:
            assert not hasattr(SQLiteMarketplaceGovernanceStore, name), \
                f"SQLiteMarketplaceGovernanceStore 不应有 {name}"


class TestSourceClean:
    SOURCES = [
        ("Store", SQLiteMarketplaceGovernanceStore),
        ("Service", MarketplaceGovernanceService),
        ("Domain Review", Review),
        ("Domain Report", Report),
        ("Domain TrustScore", TrustScore),
        ("Domain GovernanceEvent", GovernanceEvent),
    ]

    @pytest.mark.parametrize("label,cls", SOURCES)
    def test_source_clean(self, label, cls):
        src = inspect.getsource(cls).lower()
        for p in FORBIDDEN_IMPORTS:
            assert p not in src, f"{label} 源码不应含 {p}"


class TestTrustScorePureMetadata:
    """验证 TrustScore 计算完全不依赖 runtime。"""

    def test_calculate_is_pure_python(self):
        src = inspect.getsource(MarketplaceGovernanceService.calculate_trust_score)
        assert "subprocess" not in src
        assert "eval" not in src
        assert "exec" not in src
        assert "import" not in src or "import" in src.split("def")[0]  # only in type hints

    def test_risk_classify_is_pure(self):
        src = inspect.getsource(MarketplaceGovernanceService._classify_risk)
        assert "eval" not in src and "exec" not in src
