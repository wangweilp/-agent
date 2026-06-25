/**
 * 知维 OS Crash Detection Engine — 崩溃检测引擎
 * Zhiwei OS Crash Detection Engine
 *
 * 4 种检测能力：
 * 1. detectSessionBreak()   — 会话中断（CausalKernel 内存丢失但 EventStore 有数据）
 * 2. detectStateCorruption() — 状态损坏（version 与 event count 不匹配）
 * 3. detectEventGap()       — 事件缺口（parent_event_id 指向缺失事件）
 * 4. detectSnapshotDrift()  — 快照漂移（snapshot.cursor 与 event count 不一致）
 *
 * 输入来源：
 * - EventStore（L1 truth）
 * - SnapshotStore（L2 cache）
 * - AuthorityValidator（一致性报告）
 * - ReplayCursor state（L3 内存）
 */

import { causalKernel } from "@/lib/event-bus/causal-kernel";
import { persistencePipeline } from "@/lib/persistence/pipeline";
import { consistencyValidator } from "@/lib/authority/consistency-validator";
import { createInitialState, type SystemState } from "@/lib/replay/types";
import { applyEvent } from "@/lib/replay/state-reducer";
import type { SystemEvent } from "@/types/event-bus";
import type { SystemSnapshot } from "@/lib/persistence/types";
import type {
  CrashReport,
  CrashType,
  CrashSeverity,
  CrashEvidence,
  RecoveryStrategy,
} from "@/lib/self-healing/types";

// ═══════════════════════════════════════════════════════════════
// CrashDetector — 崩溃检测引擎
// ═══════════════════════════════════════════════════════════════

let reportCounter = 0;

export class CrashDetector {
  /**
   * 检测会话中断 — CausalKernel 内存丢失但 EventStore 有数据
   *
   * 场景：浏览器刷新后，CausalKernel 内存清空，但 IndexedDB EventStore 仍有事件
   */
  async detectSessionBreak(trace_id: string): Promise<CrashReport | null> {
    const evidence: CrashEvidence[] = [];

    // 从 EventStore 加载事件
    const persistedEvents = await persistencePipeline.loadEventsByTraceId(trace_id);
    if (persistedEvents.length === 0) return null;

    // 检查 CausalKernel 内存中是否有这些事件
    const memoryEventCount = causalKernel.replay(trace_id).length;

    if (memoryEventCount < persistedEvents.length) {
      evidence.push({
        kind: "session_break",
        description: `CausalKernel memory has ${memoryEventCount} events, but EventStore has ${persistedEvents.length}`,
        expected: persistedEvents.length,
        actual: memoryEventCount,
      });
    }

    if (evidence.length === 0) return null;

    return this.buildReport(
      "CRASH",
      "high",
      trace_id,
      evidence,
      "EVENT_REPLAY",
    );
  }

  /**
   * 检测状态损坏 — version 与 event count 不匹配
   *
   * 场景：状态被篡改或 reducer 出错导致 version 不一致
   */
  async detectStateCorruption(
    trace_id: string,
    currentState: SystemState,
  ): Promise<CrashReport | null> {
    const evidence: CrashEvidence[] = [];

    const events = await this.getEvents(trace_id);
    if (events.length === 0) return null;

    // 重建权威状态
    const rebuiltState = this.rebuildFromEvents(events);

    // version 检查
    if (currentState.version !== rebuiltState.version) {
      evidence.push({
        kind: "version_mismatch",
        description: `State version (${currentState.version}) does not match rebuilt (${rebuiltState.version})`,
        expected: rebuiltState.version,
        actual: currentState.version,
      });
    }

    // kill_switches 数量检查
    if (currentState.runtime.kill_switches.length !== rebuiltState.runtime.kill_switches.length) {
      evidence.push({
        kind: "version_mismatch",
        description: `kill_switches count: current=${currentState.runtime.kill_switches.length}, rebuilt=${rebuiltState.runtime.kill_switches.length}`,
        expected: rebuiltState.runtime.kill_switches.length,
        actual: currentState.runtime.kill_switches.length,
      });
    }

    // memories 数量检查
    if (currentState.memory.memories.size !== rebuiltState.memory.memories.size) {
      evidence.push({
        kind: "version_mismatch",
        description: `memories count: current=${currentState.memory.memories.size}, rebuilt=${rebuiltState.memory.memories.size}`,
        expected: rebuiltState.memory.memories.size,
        actual: currentState.memory.memories.size,
      });
    }

    if (evidence.length === 0) return null;

    return this.buildReport(
      "CORRUPTION",
      "critical",
      trace_id,
      evidence,
      "FORCE_REBUILD",
    );
  }

