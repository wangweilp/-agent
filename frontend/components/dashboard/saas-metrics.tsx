"use client";

import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  DollarSign,
  Users,
  TrendingUp,
  TrendingDown,
  Activity,
  CreditCard,
  UserCheck,
  UserX,
} from "lucide-react";
import { api } from "@/services/api";
import type { PlatformStats } from "@/types";
import { cn, formatNumber } from "@/lib/utils";
import { layout } from "@/styles/layout";

function formatCurrency(cents: number): string {
  return `¥${(cents / 100).toLocaleString("zh-CN", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

interface MetricCardProps {
  icon: React.ElementType;
  label: string;
  value: string | number;
  sub?: string;
  accent?: "emerald" | "blue" | "purple" | "amber" | "red" | "default";
  isLoading?: boolean;
}

function MetricCard({ icon: Icon, label, value, sub, accent = "default", isLoading }: MetricCardProps) {
  const accentColors: Record<string, string> = {
    emerald: "text-emerald-400 bg-emerald-400/10",
    blue: "text-blue-400 bg-blue-400/10",
    purple: "text-purple-400 bg-purple-400/10",
    amber: "text-amber-400 bg-amber-400/10",
    red: "text-red-400 bg-red-400/10",
    default: "text-os-accent bg-os-accent/10",
  };
  const color = accentColors[accent] || accentColors.default;

  return (
    <div className="os-card p-4">
      <div className="flex items-center gap-2 mb-2">
        <div className={cn("w-7 h-7 rounded-md flex items-center justify-center", color.split(" ")[1], color.split(" ")[0])}>
          <Icon size={14} />
        </div>
        <span className="text-xs text-os-subtle">{label}</span>
      </div>
      {isLoading ? (
        <div className="h-7 w-20 bg-os-surface animate-pulse rounded" />
      ) : (
        <>
          <p className="text-xl font-semibold text-os-text-high">{value}</p>
          {sub && <p className="text-2xs text-os-muted mt-0.5">{sub}</p>}
        </>
      )}
    </div>
  );
}

export function SaaSMetrics() {
  const { data: stats, isLoading } = useQuery<PlatformStats>({
    queryKey: ["saas-platform-stats"],
    queryFn: () => api.usage.getPlatformStats(),
    refetchInterval: 30000,
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="flex items-center gap-2 mb-4">
        <DollarSign size={14} className="text-os-accent" />
        <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">
          SaaS 指标
        </h2>
      </div>

      <div className={layout.grid.fiveLg}>
        {/* MRR */}
        <MetricCard
          icon={DollarSign}
          label="MRR"
          value={stats ? formatCurrency(stats.mrr_cents) : "..."}
          accent="emerald"
          isLoading={isLoading}
        />

        {/* ARR */}
        <MetricCard
          icon={TrendingUp}
          label="ARR"
          value={stats ? formatCurrency(stats.arr_cents) : "..."}
          accent="blue"
          isLoading={isLoading}
        />

        {/* Total Tenants */}
        <MetricCard
          icon={Users}
          label="总租户"
          value={stats ? formatNumber(stats.total_tenants) : "..."}
          sub={stats ? `活跃 ${stats.active_tenants} · 付费 ${stats.paying_tenants}` : undefined}
          accent="purple"
          isLoading={isLoading}
        />

        {/* Conversion */}
        <MetricCard
          icon={UserCheck}
          label="转化率"
          value={stats ? formatPercent(stats.conversion_rate) : "..."}
          sub={stats ? `试用 ${stats.trial_tenants} 个` : undefined}
          accent="amber"
          isLoading={isLoading}
        />

        {/* Churn */}
        <MetricCard
          icon={UserX}
          label="月流失率"
          value={stats ? formatPercent(stats.churn_rate) : "..."}
          sub={stats ? `留存 ${formatPercent(stats.retention_rate)}` : undefined}
          accent="red"
          isLoading={isLoading}
        />
      </div>

      {/* Secondary Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
        <MetricCard
          icon={CreditCard}
          label="ARPU"
          value={stats ? formatCurrency(stats.avg_revenue_per_user) : "..."}
          accent="default"
          isLoading={isLoading}
        />
        <MetricCard
          icon={Activity}
          label="总收入"
          value={stats ? formatCurrency(stats.total_revenue_cents) : "..."}
          accent="default"
          isLoading={isLoading}
        />
        <MetricCard
          icon={TrendingUp}
          label="月留存率"
          value={stats ? formatPercent(stats.retention_rate) : "..."}
          accent="default"
          isLoading={isLoading}
        />
        <MetricCard
          icon={TrendingDown}
          label="付费用户"
          value={stats ? stats.paying_tenants : "..."}
          accent="default"
          isLoading={isLoading}
        />
      </div>
    </motion.div>
  );
}
