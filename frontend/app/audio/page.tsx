"use client";

import { useState, useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  Mic, Music, Search, Upload, Loader2, CheckCircle2, XCircle,
  Archive, Trash2, Play, Pause, ChevronDown, ChevronRight,
  Clock, Tag, Zap, Eye, Filter,
} from "lucide-react";
import { api } from "@/services/api";
import { PageTransition, StaggerItem } from "@/components/animations/page-transition";
import { CardSkeleton } from "@/components/animations/skeleton";
import { cn, formatDate, importanceColor } from "@/lib/utils";
import type { Memory, AudioUploadResult } from "@/types";

export default function AudioPage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // State
  const [query, setQuery] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResults, setUploadResults] = useState<AudioUploadResult | null>(null);

  // Query audio memories
  const { data: memories, isLoading } = useQuery({
    queryKey: ["audio-memories", query],
    queryFn: () => api.audio.list({ q: query || undefined, limit: 50 }),
    refetchInterval: 15000,
  });

  // Mutations
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.audio.softDelete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["audio-memories"] }),
  });

  const archiveMutation = useMutation({
    mutationFn: (id: string) => api.audio.archive(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["audio-memories"] }),
  });

  // Upload handler
  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    setUploading(true);
    try {
      const result = await api.audio.upload(files);
      setUploadResults(result);
      queryClient.invalidateQueries({ queryKey: ["audio-memories"] });
    } catch {
      // handled by UI
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const typeLabel: Record<string, string> = {
    episodic: "情景", semantic: "语义", procedural: "程序", reflect: "反思", working: "工作区",
  };
  const statusLabel: Record<string, string> = {
    active: "活跃", archived: "已归档", merged: "已合并", deleted: "已删除",
  };

  return (
    <PageTransition>
      <div className="p-6 space-y-4 max-w-[1440px] mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight">音频记忆</h1>
            <p className="text-xs text-os-subtle mt-0.5">
              {memories ? `${memories.length} 条音频记忆` : "加载中..."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* Upload button */}
            <input
              ref={fileInputRef}
              type="file"
              accept="audio/*"
              multiple
              className="hidden"
              onChange={handleUpload}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="flex items-center gap-2 px-3 py-2 rounded-md bg-os-accent text-white text-xs font-medium hover:bg-os-accent/90 transition-colors disabled:opacity-50"
            >
              {uploading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Upload size={14} />
              )}
              上传音频
            </button>
          </div>
        </div>

        {/* Upload results */}
        <AnimatePresence>
          {uploadResults && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="os-card border-emerald-200 bg-emerald-50 p-4"
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-medium text-emerald-700">
                  上传完成 — {uploadResults.total_tasks_enqueued} 个记忆任务已入队
                </span>
                <button
                  onClick={() => setUploadResults(null)}
                  className="text-2xs text-os-subtle hover:text-os-text"
                >
                  关闭
                </button>
              </div>
              <div className="space-y-2">
                {uploadResults.items.map((item) => (
                  <div key={item.file_id} className="flex items-start gap-3 text-2xs">
                    <Music size={12} className="text-os-subtle mt-0.5 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-os-text-high font-medium truncate">{item.filename}</p>
                      <p className="text-os-subtle">{item.analysis.summary}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-os-subtle">{item.analysis.topic}</span>
                        <span className="text-os-subtle">|</span>
                        <span className="text-os-subtle">{item.analysis.sentiment}</span>
                        {item.analysis.duration_seconds > 0 && (
                          <>
                            <span className="text-os-subtle">|</span>
                            <span className="text-os-subtle">{Math.round(item.analysis.duration_seconds)}s</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Search */}
        <div className="flex items-center gap-2">
          <div className="flex-1 relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-os-muted" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索音频记忆..."
              className="w-full h-9 pl-9 pr-4 bg-os-surface border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-subtle focus:outline-none focus:border-os-accent"
            />
          </div>
        </div>

        {/* Audio Memories List */}
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (<CardSkeleton key={i} />))}
          </div>
        ) : !memories || memories.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24">
            <Mic size={48} className="mb-4 text-slate-500" />
            <p className="text-sm text-os-text-high">
              {query.trim() ? "未找到匹配的音频记忆" : "暂无音频记忆"}
            </p>
            <p className="mt-1 text-2xs text-os-subtle">
              {query.trim() ? "请尝试调整搜索关键词" : "上传音频文件开始记录"}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {memories.map((mem, i) => (
              <motion.div
                key={mem.id}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03 }}
                className={cn(
                  "os-card p-4 os-card-hover transition-colors",
                  mem.status === "archived" && "bg-os-surface-muted"
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  {/* Icon */}
                  <div className={cn(
                    "w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
                    mem.memory_type === "reflect" ? "bg-amber-50" :
                    mem.memory_type === "semantic" ? "bg-emerald-50" :
                    "bg-indigo-50"
                  )}>
                    <Music size={14} className={cn(
                      mem.memory_type === "reflect" ? "text-amber-700" :
                      mem.memory_type === "semantic" ? "text-emerald-700" :
                      "text-indigo-700"
                    )} />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-2xs font-medium text-os-text-high">
                        {typeLabel[mem.memory_type] || mem.memory_type}
                      </span>
                      {mem.status !== "active" && (
                        <span className="rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-2xs text-amber-800">
                          {statusLabel[mem.status] || mem.status}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-os-text leading-relaxed line-clamp-3">
                      {mem.summary || mem.content.slice(0, 200)}
                    </p>

                    {/* Entities */}
                    {mem.entities.length > 0 && (
                      <div className="flex gap-1 mt-1.5 flex-wrap">
                        {mem.entities.slice(0, 5).map((e) => (
                          <span key={e} className="rounded bg-os-elevated px-1 py-0.5 text-2xs text-os-subtle">
                            {e}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Footer */}
                    <div className="mt-2 flex items-center gap-3 text-2xs text-os-subtle">
                      <span className="flex items-center gap-1">
                        <Clock size={10} />{formatDate(mem.timestamp)}
                      </span>
                      <span className="flex items-center gap-1">
                        <Eye size={10} />{mem.access_count}
                      </span>
                      <span className={cn("font-mono", importanceColor(mem.importance))}>
                        重要性 {mem.importance}
                      </span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 shrink-0">
                    {mem.status === "active" && (
                      <>
                        <button
                          onClick={() => archiveMutation.mutate(mem.id)}
                          disabled={archiveMutation.isPending}
                          className="p-1.5 rounded text-os-muted transition-colors hover:bg-os-elevated hover:text-amber-700"
                          title="归档"
                        >
                          <Archive size={13} />
                        </button>
                        <button
                          onClick={() => deleteMutation.mutate(mem.id)}
                          disabled={deleteMutation.isPending}
                          className="p-1.5 rounded text-os-muted transition-colors hover:bg-os-elevated hover:text-red-700"
                          title="删除"
                        >
                          <Trash2 size={13} />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </PageTransition>
  );
}
