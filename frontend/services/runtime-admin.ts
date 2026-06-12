/** Runtime Admin API Client — /admin/runtime 端点 */
import { getAccessToken } from "@/stores/auth-store";
import type {
  RuntimeAdaptersResponse, RuntimeBindingsResponse, RuntimeBindingDetailResponse,
  RuntimeBindingActionResponse, RuntimeEligibilityResult,
  SandboxPoliciesResponse, SandboxPolicy, SandboxPolicyTestRequest,
  SandboxPolicyTestResult,
} from "@/types/runtime-admin";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const RA_BASE = `${API_BASE}/admin/runtime`;
const SP_BASE = `${API_BASE}/admin/sandbox-policies`;

export class RuntimeAdminApiError extends Error {
  constructor(public status: number, message: string, public detail: unknown = null) {
    super(message); this.name = "RuntimeAdminApiError";
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  const t = getAccessToken(); if (t) return t;
  try { const raw = localStorage.getItem("agent-os-auth"); if (!raw) return null; return JSON.parse(raw)?.state?.token?.access_token || null; } catch { return null; }
}

async function fetchJSON<T>(base: string, path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${base}${path}`, { ...init, headers });
  const raw = await res.text();
  if (!res.ok) {
    let msg = `[${res.status}]`; let detail: unknown = null;
    try { const p = JSON.parse(raw); detail = p.detail || p; msg = typeof detail === "string" ? `${msg} ${detail}` : `${msg} ${JSON.stringify(detail).slice(0, 200)}`; } catch { msg = `${msg} ${raw.slice(0, 200)}`; }
    throw new RuntimeAdminApiError(res.status, msg, detail);
  }
  if (!raw.trim()) return {} as T;
  return JSON.parse(raw) as T;
}

// ── Adapters ──
export async function listRuntimeAdapters(params?: { status?: string; adapter_type?: string; mvp_only?: boolean }) {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.adapter_type) sp.set("adapter_type", params.adapter_type);
  if (params?.mvp_only) sp.set("mvp_only", "true");
  const qs = sp.toString();
  return fetchJSON<RuntimeAdaptersResponse>(RA_BASE, `/adapters${qs ? `?${qs}` : ""}`);
}

// ── Bindings ──
export async function listRuntimeBindings(params?: { tenant_id?: string; developer_id?: string; marketplace_agent_id?: string; runtime_status?: string; adapter_type?: string }) {
  const sp = new URLSearchParams();
  if (params?.tenant_id) sp.set("tenant_id", params.tenant_id);
  if (params?.developer_id) sp.set("developer_id", params.developer_id);
  if (params?.marketplace_agent_id) sp.set("marketplace_agent_id", params.marketplace_agent_id);
  if (params?.runtime_status) sp.set("runtime_status", params.runtime_status);
  if (params?.adapter_type) sp.set("adapter_type", params.adapter_type);
  const qs = sp.toString();
  return fetchJSON<RuntimeBindingsResponse>(RA_BASE, `/bindings${qs ? `?${qs}` : ""}`);
}

export async function createRuntimeBinding(payload: { marketplace_agent_id: string; adapter_id?: string; sandbox_policy_id?: string | null; metadata?: Record<string, unknown> }) {
  return fetchJSON<RuntimeBindingActionResponse>(RA_BASE, "/bindings", { method: "POST", body: JSON.stringify(payload) });
}

export async function getRuntimeBinding(bindingId: string) {
  return fetchJSON<RuntimeBindingDetailResponse>(RA_BASE, `/${encodeURIComponent(bindingId)}`);
}

export async function enableRuntimeBinding(bindingId: string) {
  return fetchJSON<RuntimeBindingActionResponse>(RA_BASE, `/bindings/${encodeURIComponent(bindingId)}/enable`, { method: "POST", body: "{}" });
}

export async function disableRuntimeBinding(bindingId: string) {
  return fetchJSON<RuntimeBindingActionResponse>(RA_BASE, `/bindings/${encodeURIComponent(bindingId)}/disable`, { method: "POST", body: "{}" });
}

export async function suspendRuntimeBinding(bindingId: string) {
  return fetchJSON<RuntimeBindingActionResponse>(RA_BASE, `/bindings/${encodeURIComponent(bindingId)}/suspend`, { method: "POST", body: "{}" });
}

export async function assignRuntimeBindingSandboxPolicy(bindingId: string, sandboxPolicyId: string) {
  return fetchJSON<RuntimeBindingActionResponse>(RA_BASE, `/bindings/${encodeURIComponent(bindingId)}/sandbox-policy`, { method: "POST", body: JSON.stringify({ sandbox_policy_id: sandboxPolicyId }) });
}

export async function getRuntimeEligibility(marketplaceAgentId: string, tenantId?: string) {
  const qs = tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : "";
  return fetchJSON<RuntimeEligibilityResult>(RA_BASE, `/developer-agents/${encodeURIComponent(marketplaceAgentId)}/eligibility${qs}`);
}

// ── Sandbox Policies ──
export async function listSandboxPolicies(params?: { status?: string; scope?: string }) {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.scope) sp.set("scope", params.scope);
  const qs = sp.toString();
  return fetchJSON<SandboxPoliciesResponse>(SP_BASE, `${qs ? `?${qs}` : ""}`);
}

export async function getSandboxPolicy(policyId: string) {
  return fetchJSON<{ policy: SandboxPolicy }>(SP_BASE, `/${encodeURIComponent(policyId)}`);
}

export async function createSandboxPolicy(payload: Record<string, unknown>) {
  return fetchJSON<{ policy: SandboxPolicy }>(SP_BASE, "", { method: "POST", body: JSON.stringify(payload) });
}

export async function updateSandboxPolicy(policyId: string, payload: Record<string, unknown>) {
  return fetchJSON<{ policy: SandboxPolicy }>(SP_BASE, `/${encodeURIComponent(policyId)}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function testSandboxPolicy(policyId: string, payload: SandboxPolicyTestRequest) {
  return fetchJSON<SandboxPolicyTestResult>(SP_BASE, `/${encodeURIComponent(policyId)}/test`, { method: "POST", body: JSON.stringify(payload) });
}

export async function enableSandboxPolicy(policyId: string) {
  return fetchJSON<{ success: boolean }>(SP_BASE, `/${encodeURIComponent(policyId)}/enable`, { method: "POST", body: "{}" });
}

export async function disableSandboxPolicy(policyId: string) {
  return fetchJSON<{ success: boolean }>(SP_BASE, `/${encodeURIComponent(policyId)}/disable`, { method: "POST", body: "{}" });
}
