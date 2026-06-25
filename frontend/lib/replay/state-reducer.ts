/**
 * 知维 OS Replay Engine — State Reducer
 * Zhiwei OS Replay Engine — State Reducer
 *
 * L2 Replay Engine 核心：
 * - applyEvent(state, event) → newState  纯函数状态重建
 * - runtime reducer / memory reducer / governance reducer
 *
 * 约束：
 * - 纯函数（无副作用）
 * - deterministic（相同输入 → 相同输出）
 * - 不允许 mutation（始终返回新对象）
 * - 按 event.source 分发到对应 reducer
 */

import type {
  SystemEvent,
  RuntimeEventPayload,
  MemoryEventPayload,
  GovernanceEventPayload,
} from "@/types/event-bus";
import type {
  SystemState,
  RuntimeState,
  MemoryState,
  GovernanceState,
} from "@/lib/replay/types";
import { createInitialState } from "@/lib/replay/types";

// ═══════════════════════════════════════════════════════════════
// applyEvent — 主入口（纯函数）
// ═══════════════════════════════════════════════════════════════

/**
 * 应用事件到状态 — 纯函数，返回新状态
 *
 * @param state 当前状态
 * @param event 要应用的事件
 * @returns 新状态（不修改原状态）
 */
export function applyEvent(state: SystemState, event: SystemEvent): SystemState {
  // 按 source 分发
  let newRuntime = state.runtime;
  let newMemory = state.memory;
  let newGovernance = state.governance;

  switch (event.source) {
    case "runtime":
      newRuntime = applyRuntimeEvent(state.runtime, event);
      break;
    case "memory":
      newMemory = applyMemoryEvent(state.memory, event);
      break;
    case "governance":
      newGovernance = applyGovernanceEvent(state.governance, event);
      break;
    case "agent":
      // Agent 事件不直接修改系统状态（仅影响因果链）
      // 但 agent.tool.completed 可能影响 runtime（如句柄释放）
      break;
    case "observability":
      // Observability 是 overlay，不修改系统状态
      break;
  }

  return {
    runtime: newRuntime,
    memory: newMemory,
    governance: newGovernance,
    version: state.version + 1,
    last_applied_event_id: event.event_id,
    last_applied_timestamp: event.timestamp,
  };
}

// ═══════════════════════════════════════════════════════════════
// Runtime Reducer
// ═══════════════════════════════════════════════════════════════

function applyRuntimeEvent(state: RuntimeState, event: SystemEvent): RuntimeState {
  const payload = event.payload as RuntimeEventPayload;

  switch (event.type) {
    case "runtime.kill_switch.triggered": {
      const p = payload as Extract<RuntimeEventPayload, { target_id: string; reason: string; force: boolean }>;
      return {
        ...state,
        kill_switches: [
          ...state.kill_switches,
          {
            target_id: p.target_id,
            target_type: p.target_type,
            reason: p.reason,
            status: "triggered",
            timestamp: event.timestamp,
          },
        ],
        active_handles: new Set(state.active_handles).add(p.target_id),
      };
    }

    case "runtime.kill_switch.completed": {
      const p = payload as Extract<RuntimeEventPayload, { target_id: string; action_taken: string; status_after: string }>;
      const newActive = new Set(state.active_handles);
      newActive.delete(p.target_id);
      return {
        ...state,
        kill_switches: state.kill_switches.map((k) =>
          k.target_id === p.target_id && k.status === "triggered"
            ? { ...k, status: "completed" as const }
            : k,
        ),
        active_handles: newActive,
      };
    }

    case "runtime.gate.denied": {
      const p = payload as Extract<RuntimeEventPayload, { gate_type: string; target_id: string; violated_rules: string[] }>;
      return {
        ...state,
        gate_decisions: [
          ...state.gate_decisions,
          {
            gate_type: p.gate_type,
            target_id: p.target_id,
            decision: "denied" as const,
            violated_rules: p.violated_rules,
            timestamp: event.timestamp,
          },
        ],
      };
    }

    case "runtime.gate.allowed": {
      const p = payload as Extract<RuntimeEventPayload, { gate_type: string; target_id: string; matched_rules: string[] }>;
      return {
        ...state,
        gate_decisions: [
          ...state.gate_decisions,
          {
            gate_type: p.gate_type,
            target_id: p.target_id,
            decision: "allowed" as const,
            violated_rules: [],
            timestamp: event.timestamp,
          },
        ],
      };
    }

    case "runtime.sandbox.violation": {
      const p = payload as Extract<RuntimeEventPayload, { handle_id: string; violation_type: string; description: string }>;
      return {
        ...state,
        sandbox_events: [
          ...state.sandbox_events,
          {
            handle_id: p.handle_id,
            state: "violation" as const,
            reason: p.description,
            timestamp: event.timestamp,
          },
        ],
      };
    }

    case "runtime.sandbox.terminated": {
      const p = payload as Extract<RuntimeEventPayload, { handle_id: string; reason: string; cleanup_actions: string[] }>;
      const newActive = new Set(state.active_handles);
      newActive.delete(p.handle_id);
      return {
        ...state,
        sandbox_events: [
          ...state.sandbox_events,
          {
            handle_id: p.handle_id,
            state: "terminated" as const,
            reason: p.reason,
            timestamp: event.timestamp,
          },
        ],
        active_handles: newActive,
      };
    }

    case "runtime.handle.cancel_requested": {
      // 句柄取消请求不直接修改状态（等待 runtime.handle.cancelled）
      return state;
    }

    default:
      return state;
  }
}

