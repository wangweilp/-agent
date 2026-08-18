"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Archive,
  BarChart3,
  Brain,
  Cpu,
  GitMerge,
  Layers,
  Lightbulb,
  Tag,
  TrendingUp,
} from "lucide-react";
import { api } from "@/services/api";
import { PageTransition, StaggerItem } from "@/components/animations/page-transition";
import { TraceTimeline } from "@/components/dashboard/trace-timeline";
import { MemoryChart } from "@/components/dashboard/memory-chart";
import { RuntimeMonitor } from "@/components/dashboard/runtime-monitor";
import { TopicList } from "@/components/dashboard/topic-list";
import { RecentMemories } from "@/components/dashboard/recent-memories";
import { RecentReflections } from "@/components/dashboard/recent-reflections";
import { EntityList } from "@/components/dashboard/entity-list";
import { SaaSMetrics } from "@/components/dashboard/saas-metrics";
import {
  InfoBanner,
  MetricCard,
  OsBadge,
  OsCard,
  PageHeader,
  PageShell,
  SectionHeader,
  StatusBadge,
} from "@/components/ui/os";
import { cn, formatNumber } from "@/lib/utils";
import { layout } from "@/styles/layout";

interface ChartDataPoint {
  label: string;
  count: number;
  episodic: number;
  semantic: number;
  reflect: number;
}

