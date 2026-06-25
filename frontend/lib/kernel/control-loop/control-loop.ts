/**
 * 知维 OS Kernel Control Loop — 核心统一控制循环
 * Zhiwei OS Kernel Control Loop — Unified OS Control Loop
 *
 * v6 核心跃迁：从外挂式系统升级为内核级统一控制循环
 *
 * 统一循环：
 * OBSERVE → DECIDE → ENFORCE → RECONCILE → HEAL → COMPACT → REPLAY_VERIFY → OBSERVE
 *
 * 强制规则：
 * Rule 1 — Self-healing cannot be external module（内嵌进 control loop）
 * Rule 2 — Enforcement cannot be separate kernel（是 loop stage）
 * Rule 3 — Authority is not validator only（参与 DECIDE 阶段）
 * Rule 4 — Snapshot is loop optimization only（不作 recovery primary source）
 *
 * 架构升级（v5 → v6）：
 * v5: SelfHealingKernel + EnforcementKernel + Authority Layer（分离）
 * v6: OSControlLoop（唯一 runtime kernel，统一所有 stage）
 */

import { causalKernel } from "@/lib/event-bus/causal-kernel";
import { persistencePipeline } from "@/lib/persistence/pipeline";
import { consistencyValidator } from "@/lib/authority/consistency-validator";
import { enforcementLoop } from "@/lib/enforcement/loop";
import { eventGateSystem } from "@/lib/enforcement/event-gate";
import { policyEngine } from "@/lib/enforcement/policy-engine";
import { crashDetector } from "@/lib/self-healing/crash-detector";
import { autoRecoveryEngine } from "@/lib/self-healing/recovery-engine";
import { consistencyAutoHealer } from "@/lib/self-healing/auto-healer";
import { snapshotCompactor } from "@/lib/self-healing/snapshot-compactor";
import { applyEvent } from "@/lib/replay/state-reducer";
import { createInitialState, type SystemState } from "@/lib/replay/types";
import { adaptiveScheduler } from "@/lib/kernel/control-loop/scheduler";
import { stabilizer } from "@/lib/kernel/control-loop/stabilizer";
import { loopMemory } from "@/lib/kernel/control-loop/loop-memory";
import type { SystemEvent } from "@/types/event-bus";
import type {
  ControlState,
  ControlMode,
  LoopCycle,
  ObserveResult,
  DecisionResult,
  EnforcementStageResult,
  ReconcileResult,
  HealingStageResult,
  CompactionStageResult,
  ReplayVerifyResult,
  StateDelta,
} from "@/lib/kernel/control-loop/types";

// ═══════════════════════════════════════════════════════════════
// OSControlLoop — 核心统一控制循环
// ═══════════════════════════════════════════════════════════════

type ControlLoopListener = (state: ControlState) => void;

export class OSControlLoop {
  /** 全局控制状态 */
  private state: ControlState = {
    mode: "NORMAL",
    last_cycle: 0,
    drift_score: 0,
    health_score: 100,
    enforcement_pressure: 50,
    current_interval_ms: 5000,
    running: false,
    last_cycle_at: null,
    last_error: null,
  };

  private listeners: Set<ControlLoopListener> = new Set();
  /** 待处理的事件队列（ENFORCE 阶段消费） */
  private pendingEvents: Map<string, SystemEvent[]> = new Map();

  // ═══════════════════════════════════════════════════════════════
  // 公共 API
  // ═══════════════════════════════════════════════════════════════

  /**
   * 获取控制状态
   */
  getState(): ControlState {
    return { ...this.state };
  }

