"use client";

import { motion } from "framer-motion";
import { cn, formatDate, importanceColor } from "@/lib/utils";
import type { Memory } from "@/types";

const typeLabel: Record<string, string> = {
  episodic: "情景",
  semantic: "语义",
  procedural: "程序",
  reflect: "反思",
};

const statusLabel: Record<string, string> = {
  active: "活跃",
  archived: "已归档",
  merged: "已合并",
  deleted: "已删除",
};

const statusStyle: Record<string, string> = {
  active: "bg-os-success-soft text-os-success",
  archived: "bg-os-warning-soft text-os-warning",
  merged: "bg-os-surface-muted text-os-subtle",
  deleted: "bg-os-danger-soft text-os-danger",
};

function readableImportanceColor(score: number) {
  return importanceColor(score)
    .replace("text-emerald-400", "text-os-success")
    .replace("text-amber-400", "text-os-warning")
    .replace("text-zinc-500", "text-os-subtle");
}

interface MemoryTableProps {
  memories: Memory[];
  selected: Set<string>;
  onToggleSelect: (id: string) => void;
  onSelectAll: () => void;
  onViewDetail: (id: string) => void;
}

export function MemoryTable({
  memories, selected, onToggleSelect, onSelectAll, onViewDetail,
}: MemoryTableProps) {
  const allSelected = memories.length > 0 && selected.size === memories.length;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-os-border text-os-subtle text-2xs uppercase tracking-wider">
            <th className="py-2.5 px-2 text-left w-8">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={onSelectAll}
                className="rounded border-os-border bg-os-surface accent-indigo-400"
              />
            </th>
            <th className="py-2.5 px-2 text-left">时间</th>
            <th className="py-2.5 px-2 text-left">内容</th>
            <th className="py-2.5 px-2 text-left hidden md:table-cell">类型</th>
            <th className="py-2.5 px-2 text-left hidden md:table-cell">状态</th>
            <th className="py-2.5 px-2 text-right hidden lg:table-cell">重要性</th>
          </tr>
        </thead>
        <tbody>
          {memories.map((mem, i) => (
            <motion.tr
              key={mem.id}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: i * 0.02 }}
              className={cn(
                "border-b border-os-border/50 hover:bg-os-surface-hover transition-colors cursor-pointer",
                selected.has(mem.id) && "bg-os-accent/5"
              )}
              onClick={() => onViewDetail(mem.id)}
            >
              <td className="py-2.5 px-2" onClick={(e) => e.stopPropagation()}>
                <input
                  type="checkbox"
                  checked={selected.has(mem.id)}
                  onChange={() => onToggleSelect(mem.id)}
                  className="rounded border-os-border bg-os-surface accent-indigo-400"
                />
              </td>
              <td className="py-2.5 px-2 text-2xs text-os-subtle whitespace-nowrap font-mono">
                {formatDate(mem.timestamp)}
              </td>
              <td className="py-2.5 px-2">
                <p className="max-w-[300px] break-words text-os-text-high [overflow-wrap:anywhere] line-clamp-1">
                  {mem.summary || mem.content.slice(0, 80)}
                </p>
                {mem.entities.length > 0 && (
                  <div className="flex gap-1 mt-1 flex-wrap">
                    {mem.entities.slice(0, 3).map((e) => (
                      <span key={e} className="inline-block max-w-[8rem] truncate rounded bg-os-elevated px-1 py-0.5 align-middle text-2xs text-os-subtle">
                        {e}
                      </span>
                    ))}
                  </div>
                )}
              </td>
              <td className="py-2.5 px-2 hidden md:table-cell">
                <span className="text-2xs text-os-subtle">
                  {typeLabel[mem.memory_type] || mem.memory_type}
                </span>
              </td>
              <td className="py-2.5 px-2 hidden md:table-cell">
                <span className={cn("os-badge text-2xs", statusStyle[mem.status] || "text-os-subtle")}>
                  {statusLabel[mem.status] || mem.status}
                </span>
              </td>
              <td className="py-2.5 px-2 text-right hidden lg:table-cell">
                <span className={cn("font-mono font-medium", readableImportanceColor(mem.importance))}>
                  {mem.importance}
                </span>
              </td>
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
