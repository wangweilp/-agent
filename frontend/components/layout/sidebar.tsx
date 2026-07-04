"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  BarChart3,
  Bot,
  Brain,
  BrainCircuit,
  Bug,
  Building2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Code2,
  CreditCard,
  Crown,
  Gauge,
  GitGraph,
  LayoutDashboard,
  Lightbulb,
  MessageSquare,
  Mic,
  Network,
  ServerCog,
  Shield,
  ShieldAlert,
  ShieldCheck,
  ShoppingBag,
  UserCircle,
  Video,
  Workflow,
  Wrench,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useFocusTrap } from "@/hooks/useFocusTrap";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

type NavSection = {
  id: string;
  label: string;
  accent: "success" | "danger" | "primary" | "info" | "muted";
  items: NavItem[];
};

const navSections: NavSection[] = [
  {
    id: "workspace",
    label: "Workspace",
    accent: "primary",
    items: [{ href: "/home", label: "工作台", icon: LayoutDashboard }],
  },
  {
    id: "kernel",
    label: "Causal Kernel",
    accent: "success",
    items: [
      { href: "/causal-kernel", label: "因果内核", icon: Network },
      { href: "/causal-graph", label: "因果图引擎", icon: Workflow },
    ],
  },
  {
    id: "control",
    label: "Control Plane",
    accent: "danger",
    items: [{ href: "/runtime", label: "运行时控制面", icon: ShieldAlert }],
  },
  {
    id: "cognitive",
    label: "Cognitive Plane",
    accent: "primary",
    items: [
      { href: "/memory-console", label: "记忆智能控制台", icon: BrainCircuit },
      { href: "/memory", label: "记忆管理", icon: Brain },
      { href: "/reflection", label: "反思", icon: Lightbulb },
      { href: "/graph", label: "知识图谱", icon: GitGraph },
    ],
  },
  {
    id: "observability",
    label: "Observability",
    accent: "info",
    items: [
      { href: "/dashboard", label: "仪表盘", icon: LayoutDashboard },
      { href: "/timeline", label: "时间轴", icon: Clock },
      { href: "/dashboard-v2", label: "可观测性", icon: Gauge },
      { href: "/debug", label: "Debug", icon: Bug },
    ],
  },
  {
    id: "platform",
    label: "Platform",
    accent: "muted",
    items: [
      { href: "/chat", label: "对话", icon: MessageSquare },
      { href: "/audio", label: "音频", icon: Mic },
      { href: "/video", label: "视频", icon: Video },
      { href: "/tools", label: "工具中心", icon: Wrench },
      { href: "/agents", label: "内部智能体中心", icon: Bot },
      { href: "/agent-marketplace", label: "智能体市场", icon: ShoppingBag },
      { href: "/workspace", label: "工作区", icon: Building2 },
    ],
  },
  {
    id: "admin",
    label: "Admin & Dev",
    accent: "muted",
    items: [
      { href: "/developer", label: "开发者控制台", icon: Code2 },
      { href: "/admin/agent-submissions", label: "智能体审核", icon: ShieldCheck },
      { href: "/admin/runtime", label: "运行时管理", icon: ServerCog },
      { href: "/admin", label: "管理", icon: Shield },
      { href: "/analytics", label: "运营分析", icon: BarChart3 },
      { href: "/pricing", label: "套餐", icon: Crown },
      { href: "/billing", label: "账单", icon: CreditCard },
      { href: "/account", label: "账户", icon: UserCircle },
    ],
  },
];

const accentMap = {
  success: "bg-os-success",
  danger: "bg-os-danger",
  primary: "bg-os-primary",
  info: "bg-os-info",
  muted: "bg-os-muted",
};

