"use client";

import { useCallback, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertOctagon,
  Fence,
  FlaskConical,
  Power,
  RefreshCw,
  ShieldAlert,
  SlidersHorizontal,
  type LucideIcon,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { PageTransition } from "@/components/animations/page-transition";
import { GateMatrix } from "@/components/runtime/GateMatrix";
import { IncidentStream } from "@/components/runtime/IncidentStream";
import { KillSwitchPanel } from "@/components/runtime/KillSwitchPanel";
import { RedTeamResults } from "@/components/runtime/RedTeamResults";
import { SandboxSimulator } from "@/components/runtime/SandboxSimulator";
import { InfoBanner, OsButton, PageHeader, PageShell, StatusBadge, Toolbar } from "@/components/ui/os";
import { cn } from "@/lib/utils";
import { getRuntimeGovernanceSummary } from "@/services/runtime-admin";
import { tabStyles } from "@/styles/components";

type TabId = "kill" | "gates" | "incidents" | "redteam" | "simulator";

const TABS: { id: TabId; label: string; icon: LucideIcon; hint: string }[] = [
  { id: "kill", label: "Kill Switch", icon: Power, hint: "实时终止控制" },
  { id: "gates", label: "Gate Matrix", icon: Fence, hint: "执行约束矩阵" },
  { id: "incidents", label: "Incident Center", icon: AlertOctagon, hint: "安全事件流" },
  { id: "redteam", label: "Red Team", icon: FlaskConical, hint: "对抗测试结果" },
  { id: "simulator", label: "Policy Simulator", icon: SlidersHorizontal, hint: "沙箱策略模拟" },
];

export default function RuntimeControlPlanePage() {
  const [active, setActive] = useState<TabId>("kill");
  const [visited, setVisited] = useState<Set<TabId>>(new Set(["kill"]));

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
      case "kill":
        return <KillSwitchPanel governance={governance} />;
      case "gates":
        return <GateMatrix governance={governance} />;
      case "incidents":
        return <IncidentStream governance={governance} />;
      case "redteam":
        return <RedTeamResults governance={governance} />;
      case "simulator":
        return <SandboxSimulator />;
    }
  };

  return (
    <PageTransition>
      <PageShell>
        <PageHeader
          icon={ShieldAlert}
          title="Runtime Control Plane"
          subtitle="运行时治理控制面：Kill Switch、Gate Matrix、Incident、Red Team 与策略模拟。"
          actions={
            <>
              <StatusBadge status={governance?.production_sandbox === "disabled" ? "warning" : "ready"}>
                {governance?.current_mode || "metadata-only / simulation"}
              </StatusBadge>
              <OsButton onClick={() => refetch()} disabled={isFetching} size="sm" variant="secondary">
                <RefreshCw size={13} className={cn(isFetching && "animate-spin")} />
                刷新
              </OsButton>
            </>
          }
        />

        {governance?.boundary_statement && (
          <InfoBanner variant="warning" title="运行时边界声明">
            {governance.boundary_statement}
          </InfoBanner>
        )}

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
                    layoutId="runtime-tab-indicator"
                    className="absolute inset-x-3 -bottom-[7px] h-0.5 rounded-full bg-os-danger"
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
