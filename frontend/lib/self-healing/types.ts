/**
 * 知维 OS Self-Healing Snapshot Engine — 类型定义
 * Zhiwei OS Self-Healing Snapshot Engine — Type Definitions
 *
 * v5 核心：crash / inconsistency / policy drift 后自动检测 → 回滚 → 重建 → 修复
 *
 * 4 个核心模块：
 * 1. CrashDetector           — 检测 crash / corruption / drift / event gap
 * 2. AutoRecoveryEngine      — 4 种恢复策略（EVENT_REPLAY / SNAPSHOT_ROLLBACK / HYBRID / FORCE_REBUILD）
 * 3. ConsistencyAutoHealer   — heal loop until consistent OR max_attempts
 * 4. SnapshotCompactor       — 合并/压缩/删除冗余 snapshot
 *
 * 系统规则（强制）：
 * Rule 1 — Snapshot is NOT truth（L1 EventStore 是唯一 truth）
 * Rule 2 — Snapshot is only acceleration（不能作为最终状态来源）
 * Rule 3 — Authority Layer must validate after recovery
 * Rule 4 — Enforcement Layer must re-run after recovery
 */

import type { SystemEvent } from "@/types/event-bus";
import type { SystemState } from "@/lib/replay/types";
import type { SystemSnapshot } from "@/lib/persistence/types";
import type { ConsistencyReport } from "@/lib/authority/types";

// ═══════════════════════════════════════════════════════════════
// 1️⃣ CrashDetector — 崩溃检测
// ═══════════════════════════════════════════════════════════════

/**
 * 崩溃类型
 */
export type CrashType =
  | "CRASH"           // 会话中断（浏览器刷新/关闭）
  | "CORRUPTION"      // 状态损坏（数据被篡改）
  | "DRIFT"           // 快照漂移（snapshot 与 event 不一致）
  | "EVENT_GAP";      // 事件缺口（parent_event_id 指向缺失事件）

/**
 * 崩溃严重级别
 */
export type CrashSeverity = "low" | "medium" | "high" | "critical";

/**
 * 证据条目
 */
export interface CrashEvidence {
  /** 证据类型 */
  kind: "missing_event" | "version_mismatch" | "cursor_exceeds" | "broken_causal" | "snapshot_drift" | "session_break";
  /** 证据描述 */
  description: string;
  /** 期望值 */
  expected?: unknown;
  /** 实际值 */
  actual?: unknown;
  /** 相关 event_id */
  event_id?: string;
  /** 相关 snapshot_id */
  snapshot_id?: string;
}

/**
 * 崩溃报告
 */
export interface CrashReport {
  /** 报告 ID */
  report_id: string;
  /** 崩溃类型 */
  type: CrashType;
  /** 严重级别 */
  severity: CrashSeverity;
  /** 涉及的 trace_id */
  trace_id: string;
  /** 证据列表 */
  evidence: CrashEvidence[];
  /** 检测时间 */
  detected_at: string;
  /** 是否需要恢复 */
  needs_recovery: boolean;
  /** 建议的恢复策略 */
  suggested_strategy: RecoveryStrategy;
}

// ═══════════════════════════════════════════════════════════════
// 2️⃣ AutoRecoveryEngine — 自动恢复
// ═══════════════════════════════════════════════════════════════

/**
 * 恢复策略
 */
export type RecoveryStrategy =
  | "EVENT_REPLAY"       // 从 EventStore 重建（最权威）
  | "SNAPSHOT_ROLLBACK"  // 回滚到最近 snapshot
  | "HYBRID_RECOVERY"    // snapshot + replay delta
  | "FORCE_REBUILD";     // Authority Layer 强制重建

/**
 * 恢复结果
 */
export interface RecoveryResult {
  /** 使用的策略 */
  strategy_used: RecoveryStrategy;
  /** 恢复后的最终状态 */
  final_state: SystemState;
  /** 恢复来源 */
  restored_from: "event" | "snapshot" | "hybrid";
  /** 重放的事件数 */
  replayed_events_count: number;
  /** 使用的 snapshot（如有） */
  snapshot_used: SystemSnapshot | null;
  /** 恢复后的一致性报告 */
  consistency_after_recovery: ConsistencyReport | null;
  /** 是否成功 */
  success: boolean;
  /** 恢复耗时（ms） */
  duration_ms: number;
  /** 错误信息 */
  error: string | null;
  /** 恢复时间 */
  recovered_at: string;
}

// ═══════════════════════════════════════════════════════════════
// 3️⃣ ConsistencyAutoHealer — 一致性自动修复
// ═══════════════════════════════════════════════════════════════

/**
 * 修复状态
 */
export type HealStatus =
  | "consistent"        // 已一致
  | "healing"           // 修复中
  | "escalated"         // 升级（超过 max_attempts）
  | "failed";           // 失败

/**
 * 单次修复尝试结果
 */
