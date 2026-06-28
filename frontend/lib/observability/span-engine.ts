/**
 * 知维 OS Span Engine — 执行跨度引擎
 * Zhiwei OS Span Engine
 *
 * 能力：
 * - startSpan()        — 开始 span
 * - endSpan()          — 结束 span
 * - linkSpanToEvent()  — 关联 span 到 event
 * - measureDuration()  — 测量执行时长
 *
 * 要求：
 * - enforcement pipeline 每一 stage 必须生成 span
 * - replay 每一 frame 必须生成 span
 * - snapshot restore 必须生成 span
 */

import { observabilityStore } from "@/lib/observability/store";
import type {
  SystemTraceEvent,
  SpanStatus,
  CreateSpanParams,
  SpanMetadata,
  SystemLayer,
  TraceService,
  SpanKind,
} from "@/lib/observability/types";

// ═══════════════════════════════════════════════════════════════
// SpanEngine — Span 引擎
// ═══════════════════════════════════════════════════════════════

let spanCounter = 0;

export class SpanEngine {
  /**
   * 生成 span_id
   */
  private generateSpanId(): string {
    spanCounter++;
    return `span_${Date.now()}_${spanCounter}`;
  }

  /**
   * 开始 span — 创建一个新的 span 并存储
   */
  async startSpan(params: CreateSpanParams): Promise<SystemTraceEvent> {
    const span: SystemTraceEvent = {
      span_id: this.generateSpanId(),
      parent_span_id: params.parent_span_id ?? null,
      trace_id: params.trace_id,
      event_id: params.event_id,
      causal_ref_id: params.causal_ref_id,
      snapshot_id: params.snapshot_id,
      enforcement_loop_id: params.enforcement_loop_id,
      layer: params.layer,
      service: params.service,
      kind: params.kind,
      start_time: new Date().toISOString(),
      status: "started",
      metadata: params.metadata ?? {},
    };

    await observabilityStore.putSpan(span);
    return span;
  }

  /**
   * 结束 span — 设置 end_time / duration / status
   */
  async endSpan(
    span_id: string,
    status: SpanStatus = "completed",
    error?: string,
    metadata?: Partial<SpanMetadata>,
  ): Promise<SystemTraceEvent | null> {
    const span = await observabilityStore.getSpan(span_id);
    if (!span) return null;

    const endTime = new Date().toISOString();
    const duration = new Date(endTime).getTime() - new Date(span.start_time).getTime();

    const updated: SystemTraceEvent = {
      ...span,
      end_time: endTime,
      duration_ms: duration,
      status,
      error: status === "error" ? error : undefined,
      metadata: metadata ? { ...span.metadata, ...metadata } : span.metadata,
    };

    await observabilityStore.putSpan(updated);
    return updated;
  }

  /**
   * 关联 span 到 event — 建立 span ↔ event 双向关联
   */
  async linkSpanToEvent(span_id: string, event_id: string): Promise<void> {
    const span = await observabilityStore.getSpan(span_id);
    if (!span) return;

    const updated: SystemTraceEvent = {
      ...span,
      event_id,
    };
    await observabilityStore.putSpan(updated);
  }

  /**
   * 关联 span 到 snapshot
   */
  async linkSpanToSnapshot(span_id: string, snapshot_id: string): Promise<void> {
    const span = await observabilityStore.getSpan(span_id);
    if (!span) return;

    const updated: SystemTraceEvent = {
      ...span,
      snapshot_id,
    };
    await observabilityStore.putSpan(updated);
  }

  /**
   * 关联 span 到 enforcement loop
   */
  async linkSpanToEnforcement(span_id: string, enforcement_loop_id: string): Promise<void> {
    const span = await observabilityStore.getSpan(span_id);
    if (!span) return;

    const updated: SystemTraceEvent = {
      ...span,
      enforcement_loop_id,
    };
    await observabilityStore.putSpan(updated);
  }

  /**
   * 测量执行时长 — 便捷方法，包装 startSpan + endSpan
   *
   * @param params  span 参数
   * @param fn      要测量的函数
   * @returns       { result, span }
   */
  async measureDuration<T>(
    params: CreateSpanParams,
    fn: () => Promise<T>,
  ): Promise<{ result: T; span: SystemTraceEvent }> {
    const span = await this.startSpan(params);
    try {
      const result = await fn();
      const endedSpan = await this.endSpan(span.span_id, "completed");
      return { result, span: endedSpan ?? span };
    } catch (err) {
      const endedSpan = await this.endSpan(
        span.span_id,
        "error",
        err instanceof Error ? err.message : String(err),
      );
      throw err;
      return { result: undefined as unknown as T, span: endedSpan ?? span };
    }
  }

