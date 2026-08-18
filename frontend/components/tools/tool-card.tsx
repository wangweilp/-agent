"use client";

import { motion } from "framer-motion";
import { Wrench, Shield, AlertTriangle, CheckCircle2, ToggleLeft, ToggleRight } from "lucide-react";
import { cn, formatMs } from "@/lib/utils";
import type { ToolInfo } from "@/types";

const riskStyle: Record<string, { icon: React.ElementType; color: string; label: string }> = {
  low: { icon: CheckCircle2, color: "bg-emerald-400/10 text-emerald-700", label: "低风险" },
  medium: { icon: AlertTriangle, color: "bg-amber-400/10 text-amber-800", label: "中风险" },
  high: { icon: Shield, color: "bg-red-400/10 text-red-700", label: "高风险" },
};

export function ToolCard({ tool }: { tool: ToolInfo }) {
  const risk = riskStyle[tool.risk_level] || {
    icon: AlertTriangle,
    color: "bg-zinc-500/10 text-os-subtle",
    label: `未知风险（${tool.risk_level}）`,
  };
  const RiskIcon = risk.icon;

  return (
    <motion.div
      whileHover={{ y: -1 }}
      className="os-card p-5 os-card-hover"
    >
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg", tool.enabled ? "bg-os-accent/10" : "bg-zinc-500/5")}>
            <Wrench size={18} className={tool.enabled ? "text-os-accent" : "text-os-subtle"} />
          </div>
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <h3 className="min-w-0 truncate font-mono text-sm font-semibold text-os-text-high" title={tool.name}>
                {tool.name}
              </h3>
              <span className={cn("os-badge shrink-0", risk.color)}>
                <RiskIcon size={10} />
                {risk.label}
              </span>
            </div>
            <p className="mt-0.5 truncate text-2xs text-os-subtle" title={tool.category}>{tool.category}</p>
          </div>
        </div>
        <button
          type="button"
          className="shrink-0 text-os-subtle transition-colors hover:text-os-text"
          aria-label={tool.enabled ? "停用工具" : "启用工具"}
        >
          {tool.enabled ? <ToggleRight size={22} className="text-os-accent" /> : <ToggleLeft size={22} />}
        </button>
      </div>

      <p className="mb-4 break-words text-xs leading-relaxed text-os-text">{tool.description}</p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-3 border-t border-os-border">
        <div className="text-center">
          <p className="text-lg font-semibold text-os-text-high font-mono">{tool.call_count}</p>
          <p className="text-2xs text-os-subtle">调用次数</p>
        </div>
        <div className="text-center">
          <p className="text-lg font-semibold text-os-text-high font-mono">{formatMs(tool.avg_duration_ms)}</p>
          <p className="text-2xs text-os-subtle">平均耗时</p>
        </div>
        <div className="text-center">
          <p className="text-lg font-semibold text-os-text-high font-mono">{Math.round(tool.success_rate * 100)}%</p>
          <p className="text-2xs text-os-subtle">成功率</p>
        </div>
      </div>

      {tool.requires_confirmation && (
        <div className="flex items-center gap-1.5 mt-3 p-2 rounded-md bg-red-400/5 border border-red-400/10">
          <Shield size={12} className="text-red-700" />
          <span className="text-2xs text-red-700">需要用户确认才能执行</span>
        </div>
      )}
    </motion.div>
  );
}
