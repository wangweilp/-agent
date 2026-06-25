/**
 * 知维 OS Auto Recovery Engine — 自动恢复引擎
 * Zhiwei OS Auto Recovery Engine
 *
 * 4 种恢复策略：
 * 1. EVENT_REPLAY      — 从 EventStore 重建（最权威，Rule 1: L1 是唯一 truth）
 * 2. SNAPSHOT_ROLLBACK — 回滚到最近 snapshot（Rule 2: 仅加速，非最终来源）
 * 3. HYBRID_RECOVERY   — snapshot + replay delta（最优性能）
 * 4. FORCE_REBUILD     — Authority Layer 强制重建（Rule 3: 必须经验证）
 *
 * 系统规则强制：
 * - 所有恢复后必须经 Authority Layer 验证（Rule 3）
 * - 恢复后状态必须标记为 L1_EVENT_STREAM 权威
 */

import { causalKernel } from "@/lib/event-bus/causal-kernel";
import { persistencePipeline } from "@/lib/persistence/pipeline";
import { reconstructionEngine } from "@/lib/authority/reconstruction-engine";
import { consistencyValidator } from "@/lib/authority/consistency-validator";
import { applyEvent } from "@/lib/replay/state-reducer";
import { createInitialState, type SystemState } from "@/lib/replay/types";
import type { SystemEvent } from "@/types/event-bus";
import type { SystemSnapshot } from "@/lib/persistence/types";
import { deserializeState } from "@/lib/persistence/types";
import type {
  RecoveryStrategy,
  RecoveryResult,
  CrashReport,
} from "@/lib/self-healing/types";

// ═══════════════════════════════════════════════════════════════
// AutoRecoveryEngine — 自动恢复引擎
// ═══════════════════════════════════════════════════════════════

export class AutoRecoveryEngine {
  /**
   * 恢复 — 主入口
   *
   * @param trace_id      要恢复的 trace
   * @param strategy      恢复策略（不指定则自动选择）
   * @param crashReport   崩溃报告（用于辅助决策）
   */
  async recover(
    trace_id: string,
    strategy?: RecoveryStrategy,
    crashReport?: CrashReport,
  ): Promise<RecoveryResult> {
    const startTime = Date.now();
    const recoveredAt = new Date().toISOString();

    try {
      // 选择策略
      const chosenStrategy = strategy ?? this.chooseRecoveryStrategy(crashReport);

      // 获取事件
      const events = await this.getEvents(trace_id);
      if (events.length === 0) {
        return this.failure(trace_id, chosenStrategy, "No events found in EventStore", startTime, recoveredAt);
      }

      // 按策略执行恢复
      let state: SystemState;
      let restoredFrom: "event" | "snapshot" | "hybrid";
      let replayedCount: number;
      let snapshotUsed: SystemSnapshot | null = null;

      switch (chosenStrategy) {
        case "EVENT_REPLAY":
          state = this.rebuildFromEvents(events);
          restoredFrom = "event";
          replayedCount = events.length;
          break;

        case "SNAPSHOT_ROLLBACK":
          snapshotUsed = await persistencePipeline.getLatestSnapshot(trace_id);
          if (!snapshotUsed) {
            // 无 snapshot，降级为 EVENT_REPLAY
            state = this.rebuildFromEvents(events);
            restoredFrom = "event";
            replayedCount = events.length;
          } else {
            state = this.rollbackToSnapshot(snapshotUsed);
            restoredFrom = "snapshot";
            replayedCount = 0;
          }
          break;

        case "HYBRID_RECOVERY":
          snapshotUsed = await persistencePipeline.getLatestSnapshot(trace_id);
          if (!snapshotUsed) {
            // 无 snapshot，降级为 EVENT_REPLAY
            state = this.rebuildFromEvents(events);
            restoredFrom = "event";
            replayedCount = events.length;
          } else {
            const result = this.hybridRecovery(snapshotUsed, events);
            state = result.state;
            replayedCount = result.replayedCount;
            restoredFrom = "hybrid";
          }
          break;

        case "FORCE_REBUILD":
          // 使用 Authority Layer 的 reconstructionEngine 强制重建
          const rebuildResult = await reconstructionEngine.rebuildSystem(
            trace_id,
            events,
            await persistencePipeline.getLatestSnapshot(trace_id),
            { strategy: "FULL_FROM_EVENTS", force_full_rebuild: true, validate_after: true },
          );
          if (!rebuildResult.success) {
            return this.failure(trace_id, chosenStrategy, rebuildResult.error ?? "Force rebuild failed", startTime, recoveredAt);
          }
          state = rebuildResult.authoritative_state.state;
          restoredFrom = "event";
          replayedCount = rebuildResult.events_applied;
          break;

        default:
          return this.failure(trace_id, chosenStrategy, `Unknown strategy: ${chosenStrategy}`, startTime, recoveredAt);
      }

      // Rule 3: 恢复后必须经 Authority Layer 验证
      const consistency = consistencyValidator.validate(
        trace_id,
        state,
        events,
        snapshotUsed,
        null,
        replayedCount,
      );

      return {
        strategy_used: chosenStrategy,
        final_state: state,
        restored_from: restoredFrom,
        replayed_events_count: replayedCount,
        snapshot_used: snapshotUsed,
        consistency_after_recovery: consistency,
        success: true,
        duration_ms: Date.now() - startTime,
        error: null,
        recovered_at: recoveredAt,
      };
    } catch (err) {
      return this.failure(
        trace_id,
        strategy ?? "EVENT_REPLAY",
        err instanceof Error ? err.message : String(err),
        startTime,
        recoveredAt,
      );
    }
  }

