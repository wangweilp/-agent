import type {
  AgentStatus, ChatRequest, ChatResponse, DashboardMetrics, Memory, ReflectionInsight, ToolInfo, TraceEntry, UploadResult,
  AuthTokens, AuthUser, LoginResponse, RegisterResponse,
  Workspace, WorkspaceMember, WorkspaceDashboard, ActivityEvent, AuditLogEntry,
  ActionPlan, Notification,
} from "@/types";
import type { ImportJobResponse, ImportJobListResponse } from "@/types/import";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    // Read from zustand persist localStorage (same key used by auth-store)
    const raw = localStorage.getItem("agent-os-auth");
    if (raw) {
      const parsed = JSON.parse(raw);
      return parsed?.state?.token?.access_token || null;
    }
  } catch { /* ignore */ }
  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(init?.headers as Record<string, string> || {}) };
  const token = getToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
  });
  if (!res.ok) {
    const body = await res.text();
    let msg = `API ${res.status}`;
    try { const j = JSON.parse(body); if (j.detail) msg = j.detail; } catch { /* use raw */ }
    throw new ApiError(res.status, msg);
  }
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
    search(params?: import("@/types").MemorySearchParams): Promise<Memory[]> {
      const sp = new URLSearchParams();
      if (params?.q) sp.set("q", params.q);
      if (params?.type) sp.set("type", params.type);
      if (params?.status) sp.set("status", params.status);
      if (params?.date_from) sp.set("date_from", params.date_from);
      if (params?.date_to) sp.set("date_to", params.date_to);
      if (params?.semantic) sp.set("semantic", "true");
      if (params?.limit) sp.set("limit", String(params.limit));
      const qs = sp.toString();
      return request(`/memory/search${qs ? `?${qs}` : ""}`);
    },
    update(id: string, data: import("@/types").MemoryUpdateRequest): Promise<Memory> {
      return request(`/memory/${id}`, { method: "PATCH", body: JSON.stringify(data) });
    },
    softDelete(id: string): Promise<{ id: string; status: string }> {
      return request(`/memory/${id}`, { method: "DELETE" });
    },
    merge(data: import("@/types").MemoryMergeRequest): Promise<import("@/types").MemoryMergeResponse> {
      return request("/memory/merge", { method: "POST", body: JSON.stringify(data) });
    },
    archive(id: string): Promise<{ id: string; status: string; archived_at: string }> {
      return request(`/memory/${id}/archive`, { method: "POST" });
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
    summary(): Promise<import("@/types").DashboardSummary> {
      return request("/dashboard/summary");
    },
    topics(limit?: number): Promise<import("@/types").TopicItem[]> {
      const qs = limit ? `?limit=${limit}` : "";
      return request(`/dashboard/topics${qs}`);
    },
    entities(limit?: number): Promise<import("@/types").EntityItem[]> {
      const qs = limit ? `?limit=${limit}` : "";
      return request(`/dashboard/entities${qs}`);
    },
    recent(limit?: number): Promise<import("@/types").RecentMemoryItem[]> {
      const qs = limit ? `?limit=${limit}` : "";
      return request(`/dashboard/recent${qs}`);
    },
    reflections(limit?: number): Promise<import("@/types").RecentReflectionItem[]> {
      const qs = limit ? `?limit=${limit}` : "";
      return request(`/dashboard/reflections${qs}`);
    },
    weeklyReport(): Promise<import("@/types").WeeklyReportPlaceholder> {
      return request("/dashboard/weekly-report");
    },
  },

  timeline: {
    list(params?: {
      start_date?: string; end_date?: string;
      memory_type?: string; entity?: string;
      page?: number; limit?: number;
    }): Promise<import("@/types").TimelineDay[]> {
      const sp = new URLSearchParams();
      if (params?.start_date) sp.set("start_date", params.start_date);
      if (params?.end_date) sp.set("end_date", params.end_date);
      if (params?.memory_type) sp.set("memory_type", params.memory_type);
      if (params?.entity) sp.set("entity", params.entity);
      if (params?.page) sp.set("page", String(params.page));
      if (params?.limit) sp.set("limit", String(params.limit));
      const qs = sp.toString();
      return request(`/timeline${qs ? `?${qs}` : ""}`);
    },
    day(date: string): Promise<import("@/types").TimelineDay> {
      return request(`/timeline/day/${date}`);
    },
    stats(params?: {
      start_date?: string; end_date?: string;
    }): Promise<import("@/types").TimelineStats> {
      const sp = new URLSearchParams();
      if (params?.start_date) sp.set("start_date", params.start_date);
      if (params?.end_date) sp.set("end_date", params.end_date);
      const qs = sp.toString();
      return request(`/timeline/stats${qs ? `?${qs}` : ""}`);
    },
  },

  graph: {
    get(params?: {
      entity_type?: string; min_importance?: number; limit?: number;
    }): Promise<import("@/types").GraphData> {
      const sp = new URLSearchParams();
      if (params?.entity_type) sp.set("entity_type", params.entity_type);
      if (params?.min_importance) sp.set("min_importance", String(params.min_importance));
      if (params?.limit) sp.set("limit", String(params.limit));
      const qs = sp.toString();
      return request(`/graph${qs ? `?${qs}` : ""}`);
    },
    entity(name: string): Promise<import("@/types").EntityDetail> {
      return request(`/graph/entity/${encodeURIComponent(name)}`);
    },
    subgraph(entity: string, depth: number = 2): Promise<import("@/types").GraphData> {
      return request(`/graph/subgraph?entity=${encodeURIComponent(entity)}&depth=${depth}`);
    },
  },

  audio: {
    upload(files: File[]): Promise<import("@/types").AudioUploadResult> {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      return fetch(`${BASE}/audio/upload`, { method: "POST", body: form }).then((res) => {
        if (!res.ok) throw new ApiError(res.status, `上传失败: ${res.statusText}`);
        return res.json();
      });
    },
    list(params?: { q?: string; limit?: number }): Promise<Memory[]> {
      const sp = new URLSearchParams();
      if (params?.q) sp.set("q", params.q);
      if (params?.limit) sp.set("limit", String(params.limit));
      const qs = sp.toString();
      return request(`/audio${qs ? `?${qs}` : ""}`);
    },
    getById(id: string): Promise<Memory> {
      return request(`/audio/${id}`);
    },
    update(id: string, data: import("@/types").MemoryUpdateRequest): Promise<Memory> {
      return request(`/audio/${id}`, { method: "PATCH", body: JSON.stringify(data) });
    },
    softDelete(id: string): Promise<{ id: string; status: string }> {
      return request(`/audio/${id}`, { method: "DELETE" });
    },
    archive(id: string): Promise<{ id: string; status: string; archived_at: string }> {
      return request(`/audio/${id}/archive`, { method: "POST" });
    },
  },

  video: {
    upload(files: File[]): Promise<import("@/types").VideoUploadResult> {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      return fetch(`${BASE}/video/upload`, { method: "POST", body: form }).then((res) => {
        if (!res.ok) throw new ApiError(res.status, `上传失败: ${res.statusText}`);
        return res.json();
      });
    },
    list(params?: { q?: string; limit?: number }): Promise<Memory[]> {
      const sp = new URLSearchParams();
      if (params?.q) sp.set("q", params.q);
      if (params?.limit) sp.set("limit", String(params.limit));
      const qs = sp.toString();
      return request(`/video${qs ? `?${qs}` : ""}`);
    },
    getById(id: string): Promise<Memory> {
      return request(`/video/${id}`);
    },
    update(id: string, data: import("@/types").MemoryUpdateRequest): Promise<Memory> {
      return request(`/video/${id}`, { method: "PATCH", body: JSON.stringify(data) });
    },
    softDelete(id: string): Promise<{ id: string; status: string }> {
      return request(`/video/${id}`, { method: "DELETE" });
    },
    archive(id: string): Promise<{ id: string; status: string; archived_at: string }> {
      return request(`/video/${id}/archive`, { method: "POST" });
    },
  },

  // ── Auth ──

  auth: {
    register(email: string, password: string, name?: string): Promise<RegisterResponse> {
      return request("/auth/register", { method: "POST", body: JSON.stringify({ email, password, name }) });
    },
    login(email: string, password: string): Promise<LoginResponse> {
      return request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    },
    refresh(refreshToken: string): Promise<AuthTokens> {
      return request("/auth/refresh", { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) });
    },
    me(): Promise<{ user: AuthUser; workspaces: Workspace[] }> {
      return request("/auth/me");
    },
    listWorkspaces(): Promise<Workspace[]> {
      return request("/auth/workspaces");
    },
    createWorkspace(name: string): Promise<Workspace> {
      return request("/auth/workspaces", { method: "POST", body: JSON.stringify({ name }) });
    },
  },

  // ── Workspace ──

  workspace: {
    listMembers(id: string): Promise<WorkspaceMember[]> {
      return request(`/workspace/${id}/members`);
    },
    addMember(id: string, email: string, role: string = "member"): Promise<WorkspaceMember> {
      return request(`/workspace/${id}/members`, { method: "POST", body: JSON.stringify({ email, role }) });
    },
    updateRole(id: string, userId: string, role: string): Promise<{ user_id: string; role: string }> {
      return request(`/workspace/${id}/members/${userId}`, { method: "PATCH", body: JSON.stringify({ role }) });
    },
    removeMember(id: string, userId: string): Promise<{ status: string }> {
      return request(`/workspace/${id}/members/${userId}`, { method: "DELETE" });
    },
    dashboard(id: string): Promise<WorkspaceDashboard> {
      return request(`/workspace/${id}/dashboard`);
    },
    actionPlans(id: string, params?: { assignee?: string; status?: string; limit?: number }): Promise<ActionPlan[]> {
      const sp = new URLSearchParams();
      if (params?.assignee) sp.set("assignee", params.assignee);
      if (params?.status) sp.set("status", params.status);
      if (params?.limit) sp.set("limit", String(params.limit));
      const qs = sp.toString();
      return request(`/workspace/${id}/action-plans${qs ? `?${qs}` : ""}`);
    },
    createActionPlan(id: string, data: {
      title: string; description?: string; assigned_to?: string;
      priority?: string; due_date?: string; related_memory_ids?: string[];
    }): Promise<ActionPlan> {
      return request(`/workspace/${id}/action-plan`, { method: "POST", body: JSON.stringify(data) });
    },
    activityLog(id: string, limit?: number): Promise<ActivityEvent[]> {
      const qs = limit ? `?limit=${limit}` : "";
      return request(`/workspace/${id}/activity-log${qs}`);
    },
    auditLog(id: string, params?: { action?: string; user_id?: string; limit?: number }): Promise<AuditLogEntry[]> {
      const sp = new URLSearchParams();
      if (params?.action) sp.set("action", params.action);
      if (params?.user_id) sp.set("user_id", params.user_id);
      if (params?.limit) sp.set("limit", String(params.limit || 50));
      const qs = sp.toString();
      return request(`/workspace/${id}/audit-log${qs ? `?${qs}` : ""}`);
    },
    notifications(unreadOnly?: boolean, limit?: number): Promise<Notification[]> {
      const sp = new URLSearchParams();
      if (unreadOnly) sp.set("unread_only", "true");
      if (limit) sp.set("limit", String(limit));
      const qs = sp.toString();
      return request(`/notifications${qs ? `?${qs}` : ""}`);
    },
    unreadCount(): Promise<{ unread: number }> {
      return request("/notifications/unread-count");
    },
    readAllNotifications(): Promise<{ status: string }> {
      return request("/notifications/read-all", { method: "POST" });
    },
  },

  // ── Import Jobs ──

  imports: {
    upload(files: File[], title?: string, tags?: string[]): Promise<ImportJobResponse> {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      if (title) form.append("title", title);
      if (tags && tags.length > 0) form.append("tags", tags.join(","));
      const headers: Record<string, string> = {};
      const token = getToken();
      if (token) headers["Authorization"] = `Bearer ${token}`;
      return fetch(`${BASE}/import`, {
        method: "POST",
        headers,
        body: form,
      }).then((res) => {
        if (!res.ok) throw new ApiError(res.status, `导入失败: ${res.statusText}`);
        return res.json();
      });
    },
    list(): Promise<ImportJobListResponse> {
      return request("/import");
    },
    get(jobId: string): Promise<ImportJobResponse> {
      return request(`/import/${jobId}`);
    },
    retry(jobId: string): Promise<ImportJobResponse> {
      return request(`/import/${jobId}/retry`, { method: "POST" });
    },
    delete(jobId: string): Promise<void> {
      return request(`/import/${jobId}`, { method: "DELETE" });
    },
  },
};

