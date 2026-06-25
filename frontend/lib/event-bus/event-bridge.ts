/**
 * 知维 OS Event Bridge — 前端 SSE 接收层
 * Zhiwei OS Event Bridge — Frontend SSE Ingestion Client
 *
 * L2 Replay Engine 核心组件：
 * - 连接后端 /events/stream SSE 端点
 * - 接收 backend EventBus 的真实事件
 * - 转换为 SystemEvent 并 ingest 到 CausalKernel（origin="backend"）
 * - 自动重连（指数退避）
 * - 区分 real events vs simulated events
 *
 * 架构：
 *   Python EventBus → SSE /events/stream → EventBridgeClient → causalKernel.publish()
 */

import { causalKernel } from "@/lib/event-bus/causal-kernel";
import type { SystemEvent, EventOrigin } from "@/types/event-bus";

// ═══════════════════════════════════════════════════════════════
// EventBridgeClient — SSE 客户端单例
// ═══════════════════════════════════════════════════════════════

type ConnectionStatus = "disconnected" | "connecting" | "connected" | "error";

interface BridgeState {
  status: ConnectionStatus;
  url: string;
  eventsIngested: number;
  lastEventAt: string | null;
  lastError: string | null;
  reconnectAttempts: number;
}

type StateListener = (state: BridgeState) => void;

class EventBridgeClient {
  private eventSource: EventSource | null = null;
  private state: BridgeState = {
    status: "disconnected",
    url: "",
    eventsIngested: 0,
    lastEventAt: null,
    lastError: null,
    reconnectAttempts: 0,
  };
  private listeners: Set<StateListener> = new Set();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private maxReconnectDelay = 30000; // 30s 上限

  /**
   * 连接到后端 SSE 端点
   */
  connect(url = "/events/stream"): void {
    if (this.state.status === "connected" || this.state.status === "connecting") {
      return;
    }

    this.updateState({
      status: "connecting",
      url,
      lastError: null,
    });

    try {
      this.eventSource = new EventSource(url);

      this.eventSource.onopen = () => {
        this.updateState({
          status: "connected",
          reconnectAttempts: 0,
          lastError: null,
        });
      };

      this.eventSource.onmessage = (ev: MessageEvent) => {
        this.handleMessage(ev.data);
      };

      this.eventSource.onerror = () => {
        this.updateState({
          status: "error",
          lastError: "SSE connection error",
        });
        this.scheduleReconnect();
      };
    } catch (err) {
      this.updateState({
        status: "error",
        lastError: err instanceof Error ? err.message : String(err),
      });
      this.scheduleReconnect();
    }
  }

  /**
   * 断开连接
   */
  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    this.updateState({ status: "disconnected" });
  }

  /**
   * 处理收到的 SSE 消息 — 转换并 ingest 到 CausalKernel
   */
  private handleMessage(rawData: string): void {
    try {
      const event = JSON.parse(rawData) as SystemEvent;

      // 标记为 backend 事件
      const backendEvent: SystemEvent = {
        ...event,
        origin: "backend" as EventOrigin,
      };

      // 直接写入 CausalKernel（绕过 emit，因为 event_id/timestamp 已由后端生成）
      causalKernel.publish(backendEvent);

      this.updateState({
        eventsIngested: this.state.eventsIngested + 1,
        lastEventAt: new Date().toISOString(),
      });
    } catch (err) {
      this.updateState({
        lastError: `Failed to parse SSE event: ${err instanceof Error ? err.message : String(err)}`,
      });
    }
  }

  /**
   * 指数退避重连
   */
  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;

    const attempts = this.state.reconnectAttempts;
    const delay = Math.min(1000 * Math.pow(2, attempts), this.maxReconnectDelay);

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.updateState({ reconnectAttempts: attempts + 1 });
      this.connect(this.state.url);
    }, delay);
  }

  /**
   * 状态订阅
   */
  subscribe(listener: StateListener): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => { this.listeners.delete(listener); };
  }

  /**
   * 获取当前状态
   */
  getState(): BridgeState {
    return { ...this.state };
  }

  private updateState(patch: Partial<BridgeState>): void {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) {
      try {
        listener(this.state);
      } catch (err) {
        console.error("[EventBridge] state listener error:", err);
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const eventBridge = new EventBridgeClient();

// ═══════════════════════════════════════════════════════════════
// 辅助：标记 simulate 事件
// ═══════════════════════════════════════════════════════════════

/**
 * 为 simulate 事件添加 origin 标记
 * 用于 createRootEvent / createChildEvent / createMultiCausalEvent
 */
export function markAsSimulated<T extends SystemEvent>(event: T): T {
  return { ...event, origin: "simulated" };
}

export type { BridgeState, ConnectionStatus };