function isRouteActive(pathname: string, href: string) {
  if (href === "/home") return pathname === "/home" || pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar({
  mobileOpen = false,
  onClose,
}: {
  mobileOpen?: boolean;
  onClose?: () => void;
}) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const drawerRef = useRef<HTMLElement>(null);
  useFocusTrap(drawerRef, mobileOpen);

  return (
    <>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-950/20 backdrop-blur-[2px] md:hidden"
          onClick={onClose}
          aria-hidden
        />
      )}
      <motion.aside
        ref={drawerRef}
        animate={{ width: mobileOpen ? 280 : collapsed ? 68 : 248 }}
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex h-screen shrink-0 flex-col overflow-hidden border-r border-os-border-subtle bg-white shadow-os-floating md:shadow-none",
          "transition-transform duration-200 ease-out md:transition-none",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
          "md:relative md:z-auto",
        )}
        transition={{ duration: 0.18, ease: "easeInOut" }}
      >
        <div className={cn("flex h-14 items-center border-b border-os-border-subtle px-4", collapsed && "justify-center px-2")}>
          <div className="flex shrink-0 items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-os-primary/15 bg-os-primary-soft text-os-primary shadow-os-card">
              <Zap size={16} />
            </div>
            <AnimatePresence initial={false}>
              {!collapsed && (
                <motion.span
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -4 }}
                  className="whitespace-nowrap text-sm font-semibold text-os-text-high"
                >
                  知维 OS
                </motion.span>
              )}
            </AnimatePresence>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto px-2.5 py-3">
          {navSections.map((section) => (
            <div key={section.id} className="mb-3">
              {!collapsed ? (
                <div className="flex items-center gap-1.5 px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-[0.11em] text-os-muted">
                  <span className={cn("h-1.5 w-1.5 rounded-full", accentMap[section.accent])} />
                  {section.label}
                </div>
              ) : (
                <div className="mx-3 my-2 h-px bg-os-border-subtle" />
              )}

              <div className="space-y-1">
                {section.items.map((item) => {
                  const active = isRouteActive(pathname, item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={onClose}
                      title={collapsed ? item.label : undefined}
                      className={cn(
                        "group relative flex h-9 items-center gap-2.5 rounded-xl border px-3 text-sm transition-[background-color,border-color,color] duration-150 focus-visible:ring-2 focus-visible:ring-os-primary/25",
                        active
                          ? "border-os-primary/15 bg-os-primary-soft text-os-primary"
                          : "border-transparent text-os-subtle hover:bg-os-surface-hover hover:text-os-text-high",
                        collapsed && "justify-center px-0",
                      )}
                    >
                      {active && !collapsed && (
                        <motion.span
                          layoutId={`sidebar-active-${section.id}`}
                          className="absolute left-0 top-2 h-5 w-0.5 rounded-full bg-os-primary"
                          transition={{ duration: 0.18 }}
                        />
                      )}
                      <item.icon size={17} className="shrink-0" />
                      <AnimatePresence initial={false}>
                        {!collapsed && (
                          <motion.span
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            className="min-w-0 truncate"
                          >
                            {item.label}
                          </motion.span>
                        )}
                      </AnimatePresence>
                      {active && !collapsed && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-current opacity-70" />}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className={cn("border-t border-os-border-subtle p-2.5", collapsed && "px-2")}>
          <div className={cn("flex items-center gap-2 rounded-2xl border border-os-border bg-os-surface-tinted p-2", collapsed && "justify-center")}>
            <div className="relative shrink-0">
              <div className="h-2 w-2 rounded-full bg-os-success" />
              <div className="absolute inset-0 h-2 w-2 rounded-full bg-os-success animate-status-breathe motion-reduce:animate-none" />
            </div>
            {!collapsed && (
              <div className="min-w-0 flex-1">
                <p className="truncate text-[11px] font-medium text-os-text-high">系统运行中</p>
                <p className="truncate font-mono text-[10px] text-os-muted">Control plane ready</p>
              </div>
            )}
            <button
              onClick={() => setCollapsed(!collapsed)}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-os-subtle transition-colors duration-150 hover:bg-white hover:text-os-primary focus-visible:ring-2 focus-visible:ring-os-primary/25"
              aria-label={collapsed ? "展开侧边栏" : "折叠侧边栏"}
              type="button"
            >
              {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
            </button>
          </div>
        </div>
      </motion.aside>
    </>
  );
}
