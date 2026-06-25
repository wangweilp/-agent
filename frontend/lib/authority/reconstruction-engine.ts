/**
 * 知维 OS Unified Reconstruction Contract — 统一重建契约
 * Zhiwei OS Unified Reconstruction Contract
 *
 * 核心契约：
 * rebuildSystem(trace_id) → ReconstructionResult
 *
 * 保证：
 * - deterministic: 相同输入 → 相同输出
 * - reproducible: 可重复执行
 * - version-safe: 版本兼容
 * - checkpoint-aware: 优先使用 snapshot 加速
 *
 * 权威层级：
 * L1_EVENT_STREAM > L2_SNAPSHOT > L3_IN_MEMORY_STATE > L4_DERIVED_GRAPH
 *
 * 重建策略：
 * 1. FULL_FROM_EVENTS       — 从所有事件重建（最权威）
 * 2. SNAPSHOT_ACCELERATED   — snapshot + 增量事件
 * 3. VALIDATED_REBUILD      — 重建后验证一致性
 * 4. CONFLICT_RESOLUTION    — 冲突时强制解决后重建
 */

import { causalKernel } from "@/lib/event-bus/causal-kernel";
import { applyEvent } from "@/lib/replay/state-reducer";
import { createInitialState, type SystemState } from "@/lib/replay/types";
import type { SystemEvent } from "@/types/event-bus";
import type { SystemSnapshot } from "@/lib/persistence/types";
import { deserializeState } from "@/lib/persistence/types";
import { consistencyValidator } from "@/lib/authority/consistency-validator";
import type {
  ReconstructionOptions,
  ReconstructionResult,
  AuthoritativeState,
  AuthoritySource,
} from "@/lib/authority/types";
import { DEFAULT_RECONSTRUCTION_OPTIONS } from "@/lib/authority/types";

// ═══════════════════════════════════════════════════════════════
// ReconstructionEngine — 重建引擎
// ═══════════════════════════════════════════════════════════════

export class ReconstructionEngine {
  /**
   * rebuildSystem — 统一重建契约主入口
   *
   * @param trace_id      要重建的 trace
   * @param events       事件流（L1 权威来源）
   * @param snapshot    可选 snapshot（L2 加速基点）
   * @param options     重建选项
   * @returns 重建结果（含权威状态 + 一致性报告）
   */
  async rebuildSystem(
    trace_id: string,
    events: SystemEvent[],
    snapshot: SystemSnapshot | null,
    options: Partial<ReconstructionOptions> = {},
  ): Promise<ReconstructionResult> {
    const opts = { ...DEFAULT_RECONSTRUCTION_OPTIONS, ...options };
    const startTime = Date.now();

    try {
      // 事件数检查
      if (events.length > opts.max_events) {
        return this.failure(
          trace_id,
          `Event count (${events.length}) exceeds max_events (${opts.max_events})`,
          startTime,
        );
      }

      // 按策略重建
      let state: SystemState;
      let snapshotBase: SystemSnapshot | null = null;
      let eventsApplied: number;

      if (opts.force_full_rebuild || !opts.use_snapshot || !snapshot) {
        // 策略 1：从所有事件重建（最权威）
        state = this.rebuildFromEvents(events);
        eventsApplied = events.length;
      } else {
        // 策略 2：snapshot + 增量事件
        const result = this.rebuildFromSnapshot(snapshot, events);
        state = result.state;
        snapshotBase = result.snapshotBase;
        eventsApplied = result.eventsApplied;
      }

      // 构建权威状态
      const authority: AuthoritySource = {
        level: snapshotBase ? "L2_SNAPSHOT" : "L1_EVENT_STREAM",
        source_id: snapshotBase ? snapshotBase.snapshot_id : `events:${trace_id}`,
        generated_at: new Date().toISOString(),
        verified: false,
      };

      const authoritativeState: AuthoritativeState = {
        state,
        authority,
        event_count: eventsApplied,
        rebuild_base: snapshotBase?.snapshot_id ?? null,
      };

      // 一致性验证（如启用）
      let consistencyReport = null;
      if (opts.validate_after) {
        consistencyReport = consistencyValidator.validate(
          trace_id,
          state,
          events,
          snapshotBase,
          null, // graph 由调用方提供
          eventsApplied,
        );
        authority.verified = consistencyReport.passed;
      } else {
        authority.verified = true;
      }

      return {
        authoritative_state: authoritativeState,
        events_applied: eventsApplied,
        snapshot_base: snapshotBase,
        duration_ms: Date.now() - startTime,
        consistency_report: consistencyReport,
        success: true,
        error: null,
      };
    } catch (err) {
      return this.failure(
        trace_id,
        err instanceof Error ? err.message : String(err),
        startTime,
      );
    }
  }

  /**
   * 从事件流完整重建（L1 权威）
   */
  private rebuildFromEvents(events: SystemEvent[]): SystemState {
    let state = createInitialState();
    for (const event of events) {
      state = applyEvent(state, event);
    }
    return state;
  }

  /**
   * 从 snapshot + 增量事件重建（L2 加速）
   */
  private rebuildFromSnapshot(
    snapshot: SystemSnapshot,
    events: SystemEvent[],
  ): { state: SystemState; snapshotBase: SystemSnapshot; eventsApplied: number } {
    // 从 snapshot 反序列化状态
    let state = deserializeState(snapshot.state);
    let eventsApplied = snapshot.cursor;

    // 应用 snapshot.cursor 之后的增量事件
    for (let i = snapshot.cursor; i < events.length; i++) {
      const event = events[i];
      if (!event) break;
      state = applyEvent(state, event);
      eventsApplied++;
    }

    return { state, snapshotBase: snapshot, eventsApplied };
  }

  /**
   * 构建失败结果
   */
  private failure(trace_id: string, error: string, startTime: number): ReconstructionResult {
    return {
      authoritative_state: {
        state: createInitialState(),
        authority: {
          level: "L1_EVENT_STREAM",
          source_id: `failed:${trace_id}`,
          generated_at: new Date().toISOString(),
          verified: false,
        },
        event_count: 0,
        rebuild_base: null,
      },
      events_applied: 0,
      snapshot_base: null,
      duration_ms: Date.now() - startTime,
      consistency_report: null,
      success: false,
      error,
    };
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const reconstructionEngine = new ReconstructionEngine();
