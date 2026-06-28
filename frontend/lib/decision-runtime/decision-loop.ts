/**
 * 知维 OS Decision Runtime Loop — 运行时决策循环（v6.1 严格版）
 * Zhiwei OS Decision Runtime Loop (v6.1)
 *
 * ═══════════════════════════════════════════════════════════════
 * OS INVARIANT (v6.1):
 *
 *   DecisionRuntimeLoop = ORCHESTRATOR ONLY
 *
 *   组合调用三个独立模块（不混合职责）：
 *     - DecisionEngine       → CONTROL FLOW（commit/reject/override）
 *     - DecisionPolicyKernel → SCORING（在 Engine 内部调用）
 *     - ExecutionRouter      → ROUTING（route + Blocker）
 *     - DecisionFeedbackLoop → WEIGHTS UPDATE（adjust PolicyWeights）
 *
 *   Loop 自身不实现任何 control / scoring / routing / weights 逻辑
 * ═══════════════════════════════════════════════════════════════
 *
 * 严格按用户提示词：
 *   🔁 核心执行循环：
 *   Event → Decision Engine → DecisionNode → Commit → Route → Next Event
 *
 *   runtime loop:
 *   while (true) {
 *     const event = EventBus.next();
 *     const decision = DecisionEngine.evaluate(event, context);
 *     if (decision.state === "REJECTED") continue;
 *     if (decision.state === "COMMITTED") {
 *       ExecutionRouter.route(decision);
 *       EventBus.emit(decision.triggers);
 *     }
 *   }
 *
 * v6 核心机制：
 *   1. Decision controls execution（Event routing depends on decision）
 *   2. Decision-to-Decision 自引用（meta decision 生成）
 *      if (previousDecision.confidence < 0.5) {
 *        generateMetaDecision(previousDecision);
 *      }
 *
 * v6.1 边界固化：
 *   - Engine.evaluate() 内部已拆分 STEP 1 (DPC scoring) + STEP 2 (control)
 *   - FeedbackLoop.update() 只修改 weights，不触碰 Engine/Router
 *   - Loop 是 orchestrator，不混合 control / scoring / routing / weights
 *
 * ❗强约束：不依赖 observability layer / graph / explanation / WHY
 */

import type {
  DecisionNode,
  RuntimeContext,
  AuthorityContext,
  ExecutionResult,
  DecisionEngineOptions,
} from "./types";
import type { SystemEvent } from "@/types/event-bus";
import { DecisionEngine } from "./decision-engine";
import { ExecutionRouter } from "./execution-router";
import { DecisionFeedbackLoop } from "./decision-feedback";

// ═══════════════════════════════════════════════════════════════
// EventQueue — 事件队列（内部辅助）
// ═══════════════════════════════════════════════════════════════

/**
 * EventQueue — 事件队列
 *
 * 用于实现 while(true) loop 的 EventBus.next() 语义
 *
 * 支持：
 * - push(event): 入队
 * - next(): 出队（阻塞语义，无事件时返回 null）
 * - isEmpty(): 判空
 */
export class EventQueue {
  private queue: SystemEvent[] = [];

  push(event: SystemEvent): void {
    this.queue.push(event);
  }

  pushBatch(events: SystemEvent[]): void {
    for (const event of events) {
      this.queue.push(event);
    }
  }

  next(): SystemEvent | null {
    return this.queue.shift() ?? null;
  }

  isEmpty(): boolean {
    return this.queue.length === 0;
  }

  size(): number {
    return this.queue.length;
  }

  clear(): void {
    this.queue = [];
  }
}

// ═══════════════════════════════════════════════════════════════
// DecisionRuntimeLoop — v6 核心 runtime loop
// ═══════════════════════════════════════════════════════════════

/**
 * DecisionRuntimeLoop — v6 核心 runtime loop
 *
 * 严格按用户提示词实现 while(true) loop：
 *
 *   while (true) {
 *     const event = EventBus.next();
 *     const decision = DecisionEngine.evaluate(event, context);
 *     if (decision.state === "REJECTED") continue;
 *     if (decision.state === "COMMITTED") {
 *       ExecutionRouter.route(decision);
 *       EventBus.emit(decision.triggers);
 *     }
 *   }
 *
 * 额外实现：
 *   1. Meta Decision 生成（confidence < threshold 时）
 *   2. Decision Feedback Loop（决策执行后更新 PolicyWeights）
 */
