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
  { id: "kill", label: "熔断开关", icon: Power, hint: "实时终止控制" },
  { id: "gates", label: "门禁矩阵", icon: Fence, hint: "执行约束矩阵" },
  { id: "incidents", label: "事件中心", icon: AlertOctagon, hint: "安全事件流" },
  { id: "redteam", label: "红队测试", icon: FlaskConical, hint: "对抗测试结果" },
  { id: "simulator", label: "策略模拟", icon: SlidersHorizontal, hint: "沙箱策略模拟" },
];

const MODE_LABELS: Record<string, string> = {
  "metadata-only / simulation": "仅元数据 / 模拟运行",
  "metadata-only": "仅元数据",
  simulation: "模拟运行",
};

export default function RuntimeControlPlanePage() {
  const [active, setActive] = useState<TabId>("kill");
  const [visited, setVisited] = useState<Set<TabId>>(new Set(["kill"]));

  const { data: governance, refetch, isFetching, isError } = useQuery({
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
          title="运行时控制平面"
          subtitle="运行时治理控制面：熔断开关、门禁矩阵、安全事件、红队测试与策略模拟。"
          actions={
            <>
              <StatusBadge status={isError || governance?.production_sandbox === "disabled" ? "warning" : "ready"}>
                {isError
                  ? "治理数据加载失败"
                  : MODE_LABELS[governance?.current_mode || ""] || governance?.current_mode || "仅元数据 / 模拟运行"}
              </StatusBadge>
              <OsButton onClick={() => refetch()} disabled={isFetching} size="sm" variant="secondary">
                <RefreshCw size={13} className={cn(isFetching && "animate-spin")} />
                刷新
              </OsButton>
            </>
          }
        />

        {isError && (
          <InfoBanner variant="danger" title="运行时治理数据加载失败">
            当前控制数据可能不完整，请稍后刷新；页面不会将缺失数据标记为正常状态。
          </InfoBanner>
        )}

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
