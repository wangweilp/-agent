/**
 * 知维 OS Replay Engine — 状态类型定义
 * Zhiwei OS Replay Engine — State Types
 *
 * L2 Replay Engine 核心：
 * - SystemState: 系统状态快照（runtime + memory + governance）
 * - ReplayFrame: 单步回放帧（state_before + event + state_after）
 * - ExecutionState: 执行状态机
 */

import type { SystemEvent, EventSource, EventType } from "@/types/event-bus";

// ═══════════════════════════════════════════════════════════════
// Runtime State — 运行时控制面状态
// ═══════════════════════════════════════════════════════════════

export interface KillSwitchRecord {
  target_id: string;
  target_type: string;
  reason: string;
  status: "triggered" | "completed";
  timestamp: string;
}

export interface GateRecord {
  gate_type: string;
  target_id: string;
  decision: "allowed" | "denied";
  violated_rules: string[];
  timestamp: string;
}

export interface SandboxRecord {
  handle_id: string;
  state: "violation" | "terminated";
  reason: string;
  timestamp: string;
}

export interface RuntimeState {
  kill_switches: KillSwitchRecord[];
  gate_decisions: GateRecord[];
  sandbox_events: SandboxRecord[];
  active_handles: Set<string>;
}

// ═══════════════════════════════════════════════════════════════
// Memory State — 认知面状态
// ═══════════════════════════════════════════════════════════════

export interface MemoryRecord {
  memory_id: string;
  tier: "stm" | "wm" | "ltm";
  memory_type: string;
  content_preview: string;
  importance: number;
  source: string;
  entities: string[];
  timestamp: string;
}

export interface ReflectionRecord {
  trigger_reason: string;
  insights_generated: number;
  topics: string[];
  timestamp: string;
}

export interface MemoryState {
  memories: Map<string, MemoryRecord>;
  reflections: ReflectionRecord[];
  conflicts: Array<{ memory_ids: string[]; conflict_type: string; timestamp: string }>;
  retrievals: Array<{ query: string; hits_count: number; timestamp: string }>;
}

// ═══════════════════════════════════════════════════════════════
// Governance State — 治理面状态
// ═══════════════════════════════════════════════════════════════

export interface PolicyEvaluationRecord {
  policy_id: string;
  policy_name: string;
  decision: "allowed" | "denied";
  violations: string[];
  timestamp: string;
}

export interface IncidentRecord {
  incident_id: string;
  title: string;
  severity: "critical" | "high" | "medium" | "low";
  status: "open" | "resolved";
  timestamp: string;
  resolution?: string;
}

export interface AuditRecord {
  audit_id: string;
  action: string;
  resource_id: string;
  actor: string;
  timestamp: string;
}

export interface GovernanceState {
  policy_evaluations: PolicyEvaluationRecord[];
  incidents: Map<string, IncidentRecord>;
  audit_records: AuditRecord[];
  blocked_executions: Array<{ target_id: string; reason: string; timestamp: string }>;
}

// ═══════════════════════════════════════════════════════════════
// System State — 完整系统状态快照
// ═══════════════════════════════════════════════════════════════

export interface SystemState {
  runtime: RuntimeState;
  memory: MemoryState;
  governance: GovernanceState;
  /** 状态版本（每次 applyEvent 递增） */
  version: number;
  /** 最后应用的 event_id */
  last_applied_event_id: string | null;
  /** 最后应用时间 */
  last_applied_timestamp: string | null;
}

// ═══════════════════════════════════════════════════════════════
// Replay Frame — 单步回放帧
// ═══════════════════════════════════════════════════════════════

export interface ReplayFrame {
  /** 帧序号（从 0 开始） */
  index: number;
  /** 应用事件前的状态快照 */
  state_before: SystemState;
  /** 应用的事件 */
  event: SystemEvent;
  /** 应用事件后的状态快照 */
  state_after: SystemState;
  /** 该事件是否成功应用 */
  applied: boolean;
  /** 应用失败原因（如因果顺序违反） */
  error?: string;
}

// ═══════════════════════════════════════════════════════════════
// Execution State — 执行状态机
// ═══════════════════════════════════════════════════════════════

export type ExecutionStatus =
  | "idle"        // 未开始
  | "playing"     // 自动播放中
  | "paused"      // 已暂停
  | "step_forward" // 单步前进
  | "step_backward" // 单步后退
  | "completed"   // 已完成
  | "error";      // 错误

export interface ExecutionState {
  status: ExecutionStatus;
  /** 当前游标位置（已执行的帧数） */
  cursor: number;
  /** 总帧数 */
  total_frames: number;
  /** 当前状态 */
  current_state: SystemState;
  /** 执行历史（所有帧） */
  frames: ReplayFrame[];
  /** 已执行的 event_id 集合（因果顺序验证用） */
  executed_event_ids: Set<string>;
  /** 最后错误 */
  last_error: string | null;
}

// ═══════════════════════════════════════════════════════════════
// 工厂函数
// ═══════════════════════════════════════════════════════════════

/** 创建初始空状态 */
export function createInitialState(): SystemState {
  return {
    runtime: {
      kill_switches: [],
      gate_decisions: [],
      sandbox_events: [],
      active_handles: new Set(),
    },
    memory: {
      memories: new Map(),
      reflections: [],
      conflicts: [],
      retrievals: [],
    },
    governance: {
      policy_evaluations: [],
      incidents: new Map(),
      audit_records: [],
      blocked_executions: [],
    },
    version: 0,
    last_applied_event_id: null,
    last_applied_timestamp: null,
  };
}

/** 创建初始执行状态 */
export function createInitialExecutionState(): ExecutionState {
  return {
    status: "idle",
    cursor: 0,
    total_frames: 0,
    current_state: createInitialState(),
    frames: [],
    executed_event_ids: new Set(),
    last_error: null,
  };
}
