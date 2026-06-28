"use client";

import { useQuery } from "@tanstack/react-query";
import {
  DollarSign,
  TrendingUp,
  Users,
  Repeat,
  Bot,
  Timer,
  Coins,
  Brain,
  Target,
  GitBranch,
  Activity,
} from "lucide-react";
import { api } from "@/services/api";
import { KpiCard } from "./kpi-card";
import { QueryState } from "./query-state";
import {
  formatCents,
  formatPercent,
  formatLatency,
  formatDelta,
  formatCompact,
} from "./format";
import { layout } from "@/styles/layout";

const STALE = 60 * 1000; // 60s

function KpiGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h3 className="text-2xs font-medium text-os-muted uppercase tracking-wider px-1">{title}</h3>
      <div className={layout.grid.fourLg}>{children}</div>
    </div>
  );
}

export function TabOverview() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["dashboard-v2-overview"],
    queryFn: () => api.dashboardV2.overview(),
    staleTime: STALE,
  });

  return (
    <QueryState
      isLoading={isLoading}
      isError={isError}
      onRetry={() => refetch()}
      errorText="概览数据加载失败"
      skeleton={
        <div className={layout.grid.fourLg}>
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="os-card p-4 space-y-3">
              <div className="h-3 w-16 rounded bg-os-elevated shimmer-bg" />
              <div className="h-6 w-24 rounded bg-os-elevated shimmer-bg" />
            </div>
          ))}
        </div>
      }
    >
      <div className="space-y-5">
        <KpiGroup title="商业指标">
          <KpiCard icon={DollarSign} label="MRR" value={formatCents(data?.mrr_cents ?? 0)} accent="emerald" sub="月度经常性收入" />
          <KpiCard icon={TrendingUp} label="ARR" value={formatCents(data?.arr_cents ?? 0)} accent="emerald" sub="年化收入" />
          <KpiCard icon={DollarSign} label="ARPU" value={formatCents(data?.arpu_cents ?? 0)} accent="cyan" sub="单用户平均收入" />
          <KpiCard icon={Activity} label="Gross Margin" value={formatPercent(data?.gross_margin_pct ?? 0)} accent="emerald" sub="毛利率" />
        </KpiGroup>

        <KpiGroup title="用户增长">
          <KpiCard icon={Users} label="DAU" value={formatCompact(data?.dau ?? 0)} accent="indigo" sub="日活跃用户" />
          <KpiCard icon={Users} label="WAU" value={formatCompact(data?.wau ?? 0)} accent="indigo" sub="周活跃用户" />
          <KpiCard icon={Users} label="MAU" value={formatCompact(data?.mau ?? 0)} accent="indigo" sub="月活跃用户" />
        </KpiGroup>

        <KpiGroup title="留存">
          <KpiCard icon={Repeat} label="D1 留存" value={formatPercent(data?.retention_d1 ?? 0)} accent="violet" sub="次日留存率" />
          <KpiCard icon={Repeat} label="D7 留存" value={formatPercent(data?.retention_d7 ?? 0)} accent="violet" sub="7日留存率" />
        </KpiGroup>

        <KpiGroup title="智能体性能">
          <KpiCard icon={Bot} label="智能体成功率" value={formatPercent(data?.agent_success_rate ?? 0)} accent="emerald" sub="今日" />
          <KpiCard icon={Timer} label="P95 延迟" value={formatLatency(data?.p95_latency_ms ?? 0)} accent="amber" sub="今日" />
          <KpiCard icon={Coins} label="Token 成本" value={formatCents(data?.token_cost_today_cents ?? 0)} accent="rose" sub="今日" />
        </KpiGroup>

        <KpiGroup title="记忆健康">
          <KpiCard icon={Brain} label="总记忆" value={formatCompact(data?.total_memories ?? 0)} accent="indigo" sub="全量" />
          <KpiCard icon={Target} label="命中率" value={formatPercent(data?.memory_hit_rate ?? 0)} accent="emerald" sub="记忆 Hit Rate" />
          <KpiCard icon={GitBranch} label="净增长" value={formatDelta(data?.net_growth_today ?? 0)} accent="cyan" sub="今日" />
        </KpiGroup>
      </div>
    </QueryState>
  );
}
