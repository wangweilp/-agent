"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard,
  MessageSquare,
  Brain,
  Lightbulb,
  Wrench,
  ChevronLeft,
  ChevronRight,
  Zap,
  Bot,
  Bug,
  Clock,
  Code2,
  GitGraph,
  Mic,
  Video,
  Building2,
  Shield,
  ShieldCheck,
  BarChart3,
  CreditCard,
  Crown,
  ShoppingBag,
  UserCircle,
  ServerCog,
  Gauge,
  ShieldAlert,
  BrainCircuit,
  Network,
  Workflow,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useState, useRef } from "react";
import { useFocusTrap } from "@/hooks/useFocusTrap";

type NavItem = {
  href: string;
  label: string;
  icon: typeof Zap;
};

type NavSection = {
  id: string;
  label: string;
  accent: "emerald" | "rose" | "violet" | "indigo" | "zinc";
  items: NavItem[];
};

// ── 系统层级导航：Workspace > Control Plane > Cognitive Plane > Observability Plane ──
// 知维 OS（Zhiwei OS）— AI Operating System
const navSections: NavSection[] = [
  {
    id: "workspace",
    label: "Workspace",
    accent: "indigo",
    items: [
      // 工作台 (Workspace Hub)：登录后门面首页，极客风 Hero 视觉，与仪表盘物理隔离
      { href: "/home", label: "工作台", icon: LayoutDashboard },
    ],
  },
  {
    id: "kernel",
    label: "Causal Kernel",
    accent: "emerald",
    items: [
      { href: "/causal-kernel", label: "因果内核", icon: Network },
      { href: "/causal-graph", label: "因果图引擎", icon: Workflow },
    ],
  },
  {
    id: "control",
    label: "Control Plane",
    accent: "rose",
    items: [
      { href: "/runtime", label: "运行时控制面", icon: ShieldAlert },
    ],
  },
  {
    id: "cognitive",
    label: "Cognitive Plane",
    accent: "violet",
    items: [
      { href: "/memory-console", label: "记忆智能控制台", icon: BrainCircuit },
      { href: "/memory", label: "记忆管理", icon: Brain },
      { href: "/reflection", label: "反思", icon: Lightbulb },
      { href: "/graph", label: "知识图谱", icon: GitGraph },
    ],
  },
  {
    id: "observability",
    label: "可观测性 Plane",
    accent: "indigo",
    items: [
      // 仪表盘 (Dashboard)：纯数据图表监控中心，与工作台 (Workspace Hub) 物理隔离
      { href: "/dashboard", label: "仪表盘", icon: LayoutDashboard },
      { href: "/timeline", label: "时间轴", icon: Clock },
      { href: "/dashboard-v2", label: "可观测性", icon: Gauge },
      { href: "/debug", label: "Debug", icon: Bug },
    ],
  },
  {
    id: "platform",
    label: "Platform",
    accent: "zinc",
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
    accent: "zinc",
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
  emerald: "text-emerald-400",
  rose: "text-rose-400",
  violet: "text-violet-400",
  indigo: "text-indigo-400",
  zinc: "text-os-muted",
};

const activeAccentBg = {
  emerald: "bg-emerald-400/10 text-emerald-400",
  rose: "bg-rose-400/10 text-rose-400",
  violet: "bg-violet-400/10 text-violet-400",
  indigo: "bg-indigo-400/10 text-indigo-400",
  zinc: "bg-os-accent/10 text-os-accent",
};

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
      {/* 移动端深色半透明遮罩 — 点击关闭侧边栏 */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm md:hidden"
          onClick={onClose}
          aria-hidden
        />
      )}
    <motion.aside
      ref={drawerRef}
      animate={{ width: mobileOpen ? 280 : collapsed ? 64 : 240 }}
      className={cn(
        "fixed inset-y-0 left-0 z-50 h-screen bg-os-surface/80 backdrop-blur-md border-r border-os-border/50 flex flex-col shrink-0 overflow-hidden shadow-2xl md:shadow-none",
        // 移动端滑入/滑出；桌面端回归 relative 内联布局
        "transition-transform duration-300 ease-in-out md:transition-none",
        mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        "md:relative md:z-auto",
      )}
      transition={{ duration: 0.2, ease: "easeInOut" }}
    >
      {/* Logo */}
      <div className={cn("flex items-center h-14 px-4 border-b border-os-border", collapsed && "justify-center px-2")}>
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="w-7 h-7 rounded-lg bg-os-accent/15 flex items-center justify-center">
            <Zap size={15} className="text-os-accent" />
          </div>
          <AnimatePresence>
            {!collapsed && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-sm font-semibold text-os-text-high tracking-tight whitespace-nowrap"
              >
                知维 OS
              </motion.span>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Nav — 按系统层级分组 */}
      <nav className="flex-1 py-2 px-2 overflow-y-auto">
        {navSections.map((section) => (
          <div key={section.id} className="mb-3">
            {/* Section label */}
            {!collapsed && (
              <div className={cn(
                "flex items-center gap-1.5 px-2.5 py-1 text-2xs font-medium uppercase tracking-wider",
                accentMap[section.accent],
              )}>
                <span className="w-1 h-1 rounded-full bg-current opacity-60" />
                {section.label}
              </div>
            )}
            {collapsed && (
              <div className="my-1 mx-2 h-px bg-os-border/50" />
            )}

            {/* Section items */}
            <div className="space-y-0.5 mt-0.5">
              {section.items.map((item) => {
                const isActive = pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={onClose}
                    className={cn(
                      "flex items-center gap-3 h-9 px-2.5 rounded-md text-sm transition-colors duration-200 group relative",
                      isActive
                        ? "bg-os-accent/10 text-os-accent border-l-2 border-os-accent"
                        : "text-os-text hover:text-os-text-high hover:bg-os-elevated border-l-2 border-transparent",
                      collapsed && "justify-center px-0",
                    )}
                  >
                    <item.icon size={18} className="shrink-0" />
                    <AnimatePresence>
                      {!collapsed && (
                        <motion.span
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                          className="whitespace-nowrap"
                        >
                          {item.label}
                        </motion.span>
                      )}
                    </AnimatePresence>
                    {isActive && !collapsed && (
                      <motion.div
                        layoutId={`sidebar-active-${section.id}`}
                        className="ml-auto w-1 h-1 rounded-full bg-current"
                        transition={{ duration: 0.2 }}
                      />
                    )}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Collapse button */}
      <div className="border-t border-os-border p-2">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center justify-center w-full h-8 rounded-md text-os-subtle hover:text-os-text hover:bg-os-elevated transition-all"
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      {/* Status indicator */}
      <div className={cn("border-t border-os-border px-4 py-3", collapsed && "px-2")}>
        <div className="flex items-center gap-2">
          <div className="relative">
            <div className="w-2 h-2 rounded-full bg-emerald-400" />
            <div className="absolute inset-0 w-2 h-2 rounded-full bg-emerald-400 animate-status-breathe" />
          </div>
          {!collapsed && (
            <span className="text-2xs text-os-subtle whitespace-nowrap">系统运行中</span>
          )}
        </div>
      </div>
    </motion.aside>
    </>
  );
}
