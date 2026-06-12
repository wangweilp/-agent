"use client";

import { cn } from "@/lib/utils";
import { BadgeCheck, Coins, DollarSign, Repeat } from "lucide-react";

interface AgentPricingBadgeProps {
  model: string;
  className?: string;
}

const PRICING_CONFIG: Record<string, { label: string; icon: typeof BadgeCheck; color: string }> = {
  free: { label: "免费", icon: BadgeCheck, color: "bg-emerald-400/10 text-emerald-300 border-emerald-400/20" },
  per_use: { label: "按次计费", icon: Coins, color: "bg-amber-400/10 text-amber-300 border-amber-400/20" },
  per_seat: { label: "按人计费", icon: DollarSign, color: "bg-violet-400/10 text-violet-300 border-violet-400/20" },
  subscription: { label: "订阅", icon: Repeat, color: "bg-blue-400/10 text-blue-300 border-blue-400/20" },
};

export function AgentPricingBadge({ model, className }: AgentPricingBadgeProps) {
  const config = PRICING_CONFIG[model] || { label: model, icon: BadgeCheck, color: "bg-zinc-500/10 text-os-subtle border-os-border" };
  const Icon = config.icon;

  return (
    <span className={cn("os-badge inline-flex items-center gap-1 border", config.color, className)}>
      <Icon size={12} />
      {config.label}
    </span>
  );
}
