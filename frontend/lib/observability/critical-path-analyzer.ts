/**
 * 知维 OS Critical Path Analyzer — 关键路径分析器
 * Zhiwei OS Critical Path Analyzer
 *
 * 三大分析维度：
 * 1. latency_hotpath      — 最高延迟链（按 duration_ms 总和最大）
 * 2. causal_hotpath       — 最长因果链（按 span 数量最多）
 * 3. enforcement_hotpath  — 最多策略干预链（按 enforcement 决策数量最多）
 *
 * 输出：CriticalPathReport
 */

import { observabilityStore } from "@/lib/observability/store";
import { traceCorrelator } from "@/lib/observability/correlator";
import { causalKernel } from "@/lib/event-bus/causal-kernel";
import type { CausalLink } from "@/types/event-bus";
import type {
  SystemTraceEvent,
  SpanEdge,
  SpanPath,
  CriticalPathReport,
} from "@/lib/observability/types";

// ═══════════════════════════════════════════════════════════════
// CriticalPathAnalyzer — 关键路径分析器
// ═══════════════════════════════════════════════════════════════

export class CriticalPathAnalyzer {
  /**
   * 分析 trace 的关键路径 — 主入口
   *
   * @param trace_id  目标 trace
   * @returns 关键路径报告
   */
  async analyze(trace_id: string): Promise<CriticalPathReport> {
    const analyzedAt = new Date().toISOString();

    // 1. 获取 trace 所有 span
    const spans = await observabilityStore.getSpansByTraceId(trace_id);

    // 2. 获取/推导所有边
    const storedEdges = await observabilityStore.getEdgesByTraceId(trace_id);
    const derivedEdges = await traceCorrelator.deriveCausalEdges(trace_id, spans);
    const allEdges = this.dedupEdges(storedEdges, derivedEdges);

    // 3. 计算三大热路径
    const latencyHotpath = this.computeLatencyHotpath(spans, allEdges);
    const causalHotpath = this.computeCausalHotpath(spans, allEdges, trace_id);
    const enforcementHotpath = this.computeEnforcementHotpath(spans, allEdges);
    // v5 OS-level：决策热路径（决策密度 + 复杂度）
    const decisionHotpath = this.computeDecisionHotpath(spans, allEdges);

    // 4. 总耗时
    const totalDuration = spans.reduce((sum, s) => sum + (s.duration_ms ?? 0), 0);

    return {
      trace_id,
      latency_hotpath: latencyHotpath,
      causal_hotpath: causalHotpath,
      enforcement_hotpath: enforcementHotpath,
      decision_hotpath: decisionHotpath,
      analyzed_at: analyzedAt,
      total_duration_ms: totalDuration,
    };
  }

  // ─────────────────────────────────────────────────────────────
  // 1. latency_hotpath — 最高延迟链
  // ─────────────────────────────────────────────────────────────

  /**
   * 计算 latency 热路径 — 在所有 root→leaf 路径中，找 duration_ms 总和最大的
   *
   * 算法：DFS 遍历所有根到叶子的路径，累计 duration_ms，取最大者
   */
  private computeLatencyHotpath(
    spans: SystemTraceEvent[],
    edges: SpanEdge[],
  ): SpanPath[] {
    if (spans.length === 0) return [];

    const spanMap = new Map(spans.map((s) => [s.span_id, s]));
    const roots = spans.filter((s) => !s.parent_span_id);
    if (roots.length === 0) return [];

    // 构建邻接表（仅 parent_child 和 causal_link 边）
    const adj = this.buildAdjacencyList(spans, edges, ["parent_child", "causal_link"]);

    // DFS 找最长延迟路径
    let bestPath: SystemTraceEvent[] = [];
    let bestDuration = -1;

    const dfs = (
      currentId: string,
      path: SystemTraceEvent[],
      duration: number,
      visited: Set<string>,
    ) => {
      if (visited.has(currentId)) return; // 防环
      const span = spanMap.get(currentId);
      if (!span) return;

      const newPath = [...path, span];
      const newDuration = duration + (span.duration_ms ?? 0);
      const newVisited = new Set(visited);
      newVisited.add(currentId);

      const children = adj.get(currentId) || [];
      if (children.length === 0) {
        // 叶子节点 — 候选路径
        if (newDuration > bestDuration) {
          bestDuration = newDuration;
          bestPath = newPath;
        }
      } else {
        for (const child of children) {
          dfs(child, newPath, newDuration, newVisited);
        }
      }
    };

    for (const root of roots) {
      dfs(root.span_id, [], 0, new Set());
    }

    if (bestPath.length === 0) return [];

    return [
      {
        span_ids: bestPath.map((s) => s.span_id),
        spans: bestPath,
        total_duration_ms: bestDuration < 0 ? 0 : bestDuration,
        span_count: bestPath.length,
        description: `Highest latency chain: ${bestPath.length} spans, ${bestDuration < 0 ? 0 : bestDuration}ms total`,
      },
    ];
  }

