/**
 * 知维 OS Decision Feedback Loop — 自演化核心（v6.1 严格版）
 * Zhiwei OS Decision Feedback Loop (v6.1)
 *
 * ═══════════════════════════════════════════════════════════════
 * OS INVARIANT (v6.1):
 *
 *   DecisionFeedbackLoop = WEIGHTS UPDATE ONLY
 *
 *   ❌ NOT control flow（不调用 DecisionEngine.commit/reject/override）
 *   ❌ NOT execution routing（不调用 ExecutionRouter.route）
 *   ❌ NOT scoring（不调用 DecisionPolicyKernel.compute）
 *   ❌ NOT state mutation of DecisionNode
 *
 *   ✔ ONLY modifies:
 *        PolicyWeightsManager.weights
 *        PolicyWeightsManager.history
 * ═══════════════════════════════════════════════════════════════
 *
 * 严格按用户提示词：
 *   🔁 核心机制：Decision outcome → modifies future decision scoring
 *
 *   class DecisionFeedbackLoop {
 *     update(decision: DecisionNode, outcome: ExecutionResult): void {
 *       PolicyWeights.adjust(decision.policy_context, outcome);
 *     }
 *   }
 *
 * v6.1 边界规则：
 *   FeedbackLoop 只修改 PolicyKernel.weights
 *   不修改 DecisionEngine（不调 commit/reject/override）
 *   不修改 ExecutionRouter（不调 route/unblock）
 *
 * v6 核心：Decision influences future decisions
 *   feedback loop exists
 *
 * 自演化机制：
 *   1. Decision COMMITTED → 执行 → ExecutionResult
 *   2. DecisionFeedbackLoop.update(decision, outcome)
 *   3. PolicyWeights.adjust(policy_context, outcome)
 *   4. 后续 evaluate() 时，weights 通过 DecisionContext 传入 DPC，影响 scoring
 *
 * ❗强约束：不依赖 observability layer / graph / explanation / WHY
 */

import type { DecisionNode, ExecutionResult, PolicyWeights, AuthorityContext } from "./types";
import type { StabilityEnforcementResult } from "./policy/decision-stability-kernel";
import {
  DecisionStabilityKernel,
  decisionStabilityKernel,
} from "./policy/decision-stability-kernel";

// ═══════════════════════════════════════════════════════════════
// PolicyWeightsManager — 策略权重管理器
// ═══════════════════════════════════════════════════════════════

/**
 * PolicyWeightsManager — 策略权重管理器
 *
 * 职责：
 * - 存储 policy_id → weight 映射
 * - 根据 ExecutionResult 调整权重
 * - 提供权重查询（用于规则 confidence 调整）
 *
 * 自演化核心算法：
 * - success=true  → weight +0.05（最多 1.0）
 * - success=false → weight -0.10（最少 0.0）
 * - 边界 clamp 在 [0, 1]
 *
 * ═══════════════════════════════════════════════════════════════
 * v6.2 增量（add-only, backward compatible）：
 *
 *   所有 weight update 必须经过 DecisionStabilityKernel (DSK)：
 *     raw_delta → DSK.enforce() → final_weight
 *
 *   DSK 提供：
 *     - Delta bounding   (|Δ| ≤ 0.1)
 *     - Weight clamp      (weight ∈ [0, 1])
 *     - Drift detection   (滑动窗口单向漂移检测)
 *     - Mean reversion    (漂移时向 0.5 衰减)
 *
 *   向后兼容：
 *     - v6.1 行为 = DSK disabled (max_delta=∞, enable_drift_damping=false)
 *     - v6.2 默认 = DSK enabled (DEFAULT_STABILITY_CONFIG)
 * ═══════════════════════════════════════════════════════════════
 *
 * ❗确定性：相同输入永远产生相同输出（含 DSK 路径，DSK 也是 pure function）
 */
export class PolicyWeightsManager {
  /** 策略权重（policy_id → weight） */
  private weights: Map<string, number> = new Map();
  /** 调整历史（用于 audit） */
  private history: PolicyWeights["adjustment_history"] = [];
  /**
   * 稳定性内核（v6.2 新增）
   *
   * 默认使用全局单例 decisionStabilityKernel，
   * 可通过 setStabilityKernel() 替换为自定义配置（用于测试 / 调优）。
   *
   * ❗DSK 是 pure function，无内部 state，故共享单例不会引入 state 污染。
   */
  private stabilityKernel: DecisionStabilityKernel;

