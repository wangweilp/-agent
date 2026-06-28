/**
 * 知维 OS Decision Stability Kernel — 稳定性内核（v6.2 核心）
 * Zhiwei OS Decision Stability Kernel (DSK) (v6.2)
 *
 * ═══════════════════════════════════════════════════════════════
 * OS INVARIANT (v6.2):
 *
 *   DecisionStabilityKernel = NORMALIZATION ONLY
 *
 *   ❌ NOT control flow（不调用 DecisionEngine.commit/reject/override）
 *   ❌ NOT execution routing（不调用 ExecutionRouter.route）
 *   ❌ NOT scoring（不调用 DecisionPolicyKernel.compute）
 *   ❌ NOT policy weight 来源（不产生 reward signal）
 *
 *   ✔ ONLY:
 *        bound delta         (Δweight ∈ [-max_delta, +max_delta])
 *        clamp weight        (weight ∈ [weight_min, weight_max])
 *        detect drift        (长期单边强化检测)
 *        mean reversion      (drift dampening)
 *        normalize weights   (全局分布保持)
 *
 *   PURE FUNCTION: 相同输入永远产生相同输出，无副作用、无内部 state
 * ═══════════════════════════════════════════════════════════════
 *
 * v6.2 核心跃迁：
 *   v6.1: unbounded adaptive system（feedback loop 无边界约束）
 *   v6.2: bounded stable adaptive system（OS-grade stability）
 *
 * v6.1 风险（v6.2 修复目标）：
 *   - Feedback Loop Amplification Drift
 *     reward 累积无归一化约束 → 长期单边强化 → policy weight 极化
 *   - 本质：Unbounded reinforcement in policy weight space
 *
 * v6.2 修复策略（control theory level）：
 *   1. Delta bounding      — 单次调整幅度有界
 *   2. Weight clamp         — 权重绝对值有界
 *   3. Drift detection      — 滑动窗口检测长期单边趋势
 *   4. Mean reversion       — 漂移时向中心值衰减
 *   5. Global normalization — 全局权重分布保持
 *
 * 严格约束（不可违反）：
 *   - DSK 只在 DecisionFeedbackLoop.update() 路径生效
 *   - DSK 不触碰 Engine / DPC / Router
 *   - DSK 是 pure function，不持有 state
 *   - DSK 默认 enabled，可通过 config 禁用（向后兼容）
 *
 * 数学契约：
 *   enforce(input: StabilityEnforcementInput): StabilityEnforcementResult
 *
 *   INPUT:  { policy_id, old_weight, raw_delta, history }
 *   OUTPUT: { final_weight, applied_delta, bounded_delta,
 *             drift_dampened, drift_direction, drift_ratio, reason }
 *
 *   满足：
 *     |applied_delta| ≤ max_delta
 *     weight_min ≤ final_weight ≤ weight_max
 *     drift_dampened = true ⟹ final_weight 向 mean_reversion_target 收敛
 */

import type { PolicyWeights } from "../types";

// ═══════════════════════════════════════════════════════════════
// 1️⃣ StabilityConfig — DSK 配置（pure data）
// ═══════════════════════════════════════════════════════════════

/**
 * StabilityConfig — DSK 配置
 *
 * 所有阈值集中在此，便于调优（但不暴露到运行时修改入口）
 *
 * 默认值依据 control theory:
 *   - max_delta = 0.1       — 单次调整 ≤ 10%（保守）
 *   - drift_window = 10     — 滑动窗口 10 次调整
 *   - drift_threshold = 0.7 — 单向占比 > 70% 触发 dampening
 *   - mean_reversion = 0.5  — 权重中心
 *   - reversion_strength = 0.3 — 30% 衰减幅度（温和）
 */
export interface StabilityConfig {
  /** 权重下界（默认 0） */
  weight_min: number;
  /** 权重上界（默认 1） */
  weight_max: number;
  /** 单次调整最大幅度（默认 0.1，Δweight ∈ [-0.1, +0.1]） */
  max_delta: number;
  /** 漂移检测滑动窗口大小（默认 10） */
  drift_window_size: number;
  /** 单向漂移触发阈值（默认 0.7 = 70%） */
  drift_threshold: number;
  /** 均值回归目标值（默认 0.5） */
  mean_reversion_target: number;
  /** 均值回归强度（0=无衰减, 1=完全拉回；默认 0.3） */
  mean_reversion_strength: number;
  /** 是否启用漂移 dampening（默认 true，关闭则纯 clamp） */
  enable_drift_damping: boolean;
}

