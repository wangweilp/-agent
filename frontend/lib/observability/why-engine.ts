/**
 * 知维 OS WHY Engine — 可解释性引擎
 * Zhiwei OS WHY Engine
 *
 * 核心能力：why(trace_id, event_id?)
 *
 * 回答：
 * - 为什么这个 event 被执行？
 * - 它依赖哪个 causal path？
 * - 被哪个 policy 放行/阻断？
 * - 是否来自 snapshot replay？
 * - 是否来自 enforcement modification？
 *
 * 输出：WhyExplanation
 */

import { observabilityStore } from "@/lib/observability/store";
import { traceCorrelator } from "@/lib/observability/correlator";
import { causalKernel } from "@/lib/event-bus/causal-kernel";
import { persistencePipeline } from "@/lib/persistence/pipeline";
import type { SystemEvent, CausalLink } from "@/types/event-bus";
import type {
  WhyExplanation,
  PolicyDecision,
  EnforcementRecord,
  SystemTraceEvent,
  CounterfactualAnalysis,
  AlternativePath,
} from "@/lib/observability/types";

// ═══════════════════════════════════════════════════════════════
// WhyEngine — 可解释性引擎
// ═══════════════════════════════════════════════════════════════

export class WhyEngine {
  /**
   * WHY — 主入口
   *
   * @param trace_id  查询的 trace
   * @param event_id  查询的事件（不指定则解释整个 trace）
   */
  async why(trace_id: string, event_id?: string): Promise<WhyExplanation> {
    const generatedAt = new Date().toISOString();

    // 1. 获取关联的 span
    let span: SystemTraceEvent | null = null;
    if (event_id) {
      span = await observabilityStore.getSpanByEventId(event_id);
    }

    // 2. 构建根因链
    const rootCauseChain = await this.buildRootCauseChain(trace_id, event_id, span);

    // 3. 构建决策路径
    const decisionPath = await this.buildDecisionPath(trace_id, event_id);

    // 4. 构建因果路径
    const causalPath = await this.buildCausalPath(trace_id, event_id);

    // 5. 检查 snapshot 来源
    const snapshotOrigin = await this.checkSnapshotOrigin(span, trace_id);

    // 6. 检查 enforcement 干预
    const enforcementIntervention = await this.checkEnforcementIntervention(trace_id, event_id, span);

    // 7. 计算置信度
    const confidenceScore = this.computeConfidenceScore(
      rootCauseChain,
      decisionPath,
      causalPath,
      snapshotOrigin,
      enforcementIntervention,
    );

    // 8. 生成人类可读摘要
    const summary = this.generateSummary(
      trace_id, event_id, rootCauseChain, decisionPath,
      enforcementIntervention, snapshotOrigin,
    );

    return {
      trace_id,
      event_id,
      span_id: span?.span_id,
      root_cause_chain: rootCauseChain,
      decision_path: decisionPath,
      causal_path: causalPath,
      snapshot_origin: snapshotOrigin ?? undefined,
      enforcement_intervention: enforcementIntervention ?? undefined,
      confidence_score: confidenceScore,
      summary,
      generated_at: generatedAt,
    };
  }

  // ─────────────────────────────────────────────────────────────
  // 子方法实现
  // ─────────────────────────────────────────────────────────────

  /**
   * 构建根因链 — 从根 span 到当前 span 的完整路径
   */
  private async buildRootCauseChain(
    trace_id: string,
    event_id?: string,
    targetSpan?: SystemTraceEvent | null,
  ): Promise<SystemTraceEvent[]> {
    const spans = await observabilityStore.getSpansByTraceId(trace_id);
    if (spans.length === 0) return [];

    const spanMap = new Map(spans.map((s) => [s.span_id, s]));

    // 找到目标 span
    let target = targetSpan;
    if (!target && event_id) {
      target = await observabilityStore.getSpanByEventId(event_id);
    }
    if (!target) {
      // 没有指定 → 返回根 span
      return spans.filter((s) => !s.parent_span_id);
    }

    // 从目标 span 向上回溯到根
    const chain: SystemTraceEvent[] = [];
    let current: SystemTraceEvent | undefined = target;
    const visited = new Set<string>();

    while (current && !visited.has(current.span_id)) {
      visited.add(current.span_id);
      chain.unshift(current);
      if (current.parent_span_id) {
        current = spanMap.get(current.parent_span_id);
      } else {
        break;
      }
    }

    return chain;
  }

