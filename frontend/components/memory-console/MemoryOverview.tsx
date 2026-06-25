"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Layers, Zap, Brain, Database, Activity, TrendingUp,
  Archive, GitMerge, FileText, Cpu, Sparkles,
} from "lucide-react";
import { cn, formatNumber, formatDate, importanceColor } from "@/lib/utils";
import { api } from "@/services/api";
import type { DashboardSummary } from "@/types";

interface Props {
  summary?: DashboardSummary;
}

// ── 三层记忆推断逻辑 ──
// STM (Short-Term): 近期 active episodic 记忆（context window 模拟）
// WM (Working): 高频访问的 active 记忆（access_count 高）
// LTM (Long-Term): semantic/procedural 或 archived 记忆（持久化知识）
interface TierStats {
  count: number;
  avgImportance: number;
  topItems: Array<{
    id: string;
    content: string;
    importance: number;
    memory_type: string;
    access_count: number;
    timestamp: string;
  }>;
}

const TYPE_LABELS: Record<string, string> = {
  episodic: "情景",
  semantic: "语义",
  procedural: "程序",
  reflect: "反思",
};

const SOURCE_LABELS: Record<string, string> = {
  user: "用户",
  agent: "Agent",
  reflect: "反思",
};

export function MemoryOverview({ summary }: Props) {
  // 拉取记忆列表用于三层推断
  const { data: memories, isLoading } = useQuery({
    queryKey: ["memory-console-list"],
    queryFn: () => api.memory.list({ limit: 200 }),
    refetchInterval: 30000,
  });

  // 拉取向量索引健康度
  const { data: memoryHealth } = useQuery({
    queryKey: ["memory-console-health", 30],
    queryFn: () => api.dashboardV2.memoryHealth(30),
    refetchInterval: 60000,
  });

  // 三层推断
  const tiers = useMemo<{ stm: TierStats; wm: TierStats; ltm: TierStats }>(() => {
    const list = memories || [];
    const now = Date.now();
    const ONE_HOUR = 60 * 60 * 1000;

    // STM: 1小时内的 active episodic
    const stmItems = list
      .filter((m) => {
        if (m.status !== "active" || m.memory_type !== "episodic") return false;
        const age = now - new Date(m.timestamp).getTime();
        return age < ONE_HOUR;
      })
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

    // WM: active 且 access_count >= 3（高频访问的工作集）
    const wmItems = list
      .filter((m) => m.status === "active" && (m.access_count || 0) >= 3 && !stmItems.includes(m))
      .sort((a, b) => (b.access_count || 0) - (a.access_count || 0));

    // LTM: semantic/procedural 或 archived（持久化知识）
    const ltmItems = list
      .filter((m) => {
        if (m.status === "archived") return true;
        return (m.memory_type === "semantic" || m.memory_type === "procedural") && !stmItems.includes(m) && !wmItems.includes(m);
      })
      .sort((a, b) => b.importance - a.importance);

    const calcStats = (items: typeof list): TierStats => ({
      count: items.length,
      avgImportance: items.length > 0 ? items.reduce((s, m) => s + m.importance, 0) / items.length : 0,
      topItems: items.slice(0, 5).map((m) => ({
        id: m.id,
        content: m.content,
        importance: m.importance,
        memory_type: m.memory_type,
        access_count: m.access_count,
        timestamp: m.timestamp,
      })),
    });

    return {
      stm: calcStats(stmItems),
      wm: calcStats(wmItems),
      ltm: calcStats(ltmItems),
    };
  }, [memories]);

  // 向量化状态
  const vectorStats = useMemo(() => {
    const list = memories || [];
    const vectorized = list.filter((m) => m.embedding_status === "vectorized").length;
    const missing = list.filter((m) => m.embedding_status === "missing").length;
    return { vectorized, missing, total: list.length, rate: list.length > 0 ? vectorized / list.length : 0 };
  }, [memories]);

  return (
    <div className="space-y-4">
      {/* ── 三层认知卡片 ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <TierCard
          tier="STM"
          label="短期记忆"
          subtitle="Short-Term Memory"
          description="Context Window 模拟 · 近 1h 情景记忆"
          count={tiers.stm.count}
          avgImportance={tiers.stm.avgImportance}
          accent="cyan"
          icon={<Zap size={14} />}
          items={tiers.stm.topItems}
          isLoading={isLoading}
        />
        <TierCard
          tier="WM"
          label="工作记忆"
          subtitle="Working Memory"
          description="高频访问活跃集 · access_count ≥ 3"
          count={tiers.wm.count}
          avgImportance={tiers.wm.avgImportance}
          accent="violet"
          icon={<Activity size={14} />}
          items={tiers.wm.topItems}
          isLoading={isLoading}
        />
        <TierCard
          tier="LTM"
          label="长期记忆"
          subtitle="Long-Term Memory"
          description="语义/程序知识 · 已归档记忆"
          count={tiers.ltm.count}
          avgImportance={tiers.ltm.avgImportance}
          accent="emerald"
          icon={<Database size={14} />}
          items={tiers.ltm.topItems}
          isLoading={isLoading}
        />
      </div>

      {/* ── 全局统计 + 向量索引 ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 全局记忆统计 */}
        <div className="rounded-md border border-os-border bg-os-surface/30 p-4">
          <div className="flex items-center gap-2 mb-3">
            <Layers size={13} className="text-violet-400" />
            <h3 className="text-xs font-semibold text-os-text-high">全局记忆统计</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatTile label="总记忆" value={summary?.total_memories ?? 0} icon={<Brain size={11} />} />
            <StatTile label="活跃" value={summary?.active_memories ?? 0} icon={<Activity size={11} />} accent="emerald" />
            <StatTile label="已归档" value={summary?.archived_memories ?? 0} icon={<Archive size={11} />} accent="amber" />
            <StatTile label="已合并" value={summary?.merged_memories ?? 0} icon={<GitMerge size={11} />} accent="violet" />
            <StatTile label="情景" value={summary?.episodic_count ?? 0} icon={<Zap size={11} />} />
            <StatTile label="语义" value={summary?.semantic_count ?? 0} icon={<Database size={11} />} />
            <StatTile label="反思" value={summary?.reflect_count ?? 0} icon={<Sparkles size={11} />} />
            <StatTile label="周增长" value={summary?.weekly_growth ?? 0} icon={<TrendingUp size={11} />} accent="emerald" />
          </div>
        </div>

        {/* 向量索引健康度 */}
        <div className="rounded-md border border-os-border bg-os-surface/30 p-4">
          <div className="flex items-center gap-2 mb-3">
            <Cpu size={13} className="text-violet-400" />
            <h3 className="text-xs font-semibold text-os-text-high">向量索引健康度</h3>
            {memoryHealth && (
              <span className="ml-auto text-2xs text-os-muted font-mono">
                hit_rate: {(memoryHealth.hit_rate * 100).toFixed(1)}%
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <StatTile label="总向量" value={vectorStats.total} icon={<Database size={11} />} />
            <StatTile label="已索引" value={vectorStats.vectorized} icon={<Cpu size={11} />} accent="emerald" />
            <StatTile label="缺失" value={vectorStats.missing} icon={<FileText size={11} />} accent={vectorStats.missing > 0 ? "rose" : "zinc"} />
            <StatTile label="覆盖率" value={`${(vectorStats.rate * 100).toFixed(0)}%`} icon={<TrendingUp size={11} />} accent={vectorStats.rate > 0.9 ? "emerald" : "amber"} />
          </div>
          {/* 覆盖率进度条 */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-2xs text-os-muted">
              <span>向量覆盖率</span>
              <span className="font-mono">{(vectorStats.rate * 100).toFixed(1)}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-os-elevated overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${vectorStats.rate * 100}%` }}
                transition={{ duration: 0.6, ease: "easeOut" }}
                className={cn(
                  "h-full rounded-full",
                  vectorStats.rate > 0.9 ? "bg-emerald-400" : vectorStats.rate > 0.5 ? "bg-amber-400" : "bg-rose-400",
                )}
              />
            </div>
          </div>
          {/* 类型分布 */}
          {memoryHealth?.type_distribution && memoryHealth.type_distribution.length > 0 && (
            <div className="mt-3 pt-3 border-t border-os-border/50">
              <div className="text-2xs text-os-muted mb-2">类型分布</div>
              <div className="flex flex-wrap gap-1.5">
                {memoryHealth.type_distribution.map((t) => (
                  <span key={t.memory_type} className="text-2xs px-2 py-0.5 rounded bg-os-elevated text-os-subtle font-mono">
                    {TYPE_LABELS[t.memory_type] || t.memory_type}: {t.count}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── 三层卡片 ──

const ACCENT_MAP = {
  cyan: {
    border: "border-cyan-400/20",
    bg: "bg-cyan-400/[0.02]",
    text: "text-cyan-400",
    bar: "bg-cyan-400",
    chip: "bg-cyan-400/10 text-cyan-400",
  },
  violet: {
    border: "border-violet-400/20",
    bg: "bg-violet-400/[0.02]",
    text: "text-violet-400",
    bar: "bg-violet-400",
    chip: "bg-violet-400/10 text-violet-400",
  },
  emerald: {
    border: "border-emerald-400/20",
    bg: "bg-emerald-400/[0.02]",
    text: "text-emerald-400",
    bar: "bg-emerald-400",
    chip: "bg-emerald-400/10 text-emerald-400",
  },
} as const;

function TierCard({
  tier, label, subtitle, description, count, avgImportance, accent, icon, items, isLoading,
}: {
  tier: string;
  label: string;
  subtitle: string;
  description: string;
  count: number;
  avgImportance: number;
  accent: keyof typeof ACCENT_MAP;
  icon: React.ReactNode;
  items: TierStats["topItems"];
  isLoading: boolean;
}) {
  const a = ACCENT_MAP[accent];
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("rounded-md border p-4 space-y-3", a.border, a.bg)}
    >
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-1.5">
            <span className={a.text}>{icon}</span>
            <span className={cn("text-xs font-bold tracking-wider", a.text)}>{tier}</span>
            <span className="text-xs font-medium text-os-text-high">{label}</span>
          </div>
          <div className="text-2xs text-os-muted mt-0.5">{subtitle}</div>
        </div>
        <div className="text-right">
          <div className={cn("text-xl font-bold tabular-nums", a.text)}>{count}</div>
          <div className="text-2xs text-os-muted">items</div>
        </div>
      </div>

      {/* Description */}
      <p className="text-2xs text-os-subtle leading-relaxed">{description}</p>

      {/* Avg importance bar */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-2xs text-os-muted">
          <span>平均重要度</span>
          <span className="font-mono">{avgImportance.toFixed(1)}</span>
        </div>
        <div className="h-1 rounded-full bg-os-elevated overflow-hidden">
          <div
            className={cn("h-full rounded-full", a.bar)}
            style={{ width: `${(avgImportance / 10) * 100}%` }}
          />
        </div>
      </div>

      {/* Top items */}
      <div className="space-y-1.5">
        <div className="text-2xs text-os-muted uppercase tracking-wider">Top 5</div>
        {isLoading ? (
          <div className="text-2xs text-os-muted py-2">加载中...</div>
        ) : items.length === 0 ? (
          <div className="text-2xs text-os-muted py-2">暂无数据</div>
        ) : (
          <ul className="space-y-1">
            {items.map((item) => (
              <li key={item.id} className="flex items-start gap-2 text-2xs">
                <span className={cn("shrink-0 px-1 py-0.5 rounded font-mono", a.chip)}>
                  {TYPE_LABELS[item.memory_type] || item.memory_type}
                </span>
                <span className="text-os-subtle truncate flex-1" title={item.content}>
                  {item.content}
                </span>
                <span className={cn("shrink-0 font-mono", importanceColor(item.importance))}>
                  {item.importance}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </motion.div>
  );
}

// ── 统计磁贴 ──

function StatTile({
  label, value, icon, accent = "zinc",
}: {
  label: string;
  value: number | string;
  icon: React.ReactNode;
  accent?: "zinc" | "emerald" | "amber" | "rose" | "violet";
}) {
  const accentMap = {
    zinc: "text-os-subtle",
    emerald: "text-emerald-400",
    amber: "text-amber-400",
    rose: "text-rose-400",
    violet: "text-violet-400",
  };
  return (
    <div className="rounded-md border border-os-border/50 bg-os-base/50 p-2.5">
      <div className="flex items-center gap-1 text-2xs text-os-muted mb-1">
        <span className={accentMap[accent]}>{icon}</span>
        {label}
      </div>
      <div className={cn("text-lg font-bold tabular-nums", accentMap[accent])}>
        {typeof value === "number" ? formatNumber(value) : value}
      </div>
    </div>
  );
}
