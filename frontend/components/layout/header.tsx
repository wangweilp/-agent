"use client";

import { useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Building2, ChevronDown, LogOut, Menu } from "lucide-react";
import { useAgentStore } from "@/stores/agent-store";
import { useAuthStore } from "@/stores/auth-store";
import { OsButton, StatusBadge } from "@/components/ui/os";

export function Header({ onMenuClick }: { onMenuClick?: () => void }) {
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
    thinking: "思考中",
    acting: "执行中",
    reflecting: "反思中",
  };

  const statusTone: Record<string, "ready" | "info" | "warning"> = {
    idle: "ready",
    thinking: "info",
    acting: "warning",
    reflecting: "info",
  };

  return (
    <header className="relative flex h-[52px] shrink-0 items-center justify-between gap-2 border-b border-os-border-subtle bg-white/90 px-3 shadow-none backdrop-blur-md sm:px-4 md:h-14 md:px-5">
      <div className="flex min-w-0 items-center gap-2 sm:gap-3">
        {onMenuClick && (
          <OsButton
            onClick={onMenuClick}
            variant="ghost"
            size="icon"
            className="-ml-1 md:hidden"
            aria-label="打开菜单"
            type="button"
          >
            <Menu size={18} />
          </OsButton>
        )}
        <StatusBadge status={statusTone[status] ?? "muted"}>{statusLabel[status] || status}</StatusBadge>
        {traceId && (
          <span className="hidden whitespace-nowrap rounded-full border border-os-border bg-white px-2 py-1 font-mono text-[11px] text-os-muted sm:inline">
            {traceId.slice(0, 8)}
          </span>
        )}
      </div>

      <div className="flex min-w-0 items-center justify-end gap-1.5 sm:gap-2">
        {currentWorkspace && (
          <Link
            href="/workspace"
            className="flex h-9 min-w-0 items-center gap-1.5 rounded-xl border border-transparent px-2 text-xs text-os-subtle transition-colors duration-150 hover:border-os-border hover:bg-white hover:text-os-text-high focus-visible:ring-2 focus-visible:ring-os-primary/25 sm:max-w-[190px] md:max-w-[240px]"
          >
            <Building2 size={13} className="shrink-0 text-os-muted" />
            <span className="hidden max-w-[140px] truncate whitespace-nowrap sm:inline">{currentWorkspace.name}</span>
            <ChevronDown size={12} className="hidden shrink-0 sm:block" />
          </Link>
        )}

        {user && (
          <>
            <span className="hidden max-w-[150px] truncate whitespace-nowrap rounded-full border border-os-border bg-white px-2.5 py-1 text-[11px] text-os-muted lg:inline">
              {user.name || user.email}
            </span>
            <OsButton
              onClick={handleLogout}
              variant="ghost"
              size="icon"
              className="hover:text-os-danger"
              title="退出登录"
              aria-label="退出登录"
              type="button"
            >
              <LogOut size={14} />
            </OsButton>
          </>
        )}

        <span className="hidden whitespace-nowrap rounded-full border border-os-border bg-white px-2 py-1 font-mono text-[11px] text-os-muted sm:inline">
          v0.1.0
        </span>
      </div>
    </header>
  );
}
