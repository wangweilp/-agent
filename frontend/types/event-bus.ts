/**
 * 知维 OS 因果内核 — 统一事件模型
 * Zhiwei OS Causal Kernel — Unified Event Model
 *
 * 设计原则：
 * 1. 所有系统行为事件化（runtime / memory / governance / agent / observability）
 * 2. 每个事件携带因果信息（parent_event_id + cause_type），可构建因果链
 * 3. 每个事件携带 trace_id，支持完整回放（Replay）
 * 4. payload 强结构化，禁止自由文本日志
 * 5. 事件是系统第一公民，UI 订阅事件流实现事件驱动 UI
 */

// ═══════════════════════════════════════════════════════════════
// 基础枚举：事件来源 / 严重级别 / 因果类型
// ═══════════════════════════════════════════════════════════════

/** 事件来源系统 — 五大平面 */
export type EventSource =
  | "runtime" // 运行时控制面（Kill Switch / Gate / Sandbox）
  | "memory" // 认知面（STM / WM / LTM / Reflection）
  | "governance" // 治理面（Policy / Audit / Incident）
  | "agent" // 执行面（Agent 决策 / 工具调用）
  | "observability"; // 可观测面（Trace / Metric）

/** 事件严重级别 */
export type EventSeverity = "info" | "warn" | "critical";

/**
 * 因果类型 — 描述事件为何发生
 * 这是因果链的核心，用于区分"谁触发了什么"
 */
export type CauseType =
  | "user_action" // 用户行为触发（如点击 Kill Switch）
  | "system_policy" // 系统策略触发（如 Gate 拒绝）
  | "agent_decision" // Agent 自主决策（如调用工具）
  | "system_event" // 系统内部事件（如超时、状态变更）
  | "external_trigger"; // 外部触发（如 Webhook、定时任务）

// ═══════════════════════════════════════════════════════════════
// 统一事件结构
// ═══════════════════════════════════════════════════════════════

/**
 * 因果关系类型 — 描述事件之间的因果关系
 * 用于构建因果图（DAG），支持多父节点
 */
export type CausalRelation =
  | "caused_by" // 直接因果（A 导致 B）
  | "influenced_by" // 影响关系（A 影响 B 的决策）
  | "blocked_by" // 阻断关系（A 阻止 B 执行）
  | "triggered_by"; // 触发关系（A 触发 B 发生）

/**
 * 因果边 — 描述两个事件之间的因果关系
 * 一个事件可以有多条入边（多父），构成因果图而非因果树
 */
export interface CausalLink {
  /** 父事件 ID */
  from: string;
  /** 关系类型 */
  relation: CausalRelation;
  /** 因果强度权重（0-1，默认 1.0） */
  weight?: number;
}

/**
 * 因果信息 — 每个事件必须携带
 * 支持单父（向后兼容）+ 多父（图结构）
 */
export interface EventCausal {
  /** 主父事件 ID（null 表示根事件，即因果链起点）— 向后兼容字段 */
  parent_event_id: string | null;
  /** 因果类型 — 描述本事件与主父事件的因果关系 */
  cause_type: CauseType;
  /** 因果元数据（可选，结构化补充信息） */
  cause_metadata?: Record<string, unknown>;
  /**
   * 多父因果边（图结构核心）— 支持一个事件由多个事件共同导致
   * 例如：runtime.gate.denied 可同时 caused_by agent.decision + influenced_by governance.policy
   * 若为空，则退化为单父树结构（使用 parent_event_id）
   */
  causal_links?: CausalLink[];
}

// ═══════════════════════════════════════════════════════════════
// 事件来源标记 — 区分真实后端事件与模拟事件（L2 Replay Engine）
// ═══════════════════════════════════════════════════════════════

/**
 * 事件来源标记 — L2 Replay Engine 核心
 * - backend:   来自 Python EventBus 的真实事件（经 SSE bridge 接入）
 * - simulated: 前端 simulate 函数生成的测试事件
 *
 * Replay Engine 仅对 backend 事件执行 state reconstruction，
 * simulated 事件仅用于演示，不参与 deterministic replay。
 */
export type EventOrigin = "backend" | "simulated";

// ═══════════════════════════════════════════════════════════════
// 统一事件结构
// ═══════════════════════════════════════════════════════════════

/**
 * 知维 OS 统一事件结构
 * 所有系统行为的唯一表示形式
 */
export interface SystemEvent {
  // ── 身份标识 ──
  /** 事件唯一 ID（UUID v4） */
  event_id: string;
  /** 事件发生时间（ISO 8601，带时区） */
  timestamp: string;

  // ── 来源与类型 ──
  /** 来源系统 */
  source: EventSource;
  /** 事件类型（强类型联合，见下方 EventType） */
  type: EventType;
  /** 严重级别 */
  severity: EventSeverity;

