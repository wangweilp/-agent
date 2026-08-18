"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  Brain,
  GitGraph,
  Maximize,
  Network as NetworkIcon,
  RotateCcw,
  Search,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { DataSet } from "vis-data";
import { Network, type Data, type Edge, type Node } from "vis-network";
import { api } from "@/services/api";
import { PageTransition } from "@/components/animations/page-transition";
import { Skeleton } from "@/components/animations/skeleton";
import { KnowledgeGraphBackground } from "@/components/graph/KnowledgeGraphBackground";
import {
  EmptyState,
  OsBadge,
  OsButton,
  OsCard,
  OsInput,
  PageHeader,
  PageShell,
  RankRow,
  StatusBadge,
  Toolbar,
} from "@/components/ui/os";
import { cn, formatDate, importanceColor } from "@/lib/utils";
import type { EntityDetail, GraphData, GraphNode } from "@/types";

const NODE_SIZE_SCALE = 0.58;

const NODE_COLORS: Record<GraphNode["type"], string> = {
  entity: "#7C8CF8",
  concept: "#3DBE8B",
  memory: "#9F8CF2",
  image: "#D99A1E",
};

const NODE_SOFT: Record<GraphNode["type"], string> = {
  entity: "rgba(124,140,248,0.14)",
  concept: "rgba(61,190,139,0.14)",
  memory: "rgba(159,140,242,0.13)",
  image: "rgba(217,154,30,0.14)",
};

const GROUP_COLORS = ["#7C8CF8", "#3DBE8B", "#D99A1E", "#D96565", "#9F8CF2", "#2CA8C2"];

const ENTITY_TYPE_OPTIONS = ["", "person", "tech", "org", "topic", "location"];

function nodeColor(node: GraphNode, groupColorMap: Record<string, string>) {
  return NODE_COLORS[node.type] || groupColorMap[node.group] || "#7C8CF8";
}

function entityTypeLabel(type: string) {
  const labels: Record<string, string> = {
    person: "人物",
    tech: "技术",
    org: "组织",
    topic: "主题",
    location: "地点",
  };
  return labels[type] || type || "全部实体类型";
}

function entityVariant(type?: string) {
  if (type === "person") return "primary";
  if (type === "tech") return "info";
  if (type === "org") return "success";
  if (type === "location") return "warning";
  return "muted";
}

