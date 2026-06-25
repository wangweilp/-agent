/**
 * 知维 OS 因果内核 — UI 订阅 Hooks
 *
 * 事件驱动 UI 的接入点：
 * - useEventStream(filter)   实时订阅事件流（事件驱动 UI 更新）
 * - useEventReplay(trace_id) 回放指定 trace 的完整事件链
 * - useCausalChain(event_id)  构建因果链树
 * - useCausalPath(event_id)   获取因果路径
 * - useKernelStats()          内核统计
 */

import { useEffect, useState, useRef, useCallback } from "react";
import { causalKernel } from "@/lib/event-bus/causal-kernel";
import type {
  SystemEvent,
  EventFilter,
  CausalChainNode,
  CausalPath,
  EventSource,
  EventSeverity,
} from "@/types/event-bus";

// ═══════════════════════════════════════════════════════════════
// useEventStream — 实时事件流订阅
// ═══════════════════════════════════════════════════════════════

/**
 * 实时订阅事件流 — 事件驱动 UI 的核心 hook
 *
 * @param filter 过滤器（source / type / severity / trace_id / predicate）
 * @param maxEvents 缓冲区上限（默认 100）
 * @returns 事件列表（最新在前）+ 是否活跃
 */
export function useEventStream(
  filter: EventFilter,
  maxEvents = 100,
): {
  events: SystemEvent[];
  total: number;
  clear: () => void;
} {
  const [events, setEvents] = useState<SystemEvent[]>([]);
  const [total, setTotal] = useState(0);
  const filterRef = useRef(filter);
  filterRef.current = filter;

  useEffect(() => {
    const handle = causalKernel.subscribe(filterRef.current, (event) => {
      setEvents((prev) => [event, ...prev].slice(0, maxEvents));
      setTotal((t) => t + 1);
    });

    return () => handle.unsubscribe();
  }, [maxEvents]);

  const clear = useCallback(() => {
    setEvents([]);
    setTotal(0);
  }, []);

  return { events, total, clear };
}

// ═══════════════════════════════════════════════════════════════
// useEventReplay — Trace 回放
// ═══════════════════════════════════════════════════════════════

/**
 * 回放指定 trace 的完整事件链
 * 按 timestamp 升序返回
 */
export function useEventReplay(trace_id: string | null): {
  events: SystemEvent[];
  isLoading: boolean;
} {
  const [events, setEvents] = useState<SystemEvent[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!trace_id) {
      setEvents([]);
      return;
    }

    setIsLoading(true);
    const replayed = causalKernel.replay(trace_id);
    setEvents(replayed);
    setIsLoading(false);

    // 订阅该 trace 的新事件（实时回放模式）
    const handle = causalKernel.subscribe(
      { trace_id },
      () => {
        const updated = causalKernel.replay(trace_id);
        setEvents(updated);
      },
    );

    return () => handle.unsubscribe();
  }, [trace_id]);

  return { events, isLoading };
}

// ═══════════════════════════════════════════════════════════════
// useCausalChain — 因果链树
// ═══════════════════════════════════════════════════════════════

/**
 * 构建因果链树 — 从指定事件开始递归展开所有子事件
 * 用于可视化：决策链 / 行为链 / 因果树
 */
export function useCausalChain(event_id: string | null): CausalChainNode | null {
  const [chain, setChain] = useState<CausalChainNode | null>(null);

  useEffect(() => {
    if (!event_id) {
      setChain(null);
      return;
    }

    const refresh = () => {
      const node = causalKernel.getCausalChain(event_id);
      setChain(node);
    };

    refresh();

    // 订阅新事件以更新因果树
    const handle = causalKernel.subscribeAll(() => {
      // 节流：仅当新事件可能影响当前链时刷新
      refresh();
    });

    return () => handle.unsubscribe();
  }, [event_id]);

  return chain;
}

// ═══════════════════════════════════════════════════════════════
// useCausalPath — 因果路径
// ═══════════════════════════════════════════════════════════════

/**
 * 获取因果路径 — 从根事件到指定事件的线性链
 * 用于回溯：为什么这个事件会发生？
 */
export function useCausalPath(event_id: string | null): CausalPath | null {
  const [path, setPath] = useState<CausalPath | null>(null);

  useEffect(() => {
    if (!event_id) {
      setPath(null);
      return;
    }

    const refresh = () => {
      const p = causalKernel.getCausalPath(event_id);
      setPath(p);
    };

    refresh();

    const handle = causalKernel.subscribeAll(refresh);
    return () => handle.unsubscribe();
  }, [event_id]);

  return path;
}

// ═══════════════════════════════════════════════════════════════
// useKernelStats — 内核统计
// ═══════════════════════════════════════════════════════════════

interface KernelStats {
  totalPublished: number;
  activeSubscribers: number;
  storedEvents: number;
  traceCount: number;
  bySource: Record<EventSource, number>;
  bySeverity: Record<EventSeverity, number>;
}

/**
 * 内核统计 — 实时反映系统事件活跃度
 */
export function useKernelStats(): KernelStats {
  const [stats, setStats] = useState<KernelStats>(() => computeStats());

  useEffect(() => {
    const handle = causalKernel.subscribeAll(() => {
      setStats(computeStats());
    });
    return () => handle.unsubscribe();
  }, []);

  return stats;
}

function computeStats(): KernelStats {
  const base = causalKernel.getStats();
  return {
    totalPublished: base.totalPublished,
    activeSubscribers: base.activeSubscribers,
    storedEvents: base.storedEvents,
    traceCount: base.traceCount,
    bySource: causalKernel.getStatsBySource(),
    bySeverity: causalKernel.getStatsBySeverity(),
  };
}

// ═══════════════════════════════════════════════════════════════
// useRecentTraces — 最近的 trace 列表
// ═══════════════════════════════════════════════════════════════

/**
 * 获取最近的 trace_id 列表（用于回放选择）
 */
export function useRecentTraces(limit = 20): string[] {
  const [traces, setTraces] = useState<string[]>([]);

  useEffect(() => {
    const refresh = () => {
      setTraces(causalKernel.getTraceIds().slice(-limit).reverse());
    };
    refresh();

    const handle = causalKernel.subscribeAll(refresh);
    return () => handle.unsubscribe();
  }, [limit]);

  return traces;
}
