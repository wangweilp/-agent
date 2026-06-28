/**
 * 知维 OS Decision Policy Kernel — 纯评分内核（v6.1 核心抽象）
 * Zhiwei OS Decision Policy Kernel (DPC) (v6.1)
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
 * v6.1 核心跃迁：
 *   从 v6 的 "Phase-mixed Kernel"（control + scoring 混合）
 *   升级为 "OS-grade separation of concerns"
 *
 * v6 风险（已识别）：
 *   - DecisionEngine.evaluate() 同时做 control + scoring
 *   - PolicyWeights = hidden global state
 *   - feedback loop 无边界增长
 *
 * v6.1 修复：
 *   - DecisionPolicyKernel = pure scoring kernel（纯函数）
 *   - DecisionEngine = control flow only
 *   - DecisionFeedbackLoop = weights update only（不碰 Engine/Router）
 *
 * 纯函数契约：
 *   INPUT:  DecisionContext
 *   OUTPUT: DecisionScore (priority / confidence / cost / utility)
 *
 * ❗强约束：
 *   - DPC 不修改任何 state
 *   - DPC 不调用 Engine / Router / FeedbackLoop
 *   - DPC 只做计算（pure function）
 */

import type {
  AuthorityContext,
  DecisionNode,
} from "../types";
import type { SystemEvent } from "@/types/event-bus";

// ═══════════════════════════════════════════════════════════════
// 1️⃣ DecisionContext — DPC 输入（纯数据，无副作用）
// ═══════════════════════════════════════════════════════════════

/**
 * DecisionContext — DPC 的输入
 *
 * 严格按用户提示词定义
 *
 * ❗纯数据结构，不包含任何方法或副作用
 */
export interface DecisionContext {
  /** 待评估的事件 */
  event: SystemEvent;
  /** 权威上下文 */
  authority: AuthorityContext;
  /** 历史决策（可选，用于 scoring 上下文） */
  history?: DecisionNode[];
  /** 权重映射（可选，来自 PolicyWeightsManager） */
  weights?: Record<string, number>;
}

// ═══════════════════════════════════════════════════════════════
// 2️⃣ DecisionScore — DPC 输出（纯数据，无副作用）
// ═══════════════════════════════════════════════════════════════

/**
 * DecisionScore — DPC 的输出
 *
 * 严格按用户提示词定义
 *
 * ❗纯数据结构，DecisionEngine 基于此决定 control flow
 */
export interface DecisionScore {
  /** 优先级（0-1，数字越大优先级越高） */
  priority: number;
  /** 置信度（0-1，数字越大越可信） */
  confidence: number;
  /** 成本（0-1，数字越大成本越高） */
  cost: number;
  /** 效用（0-1，综合 priority + confidence 的效用分数） */
  utility: number;
}

// ═══════════════════════════════════════════════════════════════
// 3️⃣ DecisionPolicyKernel — 纯评分内核（v6.1 核心）
// ═══════════════════════════════════════════════════════════════

/**
 * DecisionPolicyKernel (DPC) — v6.1 核心抽象
 *
 * ═══════════════════════════════════════════════════════════════
 * OS INVARIANT (v6.1):
 *
 *   DecisionPolicyKernel = SCORING ONLY
 *
 *   ❌ NOT control flow
 *   ❌ NOT execution routing
 *   ❌ NOT state mutation
 *   ❌ NOT feedback learning
 *
 *   ✔ ONLY compute score
 * ═══════════════════════════════════════════════════════════════
 *
 * 纯函数契约：
 *   compute(context: DecisionContext): DecisionScore
 *
 * 同一 context 永远产生同一 score（确定性）
 */
