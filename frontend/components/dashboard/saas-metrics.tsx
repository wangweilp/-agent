"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Activity,
  CreditCard,
  DollarSign,
  TrendingDown,
  TrendingUp,
  UserCheck,
  Users,
  UserX,
} from "lucide-react";
import { api } from "@/services/api";
import { MetricCard, OsBadge, SectionHeader } from "@/components/ui/os";
import type { PlatformStats } from "@/types";
import { formatNumber } from "@/lib/utils";
import { layout } from "@/styles/layout";

function formatCurrency(cents: number): string {
  return `¥${(cents / 100).toLocaleString("zh-CN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`;
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function SaaSMetrics() {
  const { data: stats, isLoading } = useQuery<PlatformStats>({
    queryKey: ["saas-platform-stats"],
    queryFn: () => api.usage.getPlatformStats(),
    refetchInterval: 30000,
  });

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22 }}
      className="space-y-3"
    >
      <SectionHeader
        icon={DollarSign}
        title="SaaS 指标"
        subtitle="营收、租户与留存指标使用与记忆指标一致的密度和状态色。"
        actions={<OsBadge variant="muted">30s refresh</OsBadge>}
      />

      <div className={layout.grid.fiveLg}>
        <MetricCard
          icon={DollarSign}
          label="MRR"
          value={stats && !isLoading ? formatCurrency(stats.mrr_cents) : "..."}
          detail="月经常性收入"
          accent="success"
        />
        <MetricCard
          icon={TrendingUp}
          label="ARR"
          value={stats && !isLoading ? formatCurrency(stats.arr_cents) : "..."}
          detail="年化收入"
          accent="info"
        />
        <MetricCard
          icon={Users}
          label="总租户"
          value={stats && !isLoading ? formatNumber(stats.total_tenants) : "..."}
          detail={stats ? `活跃 ${stats.active_tenants} / 付费 ${stats.paying_tenants}` : "等待平台统计"}
          accent="primary"
        />
        <MetricCard
          icon={UserCheck}
          label="转化率"
          value={stats && !isLoading ? formatPercent(stats.conversion_rate) : "..."}
          detail={stats ? `试用 ${stats.trial_tenants} 个` : "等待试用数据"}
          accent="warning"
        />
        <MetricCard
          icon={UserX}
          label="月流失率"
          value={stats && !isLoading ? formatPercent(stats.churn_rate) : "..."}
          detail={stats ? `留存 ${formatPercent(stats.retention_rate)}` : "等待留存数据"}
          accent={stats && stats.churn_rate > 0.05 ? "danger" : "muted"}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          icon={CreditCard}
          label="ARPU"
          value={stats && !isLoading ? formatCurrency(stats.avg_revenue_per_user) : "..."}
          detail="平均客户收入"
          accent="muted"
        />
        <MetricCard
          icon={Activity}
          label="总收入"
          value={stats && !isLoading ? formatCurrency(stats.total_revenue_cents) : "..."}
          detail="累计确认收入"
          accent="muted"
        />
        <MetricCard
          icon={TrendingUp}
          label="月留存率"
          value={stats && !isLoading ? formatPercent(stats.retention_rate) : "..."}
          detail="活跃租户留存"
          accent="success"
        />
        <MetricCard
          icon={TrendingDown}
          label="付费用户"
          value={stats && !isLoading ? stats.paying_tenants : "..."}
          detail="当前付费租户"
          accent="muted"
        />
      </div>
    </motion.section>
  );
}
