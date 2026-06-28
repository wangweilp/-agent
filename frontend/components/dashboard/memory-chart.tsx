"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { Skeleton } from "@/components/animations/skeleton";
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
  if (isLoading) return <Skeleton className="h-48 w-full" />;
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-2xs text-os-muted">
        暂无增长数据 — 开始记录记忆后将显示趋势
      </div>
    );
  }

  return (
    <div className="h-48 w-full">
      <ResponsiveChartContainer height="100%">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="episodicGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#818CF8" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#818CF8" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="semanticGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#34D399" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#34D399" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="reflectGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#FBBF24" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#FBBF24" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(255,255,255,0.03)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: "#52525B", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#52525B", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            allowDecimals={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#18181B",
              border: "1px solid #27272A",
              borderRadius: "12px",
              fontSize: "12px",
              color: "#E4E4E7",
              boxShadow: "0 4px 20px rgba(0,0,0,0.5)",
            }}
            itemStyle={{ color: "#A1A1AA" }}
          />
          <Bar dataKey="episodic" stackId="a" fill="#818CF8" radius={[0, 0, 0, 0]} />
          <Bar dataKey="semantic" stackId="a" fill="#34D399" radius={[0, 0, 0, 0]} />
          <Bar dataKey="reflect" stackId="a" fill="#FBBF24" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      </ResponsiveChartContainer>
    </div>
  );
}
