"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Lightbulb, TrendingUp, AlertTriangle, Sparkles } from "lucide-react";
import { api } from "@/services/api";
import { PageTransition, StaggerItem } from "@/components/animations/page-transition";
import { ReflectionTimeline } from "@/components/reflection/reflection-timeline";
import { InsightCard } from "@/components/reflection/insight-card";
import { CardSkeleton } from "@/components/animations/skeleton";
import type { ReflectionInsight } from "@/types";

export default function ReflectionPage() {
  const { data: insights, isLoading } = useQuery({
    queryKey: ["reflections"],
    queryFn: () => api.reflection.list(),
    refetchInterval: 20000,
  });

  const list = insights || [];

  // Demo insights for UI demonstration (固定时间戳避免 hydration mismatch)
  const demoInsights: ReflectionInsight[] = list.length > 0 ? list : [
    {
      id: "1",
      topic: "用户学习路径分析",
      finding: "用户在过去两周持续学习 Rust 和系统编程，与之前提到的「想深入理解计算机底层」目标一致。建议关注操作系统相关知识的积累。",
      confidence: 0.85,
      timestamp: "2026-05-26T20:00:00.000Z",
      related_memories: ["m1", "m2", "m3"],
    },
    {
      id: "2",
      topic: "知识体系矛盾检测",
      finding: "用户提到「喜欢静态类型的安全性」但同时表示「Python 的动态性让开发更快」。这并非真正矛盾，而是反映用户在不同场景下的工具偏好。",
      confidence: 0.72,
      timestamp: "2026-05-26T18:00:00.000Z",
      related_memories: ["m4", "m5"],
    },
    {
      id: "3",
      topic: "长期兴趣模式",
      finding: "用户对 AI Agent 架构的兴趣呈上升趋势，从最初的 LLM 调用逐步深入到 Memory 系统和认知架构。这可能预示用户正在构建自己的 Agent 项目。",
      confidence: 0.91,
      timestamp: "2026-05-26T16:00:00.000Z",
      related_memories: ["m6", "m7", "m8", "m9"],
    },
  ];

  return (
    <PageTransition>
      <div className="p-6 space-y-6 max-w-[1440px] mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight">反思</h1>
            <p className="text-xs text-os-subtle mt-0.5">AI 自我反思 — 矛盾检测、模式发现与深度洞察</p>
          </div>
          <div className="flex items-center gap-2 text-2xs text-os-subtle">
            <Sparkles size={12} className="text-amber-400" />
            {demoInsights.length} 条洞察
          </div>
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <StaggerItem delay={0}>
            <div className="os-card p-4 flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-amber-400/10 flex items-center justify-center">
                <Lightbulb size={18} className="text-amber-400" />
              </div>
              <div>
                <p className="text-2xs text-os-subtle">总洞察数</p>
                <p className="text-lg font-semibold text-os-text-high font-mono">{demoInsights.length}</p>
              </div>
            </div>
          </StaggerItem>
          <StaggerItem delay={0.05}>
            <div className="os-card p-4 flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-emerald-400/10 flex items-center justify-center">
                <TrendingUp size={18} className="text-emerald-400" />
              </div>
              <div>
                <p className="text-2xs text-os-subtle">平均置信度</p>
                <p className="text-lg font-semibold text-os-text-high font-mono">
                  {Math.round(demoInsights.reduce((s, i) => s + i.confidence, 0) / demoInsights.length * 100)}%
                </p>
              </div>
            </div>
          </StaggerItem>
          <StaggerItem delay={0.1}>
            <div className="os-card p-4 flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-violet-400/10 flex items-center justify-center">
                <AlertTriangle size={18} className="text-violet-400" />
              </div>
              <div>
                <p className="text-2xs text-os-subtle">发现矛盾</p>
                <p className="text-lg font-semibold text-os-text-high font-mono">1</p>
              </div>
            </div>
          </StaggerItem>
        </div>

        {/* Insights Grid */}
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (<CardSkeleton key={i} />))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {demoInsights.map((insight, i) => (
              <StaggerItem key={insight.id} delay={i * 0.08}>
                <InsightCard insight={insight} />
              </StaggerItem>
            ))}
          </div>
        )}

        {/* Timeline */}
        <StaggerItem delay={0.3}>
          <div className="os-card p-4">
            <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider mb-4">反思时间线</h2>
            <ReflectionTimeline insights={demoInsights} />
          </div>
        </StaggerItem>
      </div>
    </PageTransition>
  );
}