export class DecisionRuntimeLoop {
  private engine: DecisionEngine;
  private router: ExecutionRouter;
  private feedbackLoop: DecisionFeedbackLoop;
  private eventQueue: EventQueue;
  /** 是否正在运行 */
  private running: boolean = false;
  /** 最大迭代次数（防止无限循环） */
  private maxIterations: number;
  /** meta decision 触发阈值 */
  private metaDecisionThreshold: number;
  /** 是否启用 meta decision */
  private enableMetaDecision: boolean;
  /** 执行结果回调（用于外部观察） */
  private onDecisionCommitted?: (decision: DecisionNode) => void;
  private onDecisionRejected?: (decision: DecisionNode) => void;
  private onMetaDecisionGenerated?: (meta: DecisionNode, original: DecisionNode) => void;

  constructor(options?: {
    engine?: DecisionEngine;
    router?: ExecutionRouter;
    feedbackLoop?: DecisionFeedbackLoop;
    maxIterations?: number;
    metaDecisionThreshold?: number;
    enableMetaDecision?: boolean;
  }) {
    this.engine = options?.engine ?? new DecisionEngine();
    this.router = options?.router ?? new ExecutionRouter();
    this.feedbackLoop = options?.feedbackLoop ?? new DecisionFeedbackLoop();
    this.eventQueue = new EventQueue();
    this.maxIterations = options?.maxIterations ?? 1000;
    this.metaDecisionThreshold = options?.metaDecisionThreshold ?? 0.5;
    this.enableMetaDecision = options?.enableMetaDecision ?? true;
  }

  // ═══════════════════════════════════════════════════════════════
  // 核心 API 1：enqueue — 入队事件
  // ═══════════════════════════════════════════════════════════════

  /**
   * 入队事件
   *
   * @param event 待处理的事件
   */
  enqueue(event: SystemEvent): void {
    this.eventQueue.push(event);
  }

  /**
   * 批量入队
   */
  enqueueBatch(events: SystemEvent[]): void {
    this.eventQueue.pushBatch(events);
  }

  // ═══════════════════════════════════════════════════════════════
  // 核心 API 2：run — while(true) 主循环
  // ═══════════════════════════════════════════════════════════════

  /**
   * 运行主循环（严格按用户提示词）
   *
   *   while (true) {
   *     const event = EventBus.next();
   *     const decision = DecisionEngine.evaluate(event, context);
   *     if (decision.state === "REJECTED") continue;
   *     if (decision.state === "COMMITTED") {
   *       ExecutionRouter.route(decision);
   *       EventBus.emit(decision.triggers);
   *     }
   *   }
   *
   * @param context 运行时上下文
   * @param maxIterations 最大迭代次数（默认 this.maxIterations）
   * @returns 处理的决策列表
   */
  run(context: RuntimeContext, maxIterations?: number): DecisionNode[] {
    const max = maxIterations ?? this.maxIterations;
    const results: DecisionNode[] = [];
    this.running = true;

    let iteration = 0;
    while (this.running && iteration < max) {
      // 1. 获取下一个事件（EventBus.next() 语义）
      const event = this.eventQueue.next();
      if (!event) {
        // 队列为空，退出循环
        break;
      }

      iteration++;

      // 2. 检查 event 是否被阻断（基于 router 的 blocked paths）
      if (this.router.isBlocked(event.trace_id, event)) {
        // 被阻断，跳过（continue 语义）
        const blockedDecision = this.createBlockedDecision(event, context);
        results.push(blockedDecision);
        this.onDecisionRejected?.(blockedDecision);
        continue;
      }

      // 3. DecisionEngine.evaluate(event, context)
      const decision = this.engine.evaluate(event, context);

      // 4. if (decision.state === "REJECTED") continue
      if (decision.state === "REJECTED") {
        results.push(decision);
        this.onDecisionRejected?.(decision);
        continue;
      }

      // 5. if (decision.state === "COMMITTED")
      if (decision.state === "COMMITTED") {
        // 5.1 ExecutionRouter.route(decision)
        this.router.route(decision);

        // 5.2 EventBus.emit(decision.triggers) — 由 router 内部完成

        // 5.3 Decision Feedback Loop（自演化）
        this.applyFeedbackLoop(decision);

        // 5.4 Meta Decision 生成（Decision-to-Decision 自引用）
        if (this.enableMetaDecision && decision.confidence < this.metaDecisionThreshold) {
          const meta = this.generateMetaDecision(decision, context);
          if (meta) {
            results.push(meta);
            this.onMetaDecisionGenerated?.(meta, decision);
          }
        }

        results.push(decision);
        this.onDecisionCommitted?.(decision);
      }
    }

    this.running = false;
    return results;
  }