  /**
   * 构建决策路径 — 收集涉及的 policy 决策
   */
  private async buildDecisionPath(trace_id: string, event_id?: string): Promise<PolicyDecision[]> {
    const spans = await observabilityStore.getSpansByTraceId(trace_id);
    const decisions: PolicyDecision[] = [];

    for (const span of spans) {
      // policy_evaluation 和 gate_decision span 携带决策信息
      if (span.kind === "policy_evaluation" || span.kind === "gate_decision") {
        if (
          span.metadata.policy_id ||
          span.metadata.rule_id ||
          span.metadata.decision
        ) {
          decisions.push({
            policy_id: span.metadata.policy_id ?? "unknown",
            policy_name: span.metadata.tags?.policy_name ?? "Unknown Policy",
            rule_id: span.metadata.rule_id ?? "unknown",
            decision: span.metadata.decision ?? "unknown",
            reason: span.metadata.tags?.reason ?? span.metadata.output_summary ?? "No reason recorded",
            decided_at: span.start_time,
            span_id: span.span_id,
          });
        }
      }
    }

    // 如指定 event_id，过滤到相关决策
    if (event_id) {
      // 找到该 event 的 span，然后找其祖先链涉及的决策
      const targetSpan = await observabilityStore.getSpanByEventId(event_id);
      if (targetSpan) {
        const ancestors = new Set<string>();
        let current: SystemTraceEvent | undefined = targetSpan;
        const spanMap = new Map(spans.map((s) => [s.span_id, s]));
        const visited = new Set<string>();
        while (current && !visited.has(current.span_id)) {
          visited.add(current.span_id);
          ancestors.add(current.span_id);
          if (current.parent_span_id) {
            current = spanMap.get(current.parent_span_id);
          } else break;
        }
        return decisions.filter((d) => d.span_id && ancestors.has(d.span_id));
      }
    }

    return decisions;
  }

  /**
   * 构建因果路径 — 涉及的 causal links
   */
  private async buildCausalPath(trace_id: string, event_id?: string): Promise<CausalLink[]> {
    const events = causalKernel.replay(trace_id);
    const links: CausalLink[] = [];

    for (const event of events) {
      if (event.causal.parent_event_id) {
        links.push({
          from: event.causal.parent_event_id,
          relation: "caused_by",
          weight: 1.0,
        });
      }
      if (event.causal.causal_links) {
        for (const link of event.causal.causal_links) {
          // 避免重复
          const exists = links.some(
            (l) => l.from === link.from && l.relation === link.relation,
          );
          if (!exists) {
            links.push(link);
          }
        }
      }
    }

    // 如指定 event_id，过滤到该事件的因果路径
    if (event_id) {
      // 找到该事件，然后回溯其因果链
      const eventMap = new Map(events.map((e) => [e.event_id, e]));
      const target = events.find((e) => e.event_id === event_id);
      if (target) {
        const relevantLinks: CausalLink[] = [];
        const visited = new Set<string>();

        const collect = (eventId: string) => {
          if (visited.has(eventId)) return;
          visited.add(eventId);

          const event = eventMap.get(eventId);
          if (!event) return;

          if (event.causal.parent_event_id) {
            relevantLinks.push({
              from: event.causal.parent_event_id,
              relation: "caused_by",
              weight: 1.0,
            });
            collect(event.causal.parent_event_id);
          }

          if (event.causal.causal_links) {
            for (const link of event.causal.causal_links) {
              relevantLinks.push(link);
              collect(link.from);
            }
          }
        };

        collect(event_id);
        return relevantLinks;
      }
    }

    return links;
  }

  /**
   * 检查 snapshot 来源
   */
  private async checkSnapshotOrigin(
    span: SystemTraceEvent | null,
    trace_id: string,
  ): Promise<{ snapshot_id: string; cursor: number; restored_at: string } | null> {
    // 检查 span 是否关联 snapshot
    if (span?.snapshot_id && span.kind === "snapshot_restore") {
      const snapshot = await persistencePipeline.getLatestSnapshot(trace_id);
      if (snapshot && snapshot.snapshot_id === span.snapshot_id) {
        return {
          snapshot_id: snapshot.snapshot_id,
          cursor: snapshot.cursor,
          restored_at: span.start_time,
        };
      }
    }

    // 检查 trace 是否有 snapshot_restore span
    const spans = await observabilityStore.getSpansByTraceId(trace_id);
    const restoreSpan = spans.find((s) => s.kind === "snapshot_restore" && s.snapshot_id);
    if (restoreSpan?.snapshot_id) {
      const snapshots = await persistencePipeline.listSnapshots(trace_id);
      const snapshot = snapshots.find((s) => s.snapshot_id === restoreSpan.snapshot_id);
      if (snapshot) {
        return {
          snapshot_id: snapshot.snapshot_id,
          cursor: snapshot.cursor,
          restored_at: restoreSpan.start_time,
        };
      }
    }

    return null;
  }

