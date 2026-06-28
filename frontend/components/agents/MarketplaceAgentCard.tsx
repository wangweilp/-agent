"use client";

import {
  ArrowDownToLine,
  Bot,
  CheckCircle2,
  ExternalLink,
  Loader2,
  Star,
  User,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { MarketplaceAgent } from "@/types/marketplace";

interface MarketplaceAgentCardProps {
  agent: MarketplaceAgent;
  installed?: boolean;
  busy?: boolean;
  onInstall?: (marketplaceAgentId: string) => void;
  onDetail?: (marketplaceAgentId: string) => void;
}

function pricingLabel(model: string): string {
  const map: Record<string, string> = {
    free: "免费",
    per_use: "按次计费",
    per_seat: "按人计费",
    subscription: "订阅",
  };
  return map[model] || model;
}

function pricingColor(model: string): string {
  if (model === "free") return "bg-emerald-400/10 text-emerald-300";
  if (model === "per_use") return "bg-amber-400/10 text-amber-300";
  return "bg-violet-400/10 text-violet-300";
}

function categoryColor(category: string): string {
  const map: Record<string, string> = {
    automation: "bg-blue-400/10 text-blue-300",
    assistant: "bg-cyan-400/10 text-cyan-300",
    knowledge: "bg-emerald-400/10 text-emerald-300",
    training: "bg-violet-400/10 text-violet-300",
    sales: "bg-amber-400/10 text-amber-300",
    support: "bg-rose-400/10 text-rose-300",
    engineering: "bg-indigo-400/10 text-indigo-300",
    hr: "bg-pink-400/10 text-pink-300",
    analytics: "bg-orange-400/10 text-orange-300",
  };
  return map[category] || "bg-zinc-400/10 text-zinc-300";
}

function formatDownloads(count: number): string {
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k`;
  return String(count);
}

export function MarketplaceAgentCard({
  agent,
  installed = false,
  busy = false,
  onInstall,
  onDetail,
}: MarketplaceAgentCardProps) {
  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onDetail?.(agent.marketplace_agent_id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onDetail?.(agent.marketplace_agent_id);
        }
      }}
      className={cn(
        "group relative flex min-h-[260px] cursor-pointer flex-col p-5 outline-none",
        "bg-os-surface/40 backdrop-blur-md border border-os-border/50 rounded-2xl",
        "hover:-translate-y-1 hover:shadow-[0_8px_30px_rgba(129,140,248,0.12)] hover:border-os-accent/50 transition-all duration-300",
        "focus-visible:ring-2 focus-visible:ring-os-accent/70",
      )}
    >
      {/* Header — Icon with glow + Title + Description */}
      <div className="flex items-start gap-3">
        <div className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-os-accent/30 bg-os-accent/10 text-os-accent">
          <Bot size={20} />
          <div className="pointer-events-none absolute inset-0 rounded-xl bg-os-accent/10 blur-md -z-10" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-sm font-semibold text-os-text-high">
              {agent.display_name}
            </h3>
            {installed && (
              <CheckCircle2 size={13} className="shrink-0 text-os-success" />
            )}
          </div>
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-os-subtle">
            {agent.description || "暂无描述"}
          </p>
        </div>
      </div>

      {/* Tags — refined */}
      <div className="mt-3 flex flex-wrap gap-1.5">
        <span className={cn("os-badge text-2xs", categoryColor(agent.category))}>
          {agent.category}
        </span>
        <span className={cn("os-badge text-2xs", pricingColor(agent.pricing_model))}>
          {pricingLabel(agent.pricing_model)}
        </span>
        <span className="os-badge text-2xs bg-os-elevated text-os-subtle">
          v{agent.version}
        </span>
      </div>

      {/* Bottom Stats — downloads | rating | author (elegant flex) */}
      <div className="mt-auto flex items-center gap-4 pt-4 text-2xs text-os-muted">
        <span className="inline-flex items-center gap-1">
          <ArrowDownToLine size={11} />
          {formatDownloads(agent.install_count)}
        </span>
        <span className="inline-flex items-center gap-0.5 text-amber-300">
          <Star size={11} className="fill-amber-300" />
          {agent.rating.toFixed(1)}
        </span>
        <span className="inline-flex min-w-0 items-center gap-1 truncate">
          <User size={11} className="shrink-0" />
          <span className="truncate">{agent.publisher_name}</span>
        </span>
      </div>

      {/* Divider */}
      <div className="my-3 h-px bg-os-border/50" />

      {/* Actions — multi-state install button */}
      <div className="flex gap-2">
        <button
          type="button"
          className="inline-flex h-9 flex-1 items-center justify-center gap-1.5 rounded-lg border border-os-border bg-os-surface/60 px-3 text-xs font-medium text-os-subtle transition-colors hover:border-os-accent/40 hover:text-os-text-high"
          onClick={(e) => {
            e.stopPropagation();
            onDetail?.(agent.marketplace_agent_id);
          }}
        >
          <ExternalLink size={13} />
          详情
        </button>
        <button
          type="button"
          disabled={busy || installed}
          onClick={(e) => {
            e.stopPropagation();
            if (!installed && !busy) onInstall?.(agent.marketplace_agent_id);
          }}
          className={cn(
            "inline-flex h-9 flex-1 items-center justify-center gap-1.5 rounded-lg px-3 text-xs font-medium transition-all duration-200",
            installed
              ? "bg-os-success/10 text-os-success border border-os-success/30 cursor-default"
              : busy
                ? "border border-os-accent text-os-accent bg-transparent cursor-wait"
                : "bg-os-elevated text-os-text hover:bg-os-accent/20 hover:text-os-accent",
          )}
        >
          {busy ? (
            <Loader2 size={13} className="animate-spin" />
          ) : installed ? (
            <CheckCircle2 size={13} />
          ) : (
            <ArrowDownToLine size={13} />
          )}
          {busy ? "注入中" : installed ? "已注入" : "注入"}
        </button>
      </div>
    </article>
  );
}
