/**
 * 知维 OS Trace Builder — 构造层
 * Zhiwei OS Trace Builder
 *
 * v5 OS-level 核心新增：
 *   Event → TraceEvent → Span Tree
 *
 * 职责：
 * - 给每个 event 自动生成 span
 * - 绑定 causal_chain（嵌入路径，从根到当前）
 * - 绑定 decision（结构化决策信息）
 * - 生成 explanation summary（人类可读 WHY）
 *
 * 设计原则：
 * 1. Observability cannot mutate state — 不修改 Event/Snapshot/Authority
 * 2. Trace is derived, not source       — Event → Trace（派生，单向）
 * 3. WHY must be reproducible           — 同 trace_id → 同 Trace Tree
 */

import { observabilityStore } from "@/lib/observability/store";
import { spanEngine } from "@/lib/observability/span-engine";
import { causalKernel } from "@/lib/event-bus/causal-kernel";
import type { SystemEvent } from "@/types/event-bus";
import type {
  SystemTraceEvent,
  TraceDecision,
  TraceExplanation,
  AlternativePath,
  SystemLayer,
  TraceService,
  SpanKind,
  CreateSpanParams,
  SpanMetadata,
} from "@/lib/observability/types";

// ═══════════════════════════════════════════════════════════════
// TraceBuilder — Trace 构造器
// ═══════════════════════════════════════════════════════════════

export class TraceBuilder {
  /**
   * 从单个事件构造 Trace Span — 自动绑定 causal_chain + decision + explanation
   *
   * 这是 v5 的核心入口：每当系统产生一个 event，自动生成对应的 trace span。
   *
   * @param event 源事件
   * @param options 构造选项（parent span、enforcement 决策等）
   * @returns 生成的 SystemTraceEvent
   */
  async buildSpanFromEvent(
    event: SystemEvent,
    options: {
      parent_span_id?: string;
      layer?: SystemLayer;
      service?: TraceService;
      kind?: SpanKind;
      enforcement_action?: string;
      rules_matched?: string[];
      authority_level?: SystemLayer;
      snapshot_used?: string;
      alternatives?: AlternativePath[];
    } = {},
  ): Promise<SystemTraceEvent> {
    // 1. 推导 causal_chain（嵌入路径）
    const causalChain = this.deriveCausalChain(event);

    // 2. 推导 layer / service / kind（如未指定）
    const layer = options.layer ?? this.inferLayer(event);
    const service = options.service ?? this.inferService(event);
    const kind = options.kind ?? this.inferKind(event);

    // 3. 构造 decision（v5 OS-level 结构化决策）
    const decision = this.buildDecision(event, options);

    // 4. 构造 explanation（v5 OS-level 人类可读 WHY + 替代路径）
    const explanation = this.buildExplanation(event, causalChain, options.alternatives ?? []);

    // 5. 构造 metadata（保留向后兼容）
    const metadata = this.buildMetadata(event, options);

    // 6. 通过 SpanEngine 创建 span（复用现有基础设施）
    const spanParams: CreateSpanParams = {
      trace_id: event.trace_id,
      parent_span_id: options.parent_span_id,
      layer,
      service,
      kind,
      event_id: event.event_id,
      causal_ref_id: event.causal.parent_event_id ?? undefined,
      snapshot_id: options.snapshot_used,
      enforcement_loop_id: undefined,
      metadata,
    };

    const span = await spanEngine.startSpan(spanParams);

    // 7. v5 OS-level：直接嵌入 causal_chain + decision + explanation（无需回查）
    const enhancedSpan: SystemTraceEvent = {
      ...span,
      causal_event_id: event.event_id,
      causal_chain: causalChain,
      decision,
      explanation,
    };

    await observabilityStore.putSpan(enhancedSpan);
    return enhancedSpan;
  }

