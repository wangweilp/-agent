"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  GitGraph, Zap, Play, ChevronRight, X, Activity,
  Crosshair, Layers, AlertTriangle, CircleDot, ArrowRight,
  RefreshCw, Target, Flame,
} from "lucide-react";
import { PageTransition } from "@/components/animations/page-transition";
import { cn, formatDate } from "@/lib/utils";
import {
  causalKernel,
  createRootEvent, createChildEvent, createMultiCausalEvent, newTraceId,
} from "@/lib/event-bus/causal-kernel";
import { useCausalGraph, useTopImpactNodes } from "@/hooks/use-causal-graph";
import { useRecentTraces } from "@/hooks/use-event-stream";
import type {
  CausalGraphNode, CausalGraphEdge, EventSource, EventSeverity,
  CausalRelation, SystemEvent,
} from "@/types/event-bus";

// ═══════════════════════════════════════════════════════════════
// 来源样式映射 — 按用户规范着色
// 🟥 Runtime / 🟦 Memory / 🟨 Governance / 🟩 Agent / ⬜ Observability
// ═══════════════════════════════════════════════════════════════

const SOURCE_CONFIG: Record<EventSource, {
  color: string; fill: string; stroke: string; label: string; layer: number;
}> = {
  runtime: { color: "#f43f5e", fill: "rgba(244,63,94,0.15)", stroke: "#f43f5e", label: "运行时", layer: 0 },
  governance: { color: "#f59e0b", fill: "rgba(245,158,11,0.15)", stroke: "#f59e0b", label: "治理", layer: 1 },
  agent: { color: "#22c55e", fill: "rgba(34,197,94,0.15)", stroke: "#22c55e", label: "智能体", layer: 2 },
  memory: { color: "#3b82f6", fill: "rgba(59,130,246,0.15)", stroke: "#3b82f6", label: "记忆", layer: 3 },
  observability: { color: "#64748b", fill: "rgba(100,116,139,0.10)", stroke: "#64748b", label: "可观测性", layer: 4 },
};

const SOURCE_ORDER: EventSource[] = ["runtime", "governance", "agent", "memory", "observability"];

const RELATION_LABEL: Record<CausalRelation, string> = {
  caused_by: "导致",
  influenced_by: "影响",
  blocked_by: "阻断",
  triggered_by: "触发",
};

const SEVERITY_DOT: Record<EventSeverity, string> = {
  info: "bg-os-muted",
  warn: "bg-amber-400",
  critical: "bg-rose-400",
};

// ═══════════════════════════════════════════════════════════════
// 图布局算法 — 分层 + 时间排序
// ═══════════════════════════════════════════════════════════════

interface PositionedNode extends CausalGraphNode {
  x: number;
  y: number;
}

const LAYER_HEIGHT = 130;
const NODE_RADIUS = 22;
const PADDING_X = 60;
const PADDING_Y = 50;
const MIN_LAYER_GAP = 180;

function layoutGraph(
  nodes: CausalGraphNode[],
  edges: CausalGraphEdge[],
  width: number,
): { positioned: PositionedNode[]; layerYs: number[] } {
  if (nodes.length === 0) return { positioned: [], layerYs: [] };

  // 按来源分组
  const bySource = new Map<EventSource, CausalGraphNode[]>();
  for (const n of nodes) {
    const arr = bySource.get(n.source) || [];
    arr.push(n);
    bySource.set(n.source, arr);
  }

  // 每层内按时间排序
  for (const arr of bySource.values()) {
    arr.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  }

  // 计算每层 Y 坐标（仅包含有节点的层）
  const activeLayers = SOURCE_ORDER.filter((s) => (bySource.get(s)?.length || 0) > 0);
  const layerYs = activeLayers.map((_, i) => PADDING_Y + i * LAYER_HEIGHT);

  // 计算每层 X 坐标（均匀分布）
  const positioned: PositionedNode[] = [];
  const usableWidth = Math.max(width - PADDING_X * 2, MIN_LAYER_GAP);

  activeLayers.forEach((source, layerIdx) => {
    const arr = bySource.get(source)!;
    const y = layerYs[layerIdx];
    const stepX = arr.length > 1 ? usableWidth / (arr.length - 1) : 0;
    arr.forEach((n, i) => {
      const x = arr.length === 1
        ? PADDING_X + usableWidth / 2
        : PADDING_X + i * stepX;
      positioned.push({ ...n, x, y });
    });
  });

  return { positioned, layerYs };
}

