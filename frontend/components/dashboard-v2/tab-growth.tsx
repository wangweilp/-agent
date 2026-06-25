"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { Users, Filter, Layers } from "lucide-react";
import { api } from "@/services/api";
import { SeriesChart } from "./series-chart";
import { SectionCard } from "./section-card";
import { KpiCard } from "./kpi-card";
import { QueryState, EmptyState } from "./query-state";
import { formatPercent } from "./format";
import { cn } from "@/lib/utils";

const STALE = 5 * 60 * 1000; // 5min
const RANGES = [
  { label: "7 天", days: 7 },
  { label: "30 天", days: 30 },
  { label: "90 天", days: 90 },
];

const FUNNEL_COLORS = ["#818CF8", "#34D399", "#FBBF24", "#F87171", "#22D3EE", "#A78BFA"];

const tooltipStyle = {
  background: "#18181B",
  border: "1px solid #27272A",
  borderRadius: "8px",
  fontSize: "12px",
  color: "#E4E4E7",
};

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

function CohortTable({ rows }: { rows: { cohort_date: string; cohort_size: number; d1: number; d7: number }[] }) {
  if (!rows || rows.length === 0) {
    return <EmptyState message="暂无留存队列数据" />;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-2xs">
        <thead>
          <tr className="text-os-muted border-b border-os-border">
            <th className="text-left font-medium py-2 px-2">队列日期</th>
            <th className="text-right font-medium py-2 px-2">规模</th>
            <th className="text-right font-medium py-2 px-2">D1</th>
            <th className="text-right font-medium py-2 px-2">D7</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.cohort_date} className="border-b border-os-border/50 hover:bg-os-elevated/50">
              <td className="py-1.5 px-2 text-os-text font-mono">{r.cohort_date || "—"}</td>
              <td className="py-1.5 px-2 text-right text-os-text font-mono">{r.cohort_size}</td>
              <td className={cn("py-1.5 px-2 text-right font-mono", r.d1 >= 40 ? "text-emerald-400" : r.d1 >= 20 ? "text-amber-400" : "text-os-subtle")}>
                {formatPercent(r.d1)}
              </td>
              <td className={cn("py-1.5 px-2 text-right font-mono", r.d7 >= 30 ? "text-emerald-400" : r.d7 >= 15 ? "text-amber-400" : "text-os-subtle")}>
                {formatPercent(r.d7)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FunnelChart({ stages }: { stages: { stage: string; count: number }[] }) {
  if (!stages || stages.length === 0) {
    return <EmptyState message="暂无漏斗数据" />;
  }
  const data = stages.map((s) => ({ name: s.stage, count: s.count }));
  return (
    <div style={{ height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272A" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 10, fill: "#52525B" }} axisLine={false} tickLine={false} allowDecimals={false} />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: "#A1A1AA" }} axisLine={false} tickLine={false} width={72} />
          <Tooltip contentStyle={tooltipStyle} />
          <Bar dataKey="count" radius={[0, 4, 4, 0]}>
            {data.map((_, i) => (
              <Cell key={i} fill={FUNNEL_COLORS[i % FUNNEL_COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TabGrowth() {
  const [days, setDays] = useState(30);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["dashboard-v2-growth", days],
    queryFn: () => api.dashboardV2.growth(days),
    staleTime: STALE,
  });

  const rangeSwitcher = <RangeSwitcher value={days} onChange={setDays} />;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard icon={Users} label="激活率" value={formatPercent(data?.activation_rate ?? 0)} accent="emerald" sub={`${days} 天`} />
        <KpiCard icon={Users} label="DAU 峰值" value={String(Math.max(0, ...(data?.dau_series ?? []).map((p) => p.value))) || "0"} accent="indigo" sub={`${days} 天`} />
        <KpiCard icon={Users} label="MAU 末值" value={String(data?.mau_series?.at(-1)?.value ?? 0)} accent="violet" sub="最新" />
        <KpiCard icon={Filter} label="漏斗阶段" value={String(data?.funnel?.length ?? 0)} accent="cyan" sub="转化漏斗" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <SectionCard title="DAU 趋势" icon={<Users size={14} />} action={rangeSwitcher}>
          <SeriesChart data={data?.dau_series} isLoading={isLoading} isError={isError} onRetry={() => refetch()} color="#818CF8" emptyText={`${days} 天内无 DAU 数据`} />
        </SectionCard>
        <SectionCard title="WAU 趋势" icon={<Users size={14} />}>
          <SeriesChart data={data?.wau_series} isLoading={isLoading} isError={isError} onRetry={() => refetch()} color="#34D399" emptyText="无 WAU 数据" />
        </SectionCard>
        <SectionCard title="MAU 趋势" icon={<Users size={14} />}>
          <SeriesChart data={data?.mau_series} isLoading={isLoading} isError={isError} onRetry={() => refetch()} color="#A78BFA" emptyText="无 MAU 数据" />
        </SectionCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SectionCard title="留存队列 (Cohort)" icon={<Layers size={14} />}>
          <QueryState isLoading={isLoading} isError={isError} onRetry={() => refetch()} skeleton={<div className="h-48 rounded bg-os-elevated shimmer-bg" />}>
            <CohortTable rows={data?.retention_cohort ?? []} />
          </QueryState>
        </SectionCard>
        <SectionCard title="激活漏斗 (Funnel)" icon={<Filter size={14} />}>
          <QueryState isLoading={isLoading} isError={isError} onRetry={() => refetch()} skeleton={<div className="h-48 rounded bg-os-elevated shimmer-bg" />}>
            <FunnelChart stages={data?.funnel ?? []} />
          </QueryState>
        </SectionCard>
      </div>
    </div>
  );
}
