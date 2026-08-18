"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  BrainCircuit,
  ChevronDown,
  ChevronRight,
  Clock,
  Cpu,
  GitBranch,
  Layers,
  Play,
  Radio,
  RefreshCw,
  ShieldAlert,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { PageTransition } from "@/components/animations/page-transition";
import {
  EmptyState,
  InfoBanner,
  MetricCard,
  OsButton,
  OsCard,
  PageHeader,
  PageShell,
  StatusBadge,
  Toolbar,
  chipStyles,
} from "@/components/ui/os";
import { cn, formatDate } from "@/lib/utils";
import { causalKernel, createChildEvent, createRootEvent, newTraceId } from "@/lib/event-bus/causal-kernel";
import { useCausalChain, useEventReplay, useEventStream, useKernelStats, useRecentTraces } from "@/hooks/use-event-stream";
import type { CausalChainNode, CauseType, EventSeverity, EventSource, SystemEvent } from "@/types/event-bus";
import { layout } from "@/styles/layout";
import { tabStyles } from "@/styles/components";

type SourceStyle = {
  label: string;
  dot: string;
  text: string;
  badge: string;
  metricAccent: "primary" | "success" | "warning" | "danger" | "info" | "muted";
  icon: LucideIcon;
};

const SOURCE_STYLE: Record<EventSource, SourceStyle> = {
  runtime: {
    label: "运行时",
    dot: "bg-os-danger",
    text: "text-os-danger",
    badge: "border-os-danger/20 bg-os-danger-soft text-os-danger",
    metricAccent: "danger",
    icon: ShieldAlert,
  },
  memory: {
    label: "记忆",
    dot: "bg-os-primary",
    text: "text-os-primary",
    badge: "border-os-primary/20 bg-os-primary-soft text-os-primary",
    metricAccent: "primary",
    icon: BrainCircuit,
  },
  governance: {
    label: "治理",
    dot: "bg-os-warning",
    text: "text-os-warning",
    badge: "border-os-warning/20 bg-os-warning-soft text-os-warning",
    metricAccent: "warning",
    icon: AlertTriangle,
  },
  agent: {
    label: "智能体",
    dot: "bg-os-info",
    text: "text-os-info",
    badge: "border-os-info/20 bg-os-info-soft text-os-info",
    metricAccent: "info",
    icon: Cpu,
  },
  observability: {
    label: "可观测性",
    dot: "bg-os-success",
    text: "text-os-success",
    badge: "border-os-success/20 bg-os-success-soft text-os-success",
    metricAccent: "success",
    icon: Activity,
  },
};

const SEVERITY_STYLE: Record<EventSeverity, { dot: string; text: string; label: string }> = {
  info: { dot: "bg-os-muted", text: "text-os-subtle", label: "信息" },
  warn: { dot: "bg-os-warning", text: "text-os-warning", label: "警告" },
  critical: { dot: "bg-os-danger", text: "text-os-danger", label: "严重" },
};

const CAUSE_LABELS: Record<CauseType, string> = {
  user_action: "用户行为",
  system_policy: "系统策略",
  agent_decision: "智能体决策",
  system_event: "系统事件",
  external_trigger: "外部触发",
};

type TabId = "stream" | "replay" | "causal";

const TABS: { id: TabId; label: string; icon: LucideIcon; hint: string }[] = [
  { id: "stream", label: "实时事件流", icon: Radio, hint: "实时事件流" },
  { id: "replay", label: "追踪回放", icon: Play, hint: "链路回放" },
  { id: "causal", label: "因果链", icon: GitBranch, hint: "因果链树" },
];

