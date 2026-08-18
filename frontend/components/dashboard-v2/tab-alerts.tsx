"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bell, AlertTriangle, Info, XCircle, CheckCircle2 } from "lucide-react";
import { api } from "@/services/api";
import { SectionCard } from "./section-card";
import { QueryState, EmptyState } from "./query-state";
import { cn } from "@/lib/utils";

const STALE = 60 * 1000; // 1min

type SeverityFilter = "all" | "critical" | "warning";

const SEVERITY_STYLES: Record<string, string> = {
  info: "bg-cyan-400/10 text-cyan-700 border-cyan-400/20",
  warning: "bg-amber-400/10 text-amber-800 border-amber-400/20",
  critical: "bg-rose-400/10 text-rose-700 border-rose-400/20",
};

const SEVERITY_ICONS: Record<string, React.ReactNode> = {
  info: <Info size={12} />,
  warning: <AlertTriangle size={12} />,
  critical: <XCircle size={12} />,
};

const SEVERITY_LABELS: Record<string, string> = {
  info: "提示",
  warning: "警告",
  critical: "严重",
};

const FILTERS: { label: string; value: SeverityFilter }[] = [
  { label: "全部", value: "all" },
  { label: "严重", value: "critical" },
  { label: "警告", value: "warning" },
];

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN");
  } catch {
    return "—";
  }
}

export function TabAlerts() {
  const [filter, setFilter] = useState<SeverityFilter>("all");

  const rulesQ = useQuery({
    queryKey: ["dashboard-v2-alerts-rules"],
    queryFn: () => api.alerts.listRules(),
    staleTime: STALE,
  });

  const eventsQ = useQuery({
    queryKey: ["dashboard-v2-alerts-events"],
    queryFn: () => api.alerts.listEvents({ limit: 50 }),
    staleTime: STALE,
  });

  const isLoading = rulesQ.isLoading || eventsQ.isLoading;
  const isError = rulesQ.isError || eventsQ.isError;

  const rules = (rulesQ.data ?? []).filter((r) => filter === "all" || r.severity === filter);
  const events = (eventsQ.data ?? []).filter((e) => filter === "all" || e.severity === filter);

  const filterBar = (
    <div className="flex items-center gap-1 rounded-md border border-os-border p-0.5">
      {FILTERS.map((f) => (
        <button
          key={f.value}
          onClick={() => setFilter(f.value)}
          className={cn(
            "px-2 py-0.5 text-2xs rounded transition-colors",
            filter === f.value ? "bg-os-accent/15 text-os-accent" : "text-os-subtle hover:text-os-text",
          )}
        >
          {f.label}
        </button>
      ))}
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">{filterBar}</div>

      <SectionCard title={`告警规则 (${rules.length})`} icon={<Bell size={14} />}>
        <QueryState
          isLoading={rulesQ.isLoading}
          isError={rulesQ.isError}
          onRetry={() => rulesQ.refetch()}
          skeleton={<div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-10 rounded bg-os-elevated shimmer-bg" />)}</div>}
        >
          {rules.length === 0 ? (
            <EmptyState message={filter === "all" ? "暂无告警规则" : `无${SEVERITY_LABELS[filter] || filter}级别规则`} />
          ) : (
            <div className="divide-y divide-os-border/50">
              {rules.map((rule) => (
                <div key={rule.id} className="flex flex-col gap-2 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
                  <div className="flex w-full min-w-0 items-center gap-3 sm:w-auto">
                    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-2xs font-medium shrink-0", SEVERITY_STYLES[rule.severity] ?? SEVERITY_STYLES.info)}>
                      {SEVERITY_ICONS[rule.severity] ?? SEVERITY_ICONS.info}
                      {SEVERITY_LABELS[rule.severity] || rule.severity}
                    </span>
                    <div className="min-w-0">
                      <p className="text-xs text-os-text-high truncate">{rule.name}</p>
                      <p className="text-2xs text-os-subtle truncate">
                        {rule.metric} {rule.condition} {rule.threshold}
                      </p>
                    </div>
                  </div>
                  <div className="flex w-full items-center justify-between gap-3 sm:w-auto sm:shrink-0 sm:justify-start">
                    <span className={cn("text-2xs", rule.enabled ? "text-emerald-700" : "text-os-subtle")}>
                      {rule.enabled ? "启用" : "禁用"}
                    </span>
                    <span className="text-right text-2xs text-os-subtle sm:w-32">{formatTime(rule.last_triggered_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </QueryState>
      </SectionCard>

      <SectionCard title={`告警事件 (${events.length})`} icon={<AlertTriangle size={14} />}>
        <QueryState
          isLoading={eventsQ.isLoading}
          isError={eventsQ.isError}
          onRetry={() => eventsQ.refetch()}
          skeleton={<div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-10 rounded bg-os-elevated shimmer-bg" />)}</div>}
        >
          {events.length === 0 ? (
            <EmptyState message={filter === "all" ? "暂无告警事件" : `无${SEVERITY_LABELS[filter] || filter}级别事件`} />
          ) : (
            <div className="divide-y divide-os-border/50">
              {events.map((event) => (
                <div key={event.id} className="flex flex-col gap-2 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
                  <div className="flex w-full min-w-0 items-center gap-3 sm:w-auto">
                    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-2xs font-medium shrink-0", SEVERITY_STYLES[event.severity] ?? SEVERITY_STYLES.info)}>
                      {SEVERITY_ICONS[event.severity] ?? SEVERITY_ICONS.info}
                    </span>
                    <div className="min-w-0">
                      <p className="text-xs text-os-text truncate">{event.message}</p>
                      <p className="text-2xs text-os-subtle truncate">{event.rule_name}</p>
                    </div>
                  </div>
                  <div className="flex w-full items-center justify-between gap-3 sm:w-auto sm:shrink-0 sm:justify-start">
                    {event.acknowledged ? (
                      <span className="flex items-center gap-1 text-2xs text-emerald-700">
                        <CheckCircle2 size={11} /> 已确认
                      </span>
                    ) : (
                      <span className="text-2xs text-amber-800">未确认</span>
                    )}
                    <span className="text-right text-2xs text-os-subtle sm:w-32">{formatTime(event.triggered_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </QueryState>
      </SectionCard>

      {isError && !isLoading && (
        <div className="text-center text-2xs text-red-700">部分告警数据加载失败，可点击重试</div>
      )}
    </div>
  );
}
