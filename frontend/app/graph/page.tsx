"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search, GitGraph, Maximize2, Minimize2, RotateCcw,
  Filter, X, ExternalLink, Brain, Hash, Activity,
  ChevronDown, ZoomIn, ZoomOut,
} from "lucide-react";
import { DataSet } from "vis-data";
import { Network } from "vis-network";
import { api } from "@/services/api";
import { PageTransition } from "@/components/animations/page-transition";
import { Skeleton } from "@/components/animations/skeleton";
import { cn, formatDate, importanceColor } from "@/lib/utils";
import type { GraphData, GraphNode, EntityDetail } from "@/types";

// ── Constants ──

const NODE_COLORS: Record<string, string> = {
  entity: "#818CF8",   // indigo
  concept: "#34D399",  // emerald
  memory: "#A78BFA",   // violet
  image: "#FBBF24",    // amber
};

const GROUP_COLORS = [
  "#818CF8", "#34D399", "#FBBF24", "#F87171", "#A78BFA",
  "#38BDF8", "#FB923C", "#A3E635", "#E879F9", "#FDBA74",
];

// ── Sub-components ──

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
            className="fixed inset-0 bg-black/40 z-40" onClick={onClose}
          />
          <motion.div
            initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="fixed right-0 top-0 bottom-0 w-full max-w-md bg-os-surface border-l border-os-border z-50 overflow-y-auto shadow-os-lg"
          >
            <div className="sticky top-0 bg-os-surface border-b border-os-border px-5 py-3 flex items-center justify-between z-10">
              <h2 className="text-sm font-semibold text-os-text-high">{entityName}</h2>
              <button onClick={onClose} className="p-1.5 rounded hover:bg-os-elevated">
                <X size={16} className="text-os-subtle" />
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
                  {/* Stats */}
                  <div className="flex items-center gap-3 text-2xs">
                    <span className="os-badge bg-indigo-400/10 text-indigo-400">
                      {data.entity_type || "entity"}
                    </span>
                    <span className="text-os-subtle">提及 {data.mention_count} 次</span>
                    {data.first_seen && (
                      <span className="text-os-muted">首次 {formatDate(data.first_seen)}</span>
                    )}
                  </div>

                  {/* Recent Activity */}
                  {data.recent_activity.length > 0 && (
                    <div>
                      <h3 className="text-2xs text-os-subtle uppercase tracking-wider mb-2">最近活动</h3>
                      <div className="space-y-1.5">
                        {data.recent_activity.map((act) => (
                          <div key={act.id} className="text-2xs text-os-text-high line-clamp-2 bg-os-elevated rounded p-2">
                            <span className="text-os-muted">{act.timestamp.slice(0, 10)} </span>
                            {act.content_preview}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Related Entities */}
                  {data.related_entities.length > 0 && (
                    <div>
                      <h3 className="text-2xs text-os-subtle uppercase tracking-wider mb-2">
                        相关实体 ({data.related_entities.length})
                      </h3>
                      <div className="flex flex-wrap gap-1.5">
                        {data.related_entities.map((e) => (
                          <span key={e.name} className="text-2xs px-2 py-1 rounded-full bg-os-elevated text-os-subtle border border-os-border/30">
                            {e.name}
                            <span className="text-os-muted ml-1">×{e.co_count}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Related Memories */}
                  {data.related_memories.length > 0 && (
                    <div>
                      <h3 className="text-2xs text-os-subtle uppercase tracking-wider mb-2">
                        相关记忆 ({data.related_memories.length})
                      </h3>
                      <div className="space-y-2">
                        {data.related_memories.slice(0, 10).map((mem) => (
                          <div key={mem.id} className="text-xs text-os-text-high bg-os-elevated rounded p-2.5">
                            <p className="line-clamp-3 leading-relaxed">{mem.content_preview}</p>
                            <div className="flex items-center gap-2 mt-1.5 text-2xs text-os-muted">
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
                <p className="text-xs text-os-muted text-center py-8">加载失败</p>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

// ── Main Page ──

export default function GraphPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [entityFilter, setEntityFilter] = useState("");
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const [stats, setStats] = useState<GraphData["stats"] | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["graph", entityFilter],
    queryFn: () => api.graph.get({
      entity_type: entityFilter || undefined,
      limit: 300,
    }),
    refetchInterval: 60000,
  });

  // ── Build / update vis-network ──
  const buildGraph = useCallback((graphData: GraphData) => {
    if (!containerRef.current) return;
    const container = containerRef.current;

    // Destroy previous instance
    if (networkRef.current) {
      networkRef.current.destroy();
      networkRef.current = null;
    }

    if (!graphData.nodes.length) return;

    // Assign colors to groups
    const groupColorMap: Record<string, string> = {};
    let gi = 0;
    const uniqueGroups = [...new Set(graphData.nodes.map((n) => n.group).filter(Boolean))];
    for (const g of uniqueGroups) {
      groupColorMap[g] = GROUP_COLORS[gi % GROUP_COLORS.length];
      gi++;
    }

    const nodes = new DataSet(
      graphData.nodes.map((n) => ({
        id: n.id,
        label: n.label.length > 20 ? n.label.slice(0, 20) + "..." : n.label,
        title: `<b>${n.label}</b><br/>类型: ${n.type}<br/>提及: ${n.memory_count}<br/>重要性: ${n.importance}`,
        group: n.group || n.type,
        value: Math.max(n.importance, 3) + Math.min(n.memory_count, 10),
        color: {
          background: NODE_COLORS[n.type] || groupColorMap[n.group] || "#818CF8",
          border: "#27272A",
          highlight: { background: NODE_COLORS[n.type] || "#818CF8", border: "#818CF8" },
          hover: { background: NODE_COLORS[n.type] || "#818CF8", border: "#A5B4FC" },
        },
        font: { color: "#E4E4E7", size: 11, face: "Inter, sans-serif" },
        borderWidth: 1.5,
        shape: n.type === "concept" ? "diamond" : n.type === "memory" ? "box" : "dot",
        size: 12 + Math.min(n.memory_count * 2, 40),
      })) as any
    );

    const edges = new DataSet(
      graphData.edges.map((e) => ({
        from: e.source,
        to: e.target,
        label: e.relation === "co_occurrence" ? "" : e.relation.slice(0, 6),
        title: `${e.relation} (权重: ${e.weight})`,
        value: e.weight,
        color: {
          color: e.relation === "co_occurrence" ? "#3F3F4660" : "#52525B80",
          highlight: "#818CF8",
          hover: "#A5B4FC",
        },
        width: Math.max(e.weight * 0.7, 0.5),
        smooth: { type: "continuous" as const },
        font: { color: "#52525B", size: 8, strokeWidth: 0 },
      })) as any
    );

    const network = new Network(container, { nodes, edges } as any, {
      physics: {
        solver: "forceAtlas2Based",
        forceAtlas2Based: {
          gravitationalConstant: -50,
          centralGravity: 0.01,
          springLength: 120,
          springConstant: 0.08,
        },
        stabilization: { iterations: 100 },
      },
      interaction: {
        hover: true,
        tooltipDelay: 200,
        zoomView: true,
        dragView: true,
      },
      nodes: {
        scaling: { min: 8, max: 50 },
      },
      edges: {
        scaling: { min: 0.3, max: 5 },
      },
      layout: {
        improvedLayout: true,
      },
    });

    // Click handler → show entity detail
    network.on("click", (params) => {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0] as string;
        const node = graphData.nodes.find((n) => n.id === nodeId);
        if (node?.type === "entity") {
          setSelectedEntity(node.label);
        }
      }
    });

    networkRef.current = network;
    setStats(graphData.stats);
  }, []);

  useEffect(() => {
    if (data) buildGraph(data);
  }, [data, buildGraph]);

  // Resize handler
  useEffect(() => {
    const onResize = () => {
      if (networkRef.current) {
        networkRef.current.redraw();
      }
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // Cleanup
  useEffect(() => {
    return () => {
      if (networkRef.current) {
        networkRef.current.destroy();
        networkRef.current = null;
      }
    };
  }, []);

  // ── Search ──
  const handleSearch = useCallback(() => {
    if (!networkRef.current || !searchTerm.trim()) return;
    // Find nodes matching search term
    const allNodes = (networkRef.current as any).body.data.nodes.get();
    const matchIds = allNodes
      .filter((n: any) =>
        (n.label || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
        (n.title || "").toLowerCase().includes(searchTerm.toLowerCase())
      )
      .map((n: any) => n.id);

    if (matchIds.length > 0) {
      // Highlight and focus on first match
      networkRef.current.selectNodes(matchIds, false);
      networkRef.current.focus(matchIds[0], { scale: 1.5, animation: true });
      setSelectedEntity(
        allNodes.find((n: any) => n.id === matchIds[0])?.label || null
      );
    }
  }, [searchTerm]);

  // ── Zoom helpers ──
  const zoomIn = () => networkRef.current?.moveTo({ scale: (networkRef.current.getScale() || 1) * 1.3 });
  const zoomOut = () => networkRef.current?.moveTo({ scale: (networkRef.current.getScale() || 1) * 0.7 });
  const resetView = () => {
    if (networkRef.current) {
      networkRef.current.fit({ animation: { duration: 500, easingFunction: "easeInOutQuad" } });
    }
  };

  const entityTypeOptions = ["", "person", "tech", "org", "topic", "location"];

  return (
    <PageTransition>
      <div className="p-6 space-y-4 max-w-[1440px] mx-auto h-[calc(100vh-4rem)] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between shrink-0">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight">知识图谱</h1>
            <p className="text-xs text-os-subtle mt-0.5">
              {stats
                ? `${stats.node_count} 节点 · ${stats.edge_count} 关系`
                : "加载中..."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* Zoom controls */}
            <button onClick={zoomIn} className="p-1.5 rounded hover:bg-os-elevated text-os-subtle hover:text-os-text" title="放大">
              <ZoomIn size={14} />
            </button>
            <button onClick={zoomOut} className="p-1.5 rounded hover:bg-os-elevated text-os-subtle hover:text-os-text" title="缩小">
              <ZoomOut size={14} />
            </button>
            <button onClick={resetView} className="p-1.5 rounded hover:bg-os-elevated text-os-subtle hover:text-os-text" title="重置">
              <RotateCcw size={14} />
            </button>

            {/* Entity type filter */}
            <select
              value={entityFilter}
              onChange={(e) => setEntityFilter(e.target.value)}
              className="h-7 px-2 rounded bg-os-surface border border-os-border text-2xs text-os-text-high focus:outline-none focus:border-os-accent"
            >
              <option value="">全部实体类型</option>
              {entityTypeOptions.filter(Boolean).map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>

            {/* Search */}
            <div className="relative">
              <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-os-muted" />
              <input
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                placeholder="搜索实体..."
                className="w-40 h-7 pl-7 pr-2 bg-os-surface border border-os-border rounded text-2xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent"
              />
            </div>
          </div>
        </div>

        {/* Stats cards */}
        {stats && (
          <div className="flex items-center gap-4 shrink-0 text-2xs">
            <div className="flex items-center gap-1.5">
              <Brain size={12} className="text-indigo-400" />
              <span className="text-os-subtle">实体节点</span>
              <span className="font-mono text-os-text-high">{stats.entity_nodes || 0}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <GitGraph size={12} className="text-emerald-400" />
              <span className="text-os-subtle">概念节点</span>
              <span className="font-mono text-os-text-high">{stats.concept_nodes || 0}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Activity size={12} className="text-amber-400" />
              <span className="text-os-subtle">关系边</span>
              <span className="font-mono text-os-text-high">{stats.edge_count || 0}</span>
            </div>
            {stats.top_entities && stats.top_entities.length > 0 && (
              <>
                <span className="w-px h-3 bg-os-border" />
                <span className="text-os-muted">Top:</span>
                {stats.top_entities.slice(0, 5).map((name, i) => (
                  <button
                    key={name}
                    onClick={() => setSelectedEntity(name)}
                    className="px-1.5 py-0.5 rounded bg-os-elevated text-indigo-400/80 hover:text-indigo-400 transition-colors"
                  >
                    {name}
                  </button>
                ))}
              </>
            )}
          </div>
        )}

        {/* Graph Canvas */}
        <div className="flex-1 min-h-0 relative">
          {isLoading ? (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="space-y-3 text-center">
                <GitGraph size={48} className="text-os-muted mx-auto animate-pulse" />
                <p className="text-xs text-os-muted">加载图谱数据...</p>
              </div>
            </div>
          ) : !data || data.nodes.length === 0 ? (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center space-y-2">
                <GitGraph size={48} className="text-os-muted mx-auto opacity-30" />
                <p className="text-xs text-os-muted">暂无图谱数据</p>
                <p className="text-2xs text-os-muted">开始记录带有实体的记忆后，图谱将自动生成</p>
              </div>
            </div>
          ) : null}
          <div
            ref={containerRef}
            className="w-full h-full rounded-lg border border-os-border bg-os-surface"
            style={{ minHeight: 400 }}
          />
        </div>

        {/* Entity Detail Drawer */}
        <EntityDrawer
          entityName={selectedEntity}
          onClose={() => setSelectedEntity(null)}
        />
      </div>
    </PageTransition>
  );
}
