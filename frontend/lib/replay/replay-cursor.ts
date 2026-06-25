/**
 * 知维 OS Replay Engine — Replay Cursor
 * Zhiwei OS Replay Engine — Replay Cursor Engine
 *
 * L2 Replay Engine 核心：
 * - stepForward()   单步前进（按因果顺序，验证 parent_event_id）
 * - stepBackward()  单步后退（回退到上一帧状态）
 * - jumpTo(event_id) 跳转到指定事件
 * - play()          自动播放
 * - pause()         暂停
 *
 * 关键约束：
 * - 按因果顺序执行（不是 timestamp）
 * - 必须验证 parent_event_id 已执行
 * - 支持 pause/resume
 * - 状态重建基于 applyEvent 纯函数
 */

import { causalKernel } from "@/lib/event-bus/causal-kernel";
import { applyEvent } from "@/lib/replay/state-reducer";
import {
  createInitialExecutionState,
  createInitialState,
  type SystemState,
  type ExecutionState,
  type ReplayFrame,
  type ExecutionStatus,
} from "@/lib/replay/types";
import type { SystemEvent } from "@/types/event-bus";

// ═══════════════════════════════════════════════════════════════
// ReplayCursor — 回放游标引擎
// ═══════════════════════════════════════════════════════════════

type CursorListener = (state: ExecutionState) => void;

class ReplayCursor {
  private state: ExecutionState = createInitialExecutionState();
  private listeners: Set<CursorListener> = new Set();
  private playTimer: ReturnType<typeof setInterval> | null = null;
  private playIntervalMs = 500;

  /**
   * 加载 trace — 从 CausalKernel 拉取事件并按因果顺序排序
   */
  loadTrace(trace_id: string): void {
    this.pause();
    const events = causalKernel.replay(trace_id);
    // 因果顺序排序（拓扑序）：parent 必须在 child 之前
    const sorted = this.sortByCausalOrder(events);

    // 重建所有帧（使用 applyEvent 纯函数）
    const frames: ReplayFrame[] = [];
    let currentState = createInitialState();
    const executedIds = new Set<string>();

    for (let i = 0; i < sorted.length; i++) {
      const event = sorted[i];
      const stateBefore = currentState;

      let applied = true;
      let error: string | undefined;

      // 因果顺序验证
      if (event.causal.parent_event_id && !executedIds.has(event.causal.parent_event_id)) {
        applied = false;
        error = `parent_event_id ${event.causal.parent_event_id} not yet executed`;
      }

      let stateAfter = currentState;
      if (applied) {
        stateAfter = applyEvent(currentState, event);
        executedIds.add(event.event_id);
      }

      frames.push({
        index: i,
        state_before: stateBefore,
        event,
        state_after: stateAfter,
        applied,
        error,
      });

      currentState = stateAfter;
    }

    this.state = {
      status: "idle",
      cursor: 0,
      total_frames: frames.length,
      current_state: frames.length > 0 ? frames[0].state_before : createInitialState(),
      frames,
      executed_event_ids: new Set(),
      last_error: null,
    };
    this.notify();
  }

  /**
   * 单步前进 — 按因果顺序执行下一帧
   * 验证 parent_event_id 已执行
   */
  stepForward(): boolean {
    if (this.state.cursor >= this.state.total_frames) {
      this.updateState({ status: "completed" });
      return false;
    }

    const frame = this.state.frames[this.state.cursor];
    if (!frame) return false;

    // 因果顺序验证
    if (frame.event.causal.parent_event_id && !this.state.executed_event_ids.has(frame.event.causal.parent_event_id)) {
      this.updateState({
        status: "error",
        last_error: `Causal order violation: parent ${frame.event.causal.parent_event_id} not executed`,
      });
      return false;
    }

    // 执行：应用事件到当前状态
    const newState = applyEvent(this.state.current_state, frame.event);
    const newExecuted = new Set(this.state.executed_event_ids);
    newExecuted.add(frame.event.event_id);

    this.updateState({
      status: "step_forward",
      cursor: this.state.cursor + 1,
      current_state: newState,
      executed_event_ids: newExecuted,
      last_error: null,
    });

    // 检查是否完成
    if (this.state.cursor >= this.state.total_frames) {
      this.updateState({ status: "completed" });
    } else {
      this.updateState({ status: "paused" });
    }

    return true;
  }

  /**
   * 单步后退 — 回退到上一帧状态
   * 通过重新执行前 N-1 帧实现（纯函数无副作用，可重建）
   */
  stepBackward(): boolean {
    if (this.state.cursor <= 0) {
      return false;
    }

    const targetCursor = this.state.cursor - 1;
    this.rebuildToCursor(targetCursor);
    this.updateState({ status: "paused" });
    return true;
  }

