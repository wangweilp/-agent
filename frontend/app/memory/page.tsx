"use client";

import { useCallback, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence } from "framer-motion";
import { Archive, Brain, GitMerge, Grid3x3, List, Search, Sparkles, Table2 } from "lucide-react";
import { api } from "@/services/api";
import { PageTransition, StaggerItem } from "@/components/animations/page-transition";
import { CardSkeleton } from "@/components/animations/skeleton";
import { MemoryCard } from "@/components/memory/memory-card";
import { MemoryTimeline } from "@/components/memory/memory-timeline";
import { MemoryTable } from "@/components/memory/memory-table";
import { MemoryDrawer } from "@/components/memory/memory-drawer";
import { MemoryFilterBar } from "@/components/memory/memory-filter-bar";
import {
  EmptyState,
  OsBadge,
  OsButton,
  OsInput,
  PageHeader,
  PageShell,
  StatusBadge,
  Toolbar,
} from "@/components/ui/os";
import { tabStyles } from "@/styles/components";
import { cn } from "@/lib/utils";

type ViewMode = "grid" | "timeline" | "table";

const viewModes = [
  { mode: "grid" as const, icon: Grid3x3, label: "卡片" },
  { mode: "timeline" as const, icon: List, label: "时间线" },
  { mode: "table" as const, icon: Table2, label: "表格" },
];

export default function MemoryPage() {
  const queryClient = useQueryClient();

  const [query, setQuery] = useState("");
  const [semantic, setSemantic] = useState(false);
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [detailId, setDetailId] = useState<string | null>(null);

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

  const { data: memories, isLoading, isError } = useQuery({
    queryKey: ["memories", searchParams],
    queryFn: () => api.memory.search(searchParams),
    refetchInterval: 20000,
  });

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

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    if (!memories) return;
    if (selectedIds.size === memories.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(memories.map((memory) => memory.id)));
    }
  }, [memories, selectedIds.size]);

  const clearFilters = useCallback(() => {
    setTypeFilter("");
    setStatusFilter("");
    setDateFrom("");
    setDateTo("");
  }, []);

  return (
    <PageTransition>
      <PageShell>
        <PageHeader
          icon={Brain}
          title="记忆管理"
          subtitle={memories ? `共 ${memories.length} 条记忆。支持关键词、语义检索、批量合并与归档。` : "正在加载记忆索引。"}
          actions={
            <>
              <StatusBadge status={semantic ? "info" : "ready"}>{semantic ? "语义搜索" : "关键词搜索"}</StatusBadge>
              {selectedIds.size > 0 && <OsBadge variant="primary">{selectedIds.size} 已选</OsBadge>}
            </>
          }
        />

        <Toolbar>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              queryClient.invalidateQueries({ queryKey: ["memories"] });
            }}
            className="flex min-w-0 flex-1 flex-col gap-2 md:flex-row md:items-center"
          >
            <div className="relative min-w-0 flex-1">
              <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-os-muted" />
              <OsInput
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={semantic ? "语义搜索：输入自然语言描述..." : "搜索记忆关键词、实体名..."}
                className="w-full pl-9 md:pr-32"
                aria-label="搜索记忆"
              />
              <div className="mt-2 flex items-center gap-2 md:absolute md:right-1.5 md:top-1/2 md:mt-0 md:-translate-y-1/2">
                <OsButton type="button" variant={semantic ? "soft" : "ghost"} size="sm" onClick={() => setSemantic((value) => !value)}>
                  <Sparkles size={13} />
                  语义
                </OsButton>
                <OsButton type="submit" variant="primary" size="sm">
                  搜索
                </OsButton>
              </div>
            </div>
          </form>

          <div className="flex items-center gap-1 rounded-2xl border border-os-border bg-os-surface-tinted p-1">
            {viewModes.map(({ mode, icon: Icon, label }) => (
              <button
                key={mode}
                type="button"
                onClick={() => setViewMode(mode)}
                className={tabStyles({ active: viewMode === mode })}
                aria-label={`切换到${label}视图`}
                title={label}
              >
                <Icon size={15} />
              </button>
            ))}
          </div>

          {selectedIds.size > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              {selectedIds.size >= 2 && (
                <OsButton
                  type="button"
                  variant="soft"
                  size="sm"
                  onClick={() => mergeMutation.mutate()}
                  disabled={mergeMutation.isPending}
                >
                  <GitMerge size={13} />
                  合并
                </OsButton>
              )}
              <OsButton
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => batchArchiveMutation.mutate()}
                disabled={batchArchiveMutation.isPending}
              >
                <Archive size={13} />
                归档
              </OsButton>
            </div>
          )}
        </Toolbar>

        <MemoryFilterBar
          type={typeFilter}
          status={statusFilter}
          dateFrom={dateFrom}
          dateTo={dateTo}
          onTypeChange={setTypeFilter}
          onStatusChange={setStatusFilter}
          onDateFromChange={setDateFrom}
          onDateToChange={setDateTo}
          onClear={clearFilters}
          hasFilters={hasFilters}
        />

        {isLoading ? (
          <div className={cn(viewMode === "grid" ? "grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3" : "space-y-3")}>
            {Array.from({ length: 6 }).map((_, index) => (
              <CardSkeleton key={index} />
            ))}
          </div>
        ) : isError ? (
          <EmptyState
            icon={Brain}
            title="记忆加载失败"
            description="暂时无法读取记忆数据，请检查网络连接后重试。"
            className="min-h-[360px]"
          />
        ) : !memories || memories.length === 0 ? (
          <EmptyState
            icon={Brain}
            title="没有找到记忆"
            description="尝试调整搜索条件，或开始与智能体对话来创建新的记忆。"
            className="min-h-[360px]"
          />
        ) : (
          <>
            {viewMode === "grid" && (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                <AnimatePresence mode="popLayout">
                  {memories.map((memory, index) => (
                    <StaggerItem key={memory.id} delay={index * 0.02}>
                      <MemoryCard
                        memory={memory}
                        selected={selectedIds.has(memory.id)}
                        onToggleSelect={toggleSelect}
                        onClick={(id) => setDetailId(id)}
                      />
                    </StaggerItem>
                  ))}
                </AnimatePresence>
              </div>
            )}

            {viewMode === "timeline" && <MemoryTimeline memories={memories} />}

            {viewMode === "table" && (
              <MemoryTable
                memories={memories}
                selected={selectedIds}
                onToggleSelect={toggleSelect}
                onSelectAll={selectAll}
                onViewDetail={(id) => setDetailId(id)}
              />
            )}
          </>
        )}

        <MemoryDrawer
          memoryId={detailId}
          onClose={() => setDetailId(null)}
          onArchived={() => queryClient.invalidateQueries({ queryKey: ["memories"] })}
          onDeleted={() => queryClient.invalidateQueries({ queryKey: ["memories"] })}
        />
      </PageShell>
    </PageTransition>
  );
}
