/**
 * 知维 OS Consistency Validator — 系统一致性验证
 * Zhiwei OS Consistency Validator
 *
 * 职责：
 * validateSystemConsistency(state, eventStore, snapshotStore, graph)
 *
 * 检测维度：
 * 1. state vs event mismatch      — 内存状态与事件流重建结果不一致
 * 2. snapshot drift               — snapshot 与事件重建结果漂移
 * 3. graph inconsistency          — 因果图与事件流不一致
 * 4. causal chain broken          — 因果链断裂
 * 5. cursor state mismatch        — 游标位置与状态不匹配
 * 6. event count mismatch         — 事件计数不一致
 * 7. timestamp order violation    — 时间戳顺序违反
 * 8. origin mismatch              — 事件来源标记不一致
 *
 * 约束：
 * - 只读验证，不修改任何状态
 * - 输出 InconsistencyReport[]
 * - 严重级别分级
 */

import type { SystemEvent, CausalGraph } from "@/types/event-bus";
import type { SystemState } from "@/lib/replay/types";
import type { SystemSnapshot, IEventStore, ISnapshotStore } from "@/lib/persistence/types";
import type {
  ConsistencyReport,
  InconsistencyReport,
  InconsistencySeverity,
} from "@/lib/authority/types";
import { applyEvent } from "@/lib/replay/state-reducer";
import { createInitialState } from "@/lib/replay/types";

// ═══════════════════════════════════════════════════════════════
// ConsistencyValidator — 一致性验证器
// ═══════════════════════════════════════════════════════════════

export class ConsistencyValidator {
  /**
   * 验证系统一致性 — 主入口
   *
   * @param state          当前内存状态（L3）
   * @param events         事件流（L1）
   * @param snapshot      最近 snapshot（L2，可选）
   * @param graph         因果图（L4，可选）
   * @param cursor        当前游标位置（可选）
   * @returns 一致性报告
   */
  validate(
    trace_id: string,
    state: SystemState,
    events: SystemEvent[],
    snapshot: SystemSnapshot | null,
    graph: CausalGraph | null,
    cursor?: number,
  ): ConsistencyReport {
    const inconsistencies: InconsistencyReport[] = [];

    // 1. 从事件流重建权威状态
    const rebuiltState = this.rebuildFromEvents(events);
    const rebuiltEventCount = events.length;

    // 2. state vs event mismatch
    this.checkStateVsEvents(trace_id, state, rebuiltState, events.length, inconsistencies);

    // 3. snapshot drift
    if (snapshot) {
      this.checkSnapshotDrift(trace_id, snapshot, rebuiltState, rebuiltEventCount, inconsistencies);
    }

    // 4. graph inconsistency
    if (graph) {
      this.checkGraphConsistency(trace_id, graph, events, inconsistencies);
    }

    // 5. causal chain broken
    this.checkCausalChain(trace_id, events, inconsistencies);

    // 6. cursor state mismatch
    if (cursor !== undefined) {
      this.checkCursorState(trace_id, cursor, state, events.length, inconsistencies);
    }

    // 7. event count mismatch
    if (snapshot) {
      this.checkEventCount(trace_id, snapshot, events.length, inconsistencies);
    }

    // 8. timestamp order violation
    this.checkTimestampOrder(trace_id, events, inconsistencies);

    // 9. origin mismatch
    this.checkOriginConsistency(trace_id, events, inconsistencies);

    // 生成统计
    const stats = this.computeStats(inconsistencies);

    return {
      validated_at: new Date().toISOString(),
      trace_id,
      passed: stats.critical_count === 0 && stats.high_count === 0,
      inconsistencies,
      stats,
    };
  }

  // ─────────────────────────────────────────────────────────────
  // 检查 1：state vs event mismatch
  // ─────────────────────────────────────────────────────────────

