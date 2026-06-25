"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Clock, ArrowRight, Brain, Archive, GitMerge, TrendingUp,
  Image, Sparkles, FileText, Loader2, Calendar,
} from "lucide-react";
import { cn, formatDate, formatNumber } from "@/lib/utils";
import { api } from "@/services/api";
import type { TimelineEvent, TimelineStats } from "@/types";

// ── 事件类型映射 ──
const EVENT_META: Record<string, {
  label: string;
  icon: React.ReactNode;
  color: string;
  bg: string;
  border: string;
}> = {
  memory_created: {
    label: "记忆创建",
    icon: <Brain size={11} />,
    color: "text-emerald-400",
    bg: "bg-emerald-400/10",
    border: "border-emerald-400/20",
  },
  memory_archived: {
    label: "记忆归档",
    icon: <Archive size={11} />,
    color: "text-amber-400",
    bg: "bg-amber-400/10",
    border: "border-amber-400/20",
  },
  memory_merged: {
    label: "记忆合并",
    icon: <GitMerge size={11} />,
    color: "text-violet-400",
    bg: "bg-violet-400/10",
    border: "border-violet-400/20",
  },
  memory_promoted: {
    label: "记忆提升",
    icon: <TrendingUp size={11} />,
    color: "text-cyan-400",
    bg: "bg-cyan-400/10",
    border: "border-cyan-400/20",
  },
  image_uploaded: {
    label: "图片上传",
    icon: <Image size={11} />,
    color: "text-sky-400",
    bg: "bg-sky-400/10",
    border: "border-sky-400/20",
  },
  reflection_generated: {
    label: "反思生成",
    icon: <Sparkles size={11} />,
    color: "text-indigo-400",
    bg: "bg-indigo-400/10",
    border: "border-indigo-400/20",
  },
  weekly_report_generated: {
    label: "周报生成",
    icon: <FileText size={11} />,
    color: "text-zinc-400",
    bg: "bg-zinc-400/10",
    border: "border-zinc-400/20",
  },
};

const TYPE_LABELS: Record<string, string> = {
  episodic: "情景",
  semantic: "语义",
  procedural: "程序",
  reflect: "反思",
};

