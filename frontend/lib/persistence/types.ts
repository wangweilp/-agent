/**
 * 知维 OS Persistence Layer — 类型定义
 * Zhiwei OS Persistence Layer — Type Definitions
 *
 * 三层持久化结构：
 * 1. EventStore   — 持久化所有 SystemEvent（接口 + MemoryEventStore + IndexedDBEventStore）
 * 2. SnapshotStore — 持久化 SystemSnapshot（checkpoint + restore）
 * 3. Persistence Pipeline — event → EventStore → SnapshotStore → Replay Engine
 *
 * 约束：
 * - 不修改 Causal Graph
 * - 不修改 Replay Logic
 * - 只加持久化层
 * - 必须 backward compatible
 */

import type { SystemEvent } from "@/types/event-bus";
import type { SystemState } from "@/lib/replay/types";

// ═══════════════════════════════════════════════════════════════
// EventStore 接口定义
// ═══════════════════════════════════════════════════════════════

/**
 * EventStore — 事件持久化接口
 * 抽象层，支持多种后端实现（Memory / IndexedDB）
 *
 * 设计原则：
 * - 异步 API（兼容 IndexedDB）
 * - 不参与因果索引构建（仅持久化）
 * - 不参与订阅通知（由 CausalKernel 负责）
 */
export interface IEventStore {
  /** 存储单个事件 */
  put(event: SystemEvent): Promise<void>;

  /** 批量存储事件 */
  putBatch(events: SystemEvent[]): Promise<void>;

  /** 获取单个事件 */
  get(event_id: string): Promise<SystemEvent | null>;

  /** 按 trace_id 查询事件（按时间排序） */
  getByTraceId(trace_id: string): Promise<SystemEvent[]>;

  /** 时间范围查询 */
  getByTimeRange(from: string, to: string): Promise<SystemEvent[]>;

  /** 获取所有 trace_id */
  getTraceIds(): Promise<string[]>;

  /** 删除单个事件 */
  delete(event_id: string): Promise<void>;

  /** 清空所有事件 */
  clear(): Promise<void>;

  /** 获取事件总数 */
  count(): Promise<number>;
}

// ═══════════════════════════════════════════════════════════════
// SnapshotStore 接口定义
// ═══════════════════════════════════════════════════════════════

/**
 * 系统快照 — 完整状态检查点
 */
export interface SystemSnapshot {
  /** 快照唯一 ID */
  snapshot_id: string;
  /** 所属 trace_id */
  trace_id: string;
  /** 创建快照时的游标位置（已应用的事件数） */
  cursor: number;
  /** 序列化的 SystemState（JSON 字符串，兼容 Map/Set） */
  state: SerializedSystemState;
  /** 快照创建时间 */
  timestamp: string;
  /** 创建原因（auto_checkpoint / manual / restore_base） */
  reason: SnapshotReason;
  /** 快照包含的事件数 */
  event_count: number;
}

/**
 * 快照创建原因
 */
export type SnapshotReason =
  | "auto_checkpoint"   // 自动检查点（每 N 事件触发）
  | "manual"             // 手动创建
  | "restore_base"       // 作为恢复基点
  | "session_start"      // 会话开始
  | "session_end";       // 会话结束

/**
 * 序列化的 SystemState — 兼容 Map/Set 的 JSON 表示
 *
 * SystemState 含 Map<string, MemoryRecord> 和 Set<string>，
 * 无法直接 JSON.stringify，需要转换为普通对象/数组
 */
export interface SerializedSystemState {
  runtime: {
    kill_switches: import("@/lib/replay/types").KillSwitchRecord[];
    gate_decisions: import("@/lib/replay/types").GateRecord[];
    sandbox_events: import("@/lib/replay/types").SandboxRecord[];
    active_handles: string[]; // Set → array
  };
  memory: {
    memories: Array<[string, import("@/lib/replay/types").MemoryRecord]>; // Map → entries
    reflections: import("@/lib/replay/types").ReflectionRecord[];
    conflicts: import("@/lib/replay/types").MemoryState["conflicts"];
    retrievals: import("@/lib/replay/types").MemoryState["retrievals"];
  };
  governance: {
    policy_evaluations: import("@/lib/replay/types").PolicyEvaluationRecord[];
    incidents: Array<[string, import("@/lib/replay/types").IncidentRecord]>; // Map → entries
    audit_records: import("@/lib/replay/types").AuditRecord[];
    blocked_executions: import("@/lib/replay/types").GovernanceState["blocked_executions"];
  };
  version: number;
  last_applied_event_id: string | null;
  last_applied_timestamp: string | null;
}

