/**
 * 知维 OS Runtime Truth Enforcement Loop — 强制执行闭环
 * Zhiwei OS Runtime Truth Enforcement Loop
 *
 * 核心闭环：
 * event → validate → enforce → apply → validate → reconcile
 *
 * 闭环职责：
 * 1. validate (pre)    — 事件进入前验证（结构 + 门控）
 * 2. enforce            — 执行门控决策（ALLOW/BLOCK/MODIFY/QUARANTINE）
 * 3. apply              — 应用到 EventStore
 * 4. validate (post)    — 应用后验证（一致性）
 * 5. reconcile          — 对账（与 Authority Layer 协调）
 *
 * 闭环保证：
 * - 任何事件必须经过完整闭环才能进入系统
 * - BLOCK 决策时事件不进入 EventStore
 * - 每个闭环记录完整执行轨迹
 * - 支持事后审计与回放
 */

import { enforcementPipeline } from "@/lib/enforcement/pipeline";
import { eventGateSystem } from "@/lib/enforcement/event-gate";
import { policyEngine } from "@/lib/enforcement/policy-engine";
import type {
  SystemEvent,
} from "@/types/event-bus";
import type {
  EnforcementLoopRecord,
  EnforcementKernelState,
  LoopStatus,
  StageResult,
  GateResult,
} from "@/lib/enforcement/types";

// ═══════════════════════════════════════════════════════════════
// EnforcementLoop — 强制执行闭环
// ═══════════════════════════════════════════════════════════════

let loopCounter = 0;

type LoopListener = (record: EnforcementLoopRecord) => void;

export class EnforcementLoop {
  private state: EnforcementKernelState = {
    enabled: true,
    total_processed: 0,
    total_allowed: 0,
    total_blocked: 0,
    total_modified: 0,
    total_quarantined: 0,
    active_policies: 0,
    active_rules: 0,
    last_enforced_at: null,
    last_error: null,
  };
  private listeners: Set<LoopListener> = new Set();
  /** 闭环执行历史（最近 N 条） */
  private history: EnforcementLoopRecord[] = [];
  private maxHistorySize = 1000;

  /**
   * 执行闭环 — 主入口
   *
   * @param event 待处理事件
   * @returns 闭环执行记录
   */
  enforce(event: SystemEvent): EnforcementLoopRecord {
    const startTime = Date.now();
    loopCounter++;
    const loopId = `loop_${Date.now()}_${loopCounter}`;

    // 通过 pipeline 执行（包含所有阶段）
    const pipelineResult = enforcementPipeline.execute(event);

    // 构建各阶段结果
    const stages = pipelineResult.stages;
    const preValidation = this.findStage(stages, "pre_validate");
    const enforcement = this.findStage(stages, "gate");
    const application = this.findStage(stages, "apply");
    const postValidation = this.findStage(stages, "post_validate");
    const reconciliation = this.findStage(stages, "reconcile");

    // 确定闭环状态
    const status = this.determineStatus(pipelineResult.final_decision, pipelineResult.applied);

    // 构建对账结果
    const reconciliationResult = this.buildReconciliationResult(pipelineResult.final_decision, pipelineResult.applied);

    const record: EnforcementLoopRecord = {
      loop_id: loopId,
      event: pipelineResult.final_event ?? event,
      status,
      pre_validation: preValidation,
      enforcement: enforcement,
      application: application,
      post_validation: postValidation,
      reconciliation: reconciliation,
      final_decision: pipelineResult.final_decision,
      success: pipelineResult.applied,
      reconciliation_result: reconciliationResult,
      executed_at: new Date().toISOString(),
      total_duration_ms: Date.now() - startTime,
    };

    // 更新统计
    this.updateStats(pipelineResult.final_decision, pipelineResult.applied);

    // 记录历史
    this.history.push(record);
    if (this.history.length > this.maxHistorySize) {
      this.history.shift();
    }

    // 通知监听器
    this.notifyListeners(record);

    return record;
  }

  /**
   * 批量执行闭环
   */
  enforceBatch(events: SystemEvent[]): EnforcementLoopRecord[] {
    return events.map((e) => this.enforce(e));
  }

  /**
   * 预检查 — 不实际执行，仅检查事件是否会被允许
   */
  preCheck(event: SystemEvent): { would_allow: boolean; decision: GateResult["decision"]; reason: string } {
    const gateResult = eventGateSystem.validateEvent(event);
    return {
      would_allow: gateResult.decision === "ALLOW" || gateResult.decision === "MODIFY",
      decision: gateResult.decision,
      reason: gateResult.reason,
    };
  }

  /**
   * 获取内核状态
   */
  getState(): EnforcementKernelState {
    // 刷新活跃策略/规则数
    const stats = policyEngine.getStats();
    this.state.active_policies = stats.active_policies;
    this.state.active_rules = stats.active_rules;
    return { ...this.state };
  }

  /**
   * 获取执行历史
   */
  getHistory(limit = 100): EnforcementLoopRecord[] {
    return this.history.slice(-limit);
  }

  /**
   * 获取被阻断的事件历史
   */
  getBlockedHistory(limit = 50): EnforcementLoopRecord[] {
    return this.history
      .filter((r) => r.final_decision === "BLOCK")
      .slice(-limit);
  }

  /**
   * 订阅闭环执行
   */
  subscribe(listener: LoopListener): () => void {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }

  /**
   * 启用/禁用内核
   */
  setEnabled(enabled: boolean): void {
    this.state.enabled = enabled;
    enforcementPipeline.setEnabled(enabled);
  }

  /**
   * 重置统计
   */
  resetStats(): void {
    this.state = {
      ...this.state,
      total_processed: 0,
      total_allowed: 0,
      total_blocked: 0,
      total_modified: 0,
      total_quarantined: 0,
      last_enforced_at: null,
      last_error: null,
    };
  }

  // ─────────────────────────────────────────────────────────────
  // 内部方法
  // ─────────────────────────────────────────────────────────────

  private findStage(stages: StageResult[], stage: string): StageResult {
    return stages.find((s) => s.stage === stage) ?? {
      stage: stage as StageResult["stage"],
      passed: false,
      duration_ms: 0,
      error: "Stage not executed",
    };
  }

  private determineStatus(decision: GateResult["decision"], applied: boolean): LoopStatus {
    if (decision === "BLOCK") return "blocked";
    if (decision === "QUARANTINE") return "blocked";
    if (!applied) return "error";
    return "completed";
  }

  private buildReconciliationResult(
    decision: GateResult["decision"],
    applied: boolean,
  ): EnforcementLoopRecord["reconciliation_result"] {
    if (!applied) {
      return {
        consistent: false,
        inconsistencies_count: 1,
        authority_level: "L1",
      };
    }
    return {
      consistent: true,
      inconsistencies_count: 0,
      authority_level: "L1",
    };
  }

  private updateStats(decision: GateResult["decision"], applied: boolean): void {
    this.state.total_processed++;
    if (applied) {
      if (decision === "MODIFY") {
        this.state.total_modified++;
      } else {
        this.state.total_allowed++;
      }
    } else {
      if (decision === "BLOCK") {
        this.state.total_blocked++;
      } else if (decision === "QUARANTINE") {
        this.state.total_quarantined++;
      }
    }
    this.state.last_enforced_at = new Date().toISOString();
  }

  private notifyListeners(record: EnforcementLoopRecord): void {
    for (const listener of this.listeners) {
      try {
        listener(record);
      } catch (err) {
        console.error("[EnforcementLoop] listener error:", err);
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const enforcementLoop = new EnforcementLoop();