export function MemoryFlowTimeline() {
  const [filterType, setFilterType] = useState<string>("all");

  // 拉取时间线
  const { data: days, isLoading } = useQuery({
    queryKey: ["memory-flow-timeline", 14],
    queryFn: () => api.timeline.list({ limit: 14 }),
    refetchInterval: 30000,
  });

  // 拉取统计
  const { data: stats } = useQuery({
    queryKey: ["memory-flow-stats"],
    queryFn: () => api.timeline.stats(),
    refetchInterval: 60000,
  });

  // 展平事件并按类型过滤
  const allEvents = useMemo(() => {
    if (!days) return [];
    return days.flatMap((day) =>
      day.events.map((e) => ({ ...e, day_date: day.date })),
    );
  }, [days]);

  const filteredEvents = useMemo(() => {
    if (filterType === "all") return allEvents;
    return allEvents.filter((e) => e.type === filterType);
  }, [allEvents, filterType]);

  // 统计磁贴数据
  const statTiles = [
    { label: "总事件", value: stats?.total_events ?? 0, icon: <Clock size={11} />, accent: "violet" as const },
    { label: "创建", value: stats?.created_count ?? 0, icon: <Brain size={11} />, accent: "emerald" as const },
    { label: "归档", value: stats?.archived_count ?? 0, icon: <Archive size={11} />, accent: "amber" as const },
    { label: "合并", value: stats?.merged_count ?? 0, icon: <GitMerge size={11} />, accent: "violet" as const },
    { label: "提升", value: stats?.promoted_count ?? 0, icon: <TrendingUp size={11} />, accent: "cyan" as const },
    { label: "反思", value: stats?.reflection_count ?? 0, icon: <Sparkles size={11} />, accent: "indigo" as const },
    { label: "图片", value: stats?.image_count ?? 0, icon: <Image size={11} />, accent: "sky" as const },
    { label: "周报", value: stats?.weekly_report_count ?? 0, icon: <FileText size={11} />, accent: "zinc" as const },
  ];

  return (
    <div className="space-y-4">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Clock size={14} className="text-violet-400" />
          <h2 className="text-sm font-semibold text-os-text-high">记忆流转时间线</h2>
          <span className="text-2xs text-os-muted">chat → working → long-term storage</span>
        </div>
      </div>

      {/* ── 统计磁贴 ── */}
      <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
        {statTiles.map((s) => (
          <StatMini key={s.label} {...s} />
        ))}
      </div>

      {/* ── 过滤器 ── */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-2xs text-os-muted mr-1">事件类型:</span>
        <FilterChip
          active={filterType === "all"}
          onClick={() => setFilterType("all")}
          label="全部"
        />
        {Object.entries(EVENT_META).map(([key, meta]) => (
          <FilterChip
            key={key}
            active={filterType === key}
            onClick={() => setFilterType(key)}
            label={meta.label}
            icon={meta.icon}
          />
        ))}
      </div>

      {/* ── 时间线 ── */}
      <div className="rounded-md border border-os-border bg-os-surface/30 p-4">
        {isLoading ? (
          <div className="flex items-center justify-center py-8 text-2xs text-os-muted gap-2">
            <Loader2 size={14} className="animate-spin" /> 加载时间线...
          </div>
        ) : filteredEvents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-2xs text-os-muted">
            <Clock size={20} className="mb-2 opacity-50" />
            暂无事件
          </div>
        ) : (
          <div className="space-y-4">
            {days?.map((day) => {
              const dayEvents = day.events.filter((e) =>
                filterType === "all" ? true : e.type === filterType,
              );
              if (dayEvents.length === 0) return null;
              return (
                <div key={day.date} className="space-y-2">
                  {/* 日期分隔 */}
                  <div className="flex items-center gap-2 sticky top-0 bg-os-surface/80 backdrop-blur-sm py-1 z-10">
                    <Calendar size={11} className="text-os-muted" />
                    <span className="text-2xs font-medium text-os-subtle font-mono">{day.date}</span>
                    <span className="text-2xs text-os-muted">·</span>
                    <span className="text-2xs text-os-muted">{dayEvents.length} events</span>
                    <div className="flex-1 h-px bg-os-border/50" />
                  </div>

                  {/* 事件列表 */}
                  <ul className="space-y-1.5">
                    {dayEvents.map((event, idx) => {
                      const meta = EVENT_META[event.type] || EVENT_META.memory_created;
                      return (
                        <motion.li
                          key={event.id}
                          initial={{ opacity: 0, x: -8 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: Math.min(idx * 0.02, 0.3) }}
                          className="flex items-start gap-2.5 group"
                        >
                          {/* 事件图标 */}
                          <div className={cn(
                            "shrink-0 w-6 h-6 rounded flex items-center justify-center border",
                            meta.bg, meta.border, meta.color,
                          )}>
                            {meta.icon}
                          </div>

                          {/* 事件内容 */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className={cn("text-2xs font-medium", meta.color)}>
                                {meta.label}
                              </span>
                              <span className="text-2xs text-os-muted font-mono">
                                {TYPE_LABELS[event.memory_type] || event.memory_type}
                              </span>
                              <span className="text-2xs text-os-muted">·</span>
                              <span className="text-2xs text-os-muted">
                                {formatDate(event.timestamp)}
                              </span>
                              {event.status !== "active" && (
                                <span className="text-2xs px-1 py-0.5 rounded bg-os-elevated text-os-muted font-mono">
                                  {event.status}
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-os-subtle mt-0.5 truncate group-hover:whitespace-normal group-hover:overflow-visible">
                              {event.content_preview}
                            </p>
                            {event.entities.length > 0 && (
                              <div className="flex items-center gap-1 mt-1 flex-wrap">
                                {event.entities.slice(0, 5).map((e) => (
                                  <span key={e} className="text-2xs px-1 py-0.5 rounded bg-violet-400/10 text-violet-300 font-mono">
                                    {e}
                                  </span>
                                ))}
                                {event.entities.length > 5 && (
                                  <span className="text-2xs text-os-muted">+{event.entities.length - 5}</span>
                                )}
                              </div>
                            )}
                          </div>

                          {/* 重要度 */}
                          <div className="shrink-0 text-right">
                            <div className={cn(
                              "text-xs font-bold tabular-nums",
                              event.importance >= 8 ? "text-emerald-400" : event.importance >= 6 ? "text-amber-400" : "text-zinc-500",
                            )}>
                              {event.importance}
                            </div>
                            <div className="text-2xs text-os-muted">imp</div>
                          </div>
                        </motion.li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── 流转示意 ── */}
      <div className="rounded-md border border-os-border bg-os-surface/20 p-3">
        <div className="text-2xs text-os-muted mb-2 uppercase tracking-wider">记忆流转路径</div>
        <div className="flex items-center gap-2 text-2xs flex-wrap">
          <FlowNode label="Chat Input" color="cyan" />
          <ArrowRight size={11} className="text-os-muted" />
          <FlowNode label="STM (Episodic)" color="cyan" />
          <ArrowRight size={11} className="text-os-muted" />
          <FlowNode label="WM (Working Set)" color="violet" />
          <ArrowRight size={11} className="text-os-muted" />
          <FlowNode label="Reflection" color="indigo" />
          <ArrowRight size={11} className="text-os-muted" />
          <FlowNode label="LTM (Semantic/Procedural)" color="emerald" />
          <ArrowRight size={11} className="text-os-muted" />
          <FlowNode label="Archive" color="amber" />
        </div>
      </div>
    </div>
  );
}

// ── 子组件 ──

function StatMini({
  label, value, icon, accent,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  accent: "violet" | "emerald" | "amber" | "cyan" | "indigo" | "sky" | "zinc";
}) {
  const accentMap = {
    violet: "text-violet-400",
    emerald: "text-emerald-400",
    amber: "text-amber-400",
    cyan: "text-cyan-400",
    indigo: "text-indigo-400",
    sky: "text-sky-400",
    zinc: "text-zinc-400",
  };
  return (
    <div className="rounded-md border border-os-border/50 bg-os-base/50 p-2">
      <div className="flex items-center gap-1 text-2xs text-os-muted mb-0.5">
        <span className={accentMap[accent]}>{icon}</span>
        {label}
      </div>
      <div className={cn("text-sm font-bold tabular-nums", accentMap[accent])}>
        {formatNumber(value)}
      </div>
    </div>
  );
}

function FilterChip({
  active, onClick, label, icon,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  icon?: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-1 px-2 py-0.5 rounded text-2xs transition-colors",
        active
          ? "bg-violet-400/10 text-violet-300 border border-violet-400/30"
          : "bg-os-elevated text-os-muted border border-os-border hover:text-os-subtle",
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function FlowNode({ label, color }: { label: string; color: "cyan" | "violet" | "indigo" | "emerald" | "amber" }) {
  const colorMap = {
    cyan: "bg-cyan-400/10 text-cyan-400 border-cyan-400/20",
    violet: "bg-violet-400/10 text-violet-400 border-violet-400/20",
    indigo: "bg-indigo-400/10 text-indigo-400 border-indigo-400/20",
    emerald: "bg-emerald-400/10 text-emerald-400 border-emerald-400/20",
    amber: "bg-amber-400/10 text-amber-400 border-amber-400/20",
  };
  return (
    <span className={cn("px-2 py-0.5 rounded border font-mono", colorMap[color])}>
      {label}
    </span>
  );
}
