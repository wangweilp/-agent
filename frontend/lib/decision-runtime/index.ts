/**
 * 知维 OS Decision Runtime Layer — 统一门面（v6.2 严格版）
 * Zhiwei OS Decision Runtime Layer — Unified Facade
 *
 * v6.2 核心入口：
 *   Decision Stability Kernel (DSK) — Bounded Learning Stability Layer
 *
 * ═══════════════════════════════════════════════════════════════
 * OS INVARIANT (v6.2):
 *
 *   DecisionEngine          = CONTROL ONLY（是否执行）
 *   DecisionPolicyKernel    = SCORING ONLY（如何排序）
 *   DecisionStabilityKernel = NORMALIZATION ONLY（如何约束权重更新）  ← v6.2 新增
 *   ExecutionRouter         = ROUTING ONLY（route + Blocker）
 *   DecisionFeedbackLoop    = WEIGHTS UPDATE ONLY（adjust PolicyWeights，经 DSK 约束）
 *
 *   DO NOT MIX.
 * ═══════════════════════════════════════════════════════════════
 *
 * 架构层级：
 *   ┌─────────────────────────────────────────┐
 *   │  Decision Runtime Layer Facade（本文件） │  ← 统一入口
 *   ├─────────────────────────────────────────┤
 *   │  DecisionRuntimeLoop                     │  ← while(true) runtime loop（orchestrator）
 *   │  DecisionEngine                          │  ← CONTROL ONLY（evaluate/commit/reject/override）
 *   │  DecisionPolicyKernel (DPC)              │  ← SCORING ONLY（pure function）
 *   │  DecisionStabilityKernel (DSK)          │  ← NORMALIZATION ONLY（pure function）  ← v6.2 新增
 *   │  ExecutionRouter                         │  ← ROUTING ONLY（route + Blocker + EventBus.emit）
 *   │  DecisionFeedbackLoop                    │  ← WEIGHTS UPDATE ONLY（adjust 经 DSK 约束）  ← v6.2 增强
 *   │  DecisionStateMachine                    │  ← 6 状态确定性状态机
 *   ├─────────────────────────────────────────┤
 *   │  EventStore / Enforcement / Observability│  ← v1-v5 数据层（不修改）
 *   └─────────────────────────────────────────┘
 *
 * v6.1 → v6.2 跃迁：
 *   v6.1: unbounded adaptive system（feedback loop 无边界约束）
 *         风险：Feedback Loop Amplification Drift
 *               （reward 累积无归一化约束 → 长期单边强化 → policy weight 极化）
 *   v6.2: bounded stable adaptive system（OS-grade stability）
 *         修复：DSK enforce pipeline
 *               raw_delta → boundDelta → clampWeight → detectDrift → meanReversion → final_weight
 *
 * ❗强约束：不依赖 observability layer / graph / explanation / WHY
 */

// ── 类型导出 ──
export type {
  DecisionState,
  DecisionAction,
  DecisionNode,
  AuthorityContext,
  RuntimeContext,
  ExecutionResult,
  DecisionRule,
  PolicyWeights,
  DecisionEngineOptions,
} from "./types";

// ── 状态机导出 ──
export {
  DecisionStateMachine,
  decisionStateMachine,
  StateTransitionError,
} from "./decision-state-machine";

// ── 决策引擎导出（v6.1 CONTROL ONLY） ──
export { DecisionEngine, decisionEngine } from "./decision-engine";

// ── 策略评分内核导出（v6.1 新增，SCORING ONLY） ──
export {
  DecisionPolicyKernel,
  decisionPolicyKernel,
} from "./policy/decision-policy-kernel";
export type {
  DecisionContext,
  DecisionScore,
} from "./policy/decision-policy-kernel";

// ── 稳定性内核导出（v6.2 新增，NORMALIZATION ONLY） ──
export {
  DecisionStabilityKernel,
  decisionStabilityKernel,
  DEFAULT_STABILITY_CONFIG,
  createStabilityKernel,
} from "./policy/decision-stability-kernel";
export type {
  StabilityConfig,
  StabilityContext,
  StabilityEnforcementInput,
  StabilityEnforcementResult,
  DriftDetectionResult,
} from "./policy/decision-stability-kernel";

// ── 路由控制器导出（ROUTING ONLY） ──
export { ExecutionRouter, Blocker, executionRouter, blocker } from "./execution-router";

// ── 反馈循环导出（WEIGHTS UPDATE ONLY） ──
export {
  DecisionFeedbackLoop,
  PolicyWeightsManager,
  decisionFeedbackLoop,
  policyWeightsManager,
} from "./decision-feedback";

// ── 运行时循环导出（ORCHESTRATOR） ──
export {
  DecisionRuntimeLoop,
  EventQueue,
  decisionRuntimeLoop,
  createDecisionRuntimeLoop,
} from "./decision-loop";

// ── 工厂函数 ──

