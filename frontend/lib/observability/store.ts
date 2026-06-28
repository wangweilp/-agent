/**
 * 知维 OS Observability Store — 可观测性持久化层
 * Zhiwei OS Observability Store
 *
 * IndexedDB 持久化：
 * - spans                — 所有 span
 * - traces               — trace 元数据
 * - trace_edges          — span 边
 * - execution_profiles   — 执行画像
 *
 * 支持查询：
 * - time range query
 * - trace replay visualization
 * - critical path extraction
 */

import type {
  SystemTraceEvent,
  SpanEdge,
  ExecutionProfile,
  SpanFilter,
} from "@/lib/observability/types";

// ═══════════════════════════════════════════════════════════════
// ObservabilityStore — 可观测性持久化层
// ═══════════════════════════════════════════════════════════════

const DB_NAME = "zhiwei-os-observability";
const DB_VERSION = 1;
const STORES = {
  SPANS: "spans",
  TRACES: "traces",
  EDGES: "trace_edges",
  PROFILES: "execution_profiles",
} as const;

export class ObservabilityStore {
  private db: IDBDatabase | null = null;
  private useMemory: boolean = false;

  // 内存降级存储
  private memorySpans: Map<string, SystemTraceEvent> = new Map();
  private memoryTraces: Map<string, { trace_id: string; span_count: number; started_at: string; ended_at: string }> = new Map();
  private memoryEdges: SpanEdge[] = [];
  private memoryProfiles: Map<string, ExecutionProfile> = new Map();

  constructor() {
    this.init();
  }

  /**
   * 初始化 IndexedDB
   */
  private init(): void {
    if (typeof indexedDB === "undefined") {
      this.useMemory = true;
      return;
    }

    try {
      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onupgradeneeded = () => {
        const db = request.result;

        // spans store
        if (!db.objectStoreNames.contains(STORES.SPANS)) {
          const spanStore = db.createObjectStore(STORES.SPANS, { keyPath: "span_id" });
          spanStore.createIndex("by_trace", "trace_id", { unique: false });
          spanStore.createIndex("by_event", "event_id", { unique: false });
          spanStore.createIndex("by_parent", "parent_span_id", { unique: false });
          spanStore.createIndex("by_start_time", "start_time", { unique: false });
        }

        // traces store
        if (!db.objectStoreNames.contains(STORES.TRACES)) {
          db.createObjectStore(STORES.TRACES, { keyPath: "trace_id" });
        }

        // trace_edges store
        if (!db.objectStoreNames.contains(STORES.EDGES)) {
          const edgeStore = db.createObjectStore(STORES.EDGES, { keyPath: ["from", "to", "type"] });
          edgeStore.createIndex("by_from", "from", { unique: false });
          edgeStore.createIndex("by_to", "to", { unique: false });
        }

        // execution_profiles store
        if (!db.objectStoreNames.contains(STORES.PROFILES)) {
          const profileStore = db.createObjectStore(STORES.PROFILES, { keyPath: "profile_id" });
          profileStore.createIndex("by_trace", "trace_id", { unique: false });
        }
      };

      request.onsuccess = () => {
        this.db = request.result;
      };

      request.onerror = () => {
        this.useMemory = true;
      };
    } catch {
      this.useMemory = true;
    }
  }

  // ─────────────────────────────────────────────────────────────
  // Span 操作
  // ─────────────────────────────────────────────────────────────

