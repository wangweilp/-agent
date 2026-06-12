/** Admin Review API Client — /admin/agent-submissions 端点。 */

import { getAccessToken } from "@/stores/auth-store";
import type {
  AdminReviewListResponse,
  AdminSubmissionDetailResponse,
  AdminSubmissionListResponse,
  PublishSubmissionResponse,
  ReviewActionRequest,
  SubmissionDetailResponse,
} from "@/types/open-platform";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const AR_API_BASE = `${API_BASE}/admin/agent-submissions`;

export class AdminReviewApiError extends Error {
  constructor(public status: number, message: string, public detail: unknown = null) {
    super(message);
    this.name = "AdminReviewApiError";
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

  const res = await fetch(`${AR_API_BASE}${path}`, { ...init, headers });
  const raw = await res.text();

  if (!res.ok) {
    let msg = `[${res.status}]`;
    let detail: unknown = null;
    try {
      const parsed = JSON.parse(raw);
      detail = parsed.detail || parsed;
      msg = typeof detail === "string" ? `${msg} ${detail}` : `${msg} ${JSON.stringify(detail).slice(0, 300)}`;
    } catch { msg = `${msg} ${raw.slice(0, 200)}`; }
    throw new AdminReviewApiError(res.status, msg, detail);
  }
  if (!raw.trim()) return {} as T;
  return JSON.parse(raw) as T;
}

export async function listAdminSubmissions(params?: { status?: string; tenant_id?: string; developer_id?: string }): Promise<AdminSubmissionListResponse> {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.tenant_id) sp.set("tenant_id", params.tenant_id);
  if (params?.developer_id) sp.set("developer_id", params.developer_id);
  const qs = sp.toString();
  return fetchJSON<AdminSubmissionListResponse>(qs ? `?${qs}` : "");
}

export async function getAdminSubmission(submissionId: string): Promise<AdminSubmissionDetailResponse> {
  return fetchJSON<AdminSubmissionDetailResponse>(`/${encodeURIComponent(submissionId)}`);
}

export async function listAdminSubmissionReviews(submissionId: string): Promise<AdminReviewListResponse> {
  return fetchJSON<AdminReviewListResponse>(`/${encodeURIComponent(submissionId)}/reviews`);
}

export async function startAdminSubmissionReview(submissionId: string): Promise<SubmissionDetailResponse> {
  return fetchJSON<SubmissionDetailResponse>(`/${encodeURIComponent(submissionId)}/start-review`, { method: "POST", body: "{}" });
}

export async function approveAdminSubmission(submissionId: string, payload: ReviewActionRequest): Promise<SubmissionDetailResponse> {
  return fetchJSON<SubmissionDetailResponse>(`/${encodeURIComponent(submissionId)}/approve`, { method: "POST", body: JSON.stringify(payload) });
}

export async function rejectAdminSubmission(submissionId: string, payload: ReviewActionRequest): Promise<SubmissionDetailResponse> {
  return fetchJSON<SubmissionDetailResponse>(`/${encodeURIComponent(submissionId)}/reject`, { method: "POST", body: JSON.stringify(payload) });
}

export async function requestChangesAdminSubmission(submissionId: string, payload: ReviewActionRequest): Promise<SubmissionDetailResponse> {
  return fetchJSON<SubmissionDetailResponse>(`/${encodeURIComponent(submissionId)}/request-changes`, { method: "POST", body: JSON.stringify(payload) });
}

// Step 22-H: Publish
export async function publishAdminSubmission(submissionId: string): Promise<PublishSubmissionResponse> {
  return fetchJSON<PublishSubmissionResponse>(`/${encodeURIComponent(submissionId)}/publish`, { method: "POST", body: "{}" });
}

// Step 23-F: Package Validation
export async function validateSubmissionPackage(submissionId: string, validationOptions?: Record<string, unknown>) {
  return fetchJSON<Record<string, unknown>>(`/${encodeURIComponent(submissionId)}/validate-package`, { method: "POST", body: JSON.stringify({ validation_options: validationOptions }) });
}

export async function getSubmissionPackageValidation(submissionId: string): Promise<{ validation: Record<string, unknown> | null }> {
  return fetchJSON<{ validation: Record<string, unknown> | null }>(`/${encodeURIComponent(submissionId)}/package-validation`);
}
