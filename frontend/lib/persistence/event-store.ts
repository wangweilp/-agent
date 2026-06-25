/**
 * 知维 OS Persistence Layer — EventStore 实现
 * Zhiwei OS Persistence Layer — EventStore Implementations
 *
 * 提供两种实现：
 * 1. MemoryEventStore   — 内存实现（向后兼容，默认）
 * 2. IndexedDBEventStore — 浏览器持久化实现（crash restart 可恢复）
 *
 * 两者实现相同的 IEventStore 接口，可互换
 */

import type { SystemEvent } from "@/types/event-bus";
import type { IEventStore } from "@/lib/persistence/types";

// ═══════════════════════════════════════════════════════════════
// MemoryEventStore — 内存实现（向后兼容）
// ═══════════════════════════════════════════════════════════════

/**
 * 内存 EventStore — 不持久化，刷新即丢
 * 用于开发环境或不需要持久化的场景
 */
export class MemoryEventStore implements IEventStore {
  private events: Map<string, SystemEvent> = new Map();
  private traceIndex: Map<string, string[]> = new Map();
  private timeIndex: Array<{ id: string; ts: string }> = [];

  async put(event: SystemEvent): Promise<void> {
    this.events.set(event.event_id, event);

    // trace 索引
    const traceEvents = this.traceIndex.get(event.trace_id) || [];
    traceEvents.push(event.event_id);
    this.traceIndex.set(event.trace_id, traceEvents);

    // 时间索引
    this.timeIndex.push({ id: event.event_id, ts: event.timestamp });
    this.timeIndex.sort((a, b) => a.ts.localeCompare(b.ts));
  }

  async putBatch(events: SystemEvent[]): Promise<void> {
    for (const event of events) {
      await this.put(event);
    }
  }

  async get(event_id: string): Promise<SystemEvent | null> {
    return this.events.get(event_id) ?? null;
  }

  async getByTraceId(trace_id: string): Promise<SystemEvent[]> {
    const ids = this.traceIndex.get(trace_id) || [];
    return ids
      .map((id) => this.events.get(id))
      .filter((e): e is SystemEvent => e !== null)
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  }

  async getByTimeRange(from: string, to: string): Promise<SystemEvent[]> {
    return this.timeIndex
      .filter((entry) => entry.ts >= from && entry.ts <= to)
      .map((entry) => this.events.get(entry.id))
      .filter((e): e is SystemEvent => e !== null)
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  }

  async getTraceIds(): Promise<string[]> {
    return Array.from(this.traceIndex.keys());
  }

  async delete(event_id: string): Promise<void> {
    const event = this.events.get(event_id);
    if (event) {
      this.events.delete(event_id);
      // 清理 trace 索引
      const traceEvents = this.traceIndex.get(event.trace_id) || [];
      const idx = traceEvents.indexOf(event_id);
      if (idx >= 0) traceEvents.splice(idx, 1);
      // 清理时间索引
      this.timeIndex = this.timeIndex.filter((entry) => entry.id !== event_id);
    }
  }

  async clear(): Promise<void> {
    this.events.clear();
    this.traceIndex.clear();
    this.timeIndex = [];
  }

  async count(): Promise<number> {
    return this.events.size;
  }
}

// ═══════════════════════════════════════════════════════════════
// IndexedDBEventStore — 浏览器持久化实现
// ═══════════════════════════════════════════════════════════════

const DB_NAME = "zhiwei-os";
const DB_VERSION = 1;
const EVENT_STORE = "events";
const TRACE_INDEX = "by_trace";
const TIME_INDEX = "by_time";

/**
 * IndexedDB EventStore — 浏览器持久化
 * crash restart 后可恢复所有事件
 *
 * Schema:
 * - events (keyPath: event_id)
 *   - by_trace (index: trace_id)
 *   - by_time (index: timestamp)
 */
export class IndexedDBEventStore implements IEventStore {
  private db: IDBDatabase | null = null;
  private initPromise: Promise<void> | null = null;