  /**
   * 订阅状态变化
   */
  subscribe(listener: ControlLoopListener): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => { this.listeners.delete(listener); };
  }

  /**
   * 提交事件到待处理队列（供 ENFORCE 阶段消费）
   */
  submitEvent(trace_id: string, event: SystemEvent): void {
    const queue = this.pendingEvents.get(trace_id) || [];
    queue.push(event);
    this.pendingEvents.set(trace_id, queue);
  }

  // ─────────────────────────────────────────────────────────────
  // 循环阶段实现
  // ─────────────────────────────────────────────────────────────

  /**
   * 阶段 1：OBSERVE — 观察系统当前状态
   *
   * 从 EventStore / SnapshotStore / CausalKernel 收集当前状态
   * 检测崩溃、漂移、缺口
   */
  async observe(trace_id: string): Promise<ObserveResult> {
    const start = Date.now();

    // 获取事件
    const events = await this.getEvents(trace_id);

    // 获取 snapshot 列表
    const snapshots = await persistencePipeline.listSnapshots(trace_id);

    // 检测崩溃
    const crashes = await crashDetector.detectAll(trace_id);

    // 重建当前状态
    const currentState = this.rebuildFromEvents(events);

    // 一致性验证
    const latestSnapshot = snapshots[snapshots.length - 1] ?? null;
    const consistency = consistencyValidator.validate(
      trace_id,
      currentState,
      events,
      latestSnapshot,
      null,
      events.length,
    );

    return {
      trace_id,
      event_count: events.length,
      snapshot_count: snapshots.length,
      crashes,
      consistency,
      current_state: currentState,
      observed_at: new Date().toISOString(),
      duration_ms: Date.now() - start,
    };
  }

  /**
   * 阶段 2：DECIDE — 决策（Rule 3: Authority 必须参与）
   *
   * 基于 OBSERVE 结果决定后续操作
   */
  decide(observeResult: ObserveResult): DecisionResult {
    const start = Date.now();

    let needsEnforcement = false;
    let needsHealing = false;
    let needsCompaction = false;
    let suggestedMode: ControlMode = "NORMAL";
    let suggestedPressure = this.state.enforcement_pressure;
    const reasons: string[] = [];

    // Authority 参与 DECIDE（Rule 3）
    const consistencyPassed = observeResult.consistency?.passed ?? true;
    const inconsistencyCount = observeResult.consistency?.stats.failed_checks ?? 0;

    // 决策逻辑
    if (observeResult.crashes.length > 0) {
      needsHealing = true;
      const criticalCount = observeResult.crashes.filter((c) => c.severity === "critical").length;
      if (criticalCount > 0) {
        suggestedMode = "LOCKED";
        suggestedPressure = 100;
        reasons.push(`${criticalCount} critical crashes detected`);
      } else {
        suggestedMode = "HEALING";
        suggestedPressure = 80;
        reasons.push(`${observeResult.crashes.length} crashes detected, triggering healing`);
      }
    }

    if (!consistencyPassed) {
      needsHealing = true;
      if (suggestedMode === "NORMAL") {
        suggestedMode = "DEGRADED";
        suggestedPressure = 70;
      }
      reasons.push(`Consistency validation failed: ${inconsistencyCount} inconsistencies`);
    }

    // 待处理事件 → 需要 enforcement
    const pendingCount = this.pendingEvents.get(observeResult.trace_id)?.length ?? 0;
    if (pendingCount > 0) {
      needsEnforcement = true;
      reasons.push(`${pendingCount} pending events to enforce`);
    }

    // snapshot 过多 → 需要 compaction
    if (observeResult.snapshot_count > 10) {
      needsCompaction = true;
      reasons.push(`${observeResult.snapshot_count} snapshots, compaction needed`);
    }

    // drift 评估
    const driftScore = this.computeDriftScore(observeResult);
    if (driftScore > 50) {
      if (suggestedMode === "NORMAL") {
        suggestedMode = "DEGRADED";
      }
      reasons.push(`High drift score: ${driftScore}`);
    }

    return {
      trace_id: observeResult.trace_id,
      needs_enforcement: needsEnforcement,
      needs_healing: needsHealing,
      needs_compaction: needsCompaction,
      suggested_mode: suggestedMode,
      suggested_pressure: suggestedPressure,
      reason: reasons.length > 0 ? reasons.join("; ") : "System healthy",
      authority_decision: {
        consistency_passed: consistencyPassed,
        inconsistency_count: inconsistencyCount,
        authority_level: "L1",
      },
      decided_at: new Date().toISOString(),
      duration_ms: Date.now() - start,
    };
  }

  /**
   * 阶段 3：ENFORCE — 执行（Rule 2: Enforcement 是 loop stage）
   *
   * 处理待处理事件，应用 policy
   */
  async enforce(trace_id: string): Promise<EnforcementStageResult> {
    const start = Date.now();

    const pending = this.pendingEvents.get(trace_id) || [];
    let allowed = 0;
    let blocked = 0;
    let modified = 0;
    let lastGateResult = null;

    for (const event of pending) {
      // 通过 enforcement loop 处理（Rule 2: 是 loop stage，不是独立 kernel）
      const record = enforcementLoop.enforce(event);

      if (record.final_decision === "ALLOW") {
        allowed++;
      } else if (record.final_decision === "BLOCK") {
        blocked++;
      } else if (record.final_decision === "MODIFY") {
        modified++;
      }

      lastGateResult = record.enforcement?.gate_result ?? null;
    }

    // 清空已处理事件
    this.pendingEvents.delete(trace_id);

    return {
      events_processed: pending.length,
      events_allowed: allowed,
      events_blocked: blocked,
      events_modified: modified,
      last_gate_result: lastGateResult,
      enforced_at: new Date().toISOString(),
      duration_ms: Date.now() - start,
    };
  }

  /**
   * 阶段 4：RECONCILE — 对账
   *
   * 确认 enforcement 后的状态与 Authority Layer 一致
   */
  async reconcile(trace_id: string): Promise<ReconcileResult> {
    const start = Date.now();

    const events = await this.getEvents(trace_id);
    const state = this.rebuildFromEvents(events);
    const snapshot = await persistencePipeline.getLatestSnapshot(trace_id);

    const consistency = consistencyValidator.validate(
      trace_id, state, events, snapshot, null, events.length,
    );

    return {
      trace_id,
      consistent: consistency.passed,
      inconsistency_count: consistency.stats.failed_checks,
      authority_level: "L1",
      reconciled_at: new Date().toISOString(),
      duration_ms: Date.now() - start,
    };
  }

  /**
   * 阶段 5：HEAL — 修复（Rule 1: Self-healing 内嵌进 control loop）
   *
   * 如检测到不一致，触发修复
   */
  async heal(trace_id: string, needsHealing: boolean): Promise<HealingStageResult> {
    const start = Date.now();

    if (!needsHealing) {
      return {
        trace_id,
        healed: false,
        recovery_strategy: null,
        recovery: null,
        consistent_after: true,
        healed_at: new Date().toISOString(),
        duration_ms: Date.now() - start,
      };
    }

    // 检测 infinite healing loop
    if (loopMemory.detectInfiniteHealingLoop(5)) {
      return {
        trace_id,
        healed: false,
        recovery_strategy: null,
        recovery: null,
        consistent_after: false,
        healed_at: new Date().toISOString(),
        duration_ms: Date.now() - start,
      };
    }

    // 执行修复（Rule 1: 内嵌进 loop，不是外挂）
    const healResult = await consistencyAutoHealer.heal(trace_id);

    return {
      trace_id,
      healed: healResult.final_status === "consistent",
      recovery_strategy: healResult.attempts[0]?.strategy ?? null,
      recovery: healResult.attempts[0]?.recovery ?? null,
      consistent_after: healResult.final_status === "consistent",
      healed_at: new Date().toISOString(),
      duration_ms: Date.now() - start,
    };
  }

  /**
   * 阶段 6：COMPACT — 压缩（Rule 4: Snapshot 是 loop optimization only）
   */
  async compact(trace_id: string, needsCompaction: boolean): Promise<CompactionStageResult> {
    const start = Date.now();

    if (!needsCompaction) {
      return {
        trace_id,
        compacted: false,
        before_count: 0,
        after_count: 0,
        result: null,
        compacted_at: new Date().toISOString(),
        duration_ms: Date.now() - start,
      };
    }

    const result = await snapshotCompactor.compact(trace_id, "MERGE_RANGE");

    return {
      trace_id,
      compacted: result.success,
      before_count: result.before_count,
      after_count: result.after_count,
      result,
      compacted_at: new Date().toISOString(),
      duration_ms: Date.now() - start,
    };
  }

  /**
   * 阶段 7：REPLAY_VERIFY — 回放验证
   *
   * 确保确定性：从事件重建状态，验证与当前状态一致
   */
  async verify(trace_id: string): Promise<ReplayVerifyResult> {
    const start = Date.now();

    const events = await this.getEvents(trace_id);
    const state = this.rebuildFromEvents(events);

    return {
      trace_id,
      verified: state.version === events.length,
      replayed_events: events.length,
      state_version: state.version,
      verified_at: new Date().toISOString(),
      duration_ms: Date.now() - start,
    };
  }

  // ═══════════════════════════════════════════════════════════════
  // 完整循环执行
  // ═══════════════════════════════════════════════════════════════

  /**
   * 执行一次完整循环
   * OBSERVE → DECIDE → ENFORCE → RECONCILE → HEAL → COMPACT → REPLAY_VERIFY
   */
  async runCycle(trace_id: string): Promise<LoopCycle> {
    const startTime = Date.now();
    const startedAt = new Date().toISOString();
    const cycleNumber = this.state.last_cycle + 1;
    const driftScoreBefore = this.state.drift_score;
    const modeBefore = this.state.mode;

    try {
      // 1. OBSERVE
      const observeResult = await this.observe(trace_id);

      // 2. DECIDE
      const decision = this.decide(observeResult);

      // 3. ENFORCE
      const enforcementResult = await this.enforce(trace_id);

      // 4. RECONCILE
      const reconcileResult = await this.reconcile(trace_id);

      // 5. HEAL
      const healingResult = await this.heal(trace_id, decision.needs_healing);

      // 6. COMPACT
      const compactionResult = await this.compact(trace_id, decision.needs_compaction);

      // 7. REPLAY_VERIFY
      const replayVerifyResult = await this.verify(trace_id);

      // 更新控制状态
      const driftScoreAfter = this.computeDriftScore(observeResult);
      const modeAfter = decision.suggested_mode;
      const healthScore = 100 - driftScoreAfter;

      const stateDelta: StateDelta = {
        drift_delta: driftScoreAfter - driftScoreBefore,
        health_delta: healthScore - this.state.health_score,
        pressure_delta: decision.suggested_pressure - this.state.enforcement_pressure,
        mode_changed: modeAfter !== modeBefore,
        previous_mode: modeBefore,
        new_mode: modeAfter,
      };

      this.state = {
        ...this.state,
        mode: modeAfter,
        last_cycle: cycleNumber,
        drift_score: driftScoreAfter,
        health_score: healthScore,
        enforcement_pressure: decision.suggested_pressure,
        last_cycle_at: startedAt,
        last_error: null,
      };

      // 自适应调度
      const nextInterval = adaptiveScheduler.computeNextInterval(driftScoreAfter, healthScore);
      this.state.current_interval_ms = nextInterval;

      const cycle: LoopCycle = {
        cycle_number: cycleNumber,
        trace_id,
        started_at: startedAt,
        ended_at: new Date().toISOString(),
        total_duration_ms: Date.now() - startTime,
        observe_result: observeResult,
        decision,
        enforcement_result: enforcementResult,
        reconcile_result: reconcileResult,
        healing_result: healingResult,
        compaction_result: compactionResult,
        replay_verify_result: replayVerifyResult,
        state_delta: stateDelta,
        drift_score_before: driftScoreBefore,
        drift_score_after: driftScoreAfter,
        success: true,
        error: null,
      };

      // 记录到循环内存
      loopMemory.record(cycle);

      // 通知监听器
      this.notifyListeners();

      return cycle;
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      this.state.last_error = errorMsg;
      this.state.last_cycle = cycleNumber;
      this.state.last_cycle_at = startedAt;

      const cycle: LoopCycle = {
        cycle_number: cycleNumber,
        trace_id,
        started_at: startedAt,
        ended_at: new Date().toISOString(),
        total_duration_ms: Date.now() - startTime,
        observe_result: {
          trace_id,
          event_count: 0,
          snapshot_count: 0,
          crashes: [],
          consistency: null,
          current_state: null,
          observed_at: startedAt,
          duration_ms: 0,
        },
        decision: {
          trace_id,
          needs_enforcement: false,
          needs_healing: false,
          needs_compaction: false,
          suggested_mode: "LOCKED",
          suggested_pressure: 100,
          reason: `Cycle failed: ${errorMsg}`,
          authority_decision: { consistency_passed: false, inconsistency_count: 0, authority_level: "L1" },
          decided_at: startedAt,
          duration_ms: 0,
        },
        enforcement_result: null,
        reconcile_result: null,
        healing_result: null,
        compaction_result: null,
        replay_verify_result: null,
        state_delta: {
          drift_delta: 0,
          health_delta: 0,
          pressure_delta: 0,
          mode_changed: modeBefore !== "LOCKED",
          previous_mode: modeBefore,
          new_mode: "LOCKED",
        },
        drift_score_before: driftScoreBefore,
        drift_score_after: 100,
        success: false,
        error: errorMsg,
      };

      loopMemory.record(cycle);
      this.notifyListeners();

      return cycle;
    }
  }

  /**
   * 启动控制循环（continuous loop，自适应间隔）
   */
  startControlLoop(intervalMs: number = 5000): void {
    if (this.state.running) {
      console.warn("[OSControlLoop] already running");
      return;
    }

    this.state.running = true;
    this.state.current_interval_ms = intervalMs;
    this.notifyListeners();

    adaptiveScheduler.start(
      async () => {
        const traceIds = await persistencePipeline.getAllTraceIds();
        for (const traceId of traceIds) {
          await this.runCycle(traceId);
        }
        // 自适应重新调度
        adaptiveScheduler.reschedule(this.state);
      },
      this.state,
    );
  }

  /**
   * 停止控制循环
   */
  stopControlLoop(): void {
    adaptiveScheduler.stop();
    this.state.running = false;
    this.notifyListeners();
  }

  /**
   * 稳定化系统 — 触发自稳定
   */
  async stabilizeSystem(trace_id: string): Promise<import("@/lib/kernel/control-loop/types").StabilizationResult> {
    return stabilizer.stabilizeSystem(
      trace_id,
      this.state.mode,
      this.state.drift_score,
      this.state.health_score,
      this.state.enforcement_pressure,
    );
  }

  /**
   * 获取循环历史
   */
  getHistory(): import("@/lib/kernel/control-loop/types").ControlLoopHistory {
    return loopMemory.getHistory();
  }

  /**
   * 获取最近循环
   */
  getRecentCycles(n: number): LoopCycle[] {
    return loopMemory.getRecentCycles(n);
  }

  // ═══════════════════════════════════════════════════════════════
  // 内部方法
  // ═══════════════════════════════════════════════════════════════

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
   * 计算 drift score（0-100）
   *
   * 基于：
   * - 崩溃数
   * - 不一致数
   * - 待处理事件数
   */
  private computeDriftScore(observeResult: ObserveResult): number {
    let score = 0;

    // 崩溃数（每个 +20）
    score += observeResult.crashes.length * 20;

    // 不一致数（每个 +5）
    const inconsistencyCount = observeResult.consistency?.stats.failed_checks ?? 0;
    score += inconsistencyCount * 5;

    // 待处理事件数（每个 +1）
    const pendingCount = this.pendingEvents.get(observeResult.trace_id)?.length ?? 0;
    score += pendingCount;

    return Math.min(100, score);
  }

  private notifyListeners(): void {
    for (const listener of this.listeners) {
      try {
        listener(this.state);
      } catch (err) {
        console.error("[OSControlLoop] listener error:", err);
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出 — 唯一的 runtime kernel
// ═══════════════════════════════════════════════════════════════

export const osControlLoop = new OSControlLoop();
