"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Wrench, Shield, AlertTriangle } from "lucide-react";
import { api } from "@/services/api";
import { PageTransition, StaggerItem } from "@/components/animations/page-transition";
import { ToolCard } from "@/components/tools/tool-card";
import { CardSkeleton } from "@/components/animations/skeleton";
import type { ToolInfo } from "@/types";
import { layout } from "@/styles/layout";

// Static tool definitions for UI (backend /tools endpoint coming)
const defaultTools: ToolInfo[] = [
  {
    name: "remember",
    description: "存储新的长期记忆。分析内容重要性，检测新颖度，自动去重或合并相似记忆。",
    category: "记忆管理",
    requires_confirmation: false,
    call_count: 128,
    avg_duration_ms: 450,
    success_rate: 0.98,
    risk_level: "low",
    enabled: true,
  },
  {
    name: "recall",
    description: "语义检索长期记忆。向量搜索 + 实体匹配 → RRF 融合 + 时间衰减 + 重要性加权。",
    category: "记忆检索",
    requires_confirmation: false,
    call_count: 256,
    avg_duration_ms: 320,
    success_rate: 0.95,
    risk_level: "low",
    enabled: true,
  },
  {
    name: "reflect",
    description: "反思近期对话，发现矛盾、联系或知识盲点。含防自激机制，自动发现隐藏模式。",
    category: "认知引擎",
    requires_confirmation: false,
    call_count: 42,
    avg_duration_ms: 2800,
    success_rate: 0.88,
    risk_level: "medium",
    enabled: true,
  },
  {
    name: "delete_memory",
    description: "删除指定记忆。高度危险操作，需用户二次确认。",
    category: "记忆管理",
    requires_confirmation: true,
    call_count: 3,
    avg_duration_ms: 150,
    success_rate: 1.0,
    risk_level: "high",
    enabled: false,
  },
];

export default function ToolsPage() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string>("all");

  const filtered = defaultTools.filter((t) => {
    if (query && !t.name.includes(query) && !t.description.includes(query)) return false;
    if (category !== "all" && t.category !== category) return false;
    return true;
  });

  const categories = ["all", ...new Set(defaultTools.map((t) => t.category))];

  return (
    <PageTransition>
      <div className="p-6 space-y-6 max-w-[1440px] mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight">工具中心</h1>
            <p className="text-xs text-os-subtle mt-0.5">Tool Calling 管理与监控 — 权限分级、调用统计、性能指标</p>
          </div>
          <div className="flex items-center gap-2 text-2xs text-os-muted">
            <Wrench size={12} />
            {defaultTools.length} 个工具
          </div>
        </div>

        {/* Search & Filters */}
        <div className="flex items-center gap-3">
          <div className="flex-1 relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-os-muted" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索工具..."
              className="w-full h-9 pl-9 pr-4 bg-os-surface border border-os-border rounded-md text-sm text-os-text-high placeholder-os-muted outline-none focus:border-os-accent/50 transition-colors"
            />
          </div>
          <div className="flex items-center gap-1">
            {categories.map((c) => (
              <button
                key={c}
                onClick={() => setCategory(c)}
                className={`px-3 py-1.5 rounded-md text-xs whitespace-nowrap transition-all ${category === c ? "bg-os-accent/10 text-os-accent" : "text-os-subtle hover:text-os-text"}`}
              >
                {c === "all" ? "全部" : c}
              </button>
            ))}
          </div>
        </div>

        {/* Tools Grid */}
        <motion.div layout className={layout.grid.twoMd}>
          <AnimatePresence mode="popLayout">
            {filtered.map((tool, i) => (
              <StaggerItem key={tool.name} delay={i * 0.05}>
                <ToolCard tool={tool} />
              </StaggerItem>
            ))}
          </AnimatePresence>
        </motion.div>

        {filtered.length === 0 && (
          <div className="text-center py-20">
            <Wrench size={32} className="text-os-muted mx-auto mb-3" />
            <p className="text-os-subtle text-sm">未找到匹配的工具</p>
          </div>
        )}
      </div>
    </PageTransition>
  );
}
