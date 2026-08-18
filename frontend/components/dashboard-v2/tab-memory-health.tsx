"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { Brain, Target, GitBranch, Layers, Activity } from "lucide-react";
import { api } from "@/services/api";
import { SeriesChart } from "./series-chart";
import { SectionCard } from "./section-card";
import { KpiCard } from "./kpi-card";
import { QueryState, EmptyState } from "./query-state";
import { formatPercent, formatDelta, formatCompact } from "./format";
import { cn } from "@/lib/utils";
import { layout } from "@/styles/layout";

const STALE = 5 * 60 * 1000;
const RANGES = [
  { label: "7 天", days: 7 },
  { label: "30 天", days: 30 },
  { label: "90 天", days: 90 },
];
const PIE_COLORS = ["#818CF8", "#34D399", "#FBBF24", "#F87171", "#22D3EE", "#A78BFA"];

const tooltipStyle = {
  backgroundColor: "#18181B",
  border: "1px solid #27272A",
  borderRadius: "12px",
  fontSize: "12px",
  color: "#E4E4E7",
  boxShadow: "0 4px 20px rgba(0,0,0,0.5)",
};

const tooltipItemStyle = { color: "#A1A1AA" };

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

function DistributionPie({ items }: { items: { memory_type: string; count: number }[] }) {
  if (!items || items.length === 0) {
    return <EmptyState message="暂无类型分布数据" />;
  }
  const data = items.map((i) => ({ name: i.memory_type || "未知", value: i.count }));
  return (
    <div style={{ height: 240 }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} cx="50%" cy="50%" innerRadius={50} outerRadius={90} paddingAngle={3} dataKey="value" label={({ name, value }: { name: string; value: number }) => `${name}: ${value}`}>
            {data.map((_, i) => (
              <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={tooltipStyle} itemStyle={tooltipItemStyle} />
          <Legend wrapperStyle={{ fontSize: 11, color: "#52525B" }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TabMemoryHealth() {
  const [days, setDays] = useState(30);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["dashboard-v2-memory-health", days],
    queryFn: () => api.dashboardV2.memoryHealth(days),
    staleTime: STALE,
  });

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <RangeSwitcher value={days} onChange={setDays} />
      </div>

      <div className={layout.grid.fourMd}>
        <KpiCard icon={Brain} label="总记忆" value={formatCompact(data?.total_memories ?? 0)} accent="indigo" sub="全量" />
        <KpiCard icon={Activity} label="活跃记忆" value={formatCompact(data?.active_memories ?? 0)} accent="emerald" sub="活跃" />
        <KpiCard icon={Target} label="命中率" value={formatPercent(data?.hit_rate ?? 0)} accent="violet" sub="检索命中率" />
        <KpiCard icon={GitBranch} label="净增长" value={formatDelta(data?.net_growth ?? 0)} accent="cyan" sub={`${days} 天`} />
      </div>

      <div className={layout.grid.threeLg}>
        <div className="lg:col-span-2">
          <SectionCard title="记忆增长趋势" icon={<Layers size={14} />}>
            <SeriesChart data={data?.growth_series} isLoading={isLoading} isError={isError} onRetry={() => refetch()} color="#818CF8" height={260} emptyText="无增长趋势数据" />
          </SectionCard>
        </div>
        <SectionCard title="类型分布" icon={<Brain size={14} />}>
          <QueryState isLoading={isLoading} isError={isError} onRetry={() => refetch()} skeleton={<div className="h-60 rounded bg-os-elevated shimmer-bg" />}>
            <DistributionPie items={data?.type_distribution ?? []} />
          </QueryState>
        </SectionCard>
      </div>
    </div>
  );
}