  /**
   * 从 trace 构建完整 Span Tree — 批量构造
   *
   * 内部：
   *   1. causalKernel.replay(trace_id) 拉取所有事件
   *   2. 按时间排序
   *   3. 依次为每个事件构造 span（建立 parent_span_id 关系）
   *   4. 返回 span tree
   *
   * @param trace_id 目标 trace
   * @returns span 列表（按时间排序）
   */
  async buildTraceFromEvents(trace_id: string): Promise<SystemTraceEvent[]> {
    const events = causalKernel.replay(trace_id);
    if (events.length === 0) return [];

    // 按时间排序（确保因果顺序）
    const sorted = [...events].sort((a, b) => a.timestamp.localeCompare(b.timestamp));

    // 维护 event_id → span_id 映射（用于建立 parent_span_id）
    const eventToSpan = new Map<string, string>();
    const spans: SystemTraceEvent[] = [];

    for (const event of sorted) {
      const parentSpanId = event.causal.parent_event_id
        ? eventToSpan.get(event.causal.parent_event_id)
        : undefined;

      const span = await this.buildSpanFromEvent(event, { parent_span_id: parentSpanId });
      eventToSpan.set(event.event_id, span.span_id);
      spans.push(span);
    }

    return spans;
  }

  // ─────────────────────────────────────────────────────────────
  // 内部方法：因果链推导
  // ─────────────────────────────────────────────────────────────

  /**
   * 推导 causal_chain — 从根到当前事件的完整 event_id 路径
   *
   * 这是 v5 的关键升级：
   * 不再仅靠 parent_span_id 推导因果，而是直接嵌入完整 event_id 路径。
   * 这样 WHY Engine 不需要回查 causal kernel 即可解释因果。
   */
  private deriveCausalChain(event: SystemEvent): string[] {
    const events = causalKernel.replay(event.trace_id);
    const eventMap = new Map(events.map((e) => [e.event_id, e]));

    const chain: string[] = [];
    const visited = new Set<string>();

    // 从当前事件向上回溯
    const collect = (eventId: string) => {
      if (visited.has(eventId)) return;
      visited.add(eventId);

      const e = eventMap.get(eventId);
      if (!e) return;

      // 主父事件
      if (e.causal.parent_event_id) {
        collect(e.causal.parent_event_id);
      }

      // 多父因果边（取第一条作为主路径）
      if (e.causal.causal_links && e.causal.causal_links.length > 0) {
        for (const link of e.causal.causal_links) {
          collect(link.from);
        }
      }
    };

    collect(event.event_id);

    // chain 是反序的（叶子在前），需要反转为根→当前
    return [event.event_id, ...this.collectAncestors(event, eventMap, new Set())].reverse();
  }

  /**
   * 收集祖先事件 ID（BFS，去重）
   */
  private collectAncestors(
    event: SystemEvent,
    eventMap: Map<string, SystemEvent>,
    visited: Set<string>,
  ): string[] {
    const result: string[] = [];
    if (visited.has(event.event_id)) return result;
    visited.add(event.event_id);

    if (event.causal.parent_event_id) {
      const parent = eventMap.get(event.causal.parent_event_id);
      if (parent) {
        result.push(parent.event_id);
        result.push(...this.collectAncestors(parent, eventMap, visited));
      }
    }

    if (event.causal.causal_links) {
      for (const link of event.causal.causal_links) {
        const source = eventMap.get(link.from);
        if (source) {
          result.push(source.event_id);
          result.push(...this.collectAncestors(source, eventMap, visited));
        }
      }
    }

    return result;
  }

  // ─────────────────────────────────────────────────────────────
  // 内部方法：决策与解释构造
  // ─────────────────────────────────────────────────────────────

  /**
   * 构造 TraceDecision — 结构化决策信息
   *
   * v5 OS-level：不再散装在 metadata，而是结构化为可推理字段
   */
  private buildDecision(
    event: SystemEvent,
    options: {
      enforcement_action?: string;
      rules_matched?: string[];
      authority_level?: SystemLayer;
      snapshot_used?: string;
    },
  ): TraceDecision {
    return {
      trigger_event_id: event.causal.parent_event_id ?? event.event_id,
      rule_matched: options.rules_matched ?? [],
      authority_level: options.authority_level ?? "L1",
      enforcement_action: options.enforcement_action,
      snapshot_used: options.snapshot_used,
      decided_at: event.timestamp,
    };
  }

