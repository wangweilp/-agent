"use client";

import { useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAgentStore } from "@/stores/agent-store";
import { useAuthStore } from "@/stores/auth-store";
import { Building2, ChevronDown, LogOut } from "lucide-react";

export function Header() {
  const status = useAgentStore((s) => s.status);
  const traceId = useAgentStore((s) => s.traceId);
  const currentWorkspace = useAuthStore((s) => s.currentWorkspace);
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const router = useRouter();

  const handleLogout = useCallback(() => {
    clearAuth();
    router.push("/login");
  }, [clearAuth, router]);

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
    <header className="h-12 border-b border-os-border/60 bg-os-base/80 backdrop-blur-xl flex items-center justify-between px-6 shrink-0 relative">
      {/* 底部光条 */}
      <div className="absolute bottom-0 left-1/4 right-1/4 h-px bg-gradient-to-r from-transparent via-os-accent/10 to-transparent" />
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
        {/* Workspace indicator */}
        {currentWorkspace && (
          <Link
            href="/workspace"
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs text-os-subtle hover:text-os-text hover:bg-os-elevated transition-colors"
          >
            <Building2 size={12} className="text-os-accent/70" />
            <span className="max-w-[120px] truncate">{currentWorkspace.name}</span>
            <ChevronDown size={10} />
          </Link>
        )}

        {/* User indicator */}
        {user && (
          <>
            <span className="text-2xs text-os-muted">
              {user.name || user.email}
            </span>
            <button
              onClick={handleLogout}
              className="p-1 rounded text-os-muted hover:text-os-danger hover:bg-os-danger/10 transition-colors"
              title="退出登录"
            >
              <LogOut size={13} />
            </button>
          </>
        )}

        <span className="text-2xs text-os-muted">v0.1.0</span>
      </div>
    </header>
  );
}