function aggregateByDay(
  memories: { timestamp: string; memory_type: string }[],
  days: number,
): ChartDataPoint[] {
  const now = new Date();
  const buckets: Map<string, { episodic: number; semantic: number; reflect: number }> = new Map();

  let bucketSize = 1;
  if (days >= 60) bucketSize = 7;
  else if (days >= 14) bucketSize = 3;

  for (let i = days - 1; i >= 0; i -= bucketSize) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const key =
      bucketSize >= 7
        ? d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" })
        : d.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
    buckets.set(key, { episodic: 0, semantic: 0, reflect: 0 });
  }

  const cutoff = new Date(now);
  cutoff.setDate(cutoff.getDate() - days);
  for (const mem of memories) {
    const t = new Date(mem.timestamp);
    if (t < cutoff) continue;

    const d = new Date(t);
    if (bucketSize >= 7) {
      d.setDate(d.getDate() - d.getDay());
    } else if (bucketSize >= 3) {
      d.setDate(d.getDate() - (d.getDate() % bucketSize));
    }

    const key =
      bucketSize >= 7
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

export default function DashboardPage() {
  const { data: summary, isLoading: summaryLoading, isError: summaryError } = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: () => api.dashboard.summary(),
    refetchInterval: 15000,
  });

  const { data: topics, isLoading: topicsLoading, isError: topicsError } = useQuery({
    queryKey: ["dashboard-topics"],
    queryFn: () => api.dashboard.topics(10),
    refetchInterval: 30000,
  });

  const { data: entities, isLoading: entitiesLoading, isError: entitiesError } = useQuery({
    queryKey: ["dashboard-entities"],
    queryFn: () => api.dashboard.entities(24),
    refetchInterval: 30000,
  });

  const { data: recentMemories, isLoading: recentLoading, isError: recentError } = useQuery({
    queryKey: ["dashboard-recent"],
    queryFn: () => api.dashboard.recent(500),
    refetchInterval: 30000,
  });

  const { data: reflections, isLoading: reflectionsLoading, isError: reflectionsError } = useQuery({
    queryKey: ["dashboard-reflections"],
    queryFn: () => api.dashboard.reflections(6),
    refetchInterval: 30000,
  });

  const { data: weeklyReport, isError: weeklyError } = useQuery({
    queryKey: ["dashboard-weekly"],
    queryFn: () => api.dashboard.weeklyReport(),
    refetchInterval: 60000,
  });

  const { data: traces, isError: tracesError } = useQuery({
    queryKey: ["dashboard-traces"],
    queryFn: () => api.dashboard.traces(),
    refetchInterval: 5000,
  });

  const chartData = useMemo(() => {
    if (!recentMemories || recentMemories.length === 0) return [];
    return aggregateByDay(recentMemories, 30);
  }, [recentMemories]);

  const totalQueue = (summary?.queue_depth || 0) + (summary?.dlq_count || 0);
  const dashboardError =
    summaryError ||
    topicsError ||
    entitiesError ||
    recentError ||
    reflectionsError ||
    weeklyError ||
    tracesError;

  return (
    <PageTransition>
      <PageShell>
        <PageHeader
          icon={BarChart3}
          title="记忆仪表盘"
          subtitle="面向工作区的记忆增长、知识主题、运行状态与 trace 流水线总览。"
          actions={
            <>
              <StatusBadge status={dashboardError ? "warning" : summary?.dlq_count ? "warning" : "ready"}>
                {dashboardError ? "部分数据加载失败" : summary?.dlq_count ? "需要关注" : "实时监控中"}
              </StatusBadge>
              <OsBadge variant="muted">每 15 秒刷新</OsBadge>
            </>
          }
        />

        {dashboardError && (
          <InfoBanner icon={AlertTriangle} variant="danger" title="部分仪表盘数据加载失败">
            当前页面可能显示不完整数据，请稍后刷新。已成功返回的数据仍会正常保留。
          </InfoBanner>
        )}

        <SaaSMetrics />

        <div className={layout.grid.five}>
          <StaggerItem delay={0}>
            <MetricCard
              icon={Brain}
              label="总记忆"
              value={summaryLoading ? "..." : formatNumber(summary?.total_memories || 0)}
              detail="情景 / 语义 / 反思"
              accent="primary"
            />
          </StaggerItem>
          <StaggerItem delay={0.03}>
            <MetricCard
              icon={Layers}
              label="活跃记忆"
              value={summaryLoading ? "..." : formatNumber(summary?.active_memories || 0)}
              detail="可被检索与召回"
              accent="success"
            />
          </StaggerItem>
          <StaggerItem delay={0.06}>
            <MetricCard
              icon={Archive}
              label="已归档"
              value={summaryLoading ? "..." : formatNumber(summary?.archived_memories || 0)}
              detail="低频但保留上下文"
              accent="warning"
            />
          </StaggerItem>
          <StaggerItem delay={0.09}>
            <MetricCard
              icon={GitMerge}
              label="已合并"
              value={summaryLoading ? "..." : formatNumber(summary?.merged_memories || 0)}
              detail="去重与语义聚合"
              accent="info"
            />
          </StaggerItem>
          <StaggerItem delay={0.12}>
            <MetricCard
              icon={Lightbulb}
              label="反思"
              value={summaryLoading ? "..." : formatNumber(summary?.reflect_count || 0)}
              detail="自动沉淀的洞察"
              accent="warning"
            />
          </StaggerItem>
        </div>

        <InfoBanner icon={Cpu} variant={totalQueue > 5 ? "warning" : "info"}>
          当前队列深度 {summary?.queue_depth || 0}，DLQ {summary?.dlq_count || 0}。运行时面板会同步展示工作进程、任务耗时与最近写入状态。
        </InfoBanner>

        <div className={layout.grid.threeLg}>
          <OsCard className="lg:col-span-2" padding="md">
            <SectionHeader
              icon={TrendingUp}
              title="记忆增长"
              subtitle="最近 30 天按记忆类型聚合，保持固定图表高度，避免空数据时布局塌陷。"
              actions={
                !recentLoading && (
                  <OsBadge variant="muted">
                    {summary?.episodic_count || 0} 情景 / {summary?.semantic_count || 0} 语义 / {summary?.reflect_count || 0} 反思
                  </OsBadge>
                )
              }
              className="mb-4"
            />
            <MemoryChart data={chartData} isLoading={recentLoading} />
          </OsCard>

          <OsCard padding="md">
            <SectionHeader
              icon={Tag}
              title="热门主题"
              subtitle="按提及次数排序，使用排名与微型进度条呈现。"
              actions={<OsBadge variant="muted">{topics?.length || 0} 个</OsBadge>}
              className="mb-4"
            />
            <TopicList topics={topics} isLoading={topicsLoading} />
          </OsCard>
        </div>

        <div className={layout.grid.twoLg}>
          <OsCard padding="md">
            <SectionHeader
              icon={Brain}
              title="最近记忆"
              subtitle="保留时间线结构，降低颜色饱和度并强化内容扫描。"
              actions={<OsBadge variant="muted">{recentMemories?.slice(0, 15).length || 0} 条</OsBadge>}
              className="mb-4"
            />
            <RecentMemories memories={recentMemories?.slice(0, 15)} isLoading={recentLoading} />
          </OsCard>

          <OsCard padding="md">
            <SectionHeader
              icon={Lightbulb}
              title="最近反思"
              subtitle="展示高价值洞察，而不是松散文本堆叠。"
              actions={<OsBadge variant="muted">{reflections?.length || 0} 条</OsBadge>}
              className="mb-4"
            />
            <RecentReflections reflections={reflections} isLoading={reflectionsLoading} />
          </OsCard>
        </div>

        <div className={layout.grid.threeLg}>
          <OsCard className="lg:col-span-2" padding="md">
            <SectionHeader
              icon={Tag}
              title="实体图谱摘要"
              subtitle="从记忆流抽取的实体标签，按提及强度控制尺寸与层级。"
              actions={<OsBadge variant="muted">{entities?.length || 0} 个</OsBadge>}
              className="mb-4"
            />
            <EntityList entities={entities} isLoading={entitiesLoading} />
          </OsCard>

          <OsCard padding="md">
            <SectionHeader icon={Activity} title="系统健康" subtitle="写入工作进程、队列与本周统计。" className="mb-4" />
            <div className="space-y-4">
              {summary && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-2xl border border-os-border bg-os-surface-tinted p-3">
                    <span className="text-xs text-os-subtle">队列待处理</span>
                    <p className={cn("mt-1 font-mono text-xl font-semibold", summary.queue_depth > 5 ? "text-os-warning" : "text-os-success")}>
                      {summary.queue_depth}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-os-border bg-os-surface-tinted p-3">
                    <span className="text-xs text-os-subtle">DLQ 积压</span>
                    <p className={cn("mt-1 font-mono text-xl font-semibold", summary.dlq_count > 0 ? "text-os-danger" : "text-os-subtle")}>
                      {summary.dlq_count}
                    </p>
                  </div>
                </div>
              )}

              <RuntimeMonitor />

              {weeklyReport && (
                <div className="rounded-2xl border border-os-border bg-white p-4">
                  <p className="text-sm leading-6 text-os-text">{weeklyReport.message}</p>
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-os-subtle">
                    <OsBadge variant="success">本周 +{weeklyReport.stats.week_new_memories} 条</OsBadge>
                    <OsBadge variant="warning">反思 {weeklyReport.stats.week_reflections} 条</OsBadge>
                  </div>
                  {weeklyReport.stats.week_top_entities.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {weeklyReport.stats.week_top_entities.map((name) => (
                        <OsBadge key={name} variant="muted">
                          #{name}
                        </OsBadge>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </OsCard>
        </div>

        <OsCard padding="md">
          <SectionHeader
            icon={BarChart3}
            title="实时追踪"
            subtitle="最近的推理、工具调用、记忆读写与反思执行瀑布流。"
            actions={<OsBadge variant="muted">{traces?.length || 0} 条记录</OsBadge>}
            className="mb-4"
          />
          <TraceTimeline traces={traces || []} />
        </OsCard>
      </PageShell>
    </PageTransition>
  );
}