  // ─────────────────────────────────────────────────────────────
  // 2. causal_hotpath — 最长因果链
  // ─────────────────────────────────────────────────────────────

  /**
   * 计算 causal 热路径 — 在所有路径中，找 span 数量最多的
   *
   * 算法：DFS 遍历所有 root→leaf 路径，累计 span 数量，取最多者
   * 同时结合事件因果链（causal_kernel.replay）确保覆盖完整因果路径
   */
  private computeCausalHotpath(
    spans: SystemTraceEvent[],
    edges: SpanEdge[],
    trace_id: string,
  ): SpanPath[] {
    if (spans.length === 0) return [];

    const spanMap = new Map(spans.map((s) => [s.span_id, s]));
    const roots = spans.filter((s) => !s.parent_span_id);
    if (roots.length === 0) return [];

    // 构建邻接表（causal_link 优先）
    const adj = this.buildAdjacencyList(spans, edges, [
      "causal_link",
      "parent_child",
      "follows_from",
    ]);

    // DFS 找最长 span 链
    let bestPath: SystemTraceEvent[] = [];

    const dfs = (
      currentId: string,
      path: SystemTraceEvent[],
      visited: Set<string>,
    ) => {
      if (visited.has(currentId)) return; // 防环
      const span = spanMap.get(currentId);
      if (!span) return;

      const newPath = [...path, span];
      const newVisited = new Set(visited);
      newVisited.add(currentId);

      const children = adj.get(currentId) || [];
      if (children.length === 0) {
        if (newPath.length > bestPath.length) {
          bestPath = newPath;
        }
      } else {
        for (const child of children) {
          dfs(child, newPath, newVisited);
        }
      }
    };

    for (const root of roots) {
      dfs(root.span_id, [], new Set());
    }

    // 补充：从事件因果链推导（如 span 链为空，回退到纯事件因果链）
    if (bestPath.length === 0) {
      const eventPath = this.deriveEventCausalPath(trace_id, spanMap);
      if (eventPath.length > 0) {
        const duration = eventPath.reduce((sum, s) => sum + (s.duration_ms ?? 0), 0);
        return [
          {
            span_ids: eventPath.map((s) => s.span_id),
            spans: eventPath,
            total_duration_ms: duration,
            span_count: eventPath.length,
            description: `Longest causal chain (event-derived): ${eventPath.length} spans`,
          },
        ];
      }
      return [];
    }

    const duration = bestPath.reduce((sum, s) => sum + (s.duration_ms ?? 0), 0);

    return [
      {
        span_ids: bestPath.map((s) => s.span_id),
        spans: bestPath,
        total_duration_ms: duration,
        span_count: bestPath.length,
        description: `Longest causal chain: ${bestPath.length} spans, ${duration}ms total`,
      },
    ];
  }

  /**
   * 从事件因果链推导 span 路径（回退策略）
   * 找最长的事件因果链，然后映射到 span
   */
  private deriveEventCausalPath(
    trace_id: string,
    spanMap: Map<string, SystemTraceEvent>,
  ): SystemTraceEvent[] {
    const events = causalKernel.replay(trace_id);
    if (events.length === 0) return [];

    // 构建 event_id → event 映射
    const eventMap = new Map(events.map((e) => [e.event_id, e]));

    // 构建 event_id → span 映射
    const eventToSpan = new Map<string, SystemTraceEvent>();
    for (const span of spanMap.values()) {
      if (span.event_id) {
        eventToSpan.set(span.event_id, span);
      }
    }

    // DFS 找最长因果链
    let bestEventPath: string[] = [];

    const dfs = (eventId: string, path: string[], visited: Set<string>) => {
      if (visited.has(eventId)) return;
      const event = eventMap.get(eventId);
      if (!event) return;

      const newPath = [...path, eventId];
      const newVisited = new Set(visited);
      newVisited.add(eventId);

      // 找该事件的所有因果父节点
      const parents: string[] = [];
      if (event.causal.parent_event_id) {
        parents.push(event.causal.parent_event_id);
      }
      if (event.causal.causal_links) {
        for (const link of event.causal.causal_links) {
          parents.push(link.from);
        }
      }

      if (parents.length === 0) {
        // 根事件
        if (newPath.length > bestEventPath.length) {
          bestEventPath = newPath;
        }
      } else {
        for (const parent of parents) {
          dfs(parent, newPath, newVisited);
        }
      }
    };

    // 从每个事件向上回溯
    for (const event of events) {
      dfs(event.event_id, [], new Set());
    }

    // 反转（从根到当前）
    bestEventPath.reverse();

    // 映射到 span（只保留有 span 的事件）
    const spans: SystemTraceEvent[] = [];
    for (const eventId of bestEventPath) {
      const span = eventToSpan.get(eventId);
      if (span) {
        spans.push(span);
      }
    }

    return spans;
  }

