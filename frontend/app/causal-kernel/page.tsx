"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BrainCircuit, Activity, GitBranch, Play, Pause, Zap,
  Radio, Clock, ChevronRight, ChevronDown, RefreshCw,
  Cpu, Layers, AlertTriangle, ShieldAlert,
} from "lucide-react";
import { PageTransition } from "@/components/animations/page-transition";
import { cn, formatDate } from "@/lib/utils";
import {
  causalKernel, createRootEvent, createChildEvent, newTraceId,
} from "@/lib/event-bus/causal-kernel";
import {
  useEventStream, useEventReplay, useCausalChain,
  useKernelStats, useRecentTraces,
} from "@/hooks/use-event-stream";
import type {
  SystemEvent, EventSource, EventSeverity, CauseType,
} from "@/types/event-bus";
import { layout } from "@/styles/layout";

// ── 事件来源样式映射 ──
const SOURCE_STYLE: Record<EventSource, { color: string; bg: string; border: string; label: string }> = {
  runtime: { color: "text-rose-400", bg: "bg-rose-400/10", border: "border-rose-400/25", label: "运行时" },
  memory: { color: "text-violet-400", bg: "bg-violet-400/10", border: "border-violet-400/25", label: "记忆" },
  governance: { color: "text-amber-400", bg: "bg-amber-400/10", border: "border-amber-400/25", label: "治理" },
  agent: { color: "text-cyan-400", bg: "bg-cyan-400/10", border: "border-cyan-400/25", label: "智能体" },
  observability: { color: "text-emerald-400", bg: "bg-emerald-400/10", border: "border-emerald-400/25", label: "可观测性" },
};

const SEVERITY_STYLE: Record<EventSeverity, { color: string; dot: string }> = {
  info: { color: "text-os-subtle", dot: "bg-os-muted" },
  warn: { color: "text-amber-400", dot: "bg-amber-400" },
  critical: { color: "text-rose-400", dot: "bg-rose-400" },
};

const CAUSE_LABELS: Record<CauseType, string> = {
  user_action: "用户行为",
  system_policy: "系统策略",
  agent_decision: "智能体决策",
  system_event: "系统事件",
  external_trigger: "外部触发",
};

type TabId = "stream" | "replay" | "causal";

