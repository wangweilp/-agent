/** Open Platform Developer API Client — /developers 端点。 */

import { getAccessToken } from "@/stores/auth-store";
import { API_BASE_URL } from "./api";
import type {
  ApiKeyListResponse,
  CreateApiKeyRequest,
  CreateApiKeyResponse,
  CreateSubmissionRequest,
  DeveloperMeResponse,
  DeveloperRegisterRequest,
  DeveloperUpdateRequest,
  SubmissionDetailResponse,
  SubmissionListResponse,
  UpdateSubmissionRequest,
  ValidateSubmissionResponse,
  VerifyRequestResponse,
} from "@/types/open-platform";

const API_BASE = API_BASE_URL;
const DEV_API_BASE = `${API_BASE}/developers`;

export class DeveloperApiError extends Error {
  constructor(public status: number, message: string, public detail: unknown = null) {
    super(message);
    this.name = "DeveloperApiError";
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  const t = getAccessToken();
  if (t) return t;
  try {
    const raw = localStorage.getItem("agent-os-auth");
    if (!raw) return null;
    return JSON.parse(raw)?.state?.token?.access_token || null;
  } catch { return null; }
}

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${DEV_API_BASE}${path}`, { ...init, headers });
  const raw = await res.text();

  if (!res.ok) {
    let message = `[${res.status}]`;
    let detail: unknown = null;
    try {
      const parsed = JSON.parse(raw);
      detail = parsed.detail || parsed;
      message = typeof detail === "string" ? `${message} ${detail}` : `${message} ${parsed.detail?.message || parsed.message || raw.slice(0, 200)}`;
    } catch { message = `${message} ${raw.slice(0, 200)}`; }
    throw new DeveloperApiError(res.status, message, detail);
  }
  if (!raw.trim()) return {} as T;
  return JSON.parse(raw) as T;
}

// ═══════════════════════════════════════════
// Developer Account
// ═══════════════════════════════════════════

export async function registerDeveloper(payload: DeveloperRegisterRequest): Promise<DeveloperMeResponse> {
  return fetchJSON<DeveloperMeResponse>("/register", { method: "POST", body: JSON.stringify(payload) });
}

export async function getDeveloperMe(): Promise<DeveloperMeResponse> {
  return fetchJSON<DeveloperMeResponse>("/me");
}

export async function updateDeveloperMe(payload: DeveloperUpdateRequest): Promise<DeveloperMeResponse> {
  return fetchJSON<DeveloperMeResponse>("/me", { method: "PATCH", body: JSON.stringify(payload) });
}

export async function requestDeveloperVerification(): Promise<VerifyRequestResponse> {
  return fetchJSON<VerifyRequestResponse>("/me/verify-request", { method: "POST" });
}

// ═══════════════════════════════════════════
// API Keys
// ═══════════════════════════════════════════

export async function createDeveloperApiKey(payload: CreateApiKeyRequest): Promise<CreateApiKeyResponse> {
  return fetchJSON<CreateApiKeyResponse>("/api-keys", { method: "POST", body: JSON.stringify(payload) });
}

export async function listDeveloperApiKeys(includeRevoked = false): Promise<ApiKeyListResponse> {
  const qs = includeRevoked ? "?include_revoked=true" : "";
  return fetchJSON<ApiKeyListResponse>(`/api-keys${qs}`);
}

export async function revokeDeveloperApiKey(apiKeyId: string): Promise<{ success: boolean }> {
  return fetchJSON<{ success: boolean }>(`/api-keys/${encodeURIComponent(apiKeyId)}`, { method: "DELETE" });
}

// ═══════════════════════════════════════════
// Agent Submissions
// ═══════════════════════════════════════════

export async function createDeveloperSubmission(payload: CreateSubmissionRequest): Promise<SubmissionDetailResponse> {
  return fetchJSON<SubmissionDetailResponse>("/agents", { method: "POST", body: JSON.stringify(payload) });
}

export async function listDeveloperSubmissions(params?: { status?: string; include_withdrawn?: boolean }): Promise<SubmissionListResponse> {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.include_withdrawn) sp.set("include_withdrawn", "true");
  const qs = sp.toString();
  return fetchJSON<SubmissionListResponse>(`/agents${qs ? `?${qs}` : ""}`);
}

export async function getDeveloperSubmission(submissionId: string): Promise<SubmissionDetailResponse> {
  return fetchJSON<SubmissionDetailResponse>(`/agents/${encodeURIComponent(submissionId)}`);
}

export async function updateDeveloperSubmission(submissionId: string, payload: UpdateSubmissionRequest): Promise<SubmissionDetailResponse> {
  return fetchJSON<SubmissionDetailResponse>(`/agents/${encodeURIComponent(submissionId)}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function validateDeveloperSubmission(submissionId: string): Promise<ValidateSubmissionResponse> {
  return fetchJSON<ValidateSubmissionResponse>(`/agents/${encodeURIComponent(submissionId)}/validate`, { method: "POST" });
}

export async function submitDeveloperSubmission(submissionId: string): Promise<SubmissionDetailResponse> {
  return fetchJSON<SubmissionDetailResponse>(`/agents/${encodeURIComponent(submissionId)}/submit`, { method: "POST", body: "{}" });
}

export async function withdrawDeveloperSubmission(submissionId: string): Promise<SubmissionDetailResponse> {
  return fetchJSON<SubmissionDetailResponse>(`/agents/${encodeURIComponent(submissionId)}/withdraw`, { method: "POST", body: "{}" });
}
