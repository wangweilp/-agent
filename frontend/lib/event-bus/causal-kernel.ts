/**
 * 知维 OS 因果内核 — Event Bus 核心实现（v2 图结构版）
 * Zhiwei OS Causal Kernel — Event Bus Core (v2 Graph)
 *
 * v2 升级 — 修复 3 个结构性风险：
 * 1. 风险1修复：环形缓冲保留策略 — trace_id_lock 保证因果完整性，被锁定 trace 永久保留
 * 2. 风险2修复：因果关系从树升级为图 — causal_links 支持多父节点，构建 DAG
 * 3. 风险3修复：Event Projection Layer — project() 投影能力，防止 UI flood
 *
 * 核心能力：
 * - publish(event)       发布事件（存储 + 通知订阅者）
 * - subscribe(filter)    订阅事件流（支持多维度过滤）
 * - replay(trace_id)     回放指定 trace 的完整事件链
 * - getEvent(id)         获取单个事件
 * - getCausalChain(id)  构建因果链树（向后兼容）
 * - getCausalPath(id)    获取从根到指定事件的因果路径
 * - lockTrace(id)        锁定 trace（永久保留，防止覆盖）
 * - project(params)      Event Projection Layer（投影子图）
 */

import type {
  SystemEvent,
  EventFilter,
  EventHandler,
  SubscriptionHandle,
  CreateEventParams,
  CausalChainNode,
  CausalPath,
  EventSource,
  EventSeverity,
  CauseType,
  CausalLink,
  CausalRelation,
  RetentionPolicy,
  ProjectionParams,
  ProjectionResult,
  CausalGraph,
  CausalGraphNode,
  CausalGraphEdge,
} from "@/types/event-bus";

// ═══════════════════════════════════════════════════════════════
// 内部数据结构
// ═══════════════════════════════════════════════════════════════

interface Subscriber {
  id: string;
  filter: EventFilter;
  handler: EventHandler;
}

interface EventStore {
  /** 环形缓冲 — 仅存储未锁定 trace 的事件 */
  ringBuffer: SystemEvent[];
  /** event_id → 环形缓冲索引位置（仅未锁定事件） */
  ringIndex: Map<string, number>;

  /** 永久存储 — 被锁定 trace 的事件（保证因果完整性） */
  pinnedEvents: Map<string, SystemEvent>;

  /** event_id → 事件引用（统一查找入口，指向 ringBuffer 或 pinnedEvents） */
  byEventId: Map<string, { kind: "ring" | "pinned"; index: number }>;

  /** trace_id → event_id 列表（回放用） */
  byTraceId: Map<string, string[]>;

  /** event_id → 子事件 ID 列表（因果链遍历用，树结构索引） */
  childrenIndex: Map<string, string[]>;

  /** event_id → 入边列表（图结构索引，多父支持） */
  inEdgesIndex: Map<string, CausalLink[]>;

  /** event_id → 出边列表（图结构索引，下游遍历用） */
  outEdgesIndex: Map<string, CausalLink[]>;

  /** 环形缓冲容量 */
  capacity: number;
  /** 环形缓冲写入位置 */
  head: number;
}

// ═══════════════════════════════════════════════════════════════
// CausalKernel — 因果内核单例（v2）
// ═══════════════════════════════════════════════════════════════

class CausalKernel {
  private store: EventStore;
  private subscribers: Map<string, Subscriber> = new Map();
  private subscriberCounter = 0;

  /** 保留策略 — 风险1修复核心 */
  private retention: RetentionPolicy;

  /** 全局事件计数器 */
  private stats = {
    totalPublished: 0,
    totalSubscribers: 0,
    pinnedCount: 0,
    evictedCount: 0,
  };

  constructor(capacity = 10000) {
    this.store = {
      ringBuffer: new Array(capacity),
      ringIndex: new Map(),
      pinnedEvents: new Map(),
      byEventId: new Map(),
      byTraceId: new Map(),
      childrenIndex: new Map(),
      inEdgesIndex: new Map(),
      outEdgesIndex: new Map(),
      capacity,
      head: 0,
    };
    // 默认保留策略：trace_id_lock=true，所有 trace 自动锁定
    this.retention = {
      trace_id_lock: true,
      locked_traces: new Set(),
      ring_capacity: capacity,
    };
  }