export default function CausalKernelPage() {
  const [active, setActive] = useState<TabId>("stream");
  const [visited, setVisited] = useState<Set<TabId>>(new Set(["stream"]));
  const stats = useKernelStats();

  const select = (id: TabId) => {
    setActive(id);
    setVisited((prev) => new Set(prev).add(id));
  };

  const renderTab = (id: TabId) => {
    switch (id) {
      case "stream":
        return <LiveStreamTab />;
      case "replay":
        return <ReplayTab />;
      case "causal":
        return <CausalChainTab />;
    }
  };

  return (
    <PageTransition>
      <PageShell>
        <PageHeader
          icon={BrainCircuit}
          title="知维 OS 因果内核"
          subtitle="事件驱动内核层：因果关系追踪、追踪记录回放与跨模块事件统一。"
          actions={
            <>
              <StatusBadge status="ready">
                {stats.storedEvents} 个事件 · {stats.traceCount} 条追踪记录
              </StatusBadge>
              <OsButton onClick={simulateEventFlow} size="sm" variant="soft">
                <Zap size={13} />
                模拟事件流
              </OsButton>
            </>
          }
        />

        <div className={layout.grid.five}>
          {(Object.keys(SOURCE_STYLE) as EventSource[]).map((source) => {
            const cfg = SOURCE_STYLE[source];
            return (
              <MetricCard
                key={source}
                label={cfg.label}
                value={stats.bySource[source]}
                icon={cfg.icon}
                accent={cfg.metricAccent}
                detail="事件来源"
              />
            );
          })}
        </div>

        <InfoBanner variant="info" title="因果内核边界">
          事件总线（Event Bus）不等同于日志系统或普通消息队列。每个事件携带 parent_event_id 与 cause_type，形成可回放、可解释的因果链。
        </InfoBanner>

        <Toolbar className="overflow-x-auto">
          {TABS.map((tab) => {
            const isActive = active === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => select(tab.id)}
                className={tabStyles({ active: isActive })}
                title={tab.hint}
                type="button"
              >
                <tab.icon size={14} />
                <span>{tab.label}</span>
                {isActive && (
                  <motion.span
                    layoutId="causal-kernel-tab"
                    className="absolute inset-x-3 -bottom-[7px] h-0.5 rounded-full bg-os-success"
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

function LiveStreamTab() {
  const [filterSource, setFilterSource] = useState<EventSource | "all">("all");
  const { events, total, clear } = useEventStream(
    useMemo(() => ({ source: filterSource === "all" ? undefined : filterSource }), [filterSource]),
    100,
  );

  return (
    <div className="space-y-4">
      <Toolbar>
        <span className="mr-1 text-xs font-medium text-os-subtle">来源</span>
        <FilterChip active={filterSource === "all"} onClick={() => setFilterSource("all")} label="全部" />
        {(Object.keys(SOURCE_STYLE) as EventSource[]).map((src) => (
          <FilterChip
            key={src}
            active={filterSource === src}
            onClick={() => setFilterSource(src)}
            label={SOURCE_STYLE[src].label}
          />
        ))}
        <div className="ml-auto flex items-center gap-2">
          <span className="font-mono text-xs text-os-subtle">已接收 {total} 条</span>
          <OsButton onClick={clear} size="sm" variant="ghost">
            清空
          </OsButton>
        </div>
      </Toolbar>

      <OsCard padding="none" className="overflow-hidden">
        {events.length === 0 ? (
          <EmptyState
            icon={Radio}
            title="等待事件流入"
            description="点击右上角“模拟事件流”生成一条完整的观测、决策、治理、运行时与记忆写入链路。"
            action={
              <OsButton onClick={simulateEventFlow} size="sm" variant="soft">
                <Zap size={13} />
                生成示例事件
              </OsButton>
            }
            className="m-4"
          />
        ) : (
          <ul className="max-h-[620px] divide-y divide-os-border overflow-y-auto">
            <AnimatePresence initial={false}>
              {events.map((event) => (
                <EventRow key={event.event_id} event={event} />
              ))}
            </AnimatePresence>
          </ul>
        )}
      </OsCard>
    </div>
  );
}

function ReplayTab() {
  const traces = useRecentTraces(20);
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);
  const { events, isLoading } = useEventReplay(selectedTrace);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
      <OsCard padding="none" className="overflow-hidden">
        <PanelTitle icon={Layers} title="追踪记录列表" count={traces.length} />
        {traces.length === 0 ? (
          <EmptyState icon={Layers} title="暂无追踪记录" description="生成示例事件后，这里会出现可回放链路。" className="m-4" />
        ) : (
          <div className="max-h-[620px] divide-y divide-os-border overflow-y-auto">
            {traces.map((tid) => (
              <button
                key={tid}
                onClick={() => setSelectedTrace(tid)}
                className={cn(
                  "flex w-full items-center gap-2 px-4 py-3 text-left transition-colors duration-150",
                  selectedTrace === tid ? "bg-os-primary-soft text-os-primary" : "hover:bg-os-surface-hover",
                )}
                type="button"
              >
                <span className="h-2 w-2 rounded-full bg-current opacity-70" />
                <span className="min-w-0 flex-1 truncate font-mono text-xs">{tid}</span>
              </button>
            ))}
          </div>
        )}
      </OsCard>

      <OsCard padding="none" className="overflow-hidden">
        <PanelTitle icon={Play} title="回放链路" detail={selectedTrace ?? undefined} count={events.length} />
        {!selectedTrace ? (
          <EmptyState icon={Play} title="选择一条追踪记录" description="从左侧选择追踪记录后，可查看按时间排序的事件链。" className="m-4" />
        ) : isLoading ? (
          <EmptyState icon={RefreshCw} title="加载中" description="正在从因果内核读取追踪事件。" className="m-4" />
        ) : events.length === 0 ? (
          <EmptyState icon={Clock} title="该追踪记录暂无事件" description="追踪记录存在，但当前没有可回放事件。" className="m-4" />
        ) : (
          <ul className="divide-y divide-os-border">
            {events.map((event, idx) => (
              <ReplayEventRow key={event.event_id} event={event} index={idx} />
            ))}
          </ul>
        )}
      </OsCard>
    </div>
  );
}

function CausalChainTab() {
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const stats = useKernelStats();
  const chain = useCausalChain(selectedEventId);

  const rootEvents = useMemo(() => {
    return causalKernel.getRecentEvents(200).filter((e) => e.causal.parent_event_id === null);
  }, [stats.storedEvents]);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[420px_minmax(0,1fr)]">
      <OsCard padding="none" className="overflow-hidden">
        <PanelTitle icon={GitBranch} title="根事件" count={rootEvents.length} />
        {rootEvents.length === 0 ? (
          <EmptyState icon={GitBranch} title="暂无根事件" description="根事件是因果链的起点，生成示例后可查看。" className="m-4" />
        ) : (
          <div className="max-h-[620px] divide-y divide-os-border overflow-y-auto">
            {rootEvents.map((event) => {
              const style = SOURCE_STYLE[event.source];
              const selected = selectedEventId === event.event_id;
              return (
                <button
                  key={event.event_id}
                  onClick={() => setSelectedEventId(event.event_id)}
                  className={cn(
                    "w-full px-4 py-3 text-left transition-colors duration-150",
                    selected ? "bg-os-primary-soft" : "hover:bg-os-surface-hover",
                  )}
                  type="button"
                >
                  <div className="flex items-center gap-2">
                    <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", style.badge)}>
                      {style.label}
                    </span>
                    <span className="min-w-0 flex-1 truncate font-mono text-xs text-os-text-high">{event.type}</span>
                  </div>
                  <div className="mt-1 truncate font-mono text-[11px] text-os-subtle">{event.event_id}</div>
                </button>
              );
            })}
          </div>
        )}
      </OsCard>

      <OsCard padding="none" className="overflow-hidden">
        <PanelTitle icon={GitBranch} title="因果链树" detail={selectedEventId?.slice(0, 18)} />
        <div className="min-h-[420px] p-4">
          {!chain ? (
            <EmptyState icon={GitBranch} title="选择根事件查看链路" description="因果链树会展示父事件、子事件、cause_type 与载荷摘要。" />
          ) : (
            <CausalNode node={chain} />
          )}
        </div>
      </OsCard>
    </div>
  );
}

function CausalNode({ node }: { node: CausalChainNode }) {
  const [expanded, setExpanded] = useState(true);
  const event = node.event;
  const source = SOURCE_STYLE[event.source];
  const severity = SEVERITY_STYLE[event.severity];

  return (
    <div className={cn("relative", node.depth > 0 && "ml-4 border-l border-os-border pl-4")}>
      <motion.div
        initial={{ opacity: 0, x: -8 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: Math.min(node.depth * 0.04, 0.18) }}
        className="mb-2 rounded-2xl border border-os-border bg-white p-3 shadow-os-card"
      >
        <div className="flex min-w-0 items-center gap-2">
          {node.children.length > 0 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="shrink-0 rounded-lg p-1 text-os-muted hover:bg-os-surface-hover hover:text-os-text-high"
              aria-label={expanded ? "收起子事件" : "展开子事件"}
              type="button"
            >
              {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>
          )}
          <span className={cn("h-2 w-2 shrink-0 rounded-full", severity.dot)} />
          <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", source.badge)}>
            {source.label}
          </span>
          <span className="min-w-0 flex-1 truncate font-mono text-xs text-os-text-high">{event.type}</span>
          <span className="shrink-0 text-xs text-os-subtle">{formatDate(event.timestamp)}</span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-os-subtle">
          <span className="font-mono">{event.event_id.slice(0, 12)}</span>
          <span className={source.text}>{CAUSE_LABELS[event.causal.cause_type]}</span>
          <span className={severity.text}>{severity.label}</span>
          <span className="font-mono">载荷：{Object.keys(event.payload as object).join(", ") || "空"}</span>
        </div>
      </motion.div>
      {expanded && node.children.length > 0 && (
        <div className="space-y-1">
          {node.children.map((child) => (
            <CausalNode key={child.event.event_id} node={child} />
          ))}
        </div>
      )}
    </div>
  );
}

function EventRow({ event }: { event: SystemEvent }) {
  const source = SOURCE_STYLE[event.source];
  const severity = SEVERITY_STYLE[event.severity];

  return (
    <motion.li
      layout
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0 }}
      className="px-4 py-3 transition-colors duration-150 hover:bg-os-surface-hover"
    >
      <div className="flex min-w-0 items-center gap-2">
        <span className={cn("h-2 w-2 shrink-0 rounded-full", severity.dot)} />
        <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", source.badge)}>
          {source.label}
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-os-text-high">{event.type}</span>
        {event.causal.parent_event_id && (
          <span className="hidden items-center gap-0.5 rounded-full bg-os-surface-muted px-2 py-0.5 text-[11px] text-os-subtle sm:flex">
            <ChevronRight size={10} />
            子事件
          </span>
        )}
        <span className="shrink-0 text-xs text-os-subtle">{formatDate(event.timestamp)}</span>
      </div>
      <div className="mt-1 flex min-w-0 flex-wrap items-center gap-2 text-[11px] text-os-subtle">
        <span className="font-mono">{event.event_id.slice(0, 12)}</span>
        <span className="font-mono">{event.trace_id.slice(0, 22)}</span>
        <span className={severity.text}>{severity.label}</span>
        <span className={source.text}>{CAUSE_LABELS[event.causal.cause_type]}</span>
      </div>
    </motion.li>
  );
}

function ReplayEventRow({ event, index }: { event: SystemEvent; index: number }) {
  const source = SOURCE_STYLE[event.source];
  const severity = SEVERITY_STYLE[event.severity];

  return (
    <motion.li
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.025 }}
      className="px-4 py-3"
    >
      <div className="flex min-w-0 items-center gap-2">
        <span className="w-8 shrink-0 font-mono text-xs text-os-subtle">#{index + 1}</span>
        <span className={cn("h-2 w-2 shrink-0 rounded-full", severity.dot)} />
        <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", source.badge)}>
          {source.label}
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-os-text-high">{event.type}</span>
        <span className="shrink-0 text-xs text-os-subtle">{formatDate(event.timestamp)}</span>
      </div>
      <div className="mt-2 ml-10 flex min-w-0 flex-wrap items-center gap-2 text-[11px] text-os-subtle">
        <span className="font-mono">{event.event_id.slice(0, 12)}</span>
        <span className={severity.text}>{severity.label}</span>
        {event.causal.parent_event_id ? (
          <span className="font-mono text-os-primary">父事件 {event.causal.parent_event_id.slice(0, 12)}</span>
        ) : (
          <span className="font-semibold text-os-success">根节点</span>
        )}
      </div>
      <p className="mt-1 ml-10 truncate font-mono text-[11px] text-os-subtle">
        载荷：{JSON.stringify(event.payload).slice(0, 140)}
        {JSON.stringify(event.payload).length > 140 && "..."}
      </p>
    </motion.li>
  );
}

