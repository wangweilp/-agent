/**
 * 知维 OS Decision Runtime Primitive — 类型定义
 * Zhiwei OS Decision Runtime Layer — Type Definitions (v6 严格版)
 *
 * v6 核心跃迁：
 *   Decision = Runtime Control Object（不是数据）
 *
 * ❗严格遵循用户提示词：
 * - 6 状态 DecisionState（PENDING/EVALUATING/COMMITTED/REJECTED/OVERRIDDEN/EXPIRED）
 * - DecisionNode 含 policy_context / cost / actions[] / triggers / blocks / parent/child
 * - 不依赖 observability layer / graph / explanation / WHY
 *
 * v5/v6 边界：
 *   v5: "Why did it happen?"（解释系统，已冻结）
 *   v6: "Make it happen differently"（控制系统）
 *
 * 系统级定义：
 *   v6 = The Operating System where Decisions are Execution Primitives, not Observations
 */

import type { SystemEvent } from "@/types/event-bus";

// ═══════════════════════════════════════════════════════════════
// 1️⃣ DecisionState — 决策状态机状态（6 状态）
// ═══════════════════════════════════════════════════════════════

/**
 * 决策状态（运行时状态机，6 状态）
 *
 * 状态流转规则（严格遵循用户提示词）：
 *   PENDING → EVALUATING       (开始评估)
 *   EVALUATING → COMMITTED     (评估通过)
 *   EVALUATING → REJECTED      (评估失败)
 *   COMMITTED → OVERRIDDEN     (被更高权限覆盖)
 *   any → EXPIRED              (超时失效)
 *
 * ❗强规则：state transition must be deterministic
 */
export type DecisionState =
  | "PENDING"      // 待评估
  | "EVALUATING"   // 评估中
  | "COMMITTED"    // 已提交（生效中，影响 routing）
  | "REJECTED"     // 已拒绝（不生效）
  | "OVERRIDDEN"   // 已被覆盖（被 override 覆盖）
  | "EXPIRED";     // 已过期（TTL 超时）

// ═══════════════════════════════════════════════════════════════
// 2️⃣ DecisionAction — 决策动作（控制平面语义）
// ═══════════════════════════════════════════════════════════════

/**
 * 决策动作 — 控制 execution routing 的语义
 *
 * v6 DecisionAction 是 runtime control primitive，直接修改 execution context
 */
export type DecisionAction =
  | "ALLOW"        // 允许执行
  | "BLOCK"        // 阻断执行
  | "MODIFY"       // 修改执行（修改 event payload）
  | "QUARANTINE"   // 隔离执行
  | "ESCALATE"     // 升级执行
  | "OVERRIDE";    // 覆盖执行

// ═══════════════════════════════════════════════════════════════
// 3️⃣ AuthorityContext — 权威上下文（来自 v3 Authority Layer）
// ═══════════════════════════════════════════════════════════════

/**
 * 权威上下文 — 决策评估时参考的 authority 信息
 *
 * ❗只读消费 v3 Authority Layer，不修改
 */
export interface AuthorityContext {
  /** 当前 trace_id */
  trace_id: string;
  /** 当前权威层级（L1>L2>L3>L4） */
  authority_level: "L1" | "L2" | "L3" | "L4";
  /** 当前活跃的 policy 列表（影响决策评估） */
  active_policies: string[];
  /** 当前 kill_switch 状态 */
  kill_switch_active: boolean;
  /** 权威元数据 */
  metadata: Record<string, unknown>;
}

// ═══════════════════════════════════════════════════════════════
// 4️⃣ RuntimeContext — 运行时上下文
// ═══════════════════════════════════════════════════════════════

/**
 * 运行时上下文 — DecisionEngine.evaluate(event, context) 的 context 参数
 *
 * 包含 authority context + runtime 状态
 */
export interface RuntimeContext {
  /** 权威上下文（来自 v3） */
  authority: AuthorityContext;
  /** 当前 routing 状态（累积态，跨 event） */
  blocked_paths: string[];
  /** 当前活跃决策数 */
  active_decision_count: number;
  /** 运行时元数据 */
  metadata: Record<string, unknown>;
}

// ═══════════════════════════════════════════════════════════════
// 5️⃣ DecisionNode — 运行时决策原语（严格按用户提示词）
// ═══════════════════════════════════════════════════════════════

/**
 * DecisionNode — v6 核心运行时决策原语
 *
 * ❗严格按用户提示词定义，不简化
 *
 * v6 本质：
 *   Decision = Runtime Control Object（不是数据）
 *
 * 与 v5 区别：
 * - v5 Decision 是 Graph node（derived）
 * - v6 DecisionNode 是 Runtime object（primitive）
 */
export interface DecisionNode {
  /** 决策 ID（全局唯一） */
  decision_id: string;

  // ── runtime identity ──
  /** 关联的 trace_id */
  trace_id: string;
  /** 关联的 span_id（可选，用于桥接 v5，但不依赖） */
  span_id?: string;