  // ─────────────────────────────────────────────────────────────
  // 保留策略管理（风险1修复）
  // ─────────────────────────────────────────────────────────────

  /**
   * 显式锁定 trace — 永久保留该 trace 的所有事件
   */
  lockTrace(trace_id: string): void {
    this.retention.locked_traces.add(trace_id);
  }

  /**
   * 解锁 trace — 允许该 trace 的事件被环形缓冲覆盖
   */
  unlockTrace(trace_id: string): void {
    this.retention.locked_traces.delete(trace_id);
    // 将该 trace 的事件从 pinned 迁移到环形缓冲
    const eventIds = this.store.byTraceId.get(trace_id) || [];
    for (const eid of eventIds) {
      const ref = this.store.byEventId.get(eid);
      if (ref?.kind === "pinned") {
        const event = this.store.pinnedEvents.get(eid);
        if (event) {
          this.store.pinnedEvents.delete(eid);
          this.stats.pinnedCount--;
          this.writeToRing(event);
        }
      }
    }
  }

  /**
   * 设置保留策略
   */
  setRetentionPolicy(policy: Partial<RetentionPolicy>): void {
    this.retention = { ...this.retention, ...policy };
  }

  /**
   * 判断 trace 是否应被锁定（永久保留）
   */
  private shouldLockTrace(trace_id: string): boolean {
    if (this.retention.trace_id_lock) return true;
    return this.retention.locked_traces.has(trace_id);
  }

  // ─────────────────────────────────────────────────────────────
  // 事件发布
  // ─────────────────────────────────────────────────────────────

  /**
   * 发布事件 — 因果内核核心入口
   * 1. 根据保留策略决定存储位置（pinned 或 ring）
   * 2. 更新索引（event_id / trace_id / children / edges）
   * 3. 同步通知所有匹配的订阅者
   */
  publish(event: SystemEvent): void {
    const shouldLock = this.shouldLockTrace(event.trace_id);

    if (shouldLock) {
      // 风险1修复：锁定 trace 存入永久存储，永不被覆盖
      this.store.pinnedEvents.set(event.event_id, event);
      this.store.byEventId.set(event.event_id, { kind: "pinned", index: -1 });
      this.stats.pinnedCount++;
    } else {
      this.writeToRing(event);
    }

    // 更新 trace_id 索引
    const traceEvents = this.store.byTraceId.get(event.trace_id) || [];
    traceEvents.push(event.event_id);
    this.store.byTraceId.set(event.trace_id, traceEvents);

    // 更新因果索引（风险2修复：同时支持树和图）
    this.indexCausalEdges(event);

    this.stats.totalPublished++;

    // 通知订阅者（同步，保证事件顺序）
    for (const subscriber of this.subscribers.values()) {
      if (this.matchFilter(event, subscriber.filter)) {
        try {
          subscriber.handler(event);
        } catch (err) {
          console.error("[CausalKernel] subscriber handler error:", err);
        }
      }
    }
  }

  /**
   * 写入环形缓冲（未锁定事件）
   */
  private writeToRing(event: SystemEvent): void {
    const idx = this.store.head;
    // 记录被覆盖的旧事件（清理索引）
    const old = this.store.ringBuffer[idx];
    if (old) {
      this.store.ringIndex.delete(old.event_id);
      this.store.byEventId.delete(old.event_id);
      this.stats.evictedCount++;
    }
    this.store.ringBuffer[idx] = event;
    this.store.ringIndex.set(event.event_id, idx);
    this.store.byEventId.set(event.event_id, { kind: "ring", index: idx });
    this.store.head = (this.store.head + 1) % this.store.capacity;
  }

