"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Brain,
  Zap,
  Clock,
  TrendingUp,
  Target,
  Activity,
  BarChart3,
  Cpu,
} from "lucide-react";
import { api } from "@/services/api";
import { PageTransition, StaggerItem } from "@/components/animations/page-transition";
import { CardSkeleton } from "@/components/animations/skeleton";
import { StatusCard } from "@/components/dashboard/status-card";
import { TraceTimeline } from "@/components/dashboard/trace-timeline";
import { AgentStatusPanel } from "@/components/dashboard/agent-status";
import { MemoryChart } from "@/components/dashboard/memory-chart";
import { RuntimeMonitor } from "@/components/dashboard/runtime-monitor";
import { cn, formatNumber } from "@/lib/utils";

export default function DashboardPage() {
  const { data: metrics, isLoading } = useQuery({
    queryKey: ["dashboard-metrics"],
    queryFn: () => api.dashboard.metrics(),
    refetchInterval: 10000,
  });

  const { data: traces } = useQuery({
    queryKey: ["dashboard-traces"],
    queryFn: () => api.dashboard.traces(),
    refetchInterval: 5000,
  });

  return (
    <PageTransition>
      <div className="p-6 space-y-6 max-w-[1440px] mx-auto">
        {/* Page header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight">仪表盘</h1>
            <p className="text-xs text-os-subtle mt-0.5">Agent 系统运行状态与实时指标</p>
          </div>
          <div className="flex items-center gap-2 text-2xs text-os-muted">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-status-breathe" />
            实时监控中
          </div>
        </div>

        {/* Metric Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StaggerItem delay={0}>
            <StatusCard
              icon={Brain}
              label="长期记忆"
              value={isLoading ? "..." : formatNumber(metrics?.memory_count || 0)}
              change={metrics?.memory_growth}
              changeLabel="较上周"
              accent="indigo"
            />
          </StaggerItem>
          <StaggerItem delay={0.05}>
            <StatusCard
              icon={Target}
              label="Recall 成功率"
              value={isLoading ? "..." : `${metrics?.recall_success_rate || 0}%`}
              accent="emerald"
            />
          </StaggerItem>
          <StaggerItem delay={0.1}>
            <StatusCard
              icon={Zap}
              label="今日 Tool Calls"
              value={isLoading ? "..." : formatNumber(metrics?.tool_calls_today || 0)}
              accent="amber"
            />
          </StaggerItem>
          <StaggerItem delay={0.15}>
            <StatusCard
              icon={Clock}
              label="平均延迟"
              value={isLoading ? "..." : `${metrics?.avg_latency_ms || 0}ms`}
              accent="violet"
            />
          </StaggerItem>
        </div>

        {/* Main content grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Agent Status */}
          <StaggerItem delay={0.2}>
            <div className="os-card p-4 h-full">
              <div className="flex items-center gap-2 mb-4">
                <Cpu size={14} className="text-os-accent" />
                <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">Agent 状态</h2>
              </div>
              <AgentStatusPanel />
            </div>
          </StaggerItem>

          {/* Memory Growth Chart */}
          <StaggerItem delay={0.25}>
            <div className="os-card p-4 h-full">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp size={14} className="text-os-accent" />
                <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">记忆增长</h2>
              </div>
              <MemoryChart />
            </div>
          </StaggerItem>

          {/* Runtime Monitor */}
          <StaggerItem delay={0.3}>
            <div className="os-card p-4 h-full">
              <div className="flex items-center gap-2 mb-4">
                <Activity size={14} className="text-os-accent" />
                <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">Runtime Monitor</h2>
              </div>
              <RuntimeMonitor />
            </div>
          </StaggerItem>
        </div>

        {/* Trace Timeline */}
        <StaggerItem delay={0.35}>
          <div className="os-card p-4">
            <div className="flex items-center gap-2 mb-4">
              <BarChart3 size={14} className="text-os-accent" />
              <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">实时 Trace</h2>
              <span className="text-2xs text-os-muted ml-auto">
                {traces?.length || 0} 条记录
              </span>
            </div>
            <TraceTimeline traces={traces || []} />
          </div>
        </StaggerItem>
      </div>
    </PageTransition>
  );
}
