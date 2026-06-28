/**
 * 知维 OS 因果图引擎 — UI 接入 Hook
 * Zhiwei OS Causal Graph Engine — UI Hook
 *
 * 内部流程：
 *   eventBus.replay(trace_id) → causalGraphEngine.buildGraph() → return nodes + edges
 *
 * 核心 Hook：
 * - useCausalGraph(trace_id)        构建完整因果图 + 关键路径（图视图主入口）
 * - useCausalSubgraph(event_id, d)  获取子图（UI 节点展开用）
 * - useCriticalPath(trace_id)       获取关键路径（runtime → governance → memory）
 * - useGraphProjection(params)      Event Projection Layer 投影
 * - useTopImpactNodes(trace_id, n) 高影响节点 Top N
 */

import { useEffect, useState, useRef, useCallback } from "react";
import { causalKernel } from "@/lib/event-bus/causal-kernel";
import { causalGraphEngine } from "@/lib/event-bus/causal-graph-engine";
import type {
  CausalGraph,
  CausalGraphNode,
  CausalGraphEdge,
  CriticalPath,
  ProjectionParams,
  ProjectionResult,
} from "@/types/event-bus";

// ═══════════════════════════════════════════════════════════════
// useCausalGraph — 因果图主 Hook
// ═══════════════════════════════════════════════════════════════

export interface CausalGraphData {
  /** 节点列表（按时间排序） */
  nodes: CausalGraphNode[];
  /** 边列表 */
  edges: CausalGraphEdge[];
  /** 图统计 */
  stats: CausalGraph["stats"] | null;
  /** 关键路径（runtime → governance → memory） */
  criticalPath: CriticalPath | null;
  /** 根节点（无入边，Agent decision 优先） */
  roots: CausalGraphNode[];
  /** 叶节点（无出边，排除 observability overlay） */
  leaves: CausalGraphNode[];
  /** 是否正在构建 */
  isBuilding: boolean;
  /**
   * 水合凭据 — trace_id 对应的 build() 是否已至少完成一次
   * 用于区分「正在水合」与「合法空图」，不要用 nodes.length 反推 lifecycle
   */
  hydrated: boolean;
  /** 重新构建（手动触发） */
  rebuild: () => void;
}

/**
 * 构建完整因果图 — 图视图主入口
 *
 * 内部：
 *   1. causalKernel.replay(trace_id)  拉取 trace 所有事件
 *   2. causalGraphEngine.buildGraph() 构建图 + 应用规则 + 计算 impact
 *   3. causalGraphEngine.getCriticalPath() 找关键路径
 *   4. 订阅事件流，新事件到达时自动重建
 *
 * @param trace_id Trace ID（null 时不构建）
 */
export function useCausalGraph(trace_id: string | null): CausalGraphData {
  const [graph, setGraph] = useState<CausalGraph | null>(null);
  const [criticalPath, setCriticalPath] = useState<CriticalPath | null>(null);
  const [isBuilding, setIsBuilding] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const traceRef = useRef(trace_id);
  traceRef.current = trace_id;

  const build = useCallback(() => {
    const tid = traceRef.current;
    if (!tid) {
      setGraph(null);
      setCriticalPath(null);
      setHydrated(false);
      return;
    }
    setIsBuilding(true);
    // buildGraph 内部已调用 causalKernel.replay
    const g = causalGraphEngine.buildGraph(tid);
    setGraph(g);
    // 关键路径检测（会标记 edges.is_critical_path）
    const cp = g ? causalGraphEngine.getCriticalPath(tid) : null;
    setCriticalPath(cp);
    setIsBuilding(false);
    // 标记 lifecycle 完成 — 这是区分「正在水合」与「合法空图」的唯一凭据
    // 注意：g 可能为 null（trace 存在但无事件），此时 hydrated 仍应为 true
    setHydrated(true);
  }, []);

  useEffect(() => {
    // trace 切换时重置水合凭据，保证下一轮 build 期间 traceState 正确回到 hydrating
    setHydrated(false);
    build();

    if (!trace_id) return;

    // 订阅该 trace 的新事件，自动重建图
    const handle = causalKernel.subscribe({ trace_id }, () => {
      build();
    });

    return () => handle.unsubscribe();
  }, [trace_id, build]);

  // 派生：节点列表（按时间升序）、根节点、叶节点
  const nodes = graph
    ? Array.from(graph.nodes.values()).sort((a, b) => a.timestamp.localeCompare(b.timestamp))
    : [];
  const edges = graph ? graph.edges : [];
  const stats = graph ? graph.stats : null;
  const roots = graph ? causalGraphEngine.getRoots(graph) : [];
  const leaves = graph ? causalGraphEngine.getLeaves(graph) : [];

  return {
    nodes,
    edges,
    stats,
    criticalPath,
    roots,
    leaves,
    isBuilding,
    hydrated,
    rebuild: build,
  };
}

// ═══════════════════════════════════════════════════════════════
// useCausalSubgraph — 子图（节点展开用）
// ═══════════════════════════════════════════════════════════════