  /**
   * 索引因果边（风险2修复：图结构支持多父）
   */
  private indexCausalEdges(event: SystemEvent): void {
    const links = this.collectCausalLinks(event);

    for (const link of links) {
      // childrenIndex（向后兼容树结构）
      const children = this.store.childrenIndex.get(link.from) || [];
      if (!children.includes(event.event_id)) {
        children.push(event.event_id);
        this.store.childrenIndex.set(link.from, children);
      }

      // inEdgesIndex（图结构：本事件的入边）
      const inEdges = this.store.inEdgesIndex.get(event.event_id) || [];
      inEdges.push(link);
      this.store.inEdgesIndex.set(event.event_id, inEdges);

      // outEdgesIndex（图结构：父事件的出边）
      const outEdges = this.store.outEdgesIndex.get(link.from) || [];
      outEdges.push({ from: link.from, relation: link.relation, weight: link.weight ?? 1.0 });
      this.store.outEdgesIndex.set(link.from, outEdges);
    }
  }

  /**
   * 收集事件的所有因果边（兼容单父 + 多父）
   */
  private collectCausalLinks(event: SystemEvent): CausalLink[] {
    const links: CausalLink[] = [];

    // 单父（向后兼容）
    if (event.causal.parent_event_id) {
      links.push({
        from: event.causal.parent_event_id,
        relation: "caused_by",
        weight: 1.0,
      });
    }

    // 多父（图结构）
    if (event.causal.causal_links) {
      for (const link of event.causal.causal_links) {
        // 避免重复添加主父边
        const isPrimary = link.from === event.causal.parent_event_id && link.relation === "caused_by";
        if (!isPrimary) {
          links.push(link);
        }
      }
    }

    return links;
  }

  /**
   * 创建并发布事件（便捷方法）
   */
  emit(params: CreateEventParams): SystemEvent {
    const event: SystemEvent = {
      event_id: this.generateEventId(),
      timestamp: new Date().toISOString(),
      source: params.source,
      type: params.type,
      severity: params.severity,
      trace_id: params.trace_id,
      payload: params.payload,
      causal: params.causal,
      origin: "simulated",
    };
    this.publish(event);
    return event;
  }

  // ─────────────────────────────────────────────────────────────
  // 订阅
  // ─────────────────────────────────────────────────────────────

  subscribe(filter: EventFilter, handler: EventHandler): SubscriptionHandle {
    const id = `sub_${++this.subscriberCounter}`;
    this.subscribers.set(id, { id, filter, handler });
    this.stats.totalSubscribers++;
    return {
      id,
      unsubscribe: () => { this.subscribers.delete(id); },
    };
  }

  subscribeAll(handler: EventHandler): SubscriptionHandle {
    return this.subscribe({}, handler);
  }

  // ─────────────────────────────────────────────────────────────
  // 回放与查询
  // ─────────────────────────────────────────────────────────────

  /**
   * 回放指定 trace 的完整事件链（保证因果完整性）
   */
  replay(trace_id: string): SystemEvent[] {
    const eventIds = this.store.byTraceId.get(trace_id) || [];
    return eventIds
      .map((id) => this.getEvent(id))
      .filter((e): e is SystemEvent => e !== null)
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  }

  /**
   * 获取单个事件（统一查找入口）
   */
  getEvent(event_id: string): SystemEvent | null {
    const ref = this.store.byEventId.get(event_id);
    if (!ref) return null;
    if (ref.kind === "pinned") {
      return this.store.pinnedEvents.get(event_id) ?? null;
    }
    return this.store.ringBuffer[ref.index] ?? null;
  }

  /**
   * 获取所有事件（按时间倒序）
   */
  getRecentEvents(limit = 100): SystemEvent[] {
    const result: SystemEvent[] = [];
    // 合并 pinned + ring
    for (const event of this.store.pinnedEvents.values()) {
      result.push(event);
    }
    const ringTotal = Math.min(limit, this.stats.totalPublished - this.stats.pinnedCount);
    let cursor = (this.store.head - 1 + this.store.capacity) % this.store.capacity;
    for (let i = 0; i < ringTotal; i++) {
      const event = this.store.ringBuffer[cursor];
      if (event) result.push(event);
      cursor = (cursor - 1 + this.store.capacity) % this.store.capacity;
    }
    return result
      .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
      .slice(0, limit);
  }

