"use client";

import { motion } from "framer-motion";
import { Lightbulb } from "lucide-react";
import { formatDate } from "@/lib/utils";
import type { ReflectionInsight } from "@/types";

export function ReflectionTimeline({ insights }: { insights: ReflectionInsight[] }) {
  const sorted = [...insights].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );

  if (sorted.length === 0) {
    return <p className="text-xs text-os-muted text-center py-8">暂无反思记录</p>;
  }

  return (
    <div className="relative pl-6">
      <div className="absolute left-[9px] top-2 bottom-2 w-px bg-os-border" />

      <div className="space-y-3">
        {sorted.map((insight, i) => (
          <motion.div
            key={insight.id}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: i * 0.05 }}
            className="relative"
          >
            <div className="absolute -left-[22px] top-1 w-2 h-2 rounded-full bg-amber-400 border-2 border-os-base" />
            <div className="ml-2">
              <p className="text-xs font-medium text-os-text-high">{insight.topic}</p>
              <p className="text-2xs text-os-muted mt-0.5">{formatDate(insight.timestamp)}</p>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-2xs text-amber-400/80">
                  {Math.round(insight.confidence * 100)}% 置信
                </span>
                <span className="text-2xs text-os-muted">
                  {insight.related_memories.length} 条关联
                </span>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