  // ── execution state ──
  /** 当前决策状态（6 状态机） */
  state: DecisionState;

  // ── control plane input ──
  /** 输入事件（触发该决策的事件） */
  input_event: SystemEvent;
  /** 权威上下文（评估时参考） */
  policy_context: AuthorityContext;

  // ── runtime evaluation ──
  /** 运行时置信度（0-1） */
  confidence: number;
  /** 执行排序权重（数字越大优先级越高） */
  priority: number;
  /** 执行成本权重（用于 cost-aware routing） */
  cost: number;

  // ── control effects ──
  /** 决策动作列表（一个决策可产生多个动作） */
  actions: DecisionAction[];

  // ── execution links ──
  /** 触发的 event routing targets（COMMITTED 后 emit） */
  triggers?: string[];
  /** 阻断的 execution paths（COMMITTED 后 block） */
  blocks?: string[];

  // ── runtime lineage（Decision→Decision 自引用） ──
  /** 父决策 ID（用于 meta decision 生成） */
  parent_decision_id?: string;
  /** 子决策 ID 列表（meta decision 生成的子决策） */
  child_decision_ids?: string[];

  // ── lifecycle ──
  /** 创建时间（ms timestamp） */
  created_at: number;
  /** 提交时间（ms timestamp，COMMITTED 时设置） */
  committed_at?: number;
  /** 拒绝原因（REJECTED 时设置） */
  rejection_reason?: string;
  /** 覆盖原因（OVERRIDDEN 时设置） */
  override_reason?: string;

  // ── audit（用于追踪决策来源，但不依赖 observability） ──
  /** 决策来源（哪个规则/引擎产生） */
  source?: string;
  /** 决策规则 ID */
  rule_id?: string;
}

// ═══════════════════════════════════════════════════════════════
// 6️⃣ ExecutionResult — 执行结果（Feedback Loop 用）
// ═══════════════════════════════════════════════════════════════

/**
 * 执行结果 — Decision Feedback Loop 的输入
 *
 * 用于：Decision outcome → modifies future decision scoring
 */
export interface ExecutionResult {
  /** 关联的决策 ID */
  decision_id: string;
  /** 执行是否成功 */
  success: boolean;
  /** 执行耗时（ms） */
  duration_ms: number;
  /** 执行产出的事件列表 */
  emitted_events: SystemEvent[];
  /** 执行错误（失败时） */
  error?: string;
  /** 执行元数据 */
  metadata: Record<string, unknown>;
}

// ═══════════════════════════════════════════════════════════════
// 7️⃣ DecisionRule — 决策规则
// ═══════════════════════════════════════════════════════════════

/**
 * 决策规则 — DecisionEngine.evaluate 时使用的规则
 */
export interface DecisionRule {
  /** 规则 ID */
  rule_id: string;
  /** 规则名称 */
  name: string;
  /** 规则优先级（数字越大优先级越高） */
  priority: number;
  /** 是否启用 */
  enabled: boolean;
  /** 事件类型匹配 */
  event_types: string[];
  /** 规则谓词 */
  predicate: (event: SystemEvent, context: RuntimeContext) => boolean;
  /** 决策动作（规则命中后产生的 actions） */
  actions: DecisionAction[];
  /** 置信度计算 */
  confidence: (event: SystemEvent, context: RuntimeContext) => number;
  /** 成本计算 */
  cost: (event: SystemEvent, context: RuntimeContext) => number;
  /** 触发的 routing targets */
  triggers?: string[];
  /** 阻断的 paths */
  blocks?: string[];
  /** 规则来源 */
  source: string;
}

// ═══════════════════════════════════════════════════════════════
// 8️⃣ PolicyWeights — 策略权重（Feedback Loop 调整）
// ═══════════════════════════════════════════════════════════════

/**
 * 策略权重 — DecisionFeedbackLoop 调整的对象
 *
 * 自演化核心：
 *   Decision outcome → modifies PolicyWeights → affects future decision scoring
 */
export interface PolicyWeights {
  /** policy_id → weight（0-1） */
  weights: Map<string, number>;
  /** 调整历史（用于 audit） */
  adjustment_history: Array<{
    policy_id: string;
    old_weight: number;
    new_weight: number;
    reason: string;
    adjusted_at: number;
  }>;
}

// ═══════════════════════════════════════════════════════════════
// 9️⃣ DecisionEngineOptions — 引擎配置
// ═══════════════════════════════════════════════════════════════

export interface DecisionEngineOptions {
  /** 决策 TTL（ms，超时自动 EXPIRED） */
  decision_ttl_ms: number;
  /** 是否启用 meta decision 生成（confidence < 0.5 时） */
  enable_meta_decision: boolean;
  /** meta decision 触发阈值 */
  meta_decision_threshold: number;
  /** 最大并行活跃决策数（per trace） */
  max_active_per_trace: number;
}
