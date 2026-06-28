/** Cognitive Kernel API client for the Python backend.
 *
 * Backend base: ``http://localhost:8000/api/v1`` (overridable via
 * ``NEXT_PUBLIC_API_URL``).  Every function is async and returns a
 * strongly-typed response; network / non-2xx errors are surfaced as
 * ``KernelApiError`` so callers can handle them gracefully.
 */
import { toast } from "@/stores/ui-store";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const KERNEL_BASE = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/$/, "");

const KERNEL_PREFIX = "/api/v1";

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

export class KernelApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message);
    this.name = "KernelApiError";
  }
}

// ---------------------------------------------------------------------------
// Internal fetch helper
// ---------------------------------------------------------------------------

async function kernelFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const url = `${KERNEL_BASE}${KERNEL_PREFIX}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string>) || {}),
  };

  let res: Response;
  try {
    res = await fetch(url, { ...init, headers });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Network error";
    throw new KernelApiError(0, msg);
  }

  if (!res.ok) {
    let body: unknown;
    let detail = `HTTP ${res.status}`;
    try {
      body = await res.clone().json();
      if (body && typeof body === "object" && "detail" in body) {
        detail = String((body as Record<string, unknown>).detail);
      }
    } catch {
      // use status fallback
    }
    throw new KernelApiError(res.status, detail, body);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Domain types (mirrors backend Pydantic models)
// ---------------------------------------------------------------------------

export type MemoryScope = "episodic" | "semantic";

export interface MemoryWriteRequest {
  content: string;
  scope: MemoryScope;
  importance: number;
}

export interface MemoryWriteResponse {
  id: string;
  scope: MemoryScope;
  importance: number;
  timestamp: string;
  status: string;
}

export interface MemorySearchRequest {
  query: string;
  top_k: number;
  rerank: boolean;
  scope?: MemoryScope | null;
}

export interface MemorySearchHit {
  id: string;
  content: string;
  scope: MemoryScope;
  importance: number;
  timestamp: string;
  score: number;
}

export interface MemorySearchResponse {
  query: string;
  hits: MemorySearchHit[];
  total: number;
  reranked: boolean;
}

export type IntentLabel = "MEMORY_SEARCH" | "CODE_EXECUTION";

export interface RouteResponse {
  intent: IntentLabel;
  confidence: number;
  raw_query: string;
}

export interface ExecuteResponse {
  status: "SUCCESS" | "INTERCEPTED" | "ERROR";
  reason?: string | null;
  result?: {
    stdout?: string;
    stderr?: string;
    exit_code?: number;
    mock?: boolean;
  } | null;
  execution_time_ms?: number | null;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export const kernelApi = {
  /** POST /memory/write — persist a memory to the multi-layer engine. */
  async writeMemory(
    content: string,
    scope: MemoryScope = "episodic",
    importance: number = 1.0,
  ): Promise<MemoryWriteResponse> {
    const body: MemoryWriteRequest = { content, scope, importance };
    return kernelFetch<MemoryWriteResponse>("/memory/write", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** POST /memory/search — vector-similarity recall with optional mock rerank. */
  async searchMemory(
    query: string,
    topK: number = 5,
    rerank: boolean = false,
    scope?: MemoryScope | null,
  ): Promise<MemorySearchResponse> {
    const body: MemorySearchRequest = {
      query,
      top_k: topK,
      rerank,
      scope: scope ?? null,
    };
    return kernelFetch<MemorySearchResponse>("/memory/search", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** POST /kernel/route — classify a user query intent (mock LLM router). */
  async routeIntent(query: string): Promise<RouteResponse> {
    return kernelFetch<RouteResponse>("/kernel/route", {
      method: "POST",
      body: JSON.stringify({ query }),
    });
  },

  /** POST /kernel/execute — security-gated mock sandbox execution. */
  async executeSandbox(code: string): Promise<ExecuteResponse> {
    return kernelFetch<ExecuteResponse>("/kernel/execute", {
      method: "POST",
      body: JSON.stringify({ code_string: code }),
    });
  },
};

// ---------------------------------------------------------------------------
// Convenience: catch + toast helper
// ---------------------------------------------------------------------------

/** Call an async kernel API function and surface errors via the toast system.
 *
 * Usage::
 *
 *   const result = await kernelSafe(kernelApi.routeIntent("hello"));
 *   if (result) { /* use result *​/ }
 */
export async function kernelSafe<T>(
  promise: Promise<T>,
  fallbackMessage?: string,
): Promise<T | null> {
  try {
    return await promise;
  } catch (err: unknown) {
    const msg =
      err instanceof KernelApiError
        ? `[${err.status}] ${err.message}`
        : err instanceof Error
          ? err.message
          : "Unknown error";
    console.error("[kernelSafe]", msg, err);
    toast.danger(fallbackMessage ?? "内核 API 调用失败", msg);
    return null;
  }
}