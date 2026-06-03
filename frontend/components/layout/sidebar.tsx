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
  Bug,
  Clock,
  GitGraph,
  Mic,
  Video,
  Building2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useState } from "react";

const navItems = [
  { href: "/dashboard", label: "仪表盘", icon: LayoutDashboard, active: true },
  { href: "/chat", label: "对话", icon: MessageSquare },
  { href: "/memory", label: "记忆", icon: Brain },
  { href: "/timeline", label: "时间轴", icon: Clock },
  { href: "/graph", label: "知识图谱", icon: GitGraph },
  { href: "/audio", label: "音频", icon: Mic },
  { href: "/video", label: "视频", icon: Video },
  { href: "/workspace", label: "工作区", icon: Building2 },
  { href: "/reflection", label: "反思", icon: Lightbulb },
  { href: "/tools", label: "工具中心", icon: Wrench },
  { href: "/debug", label: "Debug", icon: Bug },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <motion.aside
      animate={{ width: collapsed ? 64 : 240 }}
      className="relative h-screen bg-os-base border-r border-os-border flex flex-col shrink-0 overflow-hidden"
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
                Agent OS
              </motion.span>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 h-9 px-2.5 rounded-md text-sm transition-all duration-150 group",
                isActive
                  ? "bg-os-accent/10 text-os-accent"
                  : "text-os-text hover:text-os-text-high hover:bg-os-elevated",
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
                  layoutId="sidebar-active"
                  className="ml-auto w-1 h-1 rounded-full bg-os-accent"
                  transition={{ duration: 0.2 }}
                />
              )}
            </Link>
          );
        })}
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
  );
}
