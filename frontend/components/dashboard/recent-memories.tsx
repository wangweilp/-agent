"use client";

import { motion } from "framer-motion";
import { Clock, MessageSquare, Zap, User, Database } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { zhCN } from "date-fns/locale";
import { Skeleton } from "@/components/animations/skeleton";
import { EmptyState } from "@/components/dashboard-v2/query-state";
import { importanceColor, importanceBg } from "@/lib/utils";
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

// 记忆类型标识色 — 左侧时间线圆点配色
const memoryTypeDot: Record<string, string> = {
  episodic: "bg-os-accent shadow-[0_0_6px_rgba(129,140,248,0.6)]",
  semantic: "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.6)]",
  procedural: "bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.6)]",
  reflect: "bg-os-accent-violet shadow-[0_0_6px_rgba(167,139,250,0.6)]",
};

export function RecentMemories({ memories, isLoading }: RecentMemoriesProps) {
  if (isLoading) return <Skeleton className="h-64" />;
  if (!memories || memories.length === 0) {
    return (
      <EmptyState
        icon={Database}
        message="暂无记忆数据"
        description="智能体的记忆流将在此处实时显示"
      />
    );
  }

  return (
    <div className="relative pl-6">
      {/* 左侧贯穿垂直极细线 — 时间线轴线 */}
      <div className="absolute left-[7px] top-2 bottom-2 w-px bg-os-border" />

      <div className="space-y-1">
        {memories.map((mem, i) => {
          const Icon = sourceIcon[mem.source] || User;
          const dotColor = memoryTypeDot[mem.memory_type] || "bg-os-accent shadow-[0_0_6px_rgba(129,140,248,0.6)]";
          return (
            <motion.div
              key={mem.id}
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03 }}
              className="relative flex items-start gap-3.5 py-3 px-3.5 rounded-lg hover:bg-os-surface-hover transition-colors group"
            >
              {/* 左侧发光小圆点 — 时间线节点（类型标识色） */}
              <div className={`absolute left-[-19px] top-4 w-2.5 h-2.5 rounded-full ring-2 ring-os-surface ${dotColor}`} />

              {/* Source icon */}
              <div className="w-7 h-7 rounded-full bg-os-surface flex items-center justify-center shrink-0 mt-0.5">
                <Icon size={12} className="text-os-subtle" />
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <p className="text-sm text-os-text-high line-clamp-2 leading-relaxed">
                  {mem.content_preview}
                </p>
                <div className="flex items-center gap-2.5 mt-2">
                  <span className="text-xs font-mono text-os-subtle flex items-center gap-1">
                    <Clock size={11} />
                    {formatDistanceToNow(new Date(mem.timestamp), { addSuffix: true, locale: zhCN })}
                  </span>
                  {mem.memory_type && (
                    <span className="text-xs px-2 py-0.5 rounded bg-os-surface text-os-subtle">
                      {memoryTypeLabel[mem.memory_type] || mem.memory_type}
                    </span>
                  )}
                  {mem.entities.length > 0 && (
                    <span className="text-xs text-os-muted truncate max-w-[120px]">
                      {mem.entities.slice(0, 2).join(", ")}
                    </span>
                  )}
                </div>
              </div>

              {/* Importance indicator */}
              <div className="flex flex-col items-center gap-1 shrink-0">
                <span className={`text-xs font-mono ${importanceColor(mem.importance)}`}>
                  {mem.importance}
                </span>
                <div className={`w-1.5 h-1.5 rounded-full ${importanceBg(mem.importance)}`} />
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
