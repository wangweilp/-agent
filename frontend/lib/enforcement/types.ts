/**
 * 知维 OS Runtime Enforcement Kernel — 类型定义
 * Zhiwei OS Runtime Enforcement Kernel — Type Definitions
 *
 * v4 核心：从 reactive validation（事后检查）升级为 proactive enforcement（事前阻断）
 *
 * 4 个核心模块：
 * 1. Event Gate System       — validateEvent(event) → ALLOW / BLOCK / MODIFY
 * 2. Enforcement Pipeline    — event → pre-validate → gate → transform → apply
 * 3. Policy Engine           — kill switch / memory write / governance override
 * 4. Enforcement Loop        — validate → enforce → apply → validate → reconcile
 *
 * 约束：
 * - 不修改 EventStore / SnapshotStore
 * - 不修改 Authority Layer
 * - 只加 runtime control layer
 * - backward compatible
 */

import type { SystemEvent, EventSource, EventSeverity, EventType } from "@/types/event-bus";
import type { SystemState } from "@/lib/replay/types";

// ═══════════════════════════════════════════════════════════════
// 1️⃣ Event Gate System — 事件门控
// ═══════════════════════════════════════════════════════════════

/**
 * 门控决策 — 事件进入系统前的处置结果
 *
 * - ALLOW:   允许事件通过，进入 EventStore
 * - BLOCK:   阻断事件，不进入 EventStore，记录拒绝原因
 * - MODIFY:  修改事件后允许通过（如降级 severity、修改 payload）
 * - QUARANTINE: 隔离事件，待人工审核
 */
export type GateDecision = "ALLOW" | "BLOCK" | "MODIFY" | "QUARANTINE";

/**
 * 门控评估结果
 */
export interface GateResult {
  /** 决策 */
  decision: GateDecision;
  /** 触发的规则 ID */
  rule_id: string;
  /** 触发的策略 ID */
  policy_id: string;
  /** 决策原因 */
  reason: string;
  /** 修改后的事件（仅 MODIFY 时有效） */
  modified_event?: SystemEvent;
  /** 权威层级（用于 authority-aware gating） */
  authority_level: "L1" | "L2" | "L3" | "L4";
  /** 严重级别（用于 severity-based blocking） */
  severity: EventSeverity;
  /** 评估时间 */
  evaluated_at: string;
}

/**
 * 门控规则 — 单条规则定义
 */
export interface GateRule {
  /** 规则 ID */
  rule_id: string;
  /** 规则名称 */
  name: string;
  /** 规则描述 */
  description: string;
  /** 触发条件 */
  condition: GateCondition;
  /** 触发后的决策 */
  decision: GateDecision;
  /** 优先级（数字越大优先级越高） */
  priority: number;
  /** 是否启用 */
  enabled: boolean;
}

/**
 * 门控条件 — 事件匹配条件
 */
export interface GateCondition {
  /** 事件来源（可选，不填=匹配所有） */
  source?: EventSource | EventSource[];
  /** 事件类型（可选） */
  type?: EventType | EventType[];
  /** 严重级别（可选） */
  severity?: EventSeverity | EventSeverity[];
  /** trace_id（可选，特定 trace 限制） */
  trace_id?: string;
  /** 自定义谓词（高级匹配） */
  predicate?: (event: SystemEvent) => boolean;
}

// ═══════════════════════════════════════════════════════════════
// 2️⃣ Policy Engine — 策略引擎
// ═══════════════════════════════════════════════════════════════

/**
 * 策略类型 — 三大运行时策略域
 */
export type PolicyDomain =
  | "kill_switch"        // Kill Switch 策略（紧急阻断）
  | "memory_write"      // Memory 写入策略（认知面控制）
  | "governance_override"; // Governance 覆盖策略（治理面控制）

/**
 * 策略状态
 */
export type PolicyStatus = "active" | "disabled" | "deprecated";

/**
 * 运行时策略 — 完整策略定义
 */
export interface RuntimePolicy {
  /** 策略 ID */
  policy_id: string;
  /** 策略域 */
  domain: PolicyDomain;
  /** 策略名称 */
  name: string;
  /** 策略描述 */
  description: string;
  /** 策略版本（用于 versioning） */
  version: number;
  /** 优先级（数字越大优先级越高，同域内生效） */
  priority: number;
  /** 策略状态 */
  status: PolicyStatus;
  /** 关联的门控规则 */
  rules: GateRule[];
  /** 创建时间 */
  created_at: string;
  /** 最后更新时间 */
  updated_at: string;
  /** 策略元数据 */
  metadata?: Record<string, unknown>;
}

