/**
 * 知维 OS Observability Kernel — 统一门面
 * Zhiwei OS Observability Kernel — Unified Facade
 *
 * v7 核心入口：
 * 整合 Types + Store + Span Engine + Correlator + WHY Engine + Critical Path Analyzer
 *
 * 架构层级：
 * ┌──────────────────────────────────────────────┐
 * │  ObservabilityFacade（本文件）               │  ← 统一入口
 * ├──────────────────────────────────────────────┤
 * │  SpanEngine              — Span 创建/管理    │
 * │  TraceCorrelator         — Trace 图构建      │
 * │  WhyEngine               — WHY 解释          │
 * │  CriticalPathAnalyzer    — 关键路径分析      │
 * ├──────────────────────────────────────────────┤
 * │  ObservabilityStore      — IndexedDB 持久化  │
 * ├──────────────────────────────────────────────┤
 * │  CausalKernel / EventStore / SnapshotStore  │  ← 数据层（不修改）
 * └──────────────────────────────────────────────┘
 *
 * 系统升级为：
 * Event Layer → Causal Layer → Authority Layer → Enforcement Layer → Observability Layer
 *
 * 新增第 5 层：OBSERVABILITY LAYER（系统自我解释能力）
 */

// ═══════════════════════════════════════════════════════════════
// 类型导出
// ═══════════════════════════════════════════════════════════════

export type {
  SystemLayer,
  TraceService,
  SpanStatus,
  SpanKind,
  SystemTraceEvent,
  SpanMetadata,
  SpanEdgeType,
  SpanEdge,
  TraceGraph,
  TraceStats,
  WhyExplanation,
  PolicyDecision,
  EnforcementRecord,
  CriticalPathReport,
  SpanPath,
  ExecutionProfile,
  CreateSpanParams,
  SpanFilter,
  // v5 OS-level 新增类型导出
  TraceDecision,
  TraceExplanation,
  AlternativePath,
  DecisionNode,
  DecisionEdge,
  DecisionEdgeType,
  DecisionGraph,
  DecisionGraphStats,
  CounterfactualAnalysis,
} from "@/lib/observability/types";

// 决策回放结果类型（why-engine.ts 定义）
export type { DecisionReplayItem, DecisionReplayResult } from "@/lib/observability/why-engine";

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export { observabilityStore } from "@/lib/observability/store";
export { ObservabilityStore } from "@/lib/observability/store";

export { spanEngine, SpanEngine } from "@/lib/observability/span-engine";

export { traceCorrelator, TraceCorrelator } from "@/lib/observability/correlator";

export { whyEngine, WhyEngine } from "@/lib/observability/why-engine";

export { criticalPathAnalyzer, CriticalPathAnalyzer } from "@/lib/observability/critical-path-analyzer";

// v5 OS-level 新增模块单例
export { traceBuilder, TraceBuilder } from "@/lib/observability/trace-builder";
export { decisionGraphEngine, DecisionGraphEngine } from "@/lib/observability/decision-graph";

// ═══════════════════════════════════════════════════════════════
// 统一门面 — ObservabilityFacade
// ═══════════════════════════════════════════════════════════════

import { observabilityStore } from "@/lib/observability/store";
import { spanEngine } from "@/lib/observability/span-engine";
import { traceCorrelator } from "@/lib/observability/correlator";
import { whyEngine } from "@/lib/observability/why-engine";
import { criticalPathAnalyzer } from "@/lib/observability/critical-path-analyzer";
import { traceBuilder } from "@/lib/observability/trace-builder";
import { decisionGraphEngine } from "@/lib/observability/decision-graph";
import type {
  SpanStatus,
  SpanMetadata,
  TraceGraph,
  WhyExplanation,
  CriticalPathReport,
  CreateSpanParams,
  SpanFilter,
  DecisionGraph,
  CounterfactualAnalysis,
} from "@/lib/observability/types";
import type { DecisionReplayResult } from "@/lib/observability/why-engine";
import type { SystemEvent } from "@/types/event-bus";

