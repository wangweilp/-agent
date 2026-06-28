"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Building2,
  Users,
  Shield,
  ShieldAlert,
  FileText,
  Server,
  ChevronRight,
  LayoutDashboard,
} from "lucide-react";
import { cn } from "@/lib/utils";

const adminNavItems = [
  { href: "/admin", label: "企业仪表盘", icon: LayoutDashboard },
  { href: "/admin/runtime", label: "运行时治理", icon: ShieldAlert },
  { href: "/admin/organization", label: "组织中心", icon: Building2 },
  { href: "/admin/users", label: "用户管理", icon: Users },
  { href: "/admin/audit", label: "审计中心", icon: Shield },
  { href: "/admin/policy", label: "策略中心", icon: FileText },
  { href: "/admin/deployment", label: "部署状态", icon: Server },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-full">
      {/* Admin Sidebar — 移动端隐藏（主侧边栏抽屉已含管理导航），桌面端保留双栏 */}
      <aside className="hidden md:flex w-56 shrink-0 border-r border-os-border/60 bg-os-base/80 backdrop-blur-sm flex-col">
        <div className="px-4 py-4 border-b border-os-border/60">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-6 h-6 rounded-lg bg-os-accent/10 flex items-center justify-center">
              <Shield size={13} className="text-os-accent" />
            </div>
            <h1 className="text-sm font-semibold text-os-text-high tracking-tight">
              企业管理
            </h1>
          </div>
          <p className="text-2xs text-os-muted ml-8">
            系统管理控制台
          </p>
        </div>

        <nav className="flex-1 py-3 px-2 space-y-0.5">
          {adminNavItems.map((item) => {
            const isActive =
              item.href === "/admin"
                ? pathname === "/admin"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-2.5 h-9 px-2.5 rounded-lg text-xs transition-all duration-150 group",
                  isActive
                    ? "bg-os-accent/10 text-os-accent border border-os-accent/10"
                    : "text-os-text hover:text-os-text-high hover:bg-os-elevated/80 border border-transparent"
                )}
              >
                <div className={cn(
                  "w-6 h-6 rounded-md flex items-center justify-center shrink-0",
                  isActive ? "bg-os-accent/15" : "bg-os-elevated/50"
                )}>
                  <item.icon size={14} className={isActive ? "text-os-accent" : "text-os-subtle"} />
                </div>
                <span className="whitespace-nowrap">{item.label}</span>
                {isActive && (
                  <ChevronRight size={12} className="ml-auto text-os-accent" />
                )}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-os-border/60 px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="relative">
              <div className="w-2 h-2 rounded-full bg-emerald-400" />
              <div className="absolute inset-0 w-2 h-2 rounded-full bg-emerald-400 animate-status-breathe" />
            </div>
            <span className="text-2xs text-os-subtle">管理面板运行中</span>
          </div>
        </div>
      </aside>

      {/* Content */}
      <div className="flex-1 overflow-y-auto bg-os-base">{children}</div>
    </div>
  );
}