  /**
   * 初始化数据库连接
   */
  private async init(): Promise<void> {
    if (this.db) return;
    if (this.initPromise) return this.initPromise;

    this.initPromise = new Promise<void>((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onerror = () => reject(request.error);

      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;

        // events 表（keyPath: event_id）
        if (!db.objectStoreNames.contains(EVENT_STORE)) {
          const store = db.createObjectStore(EVENT_STORE, { keyPath: "event_id" });
          // trace_id 索引
          store.createIndex(TRACE_INDEX, "trace_id", { unique: false });
          // timestamp 索引
          store.createIndex(TIME_INDEX, "timestamp", { unique: false });
        }
      };
    });

    return this.initPromise;
  }

  async put(event: SystemEvent): Promise<void> {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(EVENT_STORE, "readwrite");
      const store = tx.objectStore(EVENT_STORE);
      const request = store.put(event);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async putBatch(events: SystemEvent[]): Promise<void> {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(EVENT_STORE, "readwrite");
      const store = tx.objectStore(EVENT_STORE);

      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);

      for (const event of events) {
        store.put(event);
      }
    });
  }

  async get(event_id: string): Promise<SystemEvent | null> {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(EVENT_STORE, "readonly");
      const store = tx.objectStore(EVENT_STORE);
      const request = store.get(event_id);
      request.onsuccess = () => resolve(request.result ?? null);
      request.onerror = () => reject(request.error);
    });
  }

  async getByTraceId(trace_id: string): Promise<SystemEvent[]> {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(EVENT_STORE, "readonly");
      const store = tx.objectStore(EVENT_STORE);
      const index = store.index(TRACE_INDEX);
      const request = index.getAll(trace_id);
      request.onsuccess = () => {
        const events = (request.result || []) as SystemEvent[];
        events.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
        resolve(events);
      };
      request.onerror = () => reject(request.error);
    });
  }

  async getByTimeRange(from: string, to: string): Promise<SystemEvent[]> {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(EVENT_STORE, "readonly");
      const store = tx.objectStore(EVENT_STORE);
      const index = store.index(TIME_INDEX);
      // IDBKeyRange.bound 是闭区间
      const range = IDBKeyRange.bound(from, to);
      const request = index.getAll(range);
      request.onsuccess = () => {
        const events = (request.result || []) as SystemEvent[];
        events.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
        resolve(events);
      };
      request.onerror = () => reject(request.error);
    });
  }

  async getTraceIds(): Promise<string[]> {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(EVENT_STORE, "readonly");
      const store = tx.objectStore(EVENT_STORE);
      const index = store.index(TRACE_INDEX);
      // getAllKeys 获取所有 trace_id（可能有重复）
      const request = index.getAllKeys();
      request.onsuccess = () => {
        const keys = (request.result || []) as string[];
        // 去重
        const unique = Array.from(new Set(keys));
        resolve(unique);
      };
      request.onerror = () => reject(request.error);
    });
  }

  async delete(event_id: string): Promise<void> {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(EVENT_STORE, "readwrite");
      const store = tx.objectStore(EVENT_STORE);
      const request = store.delete(event_id);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async clear(): Promise<void> {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(EVENT_STORE, "readwrite");
      const store = tx.objectStore(EVENT_STORE);
      const request = store.clear();
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async count(): Promise<number> {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(EVENT_STORE, "readonly");
      const store = tx.objectStore(EVENT_STORE);
      const request = store.count();
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
}

// ═══════════════════════════════════════════════════════════════
// 工厂函数 — 根据环境选择实现
// ═══════════════════════════════════════════════════════════════

/**
 * 创建 EventStore 实例
 * - 浏览器环境且支持 IndexedDB → IndexedDBEventStore
 * - 否则 → MemoryEventStore（降级）
 */
export function createEventStore(): IEventStore {
  // 检测 IndexedDB 支持
  if (typeof indexedDB !== "undefined") {
    try {
      return new IndexedDBEventStore();
    } catch (err) {
      console.warn("[Persistence] IndexedDB init failed, fallback to Memory:", err);
    }
  }
  return new MemoryEventStore();
}
