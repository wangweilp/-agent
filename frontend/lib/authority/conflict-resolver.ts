/**
 * 知维 OS Conflict Resolution Model — 冲突解决模型
 * Zhiwei OS Conflict Resolution Model
 *
 * 职责：
 * 当出现冲突时（event vs snapshot / state vs graph / replay vs cached），
 * 根据权威层级和解决策略选择正确版本。
 *
 * 解决优先级规则（基于权威层级）：
 * 1. PREFER_EVENT_STREAM     — L1 事件流最权威，冲突时优先
 * 2. PREFER_LATEST_SNAPSHOT  — L2 snapshot 次之
 * 3. PREFER_MOST_CONSERVATIVE — 选择最小状态（保守）
 * 4. FORCE_REBUILD           — 强制从事件重建
 * 5. MARK_INCONSISTENT       — 标记不一致，不自动解决
 * 6. ROLLBACK_TO_CHECKPOINT  — 回滚到上一个 checkpoint
 *
 * 默认策略：PREFER_EVENT_STREAM（L1 是 single source of truth）
 */

import { applyEvent } from "@/lib/replay/state-reducer";
import { createInitialState, type SystemState } from "@/lib/replay/types";
import type { SystemEvent } from "@/types/event-bus";
import type { SystemSnapshot } from "@/lib/persistence/types";
import { deserializeState } from "@/lib/persistence/types";
import type {
  ConflictRecord,
  ConflictType,
  ConflictResolutionStrategy,
  AuthoritySource,
  RollbackResult,
} from "@/lib/authority/types";

// ═══════════════════════════════════════════════════════════════
// ConflictResolver — 冲突解决器
// ═══════════════════════════════════════════════════════════════

let conflictCounter = 0;

export class ConflictResolver {
  /** 冲突历史记录 */
  private conflictHistory: Map<string, ConflictRecord> = new Map();

  /**
   * 解决冲突 — 主入口
   *
   * @param type          冲突类型
   * @param sources       冲突涉及的来源
   * @param description   冲突描述
   * @param events        事件流（L1，用于 FORCE_REBUILD）
   * @param snapshots     snapshot 列表（L2，用于 ROLLBACK）
   * @param strategy      解决策略（默认 PREFER_EVENT_STREAM）
   * @returns 冲突记录（含解决结果）
   */
  resolve(
    type: ConflictType,
    sources: AuthoritySource[],
    description: string,
    events: SystemEvent[],
    snapshots: SystemSnapshot[],
    strategy: ConflictResolutionStrategy = "PREFER_EVENT_STREAM",
  ): ConflictRecord {
    conflictCounter++;
    const conflictId = `conflict_${Date.now()}_${conflictCounter}`;

    const record: ConflictRecord = {
      conflict_id: conflictId,
      type,
      sources,
      description,
      resolution_strategy: strategy,
      resolved: false,
      resolved_at: null,
      resolution_note: null,
    };

    try {
      switch (strategy) {
        case "PREFER_EVENT_STREAM":
          record.resolved = true;
          record.resolution_note = "Resolved by preferring L1 event stream (highest authority)";
          break;

        case "PREFER_LATEST_SNAPSHOT":
          if (snapshots.length > 0) {
            record.resolved = true;
            record.resolution_note = `Resolved by preferring latest snapshot: ${snapshots[snapshots.length - 1].snapshot_id}`;
          } else {
            record.resolution_note = "No snapshot available, fallback to event stream";
            record.resolved = true;
          }
          break;

        case "PREFER_MOST_CONSERVATIVE":
          record.resolved = true;
          record.resolution_note = "Resolved by preferring most conservative (minimal) state";
          break;

        case "FORCE_REBUILD":
          // 强制从事件重建
          record.resolved = true;
          record.resolution_note = `Resolved by force rebuild from ${events.length} events`;
          break;

        case "MARK_INCONSISTENT":
          record.resolved = false;
          record.resolution_note = "Marked as inconsistent, manual intervention required";
          break;

        case "ROLLBACK_TO_CHECKPOINT":
          if (snapshots.length > 0) {
            record.resolved = true;
            record.resolution_note = `Resolved by rollback to checkpoint: ${snapshots[snapshots.length - 1].snapshot_id}`;
          } else {
            record.resolved = false;
            record.resolution_note = "No checkpoint available for rollback";
          }
          break;
      }
    } catch (err) {
      record.resolved = false;
      record.resolution_note = `Resolution failed: ${err instanceof Error ? err.message : String(err)}`;
    }

    if (record.resolved) {
      record.resolved_at = new Date().toISOString();
    }

    this.conflictHistory.set(conflictId, record);
    return record;
  }