  /**
   * 运行单次（处理一个事件）
   *
   * @param event 待处理的事件
   * @param context 运行时上下文
   * @returns 生成的决策
   */
  runOnce(event: SystemEvent, context: RuntimeContext): DecisionNode {
    // 检查是否被阻断
    if (this.router.isBlocked(event.trace_id, event)) {
      return this.createBlockedDecision(event, context);
    }

    // 评估
    const decision = this.engine.evaluate(event, context);

    if (decision.state === "COMMITTED") {
      // 路由
      this.router.route(decision);

      // Feedback Loop
      this.applyFeedbackLoop(decision);

      // Meta Decision
      if (this.enableMetaDecision && decision.confidence < this.metaDecisionThreshold) {
        this.generateMetaDecision(decision, context);
      }
    }

    return decision;
  }

  // ═══════════════════════════════════════════════════════════════
  // 核心 API 3：stop — 停止循环
  // ═══════════════════════════════════════════════════════════════

  /**
   * 停止循环
   */
  stop(): void {
    this.running = false;
  }

  // ═══════════════════════════════════════════════════════════════
  // 核心 API 4：回调注册
  // ═══════════════════════════════════════════════════════════════

  /**
   * 注册决策提交回调
   */
  onCommitted(callback: (decision: DecisionNode) => void): void {
    this.onDecisionCommitted = callback;
  }

  /**
   * 注册决策拒绝回调
   */
  onRejected(callback: (decision: DecisionNode) => void): void {
    this.onDecisionRejected = callback;
  }

  /**
   * 注册 meta decision 生成回调
   */
  onMetaDecision(callback: (meta: DecisionNode, original: DecisionNode) => void): void {
    this.onMetaDecisionGenerated = callback;
  }

  // ═══════════════════════════════════════════════════════════════
  // 辅助 API
  // ═══════════════════════════════════════════════════════════════

  /**
   * 获取决策引擎
   */
  getEngine(): DecisionEngine {
    return this.engine;
  }

  /**
   * 获取路由控制器
   */
  getRouter(): ExecutionRouter {
    return this.router;
  }

  /**
   * 获取反馈循环
   */
  getFeedbackLoop(): DecisionFeedbackLoop {
    return this.feedbackLoop;
  }

  /**
   * 获取事件队列
   */
  getEventQueue(): EventQueue {
    return this.eventQueue;
  }

  /**
   * 是否正在运行
   */
  isRunning(): boolean {
    return this.running;
  }

  /**
   * 清空所有状态（用于测试）
   */
  clear(): void {
    this.engine.clear();
    this.router.clear();
    this.feedbackLoop.clear();
    this.eventQueue.clear();
    this.running = false;
  }

  // ═══════════════════════════════════════════════════════════════
  // 内部辅助方法
  // ═══════════════════════════════════════════════════════════════

  /**
   * 应用 Feedback Loop（自演化核心）
   *
   * Decision outcome → modifies PolicyWeights → affects future decision scoring
   */
  private applyFeedbackLoop(decision: DecisionNode): void {
    // 构造 ExecutionResult（基于 decision 的执行情况）
    const outcome: ExecutionResult = {
      decision_id: decision.decision_id,
      success: true, // COMMITTED 视为成功
      duration_ms: decision.committed_at
        ? Date.now() - decision.committed_at
        : 0,
      emitted_events: [], // 实际场景中由 router emit 的事件
      metadata: {
        actions: decision.actions,
        confidence: decision.confidence,
      },
    };

    this.feedbackLoop.update(decision, outcome);
  }

