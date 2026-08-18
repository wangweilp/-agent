"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  ChevronRight,
  CircleDot,
  Crosshair,
  Flame,
  GitGraph,
  Layers,
  Play,
  RefreshCw,
  Target,
  Zap,
} from "lucide-react";
import { PageTransition } from "@/components/animations/page-transition";
import {
  EmptyState,
  InfoBanner,
  OsBadge,
  OsButton,
  OsCard,
  PageHeader,
  PageShell,
  ProgressBar,
  RankRow,
  SectionHeader,
  StatusBadge,
  Toolbar,
} from "@/components/ui/os";
import { formatDate } from "@/lib/utils";
import {
  causalKernel,
  createChildEvent,
  createMultiCausalEvent,
  createRootEvent,
  newTraceId,
} from "@/lib/event-bus/causal-kernel";
import { useCausalGraph, useTopImpactNodes } from "@/hooks/use-causal-graph";
import { useRecentTraces } from "@/hooks/use-event-stream";
import type {
  CausalGraphEdge,
  CausalGraphNode,
  CausalRelation,
  EventSeverity,
  EventSource,
  SystemEvent,
} from "@/types/event-bus";

type BadgeTone = "default" | "primary" | "success" | "warning" | "danger" | "info" | "muted";

const SOURCE_CONFIG: Record<
  EventSource,
  { color: string; fill: string; border: string; label: string; layer: number; badge: BadgeTone }
> = {
  runtime: {
    color: "#D65F5F",
    fill: "rgba(214,95,95,0.12)",
    border: "#D65F5F",
    label: "运行时",
    layer: 0,
    badge: "danger",
  },
  governance: {
    color: "#C88A2D",
    fill: "rgba(200,138,45,0.13)",
    border: "#C88A2D",
    label: "治理",
    layer: 1,
    badge: "warning",
  },
  agent: {
    color: "#3B9F72",
    fill: "rgba(59,159,114,0.13)",
    border: "#3B9F72",
    label: "智能体",
    layer: 2,
    badge: "success",
  },
  memory: {
    color: "#6678D9",
    fill: "rgba(102,120,217,0.13)",
    border: "#6678D9",
    label: "记忆",
    layer: 3,
    badge: "primary",
  },
  observability: {
    color: "#64748B",
    fill: "rgba(100,116,139,0.10)",
    border: "#64748B",
    label: "可观测性",
    layer: 4,
    badge: "muted",
  },
};

const SOURCE_ORDER: EventSource[] = ["runtime", "governance", "agent", "memory", "observability"];

const RELATION_LABEL: Record<CausalRelation, string> = {
  caused_by: "导致",
  influenced_by: "影响",
  blocked_by: "阻断",
  triggered_by: "触发",
};

const SEVERITY_CONFIG: Record<EventSeverity, { label: string; dot: string; badge: BadgeTone }> = {
  info: { label: "信息", dot: "bg-os-muted", badge: "muted" },
  warn: { label: "警告", dot: "bg-os-warning", badge: "warning" },
  critical: { label: "严重", dot: "bg-os-danger", badge: "danger" },
};

interface PositionedNode extends CausalGraphNode {
  x: number;
  y: number;
}

type TraceRuntimeState = "hydrating" | "ready" | "empty" | "invalid";

const LAYER_HEIGHT = 128;
const NODE_RADIUS = 23;
const PADDING_X = 72;
const PADDING_Y = 58;
const MIN_CANVAS_WIDTH = 760;

function layoutGraph(nodes: CausalGraphNode[], width: number): { positioned: PositionedNode[]; layerYs: number[] } {
  if (nodes.length === 0) return { positioned: [], layerYs: [] };

  const bySource = new Map<EventSource, CausalGraphNode[]>();
  for (const node of nodes) {
    const list = bySource.get(node.source) || [];
    list.push(node);
    bySource.set(node.source, list);
  }

  for (const list of bySource.values()) {
    list.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  }

  const activeLayers = SOURCE_ORDER.filter((source) => (bySource.get(source)?.length || 0) > 0);
  const layerYs = activeLayers.map((_, index) => PADDING_Y + index * LAYER_HEIGHT);
  const usableWidth = Math.max(width, MIN_CANVAS_WIDTH) - PADDING_X * 2;

  const positioned: PositionedNode[] = [];
  activeLayers.forEach((source, layerIndex) => {
    const list = bySource.get(source) || [];
    const y = layerYs[layerIndex];
    const stepX = list.length > 1 ? usableWidth / (list.length - 1) : 0;
    list.forEach((node, index) => {
      positioned.push({
        ...node,
        x: list.length === 1 ? PADDING_X + usableWidth / 2 : PADDING_X + index * stepX,
        y,
      });
    });
  });

  return { positioned, layerYs };
}