  /**
   * 选择权威状态 — 根据解决策略从多个来源中选择
   *
   * @param events      事件流（L1）
   * @param snapshot    snapshot（L2，可选）
   * @param cachedState 内存缓存状态（L3，可选）
   * @param strategy    解决策略
   * @returns 选中的状态 + 来源标记
   */
  selectAuthoritativeState(
    events: SystemEvent[],
    snapshot: SystemSnapshot | null,
    cachedState: SystemState | null,
    strategy: ConflictResolutionStrategy = "PREFER_EVENT_STREAM",
  ): { state: SystemState; source: AuthoritySource; conflict: ConflictRecord | null } {
    let conflict: ConflictRecord | null = null;

    // 检测冲突：event 重建 vs cachedState
    const eventRebuiltState = this.rebuildFromEvents(events);

    if (cachedState && this.statesDiffer(cachedState, eventRebuiltState)) {
      // 检测到冲突
      conflict = this.resolve(
        "REPLAY_VS_CACHED",
        [
          { level: "L1_EVENT_STREAM", source_id: "events", generated_at: new Date().toISOString(), verified: true },
          { level: "L3_IN_MEMORY_STATE", source_id: "cached", generated_at: new Date().toISOString(), verified: false },
        ],
        "Cached state differs from event-rebuilt state",
        events,
        snapshot ? [snapshot] : [],
        strategy,
      );
    }

    // 按策略选择
    switch (strategy) {
      case "PREFER_EVENT_STREAM":
      case "FORCE_REBUILD":
        return {
          state: eventRebuiltState,
          source: {
            level: "L1_EVENT_STREAM",
            source_id: "events",
            generated_at: new Date().toISOString(),
            verified: true,
          },
          conflict,
        };

      case "PREFER_LATEST_SNAPSHOT":
        if (snapshot) {
          return {
            state: this.rebuildFromSnapshot(snapshot, events),
            source: {
              level: "L2_SNAPSHOT",
              source_id: snapshot.snapshot_id,
              generated_at: new Date().toISOString(),
              verified: true,
            },
            conflict,
          };
        }
        // fallback to event stream
        return {
          state: eventRebuiltState,
          source: {
            level: "L1_EVENT_STREAM",
            source_id: "events",
            generated_at: new Date().toISOString(),
            verified: true,
          },
          conflict,
        };

      case "PREFER_MOST_CONSERVATIVE":
        // 选择最小状态（version 最小）
        const candidates = [eventRebuiltState];
        if (snapshot) candidates.push(this.rebuildFromSnapshot(snapshot, events));
        if (cachedState) candidates.push(cachedState);
        const mostConservative = candidates.reduce((min, s) =>
          s.version < min.version ? s : min,
        );
        return {
          state: mostConservative,
          source: {
            level: "L3_IN_MEMORY_STATE",
            source_id: "conservative",
            generated_at: new Date().toISOString(),
            verified: false,
          },
          conflict,
        };

      case "ROLLBACK_TO_CHECKPOINT":
        if (snapshot) {
          return {
            state: this.rebuildFromSnapshot(snapshot, events),
            source: {
              level: "L2_SNAPSHOT",
              source_id: snapshot.snapshot_id,
              generated_at: new Date().toISOString(),
              verified: true,
            },
            conflict,
          };
        }
        return {
          state: eventRebuiltState,
          source: {
            level: "L1_EVENT_STREAM",
            source_id: "events",
            generated_at: new Date().toISOString(),
            verified: true,
          },
          conflict,
        };

      case "MARK_INCONSISTENT":
        // 不自动解决，返回 event-rebuilt（最权威）
        return {
          state: eventRebuiltState,
          source: {
            level: "L1_EVENT_STREAM",
            source_id: "events",
            generated_at: new Date().toISOString(),
            verified: false,
          },
          conflict,
        };

      default:
        return {
          state: eventRebuiltState,
          source: {
            level: "L1_EVENT_STREAM",
            source_id: "events",
            generated_at: new Date().toISOString(),
            verified: true,
          },
          conflict,
        };
    }
  }

  /**
   * 回滚到 checkpoint
   *
   * @param snapshot    回滚目标 snapshot
   * @param events      事件流（用于计算丢弃事件数）
   * @returns 回滚结果
   */
  rollbackToCheckpoint(
    snapshot: SystemSnapshot,
    events: SystemEvent[],
  ): RollbackResult {
    try {
      const restoredState = deserializeState(snapshot.state);
      const discardedEvents = Math.max(0, events.length - snapshot.cursor);

      return {
        success: true,
        rolled_back_to: snapshot.snapshot_id,
        restored_state: restoredState,
        discarded_events: discardedEvents,
        reason: `Rolled back to snapshot ${snapshot.snapshot_id} (cursor=${snapshot.cursor})`,
      };
    } catch (err) {
      return {
        success: false,
        rolled_back_to: snapshot.snapshot_id,
        restored_state: null,
        discarded_events: 0,
        reason: `Rollback failed: ${err instanceof Error ? err.message : String(err)}`,
      };
    }
  }

  /**
   * 获取冲突历史
   */
  getConflictHistory(): ConflictRecord[] {
    return Array.from(this.conflictHistory.values());
  }

  /**
   * 获取指定 trace 的冲突历史
   */
  getConflictsByTrace(trace_id: string): ConflictRecord[] {
    return this.getConflictHistory().filter((c) =>
      c.sources.some((s) => s.source_id.includes(trace_id)),
    );
  }

  // ─────────────────────────────────────────────────────────────
  // 内部方法
  // ─────────────────────────────────────────────────────────────

  /**
   * 从事件重建状态
   */
  private rebuildFromEvents(events: SystemEvent[]): SystemState {
    let state = createInitialState();
    for (const event of events) {
      state = applyEvent(state, event);
    }
    return state;
  }

  /**
   * 从 snapshot + 增量事件重建
   */
  private rebuildFromSnapshot(snapshot: SystemSnapshot, events: SystemEvent[]): SystemState {
    let state = deserializeState(snapshot.state);
    for (let i = snapshot.cursor; i < events.length; i++) {
      const event = events[i];
      if (!event) break;
      state = applyEvent(state, event);
    }
    return state;
  }

  /**
   * 检测两个状态是否不同
   */
  private statesDiffer(a: SystemState, b: SystemState): boolean {
    if (a.version !== b.version) return true;
    if (a.last_applied_event_id !== b.last_applied_event_id) return true;
    if (a.runtime.kill_switches.length !== b.runtime.kill_switches.length) return true;
    if (a.memory.memories.size !== b.memory.memories.size) return true;
    if (a.governance.incidents.size !== b.governance.incidents.size) return true;
    return false;
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const conflictResolver = new ConflictResolver();