  /**
   * 构造 TraceExplanation — 人类可读 WHY + 替代路径
   *
   * v5 OS-level：替代路径是反事实分析的数据基础
   */
  private buildExplanation(
    event: SystemEvent,
    causalChain: string[],
    alternatives: AlternativePath[],
  ): TraceExplanation {
    const summary = this.generateSummary(event, causalChain, alternatives);

    return {
      summary,
      causal_path: causalChain,
      alternatives_considered: alternatives,
      generated_at: new Date().toISOString(),
    };
  }

  /**
   * 生成人类可读 WHY 摘要
   */
  private generateSummary(
    event: SystemEvent,
    causalChain: string[],
    alternatives: AlternativePath[],
  ): string {
    const parts: string[] = [];

    parts.push(`Event ${event.event_id} (${event.type})`);

    if (causalChain.length > 1) {
      parts.push(`was caused by chain of ${causalChain.length} events`);
    } else {
      parts.push(`is a root event`);
    }

    if (alternatives.length > 0) {
      parts.push(`with ${alternatives.length} alternatives considered`);
    }

    return parts.join(", ") + ".";
  }

  /**
   * 构造 metadata（保留向后兼容）
   */
  private buildMetadata(
    event: SystemEvent,
    options: {
      enforcement_action?: string;
      rules_matched?: string[];
    },
  ): SpanMetadata {
    const metadata: SpanMetadata = {
      operation: event.type,
      tags: {
        event_type: event.type,
        severity: event.severity,
        source: event.source,
      },
    };

    if (options.enforcement_action) {
      metadata.decision = options.enforcement_action;
    }

    if (options.rules_matched && options.rules_matched.length > 0) {
      metadata.rule_id = options.rules_matched[0];
    }

    return metadata;
  }

  // ─────────────────────────────────────────────────────────────
  // 内部方法：layer / service / kind 推导
  // ─────────────────────────────────────────────────────────────

  private inferLayer(event: SystemEvent): SystemLayer {
    if (event.source.startsWith("enforcement")) return "L4";
    if (event.source.startsWith("authority")) return "L3";
    if (event.source.startsWith("snapshot") || event.source.startsWith("persistence")) return "L2";
    if (event.source.startsWith("observability")) return "L5";
    return "L1";
  }

  private inferService(event: SystemEvent): TraceService {
    const source = event.source;
    if (source.startsWith("runtime")) return "runtime";
    if (source.startsWith("memory")) return "memory";
    if (source.startsWith("governance")) return "governance";
    if (source.startsWith("enforcement")) return "enforcement";
    if (source.startsWith("authority")) return "authority";
    if (source.startsWith("self_healing")) return "self_healing";
    if (source.startsWith("control_loop")) return "control_loop";
    if (source.startsWith("replay")) return "replay";
    if (source.startsWith("snapshot")) return "snapshot";
    if (source.startsWith("causal_graph")) return "causal_graph";
    if (source.startsWith("agent")) return "agent";
    return "event_bus";
  }

  private inferKind(event: SystemEvent): SpanKind {
    const type = event.type;
    if (type.includes("enforcement") || type.includes("gate")) return "enforcement_stage";
    if (type.includes("policy")) return "policy_evaluation";
    if (type.includes("gate")) return "gate_decision";
    if (type.includes("replay")) return "replay_frame";
    if (type.includes("snapshot") && type.includes("restore")) return "snapshot_restore";
    if (type.includes("snapshot")) return "snapshot_create";
    if (type.includes("recovery")) return "recovery";
    if (type.includes("validation")) return "validation";
    if (type.includes("compaction")) return "compaction";
    if (type.includes("control_loop")) return "control_loop_cycle";
    return "event_publish";
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const traceBuilder = new TraceBuilder();
