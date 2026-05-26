"use client";

import { motion } from "framer-motion";
import { Lightbulb, TrendingUp, AlertTriangle, Link2 } from "lucide-react";
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
              highConf ? "text-emerald-400" : midConf ? "text-amber-400" : "text-os-subtle",
            )}
          />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-os-text-high">{insight.topic}</h3>
            <span
              className={cn(
                "os-badge",
                highConf ? "bg-emerald-400/10 text-emerald-400" : midConf ? "bg-amber-400/10 text-amber-400" : "bg-zinc-500/10 text-zinc-400",
              )}
            >
              {Math.round(insight.confidence * 100)}% 置信度
            </span>
          </div>

          <p className="text-sm text-os-text leading-relaxed">{insight.finding}</p>

          <div className="flex items-center gap-4 mt-3 pt-3 border-t border-os-border">
            <span className="text-2xs text-os-muted">{formatDate(insight.timestamp)}</span>
            <span className="text-2xs text-os-muted flex items-center gap-1">
              <Link2 size={10} />
              {insight.related_memories.length} 条关联记忆
            </span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
