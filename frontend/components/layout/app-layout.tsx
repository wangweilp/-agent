"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { Header } from "./header";
import { AuthGuard } from "./auth-guard";
import { useDrawerRuntime } from "@/hooks/useDrawerRuntime";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLoginPage = pathname === "/login";
  const [mobileOpen, setMobileOpen] = useState(false);
  useDrawerRuntime(mobileOpen, () => setMobileOpen(false));

  return (
    <AuthGuard>
      {isLoginPage ? (
        // 登录页不使用 sidebar+header 布局
        children
      ) : (
        <div className="flex h-screen overflow-hidden bg-os-base bg-grid-subtle">
          <Sidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
          <div className="flex-1 flex flex-col min-w-0">
            <Header onMenuClick={() => setMobileOpen(true)} />
            {/*
              直接渲染 children，不使用 AnimatePresence + motion.div key={pathname} 包裹。
              原因：Next.js 15 + React 19 + framer-motion 11 在 CSR 路由切换时，
              AnimatePresence 的 key 变化可能导致新组件的 animate 不触发，
              使 motion.div 卡在 initial={{ opacity: 0 }}，整个页面不可见。
              刷新走 SSR 时 framer-motion 跳过 initial 动画，所以刷新后正常。
              各页面内部的 PageTransition 仍提供入场动画。
            */}
            <main className="flex-1 overflow-y-auto">{children}</main>
          </div>
        </div>
      )}
    </AuthGuard>
  );
}