  // ── 链路追踪 ──
  /** Trace ID — 同一链路的所有事件共享，用于回放 */
  trace_id: string;

  // ── 结构化载荷 ──
  /** 事件载荷（强结构化，禁止自由文本） */
  payload: EventPayload;

  // ── 因果链（核心） ──
  /** 因果信息 — 构建因果链 / 决策链 / 行为链 */
  causal: EventCausal;

  // ── 来源标记（L2 Replay Engine） ──
  /**
   * 事件来源标记 — 区分真实后端事件与模拟事件
   * - backend:   来自 Python EventBus（经 SSE bridge）
   * - simulated: 前端 simulate 函数生成
   * 默认 simulated（向后兼容）
   */
  origin?: EventOrigin;
}

// ═══════════════════════════════════════════════════════════════
// 事件类型分类法（EventType）
// ═══════════════════════════════════════════════════════════════

/**
 * Runtime Events — 运行时控制面事件
 * 来源：Kill Switch / Gate Matrix / Sandbox
 */
export type RuntimeEventType =
  | "runtime.kill_switch.triggered" // Kill Switch 被触发
  | "runtime.kill_switch.completed" // Kill 执行完成
  | "runtime.gate.denied" // Gate 拒绝执行
  | "runtime.gate.allowed" // Gate 允许执行
  | "runtime.sandbox.violation" // 沙箱违规
  | "runtime.sandbox.terminated" // 沙箱终止
  | "runtime.handle.cancel_requested"; // 句柄取消请求

/**
 * Memory Events — 认知面事件
 * 来源：STM / WM / LTM / Reflection / Retrieval
 */
export type MemoryEventType =
  | "memory.write.stm" // 写入短期记忆
  | "memory.write.wm" // 写入工作记忆
  | "memory.write.ltm" // 写入长期记忆
  | "memory.archive.executed" // 记忆归档
  | "memory.merge.executed" // 记忆合并
  | "memory.reflection.triggered" // 反思触发
  | "memory.reflection.completed" // 反思完成
  | "memory.conflict.detected" // 冲突检测
  | "memory.conflict.resolved" // 冲突解决
  | "memory.retrieval.executed"; // 检索执行

/**
 * Governance Events — 治理面事件
 * 来源：Policy / Audit / Incident
 */
export type GovernanceEventType =
  | "governance.policy.evaluated" // 策略评估
  | "governance.policy.violation" // 策略违规
  | "governance.execution.blocked" // 执行被阻断
  | "governance.audit.record_generated" // 审计记录生成
  | "governance.incident.created" // 事件创建
  | "governance.incident.resolved"; // 事件解决

/**
 * Agent Events — 执行面事件
 * 来源：Agent 决策 / 工具调用
 */
export type AgentEventType =
  | "agent.decision.made" // Agent 决策
  | "agent.tool.called" // 工具调用
  | "agent.tool.completed" // 工具完成
  | "agent.action.started" // 动作开始
  | "agent.action.completed" // 动作完成
  | "agent.reflection.triggered"; // Agent 反思触发

/**
 * Observability Events — 可观测面事件
 * 来源：Trace / Metric
 */
export type ObservabilityEventType =
  | "observability.trace.started" // Trace 开始
  | "observability.trace.completed" // Trace 完成
  | "observability.metric.recorded"; // 指标记录

/** 全部事件类型联合 */
export type EventType =
  | RuntimeEventType
  | MemoryEventType
  | GovernanceEventType
  | AgentEventType
  | ObservabilityEventType;

// ═══════════════════════════════════════════════════════════════
// 结构化 Payload（按事件类型定义）
// ═══════════════════════════════════════════════════════════════

/** 事件载荷联合类型 — 强结构化 */
export type EventPayload =
  | RuntimeEventPayload
  | MemoryEventPayload
  | GovernanceEventPayload
  | AgentEventPayload
  | ObservabilityEventPayload;

// ── Runtime Payloads ──

export interface KillSwitchTriggeredPayload {
  target_type: "job" | "execution-plan" | "container-plan";
  target_id: string;
  reason: string;
  force: boolean;
  requested_by: string;
}

export interface KillSwitchCompletedPayload {
  target_id: string;
  action_taken: string;
  status_before: string;
  status_after: string;
  provider: string;
  duration_ms: number;
}

export interface GateDeniedPayload {
  gate_type: "download" | "artifact" | "package";
  target_id: string;
  violated_rules: string[];
  requested_resource: string;
}

export interface GateAllowedPayload {
  gate_type: "download" | "artifact" | "package";
  target_id: string;
  matched_rules: string[];
}

export interface SandboxViolationPayload {
  handle_id: string;
  violation_type: string;
  description: string;
  severity_level: string;
}

export interface SandboxTerminatedPayload {
  handle_id: string;
  reason: string;
  cleanup_actions: string[];
}

