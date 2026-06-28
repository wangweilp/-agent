"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, RefreshCw, Home, Bug } from "lucide-react";

/**
 * 全局错误边界 — 捕获渲染期未处理异常，避免整树白屏。
 *
 * 触发场景：CSR 跳转时子组件抛出同步异常（如脏数据解析、undefined 访问），
 * 若无此边界，React 会卸载整个组件树导致白屏；F5 刷新走 SSR 绕过异常路径，
 * 因此出现"点击跳转白屏、刷新恢复"的症状。
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // 上报到控制台，便于 DevTools 排查（生产环境可接入 Sentry/自建上报）
    console.error("[GlobalErrorBoundary]", error);
  }, [error]);

  const isDev = process.env.NODE_ENV !== "production";

  return (
    <main className="min-h-screen bg-os-base flex items-center justify-center p-4">
      <div className="w-full max-w-lg rounded-2xl border border-red-500/20 bg-os-surface/60 backdrop-blur-md p-6 shadow-2xl">
        <div className="flex items-start gap-4 mb-5">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-red-500/30 bg-red-500/10 text-red-400">
            <AlertTriangle size={22} />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-semibold text-os-text-high">
              渲染异常
            </h2>
            <p className="mt-1 text-sm text-os-subtle leading-6">
              页面在加载时遇到未预期的错误。可尝试重试，或返回首页重新进入。
            </p>
          </div>
        </div>

        {isDev && (
          <details className="mb-5 rounded-lg border border-os-border/60 bg-[#000000] p-3 group">
            <summary className="flex cursor-pointer items-center gap-2 text-2xs font-mono text-os-muted hover:text-os-subtle">
              <Bug size={12} />
              <span>错误详情（仅开发环境）</span>
            </summary>
            <div className="mt-2 space-y-1.5 font-mono text-2xs text-os-subtle">
              <p className="text-red-300 break-all">{error?.message || "Unknown error"}</p>
              {error?.digest && (
                <p className="text-os-muted">digest: {error.digest}</p>
              )}
              {error?.stack && (
                <pre className="mt-2 whitespace-pre-wrap break-all text-os-muted text-2xs leading-4 max-h-48 overflow-y-auto">
                  {error.stack}
                </pre>
              )}
            </div>
          </details>
        )}

        <div className="flex flex-wrap gap-2">
          <button
            onClick={reset}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-os-accent px-4 text-xs font-medium text-white transition-colors hover:bg-os-accent/90"
          >
            <RefreshCw size={13} />
            重试
          </button>
          <button
            onClick={() => {
              if (typeof window !== "undefined") window.location.reload();
            }}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-os-border bg-os-elevated px-4 text-xs font-medium text-os-text-high transition-colors hover:bg-os-surface"
          >
            <RefreshCw size={13} />
            刷新页面
          </button>
          <Link
            href="/"
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-os-border bg-os-elevated px-4 text-xs font-medium text-os-subtle transition-colors hover:text-os-text-high"
          >
            <Home size={13} />
            返回首页
          </Link>
        </div>
      </div>
    </main>
  );
}
