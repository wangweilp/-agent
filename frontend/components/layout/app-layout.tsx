"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { Header } from "./header";
import { AuthGuard } from "./auth-guard";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLoginPage = pathname === "/login";

  return (
    <AuthGuard>
      {isLoginPage ? (
        // 登录页不使用 sidebar+header 布局
        children
      ) : (
        <div className="flex h-screen overflow-hidden bg-os-base">
          <Sidebar />
          <div className="flex-1 flex flex-col min-w-0">
            <Header />
            <main className="flex-1 overflow-y-auto">{children}</main>
          </div>
        </div>
      )}
    </AuthGuard>
  );
}
