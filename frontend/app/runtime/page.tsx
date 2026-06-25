"use client";

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  ShieldAlert,
  Power,
  Fence,
  AlertOctagon,
  FlaskConical,
  SlidersHorizontal,
  RefreshCw,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { PageTransition } from "@/components/animations/page-transition";
import { cn } from "@/lib/utils";
import { getRuntimeGovernanceSummary } from "@/services/runtime-admin";
import { KillSwitchPanel } from "@/components/runtime/KillSwitchPanel";
import { GateMatrix } from "@/components/runtime/GateMatrix";
import { IncidentStream } from "@/components/runtime/IncidentStream";
import { RedTeamResults } from "@/components/runtime/RedTeamResults";
import { SandboxSimulator } from "@/components/runtime/SandboxSimulator";

type TabId = "kill" | "gates" | "incidents" | "redteam" | "simulator";

const TABS: { id: TabId; label: string; icon: typeof Power; hint: string }[] = [
  { id: "kill", label: "Kill Switch", icon: Power, hint: "实时终止控制" },
  { id: "gates", label: "Gate Matrix", icon: Fence, hint: "执行约束矩阵" },
  { id: "incidents", label: "Incident Center", icon: AlertOctagon, hint: "安全事件流" },
  { id: "redteam", label: "Red Team", icon: FlaskConical, hint: "对抗测试结果" },
  { id: "simulator", label: "Policy Simulator", icon: SlidersHorizontal, hint: "沙箱策略模拟" },
];

export default function RuntimeControlPlanePage() {
  const [active, setActive] = useState<TabId>("kill");
  const [visited, setVisited] = useState<Set<TabId>>(new Set(["kill"]));

  // Governance summary — shared across all tabs as the metadata backbone.
  const { data: governance, refetch, isFetching } = useQuery({
    queryKey: ["runtime-governance-summary"],
    queryFn: () => getRuntimeGovernanceSummary(),
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
      case "kill": return <KillSwitchPanel governance={governance} />;
      case "gates": return <GateMatrix governance={governance} />;
      case "incidents": return <IncidentStream governance={governance} />;
      case "redteam": return <RedTeamResults governance={governance} />;
      case "simulator": return <SandboxSimulator />;
    }
  };

  return (
    <PageTransition>
      <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
        {/* ── Header ── */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight flex items-center gap-2">
              <ShieldAlert size={16} className="text-rose-400" />
              Runtime Control Plane
            </h1>
            <p className="text-xs text-os-subtle mt-0.5">
              运行时治理控制面 — Kill Switch · Gate Matrix · Incident · Red Team · Policy Simulator
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Live status indicator */}
            <div className="flex items-center gap-2 px-2.5 py-1 rounded-md border border-os-border bg-os-surface">
              <div className="relative">
                <div className={cn(
                  "w-1.5 h-1.5 rounded-full",
                  governance?.production_sandbox === "disabled" ? "bg-amber-400" : "bg-emerald-400"
                )} />
                <div className={cn(
                  "absolute inset-0 w-1.5 h-1.5 rounded-full animate-status-breathe",
                  governance?.production_sandbox === "disabled" ? "bg-amber-400" : "bg-emerald-400"
                )} />
              </div>
              <span className="text-2xs text-os-subtle font-mono">
                {governance?.current_mode || "metadata-only / simulation"}
              </span>
            </div>
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="flex items-center gap-1.5 h-7 px-2.5 rounded-md border border-os-border bg-os-surface text-2xs text-os-subtle hover:text-os-text-high hover:border-os-muted transition-colors disabled:opacity-50"
            >
              <RefreshCw size={11} className={isFetching ? "animate-spin" : ""} />
              刷新
            </button>
          </div>
        </div>

        {/* ── Boundary statement ── */}
        {governance?.boundary_statement && (
          <div className="rounded-md border border-amber-400/20 bg-amber-400/[0.03] px-3 py-2">
            <p className="text-2xs leading-5 text-amber-200/80">
              <span className="font-medium text-amber-300">边界声明 · </span>
              {governance.boundary_statement}
            </p>
          </div>
        )}

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
                <span>{tab.label}</span>
                {isActive && (
                  <motion.div
                    layoutId="runtime-tab"
                    className="absolute left-0 right-0 -bottom-px h-0.5 bg-rose-400"
                    transition={{ duration: 0.2 }}
                  />
                )}
              </button>
            );
          })}
        </div>

        {/* ── Tab panels ── */}
        {TABS.map((tab) => (
          <div key={tab.id} className={cn(active === tab.id ? "block" : "hidden")}>
            {visited.has(tab.id) && renderTab(tab.id)}
          </div>
        ))}
      </div>
    </PageTransition>
  );
}