  /**
   * 获取所有 trace_id 列表
   */
  getTraceIds(): string[] {
    return Array.from(this.store.byTraceId.keys());
  }

  // ─────────────────────────────────────────────────────────────
  // 因果链能力（树 + 图）
  // ─────────────────────────────────────────────────────────────

  /**
   * 构建因果链树（向后兼容，基于主父事件）
   */
  getCausalChain(event_id: string): CausalChainNode | null {
    const event = this.getEvent(event_id);
    if (!event) return null;
    return this.buildCausalNode(event, 0, new Set());
  }

  /**
   * 获取因果路径（基于主父事件）
   */
  getCausalPath(event_id: string): CausalPath | null {
    const event = this.getEvent(event_id);
    if (!event) return null;

    const path: SystemEvent[] = [event];
    let current = event;
    const visited = new Set<string>([event.event_id]);

    while (current.causal.parent_event_id) {
      if (visited.has(current.causal.parent_event_id)) break; // 防环
      visited.add(current.causal.parent_event_id);
      const parent = this.getEvent(current.causal.parent_event_id);
      if (!parent) break;
      path.unshift(parent);
      current = parent;
    }

    return { events: path, depth: path.length };
  }

  /**
   * 获取指定事件的所有父事件（图结构：多父支持）
   */
  getParents(event_id: string): SystemEvent[] {
    const inEdges = this.store.inEdgesIndex.get(event_id) || [];
    return inEdges
      .map((link) => this.getEvent(link.from))
      .filter((e): e is SystemEvent => e !== null);
  }

  /**
   * 获取指定事件的所有子事件（直接子节点）
   */
  getChildren(event_id: string): SystemEvent[] {
    const childIds = this.store.childrenIndex.get(event_id) || [];
    return childIds
      .map((id) => this.getEvent(id))
      .filter((e): e is SystemEvent => e !== null);
  }

  /**
   * 获取指定事件的入边（图结构）
   */
  getInEdges(event_id: string): CausalLink[] {
    return this.store.inEdgesIndex.get(event_id) || [];
  }

  /**
   * 获取指定事件的出边（图结构）
   */
  getOutEdges(event_id: string): CausalLink[] {
    return this.store.outEdgesIndex.get(event_id) || [];
  }

  /**
   * 获取根事件
   */
  getRootEvent(event_id: string): SystemEvent | null {
    const path = this.getCausalPath(event_id);
    if (!path || path.events.length === 0) return null;
    return path.events[0];
  }

  // ─────────────────────────────────────────────────────────────
  // Event Projection Layer（风险3修复）
  // ─────────────────────────────────────────────────────────────

  /**
   * 投影 — 从全量事件流中提取子图，防止 UI flood
   * 支持：trace_id / source / severity / time_range 维度投影
   */
  project(params: ProjectionParams): ProjectionResult {
    const allEvents = this.getRecentEvents(this.store.capacity + this.stats.pinnedCount);
    let filtered = allEvents;

    if (params.dimension === "trace_id" && params.trace_id) {
      filtered = allEvents.filter((e) => e.trace_id === params.trace_id);
    } else if (params.dimension === "source" && params.source) {
      const sources = Array.isArray(params.source) ? params.source : [params.source];
      filtered = allEvents.filter((e) => sources.includes(e.source));
    } else if (params.dimension === "severity" && params.severity) {
      const severities = Array.isArray(params.severity) ? params.severity : [params.severity];
      filtered = allEvents.filter((e) => severities.includes(e.severity));
    } else if (params.dimension === "time_range") {
      filtered = allEvents.filter((e) => {
        if (params.time_from && e.timestamp < params.time_from) return false;
        if (params.time_to && e.timestamp > params.time_to) return false;
        return true;
      });
    }

    // 限制节点数
    const maxNodes = params.max_nodes ?? 500;
    if (filtered.length > maxNodes) {
      filtered = filtered.slice(0, maxNodes);
    }

    // 构建子图
    const graph = this.buildGraphFromEvents(filtered, params.trace_id || "projection");

    return {
      graph,
      total_events_scanned: allEvents.length,
      filtered_events: filtered.length,
    };
  }