  /**
   * 检查 enforcement 干预
   */
  private async checkEnforcementIntervention(
    trace_id: string,
    event_id?: string,
    span?: SystemTraceEvent | null,
  ): Promise<EnforcementRecord | null> {
    const spans = await observabilityStore.getSpansByTraceId(trace_id);

    // 找到 enforcement 相关 span
    const enforcementSpans = spans.filter(
      (s) => s.kind === "gate_decision" || s.kind === "policy_evaluation",
    );

    // 如指定 event_id，找该 event 的 enforcement span
    let relevantSpan = span;
    if (!relevantSpan && event_id) {
      relevantSpan = await observabilityStore.getSpanByEventId(event_id);
    }

    if (relevantSpan) {
      // 找该 span 或其祖先的 enforcement span
      const spanMap = new Map(spans.map((s) => [s.span_id, s]));
      let current: SystemTraceEvent | undefined = relevantSpan;
      const visited = new Set<string>();
      while (current && !visited.has(current.span_id)) {
        visited.add(current.span_id);
        if (current.kind === "gate_decision" || current.kind === "policy_evaluation") {
          return {
            loop_id: current.enforcement_loop_id ?? "unknown",
            final_decision: current.metadata.decision ?? "unknown",
            modified: current.metadata.decision === "MODIFY",
            modification_details: current.metadata.decision === "MODIFY"
              ? current.metadata.output_summary
              : undefined,
            blocked: current.metadata.decision === "BLOCK",
            block_reason: current.metadata.decision === "BLOCK"
              ? current.metadata.output_summary
              : undefined,
            policy_id: current.metadata.policy_id,
            rule_id: current.metadata.rule_id,
            intervened_at: current.start_time,
          };
        }
        if (current.parent_span_id) {
          current = spanMap.get(current.parent_span_id);
        } else break;
      }
    }

    // 否则返回 trace 的第一个 enforcement 决策
    if (enforcementSpans.length > 0) {
      const first = enforcementSpans[0];
      return {
        loop_id: first.enforcement_loop_id ?? "unknown",
        final_decision: first.metadata.decision ?? "unknown",
        modified: first.metadata.decision === "MODIFY",
        modification_details: first.metadata.decision === "MODIFY"
          ? first.metadata.output_summary
          : undefined,
        blocked: first.metadata.decision === "BLOCK",
        block_reason: first.metadata.decision === "BLOCK"
          ? first.metadata.output_summary
          : undefined,
        policy_id: first.metadata.policy_id,
        rule_id: first.metadata.rule_id,
        intervened_at: first.start_time,
      };
    }

    return null;
  }

  /**
   * 计算置信度分数（0-1）
   */
  private computeConfidenceScore(
    rootCauseChain: SystemTraceEvent[],
    decisionPath: PolicyDecision[],
    causalPath: CausalLink[],
    snapshotOrigin: { snapshot_id: string; cursor: number; restored_at: string } | null,
    enforcementIntervention: EnforcementRecord | null,
  ): number {
    let score = 0;

    // 根因链越完整，置信度越高
    if (rootCauseChain.length > 0) score += 0.3;
    if (rootCauseChain.length >= 3) score += 0.1;

    // 决策路径越清晰，置信度越高
    if (decisionPath.length > 0) score += 0.2;
    if (decisionPath.length >= 2) score += 0.1;

    // 因果路径越完整，置信度越高
    if (causalPath.length > 0) score += 0.2;

    // 有 snapshot 来源 → 增加置信度
    if (snapshotOrigin) score += 0.1;

    // 有 enforcement 干预记录 → 增加置信度
    if (enforcementIntervention) score += 0.1;

    return Math.min(1, score);
  }

