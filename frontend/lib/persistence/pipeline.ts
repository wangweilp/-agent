/**
 * 知维 OS Persistence Layer — Persistence Pipeline
 * Zhiwei OS Persistence Layer — Persistence Pipeline
 *
 * 持久化管道核心：
 *   event → EventStore → SnapshotStore → Replay Engine
 *
 * 职责：
 * - 拦截 CausalKernel.publish() 的事件，异步写入 EventStore
 * - 自动检查点：每 N 事件创建 snapshot
 * - 提供 createSnapshot / restoreFromSnapshot / listSnapshots API
 * - 集成到 ReplayCursor：loadTrace 优先从 EventStore 读取
 *
 * 约束：
 * - 不修改 CausalKernel 的因果索引逻辑
 * - 不修改 ReplayCursor 的 applyEvent 逻辑
 * - 异步写入，不阻塞主流程（fire-and-forget）
 * - backward compatible：未初始化时自动降级为内存模式
 */

import { causalKernel } from "@/lib/event-bus/causal-kernel";
import { applyEvent } from "@/lib/replay/state-reducer";
import { createInitialState, type SystemState } from "@/lib/replay/types";
import type { SystemEvent } from "@/types/event-bus";
import type {
  IEventStore,
  ISnapshotStore,
  SystemSnapshot,
  SnapshotReason,
  PersistenceConfig,
} from "@/lib/persistence/types";
import { serializeState, deserializeState, DEFAULT_PERSISTENCE_CONFIG } from "@/lib/persistence/types";
import { createEventStore } from "@/lib/persistence/event-store";
import { createSnapshotStore, generateSnapshotId } from "@/lib/persistence/snapshot-store";

// ═══════════════════════════════════════════════════════════════
// PersistencePipeline — 持久化管道单例
// ═══════════════════════════════════════════════════════════════

type PipelineListener = (state: PipelineState) => void;

export interface PipelineState {
  initialized: boolean;
  eventStoreType: "memory" | "indexeddb";
  snapshotStoreType: "memory" | "indexeddb";
  eventsPersisted: number;
  snapshotsCreated: number;
  lastSnapshotAt: string | null;
  lastError: string | null;
}

class PersistencePipeline {
  private eventStore: IEventStore | null = null;
  private snapshotStore: ISnapshotStore | null = null;
  private config: PersistenceConfig = DEFAULT_PERSISTENCE_CONFIG;
  private state: PipelineState = {
    initialized: false,
    eventStoreType: "memory",
    snapshotStoreType: "memory",
    eventsPersisted: 0,
    snapshotsCreated: 0,
    lastSnapshotAt: null,
    lastError: null,
  };
  private listeners: Set<PipelineListener> = new Set();

  // trace_id → 事件计数器（用于 autoCheckpoint）
  private traceEventCounts: Map<string, number> = new Map();

  // 订阅 CausalKernel 的句柄
  private subscriptionHandle: { unsubscribe: () => void } | null = null;

  /**
   * 初始化持久化管道
   * - 创建 EventStore + SnapshotStore
   * - 订阅 CausalKernel 事件流
   */
  async initialize(config?: Partial<PersistenceConfig>): Promise<void> {
    if (this.state.initialized) return;

    this.config = { ...DEFAULT_PERSISTENCE_CONFIG, ...config };

    // 创建 stores
    this.eventStore = createEventStore();
    this.snapshotStore = createSnapshotStore();

    // 检测实际类型
    const eventStoreType = this.eventStore.constructor.name.includes("IndexedDB")
      ? "indexeddb" : "memory";
    const snapshotStoreType = this.snapshotStore.constructor.name.includes("IndexedDB")
      ? "indexeddb" : "memory";

    this.updateState({
      initialized: true,
      eventStoreType,
      snapshotStoreType,
    });

    // 订阅 CausalKernel — 拦截所有事件
    this.subscriptionHandle = causalKernel.subscribeAll((event) => {
      // fire-and-forget，不阻塞主流程
      this.handleEvent(event).catch((err) => {
        console.error("[Persistence] event persist error:", err);
      });
    });

    console.info("[Persistence] pipeline initialized", {
      eventStore: eventStoreType,
      snapshotStore: snapshotStoreType,
    });
  }

  /**
   * 关闭管道
   */
  shutdown(): void {
    if (this.subscriptionHandle) {
      this.subscriptionHandle.unsubscribe();
      this.subscriptionHandle = null;
    }
    this.updateState({ initialized: false });
  }

  // ─────────────────────────────────────────────────────────────
  // 事件处理（自动持久化 + autoCheckpoint）
  // ─────────────────────────────────────────────────────────────

  /**
   * 处理事件 — 写入 EventStore + 检查 autoCheckpoint
   */
  private async handleEvent(event: SystemEvent): Promise<void> {
    if (!this.eventStore) return;

    // 1. 写入 EventStore
    await this.eventStore.put(event);
    this.updateState({ eventsPersisted: this.state.eventsPersisted + 1 });

    // 2. autoCheckpoint 检查
    if (this.config.enableSnapshotStore && this.config.autoCheckpointInterval > 0) {
      const count = (this.traceEventCounts.get(event.trace_id) || 0) + 1;
      this.traceEventCounts.set(event.trace_id, count);

      if (count % this.config.autoCheckpointInterval === 0) {
        await this.autoCreateSnapshot(event.trace_id);
      }
    }
  }

