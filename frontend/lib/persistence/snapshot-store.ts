/**
 * 知维 OS Persistence Layer — SnapshotStore 实现
 * Zhiwei OS Persistence Layer — SnapshotStore Implementation
 *
 * 提供两种实现：
 * 1. MemorySnapshotStore   — 内存实现（向后兼容）
 * 2. IndexedDBSnapshotStore — 浏览器持久化实现（crash restart 可恢复）
 *
 * Snapshot 用于：
 * - 加速 replay（从 snapshot 开始重放，而非从头）
 * - crash recovery（restoreFromSnapshot）
 * - checkpoint（autoCheckpoint 每 N 事件）
 */

import type {
  ISnapshotStore,
  SystemSnapshot,
  SnapshotReason,
} from "@/lib/persistence/types";
import { serializeState } from "@/lib/persistence/types";
import type { SystemState } from "@/lib/replay/types";

// ═══════════════════════════════════════════════════════════════
// MemorySnapshotStore — 内存实现
// ═══════════════════════════════════════════════════════════════

/**
 * 内存 SnapshotStore — 不持久化，刷新即丢
 */
export class MemorySnapshotStore implements ISnapshotStore {
  private snapshots: Map<string, SystemSnapshot> = new Map();
  private traceIndex: Map<string, string[]> = new Map();

  async put(snapshot: SystemSnapshot): Promise<void> {
    this.snapshots.set(snapshot.snapshot_id, snapshot);

    // trace 索引
    const ids = this.traceIndex.get(snapshot.trace_id) || [];
    ids.push(snapshot.snapshot_id);
    this.traceIndex.set(snapshot.trace_id, ids);
  }

  async get(snapshot_id: string): Promise<SystemSnapshot | null> {
    return this.snapshots.get(snapshot_id) ?? null;
  }

  async listByTraceId(trace_id: string): Promise<SystemSnapshot[]> {
    const ids = this.traceIndex.get(trace_id) || [];
    return ids
      .map((id) => this.snapshots.get(id))
      .filter((s): s is SystemSnapshot => s !== null)
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  }

  async getLatestByTraceId(trace_id: string): Promise<SystemSnapshot | null> {
    const snapshots = await this.listByTraceId(trace_id);
    if (snapshots.length === 0) return null;
    return snapshots[snapshots.length - 1];
  }

  async getLatestBeforeCursor(trace_id: string, cursor: number): Promise<SystemSnapshot | null> {
    const snapshots = await this.listByTraceId(trace_id);
    // 找到 cursor <= 指定值的最近快照
    const candidates = snapshots.filter((s) => s.cursor <= cursor);
    if (candidates.length === 0) return null;
    return candidates[candidates.length - 1];
  }

  async delete(snapshot_id: string): Promise<void> {
    const snapshot = this.snapshots.get(snapshot_id);
    if (snapshot) {
      this.snapshots.delete(snapshot_id);
      const ids = this.traceIndex.get(snapshot.trace_id) || [];
      const idx = ids.indexOf(snapshot_id);
      if (idx >= 0) ids.splice(idx, 1);
    }
  }

  async clear(): Promise<void> {
    this.snapshots.clear();
    this.traceIndex.clear();
  }

  async count(): Promise<number> {
    return this.snapshots.size;
  }
}

// ═══════════════════════════════════════════════════════════════
// IndexedDBSnapshotStore — 浏览器持久化实现
// ═══════════════════════════════════════════════════════════════

const DB_NAME = "zhiwei-os";
const DB_VERSION = 1;
const SNAPSHOT_STORE = "snapshots";
const SNAPSHOT_TRACE_INDEX = "by_trace";

/**
 * IndexedDB SnapshotStore — 浏览器持久化
 *
 * Schema:
 * - snapshots (keyPath: snapshot_id)
 *   - by_trace (index: trace_id)
 */
export class IndexedDBSnapshotStore implements ISnapshotStore {
  private db: IDBDatabase | null = null;
  private initPromise: Promise<void> | null = null;

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