  /**
   * 选择恢复策略 — 基于崩溃报告
   */
  chooseRecoveryStrategy(crashReport?: CrashReport): RecoveryStrategy {
    if (!crashReport) return "EVENT_REPLAY";

    switch (crashReport.type) {
      case "CRASH":
        // 会话中断：优先 HYBRID（snapshot + delta）
        return "HYBRID_RECOVERY";
      case "CORRUPTION":
        // 状态损坏：必须 FORCE_REBUILD
        return "FORCE_REBUILD";
      case "DRIFT":
        // 快照漂移：回滚到 snapshot
        return "SNAPSHOT_ROLLBACK";
      case "EVENT_GAP":
        // 事件缺口：从 EventStore 重建
        return "EVENT_REPLAY";
      default:
        return "EVENT_REPLAY";
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 策略实现
  // ─────────────────────────────────────────────────────────────

  /**
   * 策略 1：EVENT_REPLAY — 从 EventStore 重建（Rule 1: L1 是唯一 truth）
   */
  private rebuildFromEvents(events: SystemEvent[]): SystemState {
    let state = createInitialState();
    for (const event of events) {
      state = applyEvent(state, event);
    }
    return state;
  }

  /**
   * 策略 2：SNAPSHOT_ROLLBACK — 回滚到最近 snapshot（Rule 2: 仅加速）
   */
  private rollbackToSnapshot(snapshot: SystemSnapshot): SystemState {
    return deserializeState(snapshot.state);
  }

  /**
   * 策略 3：HYBRID_RECOVERY — snapshot + replay delta
   */
  private hybridRecovery(
    snapshot: SystemSnapshot,
    events: SystemEvent[],
  ): { state: SystemState; replayedCount: number } {
    let state = deserializeState(snapshot.state);
    let replayedCount = 0;

    // 应用 snapshot.cursor 之后的增量事件
    for (let i = snapshot.cursor; i < events.length; i++) {
      const event = events[i];
      if (!event) break;
      state = applyEvent(state, event);
      replayedCount++;
    }

    return { state, replayedCount };
  }

  // ─────────────────────────────────────────────────────────────
  // 辅助方法
  // ─────────────────────────────────────────────────────────────

  private async getEvents(trace_id: string): Promise<SystemEvent[]> {
    // 优先从内存读取
    let events = causalKernel.replay(trace_id);
    if (events.length === 0) {
      // 从 EventStore 读取（跨 session 恢复）
      events = await persistencePipeline.loadEventsByTraceId(trace_id);

      // 恢复到 CausalKernel 内存
      for (const event of events) {
        if (!causalKernel.getEvent(event.event_id)) {
          causalKernel.publish(event);
        }
      }
    }
    return events;
  }

  private failure(
    trace_id: string,
    strategy: RecoveryStrategy,
    error: string,
    startTime: number,
    recoveredAt: string,
  ): RecoveryResult {
    return {
      strategy_used: strategy,
      final_state: createInitialState(),
      restored_from: "event",
      replayed_events_count: 0,
      snapshot_used: null,
      consistency_after_recovery: null,
      success: false,
      duration_ms: Date.now() - startTime,
      error,
      recovered_at: recoveredAt,
    };
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const autoRecoveryEngine = new AutoRecoveryEngine();
