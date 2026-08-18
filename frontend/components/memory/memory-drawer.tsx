"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  X, Clock, Tag, Eye, Zap, Archive, Trash2, Save, Edit3,
} from "lucide-react";
import { api } from "@/services/api";
import { cn, formatDate, importanceColor } from "@/lib/utils";

const typeLabel: Record<string, string> = {
  episodic: "情景记忆",
  semantic: "语义记忆",
  procedural: "程序记忆",
  reflect: "反思洞察",
};

const sourceLabel: Record<string, string> = {
  user: "用户", agent: "智能体", reflect: "反思",
};

const statusLabel: Record<string, string> = {
  active: "活跃",
  archived: "已归档",
  merged: "已合并",
  deleted: "已删除",
};

const statusStyle: Record<string, string> = {
  active: "text-os-success",
  archived: "text-os-warning",
  merged: "text-os-subtle",
  deleted: "text-os-danger",
};

function readableImportanceColor(score: number) {
  return importanceColor(score)
    .replace("text-emerald-400", "text-os-success")
    .replace("text-amber-400", "text-os-warning")
    .replace("text-zinc-500", "text-os-subtle");
}

interface MemoryDrawerProps {
  memoryId: string | null;
  onClose: () => void;
  onArchived?: () => void;
  onDeleted?: () => void;
}