        // snapshots 表（keyPath: snapshot_id）
        if (!db.objectStoreNames.contains(SNAPSHOT_STORE)) {
          const store = db.createObjectStore(SNAPSHOT_STORE, { keyPath: "snapshot_id" });
          store.createIndex(SNAPSHOT_TRACE_INDEX, "trace_id", { unique: false });
        }
      };
    });

    return this.initPromise;
  }

  async put(snapshot: SystemSnapshot): Promise<void> {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(SNAPSHOT_STORE, "readwrite");
      const store = tx.objectStore(SNAPSHOT_STORE);
      const request = store.put(snapshot);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async get(snapshot_id: string): Promise<SystemSnapshot | null> {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(SNAPSHOT_STORE, "readonly");
      const store = tx.objectStore(SNAPSHOT_STORE);
      const request = store.get(snapshot_id);
      request.onsuccess = () => resolve(request.result ?? null);
      request.onerror = () => reject(request.error);
    });
  }

  async listByTraceId(trace_id: string): Promise<SystemSnapshot[]> {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(SNAPSHOT_STORE, "readonly");
      const store = tx.objectStore(SNAPSHOT_STORE);
      const index = store.index(SNAPSHOT_TRACE_INDEX);
      const request = index.getAll(trace_id);
      request.onsuccess = () => {
        const snapshots = (request.result || []) as SystemSnapshot[];
        snapshots.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
        resolve(snapshots);
      };
      request.onerror = () => reject(request.error);
    });
  }

  async getLatestByTraceId(trace_id: string): Promise<SystemSnapshot | null> {
    const snapshots = await this.listByTraceId(trace_id);
    if (snapshots.length === 0) return null;
    return snapshots[snapshots.length - 1];
  }

  async getLatestBeforeCursor(trace_id: string, cursor: number): Promise<SystemSnapshot | null> {
    const snapshots = await this.listByTraceId(trace_id);
    const candidates = snapshots.filter((s) => s.cursor <= cursor);
    if (candidates.length === 0) return null;
    return candidates[candidates.length - 1];
  }

  async delete(snapshot_id: string): Promise<void> {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(SNAPSHOT_STORE, "readwrite");
      const store = tx.objectStore(SNAPSHOT_STORE);
      const request = store.delete(snapshot_id);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async clear(): Promise<void> {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(SNAPSHOT_STORE, "readwrite");
      const store = tx.objectStore(SNAPSHOT_STORE);
      const request = store.clear();
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async count(): Promise<number> {
    await this.init();
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(SNAPSHOT_STORE, "readonly");
      const store = tx.objectStore(SNAPSHOT_STORE);
      const request = store.count();
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
}

// ═══════════════════════════════════════════════════════════════
// 工厂函数
// ═══════════════════════════════════════════════════════════════

export function createSnapshotStore(): ISnapshotStore {
  if (typeof indexedDB !== "undefined") {
    try {
      return new IndexedDBSnapshotStore();
    } catch (err) {
      console.warn("[Persistence] IndexedDB snapshot store init failed, fallback to Memory:", err);
    }
  }
  return new MemorySnapshotStore();
}

// ═══════════════════════════════════════════════════════════════
// Snapshot 工厂函数 — 创建快照对象
// ═══════════════════════════════════════════════════════════════

let snapshotCounter = 0;

/**
 * 生成快照 ID
 */
export function generateSnapshotId(): string {
  snapshotCounter++;
  return `snap_${Date.now()}_${snapshotCounter}`;
}

/**
 * 创建快照对象
 */
export function createSnapshotObject(
  trace_id: string,
  cursor: number,
  state: SystemState,
  event_count: number,
  reason: SnapshotReason,
): SystemSnapshot {
  return {
    snapshot_id: generateSnapshotId(),
    trace_id,
    cursor,
    state: serializeState(state),
    timestamp: new Date().toISOString(),
    reason,
    event_count,
  };
}
