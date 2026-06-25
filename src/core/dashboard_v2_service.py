"""Dashboard V2 Service — 聚合 AnalyticsRepository，返回 Pydantic 响应模型。

职责：
- 调用 AnalyticsRepository 获取原始数据
- 组装为 OverviewResponse / GrowthResponse / AgentPerformanceResponse / MemoryHealthResponse
- 异常降级：任何查询失败返回默认值，保证仪表盘不崩

禁止 SQL 出现在 Router 中 — 所有数据访问通过 Repository。
"""
import logging

from src.api.dashboard_v2_schemas import (
    AgentPerformanceResponse,
    CohortRow,
    FunnelStage,
    GrowthResponse,
    LatencyPercentiles,
    MemoryHealthResponse,
    MemoryTypeItem,
    MetricPoint,
    OverviewResponse,
)
from src.core.analytics.analytics_repository import AnalyticsRepository

logger = logging.getLogger(__name__)


class DashboardV2Service:
    """Dashboard V2 业务层。

    接受一个 AnalyticsRepository 实例，聚合 P0 指标。
    """

    def __init__(self, repo: AnalyticsRepository) -> None:
        self._repo = repo

    # ── 概览 ──────────────────────────────────────────────

    def get_overview(self, tenant_id: str = "") -> OverviewResponse:
        """概览 KPI 墙 — 商业 + 增长 + Agent + Memory + 成本。"""
        try:
            return OverviewResponse(
                # 商业
                mrr_cents=self._repo.get_mrr_cents(),
                arr_cents=self._repo.get_arr_cents(),
                arpu_cents=self._repo.get_arpu_cents(),
                gross_margin_pct=self._repo.get_gross_margin_pct(),
                # 增长
                dau=self._repo.get_dau(tenant_id),
                wau=self._repo.get_wau(tenant_id),
                mau=self._repo.get_mau(tenant_id),
                retention_d1=self._repo.get_retention_d1(tenant_id),
                retention_d7=self._repo.get_retention_d7(tenant_id),
                # Agent
                agent_success_rate=self._repo.get_agent_success_rate(tenant_id, days=1),
                p95_latency_ms=self._repo.get_p95_latency_ms(tenant_id, days=1),
                token_cost_today_cents=self._repo.get_token_cost_cents(tenant_id, days=1),
                # Memory
                total_memories=self._repo.get_total_memories(tenant_id),
                memory_hit_rate=self._repo.get_memory_hit_rate(tenant_id),
                net_growth_today=self._repo.get_net_memory_growth(tenant_id, days=1),
            )
        except Exception:
            logger.warning("dashboard_v2_overview_failed", exc_info=True)
            return OverviewResponse()

    # ── 增长 ──────────────────────────────────────────────

    def get_growth(self, tenant_id: str = "", days: int = 30) -> GrowthResponse:
        """增长指标 — DAU/WAU/MAU 趋势 + 留存队列 + 转化漏斗 + 激活率。"""
        try:
            dau_series = self._repo.get_dau_series(tenant_id, days=days)
            # WAU/MAU 复用 DAU 序列接口（按日聚合，前端可自行滚动计算）
            wau_series = self._repo.get_dau_series(tenant_id, days=min(days, 7))
            mau_series = self._repo.get_dau_series(tenant_id, days=min(days, 30))

            cohort_rows = self._repo.get_retention_cohort(tenant_id, weeks=8)
            retention_cohort = [
                CohortRow(
                    cohort_date=r.get("cohort_date", ""),
                    cohort_size=r.get("cohort_size", 0),
                    d1=r.get("d1", 0.0),
                    d7=r.get("d7", 0.0),
                )
                for r in cohort_rows
            ]

            funnel_data = self._repo.get_conversion_funnel(tenant_id, days=days)
            funnel = [
                FunnelStage(stage=f.get("stage", ""), count=f.get("count", 0))
                for f in funnel_data
            ]

            activation_rate = self._repo.get_activation_rate(tenant_id, days=days)

            return GrowthResponse(
                dau_series=[MetricPoint(date=p.get("date", ""), value=p.get("value", 0.0)) for p in dau_series],
                wau_series=[MetricPoint(date=p.get("date", ""), value=p.get("value", 0.0)) for p in wau_series],
                mau_series=[MetricPoint(date=p.get("date", ""), value=p.get("value", 0.0)) for p in mau_series],
                retention_cohort=retention_cohort,
                funnel=funnel,
                activation_rate=activation_rate,
            )
        except Exception:
            logger.warning("dashboard_v2_growth_failed", exc_info=True)
            return GrowthResponse()

    # ── Agent 性能 ───────────────────────────────────────

    def get_agent_performance(self, tenant_id: str = "", days: int = 7) -> AgentPerformanceResponse:
        """Agent 性能指标 — 调用量 + 成功率 + 真实延迟分位数 + Token。"""
        try:
            success_rate = self._repo.get_agent_success_rate(tenant_id, days=days)
            failure_rate = round(100.0 - success_rate, 2) if success_rate > 0 else 0.0

            # 真实 P50/P95/P99（Phase 25 升级，移除估算逻辑）
            percentiles = self._repo.get_latency_percentiles(tenant_id, days=days)
            latency = LatencyPercentiles(
                p50_ms=percentiles.get("p50_ms", 0.0),
                p95_ms=percentiles.get("p95_ms", 0.0),
                p99_ms=percentiles.get("p99_ms", 0.0),
            )

            call_series = self._repo.get_agent_call_volume_series(tenant_id, days=days)
            token_series = self._repo.get_token_usage_series(tenant_id, days=days)
            token_cost = self._repo.get_token_cost_cents(tenant_id, days=days)

            return AgentPerformanceResponse(
                call_volume_series=[
                    MetricPoint(date=p.get("date", ""), value=p.get("value", 0.0))
                    for p in call_series
                ],
                success_rate=success_rate,
                failure_rate=failure_rate,
                latency=latency,
                token_usage_series=[
                    MetricPoint(date=p.get("date", ""), value=p.get("value", 0.0))
                    for p in token_series
                ],
                token_cost_cents=token_cost,
            )
        except Exception:
            logger.warning("dashboard_v2_agent_performance_failed", exc_info=True)
            return AgentPerformanceResponse()

    # ── Memory 健康 ───────────────────────────────────────

    def get_memory_health(self, tenant_id: str = "", days: int = 30) -> MemoryHealthResponse:
        """Memory 健康指标 — 增长 + 命中率 + 类型分布。"""
        try:
            growth_series = self._repo.get_memory_growth_series(tenant_id, days=days)
            hit_rate = self._repo.get_memory_hit_rate(tenant_id)
            total = self._repo.get_total_memories(tenant_id)
            active = self._repo.get_active_memories(tenant_id)
            net_growth = self._repo.get_net_memory_growth(tenant_id, days=days)
            type_dist = self._repo.get_memory_type_distribution(tenant_id)

            return MemoryHealthResponse(
                growth_series=[
                    MetricPoint(date=p.get("date", ""), value=p.get("value", 0.0))
                    for p in growth_series
                ],
                hit_rate=hit_rate,
                total_memories=total,
                active_memories=active,
                net_growth=net_growth,
                type_distribution=[
                    MemoryTypeItem(memory_type=t.get("memory_type", ""), count=t.get("count", 0))
                    for t in type_dist
                ],
            )
        except Exception:
            logger.warning("dashboard_v2_memory_health_failed", exc_info=True)
            return MemoryHealthResponse()
