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

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#f97316"];

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
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-muted-foreground">{title}</h3>
      <ResponsiveContainer width="100%" height={240}>
        {type === "area" ? (
          <AreaChart data={formattedData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Area
              type="monotone"
              dataKey={dataKey}
              stroke="#3b82f6"
              fill="#3b82f6"
              fillOpacity={0.15}
              strokeWidth={2}
            />
          </AreaChart>
        ) : (
          <BarChart data={formattedData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey={dataKey} fill="#3b82f6" radius={[4, 4, 0, 0]} />
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
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-muted-foreground">{title}</h3>
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
          <Tooltip />
          <Legend />
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
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-muted-foreground">{title}</h3>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="month" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} />
          <Tooltip formatter={(value: number) => `${value}%`} />
          <Bar dataKey="retention_rate" fill="#10b981" radius={[4, 4, 0, 0]} name="留存率 %" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
