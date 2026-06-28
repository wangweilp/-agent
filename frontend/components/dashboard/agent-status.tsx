"use client";

import { motion } from "framer-motion";
import { useAgentStore } from "@/stores/agent-store";
import { Brain, Zap, Activity, Cpu } from "lucide-react";

export function AgentStatusPanel() {
  const status = useAgentStore((s) => s.status);
  const traceId = useAgentStore((s) => s.traceId);
  const traces = useAgentStore((s) => s.traces);

  const phases = [
    { key: "idle", label: "就绪", icon: Activity },
    { key: "thinking", label: "思考", icon: Brain },
    { key: "acting", label: "执行", icon: Zap },
    { key: "reflecting", label: "反思", icon: Cpu },
  ];

  const currentIdx = phases.findIndex((p) => p.key === status);

  return (
    <div className="space-y-6">
      {/* Phase indicators */}
      <div className="flex items-center gap-1.5">
        {phases.map((phase, i) => {
          const isActive = i <= currentIdx;
          const isCurrent = i === currentIdx;
          const Icon = phase.icon;
          return (
            <div key={phase.key} className="flex items-center gap-1.5 flex-1">
              <motion.div
                animate={isCurrent ? { scale: [1, 1.05, 1] } : {}}
                transition={{ duration: 2, repeat: Infinity }}
                className={`flex-1 flex flex-col items-center gap-1.5 p-3 rounded-lg transition-colors ${
                  isActive ? "bg-os-accent/5" : "opacity-30"
                }`}
              >
                <Icon size={16} className={isCurrent ? "text-os-accent" : "text-os-subtle"} />
                <span className="text-xs text-os-subtle">{phase.label}</span>
              </motion.div>
              {i < phases.length - 1 && (
                <div className={`w-3 h-px ${i < currentIdx ? "bg-os-accent/40" : "bg-os-border"}`} />
              )}
            </div>
          );
        })}
      </div>

      {/* Current state detail */}
      <div className="p-4 rounded-xl bg-os-elevated border border-os-border">
        <div className="flex items-center justify-between mb-2.5">
          <span className="text-xs text-os-subtle">当前状态</span>
          <motion.span
            key={status}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-sm font-medium text-os-accent"
          >
            {phases[currentIdx]?.label || "未知"}
          </motion.span>
        </div>
        {traceId && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-os-subtle">Trace ID</span>
            <span className="text-xs text-os-muted font-mono">{traceId.slice(0, 12)}</span>
          </div>
        )}
      </div>

      {/* Recent activity */}
      <div>
        <span className="text-xs text-os-subtle uppercase tracking-wider">最近活动</span>
        <div className="mt-3 space-y-1.5 max-h-32 overflow-y-auto">
          {traces.slice(-5).reverse().map((t) => (
            <div key={t.id} className="text-xs text-os-muted flex justify-between">
              <span className="truncate mr-2">{t.detail}</span>
              <span className="shrink-0">{t.status === "running" ? "⏳" : t.status === "success" ? "✓" : "✗"}</span>
            </div>
          ))}
          {traces.length === 0 && (
            <p className="text-xs text-os-muted">暂无活动</p>
          )}
        </div>
      </div>
    </div>
  );
}
