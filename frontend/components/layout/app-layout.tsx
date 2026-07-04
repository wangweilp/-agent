"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { AuthGuard } from "./auth-guard";
import { Header } from "./header";
import { Sidebar } from "./Sidebar";
import { useDrawerRuntime } from "@/hooks/useDrawerRuntime";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLoginPage = pathname === "/login";
  const [mobileOpen, setMobileOpen] = useState(false);
  useDrawerRuntime(mobileOpen, () => setMobileOpen(false));

  return (
    <AuthGuard>
      {isLoginPage ? (
        children
      ) : (
        <div className="flex h-screen overflow-hidden bg-os-page">
          <Sidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
          <div className="flex min-w-0 flex-1 flex-col">
            <Header onMenuClick={() => setMobileOpen(true)} />
            <main className="min-w-0 flex-1 overflow-y-auto bg-os-page">{children}</main>
          </div>
        </div>
      )}
    </AuthGuard>
  );
}