  /**
   * 从事件列表构建因果图
   */
  private buildGraphFromEvents(events: SystemEvent[], trace_id: string): CausalGraph {
    const nodes = new Map<string, CausalGraphNode>();
    const edges: CausalGraphEdge[] = [];
    const eventSet = new Set(events.map((e) => e.event_id));

    // 构建节点
    for (const event of events) {
      nodes.set(event.event_id, {
        event_id: event.event_id,
        type: event.type,
        source: event.source,
        timestamp: event.timestamp,
        severity: event.severity,
        trace_id: event.trace_id,
      });
    }

    // 构建边（仅包含两端都在子图中的边）
    for (const event of events) {
      const links = this.collectCausalLinks(event);
      for (const link of links) {
        if (eventSet.has(link.from) && eventSet.has(event.event_id)) {
          edges.push({
            from: link.from,
            to: event.event_id,
            relation: link.relation,
            weight: link.weight ?? 1.0,
          });
        }
      }
    }

    // 计算统计
    const inDegree = new Map<string, number>();
    const outDegree = new Map<string, number>();
    for (const node of nodes.keys()) {
      inDegree.set(node, 0);
      outDegree.set(node, 0);
    }
    for (const edge of edges) {
      inDegree.set(edge.to, (inDegree.get(edge.to) || 0) + 1);
      outDegree.set(edge.from, (outDegree.get(edge.from) || 0) + 1);
    }
    let rootCount = 0;
    let leafCount = 0;
    for (const node of nodes.keys()) {
      if ((inDegree.get(node) || 0) === 0) rootCount++;
      if ((outDegree.get(node) || 0) === 0) leafCount++;
    }

    return {
      nodes,
      edges,
      trace_id,
      stats: {
        node_count: nodes.size,
        edge_count: edges.length,
        root_count: rootCount,
        leaf_count: leafCount,
        max_depth: 0, // 由 Graph Engine 计算
      },
    };
  }

  // ─────────────────────────────────────────────────────────────
  // 统计
  // ─────────────────────────────────────────────────────────────

  getStats() {
    return {
      ...this.stats,
      activeSubscribers: this.subscribers.size,
      storedEvents: this.stats.pinnedCount + Math.min(
        this.stats.totalPublished - this.stats.pinnedCount,
        this.store.capacity,
      ),
      traceCount: this.store.byTraceId.size,
      lockedTraces: this.retention.locked_traces.size,
      traceLockEnabled: this.retention.trace_id_lock,
    };
  }

  getStatsBySource(): Record<EventSource, number> {
    const counts: Record<EventSource, number> = {
      runtime: 0, memory: 0, governance: 0, agent: 0, observability: 0,
    };
    for (const event of this.getRecentEvents(this.store.capacity + this.stats.pinnedCount)) {
      counts[event.source]++;
    }
    return counts;
  }

  getStatsBySeverity(): Record<EventSeverity, number> {
    const counts: Record<EventSeverity, number> = { info: 0, warn: 0, critical: 0 };
    for (const event of this.getRecentEvents(this.store.capacity + this.stats.pinnedCount)) {
      counts[event.severity]++;
    }
    return counts;
  }

  // ─────────────────────────────────────────────────────────────
  // 内部方法
  // ─────────────────────────────────────────────────────────────

  private buildCausalNode(event: SystemEvent, depth: number, visited: Set<string>): CausalChainNode {
    if (visited.has(event.event_id)) {
      return { event, children: [], depth };
    }
    visited.add(event.event_id);

    const childIds = this.store.childrenIndex.get(event.event_id) || [];
    const children = childIds
      .map((id) => this.getEvent(id))
      .filter((e): e is SystemEvent => e !== null)
      .map((child) => this.buildCausalNode(child, depth + 1, visited));

    return { event, children, depth };
  }

