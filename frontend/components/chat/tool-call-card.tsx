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
      className="flex min-w-0 items-start gap-2.5 pl-0"
    >
      <div className={`
        flex min-w-0 max-w-full flex-wrap items-center gap-2 rounded-lg border px-3 py-1.5 sm:max-w-[85%]
        ${isRunning ? "bg-amber-400/5 border-amber-400/20" : ""}
        ${isSuccess ? "bg-emerald-400/5 border-emerald-400/10" : ""}
        ${isFailed ? "bg-red-400/5 border-red-400/10" : ""}
        ${!isRunning && !isSuccess && !isFailed ? "bg-os-elevated/50 border-os-border" : ""}
      `}>
        <Wrench size={12} className={`shrink-0 ${isRunning ? "text-amber-800 animate-pulse" : isSuccess ? "text-emerald-700" : isFailed ? "text-red-700" : "text-os-subtle"}`} />
        <span className="min-w-0 flex-1 truncate text-xs font-medium text-os-text">{toolCall.tool_name}</span>
        <span className="text-2xs shrink-0">
          {isRunning ? (
            <span className="flex items-center gap-1 text-amber-800">
              <Loader2 size={10} className="animate-spin" />
              <span>执行中</span>
            </span>
          ) : isSuccess ? (
            <span className="flex items-center gap-1 text-emerald-700">
              <CheckCircle2 size={10} />
              <span>完成</span>
            </span>
          ) : isFailed ? (
            <span className="flex items-center gap-1 text-red-700">
              <XCircle size={10} />
              <span>失败</span>
            </span>
          ) : null}
        </span>
        {Object.keys(toolCall.arguments).length > 0 && (
          <span
            className="basis-full truncate pl-5 text-2xs text-os-subtle"
            title={JSON.stringify(toolCall.arguments)}
          >
            {JSON.stringify(toolCall.arguments).slice(0, 60)}
          </span>
        )}
      </div>
    </motion.div>
  );
}
