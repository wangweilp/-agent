"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Building2,
  Users,
  Shield,
  FileText,
  Server,
  ChevronRight,
  LayoutDashboard,
} from "lucide-react";
import { cn } from "@/lib/utils";

const adminNavItems = [
  { href: "/admin", label: "Enterprise Dashboard", icon: LayoutDashboard },
  { href: "/admin/organization", label: "Organization Center", icon: Building2 },
  { href: "/admin/users", label: "User Management", icon: Users },
  { href: "/admin/audit", label: "Audit Center", icon: Shield },
  { href: "/admin/policy", label: "Policy Center", icon: FileText },
  { href: "/admin/deployment", label: "Deployment Status", icon: Server },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-full">
      {/* Admin Sidebar */}
      <aside className="w-56 shrink-0 border-r border-os-border bg-os-surface/50 flex flex-col">
        <div className="px-4 py-4 border-b border-os-border">
          <h1 className="text-sm font-semibold text-os-text-high tracking-tight">
            Enterprise Admin
          </h1>
          <p className="text-2xs text-os-muted mt-0.5">
            System administration
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
                  "flex items-center gap-2.5 h-9 px-2.5 rounded-md text-xs transition-all duration-150 group",
                  isActive
                    ? "bg-os-accent/10 text-os-accent"
                    : "text-os-text hover:text-os-text-high hover:bg-os-elevated"
                )}
              >
                <item.icon size={15} className="shrink-0" />
                <span className="whitespace-nowrap">{item.label}</span>
                {isActive && (
                  <ChevronRight size={12} className="ml-auto text-os-accent" />
                )}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-os-border px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="relative">
              <div className="w-2 h-2 rounded-full bg-emerald-400" />
              <div className="absolute inset-0 w-2 h-2 rounded-full bg-emerald-400 animate-status-breathe" />
            </div>
            <span className="text-2xs text-os-subtle">Admin Panel Active</span>
          </div>
        </div>
      </aside>

      {/* Content */}
      <div className="flex-1 overflow-y-auto bg-os-base">{children}</div>
    </div>
  );
}