/**
 * ObservabilityFacade — 可观测性内核统一入口
 *
 * 聚合所有可观测性能力，提供一站式访问
 *
 * v5 OS-level 升级：新增 Trace Builder + Decision Graph + Counterfactual
 */
export const observabilityFacade = {
  // ── Span Engine ──
  startSpan: (params: CreateSpanParams) => spanEngine.startSpan(params),
  endSpan: (
    span_id: string,
    status?: SpanStatus,
    error?: string,
    metadata?: Partial<SpanMetadata>,
  ) => spanEngine.endSpan(span_id, status, error, metadata),
  linkSpanToEvent: (span_id: string, event_id: string) =>
    spanEngine.linkSpanToEvent(span_id, event_id),
  measureDuration: <T>(params: CreateSpanParams, fn: () => Promise<T>) =>
    spanEngine.measureDuration(params, fn),

  // ── Trace Correlator ──
  buildTraceGraph: (trace_id: string): Promise<TraceGraph> =>
    traceCorrelator.buildTraceGraph(trace_id),
  getSpanByEventId: (event_id: string) => traceCorrelator.getSpanByEventId(event_id),

  // ── WHY Engine ──
  why: (trace_id: string, event_id?: string): Promise<WhyExplanation> =>
    whyEngine.why(trace_id, event_id),

  // ── Critical Path Analyzer ──
  analyzeCriticalPath: (trace_id: string): Promise<CriticalPathReport> =>
    criticalPathAnalyzer.analyze(trace_id),

  // ── Store ──
  getSpansByTraceId: (trace_id: string) => observabilityStore.getSpansByTraceId(trace_id),
  getTraceIds: () => observabilityStore.getTraceIds(),
  querySpans: (filter: SpanFilter) => observabilityStore.querySpans(filter),
  clear: () => observabilityStore.clear(),

  // ── v5 OS-level 新增：Trace Builder ──
  /**
   * 从单个事件构造 Trace Span（自动绑定 causal_chain + decision + explanation）
   */
  buildSpanFromEvent: (
    event: SystemEvent,
    options?: Parameters<typeof traceBuilder.buildSpanFromEvent>[1],
  ) => traceBuilder.buildSpanFromEvent(event, options),

  /**
   * 从 trace 批量构造 Span Tree
   */
  buildTraceFromEvents: (trace_id: string) => traceBuilder.buildTraceFromEvents(trace_id),

  // ── v5 OS-level 新增：Decision Graph ──
  /**
   * 构建决策图 — 三图合一的关键新增
   * Execution Graph + Causal Graph + Decision Graph = OS-level explainability
   */
  buildDecisionGraph: (trace_id: string): Promise<DecisionGraph> =>
    decisionGraphEngine.buildDecisionGraph(trace_id),

  /**
   * 获取决策的替代路径（反事实分析入口）
   */
  getAlternatives: (span_id: string) => decisionGraphEngine.getAlternatives(span_id),

  // ── v5 OS-level 新增：Counterfactual Analysis ──
  /**
   * 反事实分析 — "如果 X 没发生 / 决策不同，会怎样？"
   */
  counterfactual: (
    trace_id: string,
    hypothetical_event_id: string,
    hypothetical_decision?: string,
  ): Promise<CounterfactualAnalysis> =>
    whyEngine.counterfactual(trace_id, hypothetical_event_id, hypothetical_decision),

  // ── v5 OS-level 新增：Decision Replay ──
  /**
   * 决策回放 — 重放决策路径，可修改假设决策
   */
  replayDecisions: (
    trace_id: string,
    overrideDecisions?: Map<string, string>,
  ): Promise<DecisionReplayResult> =>
    whyEngine.replayDecisions(trace_id, overrideDecisions),
};

// ═══════════════════════════════════════════════════════════════
// UI Hooks 导出
// ═══════════════════════════════════════════════════════════════

export {
  useTraceGraph,
  useWhy,
  useCriticalPath,
  useObservabilityStats,
  useSpanEngine,
} from "@/hooks/use-observability";
export type {
  TraceGraphData,
  SpanTreeNode,
  WhyData,
  CriticalPathData,
  ObservabilityStatsData,
} from "@/hooks/use-observability";
