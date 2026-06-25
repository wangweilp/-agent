/**
 * 知维 OS Snapshot Compaction Engine — 快照压缩引擎
 * Zhiwei OS Snapshot Compaction Engine
 *
 * 解决问题：snapshot 无限增长 + replay 越来越慢
 *
 * 4 种压缩策略：
 * 1. KEEP_LATEST        — 保留最新 snapshot（删除旧的）
 * 2. KEEP_AUTHORITATIVE — 保留 validated snapshot（删除未验证的）
 * 3. MERGE_RANGE        — 合并连续 snapshot（保留合并点）
 * 4. DROP_INVALID       — 删除 drift snapshot
 *
 * 系统规则：
 * - Rule 1: Snapshot is NOT truth（压缩不影响 L1）
 * - Rule 2: Snapshot is only acceleration（压缩只影响性能）
 */

import { persistencePipeline } from "@/lib/persistence/pipeline";
import { crashDetector } from "@/lib/self-healing/crash-detector";
import { causalKernel } from "@/lib/event-bus/causal-kernel";
import { applyEvent } from "@/lib/replay/state-reducer";
import { createInitialState, type SystemState } from "@/lib/replay/types";
import { serializeState } from "@/lib/persistence/types";
import { generateSnapshotId } from "@/lib/persistence/snapshot-store";
import type { SystemSnapshot } from "@/lib/persistence/types";
import type { SystemEvent } from "@/types/event-bus";
import type {
  CompactionStrategy,
  CompactionResult,
  CompactionAction,
} from "@/lib/self-healing/types";

// ═══════════════════════════════════════════════════════════════
// SnapshotCompactor — 快照压缩引擎
// ═══════════════════════════════════════════════════════════════

