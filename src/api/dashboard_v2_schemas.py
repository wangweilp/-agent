"""Dashboard V2 API Schemas — Pydantic v2 响应模型。

P0 指标专用，禁止 Optional[Any]，全部使用 Field(default=...) / Field(default_factory=list)。
保证 OpenAPI 可生成，无 ForwardRef 错误。
"""
from pydantic import BaseModel, Field


# ── 共享子模型 ──────────────────────────────────────────

class MetricPoint(BaseModel):
    """时间序列数据点。"""
    date: str = Field(default="", description="日期（YYYY-MM-DD）")
    value: float = Field(default=0.0, description="指标值")


class FunnelStage(BaseModel):
    """漏斗阶段。"""
    stage: str = Field(default="", description="阶段名称")
    count: int = Field(default=0, description="用户数")


class CohortRow(BaseModel):
    """留存队列行。"""
    cohort_date: str = Field(default="", description="队列日期")
    cohort_size: int = Field(default=0, description="队列规模")
    d1: float = Field(default=0.0, description="次日留存率（%）")
    d7: float = Field(default=0.0, description="7日留存率（%）")


class LatencyPercentiles(BaseModel):
    """延迟分位数。"""
    p50_ms: float = Field(default=0.0, description="P50 延迟（毫秒）")
    p95_ms: float = Field(default=0.0, description="P95 延迟（毫秒）")
    p99_ms: float = Field(default=0.0, description="P99 延迟（毫秒）")


class MemoryTypeItem(BaseModel):
    """记忆类型分布项。"""
    memory_type: str = Field(default="", description="记忆类型")
    count: int = Field(default=0, description="数量")


# ── Overview ───────────────────────────────────────────

class OverviewResponse(BaseModel):
    """概览 KPI 墙 — 商业 + 增长 + Agent + Memory + 成本 核心指标。"""
    # 商业
    mrr_cents: int = Field(default=0, description="月度经常性收入（分）")
    arr_cents: int = Field(default=0, description="年化收入（分）")
    arpu_cents: int = Field(default=0, description="单用户平均收入（分）")
    gross_margin_pct: float = Field(default=0.0, description="毛利率（%）")
    # 增长
    dau: int = Field(default=0, description="日活跃用户数")
    wau: int = Field(default=0, description="周活跃用户数")
    mau: int = Field(default=0, description="月活跃用户数")
    retention_d1: float = Field(default=0.0, description="次日留存率（%）")
    retention_d7: float = Field(default=0.0, description="7日留存率（%）")
    # Agent
    agent_success_rate: float = Field(default=0.0, description="Agent 成功率（%）")
    p95_latency_ms: float = Field(default=0.0, description="P95 响应时间（毫秒）")
    token_cost_today_cents: int = Field(default=0, description="今日 Token 成本（分）")
    # Memory
    total_memories: int = Field(default=0, description="总记忆数")
    memory_hit_rate: float = Field(default=0.0, description="记忆命中率（%）")
    net_growth_today: int = Field(default=0, description="今日净增记忆数")


# ── Growth ─────────────────────────────────────────────

class GrowthResponse(BaseModel):
    """增长指标 — DAU/WAU/MAU 趋势 + 留存队列 + 转化漏斗 + 激活率。"""
    dau_series: list[MetricPoint] = Field(default_factory=list, description="DAU 时间序列")
    wau_series: list[MetricPoint] = Field(default_factory=list, description="WAU 时间序列")
    mau_series: list[MetricPoint] = Field(default_factory=list, description="MAU 时间序列")
    retention_cohort: list[CohortRow] = Field(default_factory=list, description="留存队列矩阵")
    funnel: list[FunnelStage] = Field(default_factory=list, description="转化漏斗")
    activation_rate: float = Field(default=0.0, description="激活率（%）")


# ── Agent Performance ───────────────────────────────────

class AgentPerformanceResponse(BaseModel):
    """Agent 性能指标 — 调用量 + 成功率 + 延迟 + Token。"""
    call_volume_series: list[MetricPoint] = Field(default_factory=list, description="调用量时间序列")
    success_rate: float = Field(default=0.0, description="成功率（%）")
    failure_rate: float = Field(default=0.0, description="失败率（%）")
    latency: LatencyPercentiles = Field(
        default_factory=LatencyPercentiles, description="延迟分位数"
    )
    token_usage_series: list[MetricPoint] = Field(default_factory=list, description="Token 消耗时间序列")
    token_cost_cents: int = Field(default=0, description="Token 成本（分）")


# ── Memory Health ───────────────────────────────────────

class MemoryHealthResponse(BaseModel):
    """Memory 健康指标 — 增长 + 命中率 + 类型分布。"""
    growth_series: list[MetricPoint] = Field(default_factory=list, description="记忆增长时间序列")
    hit_rate: float = Field(default=0.0, description="命中率（%）")
    total_memories: int = Field(default=0, description="总记忆数")
    active_memories: int = Field(default=0, description="活跃记忆数")
    net_growth: int = Field(default=0, description="净增记忆数")
    type_distribution: list[MemoryTypeItem] = Field(
        default_factory=list, description="记忆类型分布"
    )
