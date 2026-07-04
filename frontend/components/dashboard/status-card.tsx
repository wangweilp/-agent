"use client";

import { TrendingDown, TrendingUp } from "lucide-react";
import { MetricCard } from "@/components/ui/os";
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
  indigo: "primary",
  emerald: "success",
  amber: "warning",
  violet: "info",
} as const;

export function StatusCard({ icon, label, value, change, changeLabel, accent, isLoading }: StatusCardProps) {
  const trend =
    change !== undefined ? (
      <span className={cn("inline-flex items-center gap-1", change >= 0 ? "text-os-success" : "text-os-danger")}>
        {change >= 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
        {change > 0 ? "+" : ""}
        {change}% {changeLabel}
      </span>
    ) : undefined;

  return (
    <MetricCard
      icon={icon}
      label={label}
      value={isLoading ? "..." : value}
      trend={trend}
      detail={changeLabel && change === undefined ? changeLabel : undefined}
      accent={accentMap[accent]}
    />
  );
}
