"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search, GitGraph, RotateCcw, X, Brain, Activity,
  ZoomIn, ZoomOut,
} from "lucide-react";
import { DataSet } from "vis-data";
import { Network, type Data, type Edge, type Node } from "vis-network";
import { api } from "@/services/api";
import { PageTransition } from "@/components/animations/page-transition";
import { Skeleton } from "@/components/animations/skeleton";
import { KnowledgeGraphBackground } from "@/components/graph/KnowledgeGraphBackground";
import { cn, formatDate, importanceColor } from "@/lib/utils";
import type { GraphData, EntityDetail } from "@/types";

type GraphNodeUpdate = Partial<Node> & { id: string; label?: string; title?: string; group?: string };
type GraphEdgeUpdate = Partial<Edge> & { id: string };
type NetworkDataBridge = {
  body: {
    data: {
      nodes: {
        update(items: GraphNodeUpdate[]): void;
        get(): GraphNodeUpdate[];
      };
      edges: {
        update(items: GraphEdgeUpdate[]): void;
      };
    };
  };
};
type VisHoverParams = { node?: string };
type VisClickParams = { nodes: string[]; edges: string[] };

function networkData(network: Network) {
  return (network as unknown as NetworkDataBridge).body.data;
}

// ═══════════════════════════════════════════
// Design Tokens — 克制 · 深空 · 智能体网络
// ═══════════════════════════════════════════

const NODE_SIZE_SCALE = 0.55;

const NODE_COLORS: Record<string, string> = {
  entity:  "#7F8CFF",  // soft indigo
  concept: "#4ADE80",  // soft emerald
  memory:  "#A78BFA",  // soft violet
  image:   "#FACC15",  // soft amber
};

const NODE_GLOW: Record<string, string> = {
  entity:  "rgba(127,140,255,0.25)",
  concept: "rgba(74,222,128,0.25)",
  memory:  "rgba(167,139,250,0.25)",
  image:   "rgba(250,204,21,0.25)",
};

const GROUP_COLORS = [
  "#7F8CFF", "#4ADE80", "#FACC15", "#F87171", "#A78BFA",
  "#38BDF8", "#FB923C", "#A3E635", "#E879F9", "#FDBA74",
];

// Edge — 蓝紫渐变主关系，灰紫次级
const EDGE_PRIMARY   = "rgba(111,123,255,0.55)";
const EDGE_SECONDARY = "rgba(139,128,188,0.22)";
const EDGE_COOCCUR   = "rgba(90,82,128,0.18)";

// Highlight palette
const HL_BG     = "#5B8DEE";
const HL_BORDER = "#7BA5F7";
const HL_EDGE   = "rgba(91,141,238,0.65)";
const DIM_NODE  = "rgba(110,108,135,0.15)";
const DIM_BORDER_NODE = "rgba(110,108,135,0.08)";
const DIM_EDGE  = "rgba(80,76,110,0.08)";

// ── Sub-components ─────────────────────────────────────