function PanelTitle({
  icon: Icon,
  title,
  count,
  detail,
}: {
  icon: LucideIcon;
  title: string;
  count?: number;
  detail?: string;
}) {
  return (
    <div className="flex min-h-11 items-center gap-2 border-b border-os-border px-4">
      <Icon size={14} className="text-os-primary" />
      <h2 className="text-sm font-semibold text-os-text-high">{title}</h2>
      {detail && <span className="min-w-0 truncate font-mono text-[11px] text-os-subtle">{detail}</span>}
      {typeof count === "number" && <span className="ml-auto font-mono text-xs text-os-subtle">{count}</span>}
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button onClick={onClick} className={chipStyles({ active })} type="button">
      {label}
    </button>
  );
}

function simulateEventFlow() {
  const trace_id = newTraceId("trace");

  const traceStart = createRootEvent(
    "observability",
    "observability.trace.started",
    "info",
    trace_id,
    { trace_id, trigger: "user_action", context: { source: "causal_kernel_ui" } },
    "user_action",
  );

  const agentDecision = createChildEvent(
    traceStart,
    "agent",
    "agent.decision.made",
    "info",
    {
      agent_id: "agent-001",
      decision: "execute_tool",
      reasoning: "用户请求执行文件下载，需进入治理评估",
      confidence: 0.85,
      alternatives_considered: ["ask_confirmation", "deny"],
    },
    "agent_decision",
  );

  const policyEval = createChildEvent(
    agentDecision,
    "governance",
    "governance.policy.evaluated",
    "warn",
    {
      policy_id: "download-gate-v1",
      policy_name: "Download Gate",
      decision: "denied",
      evaluated_rules: ["network_whitelist", "domain_check"],
      violations: ["domain_not_in_whitelist"],
      warnings: [],
    },
    "system_policy",
  );

  const gateDenied = createChildEvent(
    policyEval,
    "runtime",
    "runtime.gate.denied",
    "critical",
    {
      gate_type: "download",
      target_id: "download-req-001",
      violated_rules: ["domain_not_in_whitelist"],
      requested_resource: "https://malicious.example.com/file.exe",
    },
    "system_policy",
  );

  createChildEvent(
    gateDenied,
    "governance",
    "governance.audit.record_generated",
    "info",
    {
      audit_id: "audit-001",
      action: "gate_denied",
      resource_type: "download_request",
      resource_id: "download-req-001",
      actor: "system",
    },
    "system_event",
  );

  createChildEvent(
    gateDenied,
    "memory",
    "memory.write.ltm",
    "info",
    {
      memory_id: "mem-001",
      tier: "ltm",
      memory_type: "episodic",
      content_preview: "Download request denied by gate: domain not in whitelist",
      importance: 7,
      source: "agent",
      entities: ["download-gate", "malicious.example.com"],
    },
    "system_event",
  );

  createChildEvent(
    traceStart,
    "observability",
    "observability.trace.completed",
    "info",
    {
      trace_id,
      event_count: 7,
      duration_ms: 42,
      status: "success",
    },
    "system_event",
  );
}
