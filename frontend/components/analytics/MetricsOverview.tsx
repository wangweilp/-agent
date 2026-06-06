"use client";

import { cn } from "@/lib/utils";
import { TrendingDown, TrendingUp, DollarSign, Users, Percent, Activity } from "lucide-react";

interface MetricCardProps {
  title: string;
  value: string;
  subtitle?: string;
  icon: React.ReactNode;
  trend?: "up" | "down";
  trendValue?: string;
}

function MetricCard({ title, value, subtitle, icon, trend, trendValue }: MetricCardProps) {
  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">{title}</span>
        <span className="text-muted-foreground/60">{icon}</span>
      </div>
      <div className="mt-2">
        <span className="text-2xl font-bold">{value}</span>
        {trend && (
          <span
            className={cn(
              "ml-2 text-sm font-medium",
              trend === "up" ? "text-green-500" : "text-red-500"
            )}
          >
            {trend === "up" ? <TrendingUp className="inline h-3 w-3" /> : <TrendingDown className="inline h-3 w-3" />}
            {" "}{trendValue}
          </span>
        )}
      </div>
      {subtitle && <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>}
    </div>
  );
}

interface MetricsOverviewProps {
  mrr: number;
  arr: number;
  conversionRate: number;
  retentionRate: number;
  activeTenants: number;
  totalTenants: number;
  payingTenants: number;
  churnRate: number;
}

export default function MetricsOverview({
  mrr,
  arr,
  conversionRate,
  retentionRate,
  activeTenants,
  totalTenants,
  payingTenants,
  churnRate,
}: MetricsOverviewProps) {
  const formatCny = (cents: number) =>
    `¥${(cents / 100).toLocaleString("zh-CN", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <MetricCard
        title="MRR"
        value={formatCny(mrr)}
        subtitle="月度经常性收入"
        icon={<DollarSign className="h-4 w-4" />}
        trend="up"
        trendValue="+12.5%"
      />
      <MetricCard
        title="ARR"
        value={formatCny(arr)}
        subtitle="年度经常性收入"
        icon={<DollarSign className="h-4 w-4" />}
      />
      <MetricCard
        title="付费转化率"
        value={`${(conversionRate * 100).toFixed(1)}%`}
        subtitle={`${payingTenants}/${totalTenants} 付费租户`}
        icon={<Percent className="h-4 w-4" />}
        trend={conversionRate > 0.2 ? "up" : "down"}
        trendValue={`${(conversionRate * 100).toFixed(1)}%`}
      />
      <MetricCard
        title="留存率"
        value={`${(retentionRate * 100).toFixed(1)}%`}
        subtitle={`流失率 ${(churnRate * 100).toFixed(1)}%`}
        icon={<Activity className="h-4 w-4" />}
        trend={retentionRate > 0.8 ? "up" : "down"}
        trendValue={`${(retentionRate * 100).toFixed(1)}%`}
      />
      <MetricCard
        title="活跃租户"
        value={String(activeTenants)}
        subtitle={`共 ${totalTenants} 个租户`}
        icon={<Users className="h-4 w-4" />}
      />
      <MetricCard
        title="付费租户"
        value={String(payingTenants)}
        subtitle={`${totalTenants > 0 ? ((payingTenants / totalTenants) * 100).toFixed(0) : 0}% 付费率`}
        icon={<Users className="h-4 w-4" />}
      />
      <MetricCard
        title="转化率"
        value={`${(conversionRate * 100).toFixed(1)}%`}
        icon={<TrendingUp className="h-4 w-4" />}
      />
      <MetricCard
        title="流失率"
        value={`${(churnRate * 100).toFixed(1)}%`}
        icon={<TrendingDown className="h-4 w-4" />}
      />
    </div>
  );
}
