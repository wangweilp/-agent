"use client";

import { motion } from "framer-motion";
import {
  Brain,
  Wrench,
  Lightbulb,
  MessageSquare,
  Database,
  AlertTriangle,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { zhCN } from "date-fns/locale";
import { cn, formatMs } from "@/lib/utils";
import type { TraceEntry } from "@/types";

const typeIcons: Record<string, React.ElementType> = {
  llm_call: MessageSquare,
  tool_call: Wrench,
  reflection: Lightbulb,
  memory_write: Database,
  memory_read: Brain,
};

// Trace 类型标识色 — 左侧时间线圆点
const typeDotColor: Record<string, string> = {
  llm_call: "bg-os-accent shadow-[0_0_6px_rgba(129,140,248,0.6)]",
  tool_call: "bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.6)]",
  reflection: "bg-os-accent-violet shadow-[0_0_6px_rgba(167,139,250,0.6)]",
  memory_write: "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.6)]",
  memory_read: "bg-os-accent-cyan shadow-[0_0_6px_rgba(34,211,238,0.6)]",
};

const typeLabel: Record<string, string> = {
  llm_call: "LLM_CALL",
  tool_call: "TOOL_CALL",
  reflection: "REFLECT",
  memory_write: "MEM_WRITE",
  memory_read: "MEM_READ",
};

// ── 瀑布流衍生指标计算 ──
// 后端 TraceEntry 暂未提供 tokens/cost 字段，
// 此处使用合理的 Mock 公式补齐 UI 骨架（cost = (tokens / 1000) * 0.002）

interface WaterfallMetrics {
  latencyMs: number;
  tokensIn: number;
  tokensOut: number;
  costUsd: number;
  isHighLatency: boolean;
  isFailed: boolean;
  barWidthPct: number; // 瀑布流横向条宽度（相对最大 latency）
}

function computeMetrics(trace: TraceEntry, maxLatency: number): WaterfallMetrics {
  const latencyMs = trace.duration_ms;

  // 基于 trace 类型和耗时合理 Mock tokens（确定性，避免每次渲染抖动）
  const seed = trace.id.length + latencyMs;
  const baseTokens: Record<string, { in: number; out: number }> = {
    llm_call: { in: 320 + (seed % 480), out: 180 + (seed % 320) },
    tool_call: { in: 80 + (seed % 120), out: 60 + (seed % 90) },
    reflection: { in: 240 + (seed % 360), out: 120 + (seed % 240) },
    memory_write: { in: 32 + (seed % 48), out: 0 },
    memory_read: { in: 16 + (seed % 24), out: 0 },
  };
  const t = baseTokens[trace.type] ?? { in: 100, out: 50 };
  const tokensIn = t.in;
  const tokensOut = t.out;
  const totalTokens = tokensIn + tokensOut;

  // cost = (tokens / 1000) * 0.002  (USD)
  const costUsd = (totalTokens / 1000) * 0.002;

  const isHighLatency = latencyMs > 2000;
  const isFailed = trace.status === "failed";
  const barWidthPct = maxLatency > 0 ? Math.max(4, (latencyMs / maxLatency) * 100) : 4;

  return { latencyMs, tokensIn, tokensOut, costUsd, isHighLatency, isFailed, barWidthPct };
}

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return n.toString();
}

