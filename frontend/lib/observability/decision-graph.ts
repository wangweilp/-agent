/**
 * 知维 OS Decision Graph Engine — 决策图引擎
 * Zhiwei OS Decision Graph Engine
 *
 * v5 OS-level 关键新增：三图合一的缺失环节
 *
 * 三图关系：
 *   Execution Graph (Span Tree)  — "做了什么"        （已有）
 *   Causal Graph (Event DAG)    — "什么导致什么"     （已有）
 *   Decision Graph (本文)        — "为什么这么做"    （v5 新增）
 *
 * 区别：
 * - Span 描述"执行跨度"（时间维度）
 * - Event 描述"事实发生"（数据维度）
 * - Decision 描述"决策点"（推理维度）—— 包含触发、规则匹配、替代路径
 *
 * 设计原则：
 * 1. Decision 是派生数据，从 span.decision 字段聚合
 * 2. 不修改原 span，只读取
 * 3. 决策边的推导基于：
 *    - 同一 enforcement_loop 内的决策顺序
 *    - 高优先级规则覆盖低优先级规则（overridden_by）
 *    - 跨层级升级（escalated_to）
 */

import { observabilityStore } from "@/lib/observability/store";
import { causalKernel } from "@/lib/event-bus/causal-kernel";
import type { SystemEvent } from "@/types/event-bus";
import type {
  SystemTraceEvent,
  DecisionNode,
  DecisionEdge,
  DecisionGraph,
  DecisionGraphStats,
  DecisionEdgeType,
  AlternativePath,
} from "@/lib/observability/types";

// ═══════════════════════════════════════════════════════════════
// DecisionGraphEngine — 决策图引擎
// ═══════════════════════════════════════════════════════════════

export class DecisionGraphEngine {
  private decisionCounter = 0;

  /**
   * 构建决策图 — 主入口
   *
   * 步骤：
   * 1. 从 store 获取 trace 所有 span
   * 2. 过滤出有 decision 字段的 span（v5 OS-level 结构化决策）
   * 3. 兼容旧 span：从 metadata 推导 decision（向后兼容）
   * 4. 构造 DecisionNode 列表
   * 5. 推导 DecisionEdge（决策间因果关系）
   * 6. 识别根决策（无入边的决策）
   * 7. 计算统计
   *
   * @param trace_id 目标 trace
   * @returns 决策图
   */
  async buildDecisionGraph(trace_id: string): Promise<DecisionGraph> {
    // 1. 获取所有 span
    const spans = await observabilityStore.getSpansByTraceId(trace_id);

    // 2. 提取决策节点（v5 结构化 + 向后兼容旧 span）
    const nodes = this.extractDecisionNodes(spans, trace_id);

    // 3. 推导决策边
    const edges = this.deriveDecisionEdges(nodes, spans, trace_id);

    // 4. 识别根决策（无入边）
    const rootDecisions = this.findRootDecisions(nodes, edges);

    // 5. 计算统计
    const stats = this.computeStats(nodes, edges, rootDecisions);

    return {
      trace_id,
      nodes,
      edges,
      root_decisions: rootDecisions,
      stats,
    };
  }

  /**
   * 获取单个决策节点（按 span_id）
   */
  async getDecisionBySpanId(span_id: string): Promise<DecisionNode | null> {
    const span = await observabilityStore.getSpan(span_id);
    if (!span) return null;

    const nodes = this.extractDecisionNodes([span], span.trace_id);
    return nodes[0] ?? null;
  }

  /**
   * 获取决策的替代路径（反事实分析入口）
   */
  async getAlternatives(span_id: string): Promise<AlternativePath[]> {
    const span = await observabilityStore.getSpan(span_id);
    if (!span) return [];

    // v5 结构化字段
    if (span.explanation?.alternatives_considered) {
      return span.explanation.alternatives_considered;
    }

    return [];
  }

  // ─────────────────────────────────────────────────────────────
  // 内部方法：节点提取
  // ─────────────────────────────────────────────────────────────

  /**
   * 从 span 列表提取决策节点
   *
   * v5 OS-level：优先使用 span.decision 结构化字段
   * 向后兼容：对旧 span，从 metadata 推导
   */
  private extractDecisionNodes(spans: SystemTraceEvent[], trace_id: string): DecisionNode[] {
    const nodes: DecisionNode[] = [];

    for (const span of spans) {
      // v5：优先使用结构化 decision 字段
      if (span.decision) {
        nodes.push({
          decision_id: `dec_${span.span_id}`,
          trace_id,
          span_id: span.span_id,
          trigger_event_id: span.decision.trigger_event_id,
          rules_matched: span.decision.rule_matched,
          authority_level: span.decision.authority_level,
          final_decision: span.decision.enforcement_action ?? "EXECUTED",
          alternatives: span.explanation?.alternatives_considered ?? [],
          decided_at: span.decision.decided_at,
          metadata: {
            policy_id: span.metadata.policy_id,
            enforcement_loop_id: span.enforcement_loop_id,
            snapshot_id: span.decision.snapshot_used,
            reason: span.metadata.tags?.reason,
          },
        });
        continue;
      }

      // 向后兼容：从 metadata 推导（旧 span）
      if (this.isDecisionSpan(span)) {
        const decision = this.inferDecisionFromMetadata(span);
        if (decision) {
          nodes.push({
            decision_id: `dec_${span.span_id}`,
            trace_id,
            span_id: span.span_id,
            trigger_event_id: span.event_id ?? span.span_id,
            rules_matched: span.metadata.rule_id ? [span.metadata.rule_id] : [],
            authority_level: span.layer,
            final_decision: decision,
            alternatives: [],
            decided_at: span.start_time,
            metadata: {
              policy_id: span.metadata.policy_id,
              enforcement_loop_id: span.enforcement_loop_id,
              reason: span.metadata.output_summary,
            },
          });
        }
      }
    }

    return nodes;
  }

