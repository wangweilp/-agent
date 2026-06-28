/**
 * 知维 OS Observability Kernel — 类型定义
 * Zhiwei OS Observability Kernel — Type Definitions
 *
 * v7 核心：从"可执行 + 可回放"升级为"可解释 + 可追因 + 可审计 + 可理解"
 *
 * 新增第 5 层：OBSERVABILITY LAYER（系统自我解释能力）
 *
 * 架构：
 * Event Layer → Causal Layer → Authority Layer → Enforcement Layer → Observability Layer
 *
 * 核心能力：
 * 1. 全链路 Trace 系统（trace tree + span graph + causal merge）
 * 2. Span Engine（startSpan/endSpan/linkSpanToEvent/measureDuration）
 * 3. Distributed Trace Correlator（跨层关联器）
 * 4. WHY Engine（why(trace_id, event_id)）
 * 5. Observability Store（IndexedDB 持久化）
 * 6. Critical Path Analyzer（latency/causal/enforcement hotpath）
 */

import type { SystemEvent, CausalLink, CausalRelation } from "@/types/event-bus";

// ═══════════════════════════════════════════════════════════════
// 1️⃣ SystemTraceEvent — 全链路 Trace 事件
// ═══════════════════════════════════════════════════════════════

/**
 * 系统层级 — 标识事件所属的架构层
 */
export type SystemLayer = "L1" | "L2" | "L3" | "L4" | "L5";

/**
 * 服务来源 — 标识事件产生的系统模块
 */
export type TraceService =
  | "runtime"          // 运行时
  | "memory"           // 认知面
  | "governance"       // 治理面
  | "enforcement"     // 强制执行
  | "authority"        // 权威层
  | "self_healing"    // 自愈
  | "control_loop"    // 控制循环
  | "observability"   // 可观测性
  | "replay"          // 回放引擎
  | "snapshot"        // 快照引擎
  | "causal_graph"    // 因果图
  | "event_bus"       // 事件总线
  | "agent";          // 执行面

/**
 * Span 状态
 */
export type SpanStatus = "started" | "completed" | "error" | "cancelled";

/**
 * Span 类型 — 标识 span 代表的执行类型
 */
export type SpanKind =
  | "enforcement_stage"   // enforcement pipeline 阶段
  | "replay_frame"        // replay 单帧
  | "snapshot_restore"    // snapshot 恢复
  | "snapshot_create"     // snapshot 创建
  | "causal_chain"        // 因果链
  | "control_loop_cycle"  // 控制循环
  | "recovery"            // 恢复操作
  | "validation"          // 验证
  | "compaction"          // 压缩
  | "event_publish"       // 事件发布
  | "policy_evaluation"   // 策略评估
  | "gate_decision"       // 门控决策
  | "custom";             // 自定义

/**
 * SystemTraceEvent — 全链路 Trace 事件（Span）
 *
 * 将所有系统行为升级为带 span 上下文的结构化 trace
 */
export interface SystemTraceEvent {
  // ── 身份标识 ──
  /** Span ID（唯一） */
  span_id: string;
  /** 父 Span ID（构成 span tree） */
  parent_span_id: string | null;
  /** Trace ID（同一链路共享） */
  trace_id: string;

  // ── 关联 ──
  /** 关联的 event_id（如有） */
  event_id?: string;
  /** 因果引用 ID（关联 causal chain） */
  causal_ref_id?: string;
  /** 关联的 snapshot_id（如有） */
  snapshot_id?: string;
  /** 关联的 enforcement_loop_id（如有） */
  enforcement_loop_id?: string;

  // ── v5 OS-level 升级：因果绑定（结构化嵌入，不再仅靠 event_id 引用） ──
  /**
   * 因果事件 ID（v5 OS-level 因果绑定）
   *
   * 区别于 event_id（仅引用），causal_event_id 是该 span 在因果链上的"身份锚点"。
   * 多个 span 可以引用同一 event_id，但 causal_event_id 标识因果链上的具体节点。
   */
  causal_event_id?: string;
  /**
   * 因果链（嵌入路径，从根到当前 span 的完整 event_id 路径）
   *
   * v5 关键升级：不再仅靠 parent_span_id 推导，而是直接嵌入完整因果路径。
   * 这样 WHY Engine 不需要回查 causal kernel 即可解释因果。
   */
  causal_chain?: string[];

