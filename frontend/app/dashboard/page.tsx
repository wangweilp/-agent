"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Brain,
  Layers,
  Archive,
  GitMerge,
  Lightbulb,
  TrendingUp,
  Tag,
  Cpu,
  Activity,
  BarChart3,
} from "lucide-react";
import { api } from "@/services/api";
import { PageTransition, StaggerItem } from "@/components/animations/page-transition";
import { CardSkeleton } from "@/components/animations/skeleton";
import { StatusCard } from "@/components/dashboard/status-card";
import { TraceTimeline } from "@/components/dashboard/trace-timeline";
import { AgentStatusPanel } from "@/components/dashboard/agent-status";
import { MemoryChart } from "@/components/dashboard/memory-chart";
import { RuntimeMonitor } from "@/components/dashboard/runtime-monitor";
import { TopicList } from "@/components/dashboard/topic-list";
import { RecentMemories } from "@/components/dashboard/recent-memories";
import { RecentReflections } from "@/components/dashboard/recent-reflections";
import { EntityList } from "@/components/dashboard/entity-list";
import { cn, formatNumber } from "@/lib/utils";

// ── 辅助函数 ──

interface ChartDataPoint {
  label: string;
  count: number;
  episodic: number;
  semantic: number;
  reflect: number;
}

/**
 * 将记忆列表按日期聚合成图表数据。
 * days=7  → 最近 7 天，每天一条柱
 * days=30 → 最近 30 天，每 3 天聚合一条
 * days=90 → 最近 90 天，每 7 天聚合一条
 */
function aggregateByDay(
  memories: { timestamp: string; memory_type: string }[],
  days: number,
): ChartDataPoint[] {
  const now = new Date();
  const buckets: Map<string, { episodic: number; semantic: number; reflect: number }> = new Map();

  let bucketSize = 1;
  if (days >= 60) bucketSize = 7;
  else if (days >= 14) bucketSize = 3;

  // 生成空桶
  for (let i = days - 1; i >= 0; i -= bucketSize) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const key = bucketSize >= 7
      ? d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" })
      : d.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
    buckets.set(key, { episodic: 0, semantic: 0, reflect: 0 });
  }

  // 填充数据
  const cutoff = new Date(now);
  cutoff.setDate(cutoff.getDate() - days);
  for (const mem of memories) {
    const t = new Date(mem.timestamp);
    if (t < cutoff) continue;
    const d = new Date(t);
    if (bucketSize >= 7) {
      d.setDate(d.getDate() - d.getDay()); // 对齐到周
    } else if (bucketSize >= 3) {
      d.setDate(d.getDate() - (d.getDate() % bucketSize));
    }
    const key = bucketSize >= 7
      ? d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" })
      : d.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
    const bucket = buckets.get(key);
    if (bucket) {
      if (mem.memory_type === "semantic") bucket.semantic++;
      else if (mem.memory_type === "reflect" || mem.memory_type === "procedural") bucket.reflect++;
      else bucket.episodic++;
    }
  }

  return Array.from(buckets.entries()).map(([label, vals]) => ({
    label,
    count: vals.episodic + vals.semantic + vals.reflect,
    ...vals,
  }));
}

// ── 页面组件 ──