function eventShortType(type: string) {
  return type.split(".").slice(-2).join(".");
}

export default function CausalGraphPage() {
  const traces = useRecentTraces(30);
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [showCriticalOnly, setShowCriticalOnly] = useState(false);
  const [isSeeding, setIsSeeding] = useState(false);
  const canvasRef = useRef<HTMLDivElement>(null);
  const autoSeededRef = useRef(false);
  const [canvasWidth, setCanvasWidth] = useState(920);

  useEffect(() => {
    if (!selectedTrace && traces.length > 0) {
      setSelectedTrace(traces[0]);
    }
  }, [traces, selectedTrace]);

  useEffect(() => {
    if (autoSeededRef.current) return;
    if (traces.length === 0) {
      autoSeededRef.current = true;
      setIsSeeding(true);
      const traceId = simulateMultiCausalFlow();
      setSelectedTrace(traceId);
      setSelectedNodeId(null);
      setIsSeeding(false);
    }
  }, [traces]);

  useEffect(() => {
    if (selectedTrace && traces.length > 0 && !traces.includes(selectedTrace)) {
      setSelectedTrace(null);
      setSelectedNodeId(null);
    }
  }, [traces, selectedTrace]);

  useEffect(() => {
    const update = () => {
      if (canvasRef.current) setCanvasWidth(canvasRef.current.clientWidth);
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  const handleSimulate = () => {
    setIsSeeding(true);
    const traceId = simulateMultiCausalFlow();
    setSelectedTrace(traceId);
    setSelectedNodeId(null);
    setIsSeeding(false);
  };

  const graph = useCausalGraph(selectedTrace);
  const topImpact = useTopImpactNodes(selectedTrace, 5);

  const traceState: TraceRuntimeState = useMemo(() => {
    if (isSeeding) return "hydrating";
    if (!selectedTrace) return "empty";
    if (traces.length > 0 && !traces.includes(selectedTrace)) return "invalid";
    if (!graph.hydrated) return "hydrating";
    if (graph.nodes.length === 0) return "empty";
    return "ready";
  }, [isSeeding, selectedTrace, traces, graph.hydrated, graph.nodes.length]);

  const canRenderGraph = traceState === "ready";

  const { positioned, layerYs } = useMemo(
    () => layoutGraph(graph.nodes, canvasWidth),
    [graph.nodes, canvasWidth],
  );

  const nodeMap = useMemo(() => {
    const map = new Map<string, PositionedNode>();
    for (const node of positioned) map.set(node.event_id, node);
    return map;
  }, [positioned]);

  const selectedNode = selectedNodeId ? nodeMap.get(selectedNodeId) ?? null : null;
  const selectedEvent = selectedNodeId ? causalKernel.getEvent(selectedNodeId) : null;

  const selectedCausalChain = selectedNodeId
    ? {
        parents: causalKernel.getParents(selectedNodeId),
        childEvents: causalKernel.getChildren(selectedNodeId),
      }
    : { parents: [] as SystemEvent[], childEvents: [] as SystemEvent[] };

  const visibleEdges = useMemo(() => {
    if (!showCriticalOnly) return graph.edges;
    return graph.edges.filter((edge) => edge.is_critical_path);
  }, [graph.edges, showCriticalOnly]);

  const visibleNodeIds = useMemo(() => {
    if (!showCriticalOnly) return new Set(positioned.map((node) => node.event_id));
    const ids = new Set<string>();
    for (const edge of visibleEdges) {
      ids.add(edge.from);
      ids.add(edge.to);
    }
    if (selectedNodeId) ids.add(selectedNodeId);
    return ids;
  }, [positioned, visibleEdges, selectedNodeId, showCriticalOnly]);

  const canvasHeight = Math.max(520, layerYs.length > 0 ? layerYs[layerYs.length - 1] + PADDING_Y + 52 : 520);

  return (
    <PageTransition>
      <PageShell>
        <PageHeader
          icon={GitGraph}
          title="因果图引擎"
          subtitle="把事件流投影为可解释的因果 DAG，追踪运行时、治理、智能体、记忆与可观测性之间的影响路径。"
          actions={
            <>
              <StatusBadge status={canRenderGraph ? "ready" : traceState === "invalid" ? "warning" : "info"}>
                {canRenderGraph ? "图谱就绪" : traceState === "invalid" ? "追踪记录已失效" : "准备中"}
              </StatusBadge>
              <OsButton type="button" variant="primary" size="md" onClick={handleSimulate}>
                <Zap size={15} />
                模拟因果图
              </OsButton>
            </>
          }
        />

        <Toolbar>
          <div className="flex items-center gap-2">
            <Crosshair size={15} className="text-os-subtle" />
            <span className="text-xs font-semibold tracking-[0.08em] text-os-subtle">追踪记录</span>
          </div>
          <select
            value={selectedTrace || ""}
            onChange={(e) => {
              setSelectedTrace(e.target.value || null);
              setSelectedNodeId(null);
            }}
            aria-label="选择追踪记录"
            className="h-9 min-w-0 rounded-xl border border-os-border bg-white px-3 font-mono text-xs text-os-text-high outline-none focus:border-os-primary/35 focus:ring-2 focus:ring-os-primary/15 sm:min-w-[260px]"
          >
            <option value="">{traces.length === 0 ? "暂无追踪记录" : "选择追踪记录"}</option>
            {traces.map((traceId) => (
              <option key={traceId} value={traceId}>
                {traceId.slice(0, 32)}
              </option>
            ))}
          </select>

          {graph.stats && (
            <div className="flex flex-wrap items-center gap-2">
              <OsBadge variant="muted">节点 {graph.stats.node_count}</OsBadge>
              <OsBadge variant="muted">边 {graph.stats.edge_count}</OsBadge>
              <OsBadge variant="muted">根节点 {graph.stats.root_count}</OsBadge>
              <OsBadge variant="muted">叶节点 {graph.stats.leaf_count}</OsBadge>
              <OsBadge variant={graph.criticalPath ? "danger" : "muted"}>
                关键路径 {graph.criticalPath?.nodes.length || 0}
              </OsBadge>
            </div>
          )}

          <OsButton
            type="button"
            variant={showCriticalOnly ? "dangerSoft" : "secondary"}
            size="md"
            onClick={() => setShowCriticalOnly((value) => !value)}
            className="ml-auto"
          >
            <Flame size={14} />
            {showCriticalOnly ? "仅关键路径" : "全部边"}
          </OsButton>
          <OsButton type="button" variant="ghost" size="md" onClick={graph.rebuild}>
            <RefreshCw size={14} />
            重建
          </OsButton>
        </Toolbar>

        <InfoBanner variant="info" icon={Layers}>
          关键路径只强调风险传播链，不改变底层事件存储。选择节点后右侧检查器会展示事件载荷、父事件、子事件与影响分。
        </InfoBanner>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
          <OsCard padding="none" className="min-h-[560px] overflow-hidden">
            <div className="border-b border-os-border bg-white px-4 py-3">
              <SectionHeader
                icon={GitGraph}
                title="因果画布"
                subtitle="按事件来源分层，边的粗细表示因果权重，虚线表示影响关系。"
                actions={graph.isBuilding ? <StatusBadge status="info">构建中</StatusBadge> : undefined}
              />
            </div>
            <div ref={canvasRef} className="relative min-h-[520px] overflow-hidden bg-white">
              {!canRenderGraph ? (
                <GraphEmptyState state={traceState} hasTrace={!!selectedTrace} onGenerate={handleSimulate} />
              ) : (
                <GraphCanvas
                  width={Math.max(canvasWidth, MIN_CANVAS_WIDTH)}
                  positioned={positioned}
                  layerYs={layerYs}
                  edges={visibleEdges}
                  nodeMap={nodeMap}
                  visibleNodeIds={visibleNodeIds}
                  selectedNodeId={selectedNodeId}
                  onSelectNode={setSelectedNodeId}
                  canvasHeight={canvasHeight}
                  showCriticalOnly={showCriticalOnly}
                />
              )}
            </div>
          </OsCard>

          <OsCard padding="none" className="min-h-[560px] overflow-hidden">
            <SidePanel
              node={selectedNode}
              event={selectedEvent}
              parents={selectedCausalChain.parents}
              childEvents={selectedCausalChain.childEvents}
              topImpact={topImpact}
              onSelectNode={setSelectedNodeId}
            />
          </OsCard>
        </div>
      </PageShell>
    </PageTransition>
  );
}

interface GraphCanvasProps {
  width: number;
  positioned: PositionedNode[];
  layerYs: number[];
  edges: CausalGraphEdge[];
  nodeMap: Map<string, PositionedNode>;
  visibleNodeIds: Set<string>;
  selectedNodeId: string | null;
  onSelectNode: (id: string) => void;
  canvasHeight: number;
  showCriticalOnly: boolean;
}

function GraphCanvas({
  width,
  positioned,
  layerYs,
  edges,
  nodeMap,
  visibleNodeIds,
  selectedNodeId,
  onSelectNode,
  canvasHeight,
  showCriticalOnly,
}: GraphCanvasProps) {
  const activeLayers = SOURCE_ORDER.filter((source) => positioned.some((node) => node.source === source));

  return (
    <svg
      width="100%"
      height={canvasHeight}
      viewBox={`0 0 ${width} ${canvasHeight}`}
      className="block"
      role="img"
      aria-label="因果事件图谱"
      style={{
        background:
          "radial-gradient(circle at 50% 0%, rgba(102,120,217,0.08), transparent 46%), linear-gradient(#FFFFFF, #F8FAFC)",
      }}
    >
      <defs>
        <pattern id="causal-grid" width="48" height="48" patternUnits="userSpaceOnUse">
          <path d="M 48 0 L 0 0 0 48" fill="none" stroke="rgba(100,116,139,0.08)" strokeWidth="1" />
        </pattern>
        <marker id="arrow-muted" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="rgba(100,116,139,0.45)" />
        </marker>
        <marker id="arrow-critical" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#D65F5F" />
        </marker>
      </defs>

      <rect x="0" y="0" width={width} height={canvasHeight} fill="url(#causal-grid)" />

      {activeLayers.map((source, index) => {
        const cfg = SOURCE_CONFIG[source];
        const y = layerYs[index];
        return (
          <g key={source}>
            <line x1={0} y1={y} x2={width} y2={y} stroke={cfg.color} strokeOpacity={0.13} strokeDasharray="5 5" />
            <text x={18} y={y - 12} fill={cfg.color} fillOpacity={0.72} fontSize={11} fontWeight={600}>
              {cfg.label}
            </text>
          </g>
        );
      })}

      <g>
        {edges.map((edge, index) => {
          const from = nodeMap.get(edge.from);
          const to = nodeMap.get(edge.to);
          if (!from || !to) return null;
          if (showCriticalOnly && !edge.is_critical_path) return null;

          const isCritical = !!edge.is_critical_path;
          const strokeColor = isCritical ? SOURCE_CONFIG.runtime.color : "rgba(100,116,139,0.42)";
          const strokeWidth = Math.max(1, edge.weight * (isCritical ? 2.1 : 1.45));
          const midY = (from.y + to.y) / 2;
          const path = `M ${from.x} ${from.y} C ${from.x} ${midY}, ${to.x} ${midY}, ${to.x} ${to.y}`;

          return (
            <g key={`${edge.from}-${edge.to}-${index}`}>
              {isCritical && <path d={path} fill="none" stroke={strokeColor} strokeOpacity={0.12} strokeWidth={strokeWidth + 8} />}
              <path
                d={path}
                fill="none"
                stroke={strokeColor}
                strokeOpacity={isCritical ? 0.78 : 0.36}
                strokeWidth={strokeWidth}
                strokeDasharray={edge.relation === "influenced_by" ? "5 4" : undefined}
                markerEnd={isCritical ? "url(#arrow-critical)" : "url(#arrow-muted)"}
              />
            </g>
          );
        })}
      </g>

      <g>
        {positioned.map((node) => {
          const cfg = SOURCE_CONFIG[node.source];
          const isSelected = selectedNodeId === node.event_id;
          const isVisible = visibleNodeIds.has(node.event_id);
          if (showCriticalOnly && !isVisible) return null;

          const impact = node.impact_score || 0;
          const radius = NODE_RADIUS + Math.min(impact, 12) * 0.45;
          const isHighImpact = impact > 5;

          return (
            <g
              key={node.event_id}
              transform={`translate(${node.x}, ${node.y})`}
              className="cursor-pointer outline-none"
              role="button"
              tabIndex={0}
              aria-label={`${cfg.label} ${eventShortType(node.type)}`}
              onClick={() => onSelectNode(node.event_id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") onSelectNode(node.event_id);
              }}
            >
              <title>{`${cfg.label} | ${node.type} | ${node.severity}`}</title>
              {isHighImpact && <circle r={radius + 9} fill={cfg.color} fillOpacity={0.08} />}
              {isSelected && <circle r={radius + 6} fill="none" stroke={cfg.color} strokeOpacity={0.55} strokeWidth={2} />}
              <circle r={radius} fill={cfg.fill} stroke={cfg.border} strokeWidth={isSelected ? 2.2 : 1.2} />
              <circle cx={radius * 0.58} cy={-radius * 0.58} r={3.6} className={SEVERITY_CONFIG[node.severity].dot} fill="currentColor" />
              {impact > 0 && (
                <text y={4} textAnchor="middle" fill={cfg.color} fontSize={11} fontWeight={700} className="pointer-events-none">
                  {Math.round(impact)}
                </text>
              )}
              <text y={radius + 17} textAnchor="middle" fill="#334155" fontSize={10} fontWeight={600} className="pointer-events-none">
                {eventShortType(node.type)}
              </text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}

interface SidePanelProps {
  node: PositionedNode | null;
  event: SystemEvent | null;
  parents: SystemEvent[];
  childEvents: SystemEvent[];
  topImpact: CausalGraphNode[];
  onSelectNode: (id: string) => void;
}

function SidePanel({ node, event, parents, childEvents, topImpact, onSelectNode }: SidePanelProps) {
  if (!node || !event) {
    return (
      <div className="flex h-full min-h-[560px] flex-col">
        <PanelHeader title="事件检查器" icon={CircleDot} />
        <div className="flex flex-1 items-center justify-center p-5">
          <EmptyState
            icon={Crosshair}
            title="选择节点查看详情"
            description="点击画布中的任意事件节点，查看事件载荷、因果父子关系与影响分。"
            className="min-h-[240px]"
          />
        </div>
        <TopImpactList nodes={topImpact} onSelectNode={onSelectNode} />
      </div>
    );
  }

  const cfg = SOURCE_CONFIG[node.source];
  const impact = Math.min(100, Math.round((node.impact_score || 0) * 5));

  return (
    <div className="flex h-full min-h-[560px] flex-col">
      <PanelHeader title="事件检查器" icon={CircleDot} hint="点击节点切换" />
      <div className="flex-1 overflow-y-auto">
        <div className="space-y-4 p-4">
          <OsCard padding="md" variant="inspector">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <OsBadge variant={cfg.badge}>{cfg.label}</OsBadge>
                  <OsBadge variant={SEVERITY_CONFIG[node.severity].badge}>{SEVERITY_CONFIG[node.severity].label}</OsBadge>
                </div>
                <h2 className="mt-3 break-all font-mono text-sm font-semibold leading-6 text-os-text-high">{node.type}</h2>
              </div>
            </div>
            <div className="mt-3 rounded-xl border border-os-border bg-os-surface-tinted p-3">
              <p className="break-all font-mono text-xs leading-5 text-os-subtle">{node.event_id}</p>
              <p className="mt-2 text-xs text-os-subtle">{formatDate(node.timestamp)}</p>
            </div>
          </OsCard>

          <OsCard padding="md">
            <div className="mb-2 flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.08em] text-os-subtle">
                <Target size={13} />
                影响评分
              </span>
              <span className="font-mono text-lg font-semibold" style={{ color: cfg.color }}>
                {Math.round(node.impact_score || 0)}
              </span>
            </div>
            <ProgressBar value={impact} tone={node.severity === "critical" ? "danger" : node.severity === "warn" ? "warning" : "primary"} />
            <div className="mt-2 flex items-center justify-between text-xs text-os-subtle">
              <span>下游 {node.downstream_count || 0} 节点</span>
              <span>{cfg.label} 层</span>
            </div>
          </OsCard>

          <OsCard padding="md">
            <h3 className="mb-2 text-sm font-semibold text-os-text-high">事件载荷</h3>
            <pre className="max-h-44 overflow-auto rounded-xl border border-os-border bg-os-surface-tinted p-3 font-mono text-xs leading-5 text-os-text">
{JSON.stringify(event.payload, null, 2)}
            </pre>
          </OsCard>

          <CausalList
            title={`父事件 (${parents.length})`}
            iconDirection="up"
            events={parents}
            empty="根事件，没有父节点"
            relation="caused_by"
            onSelectNode={onSelectNode}
          />

          <CausalList
            title={`子事件 (${childEvents.length})`}
            iconDirection="down"
            events={childEvents}
            empty="叶节点，没有子事件"
            onSelectNode={onSelectNode}
          />
        </div>

        <TopImpactList nodes={topImpact} onSelectNode={onSelectNode} />
      </div>
    </div>
  );
}

function PanelHeader({
  title,
  icon: Icon,
  hint,
}: {
  title: string;
  icon: typeof CircleDot;
  hint?: string;
}) {
  return (
    <div className="flex h-12 shrink-0 items-center justify-between border-b border-os-border bg-white px-4">
      <div className="flex items-center gap-2">
        <Icon size={15} className="text-os-primary" />
        <span className="text-sm font-semibold text-os-text-high">{title}</span>
      </div>
      {hint && <span className="text-xs text-os-subtle">{hint}</span>}
    </div>
  );
}

function CausalList({
  title,
  iconDirection,
  events,
  empty,
  relation,
  onSelectNode,
}: {
  title: string;
  iconDirection: "up" | "down";
  events: SystemEvent[];
  empty: string;
  relation?: CausalRelation;
  onSelectNode: (id: string) => void;
}) {
  return (
    <OsCard padding="md">
      <h3 className="mb-2 inline-flex items-center gap-1.5 text-sm font-semibold text-os-text-high">
        <ArrowRight size={14} className={iconDirection === "up" ? "rotate-180" : undefined} />
        {title}
      </h3>
      {events.length === 0 ? (
        <p className="rounded-xl border border-dashed border-os-border bg-os-surface-tinted p-3 text-sm text-os-subtle">{empty}</p>
      ) : (
        <div className="space-y-1.5">
          {events.map((item) => (
            <CausalChainItem
              key={item.event_id}
              event={item}
              relation={relation}
              onClick={() => onSelectNode(item.event_id)}
            />
          ))}
        </div>
      )}
    </OsCard>
  );
}

function CausalChainItem({
  event,
  relation,
  onClick,
}: {
  event: SystemEvent;
  relation?: CausalRelation;
  onClick: () => void;
}) {
  const cfg = SOURCE_CONFIG[event.source];
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left transition-colors hover:bg-os-surface-hover"
    >
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: cfg.color }} />
      <span className="min-w-0 flex-1 truncate font-mono text-xs text-os-text-high">{eventShortType(event.type)}</span>
      {relation && <span className="shrink-0 text-xs text-os-subtle">{RELATION_LABEL[relation]}</span>}
      <ChevronRight size={13} className="shrink-0 text-os-muted group-hover:text-os-primary" />
    </button>
  );
}

function TopImpactList({ nodes, onSelectNode }: { nodes: CausalGraphNode[]; onSelectNode: (id: string) => void }) {
  if (nodes.length === 0) return null;
  const maxImpact = Math.max(...nodes.map((node) => node.impact_score || 0), 1);
  return (
    <div className="border-t border-os-border p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="inline-flex items-center gap-1.5 text-sm font-semibold text-os-text-high">
          <Flame size={14} className="text-os-danger" />
          高影响节点
        </h3>
        <OsBadge variant="muted">前 {nodes.length} 项</OsBadge>
      </div>
      <div className="space-y-1">
        {nodes.map((node, index) => {
          const impact = node.impact_score || 0;
          return (
            <RankRow
              key={node.event_id}
              rank={index + 1}
              label={eventShortType(node.type)}
              value={Math.round(impact)}
              percent={Math.round((impact / maxImpact) * 100)}
              onClick={() => onSelectNode(node.event_id)}
            />
          );
        })}
      </div>
    </div>
  );
}

function GraphEmptyState({
  state,
  hasTrace,
  onGenerate,
}: {
  state: TraceRuntimeState;
  hasTrace: boolean;
  onGenerate: () => void;
}) {
  if (state === "hydrating") {
    return (
      <div className="flex min-h-[520px] items-center justify-center p-6">
        <EmptyState
          icon={RefreshCw}
          title="正在生成默认追踪记录"
          description="因果内核正在生成示例因果链，完成后会自动挂载图谱。"
          action={
            <RefreshCw size={18} className="mx-auto animate-spin text-os-primary" />
          }
        />
      </div>
    );
  }

  if (state === "invalid") {
    return (
      <div className="flex min-h-[520px] items-center justify-center p-6">
        <EmptyState
          icon={AlertTriangle}
          title="追踪记录已失效"
          description="所选追踪记录已从内核中移除，可以生成新的演示数据继续查看因果图。"
          action={
            <OsButton type="button" variant="primary" size="md" onClick={onGenerate}>
              <Zap size={14} />
              生成新追踪记录
            </OsButton>
          }
        />
      </div>
    );
  }

  return (
    <div className="flex min-h-[520px] items-center justify-center p-6">
      <EmptyState
        icon={GitGraph}
        title={hasTrace ? "该追踪记录暂无事件" : "暂无追踪记录"}
        description={
          hasTrace
            ? "该追踪记录已水合但不包含可渲染事件，请切换追踪记录或生成新的因果图。"
            : "还没有生成任何追踪记录，点击下方按钮创建第一条因果链。"
        }
        action={
          <OsButton type="button" variant="primary" size="md" onClick={onGenerate}>
            <Play size={14} />
            {hasTrace ? "模拟因果图" : "生成第一条追踪记录"}
          </OsButton>
        }
      />
    </div>
  );
}

function simulateMultiCausalFlow() {
  const trace_id = newTraceId("graph");

  const killTriggered = createRootEvent(
    "runtime",
    "runtime.kill_switch.triggered",
    "critical",
    trace_id,
    {
      target_type: "execution-plan",
      target_id: "plan-001",
      reason: "policy_violation_detected",
      force: false,
      requested_by: "governance-engine",
    },
    "system_policy",
  );

  const agentDecision = createRootEvent(
    "agent",
    "agent.decision.made",
    "warn",
    trace_id,
    {
      agent_id: "agent-002",
      decision: "evaluate_risk",
      reasoning: "检测到策略违规，开始评估风险等级。",
      confidence: 0.78,
      alternatives_considered: ["block", "warn", "allow"],
    },
    "agent_decision",
  );

  const policyEval = createChildEvent(
    agentDecision,
    "governance",
    "governance.policy.evaluated",
    "warn",
    {
      policy_id: "risk-gate-v2",
      policy_name: "Risk Assessment Gate",
      decision: "denied",
      evaluated_rules: ["severity_check", "blast_radius"],
      violations: ["high_blast_radius"],
      warnings: [],
    },
    "system_policy",
  );

  const gateDenied = createMultiCausalEvent(
    [
      { event: killTriggered, relation: "triggered_by", weight: 0.9 },
      { event: policyEval, relation: "caused_by", weight: 1.0 },
    ],
    policyEval,
    "runtime",
    "runtime.gate.denied",
    "critical",
    {
      gate_type: "artifact",
      target_id: "plan-001",
      violated_rules: ["high_blast_radius"],
      requested_resource: "execution-plan/plan-001",
    },
    "system_policy",
  );

  const auditRecord = createChildEvent(
    gateDenied,
    "governance",
    "governance.audit.record_generated",
    "info",
    {
      audit_id: "audit-002",
      action: "gate_denied",
      resource_type: "execution_plan",
      resource_id: "plan-001",
      actor: "governance-engine",
    },
    "system_event",
  );

  const memoryWrite = createMultiCausalEvent(
    [
      { event: gateDenied, relation: "caused_by", weight: 1.0 },
      { event: auditRecord, relation: "influenced_by", weight: 0.6 },
    ],
    gateDenied,
    "memory",
    "memory.write.ltm",
    "info",
    {
      memory_id: "mem-002",
      tier: "ltm",
      memory_type: "episodic",
      content_preview: "Execution plan blocked by risk gate: high blast radius",
      importance: 8,
      source: "agent",
      entities: ["risk-gate", "plan-001", "blast_radius"],
    },
    "system_event",
  );

  createChildEvent(
    memoryWrite,
    "memory",
    "memory.reflection.triggered",
    "info",
    {
      trigger_reason: "high_importance_memory",
      scan_scope: ["risk-gate", "blast_radius"],
    },
    "system_event",
  );

  createChildEvent(
    killTriggered,
    "observability",
    "observability.trace.completed",
    "info",
    {
      trace_id,
      event_count: 8,
      duration_ms: 156,
      status: "success",
    },
    "system_event",
  );

  return trace_id;
}
