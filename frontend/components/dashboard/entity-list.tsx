"use client";

import { motion } from "framer-motion";
import { Tag } from "lucide-react";
import { Skeleton } from "@/components/animations/skeleton";
import { EmptyState } from "@/components/dashboard-v2/query-state";
import type { EntityItem } from "@/types";

interface EntityListProps {
  entities?: EntityItem[];
  isLoading: boolean;
}

/** 按 mention_count 计算字体大小（rem） */
function fontSizeFor(count: number, max: number): string {
  if (max <= 0) return "0.7rem";
  const ratio = count / max;
  if (ratio >= 0.8) return "0.85rem";
  if (ratio >= 0.5) return "0.75rem";
  return "0.7rem";
}

/** 按 mention_count 计算不透明度 */
function opacityFor(count: number, max: number): number {
  if (max <= 0) return 0.5;
  const ratio = count / max;
  return 0.5 + ratio * 0.5;
}

export function EntityList({ entities, isLoading }: EntityListProps) {
  if (isLoading) return <Skeleton className="h-32" />;
  if (!entities || entities.length === 0) {
    return (
      <EmptyState
        icon={Tag}
        message="暂无实体数据"
        description="系统提取的实体标签将在此处聚合展示"
        className="py-8"
      />
    );
  }

  const maxCount = entities[0]?.mention_count || 1;

  return (
    <div className="flex flex-wrap gap-2.5">
      {entities.map((entity, i) => (
        <motion.span
          key={entity.name}
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: i * 0.03, duration: 0.3 }}
          className="inline-flex items-center gap-2 py-2 px-3.5 rounded-full bg-os-surface border border-os-border/40 hover:border-os-accent/50 transition-colors cursor-default"
          style={{
            fontSize: fontSizeFor(entity.mention_count, maxCount),
            opacity: opacityFor(entity.mention_count, maxCount),
          }}
        >
          <span className="text-indigo-400/70">#</span>
          <span className="text-os-text-high whitespace-nowrap">{entity.name}</span>
          <span className="text-os-muted text-xs font-mono ml-0.5">
            {entity.mention_count}
          </span>
        </motion.span>
      ))}
    </div>
  );
}
