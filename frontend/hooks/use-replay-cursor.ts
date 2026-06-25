/**
 * 知维 OS Replay Engine — UI Hook
 * Zhiwei OS Replay Engine — React Hook
 *
 * 接入 ReplayCursor，提供 React 友好的 API：
 * - useReplayCursor(trace_id)  回放游标 + 控制方法
 * - useEventBridge()           Event Bridge 连接状态
 */

import { useEffect, useState, useCallback, useRef } from "react";
import { replayCursor } from "@/lib/replay/replay-cursor";
import { eventBridge } from "@/lib/event-bus/event-bridge";
import type { ExecutionState } from "@/lib/replay/types";
import type { BridgeState } from "@/lib/event-bus/event-bridge";

// ═══════════════════════════════════════════════════════════════
// useReplayCursor — 回放游标 Hook
// ═══════════════════════════════════════════════════════════════

export interface ReplayCursorHook {
  state: ExecutionState;
  stepForward: () => void;
  stepBackward: () => void;
  jumpTo: (event_id: string) => void;
  play: (intervalMs?: number) => void;
  pause: () => void;
  reset: () => void;
  jumpToEnd: () => void;
}

/**
 * 回放游标 Hook — 加载 trace 并提供控制方法
 *
 * @param trace_id Trace ID（null 时不加载）
 */
export function useReplayCursor(trace_id: string | null): ReplayCursorHook {
  const [state, setState] = useState<ExecutionState>(replayCursor.getState());
  const traceRef = useRef(trace_id);
  traceRef.current = trace_id;

  useEffect(() => {
    const unsubscribe = replayCursor.subscribe(setState);
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (trace_id) {
      replayCursor.loadTrace(trace_id);
    }
  }, [trace_id]);

  const stepForward = useCallback(() => replayCursor.stepForward(), []);
  const stepBackward = useCallback(() => replayCursor.stepBackward(), []);
  const jumpTo = useCallback((event_id: string) => replayCursor.jumpTo(event_id), []);
  const play = useCallback((intervalMs?: number) => replayCursor.play(intervalMs), []);
  const pause = useCallback(() => replayCursor.pause(), []);
  const reset = useCallback(() => replayCursor.reset(), []);
  const jumpToEnd = useCallback(() => replayCursor.jumpToEnd(), []);

  return {
    state,
    stepForward,
    stepBackward,
    jumpTo,
    play,
    pause,
    reset,
    jumpToEnd,
  };
}

// ═══════════════════════════════════════════════════════════════
// useEventBridge — Event Bridge 连接状态 Hook
// ═══════════════════════════════════════════════════════════════

export interface EventBridgeHook {
  bridgeState: BridgeState;
  connect: (url?: string) => void;
  disconnect: () => void;
}

/**
 * Event Bridge 连接状态 Hook
 * 自动连接后端 SSE 端点
 *
 * @param autoConnect 是否自动连接（默认 true）
 * @param url SSE 端点 URL（默认 /events/stream）
 */
export function useEventBridge(
  autoConnect = true,
  url = "/events/stream",
): EventBridgeHook {
  const [bridgeState, setBridgeState] = useState<BridgeState>(eventBridge.getState());

  useEffect(() => {
    const unsubscribe = eventBridge.subscribe(setBridgeState);
    if (autoConnect) {
      eventBridge.connect(url);
    }
    return () => {
      unsubscribe();
    };
  }, [autoConnect, url]);

  const connect = useCallback((connectUrl?: string) => {
    eventBridge.connect(connectUrl || url);
  }, [url]);

  const disconnect = useCallback(() => {
    eventBridge.disconnect();
  }, []);

  return { bridgeState, connect, disconnect };
}