export interface HandleCancelRequestedPayload {
  handle_id: string;
  reason: string;
  requested_by: string;
}

export type RuntimeEventPayload =
  | KillSwitchTriggeredPayload
  | KillSwitchCompletedPayload
  | GateDeniedPayload
  | GateAllowedPayload
  | SandboxViolationPayload
  | SandboxTerminatedPayload
  | HandleCancelRequestedPayload;

// ── Memory Payloads ──

export interface MemoryWritePayload {
  memory_id: string;
  tier: "stm" | "wm" | "ltm";
  memory_type: "episodic" | "semantic" | "procedural" | "reflect";
  content_preview: string;
  importance: number;
  source: "user" | "agent" | "reflect";
  entities: string[];
}

export interface MemoryArchivePayload {
  memory_id: string;
  archived_at: string;
  reason: string;
}

export interface MemoryMergePayload {
  primary_id: string;
  merged_ids: string[];
  merged_count: number;
  reason: string;
}

export interface ReflectionTriggeredPayload {
  trigger_reason: string;
  scan_scope: string[];
}

export interface ReflectionCompletedPayload {
  insights_generated: number;
  topics: string[];
  duration_ms: number;
}

export interface ConflictDetectedPayload {
  memory_ids: string[];
  conflict_type: string;
  description: string;
}

export interface ConflictResolvedPayload {
  primary_id: string;
  resolved_ids: string[];
  resolution_strategy: string;
}

export interface RetrievalExecutedPayload {
  query: string;
  top_k: number;
  hits_count: number;
  top_score: number;
  duration_ms: number;
}

export type MemoryEventPayload =
  | MemoryWritePayload
  | MemoryArchivePayload
  | MemoryMergePayload
  | ReflectionTriggeredPayload
  | ReflectionCompletedPayload
  | ConflictDetectedPayload
  | ConflictResolvedPayload
  | RetrievalExecutedPayload;

// ── Governance Payloads ──

export interface PolicyEvaluatedPayload {
  policy_id: string;
  policy_name: string;
  decision: "allowed" | "denied";
  evaluated_rules: string[];
  violations: string[];
  warnings: string[];
}

export interface PolicyViolationPayload {
  policy_id: string;
  violation_type: string;
  description: string;
  target_id: string;
}

export interface ExecutionBlockedPayload {
  target_id: string;
  target_type: string;
  blocking_policy: string;
  reason: string;
}

export interface AuditRecordGeneratedPayload {
  audit_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  actor: string;
}

export interface IncidentCreatedPayload {
  incident_id: string;
  title: string;
  severity: "critical" | "high" | "medium" | "low";
  related_runtime: string;
  description: string;
}

export interface IncidentResolvedPayload {
  incident_id: string;
  resolution: string;
  resolved_by: string;
  duration_ms: number;
}

export type GovernanceEventPayload =
  | PolicyEvaluatedPayload
  | PolicyViolationPayload
  | ExecutionBlockedPayload
  | AuditRecordGeneratedPayload
  | IncidentCreatedPayload
  | IncidentResolvedPayload;

// ── Agent Payloads ──

export interface AgentDecisionPayload {
  agent_id: string;
  decision: string;
  reasoning: string;
  confidence: number;
  alternatives_considered: string[];
}

export interface ToolCalledPayload {
  tool_name: string;
  call_id: string;
  arguments: Record<string, unknown>;
  risk_level: "low" | "medium" | "high";
}

export interface ToolCompletedPayload {
  call_id: string;
  tool_name: string;
  success: boolean;
  duration_ms: number;
  error: string | null;
}

export interface AgentActionPayload {
  agent_id: string;
  action_type: string;
  target: string;
  status: "started" | "completed";
  duration_ms?: number;
}

export interface AgentReflectionTriggeredPayload {
  agent_id: string;
  trigger: string;
  scope: string[];
}

export type AgentEventPayload =
  | AgentDecisionPayload
  | ToolCalledPayload
  | ToolCompletedPayload
  | AgentActionPayload
  | AgentReflectionTriggeredPayload;

// ── Observability Payloads ──

export interface TraceStartedPayload {
  trace_id: string;
  trigger: string;
  context: Record<string, unknown>;
}

export interface TraceCompletedPayload {
  trace_id: string;
  event_count: number;
  duration_ms: number;
  status: "success" | "failed" | "partial";
}

export interface MetricRecordedPayload {
  metric_name: string;
  value: number;
  unit: string;
  tags: Record<string, string>;
}

export type ObservabilityEventPayload =
  | TraceStartedPayload
  | TraceCompletedPayload
  | MetricRecordedPayload;

// ═══════════════════════════════════════════════════════════════
// 因果链结构
// ═══════════════════════════════════════════════════════════════

