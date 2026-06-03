"use client";

import { useState, useMemo, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  Clock, Calendar, GitCommit, Archive, Lightbulb, Image, TrendingUp,
  FileText, ChevronLeft, ChevronRight, Filter, Brain, Hash,
  BarChart3, BookOpen, Zap,
} from "lucide-react";
import { api } from "@/services/api";
import { PageTransition, StaggerItem } from "@/components/animations/page-transition";
import { CardSkeleton, Skeleton } from "@/components/animations/skeleton";
import { cn, formatDate, importanceColor } from "@/lib/utils";
import type { TimelineDay, TimelineStats, TimelineEventType } from "@/types";

// ── Helpers ──

const eventMeta: Record<TimelineEventType, { icon: React.ElementType; label: string; color: string }> = {
  memory_created:       { icon: GitCommit, label: "创建记忆",  color: "bg-indigo-400" },
  memory_archived:      { icon: Archive,  label: "归档记忆",  color: "bg-amber-400" },
  memory_merged:        { icon: GitCommit, label: "合并记忆",  color: "bg-zinc-400" },
  memory_promoted:      { icon: TrendingUp, label: "概念提升", color: "bg-emerald-400" },
  image_uploaded:       { icon: Image,    label: "图片上传",  color: "bg-violet-400" },
  reflection_generated: { icon: Lightbulb, label: "反思生成", color: "bg-amber-400" },
  weekly_report_generated: { icon: FileText, label: "周报生成", color: "bg-emerald-400" },
};

const memoryTypeLabel: Record<string, string> = {
  episodic: "情景", semantic: "语义", procedural: "程序", reflect: "反思",
};

// ── Calendar Heatmap ──

function CalendarHeatmap({ days }: { days: TimelineDay[] }) {
  // Build a map of date → count for the last ~6 months
  const now = new Date();
  const weeksBack = 26;
  const startDate = new Date(now);
  startDate.setDate(startDate.getDate() - weeksBack * 7);

  const dateCount: Record<string, number> = {};
  for (const d of days) {
    dateCount[d.date] = (dateCount[d.date] || 0) + d.count;
  }

  const maxCount = Math.max(...Object.values(dateCount), 1);

  const weeks: { date: Date; count: number }[][] = [];
  let current = new Date(startDate);

  // Align to start of week (Sunday)
  current.setDate(current.getDate() - current.getDay());

  while (current <= now) {
    const week: { date: Date; count: number }[] = [];
    for (let i = 0; i < 7; i++) {
      const key = current.toISOString().slice(0, 10);
      week.push({ date: new Date(current), count: dateCount[key] || 0 });
      current.setDate(current.getDate() + 1);
    }
    weeks.push(week);
  }

  function heatColor(count: number): string {
    if (count === 0) return "bg-os-surface";
    const pct = count / maxCount;
    if (pct < 0.25) return "bg-indigo-400/20";
    if (pct < 0.5) return "bg-indigo-400/40";
    if (pct < 0.75) return "bg-indigo-400/60";
    return "bg-indigo-400/80";
  }

  const dayLabels = ["日", "一", "二", "三", "四", "五", "六"];

  return (
    <div className="flex gap-0.5 overflow-x-auto pb-2">
      {/* Day labels */}
      <div className="flex flex-col gap-0.5 mr-0.5">
        {dayLabels.map((label, i) => (
          <div key={i} className="w-4 h-3 flex items-center justify-center text-2xs text-os-muted">
            {i % 2 === 0 ? label : ""}
          </div>
        ))}
      </div>
      {/* Weeks */}
      {weeks.map((week, wi) => (
        <div key={wi} className="flex flex-col gap-0.5">
          {week.map((day, di) => (
            <motion.div
              key={`${wi}-${di}`}
              initial={{ opacity: 0, scale: 0.5 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: Math.min(wi * 0.01 + di * 0.005, 1) }}
              className={cn(
                "w-3 h-3 rounded-sm transition-colors",
                heatColor(day.count),
                day.count > 0 && "hover:ring-1 hover:ring-os-accent"
              )}
              title={`${day.date.toISOString().slice(0, 10)}: ${day.count} 事件`}
            />
          ))}
        </div>
      ))}
      {/* Legend */}
      <div className="flex items-end gap-0.5 ml-2 pb-0.5">
        <span className="text-2xs text-os-muted mr-0.5">少</span>
        <div className="w-3 h-3 rounded-sm bg-os-surface" />
        <div className="w-3 h-3 rounded-sm bg-indigo-400/20" />
        <div className="w-3 h-3 rounded-sm bg-indigo-400/40" />
        <div className="w-3 h-3 rounded-sm bg-indigo-400/60" />
        <div className="w-3 h-3 rounded-sm bg-indigo-400/80" />
        <span className="text-2xs text-os-muted ml-0.5">多</span>
      </div>
    </div>
  );
}

// ── Stats Bar ──

