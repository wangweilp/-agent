"use client";

import { motion } from "framer-motion";
import { Clock, MessageSquare, Zap, User } from "lucide-react";
import { Skeleton } from "@/components/animations/skeleton";
import { formatDate, importanceColor, importanceBg } from "@/lib/utils";
import type { RecentMemoryItem } from "@/types";

interface RecentMemoriesProps {
  memories?: RecentMemoryItem[];
  isLoading: boolean;
}

const sourceIcon: Record<string, React.ElementType> = {
  user: User,
  agent: Zap,
  reflect: MessageSquare,
};

const memoryTypeLabel: Record<string, string> = {
  episodic: "情景",
  semantic: "语义",
  procedural: "程序",
  reflect: "反思",
};

export function RecentMemories({ memories, isLoading }: RecentMemoriesProps) {
  if (isLoading) return <Skeleton className="h-64" />;
  if (!memories || memories.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-2xs text-os-muted">
        <Clock size={20} className="mb-2 opacity-40" />
        暂无记忆
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      {memories.map((mem, i) => {
        const Icon = sourceIcon[mem.source] || User;
        return (
          <motion.div
            key={mem.id}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.03 }}
            className="flex items-start gap-3 py-2.5 px-3 rounded-lg hover:bg-os-surface-hover transition-colors group"
          >
            {/* Source icon */}
            <div className="w-6 h-6 rounded-full bg-os-surface flex items-center justify-center shrink-0 mt-0.5">
              <Icon size={11} className="text-os-subtle" />
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <p className="text-xs text-os-text-high line-clamp-2 leading-relaxed">
                {mem.content_preview}
              </p>
              <div className="flex items-center gap-2 mt-1.5">
                <span className="text-2xs text-os-muted flex items-center gap-1">
                  <Clock size={10} />
                  {formatDate(mem.timestamp)}
                </span>
                {mem.memory_type && (
                  <span className="text-2xs px-1.5 py-0.5 rounded bg-os-surface text-os-subtle">
                    {memoryTypeLabel[mem.memory_type] || mem.memory_type}
                  </span>
                )}
                {mem.entities.length > 0 && (
                  <span className="text-2xs text-os-muted truncate max-w-[120px]">
                    {mem.entities.slice(0, 2).join(", ")}
                  </span>
                )}
              </div>
            </div>

            {/* Importance indicator */}
            <div className="flex flex-col items-center gap-0.5 shrink-0">
              <span className={`text-2xs font-mono ${importanceColor(mem.importance)}`}>
                {mem.importance}
              </span>
              <div className={`w-1.5 h-1.5 rounded-full ${importanceBg(mem.importance)}`} />
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