function formatCost(usd: number): string {
  if (usd === 0) return "$0";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(3)}`;
}

// ── 瀑布流单条节点 ──

function WaterfallNode({
  trace,
  metrics,
  index,
}: {
  trace: TraceEntry;
  metrics: WaterfallMetrics;
  index: number;
}) {
  const Icon = typeIcons[trace.type] || MessageSquare;
  const dotColor = typeDotColor[trace.type] || "bg-os-accent shadow-[0_0_6px_rgba(129,140,248,0.6)]";
  const label = typeLabel[trace.type] || trace.type.toUpperCase();
  const isRunning = trace.status === "running";

  return (
    <motion.div
      initial={{ opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: Math.min(index * 0.02, 0.3) }}
      className={cn(
        "relative rounded-md border transition-colors group",
        // 失败：整张卡片边缘透出 os-danger
        metrics.isFailed
          ? "border-os-danger/60 bg-os-danger/[0.04] shadow-[0_0_12px_rgba(248,113,113,0.08)]"
          : "border-os-border/40 bg-os-elevated/40 hover:bg-os-elevated/70"
      )}
    >
      {/* 左侧类型色条 */}
      <div className={cn("absolute left-0 top-0 bottom-0 w-0.5 rounded-l-md", dotColor.split(" ")[0])} />

      <div className="flex items-stretch gap-3 py-2 pl-3 pr-3">
        {/* ── 左：节点标识 + 时间轴圆点 ── */}
        <div className="flex shrink-0 items-center gap-2 w-[140px]">
          <div className={cn("w-2 h-2 rounded-full ring-2 ring-os-surface shrink-0", dotColor)} />
          <Icon
            size={13}
            className={cn(
              "shrink-0",
              metrics.isFailed
                ? "text-os-danger"
                : isRunning
                  ? "text-os-accent animate-pulse"
                  : "text-os-subtle"
            )}
          />
          <span className="text-2xs font-mono font-semibold text-os-text tracking-wider truncate">
            {label}
          </span>
        </div>

        {/* ── 中：瀑布流条 + 详情 ── */}
        <div className="flex-1 min-w-0 flex flex-col gap-1 justify-center">
          {/* 瀑布流条 */}
          <div className="relative h-5 w-full bg-os-base/60 rounded overflow-hidden">
            <div
              className={cn(
                "absolute left-0 top-0 bottom-0 rounded transition-all duration-300",
                metrics.isFailed
                  ? "bg-os-danger/40"
                  : metrics.isHighLatency
                    ? "bg-os-warning/40"
                    : "bg-os-accent/40"
              )}
              style={{ width: `${metrics.barWidthPct}%` }}
            >
              {/* 内部高光线 */}
              <div
                className={cn(
                  "absolute left-0 top-0 h-px w-full",
                  metrics.isFailed
                    ? "bg-os-danger"
                    : metrics.isHighLatency
                      ? "bg-os-warning"
                      : "bg-os-accent"
                )}
              />
            </div>
            {/* 条上叠加节点名 */}
            <span className="absolute left-2 top-1/2 -translate-y-1/2 text-2xs font-mono text-os-text truncate max-w-[60%]">
              {trace.step}
            </span>
          </div>
          {/* 详情行 */}
          <p className="text-2xs text-os-muted truncate" title={trace.detail}>
            {trace.detail || "—"}
          </p>
        </div>

        {/* ── 右：硬核指标（Latency / Tokens / Cost） ── */}
        <div className="flex shrink-0 items-center gap-3 font-mono text-2xs">
          {/* Latency */}
          <div className="flex flex-col items-end w-[64px]">
            <span className="text-os-subtle">latency</span>
            <span
              className={cn(
                "tabular-nums font-semibold",
                metrics.isFailed
                  ? "text-os-danger"
                  : metrics.isHighLatency
                    ? "text-os-warning"
                    : "text-os-text-high"
              )}
            >
              {metrics.latencyMs}ms
            </span>
          </div>

          {/* Tokens In/Out */}
          <div className="flex flex-col items-end w-[88px]">
            <span className="text-os-subtle">tokens</span>
            <span className="tabular-nums text-os-accent-cyan">
              <span className="text-os-text">in</span>{" "}
              {formatTokens(metrics.tokensIn)}
              <span className="text-os-border mx-0.5">/</span>
              <span className="text-os-text">out</span>{" "}
              {formatTokens(metrics.tokensOut)}
            </span>
          </div>

          {/* Cost */}
          <div className="flex flex-col items-end w-[56px]">
            <span className="text-os-subtle">cost</span>
            <span className="tabular-nums text-emerald-400">{formatCost(metrics.costUsd)}</span>
          </div>

          {/* 状态徽章 */}
          <div className="flex items-center w-[44px] justify-end">
            {metrics.isFailed ? (
              <span className="inline-flex items-center gap-0.5 rounded bg-os-danger/15 px-1.5 py-0.5 text-2xs font-bold text-os-danger border border-os-danger/30">
                <AlertTriangle className="h-2.5 w-2.5" />
                FAIL
              </span>
            ) : isRunning ? (
              <span className="inline-flex items-center gap-0.5 rounded bg-os-accent/15 px-1.5 py-0.5 text-2xs font-semibold text-os-accent border border-os-accent/30">
                <Loader2 className="h-2.5 w-2.5 animate-spin" />
                RUN
              </span>
            ) : (
              <CheckCircle2 className="h-3 w-3 text-emerald-400/60" />
            )}
          </div>
        </div>
      </div>

      {/* 悬停时显示相对时间 */}
      <span className="absolute right-2 -top-2 text-2xs font-mono text-os-subtle opacity-0 group-hover:opacity-100 transition-opacity bg-os-surface px-1 rounded">
        {formatDistanceToNow(new Date(trace.timestamp), { addSuffix: true, locale: zhCN })}
      </span>
    </motion.div>
  );
}

// ── 瀑布流表头（极简指标列说明） ──

function WaterfallHeader() {
  return (
    <div className="flex items-center gap-3 py-1.5 pl-3 pr-3 text-2xs font-mono uppercase tracking-wider text-os-subtle border-b border-os-border/40">
      <div className="shrink-0 w-[140px]">node</div>
      <div className="flex-1">waterfall</div>
      <div className="shrink-0 flex items-center gap-3">
        <span className="w-[64px] text-right">latency</span>
        <span className="w-[88px] text-right">tokens</span>
        <span className="w-[56px] text-right">cost</span>
        <span className="w-[44px] text-right">state</span>
      </div>
    </div>
  );
}

export function TraceTimeline({ traces }: { traces: TraceEntry[] }) {
  if (traces.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-xs text-os-muted">暂无 Trace 数据，启动智能体对话后将自动记录</p>
      </div>
    );
  }

  // 取最近 20 条，倒序（最新在顶部）
  const recent = traces.slice(-20).reverse();
  const maxLatency = Math.max(...recent.map((t) => t.duration_ms), 1);

  return (
    <div className="relative">
      {/* 移动端横向滚动容器 —— WaterfallNode 行内含 w-[140px]/w-[88px]/w-[64px]/w-[56px]/w-[44px] 固定列宽，375px 会溢出 */}
      <div className="overflow-x-auto -mx-1 px-1">
        <div className="min-w-[640px]">
          <WaterfallHeader />
          <div className="space-y-1 pt-1">
            {recent.map((trace, i) => {
              const metrics = computeMetrics(trace, maxLatency);
              return (
                <WaterfallNode
                  key={trace.id}
                  trace={trace}
                  metrics={metrics}
                  index={i}
                />
              );
            })}
          </div>
        </div>
      </div>

      {/* 瀑布流尾部统计 */}
      <div className="mt-2 pt-2 border-t border-os-border/40 flex items-center justify-between text-2xs font-mono text-os-subtle">
        <span>
          <span className="text-os-text">{recent.length}</span> spans
        </span>
        <span>
          max latency:{" "}
          <span className={cn(maxLatency > 2000 ? "text-os-warning" : "text-os-text-high")}>
            {formatMs(maxLatency)}
          </span>
        </span>
      </div>
    </div>
  );
}
