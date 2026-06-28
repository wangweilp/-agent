/**
 * 知维 OS Execution Router — 路由控制器（v6 核心）
 * Zhiwei OS Execution Router (v6 严格版)
 *
 * 严格按用户提示词：
 *   class ExecutionRouter {
 *     route(decision: DecisionNode): void {
 *       if (decision.blocks?.length) {
 *         Blocker.apply(decision.blocks);
 *       }
 *       for (const target of decision.triggers ?? []) {
 *         EventBus.emit({
 *           type: target,
 *           causal_decision_id: decision.decision_id,
 *         });
 *       }
 *     }
 *   }
 *
 * v6 核心：Decision controls execution
 *   Event routing depends on decision
 *
 * ❗强约束：不依赖 observability layer / graph / explanation / WHY
 */

import type { DecisionNode } from "./types";
import type { SystemEvent } from "@/types/event-bus";
import { causalKernel } from "@/lib/event-bus/causal-kernel";

// ═══════════════════════════════════════════════════════════════
// Blocker — 阻断器（内部辅助）
// ═══════════════════════════════════════════════════════════════

/**
 * Blocker — 执行路径阻断器
 *
 * 职责：管理被阻断的 execution paths（per trace）
 *
 * 当 decision COMMITTED 且包含 blocks 时：
 *   Blocker.apply(blocks) → 将 paths 加入阻断列表
 * 后续 event 匹配 blocked paths 时被阻断
 */
export class Blocker {
  /** trace_id → blocked paths 集合 */
  private blockedPaths: Map<string, Set<string>> = new Map();

  /**
   * 应用阻断（将 paths 加入阻断列表）
   *
   * @param trace_id 关联的 trace_id
   * @param paths 待阻断的 paths 列表
   */
  apply(trace_id: string, paths: string[]): void {
    if (paths.length === 0) return;

    let set = this.blockedPaths.get(trace_id);
    if (!set) {
      set = new Set();
      this.blockedPaths.set(trace_id, set);
    }
    for (const path of paths) {
      set.add(path);
    }
  }

  /**
   * 检查 path 是否被阻断
   *
   * @param trace_id 关联的 trace_id
   * @param path 待检查的 path
   * @returns 是否被阻断
   */
  isBlocked(trace_id: string, path: string): boolean {
    const set = this.blockedPaths.get(trace_id);
    return set?.has(path) ?? false;
  }

  /**
   * 检查 event 是否被阻断（基于 event.type）
   *
   * @param trace_id 关联的 trace_id
   * @param event 待检查的事件
   * @returns 是否被阻断
   */
  isEventBlocked(trace_id: string, event: SystemEvent): boolean {
    return this.isBlocked(trace_id, event.type);
  }

  /**
   * 解除阻断
   *
   * @param trace_id 关联的 trace_id
   * @param paths 待解除的 paths（如不传，解除所有）
   */
  unblock(trace_id: string, paths?: string[]): void {
    if (!paths) {
      this.blockedPaths.delete(trace_id);
      return;
    }
    const set = this.blockedPaths.get(trace_id);
    if (!set) return;
    for (const path of paths) {
      set.delete(path);
    }
  }

  /**
   * 获取阻断的 paths 列表
   */
  getBlocked(trace_id: string): string[] {
    const set = this.blockedPaths.get(trace_id);
    return set ? Array.from(set) : [];
  }

  /**
   * 清空所有阻断（用于测试）
   */
  clear(): void {
    this.blockedPaths.clear();
  }
}

// ═══════════════════════════════════════════════════════════════
// ExecutionRouter — 路由控制器（v6 核心）
// ═══════════════════════════════════════════════════════════════

/**
 * ExecutionRouter — v6 核心路由控制器
 *
 * 严格按用户提示词实现 route(decision)：
 *   1. 如果 decision.blocks 存在 → Blocker.apply(blocks)
 *   2. 遍历 decision.triggers → EventBus.emit({ type, causal_decision_id })
 *
 * v6 本质：Decision controls execution
 *   Event routing depends on decision
 */
export class ExecutionRouter {
  /** 阻断器 */
  private blocker: Blocker;

  constructor(blocker?: Blocker) {
    this.blocker = blocker ?? new Blocker();
  }

  /**
   * 路由决策（核心 API，严格按用户提示词）
   *
   * @param decision 已 COMMITTED 的决策
   * @returns void
   *
   * 副作用：
   * - 如果 decision.blocks 存在 → Blocker.apply(blocks)
   * - 遍历 decision.triggers → EventBus.emit({ type, causal_decision_id })
   */
  route(decision: DecisionNode): void {
    // 1. 应用阻断
    if (decision.blocks?.length) {
      this.blocker.apply(decision.trace_id, decision.blocks);
    }

    // 2. 触发 routing targets
    if (decision.triggers?.length) {
      for (const target of decision.triggers) {
        this.emitTriggeredEvent(target, decision);
      }
    }
  }

  /**
   * 检查 event 是否被阻断
   *
   * @param trace_id 关联的 trace_id
   * @param event 待检查的事件
   * @returns 是否被阻断
   */
  isBlocked(trace_id: string, event: SystemEvent): boolean {
    return this.blocker.isEventBlocked(trace_id, event);
  }

  /**
   * 获取阻断的 paths 列表
   */
  getBlocked(trace_id: string): string[] {
    return this.blocker.getBlocked(trace_id);
  }

  /**
   * 获取阻断器（用于外部操作）
   */
  getBlocker(): Blocker {
    return this.blocker;
  }

  /**
   * 解除阻断
   */
  unblock(trace_id: string, paths?: string[]): void {
    this.blocker.unblock(trace_id, paths);
  }

  /**
   * 清空所有状态（用于测试）
   */
  clear(): void {
    this.blocker.clear();
  }

  // ═══════════════════════════════════════════════════════════════
  // 内部辅助方法
  // ═══════════════════════════════════════════════════════════════

  /**
   * emit 触发的事件
   *
   * 严格按用户提示词：
   *   EventBus.emit({
   *     type: target,
   *     causal_decision_id: decision.decision_id,
   *   });
   *
   * 通过 causalKernel.publish() emit 事件
   * causal_decision_id 记录在 event.causal.parent_event_id（作为 causal link）
   */
  private emitTriggeredEvent(target: string, decision: DecisionNode): void {
    try {
      // 构造触发事件（使用类型断言，因为 target 是 runtime 动态字符串）
      const event = {
        event_id: this.generateEventId(),
        trace_id: decision.trace_id,
        type: target,
        timestamp: new Date().toISOString(),
        source: "runtime",
        severity: "info" as const,
        payload: {
          causal_decision_id: decision.decision_id,
          triggered_by: decision.decision_id,
          action: decision.actions.join(","),
        },
        causal: {
          parent_event_id: decision.input_event.event_id,
          cause_type: "system_event" as const,
          causal_links: [],
        },
      } as unknown as SystemEvent;

      causalKernel.publish(event);
    } catch (err) {
      console.warn(`[ExecutionRouter] emit triggered event failed:`, err);
    }
  }

  /**
   * 生成事件 ID
   */
  private generateEventId(): string {
    return `evt-triggered-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const executionRouter = new ExecutionRouter();
export const blocker = executionRouter.getBlocker();