/** 因果链节点 — 用于构建因果树 */
export interface CausalChainNode {
  event: SystemEvent;
  children: CausalChainNode[];
  depth: number;
}

/** 因果路径 — 从根到叶的线性链 */
export interface CausalPath {
  events: SystemEvent[];
  depth: number;
}

// ═══════════════════════════════════════════════════════════════
// 订阅过滤器
// ═══════════════════════════════════════════════════════════════

/** 事件订阅过滤器 — 支持多维度过滤 */
export interface EventFilter {
  source?: EventSource | EventSource[];
  type?: EventType | EventType[];
  severity?: EventSeverity | EventSeverity[];
  trace_id?: string;
  /** 自定义谓词（高级过滤） */
  predicate?: (event: SystemEvent) => boolean;
}

/** 订阅句柄 — 用于取消订阅 */
export interface SubscriptionHandle {
  id: string;
  unsubscribe: () => void;
}

/** 事件处理器 */
export type EventHandler = (event: SystemEvent) => void;

// ═══════════════════════════════════════════════════════════════
// 事件构造辅助类型
// ═══════════════════════════════════════════════════════════════

/** 事件创建参数（不含自动生成的字段） */
export interface CreateEventParams {
  source: EventSource;
  type: EventType;
  severity: EventSeverity;
  trace_id: string;
  payload: EventPayload;
  causal: EventCausal;
}

/** 事件来源 → 事件类型 映射（类型安全约束） */
export interface SourceTypeMap {
  runtime: RuntimeEventType;
  memory: MemoryEventType;
  governance: GovernanceEventType;
  agent: AgentEventType;
  observability: ObservabilityEventType;
}

// ═══════════════════════════════════════════════════════════════
// Causal Graph 结构（图引擎核心）
// ═══════════════════════════════════════════════════════════════

/** 因果图节点 — 事件的图表示 */
export interface CausalGraphNode {
  event_id: string;
  type: EventType;
  source: EventSource;
  timestamp: string;
  severity: EventSeverity;
  trace_id: string;
  /** 影响分值（由 computeImpactScore 计算） */
  impact_score?: number;
  /** 下游节点数（因果链下游） */
  downstream_count?: number;
}

/** 因果图边 — 描述两个节点间的因果关系 */
export interface CausalGraphEdge {
  /** 源节点（父事件） */
  from: string;
  /** 目标节点（子事件） */
  to: string;
  /** 关系类型 */
  relation: CausalRelation;
  /** 因果强度权重（0-1） */
  weight: number;
  /** 是否属于关键路径 */
  is_critical_path?: boolean;
}

/** 因果图 — 完整的 DAG 结构 */
export interface CausalGraph {
  /** 节点表（event_id → node） */
  nodes: Map<string, CausalGraphNode>;
  /** 边列表 */
  edges: CausalGraphEdge[];
  /** 所属 trace_id */
  trace_id: string;
  /** 图统计 */
  stats: {
    node_count: number;
    edge_count: number;
    root_count: number; // 根节点数（无入边）
    leaf_count: number; // 叶节点数（无出边）
    max_depth: number;
  };
}

/** 关键路径 — runtime → governance → memory 的核心链路 */
export interface CriticalPath {
  nodes: CausalGraphNode[];
  edges: CausalGraphEdge[];
  total_impact: number;
}

// ═══════════════════════════════════════════════════════════════
// Event Projection Layer（投影层）
// ═══════════════════════════════════════════════════════════════

/** 投影维度 — 用于从全量事件流中提取子图 */
export type ProjectionDimension =
  | "trace_id" // 按 trace 投影
  | "source" // 按来源投影
  | "severity" // 按严重级别投影
  | "time_range"; // 按时间范围投影

/** 投影参数 */
export interface ProjectionParams {
  dimension: ProjectionDimension;
  trace_id?: string;
  source?: EventSource | EventSource[];
  severity?: EventSeverity | EventSeverity[];
  time_from?: string;
  time_to?: string;
  /** 最大节点数（防止 UI flood） */
  max_nodes?: number;
}

/** 投影结果 — 子图 */
export interface ProjectionResult {
  graph: CausalGraph;
  total_events_scanned: number;
  filtered_events: number;
}

// ═══════════════════════════════════════════════════════════════
// 保留策略（Retention Policy）
// ═══════════════════════════════════════════════════════════════

/** 事件保留策略 — 保证因果完整性 */
export interface RetentionPolicy {
  /**
   * Trace 锁定 — 属于该 trace 的所有事件永久保留，不被环形缓冲覆盖
   * 默认 true：保证因果图不断链
   */
  trace_id_lock: boolean;
  /**
   * 显式锁定的 trace 集合（即使 trace_id_lock=false 也保留）
   */
  locked_traces: Set<string>;
  /**
   * 环形缓冲容量（仅影响未锁定事件）
   */
  ring_capacity: number;
}
