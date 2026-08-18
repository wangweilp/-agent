/**
 * 知维 OS Enforcement Pipeline — 执行前流水线
 * Zhiwei OS Enforcement Pipeline
 *
 * 流水线阶段：
 * event → pre_validate → gate → transform → apply → post_validate → reconcile
 *
 * 阶段职责：
 * 1. pre_validate    — 结构验证（event_id / timestamp / trace_id / causal 完整性）
 * 2. gate            — 门控评估（EventGateSystem.validateEvent）
 * 3. transform       — 事件转换（MODIFY 决策时应用修改）
 * 4. apply           — 应用到 EventStore（causalKernel.publish）
 * 5. post_validate   — 后验证（应用后一致性检查）
 * 6. reconcile       — 对账（与 Authority Layer 协调）
 *
 * 约束：
 * - BLOCK 决策时跳过 apply 及后续阶段
 * - QUARANTINE 决策时不 apply，记录隔离
 * - 每阶段记录耗时
 * - 全流程 backward compatible（未启用时直接 publish）
 */

import { causalKernel } from "@/lib/event-bus/causal-kernel";
import { eventGateSystem } from "@/lib/enforcement/event-gate";
import type {
  SystemEvent,
} from "@/types/event-bus";
import type {
  EnforcementResult,
  StageResult,
  PipelineStage,
  GateResult,
} from "@/lib/enforcement/types";

// ═══════════════════════════════════════════════════════════════
// EnforcementPipeline — 执行前流水线
// ═══════════════════════════════════════════════════════════════

export class EnforcementPipeline {
  private enabled = true;