  /**
   * 存储 span
   */
  async putSpan(span: SystemTraceEvent): Promise<void> {
    if (this.useMemory || !this.db) {
      this.memorySpans.set(span.span_id, span);
      return;
    }
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORES.SPANS, "readwrite");
      tx.objectStore(STORES.SPANS).put(span);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  /**
   * 批量存储 span
   */
  async putSpans(spans: SystemTraceEvent[]): Promise<void> {
    if (this.useMemory || !this.db) {
      for (const s of spans) this.memorySpans.set(s.span_id, s);
      return;
    }
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORES.SPANS, "readwrite");
      const store = tx.objectStore(STORES.SPANS);
      for (const s of spans) store.put(s);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  /**
   * 获取单个 span
   */
  async getSpan(span_id: string): Promise<SystemTraceEvent | null> {
    if (this.useMemory || !this.db) {
      return this.memorySpans.get(span_id) ?? null;
    }
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORES.SPANS, "readonly");
      const request = tx.objectStore(STORES.SPANS).get(span_id);
      request.onsuccess = () => resolve(request.result ?? null);
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * 按 trace_id 获取所有 span
   */
  async getSpansByTraceId(trace_id: string): Promise<SystemTraceEvent[]> {
    if (this.useMemory || !this.db) {
      return Array.from(this.memorySpans.values()).filter((s) => s.trace_id === trace_id);
    }
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORES.SPANS, "readonly");
      const index = tx.objectStore(STORES.SPANS).index("by_trace");
      const request = index.getAll(trace_id);
      request.onsuccess = () => resolve(request.result ?? []);
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * 按 event_id 获取 span
   */
  async getSpanByEventId(event_id: string): Promise<SystemTraceEvent | null> {
    if (this.useMemory || !this.db) {
      for (const span of this.memorySpans.values()) {
        if (span.event_id === event_id) return span;
      }
      return null;
    }
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORES.SPANS, "readonly");
      const index = tx.objectStore(STORES.SPANS).index("by_event");
      const request = index.get(event_id);
      request.onsuccess = () => resolve(request.result ?? null);
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * 时间范围查询
   */
  async getSpansByTimeRange(from: string, to: string): Promise<SystemTraceEvent[]> {
    if (this.useMemory || !this.db) {
      return Array.from(this.memorySpans.values())
        .filter((s) => s.start_time >= from && s.start_time <= to)
        .sort((a, b) => a.start_time.localeCompare(b.start_time));
    }
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORES.SPANS, "readonly");
      const index = tx.objectStore(STORES.SPANS).index("by_start_time");
      const range = IDBKeyRange.bound(from, to);
      const request = index.getAll(range);
      request.onsuccess = () => resolve(request.result ?? []);
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * 复合过滤查询
   */
  async querySpans(filter: SpanFilter): Promise<SystemTraceEvent[]> {
    let spans: SystemTraceEvent[];

    if (filter.trace_id) {
      spans = await this.getSpansByTraceId(filter.trace_id);
    } else if (filter.start_time_from && filter.start_time_to) {
      spans = await this.getSpansByTimeRange(filter.start_time_from, filter.start_time_to);
    } else {
      // 全量（内存模式）
      spans = this.useMemory
        ? Array.from(this.memorySpans.values())
        : await this.getAllSpans();
    }

    return spans.filter((s) => {
      if (filter.layer) {
        const layers = Array.isArray(filter.layer) ? filter.layer : [filter.layer];
        if (!layers.includes(s.layer)) return false;
      }
      if (filter.service) {
        const services = Array.isArray(filter.service) ? filter.service : [filter.service];
        if (!services.includes(s.service)) return false;
      }
      if (filter.kind) {
        const kinds = Array.isArray(filter.kind) ? filter.kind : [filter.kind];
        if (!kinds.includes(s.kind)) return false;
      }
      if (filter.status) {
        const statuses = Array.isArray(filter.status) ? filter.status : [filter.status];
        if (!statuses.includes(s.status)) return false;
      }
      if (filter.min_duration_ms !== undefined && (s.duration_ms ?? 0) < filter.min_duration_ms) return false;
      if (filter.max_duration_ms !== undefined && (s.duration_ms ?? 0) > filter.max_duration_ms) return false;
      return true;
    });
  }

