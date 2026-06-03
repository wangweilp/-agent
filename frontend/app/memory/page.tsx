"use client";

import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence } from "framer-motion";
import {
  Brain, Search, Grid3x3, List, Table2, GitMerge, Archive, Sparkles,
} from "lucide-react";
import { api } from "@/services/api";
import { PageTransition, StaggerItem } from "@/components/animations/page-transition";
import { CardSkeleton } from "@/components/animations/skeleton";
import { MemoryCard } from "@/components/memory/memory-card";
import { MemoryTimeline } from "@/components/memory/memory-timeline";
import { MemoryTable } from "@/components/memory/memory-table";
import { MemoryDrawer } from "@/components/memory/memory-drawer";
import { MemoryFilterBar } from "@/components/memory/memory-filter-bar";
import { cn } from "@/lib/utils";

type ViewMode = "grid" | "timeline" | "table";

export default function MemoryPage() {
  const queryClient = useQueryClient();

  // Search state
  const [query, setQuery] = useState("");
  const [semantic, setSemantic] = useState(false);
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [detailId, setDetailId] = useState<string | null>(null);

  // Build search params
  const searchParams = {
    q: query || undefined,
    type: typeFilter || undefined,
    status: statusFilter || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    semantic,
    limit: 100,
  };
  const hasFilters = !!(typeFilter || statusFilter || dateFrom || dateTo);

  // Data fetch — use /memory/search
  const { data: memories, isLoading } = useQuery({
    queryKey: ["memories", searchParams],
    queryFn: () => api.memory.search(searchParams),
    refetchInterval: 20000,
  });

  // Mutations
  const mergeMutation = useMutation({
    mutationFn: async () => {
      const ids = Array.from(selectedIds);
      if (ids.length < 2) return;
      return api.memory.merge({ primary_id: ids[0], secondary_ids: ids.slice(1) });
    },
    onSuccess: () => {
      setSelectedIds(new Set());
      queryClient.invalidateQueries({ queryKey: ["memories"] });
    },
  });

  const batchArchiveMutation = useMutation({
    mutationFn: async () => {
      for (const id of selectedIds) await api.memory.archive(id);
    },
    onSuccess: () => {
      setSelectedIds(new Set());
      queryClient.invalidateQueries({ queryKey: ["memories"] });
    },
  });

  // Selection handlers
  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    if (!memories) return;
    if (selectedIds.size === memories.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(memories.map((m) => m.id)));
    }
  }, [memories, selectedIds.size]);

  const clearFilters = useCallback(() => {
    setTypeFilter(""); setStatusFilter("");
    setDateFrom(""); setDateTo("");
  }, []);

  return (
    <PageTransition>
      <div className="p-6 space-y-4 max-w-[1440px] mx-auto">
        {/* ── Header ── */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight">记忆搜索中心</h1>
            <p className="text-xs text-os-subtle mt-0.5">
              {memories ? `共 ${memories.length} 条记忆` : "加载中..."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* View toggle */}
            <div className="flex items-center gap-0.5 bg-os-surface rounded-md border border-os-border p-0.5">
              {([
                { mode: "grid" as const, icon: Grid3x3, label: "卡片" },
                { mode: "timeline" as const, icon: List, label: "时间线" },
                { mode: "table" as const, icon: Table2, label: "表格" },
              ]).map(({ mode, icon: Icon, label }) => (
                <button
                  key={mode}
                  onClick={() => setViewMode(mode)}
                  className={cn(
                    "p-1.5 rounded transition-colors",
                    viewMode === mode
                      ? "bg-os-elevated text-os-text-high"
                      : "text-os-muted hover:text-os-subtle"
                  )}
                  title={label}
                >
                  <Icon size={14} />
                </button>
              ))}
            </div>

            {/* Bulk actions */}
            {selectedIds.size > 0 && (
              <div className="flex items-center gap-1.5 ml-2">
                <span className="text-2xs text-os-muted">{selectedIds.size} 已选</span>
                {selectedIds.size >= 2 && (
                  <button
                    onClick={() => mergeMutation.mutate()}
                    disabled={mergeMutation.isPending}
                    className="flex items-center gap-1 px-2.5 py-1.5 rounded text-2xs bg-os-accent/20 text-os-accent hover:bg-os-accent/30 transition-colors disabled:opacity-50"
                  >
                    <GitMerge size={11} />合并
                  </button>
                )}
                <button
                  onClick={() => batchArchiveMutation.mutate()}
                  disabled={batchArchiveMutation.isPending}
                  className="flex items-center gap-1 px-2.5 py-1.5 rounded text-2xs bg-amber-400/10 text-amber-400 hover:bg-amber-400/20 transition-colors disabled:opacity-50"
                >
                  <Archive size={11} />归档
                </button>
              </div>
            )}
          </div>
        </div>

        {/* ── Search Bar ── */}
        <form onSubmit={(e) => { e.preventDefault(); queryClient.invalidateQueries({ queryKey: ["memories"] }); }}
          className="flex items-center gap-2">
          <div className="flex-1 relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-os-muted" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={semantic ? "语义搜索 — 输入自然语言描述..." : "搜索记忆关键词、实体名..."}
              className="w-full h-9 pl-9 pr-24 bg-os-surface border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
            />
            <div className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center gap-1">
              <button
                type="button"
                onClick={() => setSemantic(!semantic)}
                className={cn(
                  "flex items-center gap-1 px-2 py-1 rounded text-2xs transition-colors",
                  semantic ? "bg-os-accent/20 text-os-accent" : "text-os-muted hover:text-os-subtle"
                )}
                title="语义搜索"
              >
                <Sparkles size={11} />语义
              </button>
              <button type="submit"
                className="px-3 py-1 rounded bg-os-accent text-white text-2xs font-medium hover:bg-os-accent/90 transition-colors">
                搜索
              </button>
            </div>
          </div>
        </form>

        {/* ── Filter Bar ── */}
        <MemoryFilterBar
          type={typeFilter} status={statusFilter}
          dateFrom={dateFrom} dateTo={dateTo}
          onTypeChange={setTypeFilter} onStatusChange={setStatusFilter}
          onDateFromChange={setDateFrom} onDateToChange={setDateTo}
          onClear={clearFilters} hasFilters={hasFilters}
        />

        {/* ── Content ── */}
        {isLoading ? (
          <div className={cn(
            viewMode === "grid" ? "grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3" : "space-y-3"
          )}>
            {Array.from({ length: 6 }).map((_, i) => (<CardSkeleton key={i} />))}
          </div>
        ) : !memories || memories.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-os-muted">
            <Brain size={48} className="mb-4 opacity-30" />
            <p className="text-sm">没有找到记忆</p>
            <p className="text-2xs mt-1">尝试调整搜索条件或开始与 Agent 对话以创建新记忆</p>
          </div>
        ) : (
          <>
            {viewMode === "grid" && (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                <AnimatePresence mode="popLayout">
                  {memories.map((mem, i) => (
                    <StaggerItem key={mem.id} delay={i * 0.02}>
                      <MemoryCard
                        memory={mem}
                        selected={selectedIds.has(mem.id)}
                        onToggleSelect={toggleSelect}
                        onClick={(id) => setDetailId(id)}
                      />
                    </StaggerItem>
                  ))}
                </AnimatePresence>
              </div>
            )}

            {viewMode === "timeline" && (
              <MemoryTimeline memories={memories} />
            )}

            {viewMode === "table" && (
              <MemoryTable
                memories={memories} selected={selectedIds}
                onToggleSelect={toggleSelect} onSelectAll={selectAll}
                onViewDetail={(id) => setDetailId(id)}
              />
            )}
          </>
        )}

        {/* ── Detail Drawer ── */}
        <MemoryDrawer
          memoryId={detailId}
          onClose={() => setDetailId(null)}
          onArchived={() => queryClient.invalidateQueries({ queryKey: ["memories"] })}
          onDeleted={() => queryClient.invalidateQueries({ queryKey: ["memories"] })}
        />
      </div>
    </PageTransition>
  );
}
