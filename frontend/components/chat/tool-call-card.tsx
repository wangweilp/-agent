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
      <div className={`
        flex items-center gap-2 rounded-lg px-3 py-1.5 max-w-[85%] border
        ${isRunning ? "bg-amber-400/5 border-amber-400/15" : ""}
        ${isSuccess ? "bg-emerald-400/5 border-emerald-400/10" : ""}
        ${isFailed ? "bg-red-400/5 border-red-400/10" : ""}
        ${!isRunning && !isSuccess && !isFailed ? "bg-os-elevated/50 border-os-border" : ""}
      `}>
        <Wrench size={12} className={isRunning ? "text-amber-400 animate-pulse" : isSuccess ? "text-emerald-400" : isFailed ? "text-red-400" : "text-os-subtle"} />
        <span className="text-xs text-os-text font-medium">{toolCall.tool_name}</span>
        <span className="text-2xs shrink-0">
          {isRunning ? (
            <span className="flex items-center gap-1 text-amber-400">
              <Loader2 size={10} className="animate-spin" />
              <span>执行中</span>
            </span>
          ) : isSuccess ? (
            <span className="flex items-center gap-1 text-emerald-400">
              <CheckCircle2 size={10} />
              <span>完成</span>
            </span>
          ) : isFailed ? (
            <span className="flex items-center gap-1 text-red-400">
              <XCircle size={10} />
              <span>失败</span>
            </span>
          ) : null}
        </span>
        {Object.keys(toolCall.arguments).length > 0 && (
          <span className="text-2xs text-os-muted truncate max-w-[160px] ml-1">
            {JSON.stringify(toolCall.arguments).slice(0, 60)}
          </span>
        )}
      </div>
    </motion.div>
  );
}