  /**
   * 获取所有 span（用于全量查询）
   */
  private async getAllSpans(): Promise<SystemTraceEvent[]> {
    if (this.useMemory || !this.db) {
      return Array.from(this.memorySpans.values());
    }
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORES.SPANS, "readonly");
      const request = tx.objectStore(STORES.SPANS).getAll();
      request.onsuccess = () => resolve(request.result ?? []);
      request.onerror = () => reject(request.error);
    });
  }

  // ─────────────────────────────────────────────────────────────
  // Edge 操作
  // ─────────────────────────────────────────────────────────────

  /**
   * 存储边
   */
  async putEdge(edge: SpanEdge): Promise<void> {
    if (this.useMemory || !this.db) {
      // 避免重复
      const exists = this.memoryEdges.some(
        (e) => e.from === edge.from && e.to === edge.to && e.type === edge.type,
      );
      if (!exists) this.memoryEdges.push(edge);
      return;
    }
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORES.EDGES, "readwrite");
      tx.objectStore(STORES.EDGES).put(edge);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  /**
   * 获取 trace 的所有边
   */
  async getEdgesByTraceId(trace_id: string): Promise<SpanEdge[]> {
    // 先获取 trace 所有 span_id，然后过滤 edges
    const spans = await this.getSpansByTraceId(trace_id);
    const spanIds = new Set(spans.map((s) => s.span_id));

    if (this.useMemory || !this.db) {
      return this.memoryEdges.filter((e) => spanIds.has(e.from) && spanIds.has(e.to));
    }

    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORES.EDGES, "readonly");
      const request = tx.objectStore(STORES.EDGES).getAll();
      request.onsuccess = () => {
        const allEdges = (request.result ?? []) as SpanEdge[];
        resolve(allEdges.filter((e) => spanIds.has(e.from) && spanIds.has(e.to)));
      };
      request.onerror = () => reject(request.error);
    });
  }

  // ─────────────────────────────────────────────────────────────
  // Trace 操作
  // ─────────────────────────────────────────────────────────────

  /**
   * 记录 trace 元数据
   */
  async putTrace(trace: {
    trace_id: string;
    span_count: number;
    started_at: string;
    ended_at: string;
  }): Promise<void> {
    if (this.useMemory || !this.db) {
      this.memoryTraces.set(trace.trace_id, trace);
      return;
    }
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORES.TRACES, "readwrite");
      tx.objectStore(STORES.TRACES).put(trace);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  /**
   * 获取所有 trace_id
   */
  async getTraceIds(): Promise<string[]> {
    if (this.useMemory || !this.db) {
      return Array.from(this.memoryTraces.keys());
    }
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORES.TRACES, "readonly");
      const request = tx.objectStore(STORES.TRACES).getAllKeys();
      request.onsuccess = () => resolve((request.result ?? []) as string[]);
      request.onerror = () => reject(request.error);
    });
  }

  // ─────────────────────────────────────────────────────────────
  // Execution Profile 操作
  // ─────────────────────────────────────────────────────────────

  /**
   * 存储执行画像
   */
  async putProfile(profile: ExecutionProfile): Promise<void> {
    if (this.useMemory || !this.db) {
      this.memoryProfiles.set(profile.profile_id, profile);
      return;
    }
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORES.PROFILES, "readwrite");
      tx.objectStore(STORES.PROFILES).put(profile);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  /**
   * 获取 trace 的执行画像
   */
  async getProfileByTraceId(trace_id: string): Promise<ExecutionProfile | null> {
    if (this.useMemory || !this.db) {
      for (const p of this.memoryProfiles.values()) {
        if (p.trace_id === trace_id) return p;
      }
      return null;
    }
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORES.PROFILES, "readonly");
      const index = tx.objectStore(STORES.PROFILES).index("by_trace");
      const request = index.get(trace_id);
      request.onsuccess = () => resolve(request.result ?? null);
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * 清空所有数据
   */
  async clear(): Promise<void> {
    if (this.useMemory || !this.db) {
      this.memorySpans.clear();
      this.memoryTraces.clear();
      this.memoryEdges = [];
      this.memoryProfiles.clear();
      return;
    }
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(
        [STORES.SPANS, STORES.TRACES, STORES.EDGES, STORES.PROFILES],
        "readwrite",
      );
      tx.objectStore(STORES.SPANS).clear();
      tx.objectStore(STORES.TRACES).clear();
      tx.objectStore(STORES.EDGES).clear();
      tx.objectStore(STORES.PROFILES).clear();
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const observabilityStore = new ObservabilityStore();
