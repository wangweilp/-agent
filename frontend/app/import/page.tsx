"use client";

import { useState, useRef, useCallback, useMemo, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload,
  FileText,
  FileCode,
  Table2,
  Braces,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Trash2,
  RotateCcw,
  BarChart3,
  Layers,
  Brain,
  AlertTriangle,
  X,
  File,
  Image,
  FileSpreadsheet,
  Terminal,
} from "lucide-react";
import { api } from "@/services/api";
import { PageTransition, StaggerItem } from "@/components/animations/page-transition";
import { CardSkeleton } from "@/components/animations/skeleton";
import type { ImportJobResponse } from "@/types/import";
import { cn, formatNumber } from "@/lib/utils";
import { layout } from "@/styles/layout";

// ── 常量 ──

const ACCEPTED_TYPES = [
  { ext: ".md", label: "Markdown", icon: FileText },
  { ext: ".txt", label: "TXT", icon: FileText },
  { ext: ".pdf", label: "PDF", icon: FileText },
  { ext: ".docx", label: "DOCX", icon: FileText },
  { ext: ".html", label: "HTML", icon: FileCode },
  { ext: ".csv", label: "CSV", icon: Table2 },
  { ext: ".json", label: "JSON", icon: Braces },
];

const STATUS_CONFIG: Record<string, { color: string; bg: string; label: string; dotClass: string }> = {
  pending:    { color: "text-amber-400", bg: "bg-amber-400/10", label: "等待中", dotClass: "bg-amber-400" },
  processing: { color: "text-blue-400",  bg: "bg-blue-400/10",  label: "处理中", dotClass: "bg-blue-400 animate-pulse" },
  completed:  { color: "text-emerald-400", bg: "bg-emerald-400/10", label: "已完成", dotClass: "bg-emerald-400" },
  failed:     { color: "text-red-400",    bg: "bg-red-400/10",    label: "失败",   dotClass: "bg-red-400" },
  cancelled:  { color: "text-zinc-500",   bg: "bg-zinc-500/10",   label: "已取消", dotClass: "bg-zinc-500" },
};