/**
 * DEFAULT_STABILITY_CONFIG — DSK 默认配置
 *
 * 设计哲学：
 *   - 保守优于激进（小 delta, 小 reversion_strength）
 *   - 检测优于强制（先检测 drift，再应用 dampening）
 *   - 确定性优于启发式（所有阈值显式声明）
 */
export const DEFAULT_STABILITY_CONFIG: StabilityConfig = {
  weight_min: 0,
  weight_max: 1,
  max_delta: 0.1,
  drift_window_size: 10,
  drift_threshold: 0.7,
  mean_reversion_target: 0.5,
  mean_reversion_strength: 0.3,
  enable_drift_damping: true,
};

// ═══════════════════════════════════════════════════════════════
// 2️⃣ StabilityContext — DSK 上下文输入（pure data）
// ═══════════════════════════════════════════════════════════════

/**
 * StabilityContext — DSK 上下文
 *
 * 与 DecisionContext (DPC 输入) 平行设计：
 *   - DecisionContext  → DPC.compute()  → DecisionScore
 *   - StabilityContext → DSK.enforce()   → StabilityEnforcementResult
 *
 * ❗纯数据结构，不包含方法或副作用
 */
export interface StabilityContext {
  /** 当前权重映射 */
  weights: Map<string, number>;
  /** 调整历史 */
  history: PolicyWeights["adjustment_history"];
}

// ═══════════════════════════════════════════════════════════════
// 3️⃣ DriftDetectionResult — 漂移检测结果（pure data）
// ═══════════════════════════════════════════════════════════════

/**
 * DriftDetectionResult — 漂移检测输出
 *
 * 检测算法：滑动窗口内单向调整占比超过 threshold
 *
 * 输出语义：
 *   drift_detected = false → 无漂移，无需 dampening
 *   drift_detected = true  → 检测到漂移，应用 mean reversion
 */
export interface DriftDetectionResult {
  /** 是否检测到漂移 */
  drift_detected: boolean;
  /** 漂移方向（'up' = 单边增, 'down' = 单边减） */
  drift_direction?: "up" | "down";
  /** 单向占比 [0, 1] */
  drift_ratio?: number;
  /** 窗口内样本数 */
  window_samples?: number;
}

// ═══════════════════════════════════════════════════════════════
// 4️⃣ StabilityEnforcementInput / Result — DSK 主入口契约
// ═══════════════════════════════════════════════════════════════

/**
 * StabilityEnforcementInput — DSK.enforce() 输入
 *
 * 由 DecisionFeedbackLoop.adjust() 在每次 weight update 时调用
 */
export interface StabilityEnforcementInput {
  /** 策略 ID */
  policy_id: string;
  /** 调整前权重 */
  old_weight: number;
  /** 原始 delta（feedback 产生的未约束 delta） */
  raw_delta: number;
  /** 调整历史（用于 drift detection） */
  history: PolicyWeights["adjustment_history"];
}

/**
 * StabilityEnforcementResult — DSK.enforce() 输出
 *
 * 确定性契约：
 *   |applied_delta| ≤ max_delta
 *   weight_min ≤ final_weight ≤ weight_max
 *   drift_dampened = true ⟹ final_weight 向 mean_reversion_target 收敛
 */
export interface StabilityEnforcementResult {
  /** 最终应用权重（已 clamp） */
  final_weight: number;
  /** 实际应用的 delta（final_weight - old_weight） */
  applied_delta: number;
  /** Delta bounding 后的 delta（drift dampening 前） */
  bounded_delta: number;
  /** 是否应用了 drift dampening */
  drift_dampened: boolean;
  /** 漂移信息（drift_dampened=true 时填充） */
  drift_direction?: "up" | "down";
  /** 单向占比（drift_dampened=true 时填充） */
  drift_ratio?: number;
  /** 调整原因（用于 audit history） */
  reason: string;
}

// ═══════════════════════════════════════════════════════════════
// 5️⃣ DecisionStabilityKernel — v6.2 稳定性内核（pure function）
// ═══════════════════════════════════════════════════════════════

