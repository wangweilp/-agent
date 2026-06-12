/** Agent Marketplace — 类型定义
 *
 * 与后端 /agent-marketplace API 的响应结构保持一致。
 * 不污染 Internal Agent Center (agents.ts) 的类型空间。
 */

// ═══════════════════════════════════════════
// Marketplace Agent
// ═══════════════════════════════════════════

export interface MarketplaceAgent {
  marketplace_agent_id: string;
  agent_id: string;
  name: string;
  display_name: string;
  description: string;
  long_description: string;
  category: string;
  department: string | null;
  capabilities: string[];
  required_permissions: string[];
  supported_workflows: string[];
  version: string;
  publisher_type: string;
  publisher_name: string;
  icon: string | null;
  visibility: string;
  pricing_model: string;
  usage_limits: Record<string, unknown>;
  install_count: number;
  rating: number;
  status: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  /** 仅在 browse/list 响应中返回：当前 tenant/workspace 的安装状态 */
  is_installed?: boolean;
  installation?: TenantAgentInstallation | null;
}

// ═══════════════════════════════════════════
// Tenant Agent Installation
// ═══════════════════════════════════════════

export interface TenantAgentInstallation {
  installation_id: string;
  tenant_id: string;
  workspace_id: string;
  marketplace_agent_id: string;
  agent_id: string;
  installed_by: string;
  installed_at: string | null;
  status: string;
  enabled: boolean;
  config: Record<string, unknown>;
  permissions_granted: string[];
  usage_limit_override: Record<string, unknown>;
  version_pinned: string | null;
  created_at: string;
  updated_at: string;
}

// ═══════════════════════════════════════════
// API Response Types
// ═══════════════════════════════════════════

export interface MarketplaceListResponse {
  agents: MarketplaceAgent[];
  total: number;
  categories: string[];
  departments: string[];
}

export interface MarketplaceDetailResponse {
  agent: MarketplaceAgent;
  is_installed: boolean;
  installation: TenantAgentInstallation | null;
}

export interface MarketplaceCategoriesResponse {
  categories: string[];
}

export interface MarketplaceDepartmentsResponse {
  departments: string[];
}

export interface MarketplaceInstallationsResponse {
  installations: TenantAgentInstallation[];
  total: number;
}

export interface MarketplacePermissionsResponse {
  required: string[];
  granted: string[];
  missing: string[];
}

export interface MarketplaceUsageResponse {
  installation_id: string;
  agent_id: string;
  marketplace_agent_id: string;
  total_calls: number;
  period_calls: number;
  install_events: number;
  last_used_at: string | null;
  limit: number | null;
  remaining: number | null;
  billing_note: string;
}

// ═══════════════════════════════════════════
// Analytics
// ═══════════════════════════════════════════

export interface MarketplaceAnalyticsSummary {
  total_marketplace_agents: number;
  installed_agents: number;
  enabled_installations: number;
  disabled_installations: number;
  install_events: number;
  agent_runs: number;
  top_categories: Record<string, number>;
  top_agents: Record<string, number>;
  billing_note: string;
}

// ═══════════════════════════════════════════
// Request Types
// ═══════════════════════════════════════════

export interface MarketplaceInstallRequest {
  workspace_id?: string;
  config?: Record<string, unknown>;
  permissions_granted?: string[];
  usage_limit_override?: Record<string, unknown>;
  version_pinned?: string | null;
}

export interface MarketplaceConfigRequest {
  config?: Record<string, unknown>;
  permissions_granted?: string[];
  usage_limit_override?: Record<string, unknown>;
  version_pinned?: string | null;
}

// ═══════════════════════════════════════════
// Browse Params
// ═══════════════════════════════════════════

export interface MarketplaceBrowseParams {
  category?: string;
  department?: string;
  status?: string;
  visibility?: string;
  installed?: boolean;
}

export interface MarketplaceInstallationsParams {
  workspace_id?: string;
  include_disabled?: boolean;
}