function EntityDrawer({
  entityName,
  onClose,
}: {
  entityName: string | null;
  onClose: () => void;
}) {
  const { data, isLoading } = useQuery<EntityDetail>({
    queryKey: ["graph-entity", entityName],
    queryFn: () => api.graph.entity(entityName!),
    enabled: !!entityName,
  });

  return (
    <AnimatePresence>
      {entityName && (
        <>
          <motion.button
            type="button"
            aria-label="关闭实体详情"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-slate-950/20 backdrop-blur-[2px]"
            onClick={onClose}
          />
          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="fixed bottom-0 right-0 top-0 z-50 w-full max-w-md overflow-y-auto border-l border-os-border bg-os-panel shadow-os-floating"
          >
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-os-border bg-os-panel/95 px-5 py-4 backdrop-blur">
              <div className="min-w-0">
                <p className="text-xs font-medium uppercase tracking-[0.08em] text-os-subtle">实体检查器</p>
                <h2 className="truncate text-base font-semibold text-os-text-high">{entityName}</h2>
              </div>
              <OsButton type="button" size="iconSm" variant="ghost" aria-label="关闭实体详情" onClick={onClose}>
                <X size={16} />
              </OsButton>
            </div>

            <div className="space-y-4 p-5">
              {isLoading ? (
                <div className="space-y-3">
                  <Skeleton className="h-10 rounded-xl" />
                  <Skeleton className="h-28 rounded-2xl" />
                  <Skeleton className="h-28 rounded-2xl" />
                </div>
              ) : data ? (
                <>
                  <OsCard padding="md">
                    <div className="flex flex-wrap items-center gap-2">
                      <OsBadge variant={entityVariant(data.entity_type)}>{entityTypeLabel(data.entity_type)}</OsBadge>
                      <OsBadge variant="muted">提及 {data.mention_count} 次</OsBadge>
                      {data.first_seen && <OsBadge variant="muted">首次 {formatDate(data.first_seen)}</OsBadge>}
                    </div>
                  </OsCard>

                  <OsCard padding="md">
                    <div className="mb-3 flex items-center justify-between gap-2">
                      <h3 className="text-sm font-semibold text-os-text-high">最近活动</h3>
                      <OsBadge variant="muted">{data.recent_activity.length} 条</OsBadge>
                    </div>
                    {data.recent_activity.length > 0 ? (
                      <div className="space-y-2">
                        {data.recent_activity.slice(0, 6).map((act) => (
                          <div key={act.id} className="rounded-xl border border-os-border bg-os-surface-tinted p-3">
                            <p className="line-clamp-2 text-sm leading-6 text-os-text">{act.content_preview}</p>
                            <p className="mt-1 text-xs text-os-subtle">{formatDate(act.timestamp)}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <EmptyState title="暂无最近活动" description="实体有统计数据，但近期没有新的记忆活动。" className="min-h-[180px]" />
                    )}
                  </OsCard>

                  <OsCard padding="md">
                    <div className="mb-3 flex items-center justify-between gap-2">
                      <h3 className="text-sm font-semibold text-os-text-high">相关实体</h3>
                      <OsBadge variant="muted">{data.related_entities.length} 个</OsBadge>
                    </div>
                    {data.related_entities.length > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {data.related_entities.map((entity) => (
                          <OsBadge key={entity.name} variant="default">
                            {entity.name} x{entity.co_count}
                          </OsBadge>
                        ))}
                      </div>
                    ) : (
                      <EmptyState title="暂无相关实体" description="还没有形成稳定的共现关系。" className="min-h-[160px]" />
                    )}
                  </OsCard>

                  <OsCard padding="md">
                    <div className="mb-3 flex items-center justify-between gap-2">
                      <h3 className="text-sm font-semibold text-os-text-high">相关记忆</h3>
                      <OsBadge variant="muted">{data.related_memories.length} 条</OsBadge>
                    </div>
                    {data.related_memories.length > 0 ? (
                      <div className="space-y-2">
                        {data.related_memories.slice(0, 10).map((memory) => (
                          <div key={memory.id} className="rounded-xl border border-os-border bg-white p-3">
                            <p className="line-clamp-3 text-sm leading-6 text-os-text">{memory.content_preview}</p>
                            <div className="mt-2 flex flex-wrap items-center gap-2">
                              <span className="text-xs text-os-subtle">{formatDate(memory.timestamp)}</span>
                              <span
                                className={cn(
                                  "font-mono text-xs",
                                  importanceColor(memory.importance)
                                    .replace("text-emerald-400", "text-os-success")
                                    .replace("text-amber-400", "text-os-warning")
                                    .replace("text-zinc-500", "text-os-subtle"),
                                )}
                              >
                                重要度 {memory.importance}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <EmptyState title="暂无相关记忆" description="后续写入更多上下文后会自动补齐。" className="min-h-[180px]" />
                    )}
                  </OsCard>
                </>
              ) : (
                <EmptyState title="加载失败" description="实体详情暂时不可用，请稍后重试。" />
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function buildVisData(graphData: GraphData): Data {
  const groupColorMap: Record<string, string> = {};
  const groups = [...new Set(graphData.nodes.map((node) => node.group).filter(Boolean))];
  groups.forEach((group, index) => {
    groupColorMap[group] = GROUP_COLORS[index % GROUP_COLORS.length];
  });

  const nodes = new DataSet<Node>(
    graphData.nodes.map((node) => {
      const color = nodeColor(node, groupColorMap);
      return {
        id: node.id,
        label: node.label.length > 22 ? `${node.label.slice(0, 22)}...` : node.label,
        title: `${node.label}\n${node.type} | 提及 ${node.memory_count} | 重要度 ${node.importance}`,
        group: node.group || node.type,
        value: (Math.max(node.importance, 3) + Math.min(node.memory_count, 10)) * NODE_SIZE_SCALE,
        color: {
          background: NODE_SOFT[node.type] || "rgba(124,140,248,0.14)",
          border: color,
          highlight: { background: "rgba(34,211,238,0.16)", border: "#22A8C2" },
          hover: { background: "rgba(99,102,241,0.12)", border: color },
        },
        font: { color: "#334155", size: 10, face: "Inter, ui-sans-serif, system-ui" },
        borderWidth: 1.4,
        shape: node.type === "concept" ? "diamond" : node.type === "memory" ? "box" : "dot",
        size: (10 + Math.min(node.memory_count * 1.8, 32)) * NODE_SIZE_SCALE,
        shadow: { enabled: true, color: "rgba(15,23,42,0.08)", size: 8 },
      };
    }),
  );

  const edges = new DataSet<Edge>(
    graphData.edges.map((edge) => ({
      id: `${edge.source}__${edge.target}__${edge.relation}`,
      from: edge.source,
      to: edge.target,
      label: edge.relation === "co_occurrence" ? "" : edge.relation.slice(0, 7),
      title: `${edge.relation} | 权重 ${edge.weight}`,
      value: edge.weight,
      color: {
        color: edge.relation === "co_occurrence" ? "rgba(148,163,184,0.24)" : "rgba(99,102,241,0.28)",
        highlight: "#7C8CF8",
        hover: "#7C8CF8",
      },
      width: Math.max(edge.weight * 0.5, 0.45),
      smooth: { enabled: true, type: "continuous", roundness: 0.08 },
      font: { color: "rgba(100,116,139,0.5)", size: 8, strokeWidth: 0 },
      arrows: { to: { enabled: false } },
    })),
  );

  return { nodes, edges };
}

export default function GraphPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasWrapperRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const graphDataRef = useRef<GraphData | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [entityFilter, setEntityFilter] = useState("");
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [mousePos, setMousePos] = useState({ x: 0.5, y: 0.5 });

  const { data, isLoading, isError } = useQuery({
    queryKey: ["graph", entityFilter],
    queryFn: () =>
      api.graph.get({
        entity_type: entityFilter || undefined,
        limit: 300,
      }),
    refetchInterval: 60000,
  });

  const buildGraph = useCallback((graphData: GraphData) => {
    if (!containerRef.current) return;

    networkRef.current?.destroy();
    networkRef.current = null;
    graphDataRef.current = graphData;
    setSelectedNode(null);

    if (!graphData.nodes.length) return;

    const network = new Network(containerRef.current, buildVisData(graphData), {
      autoResize: true,
      physics: {
        solver: "forceAtlas2Based",
        forceAtlas2Based: {
          gravitationalConstant: -50,
          centralGravity: 0.009,
          springLength: 132,
          springConstant: 0.06,
          damping: 0.36,
        },
        stabilization: { iterations: 90, updateInterval: 25 },
      },
      interaction: {
        hover: true,
        tooltipDelay: 160,
        zoomView: true,
        dragView: true,
        navigationButtons: false,
      },
      nodes: {
        borderWidthSelected: 3,
        scaling: { min: 4 * NODE_SIZE_SCALE, max: 28 * NODE_SIZE_SCALE },
      },
      edges: {
        smooth: { enabled: true, type: "continuous", roundness: 0.08 },
        scaling: { min: 0.25, max: 5 },
        selectionWidth: 1.8,
        hoverWidth: 1.4,
      },
      layout: { improvedLayout: true },
    });

    network.on("selectNode", (params) => {
      const id = params.nodes[0] as string | undefined;
      const node = graphData.nodes.find((item) => item.id === id) || null;
      setSelectedNode(node);
      if (node?.type === "entity") setSelectedEntity(node.label);
    });

    network.on("deselectNode", () => {
      setSelectedNode(null);
    });

    networkRef.current = network;
  }, []);

  useEffect(() => {
    if (data) buildGraph(data);
  }, [data, buildGraph]);

  useEffect(() => {
    const onResize = () => networkRef.current?.redraw();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(
    () => () => {
      networkRef.current?.destroy();
      networkRef.current = null;
    },
    [],
  );

  const handleSearch = useCallback(() => {
    const graphData = graphDataRef.current;
    const network = networkRef.current;
    const query = searchTerm.trim().toLowerCase();
    if (!graphData || !network || !query) return;

    const matches = graphData.nodes.filter((node) => node.label.toLowerCase().includes(query));
    if (!matches.length) return;

    network.selectNodes(matches.map((node) => node.id), false);
    network.focus(matches[0].id, { scale: 1.45, animation: { duration: 420, easingFunction: "easeInOutQuad" } });
    setSelectedNode(matches[0]);
    if (matches[0].type === "entity") setSelectedEntity(matches[0].label);
  }, [searchTerm]);

  const zoomIn = () => networkRef.current?.moveTo({ scale: (networkRef.current.getScale() || 1) * 1.25 });
  const zoomOut = () => networkRef.current?.moveTo({ scale: (networkRef.current.getScale() || 1) * 0.8 });
  const resetView = () => networkRef.current?.fit({ animation: { duration: 420, easingFunction: "easeInOutQuad" } });
  const clearSelection = () => {
    networkRef.current?.unselectAll();
    setSelectedNode(null);
  };

  const handleCanvasMouseMove = useCallback((e: React.MouseEvent) => {
    if (!canvasWrapperRef.current) return;
    const rect = canvasWrapperRef.current.getBoundingClientRect();
    setMousePos({ x: (e.clientX - rect.left) / rect.width, y: (e.clientY - rect.top) / rect.height });
  }, []);

  const parallaxIntensity = ((mousePos.x - 0.5) * 2 + (mousePos.y - 0.5) * 2) * 0.5;
  const stats = data?.stats;
  const topEntityCounts = stats?.top_entities_count || [];

  return (
    <PageTransition>
      <PageShell className="flex min-h-[calc(100vh-4rem)] flex-col !space-y-3 overflow-hidden">
        <PageHeader
          icon={GitGraph}
          title="知识图谱"
          subtitle={stats ? `${stats.node_count} 个节点 / ${stats.edge_count} 条关系。拖动画布探索实体、概念与记忆之间的连接。` : "正在加载图谱结构与实体关系。"}
          actions={
            <>
              <StatusBadge status={isError ? "warning" : isLoading ? "info" : "ready"}>
                {isError ? "图谱加载失败" : isLoading ? "同步中" : "图谱就绪"}
              </StatusBadge>
              <OsButton type="button" size="iconSm" variant="ghost" aria-label="放大图谱" onClick={zoomIn}>
                <ZoomIn size={15} />
              </OsButton>
              <OsButton type="button" size="iconSm" variant="ghost" aria-label="缩小图谱" onClick={zoomOut}>
                <ZoomOut size={15} />
              </OsButton>
              <OsButton type="button" size="iconSm" variant="ghost" aria-label="重置图谱视图" onClick={resetView}>
                <RotateCcw size={15} />
              </OsButton>
            </>
          }
        />

        <Toolbar>
          <select
            value={entityFilter}
            onChange={(e) => setEntityFilter(e.target.value)}
            aria-label="筛选实体类型"
            className="h-9 rounded-xl border border-os-border bg-white px-3 text-sm text-os-text-high outline-none focus:border-os-primary/35 focus:ring-2 focus:ring-os-primary/15"
          >
            {ENTITY_TYPE_OPTIONS.map((type) => (
              <option key={type || "all"} value={type}>
                {entityTypeLabel(type)}
              </option>
            ))}
          </select>

          <div className="relative min-w-0 flex-1 sm:max-w-xs">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-os-muted" />
            <OsInput
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="搜索实体..."
              className="w-full pl-9"
              aria-label="搜索实体"
            />
          </div>

          <OsButton type="button" size="md" variant="secondary" onClick={handleSearch}>
            <Search size={14} />
            搜索
          </OsButton>

          {selectedNode && (
            <OsButton type="button" size="md" variant="soft" onClick={clearSelection}>
              <X size={14} />
              取消聚焦
            </OsButton>
          )}

          <div className="ml-auto hidden items-center gap-2 lg:flex">
            <OsBadge variant="primary">
              <Brain size={12} />
              实体 {stats?.entity_nodes || 0}
            </OsBadge>
            <OsBadge variant="success">
              <GitGraph size={12} />
              概念 {stats?.concept_nodes || 0}
            </OsBadge>
            <OsBadge variant="warning">
              <Activity size={12} />
              关系 {stats?.edge_count || 0}
            </OsBadge>
          </div>
        </Toolbar>

        <div
          ref={canvasWrapperRef}
          onMouseMove={handleCanvasMouseMove}
          className="relative min-h-[420px] flex-1 overflow-hidden rounded-2xl border border-os-border bg-white shadow-os-elevated"
        >
          <KnowledgeGraphBackground intensity={parallaxIntensity} focusActive={!!selectedNode} />

          {isLoading ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center">
              <EmptyState icon={GitGraph} title="正在加载图谱" description="系统正在同步节点、关系与实体统计。" className="min-h-[260px] bg-white/80" />
            </div>
          ) : isError ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center">
              <EmptyState
                icon={GitGraph}
                title="图谱加载失败"
                description="暂时无法读取节点与关系，请检查网络连接后重试。"
                className="min-h-[260px] bg-white/80"
              />
            </div>
          ) : !data || data.nodes.length === 0 ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center">
              <EmptyState
                icon={GitGraph}
                title="暂无图谱数据"
                description="开始记录带有实体的记忆后，图谱会自动生成并显示关系网络。"
                className="min-h-[260px] bg-white/80"
              />
            </div>
          ) : null}

          <div className="absolute right-3 top-3 z-20 flex flex-col gap-1.5 rounded-2xl border border-os-border bg-white/92 p-1.5 shadow-os-floating backdrop-blur">
            <OsButton type="button" size="iconSm" variant="ghost" aria-label="放大图谱" onClick={zoomIn}>
              <ZoomIn size={15} />
            </OsButton>
            <OsButton type="button" size="iconSm" variant="ghost" aria-label="缩小图谱" onClick={zoomOut}>
              <ZoomOut size={15} />
            </OsButton>
            <OsButton type="button" size="iconSm" variant="ghost" aria-label="适应屏幕" onClick={resetView}>
              <Maximize size={15} />
            </OsButton>
            <div className="mx-1 h-px bg-os-border" />
            <OsButton type="button" size="iconSm" variant="ghost" aria-label="重新布局" onClick={resetView}>
              <NetworkIcon size={15} />
            </OsButton>
          </div>

          <AnimatePresence>
            {selectedNode && (
              <motion.div
                initial={{ opacity: 0, x: -16 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -16 }}
                transition={{ duration: 0.18 }}
                className="absolute left-3 top-3 z-20 w-[min(20rem,calc(100%-5.5rem))]"
              >
                <OsCard variant="inspector" padding="md">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <OsBadge variant={entityVariant(selectedNode.type)}>{entityTypeLabel(selectedNode.type)}</OsBadge>
                      <h2 className="mt-2 truncate text-sm font-semibold text-os-text-high">{selectedNode.label}</h2>
                    </div>
                    <OsButton type="button" size="iconSm" variant="ghost" aria-label="关闭节点检查器" onClick={clearSelection}>
                      <X size={14} />
                    </OsButton>
                  </div>

                  <div className="mt-4 space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-os-subtle">重要度</span>
                      <span className="font-mono font-semibold text-os-text-high">{selectedNode.importance ?? "暂无"}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-os-subtle">关联记忆</span>
                      <span className="font-mono font-semibold text-os-text-high">{selectedNode.memory_count ?? 0}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-os-subtle">分组</span>
                      <span className="max-w-[9rem] truncate font-mono text-xs text-os-text-high">{selectedNode.group || "默认"}</span>
                    </div>
                  </div>
                </OsCard>
              </motion.div>
            )}
          </AnimatePresence>

          {stats?.top_entities && stats.top_entities.length > 0 && (
            <div className="absolute bottom-3 left-3 z-20 hidden w-72 rounded-2xl border border-os-border bg-white/92 p-3 shadow-os-floating backdrop-blur lg:block">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-[0.08em] text-os-subtle">热门实体</p>
                <OsBadge variant="muted">{stats.top_entities.length}</OsBadge>
              </div>
              <div className="space-y-1">
                {stats.top_entities.slice(0, 5).map((name, index) => {
                  const max = Math.max(...topEntityCounts, 1);
                  const value = topEntityCounts[index] || 0;
                  return (
                    <RankRow
                      key={name}
                      rank={index + 1}
                      label={name}
                      value={value ? `${value}` : undefined}
                      percent={value ? Math.round((value / max) * 100) : undefined}
                      onClick={() => setSelectedEntity(name)}
                    />
                  );
                })}
              </div>
            </div>
          )}

          <div ref={containerRef} className="relative z-[2] h-full min-h-[420px] w-full" style={{ background: "transparent" }} />
        </div>

        <EntityDrawer entityName={selectedEntity} onClose={() => setSelectedEntity(null)} />
      </PageShell>
    </PageTransition>
  );
}
