/**
 * 知维 OS Persistence Layer — UI Hooks
 * Zhiwei OS Persistence Layer — React Hooks
 *
 * 提供：
 * - usePersistence()         持久化管道状态 + 控制
 * - useSnapshots(trace_id)    快照列表
 * - useCrossSessionReplay()   跨 session 回放恢复
 */

import { useEffect, useState, useCallback } from "react";
import { persistencePipeline, type PipelineState } from "@/lib/persistence/pipeline";
import type { SystemSnapshot } from "@/lib/persistence/types";

// ═══════════════════════════════════════════════════════════════
// usePersistence — 持久化管道 Hook
// ═══════════════════════════════════════════════════════════════

export interface PersistenceHook {
  state: PipelineState;
  initialize: (config?: Record<string, unknown>) => Promise<void>;
  shutdown: () => void;
  createSnapshot: (
    trace_id: string,
    state: import("@/lib/replay/types").SystemState,
    reason?: import("@/lib/persistence/types").SnapshotReason,
  ) => Promise<SystemSnapshot | null>;
  restoreFromSnapshot: (snapshot_id: string) => Promise<import("@/lib/replay/types").SystemState | null>;
  listSnapshots: (trace_id: string) => Promise<SystemSnapshot[]>;
  deleteSnapshot: (snapshot_id: string) => Promise<void>;
}

/**
 * 持久化管道 Hook — 自动初始化
 */
export function usePersistence(autoInitialize = true): PersistenceHook {
  const [state, setState] = useState<PipelineState>(persistencePipeline.getState());

  useEffect(() => {
    const unsubscribe = persistencePipeline.subscribe(setState);
    if (autoInitialize && !state.initialized) {
      persistencePipeline.initialize().catch((err) => {
        console.error("[usePersistence] initialize error:", err);
      });
    }
    return unsubscribe;
  }, [autoInitialize]);

  const initialize = useCallback(async (config?: Record<string, unknown>) => {
    await persistencePipeline.initialize(config);
  }, []);

  const shutdown = useCallback(() => {
    persistencePipeline.shutdown();
  }, []);

  const createSnapshot = useCallback(
    async (
      trace_id: string,
      state: import("@/lib/replay/types").SystemState,
      reason?: import("@/lib/persistence/types").SnapshotReason,
    ) => persistencePipeline.createSnapshot(trace_id, state, reason),
    [],
  );

  const restoreFromSnapshot = useCallback(
    async (snapshot_id: string) => persistencePipeline.restoreFromSnapshot(snapshot_id),
    [],
  );

  const listSnapshots = useCallback(
    async (trace_id: string) => persistencePipeline.listSnapshots(trace_id),
    [],
  );

  const deleteSnapshot = useCallback(
    async (snapshot_id: string) => persistencePipeline.deleteSnapshot(snapshot_id),
    [],
  );

  return {
    state,
    initialize,
    shutdown,
    createSnapshot,
    restoreFromSnapshot,
    listSnapshots,
    deleteSnapshot,
  };
}

// ═══════════════════════════════════════════════════════════════
// useSnapshots — 快照列表 Hook
// ═══════════════════════════════════════════════════════════════

export interface SnapshotsHook {
  snapshots: SystemSnapshot[];
  loading: boolean;
  refresh: () => Promise<void>;
}

/**
 * 快照列表 Hook
 */
export function useSnapshots(trace_id: string | null): SnapshotsHook {
  const [snapshots, setSnapshots] = useState<SystemSnapshot[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!trace_id) {
      setSnapshots([]);
      return;
    }
    setLoading(true);
    try {
      const list = await persistencePipeline.listSnapshots(trace_id);
      setSnapshots(list);
    } catch (err) {
      console.error("[useSnapshots] refresh error:", err);
      setSnapshots([]);
    } finally {
      setLoading(false);
    }
  }, [trace_id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { snapshots, loading, refresh };
}

// ═══════════════════════════════════════════════════════════════
// useCrossSessionReplay — 跨 session 回放恢复
// ═══════════════════════════════════════════════════════════════

export interface CrossSessionReplayHook {
  /** 可恢复的 trace_id 列表 */
  availableTraces: string[];
  loadingTraces: boolean;
  /** 加载 trace（从 EventStore 恢复事件到 CausalKernel） */
  loadTraceFromPersistence: (trace_id: string) => Promise<boolean>;
  /** 从最近快照恢复状态 */
  restoreLatestSnapshot: (trace_id: string) => Promise<import("@/lib/replay/types").SystemState | null>;
}

/**
 * 跨 session 回放恢复 Hook
 * - 列出 EventStore 中所有可恢复的 trace
 * - 加载 trace 时从 IndexedDB 恢复事件到 CausalKernel
 */
export function useCrossSessionReplay(): CrossSessionReplayHook {
  const [availableTraces, setAvailableTraces] = useState<string[]>([]);
  const [loadingTraces, setLoadingTraces] = useState(false);

  const refreshTraces = useCallback(async () => {
    setLoadingTraces(true);
    try {
      const traces = await persistencePipeline.getAllTraceIds();
      setAvailableTraces(traces);
    } catch (err) {
      console.error("[useCrossSessionReplay] refresh error:", err);
      setAvailableTraces([]);
    } finally {
      setLoadingTraces(false);
    }
  }, []);

  useEffect(() => {
    refreshTraces();
  }, [refreshTraces]);

  const loadTraceFromPersistence = useCallback(async (trace_id: string): Promise<boolean> => {
    try {
      // 从 EventStore 加载事件
      const events = await persistencePipeline.loadEventsByTraceId(trace_id);
      if (events.length === 0) return false;

      // 重新发布到 CausalKernel（恢复内存索引）
      // 注意：这里使用 publish 而非 emit，保留原始 event_id/timestamp
      const { causalKernel } = await import("@/lib/event-bus/causal-kernel");
      for (const event of events) {
        // 仅当 CausalKernel 中不存在时才 publish（避免重复）
        if (!causalKernel.getEvent(event.event_id)) {
          causalKernel.publish(event);
        }
      }
      return true;
    } catch (err) {
      console.error("[useCrossSessionReplay] loadTrace error:", err);
      return false;
    }
  }, []);

  const restoreLatestSnapshot = useCallback(
    async (trace_id: string): Promise<import("@/lib/replay/types").SystemState | null> => {
      const snapshot = await persistencePipeline.getLatestSnapshot(trace_id);
      if (!snapshot) return null;
      return persistencePipeline.restoreFromSnapshot(snapshot.snapshot_id);
    },
    [],
  );

  return {
    availableTraces,
    loadingTraces,
    loadTraceFromPersistence,
    restoreLatestSnapshot,
  };
}
