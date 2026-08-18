"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BarChart3 } from "lucide-react";
import { Skeleton } from "@/components/animations/skeleton";
import { EmptyState } from "@/components/ui/os";
import { ResponsiveChartContainer } from "@/components/ui/ResponsiveChartContainer";

interface ChartDataPoint {
  label: string;
  count: number;
  episodic: number;
  semantic: number;
  reflect: number;
}

interface MemoryChartProps {
  data?: ChartDataPoint[];
  isLoading: boolean;
}

export function MemoryChart({ data, isLoading }: MemoryChartProps) {
  if (isLoading) return <Skeleton className="h-64 w-full rounded-2xl" />;

  if (!data || data.length === 0) {
    return (
      <EmptyState
        icon={BarChart3}
        title="暂无增长数据"
        description="开始记录记忆后，这里会显示情景、语义与反思记忆的 30 天趋势。"
        className="min-h-[256px]"
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="h-64 w-full">
        <ResponsiveChartContainer height="100%" className="border-0 bg-transparent shadow-none">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid stroke="#E6EAF2" strokeDasharray="3 4" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fill: "#64748B", fontSize: 12 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "#64748B", fontSize: 12 }}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
              />
              <Tooltip
                cursor={{ fill: "rgba(99,102,241,0.06)" }}
                contentStyle={{
                  backgroundColor: "#FFFFFF",
                  border: "1px solid #E2E8F0",
                  borderRadius: "14px",
                  fontSize: "12px",
                  color: "#334155",
                  boxShadow: "0 12px 30px rgba(15, 23, 42, 0.10)",
                }}
                labelStyle={{ color: "#0F172A", fontWeight: 600 }}
              />
              <Bar dataKey="episodic" stackId="a" fill="#7C8CF8" radius={[0, 0, 0, 0]} />
              <Bar dataKey="semantic" stackId="a" fill="#3DBE8B" radius={[0, 0, 0, 0]} />
              <Bar dataKey="reflect" stackId="a" fill="#D99A1E" radius={[5, 5, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ResponsiveChartContainer>
      </div>

      <div className="flex flex-wrap items-center gap-4 text-xs text-os-subtle">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm bg-[#7C8CF8]" />
          情景记忆
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm bg-[#3DBE8B]" />
          语义记忆
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm bg-[#D99A1E]" />
          反思记忆
        </span>
      </div>
    </div>
  );
}