  /**
   * 生成人类可读摘要
   */
  private generateSummary(
    trace_id: string,
    event_id: string | undefined,
    rootCauseChain: SystemTraceEvent[],
    decisionPath: PolicyDecision[],
    enforcementIntervention: EnforcementRecord | null,
    snapshotOrigin: { snapshot_id: string; cursor: number; restored_at: string } | null,
  ): string {
    const parts: string[] = [];

    if (event_id) {
      parts.push(`Event ${event_id}`);
    } else {
      parts.push(`Trace ${trace_id}`);
    }

    // 根因
    if (rootCauseChain.length > 0) {
      const root = rootCauseChain[0];
      parts.push(`originated from ${root.service}/${root.kind} at ${root.start_time}`);
    }

    // 决策路径
    if (decisionPath.length > 0) {
      const decisions = decisionPath.map((d) => `${d.policy_name}=${d.decision}`).join(", ");
      parts.push(`was evaluated by policies: ${decisions}`);
    }

    // Enforcement 干预
    if (enforcementIntervention) {
      if (enforcementIntervention.blocked) {
        parts.push(`was BLOCKED by ${enforcementIntervention.policy_id ?? "policy"}: ${enforcementIntervention.block_reason ?? "unknown reason"}`);
      } else if (enforcementIntervention.modified) {
        parts.push(`was MODIFIED by enforcement: ${enforcementIntervention.modification_details ?? "unknown modification"}`);
      } else {
        parts.push(`was ALLOWED by ${enforcementIntervention.policy_id ?? "policy"}`);
      }
    }

    // Snapshot 来源
    if (snapshotOrigin) {
      parts.push(`was restored from snapshot ${snapshotOrigin.snapshot_id} at cursor ${snapshotOrigin.cursor}`);
    }

    return parts.join(", ") + ".";
  }

  // ─────────────────────────────────────────────────────────────
  // v5 OS-level 升级：反事实分析与决策回放
  // ─────────────────────────────────────────────────────────────

  /**
   * 反事实分析 — "如果 X 没发生 / 决策不同，会怎样？"
   *
   * v5 OS-level 关键能力：
   * 基于 span.explanation.alternatives_considered 进行假设性推理。
   *
   * 原则：Observability cannot mutate state
   *      反事实分析是"假设性推理"，不修改实际事件流
   *
   * @param trace_id            目标 trace
   * @param hypothetical_event_id 假设的事件 ID
   * @param hypothetical_decision 假设的决策（可选，不指定则假设该事件未发生）
   * @returns 反事实分析结果
   */
  async counterfactual(
    trace_id: string,
    hypothetical_event_id: string,
    hypothetical_decision?: string,
  ): Promise<CounterfactualAnalysis> {
    const analyzedAt = new Date().toISOString();

    // 1. 获取实际发生的决策
    const span = await observabilityStore.getSpanByEventId(hypothetical_event_id);
    const actualDecision = span?.decision?.enforcement_action ?? "EXECUTED";

    // 2. 获取实际因果路径
    const actualCausalPath = span?.causal_chain ?? [];

    // 3. 收集替代路径（反事实推演依据）
    const alternatives = span?.explanation?.alternatives_considered ?? [];

    // 4. 推演预期后果
    const projectedConsequence = this.projectConsequence(
      hypothetical_event_id,
      hypothetical_decision,
      actualDecision,
      alternatives,
    );

    // 5. 计算受影响的 span（如该决策不同，下游哪些 span 不会发生）
    const affectedSpans = await this.computeAffectedSpans(trace_id, hypothetical_event_id);

    // 6. 计算置信度（基于替代路径数据完整度）
    const confidence = this.computeCounterfactualConfidence(alternatives, actualCausalPath);

    return {
      trace_id,
      hypothetical_event_id,
      hypothetical_decision,
      actual_decision: actualDecision,
      actual_causal_path: actualCausalPath,
      projected_consequence: projectedConsequence,
      affected_spans: affectedSpans,
      based_on_alternatives: alternatives,
      confidence,
      analyzed_at: analyzedAt,
    };
  }

