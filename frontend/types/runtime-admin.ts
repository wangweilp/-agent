/** Runtime Admin — Step 23-G 类型定义 */

// ═══════════════════ Runtime Adapter ═══════════════════
export interface RuntimeAdapter {
  adapter_id: string;
  adapter_type: string;    // manifest_only | simulation | http_webhook | sandboxed_process | container
  name: string;
  description: string;
  supports_network: boolean;
  supports_user_data_read: boolean;
  supports_user_data_write: boolean;
  sandbox_required: boolean;
  max_timeout_ms: number;
  max_memory_mb: number;
  status: string;         // active | beta | disabled | deprecated
  version: string;
  config_schema: Record<string, unknown>;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// ═══════════════════ Runtime Binding ═══════════════════
export interface DeveloperAgentRuntimeBinding {
  binding_id: string;
  marketplace_agent_id: string;
  submission_id: string | null;
  developer_id: string;
  tenant_id: string;
  adapter_id: string;
  adapter_type: string;
  runtime_status: string;  // pending | enabled | disabled | suspended
  sandbox_policy_id: string | null;
  enabled_by: string | null;
  disabled_by: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// ═══════════════════ Eligibility ═══════════════════
export interface RuntimeEligibilityResult {
  eligible: boolean;
  code: string;
  message: string;
  marketplace_agent_id: string;
  binding_id: string | null;
  adapter_id: string | null;
  adapter_type: string | null;
  required_action: string | null;
  metadata: Record<string, unknown>;
}

// ═══════════════════ Sandbox Policy ═══════════════════
export interface SandboxPolicy {
  policy_id: string;
  name: string;
  description: string;
  scope: string;          // system | tenant
  tenant_id: string | null;
  sandbox_level: string;  // no_execution | simulation_only | restricted | isolated
  allow_network: boolean;
  allowed_domains: string[];
  allow_filesystem_read: boolean;
  allow_filesystem_write: boolean;
  allowed_paths: string[];
  allow_secrets: boolean;
  allowed_secret_names: string[];
  max_timeout_ms: number;
  max_memory_mb: number;
  max_cpu_percent: number;
  max_output_bytes: number;
  max_requests_per_minute: number;
  data_access_scope: string[];
  audit_enabled: boolean;
  kill_switch_enabled: boolean;
  status: string;         // active | disabled | deprecated
  system_managed: boolean;
  created_by: string | null;
  updated_by: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SandboxPolicyTestRequest {
  sandbox_level: string;
  requested_network: boolean;
  requested_domains: string[];
  requested_filesystem_read: boolean;
  requested_filesystem_write: boolean;
  requested_secret_names: string[];
  requested_timeout_ms: number;
  requested_memory_mb: number;
  requested_data_access_scope: string[];
}

export interface SandboxPolicyTestResult {
  policy_id: string;
  decision: string;
  allowed: boolean;
  warnings: string[];
  violations: string[];
  evaluated_rules: string[];
  metadata: Record<string, unknown>;
}

// ═══════════════════ Package Validation ═══════════════════
export interface PackageValidationCheck {
  check_id: string;
  code: string;
  severity: string;  // info | warning | error | blocker
  passed: boolean;
  message: string;
  metadata: Record<string, unknown>;
}

export interface PackageValidationResult {
  validation_id: string;
  submission_id: string;
  tenant_id: string;
  requested_by: string;
  status: string;     // not_validated | passed | passed_with_warnings | failed | blocked
  source_type: string;
  package_url: string | null;
  repository_url: string | null;
  manifest_name: string;
  manifest_version: string;
  checks: PackageValidationCheck[];
  warnings: string[];
  errors: string[];
  blockers: string[];
  package_metadata: Record<string, unknown>;
  review_recommendation: string;
  no_download_performed: boolean;
  no_execution_performed: boolean;
  no_network_performed: boolean;
  summary: { total: number; passed: number; failed: number; warnings: number; errors: number; blockers: number };
  created_at: string;
  completed_at: string | null;
  metadata: Record<string, unknown>;
}

// ═══════════════════ API Response Wrappers ═══════════════════
export interface RuntimeAdaptersResponse { adapters: RuntimeAdapter[]; total: number; }
export interface RuntimeBindingsResponse { bindings: DeveloperAgentRuntimeBinding[]; total: number; }
export interface RuntimeBindingDetailResponse {
  binding: DeveloperAgentRuntimeBinding;
  adapter: RuntimeAdapter | null;
  eligibility: RuntimeEligibilityResult;
}
export interface RuntimeBindingActionResponse { binding: DeveloperAgentRuntimeBinding | null; message?: string; }
export interface SandboxPoliciesResponse { policies: SandboxPolicy[]; total: number; }
export interface PackageValidationResponse { validation: PackageValidationResult | null; }
