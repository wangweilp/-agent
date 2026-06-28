"use client";

import { motion } from "framer-motion";
import { TrendingUp, TrendingDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ElementType } from "react";

type Accent = "indigo" | "emerald" | "amber" | "violet" | "cyan" | "rose";

const accentMap: Record<Accent, { bg: string; text: string }> = {
  indigo: { bg: "bg-indigo-400/10", text: "text-indigo-400" },
  emerald: { bg: "bg-emerald-400/10", text: "text-emerald-400" },
  amber: { bg: "bg-amber-400/10", text: "text-amber-400" },
  violet: { bg: "bg-violet-400/10", text: "text-violet-400" },
  cyan: { bg: "bg-cyan-400/10", text: "text-cyan-400" },
  rose: { bg: "bg-rose-400/10", text: "text-rose-400" },
};

interface KpiCardProps {
  icon: ElementType;
  label: string;
  value: string;
  sub?: string;
  accent?: Accent;
  change?: number;
  isLoading?: boolean;
}

// KPI 卡 — 复用 StatusCard 视觉语言，扩展 sub/cyan/rose。
export function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
  accent = "indigo",
  change,
  isLoading,
}: KpiCardProps) {
  // 骨架屏：模拟标题块 + 巨大数字块 + 子文案块的布局
  if (isLoading) {
    return (
      <div className="os-card p-6 rounded-xl flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div className="h-4 w-20 rounded bg-os-border/50 animate-pulse" />
          <div className="h-8 w-8 rounded-lg bg-os-border/50 animate-pulse" />
        </div>
        <div className="h-8 w-32 rounded bg-os-border/50 animate-pulse" />
        <div className="h-4 w-full rounded bg-os-border/30 animate-pulse" />
      </div>
    );
  }

  const c = accentMap[accent];
  return (
    <motion.div
      whileHover={{ y: -2 }}
      className="os-card p-6 rounded-xl flex flex-col gap-4 hover:border-os-accent/50 transition-colors"
    >
      <div className="flex items-center justify-between">
        <span className="text-sm text-os-muted uppercase tracking-wider">{label}</span>
        <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center", c.bg)}>
          <Icon size={15} className={c.text} />
        </div>
      </div>
      <p className="text-2xl font-semibold text-os-text-high font-mono tracking-tight">{value}</p>
      <div className="flex items-center gap-2 min-h-[18px]">
        {change !== undefined && (
          <span className={cn("flex items-center gap-1 text-xs", change >= 0 ? "text-emerald-400" : "text-rose-400")}>
            {change >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
            {change > 0 ? "+" : ""}
            {change}%
          </span>
        )}
        {sub && <span className="text-xs text-os-subtle truncate">{sub}</span>}
      </div>
    </motion.div>
  );
}
