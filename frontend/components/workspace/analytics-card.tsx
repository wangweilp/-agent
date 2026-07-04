"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import type { ElementType, ReactNode } from "react";

interface AnalyticsCardProps {
  icon?: ElementType;
  label: string;
  value: string | number;
  subValue?: string;
  accent?: "indigo" | "emerald" | "amber" | "violet" | "rose" | "cyan";
  children?: ReactNode;
  className?: string;
}

const accentMap: Record<string, { bg: string; text: string; border: string }> = {
  indigo:  { bg: "bg-indigo-400/10", text: "text-indigo-400", border: "border-indigo-400/20" },
  emerald: { bg: "bg-emerald-400/10", text: "text-emerald-400", border: "border-emerald-400/20" },
  amber:   { bg: "bg-amber-400/10", text: "text-amber-400", border: "border-amber-400/20" },
  violet:  { bg: "bg-violet-400/10", text: "text-violet-400", border: "border-violet-400/20" },
  rose:    { bg: "bg-rose-400/10", text: "text-rose-400", border: "border-rose-400/20" },
  cyan:    { bg: "bg-cyan-400/10", text: "text-cyan-400", border: "border-cyan-400/20" },
};

/** 可复用分析统计卡片 — 用于团队面板各指标展示。 */
export function AnalyticsCard({
  icon: Icon,
  label,
  value,
  subValue,
  accent = "indigo",
  children,
  className,
}: AnalyticsCardProps) {
  const colors = accentMap[accent] ?? accentMap.indigo;

  return (
    <motion.div
      whileHover={{ y: -1 }}
      className={cn(
        "os-card flex flex-col gap-2 p-4 transition-all os-card-hover border-l-2",
        colors.border,
        className,
      )}
    >
      {/* Header row */}
      <div className="flex items-center justify-between">
        <span className="text-2xs text-os-subtle uppercase tracking-wider">
          {label}
        </span>
        {Icon && (
          <div
            className={cn(
              "flex h-7 w-7 items-center justify-center rounded-lg",
              colors.bg,
            )}
          >
            <Icon size={14} className={colors.text} />
          </div>
        )}
      </div>

      {/* Value */}
      <p className="font-mono text-xl font-semibold tracking-tight text-os-text-high">
        {value}
      </p>

      {/* Sub-value */}
      {subValue && (
        <span className="text-2xs text-os-muted">{subValue}</span>
      )}

      {/* Optional detail slot */}
      {children && (
        <div className="mt-1 border-t border-os-border/70 pt-2">{children}</div>
      )}
    </motion.div>
  );
}

/** 迷你进度条 — 用于 action_completion_rate / media 占比等。 */
export function MiniProgressBar({
  label,
  percent,
  accent = "indigo",
}: {
  label: string;
  percent: number; // 0-100
  accent?: string;
}) {
  const colors = accentMap[accent] ?? accentMap.indigo;

  return (
    <div className="flex items-center gap-2 text-2xs">
      <span className="w-10 text-os-muted">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-os-elevated">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(percent, 100)}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className={cn("h-full rounded-full", colors.bg)}
        />
      </div>
      <span className="w-8 text-right text-os-subtle tabular-nums">
        {percent.toFixed(0)}%
      </span>
    </div>
  );
}