  constructor(stabilityKernel?: DecisionStabilityKernel) {
    this.stabilityKernel = stabilityKernel ?? decisionStabilityKernel;
  }

  /**
   * 设置稳定性内核（v6.2 新增，add-only）
   *
   * 用于运行时切换 DSK 配置（例如测试场景下禁用 dampening）。
   *
   * @param kernel 新的 DSK 实例（传 null 时回退到全局单例）
   */
  setStabilityKernel(kernel: DecisionStabilityKernel | null): void {
    this.stabilityKernel = kernel ?? decisionStabilityKernel;
  }

  /**
   * 获取当前稳定性内核（用于 audit）
   */
  getStabilityKernel(): DecisionStabilityKernel {
    return this.stabilityKernel;
  }

  /**
   * 获取策略权重
   *
   * @param policy_id 策略 ID
   * @returns 权重（0-1，默认 0.5）
   */
  getWeight(policy_id: string): number {
    return this.weights.get(policy_id) ?? 0.5;
  }

  /**
   * 设置策略权重
   *
   * v6.2 增量：通过 DSK.clampWeight() 应用稳定性边界
   *
   * 向后兼容：
   *   - v6.1 硬编码 clamp [0, 1]
   *   - v6.2 通过 DSK config clamp（默认仍为 [0, 1]，行为一致）
   *   - 仅当 DSK config 被显式覆盖时行为才不同
   */
  setWeight(policy_id: string, weight: number): void {
    const clamped = this.stabilityKernel.clampWeight(weight);
    this.weights.set(policy_id, clamped);
  }

  /**
   * 调整策略权重（核心 API，严格按用户提示词）
   *
   * 自演化算法（v6.1 基础 reward signal）：
   * - success=true  → raw_delta = +0.05
   * - success=false → raw_delta = -0.10
   *
   * ═══════════════════════════════════════════════════════════════
   * v6.2 增量（add-only）：
   *
   *   raw_delta 不再直接应用，而是经过 DSK.enforce()：
   *
   *     raw_delta
   *       ↓
   *     DSK.boundDelta()       → bounded_delta (|Δ| ≤ max_delta)
   *       ↓
   *     DSK.clampWeight()      → clamped_weight ∈ [min, max]
   *       ↓
   *     DSK.detectDrift()      → drift_result
   *       ↓
   *     [if drift] DSK.applyMeanReversion() → reverted_weight
   *       ↓
   *     DSK.clampWeight() (二次) → final_weight
   *
   *   稳定性保证（OS-grade）：
   *     |applied_delta| ≤ max_delta (default 0.1)
   *     weight_min ≤ final_weight ≤ weight_max (default [0, 1])
   *     drift_dampened 时 final_weight 向 mean_reversion_target 收敛
   *
   *   向后兼容：
   *     - v6.1 delta = -0.10 → v6.2 bounded_delta = -0.10（仍在 [-0.1, 0.1] 范围内）
   *     - v6.1 weight clamp [0,1] → v6.2 保留
   *     - v6.1 无 drift detection → v6.2 新增（默认 enabled，可禁用）
   * ═══════════════════════════════════════════════════════════════
   *
   * @param authority 权威上下文（包含 active_policies）
   * @param outcome 执行结果
   */
  adjust(authority: AuthorityContext, outcome: ExecutionResult): void {
    // 遍历 authority 中的 active_policies，调整权重
    for (const policy_id of authority.active_policies) {
      const oldWeight = this.getWeight(policy_id);

      // STEP 1: 计算 raw_delta（v6.1 基础 reward signal）
      const raw_delta = outcome.success ? 0.05 : -0.10;

      // STEP 2: DSK enforcement（v6.2 新增，bounded + clamp + drift detection + mean reversion）
      const stabilityResult: StabilityEnforcementResult =
        this.stabilityKernel.enforce({
          policy_id,
          old_weight: oldWeight,
          raw_delta,
          history: this.history, // 当前历史快照（用于 drift detection）
        });

      const newWeight = stabilityResult.final_weight;

      // STEP 3: 写入 weight
      this.weights.set(policy_id, newWeight);

      // STEP 4: 记录调整历史（v6.2 reason 升级为 DSK 完整 audit trail）
      this.history.push({
        policy_id,
        old_weight: oldWeight,
        new_weight: newWeight,
        reason: this.buildAdjustReason(outcome, raw_delta, stabilityResult),
        adjusted_at: Date.now(),
      });
    }
  }

