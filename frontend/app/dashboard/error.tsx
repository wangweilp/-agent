"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, RefreshCw, LayoutDashboard } from "lucide-react";

/**
 * Dashboard 路由级错误边界。
 *
 * 与 app/error.tsx 的区别：此边界触发时，root layout（Sidebar + Header）仍保持渲染，
 * 仅 main 内容区降级为错误卡片，避免整树白屏。适用于 dashboard 子组件（StatusCard、
 * MemoryChart、TraceTimeline 等）在 CSR 跳转时抛异常的场景。
 */
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[DashboardErrorBoundary]", error);
  }, [error]);

  const isDev = process.env.NODE_ENV !== "production";

  return (
    <main className="p-6 max-w-3xl mx-auto">
      <div className="rounded-2xl border border-red-500/20 bg-os-surface/60 backdrop-blur-md p-6">
        <div className="flex items-start gap-4 mb-5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-red-500/30 bg-red-500/10 text-red-400">
            <AlertTriangle size={20} />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-semibold text-os-text-high">
              仪表盘加载失败
            </h2>
            <p className="mt-1 text-xs text-os-subtle leading-5">
              页面组件在渲染时遇到错误。可重试加载，或刷新页面恢复。
            </p>
          </div>
        </div>

        {isDev && (
          <details className="mb-5 rounded-lg border border-os-border/60 bg-slate-50 p-3">
            <summary className="flex cursor-pointer items-center gap-2 text-2xs font-mono text-os-muted hover:text-os-subtle">
              <span>错误详情（仅开发环境）</span>
            </summary>
            <div className="mt-2 space-y-1.5 font-mono text-2xs text-os-subtle">
              <p className="text-red-300 break-all">{error?.message || "Unknown error"}</p>
              {error?.digest && (
                <p className="text-os-muted">digest: {error.digest}</p>
              )}
            </div>
          </details>
        )}

        <div className="flex flex-wrap gap-2">
          <button
            onClick={reset}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-os-accent px-3.5 text-2xs font-medium text-white transition-colors hover:bg-os-accent/90"
          >
            <RefreshCw size={12} />
            重试
          </button>
          <button
            onClick={() => {
              if (typeof window !== "undefined") window.location.reload();
            }}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-os-border bg-os-elevated px-3.5 text-2xs font-medium text-os-text-high transition-colors hover:bg-os-surface"
          >
            <RefreshCw size={12} />
            刷新页面
          </button>
          <Link
            href="/"
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-os-border bg-os-elevated px-3.5 text-2xs font-medium text-os-subtle transition-colors hover:text-os-text-high"
          >
            <LayoutDashboard size={12} />
            返回首页
          </Link>
        </div>
      </div>
    </main>
  );
}
