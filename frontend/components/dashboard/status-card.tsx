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
}

const accentMap = {
  indigo: { bg: "bg-indigo-400/10", text: "text-indigo-400" },
  emerald: { bg: "bg-emerald-400/10", text: "text-emerald-400" },
  amber: { bg: "bg-amber-400/10", text: "text-amber-400" },
  violet: { bg: "bg-violet-400/10", text: "text-violet-400" },
};

export function StatusCard({ icon: Icon, label, value, change, changeLabel, accent }: StatusCardProps) {
  const colors = accentMap[accent];

  return (
    <motion.div
      whileHover={{ y: -1 }}
      className="os-card p-4 flex flex-col gap-2 transition-all os-card-hover"
    >
      <div className="flex items-center justify-between">
        <span className="text-2xs text-os-subtle uppercase tracking-wider">{label}</span>
        <div className={cn("w-7 h-7 rounded-lg flex items-center justify-center", colors.bg)}>
          <Icon size={14} className={colors.text} />
        </div>
      </div>
      <p className="text-xl font-semibold text-os-text-high font-mono tracking-tight">{value}</p>
      {change !== undefined && (
        <div className="flex items-center gap-1">
          {change >= 0 ? (
            <TrendingUp size={12} className="text-emerald-400" />
          ) : (
            <TrendingDown size={12} className="text-red-400" />
          )}
          <span className={cn("text-2xs", change >= 0 ? "text-emerald-400" : "text-red-400")}>
            {change > 0 ? "+" : ""}{change}%
          </span>
          {changeLabel && <span className="text-2xs text-os-muted">{changeLabel}</span>}
        </div>
      )}
    </motion.div>
  );
}