// ═══════════════════════════════════════════════════════════════
// Memory Reducer
// ═══════════════════════════════════════════════════════════════

function applyMemoryEvent(state: MemoryState, event: SystemEvent): MemoryState {
  const payload = event.payload as MemoryEventPayload;

  switch (event.type) {
    case "memory.write.stm":
    case "memory.write.wm":
    case "memory.write.ltm": {
      const p = payload as Extract<MemoryEventPayload, { memory_id: string; tier: "stm" | "wm" | "ltm"; memory_type: string; content_preview: string; importance: number; source: string; entities: string[] }>;
      const newMemories = new Map(state.memories);
      newMemories.set(p.memory_id, {
        memory_id: p.memory_id,
        tier: p.tier,
        memory_type: p.memory_type,
        content_preview: p.content_preview,
        importance: p.importance,
        source: p.source,
        entities: p.entities,
        timestamp: event.timestamp,
      });
      return { ...state, memories: newMemories };
    }

    case "memory.archive.executed": {
      const p = payload as Extract<MemoryEventPayload, { memory_id: string; archived_at: string; reason: string }>;
      const newMemories = new Map(state.memories);
      const mem = newMemories.get(p.memory_id);
      if (mem) {
        newMemories.set(p.memory_id, { ...mem, tier: "ltm" });
      }
      return { ...state, memories: newMemories };
    }

    case "memory.merge.executed": {
      const p = payload as Extract<MemoryEventPayload, { primary_id: string; merged_ids: string[]; merged_count: number; reason: string }>;
      const newMemories = new Map(state.memories);
      // 合并的 memory 从状态中移除（已合并到 primary）
      for (const id of p.merged_ids) {
        newMemories.delete(id);
      }
      return { ...state, memories: newMemories };
    }

    case "memory.reflection.triggered": {
      const p = payload as Extract<MemoryEventPayload, { trigger_reason: string; scan_scope: string[] }>;
      return {
        ...state,
        reflections: [
          ...state.reflections,
          {
            trigger_reason: p.trigger_reason,
            insights_generated: 0,
            topics: p.scan_scope,
            timestamp: event.timestamp,
          },
        ],
      };
    }

    case "memory.reflection.completed": {
      const p = payload as Extract<MemoryEventPayload, { insights_generated: number; topics: string[]; duration_ms: number }>;
      // 更新最后一个 reflection 的 insights
      const reflections = [...state.reflections];
      if (reflections.length > 0) {
        const last = reflections[reflections.length - 1];
        reflections[reflections.length - 1] = {
          ...last,
          insights_generated: p.insights_generated,
          topics: p.topics,
        };
      }
      return { ...state, reflections };
    }

    case "memory.conflict.detected": {
      const p = payload as Extract<MemoryEventPayload, { memory_ids: string[]; conflict_type: string; description: string }>;
      return {
        ...state,
        conflicts: [
          ...state.conflicts,
          {
            memory_ids: p.memory_ids,
            conflict_type: p.conflict_type,
            timestamp: event.timestamp,
          },
        ],
      };
    }

    case "memory.conflict.resolved": {
      const p = payload as Extract<MemoryEventPayload, { primary_id: string; resolved_ids: string[]; resolution_strategy: string }>;
      // 冲突解决：从 conflicts 中移除已解决的
      const resolvedSet = new Set([p.primary_id, ...p.resolved_ids]);
      return {
        ...state,
        conflicts: state.conflicts.filter(
          (c) => !c.memory_ids.every((id) => resolvedSet.has(id)),
        ),
      };
    }

    case "memory.retrieval.executed": {
      const p = payload as Extract<MemoryEventPayload, { query: string; hits_count: number; top_score: number; duration_ms: number }>;
      return {
        ...state,
        retrievals: [
          ...state.retrievals,
          {
            query: p.query,
            hits_count: p.hits_count,
            timestamp: event.timestamp,
          },
        ],
      };
    }

    default:
      return state;
  }
}

