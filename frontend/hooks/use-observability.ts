/**
 * 知维 OS Observability Kernel — UI 接入 Hook
 * Zhiwei OS Observability Kernel — UI Hooks
 *
 * 内部流程：
 *   traceCorrelator.buildTraceGraph() → whyEngine.why() → criticalPathAnalyzer.analyze()
 *
 * 核心 Hook：
 * - useTraceGraph(trace_id)     构建 trace 图（span tree + span timeline）
 * - useWhy(trace_id, event_id?) WHY 解释（root cause + decision + causal + snapshot + enforcement）
 * - useCriticalPath(trace_id)   关键路径报告（latency/causal/enforcement hotpath）
 *
 * UI 必须能展示：
 * - trace tree
 * - span timeline
 * - causal + execution merged graph
 * - WHY explanation panel
 */

import { useEffect, useState, useRef, useCallback } from "react";
import { traceCorrelator } from "@/lib/observability/correlator";
import { whyEngine } from "@/lib/observability/why-engine";
import { criticalPathAnalyzer } from "@/lib/observability/critical-path-analyzer";
import { observabilityStore } from "@/lib/observability/store";
import { spanEngine } from "@/lib/observability/span-engine";
import type {
  TraceGraph,
  WhyExplanation,
  CriticalPathReport,
  SystemTraceEvent,
} from "@/lib/observability/types";

// ═══════════════════════════════════════════════════════════════
// useTraceGraph — Trace 图主 Hook
// ═══════════════════════════════════════════════════════════════

export interface TraceGraphData {
  /** 完整 trace 图 */
  graph: TraceGraph | null;
  /** 所有 span（按开始时间排序） — 用于 span timeline */
  spans: SystemTraceEvent[];
  /** span 树（嵌套结构） — 用于 trace tree 渲染 */
  spanTree: SpanTreeNode[];
  /** 统计信息 */
  stats: TraceGraph["stats"] | null;
  /** 根 span */
  roots: SystemTraceEvent[];
  /** 关键路径 span_id 列表 */
  criticalPath: string[];
  /** 是否正在构建 */
  isBuilding: boolean;
  /** 重新构建（手动触发） */
  rebuild: () => void;
}

/**
 * Span 树节点 — 用于 UI 渲染 trace tree
 */
export interface SpanTreeNode {
  span: SystemTraceEvent;
  children: SpanTreeNode[];
  depth: number;
}

/**
 * 构建 trace 图 — 图视图主入口
 *
 * 内部：
 *   1. traceCorrelator.buildTraceGraph() 构建 span DAG
 *   2. 计算 span tree（按 parent_span_id 嵌套）
 *   3. 排序 spans 用于 timeline 渲染
 *
 * @param trace_id Trace ID（null 时不构建）
 */
export function useTraceGraph(trace_id: string | null): TraceGraphData {
  const [graph, setGraph] = useState<TraceGraph | null>(null);
  const [isBuilding, setIsBuilding] = useState(false);
  const traceRef = useRef(trace_id);
  traceRef.current = trace_id;

  const build = useCallback(async () => {
    const tid = traceRef.current;
    if (!tid) {
      setGraph(null);
      return;
    }
    setIsBuilding(true);
    try {
      const g = await traceCorrelator.buildTraceGraph(tid);
      setGraph(g);
    } catch (err) {
      console.error("[useTraceGraph] build error:", err);
      setGraph(null);
    } finally {
      setIsBuilding(false);
    }
  }, []);

  useEffect(() => {
    build();
  }, [trace_id, build]);

  // 派生：span 列表（按 start_time 升序）
  const spans = graph
    ? [...graph.nodes].sort((a, b) => a.start_time.localeCompare(b.start_time))
    : [];

  // 派生：span 树（按 parent_span_id 嵌套）
  const spanTree = graph ? buildSpanTree(graph.nodes) : [];

  return {
    graph,
    spans,
    spanTree,
    stats: graph?.stats ?? null,
    roots: graph?.root_spans ?? [],
    criticalPath: graph?.critical_path ?? [],
    isBuilding,
    rebuild: build,
  };
}

/**
 * 构建 span 树（按 parent_span_id 嵌套）
 */
function buildSpanTree(spans: SystemTraceEvent[]): SpanTreeNode[] {
  const spanMap = new Map(spans.map((s) => [s.span_id, s]));
  const childrenMap = new Map<string | null, SystemTraceEvent[]>();

  for (const span of spans) {
    const parentKey = span.parent_span_id ?? null;
    const list = childrenMap.get(parentKey) || [];
    list.push(span);
    childrenMap.set(parentKey, list);
  }

  const buildNode = (span: SystemTraceEvent, depth: number): SpanTreeNode => {
    const children = childrenMap.get(span.span_id) || [];
    return {
      span,
      children: children
        .sort((a, b) => a.start_time.localeCompare(b.start_time))
        .map((c) => buildNode(c, depth + 1)),
      depth,
    };
  };

  const roots = childrenMap.get(null) || [];
  return roots
    .sort((a, b) => a.start_time.localeCompare(b.start_time))
    .map((r) => buildNode(r, 0));
}

