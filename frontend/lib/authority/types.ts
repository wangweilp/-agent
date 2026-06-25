/**
 * 知维 OS System Authority Layer — 类型定义
 * Zhiwei OS System Authority Layer — Type Definitions
 *
 * v3 核心设计：
 * 1. State Authority Layer       — 定义 canonical state 与权威层级
 * 2. Consistency Validator       — 跨源一致性验证
 * 3. Unified Reconstruction Contract — rebuildSystem() 确定性重建契约
 * 4. Conflict Resolution Model   — 冲突解决策略
 *
 * 约束：
 * - 不修改 EventStore / SnapshotStore 实现
 * - 不修改 CausalKernel / ReplayCursor 逻辑
 * - 只定义"系统规则层"
 * - architecture-first
 */

import type { SystemEvent } from "@/types/event-bus";
import type { SystemState } from "@/lib/replay/types";
import type { SystemSnapshot } from "@/lib/persistence/types";
import type { CausalGraph } from "@/types/event-bus";

// ═══════════════════════════════════════════════════════════════
// 1️⃣ State Authority Layer — 权威状态模型
// ═══════════════════════════════════════════════════════════════

/**
 * 权威来源层级 — 从高到低
 *
 * 层级规则：
 * - L1 Event Stream（最高权威）：事件是不可变事实，是所有状态的源头
 * - L2 Snapshot（缓存权威）：从事件重建的检查点，加速 replay
 * - L3 In-Memory State（运行时缓存）：ReplayCursor.current_state
 * - L4 Derived Graph（投影）：CausalGraph 从事件构建的视图
 *
 * 冲突时：低层级必须服从高层级
 */
export type AuthorityLevel =
  | "L1_EVENT_STREAM"     // 最高权威 — 不可变事实
  | "L2_SNAPSHOT"          // 缓存权威 — 从事件重建
  | "L3_IN_MEMORY_STATE"   // 运行时缓存 — ReplayCursor
  | "L4_DERIVED_GRAPH";    // 投影视图 — CausalGraph

/**
 * 权威来源标记 — 每个状态对象必须声明其来源
 */
export interface AuthoritySource {
  level: AuthorityLevel;
  /** 来源标识（event_id / snapshot_id / cursor position / graph_id） */
  source_id: string;
  /** 生成时间 */
  generated_at: string;
  /** 是否经过验证 */
  verified: boolean;
}

/**
 * 权威状态 — 带来源标记的 SystemState
 */
export interface AuthoritativeState {
  state: SystemState;
  authority: AuthoritySource;
  /** 重建该状态所用的事件数 */
  event_count: number;
  /** 重建基点（如有 snapshot，记录 snapshot_id） */
  rebuild_base: string | null;
}

/**
 * 状态解析规则 — 当多个来源提供状态时，如何选择
 */
export type ResolutionRule =
  | "HIGHEST_AUTHORITY"     // 选择权威层级最高的
  | "LATEST_TIMESTAMP"      // 选择时间戳最新的
  | "EVENT_DERIVED"         // 强制从事件重建（最权威）
  | "SNAPSHOT_ACCELERATED"  // 优先 snapshot + 增量事件
  | "FAIL_SAFE"             // 选择最保守的（最小状态）

// ═══════════════════════════════════════════════════════════════
// 2️⃣ Consistency Validator — 一致性验证
// ═══════════════════════════════════════════════════════════════

/**
 * 不一致严重级别
 */
export type InconsistencySeverity =
  | "critical"   // 系统状态错误，必须修复
  | "high"       // 数据漂移，影响 replay 正确性
  | "medium"     // 轻微偏差，可容忍
  | "low"        // 信息性警告
  | "info";      // 仅记录

/**
 * 不一致类型
 */
export type InconsistencyType =
  | "STATE_EVENT_MISMATCH"      // state 与 event store 不一致
  | "SNAPSHOT_DRIFT"             // snapshot 与 event 重建结果不一致
  | "GRAPH_INCONSISTENCY"        // graph 与 event 不一致
  | "CAUSAL_CHAIN_BROKEN"       // 因果链断裂（parent 缺失）
  | "CURSOR_STATE_MISMATCH"     // cursor 位置与 state 不匹配
  | "EVENT_COUNT_MISMATCH"       // 事件计数不一致
  | "TIMESTAMP_ORDER_VIOLATION" // 时间戳顺序违反
  | "ORIGIN_MISMATCH";           // 事件来源标记不一致

/**
 * 不一致报告条目
 */
export interface InconsistencyReport {
  type: InconsistencyType;
  severity: InconsistencySeverity;
  /** 不一致描述 */
  description: string;
  /** 涉及的 trace_id */
  trace_id: string;
  /** 涉及的 event_id（如适用） */
  event_id?: string;
  /** 期望值 */
  expected: unknown;
  /** 实际值 */
  actual: unknown;
  /** 建议的修复策略 */
  suggested_fix: string;
}