  // ─────────────────────────────────────────────────────────────
  // 3. enforcement_hotpath — 最多策略干预链
  // ─────────────────────────────────────────────────────────────

  /**
   * 计算 enforcement 热路径 — 在所有路径中，找 enforcement 决策数量最多的
   *
   * 算法：DFS 遍历所有 root→leaf 路径，统计 policy_evaluation/gate_decision span 数量
   */
  private computeEnforcementHotpath(
    spans: SystemTraceEvent[],
    edges: SpanEdge[],
  ): SpanPath[] {
    if (spans.length === 0) return [];

    // 过滤出 enforcement 相关的 span
    const enforcementSpans = spans.filter(
      (s) =>
        s.kind === "policy_evaluation" ||
        s.kind === "gate_decision" ||
        s.kind === "enforcement_stage",
    );

    if (enforcementSpans.length === 0) return [];

    const spanMap = new Map(spans.map((s) => [s.span_id, s]));
    const roots = spans.filter((s) => !s.parent_span_id);
    if (roots.length === 0) return [];

    // 构建邻接表
    const adj = this.buildAdjacencyList(spans, edges, [
      "parent_child",
      "causal_link",
      "enforcement_link",
    ]);

    // DFS 找 enforcement 决策最多的路径
    let bestPath: SystemTraceEvent[] = [];
    let bestDecisionCount = -1;

    const isEnforcementSpan = (span: SystemTraceEvent): boolean =>
      span.kind === "policy_evaluation" ||
      span.kind === "gate_decision" ||
      span.kind === "enforcement_stage";

    const dfs = (
      currentId: string,
      path: SystemTraceEvent[],
      decisionCount: number,
      visited: Set<string>,
    ) => {
      if (visited.has(currentId)) return;
      const span = spanMap.get(currentId);
      if (!span) return;

      const newPath = [...path, span];
      const newCount = decisionCount + (isEnforcementSpan(span) ? 1 : 0);
      const newVisited = new Set(visited);
      newVisited.add(currentId);

      const children = adj.get(currentId) || [];
      if (children.length === 0) {
        // 叶子节点
        // 优先按 enforcement 决策数排序，其次按总耗时
        if (newCount > bestDecisionCount) {
          bestDecisionCount = newCount;
          bestPath = newPath;
        } else if (newCount === bestDecisionCount && newPath.length > bestPath.length) {
          bestPath = newPath;
        }
      } else {
        for (const child of children) {
          dfs(child, newPath, newCount, newVisited);
        }
      }
    };

    for (const root of roots) {
      dfs(root.span_id, [], 0, new Set());
    }

    if (bestPath.length === 0 || bestDecisionCount <= 0) return [];

    const duration = bestPath.reduce((sum, s) => sum + (s.duration_ms ?? 0), 0);

    return [
      {
        span_ids: bestPath.map((s) => s.span_id),
        spans: bestPath,
        total_duration_ms: duration,
        span_count: bestPath.length,
        description: `Highest policy intervention chain: ${bestDecisionCount} enforcement decisions across ${bestPath.length} spans`,
      },
    ];
  }

  // ─────────────────────────────────────────────────────────────
  // 4. decision_hotpath — 决策热路径（v5 OS-level 新增）
  // ─────────────────────────────────────────────────────────────

