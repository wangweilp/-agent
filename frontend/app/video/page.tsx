"use client";

import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  Video, Search, Upload, Loader2, Archive, Trash2,
  Clock, Tag, Eye, Film, FileVideo,
} from "lucide-react";
import { api } from "@/services/api";
import { PageTransition } from "@/components/animations/page-transition";
import { CardSkeleton } from "@/components/animations/skeleton";
import { cn, formatDate, importanceColor } from "@/lib/utils";
import type { Memory, VideoUploadResult } from "@/types";

const typeLabel: Record<string, string> = {
  episodic: "情景", semantic: "语义", procedural: "程序", reflect: "反思", working: "工作区",
};

export default function VideoPage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadResults, setUploadResults] = useState<VideoUploadResult | null>(null);

  const { data: memories, isLoading } = useQuery({
    queryKey: ["video-memories", query],
    queryFn: () => api.video.list({ q: query || undefined, limit: 50 }),
    refetchInterval: 15000,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.video.softDelete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["video-memories"] }),
  });

  const archiveMutation = useMutation({
    mutationFn: (id: string) => api.video.archive(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["video-memories"] }),
  });

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    setUploading(true);
    try {
      const result = await api.video.upload(files);
      setUploadResults(result);
      queryClient.invalidateQueries({ queryKey: ["video-memories"] });
    } catch { /* UI handled */ }
    finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <PageTransition>
      <div className="p-6 space-y-4 max-w-[1440px] mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight">视频记忆</h1>
            <p className="text-xs text-os-subtle mt-0.5">
              {memories ? `${memories.length} 条视频记忆` : "加载中..."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input ref={fileInputRef} type="file" accept="video/*" multiple
              className="hidden" onChange={handleUpload} />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="flex items-center gap-2 px-3 py-2 rounded-md bg-os-accent text-white text-xs font-medium hover:bg-os-accent/90 transition-colors disabled:opacity-50"
            >
              {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              上传视频
            </button>
          </div>
        </div>

        {/* Upload results */}
        <AnimatePresence>
          {uploadResults && (
            <motion.div
              initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className="os-card border-emerald-200 bg-emerald-50 p-4"
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-medium text-emerald-700">
                  上传完成 — {uploadResults.total_tasks_enqueued} 个记忆任务
                </span>
                <button onClick={() => setUploadResults(null)}
                  className="text-2xs text-os-subtle hover:text-os-text">关闭</button>
              </div>
              <div className="space-y-2">
                {uploadResults.items.map((item) => (
                  <div key={item.file_id}
                    className="flex items-start gap-3 p-3 rounded bg-os-elevated/50 text-2xs">
                    <FileVideo size={14} className="mt-0.5 shrink-0 text-violet-700" />
                    <div className="min-w-0 flex-1">
                      <p className="text-os-text-high font-medium truncate">{item.filename}</p>
                      <p className="text-os-subtle">{item.analysis.summary}</p>
                      <div className="mt-0.5 flex items-center gap-2 text-os-subtle">
                        <span>{item.analysis.topic}</span>
                        <span>|</span>
                        <span>{item.analysis.duration_seconds > 0
                          ? `${Math.round(item.analysis.duration_seconds / 60)}m` : "?"}</span>
                        <span>|</span>
                        <span>{item.analysis.keyframe_count} 关键帧</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Search */}
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-os-muted" />
          <input value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索视频记忆..."
            className="w-full h-9 pl-9 pr-4 bg-os-surface border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-subtle focus:outline-none focus:border-os-accent" />
        </div>

        {/* Content */}
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (<CardSkeleton key={i} />))}
          </div>
        ) : !memories || memories.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24">
            <Video size={48} className="mb-4 text-slate-500" />
            <p className="text-sm text-os-text-high">
              {query.trim() ? "未找到匹配的视频记忆" : "暂无视频记忆"}
            </p>
            <p className="mt-1 text-2xs text-os-subtle">
              {query.trim() ? "请尝试调整搜索关键词" : "上传视频文件开始分析"}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {memories.map((mem) => (
              <motion.div key={mem.id}
                initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.02 }}
                className={cn("os-card p-4 os-card-hover", mem.status === "archived" && "bg-os-surface-muted")}>
                <div className="flex items-start gap-3">
                  <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
                    mem.memory_type === "reflect" ? "bg-amber-50" :
                    mem.memory_type === "semantic" ? "bg-emerald-50" : "bg-violet-50")}>
                    <Film size={14} className={mem.memory_type === "reflect" ? "text-amber-700" :
                      mem.memory_type === "semantic" ? "text-emerald-700" : "text-violet-700"} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-2xs font-medium text-os-text-high">
                        {typeLabel[mem.memory_type] || mem.memory_type}
                      </span>
                      {mem.status === "archived" && (
                        <span className="rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-2xs text-amber-800">已归档</span>
                      )}
                    </div>
                    <p className="text-xs text-os-text line-clamp-3">
                      {mem.summary || mem.content.slice(0, 200)}
                    </p>
                    {mem.entities.length > 0 && (
                      <div className="flex gap-1 mt-1.5 flex-wrap">
                        {mem.entities.slice(0, 5).map((e) => (
                          <span key={e} className="rounded bg-os-elevated px-1 py-0.5 text-2xs text-os-subtle">{e}</span>
                        ))}
                      </div>
                    )}
                    <div className="mt-2 flex items-center gap-3 text-2xs text-os-subtle">
                      <span className="flex items-center gap-1"><Clock size={10} />{formatDate(mem.timestamp)}</span>
                      <span className="flex items-center gap-1"><Eye size={10} />{mem.access_count}</span>
                      <span className={cn("font-mono", importanceColor(mem.importance))}>
                        重要性 {mem.importance}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {mem.status === "active" && (
                      <>
                        <button onClick={() => archiveMutation.mutate(mem.id)}
                          disabled={archiveMutation.isPending}
                          className="p-1.5 rounded text-os-muted hover:bg-os-elevated hover:text-amber-700"
                          title="归档"><Archive size={13} /></button>
                        <button onClick={() => deleteMutation.mutate(mem.id)}
                          disabled={deleteMutation.isPending}
                          className="p-1.5 rounded text-os-muted hover:bg-os-elevated hover:text-red-700"
                          title="删除"><Trash2 size={13} /></button>
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
