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
  backgroundColor: "#18181B",
  border: "1px solid #27272A",
  borderRadius: "12px",
  fontSize: "12px",
  color: "#E4E4E7",
  boxShadow: "0 4px 20px rgba(0,0,0,0.5)",
};

const tooltipItemStyle = { color: "#A1A1AA" };

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
      skeleton={
        <div
          style={{ height }}
          className="w-full rounded-xl bg-os-elevated shimmer-bg relative overflow-hidden border border-os-border/30"
        >
          {/* 微弱网格背景 — 模拟图表坐标系 */}
          <div
            className="absolute inset-0 opacity-40"
            style={{
              backgroundImage:
                "linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)",
              backgroundSize: "100% 25%, 16.66% 100%",
            }}
          />
        </div>
      }
    >
      <div style={{ height }} className="w-full overflow-x-auto">
        <ResponsiveContainer width="100%" height="100%">
          {type === "area" ? (
            <AreaChart data={formatted} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <defs>
                <linearGradient id={`grad-${color}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,0.03)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: "#52525B", fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#52525B", fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip
                contentStyle={tooltipStyle}
                itemStyle={tooltipItemStyle}
                formatter={(v: number) => (valueFormatter ? valueFormatter(v) : v)}
              />
              <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2} fillOpacity={0.1} fill={`url(#grad-${color})`} />
            </AreaChart>
          ) : (
            <LineChart data={formatted} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.03)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: "#52525B", fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#52525B", fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip
                contentStyle={tooltipStyle}
                itemStyle={tooltipItemStyle}
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