  /**
   * 启用/禁用流水线（禁用时直接 publish，backward compatible）
   */
  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
  }

  isEnabled(): boolean {
    return this.enabled;
  }

  /**
   * 执行流水线 — 主入口
   *
   * @param event 待处理事件
   * @returns 执行结果
   */
  execute(event: SystemEvent): EnforcementResult {
    const startTime = Date.now();
    const enforcedAt = new Date().toISOString();

    // 未启用时直接 publish（backward compatible）
    if (!this.enabled) {
      causalKernel.publish(event);
      return {
        original_event: event,
        final_event: event,
        final_decision: "ALLOW",
        applied: true,
        stages: [],
        total_duration_ms: Date.now() - startTime,
        rejection_reason: null,
        enforced_at: enforcedAt,
      };
    }

    const stages: StageResult[] = [];
    let currentEvent = event;
    let finalDecision: GateResult["decision"] = "ALLOW";
    let applied = false;
    // 阶段 1：pre_validate
    const preValidateResult = this.preValidate(event);
    stages.push(preValidateResult);
    if (!preValidateResult.passed) {
      return this.buildResult(
        event, null, "BLOCK", false, stages,
        preValidateResult.error ?? "Pre-validation failed",
        startTime, enforcedAt,
      );
    }

    // 阶段 2：gate
    const gateResult = this.gate(currentEvent);
    stages.push(gateResult);
    finalDecision = gateResult.gate_result?.decision ?? "ALLOW";

    if (finalDecision === "BLOCK") {
      return this.buildResult(
        event, null, "BLOCK", false, stages,
        gateResult.gate_result?.reason ?? "Blocked by gate",
        startTime, enforcedAt,
      );
    }

    if (finalDecision === "QUARANTINE") {
      return this.buildResult(
        event, null, "QUARANTINE", false, stages,
        gateResult.gate_result?.reason ?? "Quarantined by gate",
        startTime, enforcedAt,
      );
    }

    // 阶段 3：transform（仅 MODIFY 决策）
    if (finalDecision === "MODIFY") {
      const transformResult = this.transform(currentEvent, gateResult.gate_result);
      stages.push(transformResult);
      if (transformResult.output) {
        currentEvent = transformResult.output;
      }
    }

    // 阶段 4：apply
    const applyResult = this.apply(currentEvent);
    stages.push(applyResult);
    applied = applyResult.passed;

    if (!applyResult.passed) {
      return this.buildResult(
        event, currentEvent, finalDecision, false, stages,
        applyResult.error ?? "Apply failed",
        startTime, enforcedAt,
      );
    }

    // 阶段 5：post_validate
    const postValidateResult = this.postValidate(currentEvent);
    stages.push(postValidateResult);

    // 阶段 6：reconcile
    const reconcileResult = this.reconcile(currentEvent);
    stages.push(reconcileResult);

    return this.buildResult(
      event, currentEvent, finalDecision, applied, stages,
      null, startTime, enforcedAt,
    );
  }

  /**
   * 批量执行
   */
  executeBatch(events: SystemEvent[]): EnforcementResult[] {
    return events.map((e) => this.execute(e));
  }

  // ─────────────────────────────────────────────────────────────
  // 各阶段实现
  // ─────────────────────────────────────────────────────────────

  /**
   * 阶段 1：pre_validate — 结构验证
   */
  private preValidate(event: SystemEvent): StageResult {
    const start = Date.now();

    // 检查必需字段
    if (!event.event_id) {
      return this.stageResult("pre_validate", false, undefined, "Missing event_id", start);
    }
    if (!event.timestamp) {
      return this.stageResult("pre_validate", false, undefined, "Missing timestamp", start);
    }
    if (!event.trace_id) {
      return this.stageResult("pre_validate", false, undefined, "Missing trace_id", start);
    }
    if (!event.causal) {
      return this.stageResult("pre_validate", false, undefined, "Missing causal info", start);
    }

    return this.stageResult("pre_validate", true, event, undefined, start);
  }

  /**
   * 阶段 2：gate — 门控评估
   */
  private gate(event: SystemEvent): StageResult {
    const start = Date.now();
    const gateResult = eventGateSystem.validateEvent(event);
    return {
      stage: "gate",
      passed: gateResult.decision === "ALLOW" || gateResult.decision === "MODIFY",
      output: gateResult.modified_event ?? event,
      gate_result: gateResult,
      duration_ms: Date.now() - start,
    };
  }

  /**
   * 阶段 3：transform — 事件转换
   */
  private transform(event: SystemEvent, gateResult: GateResult | undefined): StageResult {
    const start = Date.now();
    const modifiedEvent = gateResult?.modified_event ?? event;
    return this.stageResult("transform", true, modifiedEvent, undefined, start);
  }

  /**
   * 阶段 4：apply — 应用到 EventStore
   */
  private apply(event: SystemEvent): StageResult {
    const start = Date.now();
    try {
      causalKernel.publish(event);
      return this.stageResult("apply", true, event, undefined, start);
    } catch (err) {
      return this.stageResult(
        "apply", false, undefined,
        err instanceof Error ? err.message : String(err), start,
      );
    }
  }

  /**
   * 阶段 5：post_validate — 后验证
   */
  private postValidate(event: SystemEvent): StageResult {
    const start = Date.now();
    // 验证事件已成功写入 CausalKernel
    const stored = causalKernel.getEvent(event.event_id);
    if (!stored) {
      return this.stageResult("post_validate", false, undefined, "Event not found in store after apply", start);
    }
    return this.stageResult("post_validate", true, event, undefined, start);
  }

  /**
   * 阶段 6：reconcile — 对账（与 Authority Layer 协调）
   *
   * 当前实现：记录对账状态
   * 完整实现会调用 authorityFacade.validateConsistency
   */
  private reconcile(event: SystemEvent): StageResult {
    const start = Date.now();
    // 对账：确认事件已进入 L1 权威层
    // 这里只做轻量级检查，完整对账由 Authority Layer 定期执行
    return {
      stage: "reconcile",
      passed: true,
      output: event,
      duration_ms: Date.now() - start,
    };
  }

  // ─────────────────────────────────────────────────────────────
  // 辅助方法
  // ─────────────────────────────────────────────────────────────

  private stageResult(
    stage: PipelineStage,
    passed: boolean,
    output: SystemEvent | undefined,
    error: string | undefined,
    startTime: number,
  ): StageResult {
    return {
      stage,
      passed,
      output,
      duration_ms: Date.now() - startTime,
      error,
    };
  }

  private buildResult(
    originalEvent: SystemEvent,
    finalEvent: SystemEvent | null,
    finalDecision: GateResult["decision"],
    applied: boolean,
    stages: StageResult[],
    rejectionReason: string | null,
    startTime: number,
    enforcedAt: string,
  ): EnforcementResult {
    return {
      original_event: originalEvent,
      final_event: finalEvent,
      final_decision: finalDecision,
      applied,
      stages,
      total_duration_ms: Date.now() - startTime,
      rejection_reason: rejectionReason,
      enforced_at: enforcedAt,
    };
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const enforcementPipeline = new EnforcementPipeline();
