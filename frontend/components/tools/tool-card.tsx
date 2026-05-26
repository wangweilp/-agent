"use client";

import { motion } from "framer-motion";
import { Wrench, Shield, AlertTriangle, CheckCircle2, ToggleLeft, ToggleRight, Clock, Zap } from "lucide-react";
import { cn, formatMs } from "@/lib/utils";
import type { ToolInfo } from "@/types";

const riskStyle: Record<string, { icon: React.ElementType; color: string; label: string }> = {
  low: { icon: CheckCircle2, color: "text-emerald-400", label: "低风险" },
  medium: { icon: AlertTriangle, color: "text-amber-400", label: "中风险" },
  high: { icon: Shield, color: "text-red-400", label: "高风险" },
};

export function ToolCard({ tool }: { tool: ToolInfo }) {
  const risk = riskStyle[tool.risk_level] || riskStyle.low;
  const RiskIcon = risk.icon;

  return (
    <motion.div
      whileHover={{ y: -1 }}
      className="os-card p-5 os-card-hover"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center", tool.enabled ? "bg-os-accent/10" : "bg-zinc-500/5")}>
            <Wrench size={18} className={tool.enabled ? "text-os-accent" : "text-os-muted"} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-os-text-high font-mono">{tool.name}</h3>
              <span className={cn("os-badge", risk.color.replace("text-", "bg-").replace("400", "400/10"), risk.color)}>
                <RiskIcon size={10} />
                {risk.label}
              </span>
            </div>
            <p className="text-2xs text-os-subtle mt-0.5">{tool.category}</p>
          </div>
        </div>
        <button className="text-os-subtle hover:text-os-text transition-colors">
          {tool.enabled ? <ToggleRight size={22} className="text-os-accent" /> : <ToggleLeft size={22} />}
        </button>
      </div>

      <p className="text-xs text-os-text leading-relaxed mb-4">{tool.description}</p>

      <div className="grid grid-cols-3 gap-3 pt-3 border-t border-os-border">
        <div className="text-center">
          <p className="text-lg font-semibold text-os-text-high font-mono">{tool.call_count}</p>
          <p className="text-2xs text-os-muted">调用次数</p>
        </div>
        <div className="text-center">
          <p className="text-lg font-semibold text-os-text-high font-mono">{formatMs(tool.avg_duration_ms)}</p>
          <p className="text-2xs text-os-muted">平均耗时</p>
        </div>
        <div className="text-center">
          <p className="text-lg font-semibold text-os-text-high font-mono">{Math.round(tool.success_rate * 100)}%</p>
          <p className="text-2xs text-os-muted">成功率</p>
        </div>
      </div>

      {tool.requires_confirmation && (
        <div className="flex items-center gap-1.5 mt-3 p-2 rounded-md bg-red-400/5 border border-red-400/10">
          <Shield size={12} className="text-red-400" />
          <span className="text-2xs text-red-400">需要用户确认才能执行</span>
        </div>
      )}
    </motion.div>
  );
}
