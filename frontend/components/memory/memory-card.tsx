"use client";

import { motion } from "framer-motion";
import { Clock, Zap, Tag, Eye, Check } from "lucide-react";
import { cn, formatDate, importanceColor } from "@/lib/utils";
import type { Memory } from "@/types";

const sourceLabel: Record<string, string> = { user: "用户", agent: "智能体", reflect: "反思" };
const sourceStyle: Record<string, string> = {
  user: "bg-indigo-400/10 text-indigo-700",
  agent: "bg-emerald-400/10 text-emerald-700",
  reflect: "bg-amber-400/10 text-amber-800",
};

const typeLabel: Record<string, string> = {
  episodic: "情景记忆",
  semantic: "语义记忆",
  procedural: "程序记忆",
  reflect: "反思洞察",
};

const statusStyle: Record<string, string> = {
  active: "bg-os-success-soft text-os-success",
  archived: "bg-os-warning-soft text-os-warning",
  merged: "bg-os-surface-muted text-os-subtle",
  deleted: "bg-os-danger-soft text-os-danger",
};

const statusLabel: Record<string, string> = {
  active: "活跃",
  archived: "已归档",
  merged: "已合并",
  deleted: "已删除",
};

function readableImportanceColor(score: number) {
  return importanceColor(score)
    .replace("text-emerald-400", "text-os-success")
    .replace("text-amber-400", "text-os-warning")
    .replace("text-zinc-500", "text-os-subtle");
}

interface MemoryCardProps {
  memory: Memory;
  selected?: boolean;
  onToggleSelect?: (id: string) => void;
  onClick?: (id: string) => void;
}

export function MemoryCard({ memory, selected, onToggleSelect, onClick }: MemoryCardProps) {
  return (
    <motion.div
      whileHover={{ y: -2 }}
      className={cn(
        "os-card p-4 flex flex-col gap-3 os-card-hover group cursor-pointer relative",
        selected && "ring-1 ring-os-accent"
      )}
      onClick={() => onClick?.(memory.id)}
    >
      {/* Selection checkbox */}
      {onToggleSelect && (
        <div
          className="absolute top-3 right-3 z-10"
          onClick={(e) => { e.stopPropagation(); onToggleSelect(memory.id); }}
        >
          <div className={cn(
            "w-5 h-5 rounded border flex items-center justify-center transition-colors",
            selected
              ? "bg-os-accent border-os-accent"
              : "border-os-border bg-os-surface hover:border-os-muted"
          )}>
            {selected && <Check size={11} className="text-white" />}
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <span className={cn("os-badge max-w-full truncate", sourceStyle[memory.source])}>
            {sourceLabel[memory.source] || memory.source}
          </span>
          <span className="max-w-full break-all text-2xs text-os-subtle">{typeLabel[memory.memory_type] || memory.memory_type}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {memory.status !== "active" && (
            <span className={cn("os-badge text-2xs", statusStyle[memory.status] || "text-os-subtle")}>
              {statusLabel[memory.status] || memory.status}
            </span>
          )}
          <span className={cn("text-xs font-mono font-medium", readableImportanceColor(memory.importance))}>
            {memory.importance}/10
          </span>
        </div>
      </div>

      {/* Content */}
      <p className="line-clamp-3 break-words text-sm leading-relaxed text-os-text-high [overflow-wrap:anywhere]">
        {memory.summary || memory.content}
      </p>

      {/* Entities */}
      {memory.entities.length > 0 && (
        <div className="flex items-center gap-1 flex-wrap">
          <Tag size={11} className="text-os-subtle" />
          {memory.entities.slice(0, 4).map((e) => (
            <span key={e} className="max-w-full break-all rounded bg-os-elevated px-1.5 py-0.5 text-2xs text-os-subtle">
              {e}
            </span>
          ))}
          {memory.entities.length > 4 && (
            <span className="text-2xs text-os-subtle">+{memory.entities.length - 4}</span>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-os-border pt-1">
        <div className="flex items-center gap-1 text-2xs text-os-subtle">
          <Clock size={10} />
          {formatDate(memory.timestamp)}
        </div>
        <div className="flex items-center gap-3 text-2xs text-os-subtle">
          <span className="flex items-center gap-0.5">
            <Eye size={10} /> {memory.access_count}
          </span>
          <span className="flex items-center gap-0.5">
            <Zap size={10} /> {memory.importance}
          </span>
        </div>
      </div>
    </motion.div>
  );
}