function EntityDrawer({
  entityName, onClose,
}: {
  entityName: string | null;
  onClose: () => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["graph-entity", entityName],
    queryFn: () => api.graph.entity(entityName!),
    enabled: !!entityName,
  });

  return (
    <AnimatePresence>
      {entityName && (
        <>
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 z-40" onClick={onClose}
          />
          <motion.div
            initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="fixed right-0 top-0 bottom-0 w-full max-w-md bg-[#0E0B1A] border-l border-white/5 z-50 overflow-y-auto"
          >
            <div className="sticky top-0 bg-[#0E0B1A]/95 backdrop-blur border-b border-white/5 px-5 py-3 flex items-center justify-between z-10">
              <h2 className="text-sm font-semibold text-zinc-200">{entityName}</h2>
              <button onClick={onClose} className="p-1.5 rounded hover:bg-white/5 text-zinc-500">
                <X size={16} />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {isLoading ? (
                <div className="space-y-3">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-20 w-full" />
                  <Skeleton className="h-20 w-full" />
                </div>
              ) : data ? (
                <>
                  <div className="flex items-center gap-3 text-2xs">
                    <span className="px-1.5 py-0.5 rounded bg-indigo-400/10 text-indigo-400">
                      {data.entity_type || "entity"}
                    </span>
                    <span className="text-zinc-500">提及 {data.mention_count} 次</span>
                    {data.first_seen && <span className="text-zinc-600">首次 {formatDate(data.first_seen)}</span>}
                  </div>

                  {data.recent_activity.length > 0 && (
                    <div>
                      <h3 className="text-2xs text-zinc-500 uppercase tracking-wider mb-2">最近活动</h3>
                      <div className="space-y-1.5">
                        {data.recent_activity.map((act) => (
                          <div key={act.id} className="text-2xs text-zinc-300 line-clamp-2 bg-white/5 rounded p-2">
                            <span className="text-zinc-500">{act.timestamp.slice(0, 10)} </span>
                            {act.content_preview}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {data.related_entities.length > 0 && (
                    <div>
                      <h3 className="text-2xs text-zinc-500 uppercase tracking-wider mb-2">
                        相关实体 ({data.related_entities.length})
                      </h3>
                      <div className="flex flex-wrap gap-1.5">
                        {data.related_entities.map((e) => (
                          <span key={e.name} className="text-2xs px-2 py-1 rounded-full bg-white/5 text-zinc-400 border border-white/5">
                            {e.name}
                            <span className="text-zinc-600 ml-1">×{e.co_count}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {data.related_memories.length > 0 && (
                    <div>
                      <h3 className="text-2xs text-zinc-500 uppercase tracking-wider mb-2">
                        相关记忆 ({data.related_memories.length})
                      </h3>
                      <div className="space-y-2">
                        {data.related_memories.slice(0, 10).map((mem) => (
                          <div key={mem.id} className="text-xs text-zinc-300 bg-white/5 rounded p-2.5">
                            <p className="line-clamp-3 leading-relaxed">{mem.content_preview}</p>
                            <div className="flex items-center gap-2 mt-1.5 text-2xs text-zinc-500">
                              <span>{mem.timestamp.slice(0, 10)}</span>
                              <span className={importanceColor(mem.importance)}>重要度 {mem.importance}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <p className="text-xs text-zinc-500 text-center py-8">加载失败</p>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

// ── BFS ─────────────────────────────────────────────────

function bfsNeighbors(
  nodeId: string,
  adj: Map<string, string[]>,
  depth: number,
): Set<string> {
  const visited = new Set<string>([nodeId]);
  let frontier = [nodeId];
  for (let d = 0; d < depth; d++) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const nb of adj.get(id) || []) {
        if (!visited.has(nb)) { visited.add(nb); next.push(nb); }
      }
    }
    frontier = next;
    if (!frontier.length) break;
  }
  return visited;
}

// ═══════════════════════════════════════════
// Main Page
// ═══════════════════════════════════════════

export default function GraphPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasWrapperRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const graphDataRef = useRef<GraphData | null>(null);
  const adjRef = useRef<Map<string, string[]>>(new Map());
  const [searchTerm, setSearchTerm] = useState("");
  const [entityFilter, setEntityFilter] = useState("");
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const [stats, setStats] = useState<GraphData["stats"] | null>(null);
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);
  const [mousePos, setMousePos] = useState({ x: 0.5, y: 0.5 });

  const { data, isLoading } = useQuery({
    queryKey: ["graph", entityFilter],
    queryFn: () => api.graph.get({
      entity_type: entityFilter || undefined,
      limit: 300,
    }),
    refetchInterval: 60000,
  });

  // ── clearHighlight ──
  const clearHighlight = useCallback(() => {
    const net = networkRef.current;
    if (!net) return;
    setFocusNodeId(null);
    const gd = graphDataRef.current;
    if (!gd) return;

    const groupColorMap: Record<string, string> = {};
    let gi = 0;
    const ugs = [...new Set(gd.nodes.map(n => n.group).filter(Boolean))];
    for (const g of ugs) { groupColorMap[g] = GROUP_COLORS[gi % GROUP_COLORS.length]; gi++; }

    networkData(net).nodes.update(gd.nodes.map(n => ({
      id: n.id,
      color: {
        background: NODE_COLORS[n.type] || groupColorMap[n.group] || "#7F8CFF",
        border: "rgba(255,255,255,0.08)",
        highlight: { background: NODE_COLORS[n.type] || "#7F8CFF", border: "rgba(255,255,255,0.25)" },
        hover: { background: NODE_COLORS[n.type] || "#7F8CFF", border: "rgba(255,255,255,0.4)" },
      },
      borderWidth: 1,
      font: { color: "rgba(228,228,231,0.7)", size: 9, face: "Inter, sans-serif" },
      shadow: false,
    })));

    networkData(net).edges.update(gd.edges.map(e => ({
      id: `${e.source}__${e.target}__${e.relation}`,
      color: {
        color: e.relation === "co_occurrence" ? EDGE_COOCCUR : EDGE_SECONDARY,
        highlight: HL_EDGE,
        hover: "rgba(145,155,255,0.45)",
      },
      width: Math.max(e.weight * 0.55, 0.35),
    })));
  }, []);

  // ── buildGraph ──
  const buildGraph = useCallback((graphData: GraphData) => {
    if (!containerRef.current) return;
    const container = containerRef.current;

    if (networkRef.current) { networkRef.current.destroy(); networkRef.current = null; }
    if (!graphData.nodes.length) return;

    graphDataRef.current = graphData;

    // adjacency
    const adj = new Map<string, string[]>();
    for (const e of graphData.edges) {
      if (!adj.has(e.source)) adj.set(e.source, []);
      if (!adj.has(e.target)) adj.set(e.target, []);
      adj.get(e.source)!.push(e.target);
      adj.get(e.target)!.push(e.source);
    }
    adjRef.current = adj;

    // group colours
    const groupColorMap: Record<string, string> = {};
    let gi = 0;
    const ugs = [...new Set(graphData.nodes.map(n => n.group).filter(Boolean))];
    for (const g of ugs) { groupColorMap[g] = GROUP_COLORS[gi % GROUP_COLORS.length]; gi++; }

    const nodes = new DataSet(graphData.nodes.map(n => ({
      id: n.id,
      label: n.label.length > 22 ? n.label.slice(0, 22) + "…" : n.label,
      title: `<b>${n.label}</b><br/>${n.type} · 提及${n.memory_count} · 重要度${n.importance}`,
      group: n.group || n.type,
      value: (Math.max(n.importance, 3) + Math.min(n.memory_count, 10)) * NODE_SIZE_SCALE,
      color: {
        background: NODE_COLORS[n.type] || groupColorMap[n.group] || "#7F8CFF",
        border: "rgba(255,255,255,0.08)",
        highlight: { background: NODE_COLORS[n.type] || "#7F8CFF", border: "rgba(255,255,255,0.25)" },
        hover: { background: NODE_COLORS[n.type] || "#7F8CFF", border: "rgba(255,255,255,0.4)" },
      },
      font: { color: "rgba(228,228,231,0.65)", size: 9, face: "Inter, sans-serif" },
      borderWidth: 1,
      shape: n.type === "concept" ? "diamond" : n.type === "memory" ? "box" : "dot",
      size: (9 + Math.min(n.memory_count * 2, 32)) * NODE_SIZE_SCALE,
      shadow: { enabled: true, color: NODE_GLOW[n.type] || "rgba(127,140,255,0.2)", size: 8 },
    })));

    // ── Curved Bézier edges with edge-bundling ──
    const edges = new DataSet(graphData.edges.map((e, idx) => {
      const weight = e.weight;
      const isCooccur = e.relation === "co_occurrence";
      // alternate CW / CCW to reduce overlapping
      const roundness = 0.15 + Math.min(weight * 0.04, 0.25);
      const smoothType = idx % 2 === 0 ? "curvedCW" : "curvedCCW";
      return {
        id: `${e.source}__${e.target}__${e.relation}`,
        from: e.source,
        to: e.target,
        label: isCooccur ? "" : e.relation.slice(0, 6),
        title: `${e.relation} · 权重 ${weight}`,
        value: weight,
        color: {
          color: isCooccur ? EDGE_COOCCUR : EDGE_SECONDARY,
          highlight: HL_EDGE,
          hover: "rgba(145,155,255,0.45)",
        },
        width: Math.max(weight * 0.55, 0.35),
        smooth: {
          type: smoothType,
          roundness: roundness,
        },
        font: { color: "rgba(200,200,220,0.35)", size: 7, strokeWidth: 0 },
        arrows: { to: { enabled: false } },
      };
    }));

    const network = new Network(container, { nodes, edges } as unknown as Data, {
      physics: {
        solver: "forceAtlas2Based",
        forceAtlas2Based: {
          gravitationalConstant: -55,
          centralGravity: 0.008,
          springLength: 130,
          springConstant: 0.06,
          damping: 0.35,
        },
        stabilization: { iterations: 80, updateInterval: 25 },
      },
      interaction: {
        hover: true,
        tooltipDelay: 180,
        zoomView: true,
        dragView: true,
        navigationButtons: false,
      },
      nodes: {
        scaling: { min: 4 * NODE_SIZE_SCALE, max: 28 * NODE_SIZE_SCALE },
      },
      edges: {
        scaling: { min: 0.25, max: 6 },
      },
      layout: { improvedLayout: true },
    });

    // ── Hover → 1-degree highlight ──
    network.on("hoverNode", (params?: VisHoverParams) => {
      // first reset all from any previous hover
      clearHighlight();
      const nodeId = params?.node;
      if (!nodeId) return;
      const gd = graphDataRef.current!;
      const adjMap = adjRef.current;
      const hl = bfsNeighbors(nodeId, adjMap, 1);

      const hlEdgeIds = new Set<string>();
      for (const e of graphData.edges) {
        if (hl.has(e.source) && hl.has(e.target)) {
          hlEdgeIds.add(`${e.source}__${e.target}__${e.relation}`);
        }
      }

      networkData(network).nodes.update(gd.nodes.map(n => {
        if (n.id === nodeId) return {
          id: n.id,
          color: {
            background: HL_BG,
            border: HL_BORDER,
            highlight: { background: HL_BORDER, border: "#A5C5FF" },
            hover: { background: "#4A7BDE", border: HL_BORDER },
          },
          borderWidth: 2.5,
          font: { color: "#D6E4FF", size: 11, face: "Inter, sans-serif" },
          shadow: { enabled: true, color: "rgba(91,141,238,0.5)", size: 16 },
        };
        if (hl.has(n.id)) return {
          id: n.id,
          color: {
            background: HL_BG,
            border: HL_BORDER,
            highlight: { background: HL_BORDER, border: "#A5C5FF" },
            hover: { background: "#4A7BDE", border: HL_BORDER },
          },
          borderWidth: 2,
          font: { color: "rgba(214,228,255,0.85)", size: 10, face: "Inter, sans-serif" },
          shadow: { enabled: true, color: "rgba(91,141,238,0.35)", size: 10 },
        };
        return {
          id: n.id,
          color: {
            background: DIM_NODE,
            border: DIM_BORDER_NODE,
            highlight: { background: DIM_NODE, border: DIM_BORDER_NODE },
            hover: { background: DIM_NODE, border: DIM_BORDER_NODE },
          },
          borderWidth: 0.3,
          font: { color: "rgba(140,135,165,0.2)", size: 8, face: "Inter, sans-serif" },
          shadow: false,
        };
      }));

      networkData(network).edges.update(graphData.edges.map(e => {
        const eid = `${e.source}__${e.target}__${e.relation}`;
        return hlEdgeIds.has(eid)
          ? { id: eid, color: { color: HL_EDGE, highlight: "#8DAEFF", hover: "#A5C5FF" }, width: Math.max(e.weight * 0.9, 0.9) }
          : { id: eid, color: { color: DIM_EDGE, highlight: DIM_EDGE, hover: DIM_EDGE }, width: Math.max(e.weight * 0.2, 0.15) };
      }));
    });

    network.on("blurNode", () => { clearHighlight(); });

    // ── Click → focus with BFS-2 ──
    network.on("click", (params?: VisClickParams) => {
      clearHighlight();
      if (!params) return;
      if (params.nodes.length === 0) return;

      const clickedId = params.nodes[0] as string;
      const gd = graphDataRef.current!;
      const adjMap = adjRef.current;
      const hl = bfsNeighbors(clickedId, adjMap, 2);
      setFocusNodeId(clickedId);

      const clickedNode = gd.nodes.find(n => n.id === clickedId);
      if (clickedNode?.type === "entity") setSelectedEntity(clickedNode.label);
      else setSelectedEntity(null);

      const hlEdgeIds = new Set<string>();
      for (const e of graphData.edges) {
        if (hl.has(e.source) && hl.has(e.target)) {
          hlEdgeIds.add(`${e.source}__${e.target}__${e.relation}`);
        }
      }

      networkData(network).nodes.update(gd.nodes.map(n => {
        if (n.id === clickedId) return {
          id: n.id,
          color: {
            background: HL_BG,
            border: HL_BORDER,
            highlight: { background: HL_BORDER, border: "#A5C5FF" },
            hover: { background: "#4A7BDE", border: HL_BORDER },
          },
          borderWidth: 3,
          font: { color: "#D6E4FF", size: 12, face: "Inter, sans-serif" },
          shadow: { enabled: true, color: "rgba(91,141,238,0.55)", size: 20 },
        };
        if (hl.has(n.id)) return {
          id: n.id,
          color: {
            background: HL_BG,
            border: HL_BORDER,
            highlight: { background: HL_BORDER, border: "#A5C5FF" },
            hover: { background: "#4A7BDE", border: HL_BORDER },
          },
          borderWidth: 2.2,
          font: { color: "rgba(214,228,255,0.9)", size: 10, face: "Inter, sans-serif" },
          shadow: { enabled: true, color: "rgba(91,141,238,0.4)", size: 12 },
        };
        return {
          id: n.id,
          color: {
            background: DIM_NODE,
            border: DIM_BORDER_NODE,
            highlight: { background: DIM_NODE, border: DIM_BORDER_NODE },
            hover: { background: DIM_NODE, border: DIM_BORDER_NODE },
          },
          borderWidth: 0.3,
          font: { color: "rgba(140,135,165,0.2)", size: 8, face: "Inter, sans-serif" },
          shadow: false,
        };
      }));

      networkData(network).edges.update(graphData.edges.map(e => {
        const eid = `${e.source}__${e.target}__${e.relation}`;
        return hlEdgeIds.has(eid)
          ? { id: eid, color: { color: HL_EDGE, highlight: "#8DAEFF", hover: "#A5C5FF" }, width: Math.max(e.weight * 1, 0.9) }
          : { id: eid, color: { color: DIM_EDGE, highlight: DIM_EDGE, hover: DIM_EDGE }, width: Math.max(e.weight * 0.2, 0.15) };
      }));
    });

    // Click empty → clear
    network.on("click", (p?: VisClickParams) => {
      if (p && p.nodes.length === 0 && p.edges.length === 0) clearHighlight();
    });

    networkRef.current = network;
    setStats(graphData.stats);
  }, [clearHighlight]);

  useEffect(() => { if (data) buildGraph(data); }, [data, buildGraph]);

  useEffect(() => {
    const onResize = () => networkRef.current?.redraw();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => () => {
    if (networkRef.current) { networkRef.current.destroy(); networkRef.current = null; }
  }, []);

  // ── Search ──
  const handleSearch = useCallback(() => {
    if (!networkRef.current || !searchTerm.trim()) return;
    const allNodes = networkData(networkRef.current).nodes.get();
    const matchIds = allNodes
      .filter((n) => (n.label || "").toLowerCase().includes(searchTerm.toLowerCase()) || (n.title || "").toLowerCase().includes(searchTerm.toLowerCase()))
      .map((n) => n.id);
    if (matchIds.length > 0) {
      networkRef.current.selectNodes(matchIds, false);
      networkRef.current.focus(matchIds[0], { scale: 1.5, animation: true });
      setSelectedEntity(allNodes.find((n) => n.id === matchIds[0])?.label || null);
    }
  }, [searchTerm]);

  const zoomIn  = () => networkRef.current?.moveTo({ scale: (networkRef.current.getScale() || 1) * 1.3 });
  const zoomOut = () => networkRef.current?.moveTo({ scale: (networkRef.current.getScale() || 1) * 0.7 });
  const resetView = () => networkRef.current?.fit({ animation: { duration: 500, easingFunction: "easeInOutQuad" } });

  // mouse tracking for parallax
  const handleCanvasMouseMove = useCallback((e: React.MouseEvent) => {
    if (!canvasWrapperRef.current) return;
    const r = canvasWrapperRef.current.getBoundingClientRect();
    setMousePos({ x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height });
  }, []);

  const parallaxIntensity = ((mousePos.x - 0.5) * 2 + (mousePos.y - 0.5) * 2) * 0.5;

  const entityTypeOptions = ["", "person", "tech", "org", "topic", "location"];

  return (
    <PageTransition>
      <div className="p-6 space-y-3 max-w-[1440px] mx-auto h-[calc(100vh-4rem)] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between shrink-0">
          <div>
            <h1 className="text-lg font-semibold text-zinc-200 tracking-tight">知识图谱</h1>
            <p className="text-xs text-zinc-500 mt-0.5">
              {stats ? `${stats.node_count} 节点 · ${stats.edge_count} 关系` : "加载中…"}
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <button onClick={zoomIn} className="p-1.5 rounded hover:bg-white/5 text-zinc-500 hover:text-zinc-300" title="放大">
              <ZoomIn size={14} />
            </button>
            <button onClick={zoomOut} className="p-1.5 rounded hover:bg-white/5 text-zinc-500 hover:text-zinc-300" title="缩小">
              <ZoomOut size={14} />
            </button>
            <button onClick={resetView} className="p-1.5 rounded hover:bg-white/5 text-zinc-500 hover:text-zinc-300" title="重置">
              <RotateCcw size={14} />
            </button>
            {focusNodeId && (
              <button onClick={clearHighlight} className="px-2.5 py-1 rounded text-2xs text-[#7BA5F7] bg-[#7BA5F7]/10 hover:bg-[#7BA5F7]/15 transition-colors">
                取消聚焦
              </button>
            )}
            <span className="w-px h-4 bg-white/5 mx-0.5" />
            <select
              value={entityFilter}
              onChange={(e) => setEntityFilter(e.target.value)}
              className="h-7 px-2 rounded bg-white/5 border border-white/5 text-2xs text-zinc-300 focus:outline-none focus:border-white/10"
            >
              <option value="">全部实体类型</option>
              {entityTypeOptions.filter(Boolean).map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <div className="relative">
              <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-zinc-600" />
              <input
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                placeholder="搜索实体…"
                className="w-36 h-7 pl-7 pr-2 bg-white/5 border border-white/5 rounded text-2xs text-zinc-300 placeholder:text-zinc-600 focus:outline-none focus:border-white/10"
              />
            </div>
          </div>
        </div>

        {/* Stats */}
        {stats && (
          <div className="flex items-center gap-4 shrink-0 text-2xs text-zinc-500">
            <span className="flex items-center gap-1"><Brain size={11} className="text-[#7F8CFF]" />实体 {stats.entity_nodes || 0}</span>
            <span className="flex items-center gap-1"><GitGraph size={11} className="text-[#4ADE80]" />概念 {stats.concept_nodes || 0}</span>
            <span className="flex items-center gap-1"><Activity size={11} className="text-[#FACC15]" />关系 {stats.edge_count || 0}</span>
            {stats.top_entities && stats.top_entities.length > 0 && (
              <>
                <span className="w-px h-3 bg-white/5" />
                {stats.top_entities.slice(0, 5).map(name => (
                  <button key={name} onClick={() => setSelectedEntity(name)}
                    className="px-1.5 py-0.5 rounded bg-white/5 text-[#7F8CFF]/70 hover:text-[#7F8CFF] transition-colors">
                    {name}
                  </button>
                ))}
              </>
            )}
          </div>
        )}

        {/* ── Canvas ── */}
        <div
          ref={canvasWrapperRef}
          onMouseMove={handleCanvasMouseMove}
          className="flex-1 min-h-0 relative rounded-lg overflow-hidden border border-white/5"
        >
          <KnowledgeGraphBackground intensity={parallaxIntensity} focusActive={!!focusNodeId} />

          {isLoading ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center">
              <div className="text-center space-y-3">
                <GitGraph size={48} className="text-zinc-700 mx-auto animate-pulse" />
                <p className="text-xs text-zinc-600">加载图谱数据…</p>
              </div>
            </div>
          ) : !data || data.nodes.length === 0 ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center">
              <div className="text-center space-y-2">
                <GitGraph size={48} className="text-zinc-700 mx-auto opacity-20" />
                <p className="text-xs text-zinc-600">暂无图谱数据</p>
                <p className="text-2xs text-zinc-700">开始记录带有实体的记忆后，图谱将自动生成</p>
              </div>
            </div>
          ) : null}

          <div
            ref={containerRef}
            className="w-full h-full relative z-[2]"
            style={{ background: "transparent", minHeight: 400 }}
          />
        </div>

        <EntityDrawer entityName={selectedEntity} onClose={() => setSelectedEntity(null)} />
      </div>
    </PageTransition>
  );
}