export interface HealAttempt {
  /** 尝试序号（从 1 开始） */
  attempt: number;
  /** 修复前一致性报告 */
  before: ConsistencyReport;
  /** 使用的恢复策略 */
  strategy: RecoveryStrategy;
  /** 恢复结果 */
  recovery: RecoveryResult | null;
  /** 修复后一致性报告 */
  after: ConsistencyReport | null;
  /** 是否一致 */
  consistent: boolean;
  /** 耗时（ms） */
  duration_ms: number;
}

/**
 * 修复结果（完整 loop）
 */
export interface HealResult {
  /** trace_id */
  trace_id: string;
  /** 最终状态 */
  final_status: HealStatus;
  /** 修复尝试列表 */
  attempts: HealAttempt[];
  /** 总尝试次数 */
  total_attempts: number;
  /** 最终一致性报告 */
  final_consistency: ConsistencyReport | null;
  /** 最终状态 */
  final_state: SystemState | null;
  /** 总耗时（ms） */
  total_duration_ms: number;
}

// ═══════════════════════════════════════════════════════════════
// 4️⃣ SnapshotCompactor — 快照压缩
// ═══════════════════════════════════════════════════════════════

/**
 * 压缩策略
 */
export type CompactionStrategy =
  | "KEEP_LATEST"        // 保留最新 snapshot
  | "KEEP_AUTHORITATIVE"  // 保留 validated snapshot
  | "MERGE_RANGE"        // 合并连续 snapshot
  | "DROP_INVALID";      // 删除 drift snapshot

/**
 * 压缩操作记录
 */
export interface CompactionAction {
  /** 操作类型 */
  action: "keep" | "merge" | "drop" | "compress";
  /** 涉及的 snapshot_id */
  snapshot_id: string;
  /** 合并的目标 snapshot_id（如 merge） */
  merged_into?: string;
  /** 原因 */
  reason: string;
}

/**
 * 压缩结果
 */
export interface CompactionResult {
  /** trace_id */
  trace_id: string;
  /** 使用的策略 */
  strategy: CompactionStrategy;
  /** 压缩前 snapshot 数 */
  before_count: number;
  /** 压缩后 snapshot 数 */
  after_count: number;
  /** 压缩比（after/before） */
  reduction_ratio: number;
  /** 执行的操作 */
  actions: CompactionAction[];
  /** 保留的 snapshot 列表 */
  kept_snapshots: SystemSnapshot[];
  /** 是否成功 */
  success: boolean;
  /** 耗时（ms） */
  duration_ms: number;
}

// ═══════════════════════════════════════════════════════════════
// Self-Healing Kernel 状态
// ═══════════════════════════════════════════════════════════════

/**
 * 自愈内核状态
 */
export interface SelfHealingKernelState {
  /** 是否启用 */
  enabled: boolean;
  /** 是否运行一致性循环 */
  consistency_loop_running: boolean;
  /** 总检测次数 */
  total_checks: number;
  /** 检测到的问题数 */
  total_issues_detected: number;
  /** 总恢复次数 */
  total_recoveries: number;
  /** 成功恢复次数 */
  successful_recoveries: number;
  /** 总修复次数 */
  total_heals: number;
  /** 总压缩次数 */
  total_compactions: number;
  /** 平均恢复时间（ms） */
  avg_recovery_time_ms: number;
  /** 恢复成功率 */
  recovery_success_rate: number;
  /** 快照减少比 */
  snapshot_reduction_ratio: number;
  /** 漂移检测准确率 */
  drift_detection_accuracy: number;
  /** 最后检测时间 */
  last_check_at: string | null;
  /** 最后错误 */
  last_error: string | null;
}

/**
 * 完整恢复流程结果
 */
export interface FullRecoveryResult {
  /** trace_id */
  trace_id: string;
  /** 检测报告 */
  detection: CrashReport | null;
  /** 一致性报告（修复前） */
  pre_consistency: ConsistencyReport | null;
  /** 诊断结果 */
  diagnosis: {
    needs_recovery: boolean;
    suggested_strategy: RecoveryStrategy;
    severity: CrashSeverity;
  };
  /** 恢复结果 */
  recovery: RecoveryResult | null;
  /** 验证结果（修复后） */
  verification: ConsistencyReport | null;
  /** 压缩结果 */
  compaction: CompactionResult | null;
  /** 重新执行策略数 */
  re_enforced_policies: number;
  /** 总耗时（ms） */
  total_duration_ms: number;
  /** 是否成功 */
  success: boolean;
}

/**
 * 崩溃模拟配置
 */
export interface CrashSimulationConfig {
  /** 随机丢弃事件比例（0-1） */
  random_event_drop_ratio: number;
  /** 是否损坏 snapshot */
  corrupt_snapshot: boolean;
  /** 部分回放丢失比例（0-1） */
  partial_replay_loss_ratio: number;
  /** 模拟种子（可复现） */
  seed: number;
}

export const DEFAULT_CRASH_SIMULATION_CONFIG: CrashSimulationConfig = {
  random_event_drop_ratio: 0.1,
  corrupt_snapshot: false,
  partial_replay_loss_ratio: 0.05,
  seed: 42,
};
