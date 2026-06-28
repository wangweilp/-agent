/** Agent Marketplace API Client
 *
 * 与后端 /agent-marketplace API 对接。
 * 复用现有 auth token 机制，与 agents.ts 独立的 API base。
 */

import { getAccessToken } from "@/stores/auth-store";
import { API_BASE_URL } from "./api";
import type {
  MarketplaceAnalyticsSummary,
  MarketplaceBrowseParams,
  MarketplaceConfigRequest,
  MarketplaceDetailResponse,
  MarketplaceInstallRequest,
  MarketplaceInstallationsParams,
  MarketplaceInstallationsResponse,
  MarketplaceListResponse,
  MarketplacePermissionsResponse,
  MarketplaceUsageResponse,
  TenantAgentInstallation,
} from "@/types/marketplace";

const API_BASE = API_BASE_URL;
const MKP_API_BASE = `${API_BASE}/agent-marketplace`;

export class MarketplaceApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "MarketplaceApiError";
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;

  const moduleToken = getAccessToken();
  if (moduleToken) return moduleToken;

  try {
    const raw = localStorage.getItem("agent-os-auth");
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.state?.token?.access_token || null;
  } catch {
    return null;
  }
}

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string>) || {}),
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${MKP_API_BASE}${path}`, { ...init, headers });
  const raw = await res.text();

  if (!res.ok) {
    let message = `Marketplace API ${res.status}`;
    try {
      const parsed = JSON.parse(raw);
      message = parsed.detail || parsed.message || message;
    } catch {
      if (raw.trim()) message = raw.trim().slice(0, 300);
    }
    throw new MarketplaceApiError(res.status, message);
  }

  if (!raw.trim()) return {} as T;

  try {
    return JSON.parse(raw) as T;
  } catch {
    throw new MarketplaceApiError(res.status, "Marketplace API 返回的不是有效 JSON");
  }
}

// ═══════════════════════════════════════════
// Browse & Discover
// ═══════════════════════════════════════════

export async function listMarketplaceAgents(
  params?: MarketplaceBrowseParams,
): Promise<MarketplaceListResponse> {
  const sp = new URLSearchParams();
  if (params?.category) sp.set("category", params.category);
  if (params?.department) sp.set("department", params.department);
  if (params?.status) sp.set("status", params.status);
  if (params?.visibility) sp.set("visibility", params.visibility);
  if (params?.installed !== undefined) sp.set("installed", String(params.installed));
  const qs = sp.toString();
  return fetchJSON<MarketplaceListResponse>(qs ? `?${qs}` : "");
}

export async function getMarketplaceAgent(
  marketplaceAgentId: string,
): Promise<MarketplaceDetailResponse> {
  return fetchJSON<MarketplaceDetailResponse>(`/${encodeURIComponent(marketplaceAgentId)}`);
}

export async function getMarketplaceCategories(): Promise<string[]> {
  const data = await fetchJSON<{ categories: string[] }>("/categories");
  return data.categories;
}

export async function getMarketplaceDepartments(): Promise<string[]> {
  const data = await fetchJSON<{ departments: string[] }>("/departments");
  return data.departments;
}

// ═══════════════════════════════════════════
// Installation Management
// ═══════════════════════════════════════════

export async function installMarketplaceAgent(
  marketplaceAgentId: string,
  payload: MarketplaceInstallRequest,
): Promise<{ installation: TenantAgentInstallation; agent: Record<string, unknown> }> {
  return fetchJSON(`/${encodeURIComponent(marketplaceAgentId)}/install`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listMarketplaceInstallations(
  params?: MarketplaceInstallationsParams,
): Promise<MarketplaceInstallationsResponse> {
  const sp = new URLSearchParams();
  if (params?.workspace_id) sp.set("workspace_id", params.workspace_id);
  if (params?.include_disabled !== undefined) sp.set("include_disabled", String(params.include_disabled));
  const qs = sp.toString();
  return fetchJSON<MarketplaceInstallationsResponse>(`/installations${qs ? `?${qs}` : ""}`);
}

export async function getMarketplaceInstallation(
  installationId: string,
): Promise<{ installation: TenantAgentInstallation; agent: Record<string, unknown> | null }> {
  return fetchJSON(`/installations/${encodeURIComponent(installationId)}`);
}

export async function enableMarketplaceInstallation(
  installationId: string,
): Promise<{ installation: TenantAgentInstallation }> {
  return fetchJSON(`/installations/${encodeURIComponent(installationId)}/enable`, { method: "POST" });
}

export async function disableMarketplaceInstallation(
  installationId: string,
): Promise<{ installation: TenantAgentInstallation }> {
  return fetchJSON(`/installations/${encodeURIComponent(installationId)}/disable`, { method: "POST" });
}

export async function updateMarketplaceInstallationConfig(
  installationId: string,
  payload: MarketplaceConfigRequest,
): Promise<{ installation: TenantAgentInstallation }> {
  return fetchJSON(`/installations/${encodeURIComponent(installationId)}/config`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function uninstallMarketplaceInstallation(
  installationId: string,
): Promise<{ success: boolean }> {
  return fetchJSON(`/installations/${encodeURIComponent(installationId)}`, { method: "DELETE" });
}

// ═══════════════════════════════════════════
// Permissions & Usage
// ═══════════════════════════════════════════

export async function getMarketplaceAgentPermissions(
  marketplaceAgentId: string,
): Promise<MarketplacePermissionsResponse> {
  return fetchJSON<MarketplacePermissionsResponse>(
    `/${encodeURIComponent(marketplaceAgentId)}/permissions`,
  );
}

export async function getMarketplaceInstallationUsage(
  installationId: string,
): Promise<MarketplaceUsageResponse> {
  return fetchJSON<MarketplaceUsageResponse>(
    `/installations/${encodeURIComponent(installationId)}/usage`,
  );
}

// ═══════════════════════════════════════════
// Analytics
// ═══════════════════════════════════════════

export async function getMarketplaceAnalyticsSummary(): Promise<MarketplaceAnalyticsSummary> {
  return fetchJSON<MarketplaceAnalyticsSummary>("/analytics/summary");
}
