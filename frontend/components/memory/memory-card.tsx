"use client";

import { motion } from "framer-motion";
import { Clock, Zap, Tag, Eye } from "lucide-react";
import { cn, formatDate, importanceColor, importanceBg } from "@/lib/utils";
import type { Memory } from "@/types";

const sourceLabel: Record<string, string> = { user: "用户", agent: "Agent", reflect: "反思" };
const sourceStyle: Record<string, string> = {
  user: "bg-indigo-400/10 text-indigo-400",
  agent: "bg-emerald-400/10 text-emerald-400",
  reflect: "bg-amber-400/10 text-amber-400",
};

const typeLabel: Record<string, string> = {
  episodic: "情景记忆",
  semantic: "语义记忆",
  procedural: "程序记忆",
  reflect: "反思洞察",
};

export function MemoryCard({ memory }: { memory: Memory }) {
  return (
    <motion.div
      whileHover={{ y: -2 }}
      className="os-card p-4 flex flex-col gap-3 os-card-hover group cursor-default"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className={cn("os-badge", sourceStyle[memory.source])}>
            {sourceLabel[memory.source] || memory.source}
          </span>
          <span className="text-2xs text-os-muted">{typeLabel[memory.memory_type] || memory.memory_type}</span>
        </div>
        <span className={cn("text-xs font-mono font-medium", importanceColor(memory.importance))}>
          {memory.importance}/10
        </span>
      </div>

      {/* Content */}
      <p className="text-sm text-os-text-high leading-relaxed line-clamp-3">
        {memory.summary || memory.content}
      </p>

      {/* Entities */}
      {memory.entities.length > 0 && (
        <div className="flex items-center gap-1 flex-wrap">
          <Tag size={11} className="text-os-muted" />
          {memory.entities.slice(0, 4).map((e) => (
            <span key={e} className="text-2xs px-1.5 py-0.5 rounded bg-os-elevated text-os-subtle">
              {e}
            </span>
          ))}
          {memory.entities.length > 4 && (
            <span className="text-2xs text-os-muted">+{memory.entities.length - 4}</span>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between pt-1 border-t border-os-border">
        <div className="flex items-center gap-1 text-2xs text-os-muted">
          <Clock size={10} />
          {formatDate(memory.timestamp)}
        </div>
        <div className="flex items-center gap-3 text-2xs text-os-muted">
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
