"use client";

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  BrainCircuit, Layers, Clock, Sparkles, Search,
  RefreshCw, Cpu,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { PageTransition } from "@/components/animations/page-transition";
import { cn } from "@/lib/utils";
import { api } from "@/services/api";
import { MemoryOverview } from "@/components/memory-console/MemoryOverview";
import { MemoryFlowTimeline } from "@/components/memory-console/MemoryFlowTimeline";
import { ReflectionPanel } from "@/components/memory-console/ReflectionPanel";
import { VectorInspector } from "@/components/memory-console/VectorInspector";

type TabId = "overview" | "timeline" | "reflection" | "retrieval";

const TABS: { id: TabId; label: string; icon: typeof Layers; hint: string }[] = [
  { id: "overview", label: "记忆 Overview", icon: Layers, hint: "STM / WM / LTM 三层认知" },
  { id: "timeline", label: "记忆 Flow", icon: Clock, hint: "记忆流转时间线" },
  { id: "reflection", label: "Reflection Engine", icon: Sparkles, hint: "冲突修复与洞察" },
  { id: "retrieval", label: "Retrieval Inspector", icon: Search, hint: "向量检索探针" },
];

export default function MemoryIntelligenceConsolePage() {
  const [active, setActive] = useState<TabId>("overview");
  const [visited, setVisited] = useState<Set<TabId>>(new Set(["overview"]));

  // 共享元数据：dashboard summary 提供全局记忆统计
  const { data: summary, refetch, isFetching } = useQuery({
    queryKey: ["memory-console-summary"],
    queryFn: () => api.dashboard.summary(),
    refetchInterval: 30000,
  });

  const select = useCallback((id: TabId) => {
    setActive(id);
    setVisited((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  }, []);

  const renderTab = (id: TabId) => {
    switch (id) {
      case "overview": return <MemoryOverview summary={summary} />;
      case "timeline": return <MemoryFlowTimeline />;
      case "reflection": return <ReflectionPanel />;
      case "retrieval": return <VectorInspector />;
    }
  };

  return (
    <PageTransition>
      <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
        {/* ── Header ── */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight flex items-center gap-2">
              <BrainCircuit size={16} className="text-violet-400" />
              Memory Intelligence Console
            </h1>
            <p className="text-xs text-os-subtle mt-0.5">
              认知系统控制面 — STM · WM · LTM · Reflection · Vector Retrieval
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* 认知状态指示 */}
            <div className="flex items-center gap-2 px-2.5 py-1 rounded-md border border-os-border bg-os-surface">
              <Cpu size={11} className="text-violet-400" />
              <span className="text-2xs text-os-subtle font-mono">
                {summary ? `${summary.total_memories} memories · ${summary.episodic_count}E/${summary.semantic_count}S/${summary.reflect_count}R` : "loading..."}
              </span>
            </div>
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="flex items-center gap-1.5 h-7 px-2.5 rounded-md border border-os-border bg-os-surface text-2xs text-os-subtle hover:text-os-text-high hover:border-os-muted transition-colors disabled:opacity-50"
            >
              <RefreshCw size={11} className={isFetching ? "animate-spin" : ""} />
              刷新
            </button>
          </div>
        </div>

        {/* ── 认知边界声明 ── */}
        <div className="rounded-md border border-violet-400/20 bg-violet-400/[0.03] px-3 py-2">
          <p className="text-2xs leading-5 text-violet-200/80">
            <span className="font-medium text-violet-300">认知平面 · </span>
            Memory ≠ Logs — 此面板展示记忆的结构、流转与检索质量，而非简单的写入日志。STM/WM/LTM 三层由 memory_type · status · importance · access_count 综合推断。
          </p>
        </div>

        {/* ── Tabs ── */}
        <div className="flex items-center gap-1 border-b border-os-border overflow-x-auto">
          {TABS.map((tab) => {
            const isActive = active === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => select(tab.id)}
                className={cn(
                  "relative flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors whitespace-nowrap",
                  isActive ? "text-os-text-high" : "text-os-subtle hover:text-os-text",
                )}
              >
                <tab.icon size={13} />
                <span>{tab.label}</span>
                {isActive && (
                  <motion.div
                    layoutId="memory-console-tab"
                    className="absolute left-0 right-0 -bottom-px h-0.5 bg-violet-400"
                    transition={{ duration: 0.2 }}
                  />
                )}
              </button>
            );
          })}
        </div>

        {/* ── Tab panels ── */}
        {TABS.map((tab) => (
          <div key={tab.id} className={cn(active === tab.id ? "block" : "hidden")}>
            {visited.has(tab.id) && renderTab(tab.id)}
          </div>
        ))}
      </div>
    </PageTransition>
  );
}