export default function DashboardPage() {
  // 数据查询
  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: () => api.dashboard.summary(),
    refetchInterval: 15000,
  });

  const { data: topics, isLoading: topicsLoading } = useQuery({
    queryKey: ["dashboard-topics"],
    queryFn: () => api.dashboard.topics(10),
    refetchInterval: 30000,
  });

  const { data: entities, isLoading: entitiesLoading } = useQuery({
    queryKey: ["dashboard-entities"],
    queryFn: () => api.dashboard.entities(24),
    refetchInterval: 30000,
  });

  const { data: recentMemories, isLoading: recentLoading } = useQuery({
    queryKey: ["dashboard-recent"],
    queryFn: () => api.dashboard.recent(500),
    refetchInterval: 30000,
  });

  const { data: reflections, isLoading: reflectionsLoading } = useQuery({
    queryKey: ["dashboard-reflections"],
    queryFn: () => api.dashboard.reflections(6),
    refetchInterval: 30000,
  });

  const { data: weeklyReport } = useQuery({
    queryKey: ["dashboard-weekly"],
    queryFn: () => api.dashboard.weeklyReport(),
    refetchInterval: 60000,
  });

  const { data: traces } = useQuery({
    queryKey: ["dashboard-traces"],
    queryFn: () => api.dashboard.traces(),
    refetchInterval: 5000,
  });

  // 图表数据：从 recentMemories 按天聚合（30 天窗口）
  const chartData = useMemo(() => {
    if (!recentMemories || recentMemories.length === 0) return [];
    return aggregateByDay(recentMemories, 30);
  }, [recentMemories]);

  return (
    <PageTransition>
      <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
        {/* ── Page header ── */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight">记忆仪表盘</h1>
            <p className="text-xs text-os-subtle mt-0.5">你的第二大脑 — 记忆全景</p>
          </div>
          <div className="flex items-center gap-2 text-2xs text-os-muted">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-status-breathe" />
            实时监控中
          </div>
        </div>

        {/* ── Memory Stats Cards (5 格) ── */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <StaggerItem delay={0}>
            <StatusCard
              icon={Brain}
              label="总记忆"
              value={summaryLoading ? "..." : formatNumber(summary?.total_memories || 0)}
              accent="indigo"
            />
          </StaggerItem>
          <StaggerItem delay={0.03}>
            <StatusCard
              icon={Layers}
              label="活跃记忆"
              value={summaryLoading ? "..." : formatNumber(summary?.active_memories || 0)}
              accent="emerald"
            />
          </StaggerItem>
          <StaggerItem delay={0.06}>
            <StatusCard
              icon={Archive}
              label="已归档"
              value={summaryLoading ? "..." : formatNumber(summary?.archived_memories || 0)}
              accent="amber"
            />
          </StaggerItem>
          <StaggerItem delay={0.09}>
            <StatusCard
              icon={GitMerge}
              label="已合并"
              value={summaryLoading ? "..." : formatNumber(summary?.merged_memories || 0)}
              accent="violet"
            />
          </StaggerItem>
          <StaggerItem delay={0.12}>
            <StatusCard
              icon={Lightbulb}
              label="反思"
              value={summaryLoading ? "..." : formatNumber(summary?.reflect_count || 0)}
              accent="amber"
            />
          </StaggerItem>
        </div>

        {/* ── Memory Growth + Top Topics ── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Growth Chart (2/3) */}
          <div className="lg:col-span-2">
            <StaggerItem delay={0.15}>
              <div className="os-card p-4 h-full">
                <div className="flex items-center gap-2 mb-4">
                  <TrendingUp size={14} className="text-os-accent" />
                  <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">
                    记忆增长 (30天)
                  </h2>
                  {!recentLoading && (
                    <span className="text-2xs text-os-muted ml-auto">
                      {summary?.episodic_count || 0} 情景 · {summary?.semantic_count || 0} 语义 · {summary?.reflect_count || 0} 反思
                    </span>
                  )}
                </div>
                <MemoryChart data={chartData} isLoading={recentLoading} />
                {/* Legend */}
                <div className="flex items-center gap-4 mt-2 text-2xs">
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-indigo-400" /> 情景</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-emerald-400" /> 语义</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-amber-400" /> 反思</span>
                </div>
              </div>
            </StaggerItem>
          </div>

          {/* Top Topics (1/3) */}
          <StaggerItem delay={0.2}>
            <div className="os-card p-4 h-full">
              <div className="flex items-center gap-2 mb-3">
                <Tag size={14} className="text-os-accent" />
                <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">热门主题</h2>
                <span className="text-2xs text-os-muted ml-auto">
                  {topics?.length || 0} 个
                </span>
              </div>
              <TopicList topics={topics} isLoading={topicsLoading} />
            </div>
          </StaggerItem>
        </div>

        {/* ── Recent Memories + Recent Reflections ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Recent Memories */}
          <StaggerItem delay={0.25}>
            <div className="os-card p-4 h-full">
              <div className="flex items-center gap-2 mb-3">
                <Brain size={14} className="text-os-accent" />
                <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">最近记忆</h2>
                <span className="text-2xs text-os-muted ml-auto">
                  {recentMemories?.slice(0, 15).length || 0} 条
                </span>
              </div>
              <RecentMemories
                memories={recentMemories?.slice(0, 15)}
                isLoading={recentLoading}
              />
            </div>
          </StaggerItem>

          {/* Recent Reflections */}
          <StaggerItem delay={0.3}>
            <div className="os-card p-4 h-full">
              <div className="flex items-center gap-2 mb-3">
                <Lightbulb size={14} className="text-os-accent" />
                <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">最近反思</h2>
                <span className="text-2xs text-os-muted ml-auto">
                  {reflections?.length || 0} 条
                </span>
              </div>
              <RecentReflections reflections={reflections} isLoading={reflectionsLoading} />
            </div>
          </StaggerItem>
        </div>

        {/* ── Top Entities + System Health ── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Top Entities */}
          <div className="lg:col-span-2">
          <StaggerItem delay={0.35}>
            <div className="os-card p-4 h-full">
              <div className="flex items-center gap-2 mb-3">
                <Tag size={14} className="text-os-accent" />
                <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">实体图谱</h2>
                <span className="text-2xs text-os-muted ml-auto">
                  {entities?.length || 0} 个
                </span>
              </div>
              <EntityList entities={entities} isLoading={entitiesLoading} />
            </div>
          </StaggerItem>
          </div>

          {/* System Health */}
          <StaggerItem delay={0.4}>
            <div className="os-card p-4 h-full">
              <div className="flex items-center gap-2 mb-3">
                <Activity size={14} className="text-os-accent" />
                <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">系统健康</h2>
              </div>
              <div className="space-y-4">
                {/* Queue indicators */}
                {summary && (
                  <div className="grid grid-cols-2 gap-2">
                    <div className="os-card p-2 text-center">
                      <span className="text-2xs text-os-subtle">队列待处理</span>
                      <p className={cn("text-sm font-mono font-semibold", summary.queue_depth > 5 ? "text-amber-400" : "text-emerald-400")}>
                        {summary.queue_depth}
                      </p>
                    </div>
                    <div className="os-card p-2 text-center">
                      <span className="text-2xs text-os-subtle">DLQ 积压</span>
                      <p className={cn("text-sm font-mono font-semibold", summary.dlq_count > 0 ? "text-red-400" : "text-os-subtle")}>
                        {summary.dlq_count}
                      </p>
                    </div>
                  </div>
                )}

                {/* Runtime Monitor */}
                <RuntimeMonitor />

                {/* Weekly Report Status */}
                {weeklyReport && (
                  <div className="border border-os-border/30 rounded-lg p-3 text-center">
                    <p className="text-2xs text-os-muted mb-1">
                      {weeklyReport.message}
                    </p>
                    <div className="flex items-center justify-center gap-3 text-2xs text-os-subtle">
                      <span>本周 +{weeklyReport.stats.week_new_memories} 条</span>
                      <span>反思 {weeklyReport.stats.week_reflections} 条</span>
                    </div>
                    {weeklyReport.stats.week_top_entities.length > 0 && (
                      <div className="flex items-center justify-center gap-1.5 mt-1.5 flex-wrap">
                        {weeklyReport.stats.week_top_entities.map((name) => (
                          <span key={name} className="text-2xs px-1.5 py-0.5 rounded bg-os-surface text-indigo-400/70">
                            #{name}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </StaggerItem>
        </div>

        {/* ── Trace Timeline ── */}
        <StaggerItem delay={0.45}>
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
