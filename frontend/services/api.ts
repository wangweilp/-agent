import type { AgentStatus, ChatRequest, ChatResponse, DashboardMetrics, Memory, ReflectionInsight, ToolInfo, TraceEntry, UploadResult } from "@/types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) throw new ApiError(res.status, `API ${res.status}: ${res.statusText}`);
  return res.json();
}

export const api = {
  chat(payload: ChatRequest): Promise<ChatResponse> {
    return request("/chat", { method: "POST", body: JSON.stringify(payload) });
  },

  chatStream(
    payload: ChatRequest,
    onToken: (text: string) => void,
    onToolCall: (data: unknown) => void,
    onToolResult: (data: unknown) => void,
    onDone: () => void,
    onError: (err: string) => void,
  ): AbortController {
    const ctrl = new AbortController();
    fetch(`${BASE}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: ctrl.signal,
    }).then(async (res) => {
      if (!res.ok) { onError(`HTTP ${res.status}`); return; }
      const reader = res.body?.getReader();
      if (!reader) { onError("No stream body"); return; }
      const dec = new TextDecoder();
      let buf = "";
      let eventType = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            try {
              const parsed = JSON.parse(line.slice(6));
              switch (eventType) {
                case "token": onToken(parsed.text || ""); break;
                case "tool_call": onToolCall(parsed); break;
                case "tool_result": onToolResult(parsed); break;
                case "done": onDone(); break;
                case "error": onError(parsed.message || "未知错误"); break;
              }
            } catch { /* skip parse errors */ }
            eventType = "";
          }
        }
      }
    }).catch((e) => {
      if (e.name !== "AbortError") onError(e.message);
    });
    return ctrl;
  },

  health(): Promise<AgentStatus> {
    return request("/health");
  },

  memory: {
    list(params?: { q?: string; limit?: number }): Promise<Memory[]> {
      const sp = new URLSearchParams();
      if (params?.q) sp.set("q", params.q);
      if (params?.limit) sp.set("limit", String(params.limit));
      const qs = sp.toString();
      return request(`/memory${qs ? `?${qs}` : ""}`);
    },
    getById(id: string): Promise<Memory> {
      return request(`/memory/${id}`);
    },
  },

  reflection: {
    list(): Promise<ReflectionInsight[]> {
      return request("/reflection");
    },
  },

  tools: {
    list(): Promise<ToolInfo[]> {
      return request("/tools");
    },
    toggle(name: string, enabled: boolean): Promise<void> {
      return request(`/tools/${name}`, { method: "PATCH", body: JSON.stringify({ enabled }) });
    },
  },

  upload(files: File[]): Promise<UploadResult> {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return fetch(`${BASE}/upload`, {
      method: "POST",
      body: form,
    }).then((res) => {
      if (!res.ok) throw new ApiError(res.status, `上传失败: ${res.statusText}`);
      return res.json();
    });
  },

  dashboard: {
    metrics(): Promise<DashboardMetrics> {
      return request("/dashboard/metrics");
    },
    traces(): Promise<TraceEntry[]> {
      return request("/dashboard/traces");
    },
    runtime(): Promise<import("@/types").RuntimeStats> {
      return request("/dashboard/runtime");
    },
  },
};