/**
 * 一致性验证结果
 */
export interface ConsistencyReport {
  /** 验证时间 */
  validated_at: string;
  /** trace_id */
  trace_id: string;
  /** 是否通过（无 critical/high 级别不一致） */
  passed: boolean;
  /** 不一致条目列表 */
  inconsistencies: InconsistencyReport[];
  /** 统计 */
  stats: {
    total_checks: number;
    passed_checks: number;
    failed_checks: number;
    critical_count: number;
    high_count: number;
    medium_count: number;
    low_count: number;
    info_count: number;
  };
}

// ═══════════════════════════════════════════════════════════════
// 3️⃣ Unified Reconstruction Contract — 重建契约
// ═══════════════════════════════════════════════════════════════

/**
 * 重建策略
 */
export type ReconstructionStrategy =
  | "FULL_FROM_EVENTS"          // 从所有事件重建（最权威，最慢）
  | "SNAPSHOT_ACCELERATED"      // snapshot + 增量事件（快）
  | "VALIDATED_REBUILD"         // 重建后验证一致性
  | "CONFLICT_RESOLUTION";      // 冲突时强制解决后重建

/**
 * 重建选项
 */
export interface ReconstructionOptions {
  strategy: ReconstructionStrategy;
  /** 是否使用 snapshot 加速 */
  use_snapshot: boolean;
  /** 是否在重建后验证一致性 */
  validate_after: boolean;
  /** 是否强制从 L1 事件重建（忽略缓存） */
  force_full_rebuild: boolean;
  /** 最大允许事件数（防止 OOM） */
  max_events: number;
}

export const DEFAULT_RECONSTRUCTION_OPTIONS: ReconstructionOptions = {
  strategy: "SNAPSHOT_ACCELERATED",
  use_snapshot: true,
  validate_after: true,
  force_full_rebuild: false,
  max_events: 100000,
};

/**
 * 重建结果
 */
export interface ReconstructionResult {
  /** 重建的权威状态 */
  authoritative_state: AuthoritativeState;
  /** 重建使用的事件数 */
  events_applied: number;
  /** 重建使用的 snapshot（如有） */
  snapshot_base: SystemSnapshot | null;
  /** 重建耗时（ms） */
  duration_ms: number;
  /** 重建后的一致性报告（如 validate_after=true） */
  consistency_report: ConsistencyReport | null;
  /** 是否成功 */
  success: boolean;
  /** 失败原因 */
  error: string | null;
}

// ═══════════════════════════════════════════════════════════════
// 4️⃣ Conflict Resolution Model — 冲突解决
// ═══════════════════════════════════════════════════════════════

/**
 * 冲突类型
 */
export type ConflictType =
  | "EVENT_VS_SNAPSHOT"         // 事件重建结果与 snapshot 不一致
  | "STATE_VS_GRAPH"            // 内存状态与 graph 不一致
  | "REPLAY_VS_CACHED"          // replay 结果与缓存状态不一致
  | "SNAPSHOT_VS_SNAPSHOT"      // 多个 snapshot 之间不一致
  | "EVENT_VS_EVENT";           // 事件之间矛盾（如因果顺序冲突）

/**
 * 冲突解决策略
 */
export type ConflictResolutionStrategy =
  | "PREFER_EVENT_STREAM"       // 优先事件流（最权威）
  | "PREFER_LATEST_SNAPSHOT"    // 优先最新 snapshot
  | "PREFER_MOST_CONSERVATIVE"  // 优先最保守（最小状态）
  | "FORCE_REBUILD"             // 强制从事件重建
  | "MARK_INCONSISTENT"         // 标记为不一致，不自动解决
  | "ROLLBACK_TO_CHECKPOINT";   // 回滚到上一个 checkpoint

/**
 * 冲突记录
 */
export interface ConflictRecord {
  conflict_id: string;
  type: ConflictType;
  /** 冲突涉及的来源 */
  sources: AuthoritySource[];
  /** 冲突描述 */
  description: string;
  /** 选择的解决策略 */
  resolution_strategy: ConflictResolutionStrategy;
  /** 解决结果（null 表示未解决） */
  resolved: boolean;
  /** 解决时间 */
  resolved_at: string | null;
  /** 解决说明 */
  resolution_note: string | null;
}

/**
 * 回滚策略结果
 */
export interface RollbackResult {
  success: boolean;
  /** 回滚到的 snapshot_id */
  rolled_back_to: string | null;
  /** 回滚后的状态 */
  restored_state: SystemState | null;
  /** 丢弃的事件数 */
  discarded_events: number;
  /** 回滚原因 */
  reason: string;
}
