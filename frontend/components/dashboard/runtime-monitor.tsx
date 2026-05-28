"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { HardDrive, CheckCircle2, XCircle, Clock, Layers, Database } from "lucide-react";
import { api } from "@/services/api";
import { cn } from "@/lib/utils";
import type { RuntimeStats } from "@/types";

const statusColor: Record<string, string> = {
  pending: "text-amber-400",
  processing: "text-blue-400",
  stored: "text-emerald-400",
  failed: "text-red-400",
};

const statusDot: Record<string, string> = {
  pending: "bg-amber-400",
  processing: "bg-blue-400 animate-pulse",
  stored: "bg-emerald-400",
  failed: "bg-red-400",
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
      <div className="space-y-3 animate-pulse">
        <div className="h-4 bg-os-surface-hover rounded w-24" />
        <div className="h-16 bg-os-surface-hover rounded" />
        <div className="h-20 bg-os-surface-hover rounded" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="text-xs text-red-400">
        Worker 状态获取失败 — 检查服务是否在线
      </div>
    );
  }

  const { worker, queue, dead_letter, recent_tasks } = data;

  return (
    <div className="space-y-4">
      {/* Worker Status Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div
            className={cn(
              "w-2 h-2 rounded-full",
              worker.alive ? "bg-emerald-400 animate-status-breathe" : "bg-red-400"
            )}
          />
          <span className="text-xs font-medium text-os-text-high">
            MemoryWriteWorker
          </span>
          <span className="text-2xs text-os-muted">
            {worker.alive ? `运行 ${formatUptime(worker.uptime_seconds)}` : "离线"}
          </span>
        </div>
        <span className="text-2xs text-os-muted font-mono">
          started {worker.started_at ? new Date(worker.started_at).toLocaleTimeString() : "-"}
        </span>
      </div>

      {/* Queue Stats Grid */}
      <div className="grid grid-cols-3 gap-2">
        <div className="os-card p-3 text-center">
          <div className="flex items-center justify-center gap-1 mb-1">
            <Clock size={12} className="text-amber-400" />
            <span className="text-2xs text-os-subtle">待处理</span>
          </div>
          <p className="text-lg font-mono font-semibold text-amber-400">
            {queue.pending}
          </p>
        </div>
        <div className="os-card p-3 text-center">
          <div className="flex items-center justify-center gap-1 mb-1">
            <CheckCircle2 size={12} className="text-emerald-400" />
            <span className="text-2xs text-os-subtle">已存储</span>
          </div>
          <p className="text-lg font-mono font-semibold text-emerald-400">
            {queue.total_stored}
          </p>
        </div>
        <div className="os-card p-3 text-center">
          <div className="flex items-center justify-center gap-1 mb-1">
            <XCircle size={12} className="text-red-400" />
            <span className="text-2xs text-os-subtle">失败</span>
          </div>
          <p className={cn(
            "text-lg font-mono font-semibold",
            queue.total_failed > 0 ? "text-red-400" : "text-os-subtle"
          )}>
            {queue.total_failed}
          </p>
        </div>
      </div>

      {/* DLQ Status */}
      <div className="flex items-center justify-between text-2xs">
        <div className="flex items-center gap-1.5 text-os-subtle">
          <HardDrive size={11} />
          Dead Letter Queue
        </div>
        <span className={cn(
          "font-mono",
          dead_letter.count > 0 ? "text-amber-400" : "text-os-muted"
        )}>
          {dead_letter.count} 条待重试
        </span>
      </div>

      {/* Recent Tasks */}
      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <Layers size={11} className="text-os-subtle" />
          <span className="text-2xs text-os-subtle uppercase tracking-wider">最近任务</span>
        </div>
        <div className="space-y-1 max-h-48 overflow-y-auto scrollbar-thin">
          {recent_tasks.length === 0 ? (
            <p className="text-2xs text-os-muted py-2 text-center">暂无任务记录</p>
          ) : (
            recent_tasks.slice().reverse().map((task) => (
              <motion.div
                key={task.task_id}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-os-surface-hover transition-colors"
              >
                <div className={cn("w-1.5 h-1.5 rounded-full shrink-0", statusDot[task.status] || "bg-os-muted")} />
                <span className="text-2xs text-os-text-high truncate flex-1">
                  {task.content_preview || "(无内容)"}
                </span>
                <span className={cn("text-2xs font-mono shrink-0", statusColor[task.status] || "text-os-muted")}>
                  {task.status}
                </span>
                <span className="text-2xs text-os-muted font-mono shrink-0 w-12 text-right">
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