  /**
   * 自动创建快照（从当前内存状态重建）
   */
  private async autoCreateSnapshot(trace_id: string): Promise<void> {
    if (!this.snapshotStore) return;

    try {
      // 从 CausalKernel replay 重建状态
      const events = causalKernel.replay(trace_id);
      const state = this.rebuildStateFromEvents(events);

      const snapshot: SystemSnapshot = {
        snapshot_id: generateSnapshotId(),
        trace_id,
        cursor: events.length,
        state: serializeState(state),
        timestamp: new Date().toISOString(),
        reason: "auto_checkpoint",
        event_count: events.length,
      };

      await this.snapshotStore.put(snapshot);
      this.updateState({
        snapshotsCreated: this.state.snapshotsCreated + 1,
        lastSnapshotAt: snapshot.timestamp,
      });

      // 清理过多快照
      await this.cleanupOldSnapshots(trace_id);
    } catch (err) {
      console.error("[Persistence] autoCheckpoint error:", err);
    }
  }

  /**
   * 从事件列表重建状态（使用 applyEvent 纯函数）
   */
  private rebuildStateFromEvents(events: SystemEvent[]): SystemState {
    let state = createInitialState();
    for (const event of events) {
      state = applyEvent(state, event);
    }
    return state;
  }

  /**
   * 清理过多的快照（保留最近 N 个）
   */
  private async cleanupOldSnapshots(trace_id: string): Promise<void> {
    if (!this.snapshotStore) return;
    const snapshots = await this.snapshotStore.listByTraceId(trace_id);
    const maxKeep = this.config.maxSnapshotsPerTrace;

    if (snapshots.length > maxKeep) {
      // 保留最近 maxKeep 个，删除其余
      const toDelete = snapshots.slice(0, snapshots.length - maxKeep);
      for (const snap of toDelete) {
        await this.snapshotStore.delete(snap.snapshot_id);
      }
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 公共 API — Snapshot 管理
  // ─────────────────────────────────────────────────────────────

  /**
   * 创建快照（手动）
   * @param trace_id 所属 trace
   * @param state 当前状态
   * @param reason 创建原因（默认 manual）
   */
  async createSnapshot(
    trace_id: string,
    state: SystemState,
    reason: SnapshotReason = "manual",
  ): Promise<SystemSnapshot | null> {
    if (!this.snapshotStore) return null;

    const events = causalKernel.replay(trace_id);
    const snapshot: SystemSnapshot = {
      snapshot_id: generateSnapshotId(),
      trace_id,
      cursor: events.length,
      state: serializeState(state),
      timestamp: new Date().toISOString(),
      reason,
      event_count: events.length,
    };

    await this.snapshotStore.put(snapshot);
    this.updateState({
      snapshotsCreated: this.state.snapshotsCreated + 1,
      lastSnapshotAt: snapshot.timestamp,
    });

    return snapshot;
  }

  /**
   * 从快照恢复状态
   * @param snapshot_id 快照 ID
   * @returns 恢复的 SystemState（null 表示快照不存在）
   */
  async restoreFromSnapshot(snapshot_id: string): Promise<SystemState | null> {
    if (!this.snapshotStore) return null;

    const snapshot = await this.snapshotStore.get(snapshot_id);
    if (!snapshot) return null;

    return deserializeState(snapshot.state);
  }

  /**
   * 列出指定 trace 的所有快照
   */
  async listSnapshots(trace_id: string): Promise<SystemSnapshot[]> {
    if (!this.snapshotStore) return [];
    return this.snapshotStore.listByTraceId(trace_id);
  }

  /**
   * 获取指定 trace 最近的快照（用于 replay 加速）
   */
  async getLatestSnapshot(trace_id: string): Promise<SystemSnapshot | null> {
    if (!this.snapshotStore) return null;
    return this.snapshotStore.getLatestByTraceId(trace_id);
  }

  /**
   * 获取指定游标之前的最近快照
   */
  async getSnapshotBeforeCursor(
    trace_id: string,
    cursor: number,
  ): Promise<SystemSnapshot | null> {
    if (!this.snapshotStore) return null;
    return this.snapshotStore.getLatestBeforeCursor(trace_id, cursor);
  }

  /**
   * 删除快照
   */
  async deleteSnapshot(snapshot_id: string): Promise<void> {
    if (!this.snapshotStore) return;
    await this.snapshotStore.delete(snapshot_id);
  }

  // ─────────────────────────────────────────────────────────────
  // 公共 API — EventStore 查询
  // ─────────────────────────────────────────────────────────────

  /**
   * 从 EventStore 加载指定 trace 的所有事件
   * 用于 ReplayCursor 跨 session 恢复
   */
  async loadEventsByTraceId(trace_id: string): Promise<SystemEvent[]> {
    if (!this.eventStore) return [];
    return this.eventStore.getByTraceId(trace_id);
  }

  /**
   * 获取所有 trace_id
   */
  async getAllTraceIds(): Promise<string[]> {
    if (!this.eventStore) return [];
    return this.eventStore.getTraceIds();
  }

  /**
   * 时间范围查询
   */
  async getEventsByTimeRange(from: string, to: string): Promise<SystemEvent[]> {
    if (!this.eventStore) return [];
    return this.eventStore.getByTimeRange(from, to);
  }

  /**
   * 获取 EventStore
   */
  getEventStore(): IEventStore | null {
    return this.eventStore;
  }

  /**
   * 获取 SnapshotStore
   */
  getSnapshotStore(): ISnapshotStore | null {
    return this.snapshotStore;
  }

  // ─────────────────────────────────────────────────────────────
  // 状态订阅
  // ─────────────────────────────────────────────────────────────

  /**
   * 订阅管道状态变化
   */
  subscribe(listener: PipelineListener): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => { this.listeners.delete(listener); };
  }

  /**
   * 获取当前状态
   */
  getState(): PipelineState {
    return { ...this.state };
  }

  private updateState(patch: Partial<PipelineState>): void {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) {
      try {
        listener(this.state);
      } catch (err) {
        console.error("[Persistence] listener error:", err);
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const persistencePipeline = new PersistencePipeline();
