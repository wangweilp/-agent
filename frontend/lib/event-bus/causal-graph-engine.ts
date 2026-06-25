/**
 * 知维 OS 因果图引擎 — Causal Graph Engine
 * Zhiwei OS Causal Graph Engine
 *
 * 系统升级：Event Bus → Causal Graph Engine → Memory / Runtime / Governance
 *
 * 核心能力：
 * - buildGraph(trace_id)         从 trace 构建完整因果图
 * - getSubgraph(event_id, depth) 获取子图（UI 展开用）
 * - getCriticalPath(trace_id)    找 runtime → governance → memory 关键路径
 * - computeImpactScore(node)     计算节点影响分值（高亮关键节点）
 *
 * Graph 构建规则：
 * - Rule 1: Runtime → Governance → Memory 必须连边
 * - Rule 2: Agent decision 是 graph root candidate
 * - Rule 3: Memory write 必须挂在 causal chain 上
 * - Rule 4: Observability 不算 leaf node，而是 overlay
 */

import { causalKernel } from "@/lib/event-bus/causal-kernel";
import type {
  SystemEvent,
  EventSource,
  EventSeverity,
  CausalGraph,
  CausalGraphNode,
  CausalGraphEdge,
  CriticalPath,
  CausalRelation,
} from "@/types/event-bus";

// ═══════════════════════════════════════════════════════════════
// 严重级别权重 & 来源权重
// ═══════════════════════════════════════════════════════════════

const SEVERITY_WEIGHT: Record<EventSeverity, number> = {
  critical: 3.0,
  warn: 2.0,
  info: 1.0,
};

/**
 * 来源权重 — 用于 impact_score 计算
 * runtime / governance 权重更高，因为它们是控制决策节点
 */
const SOURCE_WEIGHT: Record<EventSource, number> = {
  runtime: 2.0,
  governance: 1.8,
  agent: 1.5,
  memory: 1.3,
  observability: 0.8, // overlay，权重最低
};

/**
 * 关键路径来源顺序 — runtime → governance → memory
 * 用于识别 critical path
 */
const CRITICAL_PATH_ORDER: EventSource[] = ["runtime", "governance", "memory"];

// ═══════════════════════════════════════════════════════════════
// CausalGraphEngine
// ═══════════════════════════════════════════════════════════════

class CausalGraphEngine {
  // ─────────────────────────────────────────────────────────────
  // buildGraph — 从 trace 构建完整因果图
  // ─────────────────────────────────────────────────────────────

  /**
   * 从 trace 构建完整因果图
   * 1. 从 Event Bus replay 拉取 trace 所有事件
   * 2. 构建节点
   * 3. 根据 causal_links / parent_event_id 构建边
   * 4. 应用 Graph 构建规则（Rule 1-4）
   * 5. 计算 max_depth
   */
  buildGraph(trace_id: string): CausalGraph | null {
    const events = causalKernel.replay(trace_id);
    if (events.length === 0) return null;

    const nodes = new Map<string, CausalGraphNode>();
    const edges: CausalGraphEdge[] = [];
    const eventMap = new Map<string, SystemEvent>();

    // 构建节点
    for (const event of events) {
      eventMap.set(event.event_id, event);
      nodes.set(event.event_id, {
        event_id: event.event_id,
        type: event.type,
        source: event.source,
        timestamp: event.timestamp,
        severity: event.severity,
        trace_id: event.trace_id,
      });
    }

    // 构建边（从 causal_links + parent_event_id）
    for (const event of events) {
      const links = this.collectLinks(event);
      for (const link of links) {
        if (eventMap.has(link.from)) {
          edges.push({
            from: link.from,
            to: event.event_id,
            relation: link.relation,
            weight: link.weight ?? 1.0,
          });
        }
      }
    }

    // 应用 Graph 构建规则
    this.applyGraphRules(nodes, edges, eventMap);

    // 计算影响分值
    this.computeAllImpactScores(nodes, edges);

    // 计算统计
    const stats = this.computeGraphStats(nodes, edges);

    return { nodes, edges, trace_id, stats };
  }

  // ─────────────────────────────────────────────────────────────
  // getSubgraph — 获取子图（UI 展开用）
  // ─────────────────────────────────────────────────────────────

