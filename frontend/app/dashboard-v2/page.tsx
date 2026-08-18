"use client";

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  LayoutDashboard,
  TrendingUp,
  Bot,
  Brain,
  Coins,
  Bell,
  Activity,
} from "lucide-react";
import { PageTransition } from "@/components/animations/page-transition";
import { cn } from "@/lib/utils";
import { TabOverview } from "@/components/dashboard-v2/tab-overview";
import { TabGrowth } from "@/components/dashboard-v2/tab-growth";
import { TabAgentPerformance } from "@/components/dashboard-v2/tab-agent-performance";
import { TabMemoryHealth } from "@/components/dashboard-v2/tab-memory-health";
import { TabCostAnalytics } from "@/components/dashboard-v2/tab-cost-analytics";
import { TabAlerts } from "@/components/dashboard-v2/tab-alerts";

type TabId = "overview" | "growth" | "agent" | "memory" | "cost" | "alerts";

const TABS: { id: TabId; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "overview", label: "概览", icon: LayoutDashboard },
  { id: "growth", label: "增长", icon: TrendingUp },
  { id: "agent", label: "智能体性能", icon: Bot },
  { id: "memory", label: "记忆健康", icon: Brain },
  { id: "cost", label: "成本分析", icon: Coins },
  { id: "alerts", label: "告警", icon: Bell },
];

export default function DashboardV2Page() {
  const [active, setActive] = useState<TabId>("overview");
  // 已访问过的 Tab — 懒挂载，切换后保持状态（hidden 而非卸载）。
  const [visited, setVisited] = useState<Set<TabId>>(new Set(["overview"]));

  const select = useCallback((id: TabId) => {
    setActive(id);
    setVisited((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  }, []);

  const renderTab = (id: TabId) => {
    switch (id) {
      case "overview": return <TabOverview />;
      case "growth": return <TabGrowth />;
      case "agent": return <TabAgentPerformance />;
      case "memory": return <TabMemoryHealth />;
      case "cost": return <TabCostAnalytics />;
      case "alerts": return <TabAlerts />;
    }
  };

  return (
    <PageTransition>
      <div className="p-4 md:p-6 space-y-5 max-w-[1440px] mx-auto">
        {/* ── Header ── */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight flex items-center gap-2">
              <Activity size={16} className="text-os-accent" />
              可观测性控制台
            </h1>
            <p className="text-xs text-os-subtle mt-0.5">仪表盘 V2 — 用户增长 · 智能体 · 记忆 · 成本 · 告警</p>
          </div>
          <div className="flex items-center gap-2 text-2xs text-os-subtle">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-status-breathe" />
            实时监控中
          </div>
        </div>

        {/* ── Tabs ── */}
        <div className="flex items-center gap-1 border-b border-os-border overflow-x-auto">
          {TABS.map((tab) => {
            const isActive = active === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => select(tab.id)}
                className={cn(
                  "relative flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors whitespace-nowrap",
                  isActive ? "text-os-text-high" : "text-os-subtle hover:text-os-text",
                )}
              >
                <tab.icon size={13} />
                {tab.label}
                {isActive && (
                  <motion.div
                    layoutId="dashboard-v2-tab"
                    className="absolute left-0 right-0 -bottom-px h-0.5 bg-os-accent"
                    transition={{ duration: 0.2 }}
                  />
                )}
              </button>
            );
          })}
        </div>

        {/* ── Tab panels (懒挂载 + hidden 保状态) ── */}
        {TABS.map((tab) => (
          <div key={tab.id} className={cn(active === tab.id ? "block" : "hidden")}>
            {visited.has(tab.id) && renderTab(tab.id)}
          </div>
        ))}
      </div>
    </PageTransition>
  );
}