  /**
   * 构建 adjust history 的 reason 字段（v6.2 新增）
   *
   * 格式（向后兼容 v6.1 reason 字符串前缀）：
   *   "execution success (+0.05) | DSK: delta bounded: 0.05 → 0.05; weight clamped: ..."
   *
   * @param outcome 执行结果
   * @param raw_delta 原始 delta
   * @param stabilityResult DSK 输出
   * @returns 合并后的 reason 字符串
   */
  private buildAdjustReason(
    outcome: ExecutionResult,
    raw_delta: number,
    stabilityResult: StabilityEnforcementResult,
  ): string {
    const v61Prefix = outcome.success
      ? `execution success (${raw_delta >= 0 ? "+" : ""}${raw_delta})`
      : `execution failed: ${outcome.error ?? "unknown"} (${raw_delta})`;

    const v62Suffix = ` | DSK: ${stabilityResult.reason}${
      stabilityResult.drift_dampened
        ? ` [DRIFT DAMPENED: ${stabilityResult.drift_direction}, ratio=${stabilityResult.drift_ratio?.toFixed(2)}]`
        : ""
    }`;

    return v61Prefix + v62Suffix;
  }

  /**
   * 批量调整（多个决策同时影响）
   */
  adjustBatch(
    adjustments: Array<{ authority: AuthorityContext; outcome: ExecutionResult }>,
  ): void {
    for (const { authority, outcome } of adjustments) {
      this.adjust(authority, outcome);
    }
  }

  /**
   * 获取所有权重
   */
  getAllWeights(): Map<string, number> {
    return new Map(this.weights);
  }

  /**
   * 获取调整历史
   */
  getHistory(): PolicyWeights["adjustment_history"] {
    return [...this.history];
  }

  /**
   * 获取 PolicyWeights 快照
   */
  getSnapshot(): PolicyWeights {
    return {
      weights: new Map(this.weights),
      adjustment_history: [...this.history],
    };
  }

  /**
   * 全局权重归一化（v6.2 新增，add-only）
   *
   * 定期调用（例如每 N 次调整），通过 DSK.normalizeWeights()
   * 对全量 weights 做 clamp + 软压缩，防止全局分布失衡。
   *
   * 调用时机建议：
   *   - 每 100 次 adjust() 调用一次
   *   - 系统空闲时调用
   *   - 不在 adjust() 内部自动触发（避免影响 adjust 性能）
   *
   * ❗不修改 history，仅修改 weights
   */
  normalizeWeights(): void {
    const normalized = this.stabilityKernel.normalizeWeights(this.weights);
    this.weights = normalized;
  }

  /**
   * 稳定性审计（v6.2 新增，add-only, read-only）
   *
   * 返回每个 policy 的当前 weight + drift 状态，不修改任何东西。
   */
  auditStability(): Array<{
    policy_id: string;
    weight: number;
    drift: { drift_detected: boolean; drift_direction?: "up" | "down"; drift_ratio?: number };
  }> {
    return this.stabilityKernel.auditStability({
      weights: this.weights,
      history: this.history,
    });
  }

  /**
   * 清空（用于测试）
   */
  clear(): void {
    this.weights.clear();
    this.history = [];
  }
}

// ═══════════════════════════════════════════════════════════════
// DecisionFeedbackLoop — 自演化核心（v6 核心）
// ═══════════════════════════════════════════════════════════════

/**
 * DecisionFeedbackLoop — v6.1 自演化核心
 *
 * ═══════════════════════════════════════════════════════════════
 * OS INVARIANT (v6.1):
 *
 *   DecisionFeedbackLoop = WEIGHTS UPDATE ONLY
 *
 *   ❌ NOT control flow（不调用 DecisionEngine）
 *   ❌ NOT execution routing（不调用 ExecutionRouter）
 *   ❌ NOT scoring（不调用 DecisionPolicyKernel）
 *
 *   ✔ ONLY modifies:
 *        PolicyWeightsManager.weights
 *        PolicyWeightsManager.history
 * ═══════════════════════════════════════════════════════════════
 *
 * 严格按用户提示词：
 *   class DecisionFeedbackLoop {
 *     update(decision: DecisionNode, outcome: ExecutionResult): void {
 *       PolicyWeights.adjust(decision.policy_context, outcome);
 *     }
 *   }
 *
 * 自演化机制：
 *   Decision outcome → modifies PolicyWeights → affects future decision scoring
 *
 * 这是 v6 与 v5 的本质区别之一：
 * - v5: 单向系统（Event → Decision → Trace）
 * - v6: 反馈系统（Decision → outcome → PolicyWeights → next Decision）
 *
 * v6.1 边界：
 *   FeedbackLoop 只通过 PolicyWeightsManager 调整 weights，
 *   不直接修改 DecisionEngine 状态或 ExecutionRouter 路由。
 *   后续 evaluate() 时，weights 通过 DecisionContext 传入 DPC，
 *   DPC pure function 基于新 weights 计算 score。
 */