/**
 * SnapshotStore — 快照持久化接口
 */
export interface ISnapshotStore {
  /** 存储快照 */
  put(snapshot: SystemSnapshot): Promise<void>;

  /** 获取单个快照 */
  get(snapshot_id: string): Promise<SystemSnapshot | null>;

  /** 按 trace_id 列出快照（按时间排序） */
  listByTraceId(trace_id: string): Promise<SystemSnapshot[]>;

  /** 获取 trace 最近的快照（用于 replay 加速） */
  getLatestByTraceId(trace_id: string): Promise<SystemSnapshot | null>;

  /** 获取指定游标之前的最近快照 */
  getLatestBeforeCursor(trace_id: string, cursor: number): Promise<SystemSnapshot | null>;

  /** 删除快照 */
  delete(snapshot_id: string): Promise<void>;

  /** 清空所有快照 */
  clear(): Promise<void>;

  /** 获取快照总数 */
  count(): Promise<number>;
}

// ═══════════════════════════════════════════════════════════════
// 序列化/反序列化工具
// ═══════════════════════════════════════════════════════════════

/**
 * 序列化 SystemState → SerializedSystemState
 * 将 Map/Set 转换为可 JSON 序列化的结构
 */
export function serializeState(state: SystemState): SerializedSystemState {
  return {
    runtime: {
      kill_switches: state.runtime.kill_switches,
      gate_decisions: state.runtime.gate_decisions,
      sandbox_events: state.runtime.sandbox_events,
      active_handles: Array.from(state.runtime.active_handles),
    },
    memory: {
      memories: Array.from(state.memory.memories.entries()),
      reflections: state.memory.reflections,
      conflicts: state.memory.conflicts,
      retrievals: state.memory.retrievals,
    },
    governance: {
      policy_evaluations: state.governance.policy_evaluations,
      incidents: Array.from(state.governance.incidents.entries()),
      audit_records: state.governance.audit_records,
      blocked_executions: state.governance.blocked_executions,
    },
    version: state.version,
    last_applied_event_id: state.last_applied_event_id,
    last_applied_timestamp: state.last_applied_timestamp,
  };
}

/**
 * 反序列化 SerializedSystemState → SystemState
 * 将数组/entries 转换回 Map/Set
 */
export function deserializeState(serialized: SerializedSystemState): SystemState {
  return {
    runtime: {
      kill_switches: serialized.runtime.kill_switches,
      gate_decisions: serialized.runtime.gate_decisions,
      sandbox_events: serialized.runtime.sandbox_events,
      active_handles: new Set(serialized.runtime.active_handles),
    },
    memory: {
      memories: new Map(serialized.memory.memories),
      reflections: serialized.memory.reflections,
      conflicts: serialized.memory.conflicts,
      retrievals: serialized.memory.retrievals,
    },
    governance: {
      policy_evaluations: serialized.governance.policy_evaluations,
      incidents: new Map(serialized.governance.incidents),
      audit_records: serialized.governance.audit_records,
      blocked_executions: serialized.governance.blocked_executions,
    },
    version: serialized.version,
    last_applied_event_id: serialized.last_applied_event_id,
    last_applied_timestamp: serialized.last_applied_timestamp,
  };
}

// ═══════════════════════════════════════════════════════════════
// Persistence Pipeline 配置
// ═══════════════════════════════════════════════════════════════

/**
 * 持久化管道配置
 */
export interface PersistenceConfig {
  /** 是否启用 EventStore 持久化 */
  enableEventStore: boolean;
  /** 是否启用 SnapshotStore */
  enableSnapshotStore: boolean;
  /** 自动检查点间隔（每 N 事件创建一个 snapshot） */
  autoCheckpointInterval: number;
  /** 最大快照数（超过则清理最旧的） */
  maxSnapshotsPerTrace: number;
  /** 是否在会话开始时自动创建快照 */
  snapshotOnSessionStart: boolean;
}

export const DEFAULT_PERSISTENCE_CONFIG: PersistenceConfig = {
  enableEventStore: true,
  enableSnapshotStore: true,
  autoCheckpointInterval: 50,
  maxSnapshotsPerTrace: 20,
  snapshotOnSessionStart: false,
};
