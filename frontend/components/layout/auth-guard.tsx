"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth-store";

/** 需要登录才能访问的路径前缀 */
const PROTECTED_PREFIXES = [
  "/dashboard",
  "/chat",
  "/memory",
  "/timeline",
  "/graph",
  "/audio",
  "/video",
  "/workspace",
  "/reflection",
  "/tools",
  "/admin",
  "/pricing",
  "/billing",
  "/analytics",
  "/account",
  "/debug",
  "/agents",
  "/import",
  "/sync",
];

/** 无需登录的公开路径 */
const PUBLIC_PATHS = ["/login"];

function isProtected(pathname: string): boolean {
  // Root redirects to dashboard, so it's protected
  if (pathname === "/") return true;
  // Exact match for public paths
  if (PUBLIC_PATHS.includes(pathname)) return false;
  // Check protected prefixes
  return PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(prefix + "/")
  );
}

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // Zustand persist 从 localStorage 恢复是同步的，但 hydration 需要一帧
    // 用一个微小的延迟确保 store 已经完成 rehydration
    const t = setTimeout(() => setReady(true), 0);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (!ready) return;

    if (isProtected(pathname) && !token) {
      router.replace("/login");
    }

    // 如果已登录且访问登录页，重定向到 dashboard
    if (pathname === "/login" && token) {
      router.replace("/dashboard");
    }
  }, [ready, pathname, token, router]);

  // 登录页不需要 guard 包裹内容，直接渲染
  if (pathname === "/login") {
    return <>{children}</>;
  }

  // 未登录且需要保护 — 显示 loading 直到重定向
  if (!token && isProtected(pathname)) {
    return (
      <div className="min-h-screen bg-os-base flex items-center justify-center">
        <div className="flex items-center gap-3 text-sm text-os-subtle">
          <div className="w-2 h-2 rounded-full bg-os-accent animate-pulse" />
          验证身份...
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