function StatsBar({ stats, isLoading }: { stats?: TimelineStats; isLoading: boolean }) {
  if (isLoading) return <Skeleton className="h-12 w-full" />;
  if (!stats) return null;

  const items = [
    { count: stats.created_count, label: "新增", color: "text-indigo-400" },
    { count: stats.reflection_count, label: "反思", color: "text-amber-400" },
    { count: stats.archived_count, label: "归档", color: "text-amber-400/70" },
    { count: stats.image_count, label: "图片", color: "text-violet-400" },
    { count: stats.promoted_count, label: "提升", color: "text-emerald-400" },
  ];

  return (
    <div className="flex items-center gap-4 flex-wrap">
      <span className="text-2xs text-os-muted uppercase tracking-wider">统计</span>
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-1">
          <span className={cn("text-sm font-mono font-semibold", item.color)}>{item.count}</span>
          <span className="text-2xs text-os-subtle">{item.label}</span>
        </div>
      ))}
      <span className="text-2xs text-os-muted ml-auto">
        总计 {stats.total_events} 事件
      </span>
    </div>
  );
}

// ── Main Page ──

export default function TimelinePage() {
  const [memoryType, setMemoryType] = useState("");
  const [entity, setEntity] = useState("");
  const [dateRange, setDateRange] = useState<"all" | "today" | "week" | "month">("all");
  const [page, setPage] = useState(1);
  const limit = 30;

  // Build date range
  const { startDate, endDate } = useMemo(() => {
    const now = new Date();
    const toStr = (d: Date) => d.toISOString().slice(0, 10);
    switch (dateRange) {
      case "today": return { startDate: toStr(now), endDate: toStr(now) };
      case "week": {
        const week = new Date(now); week.setDate(week.getDate() - 7);
        return { startDate: toStr(week), endDate: "" };
      }
      case "month": {
        const month = new Date(now); month.setMonth(month.getMonth() - 1);
        return { startDate: toStr(month), endDate: "" };
      }
      default: return { startDate: "", endDate: "" };
    }
  }, [dateRange]);

  // Data
  const { data: days, isLoading } = useQuery({
    queryKey: ["timeline", startDate, endDate, memoryType, entity, page],
    queryFn: () => api.timeline.list({
      start_date: startDate || undefined,
      end_date: endDate || undefined,
      memory_type: memoryType || undefined,
      entity: entity || undefined,
      page, limit,
    }),
    refetchInterval: 30000,
  });

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["timeline-stats", startDate, endDate],
    queryFn: () => api.timeline.stats({
      start_date: startDate || undefined,
      end_date: endDate || undefined,
    }),
    refetchInterval: 60000,
  });

  const typeOptions = [
    { value: "", label: "全部类型" },
    { value: "episodic", label: "情景" },
    { value: "semantic", label: "语义" },
    { value: "reflect", label: "反思" },
  ];

  const rangeOptions = [
    { value: "all", label: "全部" },
    { value: "today", label: "今天" },
    { value: "week", label: "本周" },
    { value: "month", label: "本月" },
  ];

  return (
    <PageTransition>
      <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight">记忆时间轴</h1>
            <p className="text-xs text-os-subtle mt-0.5">
              {days ? `${days.length} 天有记录` : "加载中..."}
            </p>
          </div>
          <div className="flex items-center gap-2 text-2xs text-os-muted">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-status-breathe" />
            实时
          </div>
        </div>

        {/* Stats Bar */}
        <div className="os-card p-3">
          <StatsBar stats={stats} isLoading={statsLoading} />
        </div>

        {/* Calendar Heatmap */}
        <div className="os-card p-4 overflow-x-auto">
          <div className="flex items-center gap-2 mb-3">
            <Calendar size={14} className="text-os-accent" />
            <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">贡献日历</h2>
            <span className="text-2xs text-os-muted">过去 6 个月</span>
          </div>
          <CalendarHeatmap days={days || []} />
        </div>

        {/* Filter Bar */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Time range */}
          <div className="flex items-center gap-0.5">
            {rangeOptions.map((opt) => (
              <button
                key={opt.value}
                onClick={() => { setPage(1); setDateRange(opt.value as typeof dateRange); }}
                className={cn(
                  "px-2.5 py-1 rounded text-2xs transition-colors",
                  dateRange === opt.value
                    ? "bg-os-accent/20 text-os-accent font-medium"
                    : "text-os-subtle hover:text-os-text hover:bg-os-surface"
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <span className="w-px h-4 bg-os-border" />

          {/* Memory type filter */}
          <div className="flex items-center gap-0.5">
            {typeOptions.map((opt) => (
              <button
                key={opt.value}
                onClick={() => { setPage(1); setMemoryType(opt.value); }}
                className={cn(
                  "px-2.5 py-1 rounded text-2xs transition-colors",
                  memoryType === opt.value
                    ? "bg-os-accent/20 text-os-accent font-medium"
                    : "text-os-subtle hover:text-os-text hover:bg-os-surface"
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <span className="w-px h-4 bg-os-border" />

          {/* Entity filter */}
          <input
            value={entity}
            onChange={(e) => { setPage(1); setEntity(e.target.value); }}
            placeholder="按实体过滤..."
            className="h-6 w-40 px-2 rounded bg-os-surface border border-os-border text-2xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent"
          />

          <span className="w-px h-4 bg-os-border" />

          <div className="flex items-center gap-1">
            <Filter size={11} className="text-os-muted" />
            <span className="text-2xs text-os-muted">
              {memoryType || entity || dateRange !== "all" ? "已过滤" : "无过滤"}
            </span>
          </div>
        </div>

        {/* Timeline Feed */}
        <div className="space-y-6">
          {isLoading ? (
            <div className="space-y-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="os-card p-4 space-y-3">
                  <Skeleton className="h-3 w-20" />
                  <Skeleton className="h-12 w-full" />
                </div>
              ))}
            </div>
          ) : !days || days.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-os-muted">
              <Clock size={48} className="mb-4 opacity-30" />
              <p className="text-sm">暂无时间轴数据</p>
              <p className="text-2xs mt-1">开始记录记忆后，时间轴会自动填充</p>
            </div>
          ) : (
            <>
              {days.map((day) => (
                <motion.div
                  key={day.date}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="relative"
                >
                  {/* Date header */}
                  <div className="sticky top-0 z-10 flex items-center gap-3 mb-3 py-2 bg-os-base/80 backdrop-blur-sm">
                    <Calendar size={14} className="text-os-accent" />
                    <span className="text-sm font-semibold text-os-text-high">
                      {day.date}
                    </span>
                    <span className="text-2xs text-os-muted">
                      {day.count} 个事件
                    </span>
                    <div className="flex-1 h-px bg-os-border ml-2" />
                  </div>

                  {/* Events */}
                  <div className="space-y-2 ml-6 border-l border-os-border pl-6 pb-2">
                    {day.events.map((event, ei) => {
                      const meta = eventMeta[event.type] || eventMeta.memory_created;
                      return (
                        <motion.div
                          key={`${event.id}-${event.type}`}
                          initial={{ opacity: 0, x: -8 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: ei * 0.03 }}
                          className="relative"
                        >
                          {/* Dot */}
                          <div className={cn(
                            "absolute -left-[30px] top-2 w-2 h-2 rounded-full border-2 border-os-base",
                            importanceColor(event.importance).replace("text-", "bg-"),
                          )} />

                          {/* Card */}
                          <div className="os-card p-3 os-card-hover group">
                            <div className="flex items-start gap-3">
                              {/* Icon */}
                              <div className="w-7 h-7 rounded-lg bg-os-elevated flex items-center justify-center shrink-0 mt-0.5">
                                <meta.icon size={13} className={cn(
                                  "text-os-subtle group-hover:text-os-accent transition-colors"
                                )} />
                              </div>

                              {/* Content */}
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="text-2xs font-medium text-os-text-high">
                                    {meta.label}
                                  </span>
                                  <span className={cn(
                                    "text-2xs px-1.5 py-0.5 rounded-full",
                                    event.memory_type === "reflect" ? "bg-amber-400/10 text-amber-400" :
                                    event.memory_type === "semantic" ? "bg-emerald-400/10 text-emerald-400" :
                                    "bg-indigo-400/10 text-indigo-400"
                                  )}>
                                    {memoryTypeLabel[event.memory_type] || event.memory_type}
                                  </span>
                                </div>
                                <p className="text-xs text-os-text line-clamp-2 leading-relaxed">
                                  {event.content_preview}
                                </p>
                                {event.entities.length > 0 && (
                                  <div className="flex gap-1 mt-1.5 flex-wrap">
                                    {event.entities.slice(0, 3).map((e) => (
                                      <span key={e} className="text-2xs px-1 py-0.5 rounded bg-os-elevated text-os-muted">
                                        {e}
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>

                              {/* Importance */}
                              <span className={cn(
                                "text-2xs font-mono shrink-0",
                                importanceColor(event.importance)
                              )}>
                                {event.importance}
                              </span>
                            </div>
                          </div>
                        </motion.div>
                      );
                    })}
                  </div>
                </motion.div>
              ))}

              {/* Pagination */}
              <div className="flex items-center justify-center gap-3 pt-4">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="flex items-center gap-1 px-3 py-1.5 rounded text-xs text-os-subtle hover:text-os-text hover:bg-os-surface disabled:opacity-30 transition-colors"
                >
                  <ChevronLeft size={13} /> 上一页
                </button>
                <span className="text-2xs text-os-muted">第 {page} 页</span>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={!days || days.length < limit}
                  className="flex items-center gap-1 px-3 py-1.5 rounded text-xs text-os-subtle hover:text-os-text hover:bg-os-surface disabled:opacity-30 transition-colors"
                >
                  下一页 <ChevronRight size={13} />
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </PageTransition>
  );
}