  /**
   * 决策回放 — 重放决策路径，可修改假设决策
   *
   * v5 OS-level 关键能力：
   * 给定 trace_id，重放所有决策，支持"如果某个决策不同"的假设重放。
   *
   * @param trace_id 目标 trace
   * @param overrideDecisions 决策覆盖（span_id → 假设决策）
   * @returns 决策回放结果
   */
  async replayDecisions(
    trace_id: string,
    overrideDecisions?: Map<string, string>,
  ): Promise<DecisionReplayResult> {
    const spans = await observabilityStore.getSpansByTraceId(trace_id);
    const override = overrideDecisions ?? new Map<string, string>();

    const replayedDecisions: DecisionReplayItem[] = [];
    let divergedAt: string | null = null;

    for (const span of spans) {
      const actualDecision = span.decision?.enforcement_action ?? "EXECUTED";
      const overridden = override.get(span.span_id);
      const finalDecision = overridden ?? actualDecision;

      // 检测偏离点
      if (overridden && overridden !== actualDecision && !divergedAt) {
        divergedAt = span.span_id;
      }

      replayedDecisions.push({
        span_id: span.span_id,
        event_id: span.event_id,
        actual_decision: actualDecision,
        replayed_decision: finalDecision,
        diverged: overridden !== undefined && overridden !== actualDecision,
        trigger_event_id: span.decision?.trigger_event_id,
        rules_matched: span.decision?.rule_matched ?? [],
        authority_level: span.decision?.authority_level ?? span.layer,
        timestamp: span.start_time,
      });
    }

    return {
      trace_id,
      replayed_decisions: replayedDecisions,
      diverged_at: divergedAt,
      total_decisions: replayedDecisions.length,
      divergence_count: replayedDecisions.filter((d) => d.diverged).length,
    };
  }

  /**
   * 推演预期后果 — 反事实推理核心
   */
  private projectConsequence(
    hypothetical_event_id: string,
    hypothetical_decision: string | undefined,
    actualDecision: string,
    alternatives: AlternativePath[],
  ): string {
    // 基于替代路径推演
    if (alternatives.length > 0) {
      const best = alternatives[0];
      if (hypothetical_decision) {
        return `If decision were "${hypothetical_decision}" instead of "${actualDecision}", ` +
          `the alternative path from ${best.source} would have produced "${best.proposed_decision}". ` +
          `Expected consequence: ${best.expected_consequence ?? "unknown"}`;
      }
      return `If event ${hypothetical_event_id} had not occurred, ` +
        `alternative "${best.alternative_id}" from ${best.source} would have been considered. ` +
        `Rejection reason for alternative: ${best.rejection_reason}`;
    }

    // 无替代路径数据，基础推演
    if (hypothetical_decision) {
      return `If decision were "${hypothetical_decision}" instead of "${actualDecision}", ` +
        `downstream execution would have diverged. (No alternatives_considered data for richer projection.)`;
    }

    return `If event ${hypothetical_event_id} had not occurred, ` +
      `downstream causal chain would have been broken. (No alternatives_considered data for richer projection.)`;
  }

  /**
   * 计算受影响的 span — 下游因果链
   */
  private async computeAffectedSpans(
    trace_id: string,
    root_event_id: string,
  ): Promise<string[]> {
    const spans = await observabilityStore.getSpansByTraceId(trace_id);
    const affected: string[] = [];
    const visited = new Set<string>();

    // 找到该事件的所有下游 span（causal_chain 中包含该 event_id 的 span）
    for (const span of spans) {
      if (span.causal_chain?.includes(root_event_id) && span.event_id !== root_event_id) {
        if (!visited.has(span.span_id)) {
          visited.add(span.span_id);
          affected.push(span.span_id);
        }
      }
    }

    return affected;
  }

  /**
   * 计算反事实分析置信度
   */
  private computeCounterfactualConfidence(
    alternatives: AlternativePath[],
    actualCausalPath: string[],
  ): number {
    let score = 0;

    // 替代路径数据越完整，置信度越高
    if (alternatives.length > 0) score += 0.4;
    if (alternatives.length >= 2) score += 0.2;
    if (alternatives.some((a) => a.expected_consequence)) score += 0.2;

    // 因果路径越完整，置信度越高
    if (actualCausalPath.length > 0) score += 0.1;
    if (actualCausalPath.length >= 3) score += 0.1;

    return Math.min(1, score);
  }
}

/**
 * 决策回放单项
 */
export interface DecisionReplayItem {
  span_id: string;
  event_id?: string;
  actual_decision: string;
  replayed_decision: string;
  diverged: boolean;
  trigger_event_id?: string;
  rules_matched: string[];
  authority_level: string;
  timestamp: string;
}

/**
 * 决策回放结果
 */
export interface DecisionReplayResult {
  trace_id: string;
  replayed_decisions: DecisionReplayItem[];
  /** 首次偏离点（span_id），如无偏离则为 null */
  diverged_at: string | null;
  total_decisions: number;
  divergence_count: number;
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const whyEngine = new WhyEngine();