const TABS: { id: TabId; label: string; icon: typeof Radio; hint: string }[] = [
  { id: "stream", label: "Live Stream", icon: Radio, hint: "实时事件流" },
  { id: "replay", label: "Trace Replay", icon: Play, hint: "链路回放" },
  { id: "causal", label: "Causal Chain", icon: GitBranch, hint: "因果链树" },
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
      case "stream": return <LiveStreamTab />;
      case "replay": return <ReplayTab />;
      case "causal": return <CausalChainTab />;
    }
  };

  return (
    <PageTransition>
      <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
        {/* ── Header ── */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight flex items-center gap-2">
              <BrainCircuit size={16} className="text-emerald-400" />
              Zhiwei OS Causal Kernel
            </h1>
            <p className="text-xs text-os-subtle mt-0.5">
              知维 OS 因果内核 — 事件驱动内核层 · 因果关系追踪 · Trace 回放 · 跨模块事件统一
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-2.5 py-1 rounded-md border border-os-border bg-os-surface">
              <div className="relative">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                <div className="absolute inset-0 w-1.5 h-1.5 rounded-full bg-emerald-400 animate-status-breathe" />
              </div>
              <span className="text-2xs text-os-subtle font-mono">
                {stats.storedEvents} events · {stats.traceCount} traces
              </span>
            </div>
            <button
              onClick={() => simulateEventFlow()}
              className="flex items-center gap-1.5 h-7 px-2.5 rounded-md border border-emerald-400/30 bg-emerald-400/10 text-2xs text-emerald-300 hover:bg-emerald-400/20 transition-colors"
            >
              <Zap size={11} />
              模拟事件流
            </button>
          </div>
        </div>

        {/* ── 内核统计磁贴 ── */}
        <div className={layout.grid.five}>
          <StatTile label="运行时" value={stats.bySource.runtime} icon={<ShieldAlert size={12} />} accent="rose" />
          <StatTile label="记忆" value={stats.bySource.memory} icon={<BrainCircuit size={12} />} accent="violet" />
          <StatTile label="治理" value={stats.bySource.governance} icon={<AlertTriangle size={12} />} accent="amber" />
          <StatTile label="智能体" value={stats.bySource.agent} icon={<Cpu size={12} />} accent="cyan" />
          <StatTile label="可观测性" value={stats.bySource.observability} icon={<Activity size={12} />} accent="emerald" />
        </div>

        {/* ── 边界声明 ── */}
        <div className="rounded-md border border-emerald-400/20 bg-emerald-400/[0.03] px-3 py-2">
          <p className="text-2xs leading-5 text-emerald-200/80">
            <span className="font-medium text-emerald-300">因果内核 · </span>
            Event Bus ≠ 日志系统 ≠ 消息队列。每个事件携带 parent_event_id + cause_type 构建因果链，trace_id 支持完整回放。UI 订阅事件流实现事件驱动 UI。
          </p>
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
                <span>{tab.label}</span>
                {isActive && (
                  <motion.div
                    layoutId="causal-tab"
                    className="absolute left-0 right-0 -bottom-px h-0.5 bg-emerald-400"
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

// ═══════════════════════════════════════════════════════════════
// Tab 1: Live Stream — 实时事件流
// ═══════════════════════════════════════════════════════════════

function LiveStreamTab() {
  const [filterSource, setFilterSource] = useState<EventSource | "all">("all");
  const { events, total, clear } = useEventStream(
    useMemo(() => ({
      source: filterSource === "all" ? undefined : filterSource,
    }), [filterSource]),
    100,
  );

  return (
    <div className="space-y-3">
      {/* 过滤器 */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-2xs text-os-muted mr-1">来源:</span>
        <FilterChip active={filterSource === "all"} onClick={() => setFilterSource("all")} label="全部" />
        {(Object.keys(SOURCE_STYLE) as EventSource[]).map((src) => (
          <FilterChip
            key={src}
            active={filterSource === src}
            onClick={() => setFilterSource(src)}
            label={SOURCE_STYLE[src].label}
            color={SOURCE_STYLE[src].color}
          />
        ))}
        <div className="ml-auto flex items-center gap-2">
          <span className="text-2xs text-os-muted font-mono">{total} received</span>
          <button
            onClick={clear}
            className="text-2xs text-os-muted hover:text-os-text px-2 py-0.5 rounded hover:bg-os-elevated transition-colors"
          >
            清空
          </button>
        </div>
      </div>

      {/* 事件流 */}
      <div className="rounded-md border border-os-border bg-os-surface/30 overflow-hidden">
        {events.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-2xs text-os-muted">
            <Radio size={24} className="mb-2 opacity-50" />
            <p>等待事件流入...</p>
            <p className="mt-1">点击右上角"模拟事件流"生成示例事件</p>
          </div>
        ) : (
          <ul className="divide-y divide-os-border/50 max-h-[600px] overflow-y-auto">
            <AnimatePresence initial={false}>
              {events.map((event) => (
                <EventRow key={event.event_id} event={event} />
              ))}
            </AnimatePresence>
          </ul>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Tab 2: Trace Replay — 链路回放
// ═══════════════════════════════════════════════════════════════

function ReplayTab() {
  const traces = useRecentTraces(20);
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);
  const { events, isLoading } = useEventReplay(selectedTrace);

  return (
    <div className={layout.grid.twelve}>
      {/* 左侧：Trace 列表 */}
      <div className="col-span-12 lg:col-span-3 space-y-2">
        <div className="text-2xs font-medium text-os-subtle uppercase tracking-wider flex items-center gap-1.5">
          <Layers size={11} className="text-emerald-400/70" />
          Trace 列表
        </div>
        <div className="rounded-md border border-os-border bg-os-surface/50 max-h-[600px] overflow-y-auto">
          {traces.length === 0 ? (
            <div className="p-4 text-center text-2xs text-os-muted">暂无 trace</div>
          ) : (
            <ul className="divide-y divide-os-border/50">
              {traces.map((tid) => (
                <li key={tid}>
                  <button
                    onClick={() => setSelectedTrace(tid)}
                    className={cn(
                      "w-full text-left px-3 py-2 transition-colors",
                      selectedTrace === tid
                        ? "bg-emerald-400/5 border-l-2 border-emerald-400"
                        : "hover:bg-os-elevated/50 border-l-2 border-transparent",
                    )}
                  >
                    <span className="text-2xs font-mono text-os-subtle truncate block">{tid}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* 右侧：回放事件链 */}
      <div className="col-span-12 lg:col-span-9 space-y-2">
        <div className="text-2xs font-medium text-os-subtle uppercase tracking-wider flex items-center gap-1.5">
          <Play size={11} className="text-emerald-400/70" />
          回放链路
          {selectedTrace && (
            <span className="text-os-muted font-mono ml-2 truncate">{selectedTrace}</span>
          )}
        </div>
        <div className="rounded-md border border-os-border bg-os-surface/30 overflow-hidden">
          {!selectedTrace ? (
            <div className="flex flex-col items-center justify-center py-12 text-2xs text-os-muted">
              <Play size={24} className="mb-2 opacity-50" />
              <p>选择一个 trace 进行回放</p>
            </div>
          ) : isLoading ? (
            <div className="flex items-center justify-center py-12 text-2xs text-os-muted gap-2">
              <RefreshCw size={14} className="animate-spin" /> 加载中...
            </div>
          ) : events.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-2xs text-os-muted">
              <Clock size={24} className="mb-2 opacity-50" />
              <p>该 trace 无事件</p>
            </div>
          ) : (
            <ul className="divide-y divide-os-border/50">
              {events.map((event, idx) => (
                <ReplayEventRow key={event.event_id} event={event} index={idx} />
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Tab 3: Causal Chain — 因果链树
// ═══════════════════════════════════════════════════════════════

function CausalChainTab() {
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const chain = useCausalChain(selectedEventId);

  // 获取所有根事件（无父事件）
  const rootEvents = useMemo(() => {
    return causalKernel
      .getRecentEvents(200)
      .filter((e) => e.causal.parent_event_id === null);
  }, [useKernelStats()]);

  return (
    <div className={layout.grid.twelve}>
      {/* 左侧：根事件列表 */}
      <div className="col-span-12 lg:col-span-4 space-y-2">
        <div className="text-2xs font-medium text-os-subtle uppercase tracking-wider flex items-center gap-1.5">
          <GitBranch size={11} className="text-emerald-400/70" />
          根事件（因果链起点）
        </div>
        <div className="rounded-md border border-os-border bg-os-surface/50 max-h-[600px] overflow-y-auto">
          {rootEvents.length === 0 ? (
            <div className="p-4 text-center text-2xs text-os-muted">暂无根事件</div>
          ) : (
            <ul className="divide-y divide-os-border/50">
              {rootEvents.map((event) => {
                const style = SOURCE_STYLE[event.source];
                const isSelected = selectedEventId === event.event_id;
                return (
                  <li key={event.event_id}>
                    <button
                      onClick={() => setSelectedEventId(event.event_id)}
                      className={cn(
                        "w-full text-left px-3 py-2 transition-colors",
                        isSelected
                          ? "bg-emerald-400/5 border-l-2 border-emerald-400"
                          : "hover:bg-os-elevated/50 border-l-2 border-transparent",
                      )}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className={cn("text-2xs px-1.5 py-0.5 rounded font-mono", style.bg, style.color)}>
                          {style.label}
                        </span>
                        <span className="text-2xs font-mono text-os-muted truncate">{event.type}</span>
                      </div>
                      <div className="text-2xs text-os-muted font-mono truncate">{event.event_id.slice(0, 16)}</div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      {/* 右侧：因果链树 */}
      <div className="col-span-12 lg:col-span-8 space-y-2">
        <div className="text-2xs font-medium text-os-subtle uppercase tracking-wider flex items-center gap-1.5">
          <GitBranch size={11} className="text-emerald-400/70" />
          因果链树
          {selectedEventId && (
            <span className="text-os-muted font-mono ml-2 truncate">{selectedEventId.slice(0, 16)}</span>
          )}
        </div>
        <div className="rounded-md border border-os-border bg-os-surface/30 p-4 min-h-[400px]">
          {!chain ? (
            <div className="flex flex-col items-center justify-center py-12 text-2xs text-os-muted">
              <GitBranch size={24} className="mb-2 opacity-50" />
              <p>选择一个根事件查看因果链</p>
            </div>
          ) : (
            <CausalNode node={chain} />
          )}
        </div>
      </div>
    </div>
  );
}

// ── 因果链节点递归渲染 ──
function CausalNode({ node, isLast = true }: { node: import("@/types/event-bus").CausalChainNode; isLast?: boolean }) {
  const [expanded, setExpanded] = useState(true);
  const event = node.event;
  const style = SOURCE_STYLE[event.source];
  const sevStyle = SEVERITY_STYLE[event.severity];

  return (
    <div className={cn("relative", node.depth > 0 && "ml-4 pl-4 border-l border-os-border/50")}>
      <motion.div
        initial={{ opacity: 0, x: -8 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: node.depth * 0.05 }}
        className="rounded-md border border-os-border bg-os-base/50 p-2.5 mb-2"
      >
        <div className="flex items-center gap-2">
          {node.children.length > 0 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-os-muted hover:text-os-text shrink-0"
            >
              {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </button>
          )}
          <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", sevStyle.dot)} />
          <span className={cn("text-2xs px-1.5 py-0.5 rounded font-mono shrink-0", style.bg, style.color)}>
            {style.label}
          </span>
          <span className="text-2xs font-mono text-os-subtle truncate flex-1">{event.type}</span>
          <span className="text-2xs text-os-muted shrink-0">{formatDate(event.timestamp)}</span>
        </div>
        <div className="mt-1.5 flex items-center gap-2 text-2xs text-os-muted">
          <span className="font-mono">{event.event_id.slice(0, 12)}</span>
          <span>·</span>
          <span className="text-emerald-300/80">{CAUSE_LABELS[event.causal.cause_type]}</span>
          <span>·</span>
          <span className={sevStyle.color}>{event.severity}</span>
        </div>
        <div className="mt-1 text-2xs text-os-subtle font-mono">
          payload: {Object.keys(event.payload).join(", ")}
        </div>
      </motion.div>

      {expanded && node.children.length > 0 && (
        <div className="space-y-1">
          {node.children.map((child, idx) => (
            <CausalNode key={child.event.event_id} node={child} isLast={idx === node.children.length - 1} />
          ))}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// 事件行组件
// ═══════════════════════════════════════════════════════════════

function EventRow({ event }: { event: SystemEvent }) {
  const style = SOURCE_STYLE[event.source];
  const sevStyle = SEVERITY_STYLE[event.severity];

  return (
    <motion.li
      layout
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0 }}
      className="px-3 py-2 hover:bg-os-elevated/30 transition-colors"
    >
      <div className="flex items-center gap-2">
        <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", sevStyle.dot)} />
        <span className={cn("text-2xs px-1.5 py-0.5 rounded font-mono shrink-0", style.bg, style.color)}>
          {style.label}
        </span>
        <span className="text-2xs font-mono text-os-subtle truncate flex-1">{event.type}</span>
        {event.causal.parent_event_id && (
          <span className="text-2xs text-emerald-300/60 shrink-0 flex items-center gap-0.5">
            <ChevronRight size={9} />
            child
          </span>
        )}
        <span className="text-2xs text-os-muted shrink-0">{formatDate(event.timestamp)}</span>
      </div>
      <div className="mt-1 flex items-center gap-2 text-2xs text-os-muted">
        <span className="font-mono">{event.event_id.slice(0, 12)}</span>
        <span>·</span>
        <span className="font-mono text-os-subtle/70 truncate">{event.trace_id.slice(0, 20)}</span>
        <span>·</span>
        <span className={sevStyle.color}>{event.severity}</span>
        <span>·</span>
        <span className="text-emerald-300/70">{CAUSE_LABELS[event.causal.cause_type]}</span>
      </div>
    </motion.li>
  );
}

function ReplayEventRow({ event, index }: { event: SystemEvent; index: number }) {
  const style = SOURCE_STYLE[event.source];
  const sevStyle = SEVERITY_STYLE[event.severity];

  return (
    <motion.li
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03 }}
      className="px-3 py-2.5"
    >
      <div className="flex items-center gap-2">
        <span className="text-2xs font-mono text-os-muted shrink-0 w-6">#{index + 1}</span>
        <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", sevStyle.dot)} />
        <span className={cn("text-2xs px-1.5 py-0.5 rounded font-mono shrink-0", style.bg, style.color)}>
          {style.label}
        </span>
        <span className="text-xs font-mono text-os-text-high truncate flex-1">{event.type}</span>
        <span className="text-2xs text-os-muted shrink-0">{formatDate(event.timestamp)}</span>
      </div>
      <div className="mt-1.5 ml-12 flex items-center gap-2 text-2xs text-os-muted">
        <span className="font-mono">{event.event_id.slice(0, 12)}</span>
        <span>·</span>
        <span className={sevStyle.color}>{event.severity}</span>
        {event.causal.parent_event_id ? (
          <>
            <span>·</span>
            <span className="text-emerald-300/70">← {event.causal.parent_event_id.slice(0, 12)}</span>
          </>
        ) : (
          <>
            <span>·</span>
            <span className="text-emerald-300 font-medium">ROOT</span>
          </>
        )}
      </div>
      <div className="mt-1 ml-12 text-2xs text-os-subtle font-mono">
        payload: {JSON.stringify(event.payload).slice(0, 120)}
        {JSON.stringify(event.payload).length > 120 && "..."}
      </div>
    </motion.li>
  );
}

// ═══════════════════════════════════════════════════════════════
// 子组件
// ═══════════════════════════════════════════════════════════════

function StatTile({
  label, value, icon, accent,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  accent: "rose" | "violet" | "amber" | "cyan" | "emerald";
}) {
  const accentMap = {
    rose: "text-rose-400",
    violet: "text-violet-400",
    amber: "text-amber-400",
    cyan: "text-cyan-400",
    emerald: "text-emerald-400",
  };
  return (
    <div className="rounded-md border border-os-border bg-os-surface/30 p-2.5">
      <div className="flex items-center gap-1 text-2xs text-os-muted mb-1">
        <span className={accentMap[accent]}>{icon}</span>
        {label}
      </div>
      <div className={cn("text-lg font-bold tabular-nums", accentMap[accent])}>{value}</div>
    </div>
  );
}

function FilterChip({
  active, onClick, label, color,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  color?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "px-2 py-0.5 rounded text-2xs transition-colors",
        active
          ? "bg-emerald-400/10 text-emerald-300 border border-emerald-400/30"
          : "bg-os-elevated text-os-muted border border-os-border hover:text-os-subtle",
        color && !active && color,
      )}
    >
      {label}
    </button>
  );
}

// ═══════════════════════════════════════════════════════════════
// 模拟事件流 — 演示完整因果链路
// ═══════════════════════════════════════════════════════════════

/**
 * 模拟系统事件流，演示因果链路：
 * User Action → Runtime Event → Governance Decision → Memory Update → Observability Trace
 */
function simulateEventFlow() {
  const trace_id = newTraceId("trace");

  // 1. 根事件：用户行为触发（observability.trace.started）
  const traceStart = createRootEvent(
    "observability",
    "observability.trace.started",
    "info",
    trace_id,
    { trace_id, trigger: "user_action", context: { source: "causal_kernel_ui" } },
    "user_action",
  );

  // 2. Agent 决策（agent.decision.made）— 子事件
  const agentDecision = createChildEvent(
    traceStart,
    "agent",
    "agent.decision.made",
    "info",
    {
      agent_id: "agent-001",
      decision: "execute_tool",
      reasoning: "用户请求执行文件下载",
      confidence: 0.85,
      alternatives_considered: ["ask_confirmation", "deny"],
    },
    "agent_decision",
  );

  // 3. Governance 策略评估（governance.policy.evaluated）— 子事件
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

  // 4. Runtime Gate 拒绝（runtime.gate.denied）— 子事件
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

  // 5. Governance 审计记录（governance.audit.record_generated）— 子事件
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

  // 6. Memory 写入（memory.write.ltm）— 子事件，记录此次决策
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

  // 7. Observability trace 完成（observability.trace.completed）— 子事件
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
