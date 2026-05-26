"use client";

import { motion } from "framer-motion";
import { Wrench, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import type { ToolCall } from "@/types";

export function ToolCallCard({ toolCall }: { toolCall: ToolCall }) {
  const isRunning = toolCall.status === "running";
  const isSuccess = toolCall.status === "success";
  const isFailed = toolCall.status === "failed";

  return (
    <motion.div
      initial={{ opacity: 0, y: 4, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      className="flex items-start gap-2.5 pl-0"
    >
      <div className="flex items-center gap-2 bg-os-elevated/50 border border-os-border rounded-lg px-3 py-1.5 max-w-[85%]">
        <Wrench size={12} className={isRunning ? "text-amber-400 animate-pulse" : "text-os-subtle"} />
        <span className="text-xs text-os-text">{toolCall.tool_name}</span>
        <span className="text-2xs text-os-muted font-mono">
          {isRunning ? (
            <Loader2 size={10} className="animate-spin inline" />
          ) : isSuccess ? (
            <CheckCircle2 size={10} className="text-emerald-400 inline" />
          ) : isFailed ? (
            <XCircle size={10} className="text-red-400 inline" />
          ) : null}
        </span>
        {Object.keys(toolCall.arguments).length > 0 && (
          <span className="text-2xs text-os-muted truncate max-w-[160px]">
            {JSON.stringify(toolCall.arguments).slice(0, 60)}
          </span>
        )}
      </div>
    </motion.div>
  );
}