  private matchFilter(event: SystemEvent, filter: EventFilter): boolean {
    if (filter.source) {
      if (Array.isArray(filter.source)) {
        if (!filter.source.includes(event.source)) return false;
      } else if (event.source !== filter.source) return false;
    }
    if (filter.type) {
      if (Array.isArray(filter.type)) {
        if (!filter.type.includes(event.type)) return false;
      } else if (event.type !== filter.type) return false;
    }
    if (filter.severity) {
      if (Array.isArray(filter.severity)) {
        if (!filter.severity.includes(event.severity)) return false;
      } else if (event.severity !== filter.severity) return false;
    }
    if (filter.trace_id && event.trace_id !== filter.trace_id) return false;
    if (filter.predicate && !filter.predicate(event)) return false;
    return true;
  }

  private generateEventId(): string {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return `evt_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
  }

  reset(): void {
    this.store.ringBuffer = new Array(this.store.capacity);
    this.store.ringIndex.clear();
    this.store.pinnedEvents.clear();
    this.store.byEventId.clear();
    this.store.byTraceId.clear();
    this.store.childrenIndex.clear();
    this.store.inEdgesIndex.clear();
    this.store.outEdgesIndex.clear();
    this.store.head = 0;
    this.stats = { totalPublished: 0, totalSubscribers: 0, pinnedCount: 0, evictedCount: 0 };
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const causalKernel = new CausalKernel(10000);

// ═══════════════════════════════════════════════════════════════
// 便捷工厂函数
// ═══════════════════════════════════════════════════════════════

/** 创建根事件（因果链起点） */
export function createRootEvent(
  source: EventSource,
  type: CreateEventParams["type"],
  severity: EventSeverity,
  trace_id: string,
  payload: CreateEventParams["payload"],
  cause_type: CauseType = "user_action",
  cause_metadata?: Record<string, unknown>,
): SystemEvent {
  return causalKernel.emit({
    source, type, severity, trace_id, payload,
    causal: { parent_event_id: null, cause_type, cause_metadata },
  });
}

/** 创建子事件（单父，向后兼容） */
export function createChildEvent(
  parent: SystemEvent,
  source: EventSource,
  type: CreateEventParams["type"],
  severity: EventSeverity,
  payload: CreateEventParams["payload"],
  cause_type: CauseType = "system_event",
  cause_metadata?: Record<string, unknown>,
): SystemEvent {
  return causalKernel.emit({
    source, type, severity,
    trace_id: parent.trace_id,
    payload,
    causal: { parent_event_id: parent.event_id, cause_type, cause_metadata },
  });
}

/**
 * 创建多父事件（图结构核心）— 一个事件由多个事件共同导致
 * @param parents 父事件列表（含关系类型）
 * @param primaryParent 主父事件（用于 trace_id 继承与向后兼容）
 */
export function createMultiCausalEvent(
  parents: Array<{ event: SystemEvent; relation: CausalRelation; weight?: number }>,
  primaryParent: SystemEvent,
  source: EventSource,
  type: CreateEventParams["type"],
  severity: EventSeverity,
  payload: CreateEventParams["payload"],
  cause_type: CauseType = "system_event",
  cause_metadata?: Record<string, unknown>,
): SystemEvent {
  const causal_links = parents
    .filter((p) => p.event.event_id !== primaryParent.event_id)
    .map((p) => ({
      from: p.event.event_id,
      relation: p.relation,
      weight: p.weight ?? 1.0,
    }));

  return causalKernel.emit({
    source, type, severity,
    trace_id: primaryParent.trace_id,
    payload,
    causal: {
      parent_event_id: primaryParent.event_id,
      cause_type,
      cause_metadata,
      causal_links,
    },
  });
}

/** 生成新的 trace_id */
export function newTraceId(prefix = "trace"): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `${prefix}_${crypto.randomUUID()}`;
  }
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
}
