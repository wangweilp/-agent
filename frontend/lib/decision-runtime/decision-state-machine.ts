/**
 * 知维 OS Decision State Machine — 确定性状态机（6 状态）
 * Zhiwei OS Decision State Machine (v6 严格版)
 *
 * 严格遵循用户提示词的状态转移规则：
 *
 *   from          to            允许
 *   ─────────────────────────────────
 *   PENDING       EVALUATING    ✔
 *   EVALUATING    COMMITTED     ✔
 *   EVALUATING    REJECTED      ✔
 *   COMMITTED     OVERRIDDEN    ✔
 *   any           EXPIRED       ✔
 *
 * 非法转移（直接抛 StateTransitionError）：
 *   PENDING → COMMITTED    ❌ (必须经过 EVALUATING)
 *   PENDING → REJECTED      ❌ (必须经过 EVALUATING)
 *   COMMITTED → PENDING     ❌ (不可回退)
 *   COMMITTED → EVALUATING  ❌ (不可回退)
 *   REJECTED → *             ❌ (终态，除 EXPIRED)
 *   OVERRIDDEN → *           ❌ (终态，除 EXPIRED)
 *   EXPIRED → *              ❌ (终态)
 *
 * ❗强规则：state transition must be deterministic
 */

import type { DecisionNode, DecisionState } from "./types";

// ═══════════════════════════════════════════════════════════════
// 合法状态转移表（严格按用户提示词，确定性定义）
// ═══════════════════════════════════════════════════════════════

/**
 * 合法状态转移映射（严格按用户提示词）
 *
 * key: 当前状态
 * value: 该状态可以转移到的合法目标状态集合
 *
 * ❗确定性：这张表是静态的，不依赖运行时数据
 */
const VALID_TRANSITIONS: Record<DecisionState, DecisionState[]> = {
  PENDING: ["EVALUATING", "EXPIRED"],
  EVALUATING: ["COMMITTED", "REJECTED", "EXPIRED"],
  COMMITTED: ["OVERRIDDEN", "EXPIRED"],
  REJECTED: ["EXPIRED"],
  OVERRIDDEN: ["EXPIRED"],
  EXPIRED: [], // 终态，不可再转移
};

// ═══════════════════════════════════════════════════════════════
// StateTransitionError — 非法状态转移错误
// ═══════════════════════════════════════════════════════════════

/**
 * 非法状态转移错误
 *
 * 当尝试非法状态转移时抛出，确保状态机严格确定性
 */
export class StateTransitionError extends Error {
  constructor(
    public readonly decision_id: string,
    public readonly from_state: DecisionState,
    public readonly to_state: DecisionState,
    message?: string,
  ) {
    super(
      `Invalid state transition: ${from_state} → ${to_state} ` +
        `for decision ${decision_id}` +
        (message ? ` (${message})` : ""),
    );
    this.name = "StateTransitionError";
  }
}

// ═══════════════════════════════════════════════════════════════
// DecisionStateMachine — 确定性状态机
// ═══════════════════════════════════════════════════════════════

/**
 * DecisionStateMachine — 确定性状态机
 *
 * 职责：
 * - 校验状态转移合法性（基于静态转移表）
 * - 应用状态转移（更新 decision state + lifecycle 时间戳）
 * - 拒绝非法转移（抛 StateTransitionError）
 *
 * API（严格按用户提示词）：
 *   transition(decision: DecisionNode, target: DecisionState): DecisionNode
 *
 * ❗不负责：
 * - 冲突仲裁（由 DecisionEngine 负责）
 * - routing 计算（由 ExecutionRouter 负责）
 * - feedback 调整（由 DecisionFeedbackLoop 负责）
 */
export class DecisionStateMachine {
  /**
   * 校验状态转移是否合法
   *
   * @param from 当前状态
   * @param to 目标状态
   * @returns 是否合法
   */
  canTransition(from: DecisionState, to: DecisionState): boolean {
    const allowed = VALID_TRANSITIONS[from] ?? [];
    return allowed.includes(to);
  }

  /**
   * 获取某状态的所有合法目标状态
   */
  getValidTransitions(from: DecisionState): DecisionState[] {
    return VALID_TRANSITIONS[from] ?? [];
  }

  /**
   * 应用状态转移（核心 API，严格按用户提示词）
   *
   * @param decision 当前决策
   * @param target 目标状态
   * @returns 转移后的新 DecisionNode（不可变更新）
   *
   * @throws StateTransitionError 如果转移非法
   */
  transition(decision: DecisionNode, target: DecisionState): DecisionNode {
    const from = decision.state;

    // 1. 校验合法性
    if (!this.canTransition(from, target)) {
      throw new StateTransitionError(
        decision.decision_id,
        from,
        target,
        `valid transitions from ${from}: [${this.getValidTransitions(from).join(", ")}]`,
      );
    }

    // 2. 应用转移 + 更新时间戳（确定性副作用）
    const now = Date.now();
    const updated: DecisionNode = { ...decision };

    switch (target) {
      case "EVALUATING":
        updated.state = "EVALUATING";
        break;

      case "COMMITTED":
        updated.state = "COMMITTED";
        updated.committed_at = now;
        break;

      case "REJECTED":
        updated.state = "REJECTED";
        if (!updated.rejection_reason) {
          updated.rejection_reason = "rejected by state machine";
        }
        break;

      case "OVERRIDDEN":
        updated.state = "OVERRIDDEN";
        // override_reason 由调用方设置（通过 reject/override API）
        break;

      case "EXPIRED":
        updated.state = "EXPIRED";
        break;

      case "PENDING":
        // PENDING 是初始状态，不应通过 transition 回到
        // 理论上 VALID_TRANSITIONS 已禁止，但加防御性检查
        throw new StateTransitionError(
          decision.decision_id,
          from,
          "PENDING",
          "cannot return to PENDING state",
        );
    }

    return updated;
  }

  /**
   * 判断决策是否处于终态（不可再变更，除 EXPIRED）
   *
   * 终态：REJECTED / OVERRIDDEN / EXPIRED
   */
  isTerminal(state: DecisionState): boolean {
    return state === "REJECTED" || state === "OVERRIDDEN" || state === "EXPIRED";
  }

  /**
   * 判断决策是否处于活跃态（可影响 routing）
   *
   * 活跃态：COMMITTED（已生效）
   */
  isActive(state: DecisionState): boolean {
    return state === "COMMITTED";
  }

  /**
   * 判断决策是否可被 override
   *
   * 可被 override：COMMITTED
   * 不可被 override：PENDING/EVALUATING/REJECTED/OVERRIDDEN/EXPIRED
   */
  canOverride(state: DecisionState): boolean {
    return state === "COMMITTED";
  }

  /**
   * 判断决策是否可被 expire
   *
   * 任何非 EXPIRED 状态都可被 expire
   */
  canExpire(state: DecisionState): boolean {
    return state !== "EXPIRED";
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const decisionStateMachine = new DecisionStateMachine();