/**
 * 策略更新请求
 */
export interface PolicyUpdateRequest {
  policy_id: string;
  /** 部分更新字段 */
  patch: Partial<Omit<RuntimePolicy, "policy_id" | "created_at">>;
  /** 是否递增版本号 */
  bump_version: boolean;
}

/**
 * 策略更新结果
 */
export interface PolicyUpdateResult {
  success: boolean;
  /** 更新后的策略（如成功） */
  policy: RuntimePolicy | null;
  /** 旧版本号 */
  previous_version: number;
  /** 新版本号 */
  new_version: number;
  /** 错误原因 */
  error: string | null;
}

// ═══════════════════════════════════════════════════════════════
// 3️⃣ Enforcement Pipeline — 执行前流水线
// ═══════════════════════════════════════════════════════════════

/**
 * 流水线阶段
 */
export type PipelineStage =
  | "pre_validate"     // 预验证（结构、因果）
  | "gate"              // 门控评估
  | "transform"         // 事件转换（如 MODIFY）
  | "apply"             // 应用到 EventStore
  | "post_validate"     // 后验证（一致性）
  | "reconcile";        // 对账（与 Authority Layer）

/**
 * 流水线阶段结果
 */
export interface StageResult {
  stage: PipelineStage;
  /** 是否通过 */
  passed: boolean;
  /** 阶段输出（如修改后的事件） */
  output?: SystemEvent;
  /** 阶段产生的门控结果 */
  gate_result?: GateResult;
  /** 跳过后续阶段的原因 */
  skip_reason?: string;
  /** 阶段耗时（ms） */
  duration_ms: number;
  /** 错误信息 */
  error?: string;
}

/**
 * 完整流水线执行结果
 */
export interface EnforcementResult {
  /** 原始事件 */
  original_event: SystemEvent;
  /** 最终事件（可能被 MODIFY） */
  final_event: SystemEvent | null;
  /** 最终决策 */
  final_decision: GateDecision;
  /** 是否成功进入 EventStore */
  applied: boolean;
  /** 各阶段结果 */
  stages: StageResult[];
  /** 总耗时（ms） */
  total_duration_ms: number;
  /** 拒绝原因（如 BLOCK） */
  rejection_reason: string | null;
  /** 评估时间 */
  enforced_at: string;
}

// ═══════════════════════════════════════════════════════════════
// 4️⃣ Enforcement Loop — 强制执行闭环
// ═══════════════════════════════════════════════════════════════

/**
 * 闭环状态
 */
export type LoopStatus =
  | "idle"
  | "validating"
  | "enforcing"
  | "applying"
  | "reconciling"
  | "completed"
  | "blocked"
  | "error";

/**
 * 闭环执行记录
 */
export interface EnforcementLoopRecord {
  /** 记录 ID */
  loop_id: string;
  /** 处理的事件 */
  event: SystemEvent;
  /** 闭环状态 */
  status: LoopStatus;
  /** 各阶段结果 */
  pre_validation: StageResult;
  enforcement: StageResult;
  application: StageResult;
  post_validation: StageResult;
  reconciliation: StageResult;
  /** 最终决策 */
  final_decision: GateDecision;
  /** 是否成功 */
  success: boolean;
  /** 对账结果（与 Authority Layer） */
  reconciliation_result: {
    consistent: boolean;
    inconsistencies_count: number;
    authority_level: "L1" | "L2" | "L3" | "L4";
  } | null;
  /** 执行时间 */
  executed_at: string;
  /** 总耗时（ms） */
  total_duration_ms: number;
}

/**
 * 强制执行内核状态
 */
export interface EnforcementKernelState {
  /** 是否启用 */
  enabled: boolean;
  /** 总处理事件数 */
  total_processed: number;
  /** 允许通过数 */
  total_allowed: number;
  /** 阻断数 */
  total_blocked: number;
  /** 修改数 */
  total_modified: number;
  /** 隔离数 */
  total_quarantined: number;
  /** 活跃策略数 */
  active_policies: number;
  /** 活跃规则数 */
  active_rules: number;
  /** 最后执行时间 */
  last_enforced_at: string | null;
  /** 最后错误 */
  last_error: string | null;
}