  /**
   * 生成 Meta Decision（Decision-to-Decision 自引用）
   *
   * 严格按用户提示词：
   *   if (previousDecision.confidence < 0.5) {
   *     generateMetaDecision(previousDecision);
   *   }
   *
   * Meta Decision 是对原决策的"元决策"：
   * - parent_decision_id 指向原决策
   * - 评估原决策的置信度，可能 escalate 或 override
   *
   * @param original 原决策（confidence 低于阈值）
   * @param context 运行时上下文
   * @returns 生成的 meta decision（如生成失败返回 null）
   */
  private generateMetaDecision(
    original: DecisionNode,
    context: RuntimeContext,
  ): DecisionNode | null {
    try {
      // 通过 engine.evaluate 生成 meta decision
      // 输入事件是原决策的 input_event，但标记为 meta evaluation
      // 使用类型断言，因为 meta event type 是 runtime 动态构造的
      const metaEvent = {
        ...original.input_event,
        event_id: `meta-${original.input_event.event_id}`,
        type: `meta.evaluate.${original.input_event.type}`,
        timestamp: new Date().toISOString(),
        payload: {
          ...((original.input_event.payload as unknown as Record<string, unknown>) ?? {}),
          meta_decision_for: original.decision_id,
          original_confidence: original.confidence,
          meta_reason: `confidence ${original.confidence} < threshold ${this.metaDecisionThreshold}`,
        },
        causal: {
          parent_event_id: original.input_event.event_id,
          cause_type: "system_event" as const,
          causal_links: [],
        },
      } as unknown as SystemEvent;

      const metaDecision = this.engine.evaluate(metaEvent, context);

      // 设置 parent_decision_id（建立 Decision-to-Decision 自引用）
      metaDecision.parent_decision_id = original.decision_id;

      // 在原决策上记录 child_decision_ids
      const originalUpdated = this.engine.getDecision(original.decision_id);
      if (originalUpdated) {
        originalUpdated.child_decision_ids = [
          ...(originalUpdated.child_decision_ids ?? []),
          metaDecision.decision_id,
        ];
      }

      return metaDecision;
    } catch (err) {
      console.warn(`[DecisionRuntimeLoop] generateMetaDecision failed:`, err);
      return null;
    }
  }

  /**
   * 创建被阻断的决策（用于被 router block 的事件）
   */
  private createBlockedDecision(
    event: SystemEvent,
    context: RuntimeContext,
  ): DecisionNode {
    const now = Date.now();
    return {
      decision_id: `dec-blocked-${now}-${Math.random().toString(36).slice(2, 8)}`,
      trace_id: event.trace_id,
      state: "REJECTED",
      input_event: event,
      policy_context: context.authority,
      confidence: 0,
      priority: 0,
      cost: 0,
      actions: ["BLOCK"],
      created_at: now,
      rejection_reason: "blocked by ExecutionRouter (path blocked)",
      source: "execution_router",
    };
  }
}

// ═══════════════════════════════════════════════════════════════
// 工厂函数
// ═══════════════════════════════════════════════════════════════

/**
 * 创建 DecisionRuntimeLoop 实例
 */
export function createDecisionRuntimeLoop(options?: {
  engineOptions?: Partial<DecisionEngineOptions>;
  maxIterations?: number;
  metaDecisionThreshold?: number;
  enableMetaDecision?: boolean;
}): DecisionRuntimeLoop {
  const engine = new DecisionEngine(options?.engineOptions);
  return new DecisionRuntimeLoop({
    engine,
    maxIterations: options?.maxIterations,
    metaDecisionThreshold: options?.metaDecisionThreshold,
    enableMetaDecision: options?.enableMetaDecision,
  });
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const decisionRuntimeLoop = new DecisionRuntimeLoop();
