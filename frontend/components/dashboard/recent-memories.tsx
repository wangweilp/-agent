"use client";

import { motion } from "framer-motion";
import { Clock, Database, MessageSquare, User, Zap } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { zhCN } from "date-fns/locale";
import { Skeleton } from "@/components/animations/skeleton";
import { EmptyState, OsBadge } from "@/components/ui/os";
import { cn } from "@/lib/utils";
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
  procedural: "流程",
  reflect: "反思",
};

const memoryTypeDot: Record<string, string> = {
  episodic: "bg-os-primary",
  semantic: "bg-os-success",
  procedural: "bg-os-warning",
  reflect: "bg-os-info",
};

function importanceTextTone(score: number): string {
  if (score >= 8) return "text-emerald-700";
  if (score >= 6) return "text-amber-800";
  return "text-zinc-700";
}

export function RecentMemories({ memories, isLoading }: RecentMemoriesProps) {
  if (isLoading) return <Skeleton className="h-72 rounded-2xl" />;

  if (!memories || memories.length === 0) {
    return (
      <EmptyState
        icon={Database}
        title="暂无记忆数据"
        description="智能体写入的记忆流会在这里实时出现，包含来源、类型、实体和重要度。"
        className="min-h-[260px]"
      />
    );
  }

  return (
    <div className="relative pl-6">
      <div className="absolute bottom-3 left-[7px] top-3 w-px bg-os-border" />

      <div className="space-y-1">
        {memories.map((mem, i) => {
          const Icon = sourceIcon[mem.source] || User;
          const dotColor = memoryTypeDot[mem.memory_type] || "bg-os-primary";

          return (
            <motion.div
              key={mem.id}
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(i * 0.02, 0.2), duration: 0.16 }}
              className="relative rounded-xl px-3 py-3 transition-colors hover:bg-os-surface-hover"
            >
              <div className={cn("absolute -left-[21px] top-4 h-3 w-3 rounded-full border-2 border-white shadow-os-card", dotColor)} />

              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-os-border bg-white text-os-subtle shadow-os-card">
                  <Icon size={14} />
                </div>

                <div className="min-w-0 flex-1">
                  <p className="line-clamp-2 text-sm leading-6 text-os-text-high">{mem.content_preview}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-1 text-xs text-os-subtle">
                      <Clock size={12} />
                      {formatDistanceToNow(new Date(mem.timestamp), { addSuffix: true, locale: zhCN })}
                    </span>
                    {mem.memory_type && (
                      <OsBadge variant="muted">{memoryTypeLabel[mem.memory_type] || mem.memory_type}</OsBadge>
                    )}
                    {mem.entities.slice(0, 2).map((entity) => (
                      <OsBadge key={entity} variant="default">
                        #{entity}
                      </OsBadge>
                    ))}
                  </div>
                </div>

                <div className="shrink-0 text-right">
                  <span className={cn("font-mono text-xs font-semibold", importanceTextTone(mem.importance))}>
                    {mem.importance}
                  </span>
                  <p className="mt-0.5 text-[10px] uppercase text-os-subtle">重要度</p>
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
