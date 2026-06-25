/**
 * 知维 OS Consistency Auto-Healer — 一致性自动修复器
 * Zhiwei OS Consistency Auto-Healer
 *
 * 能力：
 * - 自动调用 Authority Layer validator
 * - 如果 detect inconsistency：自动触发 recovery
 * - 自动 rerun validation
 * - 如果失败 → escalate
 *
 * 核心方法：
 * heal(trace_id) → loop until consistent OR max_attempts reached
 *
 * 修复流程：
 * 1. validate（Authority Layer）
 * 2. 如不一致 → recover（AutoRecoveryEngine）
 * 3. rerun validate
 * 4. 如仍不一致 → escalate（升级策略）
 * 5. 循环直到一致或达到 max_attempts
 */

import { consistencyValidator } from "@/lib/authority/consistency-validator";
import { autoRecoveryEngine } from "@/lib/self-healing/recovery-engine";
import { crashDetector } from "@/lib/self-healing/crash-detector";
import { persistencePipeline } from "@/lib/persistence/pipeline";
import { causalKernel } from "@/lib/event-bus/causal-kernel";
import { createInitialState, type SystemState } from "@/lib/replay/types";
import { applyEvent } from "@/lib/replay/state-reducer";
import type { SystemEvent } from "@/types/event-bus";
import type { ConsistencyReport } from "@/lib/authority/types";
import type {
  HealResult,
  HealAttempt,
  HealStatus,
  RecoveryStrategy,
} from "@/lib/self-healing/types";

// ═══════════════════════════════════════════════════════════════
// ConsistencyAutoHealer — 一致性自动修复器
// ═══════════════════════════════════════════════════════════════

export interface AutoHealerConfig {
  /** 最大尝试次数 */
  max_attempts: number;
  /** 默认恢复策略 */
  default_strategy: RecoveryStrategy;
  /** 是否在失败时升级策略 */
  escalate_on_failure: boolean;
}

const DEFAULT_CONFIG: AutoHealerConfig = {
  max_attempts: 3,
  default_strategy: "EVENT_REPLAY",
  escalate_on_failure: true,
};

export class ConsistencyAutoHealer {
  private config: AutoHealerConfig = DEFAULT_CONFIG;

  /**
   * 配置
   */
  configure(config: Partial<AutoHealerConfig>): void {
    this.config = { ...this.config, ...config };
  }

  /**
   * 修复 — 主入口
   * heal(trace_id) → loop until consistent OR max_attempts reached
   */
  async heal(trace_id: string, currentState?: SystemState): Promise<HealResult> {
    const startTime = Date.now();
    const attempts: HealAttempt[] = [];

    let state = currentState ?? await this.getCurrentState(trace_id);
    let strategy = this.config.default_strategy;
    let finalStatus: HealStatus = "consistent";
    let finalConsistency: ConsistencyReport | null = null;

    for (let attempt = 1; attempt <= this.config.max_attempts; attempt++) {
      const attemptStart = Date.now();

      // 1. validate（Authority Layer）
      const events = await this.getEvents(trace_id);
      const snapshot = await persistencePipeline.getLatestSnapshot(trace_id);
      const before = consistencyValidator.validate(
        trace_id, state, events, snapshot, null, events.length,
      );

      // 已一致 → 完成
      if (before.passed) {
        attempts.push({
          attempt,
          before,
          strategy,
          recovery: null,
          after: before,
          consistent: true,
          duration_ms: Date.now() - attemptStart,
        });
        finalConsistency = before;
        finalStatus = "consistent";
        break;
      }

      // 2. 不一致 → recover
      const crashReport = (await crashDetector.detectAll(trace_id, state))[0];
      if (crashReport) {
        strategy = crashReport.suggested_strategy;
      }

      // 升级策略（如配置）
      if (this.config.escalate_on_failure && attempt > 1) {
        strategy = this.escalateStrategy(strategy);
      }

      const recovery = await autoRecoveryEngine.recover(trace_id, strategy, crashReport);

      // 3. rerun validate
      const after = recovery.consistency_after_recovery;

      attempts.push({
        attempt,
        before,
        strategy,
        recovery,
        after,
        consistent: recovery.success && (after?.passed ?? false),
        duration_ms: Date.now() - attemptStart,
      });

      // 更新状态
      if (recovery.success) {
        state = recovery.final_state;
        finalConsistency = after;
      }

      // 已一致 → 完成
      if (recovery.success && after?.passed) {
        finalStatus = "consistent";
        break;
      }

      // 未一致 → 继续尝试
      finalStatus = "healing";
    }

    // 达到 max_attempts 仍未一致 → escalate
    if (finalStatus !== "consistent") {
      finalStatus = attempts[attempts.length - 1]?.consistent ? "consistent" : "escalated";
    }

    return {
      trace_id,
      final_status: finalStatus,
      attempts,
      total_attempts: attempts.length,
      final_consistency: finalConsistency,
      final_state: state,
      total_duration_ms: Date.now() - startTime,
    };
  }

  /**
   * 单次修复（不循环）
   */
  async healOnce(trace_id: string, currentState?: SystemState): Promise<HealAttempt> {
    const startTime = Date.now();
    const state = currentState ?? await this.getCurrentState(trace_id);
    const events = await this.getEvents(trace_id);
    const snapshot = await persistencePipeline.getLatestSnapshot(trace_id);

    const before = consistencyValidator.validate(
      trace_id, state, events, snapshot, null, events.length,
    );

    if (before.passed) {
      return {
        attempt: 1,
        before,
        strategy: this.config.default_strategy,
        recovery: null,
        after: before,
        consistent: true,
        duration_ms: Date.now() - startTime,
      };
    }

    const crashReport = (await crashDetector.detectAll(trace_id, state))[0];
    const strategy = crashReport?.suggested_strategy ?? this.config.default_strategy;
    const recovery = await autoRecoveryEngine.recover(trace_id, strategy, crashReport);

    return {
      attempt: 1,
      before,
      strategy,
      recovery,
      after: recovery.consistency_after_recovery,
      consistent: recovery.success && (recovery.consistency_after_recovery?.passed ?? false),
      duration_ms: Date.now() - startTime,
    };
  }

  // ─────────────────────────────────────────────────────────────
  // 内部方法
  // ─────────────────────────────────────────────────────────────

  /**
   * 升级策略 — 失败时使用更强力的策略
   */
  private escalateStrategy(current: RecoveryStrategy): RecoveryStrategy {
    const escalation: Record<RecoveryStrategy, RecoveryStrategy> = {
      "EVENT_REPLAY": "HYBRID_RECOVERY",
      "SNAPSHOT_ROLLBACK": "EVENT_REPLAY",
      "HYBRID_RECOVERY": "FORCE_REBUILD",
      "FORCE_REBUILD": "FORCE_REBUILD", // 已是最强
    };
    return escalation[current];
  }

  /**
   * 获取当前状态
   */
  private async getCurrentState(trace_id: string): Promise<SystemState> {
    const events = await this.getEvents(trace_id);
    let state = createInitialState();
    for (const event of events) {
      state = applyEvent(state, event);
    }
    return state;
  }

  /**
   * 获取事件
   */
  private async getEvents(trace_id: string): Promise<SystemEvent[]> {
    let events = causalKernel.replay(trace_id);
    if (events.length === 0) {
      events = await persistencePipeline.loadEventsByTraceId(trace_id);
    }
    return events;
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const consistencyAutoHealer = new ConsistencyAutoHealer();