export interface CausalSubgraphData {
  nodes: CausalGraphNode[];
  edges: CausalGraphEdge[];
  stats: CausalGraph["stats"] | null;
  isBuilding: boolean;
}

/**
 * 获取以指定事件为中心的子图（UI 节点展开用）
 *
 * @param event_id 中心事件 ID（null 时不构建）
 * @param depth 展开深度（默认 3）
 */
export function useCausalSubgraph(
  event_id: string | null,
  depth = 3,
): CausalSubgraphData {
  const [subgraph, setSubgraph] = useState<CausalGraph | null>(null);
  const [isBuilding, setIsBuilding] = useState(false);
  const eventRef = useRef(event_id);
  eventRef.current = event_id;
  const depthRef = useRef(depth);
  depthRef.current = depth;

  useEffect(() => {
    const build = () => {
      const eid = eventRef.current;
      if (!eid) {
        setSubgraph(null);
        return;
      }
      setIsBuilding(true);
      const g = causalGraphEngine.getSubgraph(eid, depthRef.current);
      setSubgraph(g);
      setIsBuilding(false);
    };

    build();

    if (!event_id) return;

    // 监听事件流变化，自动重建子图
    const handle = causalKernel.subscribeAll(() => {
      build();
    });

    return () => handle.unsubscribe();
  }, [event_id, depth]);

  const nodes = subgraph
    ? Array.from(subgraph.nodes.values()).sort((a, b) => a.timestamp.localeCompare(b.timestamp))
    : [];
  const edges = subgraph ? subgraph.edges : [];
  const stats = subgraph ? subgraph.stats : null;

  return { nodes, edges, stats, isBuilding };
}

// ═══════════════════════════════════════════════════════════════
// useCriticalPath — 关键路径
// ═══════════════════════════════════════════════════════════════

/**
 * 获取 trace 的关键路径（runtime → governance → memory）
 * 用于 UI 红色高亮
 *
 * @param trace_id Trace ID
 */
export function useCriticalPath(trace_id: string | null): CriticalPath | null {
  const [path, setPath] = useState<CriticalPath | null>(null);

  useEffect(() => {
    if (!trace_id) {
      setPath(null);
      return;
    }

    const refresh = () => {
      setPath(causalGraphEngine.getCriticalPath(trace_id));
    };

    refresh();

    const handle = causalKernel.subscribe({ trace_id }, refresh);
    return () => handle.unsubscribe();
  }, [trace_id]);

  return path;
}

// ═══════════════════════════════════════════════════════════════
// useGraphProjection — Event Projection Layer
// ═══════════════════════════════════════════════════════════════

export interface GraphProjectionData {
  result: ProjectionResult | null;
  nodes: CausalGraphNode[];
  edges: CausalGraphEdge[];
  isProjecting: boolean;
  reproject: () => void;
}

/**
 * Event Projection Layer — 从全量事件流投影子图
 * 防止 UI flood，支持按 trace_id / source / severity / time_range 维度投影
 *
 * @param params 投影参数
 */
export function useGraphProjection(params: ProjectionParams | null): GraphProjectionData {
  const [result, setResult] = useState<ProjectionResult | null>(null);
  const [isProjecting, setIsProjecting] = useState(false);
  const paramsRef = useRef(params);
  paramsRef.current = params;

  const project = useCallback(() => {
    const p = paramsRef.current;
    if (!p) {
      setResult(null);
      return;
    }
    setIsProjecting(true);
    setResult(causalKernel.project(p));
    setIsProjecting(false);
  }, []);

  useEffect(() => {
    project();

    if (!params) return;

    // 监听事件流变化，自动重新投影
    const handle = causalKernel.subscribeAll(() => {
      project();
    });

    return () => handle.unsubscribe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params?.dimension, params?.trace_id, params?.source, params?.severity, params?.time_from, params?.time_to, params?.max_nodes, project]);

  const nodes = result
    ? Array.from(result.graph.nodes.values()).sort((a, b) => a.timestamp.localeCompare(b.timestamp))
    : [];
  const edges = result ? result.graph.edges : [];

  return {
    result,
    nodes,
    edges,
    isProjecting,
    reproject: project,
  };
}

// ═══════════════════════════════════════════════════════════════
// useTopImpactNodes — 高影响节点
// ═══════════════════════════════════════════════════════════════

/**
 * 获取 trace 中影响分值最高的 N 个节点
 * 用于 UI 高亮关键节点
 *
 * @param trace_id Trace ID
 * @param topN 返回节点数（默认 5）
 */
export function useTopImpactNodes(trace_id: string | null, topN = 5): CausalGraphNode[] {
  const [nodes, setNodes] = useState<CausalGraphNode[]>([]);

  useEffect(() => {
    if (!trace_id) {
      setNodes([]);
      return;
    }

    const refresh = () => {
      const g = causalGraphEngine.buildGraph(trace_id);
      if (!g) {
        setNodes([]);
        return;
      }
      setNodes(causalGraphEngine.getTopImpactNodes(g, topN));
    };

    refresh();

    const handle = causalKernel.subscribe({ trace_id }, refresh);
    return () => handle.unsubscribe();
  }, [trace_id, topN]);

  return nodes;
}
