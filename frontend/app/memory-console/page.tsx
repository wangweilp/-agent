"use client";

import { useCallback, useState } from "react";
import { motion } from "framer-motion";
import {
  BrainCircuit,
  Clock,
  Cpu,
  Layers,
  RefreshCw,
  Search,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { PageTransition } from "@/components/animations/page-transition";
import { MemoryFlowTimeline } from "@/components/memory-console/MemoryFlowTimeline";
import { MemoryOverview } from "@/components/memory-console/MemoryOverview";
import { ReflectionPanel } from "@/components/memory-console/ReflectionPanel";
import { VectorInspector } from "@/components/memory-console/VectorInspector";
import { InfoBanner, OsButton, PageHeader, PageShell, StatusBadge, Toolbar } from "@/components/ui/os";
import { cn } from "@/lib/utils";
import { api } from "@/services/api";
import { tabStyles } from "@/styles/components";

type TabId = "overview" | "timeline" | "reflection" | "retrieval";

const TABS: { id: TabId; label: string; icon: LucideIcon; hint: string }[] = [
  { id: "overview", label: "Memory Overview", icon: Layers, hint: "STM / WM / LTM 三层认知" },
  { id: "timeline", label: "Memory Flow", icon: Clock, hint: "记忆流转时间线" },
  { id: "reflection", label: "Reflection Engine", icon: Sparkles, hint: "冲突修复与洞察" },
  { id: "retrieval", label: "Retrieval Inspector", icon: Search, hint: "向量检索探针" },
];

export default function MemoryIntelligenceConsolePage() {
  const [active, setActive] = useState<TabId>("overview");
  const [visited, setVisited] = useState<Set<TabId>>(new Set(["overview"]));

  const { data: summary, refetch, isFetching } = useQuery({
    queryKey: ["memory-console-summary"],
    queryFn: () => api.dashboard.summary(),
    refetchInterval: 30000,
  });

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
      case "overview":
        return <MemoryOverview summary={summary} />;
      case "timeline":
        return <MemoryFlowTimeline />;
      case "reflection":
        return <ReflectionPanel />;
      case "retrieval":
        return <VectorInspector />;
    }
  };

  return (
    <PageTransition>
      <PageShell>
        <PageHeader
          icon={BrainCircuit}
          title="Memory Intelligence Console"
          subtitle="认知系统控制面：STM、WM、LTM、Reflection 与向量检索健康度。"
          actions={
            <>
              <StatusBadge status="info">
                <Cpu size={11} />
                {summary
                  ? `${summary.total_memories} memories | ${summary.episodic_count}E/${summary.semantic_count}S/${summary.reflect_count}R`
                  : "loading"}
              </StatusBadge>
              <OsButton onClick={() => refetch()} disabled={isFetching} size="sm" variant="secondary">
                <RefreshCw size={13} className={cn(isFetching && "animate-spin")} />
                刷新
              </OsButton>
            </>
          }
        />

        <InfoBanner variant="info" title="认知平面">
          Memory 不是日志列表。这里展示记忆结构、流转与检索质量，STM/WM/LTM 由 memory_type、status、importance 与 access_count 综合推断。
        </InfoBanner>

        <Toolbar className="overflow-x-auto">
          {TABS.map((tab) => {
            const isActive = active === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => select(tab.id)}
                className={cn(tabStyles({ active: isActive }), "group")}
                title={tab.hint}
                type="button"
              >
                <tab.icon size={14} />
                <span>{tab.label}</span>
                {isActive && (
                  <motion.span
                    layoutId="memory-console-tab-indicator"
                    className="absolute inset-x-3 -bottom-[7px] h-0.5 rounded-full bg-os-primary"
                    transition={{ duration: 0.18 }}
                  />
                )}
              </button>
            );
          })}
        </Toolbar>

        {TABS.map((tab) => (
          <section key={tab.id} className={cn(active === tab.id ? "block" : "hidden")}>
            {visited.has(tab.id) && renderTab(tab.id)}
          </section>
        ))}
      </PageShell>
    </PageTransition>
  );
}