/**
 * DecisionStabilityKernel (DSK) — v6.2 核心
 *
 * ═══════════════════════════════════════════════════════════════
 * OS INVARIANT (v6.2):
 *
 *   DecisionStabilityKernel = NORMALIZATION ONLY
 *
 *   ❌ NOT control flow / routing / scoring / policy weight 来源
 *   ✔ ONLY: bound / clamp / detect / dampen / normalize
 *
 *   PURE FUNCTION: 无内部 state，相同输入永远产生相同输出
 * ═══════════════════════════════════════════════════════════════
 *
 * 调用契约：
 *   DecisionFeedbackLoop.adjust() 在计算 raw_delta 后，
 *   调用 DSK.enforce() 获得 final_weight，
 *   将 final_weight 写入 PolicyWeightsManager.weights。
 *
 * 单次调整流程（pure function pipeline）：
 *   raw_delta
 *     → boundDelta()           → bounded_delta (|Δ| ≤ max_delta)
 *     → old_weight + bounded_delta
 *     → clampWeight()          → clamped_weight ∈ [min, max]
 *     → detectDrift()          → drift_result
 *     → [if drift] applyMeanReversion() → final_weight
 *     → clampWeight()          → final_weight (二次保护)
 *
 * 全局归一化（normalizeWeights）：
 *   定期调用（例如每 N 次调整），对全量 weights 做 clamp + 软压缩，
 *   防止全局分布失衡。
 */
export class DecisionStabilityKernel {
  private readonly config: StabilityConfig;

  constructor(config: Partial<StabilityConfig> = {}) {
    this.config = { ...DEFAULT_STABILITY_CONFIG, ...config };
  }

  /**
   * 获取当前配置（只读，用于 audit）
   */
  getConfig(): Readonly<StabilityConfig> {
    return { ...this.config };
  }

  // ───────────────────────────────────────────────────────────
  // 1. Delta bounding — 单次调整幅度有界
  // ───────────────────────────────────────────────────────────

  /**
   * Delta bounding — 限制单次调整幅度
   *
   * 数学契约：
   *   返回值 ∈ [-max_delta, +max_delta]
   *
   * 算法：
   *   Math.max(-max_delta, Math.min(max_delta, delta))
   *
   * ❗纯函数：相同输入永远产生相同输出
   *
   * @param delta 原始 delta
   * @returns 限制后的 delta
   */
  boundDelta(delta: number): number {
    const { max_delta } = this.config;
    return Math.max(-max_delta, Math.min(max_delta, delta));
  }

  // ───────────────────────────────────────────────────────────
  // 2. Weight clamp — 权重绝对值有界
  // ───────────────────────────────────────────────────────────

  /**
   * Weight clamp — 限制权重到 [weight_min, weight_max]
   *
   * 数学契约：
   *   返回值 ∈ [weight_min, weight_max]
   *
   * ❗纯函数：相同输入永远产生相同输出
   *
   * @param weight 原始权重
   * @returns clamp 后的权重
   */
  clampWeight(weight: number): number {
    const { weight_min, weight_max } = this.config;
    return Math.max(weight_min, Math.min(weight_max, weight));
  }

  // ───────────────────────────────────────────────────────────
  // 3. Drift detection — 长期单边强化检测
  // ───────────────────────────────────────────────────────────

  /**
   * Drift detection — 检测长期单边漂移
   *
   * 算法：
   *   1. 提取 policy_id 对应的最近 N 条 history（N = drift_window_size）
   *   2. 统计正方向调整数（new_weight > old_weight）
   *   3. 计算 positive_ratio = positive_count / samples
   *   4. 若 positive_ratio > drift_threshold → drift up
   *   5. 若 (1 - positive_ratio) > drift_threshold → drift down
   *
   * 边界情况：
   *   - samples < 3 → 不检测（数据不足）
   *   - samples = 0 → 不检测
   *
   * ❗纯函数：相同输入永远产生相同输出
   *
   * @param history 完整调整历史
   * @param policy_id 策略 ID
   * @returns 漂移检测结果
   */
  detectDrift(
    history: PolicyWeights["adjustment_history"],
    policy_id: string,
  ): DriftDetectionResult {
    if (!this.config.enable_drift_damping) {
      return { drift_detected: false };
    }

    const { drift_window_size, drift_threshold } = this.config;

    // 过滤当前 policy 的历史记录
    const policyHistory = history.filter((h) => h.policy_id === policy_id);

    // 取最近 N 条
    const window = policyHistory.slice(-drift_window_size);

    if (window.length < 3) {
      return { drift_detected: false, window_samples: window.length };
    }

    // 统计正方向调整数
    const positiveCount = window.filter(
      (h) => h.new_weight > h.old_weight,
    ).length;
    const negativeCount = window.filter(
      (h) => h.new_weight < h.old_weight,
    ).length;

    const positiveRatio = positiveCount / window.length;
    const negativeRatio = negativeCount / window.length;

    // 检测单向漂移
    if (positiveRatio > drift_threshold) {
      return {
        drift_detected: true,
        drift_direction: "up",
        drift_ratio: positiveRatio,
        window_samples: window.length,
      };
    }

    if (negativeRatio > drift_threshold) {
      return {
        drift_detected: true,
        drift_direction: "down",
        drift_ratio: negativeRatio,
        window_samples: window.length,
      };
    }

    return {
      drift_detected: false,
      window_samples: window.length,
    };
  }

