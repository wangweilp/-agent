/**
 * 知维 OS Decision Engine — 运行时决策引擎（v6.1 严格版）
 * Zhiwei OS Decision Engine (v6.1)
 *
 * ═══════════════════════════════════════════════════════════════
 * OS INVARIANT (v6.1):
 *
 *   DecisionEngine        = CONTROL ONLY（是否执行）
 *   DecisionPolicyKernel  = SCORING ONLY（如何排序）
 *
 *   DO NOT MIX.
 * ═══════════════════════════════════════════════════════════════
 *
 * v6 → v6.1 跃迁：
 *   v6:   evaluate() 同时做 control + scoring（Phase-mixed Kernel）
 *   v6.1: evaluate() 拆分为两步：
 *           STEP 1 — SCORING ONLY（委托 DPC，pure function）
 *           STEP 2 — CONTROL FLOW ONLY（基于 score 决定 commit/reject/defer）
 *
 * 严格按用户提示词实现：
 *
 *   evaluate(event, context) {
 *     // STEP 1 — SCORING ONLY (DPC)
 *     const score = this.policyKernel.compute({...});
 *
 *     // STEP 2 — CONTROL FLOW ONLY
 *     if (score.confidence < 0.2) return this.reject(event, score);
 *     if (score.priority  < 0.3) return this.defer(event, score);
 *     return this.commit(event, score);
 *   }
 *
 * ❗强约束：
 *   - DecisionEngine 不直接计算 priority/confidence/cost（已委托 DPC）
 *   - DecisionEngine 只负责 state machine 转移 + commit/reject/override
 *   - DPC 不修改任何 state（pure function）
 */

import type {
  DecisionNode,
  DecisionRule,
  DecisionEngineOptions,
  RuntimeContext,
} from "./types";
import type { SystemEvent } from "@/types/event-bus";
import { DecisionStateMachine } from "./decision-state-machine";
import {
  DecisionPolicyKernel,
  type DecisionContext,
  type DecisionScore,
} from "./policy/decision-policy-kernel";

// ═══════════════════════════════════════════════════════════════
// 默认配置
// ═══════════════════════════════════════════════════════════════

const DEFAULT_OPTIONS: DecisionEngineOptions = {
  decision_ttl_ms: 30_000,
  enable_meta_decision: true,
  meta_decision_threshold: 0.5,
  max_active_per_trace: 100,
};

// ═══════════════════════════════════════════════════════════════
// DecisionEngine — v6.1 运行时决策引擎（CONTROL ONLY）
// ═══════════════════════════════════════════════════════════════

/**
 * DecisionEngine — v6.1 运行时决策引擎
 *
 * ═══════════════════════════════════════════════════════════════
 * OS INVARIANT (v6.1):
 *
 *   DecisionEngine = CONTROL ONLY
 *
 *   ❌ NOT scoring (DPC 负责)
 *   ❌ NOT execution routing (ExecutionRouter 负责)
 *   ❌ NOT policy weight adjustment (DecisionFeedbackLoop 负责)
 *
 *   ✔ ONLY control flow:
 *        - 规则匹配（产生 actions/triggers/blocks，用于 routing 配置）
 *        - state machine 转移（PENDING → EVALUATING → COMMITTED/REJECTED）
 *        - TTL 检查（EXPIRED）
 *        - override / reject（COMMITTED → OVERRIDDEN / EVALUATING → REJECTED）
 * ═══════════════════════════════════════════════════════════════
 *
 * 评分委托：
 *   const score = this.policyKernel.compute(context);
 *   // score.priority / confidence / cost / utility
 */
export class DecisionEngine {
  /** 决策状态机（确定性，控制平面核心） */
  private stateMachine: DecisionStateMachine;
  /** 策略评分内核（v6.1 抽象，pure scoring function） */
  private policyKernel: DecisionPolicyKernel;
  /** 决策规则列表（用于匹配 actions/triggers/blocks，不参与 scoring） */
  private rules: DecisionRule[] = [];
  /** 所有决策（decision_id → DecisionNode） */
  private decisions: Map<string, DecisionNode> = new Map();
  /** trace_id → decision_ids 索引 */
  private traceIndex: Map<string, string[]> = new Map();
  /** 引擎配置 */
  private options: DecisionEngineOptions;

