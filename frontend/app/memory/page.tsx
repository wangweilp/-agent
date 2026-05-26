"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Brain, Calendar, SortAsc, Sparkles, Layers } from "lucide-react";
import { api } from "@/services/api";
import { PageTransition, StaggerItem } from "@/components/animations/page-transition";
import { MemoryCard } from "@/components/memory/memory-card";
import { MemoryTimeline } from "@/components/memory/memory-timeline";
import { CardSkeleton } from "@/components/animations/skeleton";
import type { Memory } from "@/types";

export default function MemoryPage() {
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"grid" | "timeline">("grid");
  const [filter, setFilter] = useState<string>("all");

  const { data: memories, isLoading } = useQuery({
    queryKey: ["memories", query],
    queryFn: () => api.memory.list({ q: query || undefined, limit: 50 }),
    refetchInterval: 15000,
  });

  const filtered = (memories || []).filter((m) =>
    filter === "all" ? true : m.memory_type === filter,
  );

  const typeCounts = (memories || []).reduce(
    (acc, m) => { acc[m.memory_type] = (acc[m.memory_type] || 0) + 1; return acc; },
    {} as Record<string, number>,
  );

  const filters = [
    { key: "all", label: "全部", count: memories?.length || 0 },
    { key: "episodic", label: "情景记忆", count: typeCounts.episodic || 0 },
    { key: "semantic", label: "语义记忆", count: typeCounts.semantic || 0 },
    { key: "reflect", label: "反思洞察", count: typeCounts.reflect || 0 },
  ];

  return (
    <PageTransition>
      <div className="p-6 space-y-6 max-w-[1440px] mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight">记忆</h1>
            <p className="text-xs text-os-subtle mt-0.5">AI 第二大脑 — 长期记忆存储与检索</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setView("grid")}
              className={`px-3 py-1.5 rounded-md text-xs transition-all ${view === "grid" ? "bg-os-accent/10 text-os-accent" : "text-os-subtle hover:text-os-text"}`}
            >
              <Layers size={14} className="inline mr-1" />卡片
            </button>
            <button
              onClick={() => setView("timeline")}
              className={`px-3 py-1.5 rounded-md text-xs transition-all ${view === "timeline" ? "bg-os-accent/10 text-os-accent" : "text-os-subtle hover:text-os-text"}`}
            >
              <Calendar size={14} className="inline mr-1" />时间线
            </button>
          </div>
        </div>

        {/* Search & Filters */}
        <div className="flex items-center gap-3">
          <div className="flex-1 relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-os-muted" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索记忆..."
              className="w-full h-9 pl-9 pr-4 bg-os-surface border border-os-border rounded-md text-sm text-os-text-high placeholder-os-muted outline-none focus:border-os-accent/50 transition-colors"
            />
          </div>
          <div className="flex items-center gap-1">
            {filters.map((f) => (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                className={`px-3 py-1.5 rounded-md text-xs whitespace-nowrap transition-all ${filter === f.key ? "bg-os-accent/10 text-os-accent" : "text-os-subtle hover:text-os-text"}`}
              >
                {f.label}
                <span className="ml-1 text-2xs opacity-60">{f.count}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Memory Grid */}
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
        ) : view === "grid" ? (
          <motion.div layout className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            <AnimatePresence mode="popLayout">
              {filtered.map((m, i) => (
                <StaggerItem key={m.id} delay={i * 0.03}>
                  <MemoryCard memory={m} />
                </StaggerItem>
              ))}
            </AnimatePresence>
          </motion.div>
        ) : (
          <MemoryTimeline memories={filtered} />
        )}

        {!isLoading && filtered.length === 0 && (
          <div className="text-center py-20">
            <Brain size={32} className="text-os-muted mx-auto mb-3" />
            <p className="text-os-subtle text-sm">暂无记忆数据</p>
            <p className="text-os-muted text-xs mt-1">开始与 Agent 对话，重要信息会自动存入长期记忆</p>
          </div>
        )}
      </div>
    </PageTransition>
  );
}
