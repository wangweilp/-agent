"use client";

import { cn } from "@/lib/utils";
import { useAgentStore } from "@/stores/agent-store";

export function Header() {
  const status = useAgentStore((s) => s.status);
  const traceId = useAgentStore((s) => s.traceId);

  const statusLabel: Record<string, string> = {
    idle: "就绪",
    thinking: "思考中...",
    acting: "执行中...",
    reflecting: "反思中...",
  };

  const statusDot: Record<string, string> = {
    idle: "bg-emerald-400",
    thinking: "bg-indigo-400 animate-pulse",
    acting: "bg-amber-400 animate-pulse",
    reflecting: "bg-violet-400 animate-pulse",
  };

  return (
    <header className="h-12 border-b border-os-border bg-os-base/80 backdrop-blur-xl flex items-center justify-between px-6 shrink-0">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className={cn("w-2 h-2 rounded-full", statusDot[status] || "bg-zinc-600")} />
          <span className="text-xs text-os-subtle">{statusLabel[status] || status}</span>
        </div>
        {traceId && (
          <span className="text-2xs text-os-muted font-mono">
            {traceId.slice(0, 8)}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        <span className="text-2xs text-os-muted">v0.1.0</span>
      </div>
    </header>
  );
}
