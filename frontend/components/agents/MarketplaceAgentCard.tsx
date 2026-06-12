"use client";

import { ArrowDownToLine, Bot, CheckCircle2, ExternalLink, Star } from "lucide-react";
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

export function MarketplaceAgentCard({
  agent,
  installed = false,
  busy = false,
  onInstall,
  onDetail,
}: MarketplaceAgentCardProps) {
  const firstCapabilities = agent.capabilities.slice(0, 3);

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
      className="group os-card os-card-hover flex min-h-[280px] flex-col p-4 outline-none focus-visible:ring-2 focus-visible:ring-os-accent/70"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-os-accent/30 bg-os-accent/15 text-os-accent">
            <Bot size={19} />
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-os-text-high">
              {agent.display_name}
            </h3>
            <p className="mt-1 line-clamp-2 text-xs leading-5 text-os-subtle">
              {agent.description || "暂无描述"}
            </p>
          </div>
        </div>

        {installed ? (
          <span className="os-badge shrink-0 bg-emerald-400/10 text-emerald-300">
            <CheckCircle2 size={11} />
            已安装
          </span>
        ) : (
          <span className="os-badge shrink-0 bg-zinc-500/10 text-os-muted">
            未安装
          </span>
        )}
      </div>

      {/* Tags */}
      <div className="mt-4 flex flex-wrap gap-1.5">
        <span className={cn("os-badge text-2xs", categoryColor(agent.category))}>
          {agent.category}
        </span>
        {agent.department && (
          <span className="os-badge bg-zinc-500/10 text-os-subtle">
            {agent.department}
          </span>
        )}
        <span className={cn("os-badge text-2xs", pricingColor(agent.pricing_model))}>
          {pricingLabel(agent.pricing_model)}
        </span>
        <span className="os-badge bg-os-elevated text-os-subtle">v{agent.version}</span>
        <span className="os-badge bg-os-elevated text-os-subtle">{agent.publisher_name}</span>
      </div>

      {/* Capabilities */}
      {firstCapabilities.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {firstCapabilities.map((cap) => (
            <span key={cap} className="rounded bg-os-elevated px-2 py-0.5 text-2xs text-os-subtle">
              {cap}
            </span>
          ))}
          {agent.capabilities.length > 3 && (
            <span className="rounded bg-os-elevated px-2 py-0.5 text-2xs text-os-muted">
              +{agent.capabilities.length - 3}
            </span>
          )}
        </div>
      )}

      {/* Stats */}
      <div className="mt-4 grid grid-cols-3 gap-2">
        <div className="rounded-md border border-os-border bg-os-elevated/50 px-2 py-2 text-center">
          <p className="text-2xs text-os-muted">安装</p>
          <p className="mt-0.5 text-sm font-semibold text-os-text-high">{agent.install_count}</p>
        </div>
        <div className="rounded-md border border-os-border bg-os-elevated/50 px-2 py-2 text-center">
          <p className="flex items-center justify-center gap-0.5 text-2xs text-os-muted">
            <Star size={10} />
            评分
          </p>
          <p className="mt-0.5 text-sm font-semibold text-amber-300">{agent.rating.toFixed(1)}</p>
        </div>
        <div className="rounded-md border border-os-border bg-os-elevated/50 px-2 py-2 text-center">
          <p className="text-2xs text-os-muted">权限</p>
          <p className="mt-0.5 text-sm font-semibold text-os-text-high">
            {agent.required_permissions.length}
          </p>
        </div>
      </div>

      {/* Actions */}
      <div className="mt-auto flex gap-2 pt-4">
        <button
          type="button"
          className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-md border border-os-border bg-os-surface px-3 text-xs font-medium text-os-subtle transition-colors hover:border-os-accent/40 hover:text-os-text-high"
          onClick={(e) => {
            e.stopPropagation();
            onDetail?.(agent.marketplace_agent_id);
          }}
        >
          <ExternalLink size={14} />
          详情
        </button>
        {!installed && (
          <button
            type="button"
            className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-md bg-os-accent px-3 text-xs font-medium text-white transition-colors hover:bg-os-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={busy}
            onClick={(e) => {
              e.stopPropagation();
              onInstall?.(agent.marketplace_agent_id);
            }}
          >
            {busy ? (
              <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            ) : (
              <ArrowDownToLine size={14} />
            )}
            {busy ? "安装中" : "安装"}
          </button>
        )}
        {installed && (
          <span className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-md bg-emerald-400/10 px-3 text-xs font-medium text-emerald-300">
            <CheckCircle2 size={14} />
            已安装
          </span>
        )}
      </div>
    </article>
  );
}
