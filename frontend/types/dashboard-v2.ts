// Dashboard V2 类型 — 与后端 src/api/dashboard_v2_schemas.py 对齐。

export interface MetricPoint {
  date: string;
  value: number;
}

export interface FunnelStage {
  stage: string;
  count: number;
}

export interface CohortRow {
  cohort_date: string;
  cohort_size: number;
  d1: number;
  d7: number;
}

export interface LatencyPercentiles {
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
}

export interface MemoryTypeItem {
  memory_type: string;
  count: number;
}

// ── Overview ──
export interface OverviewResponse {
  mrr_cents: number;
  arr_cents: number;
  arpu_cents: number;
  gross_margin_pct: number;
  dau: number;
  wau: number;
  mau: number;
  retention_d1: number;
  retention_d7: number;
  agent_success_rate: number;
  p95_latency_ms: number;
  token_cost_today_cents: number;
  total_memories: number;
  memory_hit_rate: number;
  net_growth_today: number;
}

// ── Growth ──
export interface GrowthResponse {
  dau_series: MetricPoint[];
  wau_series: MetricPoint[];
  mau_series: MetricPoint[];
  retention_cohort: CohortRow[];
  funnel: FunnelStage[];
  activation_rate: number;
}

// ── Agent Performance ──
export interface AgentPerformanceResponse {
  call_volume_series: MetricPoint[];
  success_rate: number;
  failure_rate: number;
  latency: LatencyPercentiles;
  token_usage_series: MetricPoint[];
  token_cost_cents: number;
}

// ── Memory Health ──
export interface MemoryHealthResponse {
  growth_series: MetricPoint[];
  hit_rate: number;
  total_memories: number;
  active_memories: number;
  net_growth: number;
  type_distribution: MemoryTypeItem[];
}