  /**
   * 测量同步函数时长
   */
  async measureSync<T>(
    params: CreateSpanParams,
    fn: () => T,
  ): Promise<{ result: T; span: SystemTraceEvent }> {
    return this.measureDuration(params, async () => fn());
  }

  // ─────────────────────────────────────────────────────────────
  // 便捷工厂方法 — 为常见场景预配置 span
  // ─────────────────────────────────────────────────────────────

  /**
   * 创建 enforcement stage span
   */
  async startEnforcementStageSpan(
    trace_id: string,
    stage: string,
    parent_span_id?: string,
  ): Promise<SystemTraceEvent> {
    return this.startSpan({
      trace_id,
      parent_span_id,
      layer: "L4",
      service: "enforcement",
      kind: "enforcement_stage",
      metadata: { operation: stage, tags: { stage } },
    });
  }

  /**
   * 创建 replay frame span
   */
  async startReplayFrameSpan(
    trace_id: string,
    frame_index: number,
    parent_span_id?: string,
  ): Promise<SystemTraceEvent> {
    return this.startSpan({
      trace_id,
      parent_span_id,
      layer: "L2",
      service: "replay",
      kind: "replay_frame",
      metadata: { operation: `frame_${frame_index}`, tags: { frame_index: String(frame_index) } },
    });
  }

  /**
   * 创建 snapshot restore span
   */
  async startSnapshotRestoreSpan(
    trace_id: string,
    snapshot_id: string,
    parent_span_id?: string,
  ): Promise<SystemTraceEvent> {
    return this.startSpan({
      trace_id,
      parent_span_id,
      layer: "L2",
      service: "snapshot",
      kind: "snapshot_restore",
      snapshot_id,
      metadata: { operation: "snapshot_restore", tags: { snapshot_id } },
    });
  }

  /**
   * 创建 snapshot create span
   */
  async startSnapshotCreateSpan(
    trace_id: string,
    parent_span_id?: string,
  ): Promise<SystemTraceEvent> {
    return this.startSpan({
      trace_id,
      parent_span_id,
      layer: "L2",
      service: "snapshot",
      kind: "snapshot_create",
      metadata: { operation: "snapshot_create" },
    });
  }

  /**
   * 创建 control loop cycle span
   */
  async startControlLoopSpan(
    trace_id: string,
    cycle_number: number,
    parent_span_id?: string,
  ): Promise<SystemTraceEvent> {
    return this.startSpan({
      trace_id,
      parent_span_id,
      layer: "L5",
      service: "control_loop",
      kind: "control_loop_cycle",
      metadata: { operation: `cycle_${cycle_number}`, tags: { cycle: String(cycle_number) } },
    });
  }

  /**
   * 创建 recovery span
   */
  async startRecoverySpan(
    trace_id: string,
    strategy: string,
    parent_span_id?: string,
  ): Promise<SystemTraceEvent> {
    return this.startSpan({
      trace_id,
      parent_span_id,
      layer: "L5",
      service: "self_healing",
      kind: "recovery",
      metadata: { operation: "recovery", recovery_strategy: strategy },
    });
  }

  /**
   * 创建 validation span
   */
  async startValidationSpan(
    trace_id: string,
    validation_type: string,
    parent_span_id?: string,
  ): Promise<SystemTraceEvent> {
    return this.startSpan({
      trace_id,
      parent_span_id,
      layer: "L3",
      service: "authority",
      kind: "validation",
      metadata: { operation: validation_type },
    });
  }

  /**
   * 创建 policy evaluation span
   */
  async startPolicyEvaluationSpan(
    trace_id: string,
    policy_id: string,
    parent_span_id?: string,
  ): Promise<SystemTraceEvent> {
    return this.startSpan({
      trace_id,
      parent_span_id,
      layer: "L4",
      service: "enforcement",
      kind: "policy_evaluation",
      metadata: { operation: "policy_evaluation", policy_id },
    });
  }

  /**
   * 创建 gate decision span
   */
  async startGateDecisionSpan(
    trace_id: string,
    event_id: string,
    parent_span_id?: string,
  ): Promise<SystemTraceEvent> {
    return this.startSpan({
      trace_id,
      parent_span_id,
      event_id,
      layer: "L4",
      service: "enforcement",
      kind: "gate_decision",
      metadata: { operation: "gate_decision" },
    });
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const spanEngine = new SpanEngine();
