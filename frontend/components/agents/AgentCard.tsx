"use client";

import { Bot, Clock, Play, Power, PowerOff, Tags, TrendingUp } from "lucide-react";

import { cn } from "@/lib/utils";
import type { AgentSummary } from "@/types/agents";

interface AgentCardProps {
  agent: AgentSummary;
  busy?: boolean;
  onRun?: (agentId: string) => void;
  onToggle?: (agentId: string, enabled: boolean) => void;
  onClick?: (agentId: string) => void;
}

function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "-";
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}

export function AgentCard({ agent, busy, onRun, onToggle, onClick }: AgentCardProps) {
  const successPercent = Math.round((agent.success_rate || 0) * 100);

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onClick?.(agent.agent_id)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onClick?.(agent.agent_id);
        }
      }}
      className="group os-card os-card-hover flex min-h-[260px] flex-col p-4 outline-none focus-visible:ring-2 focus-visible:ring-os-accent/70"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div
            className={cn(
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-md border",
              agent.enabled
                ? "border-os-accent/30 bg-os-accent/15 text-os-accent"
                : "border-os-border bg-os-elevated text-os-muted",
            )}
          >
            <Bot size={19} />
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-os-text-high">{agent.name}</h3>
            <p className="mt-1 line-clamp-3 text-xs leading-5 text-os-subtle">
              {agent.description || "暂无描述"}
            </p>
          </div>
        </div>

        <span
          className={cn(
            "os-badge shrink-0",
            agent.enabled
              ? "bg-emerald-400/10 text-emerald-300"
              : "bg-zinc-500/10 text-os-muted",
          )}
        >
          <span className={cn("h-1.5 w-1.5 rounded-full", agent.enabled ? "bg-emerald-400" : "bg-zinc-500")} />
          {agent.enabled ? "已启用" : "已停用"}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {agent.tags.length > 0 ? (
          agent.tags.map((tag) => (
            <span key={tag} className="os-badge bg-os-accent/10 text-os-accent">
              <Tags size={10} />
              {tag}
            </span>
          ))
        ) : (
          <span className="os-badge bg-os-elevated text-os-muted">无标签</span>
        )}
        <span className="os-badge bg-os-elevated text-os-subtle">v{agent.version}</span>
      </div>

      <div className="mt-5 grid grid-cols-3 gap-2">
        <div className="rounded-md border border-os-border bg-os-elevated/50 p-3">
          <p className="text-2xs text-os-muted">调用次数</p>
          <p className="mt-1 text-base font-semibold text-os-text-high">{agent.usage_count}</p>
        </div>
        <div className="rounded-md border border-os-border bg-os-elevated/50 p-3">
          <p className="flex items-center gap-1 text-2xs text-os-muted">
            <TrendingUp size={11} />
            成功率
          </p>
          <p className="mt-1 text-base font-semibold text-emerald-300">{successPercent}%</p>
        </div>
        <div className="rounded-md border border-os-border bg-os-elevated/50 p-3">
          <p className="flex items-center gap-1 text-2xs text-os-muted">
            <Clock size={11} />
            平均耗时
          </p>
          <p className="mt-1 text-base font-semibold text-os-text-high">
            {formatDuration(agent.avg_duration_ms)}
          </p>
        </div>
      </div>

      <div className="mt-3 h-1.5 rounded-full bg-os-elevated">
        <div
          className="h-full rounded-full bg-os-accent"
          style={{ width: `${Math.max(4, Math.min(100, successPercent))}%` }}
        />
      </div>

      <div className="mt-auto flex gap-2 pt-5">
        <button
          type="button"
          className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-md bg-os-accent px-3 text-xs font-medium text-white transition-colors hover:bg-os-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={busy || !agent.enabled}
          onClick={(event) => {
            event.stopPropagation();
            onRun?.(agent.agent_id);
          }}
        >
          <Play size={14} />
          运行测试
        </button>
        <button
          type="button"
          className={cn(
            "inline-flex h-9 items-center justify-center gap-2 rounded-md px-3 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
            agent.enabled
              ? "bg-red-400/10 text-red-300 hover:bg-red-400/15"
              : "bg-emerald-400/10 text-emerald-300 hover:bg-emerald-400/15",
          )}
          disabled={busy}
          onClick={(event) => {
            event.stopPropagation();
            onToggle?.(agent.agent_id, !agent.enabled);
          }}
        >
          {agent.enabled ? <PowerOff size={14} /> : <Power size={14} />}
          {busy ? "处理中" : agent.enabled ? "停用" : "启用"}
        </button>
      </div>
    </article>
  );
}