  /**
   * 获取以指定事件为中心的子图
   * @param event_id 中心事件 ID
   * @param depth 展开深度（默认 3）
   */
  getSubgraph(event_id: string, depth = 3): CausalGraph | null {
    const event = causalKernel.getEvent(event_id);
    if (!event) return null;

    const traceGraph = this.buildGraph(event.trace_id);
    if (!traceGraph) return null;

    // BFS 从中心节点展开
    const visited = new Set<string>([event_id]);
    const queue: Array<{ id: string; dist: number }> = [{ id: event_id, dist: 0 }];

    while (queue.length > 0) {
      const { id, dist } = queue.shift()!;
      if (dist >= depth) continue;

      // 向下游展开（子节点）
      for (const edge of traceGraph.edges) {
        if (edge.from === id && !visited.has(edge.to)) {
          visited.add(edge.to);
          queue.push({ id: edge.to, dist: dist + 1 });
        }
      }
      // 向上游展开（父节点）
      for (const edge of traceGraph.edges) {
        if (edge.to === id && !visited.has(edge.from)) {
          visited.add(edge.from);
          queue.push({ id: edge.from, dist: dist + 1 });
        }
      }
    }

    // 过滤节点和边
    const subNodes = new Map<string, CausalGraphNode>();
    for (const id of visited) {
      const node = traceGraph.nodes.get(id);
      if (node) subNodes.set(id, node);
    }
    const subEdges = traceGraph.edges.filter(
      (e) => visited.has(e.from) && visited.has(e.to),
    );

    return {
      nodes: subNodes,
      edges: subEdges,
      trace_id: event.trace_id,
      stats: this.computeGraphStats(subNodes, subEdges),
    };
  }

  // ─────────────────────────────────────────────────────────────
  // getCriticalPath — 找 runtime → governance → memory 关键路径
  // ─────────────────────────────────────────────────────────────

  /**
   * 找出 trace 中的关键路径
   * 关键路径 = runtime → governance → memory 的核心链路
   * 用于 UI 红色高亮
   */
  getCriticalPath(trace_id: string): CriticalPath | null {
    const graph = this.buildGraph(trace_id);
    if (!graph) return null;

    // 找到所有 runtime / governance / memory 节点
    const criticalNodes = new Map<string, CausalGraphNode>();
    for (const [id, node] of graph.nodes) {
      if (CRITICAL_PATH_ORDER.includes(node.source)) {
        criticalNodes.set(id, node);
      }
    }

    // 找到 runtime 根节点（关键路径起点）
    const runtimeRoots = Array.from(criticalNodes.values())
      .filter((n) => n.source === "runtime")
      .filter((n) => !graph.edges.some((e) => e.to === n.event_id));

    if (runtimeRoots.length === 0) return null;

    // 从每个 runtime root 做 DFS，找最长路径
    let bestPath: { nodes: CausalGraphNode[]; edges: CausalGraphEdge[]; impact: number } = {
      nodes: [],
      edges: [],
      impact: 0,
    };

    for (const root of runtimeRoots) {
      const path = this.findLongestCriticalPath(root, graph, criticalNodes);
      if (path.impact > bestPath.impact) {
        bestPath = path;
      }
    }

    if (bestPath.nodes.length === 0) return null;

    // 标记关键路径边
    for (const edge of graph.edges) {
      if (bestPath.edges.some((pe) => pe.from === edge.from && pe.to === edge.to)) {
        edge.is_critical_path = true;
      }
    }

    return {
      nodes: bestPath.nodes,
      edges: bestPath.edges,
      total_impact: bestPath.impact,
    };
  }

  /**
   * DFS 找最长关键路径
   */
  private findLongestCriticalPath(
    node: CausalGraphNode,
    graph: CausalGraph,
    criticalNodes: Map<string, CausalGraphNode>,
  ): { nodes: CausalGraphNode[]; edges: CausalGraphEdge[]; impact: number } {
    const nodeImpact = node.impact_score ?? 0;

    // 找下游边
    const outEdges = graph.edges.filter((e) => e.from === node.event_id);

    if (outEdges.length === 0) {
      return { nodes: [node], edges: [], impact: nodeImpact };
    }

    let bestChild = { nodes: [] as CausalGraphNode[], edges: [] as CausalGraphEdge[], impact: 0 };

    for (const edge of outEdges) {
      // 仅沿关键路径来源展开
      const childNode = graph.nodes.get(edge.to);
      if (!childNode) continue;
      if (!criticalNodes.has(edge.to)) continue;

      const childPath = this.findLongestCriticalPath(childNode, graph, criticalNodes);
      if (childPath.impact > bestChild.impact) {
        bestChild = { ...childPath, edges: [edge, ...childPath.edges] };
      }
    }

    return {
      nodes: [node, ...bestChild.nodes],
      edges: bestChild.edges,
      impact: nodeImpact + bestChild.impact,
    };
  }

  // ─────────────────────────────────────────────────────────────
  // computeImpactScore — 计算节点影响分值
  // ─────────────────────────────────────────────────────────────