  // ── 分类 ──
  /** 系统层级 */
  layer: SystemLayer;
  /** 服务来源 */
  service: TraceService;
  /** Span 类型 */
  kind: SpanKind;

  // ── 时间 ──
  /** 开始时间（ISO 8601） */
  start_time: string;
  /** 结束时间（ISO 8601） */
  end_time?: string;
  /** 持续时长（ms） */
  duration_ms?: number;

  // ── 状态 ──
  /** Span 状态 */
  status: SpanStatus;
  /** 错误信息（如有） */
  error?: string;

  // ── v5 OS-level 升级：WHY 核心（结构化决策与解释，不再散装在 metadata） ──
  /**
   * 决策结构（v5 关键新增）
   *
   * 记录"这个 span 为什么被执行"的结构化决策信息：
   * - 触发事件、匹配规则、权威层级、enforcement 动作、使用的 snapshot
   */
  decision?: TraceDecision;
  /**
   * 解释结构（v5 关键新增）
   *
   * 人类可读 WHY + 因果路径 + 替代路径考虑（反事实分析基础）
   */
  explanation?: TraceExplanation;

  // ── 元数据 ──
  /** 结构化元数据 */
  metadata: SpanMetadata;
}

/**
 * Trace 决策结构（v5 OS-level WHY 核心）
 *
 * 描述"这个执行行为是被哪个决策触发的"
 * 区别于 metadata（散装属性），decision 是结构化的可推理字段
 */
export interface TraceDecision {
  /** 触发该 span 的事件 ID（决策的起点） */
  trigger_event_id: string;
  /** 匹配的规则 ID 列表（可能多条规则同时命中） */
  rule_matched: string[];
  /** 权威层级（L1/L2/L3/L4/L5，决策来自哪一层） */
  authority_level: SystemLayer;
  /** enforcement 动作（ALLOW/BLOCK/MODIFY/QUARANTINE，如适用） */
  enforcement_action?: string;
  /** 使用的 snapshot ID（如该 span 来自 snapshot restore） */
  snapshot_used?: string;
  /** 决策时间戳 */
  decided_at: string;
}

/**
 * Trace 解释结构（v5 OS-level WHY 核心）
 *
 * 描述"这个执行行为的完整 WHY 解释"
 * 包含因果路径 + 替代路径考虑（反事实分析基础）
 */
export interface TraceExplanation {
  /** 人类可读的 WHY 摘要 */
  summary: string;
  /** 因果路径（event_id 列表，从根到当前） */
  causal_path: string[];
  /**
   * 替代路径考虑（反事实分析基础）
   *
   * 记录在决策时考虑过但未采纳的替代路径。
   * 例如：rule A 触发 BLOCK，但同时也考虑了 rule B（ALLOW，但优先级低）。
   * 这是反事实分析（counterfactual）的数据基础。
   */
  alternatives_considered: AlternativePath[];
  /** 生成时间 */
  generated_at: string;
}

/**
 * 替代路径（反事实分析数据结构）
 */
export interface AlternativePath {
  /** 替代路径标识 */
  alternative_id: string;
  /** 来源（rule_id / policy_id / authority_level） */
  source: string;
  /** 该替代路径会产生的决策 */
  proposed_decision: string;
  /** 为何未采纳 */
  rejection_reason: string;
  /** 该路径的预期后果（如采纳会发生什么） */
  expected_consequence?: string;
}

/**
 * Span 元数据 — 结构化补充信息
 */
export interface SpanMetadata {
  /** 操作名称 */
  operation?: string;
  /** 输入摘要 */
  input_summary?: string;
  /** 输出摘要 */
  output_summary?: string;
  /** 关联的策略 ID */
  policy_id?: string;
  /** 关联的规则 ID */
  rule_id?: string;
  /** 决策结果（enforcement） */
  decision?: string;
  /** 恢复策略（recovery） */
  recovery_strategy?: string;
  /** 自定义标签 */
  tags?: Record<string, string>;
  /** 自定义属性 */
  attributes?: Record<string, unknown>;
}

// ═══════════════════════════════════════════════════════════════
// 2️⃣ Span Edge — Span 之间的边
// ═══════════════════════════════════════════════════════════════

/**
 * Span 边类型 — 描述 span 之间的关系
 */