// ═══════════════════════════════════════════════════════════════
// 主页面
// ═══════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════
// 渲染契约 — Trace 运行时状态机
// GraphCanvas 仅允许在 "ready" 状态下挂载，彻底消灭 null-entry 渲染风险
// ═══════════════════════════════════════════════════════════════

type TraceRuntimeState =
  | "hydrating" // 正在播种 / graph 未水合完成
  | "ready"     // trace 有效且 nodes 已就绪，唯一允许渲染 GraphCanvas 的状态
  | "empty"     // 无 trace
  | "invalid";  // selectedTrace 已失效（不在 trace list 中）

export default function CausalGraphPage() {
  const traces = useRecentTraces(30);
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [showCriticalOnly, setShowCriticalOnly] = useState(false);
  const [isSeeding, setIsSeeding] = useState(false);
  const canvasRef = useRef<HTMLDivElement>(null);
  const [canvasWidth, setCanvasWidth] = useState(900);

  // 自动选中第一个 trace
  useEffect(() => {
    if (!selectedTrace && traces.length > 0) {
      setSelectedTrace(traces[0]);
    }
  }, [traces, selectedTrace]);

  // Fallback A — trace list 为空时自动生成默认 trace，保证 Graph Engine 永不进入“空白不可交互”状态
  const autoSeededRef = useRef(false);
  useEffect(() => {
    if (autoSeededRef.current) return;
    if (traces.length === 0) {
      autoSeededRef.current = true;
      setIsSeeding(true);
      const tid = simulateMultiCausalFlow();
      setSelectedTrace(tid);
      setSelectedNodeId(null);
      setIsSeeding(false);
    }
  }, [traces]);

  // 防 stale trace — selectedTrace 指向已不在 store 中的 trace 时清空
  // 仅在 traces 已水合（非空）时判定，避免与 autoSeed 的同步发布产生竞态
  useEffect(() => {
    if (selectedTrace && traces.length > 0 && !traces.includes(selectedTrace)) {
      setSelectedTrace(null);
      setSelectedNodeId(null);
    }
  }, [traces, selectedTrace]);

  // 统一的模拟入口：生成 trace 后直接选中，避免静默空白
  const handleSimulate = () => {
    setIsSeeding(true);
    const tid = simulateMultiCausalFlow();
    setSelectedTrace(tid);
    setSelectedNodeId(null);
    setIsSeeding(false);
  };

  // 监听 canvas 宽度
  useEffect(() => {
    const update = () => {
      if (canvasRef.current) {
        setCanvasWidth(canvasRef.current.clientWidth);
      }
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  const graph = useCausalGraph(selectedTrace);
  const topImpact = useTopImpactNodes(selectedTrace, 5);

  // ── 渲染契约（Render Gate）──
  // traceState 是 GraphCanvas 挂载的唯一授权凭据；canRenderGraph 为真才允许进入渲染阶段
  // hydrating 由 hook 的 hydrated lifecycle 凭据推导，而非用 nodes.length 反推，
  // 避免「合法空图（trace 存在但无事件）」被误判为「正在水合」
  const traceState: TraceRuntimeState = useMemo(() => {
    if (isSeeding) return "hydrating";
    if (!selectedTrace) return "empty";
    // traces 为空说明仍在水合中，不判 invalid（避免与 autoSeed 竞态）
    if (traces.length > 0 && !traces.includes(selectedTrace)) return "invalid";
    if (!graph.hydrated) return "hydrating";
    // 已水合但无节点 → 合法空图，归入 empty（非 hydrating）
    if (graph.nodes.length === 0) return "empty";
    return "ready";
  }, [isSeeding, selectedTrace, traces, graph.hydrated, graph.nodes.length]);

  const canRenderGraph = traceState === "ready";

  // 布局计算
  const { positioned, layerYs } = useMemo(
    () => layoutGraph(graph.nodes, graph.edges, canvasWidth),
    [graph.nodes, graph.edges, canvasWidth],
  );

  const nodeMap = useMemo(() => {
    const m = new Map<string, PositionedNode>();
    for (const n of positioned) m.set(n.event_id, n);
    return m;
  }, [positioned]);

  // 选中节点
  const selectedNode = selectedNodeId ? (nodeMap.get(selectedNodeId) ?? null) : null;
  const selectedEvent = selectedNodeId ? causalKernel.getEvent(selectedNodeId) : null;

  // 选中节点的因果链（父 + 子）
  const selectedCausalChain = useMemo(() => {
    if (!selectedNodeId) return { parents: [] as SystemEvent[], children: [] as SystemEvent[] };
    return {
      parents: causalKernel.getParents(selectedNodeId),
      children: causalKernel.getChildren(selectedNodeId),
    };
  }, [selectedNodeId, graph]);

  // 过滤显示（仅关键路径模式）
  const visibleEdges = useMemo(() => {
    if (!showCriticalOnly) return graph.edges;
    return graph.edges.filter((e) => e.is_critical_path);
  }, [graph.edges, showCriticalOnly]);

  const visibleNodeIds = useMemo(() => {
    const ids = new Set<string>();
    for (const e of visibleEdges) {
      ids.add(e.from);
      ids.add(e.to);
    }
    // 关键路径模式下也要包含选中节点
    if (selectedNodeId) ids.add(selectedNodeId);
    return ids;
  }, [visibleEdges, selectedNodeId, showCriticalOnly]);

  const canvasHeight = layerYs.length > 0 ? layerYs[layerYs.length - 1] + PADDING_Y : 400;

  return (
    <PageTransition>
      <div className="p-6 space-y-4 max-w-[1440px] mx-auto">
        {/* ── Header ── */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight flex items-center gap-2">
              <GitGraph size={16} className="text-emerald-400" />
              Causal Graph Engine
            </h1>
            <p className="text-xs text-os-subtle mt-0.5">
              知维 OS 因果图引擎 — Event → Node · Causal Link → Edge · Trace → Subgraph
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleSimulate}
              className="flex items-center gap-1.5 h-7 px-2.5 rounded-md border border-emerald-400/30 bg-emerald-400/10 text-2xs text-emerald-300 hover:bg-emerald-400/20 transition-colors"
            >
              <Zap size={11} />
              模拟因果图
            </button>
          </div>
        </div>

        {/* ── Trace Selector + Stats ── */}
        <div className="flex items-center gap-3 p-3 rounded-lg border border-os-border bg-os-surface">
          <div className="flex items-center gap-2">
            <Crosshair size={14} className="text-os-subtle" />
            <span className="text-2xs text-os-subtle uppercase tracking-wider">Trace</span>
          </div>
          <select
            value={selectedTrace || ""}
            onChange={(e) => {
              setSelectedTrace(e.target.value || null);
              setSelectedNodeId(null);
            }}
            className="h-7 px-2 rounded-md border border-os-border bg-os-base text-xs text-os-text-high font-mono focus:outline-none focus:border-emerald-400/50"
          >
            <option value="">{traces.length === 0 ? "— 无 Trace（自动生成中）—" : "— 选择 Trace —"}</option>
            {traces.map((t) => (
              <option key={t} value={t}>{t.slice(0, 24)}...</option>
            ))}
          </select>

          {graph.stats && (
            <div className="flex items-center gap-4 ml-auto">
              <Stat label="Nodes" value={graph.stats.node_count} />
              <Stat label="Edges" value={graph.stats.edge_count} />
              <Stat label="Roots" value={graph.stats.root_count} />
              <Stat label="Leaves" value={graph.stats.leaf_count} />
              <Stat label="Depth" value={graph.stats.max_depth} />
              {graph.criticalPath && (
                <Stat label="Critical" value={graph.criticalPath.nodes.length} accent="rose" />
              )}
            </div>
          )}

          <button
            onClick={() => setShowCriticalOnly(!showCriticalOnly)}
            className={cn(
              "flex items-center gap-1.5 h-7 px-2.5 rounded-md border text-2xs transition-colors",
              showCriticalOnly
                ? "border-rose-400/40 bg-rose-400/15 text-rose-300"
                : "border-os-border bg-os-base text-os-subtle hover:text-os-text",
            )}
          >
            <Flame size={11} />
            {showCriticalOnly ? "仅关键路径" : "全部边"}
          </button>
        </div>

        {/* ── Main Layout: Graph Canvas + Side Panel ── */}
        <div className="flex gap-4">
          {/* Graph Canvas */}
          <div
            ref={canvasRef}
            className="flex-1 rounded-lg border border-os-border bg-os-surface overflow-hidden relative"
            style={{ minHeight: canvasHeight }}
          >
            {!canRenderGraph ? (
              <EmptyState
                state={traceState}
                hasTrace={!!selectedTrace}
                onGenerate={handleSimulate}
              />
            ) : (
              <GraphCanvas
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

          {/* Side Panel */}
          <div className="w-80 shrink-0 rounded-lg border border-os-border bg-os-surface overflow-hidden flex flex-col">
            <SidePanel
              node={selectedNode}
              event={selectedEvent}
              parents={selectedCausalChain.parents}
              children={selectedCausalChain.children}
              topImpact={topImpact}
              onSelectNode={setSelectedNodeId}
            />
          </div>
        </div>
      </div>
    </PageTransition>
  );
}

// ═══════════════════════════════════════════════════════════════
// Graph Canvas — SVG 因果图可视化
// ═══════════════════════════════════════════════════════════════

interface GraphCanvasProps {
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
  positioned, layerYs, edges, nodeMap, visibleNodeIds,
  selectedNodeId, onSelectNode, canvasHeight, showCriticalOnly,
}: GraphCanvasProps) {
  const activeLayers = SOURCE_ORDER.filter((s) =>
    positioned.some((n) => n.source === s),
  );

  return (
    <svg
      width="100%"
      height={canvasHeight}
      className="block"
      style={{ background: "radial-gradient(circle at 50% 0%, rgba(16,185,129,0.03), transparent 60%)" }}
    >
      {/* 层背景线 + 标签 */}
      {activeLayers.map((source, i) => {
        const cfg = SOURCE_CONFIG[source];
        const y = layerYs[i];
        return (
          <g key={source}>
            <line
              x1={0} y1={y} x2="100%" y2={y}
              stroke={cfg.color} strokeOpacity={0.08} strokeDasharray="4 4"
            />
            <text
              x={12} y={y - 8}
              fill={cfg.color} fillOpacity={0.6}
              fontSize={10} fontWeight={500}
              className="uppercase tracking-wider"
            >
              {cfg.label}
            </text>
          </g>
        );
      })}

      {/* 边 */}
      <g>
        {edges.map((edge, i) => {
          const from = nodeMap.get(edge.from);
          const to = nodeMap.get(edge.to);
          if (!from || !to) return null;
          if (showCriticalOnly && !edge.is_critical_path) return null;

          const isCritical = edge.is_critical_path;
          const strokeColor = isCritical ? "#f43f5e" : "#64748b";
          const strokeOpacity = isCritical ? 0.7 : 0.25;
          const strokeWidth = Math.max(1, edge.weight * 2.5);

          // 贝塞尔曲线
          const midY = (from.y + to.y) / 2;
          const path = `M ${from.x} ${from.y} C ${from.x} ${midY}, ${to.x} ${midY}, ${to.x} ${to.y}`;

          return (
            <g key={`edge-${i}`}>
              <path
                d={path}
                fill="none"
                stroke={strokeColor}
                strokeOpacity={strokeOpacity}
                strokeWidth={strokeWidth}
                strokeDasharray={edge.relation === "influenced_by" ? "4 3" : undefined}
              />
              {isCritical && (
                <path
                  d={path}
                  fill="none"
                  stroke="#f43f5e"
                  strokeOpacity={0.3}
                  strokeWidth={strokeWidth + 4}
                  className="animate-pulse"
                />
              )}
            </g>
          );
        })}
      </g>

      {/* 节点 */}
      <g>
        {positioned.map((node) => {
          const cfg = SOURCE_CONFIG[node.source];
          const isSelected = node.event_id === selectedNodeId;
          const isVisible = visibleNodeIds.has(node.event_id);
          if (showCriticalOnly && !isVisible) return null;

          const isHighImpact = (node.impact_score || 0) > 5;
          const radius = NODE_RADIUS + (node.impact_score || 0) * 0.5;

          return (
            <g
              key={node.event_id}
              transform={`translate(${node.x}, ${node.y})`}
              className="cursor-pointer"
              onClick={() => onSelectNode(node.event_id)}
            >
              {/* 高影响光晕 */}
              {isHighImpact && (
                <circle
                  r={radius + 6}
                  fill={cfg.color}
                  fillOpacity={0.08}
                  className="animate-pulse"
                />
              )}
              {/* 选中环 */}
              {isSelected && (
                <circle
                  r={radius + 4}
                  fill="none"
                  stroke={cfg.color}
                  strokeWidth={1.5}
                  strokeOpacity={0.6}
                />
              )}
              {/* 节点主体 */}
              <circle
                r={radius}
                fill={cfg.fill}
                stroke={cfg.stroke}
                strokeWidth={isSelected ? 2 : 1}
              />
              {/* 严重级别点 */}
              <circle
                cx={radius * 0.6}
                cy={-radius * 0.6}
                r={3}
                className={SEVERITY_DOT[node.severity]}
                fill="currentColor"
              />
              {/* 节点标签 */}
              <text
                y={radius + 14}
                textAnchor="middle"
                fill={cfg.color}
                fontSize={9}
                fontWeight={500}
                className="font-mono pointer-events-none"
              >
                {node.type.split(".").pop()}
              </text>
              {/* impact score */}
              {node.impact_score !== undefined && node.impact_score > 0 && (
                <text
                  y={3}
                  textAnchor="middle"
                  fill={cfg.color}
                  fontSize={10}
                  fontWeight={600}
                  className="pointer-events-none"
                >
                  {Math.round(node.impact_score)}
                </text>
              )}
            </g>
          );
        })}
      </g>
    </svg>
  );
}

// ═══════════════════════════════════════════════════════════════
// Side Panel — 事件详情 + 因果链 + 影响分值
// ═══════════════════════════════════════════════════════════════

interface SidePanelProps {
  node: PositionedNode | null;
  event: SystemEvent | null;
  parents: SystemEvent[];
  children: SystemEvent[];
  topImpact: CausalGraphNode[];
  onSelectNode: (id: string) => void;
}

function SidePanel({ node, event, parents, children, topImpact, onSelectNode }: SidePanelProps) {
  if (!node || !event) {
    return (
      <div className="flex-1 flex flex-col">
        <PanelHeader title="事件详情" icon={CircleDot} />
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="text-center space-y-2">
            <Crosshair size={28} className="mx-auto text-os-muted" />
            <p className="text-xs text-os-subtle">点击图中的节点查看详情</p>
          </div>
        </div>
        <TopImpactList nodes={topImpact} onSelectNode={onSelectNode} />
      </div>
    );
  }

  const cfg = SOURCE_CONFIG[node.source];

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <PanelHeader title="事件详情" icon={CircleDot} onClose />
      <div className="flex-1 overflow-y-auto">
        {/* 节点基本信息 */}
        <div className="p-3 border-b border-os-border space-y-2">
          <div className="flex items-center gap-2">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ background: cfg.color }}
            />
            <span className="text-xs font-medium" style={{ color: cfg.color }}>
              {cfg.label}
            </span>
            <span className="text-2xs text-os-subtle font-mono">{node.type}</span>
          </div>
          <div className="text-2xs text-os-subtle font-mono break-all">
            {node.event_id}
          </div>
          <div className="flex items-center gap-3 text-2xs text-os-subtle">
            <span className="flex items-center gap-1">
              <div className={cn("w-1.5 h-1.5 rounded-full", SEVERITY_DOT[node.severity])} />
              {node.severity}
            </span>
            <span>{formatDate(node.timestamp)}</span>
          </div>
        </div>

        {/* Impact Score */}
        <div className="p-3 border-b border-os-border">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-2xs text-os-subtle uppercase tracking-wider flex items-center gap-1">
              <Target size={10} /> Impact Score
            </span>
            <span className="text-sm font-semibold" style={{ color: cfg.color }}>
              {Math.round(node.impact_score || 0)}
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-os-base overflow-hidden">
            <motion.div
              className="h-full rounded-full"
              style={{ background: cfg.color }}
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(100, (node.impact_score || 0) * 5)}%` }}
              transition={{ duration: 0.4 }}
            />
          </div>
          <div className="flex items-center justify-between mt-1 text-2xs text-os-subtle">
            <span>下游 {node.downstream_count || 0} 节点</span>
            <span>权重 {cfg.label}</span>
          </div>
        </div>

        {/* Payload 预览 */}
        <div className="p-3 border-b border-os-border">
          <div className="text-2xs text-os-subtle uppercase tracking-wider mb-1.5">Payload</div>
          <pre className="text-2xs text-os-text font-mono bg-os-base/50 rounded p-2 overflow-x-auto max-h-32">
{JSON.stringify(event.payload, null, 2)}
          </pre>
        </div>

        {/* 因果链 — 父事件 */}
        <div className="p-3 border-b border-os-border">
          <div className="text-2xs text-os-subtle uppercase tracking-wider mb-1.5 flex items-center gap-1">
            <ArrowRight size={10} className="rotate-180" /> 父事件（{parents.length}）
          </div>
          {parents.length === 0 ? (
            <span className="text-2xs text-os-muted">根事件（无父节点）</span>
          ) : (
            <div className="space-y-1">
              {parents.map((p) => (
                <CausalChainItem
                  key={p.event_id}
                  event={p}
                  relation="caused_by"
                  onClick={() => onSelectNode(p.event_id)}
                />
              ))}
            </div>
          )}
        </div>

        {/* 因果链 — 子事件 */}
        <div className="p-3 border-b border-os-border">
          <div className="text-2xs text-os-subtle uppercase tracking-wider mb-1.5 flex items-center gap-1">
            <ArrowRight size={10} /> 子事件（{children.length}）
          </div>
          {children.length === 0 ? (
            <span className="text-2xs text-os-muted">叶节点（无子事件）</span>
          ) : (
            <div className="space-y-1">
              {children.map((c) => (
                <CausalChainItem
                  key={c.event_id}
                  event={c}
                  onClick={() => onSelectNode(c.event_id)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Top Impact 节点 */}
        <TopImpactList nodes={topImpact} onSelectNode={onSelectNode} />
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// 子组件
// ═══════════════════════════════════════════════════════════════

function PanelHeader({
  title, icon: Icon, onClose,
}: {
  title: string;
  icon: typeof CircleDot;
  onClose?: boolean;
}) {
  return (
    <div className="flex items-center justify-between h-10 px-3 border-b border-os-border shrink-0">
      <div className="flex items-center gap-1.5">
        <Icon size={13} className="text-os-subtle" />
        <span className="text-2xs font-medium text-os-text uppercase tracking-wider">{title}</span>
      </div>
      {onClose && (
        <span className="text-2xs text-os-muted">点击节点切换</span>
      )}
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: "rose" }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-2xs text-os-subtle uppercase tracking-wider">{label}</span>
      <span className={cn(
        "text-xs font-semibold font-mono",
        accent === "rose" ? "text-rose-400" : "text-os-text-high",
      )}>
        {value}
      </span>
    </div>
  );
}

function CausalChainItem({
  event, relation, onClick,
}: {
  event: SystemEvent;
  relation?: CausalRelation;
  onClick: () => void;
}) {
  const cfg = SOURCE_CONFIG[event.source];
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-2 p-1.5 rounded-md hover:bg-os-elevated transition-colors text-left group"
    >
      <div
        className="w-1.5 h-1.5 rounded-full shrink-0"
        style={{ background: cfg.color }}
      />
      <span className="text-2xs text-os-text font-mono truncate flex-1">
        {event.type.split(".").pop()}
      </span>
      {relation && (
        <span className="text-2xs text-os-muted shrink-0">
          {RELATION_LABEL[relation]}
        </span>
      )}
      <ChevronRight size={10} className="text-os-muted group-hover:text-os-text shrink-0" />
    </button>
  );
}

function TopImpactList({
  nodes, onSelectNode,
}: {
  nodes: CausalGraphNode[];
  onSelectNode: (id: string) => void;
}) {
  if (nodes.length === 0) return null;
  return (
    <div className="p-3">
      <div className="text-2xs text-os-subtle uppercase tracking-wider mb-1.5 flex items-center gap-1">
        <Flame size={10} /> 高影响节点 Top {nodes.length}
      </div>
      <div className="space-y-1">
        {nodes.map((n, i) => {
          const cfg = SOURCE_CONFIG[n.source];
          return (
            <button
              key={n.event_id}
              onClick={() => onSelectNode(n.event_id)}
              className="w-full flex items-center gap-2 p-1.5 rounded-md hover:bg-os-elevated transition-colors text-left group"
            >
              <span className="text-2xs text-os-muted font-mono w-3">{i + 1}</span>
              <div
                className="w-1.5 h-1.5 rounded-full shrink-0"
                style={{ background: cfg.color }}
              />
              <span className="text-2xs text-os-text font-mono truncate flex-1">
                {n.type.split(".").pop()}
              </span>
              <span className="text-2xs font-semibold shrink-0" style={{ color: cfg.color }}>
                {Math.round(n.impact_score || 0)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function EmptyState({
  state,
  hasTrace,
  onGenerate,
}: {
  state: TraceRuntimeState;
  hasTrace: boolean;
  onGenerate: () => void;
}) {
  // 状态 hydrating — 播种中 / graph 未水合
  if (state === "hydrating") {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <div className="text-center space-y-3">
          <RefreshCw size={32} className="mx-auto text-emerald-400 animate-spin" />
          <div className="space-y-1">
            <p className="text-sm text-os-text font-medium">正在生成默认 Trace…</p>
            <p className="text-2xs text-os-subtle">Causal Kernel 正在播种示例因果链</p>
          </div>
        </div>
      </div>
    );
  }

  // 状态 invalid — selectedTrace 已失效，自动恢复中
  if (state === "invalid") {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <div className="text-center space-y-3">
          <AlertTriangle size={40} className="mx-auto text-amber-400" />
          <div className="space-y-1">
            <p className="text-sm text-os-text font-medium">Trace 已失效</p>
            <p className="text-2xs text-os-subtle">所选 Trace 已从内核移除，正在自动切换到可用 Trace</p>
          </div>
          <button
            onClick={onGenerate}
            className="inline-flex items-center gap-1.5 h-7 px-3 rounded-md border border-emerald-400/30 bg-emerald-400/10 text-2xs text-emerald-300 hover:bg-emerald-400/20 transition-colors"
          >
            <Zap size={11} />
            生成新 Trace
          </button>
        </div>
      </div>
    );
  }

  // 状态 empty — 细分两种语义：
  //   1. 无 trace（hasTrace=false）→ "No trace available" + Generate first trace
  //   2. 合法空图（hasTrace=true，trace 存在但已水合且无事件）→ "该 Trace 暂无事件" + 模拟因果图
  const title = hasTrace ? "该 Trace 暂无事件" : "No trace available";
  const hint = hasTrace
    ? "该 Trace 已水合但不含任何因果事件，请选择其他 Trace 或生成新数据"
    : "尚未生成任何 Trace，点击下方按钮生成首个因果图";
  const cta = hasTrace ? "模拟因果图" : "Generate first trace";

  return (
    <div className="flex items-center justify-center h-full min-h-[400px]">
      <div className="text-center space-y-3">
        <GitGraph size={40} className="mx-auto text-os-muted" />
        <div className="space-y-1">
          <p className="text-sm text-os-text font-medium">{title}</p>
          <p className="text-2xs text-os-subtle">{hint}</p>
        </div>
        <button
          onClick={onGenerate}
          className="inline-flex items-center gap-1.5 h-7 px-3 rounded-md border border-emerald-400/30 bg-emerald-400/10 text-2xs text-emerald-300 hover:bg-emerald-400/20 transition-colors"
        >
          <Zap size={11} />
          {cta}
        </button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// 模拟多父因果图 — 演示图结构（非树）
// ═══════════════════════════════════════════════════════════════

function simulateMultiCausalFlow() {
  const trace_id = newTraceId("graph");

  // 1. Runtime: Kill Switch 触发（根事件）
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

  // 2. Agent: 决策（根事件，独立起点）
  const agentDecision = createRootEvent(
    "agent",
    "agent.decision.made",
    "warn",
    trace_id,
    {
      agent_id: "agent-002",
      decision: "evaluate_risk",
      reasoning: "检测到策略违规，评估风险等级",
      confidence: 0.78,
      alternatives_considered: ["block", "warn", "allow"],
    },
    "agent_decision",
  );

  // 3. Governance: 策略评估 — 单父（agent decision）
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

  // 4. Runtime: Gate 拒绝 — 多父（killTriggered + policyEval）
  //    演示图结构：一个事件由 runtime kill + governance policy 共同导致
  const gateDenied = createMultiCausalEvent(
    [
      { event: killTriggered, relation: "triggered_by", weight: 0.9 },
      { event: policyEval, relation: "caused_by", weight: 1.0 },
    ],
    policyEval, // 主父
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

  // 5. Governance: 审计记录 — 子事件（gateDenied）
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

  // 6. Memory: 写入 LTM — 多父（gateDenied + auditRecord）
  //    演示：memory write 挂在 causal chain 上，且由多个 governance 事件共同触发
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

  // 7. Memory: 反思触发 — 子事件（memoryWrite）
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

  // 8. Observability: Trace 完成（overlay）
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