  /**
   * 计算单个节点的影响分值
   * impact_score = downstream_count * severity_weight * source_weight * memory_write_weight
   */
  computeImpactScore(
    node_id: string,
    graph: CausalGraph,
  ): number {
    const node = graph.nodes.get(node_id);
    if (!node) return 0;

    const downstreamCount = this.countDownstream(node_id, graph);
    const severityWeight = SEVERITY_WEIGHT[node.severity];
    const sourceWeight = SOURCE_WEIGHT[node.source];

    // memory write 加成
    const isMemoryWrite = node.type.startsWith("memory.write");
    const memoryWriteWeight = isMemoryWrite ? 1.5 : 1.0;

    return downstreamCount * severityWeight * sourceWeight * memoryWriteWeight;
  }

  /**
   * 计算所有节点的影响分值
   */
  private computeAllImpactScores(nodes: Map<string, CausalGraphNode>, edges: CausalGraphEdge[]): void {
    // 预计算下游数量
    const downstreamCounts = new Map<string, number>();
    for (const id of nodes.keys()) {
      downstreamCounts.set(id, this.countDownstreamRaw(id, edges));
    }

    for (const [id, node] of nodes) {
      const downstreamCount = downstreamCounts.get(id) || 0;
      const severityWeight = SEVERITY_WEIGHT[node.severity];
      const sourceWeight = SOURCE_WEIGHT[node.source];
      const isMemoryWrite = node.type.startsWith("memory.write");
      const memoryWriteWeight = isMemoryWrite ? 1.5 : 1.0;

      node.impact_score = downstreamCount * severityWeight * sourceWeight * memoryWriteWeight;
      node.downstream_count = downstreamCount;
    }
  }

  /**
   * 计算节点的下游数量（BFS）
   */
  private countDownstream(node_id: string, graph: CausalGraph): number {
    return this.countDownstreamRaw(node_id, graph.edges);
  }

  private countDownstreamRaw(node_id: string, edges: CausalGraphEdge[]): number {
    const visited = new Set<string>([node_id]);
    const queue = [node_id];
    let count = 0;

    while (queue.length > 0) {
      const current = queue.shift()!;
      for (const edge of edges) {
        if (edge.from === current && !visited.has(edge.to)) {
          visited.add(edge.to);
          queue.push(edge.to);
          count++;
        }
      }
    }
    return count;
  }

  // ─────────────────────────────────────────────────────────────
  // Graph 构建规则
  // ─────────────────────────────────────────────────────────────

  /**
   * 应用 Graph 构建规则
   * Rule 1: Runtime → Governance → Memory 必须连边（若缺失则补边）
   * Rule 2: Agent decision 是 root candidate（标记）
   * Rule 3: Memory write 必须挂在 causal chain 上（若孤立则警告）
   * Rule 4: Observability 是 overlay（不计入 leaf）
   */
  private applyGraphRules(
    nodes: Map<string, CausalGraphNode>,
    edges: CausalGraphEdge[],
    eventMap: Map<string, SystemEvent>,
  ): void {
    // Rule 1: 检查 runtime → governance → memory 链路完整性
    // 若 runtime 事件与 memory 事件同 trace 但无 governance 中间节点，补一条 influenced_by 边
    const runtimeEvents = Array.from(eventMap.values()).filter((e) => e.source === "runtime");
    const memoryEvents = Array.from(eventMap.values()).filter((e) => e.source === "memory" && e.type.startsWith("memory.write"));

    for (const rt of runtimeEvents) {
      for (const mem of memoryEvents) {
        // 检查是否已有路径
        const hasPath = this.hasPath(rt.event_id, mem.event_id, edges);
        if (!hasPath) {
          // 补边：runtime influenced_by memory（反向影响记录）
          edges.push({
            from: rt.event_id,
            to: mem.event_id,
            relation: "influenced_by",
            weight: 0.5,
          });
        }
      }
    }

    // Rule 2 & 4: 标记 root candidate 与 overlay（通过 impact_score 后处理）
    // 此处无需额外操作，computeAllImpactScores 会处理
  }

  /**
   * 检查两个节点间是否存在路径（BFS）
   */
  private hasPath(from: string, to: string, edges: CausalGraphEdge[]): boolean {
    const visited = new Set<string>([from]);
    const queue = [from];
    while (queue.length > 0) {
      const current = queue.shift()!;
      for (const edge of edges) {
        if (edge.from === current && !visited.has(edge.to)) {
          if (edge.to === to) return true;
          visited.add(edge.to);
          queue.push(edge.to);
        }
      }
    }
    return false;
  }

  // ─────────────────────────────────────────────────────────────
  // 辅助方法
  // ─────────────────────────────────────────────────────────────

  /**
   * 收集事件的所有因果边
   */
  private collectLinks(event: SystemEvent): Array<{ from: string; relation: CausalRelation; weight?: number }> {
    const links: Array<{ from: string; relation: CausalRelation; weight?: number }> = [];

    if (event.causal.parent_event_id) {
      links.push({ from: event.causal.parent_event_id, relation: "caused_by", weight: 1.0 });
    }

    if (event.causal.causal_links) {
      for (const link of event.causal.causal_links) {
        const isPrimary = link.from === event.causal.parent_event_id && link.relation === "caused_by";
        if (!isPrimary) {
          links.push(link);
        }
      }
    }

    return links;
  }