  /**
   * 判断 span 是否是决策 span（向后兼容用）
   */
  private isDecisionSpan(span: SystemTraceEvent): boolean {
    return (
      span.kind === "gate_decision" ||
      span.kind === "policy_evaluation" ||
      span.kind === "enforcement_stage" ||
      span.metadata.decision !== undefined
    );
  }

  /**
   * 从 metadata 推导决策（向后兼容）
   */
  private inferDecisionFromMetadata(span: SystemTraceEvent): string | null {
    if (span.metadata.decision) return span.metadata.decision;
    if (span.kind === "gate_decision" || span.kind === "policy_evaluation") {
      return span.metadata.tags?.decision ?? "EVALUATED";
    }
    return null;
  }

  // ─────────────────────────────────────────────────────────────
  // 内部方法：边推导
  // ─────────────────────────────────────────────────────────────

  /**
   * 推导决策边 — 决策间的因果关系
   *
   * 规则：
   * 1. triggered:        同 enforcement_loop 内，决策 A 的结果导致决策 B
   * 2. overridden_by:    同一事件被多个规则评估，高优先级覆盖低优先级
   * 3. escalated_to:     跨层级决策升级（如 L1 升级到 L4）
   * 4. alternative_of:   同一事件的不同决策（互斥）
   * 5. depends_on:       决策 B 依赖决策 A 的结果
   */
  private deriveDecisionEdges(
    nodes: DecisionNode[],
    spans: SystemTraceEvent[],
    trace_id: string,
  ): DecisionEdge[] {
    const edges: DecisionEdge[] = [];

    // 按 decided_at 排序
    const sortedNodes = [...nodes].sort((a, b) => a.decided_at.localeCompare(b.decided_at));

    // 规则 1：triggered — 同 enforcement_loop 内顺序决策
    edges.push(...this.deriveTriggeredEdges(sortedNodes));

    // 规则 2：overridden_by — 同一事件被多规则评估
    edges.push(...this.deriveOverriddenEdges(sortedNodes));

    // 规则 3：escalated_to — 跨层级升级
    edges.push(...this.deriveEscalatedEdges(sortedNodes));

    // 规则 4：alternative_of — 同事件互斥决策
    edges.push(...this.deriveAlternativeEdges(sortedNodes));

    // 规则 5：depends_on — 基于事件因果链
    edges.push(...this.deriveDependsOnEdges(sortedNodes, trace_id));

    // 去重
    return this.dedupEdges(edges);
  }

  /**
   * 规则 1：triggered — 同 enforcement_loop 内顺序决策
   */
  private deriveTriggeredEdges(nodes: DecisionNode[]): DecisionEdge[] {
    const edges: DecisionEdge[] = [];
    const loopGroups = new Map<string, DecisionNode[]>();

    for (const node of nodes) {
      const loopId = node.metadata?.enforcement_loop_id;
      if (!loopId) continue;
      const list = loopGroups.get(loopId) || [];
      list.push(node);
      loopGroups.set(loopId, list);
    }

    for (const [, group] of loopGroups) {
      // 按时间排序，前一个决策触发后一个
      for (let i = 1; i < group.length; i++) {
        edges.push({
          from: group[i - 1].decision_id,
          to: group[i].decision_id,
          type: "triggered",
          weight: 1.0,
        });
      }
    }

    return edges;
  }

  /**
   * 规则 2：overridden_by — 同一事件被多规则评估，高优先级覆盖
   */
  private deriveOverriddenEdges(nodes: DecisionNode[]): DecisionEdge[] {
    const edges: DecisionEdge[] = [];
    const byEvent = new Map<string, DecisionNode[]>();

    for (const node of nodes) {
      const list = byEvent.get(node.trigger_event_id) || [];
      list.push(node);
      byEvent.set(node.trigger_event_id, list);
    }

    for (const [, group] of byEvent) {
      if (group.length < 2) continue;
      // 按时间排序，后到的覆盖先到的
      const sorted = [...group].sort((a, b) => a.decided_at.localeCompare(b.decided_at));
      for (let i = 1; i < sorted.length; i++) {
        edges.push({
          from: sorted[i - 1].decision_id,
          to: sorted[i].decision_id,
          type: "overridden_by",
          weight: 1.0,
        });
      }
    }

    return edges;
  }