// ═══════════════════════════════════════════════════════════════
// Governance Reducer
// ═══════════════════════════════════════════════════════════════

function applyGovernanceEvent(state: GovernanceState, event: SystemEvent): GovernanceState {
  const payload = event.payload as GovernanceEventPayload;

  switch (event.type) {
    case "governance.policy.evaluated": {
      const p = payload as Extract<GovernanceEventPayload, { policy_id: string; policy_name: string; decision: "allowed" | "denied"; evaluated_rules: string[]; violations: string[]; warnings: string[] }>;
      return {
        ...state,
        policy_evaluations: [
          ...state.policy_evaluations,
          {
            policy_id: p.policy_id,
            policy_name: p.policy_name,
            decision: p.decision,
            violations: p.violations,
            timestamp: event.timestamp,
          },
        ],
      };
    }

    case "governance.policy.violation": {
      const p = payload as Extract<GovernanceEventPayload, { policy_id: string; violation_type: string; description: string; target_id: string }>;
      return {
        ...state,
        blocked_executions: [
          ...state.blocked_executions,
          {
            target_id: p.target_id,
            reason: p.description,
            timestamp: event.timestamp,
          },
        ],
      };
    }

    case "governance.execution.blocked": {
      const p = payload as Extract<GovernanceEventPayload, { target_id: string; target_type: string; blocking_policy: string; reason: string }>;
      return {
        ...state,
        blocked_executions: [
          ...state.blocked_executions,
          {
            target_id: p.target_id,
            reason: p.reason,
            timestamp: event.timestamp,
          },
        ],
      };
    }

    case "governance.audit.record_generated": {
      const p = payload as Extract<GovernanceEventPayload, { audit_id: string; action: string; resource_type: string; resource_id: string; actor: string }>;
      return {
        ...state,
        audit_records: [
          ...state.audit_records,
          {
            audit_id: p.audit_id,
            action: p.action,
            resource_id: p.resource_id,
            actor: p.actor,
            timestamp: event.timestamp,
          },
        ],
      };
    }

    case "governance.incident.created": {
      const p = payload as Extract<GovernanceEventPayload, { incident_id: string; title: string; severity: "critical" | "high" | "medium" | "low"; related_runtime: string; description: string }>;
      const newIncidents = new Map(state.incidents);
      newIncidents.set(p.incident_id, {
        incident_id: p.incident_id,
        title: p.title,
        severity: p.severity,
        status: "open" as const,
        timestamp: event.timestamp,
      });
      return { ...state, incidents: newIncidents };
    }

    case "governance.incident.resolved": {
      const p = payload as Extract<GovernanceEventPayload, { incident_id: string; resolution: string; resolved_by: string; duration_ms: number }>;
      const newIncidents = new Map(state.incidents);
      const incident = newIncidents.get(p.incident_id);
      if (incident) {
        newIncidents.set(p.incident_id, {
          ...incident,
          status: "resolved" as const,
          resolution: p.resolution,
        });
      }
      return { ...state, incidents: newIncidents };
    }

    default:
      return state;
  }
}

// ═══════════════════════════════════════════════════════════════
// executeReplay — 执行完整回放，生成 ReplayFrame[]
// ═══════════════════════════════════════════════════════════════

/**
 * 执行完整回放 — 从事件列表重建状态，生成每一帧
 *
 * @param events 事件列表（按因果顺序）
 * @returns 回放帧数组（每帧包含 state_before + event + state_after）
 */
export function executeReplay(events: SystemEvent[]): {
  frames: import("@/lib/replay/types").ReplayFrame[];
  finalState: SystemState;
} {
  const frames: import("@/lib/replay/types").ReplayFrame[] = [];
  let currentState = createInitialState();
  const executedIds = new Set<string>();

  for (let i = 0; i < events.length; i++) {
    const event = events[i];
    const stateBefore = currentState;

    // 因果顺序验证：parent_event_id 必须已执行
    let applied = true;
    let error: string | undefined;

    if (event.causal.parent_event_id && !executedIds.has(event.causal.parent_event_id)) {
      applied = false;
      error = `parent_event_id ${event.causal.parent_event_id} not yet executed`;
    }

    let stateAfter = currentState;
    if (applied) {
      stateAfter = applyEvent(currentState, event);
      executedIds.add(event.event_id);
    }

    frames.push({
      index: i,
      state_before: stateBefore,
      event,
      state_after: stateAfter,
      applied,
      error,
    });

    currentState = stateAfter;
  }

  return { frames, finalState: currentState };
}