export class SnapshotCompactor {
  /**
   * 压缩 — 主入口
   *
   * @param trace_id      要压缩的 trace
   * @param strategy      压缩策略
   */
  async compact(
    trace_id: string,
    strategy: CompactionStrategy = "MERGE_RANGE",
  ): Promise<CompactionResult> {
    const startTime = Date.now();

    try {
      const snapshots = await persistencePipeline.listSnapshots(trace_id);

      if (snapshots.length === 0) {
        return this.emptyResult(trace_id, strategy, startTime);
      }

      let actions: CompactionAction[] = [];
      let keptSnapshots: SystemSnapshot[] = [];

      switch (strategy) {
        case "KEEP_LATEST":
          ({ actions, keptSnapshots } = await this.keepLatest(trace_id, snapshots));
          break;

        case "KEEP_AUTHORITATIVE":
          ({ actions, keptSnapshots } = await this.keepAuthoritative(trace_id, snapshots));
          break;

        case "MERGE_RANGE":
          ({ actions, keptSnapshots } = await this.mergeRange(trace_id, snapshots));
          break;

        case "DROP_INVALID":
          ({ actions, keptSnapshots } = await this.dropInvalid(trace_id, snapshots));
          break;
      }

      const beforeCount = snapshots.length;
      const afterCount = keptSnapshots.length;
      const reductionRatio = beforeCount > 0 ? afterCount / beforeCount : 0;

      return {
        trace_id,
        strategy,
        before_count: beforeCount,
        after_count: afterCount,
        reduction_ratio: reductionRatio,
        actions,
        kept_snapshots: keptSnapshots,
        success: true,
        duration_ms: Date.now() - startTime,
      };
    } catch (err) {
      return {
        trace_id,
        strategy,
        before_count: 0,
        after_count: 0,
        reduction_ratio: 0,
        actions: [],
        kept_snapshots: [],
        success: false,
        duration_ms: Date.now() - startTime,
      };
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 策略实现
  // ─────────────────────────────────────────────────────────────

  /**
   * 策略 1：KEEP_LATEST — 保留最新 snapshot，删除其余
   */
  private async keepLatest(
    trace_id: string,
    snapshots: SystemSnapshot[],
  ): Promise<{ actions: CompactionAction[]; keptSnapshots: SystemSnapshot[] }> {
    const actions: CompactionAction[] = [];
    const sorted = [...snapshots].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    const latest = sorted[sorted.length - 1];

    // 保留最新，删除其余
    for (const snap of sorted) {
      if (snap.snapshot_id !== latest.snapshot_id) {
        await persistencePipeline.deleteSnapshot(snap.snapshot_id);
        actions.push({
          action: "drop",
          snapshot_id: snap.snapshot_id,
          reason: "Dropped by KEEP_LATEST (not the latest)",
        });
      }
    }

    actions.push({
      action: "keep",
      snapshot_id: latest.snapshot_id,
      reason: "Kept as latest snapshot",
    });

    return { actions, keptSnapshots: [latest] };
  }

  /**
   * 策略 2：KEEP_AUTHORITATIVE — 保留 validated snapshot，删除未验证的
   *
   * 判定 validated：snapshot.cursor 与当前 event count 一致
   */
  private async keepAuthoritative(
    trace_id: string,
    snapshots: SystemSnapshot[],
  ): Promise<{ actions: CompactionAction[]; keptSnapshots: SystemSnapshot[] }> {
    const actions: CompactionAction[] = [];
    const events = await this.getEvents(trace_id);
    const eventCount = events.length;
    const kept: SystemSnapshot[] = [];

    for (const snap of snapshots) {
      // validated: cursor <= eventCount 且 event_count === cursor
      const isValid = snap.cursor <= eventCount && snap.event_count === snap.cursor;

      if (isValid) {
        kept.push(snap);
        actions.push({
          action: "keep",
          snapshot_id: snap.snapshot_id,
          reason: "Validated snapshot (cursor matches event count)",
        });
      } else {
        await persistencePipeline.deleteSnapshot(snap.snapshot_id);
        actions.push({
          action: "drop",
          snapshot_id: snap.snapshot_id,
          reason: `Invalid snapshot (cursor=${snap.cursor}, event_count=${snap.event_count}, actual=${eventCount})`,
        });
      }
    }

    return { actions, keptSnapshots: kept };
  }

  /**
   * 策略 3：MERGE_RANGE — 合并连续 snapshot，保留合并点
   *
   * 将多个 snapshot 合并为一个（取最新状态），删除中间的
   */
  private async mergeRange(
    trace_id: string,
    snapshots: SystemSnapshot[],
  ): Promise<{ actions: CompactionAction[]; keptSnapshots: SystemSnapshot[] }> {
    const actions: CompactionAction[] = [];

    if (snapshots.length <= 1) {
      // 无需合并
      for (const snap of snapshots) {
        actions.push({
          action: "keep",
          snapshot_id: snap.snapshot_id,
          reason: "Single snapshot, no merge needed",
        });
      }
      return { actions, keptSnapshots: snapshots };
    }

    const sorted = [...snapshots].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    const latest = sorted[sorted.length - 1];

    // 创建合并后的 snapshot（基于最新事件重建）
    const events = await this.getEvents(trace_id);
    const mergedState = this.rebuildFromEvents(events);
    const mergedSnapshot: SystemSnapshot = {
      snapshot_id: generateSnapshotId(),
      trace_id,
      cursor: events.length,
      state: serializeState(mergedState),
      timestamp: new Date().toISOString(),
      reason: "restore_base",
      event_count: events.length,
    };

    // 保存合并后的 snapshot
    const snapshotStore = persistencePipeline.getSnapshotStore();
    if (snapshotStore) {
      await snapshotStore.put(mergedSnapshot);
    }

    // 删除所有旧 snapshot
    for (const snap of sorted) {
      await persistencePipeline.deleteSnapshot(snap.snapshot_id);
      actions.push({
        action: "merge",
        snapshot_id: snap.snapshot_id,
        merged_into: mergedSnapshot.snapshot_id,
        reason: "Merged into new compacted snapshot",
      });
    }

    actions.push({
      action: "keep",
      snapshot_id: mergedSnapshot.snapshot_id,
      reason: "New merged snapshot",
    });

    return { actions, keptSnapshots: [mergedSnapshot] };
  }

  /**
   * 策略 4：DROP_INVALID — 删除 drift snapshot
   *
   * 使用 CrashDetector 检测漂移，删除漂移的 snapshot
   */
  private async dropInvalid(
    trace_id: string,
    snapshots: SystemSnapshot[],
  ): Promise<{ actions: CompactionAction[]; keptSnapshots: SystemSnapshot[] }> {
    const actions: CompactionAction[] = [];
    const kept: SystemSnapshot[] = [];

    for (const snap of snapshots) {
      // 检测漂移
      const driftReport = await this.checkSnapshotDrift(trace_id, snap);

      if (driftReport) {
        await persistencePipeline.deleteSnapshot(snap.snapshot_id);
        actions.push({
          action: "drop",
          snapshot_id: snap.snapshot_id,
          reason: `Dropped due to drift: ${driftReport}`,
        });
      } else {
        kept.push(snap);
        actions.push({
          action: "keep",
          snapshot_id: snap.snapshot_id,
          reason: "Valid snapshot (no drift detected)",
        });
      }
    }

    return { actions, keptSnapshots: kept };
  }

  // ─────────────────────────────────────────────────────────────
  // 辅助方法
  // ─────────────────────────────────────────────────────────────

  private async getEvents(trace_id: string): Promise<SystemEvent[]> {
    let events = causalKernel.replay(trace_id);
    if (events.length === 0) {
      events = await persistencePipeline.loadEventsByTraceId(trace_id);
    }
    return events;
  }

  private rebuildFromEvents(events: SystemEvent[]): SystemState {
    let state = createInitialState();
    for (const event of events) {
      state = applyEvent(state, event);
    }
    return state;
  }

  /**
   * 检查单个 snapshot 是否漂移
   */
  private async checkSnapshotDrift(
    trace_id: string,
    snapshot: SystemSnapshot,
  ): Promise<string | null> {
    const events = await this.getEvents(trace_id);

    if (snapshot.cursor > events.length) {
      return `cursor (${snapshot.cursor}) exceeds event count (${events.length})`;
    }

    if (snapshot.event_count !== snapshot.cursor) {
      return `event_count (${snapshot.event_count}) != cursor (${snapshot.cursor})`;
    }

    return null;
  }

  private emptyResult(
    trace_id: string,
    strategy: CompactionStrategy,
    startTime: number,
  ): CompactionResult {
    return {
      trace_id,
      strategy,
      before_count: 0,
      after_count: 0,
      reduction_ratio: 0,
      actions: [],
      kept_snapshots: [],
      success: true,
      duration_ms: Date.now() - startTime,
    };
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const snapshotCompactor = new SnapshotCompactor();
