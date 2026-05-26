"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useChatStore } from "@/stores/chat-store";
import { useAgentStore } from "@/stores/agent-store";
import { Wrench, Brain, Zap, Activity, Clock, Cpu } from "lucide-react";
import { formatDate } from "@/lib/utils";

export function ActivityPanel() {
  const toolCalls = useChatStore((s) => s.toolCalls);
  const isThinking = useChatStore((s) => s.isThinking);
  const traces = useAgentStore((s) => s.traces);
  const status = useAgentStore((s) => s.status);

  return (
    <div className="h-full flex flex-col bg-os-base">
      <div className="flex items-center px-4 h-10 border-b border-os-border">
        <Activity size={14} className="text-os-accent mr-2" />
        <span className="text-xs font-medium text-os-text-high">Agent 活动</span>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {/* Agent Status */}
        <div className="p-3 rounded-lg bg-os-surface border border-os-border">
          <div className="flex items-center gap-2 mb-2">
            <div className={`w-1.5 h-1.5 rounded-full ${status === "idle" ? "bg-emerald-400" : "bg-indigo-400 animate-pulse"}`} />
            <span className="text-2xs text-os-subtle uppercase tracking-wider">Agent 状态</span>
          </div>
          <p className="text-xs text-os-text-high capitalize">{status}</p>
        </div>

        {/* Tool Activity */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Wrench size={12} className="text-os-subtle" />
            <span className="text-2xs text-os-subtle uppercase tracking-wider">工具调用</span>
          </div>
          <div className="space-y-1">
            <AnimatePresence>
              {toolCalls.map((tc) => (
                <motion.div
                  key={tc.call_id}
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="text-xs text-os-text bg-os-surface rounded-md px-2.5 py-1.5 border border-os-border"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{tc.tool_name}</span>
                    <span className={`text-2xs ${tc.status === "running" ? "text-amber-400" : tc.status === "success" ? "text-emerald-400" : "text-red-400"}`}>
                      {tc.status}
                    </span>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
            {toolCalls.length === 0 && (
              <p className="text-2xs text-os-muted">暂无工具调用</p>
            )}
          </div>
        </div>

        {/* Recent Traces */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Clock size={12} className="text-os-subtle" />
            <span className="text-2xs text-os-subtle uppercase tracking-wider">最近 Trace</span>
          </div>
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {traces.slice(-8).reverse().map((t) => (
              <div key={t.id} className="flex items-center justify-between text-2xs text-os-muted py-1">
                <span className="truncate flex-1 mr-2">{t.detail}</span>
                <span className="shrink-0">{t.status === "running" ? "⏳" : "✓"}</span>
              </div>
            ))}
            {traces.length === 0 && (
              <p className="text-2xs text-os-muted">暂无 Trace</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