export function MemoryDrawer({ memoryId, onClose, onArchived, onDeleted }: MemoryDrawerProps) {
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [editSummary, setEditSummary] = useState("");
  const [editImportance, setEditImportance] = useState(5);
  const queryClient = useQueryClient();

  const { data: memory, isLoading } = useQuery({
    queryKey: ["memory-detail", memoryId],
    queryFn: () => api.memory.getById(memoryId!),
    enabled: !!memoryId,
  });

  useEffect(() => {
    if (memory) {
      setEditContent(memory.content);
      setEditSummary(memory.summary || "");
      setEditImportance(memory.importance);
    }
  }, [memory]);

  // Mutations
  const updateMutation = useMutation({
    mutationFn: () => api.memory.update(memoryId!, {
      content: editContent || undefined,
      summary: editSummary || undefined,
      importance: editImportance,
    }),
    onSuccess: () => {
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: ["memory-detail", memoryId] });
      queryClient.invalidateQueries({ queryKey: ["memories"] });
    },
  });

  const archiveMutation = useMutation({
    mutationFn: () => api.memory.archive(memoryId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["memory-detail", memoryId] });
      queryClient.invalidateQueries({ queryKey: ["memories"] });
      onArchived?.();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.memory.softDelete(memoryId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["memories"] });
      onDeleted?.();
      onClose();
    },
  });

  return (
    <AnimatePresence>
      {memoryId && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-slate-950/20 z-40"
            onClick={onClose}
          />

          {/* Drawer */}
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="fixed right-0 top-0 bottom-0 w-full max-w-lg bg-os-surface border-l border-os-border z-50 overflow-y-auto shadow-os-lg"
          >
            {/* Header */}
            <div className="sticky top-0 bg-os-surface border-b border-os-border px-5 py-3 flex items-center justify-between z-10">
              <h2 className="text-sm font-semibold text-os-text-high">记忆详情</h2>
              <button onClick={onClose} className="p-1.5 rounded hover:bg-os-elevated transition-colors">
                <X size={16} className="text-os-subtle" />
              </button>
            </div>

            <div className="p-5 space-y-5">
              {isLoading ? (
                <div className="space-y-3 animate-pulse">
                  <div className="h-4 bg-os-elevated rounded w-20" />
                  <div className="h-24 bg-os-elevated rounded" />
                  <div className="h-3 bg-os-elevated rounded w-32" />
                </div>
              ) : memory ? (
                <>
                  {/* Edit toggle */}
                  <div className="flex items-center justify-between gap-3">
                    <span className={cn("os-badge min-w-0 max-w-[70%] truncate", memory.source === "user" ? "bg-indigo-400/10 text-indigo-700" :
                      memory.source === "reflect" ? "bg-amber-400/10 text-amber-800" : "bg-emerald-400/10 text-emerald-700")}>
                      {sourceLabel[memory.source] || memory.source}
                    </span>
                    <button
                      onClick={() => setEditing(!editing)}
                      className={cn(
                        "flex items-center gap-1.5 px-3 py-1.5 rounded text-xs transition-colors",
                        editing
                          ? "bg-os-accent/20 text-os-accent"
                          : "text-os-subtle hover:text-os-text hover:bg-os-elevated"
                      )}
                    >
                      <Edit3 size={12} />
                      {editing ? "取消编辑" : "编辑"}
                    </button>
                  </div>

                  {/* Content */}
                  {editing ? (
                    <div className="space-y-3">
                      <label className="text-2xs text-os-subtle uppercase tracking-wider">内容</label>
                      <textarea
                        value={editContent}
                        onChange={(e) => setEditContent(e.target.value)}
                        rows={6}
                        className="w-full p-3 rounded-md bg-os-elevated border border-os-border text-xs text-os-text-high resize-none focus:outline-none focus:border-os-accent"
                      />
                      <label className="text-2xs text-os-subtle uppercase tracking-wider">摘要</label>
                      <input
                        value={editSummary}
                        onChange={(e) => setEditSummary(e.target.value)}
                        className="w-full p-2.5 rounded-md bg-os-elevated border border-os-border text-xs text-os-text-high focus:outline-none focus:border-os-accent"
                      />
                      <label className="text-2xs text-os-subtle uppercase tracking-wider">
                        重要性 ({editImportance}/10)
                      </label>
                      <input
                        type="range"
                        min={1} max={10}
                        value={editImportance}
                        onChange={(e) => setEditImportance(Number(e.target.value))}
                        className="w-full accent-indigo-400"
                      />
                      <button
                        onClick={() => updateMutation.mutate()}
                        disabled={updateMutation.isPending}
                        className="flex items-center gap-2 px-4 py-2 rounded bg-os-accent text-white text-xs font-medium hover:bg-os-accent/90 transition-colors disabled:opacity-50"
                      >
                        <Save size={13} />
                        {updateMutation.isPending ? "保存中..." : "保存修改"}
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-os-text-high [overflow-wrap:anywhere]">
                        {memory.content}
                      </p>
                      {memory.summary && (
                        <div className="border-l-2 border-os-accent/30 pl-3 py-1">
                          <p className="break-words text-xs text-os-subtle [overflow-wrap:anywhere]">{memory.summary}</p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Metadata */}
                  <div className="grid grid-cols-1 gap-3 text-2xs sm:grid-cols-2">
                    <div className="os-card flex min-w-0 items-center gap-2 p-2.5">
                      <Clock size={12} className="text-os-subtle" />
                      <div className="min-w-0">
                        <p className="text-os-subtle">时间</p>
                        <p className="break-words text-os-text-high">{formatDate(memory.timestamp)}</p>
                      </div>
                    </div>
                    <div className="os-card flex min-w-0 items-center gap-2 p-2.5">
                      <Zap size={12} className={readableImportanceColor(memory.importance)} />
                      <div className="min-w-0">
                        <p className="text-os-subtle">重要性</p>
                        <p className={cn("font-mono", readableImportanceColor(memory.importance))}>
                          {memory.importance}/10
                        </p>
                      </div>
                    </div>
                    <div className="os-card flex min-w-0 items-center gap-2 p-2.5">
                      <Eye size={12} className="text-os-subtle" />
                      <div className="min-w-0">
                        <p className="text-os-subtle">访问次数</p>
                        <p className="text-os-text-high font-mono">{memory.access_count}</p>
                      </div>
                    </div>
                    <div className="os-card flex min-w-0 items-center gap-2 p-2.5">
                      <Tag size={12} className="text-os-subtle" />
                      <div className="min-w-0">
                        <p className="text-os-subtle">类型</p>
                        <p className="break-all text-os-text-high">
                          {typeLabel[memory.memory_type] || memory.memory_type}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Entities */}
                  {memory.entities.length > 0 && (
                    <div>
                      <h3 className="text-2xs text-os-subtle uppercase tracking-wider mb-2">实体</h3>
                      <div className="flex flex-wrap gap-1.5">
                        {memory.entities.map((e) => (
                          <span key={e} className="max-w-full break-all rounded-full bg-os-elevated px-2 py-1 text-2xs text-os-subtle">
                            {e}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Relations */}
                  {memory.relations && memory.relations.length > 0 && (
                    <div>
                      <h3 className="text-2xs text-os-subtle uppercase tracking-wider mb-2">关系</h3>
                      <div className="space-y-1">
                        {memory.relations.map((rel, i) => (
                          <div key={i} className="flex min-w-0 flex-wrap items-center gap-1.5 text-2xs text-os-subtle">
                            <span className="max-w-full break-all text-os-accent">{rel.s}</span>
                            <span className="max-w-full break-all text-os-subtle">→ {rel.p} →</span>
                            <span className="max-w-full break-all text-os-accent">{rel.o}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Status */}
                  <div className="text-2xs text-os-subtle">
                    <span>状态：</span>
                    <span className={cn(
                      "font-medium",
                      statusStyle[memory.status] || "text-os-subtle"
                    )}>
                      {statusLabel[memory.status] || memory.status}
                    </span>
                    {memory.archived_at && (
                      <span className="ml-2">归档于 {formatDate(memory.archived_at)}</span>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex flex-wrap items-center gap-2 border-t border-os-border pt-3">
                    {memory.status === "active" && (
                      <button
                        onClick={() => archiveMutation.mutate()}
                        disabled={archiveMutation.isPending}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded text-2xs text-amber-800 hover:bg-amber-400/10 transition-colors disabled:opacity-50"
                      >
                        <Archive size={12} />
                        {archiveMutation.isPending ? "归档中..." : "归档"}
                      </button>
                    )}
                    {memory.status !== "deleted" && (
                      <button
                        onClick={() => deleteMutation.mutate()}
                        disabled={deleteMutation.isPending}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded text-2xs text-red-700 hover:bg-red-400/10 transition-colors disabled:opacity-50"
                      >
                        <Trash2 size={12} />
                        {deleteMutation.isPending ? "删除中..." : "删除"}
                      </button>
                    )}
                    <span className="text-2xs text-os-subtle ml-auto">
                      ID：{memory.id.slice(0, 8)}...
                    </span>
                  </div>
                </>
              ) : (
                <p className="py-8 text-center text-xs text-os-danger">记忆数据加载失败</p>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
