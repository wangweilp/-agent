/**
 * 知维 OS Distributed Trace Correlator — 跨层关联器
 * Zhiwei OS Distributed Trace Correlator
 *
 * 关联规则：
 * - event_id → span_id           — 事件到 span 的映射
 * - snapshot_id → span_group     — 快照到 span 组的映射
 * - enforcement_loop_id → trace root — enforcement 到 trace 根的映射
 * - causal_chain → span DAG      — 因果链到 span DAG 的映射
 *
 * 输出：
 * TraceGraph {
 *   nodes: Span[]
 *   edges: SpanEdge[]
 *   root_spans
 *   critical_path
 * }
 */

import { observabilityStore } from "@/lib/observability/store";
import { causalKernel } from "@/lib/event-bus/causal-kernel";
import type { SystemEvent, CausalLink } from "@/types/event-bus";
import type {
  SystemTraceEvent,
  SpanEdge,
  TraceGraph,
  TraceStats,
  SpanEdgeType,
} from "@/lib/observability/types";

// ═══════════════════════════════════════════════════════════════
// TraceCorrelator — 跨层关联器
// ═══════════════════════════════════════════════════════════════

export class TraceCorrelator {
  /**
   * 构建 trace 图 — 主入口
   *
   * 步骤：
   * 1. 从 store 获取 trace 所有 span
   * 2. 从 causal kernel 获取事件因果链
   * 3. 合并构建 span DAG
   * 4. 识别根 span 和关键路径
   */
  async buildTraceGraph(trace_id: string): Promise<TraceGraph> {
    // 1. 获取所有 span
    const spans = await observabilityStore.getSpansByTraceId(trace_id);

    // 2. 获取所有边（已存储的）
    const edges = await observabilityStore.getEdgesByTraceId(trace_id);

    // 3. 补充因果边（从 causal chain 推导）
    const causalEdges = await this.deriveCausalEdges(trace_id, spans);
    const allEdges = this.mergeEdges(edges, causalEdges);

    // 4. 识别根 span（无 parent 的 span）
    const rootSpans = this.findRootSpans(spans);

    // 5. 计算关键路径（最长延迟路径）
    const criticalPath = this.computeCriticalPath(spans, allEdges);

    // 6. 统计
    const stats = this.computeStats(spans, allEdges);

    return {
      trace_id,
      nodes: spans,
      edges: allEdges,
      root_spans: rootSpans,
      critical_path: criticalPath,
      stats,
    };
  }

  /**
   * event_id → span_id 映射
   */
  async getSpanByEventId(event_id: string): Promise<SystemTraceEvent | null> {
    return observabilityStore.getSpanByEventId(event_id);
  }

  /**
   * snapshot_id → span_group 映射
   */
  async getSpansBySnapshotId(snapshot_id: string): Promise<SystemTraceEvent[]> {
    // 从所有 trace 中查找（需要全量扫描，因为 snapshot_id 不在索引中）
    const traceIds = await observabilityStore.getTraceIds();
    const result: SystemTraceEvent[] = [];

    for (const traceId of traceIds) {
      const spans = await observabilityStore.getSpansByTraceId(traceId);
      for (const span of spans) {
        if (span.snapshot_id === snapshot_id) {
          result.push(span);
        }
      }
    }

    return result;
  }

  /**
   * enforcement_loop_id → trace root 映射
   */
  async getSpansByEnforcementLoopId(enforcement_loop_id: string): Promise<SystemTraceEvent[]> {
    const traceIds = await observabilityStore.getTraceIds();
    const result: SystemTraceEvent[] = [];

    for (const traceId of traceIds) {
      const spans = await observabilityStore.getSpansByTraceId(traceId);
      for (const span of spans) {
        if (span.enforcement_loop_id === enforcement_loop_id) {
          result.push(span);
        }
      }
    }

    return result;
  }

  /**
   * causal_chain → span DAG 转换
   *
   * 将事件的因果链转换为 span 之间的边
   */
  async deriveCausalEdges(trace_id: string, spans: SystemTraceEvent[]): Promise<SpanEdge[]> {
    const events = causalKernel.replay(trace_id);
    const edges: SpanEdge[] = [];

    // 构建 event_id → span_id 映射
    const eventToSpan = new Map<string, string>();
    for (const span of spans) {
      if (span.event_id) {
        eventToSpan.set(span.event_id, span.span_id);
      }
    }

    // 遍历事件因果链
    for (const event of events) {
      const eventSpanId = eventToSpan.get(event.event_id);
      if (!eventSpanId) continue;

      // 主父关系
      if (event.causal.parent_event_id) {
        const parentSpanId = eventToSpan.get(event.causal.parent_event_id);
        if (parentSpanId) {
          edges.push({
            from: parentSpanId,
            to: eventSpanId,
            type: "causal_link",
            causal_relation: "caused_by",
            weight: 1.0,
          });
        }
      }

      // 多父因果边
      if (event.causal.causal_links) {
        for (const link of event.causal.causal_links) {
          const parentSpanId = eventToSpan.get(link.from);
          if (parentSpanId && parentSpanId !== eventSpanId) {
            // 避免重复
            const exists = edges.some(
              (e) => e.from === parentSpanId && e.to === eventSpanId && e.type === "causal_link",
            );
            if (!exists) {
              edges.push({
                from: parentSpanId,
                to: eventSpanId,
                type: "causal_link",
                causal_relation: link.relation,
                weight: link.weight ?? 1.0,
              });
            }
          }
        }
      }
    }

    // 补充 parent_child 边（span tree）
    for (const span of spans) {
      if (span.parent_span_id) {
        const exists = edges.some(
          (e) => e.from === span.parent_span_id && e.to === span.span_id && e.type === "parent_child",
        );
        if (!exists) {
          edges.push({
            from: span.parent_span_id,
            to: span.span_id,
            type: "parent_child",
            weight: 1.0,
          });
        }
      }
    }

    return edges;
  }

