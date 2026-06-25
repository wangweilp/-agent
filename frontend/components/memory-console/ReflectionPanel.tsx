"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Sparkles, Brain, GitMerge, AlertTriangle, TrendingUp,
  Loader2, Lightbulb, Target,
} from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { api } from "@/services/api";

export function ReflectionPanel() {
  // 拉取反思洞察列表
  const { data: insights, isLoading } = useQuery({
    queryKey: ["memory-console-reflection"],
    queryFn: () => api.reflection.list(),
    refetchInterval: 30000,
  });

  // 拉取最近的反思记忆（reflect 类型）
  const { data: recentReflections } = useQuery({
    queryKey: ["memory-console-recent-reflections", 20],
    queryFn: () => api.dashboard.reflections(20),
    refetchInterval: 30000,
  });

  // 统计
  const stats = useMemo(() => {
    const list = insights || [];
    const highConfidence = list.filter((i) => i.confidence >= 0.8).length;
    const topics = new Set(list.map((i) => i.topic)).size;
    const avgConfidence = list.length > 0 ? list.reduce((s, i) => s + i.confidence, 0) / list.length : 0;
    return { total: list.length, highConfidence, topics, avgConfidence };
  }, [insights]);

  // 按主题分组
  const groupedByTopic = useMemo(() => {
    const list = insights || [];
    const groups: Record<string, typeof list> = {};
    for (const item of list) {
      if (!groups[item.topic]) groups[item.topic] = [];
      groups[item.topic].push(item);
    }
    return Object.entries(groups).sort((a, b) => b[1].length - a[1].length);
  }, [insights]);

  return (
    <div className="space-y-4">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-violet-400" />
          <h2 className="text-sm font-semibold text-os-text-high">反思引擎日志</h2>
          <span className="text-2xs text-os-muted">conflict detection · merge decision · overwrite history</span>
        </div>
      </div>

      {/* ── 统计磁贴 ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          label="总洞察"
          value={stats.total}
          icon={<Sparkles size={12} />}
          accent="violet"
        />
        <StatCard
          label="高置信度"
          value={stats.highConfidence}
          icon={<Target size={12} />}
          accent="emerald"
          subtitle="confidence ≥ 0.8"
        />
        <StatCard
          label="独立主题"
          value={stats.topics}
          icon={<Brain size={12} />}
          accent="cyan"
        />
        <StatCard
          label="平均置信度"
          value={`${(stats.avgConfidence * 100).toFixed(0)}%`}
          icon={<TrendingUp size={12} />}
          accent={stats.avgConfidence >= 0.7 ? "emerald" : "amber"}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* ── 左侧：洞察列表（按主题分组） ── */}
        <div className="lg:col-span-2 space-y-3">
          <div className="rounded-md border border-os-border bg-os-surface/30 p-4">
            <div className="flex items-center gap-2 mb-3">
              <Lightbulb size={13} className="text-violet-400" />
              <h3 className="text-xs font-semibold text-os-text-high">洞察列表</h3>
              <span className="text-2xs text-os-muted ml-auto">{insights?.length || 0} insights</span>
            </div>

            {isLoading ? (
              <div className="flex items-center justify-center py-8 text-2xs text-os-muted gap-2">
                <Loader2 size={14} className="animate-spin" /> 加载洞察...
              </div>
            ) : !insights || insights.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-2xs text-os-muted">
                <Sparkles size={20} className="mb-2 opacity-50" />
                暂无反思洞察
              </div>
            ) : (
              <div className="space-y-4 max-h-[600px] overflow-y-auto pr-1">
                {groupedByTopic.map(([topic, items]) => (
                  <div key={topic} className="space-y-2">
                    {/* 主题标题 */}
                    <div className="flex items-center gap-2 sticky top-0 bg-os-surface/80 backdrop-blur-sm py-1 z-10">
                      <div className="w-1 h-3 rounded-full bg-violet-400" />
                      <span className="text-xs font-medium text-os-text-high">{topic}</span>
                      <span className="text-2xs text-os-muted">·</span>
                      <span className="text-2xs text-os-muted">{items.length} findings</span>
                    </div>

                    {/* 洞察列表 */}
                    <ul className="space-y-2 pl-3 border-l border-os-border/50">
                      {items.map((insight, idx) => (
                        <motion.li
                          key={insight.id}
                          initial={{ opacity: 0, y: 4 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: Math.min(idx * 0.03, 0.3) }}
                          className="pl-3 relative"
                        >
                          {/* 时间线节点 */}
                          <div className="absolute left-[-5px] top-1.5 w-2 h-2 rounded-full bg-violet-400/60 border border-violet-400/30" />

                          <div className="rounded-md border border-os-border/50 bg-os-base/40 p-2.5">
                            <div className="flex items-start justify-between gap-2 mb-1">
                              <p className="text-xs text-os-text leading-relaxed flex-1">
                                {insight.finding}
                              </p>
                              <ConfidenceBadge confidence={insight.confidence} />
                            </div>
                            <div className="flex items-center gap-2 text-2xs text-os-muted">
                              <span>{formatDate(insight.timestamp)}</span>
                              {insight.related_memories.length > 0 && (
                                <>
                                  <span>·</span>
                                  <span className="flex items-center gap-0.5">
                                    <GitMerge size={9} />
                                    {insight.related_memories.length} related
                                  </span>
                                </>
                              )}
                            </div>
                          </div>
                        </motion.li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── 右侧：反思记忆流 + 冲突解决器 ── */}
        <div className="space-y-3">
          {/* 反思记忆流 */}
          <div className="rounded-md border border-os-border bg-os-surface/30 p-3">
            <div className="flex items-center gap-2 mb-3">
              <Brain size={12} className="text-violet-400" />
              <h3 className="text-2xs font-semibold text-os-text-high">反思记忆流</h3>
            </div>
            {!recentReflections || recentReflections.length === 0 ? (
              <div className="text-2xs text-os-muted py-4 text-center">暂无反思记忆</div>
            ) : (
              <ul className="space-y-2 max-h-[280px] overflow-y-auto pr-1">
                {recentReflections.map((r) => (
                  <li key={r.id} className="rounded border border-os-border/50 bg-os-base/40 p-2">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="text-2xs font-medium text-violet-300 truncate">{r.topic}</span>
                      <span className={cn(
                        "text-2xs font-mono shrink-0",
                        r.importance >= 8 ? "text-emerald-400" : r.importance >= 6 ? "text-amber-400" : "text-zinc-500",
                      )}>
                        {r.importance}
                      </span>
                    </div>
                    <p className="text-2xs text-os-subtle leading-relaxed line-clamp-2 mb-1">
                      {r.finding}
                    </p>
                    <div className="flex items-center gap-1.5 text-2xs text-os-muted">
                      <span>{formatDate(r.timestamp)}</span>
                      {r.entities.length > 0 && (
                        <>
                          <span>·</span>
                          <span className="truncate">{r.entities.slice(0, 2).join(", ")}</span>
                        </>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* 冲突解决器（元数据展示） */}
          <div className="rounded-md border border-violet-400/20 bg-violet-400/[0.02] p-3">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle size={12} className="text-violet-400" />
              <h3 className="text-2xs font-semibold text-os-text-high">冲突解决策略</h3>
            </div>
            <ul className="space-y-1.5 text-2xs text-os-subtle">
              <li className="flex items-start gap-1.5">
                <span className="text-violet-400 mt-0.5">▸</span>
                <span><span className="text-os-text font-medium">冲突检测:</span> 同实体高重要度记忆重复写入时触发</span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-violet-400 mt-0.5">▸</span>
                <span><span className="text-os-text font-medium">合并决策:</span> 保留高 importance 记忆为主体，低 importance 合并入</span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-violet-400 mt-0.5">▸</span>
                <span><span className="text-os-text font-medium">覆盖历史:</span> 合并后 secondary 记忆状态置为 merged，保留可追溯</span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-violet-400 mt-0.5">▸</span>
                <span><span className="text-os-text font-medium">反思触发:</span> 周期性扫描活跃记忆，生成洞察并写入 reflect 类型</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── 子组件 ──

function StatCard({
  label, value, icon, accent, subtitle,
}: {
  label: string;
  value: number | string;
  icon: React.ReactNode;
  accent: "violet" | "emerald" | "amber" | "cyan";
  subtitle?: string;
}) {
  const accentMap = {
    violet: "text-violet-400",
    emerald: "text-emerald-400",
    amber: "text-amber-400",
    cyan: "text-cyan-400",
  };
  return (
    <div className="rounded-md border border-os-border bg-os-surface/30 p-3">
      <div className="flex items-center gap-1.5 text-2xs text-os-muted mb-1">
        <span className={accentMap[accent]}>{icon}</span>
        {label}
      </div>
      <div className={cn("text-lg font-bold tabular-nums", accentMap[accent])}>
        {value}
      </div>
      {subtitle && <div className="text-2xs text-os-muted mt-0.5">{subtitle}</div>}
    </div>
  );
}

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = (confidence * 100).toFixed(0);
  const color = confidence >= 0.8 ? "emerald" : confidence >= 0.6 ? "amber" : "rose";
  const colorMap = {
    emerald: "bg-emerald-400/10 text-emerald-400 border-emerald-400/20",
    amber: "bg-amber-400/10 text-amber-400 border-amber-400/20",
    rose: "bg-rose-400/10 text-rose-400 border-rose-400/20",
  };
  return (
    <span className={cn(
      "shrink-0 px-1.5 py-0.5 rounded text-2xs font-mono border",
      colorMap[color],
    )}>
      {pct}%
    </span>
  );
}
