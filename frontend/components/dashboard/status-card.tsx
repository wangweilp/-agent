"use client";

import { motion } from "framer-motion";
import { TrendingUp, TrendingDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ElementType } from "react";

interface StatusCardProps {
  icon: ElementType;
  label: string;
  value: string;
  change?: number;
  changeLabel?: string;
  accent: "indigo" | "emerald" | "amber" | "violet";
  isLoading?: boolean;
}

const accentMap = {
  indigo: { bg: "bg-indigo-400/10", text: "text-indigo-400" },
  emerald: { bg: "bg-emerald-400/10", text: "text-emerald-400" },
  amber: { bg: "bg-amber-400/10", text: "text-amber-400" },
  violet: { bg: "bg-violet-400/10", text: "text-violet-400" },
};

export function StatusCard({ icon: Icon, label, value, change, changeLabel, accent, isLoading }: StatusCardProps) {
  // 骨架屏：模拟标题块 + 巨大数字块 + 变化趋势块
  if (isLoading) {
    return (
      <div className="os-card p-6 rounded-xl flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div className="h-4 w-20 rounded bg-os-border/50 animate-pulse" />
          <div className="h-8 w-8 rounded-lg bg-os-border/50 animate-pulse" />
        </div>
        <div className="h-8 w-32 rounded bg-os-border/50 animate-pulse" />
        <div className="h-4 w-24 rounded bg-os-border/30 animate-pulse" />
      </div>
    );
  }

  const colors = accentMap[accent];

  return (
    <motion.div
      whileHover={{ y: -2 }}
      className="os-card p-6 rounded-xl flex flex-col gap-4 hover:border-os-accent/50 transition-colors"
    >
      <div className="flex items-center justify-between">
        <span className="text-sm text-os-muted uppercase tracking-wider">{label}</span>
        <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center", colors.bg)}>
          <Icon size={15} className={colors.text} />
        </div>
      </div>
      <p className="text-2xl font-semibold text-os-text-high font-mono tracking-tight">{value}</p>
      {change !== undefined && (
        <div className="flex items-center gap-1.5">
          {change >= 0 ? (
            <TrendingUp size={13} className="text-emerald-400" />
          ) : (
            <TrendingDown size={13} className="text-red-400" />
          )}
          <span className={cn("text-xs", change >= 0 ? "text-emerald-400" : "text-red-400")}>
            {change > 0 ? "+" : ""}{change}%
          </span>
          {changeLabel && <span className="text-xs text-os-muted">{changeLabel}</span>}
        </div>
      )}
    </motion.div>
  );
}
