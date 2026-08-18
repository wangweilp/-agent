"use client";

import { motion } from "framer-motion";
import { Lightbulb, Link2 } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import type { ReflectionInsight } from "@/types";

export function InsightCard({ insight }: { insight: ReflectionInsight }) {
  const highConf = insight.confidence >= 0.8;
  const midConf = insight.confidence >= 0.6;

  return (
    <motion.div
      whileHover={{ y: -1 }}
      className="os-card p-5 os-card-hover"
    >
      <div className="flex items-start gap-4">
        <div
          className={cn(
            "w-10 h-10 rounded-xl flex items-center justify-center shrink-0",
            highConf ? "bg-emerald-400/10" : midConf ? "bg-amber-400/10" : "bg-zinc-500/10",
          )}
        >
          <Lightbulb
            size={20}
            className={cn(
              highConf ? "text-emerald-700" : midConf ? "text-amber-800" : "text-os-subtle",
            )}
          />
        </div>

        <div className="flex-1 min-w-0">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <h3 className="min-w-0 break-words text-sm font-semibold text-os-text-high">{insight.topic}</h3>
            <span
              className={cn(
                "os-badge",
                highConf ? "bg-emerald-400/10 text-emerald-700" : midConf ? "bg-amber-400/10 text-amber-800" : "bg-zinc-500/10 text-zinc-700",
              )}
            >
              {Math.round(insight.confidence * 100)}% 置信度
            </span>
          </div>

          <p className="break-words text-sm leading-relaxed text-os-text">{insight.finding}</p>

          <div className="mt-3 flex flex-wrap items-center gap-4 border-t border-os-border pt-3">
            <span className="text-2xs text-os-subtle">{formatDate(insight.timestamp)}</span>
            <span className="text-2xs text-os-subtle flex items-center gap-1">
              <Link2 size={10} />
              {insight.related_memories.length} 条关联记忆
            </span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