export type SpanEdgeType =
  | "parent_child"       // 父子关系（调用树）
  | "causal_link"        // 因果关系
  | "event_link"         // 事件关联
  | "snapshot_link"      // 快照关联
  | "enforcement_link"  // enforcement 关联
  | "follows_from";      // 因果跟随（happens-before）

/**
 * Span 边 — 描述两个 span 之间的关系
 */
export interface SpanEdge {
  /** 源 span */
  from: string;
  /** 目标 span */
  to: string;
  /** 边类型 */
  type: SpanEdgeType;
  /** 关联的 causal_link（如适用） */
  causal_relation?: CausalRelation;
  /** 权重 */
  weight?: number;
}

// ═══════════════════════════════════════════════════════════════
// 3️⃣ TraceGraph — Trace 图
// ═══════════════════════════════════════════════════════════════

/**
 * Trace 图 — 完整的 trace 结构
 */
export interface TraceGraph {
  /** trace_id */
  trace_id: string;
  /** 所有 span 节点 */
  nodes: SystemTraceEvent[];
  /** 所有 span 边 */
  edges: SpanEdge[];
  /** 根 span（trace 起点） */
  root_spans: SystemTraceEvent[];
  /** 关键路径 */
  critical_path: string[];
  /** 统计信息 */
  stats: TraceStats;
}

/**
 * Trace 统计信息
 */
export interface TraceStats {
  /** span 总数 */
  span_count: number;
  /** 边总数 */
  edge_count: number;
  /** 根 span 数 */
  root_count: number;
  /** 最大深度 */
  max_depth: number;
  /** 总耗时（ms） */
  total_duration_ms: number;
  /** 最长 span 耗时（ms） */
  longest_span_ms: number;
  /** 涉及的服务数 */
  service_count: number;
  /** 涉及的层级数 */
  layer_count: number;
  /** 错误 span 数 */
  error_span_count: number;
}

// ═══════════════════════════════════════════════════════════════
// 4️⃣ WHY Engine — 解释结构
// ═══════════════════════════════════════════════════════════════

/**
 * 策略决策记录 — 用于 WHY 解释
 */
export interface PolicyDecision {
  /** 策略 ID */
  policy_id: string;
  /** 策略名称 */
  policy_name: string;
  /** 规则 ID */
  rule_id: string;
  /** 决策结果 */
  decision: string;
  /** 决策原因 */
  reason: string;
  /** 决策时间 */
  decided_at: string;
  /** 关联的 span_id */
  span_id?: string;
}

/**
 * Enforcement 干预记录
 */
export interface EnforcementRecord {
  /** enforcement loop ID */
  loop_id: string;
  /** 最终决策 */
  final_decision: string;
  /** 是否被修改 */
  modified: boolean;
  /** 修改详情 */
  modification_details?: string;
  /** 是否被阻断 */
  blocked: boolean;
  /** 阻断原因 */
  block_reason?: string;
  /** 关联的策略 */
  policy_id?: string;
  /** 关联的规则 */
  rule_id?: string;
  /** 干预时间 */
  intervened_at: string;
}

/**
 * WHY 解释 — 完整的"为什么"解释结构
 *
 * 回答：
 * - 为什么这个 event 被执行？
 * - 它依赖哪个 causal path？
 * - 被哪个 policy 放行/阻断？
 * - 是否来自 snapshot replay？
 * - 是否来自 enforcement modification？
 */
export interface WhyExplanation {
  /** 查询的 trace_id */
  trace_id: string;
  /** 查询的 event_id（如指定） */
  event_id?: string;
  /** 关联的 span_id */
  span_id?: string;

  /** 根因链 — 从根 span 到当前 span 的完整路径 */
  root_cause_chain: SystemTraceEvent[];

  /** 决策路径 — 涉及的所有 policy 决策 */
  decision_path: PolicyDecision[];

  /** 因果路径 — 涉及的 causal links */
  causal_path: CausalLink[];

  /** Snapshot 来源（如来自 snapshot replay） */
  snapshot_origin?: {
    snapshot_id: string;
    cursor: number;
    restored_at: string;
  };

  /** Enforcement 干预（如有） */
  enforcement_intervention?: EnforcementRecord;

  /** 置信度分数（0-1） */
  confidence_score: number;

  /** 人类可读的解释摘要 */
  summary: string;