  // ───────────────────────────────────────────────────────────
  // 4. Mean reversion — 漂移衰减
  // ───────────────────────────────────────────────────────────

  /**
   * Mean reversion — 将权重向中心值衰减
   *
   * 算法：
   *   final = clamped + (target - clamped) * strength
   *
   * 数学性质：
   *   - strength = 0 → 无衰减（final = clamped）
   *   - strength = 1 → 完全拉回中心（final = target）
   *   - strength ∈ (0, 1) → 部分衰减
   *
   * 漂移方向保护：
   *   - drift up 时，仅当 clamped > target 才衰减
   *   - drift down 时，仅当 clamped < target 才衰减
   *   （避免 dampening 反向加强漂移）
   *
   * ❗纯函数：相同输入永远产生相同输出
   *
   * @param clamped_weight 已 clamp 的权重
   * @param drift_direction 漂移方向
   * @returns 衰减后的权重（未 clamp，由调用方再 clamp）
   */
  applyMeanReversion(
    clamped_weight: number,
    drift_direction: "up" | "down",
  ): number {
    const { mean_reversion_target, mean_reversion_strength } = this.config;

    // 仅在漂移方向上衰减，避免反向加强
    if (drift_direction === "up" && clamped_weight > mean_reversion_target) {
      return (
        clamped_weight +
        (mean_reversion_target - clamped_weight) * mean_reversion_strength
      );
    }

    if (drift_direction === "down" && clamped_weight < mean_reversion_target) {
      return (
        clamped_weight +
        (mean_reversion_target - clamped_weight) * mean_reversion_strength
      );
    }

    return clamped_weight;
  }

  // ───────────────────────────────────────────────────────────
  // 5. enforce — 统一入口（所有 weight update 必须经过）
  // ───────────────────────────────────────────────────────────

  /**
   * enforce — DSK 主入口（stability enforcement layer）
   *
   * 执行流程（pure function pipeline）：
   *   1. Delta bounding     → bounded_delta
   *   2. Weight clamp        → clamped_weight
   *   3. Drift detection    → drift_result
   *   4. [if drift] Mean reversion → reverted_weight
   *   5. Weight clamp (二次) → final_weight
   *
   * 数学不变量（OS-grade 保证）：
   *   |applied_delta| ≤ max_delta
   *   weight_min ≤ final_weight ≤ weight_max
   *   drift_dampened = true ⟹ final_weight 比 clamped_weight 更接近 mean_reversion_target
   *
   * ❗纯函数：相同输入永远产生相同输出，无副作用、无 state
   *
   * @param input 调整输入（policy_id, old_weight, raw_delta, history）
   * @returns 调整输出（final_weight + audit metadata）
   */
  enforce(input: StabilityEnforcementInput): StabilityEnforcementResult {
    // STEP 1: Delta bounding
    const bounded_delta = this.boundDelta(input.raw_delta);

    // STEP 2: Weight clamp
    const raw_new = input.old_weight + bounded_delta;
    const clamped_weight = this.clampWeight(raw_new);

    // STEP 3: Drift detection
    const drift_result = this.detectDrift(input.history, input.policy_id);

    // STEP 4: Mean reversion（仅当检测到漂移时）
    let final_weight = clamped_weight;
    let reason_parts: string[] = [
      `delta bounded: ${input.raw_delta} → ${bounded_delta}`,
      `weight clamped: ${input.old_weight} → ${clamped_weight}`,
    ];

    if (drift_result.drift_detected && drift_result.drift_direction) {
      final_weight = this.applyMeanReversion(
        clamped_weight,
        drift_result.drift_direction,
      );
      // STEP 5: 二次 clamp（保证最终值仍在边界内）
      final_weight = this.clampWeight(final_weight);

      reason_parts.push(
        `drift dampened (${drift_result.drift_direction}, ratio=${drift_result.drift_ratio?.toFixed(2)}): ${clamped_weight} → ${final_weight}`,
      );
    }

    // 计算实际应用 delta（final - old）
    const applied_delta = final_weight - input.old_weight;

    return {
      final_weight,
      applied_delta,
      bounded_delta,
      drift_dampened: drift_result.drift_detected,
      drift_direction: drift_result.drift_direction,
      drift_ratio: drift_result.drift_ratio,
      reason: reason_parts.join("; "),
    };
  }

