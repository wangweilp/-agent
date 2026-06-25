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
}

// KPI 卡 — 复用 StatusCard 视觉语言，扩展 sub/cyan/rose。
export function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
  accent = "indigo",
  change,
}: KpiCardProps) {
  const c = accentMap[accent];
  return (
    <motion.div
      whileHover={{ y: -1 }}
      className="os-card p-4 flex flex-col gap-2 os-card-hover"
    >
      <div className="flex items-center justify-between">
        <span className="text-2xs text-os-subtle uppercase tracking-wider">{label}</span>
        <div className={cn("w-7 h-7 rounded-lg flex items-center justify-center", c.bg)}>
          <Icon size={14} className={c.text} />
        </div>
      </div>
      <p className="text-xl font-semibold text-os-text-high font-mono tracking-tight">{value}</p>
      <div className="flex items-center gap-1.5 min-h-[14px]">
        {change !== undefined && (
          <span className={cn("flex items-center gap-0.5 text-2xs", change >= 0 ? "text-emerald-400" : "text-rose-400")}>
            {change >= 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
            {change > 0 ? "+" : ""}
            {change}%
          </span>
        )}
        {sub && <span className="text-2xs text-os-muted truncate">{sub}</span>}
      </div>
    </motion.div>
  );
}