  constructor(options?: Partial<DecisionEngineOptions>) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.stateMachine = new DecisionStateMachine();
    this.policyKernel = new DecisionPolicyKernel();
  }

  // ═══════════════════════════════════════════════════════════════
  // 核心 API 1：evaluate — v6.1 拆分版（CONTROL + SCORING 分离）
  // ═══════════════════════════════════════════════════════════════

  /**
   * 评估事件并生成决策（v6.1 核心实现）
   *
   * ═══════════════════════════════════════════════════════════════
   * OS INVARIANT (v6.1):
   *
   *   STEP 1 — SCORING ONLY（委托 DPC，pure function）
   *   STEP 2 — CONTROL FLOW ONLY（基于 score 决定 commit/reject/defer）
   * ═══════════════════════════════════════════════════════════════
   *
   * @param event 待评估的事件
   * @param context 运行时上下文
   * @returns 生成的决策（COMMITTED / REJECTED / EXPIRED）
   */
  evaluate(event: SystemEvent, context: RuntimeContext): DecisionNode {
    // 1. 规则匹配（用于 actions / triggers / blocks 配置，不参与 scoring）
    const matchedRule = this.matchRule(event, context);

    // 2. 生成 DecisionNode (PENDING)
    const pending = this.createDecisionFromRule(event, context, matchedRule);
    this.storeDecision(pending);

    // 3. PENDING → EVALUATING（state machine 控制）
    const evaluating = this.stateMachine.transition(pending, "EVALUATING");
    this.decisions.set(evaluating.decision_id, evaluating);

    // 4. TTL 检查（CONTROL FLOW 的一部分，非 scoring）
    const age = Date.now() - evaluating.created_at;
    if (age > this.options.decision_ttl_ms) {
      const expired = this.stateMachine.transition(evaluating, "EXPIRED");
      this.decisions.set(expired.decision_id, expired);
      return expired;
    }

    // ───────────────────────────────────────────────────────────
    // STEP 1 — SCORING ONLY（委托 DPC，pure function）
    // ───────────────────────────────────────────────────────────
    const decisionContext: DecisionContext = {
      event,
      authority: context.authority,
      history: this.getDecisionsByTrace(event.trace_id),
      weights: this.extractWeightsFromContext(context),
    };
    const score = this.policyKernel.compute(decisionContext);

    // ───────────────────────────────────────────────────────────
    // STEP 2 — CONTROL FLOW ONLY（基于 score 决定 control flow）
    // ───────────────────────────────────────────────────────────
    let final: DecisionNode;
    if (score.confidence < 0.2) {
      // 低置信度 → REJECTED
      final = this.rejectInternal(
        evaluating,
        score,
        `confidence ${score.confidence.toFixed(3)} < 0.2`,
      );
    } else if (score.priority < 0.3) {
      // 低优先级 → REJECTED (deferred)
      // 注：用户提示词中 defer 在 6 状态机中等同于 REJECTED（无 DEFERRED 状态）
      final = this.rejectInternal(
        evaluating,
        score,
        `priority ${score.priority.toFixed(3)} < 0.3 (deferred)`,
      );
    } else {
      // 通过 → COMMITTED
      final = this.commitInternal(evaluating, score);
    }

    this.decisions.set(final.decision_id, final);
    return final;
  }

  // ═══════════════════════════════════════════════════════════════
  // 核心 API 2：commit / reject / override — CONTROL FLOW
  // ═══════════════════════════════════════════════════════════════

  /**
   * 提交决策（EVALUATING → COMMITTED）
   *
   * CONTROL FLOW：基于 DPC score 更新决策并应用状态转移
   *
   * @param decision_id 决策 ID
   * @returns 更新后的决策（COMMITTED），如不存在返回 null
   */
  commit(decision_id: string): DecisionNode | null {
    const decision = this.decisions.get(decision_id);
    if (!decision) return null;

    if (decision.state !== "EVALUATING" && decision.state !== "PENDING") {
      return decision; // 非法转移，state machine 会拒绝
    }

    // 重新评分（保证 commit 时使用最新 score）
    const score = this.policyKernel.compute({
      event: decision.input_event,
      authority: decision.policy_context,
      history: this.getDecisionsByTrace(decision.trace_id),
      weights: this.extractWeightsFromContext({
        authority: decision.policy_context,
        blocked_paths: [],
        active_decision_count: 0,
        metadata: {},
      }),
    });

    const committed = this.commitInternal(decision, score);
    this.decisions.set(committed.decision_id, committed);
    return committed;
  }

  /**
   * 拒绝决策（EVALUATING → REJECTED）
   *
   * @param decision_id 决策 ID
   * @param reason 拒绝原因
   * @returns 更新后的决策（REJECTED），如不存在返回 null
   */
  reject(decision_id: string, reason?: string): DecisionNode | null {
    const decision = this.decisions.get(decision_id);
    if (!decision) return null;

    // 保留原 score（reject 不需要重新评分）
    const score: DecisionScore = {
      priority: decision.priority,
      confidence: decision.confidence,
      cost: decision.cost,
      utility: (decision.priority + decision.confidence) / 2,
    };

    const rejected = this.rejectInternal(
      decision,
      score,
      reason ?? "rejected by external call",
    );
    this.decisions.set(rejected.decision_id, rejected);
    return rejected;
  }

  /**
   * 覆盖决策（COMMITTED → OVERRIDDEN）
   *
   * @param decision_id 决策 ID
   * @param reason 覆盖原因
   * @returns 更新后的决策（OVERRIDDEN），如不存在返回 null
   */
  override(decision_id: string, reason: string): DecisionNode | null {
    const decision = this.decisions.get(decision_id);
    if (!decision) return null;

    if (!this.stateMachine.canOverride(decision.state)) {
      return decision;
    }

    const overridden = this.stateMachine.transition(decision, "OVERRIDDEN");
    overridden.override_reason = reason;
    this.decisions.set(overridden.decision_id, overridden);
    return overridden;
  }

  // ═══════════════════════════════════════════════════════════════
  // 核心 API 3：规则管理
  // ═══════════════════════════════════════════════════════════════

  /**
   * 注册规则
   */
  registerRule(rule: DecisionRule): void {
    this.rules.push(rule);
  }

  /**
   * 批量注册规则
   */
  registerRules(rules: DecisionRule[]): void {
    for (const rule of rules) {
      this.rules.push(rule);
    }
  }

  /**
   * 获取所有规则
   */
  getRules(): DecisionRule[] {
    return [...this.rules];
  }

  // ═══════════════════════════════════════════════════════════════
  // 核心 API 4：查询
  // ═══════════════════════════════════════════════════════════════

  /**
   * 获取决策
   */
  getDecision(decision_id: string): DecisionNode | undefined {
    return this.decisions.get(decision_id);
  }

  /**
   * 获取 trace 关联的所有决策
   */
  getDecisionsByTrace(trace_id: string): DecisionNode[] {
    const ids = this.traceIndex.get(trace_id) ?? [];
    return ids
      .map((id) => this.decisions.get(id))
      .filter((d): d is DecisionNode => d !== undefined);
  }

  /**
   * 获取活跃决策（COMMITTED 状态）
   */
  getActiveDecisions(trace_id: string): DecisionNode[] {
    return this.getDecisionsByTrace(trace_id).filter((d) => d.state === "COMMITTED");
  }

  /**
   * 获取所有决策
   */
  getAllDecisions(): DecisionNode[] {
    return Array.from(this.decisions.values());
  }

  /**
   * 获取策略评分内核（v6.1 新增）
   *
   * 用于外部访问 DPC（如 FeedbackLoop 调整 weights 后通知 DPC）
   */
  getPolicyKernel(): DecisionPolicyKernel {
    return this.policyKernel;
  }

  /**
   * 获取状态机
   */
  getStateMachine(): DecisionStateMachine {
    return this.stateMachine;
  }

  /**
   * 获取引擎统计
   */
  getStats() {
    const all = this.getAllDecisions();
    return {
      total: all.length,
      by_state: {
        PENDING: all.filter((d) => d.state === "PENDING").length,
        EVALUATING: all.filter((d) => d.state === "EVALUATING").length,
        COMMITTED: all.filter((d) => d.state === "COMMITTED").length,
        REJECTED: all.filter((d) => d.state === "REJECTED").length,
        OVERRIDDEN: all.filter((d) => d.state === "OVERRIDDEN").length,
        EXPIRED: all.filter((d) => d.state === "EXPIRED").length,
      },
      by_trace: this.traceIndex.size,
      rules_count: this.rules.length,
    };
  }

  /**
   * 清空所有状态（用于测试）
   */
  clear(): void {
    this.decisions.clear();
    this.traceIndex.clear();
  }

  // ═══════════════════════════════════════════════════════════════
  // 内部辅助方法（CONTROL FLOW ONLY）
  // ═══════════════════════════════════════════════════════════════

  /**
   * 提交决策内部实现（CONTROL FLOW）
   *
   * - 应用状态转移 EVALUATING → COMMITTED
   * - 写入 DPC score（priority/confidence/cost）
   * - 设置 committed_at
   */
  private commitInternal(
    decision: DecisionNode,
    score: DecisionScore,
  ): DecisionNode {
    const committed = this.stateMachine.transition(decision, "COMMITTED");
    // 写入 DPC score（保留评分来源）
    committed.priority = score.priority;
    committed.confidence = score.confidence;
    committed.cost = score.cost;
    return committed;
  }

  /**
   * 拒绝决策内部实现（CONTROL FLOW）
   *
   * - 应用状态转移 EVALUATING → REJECTED
   * - 写入 DPC score（保留评分来源，便于 audit）
   * - 设置 rejection_reason
   */
  private rejectInternal(
    decision: DecisionNode,
    score: DecisionScore,
    reason: string,
  ): DecisionNode {
    const rejected = this.stateMachine.transition(decision, "REJECTED");
    // 写入 DPC score（即使拒绝也保留评分，便于 audit）
    rejected.priority = score.priority;
    rejected.confidence = score.confidence;
    rejected.cost = score.cost;
    rejected.rejection_reason = reason;
    return rejected;
  }

  /**
   * 匹配规则（CONTROL FLOW）
   *
   * 找到第一个匹配的规则（按 priority 降序），返回其 actions/triggers/blocks
   *
   * ❗此方法只产生 control plane 配置（actions/triggers/blocks），不参与 scoring
   *   scoring 完全由 DPC 负责
   */
  private matchRule(
    event: SystemEvent,
    context: RuntimeContext,
  ): DecisionRule | null {
    // 按 priority 降序排序
    const sortedRules = [...this.rules]
      .filter((r) => r.enabled)
      .sort((a, b) => b.priority - a.priority);

    for (const rule of sortedRules) {
      // 事件类型匹配
      if (
        rule.event_types.length > 0 &&
        !rule.event_types.includes(event.type)
      ) {
        continue;
      }

      // 谓词匹配
      try {
        if (rule.predicate(event, context)) {
          return rule;
        }
      } catch {
        // 谓词异常，跳过该规则
        continue;
      }
    }

    return null;
  }

  /**
   * 从规则创建决策（CONTROL FLOW）
   *
   * 创建 PENDING 状态的 DecisionNode，包含：
   * - 规则产生的 actions/triggers/blocks（control plane 配置）
   * - 初始 score 为默认值（实际 score 在 evaluate() 中由 DPC 计算）
   */
  private createDecisionFromRule(
    event: SystemEvent,
    context: RuntimeContext,
    rule: DecisionRule | null,
  ): DecisionNode {
    const now = Date.now();
    return {
      decision_id: this.generateDecisionId(event),
      trace_id: event.trace_id,
      state: "PENDING",
      input_event: event,
      policy_context: context.authority,
      // 初始 score（DPC 将在 evaluate() 中重新计算）
      confidence: 0,
      priority: 0,
      cost: 0,
      // 规则产生的 control plane 配置
      actions: rule?.actions ?? ["ALLOW"],
      triggers: rule?.triggers,
      blocks: rule?.blocks,
      // lifecycle
      created_at: now,
      // audit
      source: rule?.source ?? "default",
      rule_id: rule?.rule_id,
    };
  }

  /**
   * 存储决策并更新索引
   */
  private storeDecision(decision: DecisionNode): void {
    this.decisions.set(decision.decision_id, decision);
    const ids = this.traceIndex.get(decision.trace_id) ?? [];
    ids.push(decision.decision_id);
    this.traceIndex.set(decision.trace_id, ids);
  }

  /**
   * 从 RuntimeContext 提取 weights 映射（用于 DPC 输入）
   *
   * 当前实现：从 context.metadata.weights 提取（如有）
   * 未来可扩展为从 PolicyWeightsManager 提取
   */
  private extractWeightsFromContext(
    context: RuntimeContext,
  ): Record<string, number> | undefined {
    const weights = (context.metadata as { weights?: Record<string, number> }).weights;
    return weights;
  }

  /**
   * 生成决策 ID
   */
  private generateDecisionId(event: SystemEvent): string {
    return `dec-${event.trace_id}-${Date.now()}-${Math.random()
      .toString(36)
      .slice(2, 8)}`;
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const decisionEngine = new DecisionEngine();