function getFileTypeIcon(filename: string) {
  const ext = filename.slice(filename.lastIndexOf(".")).toLowerCase();
  const found = ACCEPTED_TYPES.find((t) => t.ext === ext);
  return found?.icon ?? File;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatElapsed(startedAt: string | null): string {
  if (!startedAt) return "--";
  const ms = Date.now() - new Date(startedAt).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function formatTimeAgo(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  const now = Date.now();
  const diff = now - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  return d.toLocaleDateString("zh-CN");
}

// ── 页面组件 ──

export default function ImportPage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── State ──
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [title, setTitle] = useState("");
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  // ── Toast auto-dismiss ──
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  // ── Data fetching ──
  const { data: jobList, isLoading: jobsLoading } = useQuery({
    queryKey: ["import-jobs"],
    queryFn: () => api.imports.list(),
    refetchInterval: 10000,
  });

  const jobs = jobList?.jobs ?? [];

  // ── Computed stats ──
  const stats = useMemo(() => {
    const total = jobs.length;
    const completed = jobs.filter((j) => j.status === "completed").length;
    const failed = jobs.filter((j) => j.status === "failed").length;
    const finished = completed + failed;
    const successRate = finished > 0 ? Math.round((completed / finished) * 100) : 0;
    const memories = jobs.reduce((sum, j) => sum + j.memories_created, 0);
    const chunks = jobs.reduce((sum, j) => sum + j.total_chunks, 0);
    return { total, successRate, memories, chunks, completed, failed };
  }, [jobs]);

  // ── Active jobs ──
  const activeJobs = useMemo(
    () => jobs.filter((j) => j.status === "pending" || j.status === "processing"),
    [jobs],
  );

  // ── Mutations ──
  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (selectedFiles.length === 0) throw new Error("请选择文件");
      return api.imports.upload(selectedFiles, title || undefined);
    },
    onSuccess: () => {
      setSelectedFiles([]);
      setTitle("");
      setToast({ message: "文件已提交导入", type: "success" });
      queryClient.invalidateQueries({ queryKey: ["import-jobs"] });
    },
    onError: (err: Error) => {
      setToast({ message: err.message || "导入失败", type: "error" });
    },
  });

  const retryMutation = useMutation({
    mutationFn: (jobId: string) => api.imports.retry(jobId),
    onSuccess: () => {
      setToast({ message: "已重新提交", type: "success" });
      queryClient.invalidateQueries({ queryKey: ["import-jobs"] });
    },
    onError: (err: Error) => {
      setToast({ message: err.message || "重试失败", type: "error" });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (jobId: string) => api.imports.delete(jobId),
    onSuccess: () => {
      setDeleteConfirmId(null);
      setToast({ message: "已删除", type: "success" });
      queryClient.invalidateQueries({ queryKey: ["import-jobs"] });
    },
    onError: (err: Error) => {
      setToast({ message: err.message || "删除失败", type: "error" });
    },
  });

  // ── Drag & drop handlers ──
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) setSelectedFiles((prev) => [...prev, ...files]);
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) setSelectedFiles((prev) => [...prev, ...files]);
    // reset so same file can be re‑selected
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  const removeFile = useCallback((index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const clearFiles = useCallback(() => {
    setSelectedFiles([]);
  }, []);

  // ── Derived progress for active jobs ──
  const estimateRemaining = (job: ImportJobResponse): string => {
    if (!job.started_at || job.processed_chunks === 0) return "计算中...";
    const elapsed = Date.now() - new Date(job.started_at).getTime();
    const rate = job.processed_chunks / (elapsed / 1000);
    const remaining = job.total_chunks - job.processed_chunks;
    if (rate <= 0) return "计算中...";
    const s = Math.ceil(remaining / rate);
    if (s < 60) return `${s}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
    return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  };

  return (
    <PageTransition>
      <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
        {/* ── Toast notification ── */}
        <AnimatePresence>
          {toast && (
            <motion.div
              initial={{ opacity: 0, y: -16, x: "-50%" }}
              animate={{ opacity: 1, y: 0, x: "-50%" }}
              exit={{ opacity: 0, y: -16, x: "-50%" }}
              className={cn(
                "fixed top-4 left-1/2 z-50 flex items-center gap-2 px-4 py-2.5 rounded-md shadow-lg text-xs",
                toast.type === "success"
                  ? "bg-emerald-600/90 text-white"
                  : "bg-red-600/90 text-white",
              )}
            >
              {toast.type === "success" ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
              {toast.message}
              <button
                onClick={() => setToast(null)}
                className="ml-2 opacity-70 hover:opacity-100 transition-opacity"
              >
                <X size={12} />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Header ── */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight">导入中心</h1>
            <p className="text-xs text-os-subtle mt-0.5">
              从文件导入并生成知识记忆 — 支持多种格式
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-2xs text-os-muted bg-os-surface border border-os-border rounded-full px-3 py-1">
              {jobsLoading ? "..." : `${jobs.length} 条记录`}
            </span>
          </div>
        </div>

        {/* ── Stats Cards (4-grid) ── */}
        <div className={layout.grid.fourMd}>
          <StaggerItem delay={0}>
            <div className="os-card p-4">
              <div className="flex items-center gap-2 mb-2">
                <Upload size={14} className="text-os-accent" />
                <span className="text-2xs text-os-muted">总导入</span>
              </div>
              <p className="text-lg font-semibold text-os-text-high">
                {jobsLoading ? "..." : formatNumber(stats.total)}
              </p>
            </div>
          </StaggerItem>
          <StaggerItem delay={0.03}>
            <div className="os-card p-4">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 size={14} className="text-os-accent" />
                <span className="text-2xs text-os-muted">成功率</span>
              </div>
              <p className="text-lg font-semibold text-os-text-high">
                {jobsLoading ? "..." : `${stats.successRate}%`}
              </p>
              <p className="text-2xs text-os-muted mt-0.5">
                {stats.completed} 成功 / {stats.failed} 失败
              </p>
            </div>
          </StaggerItem>
          <StaggerItem delay={0.06}>
            <div className="os-card p-4">
              <div className="flex items-center gap-2 mb-2">
                <Brain size={14} className="text-os-accent" />
                <span className="text-2xs text-os-muted">生成记忆</span>
              </div>
              <p className="text-lg font-semibold text-os-text-high">
                {jobsLoading ? "..." : formatNumber(stats.memories)}
              </p>
            </div>
          </StaggerItem>
          <StaggerItem delay={0.09}>
            <div className="os-card p-4">
              <div className="flex items-center gap-2 mb-2">
                <Layers size={14} className="text-os-accent" />
                <span className="text-2xs text-os-muted">处理 Chunks</span>
              </div>
              <p className="text-lg font-semibold text-os-text-high">
                {jobsLoading ? "..." : formatNumber(stats.chunks)}
              </p>
            </div>
          </StaggerItem>
        </div>

        {/* ── Upload Area ── */}
        <StaggerItem delay={0.12}>
          <motion.div
            whileTap={{ scale: 0.995 }}
            className={cn(
              "relative border-2 border-dashed rounded-xl p-8 transition-all duration-200 cursor-pointer",
              isDragging
                ? "border-os-accent bg-os-accent/5 scale-[1.01]"
                : "border-os-border hover:border-os-muted bg-os-surface/40",
            )}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
            }}
            role="button"
            tabIndex={0}
            aria-label="点击或拖拽文件到此处上传"
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              onChange={handleFileSelect}
              className="hidden"
              aria-hidden="true"
            />

            {selectedFiles.length === 0 ? (
              <div className="flex flex-col items-center gap-3 pointer-events-none">
                <motion.div
                  animate={isDragging ? { scale: 1.15, y: -4 } : { scale: 1, y: 0 }}
                  transition={{ type: "spring", stiffness: 300, damping: 20 }}
                >
                  <Upload size={36} className={cn("transition-colors", isDragging ? "text-os-accent" : "text-os-muted")} />
                </motion.div>
                <div className="text-center">
                  <p className="text-sm text-os-text-high font-medium">
                    {isDragging ? "松开以上传文件" : "拖拽文件到此处，或点击选择"}
                  </p>
                  <p className="text-2xs text-os-muted mt-1">支持批量上传</p>
                </div>
                <div className="flex items-center gap-1.5 flex-wrap justify-center">
                  {ACCEPTED_TYPES.map((t) => {
                    const Icon = t.icon;
                    return (
                      <span
                        key={t.ext}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs bg-os-elevated text-os-muted border border-os-border"
                      >
                        <Icon size={10} />
                        {t.label}
                      </span>
                    );
                  })}
                </div>
              </div>
            ) : (
              /* File list preview */
              <div className="space-y-3" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center justify-between">
                  <p className="text-xs text-os-text-high font-medium">
                    已选择 {selectedFiles.length} 个文件
                  </p>
                  <button
                    onClick={clearFiles}
                    className="text-2xs text-os-muted hover:text-os-subtle transition-colors"
                  >
                    清除全部
                  </button>
                </div>

                {/* Import title input */}
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="导入任务标题（可选）"
                  className="w-full h-8 px-3 bg-os-elevated border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
                />

                {/* File list */}
                <div className="max-h-48 overflow-y-auto space-y-1.5">
                  {selectedFiles.map((file, i) => {
                    const Icon = getFileTypeIcon(file.name);
                    return (
                      <div
                        key={`${file.name}-${i}`}
                        className="flex items-center gap-2 px-3 py-2 rounded-md bg-os-elevated border border-os-border/50"
                      >
                        <Icon size={14} className="text-os-muted shrink-0" />
                        <span className="text-xs text-os-text-high truncate flex-1">{file.name}</span>
                        <span className="text-2xs text-os-muted shrink-0">{formatFileSize(file.size)}</span>
                        <button
                          onClick={() => removeFile(i)}
                          className="p-0.5 rounded hover:bg-os-surface transition-colors shrink-0"
                          aria-label={`移除 ${file.name}`}
                        >
                          <X size={12} className="text-os-muted hover:text-os-subtle" />
                        </button>
                      </div>
                    );
                  })}
                </div>

                {/* Upload button */}
                <button
                  onClick={() => uploadMutation.mutate()}
                  disabled={uploadMutation.isPending}
                  className={cn(
                    "w-full flex items-center justify-center gap-2 py-2.5 rounded-md text-xs font-medium transition-all duration-200",
                    "bg-os-accent text-white hover:bg-os-accent/90 disabled:opacity-50 disabled:cursor-not-allowed",
                  )}
                >
                  {uploadMutation.isPending ? (
                    <>
                      <Loader2 size={14} className="animate-spin" />
                      上传中...
                    </>
                  ) : (
                    <>
                      <Upload size={14} />
                      开始导入
                    </>
                  )}
                </button>
              </div>
            )}
          </motion.div>
        </StaggerItem>

        {/* ── Active Import Progress Panel — 流光管线 + 终端日志 ── */}
        {activeJobs.length > 0 && (
          <StaggerItem delay={0.15}>
            <div className="os-card p-4">
              <div className="flex items-center gap-2 mb-4">
                <Loader2 size={14} className="text-os-accent-cyan animate-spin drop-shadow-[0_0_10px_rgba(34,211,238,0.6)]" />
                <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">
                  管线运行中 ({activeJobs.length})
                </h2>
              </div>
              <div className="space-y-4">
                {activeJobs.map((job) => (
                  <div key={job.job_id} className="rounded-lg border border-os-border/50 bg-os-surface/40 p-3 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-os-text-high">{job.title}</span>
                        <span className={cn(
                          "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-medium",
                          STATUS_CONFIG[job.status]?.bg,
                          STATUS_CONFIG[job.status]?.color,
                        )}>
                          <span className={cn("w-1.5 h-1.5 rounded-full", STATUS_CONFIG[job.status]?.dotClass)} />
                          {STATUS_CONFIG[job.status]?.label}
                        </span>
                      </div>
                      <span className="text-2xs font-mono text-os-muted">
                        {job.processed_chunks} / {job.total_chunks} chunks
                      </span>
                    </div>

                    {/* 流光进度条 — 赛博管线 */}
                    <div className="relative w-full h-2 bg-os-elevated rounded-full overflow-hidden">
                      <motion.div
                        className="relative h-full rounded-full bg-gradient-to-r from-os-accent to-os-accent-cyan"
                        initial={{ width: 0 }}
                        animate={{ width: `${job.progress_pct}%` }}
                        transition={{ duration: 0.5, ease: "easeOut" }}
                      >
                        {/* 流光高光层 */}
                        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/40 to-transparent animate-pulse" />
                      </motion.div>
                      {/* 管线刻度线 */}
                      <div className="absolute inset-0 flex justify-between pointer-events-none">
                        {Array.from({ length: 10 }).map((_, i) => (
                          <div key={i} className="w-px h-full bg-os-border/30" />
                        ))}
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-2xs text-os-muted">
                      <span className="inline-flex items-center gap-1">
                        <Clock size={10} />
                        已用: {formatElapsed(job.started_at)}
                      </span>
                      <span className="font-mono text-os-accent-cyan">
                        {job.progress_pct}%
                      </span>
                      <span>剩余: {estimateRemaining(job)}</span>
                    </div>
                  </div>
                ))}
              </div>

              {/* ── 终端风格日志面板 ── */}
              <div className="mt-4 rounded-xl border border-os-border/50 bg-[#000000] overflow-hidden">
                <div className="flex items-center justify-between px-3 py-2 border-b border-os-border/30">
                  <div className="flex items-center gap-1.5">
                    <Terminal size={11} className="text-os-success" />
                    <span className="font-mono text-2xs text-os-muted">pipeline.log</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="w-2 h-2 rounded-full bg-red-500/60" />
                    <div className="w-2 h-2 rounded-full bg-amber-500/60" />
                    <div className="w-2 h-2 rounded-full bg-emerald-500/60" />
                  </div>
                </div>
                <div className="h-48 overflow-y-auto p-4 font-mono text-xs text-os-success space-y-0.5">
                  {activeJobs.flatMap((job) => {
                    const logs: { ts: string; level: "OK" | "INFO" | "WARN" | "ERR"; msg: string }[] = [];
                    const now = new Date().toLocaleTimeString("en-US", { hour12: false });
                    logs.push({ ts: now, level: "INFO", msg: `> Initializing pipeline for "${job.title}"` });
                    if (job.processed_chunks > 0) {
                      const step = Math.max(1, Math.floor(job.total_chunks / 5));
                      for (let i = step; i <= job.processed_chunks; i += step) {
                        logs.push({
                          ts: now,
                          level: "OK",
                          msg: `> [OK] Chunk ${i}/${job.total_chunks} vectorized (${((i / job.total_chunks) * 100).toFixed(0)}%)`,
                        });
                      }
                      if (job.processed_chunks < job.total_chunks) {
                        logs.push({
                          ts: now,
                          level: "INFO",
                          msg: `> [..] Chunk ${job.processed_chunks + 1} embedding in progress...`,
                        });
                      }
                    }
                    if (job.status === "completed") {
                      logs.push({ ts: now, level: "OK", msg: `> [OK] Pipeline complete — ${job.memories_created} memories created` });
                    }
                    return logs.map((log, i) => (
                      <div key={`${job.job_id}-${i}`} className="leading-5">
                        <span className="text-os-muted">[{log.ts}]</span>{" "}
                        <span className={cn(
                          log.level === "OK" && "text-os-success",
                          log.level === "INFO" && "text-os-accent-cyan",
                          log.level === "WARN" && "text-amber-400",
                          log.level === "ERR" && "text-red-400",
                        )}>
                          {log.msg}
                        </span>
                      </div>
                    ));
                  })}
                  {/* 闪烁光标 */}
                  <div className="leading-5">
                    <span className="text-os-muted">$</span>{" "}
                    <span className="inline-block w-1.5 h-3.5 bg-os-success animate-pulse align-middle" />
                  </div>
                </div>
              </div>
            </div>
          </StaggerItem>
        )}

        {/* ── Import History Table ── */}
        <StaggerItem delay={0.18}>
          <div className="os-card p-4">
            <div className="flex items-center gap-2 mb-4">
              <BarChart3 size={14} className="text-os-accent" />
              <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">导入历史</h2>
              <span className="text-2xs text-os-muted ml-auto">{jobs.length} 条记录</span>
            </div>

            {jobsLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <CardSkeleton key={i} />
                ))}
              </div>
            ) : jobs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-os-muted">
                <Upload size={40} className="mb-3 opacity-30" />
                <p className="text-sm">暂无导入记录</p>
                <p className="text-2xs mt-1">拖拽文件到上方区域开始你的第一次导入</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs" role="table">
                  <thead>
                    <tr className="border-b border-os-border">
                      <th className="text-left py-2.5 px-3 text-2xs text-os-muted font-medium uppercase tracking-wider">标题</th>
                      <th className="text-left py-2.5 px-3 text-2xs text-os-muted font-medium uppercase tracking-wider hidden sm:table-cell">类型</th>
                      <th className="text-left py-2.5 px-3 text-2xs text-os-muted font-medium uppercase tracking-wider">状态</th>
                      <th className="text-left py-2.5 px-3 text-2xs text-os-muted font-medium uppercase tracking-wider hidden md:table-cell">进度</th>
                      <th className="text-left py-2.5 px-3 text-2xs text-os-muted font-medium uppercase tracking-wider hidden md:table-cell">记忆数</th>
                      <th className="text-left py-2.5 px-3 text-2xs text-os-muted font-medium uppercase tracking-wider hidden lg:table-cell">时间</th>
                      <th className="text-right py-2.5 px-3 text-2xs text-os-muted font-medium uppercase tracking-wider">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map((job) => {
                      const cfg = STATUS_CONFIG[job.status] ?? STATUS_CONFIG.pending;
                      const isProcessing = job.status === "processing";
                      const isFailed = job.status === "failed";
                      return (
                        <tr key={job.job_id} className="border-b border-os-border/50 hover:bg-os-elevated/50 transition-colors">
                          <td className="py-2.5 px-3">
                            <span className="text-os-text-high font-medium truncate max-w-[160px] block">{job.title}</span>
                          </td>
                          <td className="py-2.5 px-3 hidden sm:table-cell">
                            <span className="text-os-muted uppercase text-2xs">{job.file_type}</span>
                          </td>
                          <td className="py-2.5 px-3">
                            <span className={cn("inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs", cfg.bg, cfg.color)}>
                              <span className={cn("w-1.5 h-1.5 rounded-full", cfg.dotClass)} />
                              {cfg.label}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 hidden md:table-cell">
                            <div className="flex items-center gap-2 min-w-[100px]">
                              <div className="flex-1 h-1 bg-os-elevated rounded-full overflow-hidden">
                                <div
                                  className={cn(
                                    "h-full rounded-full transition-all duration-500",
                                    job.status === "completed" ? "bg-emerald-400" :
                                    job.status === "failed" ? "bg-red-400" :
                                    isProcessing ? "bg-blue-400" : "bg-os-muted",
                                  )}
                                  style={{ width: `${job.progress_pct}%` }}
                                />
                              </div>
                              <span className="text-2xs text-os-muted w-8 text-right">
                                {job.processed_chunks}/{job.total_chunks}
                              </span>
                            </div>
                          </td>
                          <td className="py-2.5 px-3 hidden md:table-cell">
                            <span className="text-os-subtle">{formatNumber(job.memories_created)}</span>
                          </td>
                          <td className="py-2.5 px-3 hidden lg:table-cell">
                            <span className="text-os-muted" title={job.started_at ?? undefined}>
                              {formatTimeAgo(job.started_at)}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            <div className="flex items-center justify-end gap-1">
                              {isFailed && (
                                <button
                                  onClick={() => retryMutation.mutate(job.job_id)}
                                  disabled={retryMutation.isPending}
                                  className="p-1.5 rounded hover:bg-os-elevated transition-colors text-os-muted hover:text-amber-400"
                                  title="重试"
                                  aria-label={`重试 ${job.title}`}
                                >
                                  <RotateCcw size={13} />
                                </button>
                              )}
                              <button
                                onClick={() => setDeleteConfirmId(job.job_id)}
                                className="p-1.5 rounded hover:bg-os-elevated transition-colors text-os-muted hover:text-red-400"
                                title="删除"
                                aria-label={`删除 ${job.title}`}
                              >
                                <Trash2 size={13} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </StaggerItem>

        {/* ── Delete Confirmation Modal ── */}
        <AnimatePresence>
          {deleteConfirmId && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
              onClick={() => setDeleteConfirmId(null)}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.15 }}
                onClick={(e) => e.stopPropagation()}
                className="os-card p-6 max-w-sm w-full mx-4"
                role="alertdialog"
                aria-label="确认删除"
              >
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-9 h-9 rounded-full bg-red-400/10 flex items-center justify-center">
                    <AlertTriangle size={18} className="text-red-400" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-os-text-high">确认删除</h3>
                    <p className="text-2xs text-os-muted mt-0.5">此操作不可撤销，确定要删除这个导入任务吗？</p>
                  </div>
                </div>
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setDeleteConfirmId(null)}
                    className="px-4 py-2 rounded-md text-xs text-os-subtle bg-os-elevated border border-os-border hover:text-os-text-high transition-colors"
                  >
                    取消
                  </button>
                  <button
                    onClick={() => deleteMutation.mutate(deleteConfirmId)}
                    disabled={deleteMutation.isPending}
                    className="px-4 py-2 rounded-md text-xs font-medium text-white bg-red-500 hover:bg-red-600 disabled:opacity-50 transition-colors flex items-center gap-1.5"
                  >
                    {deleteMutation.isPending ? (
                      <>
                        <Loader2 size={12} className="animate-spin" />
                        删除中...
                      </>
                    ) : (
                      <>
                        <Trash2 size={12} />
                        删除
                      </>
                    )}
                  </button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </PageTransition>
  );
}