  /**
   * 检查内存状态与事件重建结果是否一致
   */
  private checkStateVsEvents(
    trace_id: string,
    state: SystemState,
    rebuiltState: SystemState,
    eventCount: number,
    inconsistencies: InconsistencyReport[],
  ): void {
    // 版本号应等于事件数
    if (state.version !== eventCount) {
      inconsistencies.push({
        type: "STATE_EVENT_MISMATCH",
        severity: "high",
        description: `State version (${state.version}) does not match event count (${eventCount})`,
        trace_id,
        expected: eventCount,
        actual: state.version,
        suggested_fix: "Rebuild state from event stream using rebuildSystem()",
      });
    }

    // last_applied_event_id 应为最后一个事件的 ID
    if (eventCount > 0) {
      const lastEvent = rebuiltState.last_applied_event_id;
      if (state.last_applied_event_id !== lastEvent) {
        inconsistencies.push({
          type: "STATE_EVENT_MISMATCH",
          severity: "critical",
          description: `State last_applied_event_id (${state.last_applied_event_id}) does not match last event (${lastEvent})`,
          trace_id,
          expected: lastEvent,
          actual: state.last_applied_event_id,
          suggested_fix: "State is stale or corrupted, force rebuild from events",
        });
      }
    }

    // kill_switches 数量应一致
    if (state.runtime.kill_switches.length !== rebuiltState.runtime.kill_switches.length) {
      inconsistencies.push({
        type: "STATE_EVENT_MISMATCH",
        severity: "high",
        description: `Runtime kill_switches count mismatch: state=${state.runtime.kill_switches.length}, rebuilt=${rebuiltState.runtime.kill_switches.length}`,
        trace_id,
        expected: rebuiltState.runtime.kill_switches.length,
        actual: state.runtime.kill_switches.length,
        suggested_fix: "Rebuild runtime state from event stream",
      });
    }

    // memories 数量应一致
    if (state.memory.memories.size !== rebuiltState.memory.memories.size) {
      inconsistencies.push({
        type: "STATE_EVENT_MISMATCH",
        severity: "high",
        description: `Memory count mismatch: state=${state.memory.memories.size}, rebuilt=${rebuiltState.memory.memories.size}`,
        trace_id,
        expected: rebuiltState.memory.memories.size,
        actual: state.memory.memories.size,
        suggested_fix: "Rebuild memory state from event stream",
      });
    }

    // incidents 数量应一致
    if (state.governance.incidents.size !== rebuiltState.governance.incidents.size) {
      inconsistencies.push({
        type: "STATE_EVENT_MISMATCH",
        severity: "medium",
        description: `Incidents count mismatch: state=${state.governance.incidents.size}, rebuilt=${rebuiltState.governance.incidents.size}`,
        trace_id,
        expected: rebuiltState.governance.incidents.size,
        actual: state.governance.incidents.size,
        suggested_fix: "Rebuild governance state from event stream",
      });
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 检查 2：snapshot drift
  // ─────────────────────────────────────────────────────────────

  /**
   * 检查 snapshot 与事件重建结果是否漂移
   */
  private checkSnapshotDrift(
    trace_id: string,
    snapshot: SystemSnapshot,
    rebuiltState: SystemState,
    eventCount: number,
    inconsistencies: InconsistencyReport[],
  ): void {
    // snapshot.cursor 应 <= eventCount
    if (snapshot.cursor > eventCount) {
      inconsistencies.push({
        type: "SNAPSHOT_DRIFT",
        severity: "critical",
        description: `Snapshot cursor (${snapshot.cursor}) exceeds event count (${eventCount})`,
        trace_id,
        expected: eventCount,
        actual: snapshot.cursor,
        suggested_fix: "Snapshot is corrupted or events were lost, rebuild snapshot",
      });
    }

    // snapshot.event_count 应与 cursor 一致
    if (snapshot.event_count !== snapshot.cursor) {
      inconsistencies.push({
        type: "SNAPSHOT_DRIFT",
        severity: "high",
        description: `Snapshot event_count (${snapshot.event_count}) does not match cursor (${snapshot.cursor})`,
        trace_id,
        expected: snapshot.cursor,
        actual: snapshot.event_count,
        suggested_fix: "Recreate snapshot from current event stream",
      });
    }

    // 如果 snapshot.cursor === eventCount，则 snapshot.state 应与 rebuiltState 一致
    if (snapshot.cursor === eventCount) {
      const snapVersion = snapshot.state.version;
      const rebuiltVersion = rebuiltState.version;
      if (snapVersion !== rebuiltVersion) {
        inconsistencies.push({
          type: "SNAPSHOT_DRIFT",
          severity: "high",
          description: `Snapshot state version (${snapVersion}) does not match rebuilt state version (${rebuiltVersion})`,
          trace_id,
          expected: rebuiltVersion,
          actual: snapVersion,
          suggested_fix: "Snapshot is stale, recreate from event stream",
        });
      }
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 检查 3：graph inconsistency
  // ─────────────────────────────────────────────────────────────

  /**
   * 检查因果图与事件流是否一致
   */
  private checkGraphConsistency(
    trace_id: string,
    graph: CausalGraph,
    events: SystemEvent[],
    inconsistencies: InconsistencyReport[],
  ): void {
    const eventIds = new Set(events.map((e) => e.event_id));
    const graphNodeIds = new Set(graph.nodes.keys());

    // graph 节点数应等于事件数
    if (graph.stats.node_count !== events.length) {
      inconsistencies.push({
        type: "GRAPH_INCONSISTENCY",
        severity: "high",
        description: `Graph node count (${graph.stats.node_count}) does not match event count (${events.length})`,
        trace_id,
        expected: events.length,
        actual: graph.stats.node_count,
        suggested_fix: "Rebuild graph from event stream",
      });
    }

    // 检查 graph 中有但事件流中没有的节点
    for (const nodeId of graphNodeIds) {
      if (!eventIds.has(nodeId)) {
        inconsistencies.push({
          type: "GRAPH_INCONSISTENCY",
          severity: "critical",
          description: `Graph contains node ${nodeId} not in event stream`,
          trace_id,
          event_id: nodeId,
          expected: "node should exist in event stream",
          actual: "node missing from events",
          suggested_fix: "Rebuild graph from event stream",
        });
      }
    }

    // 检查事件流中有但 graph 中没有的节点
    for (const event of events) {
      if (!graphNodeIds.has(event.event_id)) {
        inconsistencies.push({
          type: "GRAPH_INCONSISTENCY",
          severity: "medium",
          description: `Event ${event.event_id} not in graph`,
          trace_id,
          event_id: event.event_id,
          expected: "event should be in graph",
          actual: "event missing from graph",
          suggested_fix: "Rebuild graph from event stream",
        });
      }
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 检查 4：causal chain broken
  // ─────────────────────────────────────────────────────────────

  /**
   * 检查因果链是否断裂（parent_event_id 指向不存在的事件）
   */
  private checkCausalChain(
    trace_id: string,
    events: SystemEvent[],
    inconsistencies: InconsistencyReport[],
  ): void {
    const eventIds = new Set(events.map((e) => e.event_id));

    for (const event of events) {
      // 检查主父事件
      if (event.causal.parent_event_id) {
        if (!eventIds.has(event.causal.parent_event_id)) {
          inconsistencies.push({
            type: "CAUSAL_CHAIN_BROKEN",
            severity: "critical",
            description: `Event ${event.event_id} has parent ${event.causal.parent_event_id} not in event stream`,
            trace_id,
            event_id: event.event_id,
            expected: "parent event should exist",
            actual: "parent event missing",
            suggested_fix: "Restore missing parent event or mark as orphan",
          });
        }
      }

      // 检查多父因果边
      if (event.causal.causal_links) {
        for (const link of event.causal.causal_links) {
          if (!eventIds.has(link.from)) {
            inconsistencies.push({
              type: "CAUSAL_CHAIN_BROKEN",
              severity: "high",
              description: `Event ${event.event_id} has causal link from ${link.from} not in event stream`,
              trace_id,
              event_id: event.event_id,
              expected: "causal link source should exist",
              actual: "causal link source missing",
              suggested_fix: "Restore missing source event or remove causal link",
            });
          }
        }
      }
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 检查 5：cursor state mismatch
  // ─────────────────────────────────────────────────────────────

  /**
   * 检查游标位置与状态是否匹配
   */
  private checkCursorState(
    trace_id: string,
    cursor: number,
    state: SystemState,
    eventCount: number,
    inconsistencies: InconsistencyReport[],
  ): void {
    // cursor 应 <= eventCount
    if (cursor > eventCount) {
      inconsistencies.push({
        type: "CURSOR_STATE_MISMATCH",
        severity: "critical",
        description: `Cursor (${cursor}) exceeds event count (${eventCount})`,
        trace_id,
        expected: eventCount,
        actual: cursor,
        suggested_fix: "Reset cursor to event count",
      });
    }

    // state.version 应等于 cursor（如果 cursor 是已应用的事件数）
    if (state.version !== cursor) {
      inconsistencies.push({
        type: "CURSOR_STATE_MISMATCH",
        severity: "high",
        description: `State version (${state.version}) does not match cursor (${cursor})`,
        trace_id,
        expected: cursor,
        actual: state.version,
        suggested_fix: "Rebuild state from cursor position",
      });
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 检查 6：event count mismatch
  // ─────────────────────────────────────────────────────────────

  private checkEventCount(
    trace_id: string,
    snapshot: SystemSnapshot,
    eventCount: number,
    inconsistencies: InconsistencyReport[],
  ): void {
    if (snapshot.event_count > eventCount) {
      inconsistencies.push({
        type: "EVENT_COUNT_MISMATCH",
        severity: "high",
        description: `Snapshot event_count (${snapshot.event_count}) exceeds current event count (${eventCount})`,
        trace_id,
        expected: eventCount,
        actual: snapshot.event_count,
        suggested_fix: "Events may have been lost, check EventStore integrity",
      });
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 检查 7：timestamp order violation
  // ─────────────────────────────────────────────────────────────

  private checkTimestampOrder(
    trace_id: string,
    events: SystemEvent[],
    inconsistencies: InconsistencyReport[],
  ): void {
    for (let i = 1; i < events.length; i++) {
      if (events[i].timestamp < events[i - 1].timestamp) {
        inconsistencies.push({
          type: "TIMESTAMP_ORDER_VIOLATION",
          severity: "low",
          description: `Event ${events[i].event_id} timestamp (${events[i].timestamp}) is before previous event (${events[i - 1].timestamp})`,
          trace_id,
          event_id: events[i].event_id,
          expected: `>= ${events[i - 1].timestamp}`,
          actual: events[i].timestamp,
          suggested_fix: "Sort events by causal order, not timestamp",
        });
        break; // 只报告第一个
      }
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 检查 8：origin mismatch
  // ─────────────────────────────────────────────────────────────

  private checkOriginConsistency(
    trace_id: string,
    events: SystemEvent[],
    inconsistencies: InconsistencyReport[],
  ): void {
    const origins = new Set(events.map((e) => e.origin ?? "simulated"));
    if (origins.size > 1) {
      inconsistencies.push({
        type: "ORIGIN_MISMATCH",
        severity: "medium",
        description: `Trace ${trace_id} contains mixed origins: ${Array.from(origins).join(", ")}`,
        trace_id,
        expected: "single origin per trace",
        actual: Array.from(origins).join(", "),
        suggested_fix: "Separate backend and simulated events into different traces",
      });
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 辅助方法
  // ─────────────────────────────────────────────────────────────

  /**
   * 从事件流重建状态（纯函数，用于验证）
   */
  private rebuildFromEvents(events: SystemEvent[]): SystemState {
    let state = createInitialState();
    for (const event of events) {
      state = applyEvent(state, event);
    }
    return state;
  }

  /**
   * 计算统计
   */
  private computeStats(inconsistencies: InconsistencyReport[]): ConsistencyReport["stats"] {
    const stats = {
      total_checks: inconsistencies.length,
      passed_checks: 0,
      failed_checks: inconsistencies.length,
      critical_count: 0,
      high_count: 0,
      medium_count: 0,
      low_count: 0,
      info_count: 0,
    };

    for (const inc of inconsistencies) {
      switch (inc.severity) {
        case "critical": stats.critical_count++; break;
        case "high": stats.high_count++; break;
        case "medium": stats.medium_count++; break;
        case "low": stats.low_count++; break;
        case "info": stats.info_count++; break;
      }
    }

    return stats;
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const consistencyValidator = new ConsistencyValidator();