  /**
   * 检测事件缺口 — parent_event_id 指向缺失事件
   *
   * 场景：事件丢失导致因果链断裂
   */
  async detectEventGap(trace_id: string): Promise<CrashReport | null> {
    const evidence: CrashEvidence[] = [];

    const events = await this.getEvents(trace_id);
    if (events.length === 0) return null;

    const eventIds = new Set(events.map((e) => e.event_id));

    for (const event of events) {
      // 检查主父事件
      if (event.causal.parent_event_id) {
        if (!eventIds.has(event.causal.parent_event_id)) {
          evidence.push({
            kind: "broken_causal",
            description: `Event ${event.event_id} has parent ${event.causal.parent_event_id} not in event stream`,
            event_id: event.event_id,
            expected: "parent event exists",
            actual: "parent event missing",
          });
        }
      }

      // 检查多父因果边
      if (event.causal.causal_links) {
        for (const link of event.causal.causal_links) {
          if (!eventIds.has(link.from)) {
            evidence.push({
              kind: "broken_causal",
              description: `Event ${event.event_id} has causal link from ${link.from} not in event stream`,
              event_id: event.event_id,
              expected: "causal link source exists",
              actual: "causal link source missing",
            });
          }
        }
      }
    }

    if (evidence.length === 0) return null;

    return this.buildReport(
      "EVENT_GAP",
      "critical",
      trace_id,
      evidence,
      "EVENT_REPLAY",
    );
  }

  /**
   * 检测快照漂移 — snapshot.cursor 与 event count 不一致
   *
   * 场景：snapshot 被写入后事件被追加，或 snapshot 损坏
   */
  async detectSnapshotDrift(trace_id: string): Promise<CrashReport | null> {
    const evidence: CrashEvidence[] = [];

    const events = await this.getEvents(trace_id);
    const snapshot = await persistencePipeline.getLatestSnapshot(trace_id);

    if (!snapshot) return null;

    // snapshot.cursor 不应超过事件数
    if (snapshot.cursor > events.length) {
      evidence.push({
        kind: "snapshot_drift",
        description: `Snapshot cursor (${snapshot.cursor}) exceeds event count (${events.length})`,
        snapshot_id: snapshot.snapshot_id,
        expected: events.length,
        actual: snapshot.cursor,
      });
    }

    // snapshot.event_count 应与 cursor 一致
    if (snapshot.event_count !== snapshot.cursor) {
      evidence.push({
        kind: "snapshot_drift",
        description: `Snapshot event_count (${snapshot.event_count}) does not match cursor (${snapshot.cursor})`,
        snapshot_id: snapshot.snapshot_id,
        expected: snapshot.cursor,
        actual: snapshot.event_count,
      });
    }

    // 如果 snapshot.cursor === events.length，则 state.version 应一致
    if (snapshot.cursor === events.length) {
      const rebuiltState = this.rebuildFromEvents(events);
      if (snapshot.state.version !== rebuiltState.version) {
        evidence.push({
          kind: "snapshot_drift",
          description: `Snapshot state.version (${snapshot.state.version}) does not match rebuilt (${rebuiltState.version})`,
          snapshot_id: snapshot.snapshot_id,
          expected: rebuiltState.version,
          actual: snapshot.state.version,
        });
      }
    }

    if (evidence.length === 0) return null;

    return this.buildReport(
      "DRIFT",
      "high",
      trace_id,
      evidence,
      "SNAPSHOT_ROLLBACK",
    );
  }

  /**
   * 全量检测 — 一次性运行所有检测
   */
  async detectAll(trace_id: string, currentState?: SystemState): Promise<CrashReport[]> {
    const reports: CrashReport[] = [];

    const sessionBreak = await this.detectSessionBreak(trace_id);
    if (sessionBreak) reports.push(sessionBreak);

    const stateCorruption = currentState
      ? await this.detectStateCorruption(trace_id, currentState)
      : null;
    if (stateCorruption) reports.push(stateCorruption);

    const eventGap = await this.detectEventGap(trace_id);
    if (eventGap) reports.push(eventGap);

    const snapshotDrift = await this.detectSnapshotDrift(trace_id);
    if (snapshotDrift) reports.push(snapshotDrift);

    return reports;
  }

  // ─────────────────────────────────────────────────────────────
  // 内部方法
  // ─────────────────────────────────────────────────────────────

  private async getEvents(trace_id: string): Promise<SystemEvent[]> {
    // 优先从内存读取，否则从 EventStore 读取
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

  private buildReport(
    type: CrashType,
    severity: CrashSeverity,
    trace_id: string,
    evidence: CrashEvidence[],
    suggestedStrategy: RecoveryStrategy,
  ): CrashReport {
    reportCounter++;
    return {
      report_id: `crash_${Date.now()}_${reportCounter}`,
      type,
      severity,
      trace_id,
      evidence,
      detected_at: new Date().toISOString(),
      needs_recovery: severity === "critical" || severity === "high",
      suggested_strategy: suggestedStrategy,
    };
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const crashDetector = new CrashDetector();
