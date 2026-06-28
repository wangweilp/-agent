"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth-store";

/** 需要登录才能访问的路径前缀 */
const PROTECTED_PREFIXES = [
  "/home",
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
  // 等待 Zustand persist 完成 rehydration，避免 CSR 跳转时 token 仍为 null
  // 导致保护路由被误判为未登录，渲染 loading 占位且 children 不挂载（表现为白屏）
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    // useStore.persist.hasHydrated() 是 Zustand 提供的同步检查 API
    if (useAuthStore.persist.hasHydrated()) {
      setHydrated(true);
      return;
    }
    // 若仍在 rehydration，订阅完成事件
    const unsub = useAuthStore.persist.onFinishHydration(() => setHydrated(true));
    return unsub;
  }, []);

  useEffect(() => {
    if (!hydrated) return;

    if (isProtected(pathname) && !token) {
      router.replace("/login");
    }

    // 如果已登录且访问登录页，重定向到工作台门面首页
    if (pathname === "/login" && token) {
      router.replace("/home");
    }
  }, [hydrated, pathname, token, router]);

  // 登录页不需要 guard 包裹内容，直接渲染
  if (pathname === "/login") {
    return <>{children}</>;
  }

  // persist 未完成 rehydration 时不急于判定为未登录，显示 loading
  // 这避免了「token 仍为 null 但实际已登录」的误判窗口
  if (!hydrated) {
    return (
      <div className="min-h-screen bg-os-base flex items-center justify-center">
        <div className="flex items-center gap-3 text-sm text-os-subtle">
          <div className="w-2 h-2 rounded-full bg-os-accent animate-pulse" />
          加载会话...
        </div>
      </div>
    );
  }

  // rehydration 完成后仍无 token — 真正未登录，显示 loading 直到重定向生效
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