  /**
   * 计算 decision 热路径 — 决策密度 + 决策复杂度最高的路径
   *
   * v5 OS-level 关键升级：
   * 与 enforcement_hotpath 的区别：
   * - enforcement_hotpath: 统计 enforcement_stage/policy_evaluation/gate_decision span 数（按 kind）
   * - decision_hotpath: 统计含 decision 字段（结构化决策）的 span 数 + alternatives_considered 数（决策复杂度）
   *
   * 算法：DFS 遍历所有 root→leaf 路径，统计决策密度（decision span 数）+ 决策复杂度（alternatives 数）
   * 综合得分 = 决策密度 * 0.7 + 决策复杂度 * 0.3
   */
  private computeDecisionHotpath(
    spans: SystemTraceEvent[],
    edges: SpanEdge[],
  ): SpanPath[] {
    if (spans.length === 0) return [];

    // 过滤出含 decision 字段的 span（v5 OS-level 结构化决策）
    const decisionSpans = spans.filter((s) => s.decision !== undefined);
    if (decisionSpans.length === 0) return [];

    const spanMap = new Map(spans.map((s) => [s.span_id, s]));
    const roots = spans.filter((s) => !s.parent_span_id);
    if (roots.length === 0) return [];

    // 构建邻接表
    const adj = this.buildAdjacencyList(spans, edges, [
      "parent_child",
      "causal_link",
      "enforcement_link",
    ]);

    // DFS 找决策综合得分最高的路径
    let bestPath: SystemTraceEvent[] = [];
    let bestScore = -1;

    const isDecisionSpan = (span: SystemTraceEvent): boolean => span.decision !== undefined;

    const getDecisionComplexity = (span: SystemTraceEvent): number =>
      span.explanation?.alternatives_considered?.length ?? 0;

    const dfs = (
      currentId: string,
      path: SystemTraceEvent[],
      decisionCount: number,
      complexitySum: number,
      visited: Set<string>,
    ) => {
      if (visited.has(currentId)) return;
      const span = spanMap.get(currentId);
      if (!span) return;

      const newPath = [...path, span];
      const isDecision = isDecisionSpan(span);
      const newDecisionCount = decisionCount + (isDecision ? 1 : 0);
      const newComplexity = complexitySum + (isDecision ? getDecisionComplexity(span) : 0);
      const newVisited = new Set(visited);
      newVisited.add(currentId);

      const children = adj.get(currentId) || [];
      if (children.length === 0) {
        // 叶子节点 — 计算综合得分
        // 综合得分 = 决策密度 * 0.7 + 决策复杂度 * 0.3
        const densityScore = newDecisionCount;
        const complexityScore = newComplexity;
        const totalScore = densityScore * 0.7 + complexityScore * 0.3;

        if (totalScore > bestScore) {
          bestScore = totalScore;
          bestPath = newPath;
        } else if (totalScore === bestScore && newPath.length > bestPath.length) {
          // 同分时取更长路径
          bestPath = newPath;
        }
      } else {
        for (const child of children) {
          dfs(child, newPath, newDecisionCount, newComplexity, newVisited);
        }
      }
    };

    for (const root of roots) {
      dfs(root.span_id, [], 0, 0, new Set());
    }

    if (bestPath.length === 0 || bestScore <= 0) return [];

    const duration = bestPath.reduce((sum, s) => sum + (s.duration_ms ?? 0), 0);
    const decisionCountInPath = bestPath.filter(isDecisionSpan).length;
    const complexityInPath = bestPath.reduce(
      (sum, s) => sum + getDecisionComplexity(s),
      0,
    );

    return [
      {
        span_ids: bestPath.map((s) => s.span_id),
        spans: bestPath,
        total_duration_ms: duration,
        span_count: bestPath.length,
        description:
          `Highest decision density chain: ${decisionCountInPath} decisions ` +
          `+ ${complexityInPath} alternatives across ${bestPath.length} spans ` +
          `(score=${bestScore.toFixed(2)})`,
      },
    ];
  }

  // ─────────────────────────────────────────────────────────────
  // 工具方法
  // ─────────────────────────────────────────────────────────────

  /**
   * 构建邻接表 — 仅包含指定类型的边
   */
  private buildAdjacencyList(
    spans: SystemTraceEvent[],
    edges: SpanEdge[],
    allowedTypes: SpanEdge["type"][],
  ): Map<string, string[]> {
    const adj = new Map<string, string[]>();
    for (const span of spans) {
      adj.set(span.span_id, []);
    }
    const allowed = new Set(allowedTypes);
    for (const edge of edges) {
      if (allowed.has(edge.type)) {
        const list = adj.get(edge.from) || [];
        list.push(edge.to);
        adj.set(edge.from, list);
      }
    }
    return adj;
  }

  /**
   * 边去重
   */
  private dedupEdges(existing: SpanEdge[], derived: SpanEdge[]): SpanEdge[] {
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
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const criticalPathAnalyzer = new CriticalPathAnalyzer();
