"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search, LayoutDashboard, ShieldAlert, GitGraph, Code2,
  MessageSquare, Settings, type LucideIcon,
} from "lucide-react";
import { useUIStore } from "@/stores/ui-store";
import { cn } from "@/lib/utils";

// ── 命令定义 ──

interface Command {
  id: string;
  label: string;
  description?: string;
  icon: LucideIcon;
  action: () => void;
  keywords?: string;
}

const COMMANDS: Command[] = [
  {
    id: "nav-dashboard",
    label: "工作台",
    description: "认知工作台总览",
    icon: LayoutDashboard,
    action: () => { window.location.href = "/home"; },
    keywords: "dashboard 工作台 home",
  },
  {
    id: "nav-chat",
    label: "对话",
    description: "Agent 对话工作区",
    icon: MessageSquare,
    action: () => { window.location.href = "/chat"; },
    keywords: "chat 对话 agent",
  },
  {
    id: "nav-graph",
    label: "记忆图谱",
    description: "知识图谱可视化",
    icon: GitGraph,
    action: () => { window.location.href = "/graph"; },
    keywords: "graph 图谱 knowledge memory",
  },
  {
    id: "nav-runtime",
    label: "安全控制面",
    description: "Runtime Governance Dashboard",
    icon: ShieldAlert,
    action: () => { window.location.href = "/admin/runtime"; },
    keywords: "runtime admin security 安全 控制面",
  },
  {
    id: "nav-developer",
    label: "开发者中心",
    description: "Open Platform & API Keys",
    icon: Code2,
    action: () => { window.location.href = "/developer"; },
    keywords: "developer 开发者 api",
  },
  {
    id: "nav-settings",
    label: "账户设置",
    description: "个人账户与配置",
    icon: Settings,
    action: () => { window.location.href = "/account"; },
    keywords: "settings 账户 account",
  },
];

// ── CommandPalette ──

export function CommandPalette() {
  const { commandPaletteOpen, closeCommandPalette } = useUIStore();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // 过滤命令
  const filtered = useMemo(() => {
    if (!query.trim()) return COMMANDS;
    const q = query.toLowerCase();
    return COMMANDS.filter((cmd) =>
      cmd.label.toLowerCase().includes(q) ||
      cmd.description?.toLowerCase().includes(q) ||
      cmd.keywords?.toLowerCase().includes(q),
    );
  }, [query]);

  // 重置选中索引当过滤结果变化
  useEffect(() => {
    setActiveIndex(0);
  }, [filtered.length]);

  // 打开时聚焦输入框
  useEffect(() => {
    if (commandPaletteOpen) {
      setQuery("");
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [commandPaletteOpen]);

  // 键盘导航
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const cmd = filtered[activeIndex];
      if (cmd) {
        cmd.action();
        closeCommandPalette();
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeCommandPalette();
    }
  };

  return (
    <AnimatePresence>
      {commandPaletteOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] px-4"
          onClick={closeCommandPalette}
        >
          {/* 遮罩 */}
          <div className="absolute inset-0 bg-os-base/60 backdrop-blur-sm" />

          {/* 面板 */}
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -8 }}
            transition={{ duration: 0.15 }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-full max-w-2xl rounded-2xl border border-os-border/50 bg-os-surface/95 backdrop-blur-xl shadow-os-lg overflow-hidden"
          >
            {/* 搜索输入区 */}
            <div className="flex items-center gap-3 px-5 py-4 border-b border-os-border/30">
              <Search size={20} className="text-os-muted shrink-0" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="搜索命令或跳转页面..."
                className="flex-1 bg-transparent text-xl text-os-text-high placeholder-os-muted outline-none"
              />
              <kbd className="shrink-0 px-2 py-0.5 rounded-md border border-os-border/50 bg-os-elevated text-2xs text-os-muted font-mono">
                ESC
              </kbd>
            </div>

            {/* 命令列表 */}
            <div className="max-h-80 overflow-y-auto p-2">
              {filtered.length === 0 ? (
                <div className="py-10 text-center">
                  <Search size={24} className="mx-auto text-os-muted/50 mb-2" />
                  <p className="text-sm text-os-muted">未找到匹配的命令</p>
                </div>
              ) : (
                filtered.map((cmd, i) => {
                  const Icon = cmd.icon;
                  return (
                    <button
                      key={cmd.id}
                      onClick={() => {
                        cmd.action();
                        closeCommandPalette();
                      }}
                      onMouseEnter={() => setActiveIndex(i)}
                      className={cn(
                        "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-left",
                        i === activeIndex
                          ? "bg-os-accent/10 text-os-text-high"
                          : "text-os-text hover:bg-os-elevated",
                      )}
                    >
                      <Icon size={16} className={cn("shrink-0", i === activeIndex ? "text-os-accent" : "text-os-subtle")} />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">{cmd.label}</p>
                        {cmd.description && (
                          <p className="text-2xs text-os-muted truncate">{cmd.description}</p>
                        )}
                      </div>
                      {i === activeIndex && (
                        <kbd className="shrink-0 px-1.5 py-0.5 rounded border border-os-border/50 bg-os-elevated text-2xs text-os-muted font-mono">
                          ↵
                        </kbd>
                      )}
                    </button>
                  );
                })
              )}
            </div>

            {/* 底部提示栏 */}
            <div className="flex items-center justify-between px-4 py-2 border-t border-os-border/30 bg-os-elevated/30">
              <div className="flex items-center gap-3 text-2xs text-os-muted">
                <span className="flex items-center gap-1">
                  <kbd className="px-1 py-0.5 rounded border border-os-border/50 bg-os-elevated font-mono">↑↓</kbd>
                  导航
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1 py-0.5 rounded border border-os-border/50 bg-os-elevated font-mono">↵</kbd>
                  选择
                </span>
              </div>
              <span className="text-2xs text-os-subtle font-mono">知维 OS · Command Palette</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ── 全局键盘监听 Hook（Cmd+K / Ctrl+K） ──

export function useGlobalCommandShortcut() {
  const toggleCommandPalette = useUIStore((s) => s.toggleCommandPalette);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Cmd+K (Mac) 或 Ctrl+K (Windows/Linux)
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        toggleCommandPalette();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [toggleCommandPalette]);
}
