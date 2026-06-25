/**
 * 知维 OS Kernel Control Loop — 类型定义
 * Zhiwei OS Kernel Control Loop — Type Definitions
 *
 * v6 核心跃迁：从外挂式 self-healing 升级为内核级统一控制循环
 *
 * 统一循环：
 * OBSERVE → DECIDE → ENFORCE → RECONCILE → HEAL → COMPACT → REPLAY_VERIFY → OBSERVE
 *
 * 强制规则：
 * Rule 1 — Self-healing cannot be external module（必须内嵌进 control loop）
 * Rule 2 — Enforcement cannot be separate kernel（必须是 loop stage）
 * Rule 3 — Authority is not validator only（必须参与 DECIDE 阶段）
 * Rule 4 — Snapshot is loop optimization only（不能作为 recovery primary source）
 */

import type { SystemEvent } from "@/types/event-bus";
import type { SystemState } from "@/lib/replay/types";
import type { ConsistencyReport } from "@/lib/authority/types";
import type { GateResult } from "@/lib/enforcement/types";
import type { CrashReport, RecoveryResult, CompactionResult } from "@/lib/self-healing/types";

// ═══════════════════════════════════════════════════════════════
// ControlState — 全局控制状态（关键新增）
// ═══════════════════════════════════════════════════════════════

/**
 * 控制模式 — 系统当前运行模式
 *
 * - NORMAL:     正常运行，所有指标健康
 * - DEGRADED:   降级运行，检测到轻微漂移
 * - HEALING:    修复中，正在执行恢复
 * - LOCKED:     锁定，严重问题，停止接受新事件
 */
export type ControlMode = "NORMAL" | "DEGRADED" | "HEALING" | "LOCKED";

/**
 * 全局控制状态 — 控制循环的核心状态对象
 */
export interface ControlState {
  /** 当前模式 */
  mode: ControlMode;
  /** 已完成的循环数 */
  last_cycle: number;
  /** 漂移分数（0-100，越高越严重） */
  drift_score: number;
  /** 健康分数（0-100，越高越好） */
  health_score: number;
  /** 执行压力（0-100，越高表示 enforcement 越严格） */
  enforcement_pressure: number;
  /** 当前循环间隔（ms） */
  current_interval_ms: number;
  /** 是否运行中 */
  running: boolean;
  /** 最后一次循环时间 */
  last_cycle_at: string | null;
  /** 最后错误 */
  last_error: string | null;
}

// ═══════════════════════════════════════════════════════════════
// Loop Cycle — 单次循环记录
// ═══════════════════════════════════════════════════════════════

/**
 * 循环阶段
 */
export type LoopStage =
  | "OBSERVE"
  | "DECIDE"
  | "ENFORCE"
  | "RECONCILE"
  | "HEAL"
  | "COMPACT"
  | "REPLAY_VERIFY";

/**
 * 观察结果 — OBSERVE 阶段输出
 */
export interface ObserveResult {
  /** 观察的 trace_id */
  trace_id: string;
  /** 当前事件数 */
  event_count: number;
  /** 当前 snapshot 数 */
  snapshot_count: number;
  /** 检测到的崩溃报告 */
  crashes: CrashReport[];
  /** 当前一致性报告 */
  consistency: ConsistencyReport | null;
  /** 当前状态 */
  current_state: SystemState | null;
  /** 观察时间 */
  observed_at: string;
  /** 观察耗时（ms） */
  duration_ms: number;
}

/**
 * 决策结果 — DECIDE 阶段输出
 *
 * Rule 3: Authority 必须参与 DECIDE 阶段
 */
export interface DecisionResult {
  /** 决策的 trace_id */
  trace_id: string;
  /** 是否需要 enforcement */
  needs_enforcement: boolean;
  /** 是否需要 healing */
  needs_healing: boolean;
  /** 是否需要 compaction */
  needs_compaction: boolean;
  /** 建议的控制模式 */
  suggested_mode: ControlMode;
  /** 建议的 enforcement 压力 */
  suggested_pressure: number;
  /** 决策原因 */
  reason: string;
  /** Authority 参与的决策元数据 */
  authority_decision: {
    consistency_passed: boolean;
    inconsistency_count: number;
    authority_level: "L1" | "L2" | "L3" | "L4";
  };
  /** 决策时间 */
  decided_at: string;
  /** 决策耗时（ms） */
  duration_ms: number;
}

/**
 * 执行结果 — ENFORCE 阶段输出
 *
 * Rule 2: Enforcement 必须是 loop stage（不是独立 kernel）
 */
export interface EnforcementStageResult {
  /** 处理的事件数 */
  events_processed: number;
  /** 允许通过数 */
  events_allowed: number;
  /** 阻断数 */
  events_blocked: number;
  /** 修改数 */
  events_modified: number;
  /** 最后一个 gate 结果 */
  last_gate_result: GateResult | null;
  /** 执行时间 */
  enforced_at: string;
  /** 耗时（ms） */
  duration_ms: number;
}

/**
 * 对账结果 — RECONCILE 阶段输出
 */
export interface ReconcileResult {
  /** trace_id */
  trace_id: string;
  /** 是否一致 */
  consistent: boolean;
  /** 不一致数 */
  inconsistency_count: number;
  /** 权威层级 */
  authority_level: "L1" | "L2" | "L3" | "L4";
  /** 对账时间 */
  reconciled_at: string;
  /** 耗时（ms） */
  duration_ms: number;
}

/**
 * 修复结果 — HEAL 阶段输出
 *
 * Rule 1: Self-healing 必须内嵌进 control loop（不是外挂）
 */