  /**
   * 记录边到 store
   */
  async recordEdge(edge: SpanEdge): Promise<void> {
    await observabilityStore.putEdge(edge);
  }

  /**
   * 记录多个边
   */
  async recordEdges(edges: SpanEdge[]): Promise<void> {
    for (const edge of edges) {
      await observabilityStore.putEdge(edge);
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 内部方法
  // ─────────────────────────────────────────────────────────────

  private mergeEdges(existing: SpanEdge[], derived: SpanEdge[]): SpanEdge[] {
    const seen = new Set<string>();
    const result: SpanEdge[] = [];

    for (const edge of [...existing, ...derived]) {
      const key = `${edge.from}->${edge.to}:${edge.type}`;
      if (!seen.has(key)) {
        seen.add(key);
        result.push(edge);
      }
    }

    return result;
  }

  private findRootSpans(spans: SystemTraceEvent[]): SystemTraceEvent[] {
    return spans.filter((s) => !s.parent_span_id);
  }

  /**
   * 计算关键路径 — 最长延迟路径（DFS）
   */
  private computeCriticalPath(spans: SystemTraceEvent[], edges: SpanEdge[]): string[] {
    if (spans.length === 0) return [];

    // 构建邻接表（仅 parent_child 和 causal_link 边）
    const adj = new Map<string, string[]>();
    for (const span of spans) {
      adj.set(span.span_id, []);
    }
    for (const edge of edges) {
      if (edge.type === "parent_child" || edge.type === "causal_link") {
        const list = adj.get(edge.from) || [];
        list.push(edge.to);
        adj.set(edge.from, list);
      }
    }

    // 找根 span
    const roots = this.findRootSpans(spans);
    if (roots.length === 0) return [];

    // DFS 找最长路径（按 duration_ms）
    const spanMap = new Map(spans.map((s) => [s.span_id, s]));
    let longestPath: string[] = [];
    let longestDuration = 0;

    const dfs = (currentId: string, path: string[], duration: number, visited: Set<string>) => {
      if (visited.has(currentId)) return; // 防环
      visited.add(currentId);

      const newPath = [...path, currentId];
      const span = spanMap.get(currentId);
      const newDuration = duration + (span?.duration_ms ?? 0);

      const children = adj.get(currentId) || [];
      if (children.length === 0) {
        // 叶子节点
        if (newDuration > longestDuration) {
          longestDuration = newDuration;
          longestPath = newPath;
        }
      } else {
        for (const child of children) {
          dfs(child, newPath, newDuration, new Set(visited));
        }
      }
    };

    for (const root of roots) {
      dfs(root.span_id, [], 0, new Set());
    }

    return longestPath;
  }

  private computeStats(spans: SystemTraceEvent[], edges: SpanEdge[]): TraceStats {
    const services = new Set(spans.map((s) => s.service));
    const layers = new Set(spans.map((s) => s.layer));
    const errorCount = spans.filter((s) => s.status === "error").length;
    const totalDuration = spans.reduce((sum, s) => sum + (s.duration_ms ?? 0), 0);
    const longestSpan = spans.reduce(
      (max, s) => Math.max(max, s.duration_ms ?? 0),
      0,
    );

    // 计算最大深度（BFS）
    const maxDepth = this.computeMaxDepth(spans);

    return {
      span_count: spans.length,
      edge_count: edges.length,
      root_count: this.findRootSpans(spans).length,
      max_depth: maxDepth,
      total_duration_ms: totalDuration,
      longest_span_ms: longestSpan,
      service_count: services.size,
      layer_count: layers.size,
      error_span_count: errorCount,
    };
  }

  private computeMaxDepth(spans: SystemTraceEvent[]): number {
    if (spans.length === 0) return 0;

    const spanMap = new Map(spans.map((s) => [s.span_id, s]));
    const depthCache = new Map<string, number>();

    const getDepth = (spanId: string, visited: Set<string>): number => {
      if (depthCache.has(spanId)) return depthCache.get(spanId)!;
      if (visited.has(spanId)) return 0; // 防环
      visited.add(spanId);

      const span = spanMap.get(spanId);
      if (!span || !span.parent_span_id) {
        depthCache.set(spanId, 1);
        return 1;
      }

      const depth = getDepth(span.parent_span_id, visited) + 1;
      depthCache.set(spanId, depth);
      return depth;
    };

    let max = 0;
    for (const span of spans) {
      max = Math.max(max, getDepth(span.span_id, new Set()));
    }
    return max;
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const traceCorrelator = new TraceCorrelator();