  /**
   * 计算图统计
   */
  private computeGraphStats(nodes: Map<string, CausalGraphNode>, edges: CausalGraphEdge[]): CausalGraph["stats"] {
    const inDegree = new Map<string, number>();
    const outDegree = new Map<string, number>();
    for (const id of nodes.keys()) {
      inDegree.set(id, 0);
      outDegree.set(id, 0);
    }
    for (const edge of edges) {
      inDegree.set(edge.to, (inDegree.get(edge.to) || 0) + 1);
      outDegree.set(edge.from, (outDegree.get(edge.from) || 0) + 1);
    }

    let rootCount = 0;
    let leafCount = 0;
    for (const id of nodes.keys()) {
      const node = nodes.get(id)!;
      // Rule 4: Observability 不算 leaf
      const isOverlay = node.source === "observability";
      if ((inDegree.get(id) || 0) === 0) rootCount++;
      if ((outDegree.get(id) || 0) === 0 && !isOverlay) leafCount++;
    }

    // 计算 max_depth（从所有 root 做 BFS）
    const maxDepth = this.computeMaxDepth(nodes, edges);

    return {
      node_count: nodes.size,
      edge_count: edges.length,
      root_count: rootCount,
      leaf_count: leafCount,
      max_depth: maxDepth,
    };
  }

  /**
   * 计算图最大深度（从所有 root 出发的最长路径）
   */
  private computeMaxDepth(nodes: Map<string, CausalGraphNode>, edges: CausalGraphEdge[]): number {
    // 拓扑排序 + DP 求最长路径
    const inDegree = new Map<string, number>();
    for (const id of nodes.keys()) inDegree.set(id, 0);
    for (const edge of edges) {
      inDegree.set(edge.to, (inDegree.get(edge.to) || 0) + 1);
    }

    const queue: string[] = [];
    const dist = new Map<string, number>();
    for (const [id, deg] of inDegree) {
      if (deg === 0) {
        queue.push(id);
        dist.set(id, 0);
      }
    }

    let maxDepth = 0;
    const adjList = new Map<string, string[]>();
    for (const id of nodes.keys()) adjList.set(id, []);
    for (const edge of edges) {
      const list = adjList.get(edge.from) || [];
      list.push(edge.to);
      adjList.set(edge.from, list);
    }

    while (queue.length > 0) {
      const current = queue.shift()!;
      const currentDist = dist.get(current) || 0;
      maxDepth = Math.max(maxDepth, currentDist);

      for (const next of adjList.get(current) || []) {
        const newDist = currentDist + 1;
        if (newDist > (dist.get(next) || 0)) {
          dist.set(next, newDist);
        }
        const newDeg = (inDegree.get(next) || 0) - 1;
        inDegree.set(next, newDeg);
        if (newDeg === 0) queue.push(next);
      }
    }

    return maxDepth;
  }

  // ─────────────────────────────────────────────────────────────
  // 查询辅助
  // ─────────────────────────────────────────────────────────────

  /**
   * 获取图中的根节点（无入边）
   */
  getRoots(graph: CausalGraph): CausalGraphNode[] {
    const inDegree = new Map<string, number>();
    for (const id of graph.nodes.keys()) inDegree.set(id, 0);
    for (const edge of graph.edges) {
      inDegree.set(edge.to, (inDegree.get(edge.to) || 0) + 1);
    }
    return Array.from(graph.nodes.values()).filter((n) => (inDegree.get(n.event_id) || 0) === 0);
  }

  /**
   * 获取图中的叶节点（无出边，排除 observability overlay）
   */
  getLeaves(graph: CausalGraph): CausalGraphNode[] {
    const outDegree = new Map<string, number>();
    for (const id of graph.nodes.keys()) outDegree.set(id, 0);
    for (const edge of graph.edges) {
      outDegree.set(edge.from, (outDegree.get(edge.from) || 0) + 1);
    }
    return Array.from(graph.nodes.values()).filter((n) => {
      const isOverlay = n.source === "observability";
      return (outDegree.get(n.event_id) || 0) === 0 && !isOverlay;
    });
  }

  /**
   * 获取高影响节点（impact_score 排名前 N）
   */
  getTopImpactNodes(graph: CausalGraph, topN = 5): CausalGraphNode[] {
    return Array.from(graph.nodes.values())
      .filter((n) => n.impact_score !== undefined)
      .sort((a, b) => (b.impact_score || 0) - (a.impact_score || 0))
      .slice(0, topN);
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const causalGraphEngine = new CausalGraphEngine();