export interface HealingStageResult {
  /** trace_id */
  trace_id: string;
  /** 是否执行了修复 */
  healed: boolean;
  /** 使用的恢复策略 */
  recovery_strategy: string | null;
  /** 恢复结果 */
  recovery: RecoveryResult | null;
  /** 修复后是否一致 */
  consistent_after: boolean;
  /** 修复时间 */
  healed_at: string;
  /** 耗时（ms） */
  duration_ms: number;
}

/**
 * 压缩结果 — COMPACT 阶段输出
 *
 * Rule 4: Snapshot 是 loop optimization only
 */
export interface CompactionStageResult {
  /** trace_id */
  trace_id: string;
  /** 是否执行了压缩 */
  compacted: boolean;
  /** 压缩前数量 */
  before_count: number;
  /** 压缩后数量 */
  after_count: number;
  /** 压缩结果 */
  result: CompactionResult | null;
  /** 压缩时间 */
  compacted_at: string;
  /** 耗时（ms） */
  duration_ms: number;
}

/**
 * 验证结果 — REPLAY_VERIFY 阶段输出
 */
export interface ReplayVerifyResult {
  /** trace_id */
  trace_id: string;
  /** 回放验证是否通过 */
  verified: boolean;
  /** 回放的事件数 */
  replayed_events: number;
  /** 状态版本 */
  state_version: number;
  /** 验证时间 */
  verified_at: string;
  /** 耗时（ms） */
  duration_ms: number;
}

/**
 * 状态增量 — 循环前后状态变化
 */
export interface StateDelta {
  /** drift_score 变化 */
  drift_delta: number;
  /** health_score 变化 */
  health_delta: number;
  /** enforcement_pressure 变化 */
  pressure_delta: number;
  /** 模式是否变化 */
  mode_changed: boolean;
  /** 旧模式 */
  previous_mode: ControlMode;
  /** 新模式 */
  new_mode: ControlMode;
}

/**
 * 完整循环记录 — 单次 control loop 执行的完整记录
 */
export interface LoopCycle {
  /** 循环序号 */
  cycle_number: number;
  /** trace_id */
  trace_id: string;
  /** 开始时间 */
  started_at: string;
  /** 结束时间 */
  ended_at: string;
  /** 总耗时（ms） */
  total_duration_ms: number;
  /** 各阶段结果 */
  observe_result: ObserveResult;
  decision: DecisionResult;
  enforcement_result: EnforcementStageResult | null;
  reconcile_result: ReconcileResult | null;
  healing_result: HealingStageResult | null;
  compaction_result: CompactionStageResult | null;
  replay_verify_result: ReplayVerifyResult | null;
  /** 状态增量 */
  state_delta: StateDelta;
  /** 循环前 drift_score */
  drift_score_before: number;
  /** 循环后 drift_score */
  drift_score_after: number;
  /** 是否成功 */
  success: boolean;
  /** 错误信息 */
  error: string | null;
}

// ═══════════════════════════════════════════════════════════════
// Control Loop Memory — 循环历史
// ═══════════════════════════════════════════════════════════════

/**
 * 控制循环历史 — 记录所有循环
 */
export interface ControlLoopHistory {
  /** 所有循环记录 */
  cycles: LoopCycle[];
  /** 总循环数 */
  total_cycles: number;
  /** 成功循环数 */
  successful_cycles: number;
  /** 失败循环数 */
  failed_cycles: number;
  /** 平均循环耗时（ms） */
  avg_cycle_duration_ms: number;
  /** 最后一次循环 */
  last_cycle: LoopCycle | null;
}

// ═══════════════════════════════════════════════════════════════
// Adaptive Scheduling — 自适应调度
// ═══════════════════════════════════════════════════════════════

/**
 * 调度配置
 */
export interface LoopSchedulerConfig {
  /** 基础间隔（ms） */
  base_interval_ms: number;
  /** 最小间隔（ms）— drift 高时 */
  min_interval_ms: number;
  /** 最大间隔（ms）— health 高时 */
  max_interval_ms: number;
  /** drift 阈值（超过则加速） */
  drift_threshold: number;
  /** health 阈值（超过则减速） */
  health_threshold: number;
  /** 自适应强度（0-1，越大响应越快） */
  adaptivity: number;
}

export const DEFAULT_SCHEDULER_CONFIG: LoopSchedulerConfig = {
  base_interval_ms: 5000,
  min_interval_ms: 500,
  max_interval_ms: 30000,
  drift_threshold: 20,
  health_threshold: 80,
  adaptivity: 0.5,
};

// ═══════════════════════════════════════════════════════════════
// Stabilization — 自稳定系统
// ═══════════════════════════════════════════════════════════════

/**
 * 稳定性评估结果
 */
export interface StabilityAssessment {
  /** 是否稳定 */
  stable: boolean;
  /** 不稳定原因 */
  instability_reasons: string[];
  /** 建议的 enforcement 压力调整 */
  pressure_adjustment: number;
  /** 建议的 snapshot 依赖度（0-1） */
  snapshot_dependency: number;
  /** 是否需要触发 healing */
  needs_healing: boolean;
  /** 评估时间 */
  assessed_at: string;
}

/**
 * 稳定化结果
 */
export interface StabilizationResult {
  /** trace_id */
  trace_id: string;
  /** 稳定前模式 */
  mode_before: ControlMode;
  /** 稳定后模式 */
  mode_after: ControlMode;
  /** 执行的操作 */
  actions: string[];
  /** 是否成功稳定 */
  stabilized: boolean;
  /** 耗时（ms） */
  duration_ms: number;
}