  /**
   * 规则 3：escalated_to — 跨层级升级
   */
  private deriveEscalatedEdges(nodes: DecisionNode[]): DecisionEdge[] {
    const edges: DecisionEdge[] = [];
    const layerOrder = ["L1", "L2", "L3", "L4", "L5"];

    for (let i = 1; i < nodes.length; i++) {
      const prev = nodes[i - 1];
      const curr = nodes[i];
      const prevLevel = layerOrder.indexOf(prev.authority_level);
      const currLevel = layerOrder.indexOf(curr.authority_level);
      if (currLevel > prevLevel) {
        edges.push({
          from: prev.decision_id,
          to: curr.decision_id,
          type: "escalated_to",
          weight: 0.8,
        });
      }
    }

    return edges;
  }

  /**
   * 规则 4：alternative_of — 同事件互斥决策
   *
   * 基于 alternatives_considered 字段（v5 OS-level）
   */
  private deriveAlternativeEdges(nodes: DecisionNode[]): DecisionEdge[] {
    const edges: DecisionEdge[] = [];

    for (const node of nodes) {
      for (const alt of node.alternatives) {
        // 找到 alternative 对应的决策节点（如存在）
        const altNode = nodes.find((n) =>
          n.rules_matched.includes(alt.source) || n.metadata?.policy_id === alt.source,
        );
        if (altNode && altNode.decision_id !== node.decision_id) {
          edges.push({
            from: node.decision_id,
            to: altNode.decision_id,
            type: "alternative_of",
            weight: 0.5,
          });
        }
      }
    }

    return edges;
  }

  /**
   * 规则 5：depends_on — 基于事件因果链
   */
  private deriveDependsOnEdges(nodes: DecisionNode[], trace_id: string): DecisionEdge[] {
    const edges: DecisionEdge[] = [];
    const events = causalKernel.replay(trace_id);
    const eventMap = new Map(events.map((e) => [e.event_id, e]));

    for (const node of nodes) {
      const event = eventMap.get(node.trigger_event_id);
      if (!event?.causal.parent_event_id) continue;

      // 找到父事件对应的决策
      const parentDecision = nodes.find(
        (n) =>
          n.trigger_event_id === event.causal.parent_event_id ||
          n.trigger_event_id === event.event_id,
      );
      if (parentDecision && parentDecision.decision_id !== node.decision_id) {
        edges.push({
          from: node.decision_id,
          to: parentDecision.decision_id,
          type: "depends_on",
          weight: 1.0,
        });
      }
    }

    return edges;
  }

  // ─────────────────────────────────────────────────────────────
  // 内部方法：根决策与统计
  // ─────────────────────────────────────────────────────────────

  private findRootDecisions(nodes: DecisionNode[], edges: DecisionEdge[]): DecisionNode[] {
    const hasIncoming = new Set(edges.map((e) => e.to));
    return nodes.filter((n) => !hasIncoming.has(n.decision_id));
  }

  private dedupEdges(edges: DecisionEdge[]): DecisionEdge[] {
    const seen = new Set<string>();
    const result: DecisionEdge[] = [];
    for (const edge of edges) {
      const key = `${edge.from}->${edge.to}:${edge.type}`;
      if (!seen.has(key)) {
        seen.add(key);
        result.push(edge);
      }
    }
    return result;
  }

  private computeStats(
    nodes: DecisionNode[],
    edges: DecisionEdge[],
    rootDecisions: DecisionNode[],
  ): DecisionGraphStats {
    const byDecision: Record<string, number> = {};
    let totalAlternatives = 0;
    const authorityLevels = new Set<string>();

    for (const node of nodes) {
      byDecision[node.final_decision] = (byDecision[node.final_decision] || 0) + 1;
      totalAlternatives += node.alternatives.length;
      authorityLevels.add(node.authority_level);
    }

    return {
      decision_count: nodes.length,
      edge_count: edges.length,
      root_count: rootDecisions.length,
      by_decision: byDecision,
      avg_alternatives: nodes.length > 0 ? totalAlternatives / nodes.length : 0,
      authority_levels: authorityLevels.size,
      max_depth: this.computeMaxDepth(nodes, edges),
    };
  }

  private computeMaxDepth(nodes: DecisionNode[], edges: DecisionEdge[]): number {
    if (nodes.length === 0) return 0;

    const adj = new Map<string, string[]>();
    for (const node of nodes) adj.set(node.decision_id, []);
    for (const edge of edges) {
      const list = adj.get(edge.from) || [];
      list.push(edge.to);
      adj.set(edge.from, list);
    }

    const roots = this.findRootDecisions(nodes, edges);
    if (roots.length === 0) return 1;

    let maxDepth = 0;
    const dfs = (id: string, depth: number, visited: Set<string>) => {
      if (visited.has(id)) return;
      visited.add(id);
      maxDepth = Math.max(maxDepth, depth);
      for (const next of adj.get(id) || []) {
        dfs(next, depth + 1, new Set(visited));
      }
    };

    for (const root of roots) {
      dfs(root.decision_id, 1, new Set());
    }

    return maxDepth;
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const decisionGraphEngine = new DecisionGraphEngine();