import { DecisionEngine } from "./decision-engine";
import { DecisionRuntimeLoop } from "./decision-loop";
import { ExecutionRouter } from "./execution-router";
import { DecisionFeedbackLoop } from "./decision-feedback";
import type { DecisionEngineOptions, DecisionRule, RuntimeContext } from "./types";
import type { SystemEvent } from "@/types/event-bus";
import type { DecisionNode } from "./types";

/**
 * 创建 DecisionEngine 实例
 */
export function createDecisionEngine(options?: Partial<DecisionEngineOptions>): DecisionEngine {
  return new DecisionEngine(options);
}

/**
 * 创建 ExecutionRouter 实例
 */
export function createExecutionRouter(): ExecutionRouter {
  return new ExecutionRouter();
}

/**
 * 创建 DecisionFeedbackLoop 实例
 */
export function createDecisionFeedbackLoop(): DecisionFeedbackLoop {
  return new DecisionFeedbackLoop();
}

// ═══════════════════════════════════════════════════════════════
// DecisionRuntimeFacade — 高级统一门面
// ═══════════════════════════════════════════════════════════════

import { decisionRuntimeLoop } from "./decision-loop";

/**
 * DecisionRuntimeFacade — 高级统一门面
 *
 * 提供一站式 API：
 * - processEvent: 处理单事件（runOnce）
 * - runLoop: 运行 while(true) 主循环
 * - enqueueEvent: 入队事件
 * - registerRule: 注册规则
 * - overrideDecision: 覆盖决策
 * - getPolicyWeights: 获取策略权重
 */
export const DecisionRuntimeFacade = {
  /**
   * 入队事件
   */
  enqueueEvent(event: SystemEvent): void {
    decisionRuntimeLoop.enqueue(event);
  },

  /**
   * 批量入队
   */
  enqueueEvents(events: SystemEvent[]): void {
    decisionRuntimeLoop.enqueueBatch(events);
  },

  /**
   * 处理单事件（runOnce）
   */
  processEvent(event: SystemEvent, context: RuntimeContext): DecisionNode {
    return decisionRuntimeLoop.runOnce(event, context);
  },

  /**
   * 运行 while(true) 主循环
   */
  runLoop(context: RuntimeContext, maxIterations?: number): DecisionNode[] {
    return decisionRuntimeLoop.run(context, maxIterations);
  },

  /**
   * 停止循环
   */
  stopLoop(): void {
    decisionRuntimeLoop.stop();
  },

  /**
   * 注册规则
   */
  registerRule(rule: DecisionRule): void {
    decisionRuntimeLoop.getEngine().registerRule(rule);
  },

  /**
   * 批量注册规则
   */
  registerRules(rules: DecisionRule[]): void {
    decisionRuntimeLoop.getEngine().registerRules(rules);
  },

  /**
   * 覆盖决策（COMMITTED → OVERRIDDEN）
   */
  overrideDecision(decision_id: string, reason: string): void {
    decisionRuntimeLoop.getEngine().override(decision_id, reason);
  },

  /**
   * 拒绝决策（EVALUATING → REJECTED）
   */
  rejectDecision(decision_id: string): void {
    decisionRuntimeLoop.getEngine().reject(decision_id);
  },

  /**
   * 获取活跃决策
   */
  getActiveDecisions(trace_id: string): DecisionNode[] {
    return decisionRuntimeLoop.getEngine().getActiveDecisions(trace_id);
  },

  /**
   * 获取阻断的 paths
   */
  getBlockedPaths(trace_id: string): string[] {
    return decisionRuntimeLoop.getRouter().getBlocked(trace_id);
  },

  /**
   * 获取策略权重快照
   */
  getPolicyWeights() {
    return decisionRuntimeLoop.getFeedbackLoop().getSnapshot();
  },

  /**
   * 获取调整历史
   */
  getAdjustmentHistory() {
    return decisionRuntimeLoop.getFeedbackLoop().getHistory();
  },

  /**
   * 获取策略评分内核（v6.1 新增）
   *
   * 用于外部访问 DPC：
   *   - 测试场景：验证 scoring 算法
   *   - 监控场景：观察 weights 变化如何影响 score
   *   - 不允许通过此 API 修改 DPC 内部 state（DPC 是 pure function，无 state）
   */
  getPolicyKernel() {
    return decisionRuntimeLoop.getEngine().getPolicyKernel();
  },

  /**
   * 注册决策提交回调
   */
  onCommitted(callback: (decision: DecisionNode) => void): void {
    decisionRuntimeLoop.onCommitted(callback);
  },

  /**
   * 注册决策拒绝回调
   */
  onRejected(callback: (decision: DecisionNode) => void): void {
    decisionRuntimeLoop.onRejected(callback);
  },

  /**
   * 注册 meta decision 生成回调
   */
  onMetaDecision(callback: (meta: DecisionNode, original: DecisionNode) => void): void {
    decisionRuntimeLoop.onMetaDecision(callback);
  },

  /**
   * 获取引擎统计
   */
  getStats() {
    return decisionRuntimeLoop.getEngine().getStats();
  },

  /**
   * 清空所有状态
   */
  reset(): void {
    decisionRuntimeLoop.clear();
  },
};
