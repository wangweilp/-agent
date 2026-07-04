"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Clock, HardDrive, Layers, XCircle } from "lucide-react";
import { api } from "@/services/api";
import { EmptyState, OsBadge, StatusBadge } from "@/components/ui/os";
import { Skeleton } from "@/components/animations/skeleton";
import { cn } from "@/lib/utils";
import type { RuntimeStats } from "@/types";

const statusTone: Record<string, string> = {
  pending: "bg-os-warning",
  processing: "bg-os-info animate-pulse",
  stored: "bg-os-success",
  failed: "bg-os-danger",
};

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function RuntimeMonitor() {
  const { data, isLoading, error } = useQuery<RuntimeStats>({
    queryKey: ["dashboard-runtime"],
    queryFn: () => api.dashboard.runtime(),
    refetchInterval: 3000,
  });

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-10 rounded-xl" />
        <Skeleton className="h-24 rounded-2xl" />
        <Skeleton className="h-36 rounded-2xl" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Worker 状态获取失败"
        description="请检查运行时服务是否在线，仪表盘会继续按 3 秒间隔自动重试。"
        className="min-h-[220px] border-os-danger/20 bg-os-danger-soft"
      />
    );
  }

  const { worker, queue, dead_letter, recent_tasks } = data;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-os-border bg-os-surface-tinted p-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <StatusBadge status={worker.alive ? "ready" : "danger"}>
              {worker.alive ? "在线" : "离线"}
            </StatusBadge>
            <span className="truncate text-sm font-semibold text-os-text-high">MemoryWriteWorker</span>
          </div>
          <p className="mt-1 text-xs text-os-muted">
            {worker.alive ? `已运行 ${formatUptime(worker.uptime_seconds)}` : "等待 worker 心跳"}
          </p>
        </div>
        <span className="font-mono text-xs text-os-muted">
          {worker.started_at ? new Date(worker.started_at).toLocaleTimeString() : "-"}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="rounded-2xl border border-os-border bg-white p-3 text-center shadow-os-card">
          <Clock size={14} className="mx-auto text-os-warning" />
          <p className="mt-1 text-xs text-os-muted">待处理</p>
          <p className="mt-1 font-mono text-lg font-semibold text-os-warning">{queue.pending}</p>
        </div>
        <div className="rounded-2xl border border-os-border bg-white p-3 text-center shadow-os-card">
          <CheckCircle2 size={14} className="mx-auto text-os-success" />
          <p className="mt-1 text-xs text-os-muted">已存储</p>
          <p className="mt-1 font-mono text-lg font-semibold text-os-success">{queue.total_stored}</p>
        </div>
        <div className="rounded-2xl border border-os-border bg-white p-3 text-center shadow-os-card">
          <XCircle size={14} className="mx-auto text-os-danger" />
          <p className="mt-1 text-xs text-os-muted">失败</p>
          <p className={cn("mt-1 font-mono text-lg font-semibold", queue.total_failed > 0 ? "text-os-danger" : "text-os-muted")}>
            {queue.total_failed}
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between rounded-xl border border-os-border bg-white px-3 py-2 text-sm">
        <span className="inline-flex items-center gap-2 text-os-muted">
          <HardDrive size={14} />
          Dead Letter Queue
        </span>
        <OsBadge variant={dead_letter.count > 0 ? "warning" : "muted"}>{dead_letter.count} 条待重试</OsBadge>
      </div>

      <div>
        <div className="mb-3 flex items-center gap-2">
          <Layers size={14} className="text-os-subtle" />
          <span className="text-xs font-semibold uppercase tracking-wide text-os-muted">最近任务</span>
        </div>
        <div className="max-h-56 space-y-1 overflow-y-auto pr-1">
          {recent_tasks.length === 0 ? (
            <EmptyState
              icon={Layers}
              title="暂无任务记录"
              description="当 worker 处理记忆写入任务时，最近任务会显示在这里。"
              className="min-h-[180px]"
            />
          ) : (
            recent_tasks.slice().reverse().map((task, index) => (
              <motion.div
                key={task.task_id}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: Math.min(index * 0.02, 0.14), duration: 0.16 }}
                className="flex min-w-0 items-center gap-2.5 rounded-xl px-2.5 py-2 transition-colors hover:bg-os-surface-hover"
              >
                <span className={cn("h-2 w-2 shrink-0 rounded-full", statusTone[task.status] || "bg-os-muted")} />
                <span className="min-w-0 flex-1 truncate text-sm text-os-text-high">
                  {task.content_preview || "(无内容)"}
                </span>
                <span className="shrink-0 font-mono text-xs text-os-muted">{task.status}</span>
                <span className="w-14 shrink-0 text-right font-mono text-xs text-os-muted">
                  {formatMs(task.elapsed_ms)}
                </span>
              </motion.div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
