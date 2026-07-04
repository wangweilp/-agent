"use client";

import { motion } from "framer-motion";
import { Calendar, Lightbulb } from "lucide-react";
import { Skeleton } from "@/components/animations/skeleton";
import { EmptyState, OsBadge } from "@/components/ui/os";
import { formatDate } from "@/lib/utils";
import type { RecentReflectionItem } from "@/types";

interface RecentReflectionsProps {
  reflections?: RecentReflectionItem[];
  isLoading: boolean;
}

export function RecentReflections({ reflections, isLoading }: RecentReflectionsProps) {
  if (isLoading) return <Skeleton className="h-72 rounded-2xl" />;

  if (!reflections || reflections.length === 0) {
    return (
      <EmptyState
        icon={Lightbulb}
        title="暂无反思记录"
        description="当系统从记忆中沉淀出洞察时，这里会显示主题、发现与相关实体。"
        className="min-h-[260px]"
      />
    );
  }

  return (
    <div className="space-y-3">
      {reflections.map((ref, i) => (
        <motion.div
          key={ref.id}
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: Math.min(i * 0.04, 0.2), duration: 0.16 }}
          className="rounded-2xl border border-os-border bg-white p-4 shadow-os-card transition-colors hover:border-os-primary/25"
        >
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-os-warning/20 bg-os-warning-soft text-os-warning">
              <Lightbulb size={16} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-os-text-high">{ref.topic}</p>
              <p className="mt-1 line-clamp-3 text-sm leading-6 text-os-muted">{ref.finding}</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1 text-xs text-os-muted">
                  <Calendar size={12} />
                  {formatDate(ref.timestamp)}
                </span>
                {ref.entities.slice(0, 2).map((entity) => (
                  <OsBadge key={entity} variant="muted">
                    #{entity}
                  </OsBadge>
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      ))}
    </div>
  );
}