// ═══════════════════════════════════════════════════════════════
// useWhy — WHY 解释 Hook
// ═══════════════════════════════════════════════════════════════

export interface WhyData {
  /** WHY 解释结果 */
  explanation: WhyExplanation | null;
  /** 是否正在查询 */
  isLoading: boolean;
  /** 错误信息 */
  error: string | null;
  /** 重新查询 */
  refetch: () => void;
}

/**
 * WHY 引擎 — 解释"为什么"
 *
 * 回答：
 * - 为什么这个 event 被执行？
 * - 它依赖哪个 causal path？
 * - 被哪个 policy 放行/阻断？
 * - 是否来自 snapshot replay？
 * - 是否来自 enforcement modification？
 *
 * @param trace_id  Trace ID
 * @param event_id  Event ID（可选，不指定则解释整个 trace）
 */
export function useWhy(trace_id: string | null, event_id?: string | null): WhyData {
  const [explanation, setExplanation] = useState<WhyExplanation | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const traceRef = useRef(trace_id);
  traceRef.current = trace_id;
  const eventRef = useRef(event_id);
  eventRef.current = event_id;

  const fetch = useCallback(async () => {
    const tid = traceRef.current;
    if (!tid) {
      setExplanation(null);
      setError(null);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const result = await whyEngine.why(tid, eventRef.current ?? undefined);
      setExplanation(result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setExplanation(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [trace_id, event_id, fetch]);

  return {
    explanation,
    isLoading,
    error,
    refetch: fetch,
  };
}

// ═══════════════════════════════════════════════════════════════
// useCriticalPath — 关键路径报告 Hook
// ═══════════════════════════════════════════════════════════════

export interface CriticalPathData {
  /** 关键路径报告 */
  report: CriticalPathReport | null;
  /** 是否正在分析 */
  isAnalyzing: boolean;
  /** 错误信息 */
  error: string | null;
  /** 重新分析 */
  refetch: () => void;
}

/**
 * 关键路径分析 — 三大热路径
 *
 * - latency_hotpath      — 最高延迟链
 * - causal_hotpath       — 最长因果链
 * - enforcement_hotpath  — 最多策略干预链
 *
 * @param trace_id Trace ID
 */
export function useCriticalPath(trace_id: string | null): CriticalPathData {
  const [report, setReport] = useState<CriticalPathReport | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const traceRef = useRef(trace_id);
  traceRef.current = trace_id;

  const analyze = useCallback(async () => {
    const tid = traceRef.current;
    if (!tid) {
      setReport(null);
      setError(null);
      return;
    }
    setIsAnalyzing(true);
    setError(null);
    try {
      const result = await criticalPathAnalyzer.analyze(tid);
      setReport(result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setReport(null);
    } finally {
      setIsAnalyzing(false);
    }
  }, []);

  useEffect(() => {
    analyze();
  }, [trace_id, analyze]);

  return {
    report,
    isAnalyzing,
    error,
    refetch: analyze,
  };
}

// ═══════════════════════════════════════════════════════════════
// useObservabilityStats — 可观测性统计 Hook（辅助）
// ═══════════════════════════════════════════════════════════════

export interface ObservabilityStatsData {
  /** trace ID 列表 */
  traceIds: string[];
  /** span 总数 */
  totalSpans: number;
  /** 是否正在加载 */
  isLoading: boolean;
}

/**
 * 获取可观测性整体统计 — 用于 Observability 仪表板
 */
export function useObservabilityStats(): ObservabilityStatsData {
  const [traceIds, setTraceIds] = useState<string[]>([]);
  const [totalSpans, setTotalSpans] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const load = async () => {
      setIsLoading(true);
      try {
        const ids = await observabilityStore.getTraceIds();
        setTraceIds(ids);
        let count = 0;
        for (const id of ids) {
          const spans = await observabilityStore.getSpansByTraceId(id);
          count += spans.length;
        }
        setTotalSpans(count);
      } catch (err) {
        console.error("[useObservabilityStats] load error:", err);
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, []);

  return { traceIds, totalSpans, isLoading };
}

// ═══════════════════════════════════════════════════════════════
// useSpanEngine — Span Engine 辅助 Hook（用于手动创建 span）
// ═══════════════════════════════════════════════════════════════

/**
 * 暴露 spanEngine 给 UI 组件使用
 * 用于在 UI 触发操作时创建 span（如手动 replay、snapshot restore）
 */
export function useSpanEngine() {
  return {
    startSpan: spanEngine.startSpan.bind(spanEngine),
    endSpan: spanEngine.endSpan.bind(spanEngine),
    linkSpanToEvent: spanEngine.linkSpanToEvent.bind(spanEngine),
    measureDuration: spanEngine.measureDuration.bind(spanEngine),
  };
}
