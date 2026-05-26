"use client";

import { motion } from "framer-motion";
import { Brain, Wrench, Lightbulb, MessageSquare, Database } from "lucide-react";
import { cn, formatMs, formatDate } from "@/lib/utils";
import type { TraceEntry } from "@/types";

const typeIcons: Record<string, React.ElementType> = {
  llm_call: MessageSquare,
  tool_call: Wrench,
  reflection: Lightbulb,
  memory_write: Database,
  memory_read: Brain,
};

const statusStyles: Record<string, string> = {
  success: "text-emerald-400",
  failed: "text-red-400",
  running: "text-indigo-400 animate-pulse",
};

export function TraceTimeline({ traces }: { traces: TraceEntry[] }) {
  if (traces.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-xs text-os-muted">暂无 Trace 数据，启动 Agent 对话后将自动记录</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {traces.slice(-20).reverse().map((trace, i) => {
        const Icon = typeIcons[trace.type] || MessageSquare;
        return (
          <motion.div
            key={trace.id}
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.02 }}
            className="flex items-center gap-3 py-2 px-2 rounded-md hover:bg-os-elevated transition-colors group"
          >
            <div className="relative shrink-0">
              <Icon size={13} className={cn("text-os-subtle", statusStyles[trace.status])} />
            </div>
            <span className="text-xs text-os-text flex-1 truncate">{trace.detail}</span>
            <span className="text-2xs text-os-muted font-mono shrink-0">{formatMs(trace.duration_ms)}</span>
            <span className="text-2xs text-os-muted shrink-0 w-16 text-right opacity-0 group-hover:opacity-100 transition-opacity">
              {formatDate(trace.timestamp)}
            </span>
          </motion.div>
        );
      })}
    </div>
  );
}