  /**
   * 跳转到指定事件 — 重建到该事件所在帧
   */
  jumpTo(event_id: string): boolean {
    const frameIndex = this.state.frames.findIndex((f) => f.event.event_id === event_id);
    if (frameIndex === -1) {
      this.updateState({
        status: "error",
        last_error: `Event ${event_id} not found in trace`,
      });
      return false;
    }

    // 跳转到该帧之后（即执行到并包含该帧）
    this.rebuildToCursor(frameIndex + 1);
    this.updateState({ status: "paused" });
    return true;
  }

  /**
   * 自动播放 — 按间隔自动 stepForward
   */
  play(intervalMs?: number): void {
    if (this.playTimer) {
      clearInterval(this.playTimer);
    }
    if (intervalMs) this.playIntervalMs = intervalMs;

    this.updateState({ status: "playing" });

    this.playTimer = setInterval(() => {
      const ok = this.stepForward();
      if (!ok) {
        this.pause();
      }
    }, this.playIntervalMs);
  }

  /**
   * 暂停
   */
  pause(): void {
    if (this.playTimer) {
      clearInterval(this.playTimer);
      this.playTimer = null;
    }
    if (this.state.status === "playing") {
      this.updateState({ status: "paused" });
    }
  }

  /**
   * 重置到起点
   */
  reset(): void {
    this.pause();
    this.updateState({
      status: "idle",
      cursor: 0,
      current_state: this.state.frames.length > 0
        ? this.state.frames[0].state_before
        : createInitialState(),
      executed_event_ids: new Set(),
      last_error: null,
    });
  }

  /**
   * 跳转到末尾
   */
  jumpToEnd(): void {
    this.rebuildToCursor(this.state.total_frames);
    this.updateState({ status: "completed" });
  }

  /**
   * 获取当前状态
   */
  getState(): ExecutionState {
    return this.state;
  }

  /**
   * 获取当前帧
   */
  getCurrentFrame(): ReplayFrame | null {
    if (this.state.cursor === 0) return null;
    return this.state.frames[this.state.cursor - 1] || null;
  }

  /**
   * 订阅状态变化
   */
  subscribe(listener: CursorListener): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => { this.listeners.delete(listener); };
  }

  // ─────────────────────────────────────────────────────────────
  // 内部方法
  // ─────────────────────────────────────────────────────────────

  /**
   * 重建到指定游标位置 — 从头执行前 N 帧
   * 纯函数重建，保证 deterministic
   */
  private rebuildToCursor(targetCursor: number): void {
    const target = Math.max(0, Math.min(targetCursor, this.state.total_frames));
    let currentState = createInitialState();
    const executedIds = new Set<string>();

    for (let i = 0; i < target; i++) {
      const frame = this.state.frames[i];
      if (!frame) break;

      // 因果顺序验证
      if (frame.event.causal.parent_event_id && !executedIds.has(frame.event.causal.parent_event_id)) {
        this.updateState({
          status: "error",
          cursor: i,
          current_state: currentState,
          executed_event_ids: executedIds,
          last_error: `Causal order violation at frame ${i}: parent ${frame.event.causal.parent_event_id} not executed`,
        });
        return;
      }

      currentState = applyEvent(currentState, frame.event);
      executedIds.add(frame.event.event_id);
    }

    this.updateState({
      cursor: target,
      current_state: currentState,
      executed_event_ids: executedIds,
      last_error: null,
    });
  }

  /**
   * 按因果顺序排序事件（拓扑序）
   * parent 必须在 child 之前
   */
  private sortByCausalOrder(events: SystemEvent[]): SystemEvent[] {
    const eventMap = new Map<string, SystemEvent>();
    for (const e of events) eventMap.set(e.event_id, e);

    const sorted: SystemEvent[] = [];
    const visited = new Set<string>();
    const visiting = new Set<string>(); // 防环

    const visit = (event: SystemEvent) => {
      if (visited.has(event.event_id)) return;
      if (visiting.has(event.event_id)) return; // 环检测
      visiting.add(event.event_id);

      // 先访问所有父事件（主父 + 多父）
      if (event.causal.parent_event_id) {
        const parent = eventMap.get(event.causal.parent_event_id);
        if (parent) visit(parent);
      }
      if (event.causal.causal_links) {
        for (const link of event.causal.causal_links) {
          const parent = eventMap.get(link.from);
          if (parent && !visited.has(parent.event_id)) {
            visit(parent);
          }
        }
      }

      visiting.delete(event.event_id);
      visited.add(event.event_id);
      sorted.push(event);
    };

    for (const event of events) {
      visit(event);
    }

    return sorted;
  }

  private updateState(patch: Partial<ExecutionState>): void {
    this.state = { ...this.state, ...patch };
    this.notify();
  }

  private notify(): void {
    for (const listener of this.listeners) {
      try {
        listener(this.state);
      } catch (err) {
        console.error("[ReplayCursor] listener error:", err);
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const replayCursor = new ReplayCursor();
