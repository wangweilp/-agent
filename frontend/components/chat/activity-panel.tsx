"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useChatStore } from "@/stores/chat-store";
import { useAgentStore } from "@/stores/agent-store";
import {
  Wrench, Brain, Activity, Clock, Cpu,
  CircleDot, Zap, ChevronRight, Layers,
} from "lucide-react";
import { formatDate } from "@/lib/utils";

interface Props {
  agentPhase?: string;
}

export function ActivityPanel({ agentPhase = "idle" }: Props) {
  const toolCalls = useChatStore((s) => s.toolCalls);
  const isThinking = useChatStore((s) => s.isThinking);
  const traces = useAgentStore((s) => s.traces);
  const status = useAgentStore((s) => s.status);

  const isIdle = status === "idle" && !isThinking && toolCalls.length === 0;
  const isActive = !isIdle;

  return (
    <div className="h-full flex flex-col bg-os-base/90 backdrop-blur-sm">
      {/* Header */}
      <div className="flex items-center px-4 h-10 border-b border-os-border shrink-0">
        <div className="relative mr-2">
          <Activity size={14} className="text-os-accent" />
          {isActive && (
            <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-os-accent animate-pulse" />
          )}
        </div>
        <span className="text-xs font-medium text-os-text-high">智能体活动</span>
        <div className="flex-1" />
        <div className={`
          flex items-center gap-1 px-1.5 py-0.5 rounded-full text-2xs
          ${isIdle ? "bg-emerald-400/8 text-emerald-400/80" : "bg-indigo-400/8 text-indigo-400/80"}
        `}>
          <div className={`w-1 h-1 rounded-full ${isIdle ? "bg-emerald-400" : "bg-indigo-400 animate-pulse"}`} />
          {isIdle ? "待命" : "运行中"}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {/* ── Agent 状态卡片 ── */}
        <div className={`rounded-xl p-3.5 border transition-all duration-500 ${
          isActive
            ? "bg-os-accent/5 border-os-accent/15 shadow-os-glow"
            : "bg-os-surface/50 border-os-border/50"
        }`}>
          <div className="flex items-center gap-2 mb-3">
            <Brain size={13} className={isActive ? "text-os-accent" : "text-os-subtle"} />
            <span className="text-2xs text-os-subtle uppercase tracking-wider">认知引擎</span>
          </div>

          {/* Status indicator */}
          <div className="flex items-center gap-3">
            <div className="relative">
              <div className={`w-8 h-8 rounded-xl flex items-center justify-center ${
                isActive ? "bg-os-accent/15" : "bg-os-elevated"
              }`}>
                <Cpu size={16} className={isActive ? "text-os-accent" : "text-os-muted"} />
              </div>
              {isActive && (
                <div className="absolute -inset-1 rounded-xl border border-os-accent/20 animate-pulse" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-xs font-medium ${isActive ? "text-os-accent" : "text-os-text-high"}`}>
                {status === "thinking" && "深度思考中"}
                {status === "acting" && "执行工具"}
                {status === "reflecting" && "自我反思"}
                {status === "idle" && "智能体就绪"}
              </p>
              <p className="text-2xs text-os-muted mt-0.5">
                {isIdle ? "等待您的指令，随时可以开始对话" : "正在处理您的请求..."}
              </p>
            </div>
          </div>

          {/* Phase indicator when active */}
          {isActive && (
            <div className="mt-3 flex items-center gap-2">
              <div className="flex-1 h-1 rounded-full bg-os-elevated overflow-hidden">
                <motion.div
                  className="h-full rounded-full bg-os-accent/40"
                  animate={{
                    width: agentPhase === "thinking" ? "60%" : agentPhase === "acting" ? "80%" : agentPhase === "reflecting" ? "40%" : "20%",
                  }}
                  transition={{ duration: 0.5 }}
                />
              </div>
              <span className="text-2xs text-os-muted whitespace-nowrap">
                {agentPhase === "retrieving" && "检索"}
                {agentPhase === "thinking" && "推理"}
                {agentPhase === "acting" && "执行"}
                {agentPhase === "reflecting" && "反思"}
              </span>
            </div>
          )}
        </div>

        {/* ── 工具调用 ── */}
        <div>
          <div className="flex items-center gap-2 mb-2.5">
            <Wrench size={12} className="text-os-subtle" />
            <span className="text-2xs text-os-subtle uppercase tracking-wider">工具调用</span>
            {toolCalls.length > 0 && (
              <span className="text-2xs text-os-accent ml-auto">{toolCalls.length}</span>
            )}
          </div>
          <div className="space-y-1.5">
            <AnimatePresence>
              {toolCalls.map((tc) => (
                <motion.div
                  key={tc.call_id}
                  initial={{ opacity: 0, height: 0, scale: 0.95 }}
                  animate={{ opacity: 1, height: "auto", scale: 1 }}
                  exit={{ opacity: 0, height: 0, scale: 0.95 }}
                  className="os-panel px-3 py-2.5"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className={`
                        w-1.5 h-1.5 rounded-full shrink-0
                        ${tc.status === "running" ? "bg-amber-400 animate-pulse" : ""}
                        ${tc.status === "success" ? "bg-emerald-400" : ""}
                        ${tc.status === "failed" ? "bg-red-400" : ""}
                      `} />
                      <span className="text-xs text-os-text-high font-medium truncate">{tc.tool_name}</span>
                    </div>
                    <span className={`text-2xs shrink-0 ml-2 ${
                      tc.status === "running" ? "text-amber-400" :
                      tc.status === "success" ? "text-emerald-400" :
                      "text-red-400"
                    }`}>
                      {tc.status === "running" ? "执行中" :
                       tc.status === "success" ? "完成" :
                       tc.status === "failed" ? "失败" : tc.status}
                    </span>
                  </div>
                  {tc.status === "running" && (
                    <div className="mt-2 h-0.5 rounded-full bg-os-elevated overflow-hidden">
                      <motion.div
                        className="h-full rounded-full bg-amber-400/40"
                        animate={{ width: ["0%", "80%", "0%"] }}
                        transition={{ duration: 1.5, repeat: Infinity }}
                      />
                    </div>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
            {toolCalls.length === 0 && (
              <div className="text-center py-4">
                <div className="w-8 h-8 rounded-lg bg-os-elevated border border-os-border/30 flex items-center justify-center mx-auto mb-1.5">
                  <Wrench size={12} className="text-os-muted/60" />
                </div>
                <p className="text-2xs text-os-muted/60">待命中 — 发送消息后可观察工具调用</p>
              </div>
            )}
          </div>
        </div>

        {/* ── 最近 Trace ── */}
        <div>
          <div className="flex items-center gap-2 mb-2.5">
            <Clock size={12} className="text-os-subtle" />
            <span className="text-2xs text-os-subtle uppercase tracking-wider">认知 Trace</span>
            {traces.length > 0 && (
              <span className="text-2xs text-os-muted ml-auto">{traces.length}</span>
            )}
          </div>
          <div className="space-y-0.5 max-h-56 overflow-y-auto">
            {traces.slice(-10).reverse().map((t, i) => (
              <motion.div
                key={t.id}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03 }}
                className="flex items-center gap-2 px-2.5 py-1.5 rounded-md hover:bg-os-elevated/50 transition-colors group"
              >
                <div className={`
                  w-1 h-1 rounded-full shrink-0
                  ${t.status === "running" ? "bg-amber-400" : "bg-emerald-400/50"}
                `} />
                <span className="text-2xs text-os-text/80 truncate flex-1">{t.detail}</span>
                <span className="text-2xs text-os-muted/60 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                  {t.status === "running" ? "运行中" : "完成"}
                </span>
              </motion.div>
            ))}
            {traces.length === 0 && (
              <div className="text-center py-4">
                <div className="w-8 h-8 rounded-lg bg-os-elevated border border-os-border/30 flex items-center justify-center mx-auto mb-1.5">
                  <Layers size={12} className="text-os-muted/60" />
                </div>
                <p className="text-2xs text-os-muted/60">暂无 Trace — 对话后将显示认知过程</p>
              </div>
            )}
          </div>
        </div>

        {/* ── Idle 状态额外提示 ── */}
        {isIdle && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="rounded-lg bg-os-surface/30 border border-os-border/30 p-3 space-y-2"
          >
            <div className="flex items-center gap-2">
              <Zap size={11} className="text-os-accent/50" />
              <span className="text-2xs text-os-subtle">功能提示</span>
            </div>
            <div className="space-y-1.5">
              {[
                { icon: CircleDot, text: "输入问题开始对话" },
                { icon: CircleDot, text: "智能体自动检索相关记忆" },
                { icon: CircleDot, text: "支持图片上传与 OCR" },
                { icon: CircleDot, text: "工具调用实时可见" },
              ].map((item, i) => (
                <div key={i} className="flex items-center gap-1.5 text-2xs text-os-muted/70">
                  <item.icon size={6} className="text-os-accent/40 shrink-0" />
                  <span>{item.text}</span>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}
