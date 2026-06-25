import type {
  AgentStatus, ChatRequest, ChatResponse, Memory, ReflectionInsight, ToolInfo, TraceEntry, UploadResult,
  AuthTokens, AuthUser, LoginResponse, RegisterResponse,
  Workspace, WorkspaceMember, WorkspaceDashboard, ActivityEvent, AuditLogEntry,
  ActionPlan, Notification,
} from "@/types";
import type { ImportJobResponse, ImportJobListResponse } from "@/types/import";
import type {
  SyncConnector,
  SyncJob,
  SyncExecution,
  SyncStats,
} from "@/types/sync";
import type {
  AgentPerformanceResponse,
  GrowthResponse,
  MemoryHealthResponse,
  OverviewResponse,
} from "@/types/dashboard-v2";
import { getAccessToken } from "@/stores/auth-store";

const BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const IMPORTS_PATH = "/imports";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  const moduleToken = getAccessToken();
  if (moduleToken) return moduleToken;

  try {
    const raw = localStorage.getItem("agent-os-auth");
    if (raw) {
      const parsed = JSON.parse(raw);
      return parsed?.state?.token?.access_token || null;
    }
  } catch { /* ignore */ }
  return null;
}

function getAuthHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function _handleAuthExpired() {
  if (typeof window === "undefined") return;
  const current = window.location.pathname;
  try {
    localStorage.removeItem("agent-os-auth");
  } catch { /* ignore */ }
  if (current !== "/login") {
    window.location.href = `/login?redirect=${encodeURIComponent(current)}`;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...getAuthHeaders(),
    ...((init?.headers as Record<string, string>) || {}),
  };
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
  });

  if (res.status === 401) {
    _handleAuthExpired();
    const body = await res.text();
    let msg = "Login expired, please sign in again";
    try { const j = JSON.parse(body); if (j.detail) msg = j.detail; } catch { /* use raw */ }
    throw new ApiError(401, msg);
  }

  if (!res.ok) {
    const body = await res.text();
    let msg = `API ${res.status}`;
    try { const j = JSON.parse(body); if (j.detail) msg = j.detail; } catch { /* use raw */ }
    throw new ApiError(res.status, msg);
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return res.json();
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  return request<T>(path, init);
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
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify(payload),
      signal: ctrl.signal,
    }).then(async (res) => {
      if (!res.ok) {
        if (res.status === 401) _handleAuthExpired();
        const body = await res.text();
        let msg = `HTTP ${res.status}`;
        try {
          const parsed = JSON.parse(body);
          if (parsed.detail) msg = parsed.detail;
        } catch {
          // Use status fallback.
        }
        onError(msg);
        return;
      }
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
      headers: getAuthHeaders(),
      body: form,
    }).then((res) => {
      if (!res.ok) throw new ApiError(res.status, `上传失败: ${res.statusText}`);
      return res.json();
    });
  },

  dashboard: {
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
      return fetch(`${BASE}/audio/upload`, { method: "POST", headers: getAuthHeaders(), body: form }).then((res) => {
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
      return fetch(`${BASE}/video/upload`, { method: "POST", headers: getAuthHeaders(), body: form }).then((res) => {
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
      return fetch(`${BASE}${IMPORTS_PATH}`, {
        method: "POST",
        headers,
        body: form,
      }).then((res) => {
        if (!res.ok) throw new ApiError(res.status, `导入失败: ${res.statusText}`);
        return res.json();
      });
    },
    list(): Promise<ImportJobListResponse> {
      return request(IMPORTS_PATH);
    },
    get(jobId: string): Promise<ImportJobResponse> {
      return request(`${IMPORTS_PATH}/${jobId}`);
    },
    retry(jobId: string): Promise<ImportJobResponse> {
      return request(`${IMPORTS_PATH}/${jobId}/retry`, { method: "POST" });
    },
    delete(jobId: string): Promise<void> {
      return request(`${IMPORTS_PATH}/${jobId}`, { method: "DELETE" });
    },
  },

  // ── Sync Hub ──

  sync: {
    // Stats
    getStats(): Promise<SyncStats> {
      return request("/sync/stats");
    },

    // Connectors
    listConnectors(): Promise<{ connectors: SyncConnector[] }> {
      return request("/sync/connectors");
    },
    createConnector(data: {
      name: string;
      connector_type: string;
      credentials: Record<string, string>;
    }): Promise<{ status: string; connector: SyncConnector }> {
      return request("/sync/connectors", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    testConnector(
      connectorId: string
    ): Promise<{ connector_id: string; success: boolean; message: string }> {
      return request(`/sync/connectors/${connectorId}/test`, { method: "POST" });
    },
    deleteConnector(connectorId: string): Promise<{ status: string; connector_id: string }> {
      return request(`/sync/connectors/${connectorId}`, { method: "DELETE" });
    },

    // Jobs
    listJobs(): Promise<{ jobs: SyncJob[] }> {
      return request("/sync/jobs");
    },
    getJob(
      jobId: string
    ): Promise<{ job: SyncJob; recent_executions: SyncExecution[] }> {
      return request(`/sync/jobs/${jobId}`);
    },
    createJob(data: {
      connector_config_id: string;
      name: string;
      rule_type: string;
      cron_expression?: string;
    }): Promise<{ status: string; job: SyncJob }> {
      return request("/sync/jobs", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    runJob(
      jobId: string
    ): Promise<{ status: string; execution_id: string }> {
      return request(`/sync/jobs/${jobId}/run`, { method: "POST" });
    },
    retryJob(
      jobId: string,
      executionId?: string
    ): Promise<{ status: string; execution_id: string }> {
      return request(`/sync/jobs/${jobId}/retry`, {
        method: "POST",
        body: JSON.stringify({ execution_id: executionId || "" }),
      });
    },
    deleteJob(jobId: string): Promise<{ status: string; job_id: string }> {
      return request(`/sync/jobs/${jobId}`, { method: "DELETE" });
    },

    // History
    getHistory(params?: {
      connector_id?: string;
      limit?: number;
    }): Promise<{ executions: SyncExecution[] }> {
      const sp = new URLSearchParams();
      if (params?.connector_id) sp.set("connector_id", params.connector_id);
      if (params?.limit) sp.set("limit", String(params.limit));
      const qs = sp.toString();
      return request(`/sync/history${qs ? `?${qs}` : ""}`);
    },
  },

  // ── SaaS: Billing ──

  billing: {
    getAccount(): Promise<import("@/types").BillingAccount> {
      return request("/billing/account");
    },
    createPaymentIntent(data: {
      amount: number; currency?: string; provider?: string;
      description?: string; invoice_id?: string;
    }): Promise<import("@/types").PaymentIntent> {
      return request("/billing/payment-intent", { method: "POST", body: JSON.stringify(data) });
    },
    listInvoices(params?: { status?: string }): Promise<import("@/types").Invoice[]> {
      const sp = new URLSearchParams();
      if (params?.status) sp.set("status", params.status);
      const qs = sp.toString();
      return request(`/billing/invoices${qs ? `?${qs}` : ""}`);
    },
    getInvoice(id: string): Promise<import("@/types").Invoice> {
      return request(`/billing/invoices/${id}`);
    },
    listPayments(): Promise<import("@/types").Payment[]> {
      return request("/billing/payments");
    },
    refundPayment(paymentId: string, data: { amount: number; reason?: string }): Promise<import("@/types").Refund> {
      return request(`/billing/payments/${paymentId}/refund`, { method: "POST", body: JSON.stringify(data) });
    },
    listRefunds(): Promise<import("@/types").Refund[]> {
      return request("/billing/refunds");
    },
  },

  // ── SaaS: Subscription ──

  subscription: {
    get(): Promise<import("@/types").Subscription> {
      return request("/subscription");
    },
    listPlans(): Promise<import("@/types").PlanPreview[]> {
      return request("/subscription/plans");
    },
    getPlan(tier: string): Promise<import("@/types").PlanPreview> {
      return request(`/subscription/plans/${tier}`);
    },
    changePlan(data: { target_tier: string; billing_cycle?: string }): Promise<import("@/types").Subscription> {
      return request("/subscription/change-plan", { method: "POST", body: JSON.stringify(data) });
    },
    cancel(): Promise<{ tenant_id: string; status: string; canceled_at: string }> {
      return request("/subscription/cancel", { method: "POST" });
    },
    resume(): Promise<import("@/types").Subscription> {
      return request("/subscription/resume", { method: "POST" });
    },
    checkLimit(resource: string): Promise<import("@/types").LimitCheckResult> {
      return request(`/subscription/check-limit?resource=${encodeURIComponent(resource)}`);
    },
    getLimits(): Promise<import("@/types").LimitCheckResult[]> {
      return request("/subscription/limits");
    },
  },

  // ── SaaS: Usage ──

  usage: {
    getStats(params?: { year?: number; month?: number }): Promise<import("@/types").UsageStats> {
      const sp = new URLSearchParams();
      if (params?.year) sp.set("year", String(params.year));
      if (params?.month) sp.set("month", String(params.month));
      const qs = sp.toString();
      return request(`/usage/stats${qs ? `?${qs}` : ""}`);
    },
    getCost(params?: { year?: number; month?: number }): Promise<import("@/types").UsageStats> {
      const sp = new URLSearchParams();
      if (params?.year) sp.set("year", String(params.year));
      if (params?.month) sp.set("month", String(params.month));
      const qs = sp.toString();
      return request(`/usage/cost${qs ? `?${qs}` : ""}`);
    },
    getDailyUsage(params: { resource: string; days?: number }): Promise<import("@/types").DailyUsage[]> {
      const sp = new URLSearchParams();
      sp.set("resource", params.resource);
      if (params.days) sp.set("days", String(params.days));
      return request(`/usage/daily?${sp.toString()}`);
    },
    getProfile(): Promise<import("@/types").UserProfile> {
      return request("/usage/profile");
    },
    getTenantSummary(days?: number): Promise<Record<string, number>> {
      const qs = days ? `?days=${days}` : "";
      return request(`/usage/tenant-summary${qs}`);
    },
    getPlatformStats(): Promise<import("@/types").PlatformStats> {
      return request("/usage/admin/platform-stats");
    },
  },

  // ── SaaS: Tenant ──

  tenant: {
    getCurrent(): Promise<import("@/types").Tenant> {
      return request("/tenants/current");
    },
    updateCurrent(data: Record<string, unknown>): Promise<import("@/types").Tenant> {
      return request("/tenants/current", { method: "PATCH", body: JSON.stringify(data) });
    },
    listMembers(): Promise<import("@/types").TenantMember[]> {
      return request("/tenants/current/members");
    },
    addMember(data: { user_id: string; role?: string }): Promise<import("@/types").TenantMember> {
      return request("/tenants/current/members", { method: "POST", body: JSON.stringify(data) });
    },
    removeMember(userId: string): Promise<{ status: string }> {
      return request(`/tenants/current/members/${userId}`, { method: "DELETE" });
    },
    listOrganizations(): Promise<import("@/types").Organization[]> {
      return request("/tenants/current/organizations");
    },
    createOrganization(data: { name: string; description?: string; parent_org_id?: string }): Promise<import("@/types").Organization> {
      return request("/tenants/current/organizations", { method: "POST", body: JSON.stringify(data) });
    },
    deleteOrganization(orgId: string): Promise<{ status: string }> {
      return request(`/tenants/current/organizations/${orgId}`, { method: "DELETE" });
    },
  },

  // ── SaaS: Growth ──

  growth: {
    // Invites
    createInvite(data: { invitee_email: string; workspace_id?: string }): Promise<import("@/types").Invite> {
      return request("/growth/invites", { method: "POST", body: JSON.stringify(data) });
    },
    listInvites(): Promise<import("@/types").Invite[]> {
      return request("/growth/invites");
    },
    acceptInvite(inviteCode: string): Promise<import("@/types").Invite> {
      return request("/growth/invites/accept", { method: "POST", body: JSON.stringify({ invite_code: inviteCode }) });
    },
    // Referrals
    createReferral(): Promise<import("@/types").Referral> {
      return request("/growth/referrals", { method: "POST" });
    },
    listReferrals(): Promise<import("@/types").Referral[]> {
      return request("/growth/referrals");
    },
    getReferralStats(): Promise<import("@/types").ReferralStats> {
      return request("/growth/referrals/stats");
    },
    // Coupons
    listCoupons(): Promise<import("@/types").Coupon[]> {
      return request("/growth/coupons");
    },
    lookupCoupon(code: string): Promise<import("@/types").Coupon> {
      return request(`/growth/coupons/${encodeURIComponent(code)}`);
    },
    redeemCoupon(data: { code: string; invoice_id?: string }): Promise<import("@/types").RedeemedCoupon> {
      return request("/growth/coupons/redeem", { method: "POST", body: JSON.stringify(data) });
    },
    // Trial
    getTrial(): Promise<import("@/types").TrialRecord> {
      return request("/growth/trial");
    },
  },

  // ── Growth & Analytics Center ──

  analytics: {
    getMetrics(): Promise<import("@/types").AnalyticsMetrics> {
      return request("/analytics/metrics");
    },
    getMemoryTrend(params?: { period?: string; days?: number }): Promise<import("@/types").MemoryTrend> {
      const sp = new URLSearchParams();
      if (params?.period) sp.set("period", params.period);
      if (params?.days) sp.set("days", String(params.days));
      const qs = sp.toString();
      return request(`/analytics/memory-trend${qs ? `?${qs}` : ""}`);
    },
    getResourceUsage(params: { resource: string; days?: number }): Promise<import("@/types").ResourceUsageTrend> {
      const sp = new URLSearchParams();
      sp.set("resource", params.resource);
      if (params.days) sp.set("days", String(params.days));
      return request(`/analytics/resource-usage?${sp.toString()}`);
    },
    getImportChannels(days?: number): Promise<import("@/types").ImportChannelBreakdown> {
      const qs = days ? `?days=${days}` : "";
      return request(`/analytics/import-channels${qs}`);
    },
    getRetention(months?: number): Promise<import("@/types").RetentionCohort> {
      const qs = months ? `?months=${months}` : "";
      return request(`/analytics/retention${qs}`);
    },
    getRealtime(): Promise<import("@/types").RealtimeMetrics> {
      return request("/analytics/realtime");
    },
  },

  alerts: {
    listRules(enabledOnly?: boolean): Promise<import("@/types").AlertRule[]> {
      const qs = enabledOnly ? "?enabled_only=true" : "";
      return request(`/alerts/rules${qs}`);
    },
    getRule(id: string): Promise<import("@/types").AlertRule> {
      return request(`/alerts/rules/${id}`);
    },
    createRule(data: {
      name: string; metric: string; condition?: string;
      threshold: number; severity?: string; channel?: string;
      cooldown_minutes?: number;
    }): Promise<import("@/types").AlertRule> {
      return request("/alerts/rules", { method: "POST", body: JSON.stringify(data) });
    },
    updateRule(id: string, data: Record<string, unknown>): Promise<import("@/types").AlertRule> {
      return request(`/alerts/rules/${id}`, { method: "PATCH", body: JSON.stringify(data) });
    },
    deleteRule(id: string): Promise<{ status: string; rule_id: string }> {
      return request(`/alerts/rules/${id}`, { method: "DELETE" });
    },
    listEvents(params?: {
      rule_id?: string; severity?: string; acknowledged?: boolean;
      limit?: number; offset?: number;
    }): Promise<import("@/types").AlertEvent[]> {
      const sp = new URLSearchParams();
      if (params?.rule_id) sp.set("rule_id", params.rule_id);
      if (params?.severity) sp.set("severity", params.severity);
      if (params?.acknowledged !== undefined) sp.set("acknowledged", String(params.acknowledged));
      if (params?.limit) sp.set("limit", String(params.limit));
      if (params?.offset) sp.set("offset", String(params.offset));
      const qs = sp.toString();
      return request(`/alerts/events${qs ? `?${qs}` : ""}`);
    },
    acknowledgeEvent(eventId: string): Promise<{ status: string; event_id: string }> {
      return request(`/alerts/events/${eventId}/acknowledge`, { method: "POST" });
    },
    testAlert(channel?: string): Promise<import("@/types").TestAlertResult> {
      const qs = channel ? `?channel=${channel}` : "";
      return request(`/alerts/test${qs}`, { method: "POST" });
    },
    seedPresets(): Promise<{ status: string; rule_ids: string[] }> {
      return request("/alerts/rules/presets", { method: "POST" });
    },
  },

  reports: {
    generate(data: { report_type: string; format?: string }): Promise<import("@/types").Report> {
      return request("/reports/generate", { method: "POST", body: JSON.stringify(data) });
    },
    list(reportType?: string, limit?: number): Promise<import("@/types").Report[]> {
      const sp = new URLSearchParams();
      if (reportType) sp.set("report_type", reportType);
      if (limit) sp.set("limit", String(limit));
      const qs = sp.toString();
      return request(`/reports${qs ? `?${qs}` : ""}`);
    },
    get(id: string): Promise<import("@/types").Report> {
      return request(`/reports/${id}`);
    },
    exportReport(id: string, format?: string): Promise<Blob> {
      const token = getToken();
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const qs = format ? `?format=${format}` : "";
      return fetch(`${BASE}/reports/${id}/export${qs}`, { headers }).then((res) => {
        if (!res.ok) throw new ApiError(res.status, `导出失败: ${res.statusText}`);
        return res.blob();
      });
    },
    delete(id: string): Promise<{ status: string; report_id: string }> {
      return request(`/reports/${id}`, { method: "DELETE" });
    },
  },

  // ── RBAC ──

  rbac: {
    users(): Promise<import("@/types").RbacUser[]> {
      return request("/api/rbac/users");
    },
    roles(orgId?: string): Promise<import("@/types").RbacRole[]> {
      const qs = orgId ? `?org_id=${encodeURIComponent(orgId)}` : "";
      return request(`/api/rbac/roles${qs}`);
    },
    assignRole(data: { user_id: string; role_id: string; organization_id: string; scope_type?: string; scope_id?: string }): Promise<unknown> {
      return request("/api/rbac/assign", { method: "POST", body: JSON.stringify(data) });
    },
    removeAssignment(assignmentId: string): Promise<{ detail: string }> {
      return request(`/api/rbac/assignments/${assignmentId}`, { method: "DELETE" });
    },
    userRoles(userId: string, orgId?: string): Promise<import("@/types").RbacRole[]> {
      const qs = orgId ? `?org_id=${encodeURIComponent(orgId)}` : "";
      return request(`/api/rbac/users/${userId}/roles${qs}`);
    },
  },

  // ── Admin ──

  admin: {
    summary(): Promise<import("@/types").AdminSummary> {
      return request("/api/admin/summary");
    },
    growth(weeks?: number): Promise<import("@/types").GrowthDataPoint[]> {
      const qs = weeks ? `?weeks=${weeks}` : "";
      return request(`/api/admin/growth${qs}`);
    },
    config(): Promise<import("@/types").AdminConfig> {
      return request("/api/admin/config");
    },
  },

  // ── Dashboard V2 (Observability Console) ──

  debug: {
    retrieve(params: { q: string; top_k?: number }): Promise<import("@/types").RetrieveHit[]> {
      const sp = new URLSearchParams();
      sp.set("q", params.q);
      if (params.top_k) sp.set("top_k", String(params.top_k));
      return request(`/debug/retrieve?${sp.toString()}`);
    },
  },

  dashboardV2: {
    overview(): Promise<OverviewResponse> {
      return request("/dashboard/v2/overview");
    },
    growth(days?: number): Promise<GrowthResponse> {
      const qs = days ? `?days=${days}` : "";
      return request(`/dashboard/v2/growth${qs}`);
    },
    agentPerformance(days?: number): Promise<AgentPerformanceResponse> {
      const qs = days ? `?days=${days}` : "";
      return request(`/dashboard/v2/agent-performance${qs}`);
    },
    memoryHealth(days?: number): Promise<MemoryHealthResponse> {
      const qs = days ? `?days=${days}` : "";
      return request(`/dashboard/v2/memory-health${qs}`);
    },
  },
};
