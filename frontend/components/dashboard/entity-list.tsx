"use client";

import { motion } from "framer-motion";
import { Tag } from "lucide-react";
import { Skeleton } from "@/components/animations/skeleton";
import { EmptyState } from "@/components/ui/os";
import type { EntityItem } from "@/types";

interface EntityListProps {
  entities?: EntityItem[];
  isLoading: boolean;
}

function fontSizeFor(count: number, max: number): string {
  if (max <= 0) return "0.78rem";
  const ratio = count / max;
  if (ratio >= 0.8) return "0.95rem";
  if (ratio >= 0.5) return "0.86rem";
  return "0.78rem";
}

function opacityFor(count: number, max: number): number {
  if (max <= 0) return 0.72;
  const ratio = count / max;
  return 0.72 + ratio * 0.28;
}

export function EntityList({ entities, isLoading }: EntityListProps) {
  if (isLoading) return <Skeleton className="h-40 rounded-2xl" />;

  if (!entities || entities.length === 0) {
    return (
      <EmptyState
        icon={Tag}
        title="暂无实体数据"
        description="系统抽取到人物、组织、地点或主题后，会在这里形成可扫描的实体云。"
        className="min-h-[220px]"
      />
    );
  }

  const maxCount = entities[0]?.mention_count || 1;

  return (
    <div className="flex flex-wrap gap-2.5">
      {entities.map((entity, i) => (
        <motion.span
          key={entity.name}
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: opacityFor(entity.mention_count, maxCount), scale: 1 }}
          transition={{ delay: Math.min(i * 0.02, 0.2), duration: 0.16 }}
          className="inline-flex max-w-full items-center gap-2 rounded-full border border-os-border bg-white px-3 py-2 text-os-text-high shadow-os-card transition-colors hover:border-os-primary/25 hover:bg-os-primary-soft/50"
          style={{ fontSize: fontSizeFor(entity.mention_count, maxCount) }}
        >
          <span className="text-os-primary">#</span>
          <span className="truncate">{entity.name}</span>
          <span className="rounded-full bg-os-surface-muted px-1.5 py-0.5 font-mono text-[11px] text-os-muted">
            {entity.mention_count}
          </span>
        </motion.span>
      ))}
    </div>
  );
}
