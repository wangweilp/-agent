"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot, CheckCircle2, XCircle, Timer, Coins } from "lucide-react";
import { api } from "@/services/api";
import { SeriesChart } from "./series-chart";
import { SectionCard } from "./section-card";
import { KpiCard } from "./kpi-card";
import { formatPercent, formatLatency, formatCents } from "./format";
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

export function TabAgentPerformance() {
  const [days, setDays] = useState(7);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["dashboard-v2-agent-performance", days],
    queryFn: () => api.dashboardV2.agentPerformance(days),
    staleTime: STALE,
  });

  const latency = data?.latency;

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <RangeSwitcher value={days} onChange={setDays} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <KpiCard icon={CheckCircle2} label="成功率" value={formatPercent(data?.success_rate ?? 0)} accent="emerald" sub={`${days} 天`} />
        <KpiCard icon={XCircle} label="失败率" value={formatPercent(data?.failure_rate ?? 0)} accent="rose" sub={`${days} 天`} />
        <KpiCard icon={Timer} label="P50" value={formatLatency(latency?.p50_ms ?? 0)} accent="indigo" sub="中位数" />
        <KpiCard icon={Timer} label="P95" value={formatLatency(latency?.p95_ms ?? 0)} accent="amber" sub="尾部" />
        <KpiCard icon={Timer} label="P99" value={formatLatency(latency?.p99_ms ?? 0)} accent="rose" sub="长尾" />
        <KpiCard icon={Coins} label="Token 成本" value={formatCents(data?.token_cost_cents ?? 0)} accent="cyan" sub={`${days} 天`} />
      </div>

      <div className={layout.grid.twoLg}>
        <SectionCard title="调用量趋势" icon={<Bot size={14} />}>
          <SeriesChart data={data?.call_volume_series} isLoading={isLoading} isError={isError} onRetry={() => refetch()} color="#818CF8" emptyText="无调用量数据" />
        </SectionCard>
        <SectionCard title="Token 消耗趋势" icon={<Coins size={14} />}>
          <SeriesChart data={data?.token_usage_series} isLoading={isLoading} isError={isError} onRetry={() => refetch()} color="#22D3EE" emptyText="无 Token 数据" />
        </SectionCard>
      </div>
    </div>
  );
}