export class DecisionFeedbackLoop {
  private weightsManager: PolicyWeightsManager;

  constructor(weightsManager?: PolicyWeightsManager) {
    this.weightsManager = weightsManager ?? new PolicyWeightsManager();
  }

  /**
   * 更新（核心 API，严格按用户提示词）
   *
   * ═══════════════════════════════════════════════════════════════
   * OS INVARIANT (v6.1):
   *   此方法 ONLY 调用 PolicyWeightsManager.adjust()，不触碰：
   *   - DecisionEngine.commit/reject/override
   *   - ExecutionRouter.route
   *   - DecisionPolicyKernel.compute
   * ═══════════════════════════════════════════════════════════════
   *
   * @param decision 已执行的决策
   * @param outcome 执行结果
   *
   * 副作用：PolicyWeightsManager.adjust(decision.policy_context, outcome)
   *         → 修改 weights + 写入 history
   */
  update(decision: DecisionNode, outcome: ExecutionResult): void {
    // v6.1 硬边界：ONLY 调整 weights，不调用 Engine/Router/DPC
    this.weightsManager.adjust(decision.policy_context, outcome);
  }

  /**
   * 批量更新
   */
  updateBatch(
    updates: Array<{ decision: DecisionNode; outcome: ExecutionResult }>,
  ): void {
    for (const { decision, outcome } of updates) {
      this.update(decision, outcome);
    }
  }

  /**
   * 获取策略权重管理器
   */
  getWeightsManager(): PolicyWeightsManager {
    return this.weightsManager;
  }

  /**
   * 获取策略权重（便捷 API）
   *
   * 用于 DecisionEngine 规则 confidence 调整：
   *   const weight = feedbackLoop.getWeight(policy_id);
   *   const adjustedConfidence = rule.confidence(event, context) * weight;
   */
  getWeight(policy_id: string): number {
    return this.weightsManager.getWeight(policy_id);
  }

  /**
   * 获取 PolicyWeights 快照
   */
  getSnapshot(): PolicyWeights {
    return this.weightsManager.getSnapshot();
  }

  /**
   * 获取调整历史
   */
  getHistory(): PolicyWeights["adjustment_history"] {
    return this.weightsManager.getHistory();
  }

  /**
   * 清空（用于测试）
   */
  clear(): void {
    this.weightsManager.clear();
  }

  // ═══════════════════════════════════════════════════════════════
  // v6.2 Stability Kernel 代理方法（add-only, backward compatible）
  // ═══════════════════════════════════════════════════════════════

  /**
   * 设置稳定性内核（v6.2 新增）
   *
   * 代理到 PolicyWeightsManager.setStabilityKernel()，
   * 用于运行时切换 DSK 配置（例如测试场景下禁用 dampening）。
   *
   * @param kernel 新的 DSK 实例（传 null 时回退到全局单例）
   */
  setStabilityKernel(kernel: DecisionStabilityKernel | null): void {
    this.weightsManager.setStabilityKernel(kernel);
  }

  /**
   * 获取稳定性内核（v6.2 新增，用于 audit）
   */
  getStabilityKernel(): DecisionStabilityKernel {
    return this.weightsManager.getStabilityKernel();
  }

  /**
   * 全局权重归一化（v6.2 新增）
   *
   * 代理到 PolicyWeightsManager.normalizeWeights()，
   * 定期调用以防止全局分布失衡。
   */
  normalizeWeights(): void {
    this.weightsManager.normalizeWeights();
  }

  /**
   * 稳定性审计（v6.2 新增, read-only）
   *
   * 代理到 PolicyWeightsManager.auditStability()，
   * 返回每个 policy 的当前 weight + drift 状态。
   */
  auditStability(): ReturnType<PolicyWeightsManager["auditStability"]> {
    return this.weightsManager.auditStability();
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const policyWeightsManager = new PolicyWeightsManager();
export const decisionFeedbackLoop = new DecisionFeedbackLoop(policyWeightsManager);