export class DecisionPolicyKernel {
  /**
   * 计算决策评分（纯函数，无副作用）
   *
   * INPUT:  DecisionContext
   * OUTPUT: DecisionScore
   *
   * @param context 决策上下文（event + authority + history + weights）
   * @returns 评分结果（priority / confidence / cost / utility）
   */
  compute(context: DecisionContext): DecisionScore {
    const priority = this.computePriority(context);
    const confidence = this.computeConfidence(context);
    const cost = this.computeCost(context);
    const utility = this.computeUtility(context);

    return {
      priority,
      confidence,
      cost,
      utility,
    };
  }

  /**
   * 计算优先级（0-1）
   *
   * 算法：
   * - 基础优先级来自 weights.priority（默认 0.5）
   * - 如果 kill_switch_active，提升优先级到 1.0（紧急）
   * - 如果有历史决策，根据历史决策数微调
   *
   * ❗纯函数：相同输入永远产生相同输出
   */
  private computePriority(ctx: DecisionContext): number {
    // 基础优先级来自 weights
    let priority = ctx.weights?.priority ?? 0.5;

    // kill_switch 激活时强制最高优先级
    if (ctx.authority.kill_switch_active) {
      priority = 1.0;
      return priority;
    }

    // 历史决策数影响（越多历史 → 略微降低优先级，避免决策堆积）
    if (ctx.history && ctx.history.length > 0) {
      const historyPenalty = Math.min(ctx.history.length * 0.01, 0.1);
      priority = Math.max(0, priority - historyPenalty);
    }

    // clamp [0, 1]
    return Math.max(0, Math.min(1, priority));
  }

  /**
   * 计算置信度（0-1）
   *
   * 算法：
   * - 基础置信度来自 weights.confidence（默认 0.5）
   * - 如果有 active_policies，每个 policy 增加 0.05 置信度（最多 +0.2）
   * - 如果有历史决策，根据历史成功率调整
   *
   * ❗纯函数：相同输入永远产生相同输出
   */
  private computeConfidence(ctx: DecisionContext): number {
    // 基础置信度来自 weights
    let confidence = ctx.weights?.confidence ?? 0.5;

    // active_policies 增加置信度（最多 +0.2）
    if (ctx.authority.active_policies.length > 0) {
      const policyBonus = Math.min(ctx.authority.active_policies.length * 0.05, 0.2);
      confidence += policyBonus;
    }

    // 历史决策成功率影响置信度
    if (ctx.history && ctx.history.length > 0) {
      const committed = ctx.history.filter((d) => d.state === "COMMITTED").length;
      const successRate = committed / ctx.history.length;

      // 成功率高 → 略微提升置信度；成功率低 → 略微降低
      const historyAdjust = (successRate - 0.5) * 0.2; // [-0.1, +0.1]
      confidence += historyAdjust;
    }

    // clamp [0, 1]
    return Math.max(0, Math.min(1, confidence));
  }

  /**
   * 计算成本（0-1）
   *
   * 算法：
   * - 基础成本来自 weights.cost（默认 0.5）
   * - 成本是反向指标（cost 越高 → 执行越昂贵）
   * - 返回值：1 - weights.cost（使 cost 与 priority/confidence 同向）
   *
   * ❗纯函数：相同输入永远产生相同输出
   */
  private computeCost(ctx: DecisionContext): number {
    // 成本是反向指标（1 - weight）
    // weights.cost = 0.8（高成本） → 返回 0.2（低效用）
    // weights.cost = 0.2（低成本） → 返回 0.8（高效用）
    return 1 - (ctx.weights?.cost ?? 0.5);
  }

  /**
   * 计算效用（0-1）
   *
   * 算法：
   * - utility = (priority + confidence) / 2
   * - 简单平均，表示决策的综合效用
   *
   * ❗纯函数：相同输入永远产生相同输出
   */
  private computeUtility(ctx: DecisionContext): number {
    const priority = this.computePriority(ctx);
    const confidence = this.computeConfidence(ctx);
    return (priority + confidence) / 2;
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const decisionPolicyKernel = new DecisionPolicyKernel();
