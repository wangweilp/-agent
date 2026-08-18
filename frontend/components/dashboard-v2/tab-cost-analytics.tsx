"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Coins, CalendarDays, Flame, TrendingUp, PiggyBank, LineChart } from "lucide-react";
import { api } from "@/services/api";
import { SeriesChart } from "./series-chart";
import { SectionCard } from "./section-card";
import { KpiCard } from "./kpi-card";
import { formatCents, estimateMonthlyCostCents } from "./format";
import { cn } from "@/lib/utils";
import { layout } from "@/styles/layout";

const STALE = 5 * 60 * 1000;
const RANGES = [
  { label: "7 天", days: 7 },
  { label: "30 天", days: 30 },
  { label: "90 天", days: 90 },
];

function RangeSwitcher({ value, onChange }: { value: number; onChange: (d: number) => void }) {
  return (
    <div className="flex items-center gap-1 rounded-md border border-os-border p-0.5">
      {RANGES.map((r) => (
        <button
          key={r.days}
          onClick={() => onChange(r.days)}
          className={cn(
            "px-2 py-0.5 text-2xs rounded transition-colors",
            value === r.days ? "bg-os-accent/15 text-os-accent" : "text-os-subtle hover:text-os-text",
          )}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}

function PlaceholderPanel({ title, icon, desc }: { title: string; icon: React.ReactNode; desc: string }) {
  return (
    <div className="os-card p-4 h-full flex flex-col">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-os-accent">{icon}</span>
        <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">{title}</h2>
        <span className="ml-auto os-badge bg-os-accent/10 text-os-accent">即将上线</span>
      </div>
      <div className="flex-1 flex items-center justify-center text-center px-4">
        <p className="text-2xs text-os-subtle leading-relaxed">{desc}</p>
      </div>
    </div>
  );
}

export function TabCostAnalytics() {
  const [days, setDays] = useState(30);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["dashboard-v2-cost", days],
    queryFn: () => api.dashboardV2.agentPerformance(days),
    staleTime: STALE,
  });

  const totalCost = data?.token_cost_cents ?? 0;
  const dailyAvg = days > 0 ? totalCost / days : 0;
  const monthlyEst = estimateMonthlyCostCents(dailyAvg);

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <RangeSwitcher value={days} onChange={setDays} />
      </div>

      <div className={layout.grid.fourMd}>
        <KpiCard icon={Coins} label="区间总成本" value={formatCents(totalCost)} accent="rose" sub={`${days} 天`} />
        <KpiCard icon={CalendarDays} label="日均成本" value={formatCents(dailyAvg)} accent="amber" sub="每日平均" />
        <KpiCard icon={Flame} label="消耗速率" value={formatCents(dailyAvg)} accent="rose" sub="每日消耗" />
        <KpiCard icon={TrendingUp} label="月度预估" value={formatCents(monthlyEst)} accent="cyan" sub="30 天外推" />
      </div>

      <SectionCard title="Token 消耗趋势" icon={<LineChart size={14} />}>
        <SeriesChart
          data={data?.token_usage_series}
          isLoading={isLoading}
          isError={isError}
          onRetry={() => refetch()}
          color="#22D3EE"
          height={260}
          emptyText="无 Token 消耗数据"
        />
      </SectionCard>

      <div className={layout.grid.twoLg}>
        <PlaceholderPanel
          title="成本预测"
          icon={<TrendingUp size={14} />}
          desc="基于历史 Token 消耗序列的成本预测（后端预测接口尚未实现，组件结构已预留）。"
        />
        <PlaceholderPanel
          title="预算"
          icon={<PiggyBank size={14} />}
          desc="设置月度预算阈值并在接近上限时触发告警（后端预算接口尚未实现，组件结构已预留）。"
        />
      </div>
    </div>
  );
}