  /** 生成时间 */
  generated_at: string;
}

// ═══════════════════════════════════════════════════════════════
// 5️⃣ Critical Path Analyzer — 关键路径分析
// ═══════════════════════════════════════════════════════════════

/**
 * 关键路径报告
 */
export interface CriticalPathReport {
  /** trace_id */
  trace_id: string;
  /** 延迟热路径（最高延迟链） */
  latency_hotpath: SpanPath[];
  /** 因果热路径（最长因果链） */
  causal_hotpath: SpanPath[];
  /** Enforcement 干预热路径（最多策略干预链） */
  enforcement_hotpath: SpanPath[];
  /**
   * 决策热路径（v5 OS-level 新增：决策密度最高的链）
   *
   * 与 enforcement_hotpath 的区别：
   * - enforcement_hotpath: 统计 enforcement_stage/policy_evaluation/gate_decision span 数
   * - decision_hotpath: 统计含 decision 字段（结构化决策）的 span 数 + 决策复杂度
   *
   * v5 OS-level：决策密度 + 决策复杂度（含 alternatives_considered）
   */
  decision_hotpath: SpanPath[];
  /** 分析时间 */
  analyzed_at: string;
  /** 总耗时 */
  total_duration_ms: number;
}

/**
 * Span 路径 — 一条 span 链
 */
export interface SpanPath {
  /** 路径上的 span_id 列表（有序） */
  span_ids: string[];
  /** 路径上的 span 列表 */
  spans: SystemTraceEvent[];
  /** 路径总耗时（ms） */
  total_duration_ms: number;
  /** 路径跨度数 */
  span_count: number;
  /** 路径描述 */
  description: string;
}

// ═══════════════════════════════════════════════════════════════
// 6️⃣ Execution Profile — 执行画像
// ═══════════════════════════════════════════════════════════════

/**
 * 执行画像 — 单次执行的完整画像
 */
export interface ExecutionProfile {
  /** profile ID */
  profile_id: string;
  /** trace_id */
  trace_id: string;
  /** 开始时间 */
  started_at: string;
  /** 结束时间 */
  ended_at: string;
  /** 总耗时 */
  total_duration_ms: number;
  /** span 数量 */
  span_count: number;
  /** 事件数量 */
  event_count: number;
  /** enforcement 决策数 */
  enforcement_decisions: number;
  /** 阻断数 */
  blocked_count: number;
  /** 修改数 */
  modified_count: number;
  /** 恢复次数 */
  recovery_count: number;
  /** snapshot 使用数 */
  snapshot_count: number;
  /** 服务分布 */
  service_distribution: Record<TraceService, number>;
  /** 层级分布 */
  layer_distribution: Record<SystemLayer, number>;
  /** 关键路径 */
  critical_path: string[];
}

// ═══════════════════════════════════════════════════════════════
// 7️⃣ Span Engine — Span 创建参数
// ═══════════════════════════════════════════════════════════════

/**
 * Span 创建参数
 */
export interface CreateSpanParams {
  trace_id: string;
  parent_span_id?: string;
  layer: SystemLayer;
  service: TraceService;
  kind: SpanKind;
  event_id?: string;
  causal_ref_id?: string;
  snapshot_id?: string;
  enforcement_loop_id?: string;
  metadata?: SpanMetadata;
}

/**
 * Span 查询过滤器
 */
export interface SpanFilter {
  trace_id?: string;
  layer?: SystemLayer | SystemLayer[];
  service?: TraceService | TraceService[];
  kind?: SpanKind | SpanKind[];
  status?: SpanStatus | SpanStatus[];
  start_time_from?: string;
  start_time_to?: string;
  min_duration_ms?: number;
  max_duration_ms?: number;
}

// ═══════════════════════════════════════════════════════════════
// 8️⃣ v5 OS-level 升级：Decision Graph — 决策图（三图合一的缺失环节）
// ═══════════════════════════════════════════════════════════════

/**
 * Decision Graph 节点 — 决策图节点
 *
 * 区别于 Span（执行跨度），DecisionNode 描述"一个决策点"：
 * - 触发事件、匹配规则、最终决策、被考虑的替代路径
 *
 * 三图关系：
 *   Execution Graph (Span Tree)  — "做了什么"
 *   Causal Graph (Event DAG)    — "什么导致什么"
 *   Decision Graph (本文)        — "为什么这么做"  ← v5 新增
 */
