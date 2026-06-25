"use client";

import { useMemo } from "react";
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { MetricPoint } from "@/types/dashboard-v2";
import { QueryState } from "./query-state";

interface SeriesChartProps {
  data: MetricPoint[] | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry?: () => void;
  type?: "area" | "line";
  color?: string;
  height?: number;
  emptyText?: string;
  valueFormatter?: (v: number) => string;
}

const DEFAULT_COLOR = "#818CF8";

const tooltipStyle = {
  background: "#18181B",
  border: "1px solid #27272A",
  borderRadius: "8px",
  fontSize: "12px",
  color: "#E4E4E7",
};

// MetricPoint[] 时间序列图 — 复用 Recharts，统一 loading/empty/error。
export function SeriesChart({
  data,
  isLoading,
  isError,
  onRetry,
  type = "area",
  color = DEFAULT_COLOR,
  height = 220,
  emptyText = "暂无趋势数据",
  valueFormatter,
}: SeriesChartProps) {
  const formatted = useMemo(
    () => (data ?? []).map((p) => ({ ...p, label: p.date.slice(5) })),
    [data],
  );

  const isEmpty = !isLoading && !isError && formatted.length === 0;

  return (
    <QueryState
      isLoading={isLoading}
      isError={isError}
      isEmpty={isEmpty}
      onRetry={onRetry}
      emptyText={emptyText}
      skeleton={<div style={{ height }} className="w-full rounded-md bg-os-elevated shimmer-bg" />}
    >
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          {type === "area" ? (
            <AreaChart data={formatted} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <defs>
                <linearGradient id={`grad-${color}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#52525B" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#52525B" }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip
                contentStyle={tooltipStyle}
                formatter={(v: number) => (valueFormatter ? valueFormatter(v) : v)}
              />
              <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2} fill={`url(#grad-${color})`} />
            </AreaChart>
          ) : (
            <LineChart data={formatted} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272A" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#52525B" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#52525B" }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip
                contentStyle={tooltipStyle}
                formatter={(v: number) => (valueFormatter ? valueFormatter(v) : v)}
              />
              <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2} dot={false} />
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
    </QueryState>
  );
}