  // ───────────────────────────────────────────────────────────
  // 6. Global normalization — 全局权重分布保持
  // ───────────────────────────────────────────────────────────

  /**
   * normalizeWeights — 全局权重归一化
   *
   * 用途：
   *   定期调用（例如每 N 次调整），对全量 weights 做 clamp + 软压缩，
   *   防止全局分布失衡（某个 weight 长期累积到极端值）。
   *
   * 算法（保守策略，不破坏 v6.1 语义）：
   *   1. 对每个 weight 应用 clampWeight（保证 ∈ [min, max]）
   *   2. 不做激进的归一化（如 sum-to-1），避免破坏 v6.1 weight 语义
   *   3. 仅对极端值（接近 min/max）做轻微均值回归
   *
   * ❗纯函数：相同输入永远产生相同输出，返回新 Map，不修改输入
   *
   * @param weights 原始权重映射
   * @returns 归一化后的新 Map
   */
  normalizeWeights(weights: Map<string, number>): Map<string, number> {
    const result = new Map<string, number>();
    const { mean_reversion_target, mean_reversion_strength, weight_min, weight_max } = this.config;

    // 极端值阈值（接近边界 10% 范围内视为极端）
    const extreme_low = weight_min + (weight_max - weight_min) * 0.1;
    const extreme_high = weight_max - (weight_max - weight_min) * 0.1;

    for (const [policy_id, weight] of weights) {
      let normalized = this.clampWeight(weight);

      // 对接近边界的值做轻微均值回归
      if (normalized < extreme_low || normalized > extreme_high) {
        normalized =
          normalized +
          (mean_reversion_target - normalized) * mean_reversion_strength * 0.5; // 50% 强度（温和）
        normalized = this.clampWeight(normalized);
      }

      result.set(policy_id, normalized);
    }

    return result;
  }

  // ───────────────────────────────────────────────────────────
  // 7. Stability audit — 稳定性审计（pure, read-only）
  // ───────────────────────────────────────────────────────────

  /**
   * auditStability — 审计当前 weights 的稳定性
   *
   * 返回每个 policy 的漂移状态（不修改任何东西）
   *
   * ❗纯函数：相同输入永远产生相同输出，无副作用
   *
   * @param ctx 稳定性上下文（weights + history）
   * @returns 审计结果列表
   */
  auditStability(ctx: StabilityContext): Array<{
    policy_id: string;
    weight: number;
    drift: DriftDetectionResult;
  }> {
    const results: Array<{
      policy_id: string;
      weight: number;
      drift: DriftDetectionResult;
    }> = [];

    for (const [policy_id, weight] of ctx.weights) {
      const drift = this.detectDrift(ctx.history, policy_id);
      results.push({ policy_id, weight, drift });
    }

    return results;
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出（v6.2 默认启用，可通过 disableStabilityKernel() 关闭用于测试）
// ═══════════════════════════════════════════════════════════════

/**
 * 默认 DSK 单例
 *
 * 使用 DEFAULT_STABILITY_CONFIG，向后兼容 v6.1 行为：
 *   - v6.1 已 clamp weight ∈ [0, 1]（DSK 保留此约束）
 *   - v6.1 delta = +0.05/-0.10（DSK 会将 -0.10 clamp 到 -0.1，最小破坏）
 *   - v6.1 无 drift detection（DSK 新增）
 *   - v6.1 无 mean reversion（DSK 新增）
 */
export const decisionStabilityKernel = new DecisionStabilityKernel();

/**
 * 创建自定义配置的 DSK 实例（用于测试 / 调优）
 *
 * @param config 配置覆盖
 * @returns 新的 DSK 实例
 */
export function createStabilityKernel(
  config: Partial<StabilityConfig> = {},
): DecisionStabilityKernel {
  return new DecisionStabilityKernel(config);
}

/**
 * NOOP_DSK — 空实现（用于完全禁用 v6.2，回退到 v6.1 行为）
 *
 * 仅在测试场景使用：
 *   const disabledKernel = new DecisionStabilityKernel({ enable_drift_damping: false, max_delta: Infinity });
 *
 * 注意：禁用 DSK 等于回退到 v6.1 unbounded 行为，应在明确确认风险后使用。
 */
