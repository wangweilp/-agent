/**
 * 知维 OS System Authority Layer — 统一门面
 * Zhiwei OS System Authority Layer — Unified Facade
 *
 * v3 核心入口：
 * 整合 State Authority + Consistency Validator + Reconstruction + Conflict Resolution
 *
 * 架构层级：
 * ┌─────────────────────────────────────────┐
 * │  AuthorityFacade（本文件）              │  ← 统一入口
 * ├─────────────────────────────────────────┤
 * │  ConsistencyValidator                  │  ← 一致性验证
 * │  ReconstructionEngine                  │  ← 重建契约
 * │  ConflictResolver                       │  ← 冲突解决
 * ├─────────────────────────────────────────┤
 * │  EventStore / SnapshotStore / Kernel   │  ← 数据层（不修改）
 * └─────────────────────────────────────────┘
 */

import { consistencyValidator } from "@/lib/authority/consistency-validator";
import { reconstructionEngine } from "@/lib/authority/reconstruction-engine";
import { conflictResolver } from "@/lib/authority/conflict-resolver";
import type { SystemEvent, CausalGraph } from "@/types/event-bus";
import type { SystemState } from "@/lib/replay/types";
import type { SystemSnapshot } from "@/lib/persistence/types";
import type {
  ConsistencyReport,
  ReconstructionResult,
  ReconstructionOptions,
  ConflictRecord,
  ConflictResolutionStrategy,
  AuthoritySource,
  RollbackResult,
} from "@/lib/authority/types";

// ═══════════════════════════════════════════════════════════════
// AuthorityFacade — 统一权威层门面
// ═══════════════════════════════════════════════════════════════

export class AuthorityFacade {
  /**
   * 验证系统一致性
   * validateSystemConsistency(state, eventStore, snapshotStore, graph)
   */
  validateConsistency(
    trace_id: string,
    state: SystemState,
    events: SystemEvent[],
    snapshot: SystemSnapshot | null,
    graph: CausalGraph | null,
    cursor?: number,
  ): ConsistencyReport {
    return consistencyValidator.validate(
      trace_id,
      state,
      events,
      snapshot,
      graph,
      cursor,
    );
  }

  /**
   * 统一重建 — rebuildSystem(trace_id)
   * 保证：deterministic / reproducible / version-safe / checkpoint-aware
   */
  async rebuildSystem(
    trace_id: string,
    events: SystemEvent[],
    snapshot: SystemSnapshot | null,
    options?: Partial<ReconstructionOptions>,
  ): Promise<ReconstructionResult> {
    return reconstructionEngine.rebuildSystem(trace_id, events, snapshot, options);
  }

  /**
   * 解决冲突
   */
  resolveConflict(
    type: import("@/lib/authority/types").ConflictType,
    sources: AuthoritySource[],
    description: string,
    events: SystemEvent[],
    snapshots: SystemSnapshot[],
    strategy?: ConflictResolutionStrategy,
  ): ConflictRecord {
    return conflictResolver.resolve(
      type,
      sources,
      description,
      events,
      snapshots,
      strategy,
    );
  }

  /**
   * 选择权威状态
   */
  selectAuthoritativeState(
    events: SystemEvent[],
    snapshot: SystemSnapshot | null,
    cachedState: SystemState | null,
    strategy?: ConflictResolutionStrategy,
  ): { state: SystemState; source: AuthoritySource; conflict: ConflictRecord | null } {
    return conflictResolver.selectAuthoritativeState(
      events,
      snapshot,
      cachedState,
      strategy,
    );
  }

  /**
   * 回滚到 checkpoint
   */
  rollbackToCheckpoint(snapshot: SystemSnapshot, events: SystemEvent[]): RollbackResult {
    return conflictResolver.rollbackToCheckpoint(snapshot, events);
  }

  /**
   * 获取冲突历史
   */
  getConflictHistory(): ConflictRecord[] {
    return conflictResolver.getConflictHistory();
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const authorityFacade = new AuthorityFacade();

// 重新导出子模块，方便统一引用
export { consistencyValidator } from "@/lib/authority/consistency-validator";
export { reconstructionEngine } from "@/lib/authority/reconstruction-engine";
export { conflictResolver } from "@/lib/authority/conflict-resolver";
