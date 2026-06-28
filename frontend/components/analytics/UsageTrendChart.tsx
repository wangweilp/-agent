"use client";

import { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

const COLORS = ["#818CF8", "#34D399", "#FBBF24", "#F87171", "#A78BFA", "#22D3EE", "#FB923C"];

const tooltipStyle = {
  backgroundColor: "#18181B",
  border: "1px solid #27272A",
  borderRadius: "12px",
  fontSize: "12px",
  color: "#E4E4E7",
  boxShadow: "0 4px 20px rgba(0,0,0,0.5)",
};

const tooltipItemStyle = { color: "#A1A1AA" };

interface TrendItem {
  date: string;
  count: number;
  cost: number;
}

interface UsageTrendChartProps {
  data: TrendItem[];
  title: string;
  dataKey?: "count" | "cost";
  type?: "area" | "bar";
}

export function UsageTrendChart({ data, title, dataKey = "count", type = "area" }: UsageTrendChartProps) {
  const formattedData = useMemo(
    () => data.map((d) => ({ ...d, date: d.date.slice(5) })),
    [data]
  );

  return (
    <div className="rounded-xl border border-os-border bg-os-surface p-4 shadow-os-sm">
      <h3 className="mb-3 text-sm font-semibold text-os-text-high">{title}</h3>
      <ResponsiveContainer width="100%" height={240}>
        {type === "area" ? (
          <AreaChart data={formattedData}>
            <CartesianGrid stroke="rgba(255,255,255,0.03)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" tick={{ fill: "#52525B", fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#52525B", fontSize: 12 }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={tooltipStyle} itemStyle={tooltipItemStyle} />
            <Area
              type="monotone"
              dataKey={dataKey}
              stroke="#818CF8"
              fill="#818CF8"
              fillOpacity={0.1}
              strokeWidth={2}
            />
          </AreaChart>
        ) : (
          <BarChart data={formattedData}>
            <CartesianGrid stroke="rgba(255,255,255,0.03)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" tick={{ fill: "#52525B", fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#52525B", fontSize: 12 }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={tooltipStyle} itemStyle={tooltipItemStyle} />
            <Bar dataKey={dataKey} fill="#818CF8" radius={[4, 4, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

interface ImportChannelChartProps {
  channels: Record<string, number>;
  title: string;
}

export function ImportChannelChart({ channels, title }: ImportChannelChartProps) {
  const data = useMemo(
    () =>
      Object.entries(channels).map(([name, value]) => ({
        name,
        value,
      })),
    [channels]
  );

  return (
    <div className="rounded-xl border border-os-border bg-os-surface p-4 shadow-os-sm">
      <h3 className="mb-3 text-sm font-semibold text-os-text-high">{title}</h3>
      <ResponsiveContainer width="100%" height={240}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={90}
            paddingAngle={3}
            dataKey="value"
            label={({ name, value }) => `${name}: ${value}`}
          >
            {data.map((_, index) => (
              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={tooltipStyle} itemStyle={tooltipItemStyle} />
          <Legend wrapperStyle={{ fontSize: 11, color: "#A1A1AA" }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

interface RetentionChartProps {
  cohort: Array<{
    month: string;
    new_tenants: number;
    retained: number;
    retention_rate: number;
  }>;
  title: string;
}

export function RetentionChart({ cohort, title }: RetentionChartProps) {
  const data = useMemo(
    () =>
      cohort.map((c) => ({
        ...c,
        retention_rate: Math.round(c.retention_rate * 100),
      })),
    [cohort]
  );

  return (
    <div className="rounded-xl border border-os-border bg-os-surface p-4 shadow-os-sm">
      <h3 className="mb-3 text-sm font-semibold text-os-text-high">{title}</h3>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data}>
          <CartesianGrid stroke="rgba(255,255,255,0.03)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="month" tick={{ fill: "#52525B", fontSize: 12 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: "#52525B", fontSize: 12 }} axisLine={false} tickLine={false} domain={[0, 100]} />
          <Tooltip contentStyle={tooltipStyle} itemStyle={tooltipItemStyle} formatter={(value: number) => `${value}%`} />
          <Bar dataKey="retention_rate" fill="#34D399" radius={[4, 4, 0, 0]} name="留存率 %" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