export interface DecisionNode {
  /** 决策节点 ID */
  decision_id: string;
  /** 关联的 trace_id */
  trace_id: string;
  /** 关联的 span_id（决策发生在哪个 span 内） */
  span_id: string;
  /** 触发决策的事件 ID */
  trigger_event_id: string;
  /** 匹配的规则 ID 列表 */
  rules_matched: string[];
  /** 权威层级（决策来自哪一层） */
  authority_level: SystemLayer;
  /** 最终决策（ALLOW/BLOCK/MODIFY/QUARANTINE 等） */
  final_decision: string;
  /** 被考虑的替代路径（反事实分析基础） */
  alternatives: AlternativePath[];
  /** 决策时间 */
  decided_at: string;
  /** 决策元数据 */
  metadata?: {
    policy_id?: string;
    enforcement_loop_id?: string;
    snapshot_id?: string;
    reason?: string;
  };
}

/**
 * Decision Graph 边 — 决策间的因果关系
 *
 * 描述"决策 A 导致决策 B"（决策间也有因果链）
 */
export interface DecisionEdge {
  /** 源决策 ID */
  from: string;
  /** 目标决策 ID */
  to: string;
  /** 边类型 */
  type: DecisionEdgeType;
  /** 权重 */
  weight?: number;
}

/**
 * 决策边类型
 */
export type DecisionEdgeType =
  | "triggered"        // A 触发了 B（A 的决策结果导致 B 发生）
  | "overridden_by"    // A 被 B 覆盖（高优先级规则覆盖低优先级）
  | "escalated_to"     // A 升级到 B（低层级决策升级到高层级）
  | "alternative_of"   // A 是 B 的替代（互斥决策）
  | "depends_on";      // A 依赖 B（B 必须先发生，A 才能发生）

/**
 * Decision Graph — 决策图
 *
 * v5 核心新增：将散落在 span 中的 decision 字段聚合为图结构
 *
 * 三图合一：
 *   Execution Graph + Causal Graph + Decision Graph = OS-level explainability
 */
export interface DecisionGraph {
  /** trace_id */
  trace_id: string;
  /** 决策节点列表 */
  nodes: DecisionNode[];
  /** 决策边列表 */
  edges: DecisionEdge[];
  /** 根决策（无入边的决策，通常是第一个 enforcement 决策） */
  root_decisions: DecisionNode[];
  /** 决策统计 */
  stats: DecisionGraphStats;
}

/**
 * 决策图统计
 */
export interface DecisionGraphStats {
  /** 决策总数 */
  decision_count: number;
  /** 边总数 */
  edge_count: number;
  /** 根决策数 */
  root_count: number;
  /** 各决策类型计数 */
  by_decision: Record<string, number>;
  /** 平均替代路径数（反事实分析密度） */
  avg_alternatives: number;
  /** 涉及的权威层级数 */
  authority_levels: number;
  /** 最大决策链深度 */
  max_depth: number;
}

// ═══════════════════════════════════════════════════════════════
// 9️⃣ v5 OS-level 升级：Counterfactual Analysis — 反事实分析
// ═══════════════════════════════════════════════════════════════

/**
 * 反事实分析结果 — "如果 X 没发生，会怎样？"
 *
 * v5 OS-level 关键能力：基于 alternatives_considered 进行反事实推理
 *
 * 原则：Observability cannot mutate state
 *      反事实分析是"假设性推理"，不修改实际事件流
 */
export interface CounterfactualAnalysis {
  /** 查询的 trace_id */
  trace_id: string;
  /** 假设条件：假设这个 event 没发生 */
  hypothetical_event_id: string;
  /** 假设条件：假设这个决策不同 */
  hypothetical_decision?: string;
  /** 实际发生的决策 */
  actual_decision: string;
  /** 实际因果路径 */
  actual_causal_path: string[];
  /** 反事实推演的预期后果 */
  projected_consequence: string;
  /** 预期影响的 span（如该决策不同，哪些 span 不会发生） */
  affected_spans: string[];
  /** 推演依据（基于哪些 alternatives_considered） */
  based_on_alternatives: AlternativePath[];
  /** 置信度（0-1，基于替代路径的数据完整度） */
  confidence: number;
  /** 分析时间 */
  analyzed_at: string;
}
